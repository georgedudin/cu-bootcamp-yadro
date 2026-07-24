"""The graded property: speaker identity is stable ACROSS chunks even though
chunk-local labels are arbitrary (chunk 1's SPEAKER_00 may be chunk 2's
SPEAKER_01). Synthetic embeddings exercise the REAL stitch logic end-to-end."""

import random
import uuid

from contracts import EMBEDDING_DIM, ChunkResult, ChunkSegment, ChunkWindow, Turn
from ml.pipeline import stitch
from ml.pipeline.engine import _normalise

# Hand-crafted inputs only — NO randomness in CI tests, ever. (A previous
# version generated random stub data here and flaked in CI.)
REC = uuid.UUID("7f9d3e04-2b1c-4b6e-9a70-5a1f6d2c8e11")


def _speaker_direction(speaker: int) -> list[float]:
    """Deterministic (fixed-seed) unit vector standing in for a real embedding."""
    rng = random.Random(0x5EED + speaker)
    return _normalise([rng.gauss(0.0, 1.0) for _ in range(EMBEDDING_DIM)])


def _turn(start, end, local, true_speaker):
    return Turn(start=start, end=end, local_speaker=local,
                embedding=_speaker_direction(true_speaker))


def _seg(start, end, local, text):
    return ChunkSegment(start=start, end=end, text=text, local_speaker=local, words=[])


def test_identity_survives_flipped_local_labels():
    # chunk 0: teacher=SPEAKER_00, student=SPEAKER_01
    # chunk 1: SAME true speakers but local labels FLIPPED
    results = [
        ChunkResult(recording_id=REC, chunk_index=0,
            segments=[_seg(0, 30, "SPEAKER_00", "teacher talks"),
                      _seg(31, 34, "SPEAKER_01", "student asks")],
            turns=[_turn(0, 30, "SPEAKER_00", true_speaker=0),
                   _turn(31, 34, "SPEAKER_01", true_speaker=1)]),
        ChunkResult(recording_id=REC, chunk_index=1,
            segments=[_seg(46, 76, "SPEAKER_01", "teacher continues"),
                      _seg(77, 80, "SPEAKER_00", "student replies")],
            turns=[_turn(46, 76, "SPEAKER_01", true_speaker=0),
                   _turn(77, 80, "SPEAKER_00", true_speaker=1)]),
    ]
    windows = [ChunkWindow(chunk_index=0, start_s=0, end_s=45),
               ChunkWindow(chunk_index=1, start_s=40, end_s=85)]

    out = stitch(results, windows, expected_speakers=None, duration_s=85)

    by_text = {s.text: s.speaker_id for s in out.segments}
    assert by_text["teacher talks"] == by_text["teacher continues"] == "teacher"
    assert by_text["student asks"] == by_text["student replies"] == "student_1"
    assert [s.id for s in out.speakers] == ["teacher", "student_1"]
    assert out.speakers[0].role == "teacher"


def test_seam_copies_are_deduped():
    # identical turn transcribed by BOTH chunks in the 40-45s overlap
    dup_a = _seg(41, 44, "SPEAKER_00", "seam sentence")
    dup_b = _seg(41, 44, "SPEAKER_00", "seam sentence")
    results = [
        ChunkResult(recording_id=REC, chunk_index=0,
            segments=[_seg(0, 30, "SPEAKER_00", "body"), dup_a],
            turns=[_turn(0, 30, "SPEAKER_00", 0), _turn(41, 44, "SPEAKER_00", 0)]),
        ChunkResult(recording_id=REC, chunk_index=1,
            segments=[dup_b, _seg(50, 70, "SPEAKER_00", "tail")],
            turns=[_turn(41, 44, "SPEAKER_00", 0), _turn(50, 70, "SPEAKER_00", 0)]),
    ]
    windows = [ChunkWindow(chunk_index=0, start_s=0, end_s=45),
               ChunkWindow(chunk_index=1, start_s=40, end_s=85)]

    out = stitch(results, windows, expected_speakers=None, duration_s=85)

    # The duplicate seam copy is dropped (dedupe), and the three same-speaker
    # pieces then glue into one logical block. If dedupe had failed we'd see
    # "seam sentence" twice inside the block.
    assert [s.text for s in out.segments] == ["body seam sentence tail"]


def test_same_speaker_segments_merge_across_pauses():
    # Whisper hands us many tiny segments per turn. Consecutive same-speaker
    # pieces glue into one block even across a pause (5->9 s), while a different
    # speaker breaks the run — so we get teacher / student_1 / teacher, not five
    # fragments.
    results = [
        ChunkResult(recording_id=REC, chunk_index=0,
            segments=[_seg(0, 5, "SPEAKER_00", "First sentence."),
                      _seg(9, 14, "SPEAKER_00", "Second after a pause."),
                      _seg(15, 18, "SPEAKER_01", "A question?"),
                      _seg(20, 25, "SPEAKER_00", "Back to the teacher.")],
            turns=[_turn(0, 14, "SPEAKER_00", true_speaker=0),
                   _turn(15, 18, "SPEAKER_01", true_speaker=1),
                   _turn(20, 25, "SPEAKER_00", true_speaker=0)]),
    ]
    windows = [ChunkWindow(chunk_index=0, start_s=0, end_s=45)]

    out = stitch(results, windows, expected_speakers=None, duration_s=45)

    assert [(s.speaker_id, s.text) for s in out.segments] == [
        ("teacher", "First sentence. Second after a pause."),
        ("student_1", "A question?"),
        ("teacher", "Back to the teacher."),
    ]


def test_expected_speakers_above_observations_clamps_instead_of_failing():
    # Upload hint says 2 speakers, but the audio only produced ONE chunk-local
    # observation. This must degrade to a smaller speaker set, not fail the
    # whole recording (it used to raise and mark the recording failed).
    results = [
        ChunkResult(recording_id=REC, chunk_index=0,
            segments=[_seg(0, 30, "SPEAKER_00", "only voice")],
            turns=[_turn(0, 30, "SPEAKER_00", true_speaker=0)]),
    ]
    windows = [ChunkWindow(chunk_index=0, start_s=0, end_s=45)]

    out = stitch(results, windows, expected_speakers=2, duration_s=45)

    assert [s.id for s in out.speakers] == ["teacher"]
    assert [s.speaker_id for s in out.segments] == ["teacher"]
