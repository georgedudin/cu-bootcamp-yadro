"""Speech recognition, chunk diarization and cross-chunk speaker stitching.

The heavy ML imports are intentionally lazy: the reduce worker can stitch
already-computed embeddings without loading Whisper, pyannote or SpeechBrain.
Models are cached per worker process, which is safe because RQ uses
``SimpleWorker`` and also avoids reloading several gigabytes for every chunk.
"""

from __future__ import annotations

import logging
import math
import os
import re
import wave
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urlparse

from contracts import (
    ChunkResult,
    ChunkSegment,
    ChunkWindow,
    EMBEDDING_DIM,
    SpeakerRole,
    StitchResult,
    StitchSpeaker,
    TimelineSegment,
    TranscribeChunkJob,
    Turn,
    Word,
)

log = logging.getLogger(__name__)

_MIN_EMBEDDING_AUDIO_S = 0.5
_DEFAULT_CLUSTER_DISTANCE = 0.72


def _normalise(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 1e-12:
        return [0.0] * len(vector)
    return [value / norm for value in vector]


def _local_wav_path(uri: str) -> Path:
    parsed = urlparse(uri)
    if parsed.scheme not in ("", "file"):
        raise ValueError(f"wav_uri must be a local path or file URI, got {parsed.scheme!r}")
    if parsed.scheme == "file":
        from urllib.request import url2pathname

        path = url2pathname(unquote(parsed.path))
        if parsed.netloc:
            path = f"//{parsed.netloc}{path}"
        return Path(path)
    return Path(uri)


def _read_wav_window(job: TranscribeChunkJob):
    """Read only the requested PCM window and return mono float32 samples."""
    import numpy as np

    path = _local_wav_path(job.wav_uri)
    with wave.open(str(path), "rb") as wav:
        sample_rate = wav.getframerate()
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        if sample_rate != job.target_sr:
            raise ValueError(
                f"Expected {job.target_sr} Hz canonical WAV, got {sample_rate} Hz"
            )
        if sample_width not in (1, 2, 3, 4):
            raise ValueError(f"Unsupported PCM sample width: {sample_width} bytes")

        first_frame = max(0, round(job.start_s * sample_rate))
        last_frame = min(wav.getnframes(), round(job.end_s * sample_rate))
        wav.setpos(min(first_frame, wav.getnframes()))
        raw = wav.readframes(max(0, last_frame - first_frame))

    if sample_width == 1:
        samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sample_width == 2:
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sample_width == 3:
        packed = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        values = (
            packed[:, 0].astype(np.int32)
            | (packed[:, 1].astype(np.int32) << 8)
            | (packed[:, 2].astype(np.int32) << 16)
        )
        values = np.where(values & 0x800000, values - 0x1000000, values)
        samples = values.astype(np.float32) / 8388608.0
    else:
        samples = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0

    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return np.ascontiguousarray(samples, dtype=np.float32), sample_rate


def _device() -> str:
    configured = os.getenv("ML_DEVICE", "auto").lower()
    if configured != "auto":
        return configured
    import torch

    return "cuda" if torch.cuda.is_available() else "cpu"


@lru_cache(maxsize=4)
def _whisper_model(model_name: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel

    return WhisperModel(model_name, device=device, compute_type=compute_type)


def _patch_huggingface_hub_for_pyannote() -> None:
    """Bridge pyannote.audio 3.x to huggingface_hub 1.x.

    pyannote 3.x calls ``hf_hub_download(use_auth_token=...)`` while
    huggingface_hub 1.x renamed that argument to ``token``. Patching before
    importing pyannote also fixes the function reference copied into
    ``pyannote.audio.core.pipeline``.
    """
    import inspect
    from functools import wraps

    import huggingface_hub

    original = huggingface_hub.hf_hub_download
    if (
        "use_auth_token" in inspect.signature(original).parameters
        or getattr(original, "_pyannote_auth_compat", False)
    ):
        return

    @wraps(original)
    def compatible_hf_hub_download(*args, use_auth_token=None, **kwargs):
        if use_auth_token is not None:
            kwargs.setdefault("token", use_auth_token)
        return original(*args, **kwargs)

    compatible_hf_hub_download._pyannote_auth_compat = True
    huggingface_hub.hf_hub_download = compatible_hf_hub_download


@lru_cache(maxsize=2)
def _diarization_pipeline(model_name: str, device: str):
    # torchaudio 2.9 removed its legacy metadata/backend names while
    # pyannote.audio 3.x still imports them. This pipeline always passes an
    # in-memory waveform, so pyannote only needs the names for annotations and
    # backend selection; no removed torchaudio file-I/O function is called.
    import torchaudio
    import torch
    if not hasattr(torchaudio, "AudioMetaData"):
        from collections import namedtuple

        torchaudio.AudioMetaData = namedtuple(  # type: ignore[attr-defined]
            "AudioMetaData",
            "sample_rate num_frames num_channels bits_per_sample encoding",
        )
    if not hasattr(torchaudio, "list_audio_backends"):
        torchaudio.list_audio_backends = lambda: ["soundfile"]  # type: ignore[attr-defined]

    # Official pyannote 3.x checkpoints contain this harmless version value.
    # PyTorch 2.6+ defaults torch.load to weights_only=True, so it must be
    # explicitly allowlisted before Lightning loads the trusted checkpoint.
    from torch.torch_version import TorchVersion

    _patch_huggingface_hub_for_pyannote()
    from pyannote.audio import Pipeline
    from pyannote.audio.core.task import Problem, Resolution, Specifications

    torch.serialization.add_safe_globals(
        [TorchVersion, Specifications, Problem, Resolution]
    )

    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")
    pipeline = Pipeline.from_pretrained(
        model_name,
        **({"use_auth_token": token} if token else {}),
    )
    if pipeline is None:
        raise RuntimeError(
            f"Could not load gated pyannote model {model_name!r}; "
            "accept its Hugging Face terms and provide HF_TOKEN"
        )
    pipeline.to(torch.device(device))
    return pipeline


@lru_cache(maxsize=2)
def _speaker_encoder(model_name: str, device: str):
    try:
        from speechbrain.inference.speaker import EncoderClassifier
    except ImportError:  # SpeechBrain < 1.0
        from speechbrain.pretrained import EncoderClassifier

    savedir = os.getenv("ECAPA_CACHE_DIR")
    kwargs = {"source": model_name, "run_opts": {"device": device}}
    if savedir:
        kwargs["savedir"] = savedir
    return EncoderClassifier.from_hparams(**kwargs)


# Public loaders: env resolution lives here so warmup / worker-boot preload hit
# the SAME lru_cache keys the per-job path uses — a preloaded model is never
# reloaded on the first real chunk.

def get_whisper(device: str | None = None):
    return _whisper_model(
        os.getenv("ASR_MODEL", "large-v3"),
        device or _device(),
        os.getenv("ASR_COMPUTE_TYPE", "int8"),
    )


def get_diarizer(device: str | None = None):
    return _diarization_pipeline(
        os.getenv("DIARIZATION_MODEL", "pyannote/speaker-diarization-3.1"),
        device or _device(),
    )


def get_encoder(device: str | None = None):
    return _speaker_encoder(
        os.getenv("ECAPA_MODEL", "speechbrain/spkrec-ecapa-voxceleb"),
        device or _device(),
    )


def preload_chunk_models() -> None:
    """Load ASR + diarization + embedding models AND push ~1 s of silence
    through each (worker boot / deploy warmup).

    Loading alone is NOT enough: CTranslate2 dlopens cuBLAS at the first
    encode, not in the constructor — a machine that can load models but not
    infer (wrong CUDA sonames, exhausted VRAM) must fail HERE, loudly,
    instead of surfacing as per-job retry churn."""
    import numpy as np
    import torch

    device = _device()
    log.info("preloading chunk models on device=%s", device)
    silence = np.zeros(16000, dtype=np.float32)  # 1 s @ the canonical 16 kHz
    segments, _ = get_whisper(device).transcribe(silence, beam_size=1)
    list(segments)  # consume the generator: forces the encoder GEMM
    get_diarizer(device)(
        {"waveform": torch.from_numpy(silence).unsqueeze(0), "sample_rate": 16000}
    )
    with torch.inference_mode():
        get_encoder(device).encode_batch(
            torch.from_numpy(silence).unsqueeze(0).to(device)
        )
    log.info("chunk models ready (smoke inference passed)")


def _iter_diarization(annotation):
    # community-1 wraps the Annotation, while speaker-diarization-3.1 returns
    # the Annotation directly.
    annotation = getattr(annotation, "speaker_diarization", annotation)
    for segment, _, label in annotation.itertracks(yield_label=True):
        yield float(segment.start), float(segment.end), str(label)


def _overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))


