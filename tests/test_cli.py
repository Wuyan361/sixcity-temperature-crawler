"""命令行入口测试。"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest
import requests
from openpyxl import load_workbook
from tests.conftest import FakeClient

from sixcity_temp.cli import EXIT_OK, EXIT_PARTIAL, EXIT_USAGE, main, run
from sixcity_temp.config import DEFAULT_APPARENT_FILENAME, DEFAULT_TEMPERATURE_FILENAME


def test_run_writes_both_workbooks(tmp_path: Path) -> None:
    """默认抓取六个城市，生成两个 Excel。"""
    exit_code = run(["--output-dir", str(tmp_path)], client_factory=FakeClient)

    assert exit_code == EXIT_OK
    temperature = load_workbook(tmp_path / DEFAULT_TEMPERATURE_FILENAME)
    assert temperature.sheetnames == ["海南", "韶关", "梅州", "茂名", "广州", "深圳"]
    apparent = load_workbook(tmp_path / DEFAULT_APPARENT_FILENAME)
    assert apparent.sheetnames == ["海南", "韶关", "梅州", "茂名", "广州", "深圳"]


def test_run_filters_cities_by_name(tmp_path: Path) -> None:
    """--only-city 只抓指定城市。"""
    exit_code = run(
        ["--output-dir", str(tmp_path), "--only-city", "广州"], client_factory=FakeClient
    )

    assert exit_code == EXIT_OK
    assert load_workbook(tmp_path / DEFAULT_TEMPERATURE_FILENAME).sheetnames == ["广州"]


def test_run_uses_custom_cities_file(tmp_path: Path) -> None:
    """--cities 读取自定义城市配置。"""
    cities_file = tmp_path / "cities.json"
    cities_file.write_text(
        json.dumps({"cities": [{"name": "汕头", "latitude": 23.35, "longitude": 116.68}]}),
        encoding="utf-8",
    )

    exit_code = run(
        ["--output-dir", str(tmp_path), "--cities", str(cities_file)], client_factory=FakeClient
    )

    assert exit_code == EXIT_OK
    assert load_workbook(tmp_path / DEFAULT_TEMPERATURE_FILENAME).sheetnames == ["汕头"]


def test_run_returns_usage_error_for_unknown_city(tmp_path: Path) -> None:
    """城市名不匹配时返回参数错误码。"""
    exit_code = run(
        ["--output-dir", str(tmp_path), "--only-city", "不存在"], client_factory=FakeClient
    )

    assert exit_code == EXIT_USAGE


def test_run_returns_usage_error_for_bad_history_start(tmp_path: Path) -> None:
    """日期格式错误时返回参数错误码。"""
    exit_code = run(
        ["--output-dir", str(tmp_path), "--history-start", "2025/01/01"],
        client_factory=FakeClient,
    )

    assert exit_code == EXIT_USAGE


def test_run_returns_usage_error_for_broken_cities_file(tmp_path: Path) -> None:
    """城市配置文件损坏时返回参数错误码。"""
    cities_file = tmp_path / "cities.json"
    cities_file.write_text("{ 坏文件", encoding="utf-8")

    exit_code = run(
        ["--output-dir", str(tmp_path), "--cities", str(cities_file)], client_factory=FakeClient
    )

    assert exit_code == EXIT_USAGE


def test_run_keeps_other_cities_when_one_fails(tmp_path: Path) -> None:
    """单个城市抓取失败时，其余城市照常导出并返回部分失败码。"""

    def factory(timeout: int) -> FakeClient:
        return FakeClient(timeout, failing={"梅州"})

    exit_code = run(["--output-dir", str(tmp_path)], client_factory=factory)

    assert exit_code == EXIT_PARTIAL
    assert load_workbook(tmp_path / DEFAULT_TEMPERATURE_FILENAME).sheetnames == [
        "海南",
        "韶关",
        "茂名",
        "广州",
        "深圳",
    ]


def test_run_returns_partial_when_all_cities_fail(tmp_path: Path) -> None:
    """所有城市都失败时不生成文件。"""

    def factory(timeout: int) -> FakeClient:
        return FakeClient(timeout, failing={"海南", "韶关", "梅州", "茂名", "广州", "深圳"})

    exit_code = run(["--output-dir", str(tmp_path)], client_factory=factory)

    assert exit_code == EXIT_PARTIAL
    assert not (tmp_path / DEFAULT_TEMPERATURE_FILENAME).exists()


def test_run_without_style_skips_formatting(tmp_path: Path) -> None:
    """--no-style 生成的文件不做美化。"""
    exit_code = run(
        ["--output-dir", str(tmp_path), "--only-city", "广州", "--no-style"],
        client_factory=FakeClient,
    )

    assert exit_code == EXIT_OK
    worksheet = load_workbook(tmp_path / DEFAULT_TEMPERATURE_FILENAME)["广州"]
    assert worksheet.freeze_panes is None


def test_run_handles_rate_limit_by_waiting(tmp_path: Path) -> None:
    """429 限流时进入等待重试流程，仍可拿到数据。"""
    payload_calls: list[int] = []

    def factory(timeout: int) -> FakeClient:
        payload_calls.append(timeout)
        return FakeClient(timeout)

    exit_code = run(["--output-dir", str(tmp_path), "--only-city", "广州"], client_factory=factory)

    assert exit_code == EXIT_OK
    assert payload_calls == [30]


def test_run_writes_table_around_current_date(tmp_path: Path) -> None:
    """导出内容包含今天及之后的数据，并标记实测 / 预测。"""
    today = date.today()

    def factory(timeout: int) -> FakeClient:
        return FakeClient(timeout, start=today, days=3)

    exit_code = run(["--output-dir", str(tmp_path), "--only-city", "广州"], client_factory=factory)

    assert exit_code == EXIT_OK
    worksheet = load_workbook(tmp_path / DEFAULT_TEMPERATURE_FILENAME)["广州"]
    assert worksheet.cell(row=2, column=2).value == "实际"
    assert worksheet.cell(row=4, column=2).value == "预测"


def test_run_reports_connection_error_as_partial(tmp_path: Path) -> None:
    """网络异常时返回部分失败码而不是抛出未捕获异常。"""

    def factory(timeout: int) -> FakeClient:
        return FakeClient(
            timeout, failing={"广州"}, error=requests.exceptions.ConnectionError("断网")
        )

    exit_code = run(["--output-dir", str(tmp_path), "--only-city", "广州"], client_factory=factory)

    assert exit_code == EXIT_PARTIAL


def test_main_exits_with_success_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """控制台入口正常结束时以退出码 0 退出。"""
    monkeypatch.setattr("sixcity_temp.cli.OpenMeteoClient", FakeClient)
    monkeypatch.setattr(
        sys,
        "argv",
        ["sixcity-temp", "--output-dir", str(tmp_path), "--only-city", "广州"],
    )

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == EXIT_OK
    assert (tmp_path / DEFAULT_TEMPERATURE_FILENAME).exists()
