"""Agent 运行步骤追踪器：记录每个节点中模型/工具的输入输出，便于在后台 UI 中调试问题定位。

设计要点：
- 用 contextvars 把 run_id 绑定在调用线程链路上，避免多请求并发污染。
- 所有 record_* 方法在 trace 未启动时静默返回，调用方无需 if 判断。
- 持久化到 chroma_db/agent_traces.json，最多保留最近 N 条 run，单条 run 内步骤无上限。
- 长字符串截断阈值 MAX_FIELD_LEN，避免单条 trace 占用过大磁盘 / 前端内存。
"""

import os
import sys
import json
import threading
import datetime
import contextvars
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("agent_trace")

# DEBUG: 默认开启诊断输出，便于定位 trace 没写入的根因。问题确认后可设 AGENT_TRACE_DEBUG=0 关闭。
DEBUG = os.getenv("AGENT_TRACE_DEBUG", "1") == "1"

def _dbg(msg: str) -> None:
    if DEBUG:
        print(f"[agent_trace] {msg}", file=sys.stderr, flush=True)

TRACE_FILE = os.path.join(os.path.dirname(__file__), "chroma_db", "agent_traces.json")
MAX_RUNS = 50
MAX_FIELD_LEN = 50000  # 单字段最大字符数，超出会截断并加省略号

_current_run_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "agent_trace_run_id", default=None
)

# 内存中正在运行的 traces（按 run_id 索引）
_active_runs: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _truncate(value: Any) -> Any:
    """字符串过长截断，dict/list 递归处理。其他类型转 str。"""
    if isinstance(value, str):
        if len(value) > MAX_FIELD_LEN:
            return value[:MAX_FIELD_LEN] + f"\n...(已截断，原长度 {len(value)} 字符)"
        return value
    if isinstance(value, dict):
        return {k: _truncate(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_truncate(v) for v in value]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _truncate(str(value))


def _persist_run(run: Dict[str, Any]) -> None:
    """把单条 run 写入持久化文件（追加到列表头部，保留 MAX_RUNS 条）。"""
    try:
        os.makedirs(os.path.dirname(TRACE_FILE), exist_ok=True)
        runs: List[Dict[str, Any]] = []
        if os.path.exists(TRACE_FILE):
            try:
                with open(TRACE_FILE, "r", encoding="utf-8") as f:
                    runs = json.load(f)
            except Exception:
                runs = []
        # 去重：如果该 run_id 已存在（增量更新 / 重试），先移除旧记录
        runs = [r for r in runs if r.get("run_id") != run.get("run_id")]
        runs.insert(0, run)
        runs = runs[:MAX_RUNS]
        with open(TRACE_FILE, "w", encoding="utf-8") as f:
            json.dump(runs, f, ensure_ascii=False, indent=2)
        _dbg(f"_persist_run wrote {TRACE_FILE} (total {len(runs)} runs on disk, this run has {len(run.get('steps', []))} steps)")
    except Exception as e:
        _dbg(f"_persist_run FAILED: {e}")
        logger.error(f"Failed to persist trace: {e}")


def _persist_current() -> None:
    """读取当前线程上下文中的 active run 并立即 flush 到磁盘（不弹出）。

    每次 record_* 都调用一次，确保即使 generator 被 FastAPI 客户端断开 / 中途异常，
    磁盘上也能看到此前的 steps（status 仍为 running）。
    """
    run_id = _current_run_id.get()
    if not run_id:
        return
    with _lock:
        run = _active_runs.get(run_id)
        if run is None:
            return
        # 拷贝再持久化以避免边写边改
        snapshot = json.loads(json.dumps(run, ensure_ascii=False))
    _persist_run(snapshot)


def start_run(days: int, landmark_names: List[str]) -> str:
    """开启一条新的 trace 记录，返回 run_id 并把它绑到当前上下文。"""
    run_id = f"run_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    run = {
        "run_id": run_id,
        "start_time": _now(),
        "end_time": None,
        "status": "running",
        "days": days,
        "landmark_names": landmark_names,
        "error": None,
        "steps": [],
    }
    with _lock:
        _active_runs[run_id] = run
    _current_run_id.set(run_id)
    _dbg(f"start_run -> {run_id} (thread={threading.current_thread().name}, days={days})")
    # 立刻 flush 一份 "running" 占位记录，避免 generator 中途崩溃 / 客户端断开导致 0 持久化
    _persist_current()
    return run_id