def transcribe_chunk(job: TranscribeChunkJob) -> ChunkResult:
    """Transcribe, diarize and embed one absolute recording window."""
    import numpy as np
    import torch

    audio, sample_rate = _read_wav_window(job)
    if audio.size == 0:
        return ChunkResult(
            recording_id=job.recording_id,
            chunk_index=job.chunk_index,
            segments=[],
            turns=[],
        )

    device = _device()
    whisper = get_whisper(device)
    asr_segments, _ = whisper.transcribe(
        audio,
        language=os.getenv("ASR_LANGUAGE") or None,
        word_timestamps=True,
        vad_filter=True,
        beam_size=int(os.getenv("ASR_BEAM_SIZE", "5")),
    )
    # faster-whisper returns a generator; consume it before reusing the audio
    # in the other models.
    asr_segments = list(asr_segments)

    waveform = torch.from_numpy(audio).unsqueeze(0)
    diarizer = get_diarizer(device)
    diarization = diarizer({"waveform": waveform, "sample_rate": sample_rate})
    local_turns = list(_iter_diarization(diarization))
    if not local_turns:
        # Rare fallback for a failed/empty diarization pass: keep the ASR
        # usable and derive one local voice from its detected speech regions.
        local_turns = [
            (float(segment.start), float(segment.end), "SPEAKER_00")
            for segment in asr_segments
            if float(segment.end) > float(segment.start)
        ]

    encoder = get_encoder(device)
    turns: list[Turn] = []
    for local_start, local_end, label in local_turns:
        local_start = max(0.0, local_start)
        local_end = min(len(audio) / sample_rate, local_end)
        if local_end <= local_start:
            continue
        first = int(local_start * sample_rate)
        last = max(first + 1, int(local_end * sample_rate))
        clip = audio[first:last]
        min_samples = max(1, round(_MIN_EMBEDDING_AUDIO_S * sample_rate))
        if len(clip) < min_samples:
            clip = np.pad(clip, (0, min_samples - len(clip)))
        with torch.inference_mode():
            embedding = encoder.encode_batch(
                torch.from_numpy(np.ascontiguousarray(clip)).unsqueeze(0).to(device)
            )
        vector = embedding.detach().float().cpu().reshape(-1).tolist()
        if len(vector) != EMBEDDING_DIM:
            raise RuntimeError(
                f"ECAPA returned {len(vector)} values; expected {EMBEDDING_DIM}"
            )
        turns.append(
            Turn(
                start=job.start_s + local_start,
                end=job.start_s + local_end,
                local_speaker=label,
                embedding=_normalise(vector),
            )
        )

    segments: list[ChunkSegment] = []
    for segment in asr_segments:
        local_start = max(0.0, float(segment.start))
        local_end = min(len(audio) / sample_rate, float(segment.end))
        if local_end <= local_start:
            continue
        overlaps = [
            (_overlap(local_start, local_end, start, end), label)
            for start, end, label in local_turns
        ]
        if overlaps:
            local_speaker = max(overlaps, key=lambda item: item[0])[1]
        else:
            # This only occurs when pyannote found no speech at all. Keeping a
            # deterministic label makes the contract useful for downstream
            # diagnostics instead of silently losing Whisper text.
            local_speaker = "SPEAKER_00"
        words = [
            Word(
                start=job.start_s + max(0.0, float(word.start)),
                end=job.start_s + min(len(audio) / sample_rate, float(word.end)),
                word=word.word,
            )
            for word in (segment.words or [])
            if word.start is not None and word.end is not None
        ]
        segments.append(
            ChunkSegment(
                start=job.start_s + local_start,
                end=job.start_s + local_end,
                text=segment.text.strip(),
                local_speaker=local_speaker,
                words=words,
            )
        )

    return ChunkResult(
        recording_id=job.recording_id,
        chunk_index=job.chunk_index,
        segments=segments,
        turns=turns,
    )


