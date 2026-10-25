"""Structured LangGraph planning run for the versioned Agent endpoint."""

import concurrent.futures
import json
import os
import time
from typing import Any, Callable, TypedDict
from urllib.parse import urlparse

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph

import agent_trace
from agent import apply_vision_analysis, llm_deepseek, parse_json_block
from plan_schema import Plan, PlanIssue, PlanRequest, PlanSource, PointNote, point_key
from plan_validation import issue, normalize_candidate
from rag_service import rag_service


MAX_REVISIONS = max(0, int(os.getenv("AGENT_MAX_REVISIONS", "3")))
MODEL_TIMEOUT = max(1, float(os.getenv("AGENT_MODEL_TIMEOUT_SECONDS", "45")))
TOOL_TIMEOUT = max(1, float(os.getenv("AGENT_TOOL_TIMEOUT_SECONDS", "35")))
RUN_TIMEOUT = max(1, float(os.getenv("AGENT_RUN_TIMEOUT_SECONDS", "240")))


class AgentRunError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class PlanState(TypedDict, total=False):
    run_id: str
    request_snapshot: dict[str, Any]
    rag_context: str
    landmark_context: dict[str, Any]
    sources: list[dict[str, Any]]
    warnings: list[PlanIssue]
    candidate: dict[str, Any]
    plan: Plan | None
    errors: list[PlanIssue]
    revision_count: int
    output_text: str


def _cfg(config: dict | None, name: str, default: Any = None) -> Any:
    return (config or {}).get("configurable", {}).get(name, default)


def _check(config: dict | None) -> float:
    if _cfg(config, "should_cancel", lambda: False)():
        raise AgentRunError("RUN_CANCELLED", "规划请求已取消")
    remaining = _cfg(config, "deadline", time.monotonic() + RUN_TIMEOUT) - time.monotonic()
    if remaining <= 0:
        raise AgentRunError("TOOL_TIMEOUT", "规划总时限已到，请减少点位后重试")
    return remaining


def _progress(config: dict | None, stage: str, message: str) -> None:
    _check(config)
    agent_trace.record_status(stage, message)
    callback = _cfg(config, "on_progress")
    if callback:
        callback(stage, message)


def _bounded_call(
    config: dict | None,
    fn: Callable[[], Any],
    *,
    timeout: float,
    timeout_code: str,
    label: str,
    retries: int = 0,
) -> Any:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        remaining = _check(config)
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        parent_run_id = agent_trace.get_current_run_id()

        def traced() -> Any:
            agent_trace.attach_run(parent_run_id)
            return fn()

        future = executor.submit(traced)
        end_at = time.monotonic() + min(timeout, remaining)
        try:
            while True:
                _check(config)
                wait = min(0.2, end_at - time.monotonic())
                if wait <= 0:
                    raise AgentRunError(timeout_code, f"{label}超时")
                try:
                    return future.result(timeout=wait)
                except concurrent.futures.TimeoutError:
                    continue
        except AgentRunError as exc:
            last_error = exc
            future.cancel()
            if exc.code == "RUN_CANCELLED" or attempt == retries:
                raise
        except (TimeoutError, ConnectionError) as exc:
            last_error = exc
            if attempt == retries:
                raise AgentRunError(timeout_code, f"{label}暂时不可用：{exc}") from exc
        except Exception as exc:
            class_name = type(exc).__name__.lower()
            transient = "timeout" in class_name or "connection" in class_name
            if transient and attempt < retries:
                last_error = exc
                continue
            code = timeout_code if "timeout" in class_name else ("MODEL_UNAVAILABLE" if timeout_code == "MODEL_TIMEOUT" else "TOOL_ERROR")
            raise AgentRunError(code, f"{label}失败：{exc}") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
    raise AgentRunError(timeout_code, f"{label}失败：{last_error}")


