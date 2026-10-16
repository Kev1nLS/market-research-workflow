#!/usr/bin/env python3
"""table_check.py — 商品数据表（CSV）交付前检查。

检查项：
  1. 编码为 UTF-8 with BOM（Excel 打开中文列头不乱码）
  2. 列头与规范一致（默认 11 列）
  3. 各行列数与列头一致
  4. 「待核验」行全部列出（人工一眼找到要补什么；交付前应清零）
  5. 商品链接列空值提示

用法：
    python -I scripts/table_check.py <table.csv>

退出码：有 issue 或仍有待核验行返回 1，全部通过返回 0。
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

# 让中文在 GBK 控制台也能安全输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

EXPECTED_COLS = 11
STATUS_COL = "数据状态"
LINK_COL = "商品链接"
PENDING = "待核验"


def check(path: Path) -> tuple[list[str], list[str]]:
    """返回 (issues, pending_lines)。"""
    raw = path.read_bytes()
    issues: list[str] = []
    pending: list[str] = []

    # 1) BOM 检查
    if not raw.startswith(b"\xef\xbb\xbf"):
        issues.append("文件无 UTF-8 BOM —— Windows Excel 打开中文列头会乱码（另存为 UTF-8 with BOM）")

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        issues.append(f"无法按 UTF-8 解码: {e}")
        return issues, pending

    rows = list(csv.reader(text.splitlines()))
    rows = [r for r in rows if any(c.strip() for c in r)]  # 跳过全空行
    if not rows:
        issues.append("文件为空")
        return issues, pending

    header = [c.strip() for c in rows[0]]
    # 2) 列头检查
    if len(header) != EXPECTED_COLS:
        issues.append(f"列头 {len(header)} 列，规范为 {EXPECTED_COLS} 列: {header}")

    status_idx = header.index(STATUS_COL) if STATUS_COL in header else None
    link_idx = header.index(LINK_COL) if LINK_COL in header else None
    if status_idx is None:
        issues.append(f"列头缺少「{STATUS_COL}」列")
    if link_idx is None:
        issues.append(f"列头缺少「{LINK_COL}」列")

    # 3) 逐行列数与关键列检查
    for n, row in enumerate(rows[1:], start=2):  # 第 2 行起为数据行（行号按表格计）
        if len(row) != len(header):
            issues.append(f"第 {n} 行 {len(row)} 列 vs 列头 {len(header)} 列")
            continue
        if status_idx is not None and row[status_idx].strip() == PENDING:
            pending.append(f"第 {n} 行: {row[1].strip()[:30] if len(row) > 1 else '?'}")
        if link_idx is not None and not row[link_idx].strip():
            issues.append(f"第 {n} 行商品链接为空（人工补表要靠链接找到商品页）")

    return issues, pending


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    failed = False
    for arg in argv[1:]:
        path = Path(arg).resolve()
        if not path.is_file():
            print(f"找不到文件: {path}", file=sys.stderr)
            failed = True
            continue
        issues, pending = check(path)
        print(f"checked: {path.name}")
        for x in issues:
            print("  ISSUE:", x)
        if pending:
            failed = True
            print(f"  待核验 {len(pending)} 行（交付前应清零）:")
            for p in pending:
                print("   PENDING:", p)
        if not issues and not pending:
            print("  no issues")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