def _cluster_representatives(
    representatives: list[list[float]], expected_speakers: int | None
) -> list[int]:
    """Group (chunk, local-speaker) centroids into global speakers.

    ``expected_speakers`` is a CEILING, not an exact count. We cluster by
    natural voice distance first and only collapse down to the hint when MORE
    voices genuinely emerge — forcing exactly N shatters a dominant speaker
    (the teacher, present in nearly every chunk) into a fresh ID per chunk when
    the other students stay silent, which is the classic cross-chunk mismatch.

    ``SPEAKER_CLUSTER_DISTANCE`` is the one knob to tune on real audio: lower
    splits more (risks fragmenting one voice across chunks), higher merges more
    (risks fusing two students into one). The 0.72 default is a reasonable
    ECAPA cosine starting point — validate it against a labelled recording.
    """
    if expected_speakers is not None and expected_speakers < 1:
        raise ValueError("expected_speakers must be positive")
    if len(representatives) == 1:
        return [0]

    from sklearn.cluster import AgglomerativeClustering

    threshold = float(
        os.getenv("SPEAKER_CLUSTER_DISTANCE", str(_DEFAULT_CLUSTER_DISTANCE))
    )
    natural = [
        int(label)
        for label in AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=threshold,
            metric="cosine",
            linkage="average",
        ).fit_predict(representatives)
    ]
    if expected_speakers is None or len(set(natural)) <= expected_speakers:
        return natural

    # More natural voices than the hint allows — collapse to exactly the ceiling.
    ceiling = min(expected_speakers, len(representatives))
    log.info(
        "natural clustering found %d voices > hint %d — capping to %d",
        len(set(natural)), expected_speakers, ceiling,
    )
    return [
        int(label)
        for label in AgglomerativeClustering(
            n_clusters=ceiling, metric="cosine", linkage="average"
        ).fit_predict(representatives)
    ]


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if merged and start <= merged[-1][1] + 1e-3:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def _normalised_text(text: str) -> str:
    return re.sub(r"\W+", "", text, flags=re.UNICODE).casefold()


