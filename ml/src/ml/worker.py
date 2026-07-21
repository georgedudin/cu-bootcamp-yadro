"""RQ worker entrypoint.

SimpleWorker on purpose (architecture §7.2): CUDA cannot be re-initialized in
a forked child, and in-process execution keeps Friend A's models loaded once
and warm across jobs. The scheduler thread is needed for retry intervals.

Usage: python -m ml.worker [queue ...]     (default: chunks reduce)
"""

import logging
import sys

from redis import Redis
from rq import Queue, SimpleWorker

from core.settings import get_settings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    queue_names = sys.argv[1:] or ["chunks", "reduce"]
    connection = Redis.from_url(get_settings().redis_url)
    queues = [Queue(name, connection=connection) for name in queue_names]
    SimpleWorker(queues, connection=connection).work(with_scheduler=True)


if __name__ == "__main__":
    main()