def _model(config: dict | None, node: str, prompt: str) -> dict[str, Any]:
    def invoke() -> str:
        response = llm_deepseek.invoke(prompt)
        return response.content if hasattr(response, "content") else str(response)

    raw = _bounded_call(config, invoke, timeout=MODEL_TIMEOUT, timeout_code="MODEL_TIMEOUT", label="主规划模型", retries=1)
    agent_trace.record_llm_call(node, node, prompt, raw)
    parsed = parse_json_block(raw)
    return parsed if isinstance(parsed, dict) else {}


def _sources(result: dict[str, Any], ids: set[str]) -> list[dict[str, Any]]:
    cleaned = []
    for item in result.get("sources", []) or []:
        if not isinstance(item, dict):
            continue
        refs = [ref for ref in item.get("point_ids", []) if point_key(ref) in ids]
        if not refs:
            continue
        url = item.get("url")
        # Only a safe HTTP(S) URL can be presented as an external reference.
        parsed_url = urlparse(url) if isinstance(url, str) else None
        if not parsed_url or parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc or any(char.isspace() for char in url):
            url = None
        review_status = item.get("review_status") if item.get("review_status") in {"approved", "unreviewed", "missing"} else "missing"
        if not url:
            review_status = "missing"
        cleaned.append({
            "source_id": str(item.get("source_id") or f"source_{len(cleaned) + 1}"),
            "url": url,
            "title": str(item.get("title") or "参考资料"),
            "retrieved_at": item.get("retrieved_at"),
            "review_status": review_status,
            "point_ids": refs,
        })
    return cleaned


