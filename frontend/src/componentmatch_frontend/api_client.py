"""Single frontend HTTP boundary, using the existing request/response contracts."""

import math
import os
from dataclasses import dataclass

import httpx
from pydantic import ValidationError

from componentmatch_contracts.agent import AgentRequest, AgentResult


class APIError(Exception):
    """Only application-owned safe messages may cross into the UI."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


@dataclass(frozen=True)
class UIConfig:
    api_url: str = "http://127.0.0.1:8000"
    timeout_seconds: float = 210

    @classmethod
    def from_env(cls):
        try:
            value = cls(
                api_url=os.getenv("COMPONENTMATCH_API_URL", cls.api_url).rstrip("/"),
                timeout_seconds=float(os.getenv("COMPONENTMATCH_HTTP_TIMEOUT_SECONDS", "210")),
            )
            url = httpx.URL(value.api_url)
            # This desktop demo deliberately connects only to the local backend.
            if (
                url.scheme != "http"
                or url.host not in {"127.0.0.1", "localhost", "::1"}
                or url.userinfo
                or url.query
                or url.fragment
                or url.path not in {"", "/"}
                or not math.isfinite(value.timeout_seconds)
                or not 210 <= value.timeout_seconds <= 600
            ):
                raise ValueError
            return value
        except (ValueError, httpx.InvalidURL):
            raise APIError(
                "UI_CONFIG_ERROR", "连接配置无效，请检查本地后端地址与请求超时设置。"
            ) from None


class APIClient:
    def __init__(self, config=None, *, transport=None):
        self.config = config or UIConfig.from_env()
        self.transport = transport

    def _request(self, method, path, *, payload=None, health=False):
        timeout = httpx.Timeout(5 if health else self.config.timeout_seconds, connect=3)
        try:
            with httpx.Client(
                base_url=self.config.api_url,
                timeout=timeout,
                transport=self.transport,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                return client.request(method, path, json=payload)
        except httpx.TimeoutException:
            raise APIError(
                "API_TIMEOUT",
                "等待后端响应超时。后端可能仍在处理，请勿连续重试；稍后检查后端状态。",
            ) from None
        except httpx.TransportError:
            raise APIError(
                "API_UNAVAILABLE", "无法连接后端，请确认 FastAPI 已启动，并检查本地 API 地址。"
            ) from None

    def health(self):
        response = self._request("GET", "/health", health=True)
        try:
            healthy = response.status_code == 200 and response.json().get("status") == "ok"
        except (ValueError, AttributeError):
            healthy = False
        if not healthy:
            raise APIError("HEALTH_FAILED", "后端健康检查未通过，请检查服务状态。")
        return True

    def match(self, text, *, confirmed_fields=None):
        try:
            values = {"text": text}
            if confirmed_fields:
                values["confirmed_fields"] = confirmed_fields
            request = AgentRequest(**values)
        except ValidationError:
            raise APIError(
                "INPUT_INVALID", "请填写 1–2000 字的采购需求，不能仅包含空白。"
            ) from None
        response = self._request(
            "POST",
            "/api/v1/agent/matches",
            payload=request.model_dump(mode="json", exclude_unset=True),
        )
        return self._parse_response(response)

    @staticmethod
    def _parse_response(response):
        try:
            result = AgentResult.model_validate(response.json())
        except (ValueError, ValidationError):
            if response.status_code == 422:
                raise APIError(
                    "REQUEST_REJECTED", "请求格式未通过后端校验，请检查需求后重试。"
                ) from None
            raise APIError(
                "INVALID_RESPONSE", "后端返回了无法识别的响应，请检查服务版本和后端日志。"
            ) from None
        if response.status_code != 200 and result.status != "error":
            raise APIError("HTTP_ERROR", "后端返回异常状态，请检查服务后再重试。")
        return result