def _dedupe_segments(items):
    """Drop copies produced in overlapping windows, preserving real speech."""
    from difflib import SequenceMatcher

    kept = []
    for candidate in sorted(items, key=lambda item: (item["start"], item["chunk"])):
        duplicate_index = None
        for index in range(len(kept) - 1, -1, -1):
            previous = kept[index]
            if previous["end"] < candidate["start"] - 0.25:
                break
            if previous["chunk"] == candidate["chunk"]:
                continue
            if _overlap(
                previous["window_start"],
                previous["window_end"],
                candidate["window_start"],
                candidate["window_end"],
            ) <= 0:
                continue
            overlap = _overlap(
                previous["start"], previous["end"], candidate["start"], candidate["end"]
            )
            shorter = min(
                previous["end"] - previous["start"],
                candidate["end"] - candidate["start"],
            )
            if shorter <= 0 or overlap / shorter < 0.5:
                continue
            left = _normalised_text(previous["text"])
            right = _normalised_text(candidate["text"])
            similarity = SequenceMatcher(None, left, right).ratio() if left and right else 0.0
            if similarity >= 0.8:
                duplicate_index = index
                break
        if duplicate_index is None:
            kept.append(candidate)
        else:
            previous = kept[duplicate_index]
            # Prefer the copy with more text/words; it is usually the copy
            # farther from its chunk boundary.
            if len(candidate["text"]) > len(previous["text"]):
                kept[duplicate_index] = candidate
    return sorted(kept, key=lambda item: (item["start"], item["end"]))


def _cluster_for_time(
    t: float, chunk_turns: list[tuple[float, float, int]], fallback: int
) -> int:
    """Cluster of the diarization turn covering ``t`` (nearest turn if in a gap)."""
    for start, end, cluster in chunk_turns:
        if start <= t <= end:
            return cluster
    if chunk_turns:
        return min(
            chunk_turns, key=lambda turn: min(abs(t - turn[0]), abs(t - turn[1]))
        )[2]
    return fallback