def retrieve_node(state: PlanState, config: RunnableConfig | None = None) -> dict[str, Any]:
    _progress(config, "retrieve", "正在检索已有资料与场景信息")
    request = PlanRequest.model_validate(state["request_snapshot"])
    landmarks = [lm.model_dump(mode="json", exclude_unset=True) for lm in request.landmarks]
    warnings: list[PlanIssue] = []
    result: dict[str, Any] = {}
    try:
        result = _bounded_call(
            config, lambda: rag_service.query_landmarks_context(landmarks),
            timeout=TOOL_TIMEOUT, timeout_code="TOOL_TIMEOUT", label="资料检索", retries=1,
        ) or {}
    except AgentRunError as exc:
        if exc.code == "RUN_CANCELLED":
            raise
        warnings.append(issue(exc.code, f"资料检索失败：{exc}"))
    except Exception as exc:
        warnings.append(issue("TOOL_ERROR", f"资料检索失败：{exc}"))

    missing = result.get("missing_landmarks", landmarks)
    ingest: dict[str, Any] = {}
    if isinstance(missing, list) and missing:
        try:
            _progress(config, "retrieve", f"正在补充 {len(missing)} 个点位的公开资料")
            ingest = _bounded_call(
                config, lambda: rag_service.ingest_landmarks(missing, should_cancel=_cfg(config, "should_cancel")),
                timeout=TOOL_TIMEOUT, timeout_code="TOOL_TIMEOUT", label="联网补充", retries=1,
            ) or {}
        except AgentRunError as exc:
            if exc.code == "RUN_CANCELLED":
                raise
            warnings.append(issue(exc.code, f"联网补充失败：{exc}"))
        except Exception as exc:
            warnings.append(issue("TOOL_ERROR", f"联网补充失败：{exc}"))

    ids = {point_key(lm.id) for lm in request.landmarks}
    sources = _sources(result, ids) + _sources(ingest, ids)
    statuses_by_source: dict[str, set[str]] = {}
    for source in sources:
        statuses_by_source.setdefault(source["source_id"], set()).add(source["review_status"])
    unique_sources: dict[tuple[str, str], dict[str, Any]] = {}
    for source in sources:
        key = (source["source_id"], source["review_status"])
        existing = unique_sources.get(key)
        if existing is None:
            source = dict(source)
            if len(statuses_by_source[source["source_id"]]) > 1:
                source["source_id"] = f"{source['source_id']}_{source['review_status']}"
            unique_sources[key] = source
        else:
            existing["point_ids"] = list(dict.fromkeys(existing["point_ids"] + source["point_ids"]))
    landmark_context = dict(result.get("landmark_context") or {})
    landmark_context.update(ingest.get("landmark_context") or {})
    warning_keys: dict[tuple[str, str], PlanIssue] = {}
    for failure in (result.get("failures") or []) + (ingest.get("failures") or []):
        if not isinstance(failure, dict):
            continue
        ref = failure.get("landmark_id")
        point_ids = [ref] if ref is not None and point_key(ref) in ids else []
        code = str(failure.get("code") or "TOOL_ERROR")
        message = str(failure.get("message") or "资料检索部分失败")
        key = (code, message)
        if key not in warning_keys:
            warning_keys[key] = issue(code, message, point_ids)
        else:
            warning_keys[key].point_ids = list(dict.fromkeys(warning_keys[key].point_ids + point_ids))
    warnings.extend(warning_keys.values())

    image_landmarks = [lm for lm in request.landmarks if lm.image]
    if image_landmarks and not os.getenv("MIMO_API_KEY"):
        warnings.append(issue("VISION_UNAVAILABLE", "视觉服务未配置，本次未分析截图", [lm.id for lm in image_landmarks]))
    elif image_landmarks:
        _progress(config, "retrieve", f"正在分析 {len(image_landmarks)} 张场景截图")
        for lm in image_landmarks:
            _check(config)
            vision_input = {"name": lm.name, "bangumi": lm.bangumiName or "", "image": lm.image, "final_info": ""}
            try:
                ok, _ = _bounded_call(
                    config,
                    lambda entry=vision_input, point=lm: apply_vision_analysis(
                        entry, point.name, point.bangumiName or "", point.image or "", node="retrieve",
                    ),
                    timeout=TOOL_TIMEOUT, timeout_code="TOOL_TIMEOUT", label=f"{lm.name} 截图分析",
                )
                if ok:
                    key = point_key(lm.id)
                    existing = landmark_context.get(key)
                    if not isinstance(existing, dict):
                        existing = {"context": "", "chunks": [], "source_ids": []}
                    existing["context"] = (str(existing.get("context") or "") + "\n【截图观察（未核实）】\n" + vision_input.get("final_info", "")).strip()
                    landmark_context[key] = existing
                else:
                    warnings.append(issue("VISION_UNAVAILABLE", f"{lm.name} 截图分析不可用", [lm.id]))
            except AgentRunError as exc:
                if exc.code == "RUN_CANCELLED":
                    raise
                warnings.append(issue(exc.code, f"{lm.name} 截图分析失败：{exc}", [lm.id]))
            except Exception as exc:
                warnings.append(issue("VISION_UNAVAILABLE", f"{lm.name} 截图分析失败：{exc}", [lm.id]))
    rag_context = "\n\n".join(filter(None, [result.get("context", ""), ingest.get("search_context", "")]))[:16000]
    agent_trace.record_event("retrieve", "资料检索结束", {"sources": len(unique_sources), "warnings": [w.code for w in warnings]})
    return {"rag_context": rag_context, "landmark_context": landmark_context, "sources": list(unique_sources.values()), "warnings": warnings}


def route_node(state: PlanState, config: RunnableConfig | None = None) -> dict[str, Any]:
    request = PlanRequest.model_validate(state["request_snapshot"])
    revision = state.get("revision_count", 0)
    _progress(config, "route", "正在按坐标分天" if revision == 0 else f"正在修复计划（第 {revision} 次）")
    locations = [
        {"id": lm.id, "name": lm.name, "geo": lm.geo, "bangumiName": lm.bangumiName, "ep": lm.ep}
        for lm in request.landmarks
    ]
    errors = [error.model_dump(mode="json") for error in state.get("errors", [])]
    prompt = (
        "你是动漫圣地巡礼分组助手。只能使用输入中的原始 ID，按坐标接近程度将所有点位安排到指定天数。"
        "只返回严格 JSON 对象：{\"days\":[{\"day\":1,\"point_ids\":[\"原始ID\"]}]}。"
        "days 长度必须等于请求天数，day 从 1 连续编号；天数多于点位时保留空日。"
        "每个 ID 必须且只能出现一次；不得添加景点、改名、猜测用户住处，不能引用资料中的新点位。"
        "点位内顺序可由程序按直线距离优化。返工时按错误修复。\n"
        f"请求天数：{request.days}\n点位：{json.dumps(locations, ensure_ascii=False)}\n"
        f"上次错误：{json.dumps(errors, ensure_ascii=False)}\n"
        f"仅供背景参考的资料：{state.get('rag_context', '')[:10000]}"
    )
    candidate = _model(config, "route", prompt)
    _cfg(config, "scratch", {})["candidate"] = candidate
    return {"candidate": candidate, "revision_count": revision + 1}