def end_run(status: str = "success", error: Optional[str] = None) -> None:
    """结束当前上下文的 trace 记录并持久化。"""
    run_id = _current_run_id.get()
    _dbg(f"end_run called: run_id={run_id} status={status} (thread={threading.current_thread().name})")
    if not run_id:
        _dbg("  end_run: no run_id in context, NOTHING PERSISTED")
        return
    with _lock:
        run = _active_runs.pop(run_id, None)
    if run is None:
        _dbg(f"  end_run: {run_id} not in _active_runs, skip")
        return
    run["end_time"] = _now()
    run["status"] = status
    if error:
        run["error"] = error
    _persist_run(run)
    _dbg(f"  end_run: persisted {run_id} with {len(run['steps'])} steps to {TRACE_FILE}")


def get_current_run_id() -> Optional[str]:
    """供 worker 线程读取当前 run_id 后再传递给子线程使用。"""
    return _current_run_id.get()


def attach_run(run_id: Optional[str]) -> None:
    """在子线程入口处调用：把父线程的 run_id 绑到本线程上下文。"""
    if run_id:
        _current_run_id.set(run_id)
        _dbg(f"attach_run({run_id}) on thread={threading.current_thread().name}")


def _add_step(step: Dict[str, Any]) -> None:
    """向当前上下文的 trace 追加一个 step。"""
    run_id = _current_run_id.get()
    if not run_id:
        _dbg(f"_add_step DROPPED (no run_id in context, thread={threading.current_thread().name}, type={step.get('type')}, node={step.get('node')})")
        return
    step["timestamp"] = _now()
    with _lock:
        run = _active_runs.get(run_id)
        if run is not None:
            run["steps"].append(_truncate(step))
            _dbg(f"_add_step OK: run={run_id}, type={step.get('type')}, node={step.get('node')} (total now {len(run['steps'])})")
        else:
            _dbg(f"_add_step DROPPED (run_id {run_id} not active anymore)")
            return
    # 每个 step 都 flush，确保中途看得到进度
    _persist_current()


def record_node_start(node_name: str, summary: str = "") -> None:
    _add_step({
        "type": "node_start",
        "node": node_name,
        "summary": summary,
    })


def record_node_end(node_name: str, summary: str = "") -> None:
    _add_step({
        "type": "node_end",
        "node": node_name,
        "summary": summary,
    })


def record_llm_call(
    node: str,
    label: str,
    prompt: Any,
    response: str,
    model: str = "deepseek-v4-flash",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """记录一次 LLM 调用。prompt 可以是字符串或 messages list。"""
    step: Dict[str, Any] = {
        "type": "llm_call",
        "node": node,
        "label": label,
        "model": model,
        "prompt": prompt,
        "response": response,
    }
    if extra:
        step["extra"] = extra
    _add_step(step)


def record_tool_call(
    node: str,
    tool_name: str,
    args: Dict[str, Any],
    result: Any,
    error: Optional[str] = None,
) -> None:
    """记录一次工具调用。"""
    step: Dict[str, Any] = {
        "type": "tool_call",
        "node": node,
        "tool": tool_name,
        "args": args,
        "result": result,
    }
    if error:
        step["error"] = error
    _add_step(step)


def record_status(node: str, message: str) -> None:
    """记录用户可见的进度回调（与前端 __STATUS__ 同步）。"""
    _add_step({
        "type": "status",
        "node": node,
        "message": message,
    })


# ---------------- API：供 server.py 读取 ----------------

def list_traces() -> List[Dict[str, Any]]:
    """读取持久化 trace 摘要（不含 steps，仅列表展示用）。"""
    if not os.path.exists(TRACE_FILE):
        return []
    try:
        with open(TRACE_FILE, "r", encoding="utf-8") as f:
            runs = json.load(f)
    except Exception:
        return []
    # 摘要：去掉 steps，加上 step_count
    summaries = []
    for r in runs:
        summaries.append({
            "run_id": r.get("run_id"),
            "start_time": r.get("start_time"),
            "end_time": r.get("end_time"),
            "status": r.get("status"),
            "days": r.get("days"),
            "landmark_names": r.get("landmark_names", []),
            "error": r.get("error"),
            "step_count": len(r.get("steps", [])),
        })
    return summaries


def get_trace(run_id: str) -> Optional[Dict[str, Any]]:
    """读取指定 run 的完整 trace（包含所有 steps）。"""
    if not os.path.exists(TRACE_FILE):
        return None
    try:
        with open(TRACE_FILE, "r", encoding="utf-8") as f:
            runs = json.load(f)
    except Exception:
        return None
    for r in runs:
        if r.get("run_id") == run_id:
            return r
    return None


def clear_traces() -> None:
    if os.path.exists(TRACE_FILE):
        os.remove(TRACE_FILE)
