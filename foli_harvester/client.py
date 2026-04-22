from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class JsonResponse:
    payload: dict[str, Any]
    http_status: int
    latency_ms: int
    headers: dict[str, str]


@dataclass(frozen=True)
class BytesResponse:
    body: bytes
    http_status: int
    latency_ms: int
    headers: dict[str, str]


class FoliClient:
    def __init__(self, *, base_url: str, user_agent: str, timeout_seconds: int):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            }
        )

    def get_json(self, path: str) -> JsonResponse:
        response, latency_ms = self._get(path)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object from {path}, got {type(payload).__name__}")
        return JsonResponse(
            payload=payload,
            http_status=response.status_code,
            latency_ms=latency_ms,
            headers=dict(response.headers),
        )

    def get_bytes(self, path: str) -> BytesResponse:
        response, latency_ms = self._get(path)
        response.raise_for_status()
        return BytesResponse(
            body=response.content,
            http_status=response.status_code,
            latency_ms=latency_ms,
            headers=dict(response.headers),
        )

    def _get(self, path: str) -> tuple[requests.Response, int]:
        url = f"{self.base_url}/{path.lstrip('/')}"
        started = time.monotonic()
        response = self.session.get(url, timeout=self.timeout_seconds)
        latency_ms = int((time.monotonic() - started) * 1000)
        return response, latency_ms

