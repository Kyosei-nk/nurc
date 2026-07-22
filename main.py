"""NURC自動生成ツール CLIエントリポイント。

使い方:
    python main.py <大会HPのURL> [--date YYYY-MM-DD] [--out ファイル] [--config config.yaml]

例:
    python main.py https://karal.jp/news_flash/result.htm --date 2026-07-04
    python main.py https://www.jara.or.jp/race/2025/2025intercollege.html --date 2025-09-03
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from nurc_gen.pipeline import generate_nurc
from nurc_gen.resources import external_config_path

_ROOT = Path(__file__).resolve().parent


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise SystemExit(f"日付は YYYY-MM-DD 形式で指定してください: {s}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="大会HPからNURC結果報告文を生成する")
    parser.add_argument("url", help="大会結果ページのURL")
    parser.add_argument("--date", help="対象日(YYYY-MM-DD)。省略時は結果掲載済みの最終日")
    parser.add_argument("--out", help="出力先ファイル。省略時は output/ に自動命名")
    parser.add_argument("--config", default=str(external_config_path()), help="設定YAML")
    parser.add_argument("--stdout", action="store_true", help="ファイル保存せず標準出力へ")
    args = parser.parse_args(argv)

    target = _parse_date(args.date)

    try:
        result = generate_nurc(args.url, target, args.config)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2

    day = f"{result.resolved_target:%Y-%m-%d}" if result.resolved_target else "?"
    auto = "" if result.target_specified else "(自動判定)"
    print(f"[情報] {result.site} サイト: 全 {result.total_races} レース、名大出場 "
          f"{result.nagoya_races} 件。対象日 {day}{auto} の名大結果 "
          f"{result.day_result_races} 件を本文に反映", file=sys.stderr)

    text = result.text
    if args.stdout:
        print(text)
        return 0

    if args.out:
        out_path = Path(args.out)
    else:
        out_dir = _ROOT / "output"
        out_dir.mkdir(exist_ok=True)
        short = "kansen" if result.site == "karal" else "intercollege"
        tag = (target or date.today()).strftime("%Y%m%d")
        out_path = out_dir / f"NURC_{short}_{tag}.txt"

    out_path.write_text(text, encoding="utf-8")
    print(f"[完了] NURCを書き出しました: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
