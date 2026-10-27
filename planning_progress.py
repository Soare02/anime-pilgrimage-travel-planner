"""Small user-facing execution summaries, separate from raw model/debug traces."""

import hashlib
import json
import logging
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps


_reporter = ContextVar("planning_reporter", default=None)
_phase = ContextVar("planning_phase", default=None)
_point = ContextVar("planning_point", default="")
STAGES = {"input", "retrieve", "experience", "route", "validate", "enrich"}
STATUSES = {"running", "completed", "warning", "failed", "cancelled", "skipped"}
MAX_ENTRIES = 400


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class PlanningReporter:
    def __init__(self, callback=None):
        self.callback = callback
        self.entries = {}
        self.attempts = {}
        self.sequence = 0
        self.lock = threading.RLock()
        self.closed = False

    def _publish(self, entry):
        self.sequence += 1
        entry["sequence"] = self.sequence
        payload = {key: value for key, value in entry.items() if not key.startswith("_")}
        try:
            self.callback(payload)
        except Exception:
            logging.getLogger(__name__).warning("Planning progress callback failed", exc_info=True)

    def _update(self, key, stage, kind, title, summary, status, *, parent_id=None, attempt=1, group=None):
        if not self.callback or self.closed or stage not in STAGES or status not in STATUSES:
            return None
        with self.lock:
            if self.closed:
                return None
            if key not in self.entries:
                if len(self.entries) >= MAX_ENTRIES:
                    return None
                self.entries[key] = {
                    "id": key, "stage": stage, "group": group or stage, "kind": kind,
                    "parent_id": parent_id, "attempt": attempt, "order": len(self.entries),
                    "started_at": now_iso(), "_started": time.monotonic(),
                }
            entry = self.entries[key]
            entry.update(title=str(title)[:160], summary=str(summary)[:600], status=status)
            if status != "running":
                entry["finished_at"] = now_iso()
                entry["duration_ms"] = max(0, round((time.monotonic() - entry["_started"]) * 1000))
            self._publish(entry)
            return key

    def begin_phase(self, stage, title, summary=""):
        with self.lock:
            attempt = self.attempts.get(stage, 0) + 1
            self.attempts[stage] = attempt
            group = "validate" if stage == "route" and attempt > 1 else stage
            if stage == "route" and attempt > 1:
                title = f"路线重排 · 第 {attempt - 1} 次"
            elif stage == "validate":
                title = f"第 {attempt} 次校验"
            return self._update(f"phase:{stage}:{attempt}", stage, "phase", title, summary, "running", attempt=attempt, group=group)

    def finish_phase(self, key, summary, status="completed"):
        with self.lock:
            entry = self.entries.get(key)
            if not entry:
                return
            for child in list(self.entries.values()):
                if child.get("parent_id") == key and child["status"] == "running":
                    child_status = status if status in {"failed", "cancelled"} else "warning"
                    self._update(child["id"], child["stage"], "detail", child["title"],
                                 "执行已取消" if status == "cancelled" else "此项未完成，已保留已有结果", child_status)
            self._update(key, entry["stage"], "phase", entry["title"], summary, status)

    def activity(self, stage, key, title, summary, status="completed"):
        parent = _phase.get()
        with self.lock:
            parent_entry = self.entries.get(parent)
            if not parent_entry or parent_entry["stage"] != stage or parent_entry["status"] != "running":
                return
            digest = hashlib.sha1(json.dumps([parent, _point.get(), str(key)], ensure_ascii=False).encode()).hexdigest()[:18]
            self._update(f"detail:{digest}", stage, "detail", title, summary, status,
                         parent_id=parent, group=parent_entry["group"], attempt=parent_entry["attempt"])

    def close(self):
        with self.lock:
            self.closed = True


@contextmanager
def reporting(callback=None):
    reporter = PlanningReporter(callback)
    token = _reporter.set(reporter)
    try:
        yield reporter
    finally:
        reporter.close()
        _reporter.reset(token)


@contextmanager
def point_scope(point_id):
    token = _point.set(str(point_id))
    try:
        yield
    finally:
        _point.reset(token)


def activity(stage, key, title, summary, status="completed"):
    reporter = _reporter.get()
    if reporter:
        reporter.activity(stage, key, title, summary, status)


def update_current(summary):
    reporter = _reporter.get()
    if reporter:
        with reporter.lock:
            entry = reporter.entries.get(_phase.get())
            if entry and entry["status"] == "running":
                reporter._update(entry["id"], entry["stage"], "phase", entry["title"], summary, "running")


def track_stage(stage, title):
    def decorate(fn):
        @wraps(fn)
        def wrapped(state, config=None):
            reporter = _reporter.get()
            key = reporter.begin_phase(stage, title, f"正在{title}") if reporter else None
            token = _phase.set(key)
            try:
                result = fn(state, config)
                summary = result.pop("_step_summary", f"{title}已完成")
                status = result.pop("_step_status", "completed")
                if reporter:
                    reporter.finish_phase(key, summary, status)
                return result
            except Exception as exc:
                cancelled = getattr(exc, "code", "") == "RUN_CANCELLED"
                if reporter:
                    reporter.finish_phase(key, "已取消此步骤" if cancelled else f"{title}未能完成，请查看错误提示", "cancelled" if cancelled else "failed")
                raise
            finally:
                _phase.reset(token)
        return wrapped
    return decorate
