"""Candidate normalization and non-LLM plan invariants."""

from __future__ import annotations

import math
import uuid
from datetime import timedelta
from typing import Any

from plan_geometry import build_day, ordering_constraints, respects_order, straight_line_distance_m
from plan_schema import Plan, PlanIssue, PlanValidation, PointId, PlanRequest, ScenePreference, WeatherSnapshot, point_key


def issue(code: str, message: str, point_ids: list[PointId] | None = None, day: int | None = None) -> PlanIssue:
    return PlanIssue(code=code, message=message, point_ids=point_ids or [], day=day)


def normalize_candidate(
    request: PlanRequest,
    run_id: str,
    candidate: Any,
    *,
    warnings: list[PlanIssue] | None = None,
    audit_errors: list[PlanIssue] | None = None,
    scene_preferences: list[ScenePreference] | None = None,
    weather: list[WeatherSnapshot] | None = None,
) -> tuple[Plan | None, list[PlanIssue]]:
    """Keep valid candidate IDs, expose every rejected or missing reference."""
    if not isinstance(candidate, dict) or not isinstance(candidate.get("days"), list):
        return None, [issue("MODEL_OUTPUT_INVALID", "模型未返回可解析的逐日计划")]
    raw_days = candidate["days"]
    errors: list[PlanIssue] = list(audit_errors or [])
    if len(raw_days) != request.days:
        errors.append(issue("DAY_COUNT_MISMATCH", f"返回 {len(raw_days)} 天，要求 {request.days} 天"))

    original = {point_key(lm.id): lm.id for lm in request.landmarks}
    groups: dict[int, list[PointId]] = {day: [] for day in range(1, request.days + 1)}
    used: set[str] = set()
    seen_days: set[int] = set()
    day_details: dict[int, dict] = {}
    for index, raw_day in enumerate(raw_days, start=1):
        if not isinstance(raw_day, dict):
            errors.append(issue("MODEL_OUTPUT_INVALID", f"第 {index} 个每日安排不是对象"))
            continue
        day = raw_day.get("day", raw_day.get("day_number"))
        if isinstance(day, bool) or not isinstance(day, int) or day < 1 or day > request.days or day in seen_days:
            errors.append(issue("DAY_COUNT_MISMATCH", f"第 {index} 个每日安排的 day 无效或重复"))
            continue
        seen_days.add(day)
        day_details[day] = raw_day
        refs = raw_day.get("point_ids")
        if not isinstance(refs, list):
            errors.append(issue("MODEL_OUTPUT_INVALID", f"第 {day} 天缺少 point_ids 数组", day=day))
            continue
        for ref in refs:
            if isinstance(ref, bool) or not isinstance(ref, (str, int)):
                errors.append(issue("MODEL_OUTPUT_INVALID", f"第 {day} 天包含无效的地标 ID", day=day))
                continue
            key = point_key(ref)
            if key not in original:
                errors.append(issue("UNKNOWN_LANDMARK", f"第 {day} 天引用了未选中的地标 ID：{key}", day=day))
            elif key in used:
                errors.append(issue("DUPLICATE_LANDMARK", f"地标 ID {key} 被重复安排", [original[key]], day))
            else:
                used.add(key)
                groups[day].append(original[key])

    unassigned = [lm.id for lm in request.landmarks if point_key(lm.id) not in used]
    if unassigned:
        errors.append(issue("MISSING_LANDMARK", f"有 {len(unassigned)} 个选中的地标尚未安排", unassigned))
    if not used:
        errors.append(issue("MODEL_OUTPUT_INVALID", "没有可显示的有效候选点位"))
        return None, errors

    all_warnings = list(warnings or [])
    days = []
    for day_number in range(1, request.days + 1):
        day = build_day(day_number, groups[day_number], request.landmarks, scene_preferences)
        day.date = request.start_date + timedelta(days=day_number - 1) if request.start_date else None
        details = day_details.get(day_number, {})
        for field in ("planning_reason", "weather_advice"):
            value = details.get(field)
            if isinstance(value, str):
                setattr(day, field, value.strip()[:1200])
        days.append(day)
        if not day.point_ids:
            all_warnings.append(issue("EMPTY_DAY", f"第 {day_number} 天没有安排选中的点位", day=day_number))
        if any(leg.distance_m > 50_000 for leg in day.legs):
            all_warnings.append(issue("CROSS_REGION", f"第 {day_number} 天存在较远的点位间直线距离，请自行核实交通", day=day_number))

    plan = Plan(
        plan_id=f"plan_{uuid.uuid4().hex}",
        run_id=run_id,
        status="draft" if errors else "complete",
        request_snapshot=request.snapshot(),
        days=days,
        unassigned_point_ids=unassigned,
        validation=PlanValidation(passed=not errors, errors=errors, warnings=all_warnings),
        scene_preferences=scene_preferences or [], weather=weather or [],
    )
    invariant_errors = validate_plan(plan, request)
    if invariant_errors:
        plan.validation.errors.extend(invariant_errors)
        plan.validation.passed = False
        plan.status = "draft"
    return plan, plan.validation.errors


