"""Every committed fixture must round-trip through its Pydantic model —
this is what makes the fixtures trustworthy for FE/ML development."""

import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from contracts import (
    EMBEDDING_DIM,
    ChunkResult,
    RecordingSummary,
    Timeline,
    TranscribeChunkJob,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

CASES = [
    ("timeline.json", TypeAdapter(Timeline)),
    ("recordings_list.json", TypeAdapter(list[RecordingSummary])),
    ("chunk_result.json", TypeAdapter(ChunkResult)),
    ("transcribe_chunk_job.json", TypeAdapter(TranscribeChunkJob)),
]


@pytest.mark.parametrize("filename,adapter", CASES, ids=[c[0] for c in CASES])
def test_fixture_conforms(filename: str, adapter: TypeAdapter) -> None:
    raw = (FIXTURES / filename).read_bytes()
    parsed = adapter.validate_json(raw)
    # round-trip: dumping and re-validating must be lossless
    assert adapter.validate_json(adapter.dump_json(parsed)) == parsed


def test_chunk_result_embeddings_are_192d() -> None:
    result = ChunkResult.model_validate_json((FIXTURES / "chunk_result.json").read_bytes())
    assert result.turns, "fixture must contain at least one turn"
    assert all(len(t.embedding) == EMBEDDING_DIM for t in result.turns)


def test_extra_fields_are_rejected() -> None:
    data = json.loads((FIXTURES / "transcribe_chunk_job.json").read_bytes())
    data["surprise"] = 1
    with pytest.raises(Exception):
        TranscribeChunkJob.model_validate(data)
