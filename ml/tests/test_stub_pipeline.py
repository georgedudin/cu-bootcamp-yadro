"""The graded property: speaker identity is stable ACROSS chunks even though
chunk-local labels are arbitrary (chunk 1's SPEAKER_00 may be chunk 2's
SPEAKER_01). The stub embeddings are real enough to exercise this end-to-end."""

import uuid

from contracts import ChunkResult, ChunkSegment, ChunkWindow, Turn
from ml.pipeline import stitch
from ml.pipeline.stub import _speaker_direction

# Hand-crafted inputs only — NO randomness in CI tests, ever. (A previous
# version generated random stub data here and flaked in CI.)
REC = uuid.UUID("7f9d3e04-2b1c-4b6e-9a70-5a1f6d2c8e11")


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

    assert [s.text for s in out.segments] == ["body", "seam sentence", "tail"]
