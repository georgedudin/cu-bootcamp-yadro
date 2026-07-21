import pytest

from backend.orchestration.ingest import plan_chunks

WINDOW, OVERLAP = 45.0, 5.0


def coverage_is_complete(chunks: list[tuple[int, float, float]], duration: float) -> bool:
    if chunks[0][1] != 0.0 or chunks[-1][2] != duration:
        return False
    return all(nxt[1] < cur[2] for cur, nxt in zip(chunks, chunks[1:]))


@pytest.mark.parametrize("duration", [0.5, 5, 44.9, 45, 46, 84, 85, 86, 100, 3600, 7200.3])
def test_full_coverage_no_gaps(duration):
    chunks = plan_chunks(duration, WINDOW, OVERLAP)
    assert coverage_is_complete(chunks, duration)
    assert [c[0] for c in chunks] == list(range(len(chunks)))


def test_exact_windows_for_100s():
    assert plan_chunks(100, WINDOW, OVERLAP) == [(0, 0.0, 45.0), (1, 40.0, 85.0), (2, 80.0, 100.0)]


def test_short_recording_is_one_chunk():
    assert plan_chunks(30, WINDOW, OVERLAP) == [(0, 0.0, 30.0)]


def test_no_degenerate_tail_chunk():
    # 85s: a third window would start at 80 and cover only already-seen audio
    assert len(plan_chunks(85, WINDOW, OVERLAP)) == 2


def test_overlap_is_exactly_5s_between_neighbors():
    chunks = plan_chunks(200, WINDOW, OVERLAP)
    for cur, nxt in zip(chunks, chunks[1:-1]):
        assert cur[2] - nxt[1] == OVERLAP


def test_rejects_bad_inputs():
    with pytest.raises(ValueError):
        plan_chunks(0, WINDOW, OVERLAP)
    with pytest.raises(ValueError):
        plan_chunks(100, 5.0, 5.0)
