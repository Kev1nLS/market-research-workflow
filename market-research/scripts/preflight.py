#!/usr/bin/env python3
"""preflight.py — Markdown 转 PDF 前的排版预检。

检查三类会毁掉 PDF 排版的常见问题：
  1. 列表/表格紧跟段落且中间无空行（Python-Markdown 会把列表吸进段落）
  2. 文档开头连续元信息行（**xx**：yy）缺行尾双空格（不会硬换行）
  3. 表格列数与分隔线不一致（渲染错位）

用法：
    python -I scripts/preflight.py <input.md> [more.md ...]

退出码：有 issue 返回 1，全部通过返回 0。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# 让中文在 GBK 控制台也能安全输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BLOCK_START = re.compile(r"^(\s*[-*+] |\s*\d+\. |\||\s*> |#{1,6} |```|---)")
SEPARATOR = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
META = re.compile(r"^\*\*.+\*\*：.+")


def check(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    issues: list[str] = []

    # 1) 列表/表格紧跟普通段落
    for i in range(1, len(lines)):
        prev, cur = lines[i - 1], lines[i]
        if not prev.strip() or BLOCK_START.match(prev):
            continue
        if BLOCK_START.match(cur):
            issues.append(f"L{i + 1} 可能被吸收: prev={prev[:30]!r} cur={cur[:30]!r}")

    # 2) 开头元信息行硬换行
    for i, line in enumerate(lines[:8]):
        if META.match(line) and not line.endswith("  "):
            issues.append(f"L{i + 1} 元信息行缺行尾双空格: {line[:30]!r}")

    # 3) 表格列数一致性
    i = 0
    while i < len(lines):
        if (
            lines[i].strip().startswith("|")
            and i + 1 < len(lines)
            and SEPARATOR.match(lines[i + 1])
        ):
            head_cols = lines[i].count("|")
            if lines[i + 1].count("|") != head_cols:
                issues.append(
                    f"L{i + 1} 表头 {head_cols} 管 vs 分隔 {lines[i + 1].count('|')} 管"
                )
            j = i + 2
            while j < len(lines) and lines[j].strip().startswith("|"):
                if lines[j].count("|") != head_cols:
                    issues.append(
                        f"L{j + 1} 行 {lines[j].count('|')} 管 vs 表头 {head_cols} 管: {lines[j][:40]!r}"
                    )
                j += 1
            i = j
        else:
            i += 1

    return issues


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
        issues = check(path)
        print(f"checked: {path.name}")
        if issues:
            failed = True
            for x in issues:
                print("  ISSUE:", x)
        else:
            print("  no issues")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
