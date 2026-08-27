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


def test_is_nagoya() -> None:
    print("[共通] 名大判定(混成クルー対応・名工大除外)")
    from nurc_gen.models import Entry
    def isn(name: str) -> bool:
        return Entry(team=name).is_nagoya
    check(isn("名古屋大学"), "名古屋大学")
    check(isn("名古屋大学A"), "名古屋大学A")
    check(isn("名古屋大南山大混成"), "名古屋大南山大混成(混成クルー)")
    check(not isn("名古屋工業大学"), "名古屋工業大学は除外")
    check(not isn("市岡 俊祐 (名古屋工業大学)"), "名工大の個人種目表記も除外")


def test_intercollege_dest() -> None:
    print("[インカレ] 進出先の和訳(年ごとの規定変化に対応)")
    from nurc_gen.generate import _dest_ja
    check(_dest_ja("→Quarter finals") == "準々決勝", "Quarter finals→準々決勝")
    check(_dest_ja("→Semi-Final") == "準決勝", "Semi-Final→準決勝")
    check(_dest_ja("→Final A") == "A決勝", "Final A→A決勝")
    check(_dest_ja("→Final E") == "E決勝", "Final E→E決勝(今年のタイム順進出)")
    check(_dest_ja("→Final E 3組") == "E決勝", "組番号付きでもFinal E→E決勝")
    check(_dest_ja("") == "", "空欄(敗者復活戦行き)は空")


def test_intercollege_per_round_rank() -> None:
    print("[インカレ] (n/m)はその日のラウンドのタイム順位(予選順位を引き継がない)")
    from nurc_gen.models import Race, Entry
    # 予選: 名大は3クルー中3位。準々決勝(別日): 名大は2クルー中1位。
    heat = Race(event_code="m2x", round_name="Heat", group="1組",
                date=date(2026, 8, 26),
                entries=[Entry(team="A大", splits={"2000m": "7:00.00"}),
                         Entry(team="B大", splits={"2000m": "7:10.00"}),
                         Entry(team="名古屋大学", splits={"2000m": "7:20.00"})])
    qf = Race(event_code="m2x", round_name="QF", group="1組",
              date=date(2026, 8, 27),
              entries=[Entry(team="名古屋大学", splits={"2000m": "7:05.00"}),
                       Entry(team="C大", splits={"2000m": "7:15.00"})])
    reg = Regatta(site="jara", races=[heat, qf])
    assign_overall_ranks(reg)
    nh = next(e for e in heat.entries if e.is_nagoya)
    nq = next(e for e in qf.entries if e.is_nagoya)
    check((nh.overall_rank, nh.overall_total) == (3, 3), f"予選は予選全体で3/3 (実際{nh.overall_rank}/{nh.overall_total})")
    check((nq.overall_rank, nq.overall_total) == (1, 2), f"準々決勝は準々決勝全体で1/2 (実際{nq.overall_rank}/{nq.overall_total})")


def test_intercollege_flexible_progress() -> None:
    print("[インカレ] 進出先＝実スケジュール(3着でも進出・明後日表記)")
    from nurc_gen.models import Race, Entry
    from nurc_gen.generate import _render_intercollege
    # 予選3着(1,2着以外)だが実際は準決勝へ進むクルー。準決勝は「明後日」開催。
    heat = Race(no="1", date=date(2026, 8, 27), time="10:00", event_code="w8+",
                event_name="女子エイト", round_name="Heat", group="1組",
                entries=[Entry(bno="1", team="立教大学", rank=1, qualify_raw="→Semi-Final",
                               splits={"2000m": "7:00.00"}),
                         Entry(bno="2", team="名古屋大学", rank=3,
                               splits={"2000m": "8:00.00"})])
    semi = Race(no="20", date=date(2026, 8, 29), time="16:00", event_code="w8+",
                event_name="女子エイト", round_name="Semi F", group="1組",
                entries=[Entry(bno="1", team="名古屋大学"),
                         Entry(bno="2", team="立教大学")])
    reg = Regatta(name="テスト", venue="戸田", site="jara", races=[heat, semi])
    assign_overall_ranks(reg)
    txt = _render_intercollege(reg, date(2026, 8, 27), {})
    summary = txt.split("以下が結果の詳細")[0]
    check("女子エイト　予選3着→ 明後日の準決勝へ" in summary, "3着でも準決勝進出・明後日表記")
    check("2.名古屋大学　8:00.00(2/2) →3着　Semi-Finalへ" in txt, "詳細欄でも3着の進出先を明示")


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
    # サマリーは着順のみ(総合順位(n/m)は載せない)＋実スケジュールから進出先
    check("男子ダブルスカル　予選2着→ 明日の敗者復活戦へ" in txt, "サマリー行(着順+進出先/順位なし)")
    check("（3/25）" not in txt.split("以下が結果の詳細")[0], "サマリーに(n/m)を出さない")
    check("No.14 9:10 男子ダブルスカル Heat 1組" in txt, "詳細見出し")
    # 詳細欄は(n/m)を残しつつ、実際の進出先を「→N着 ○○へ」で付す
    check("4.名古屋大学　1:39.49 7:06.24(3/25) →2着　Repechageへ" in txt, "名大の記録行(進出先付き)")

    print("[インカレ] 生成(2日目=速報)")
    txt2 = generate(_jara_regatta(), date(2025, 9, 4), cfg)
    check("2日目の結果" in txt2, "2日目ヘッダ")
    check("Repechage 1組" in txt2, "2日目の敗者復活戦結果")
    check("男子ダブルスカル　敗者復活戦1着→ 明日の準々決勝へ" in txt2, "進出クルーのサマリー(着順+進出先/順位なし)")
    check("男子クォドルプル　敗者復活戦4着（本日終了）" in txt2, "非進出クルーの本日終了表記(順位なし)")


def main() -> int:
    for fn in (test_karal_parse, test_jara_parse, test_is_nagoya,
               test_intercollege_dest, test_intercollege_per_round_rank,
               test_intercollege_flexible_progress, test_generate):
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
