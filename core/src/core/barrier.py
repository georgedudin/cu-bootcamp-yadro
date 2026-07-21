"""The all-chunks-done barrier (architecture §7.3), retry-safe.

The naive version — upsert result, then decrement `chunks_remaining` — breaks
under retries: a worker that crashes AFTER the decrement but BEFORE the job is
acked would decrement twice when the job reruns, and stitch would fire early
(or never). The fix: the decrement only happens if THIS statement is the one
that transitions the chunk to done (`status != 'done'` guard), and both
statements share the caller's transaction, so a crashed attempt rolls back
atomically. Exactly one completion per chunk can ever decrement; exactly one
worker observes 0 and enqueues stitch.
"""

from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from core.models import CHUNK_DONE, Chunk, Recording


def record_chunk_done(
    session: Session, recording_id: UUID, chunk_index: int, result: dict
) -> int | None:
    """Store a chunk result and atomically decrement the remaining counter.

    Returns the number of chunks still remaining (the caller that sees 0
    enqueues stitch), or None if this chunk was already done — a duplicate
    delivery, in which case nothing was decremented.
    """
    claimed = session.execute(
        update(Chunk)
        .where(
            Chunk.recording_id == recording_id,
            Chunk.chunk_index == chunk_index,
            Chunk.status != CHUNK_DONE,
        )
        .values(status=CHUNK_DONE, result=result)
        .returning(Chunk.id)
    ).first()
    if claimed is None:
        return None

    return session.execute(
        update(Recording)
        .where(Recording.id == recording_id)
        .values(chunks_remaining=Recording.chunks_remaining - 1)
        .returning(Recording.chunks_remaining)
    ).scalar_one()