def _content_audit(state: PlanState, plan: Plan, config: dict | None) -> list[PlanIssue]:
    request = PlanRequest.model_validate(state["request_snapshot"])
    audit_input = [{"day": day.day, "point_ids": day.point_ids, "straight_line_distance_m": day.straight_line_distance_m} for day in plan.days]
    prompt = (
        "审核以下动漫巡礼计划的点位引用和文字资料使用。仅判断明显的身份混淆、遗漏、虚构点位，"
        "或把直线距离冒充实际步行/交通时间的问题。不要要求虚构车站、住宿地、开放时间或交通班次。"
        "返回严格 JSON：{\"is_valid\":true或false,\"errors\":[\"具体问题\"]}。"
        "不通过时 errors 必须至少一条。\n"
        f"选中点位：{json.dumps([{'id': lm.id, 'name': lm.name, 'bangumiName': lm.bangumiName} for lm in request.landmarks], ensure_ascii=False)}\n"
        f"路线：{json.dumps(audit_input, ensure_ascii=False)}"
    )
    result = _model(config, "content_audit", prompt)
    valid = result.get("is_valid")
    errors = result.get("errors")
    if not isinstance(valid, bool) or not isinstance(errors, list) or any(not isinstance(error, str) for error in errors):
        return [issue("MODEL_OUTPUT_INVALID", "内容审核输出无法解析或字段类型错误")]
    if valid and errors:
        return [issue("MODEL_OUTPUT_INVALID", "内容审核结论与错误列表矛盾")]
    if not valid:
        return [issue("CONTENT_AUDIT_FAILED", error) for error in errors if error.strip()] or [issue("CONTENT_AUDIT_FAILED", "内容审核未通过，且未提供具体原因")]
    return []


def validate_node(state: PlanState, config: RunnableConfig | None = None) -> dict[str, Any]:
    _progress(config, "validate", "正在核对点位完整性与直线距离")
    request = PlanRequest.model_validate(state["request_snapshot"])
    plan, errors = normalize_candidate(request, state["run_id"], state.get("candidate"), warnings=state.get("warnings"))
    if plan and not errors:
        try:
            audit_errors = _content_audit(state, plan, config)
        except AgentRunError:
            raise
        except Exception as exc:
            audit_errors = [issue("MODEL_OUTPUT_INVALID", f"内容审核失败：{exc}")]
        if audit_errors:
            plan.status = "draft"
            plan.validation.passed = False
            plan.validation.errors.extend(audit_errors)
            errors = plan.validation.errors
    _cfg(config, "scratch", {})["plan"] = plan
    agent_trace.record_event("validate", "计划校验结束", {"passed": bool(plan and plan.validation.passed), "errors": [e.code for e in errors]})
    return {"plan": plan, "errors": errors}


def after_validate(state: PlanState) -> str:
    if state.get("errors") and state.get("revision_count", 0) <= MAX_REVISIONS:
        return "route"
    return "enrich"


