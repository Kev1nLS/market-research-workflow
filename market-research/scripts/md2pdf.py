#!/usr/bin/env python3
"""md2pdf.py — 把 Markdown 渲染成排版干净的中文 PDF。

路子：Markdown -> HTML（内置中文排版模板）-> Edge/Chrome 无头浏览器打印 PDF。
这台机器上没有 pandoc / wkhtmltopdf，Edge 是现成且中文渲染最稳的一条路。

用法:
    python -I scripts/md2pdf.py <input.md> [output.pdf]

省略 output.pdf 时，PDF 与 md 同目录、同名。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import markdown

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "/usr/bin/microsoft-edge",
    "/usr/bin/google-chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
]

CSS = """
@page { size: A4; margin: 18mm 16mm 20mm 16mm; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }

body {
  margin: 0;
  font-family: "Microsoft YaHei", "PingFang SC", "Hiragino Sans GB",
               "Noto Sans CJK SC", "Segoe UI", sans-serif;
  font-size: 10.5pt;
  line-height: 1.8;
  color: #1f2328;
  text-align: justify;
  word-break: break-word;
}

h1 {
  font-size: 19pt; line-height: 1.4; margin: 0 0 .6em;
  padding-bottom: .3em; border-bottom: 2px solid #2b6cb0;
  color: #14304f; text-align: left;
}
h2 {
  font-size: 14pt; margin: 1.7em 0 .6em; padding-left: .55em;
  border-left: 4px solid #2b6cb0; color: #14304f;
  page-break-after: avoid; text-align: left;
}
h3 {
  font-size: 12pt; margin: 1.35em 0 .5em; color: #1c4e80;
  page-break-after: avoid; text-align: left;
}
h4 {
  font-size: 11pt; margin: 1.1em 0 .4em; color: #333;
  page-break-after: avoid; text-align: left;
}

p { margin: .55em 0; }
a { color: #2b6cb0; text-decoration: none; }
strong { color: #10305a; font-weight: 700; }
em { color: #4a5568; font-style: normal; }

ul, ol { margin: .55em 0; padding-left: 1.7em; }
li { margin: .28em 0; }
li > ul, li > ol { margin: .25em 0; }

blockquote {
  margin: .9em 0; padding: .6em .95em;
  background: #f5f8fc; border-left: 3px solid #9dc0e8; color: #445063;
}
blockquote p { margin: .2em 0; }

code {
  font-family: "Cascadia Mono", Consolas, "Courier New", monospace;
  font-size: .92em; background: #f0f2f5; color: #b3306b;
  padding: .1em .35em; border-radius: 3px;
}
pre {
  background: #f6f8fa; border: 1px solid #e2e6ea; border-radius: 5px;
  padding: .8em 1em; white-space: pre-wrap; overflow-wrap: break-word;
  page-break-inside: avoid;
}
pre code {
  background: none; color: #1f2328; padding: 0;
  font-size: .9em; line-height: 1.65;
}

table {
  width: 100%; border-collapse: collapse; margin: .9em 0; font-size: .95em;
}
th, td {
  border: 1px solid #d6dce3; padding: .5em .7em;
  text-align: left; vertical-align: top;
}
th { background: #eef3f9; font-weight: 700; color: #14304f; }
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
/* 首列全是短词时不让它被折行（如「品牌打造」被拆成两行） */
table.tight-first-col th:first-child,
table.tight-first-col td:first-child { white-space: nowrap; }

hr { border: none; border-top: 1px solid #dfe3e8; margin: 2em 0; }
"""

TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title}</title>
<base href="{base}">
<style>{css}</style>
</head>
<body>
{body}
</body>
</html>
"""


def find_browser() -> str:
    for path in BROWSERS:
        if os.path.exists(path):
            return path
    for name in ("msedge", "microsoft-edge", "google-chrome", "chrome", "chromium"):
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError("没找到 Edge / Chrome，无法打印 PDF")


def extract_title(md_text: str, fallback: str) -> str:
    for line in md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


TAG_RE = re.compile(r"<[^>]+>")
TABLE_RE = re.compile(r"<table>.*?</table>", re.S)
ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.S)
CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)


def tune_tables(html: str) -> str:
    """首列内容全是短词时打个标记，避免「品牌打造」被折成两行。"""

    def mark(match: re.Match) -> str:
        table = match.group(0)
        first_col = [
            TAG_RE.sub("", cells[0]).strip()
            for row in ROW_RE.findall(table)
            if (cells := CELL_RE.findall(row))
        ]
        if first_col and max(len(c) for c in first_col) <= 8:
            return table.replace("<table>", '<table class="tight-first-col">', 1)
        return table

    return TABLE_RE.sub(mark, html)


def build_html(md_text: str, base_dir: Path) -> str:
    body = markdown.Markdown(extensions=["extra", "sane_lists"]).convert(md_text)
    body = tune_tables(body)
    return TEMPLATE.format(
        title=extract_title(md_text, "文档"),
        base=base_dir.as_uri() + "/",
        css=CSS,
        body=body,
    )


def print_to_pdf(browser: str, html_path: Path, pdf_path: Path) -> None:
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    if pdf_path.exists():
        pdf_path.unlink()

    errors = []
    for flag in ("--headless=new", "--headless"):
        with tempfile.TemporaryDirectory(prefix="md2pdf-") as profile:
            cmd = [
                browser,
                flag,
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                "--no-pdf-header-footer",
                f"--user-data-dir={profile}",
                "--virtual-time-budget=10000",
                f"--print-to-pdf={pdf_path}",
                html_path.as_uri(),
            ]
            try:
                proc = subprocess.run(cmd, capture_output=True, timeout=120)
            except subprocess.TimeoutExpired:
                errors.append(f"{flag}: 超时")
                continue

        if pdf_path.exists() and pdf_path.stat().st_size > 0:
            return
        raw = (proc.stderr or proc.stdout or b"").decode("utf-8", "replace")
        detail = raw.strip().splitlines()
        errors.append(f"{flag}: " + (" | ".join(detail[-2:]) if detail else "无输出"))

    raise RuntimeError("打印 PDF 失败 -> " + " ;; ".join(errors))


def main(argv: list[str]) -> int:
    if not 2 <= len(argv) <= 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2

    md_path = Path(argv[1]).resolve()
    if not md_path.is_file():
        print(f"找不到文件: {md_path}", file=sys.stderr)
        return 2

    pdf_path = Path(argv[2]).resolve() if len(argv) == 3 else md_path.with_suffix(".pdf")

    md_text = md_path.read_text(encoding="utf-8")
    html = build_html(md_text, md_path.parent)
    browser = find_browser()

    with tempfile.TemporaryDirectory(prefix="md2pdf-") as tmp:
        html_path = Path(tmp) / "doc.html"
        html_path.write_text(html, encoding="utf-8")
        print_to_pdf(browser, html_path, pdf_path)

    print(f"{pdf_path}  ({pdf_path.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
