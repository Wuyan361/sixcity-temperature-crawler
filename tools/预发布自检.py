"""发布前自检：检查项目里是否残留可追溯到运行者的信息。

用法（在项目根目录执行）::

    python tools/预发布自检.py

检查五类风险：密钥 / 个人信息 / 本机绝对路径 / 缓存与运行产物 / Excel 文档属性。
发现问题时以退出码 1 结束，便于接进提交或打包流程。
"""

from __future__ import annotations

import argparse
import os
import re
import socket
import sys
import zipfile
from pathlib import Path

TEXT_SUFFIXES = {
    ".py", ".md", ".toml", ".txt", ".json", ".bat", ".cfg", ".ini", ".yml", ".yaml", ".sh"
}
CACHE_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".ipynb_checkpoints"}
JUNK_SUFFIXES = {".pyc", ".pyo", ".tmp", ".bak", ".orig", ".log", ".swp", ".old", ".rej"}
SENSITIVE_NAMES = {
    ".env", ".npmrc", ".netrc", "id_rsa", "id_ed25519", "credentials", "credentials.json",
    "secrets.json", "service-account.json",
}
# 通用占位路径白名单：文档里用作示例，不算本机痕迹
GENERIC_PATH_PREFIXES = ("d:\\output", "d:\\temp", "d:\\example", "./输出", "./output")

SECRET_KEYWORDS = (
    "password", "passwd", "pwd", "secret", "token", "api_key", "apikey", "access_key",
    "client_secret", "private_key", "credential", "authorization", "bearer",
)
SECRET_ASSIGN = re.compile(
    r"""(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|client[_-]?secret)"""
    r"""\s*[:=]\s*['\"][^'\"]{6,}['\"]"""
)
TOKEN_PATTERNS = {
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "GitHub PAT": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    "OpenAI key": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "AWS key id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\b"),
    "私钥 PEM": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
WINDOWS_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:\\\\?[^\s\"'`<>|,;)\]]{3,}")
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_CN = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
ID_CN = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
TODO_MARKERS = re.compile(r"(?i)\b(TODO|FIXME|XXX|HACK|待补充|待实现|以后再说)\b")


def load_identities() -> list[tuple[str, str]]:
    """收集本机可能泄漏身份的信息。"""
    identities: list[tuple[str, str]] = []
    for label, value in (
        ("用户名", os.environ.get("USERNAME", "")),
        ("计算机名", os.environ.get("COMPUTERNAME", "")),
        ("主机名", socket.gethostname()),
        ("用户目录名", Path.home().name),
    ):
        if value and len(value) > 3:
            identities.append((label, value))
    return identities


def scan_text(path: Path, root: Path, text: str, identities: list[tuple[str, str]]) -> list[str]:
    """扫描单个文本文件，返回问题列表。"""
    rel = path.relative_to(root)
    problems: list[str] = []

    for line_no, line in enumerate(text.splitlines(), 1):
        lowered = line.lower()
        for keyword in SECRET_KEYWORDS:
            if re.search(rf"\b{re.escape(keyword)}\b", lowered):
                problems.append(f"{rel}:{line_no}  密钥关键词「{keyword}」→ {line.strip()[:80]}")
        for name, pattern in TOKEN_PATTERNS.items():
            if pattern.search(line):
                problems.append(f"{rel}:{line_no}  {name} 疑似密钥")
        if SECRET_ASSIGN.search(line):
            problems.append(f"{rel}:{line_no}  疑似硬编码凭据赋值")
        for hit in EMAIL.findall(line):
            problems.append(f"{rel}:{line_no}  邮箱 {hit}")
        for hit in PHONE_CN.findall(line):
            problems.append(f"{rel}:{line_no}  手机号疑似 {hit[:3]}****{hit[-4:]}")
        for hit in ID_CN.findall(line):
            problems.append(f"{rel}:{line_no}  身份证号疑似 {hit[:3]}**********{hit[-3:]}")
        for label, value in identities:
            if value in line:
                problems.append(f"{rel}:{line_no}  本机{label}「{value}」出现在文本中")
        for hit in WINDOWS_PATH.findall(line):
            if hit.strip().lower().startswith(GENERIC_PATH_PREFIXES):
                continue
            problems.append(f"{rel}:{line_no}  本机绝对路径 → {hit.strip()[:70]}")
        for hit in TODO_MARKERS.findall(line):
            problems.append(f"{rel}:{line_no}  占位/待办标记「{hit}」")
    return problems


def scan_excel(path: Path, root: Path) -> list[str]:
    """检查 Excel 文档属性里是否带有个人身份。"""
    rel = path.relative_to(root)
    problems: list[str] = []
    try:
        with zipfile.ZipFile(path) as archive:
            if "docProps/core.xml" not in archive.namelist():
                return problems
            core = archive.read("docProps/core.xml").decode("utf-8", errors="replace")
    except (OSError, zipfile.BadZipFile) as error:
        return [f"{rel}  无法读取文档属性（{error}）"]

    for tag in ("dc:creator", "cp:lastModifiedBy"):
        match = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", core)
        if match and match.group(1).strip() not in ("", "sixcity-temperature-crawler"):
            problems.append(f"{rel}  文档属性 {tag} 含身份标识：{match.group(1).strip()}")
    return problems


def scan(root: Path, self_path: Path) -> list[str]:
    """扫描整个项目目录。"""
    problems: list[str] = []
    identities = load_identities()

    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        for name in list(dirnames):
            if name in CACHE_DIRS or name.endswith(".egg-info"):
                target = current.relative_to(root) / name
                problems.append(f"{target}/  缓存或构建目录，发布前应删除")
        for name in filenames:
            path = current / name
            rel = path.relative_to(root)
            if path.resolve() == self_path:
                continue
            if name.lower() in SENSITIVE_NAMES:
                problems.append(f"{rel}  敏感配置文件，不可发布")
            if name.endswith(tuple(JUNK_SUFFIXES)) or name.startswith("~$"):
                problems.append(f"{rel}  临时或备份文件，发布前应删除")
            if path.suffix.lower() == ".xlsx":
                problems.extend(scan_excel(path, root))
                continue
            if path.suffix.lower() in TEXT_SUFFIXES or path.name in {"LICENSE", ".gitignore"}:
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                problems.extend(scan_text(path, root, text, identities))
    return problems


def main() -> int:
    """命令行入口。"""
    default_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="发布前自检：查找可追溯到运行者的残留信息")
    parser.add_argument("--root", type=Path, default=default_root, help="待检查的项目根目录")
    args = parser.parse_args()

    root = args.root.resolve()
    problems = scan(root, Path(__file__).resolve())

    print(f"自检目录：{root}")
    if not problems:
        print("通过：未发现密钥、个人信息、本机绝对路径、缓存产物或文档身份标识。")
        return 0
    print(f"发现 {len(problems)} 处需要处理的问题：")
    for item in problems:
        print(f"  - {item}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