def validate_plan(plan: Plan, request: PlanRequest) -> list[PlanIssue]:
    errors: list[PlanIssue] = []
    known = {point_key(lm.id): lm for lm in request.landmarks}
    assigned: list[str] = []
    if len(plan.days) != request.days or [day.day for day in plan.days] != list(range(1, request.days + 1)):
        errors.append(issue("DAY_COUNT_MISMATCH", "每日安排必须与请求天数一致且从第 1 天连续编号"))
    for day in plan.days:
        keys = [point_key(pid) for pid in day.point_ids]
        assigned.extend(keys)
        expected_date = request.start_date + timedelta(days=day.day - 1) if request.start_date else None
        if day.date != expected_date:
            errors.append(issue("DAY_DATE_MISMATCH", "行程日期与出发日期不一致", day=day.day))
        constraints = ordering_constraints(day.point_ids, request.landmarks, plan.scene_preferences)
        if not respects_order(keys, constraints):
            errors.append(issue("SCENE_ORDER_CONFLICT", "访问顺序与原作场景时段或剧情顺序冲突", day=day.day))
        if len(day.legs) != max(0, len(keys) - 1):
            errors.append(issue("MODEL_OUTPUT_INVALID", "路段数量与点位顺序不一致", day=day.day))
            continue
        total = 0.0
        for idx, leg in enumerate(day.legs):
            left, right = point_key(leg.from_id), point_key(leg.to_id)
            if (left, right) != (keys[idx], keys[idx + 1]) or leg.distance_type != "straight_line":
                errors.append(issue("MODEL_OUTPUT_INVALID", "路段顺序或距离类型不一致", day=day.day))
                continue
            if left in known and right in known:
                expected = straight_line_distance_m(known[left].geo, known[right].geo)
                if not math.isfinite(leg.distance_m) or abs(leg.distance_m - expected) > 0.01:
                    errors.append(issue("MODEL_OUTPUT_INVALID", "路段距离与坐标计算不一致", day=day.day))
            total += leg.distance_m
        if not math.isfinite(day.straight_line_distance_m) or abs(day.straight_line_distance_m - total) > 0.01:
            errors.append(issue("MODEL_OUTPUT_INVALID", "每日距离与路段之和不一致", day=day.day))
    unassigned = [point_key(pid) for pid in plan.unassigned_point_ids]
    for key in assigned + unassigned:
        if key not in known:
            errors.append(issue("UNKNOWN_LANDMARK", f"计划引用了未选中的地标 ID：{key}"))
    if len(assigned + unassigned) != len(set(assigned + unassigned)):
        errors.append(issue("DUPLICATE_LANDMARK", "已安排与未安排列表存在重复地标"))
    if set(assigned + unassigned) != set(known):
        errors.append(issue("MISSING_LANDMARK", "选中的地标未全部出现在计划中"))
    if plan.status == "complete" and (unassigned or plan.validation.errors or not plan.validation.passed):
        errors.append(issue("MODEL_OUTPUT_INVALID", "完整结果不能包含未安排点位或校验错误"))
    return errors

