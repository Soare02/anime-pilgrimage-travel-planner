"""Shared bounded, cancellable collection of blocking search requests."""

from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextvars import copy_context


def run_search_tasks(tasks, should_stop=None, max_workers=3):
    """Yield (metadata, result, error), dropping late replies after cancellation.

    Tasks are (metadata, callable, positional_args). Running HTTP requests retain
    their own socket timeouts; queued work is cancelled without waiting for them.
    Each worker gets the caller's trace ContextVars.
    """
    stopped = should_stop or (lambda: False)
    if not tasks or stopped():
        return
    executor = ThreadPoolExecutor(max_workers=min(len(tasks), max_workers))
    pending = {}

    def invoke(fn, args):
        return None if stopped() else fn(*args)

    try:
        for metadata, fn, args in tasks:
            if stopped():
                break
            future = executor.submit(copy_context().run, invoke, fn, args)
            pending[future] = metadata
        while pending and not stopped():
            done, _ = wait(pending, timeout=0.05, return_when=FIRST_COMPLETED)
            for future in done:
                metadata = pending.pop(future)
                if stopped():
                    return
                try:
                    result = future.result()
                except Exception as exc:
                    yield metadata, None, exc
                else:
                    yield metadata, result, None
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
