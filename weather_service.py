"""Small, dated weather snapshots queried by landmark coordinates."""

import math
import os
import re
from datetime import datetime, timezone

import requests

from plan_schema import WeatherForecast, WeatherHour, WeatherSnapshot


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _description(value: dict) -> str:
    for key in ("lang_zh", "weatherDesc"):
        entries = value.get(key)
        if isinstance(entries, list) and entries and isinstance(entries[0], dict):
            text = entries[0].get("value")
            if isinstance(text, str) and text.strip():
                return text.strip()
    return ""


def _sun_time(value) -> str | None:
    match = re.fullmatch(r"(\d{1,2}):(\d{2})\s*(AM|PM)?", str(value or "").strip().upper())
    if not match:
        return None
    hour, minute = int(match[1]), int(match[2])
    if match[3]:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if match[3] == "PM" else 0)
    return f"{hour:02d}:{minute:02d}" if 0 <= hour < 24 and 0 <= minute < 60 else None


def fetch_weather_snapshot(geo: list[float]) -> WeatherSnapshot:
    """Keep provider dates; a current observation is never a future forecast."""
    location = f"{geo[0]:.4f},{geo[1]:.4f}"
    url = f"https://wttr.in/{location}"
    timeout = _number(os.getenv("WEATHER_TIMEOUT_SECONDS", "6")) or 6
    response = requests.get(url, params={"format": "j1", "lang": "zh"}, timeout=max(1, timeout))
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("天气服务未返回 JSON 对象")

    areas = data.get("nearest_area") or []
    if areas and isinstance(areas[0], dict):
        names = areas[0].get("areaName") or []
        if names and isinstance(names[0], dict):
            location = str(names[0].get("value") or location)

    current = data.get("current_condition") or []
    current_summary = ""
    if current and isinstance(current[0], dict):
        current_summary = _description(current[0])
        temperature = _number(current[0].get("temp_C"))
        if temperature is not None:
            current_summary += f"，{temperature:g}°C"

    forecast = []
    for day in data.get("weather", []) or []:
        if not isinstance(day, dict):
            continue
        hours = [hour for hour in day.get("hourly", []) if isinstance(hour, dict)]
        descriptions = list(dict.fromkeys(filter(None, (_description(hour) for hour in hours))))
        rain = [value for hour in hours if (value := _number(hour.get("chanceofrain"))) is not None and 0 <= value <= 100]
        hourly = []
        for hour in hours:
            clock = _number(hour.get("time"))
            if clock is None or not clock.is_integer():
                continue
            h, minute = divmod(int(clock), 100)
            if not (0 <= h < 24 and 0 <= minute < 60):
                continue
            chance = _number(hour.get("chanceofrain"))
            hourly.append(WeatherHour(
                time=f"{h:02d}:{minute:02d}", summary=_description(hour) or "天气描述缺失",
                temp_c=_number(hour.get("tempC")),
                rain_chance_percent=round(chance) if chance is not None and 0 <= chance <= 100 else None,
            ))
        try:
            astronomy = day.get("astronomy") or []
            sun = astronomy[0] if astronomy and isinstance(astronomy[0], dict) else {}
            forecast.append(WeatherForecast(
                date=day.get("date"), summary=" / ".join(descriptions) or "天气描述缺失",
                min_temp_c=_number(day.get("mintempC")), max_temp_c=_number(day.get("maxtempC")),
                rain_chance_percent=round(max(rain)) if rain else None,
                hourly=hourly,
                sunrise=_sun_time(sun.get("sunrise")), sunset=_sun_time(sun.get("sunset")),
            ))
        except ValueError:
            continue  # A malformed date cannot be attached to a travel day.
    if not current_summary and not forecast:
        raise ValueError("天气服务没有返回可用的实况或带日期的预报")
    return WeatherSnapshot(
        location=location, geo=list(geo), retrieved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        current_summary=current_summary, forecast=forecast, source_url=url,
    )
