"""Bounded delivery lanes shared by browser queues, with per-thread DB cleanup."""
from concurrent.futures import ThreadPoolExecutor
from django.db import connections, close_old_connections

# Shared pool: three browser queues cannot each create an unbounded set of senders.
_senders = ThreadPoolExecutor(max_workers=4, thread_name_prefix='webpush-send')


def _deliver(callback, row):
    close_old_connections()
    try:
        return callback(row)
    finally:
        connections.close_all()


def dispatch(rows, callback, parallel=False):
    if not parallel:
        for row in rows:
            callback(row)
        return
    # Claims were committed before submitting work. Each row retains its CAS lease.
    futures = [_senders.submit(_deliver, callback, row) for row in rows]
    for future in futures:
        future.result()
