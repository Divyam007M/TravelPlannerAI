"""Server-side geocoding, forecast and exchange-rate services.

The small process cache reduces calls to the public APIs. It is best-effort on
serverless instances; every returned rate keeps its provider observation date.
"""
from __future__ import annotations

import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from babel.numbers import format_currency, get_territory_currencies

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
RATE_URL = "https://api.frankfurter.dev/v2/rate"
FORECAST_DAYS = 16
WEATHER_SOURCE = "Open-Meteo"
RATE_SOURCE = "Frankfurter"
WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
    55: "Dense drizzle", 56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain", 71: "Slight snowfall",
    73: "Moderate snowfall", 75: "Heavy snowfall", 77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers", 95: "Thunderstorm",
    96: "Thunderstorm with slight hail", 97: "Heavy thunderstorm",
    99: "Thunderstorm with heavy hail",
}


class ServiceUnavailable(Exception):
    """The remote provider failed or returned unusable data."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _fetch_json(url: str, *, params: dict | None = None) -> dict:
    try:
        response = httpx.get(url, params=params, timeout=8.0, follow_redirects=False)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Expected a JSON object")
        return data
    except (httpx.HTTPError, ValueError) as exc:
        raise ServiceUnavailable("Provider unavailable") from exc


class _Cache:
    def __init__(self):
        self._items: dict[tuple, tuple[float, object]] = {}
        self._lock = threading.Lock()

    def get(self, key: tuple, *, allow_expired: bool = False):
        with self._lock:
            item = self._items.get(key)
        if item and (allow_expired or item[0] > time.monotonic()):
            return item[1]
        return None

    def put(self, key: tuple, value, ttl: int):
        with self._lock:
            self._items[key] = (time.monotonic() + ttl, value)


_cache = _Cache()


def _name(value: object) -> str:
    return str(value or "").strip().casefold()


def _place_label(item: dict) -> str:
    parts = []
    for value in (item.get("name"), item.get("admin1"), item.get("country")):
        if value and _name(value) not in {_name(existing) for existing in parts}:
            parts.append(str(value))
    return ", ".join(parts)


def resolve_location(query: str) -> dict:
    """Resolve a named place; never guess between exact names in different regions."""
    query = query.strip()
    if len(query) < 2 or len(query) > 120:
        return {"status": "invalid", "message": "Provide a city or region name (2–120 characters)."}
    key = ("geo", query.casefold())
    cached = _cache.get(key)
    if cached:
        return cached
    try:
        payload = _fetch_json(GEOCODE_URL, params={"name": query, "count": 10, "language": "en"})
    except ServiceUnavailable:
        return {"status": "unavailable", "message": "Location search is temporarily unavailable. Please try again."}
    results = payload.get("results") or []
    if not isinstance(results, list):
        return {"status": "unavailable", "message": "Location search returned unusable data."}
    place_name, _, qualifier = query.partition(",")
    exact = [item for item in results if isinstance(item, dict) and _name(item.get("name")) == _name(place_name)]
    candidates = exact or [item for item in results if isinstance(item, dict)]
    if qualifier.strip():
        qualifier_name = _name(qualifier)
        candidates = [item for item in candidates if qualifier_name in {
            _name(item.get("country")), _name(item.get("country_code")),
            _name(item.get("admin1")), _name(item.get("admin2")),
        }]
        # A country alone can contain several settlements with the same name.
        # Prefer a single matching island or administrative region only when the
        # user explicitly supplied that country (e.g. Bali, Indonesia). Ordinary
        # duplicate settlements still need clarification.
        country_matches = [item for item in candidates if qualifier_name in {
            _name(item.get("country")), _name(item.get("country_code")),
        }]
        primary_regions = [item for item in country_matches
                           if _name(item.get("admin1")) == _name(place_name)
                           and item.get("feature_code") in {"ISL", "ADM1"}]
        if len(primary_regions) == 1:
            candidates = primary_regions
    if not candidates:
        result = {"status": "not_found", "message": f"Could not resolve {query!r}. Please add a country or region; no coordinates were assumed."}
    else:
        distinct = {(item.get("name"), item.get("admin1"), item.get("country_code")) for item in candidates}
        if len(distinct) > 1:
            labels = list(dict.fromkeys(_place_label(item) for item in candidates))[:5]
            result = {"status": "ambiguous", "message": "Which place do you mean? " + "; ".join(labels) + ". Include the country or region.", "candidates": labels}
        else:
            item = candidates[0]
            try:
                latitude, longitude = float(item["latitude"]), float(item["longitude"])
                if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                    raise ValueError
            except (KeyError, TypeError, ValueError):
                return {"status": "unavailable", "message": "Location search returned unusable coordinates."}
            country_code = str(item.get("country_code") or "").upper()
            currencies = get_territory_currencies(country_code, tender=True) if country_code else []
            result = {"status": "resolved", "location": {
                "name": item.get("name"), "label": _place_label(item),
                "country": item.get("country"), "country_code": country_code,
                "region": item.get("admin1"), "latitude": latitude, "longitude": longitude,
                "timezone": item.get("timezone"),
                "usual_currency": currencies[0] if len(currencies) == 1 else None,
            }, "source": WEATHER_SOURCE}
    _cache.put(key, result, 86400)
    return result


def _local_today(tz_name: str | None) -> date:
    try:
        return datetime.now(ZoneInfo(tz_name)).date() if tz_name else _utc_now().date()
    except ZoneInfoNotFoundError:
        return _utc_now().date()


def weather_forecast(destination: str, start_date: str | None = None, days: int = 3) -> dict:
    location_result = resolve_location(destination)
    if location_result["status"] != "resolved":
        return location_result
    location = location_result["location"]
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 60:
        return {"status": "invalid", "message": "Days must be a whole number from 1 to 60."}
    today = _local_today(location.get("timezone"))
    try:
        start = date.fromisoformat(start_date) if start_date else today
    except ValueError:
        return {"status": "invalid", "message": "Use an ISO travel date such as 2026-10-03."}
    end = start + timedelta(days=days - 1)
    horizon = today + timedelta(days=FORECAST_DAYS - 1)
    if start > horizon or end < today:
        return {"status": "outside_horizon", "location": location["label"], "timezone": location.get("timezone"),
                "requested_dates": [start.isoformat(), end.isoformat()], "forecast_through": horizon.isoformat(),
                "message": "No reliable day-by-day forecast is available for these dates. Offer only clearly labeled general seasonal guidance, without invented forecast values.",
                "source": WEATHER_SOURCE}
    key = ("weather", location["latitude"], location["longitude"])
    payload = _cache.get(key)
    if not payload:
        try:
            payload = _fetch_json(FORECAST_URL, params={
                "latitude": location["latitude"], "longitude": location["longitude"],
                "timezone": location.get("timezone") or "auto", "forecast_days": FORECAST_DAYS,
                "current": "temperature_2m,precipitation,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,weather_code",
            })
            if not isinstance(payload.get("daily"), dict) or not isinstance(payload["daily"].get("time"), list):
                raise ServiceUnavailable("Missing daily forecast")
            payload = {"data": payload, "retrieved_at": _utc_now().isoformat(timespec="seconds")}
            _cache.put(key, payload, 600)
        except ServiceUnavailable:
            return {"status": "unavailable", "location": location["label"], "message": "Weather forecast is temporarily unavailable; continue planning without forecast values.", "source": WEATHER_SOURCE}
    data = payload["data"]
    daily = data["daily"]
    rows = []
    for index, day in enumerate(daily["time"]):
        if start.isoformat() <= day <= end.isoformat():
            rows.append({"date": day,
                         "min_c": _at(daily, "temperature_2m_min", index),
                         "max_c": _at(daily, "temperature_2m_max", index),
                         "precipitation_mm": _at(daily, "precipitation_sum", index),
                         "precipitation_probability_percent": _at(daily, "precipitation_probability_max", index),
                         "weather_code": _at(daily, "weather_code", index),
                         "condition": WEATHER_CODES.get(_at(daily, "weather_code", index))})
    current = data.get("current") if start_date is None or start <= today <= end else None
    if isinstance(current, dict):
        current = {**current, "condition": WEATHER_CODES.get(current.get("weather_code")),
                   "note": "Model-based current conditions, not a direct station observation"}
    return {"status": "ok", "location": location["label"], "timezone": data.get("timezone") or location.get("timezone"),
            "current": current, "forecast": rows, "requested_dates": [start.isoformat(), end.isoformat()],
            "forecast_through": horizon.isoformat(), "partial": end > horizon or start < today,
            "units": {"temperature": "°C", "precipitation": "mm", "precipitation_probability": "%"},
            "retrieved_at_utc": payload["retrieved_at"], "source": WEATHER_SOURCE,
            "source_url": "https://open-meteo.com/en/docs"}


def _at(data: dict, key: str, index: int):
    values = data.get(key)
    return values[index] if isinstance(values, list) and index < len(values) else None


def convert_currency(amount: str | float, base: str, target: str) -> dict:
    """Convert with one provider rate; an expired cache is explicitly marked."""
    base, target = str(base).strip().upper(), str(target).strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", base) or not re.fullmatch(r"[A-Z]{3}", target):
        return {"status": "invalid", "message": "Use three-letter ISO currency codes, such as INR and EUR."}
    try:
        value = Decimal(str(amount))
        if not value.is_finite() or value < 0 or value > Decimal("1000000000000"):
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        return {"status": "invalid", "message": "Amount must be a nonnegative number no greater than one trillion."}
    if base == target:
        return {"status": "ok", "base": base, "target": target, "amount": str(value),
                "converted": str(value), "formatted_amount": format_currency(value, base, locale="en_US"),
                "formatted_converted": format_currency(value, target, locale="en_US"),
                "rate": "1", "as_of": None, "source": "Identity conversion", "cached": False}
    key = ("rate", base, target)
    record = _cache.get(key)
    cached = False
    if not record:
        try:
            data = _fetch_json(f"{RATE_URL}/{base.lower()}/{target.lower()}")
            rate = Decimal(str(data["rate"]))
            observation = date.fromisoformat(data["date"])
            if rate <= 0 or not rate.is_finite() or data.get("base", "").upper() != base or data.get("quote", "").upper() != target:
                raise ValueError
            record = {"rate": rate, "as_of": observation.isoformat(), "retrieved_at_utc": _utc_now().isoformat(timespec="seconds")}
            _cache.put(key, record, 21600)
        except (ServiceUnavailable, KeyError, InvalidOperation, ValueError, TypeError):
            record = _cache.get(key, allow_expired=True)
            if not record:
                return {"status": "unavailable", "message": f"No verified {base}/{target} rate is available from {RATE_SOURCE}. Try again later or check the currency codes.", "source": RATE_SOURCE}
            cached = True
    converted = value * record["rate"]
    return {"status": "ok", "base": base, "target": target, "amount": str(value),
            "converted": str(converted), "formatted_amount": format_currency(value, base, locale="en_US"),
            "formatted_converted": format_currency(converted, target, locale="en_US"),
            "rate": str(record["rate"]), "as_of": record["as_of"],
            "as_of_note": "Provider observation date; time of day is not published",
            "retrieved_at_utc": record["retrieved_at_utc"], "source": RATE_SOURCE,
            "source_url": "https://frankfurter.dev/", "cached": cached}
