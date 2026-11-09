"""天气代码翻译测试。"""

from __future__ import annotations

import math

from sixcity_temp.weather_codes import UNKNOWN_WEATHER, describe_weather_code


def test_describe_weather_code_translates_known_code() -> None:
    """已知代码翻译成中文。"""
    assert describe_weather_code(0) == "晴"
    assert describe_weather_code(61) == "雨: 轻度"
    assert describe_weather_code(95) == "雷暴: 轻度或中度"


def test_describe_weather_code_returns_unknown_for_unknown_code() -> None:
    """未知代码返回「未知」。"""
    assert describe_weather_code(1234) == UNKNOWN_WEATHER


def test_describe_weather_code_returns_unknown_for_none() -> None:
    """None 返回「未知」。"""
    assert describe_weather_code(None) == UNKNOWN_WEATHER


def test_describe_weather_code_returns_unknown_for_nan() -> None:
    """NaN 返回「未知」。"""
    assert describe_weather_code(math.nan) == UNKNOWN_WEATHER


def test_describe_weather_code_returns_unknown_for_text() -> None:
    """非数字返回「未知」。"""
    assert describe_weather_code("晴") == UNKNOWN_WEATHER
