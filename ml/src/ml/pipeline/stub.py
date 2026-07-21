"""Fake ML with the REAL pipeline shape. Runs on CPU in ~a second per chunk.

What is fake: the "transcript" is canned text, embeddings are synthetic
vectors (one fixed direction per true speaker + noise) instead of ECAPA on
audio. What is real and worth keeping: the chunk-local labeling, the global
clustering in stitch(), the teacher-by-speech-time rule, and the overlap-seam
dedupe — Friend A can keep stitch() almost as-is and only swap the map step.
"""

import math
import random
import time

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

PHRASES = [
    "So today we continue with linear operators.",
    "Notice how the determinant behaves under row operations.",
    "Could you repeat the last step, please?",
    "This is exactly why the kernel matters.",
    "I think the answer is the identity matrix.",
    "Let us look at a concrete example on the board.",
    "Does this hold for complex eigenvalues as well?",
    "Remember this trick — it will appear in the exam.",
]

SIMULATED_GPU_SECONDS = 0.5  # keeps the FE progress bar honest during demos


def _speaker_direction(global_speaker: int) -> list[float]:
    """A fixed unit vector per TRUE speaker — chunk-independent, so clustering
    in stitch() genuinely reassembles identities across chunks."""
    rng = random.Random(f"speaker-{global_speaker}")
    v = [rng.gauss(0, 1) for _ in range(EMBEDDING_DIM)]
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v]


def _noisy(direction: list[float], rng: random.Random) -> list[float]:
    v = [x + rng.gauss(0, 0.05) for x in direction]
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v]


def transcribe_chunk(job: TranscribeChunkJob) -> ChunkResult:
    # Deterministic per (recording, chunk): retries produce identical results
    rng = random.Random(f"{job.recording_id}:{job.chunk_index}")
    time.sleep(SIMULATED_GPU_SECONDS)

    n_speakers = job.expected_speakers or 3  # teacher + 2 students by default
    segments: list[ChunkSegment] = []
    turns: list[Turn] = []
    cursor = job.start_s
    local_labels: dict[int, str] = {}

    while cursor < job.end_s - 1.0:
        # teacher (global speaker 0) dominates; students interject briefly
        is_teacher = rng.random() < 0.6
        speaker = 0 if is_teacher else rng.randrange(1, n_speakers)
        length = rng.uniform(6.0, 12.0) if is_teacher else rng.uniform(1.5, 4.0)
        start = cursor
        end = min(cursor + length, job.end_s)
        local = local_labels.setdefault(speaker, f"SPEAKER_{len(local_labels):02d}")

        text = PHRASES[rng.randrange(len(PHRASES))]
        words = text.split()
        step = (end - start) / len(words)
        segments.append(
            ChunkSegment(
                start=round(start, 2), end=round(end, 2), text=text, local_speaker=local,
                words=[
                    Word(
                        start=round(start + i * step, 2),
                        end=round(start + (i + 1) * step, 2),
                        word=w,
                    )
                    for i, w in enumerate(words)
                ],
            )
        )
        turns.append(
            Turn(
                start=round(start, 2), end=round(end, 2), local_speaker=local,
                embedding=_noisy(_speaker_direction(speaker), rng),
            )
        )
        cursor = end + rng.uniform(0.4, 1.5)  # silence gap

    return ChunkResult(
        recording_id=job.recording_id, chunk_index=job.chunk_index,
        segments=segments, turns=turns,
    )


# --- reduce ----------------------------------------------------------------


def _cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return 1.0 - dot / (na * nb)


def _mean(vectors: list[list[float]]) -> list[float]:
    return [sum(col) / len(vectors) for col in zip(*vectors)]


def _cluster(
    reps: list[list[float]], n_clusters: int | None, distance_threshold: float
) -> list[int]:
    """Agglomerative clustering on cosine distance between cluster centroids
    (the real pipeline uses sklearn AgglomerativeClustering — reimplemented
    here to keep the stub dependency-free). Centroids are merged as weighted
    means and pair distances updated incrementally, so a 2-hour lecture's
    worth of turns clusters in seconds. Returns a cluster id per input."""
    from itertools import combinations

    means = {i: list(v) for i, v in enumerate(reps)}
    sizes = dict.fromkeys(means, 1)
    root = {i: i for i in means}  # rep index -> current cluster
    dist = {
        (i, j): _cosine_distance(means[i], means[j]) for i, j in combinations(means, 2)
    }
    while len(means) > 1:
        if n_clusters is not None and len(means) <= n_clusters:
            break
        (i, j), d = min(dist.items(), key=lambda kv: kv[1])
        if n_clusters is None and d > distance_threshold:
            break
        wi, wj = sizes[i], sizes[j]
        means[i] = [(a * wi + b * wj) / (wi + wj) for a, b in zip(means[i], means[j])]
        sizes[i] = wi + wj
        del means[j], sizes[j]
        for r, c in root.items():
            if c == j:
                root[r] = i
        dist = {pair: v for pair, v in dist.items() if j not in pair}
        for k in means:
            if k != i:
                dist[(min(i, k), max(i, k))] = _cosine_distance(means[i], means[k])
    renumber = {cluster: n for n, cluster in enumerate(sorted(means))}
    return [renumber[root[r]] for r in range(len(reps))]


