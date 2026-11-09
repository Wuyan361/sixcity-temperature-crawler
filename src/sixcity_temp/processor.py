"""把原始抓取数据整理成可直接写入 Excel 的宽表。"""

from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from .fetcher import CityDataset
from .weather_codes import UNKNOWN_WEATHER, describe_weather_code

LOGGER = logging.getLogger(__name__)

HOUR_COLUMNS: list[str] = [f"{hour}时" for hour in range(24)]
DATA_TYPE_ACTUAL: str = "实际"
DATA_TYPE_FORECAST: str = "预测"


def combine_hourly(dataset: CityDataset) -> pd.DataFrame:
    """合并历史与预报的小时数据，重叠部分以历史实测为准。

    Args:
        dataset: 单个城市的原始数据。

    Returns:
        含 ``日期``、``小时`` 列的小时明细表。
    """
    combined = pd.concat(
        [dataset.archive_hourly, dataset.forecast_hourly], ignore_index=True
    ).copy()
    combined["time"] = pd.to_datetime(combined["time"])
    combined = combined.drop_duplicates(subset=["time"], keep="first")
    combined = combined.sort_values("time").reset_index(drop=True)
    combined["日期"] = combined["time"].dt.date
    combined["小时"] = combined["time"].dt.hour
    return combined


def combine_daily(dataset: CityDataset) -> pd.DataFrame:
    """合并历史与预报的每日数据，重叠部分以历史实测为准。

    Args:
        dataset: 单个城市的原始数据。

    Returns:
        以日期为索引，含 ``天气``、``最高气温``、``最低气温`` 的每日表。
    """
    daily = pd.concat([dataset.archive_daily, dataset.forecast_daily], ignore_index=True).copy()
    daily["time"] = pd.to_datetime(daily["time"]).dt.date
    daily = daily.drop_duplicates(subset=["time"], keep="first")
    daily = daily.set_index("time")
    daily.index.name = "日期"
    daily["天气"] = daily["weather_code"].map(describe_weather_code).fillna(UNKNOWN_WEATHER)
    return daily.rename(
        columns={"temperature_2m_max": "最高气温", "temperature_2m_min": "最低气温"}
    )


def build_temperature_table(dataset: CityDataset, today: date) -> pd.DataFrame:
    """生成气温宽表。

    Args:
        dataset: 单个城市的原始数据。
        today: 用于区分「实际」与「预测」的当天日期。

    Returns:
        索引为日期，列为 24 个小时气温的 DataFrame。
    """
    combined = combine_hourly(dataset)
    hourly_pivot = combined.pivot(index="日期", columns="小时", values="temperature_2m")
    hourly_pivot = hourly_pivot.reindex(columns=range(24))
    hourly_pivot.columns = HOUR_COLUMNS

    daily = combine_daily(dataset)
    table = hourly_pivot.join(daily[["天气", "最高气温", "最低气温"]], how="left")
    table.insert(0, "数据类型", [_data_type(day, today) for day in table.index])
    table = table[["数据类型", "天气", "最高气温", "最低气温", *HOUR_COLUMNS]]
    table.index.name = "日期"
    return table


def build_apparent_table(dataset: CityDataset, today: date) -> pd.DataFrame:
    """生成体感温度宽表。

    Args:
        dataset: 单个城市的原始数据。
        today: 用于区分「实际」与「预测」的当天日期。

    Returns:
        索引为日期，列为 24 个小时体感温度及最高 / 最低 / 平均体感的 DataFrame。
    """
    combined = combine_hourly(dataset)
    hourly_pivot = combined.pivot(index="日期", columns="小时", values="apparent_temperature")
    hourly_pivot = hourly_pivot.reindex(columns=range(24))
    hourly_pivot.columns = HOUR_COLUMNS

    daily_stats = (
        combined.groupby("日期")
        .agg(
            最高体感=("apparent_temperature", "max"),
            最低体感=("apparent_temperature", "min"),
            平均体感=("apparent_temperature", "mean"),
        )
        .round(1)
    )
    table = hourly_pivot.join(daily_stats)
    table.insert(0, "数据类型", [_data_type(day, today) for day in table.index])
    table = table[["数据类型", "最高体感", "最低体感", "平均体感", *HOUR_COLUMNS]]
    table.index.name = "日期"
    return table


def _data_type(day: date, today: date) -> str:
    """判断某一天属于实测还是预报。"""
    return DATA_TYPE_ACTUAL if day <= today else DATA_TYPE_FORECAST
