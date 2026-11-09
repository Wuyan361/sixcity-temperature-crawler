"""测试夹具：构造假的 Open-Meteo 会话与数据。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import pytest
import requests

from sixcity_temp.config import City
from sixcity_temp.fetcher import ARCHIVE_API_URL, FORECAST_API_URL, CityDataset


class FakeResponse:
    """``requests.Response`` 的最小替身。"""

    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        """状态码异常时抛出 ``HTTPError``，并挂上 ``response`` 便于诊断。"""
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} Error", response=self)

    def json(self) -> dict[str, Any]:
        """返回预置的 JSON 数据。"""
        return self._payload


class FakeSession:
    """按 URL 返回预置数据或抛出预置异常的假会话。"""

    def __init__(
        self,
        payloads: dict[str, dict[str, Any]] | None = None,
        errors: dict[str, Exception] | None = None,
    ) -> None:
        self.payloads = payloads or {}
        self.errors = errors or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> FakeResponse:
        """记录调用并返回预置响应。"""
        self.calls.append((url, dict(params or {})))
        if url in self.errors:
            raise self.errors[url]
        payload = self.payloads.get(url)
        if payload is None:
            raise AssertionError(f"测试没有为 {url} 准备数据")
        return FakeResponse(payload)


def build_hourly_payload(
    start: date, days: int, *, temp_base: float = 20.0
) -> dict[str, list[Any]]:
    """生成连续的逐小时数据。"""
    times: list[str] = []
    temperatures: list[float] = []
    apparent: list[float] = []
    current = datetime(start.year, start.month, start.day)
    for _ in range(days * 24):
        times.append(current.strftime("%Y-%m-%dT%H:%M"))
        drift = (current.hour - 12) * 0.5
        temperatures.append(round(temp_base + drift, 1))
        apparent.append(round(temp_base + drift + 2.0, 1))
        current += timedelta(hours=1)
    return {
        "time": times,
        "temperature_2m": temperatures,
        "apparent_temperature": apparent,
    }


def build_daily_payload(start: date, days: int) -> dict[str, list[Any]]:
    """生成连续的逐日数据。"""
    times: list[str] = []
    codes: list[int] = []
    highs: list[float] = []
    lows: list[float] = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        times.append(day.isoformat())
        codes.append(offset % 5)
        highs.append(25.0 + offset % 3)
        lows.append(15.0 + offset % 2)
    return {
        "time": times,
        "weather_code": codes,
        "temperature_2m_max": highs,
        "temperature_2m_min": lows,
    }


def make_dataset(
    city: City,
    *,
    start: date = date(2025, 1, 1),
    days: int = 3,
) -> CityDataset:
    """构造一个城市的完整数据集。"""
    return CityDataset(
        city=city,
        archive_hourly=pd.DataFrame(build_hourly_payload(start, days)),
        archive_daily=pd.DataFrame(build_daily_payload(start, days)),
        forecast_hourly=pd.DataFrame(build_hourly_payload(start, days)),
        forecast_daily=pd.DataFrame(build_daily_payload(start, days)),
    )


class FakeClient:
    """假客户端：按城市名返回数据，或按城市名抛错。"""

    def __init__(
        self,
        timeout: int = 30,
        *,
        failing: set[str] | None = None,
        error: Exception | None = None,
        start: date = date(2025, 1, 1),
        days: int = 3,
    ) -> None:
        self.timeout = timeout
        self.failing = failing or set()
        self.error = error if error is not None else requests.exceptions.ConnectionError("连接失败")
        self.start = start
        self.days = days

    def with_timeout(self, timeout: int) -> FakeClient:
        """返回使用相同配置的新实例。"""
        return FakeClient(
            timeout,
            failing=self.failing,
            error=self.error,
            start=self.start,
            days=self.days,
        )

    def fetch_city(self, city: City, history_start: date) -> CityDataset:
        """返回该城市的数据；城市在失败名单中时抛错。"""
        if city.name in self.failing:
            raise self.error
        return make_dataset(city, start=self.start, days=self.days)


@pytest.fixture
def sample_city() -> City:
    """一个用于测试的城市。"""
    return City("广州", 23.1291, 113.2644)


@pytest.fixture
def sample_dataset(sample_city: City) -> CityDataset:
    """一个用于测试的城市数据集。"""
    return make_dataset(sample_city)


@pytest.fixture
def fake_session() -> FakeSession:
    """一个同时返回历史与预报数据的假会话。"""
    payload = {
        "hourly": build_hourly_payload(date(2025, 1, 1), 3),
        "daily": build_daily_payload(date(2025, 1, 1), 3),
    }
    return FakeSession(payloads={ARCHIVE_API_URL: payload, FORECAST_API_URL: payload})


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """所有测试都不真的等待网络重试。"""
    monkeypatch.setattr("sixcity_temp.fetcher.time.sleep", lambda _seconds: None)
