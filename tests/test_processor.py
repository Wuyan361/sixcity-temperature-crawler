"""数据整理逻辑测试。"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from tests.conftest import build_daily_payload, build_hourly_payload

from sixcity_temp.config import City
from sixcity_temp.fetcher import CityDataset
from sixcity_temp.processor import (
    HOUR_COLUMNS,
    build_apparent_table,
    build_temperature_table,
    combine_daily,
    combine_hourly,
)

DAY_ONE = date(2025, 1, 1)
TODAY = date(2025, 1, 2)


def test_build_temperature_table_has_expected_columns(sample_dataset: CityDataset) -> None:
    """气温宽表列名与顺序固定。"""
    table = build_temperature_table(sample_dataset, TODAY)

    assert list(table.columns) == ["数据类型", "天气", "最高气温", "最低气温", *HOUR_COLUMNS]
    assert list(table.index) == [date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3)]
    assert table.index.name == "日期"


def test_build_temperature_table_values_match_source(sample_dataset: CityDataset) -> None:
    """气温与每日汇总值来自原始数据。"""
    table = build_temperature_table(sample_dataset, TODAY)

    assert table.loc[DAY_ONE, "0时"] == pytest.approx(14.0)
    assert table.loc[DAY_ONE, "12时"] == pytest.approx(20.0)
    assert table.loc[DAY_ONE, "23时"] == pytest.approx(25.5)
    assert table.loc[DAY_ONE, "天气"] == "晴"
    assert table.loc[DAY_ONE, "最高气温"] == pytest.approx(25.0)
    assert table.loc[DAY_ONE, "最低气温"] == pytest.approx(15.0)


def test_build_temperature_table_marks_actual_and_forecast(sample_dataset: CityDataset) -> None:
    """今天及之前标记为「实际」，之后标记为「预测」。"""
    table = build_temperature_table(sample_dataset, TODAY)

    assert list(table["数据类型"]) == ["实际", "实际", "预测"]


def test_build_temperature_table_keeps_missing_hour_as_empty(sample_city: City) -> None:
    """缺某个小时的数据时仍然保留 24 列，缺口留空。"""
    hourly = pd.DataFrame(build_hourly_payload(DAY_ONE, 1))
    hourly = hourly[hourly["time"] != "2025-01-01T03:00"]
    forecast_hourly = pd.DataFrame(build_hourly_payload(DAY_ONE, 1))
    forecast_hourly = forecast_hourly[forecast_hourly["time"] != "2025-01-01T03:00"]
    dataset = CityDataset(
        city=sample_city,
        archive_hourly=hourly,
        archive_daily=pd.DataFrame(build_daily_payload(DAY_ONE, 1)),
        forecast_hourly=forecast_hourly,
        forecast_daily=pd.DataFrame(build_daily_payload(DAY_ONE, 1)),
    )

    table = build_temperature_table(dataset, TODAY)

    assert "3时" in table.columns
    assert pd.isna(table.loc[DAY_ONE, "3时"])
    assert table.loc[DAY_ONE, "4时"] == pytest.approx(16.0)


def test_build_apparent_table_has_expected_columns(sample_dataset: CityDataset) -> None:
    """体感宽表列名与顺序固定。"""
    table = build_apparent_table(sample_dataset, TODAY)

    assert list(table.columns) == ["数据类型", "最高体感", "最低体感", "平均体感", *HOUR_COLUMNS]


def test_build_apparent_table_computes_daily_stats(sample_dataset: CityDataset) -> None:
    """最高 / 最低 / 平均体感来自逐小时体感温度。"""
    table = build_apparent_table(sample_dataset, TODAY)

    assert table.loc[DAY_ONE, "最高体感"] == pytest.approx(27.5)
    assert table.loc[DAY_ONE, "最低体感"] == pytest.approx(16.0)
    assert table.loc[DAY_ONE, "平均体感"] == pytest.approx(21.8, abs=0.05)


def test_combine_hourly_prefers_archive_on_overlap(sample_city: City) -> None:
    """历史与预报时间重叠时，以历史实测为准。"""
    dataset = CityDataset(
        city=sample_city,
        archive_hourly=pd.DataFrame(build_hourly_payload(DAY_ONE, 2, temp_base=20.0)),
        archive_daily=pd.DataFrame(build_daily_payload(DAY_ONE, 2)),
        forecast_hourly=pd.DataFrame(build_hourly_payload(DAY_ONE, 2, temp_base=30.0)),
        forecast_daily=pd.DataFrame(build_daily_payload(DAY_ONE, 2)),
    )

    combined = combine_hourly(dataset)

    assert len(combined) == 48
    assert combined["temperature_2m"].iloc[0] == pytest.approx(14.0)


def test_combine_daily_translates_weather_code(sample_dataset: CityDataset) -> None:
    """每日天气代码被翻译成中文。"""
    daily = combine_daily(sample_dataset)

    assert daily.loc[DAY_ONE, "天气"] == "晴"
    assert daily.loc[DAY_ONE, "最高气温"] == pytest.approx(25.0)
    assert daily.loc[DAY_ONE, "最低气温"] == pytest.approx(15.0)
