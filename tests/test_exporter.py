"""Excel 导出与样式测试。"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook
from tests.conftest import make_dataset

from sixcity_temp.errors import ExportError
from sixcity_temp.exporter import export_apparent_workbook, export_temperature_workbook
from sixcity_temp.processor import build_apparent_table, build_temperature_table


def test_export_temperature_workbook_creates_sheets(tmp_path: Path, sample_city) -> None:
    """每个城市一个工作表，表头包含日期列。"""
    today = date.today()
    dataset = make_dataset(sample_city, start=today, days=2)
    table = build_temperature_table(dataset, today)
    path = tmp_path / "气温.xlsx"

    export_temperature_workbook(path, {sample_city.name: table}, today)

    workbook = load_workbook(path)
    assert workbook.sheetnames == [sample_city.name]
    worksheet = workbook[sample_city.name]
    assert worksheet.cell(row=1, column=1).value == "日期"
    assert worksheet.cell(row=1, column=2).value == "数据类型"
    assert worksheet.cell(row=1, column=6).value == "0时"


def test_export_temperature_workbook_applies_style(tmp_path: Path, sample_city) -> None:
    """冻结窗格、居中边框与当天高亮生效。"""
    today = date.today()
    dataset = make_dataset(sample_city, start=today, days=2)
    table = build_temperature_table(dataset, today)
    path = tmp_path / "气温.xlsx"

    export_temperature_workbook(path, {sample_city.name: table}, today)

    worksheet = load_workbook(path)[sample_city.name]
    assert worksheet.freeze_panes == "F2"
    assert worksheet.cell(row=1, column=1).font.bold is True
    assert worksheet.cell(row=2, column=1).alignment.horizontal == "center"
    assert worksheet.cell(row=2, column=1).border.left.style == "thin"
    assert worksheet.cell(row=2, column=1).fill.start_color.rgb.endswith("FFDDC1")
    assert not worksheet.cell(row=3, column=1).fill.start_color.rgb.endswith("FFDDC1")


def test_export_without_style_leaves_default_layout(tmp_path: Path, sample_city) -> None:
    """关闭样式后不做任何美化。"""
    today = date.today()
    dataset = make_dataset(sample_city, start=today, days=2)
    table = build_temperature_table(dataset, today)
    path = tmp_path / "原始.xlsx"

    export_temperature_workbook(path, {sample_city.name: table}, today, style=False)

    worksheet = load_workbook(path)[sample_city.name]
    assert worksheet.freeze_panes is None
    assert worksheet.cell(row=2, column=1).fill.start_color.rgb.endswith("00000000")


def test_export_apparent_workbook_uses_own_freeze_panes(tmp_path: Path, sample_city) -> None:
    """体感温度表冻结到 E2。"""
    today = date.today()
    dataset = make_dataset(sample_city, start=today, days=2)
    table = build_apparent_table(dataset, today)
    path = tmp_path / "体感.xlsx"

    export_apparent_workbook(path, {sample_city.name: table}, today)

    worksheet = load_workbook(path)[sample_city.name]
    assert worksheet.freeze_panes == "E2"
    assert worksheet.cell(row=1, column=2).value == "数据类型"


def test_export_writes_neutral_document_properties(tmp_path: Path, sample_city) -> None:
    """文档属性里不出现运行者身份，只写项目标识。"""
    today = date.today()
    dataset = make_dataset(sample_city, start=today, days=2)
    table = build_temperature_table(dataset, today)
    path = tmp_path / "气温.xlsx"

    export_temperature_workbook(path, {sample_city.name: table}, today)

    properties = load_workbook(path).properties
    assert properties.creator == "sixcity-temperature-crawler"
    assert properties.lastModifiedBy == "sixcity-temperature-crawler"
    operator = os.environ.get("USERNAME", "")
    if operator:
        assert operator not in (properties.creator or "")
        assert operator not in (properties.lastModifiedBy or "")


def test_export_raises_export_error_when_file_locked(
    tmp_path: Path, sample_city, monkeypatch: pytest.MonkeyPatch
) -> None:
    """文件被占用时抛出 ExportError。"""

    def _raise_permission_error(*args, **kwargs):
        raise PermissionError(13, "拒绝访问")

    monkeypatch.setattr("sixcity_temp.exporter.pd.ExcelWriter", _raise_permission_error)
    today = date.today()
    table = build_temperature_table(make_dataset(sample_city, start=today, days=2), today)

    with pytest.raises(ExportError, match="WPS"):
        export_temperature_workbook(tmp_path / "被占用.xlsx", {sample_city.name: table}, today)


def test_export_overwrites_existing_file(tmp_path: Path, sample_city) -> None:
    """重复运行会覆盖旧文件而不是追加。"""
    today = date.today()
    table = build_temperature_table(make_dataset(sample_city, start=today, days=2), today)
    path = tmp_path / "气温.xlsx"
    pd.DataFrame({"旧": [1, 2]}).to_excel(path, index=False)

    export_temperature_workbook(path, {sample_city.name: table}, today)

    assert load_workbook(path).sheetnames == [sample_city.name]
