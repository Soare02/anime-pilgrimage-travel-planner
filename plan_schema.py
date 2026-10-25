"""Versioned data contract for a single Agent planning run."""

from __future__ import annotations

import math
import os
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator, model_validator


PointId = StrictStr | StrictInt


def point_key(value: PointId) -> str:
    """The model sees string IDs; retain the input ID's original JSON type in plans."""
    return str(value)


def _positive_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        return value if value > 0 else default
    except ValueError:
        return default


MAX_LANDMARKS = _positive_env("AGENT_MAX_LANDMARKS", 50)
MAX_DAYS = _positive_env("AGENT_MAX_DAYS", 30)


class Landmark(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: PointId
    name: str
    geo: list[float]
    originalName: str | None = None
    bangumiName: str | None = None
    bangumiOriginalName: str | None = None
    ep: str | int | float | None = None
    s: int | float | None = None
    image: str | None = None

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: PointId) -> PointId:
        if not point_key(value).strip():
            raise ValueError("地标 ID 不能为空")
        return value

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("地标名称不能为空")
        return value

    @field_validator("geo", mode="before")
    @classmethod
    def valid_geo(cls, value: Any) -> list[float]:
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError("geo 必须是 [纬度, 经度] 两个数值")
        if any(isinstance(n, bool) or not isinstance(n, (int, float)) for n in value):
            raise ValueError("坐标必须是数值")
        lat, lng = (float(n) for n in value)
        if not all(math.isfinite(n) for n in (lat, lng)):
            raise ValueError("坐标必须是有限数值")
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError("坐标超出合法经纬度范围")
        return [lat, lng]


class PlanRequest(BaseModel):
    days: StrictInt = Field(gt=0, le=MAX_DAYS)
    landmarks: list[Landmark] = Field(min_length=1, max_length=MAX_LANDMARKS)

    @model_validator(mode="after")
    def unique_ids(self) -> "PlanRequest":
        ids = [point_key(lm.id) for lm in self.landmarks]
        if len(ids) != len(set(ids)):
            raise ValueError("地标 ID 不能重复")
        return self

    def snapshot(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_unset=True)


class PlanIssue(BaseModel):
    code: str
    message: str
    point_ids: list[PointId] = Field(default_factory=list)
    day: int | None = None


class PlanValidation(BaseModel):
    passed: bool = False
    errors: list[PlanIssue] = Field(default_factory=list)
    warnings: list[PlanIssue] = Field(default_factory=list)


class PlanLeg(BaseModel):
    from_id: PointId
    to_id: PointId
    distance_m: float = Field(ge=0)
    distance_type: Literal["straight_line"] = "straight_line"


class PlanDay(BaseModel):
    day: int
    point_ids: list[PointId] = Field(default_factory=list)
    legs: list[PlanLeg] = Field(default_factory=list)
    straight_line_distance_m: float = Field(default=0, ge=0)


class PointNote(BaseModel):
    point_id: PointId
    scene_description: str = ""
    photo_advice: str = ""
    cautions: str = ""
    source_ids: list[str] = Field(default_factory=list)
    inferred: bool = False
    insufficient_data: bool = False


class PlanSource(BaseModel):
    source_id: str
    url: str | None = None
    title: str = ""
    retrieved_at: str | None = None
    review_status: Literal["approved", "unreviewed", "missing"] = "missing"
    point_ids: list[PointId] = Field(default_factory=list)


class Plan(BaseModel):
    schema_version: Literal[1] = 1
    plan_id: str
    run_id: str
    status: Literal["complete", "draft"]
    request_snapshot: dict[str, Any]
    days: list[PlanDay]
    point_notes: list[PointNote] = Field(default_factory=list)
    sources: list[PlanSource] = Field(default_factory=list)
    unassigned_point_ids: list[PointId] = Field(default_factory=list)
    validation: PlanValidation
