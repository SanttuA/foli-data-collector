from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .timeutils import unix_to_iso


_ISO_DURATION_RE = re.compile(
    r"^(?P<sign>[+-])?P"
    r"(?:(?P<days>\d+(?:\.\d+)?)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+(?:\.\d+)?)H)?"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)M)?"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)S)?"
    r")?$",
    re.IGNORECASE,
)
_NUMERIC_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")


@dataclass(frozen=True)
class ParsedVm:
    status: str
    server_time_utc: str | None
    observations: list[dict[str, Any]]


@dataclass(frozen=True)
class ParsedAlerts:
    server_time_utc: str | None
    alerts: list[dict[str, Any]]


def parse_delay_seconds(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return int(float(value))

    text = str(value).strip()
    if not text:
        return None
    if _NUMERIC_RE.match(text):
        return int(float(text))

    match = _ISO_DURATION_RE.match(text)
    if not match:
        return None
    parts = match.groupdict()
    if not any(parts.get(name) for name in ("days", "hours", "minutes", "seconds")):
        return None
    total = (
        float(parts.get("days") or 0) * 86400
        + float(parts.get("hours") or 0) * 3600
        + float(parts.get("minutes") or 0) * 60
        + float(parts.get("seconds") or 0)
    )
    sign = -1 if parts.get("sign") == "-" else 1
    return int(sign * total)


def parse_vm_payload(payload: dict[str, Any]) -> ParsedVm:
    status = str(payload.get("status") or "UNKNOWN")
    result = payload.get("result")
    server_time_utc = unix_to_iso(payload.get("servertime"))
    observations: list[dict[str, Any]] = []

    if not isinstance(result, dict):
        return ParsedVm(status=status, server_time_utc=server_time_utc, observations=observations)

    vehicles = result.get("vehicles")
    if not isinstance(vehicles, dict):
        return ParsedVm(status=status, server_time_utc=server_time_utc, observations=observations)

    for vehicle_key, vehicle in vehicles.items():
        if not isinstance(vehicle, dict):
            continue
        observations.append(_parse_vehicle(vehicle_key, vehicle))

    return ParsedVm(status=status, server_time_utc=server_time_utc, observations=observations)


def parse_alerts_payload(payload: dict[str, Any]) -> ParsedAlerts:
    alerts: list[dict[str, Any]] = []
    server_time_utc = unix_to_iso(payload.get("servertime"))

    for item in payload.get("messages") or []:
        if isinstance(item, dict):
            alerts.append(_parse_message_alert(item, "message"))

    for item in payload.get("cancellations") or []:
        if isinstance(item, dict):
            alerts.append(_parse_cancellation(item))

    for key in ("global_message", "emergency_message"):
        item = payload.get(key)
        if isinstance(item, dict) and item:
            alerts.append(_parse_message_alert(item, key))

    return ParsedAlerts(server_time_utc=server_time_utc, alerts=alerts)


def _parse_vehicle(vehicle_key: str, vehicle: dict[str, Any]) -> dict[str, Any]:
    vehicle_id = _text(vehicle.get("vehicleref")) or str(vehicle_key)
    line_ref = _text(vehicle.get("lineref"))
    direction_ref = _text(vehicle.get("directionref"))
    origin_departure = _int_or_none(vehicle.get("originaimeddeparturetime"))
    is_gtfs_matchable = bool(line_ref and direction_ref and origin_departure is not None)
    trip_match_key = (
        f"{line_ref}|{direction_ref}|{origin_departure}" if is_gtfs_matchable else None
    )

    delay_text = None if vehicle.get("delay") is None else str(vehicle.get("delay"))
    return {
        "vehicle_id": vehicle_id,
        "recorded_at_utc": unix_to_iso(vehicle.get("recordedattime")),
        "valid_until_utc": unix_to_iso(vehicle.get("validuntiltime")),
        "line_ref": line_ref,
        "direction_ref": direction_ref,
        "origin_aimed_departure_time_utc": unix_to_iso(origin_departure),
        "origin_aimed_departure_unix": origin_departure,
        "trip_match_key": trip_match_key,
        "is_gtfs_matchable": is_gtfs_matchable,
        "published_line_name": _text(vehicle.get("publishedlinename")),
        "operator_ref": _text(vehicle.get("operatorref")),
        "origin_ref": _text(vehicle.get("originref")),
        "origin_name": _text(vehicle.get("originname")),
        "destination_ref": _text(vehicle.get("destinationref")),
        "destination_name": _text(vehicle.get("destinationname")),
        "destination_aimed_arrival_time_utc": unix_to_iso(
            vehicle.get("destinationaimedarrivaltime")
        ),
        "destination_aimed_arrival_unix": _int_or_none(
            vehicle.get("destinationaimedarrivaltime")
        ),
        "latitude": _float_or_none(vehicle.get("latitude")),
        "longitude": _float_or_none(vehicle.get("longitude")),
        "delay_text": delay_text,
        "delay_seconds": parse_delay_seconds(vehicle.get("delay")),
        "in_congestion": _bool_or_none(vehicle.get("incongestion")),
        "in_panic": _bool_or_none(vehicle.get("inpanic")),
        "monitored": _bool_or_none(vehicle.get("monitored")),
        "vehicle_at_stop": _bool_or_none(vehicle.get("vehicleatstop")),
        "next_stop_point_ref": _text(vehicle.get("next_stoppointref")),
        "next_stop_point_name": _text(vehicle.get("next_stoppointname")),
        "next_destination_display": _text(vehicle.get("next_destinationdisplay")),
        "next_aimed_arrival_time_utc": unix_to_iso(vehicle.get("next_aimedarrivaltime")),
        "next_expected_arrival_time_utc": unix_to_iso(vehicle.get("next_expectedarrivaltime")),
        "next_aimed_departure_time_utc": unix_to_iso(vehicle.get("next_aimeddeparturetime")),
        "next_expected_departure_time_utc": unix_to_iso(
            vehicle.get("next_expecteddeparturetime")
        ),
    }


def _parse_message_alert(item: dict[str, Any], alert_type: str) -> dict[str, Any]:
    repeat = item.get("repeat")
    validity_start = None
    validity_end = None
    if isinstance(repeat, list) and repeat and isinstance(repeat[0], list) and len(repeat[0]) >= 2:
        validity_start = unix_to_iso(repeat[0][0])
        validity_end = unix_to_iso(repeat[0][1])

    return {
        "alert_type": alert_type,
        "source_alert_id": _text(item.get("message_id")),
        "line_ref": _single_or_none(item.get("affected_routes")),
        "cause": _text(item.get("cause")),
        "effect": _text(item.get("effect")),
        "priority": _int_or_none(item.get("priority")),
        "is_active": _bool_or_none(item.get("isactive")),
        "departure_time_utc": None,
        "validity_start_utc": validity_start,
        "validity_end_utc": validity_end,
        "icon": _text(item.get("icon")),
        "header": _text(item.get("header")),
        "message": _text(item.get("message")),
        "information": _text(item.get("information")),
        "affected_routes_json": _json_text(item.get("affected_routes", [])),
        "affected_stops_json": _json_text(item.get("affected_stops", [])),
        "categories_json": _json_text(item.get("categories", [])),
        "repeat_json": _json_text(repeat or []),
        "stops_json": None,
    }


def _parse_cancellation(item: dict[str, Any]) -> dict[str, Any]:
    stops = item.get("stops") or []
    is_active = any(bool(stop.get("isactive")) for stop in stops if isinstance(stop, dict))
    return {
        "alert_type": "cancellation",
        "source_alert_id": None,
        "line_ref": _text(item.get("line")),
        "cause": _text(item.get("cause")),
        "effect": _text(item.get("effect")),
        "priority": _int_or_none(item.get("priority")),
        "is_active": is_active,
        "departure_time_utc": unix_to_iso(item.get("departure")),
        "validity_start_utc": None,
        "validity_end_utc": None,
        "icon": _text(item.get("icon")),
        "header": None,
        "message": None,
        "information": None,
        "affected_routes_json": _json_text([item.get("line")] if item.get("line") else []),
        "affected_stops_json": _json_text(
            [stop.get("stop") for stop in stops if isinstance(stop, dict) and stop.get("stop")]
        ),
        "categories_json": _json_text(item.get("categories", [])),
        "repeat_json": None,
        "stops_json": _json_text(stops),
    }


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text != "" else None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_or_none(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _single_or_none(value: Any) -> str | None:
    if isinstance(value, list) and len(value) == 1:
        return _text(value[0])
    return None


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

