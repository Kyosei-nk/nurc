"""ローカルフィクスチャによるオフライン回帰テスト(ライブ通信なし)。

実行: python tests/test_offline.py
tests/fixtures/ 内の保存済みHTMLをパースし、既知の値を検証する。
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nurc_gen.generate import generate, load_config  # noqa: E402
from nurc_gen.models import Regatta  # noqa: E402
from nurc_gen.ranking import assign_overall_ranks  # noqa: E402
from nurc_gen.sites import jara, karal  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
_failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    mark = "OK " if cond else "NG "
    print(f"  [{mark}] {msg}")
    if not cond:
        _failures.append(msg)


def _karal_regatta() -> Regatta:
    reg = Regatta(name="2026年度関西選手権競漕大会",
                  venue="大阪府立漕艇センター(浜寺漕艇場)", site="karal")
    events = [("m1x", "男子シングルスカル"), ("m2x", "男子ダブルスカル"),
              ("m4+", "男子舵手つきフォア"), ("w1x", "女子シングルスカル"),
              ("w2x", "女子ダブルスカル")]
    for code, name in events:
        html = (FIX / f"karal_{code}.htm").read_bytes().decode("cp932", "replace")
        reg.races.extend(karal._parse_event_page(html, code, name, 2026))
    return reg


def _jara_regatta() -> Regatta:
    reg = Regatta(name="第52回全日本大学ローイング選手権大会",
                  venue="戸田ボートコース", site="jara")
    events = [("m2x", "男子ダブルスカル"), ("m4x", "男子クォドルプル"),
              ("m4+", "男子舵手付きフォア"), ("w2x", "女子ダブルスカル"),
              ("w8+", "女子エイト")]
    for code, name in events:
        html = (FIX / f"jara_{code}.html").read_text(encoding="utf-8")
        reg.races.extend(jara._parse_event_page(html, code, name, 2025))
    return reg


def test_karal_parse() -> None:
    print("[関西] パース")
    reg = _karal_regatta()
    check(len(reg.races) > 20, f"レース抽出 {len(reg.races)} 件")
    # 名工大を名大と誤判定しない
    m1x = [r for r in reg.races if r.event_code == "m1x"]
    koudai = [e for r in m1x for e in r.entries if e.team.startswith("名古屋工業")]
    check(koudai and all(not e.is_nagoya for e in koudai), "名古屋工業大学を名大扱いしない")
    # 名大M2X予選の総合順位(サンプル一致点)
    assign_overall_ranks(reg)
    a = next(e for r in reg.races if r.event_code == "m2x" and "予選" in r.round_name
             for e in r.entries if e.team == "名古屋大学A")
    check((a.overall_rank, a.overall_total) == (1, 21), f"M2X名大A (n/m)=({a.overall_rank}/{a.overall_total}) 期待(1/21)")


def test_jara_parse() -> None:
    print("[インカレ] パース")
    reg = _jara_regatta()
    assign_overall_ranks(reg)
    nagoya = next(e for r in reg.races if r.event_code == "m2x" and r.round_name == "Heat"
                  for e in r.entries if e.is_nagoya)
    check((nagoya.overall_rank, nagoya.overall_total) == (3, 25),
          f"M2X名大Heat (n/m)=({nagoya.overall_rank}/{nagoya.overall_total}) 期待(3/25)")
    # 除外の検出
    exc = [e for r in reg.races for e in r.entries if e.status]
    check(any("除外" in e.status for e in exc), "除外/DNS等の特殊状態を検出")


def test_generate() -> None:
    cfg = load_config(ROOT / "config.yaml")
    print("[関西] 生成(1日目)")
    txt = generate(_karal_regatta(), date(2026, 7, 4), cfg)
    check("1日目の結果及び翌日のレーススケジュール" in txt, "ヘッダ文面")
    check("女子シングルスカル(足立)→予選4着、準決勝進出" in txt, "サマリー行")
    check("【2日目のレーススケジュール】" in txt, "翌日スケジュール見出し")
    check("会計担当 3年 熊澤志映" in txt, "フッター差し込み")
    check("�" not in txt, "文字化けなし")

    print("[インカレ] 生成(1日目)")
    txt = generate(_jara_regatta(), date(2025, 9, 3), cfg)
    check("男子ダブルスカル　予選2着（3/25）→ 明日の敗者復活戦へ" in txt, "サマリー行(着順+進出先)")
    check("No.14 9:10 男子ダブルスカル Heat 1組" in txt, "詳細見出し")
    check("4.名古屋大学　1:39.49 7:06.24(3/25)" in txt, "名大の記録行")

    print("[インカレ] 生成(2日目=速報)")
    txt2 = generate(_jara_regatta(), date(2025, 9, 4), cfg)
    check("2日目の結果" in txt2, "2日目ヘッダ")
    check("Repechage 1組" in txt2, "2日目の敗者復活戦結果")
    check("男子ダブルスカル　敗者復活戦1着（3/25）→ 明日の準々決勝へ" in txt2, "進出クルーのサマリー(着順+進出先)")
    check("男子クォドルプル　敗者復活戦4着（15/17）（本日終了）" in txt2, "非進出クルーの本日終了表記")


def main() -> int:
    for fn in (test_karal_parse, test_jara_parse, test_generate):
        fn()
    print()
    if _failures:
        print(f"FAILED: {len(_failures)} 件")
        for f in _failures:
            print("  -", f)
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
