#!/usr/bin/env python3
"""Server酱 (sct.ftqq.com) 微信推送工具。

用法:
    python3 push_serverchan.py "标题" "正文 markdown"
    python3 push_serverchan.py --file reports/example_candidates.md
    python3 push_serverchan.py --sendkey SCTxxx --title "..." --desp "..."

SendKey 也可以从环境变量 SERVERCHAN_SENDKEY 读取 (推荐, 避免写在命令行里被 history 记录)。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API_URL = "https://sctapi.ftqq.com/{sendkey}.send"
DEFAULT_TITLE = "闲鱼监控汇报"

# Server酱 free 版对单条长度敏感 (~2000 字符), 太长截断并标注
MAX_DESP_CHARS = 1800


def read_text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def extract_first_heading(text: str, fallback: str) -> str:
    for line in text.splitlines():
        m = re.match(r"^#\s+(.+?)\s*$", line.strip())
        if m:
            return m.group(1).strip()
    return fallback


def first_table_rows(text: str, n: int = 6) -> str:
    """从 markdown 报告里抠出最有用的一张候选表 (前 n 行), 转成 Server酱友好的纯文本块。"""
    lines = text.splitlines()
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.lstrip().startswith("|"):
            current.append(line)
        else:
            if current:
                blocks.append(current)
                current = []
    if current:
        blocks.append(current)
    if not blocks:
        return ""
    # 取最大的那块表 (通常是 "最合适候选" 候选表)
    table = max(blocks, key=len)
    cleaned = []
    for row in table[: n + 2]:  # header + separator + n rows
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        cleaned.append(" | ".join(cells))
    return "\n".join(cleaned)


def to_desp(title: str, full_text: str) -> str:
    """拼接一条友好的 Server酱正文: 标题 + 候选表 + 完整报告链接提示。"""
    table_block = first_table_rows(full_text, n=6)
    if not table_block:
        desp = full_text
    else:
        desp = (
            "## 候选概览\n\n"
            f"```\n{table_block}\n```\n\n"
            f"---\n\n"
            f"完整报告 (含价格分布、全部候选、风险点):\n\n"
            f"`reports/example_candidates.md`\n"
        )
    if len(desp) > MAX_DESP_CHARS:
        desp = desp[: MAX_DESP_CHARS - 60] + "\n\n...(已截断, 看完整报告)..."
    return desp


def post_serverchan(sendkey: str, title: str, desp: str) -> dict:
    url = API_URL.format(sendkey=sendkey)
    data = urllib.parse.urlencode({"title": title, "desp": desp}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("User-Agent", "goofish-monitor-lite/1.0")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return {"http_status": resp.status, "body": body}
    except Exception as exc:  # noqa: BLE001
        return {"http_status": None, "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="通过 Server酱 推送 markdown 报告到微信")
    parser.add_argument("title_pos", nargs="?", help="推送标题 (位置参数)")
    parser.add_argument("desp_pos", nargs="?", help="推送正文 (位置参数)")
    parser.add_argument("--file", help="从 markdown 文件读内容 (优先于位置参数)")
    parser.add_argument("--sendkey", help="Server酱 SendKey (默认读 SERVERCHAN_SENDKEY 环境变量)")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要发送的内容, 不真发")
    parser.add_argument("--print-only", action="store_true", help="打印 Server酱 响应 (不接 cron 推送失败时排查用)")
    args = parser.parse_args()

    sendkey = args.sendkey or os.environ.get("SERVERCHAN_SENDKEY", "").strip()
    if not args.dry_run and not sendkey:
        print("ERROR: 必须提供 --sendkey 或设置环境变量 SERVERCHAN_SENDKEY", file=sys.stderr)
        return 2

    if args.file:
        full = read_text(args.file)
        title = args.title_pos or extract_first_heading(full, DEFAULT_TITLE)
        desp = to_desp(title, full)
    elif args.desp_pos is not None:
        title = args.title_pos or DEFAULT_TITLE
        desp = args.desp_pos
    else:
        print("ERROR: 必须提供 --file 或位置参数 (title, desp)", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"[DRY-RUN] title ({len(title)} chars): {title}")
        print(f"[DRY-RUN] desp ({len(desp)} chars):\n{desp}")
        return 0

    result = post_serverchan(sendkey, title, desp)
    print(json.dumps(result, ensure_ascii=False))
    if result.get("http_status") and 200 <= result["http_status"] < 300:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