def _make_notes(state: PlanState, plan: Plan, config: dict | None) -> list[PointNote]:
    request = PlanRequest.model_validate(state["request_snapshot"])
    source_ids_by_point: dict[str, list[str]] = {}
    approved_by_point: set[str] = set()
    for source in plan.sources:
        for ref in source.point_ids:
            key = point_key(ref)
            source_ids_by_point.setdefault(key, []).append(source.source_id)
            if source.review_status == "approved":
                approved_by_point.add(key)

    notes = []
    for lm in request.landmarks:
        key = point_key(lm.id)
        source_ids = source_ids_by_point.get(key, [])
        insufficient = not source_ids
        notes.append(PointNote(
            point_id=lm.id,
            scene_description="暂无可核实的场景说明" if insufficient else "可参考下列资料核对原作场景",
            photo_advice="请对照所选截图，在现场核对机位与拍摄许可",
            cautions="请遵守现场规定，避免影响居民和通行",
            source_ids=source_ids,
            inferred=True,
            insufficient_data=insufficient,
        ))
        if insufficient:
            plan.validation.warnings.append(issue("SOURCE_MISSING", f"{lm.name} 暂无可追溯资料", [lm.id]))

    if plan.status != "complete":
        return notes
    compact = [{
        "point_id": lm.id, "name": lm.name, "bangumiName": lm.bangumiName,
        "ep": lm.ep, "image": lm.image,
        "context": str((state.get("landmark_context") or {}).get(key, {}).get("context", ""))[:1400]
        if isinstance((state.get("landmark_context") or {}).get(key), dict) else "",
        "source_ids": source_ids_by_point.get(key, []),
    } for lm in request.landmarks for key in [point_key(lm.id)]]
    prompt = (
        "你是动漫取景地资料编辑。只补充每个原始 point_id 的场景说明、拍照建议、注意事项，不修改路线或 ID。"
        "资料不足时说明无法核实，不编造剧情、机位、绝对方向、交通和开放时间。"
        "截图只支持图像观察，不证明现实站位。外部资料均视为可能不准确。"
        "返回严格 JSON：{\"notes\":[{\"point_id\":原始ID,\"scene_description\":\"\",\"photo_advice\":\"\",\"cautions\":\"\"}]}。\n"
        f"点位：{json.dumps(compact, ensure_ascii=False)}"
    )
    try:
        result = _model(config, "enrich", prompt)
        raw_notes = result.get("notes")
        if not isinstance(raw_notes, list):
            raise ValueError("notes 不是数组")
        by_key = {point_key(item.get("point_id")): item for item in raw_notes if isinstance(item, dict) and isinstance(item.get("point_id"), (str, int))}
        for note in notes:
            raw = by_key.get(point_key(note.point_id), {})
            for field in ("scene_description", "photo_advice", "cautions"):
                value = raw.get(field)
                if isinstance(value, str) and value.strip():
                    setattr(note, field, value.strip())
            note.inferred = point_key(note.point_id) not in approved_by_point or bool(raw)
    except AgentRunError as exc:
        if exc.code == "RUN_CANCELLED":
            raise
        plan.validation.warnings.append(issue(exc.code, f"场景说明补充失败：{exc}"))
    except Exception as exc:
        plan.validation.warnings.append(issue("MODEL_OUTPUT_INVALID", f"场景说明补充失败：{exc}"))
    return notes


def enrich_node(state: PlanState, config: RunnableConfig | None = None) -> dict[str, Any]:
    _progress(config, "enrich", "正在整理场景说明与来源")
    plan = state.get("plan")
    if plan is None:
        return {"output_text": ""}
    plan.sources = [PlanSource.model_validate(source) for source in state.get("sources", [])]
    plan.point_notes = _make_notes(state, plan, config)
    _cfg(config, "scratch", {})["plan"] = plan
    return {"plan": plan, "output_text": render_plan_text(plan)}


