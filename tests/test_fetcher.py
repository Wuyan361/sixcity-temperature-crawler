"""抓取客户端测试。"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
import requests
from tests.conftest import FakeResponse, FakeSession, build_daily_payload, build_hourly_payload

from sixcity_temp.errors import DataFormatError
from sixcity_temp.fetcher import (
    ARCHIVE_API_URL,
    FORECAST_API_URL,
    OpenMeteoClient,
    diagnose_and_retry,
    fetch_city_with_retry,
)

HISTORY_START = date(2025, 1, 1)


def test_fetch_city_returns_dataset(fake_session: FakeSession, sample_city) -> None:
    """成功抓取时返回历史与预报两套数据。"""
    client = OpenMeteoClient(session=fake_session)

    dataset = client.fetch_city(sample_city, HISTORY_START)

    assert dataset.city == sample_city
    assert len(dataset.archive_hourly) == 72
    assert len(dataset.forecast_hourly) == 72
    assert len(dataset.archive_daily) == 3
    assert "temperature_2m" in dataset.archive_hourly.columns


def test_fetch_city_sends_expected_params(fake_session: FakeSession, sample_city) -> None:
    """请求参数包含经纬度、时间范围与时区。"""
    client = OpenMeteoClient(session=fake_session)

    client.fetch_city(sample_city, HISTORY_START)

    urls = [url for url, _ in fake_session.calls]
    assert urls == [ARCHIVE_API_URL, FORECAST_API_URL]
    archive_params = fake_session.calls[0][1]
    assert archive_params["latitude"] == sample_city.latitude
    assert archive_params["start_date"] == "2025-01-01"
    assert archive_params["timezone"] == "Asia/Shanghai"
    forecast_params = fake_session.calls[1][1]
    assert forecast_params["forecast_days"] == 7
    assert forecast_params["past_days"] == 5


def test_fetch_city_falls_back_when_archive_rejects_end_date(sample_city) -> None:
    """历史接口拒绝截止日期时自动回退 5 天。"""
    payload = {
        "hourly": build_hourly_payload(HISTORY_START, 3),
        "daily": build_daily_payload(HISTORY_START, 3),
    }
    session = _ArchiveRejectingSession(
        payloads={ARCHIVE_API_URL: payload, FORECAST_API_URL: payload}
    )

    client = OpenMeteoClient(session=session)
    dataset = client.fetch_city(sample_city, HISTORY_START)

    assert len(dataset.archive_hourly) == 72
    archive_calls = [params for url, params in session.calls if url == ARCHIVE_API_URL]
    assert len(archive_calls) == 2
    expected = (date.today() - timedelta(days=5)).isoformat()
    assert archive_calls[1]["end_date"] == expected


def test_fetch_city_raises_when_payload_missing_blocks(sample_city) -> None:
    """返回缺少 hourly / daily 时抛出格式错误。"""
    session = FakeSession(payloads={ARCHIVE_API_URL: {"hourly": {}}, FORECAST_API_URL: {}})

    client = OpenMeteoClient(session=session)

    with pytest.raises(DataFormatError, match="hourly"):
        client.fetch_city(sample_city, HISTORY_START)


def test_fetch_city_with_retry_returns_error_after_attempts(sample_city) -> None:
    """持续失败时返回最后一次异常。"""
    session = FakeSession(errors={ARCHIVE_API_URL: requests.exceptions.ConnectionError("断网")})

    dataset, error = fetch_city_with_retry(
        OpenMeteoClient(session=session), sample_city, HISTORY_START, max_retries=3
    )

    assert dataset is None
    assert isinstance(error, requests.exceptions.ConnectionError)
    assert len(session.calls) == 3


def test_fetch_city_with_retry_returns_data_on_second_attempt(sample_city) -> None:
    """首次失败、再次成功时正常返回数据。"""
    payload = {
        "hourly": build_hourly_payload(HISTORY_START, 3),
        "daily": build_daily_payload(HISTORY_START, 3),
    }
    session = _FailOnceSession(payloads={ARCHIVE_API_URL: payload, FORECAST_API_URL: payload})

    dataset, error = fetch_city_with_retry(
        OpenMeteoClient(session=session), sample_city, HISTORY_START, max_retries=3
    )

    assert error is None
    assert dataset is not None


def test_diagnose_and_retry_gives_up_on_connection_error(sample_city) -> None:
    """连接失败且补救后仍失败时返回 None。"""
    session = FakeSession(errors={ARCHIVE_API_URL: requests.exceptions.ConnectionError("断网")})

    dataset = diagnose_and_retry(
        OpenMeteoClient(session=session),
        sample_city,
        HISTORY_START,
        requests.exceptions.ConnectionError("断网"),
    )

    assert dataset is None


def test_diagnose_and_retry_returns_none_for_unfixable_status(sample_city) -> None:
    """404 这类无法自动解决的错误直接放弃。"""
    error = requests.exceptions.HTTPError("404 Not Found", response=FakeResponse({}, 404))

    dataset = diagnose_and_retry(OpenMeteoClient(), sample_city, HISTORY_START, error)

    assert dataset is None


class _FailOnceSession(FakeSession):
    """第一次调用失败，之后正常返回。"""

    def __init__(self, payloads: dict[str, dict]) -> None:
        super().__init__(payloads=payloads)
        self._failed = False

    def get(self, url, params=None, timeout=None):
        """首次调用抛错。"""
        if not self._failed:
            self._failed = True
            self.calls.append((url, dict(params or {})))
            raise requests.exceptions.ConnectionError("首次失败")
        return super().get(url, params=params, timeout=timeout)


class _ArchiveRejectingSession(FakeSession):
    """历史接口第一次返回 400，之后正常。"""

    def __init__(self, payloads: dict[str, dict]) -> None:
        super().__init__(payloads=payloads)
        self._failed = False

    def get(self, url, params=None, timeout=None):
        """历史接口首次调用返回 400。"""
        if url == ARCHIVE_API_URL and not self._failed:
            self._failed = True
            self.calls.append((url, dict(params or {})))
            raise requests.exceptions.HTTPError("400 Bad Request", response=FakeResponse({}, 400))
        return super().get(url, params=params, timeout=timeout)
