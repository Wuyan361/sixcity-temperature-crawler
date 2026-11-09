"""Open-Meteo 气象数据抓取客户端。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Final

import pandas as pd
import requests

from .config import DEFAULT_RETRIES, DEFAULT_TIMEOUT, City
from .errors import DataFormatError

LOGGER = logging.getLogger(__name__)

ARCHIVE_API_URL: Final[str] = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_API_URL: Final[str] = "https://api.open-meteo.com/v1/forecast"
TIMEZONE: Final[str] = "Asia/Shanghai"
HOURLY_FIELDS: Final[list[str]] = ["temperature_2m", "apparent_temperature"]
DAILY_FIELDS: Final[list[str]] = ["weather_code", "temperature_2m_max", "temperature_2m_min"]
ARCHIVE_LAG_DAYS: Final[int] = 5
"""历史接口的落盘延迟天数：落后过多时回退截止日期。"""

FETCH_ERRORS: Final[tuple[type[Exception], ...]] = (
    requests.exceptions.RequestException,
    DataFormatError,
    KeyError,
    ValueError,
)


@dataclass(frozen=True)
class CityDataset:
    """单个城市抓取到的原始数据。"""

    city: City
    archive_hourly: pd.DataFrame
    archive_daily: pd.DataFrame
    forecast_hourly: pd.DataFrame
    forecast_daily: pd.DataFrame


class OpenMeteoClient:
    """Open-Meteo 历史 + 预报接口客户端。

    Args:
        timeout: 单次 HTTP 请求超时秒数。
        session: 复用的 ``requests.Session``，便于测试时注入假会话。
    """

    def __init__(
        self, timeout: int = DEFAULT_TIMEOUT, session: requests.Session | None = None
    ) -> None:
        self._timeout = timeout
        self._session = session if session is not None else requests.Session()

    @property
    def timeout(self) -> int:
        """当前超时秒数。"""
        return self._timeout

    def with_timeout(self, timeout: int) -> OpenMeteoClient:
        """返回使用相同会话、但超时不同的新客户端。"""
        return OpenMeteoClient(timeout=timeout, session=self._session)

    def fetch_city(self, city: City, history_start: date) -> CityDataset:
        """抓取单个城市的历史 + 7 日预报数据。

        Args:
            city: 目标城市。
            history_start: 历史数据起始日期。

        Returns:
            该城市的原始数据集合。

        Raises:
            requests.exceptions.HTTPError: 接口返回错误状态码。
            DataFormatError: 返回结构缺少 hourly / daily 数据块。
        """
        archive_hourly, archive_daily = self._fetch_archive(city, history_start)
        forecast_hourly, forecast_daily = self._fetch_forecast(city)
        return CityDataset(
            city=city,
            archive_hourly=archive_hourly,
            archive_daily=archive_daily,
            forecast_hourly=forecast_hourly,
            forecast_daily=forecast_daily,
        )

    def _fetch_archive(self, city: City, history_start: date) -> tuple[pd.DataFrame, pd.DataFrame]:
        """抓取历史（实测）数据。"""
        params: dict[str, Any] = {
            "latitude": city.latitude,
            "longitude": city.longitude,
            "start_date": history_start.isoformat(),
            "end_date": (date.today() - timedelta(days=1)).isoformat(),
            "hourly": list(HOURLY_FIELDS),
            "timezone": TIMEZONE,
            "daily": list(DAILY_FIELDS),
        }
        try:
            payload = self._get_json(ARCHIVE_API_URL, params)
        except requests.exceptions.HTTPError as error:
            fallback_end = date.today() - timedelta(days=ARCHIVE_LAG_DAYS)
            LOGGER.warning(
                "%s：历史接口拒绝截止日期 %s，回退到 %s（%s）",
                city.name,
                params["end_date"],
                fallback_end.isoformat(),
                error,
            )
            params["end_date"] = fallback_end.isoformat()
            payload = self._get_json(ARCHIVE_API_URL, params)

        hourly, daily = self._parse_payload(city, payload, "历史")
        return hourly, daily

    def _fetch_forecast(self, city: City) -> tuple[pd.DataFrame, pd.DataFrame]:
        """抓取含过去 5 天在内的 7 日预报数据。"""
        params: dict[str, Any] = {
            "latitude": city.latitude,
            "longitude": city.longitude,
            "hourly": list(HOURLY_FIELDS),
            "timezone": TIMEZONE,
            "forecast_days": 7,
            "past_days": ARCHIVE_LAG_DAYS,
            "daily": list(DAILY_FIELDS),
        }
        payload = self._get_json(FORECAST_API_URL, params)
        hourly, daily = self._parse_payload(city, payload, "预报")
        return hourly, daily

    def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        """发起 GET 请求并返回 JSON 对象。"""
        response = self._session.get(url, params=params, timeout=self._timeout)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise DataFormatError(f"{url} 返回的不是 JSON 对象，而是 {type(payload).__name__}")
        return payload

    @staticmethod
    def _parse_payload(
        city: City, payload: dict[str, Any], source: str
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """把接口返回的 JSON 拆成 hourly / daily 两个 DataFrame。"""
        hourly = payload.get("hourly")
        daily = payload.get("daily")
        if not isinstance(hourly, dict) or not isinstance(daily, dict):
            raise DataFormatError(f"{city.name} 的{source}接口返回缺少 'hourly' 或 'daily' 数据块")
        return pd.DataFrame(hourly), pd.DataFrame(daily)


def fetch_city_with_retry(
    client: OpenMeteoClient,
    city: City,
    history_start: date,
    max_retries: int = DEFAULT_RETRIES,
) -> tuple[CityDataset | None, Exception | None]:
    """抓取失败自动重试。

    Args:
        client: 抓取客户端。
        city: 目标城市。
        history_start: 历史数据起始日期。
        max_retries: 最大尝试次数（含首次）。

    Returns:
        ``(数据, None)`` 表示成功，``(None, 最后一次异常)`` 表示失败。
    """
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            return client.fetch_city(city, history_start), None
        except FETCH_ERRORS as error:
            last_error = error
            LOGGER.warning("%s 第 %d/%d 次抓取失败：%s", city.name, attempt, max_retries, error)
    return None, last_error


def diagnose_and_retry(
    client: OpenMeteoClient,
    city: City,
    history_start: date,
    error: Exception,
) -> CityDataset | None:
    """根据失败类型做一次针对性补救。

    超时会放宽到 60 秒，429 限流等待 60 秒，5xx 等待 30 秒，
    连接失败等待 10 秒；仍失败则返回 ``None``。

    Args:
        client: 抓取客户端。
        city: 目标城市。
        history_start: 历史数据起始日期。
        error: 首次失败时的异常。

    Returns:
        补救成功返回数据，否则返回 ``None``。
    """
    if isinstance(error, requests.exceptions.Timeout):
        LOGGER.warning("%s 识别为网络超时，放宽到 60 秒重试一次。", city.name)
        dataset, _ = fetch_city_with_retry(
            client.with_timeout(60), city, history_start, max_retries=1
        )
        return dataset

    if isinstance(error, requests.exceptions.HTTPError) and error.response is not None:
        status = error.response.status_code
        if status == 429:
            LOGGER.warning("%s 识别为接口限流（429），等待 60 秒后重试一次。", city.name)
            time.sleep(60)
        elif status >= 500:
            LOGGER.warning(
                "%s 识别为对方服务器故障（%d），等待 30 秒后重试一次。", city.name, status
            )
            time.sleep(30)
        else:
            LOGGER.error("%s 识别为 HTTP 错误（%d），无法自动解决。", city.name, status)
            return None
        dataset, _ = fetch_city_with_retry(client, city, history_start, max_retries=1)
        return dataset

    if isinstance(error, requests.exceptions.ConnectionError):
        LOGGER.warning("%s 识别为网络连接失败，等待 10 秒后重试一次。", city.name)
        time.sleep(10)
        dataset, _ = fetch_city_with_retry(client, city, history_start, max_retries=1)
        return dataset

    LOGGER.error("%s 失败原因无法自动解决：%s: %s", city.name, type(error).__name__, error)
    return None