def _own_ranges(windows: list[ChunkWindow], duration_s: float) -> dict[int, tuple[float, float]]:
    """Seam dedupe rule: each overlap region is owned half-by-half — the seam
    midpoint splits it. A segment/turn belongs to the chunk that owns its
    midpoint; the copy seen by the neighboring chunk is dropped."""
    ordered = sorted(windows, key=lambda w: w.chunk_index)
    ranges = {}
    for prev, cur, nxt in zip(
        [None] + list(ordered[:-1]), ordered, list(ordered[1:]) + [None]
    ):
        lo = 0.0 if prev is None else (cur.start_s + prev.end_s) / 2
        hi = duration_s if nxt is None else (nxt.start_s + cur.end_s) / 2
        ranges[cur.chunk_index] = (lo, hi)
    return ranges


def stitch(
    results: list[ChunkResult],
    windows: list[ChunkWindow],
    expected_speakers: int | None,
    duration_s: float,
) -> StitchResult:
    # 1. One representative embedding per (chunk, local_speaker) — averaging
    #    turns stabilizes short utterances before global clustering (§4.3)
    keys: list[tuple[int, str]] = []
    reps: list[list[float]] = []
    for result in results:
        by_local: dict[str, list[list[float]]] = {}
        for turn in result.turns:
            by_local.setdefault(turn.local_speaker, []).append(turn.embedding)
        for local, embeddings in sorted(by_local.items()):
            keys.append((result.chunk_index, local))
            reps.append(_mean(embeddings))
    if not reps:
        return StitchResult(speakers=[], segments=[])

    # 2. Global clustering -> stable identity across chunks
    labels = _cluster(reps, expected_speakers, distance_threshold=0.5)
    cluster_of: dict[tuple[int, str], int] = dict(zip(keys, labels))

    # 3. Dedupe overlap seams, then attribute speech time per cluster
    own = _own_ranges(windows, duration_s)
    speech_s: dict[int, float] = {}
    turn_count: dict[int, int] = {}
    for result in results:
        lo, hi = own[result.chunk_index]
        for turn in result.turns:
            mid = (turn.start + turn.end) / 2
            if lo <= mid < hi:
                cluster = cluster_of[(result.chunk_index, turn.local_speaker)]
                speech_s[cluster] = speech_s.get(cluster, 0.0) + (turn.end - turn.start)
                turn_count[cluster] = turn_count.get(cluster, 0) + 1

    # 4. Teacher = most total speech time (§10); students ranked by speech time
    ranked = sorted(speech_s, key=lambda c: speech_s[c], reverse=True)
    names = {
        cluster: ("teacher" if rank == 0 else f"student_{rank}")
        for rank, cluster in enumerate(ranked)
    }

    # 5. Final timeline: deduped segments with global speaker ids
    segments: list[TimelineSegment] = []
    for result in results:
        lo, hi = own[result.chunk_index]
        for seg in result.segments:
            mid = (seg.start + seg.end) / 2
            if not (lo <= mid < hi):
                continue
            cluster = cluster_of[(result.chunk_index, seg.local_speaker)]
            if cluster not in names:
                continue  # cluster fell entirely into dropped seam copies
            segments.append(
                TimelineSegment(
                    start=seg.start, end=seg.end, speaker_id=names[cluster], text=seg.text
                )
            )
    segments.sort(key=lambda s: s.start)

    speakers = [
        StitchSpeaker(
            id=names[cluster],
            role=SpeakerRole.teacher if rank == 0 else SpeakerRole.student,
            total_s=round(speech_s[cluster], 2),
            turn_count=turn_count[cluster],
        )
        for rank, cluster in enumerate(ranked)
    ]
    return StitchResult(speakers=speakers, segments=segments)
