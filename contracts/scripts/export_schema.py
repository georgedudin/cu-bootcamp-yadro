"""Export every wire model into one JSON Schema document (draft 2020-12).

Run via `make contracts`. Output is deterministic (sorted keys, no timestamps)
so `make contracts-check` can diff it in CI.
"""

import json
from pathlib import Path

from pydantic.json_schema import models_json_schema

import contracts as c

# 'serialization' for shapes the server EMITS (responses), 'validation' for
# shapes a peer must PRODUCE and we validate (jobs, results, seam types).
MODELS = [
    (c.CleanupResponse, "serialization"),
    (c.Progress, "serialization"),
    (c.RecordingCreateResponse, "serialization"),
    (c.RecordingSummary, "serialization"),
    (c.RecordingDetail, "serialization"),
    (c.TimelineSpeaker, "serialization"),
    (c.TimelineSegment, "serialization"),
    (c.Timeline, "serialization"),
    (c.TranscribeChunkJob, "validation"),
    (c.Word, "validation"),
    (c.ChunkSegment, "validation"),
    (c.Turn, "validation"),
    (c.ChunkResult, "validation"),
    (c.StitchRecordingJob, "validation"),
    (c.ChunkWindow, "validation"),
    (c.StitchSpeaker, "validation"),
    (c.StitchResult, "validation"),
]

OUT = Path(__file__).resolve().parent.parent / "schema" / "contracts.schema.json"


def main() -> None:
    _, schema = models_json_schema(
        MODELS,
        title="cu-bootcamp-yadro wire contracts",
        description=(
            f"Generated from the contracts package v{c.CONTRACTS_VERSION}. "
            "Do not edit by hand — edit contracts/src/contracts/ and run `make contracts`."
        ),
    )
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
