"""RQ worker entrypoint.

SimpleWorker on purpose (architecture §7.2): CUDA cannot be re-initialized in
a forked child, and in-process execution keeps the models loaded once and warm
across jobs. The scheduler thread is needed for retry intervals.

Usage: python -m ml.worker [queue ...]     (default: chunks reduce)
"""

import logging
import sys

from redis import Redis
from rq import Queue, SimpleWorker

from core.settings import get_settings

log = logging.getLogger(__name__)


def _recover_stuck_stitches() -> None:
    """SimpleWorker crash window: a worker that died after committing
    status=stitching but before enqueueing the stitch job leaves the recording
    stuck forever. Stitch is idempotent, so re-enqueueing on boot is safe."""
    from sqlalchemy import select

    from contracts import RecordingStatus
    from core.models import Recording
    from core.session import session_scope
    from ml.glue import _enqueue_stitch

    with session_scope() as session:
        stuck = session.scalars(
            select(Recording.id).where(
                Recording.status == RecordingStatus.stitching.value,
                Recording.chunks_remaining == 0,
            )
        ).all()
    for recording_id in stuck:
        log.warning("re-enqueueing stitch for stuck recording %s", recording_id)
        _enqueue_stitch(recording_id)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    queue_names = sys.argv[1:] or ["chunks", "reduce"]
    if "chunks" in queue_names:
        # Fail loudly at boot, not per-job: a broken model stack must crash
        # the container (visible in `compose ps`), never churn job retries.
        from ml.pipeline import preload_chunk_models

        preload_chunk_models()
    if "reduce" in queue_names:
        _recover_stuck_stitches()
    connection = Redis.from_url(get_settings().redis_url)
    queues = [Queue(name, connection=connection) for name in queue_names]
    SimpleWorker(queues, connection=connection).work(with_scheduler=True)


if __name__ == "__main__":
    main()