def _split_segment_by_speaker(
    segment: ChunkSegment,
    chunk_turns: list[tuple[float, float, int]],
    fallback: int,
) -> list[dict]:
    """Cut one ASR segment at diarization speaker boundaries via word times.

    A single Whisper segment can straddle a speaker change — its span overlaps
    two turns — which would otherwise file two voices' words under one label and
    let the later same-speaker merge glue them into a mixed block. Assigning
    each WORD to the turn it falls in and splitting on change keeps every emitted
    piece single-speaker. Segments without word timings fall back to the old
    whole-segment assignment by maximum turn overlap.
    """
    words = [word for word in segment.words if word.end > word.start]
    if not words:
        candidates = [
            (_overlap(segment.start, segment.end, start, end), cluster)
            for start, end, cluster in chunk_turns
        ]
        positive = [candidate for candidate in candidates if candidate[0] > 0]
        cluster = max(positive, key=lambda item: item[0])[1] if positive else fallback
        return [
            {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
                "cluster": cluster,
            }
        ]

    runs: list[dict] = []
    for word in words:
        cluster = _cluster_for_time((word.start + word.end) / 2.0, chunk_turns, fallback)
        if runs and runs[-1]["cluster"] == cluster:
            run = runs[-1]
            run["end"] = word.end
            run["text"] += word.word
        else:
            runs.append(
                {"start": word.start, "end": word.end, "text": word.word, "cluster": cluster}
            )
    for run in runs:
        run["text"] = run["text"].strip()
    return runs


