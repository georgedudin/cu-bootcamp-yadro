"""RQ enqueue side. Handlers are referenced by DOTTED STRING so the backend
never imports the ml package (and its future GPU deps). Payloads are plain
JSON-mode dicts; the glue re-validates them against the contracts models."""

from functools import lru_cache

from redis import Redis
from rq import Queue, Retry

from contracts import StitchRecordingJob, TranscribeChunkJob
from core.settings import get_settings

CHUNKS_QUEUE = "chunks"
REDUCE_QUEUE = "reduce"

TRANSCRIBE_HANDLER = "ml.glue.transcribe_chunk"
STITCH_HANDLER = "ml.glue.stitch_recording"


@lru_cache
def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def chunks_queue() -> Queue:
    return Queue(CHUNKS_QUEUE, connection=_redis())


def reduce_queue() -> Queue:
    return Queue(REDUCE_QUEUE, connection=_redis())


def enqueue_transcribe_chunk(job: TranscribeChunkJob) -> None:
    chunks_queue().enqueue(
        TRANSCRIBE_HANDLER,
        job.model_dump(mode="json"),
        retry=Retry(max=get_settings().max_chunk_retries, interval=[10, 30, 60]),
        job_timeout=1800,
    )


def enqueue_stitch(job: StitchRecordingJob) -> None:
    reduce_queue().enqueue(
        STITCH_HANDLER,
        job.model_dump(mode="json"),
        retry=Retry(max=2, interval=[10, 30]),
        job_timeout=1800,
    )
