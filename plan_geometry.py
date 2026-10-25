"""Deterministic point ordering and straight-line geometry for Agent plans."""

from __future__ import annotations

import math
from typing import Iterable

from plan_schema import Landmark, PlanDay, PlanLeg, PointId, point_key


EARTH_RADIUS_M = 6_371_008.8


def straight_line_distance_m(left: Iterable[float], right: Iterable[float]) -> float:
    lat1, lon1 = (math.radians(value) for value in left)
    lat2, lon2 = (math.radians(value) for value in right)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1, math.sqrt(a)))


def distance_matrix(landmarks: list[Landmark]) -> dict[tuple[str, str], float]:
    matrix: dict[tuple[str, str], float] = {}
    for left in landmarks:
        for right in landmarks:
            matrix[point_key(left.id), point_key(right.id)] = straight_line_distance_m(left.geo, right.geo)
    return matrix


def _path_length(keys: list[str], matrix: dict[tuple[str, str], float]) -> float:
    return sum(matrix[(a, b)] for a, b in zip(keys, keys[1:]))


def order_point_ids(point_ids: list[PointId], landmarks: list[Landmark]) -> list[PointId]:
    """Try each start, then bounded 2-opt; ID breaks all distance ties."""
    if len(point_ids) < 3:
        if len(point_ids) == 2:
            return sorted(point_ids, key=point_key)
        return point_ids[:]
    matrix = distance_matrix(landmarks)
    ids = {point_key(value): value for value in point_ids}
    keys = sorted(ids)
    best: list[str] | None = None
    best_score = math.inf
    for start in keys:
        route = [start]
        remaining = set(keys) - {start}
        while remaining:
            next_key = min(remaining, key=lambda key: (matrix[(route[-1], key)], key))
            route.append(next_key)
            remaining.remove(next_key)
        # The daily route has no required starting location, so a local reversal
        # can improve the path without pretending to know a hotel or station.
        for _ in range(min(20, len(route) * 2)):
            candidate = route
            candidate_score = _path_length(route, matrix)
            for i in range(len(route) - 1):
                for j in range(i + 2, len(route) + 1):
                    trial = route[:i] + list(reversed(route[i:j])) + route[j:]
                    score = _path_length(trial, matrix)
                    if (score, trial) < (candidate_score, candidate):
                        candidate, candidate_score = trial, score
            if candidate == route:
                break
            route = candidate
        score = _path_length(route, matrix)
        if (score, route) < (best_score, best or []):
            best, best_score = route, score
    return [ids[key] for key in (best or keys)]


def build_day(day: int, point_ids: list[PointId], landmarks: list[Landmark]) -> PlanDay:
    ordered = order_point_ids(point_ids, landmarks)
    by_id = {point_key(lm.id): lm for lm in landmarks}
    legs = []
    for left, right in zip(ordered, ordered[1:]):
        distance = straight_line_distance_m(by_id[point_key(left)].geo, by_id[point_key(right)].geo)
        legs.append(PlanLeg(from_id=left, to_id=right, distance_m=round(distance, 3)))
    return PlanDay(
        day=day,
        point_ids=ordered,
        legs=legs,
        straight_line_distance_m=round(sum(leg.distance_m for leg in legs), 3),
    )