def stitch(
    results: list[ChunkResult],
    windows: list[ChunkWindow],
    expected_speakers: int | None,
    duration_s: float,
) -> StitchResult:
    """Cluster chunk-local voices and produce stable teacher/student IDs."""
    if duration_s < 0:
        raise ValueError("duration_s must be non-negative")
    if not results:
        return StitchResult(speakers=[], segments=[])
    window_by_chunk = {window.chunk_index: window for window in windows}

    # One robust observation per (chunk, local speaker). Local labels can be
    # arbitrarily permuted in every chunk, so only embeddings cross the seam.
    # Turns are weighted by duration: a 0.5 s interjection gets padded into a
    # noisy ECAPA vector, so letting it sway the centroid as much as a 30 s
    # monologue is exactly what smears one real voice across chunks.
    grouped_turns: dict[tuple[int, str], list[tuple[list[float], float]]] = defaultdict(
        list
    )
    for result in results:
        for turn in result.turns:
            weight = max(turn.end - turn.start, _MIN_EMBEDDING_AUDIO_S)
            grouped_turns[(result.chunk_index, turn.local_speaker)].append(
                (turn.embedding, weight)
            )

    keys = sorted(grouped_turns)
    representatives = []
    for key in keys:
        pairs = grouped_turns[key]
        total_weight = sum(weight for _, weight in pairs)
        mean = [
            sum(vector[dim] * weight for vector, weight in pairs) / total_weight
            for dim in range(len(pairs[0][0]))
        ]
        representatives.append(_normalise(mean))

    if not representatives:
        return StitchResult(speakers=[], segments=[])

    labels = _cluster_representatives(representatives, expected_speakers)
    local_to_cluster = dict(zip(keys, labels))

    cluster_intervals: dict[int, list[tuple[float, float]]] = defaultdict(list)
    cluster_first_seen: dict[int, float] = {}
    mapped_turns: dict[int, list[tuple[float, float, int]]] = defaultdict(list)
    for result in results:
        for turn in result.turns:
            cluster = local_to_cluster[(result.chunk_index, turn.local_speaker)]
            start = max(0.0, min(duration_s, turn.start))
            end = max(start, min(duration_s, turn.end))
            if end <= start:
                continue
            cluster_intervals[cluster].append((start, end))
            mapped_turns[result.chunk_index].append((start, end, cluster))
            cluster_first_seen[cluster] = min(
                cluster_first_seen.get(cluster, start), start
            )

    merged_by_cluster = {
        cluster: _merge_intervals(intervals)
        for cluster, intervals in cluster_intervals.items()
    }
    totals = {
        cluster: sum(end - start for start, end in intervals)
        for cluster, intervals in merged_by_cluster.items()
    }
    # Clusters with no positive-duration turns are still retained (possible
    # only with malformed input) but sort after observed speakers.
    all_clusters = sorted(set(labels))
    for cluster in all_clusters:
        totals.setdefault(cluster, 0.0)
        cluster_first_seen.setdefault(cluster, math.inf)

    # Teacher = the conversational hub, identified by how often a switch to a
    # DIFFERENT speaker follows their turn — NOT by total speech time. A lecture
    # runs teacher -> student -> teacher -> student..., so the teacher is
    # followed by a switch far more often than any single (rarely-speaking)
    # student, even when one student happens to give a long answer. Walking the
    # turns in time order, we credit each speaker every time a different speaker
    # starts right after them; overlapping seam-duplicate turns share a cluster
    # and so never register as a switch.
    ordered_turns = sorted(
        turn for chunk_turns in mapped_turns.values() for turn in chunk_turns
    )
    switch_counts: dict[int, int] = defaultdict(int)
    previous_cluster: int | None = None
    for _, _, cluster in ordered_turns:
        if previous_cluster is not None and cluster != previous_cluster:
            switch_counts[previous_cluster] += 1
        previous_cluster = cluster

    teacher_cluster = max(
        all_clusters,
        key=lambda cluster: (
            switch_counts.get(cluster, 0),  # primary: most often followed by a switch
            totals[cluster],  # tie-break: longest total speech
            -cluster,  # final deterministic tie-break
        ),
    )
    student_clusters = sorted(
        (cluster for cluster in all_clusters if cluster != teacher_cluster),
        key=lambda cluster: (cluster_first_seen[cluster], cluster),
    )
    cluster_to_id = {teacher_cluster: "teacher"}
    cluster_to_id.update(
        {cluster: f"student_{index}" for index, cluster in enumerate(student_clusters, 1)}
    )

    raw_segments = []
    for result in results:
        chunk_turns = mapped_turns[result.chunk_index]
        window = window_by_chunk.get(result.chunk_index)
        for segment in result.segments:
            fallback = local_to_cluster.get(
                (result.chunk_index, segment.local_speaker), teacher_cluster
            )
            for piece in _split_segment_by_speaker(segment, chunk_turns, fallback):
                raw_segments.append(
                    {
                        "start": max(0.0, min(duration_s, piece["start"])),
                        "end": max(0.0, min(duration_s, piece["end"])),
                        "text": piece["text"],
                        "cluster": piece["cluster"],
                        "chunk": result.chunk_index,
                        "window_start": window.start_s if window else segment.start,
                        "window_end": window.end_s if window else segment.end,
                    }
                )

    deduped = _dedupe_segments(
        item for item in raw_segments if item["end"] > item["start"]
    )

    # Whisper shreds one spoken turn into a segment every sentence or two. Glue
    # consecutive same-speaker pieces into a single logical block — only a change
    # of speaker starts a new block, a pause alone does not — so a teacher's
    # paragraph reads as one block instead of a dozen fragments. The block spans
    # first-piece start to last-piece end (internal pauses fall inside it);
    # per-speaker total_s is computed from turns, not blocks, and stays exact.
    blocks: list[dict] = []
    for item in deduped:
        if blocks and blocks[-1]["cluster"] == item["cluster"]:
            block = blocks[-1]
            block["end"] = max(block["end"], item["end"])
            piece = item["text"].strip()
            if piece:
                block["text"] = (
                    f"{block['text']} {piece}".strip() if block["text"] else piece
                )
        else:
            blocks.append(dict(item))

    timeline = [
        TimelineSegment(
            start=item["start"],
            end=item["end"],
            speaker_id=cluster_to_id[item["cluster"]],
            text=item["text"],
        )
        for item in blocks
    ]

    ordered_clusters = [teacher_cluster, *student_clusters]
    speakers = [
        StitchSpeaker(
            id=cluster_to_id[cluster],
            role=(
                SpeakerRole.teacher
                if cluster == teacher_cluster
                else SpeakerRole.student
            ),
            total_s=totals[cluster],
            turn_count=len(merged_by_cluster.get(cluster, [])),
        )
        for cluster in ordered_clusters
    ]
    return StitchResult(speakers=speakers, segments=timeline)