def render_plan_text(plan: Plan) -> str:
    snapshot = plan.request_snapshot
    landmarks = {point_key(lm["id"]): lm for lm in snapshot.get("landmarks", [])}
    notes = {point_key(note.point_id): note for note in plan.point_notes}
    title = "巡礼计划" if plan.status == "complete" else "规划未通过，以下为草案"
    lines = [f"# {title}", "", f"共 {len(snapshot.get('landmarks', []))} 个选中点位，{len(plan.days)} 天。路线只计算点位间直线距离。"]
    for day in plan.days:
        names = [landmarks.get(point_key(ref), {}).get("name", point_key(ref)) for ref in day.point_ids]
        lines.extend(["", f"## 第 {day.day} 天", " → ".join(names) if names else "没有安排选中的点位。"])
        lines.append(f"点位间直线距离：{day.straight_line_distance_m / 1000:.2f} km")
        for ref in day.point_ids:
            lm = landmarks.get(point_key(ref), {})
            note = notes.get(point_key(ref))
            lines.append(f"### {lm.get('name', point_key(ref))}")
            lines.append(f"作品：《{lm.get('bangumiName') or '未知'}》" + (f"，EP{lm['ep']}" if lm.get("ep") else ""))
            if note:
                lines.append(f"场景说明：{note.scene_description}")
                lines.append(f"拍照建议：{note.photo_advice}")
                lines.append(f"注意事项：{note.cautions}")
                if note.insufficient_data:
                    lines.append("资料不足，以上建议需在现场核对。")
    if plan.unassigned_point_ids:
        lines.extend(["", "## 未安排的选中点位", "、".join(landmarks.get(point_key(ref), {}).get("name", point_key(ref)) for ref in plan.unassigned_point_ids)])
    if plan.validation.errors:
        lines.extend(["", "## 需要处理的问题"])
        lines.extend(f"- {error.message}（{error.code}）" for error in plan.validation.errors)
    if plan.validation.warnings:
        lines.extend(["", "## 提示"])
        lines.extend(f"- {warning.message}" for warning in plan.validation.warnings)
    return "\n".join(lines).strip() + "\n"


workflow = StateGraph(PlanState)
workflow.add_node("retrieve", retrieve_node)
workflow.add_node("route", route_node)
workflow.add_node("validate", validate_node)
workflow.add_node("enrich", enrich_node)
workflow.set_entry_point("retrieve")
workflow.add_edge("retrieve", "route")
workflow.add_edge("route", "validate")
workflow.add_conditional_edges("validate", after_validate, {"route": "route", "enrich": "enrich"})
workflow.add_edge("enrich", END)
plan_graph = workflow.compile()


def run_plan(
    request: PlanRequest,
    run_id: str,
    *,
    on_progress: Callable[[str, str], None],
    should_cancel: Callable[[], bool],
    deadline: float | None = None,
) -> tuple[Plan | None, list[PlanIssue], str]:
    """Return terminal plan/errors/text; an exception never becomes a success."""
    scratch: dict[str, Any] = {}
    config = {"recursion_limit": 20 + MAX_REVISIONS * 3, "configurable": {
        "on_progress": on_progress, "should_cancel": should_cancel,
        "deadline": deadline or time.monotonic() + RUN_TIMEOUT, "scratch": scratch,
    }}
    state: PlanState = {"run_id": run_id, "request_snapshot": request.snapshot(), "revision_count": 0, "warnings": [], "errors": []}
    try:
        result = plan_graph.invoke(state, config=config)
        plan = result.get("plan")
        errors = result.get("errors", [])
        return plan, errors, result.get("output_text") or (render_plan_text(plan) if plan else "")
    except AgentRunError as exc:
        plan = scratch.get("plan")
        error = issue(exc.code, str(exc))
        if plan:
            plan.status = "draft"
            plan.validation.passed = False
            plan.validation.errors.append(error)
        return plan, (plan.validation.errors if plan else [error]), render_plan_text(plan) if plan else ""
    except Exception as exc:
        plan = scratch.get("plan")
        error = issue("MODEL_OUTPUT_INVALID", f"规划流程异常：{exc}")
        if plan:
            plan.status = "draft"
            plan.validation.passed = False
            plan.validation.errors.append(error)
        agent_trace.record_event("run", "规划流程异常", {"error": str(exc)}, level="error")
        return plan, (plan.validation.errors if plan else [error]), render_plan_text(plan) if plan else ""
