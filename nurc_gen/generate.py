"""NURC本文の生成。

サイト(karal=関西選手権 / jara=インカレ)ごとに文体が異なるため、共通の
前処理(対象日の結果抽出・翌日スケジュール抽出・順位付与)を行ったうえで
スタイル別のレンダラに振り分ける。
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .models import Entry, Race, Regatta
from .ranking import assign_overall_ranks
from .resources import bundled_path

_TEMPLATE_DIR = bundled_path("templates")

# 個人種目コード(選手名を括弧書きする種目)
_SCULL_SINGLE = {"m1x", "w1x", "msm1x", "hmm1x"}

# インカレ: ラウンド英名 -> サマリー用日本語(「明日の〇〇へ」)
from .sites.jara import ROUND_JA  # noqa: E402


# ------------------------- 設定読み込み -------------------------

def load_config(path: str | Path) -> dict:
    """簡易 key: value 形式のYAMLを読む(外部ライブラリ不要)。"""
    cfg: dict[str, str] = {}
    p = Path(path)
    if not p.exists():
        return cfg
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, val = line.partition(":")
        cfg[key.strip()] = val.strip()
    return cfg


# ------------------------- 共通前処理 -------------------------

def _race_no_int(race: Race) -> int:
    m = re.match(r"\d+", race.no or "")
    return int(m.group()) if m else 0


def _bno_int(entry: Entry) -> int:
    m = re.match(r"\d+", entry.bno or "")
    return int(m.group()) if m else 999


def _fmt_time(t: str | None) -> str:
    """表示用タイム。先頭の余分な0を除く。'01:47.15' -> '1:47.15'。"""
    if not t:
        return ""
    return re.sub(r"^0(\d:)", r"\1", t.strip())


def _distinct_dates(regatta: Regatta) -> list[date]:
    ds = {r.date for r in regatta.races if r.date}
    return sorted(ds)


_WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]


def _fmt_day(d: date) -> str:
    return f"{d.month}/{d.day}({_WEEKDAY_JA[d.weekday()]})"


def _format_period(dates: list[date]) -> str:
    """大会全体の期間表記。'7/4(土)〜7/5(日)'。単日なら1つだけ。"""
    if not dates:
        return ""
    if len(dates) == 1:
        return _fmt_day(dates[0])
    return f"{_fmt_day(dates[0])}〜{_fmt_day(dates[-1])}"


def _resolve_target_date(regatta: Regatta, target: date | None) -> date | None:
    """対象日を決める。未指定なら名大の結果がある最終日。"""
    if target:
        return target
    dated = [r.date for r in regatta.races if r.date and r.has_nagoya and r.has_result]
    return max(dated) if dated else (max(_distinct_dates(regatta)) if _distinct_dates(regatta) else None)


def _next_race_date(regatta: Regatta, target: date) -> date | None:
    later = [d for d in _distinct_dates(regatta) if d > target]
    return min(later) if later else None


def _crew_display_kansen(e: Entry, event_code: str) -> str:
    """関西式のクルー表記。個人種目は '団体 （姓）'、団体種目は '団体'。"""
    if event_code in _SCULL_SINGLE and e.surname:
        return f"{e.team} （{e.surname}）"
    return e.team


# ------------------------- 関西選手権スタイル -------------------------

def _kansen_summary_line(event_name: str, code: str, races: list[Race], e_first: Entry) -> str:
    """
    1クルーの当日サマリー行。例:
      女子シングルスカル(足立)→予選4着、準決勝進出
      男子ダブルスカルB→予選4着、CR6着
    """
    suffix = e_first.team_suffix
    head = f"{event_name}{suffix}"
    if code in _SCULL_SINGLE and e_first.surname:
        head += f"({e_first.surname})"
    parts: list[str] = []
    for r in races:
        e = next((x for x in r.entries if x.team == e_first.team), None)
        if e is None:
            continue
        if e.status:
            parts.append(f"{r.round_name}{e.status}")
            continue
        if e.rank:
            seg = f"{r.round_name}{e.rank}着"
        else:
            seg = f"{r.round_name}出漕"
        # 進出先(→準決勝進出 等)を着順の後ろに付す
        dest = _qualify_dest(e.qualify_raw)
        if dest:
            seg += f"、{dest}"
        parts.append(seg)
    return f"{head}→" + "、".join(parts)


def _zen2han_alpha(s: str) -> str:
    """全角英字A-Z/a-zを半角へ。'Ｂ決勝' -> 'B決勝'。"""
    return "".join(
        chr(ord(c) - 0xFEE0) if ("Ａ" <= c <= "Ｚ" or "ａ" <= c <= "ｚ") else c
        for c in s
    )


def _qualify_dest(qualify_raw: str) -> str:
    """'→準決勝' -> '準決勝進出'、'→Ｂ決勝' -> 'B決勝進出'。空なら ''。"""
    q = _zen2han_alpha(qualify_raw.replace("→", "").strip())
    if not q:
        return ""
    if q.endswith("進出"):
        return q
    return q + "進出"


def _kansen_detail(race: Race) -> str:
    lines = [f"No.{race.no} {race.time} {race.event_name} {race.label()}"]
    for e in sorted(race.entries, key=_bno_int):
        crew = _crew_display_kansen(e, race.event_code)
        if e.status:
            lines.append(f"{e.bno} {crew}　{e.status}")
            continue
        t_mid = _fmt_time(e.split("1000m"))
        t_fin = _fmt_time(e.final_time)
        time_str = " ".join(t for t in (t_mid, t_fin) if t)
        nm = f" ({e.overall_rank}/{e.overall_total})" if e.overall_rank else ""
        dest = _qualify_dest(e.qualify_raw)
        arrow = f"→{dest}" if dest else ""
        lines.append(f"{e.bno} {crew}　{time_str}{nm}{arrow}".rstrip())
    return "\n".join(lines)


def _kansen_schedule(race: Race) -> str:
    lines = [f"No.{race.no} {race.time} {race.event_name} {race.label()}"]
    for e in sorted(race.entries, key=_bno_int):
        crew = _crew_display_kansen(e, race.event_code)
        lines.append(f"{e.bno} {crew}")
    if race.progression:
        lines.append(f"→{race.progression}")
    return "\n".join(lines)


def _render_kansen(regatta: Regatta, target: date, cfg: dict) -> str:
    dates = _distinct_dates(regatta)
    day_no = dates.index(target) + 1 if target in dates else 1
    next_date = _next_race_date(regatta, target)

    # 名大が出た当日の結果レース(レース番号順)
    result_races = sorted(
        [r for r in regatta.races
         if r.date == target and r.has_nagoya and r.has_result],
        key=_race_no_int,
    )
    # 翌日スケジュール(名大が出るレース)
    sched_races = sorted(
        [r for r in regatta.races
         if next_date and r.date == next_date and r.has_nagoya],
        key=_race_no_int,
    ) if next_date else []

    out: list[str] = []
    out.append("名古屋大学漕艇部公式インフォメーションをお送りいたします。\n")
    period = _format_period(dates)
    venue = regatta.venue or "（会場）"
    name = regatta.name or "本大会"
    tail = "の結果及び翌日のレーススケジュール" if sched_races else "の結果"
    out.append(
        f"{period}に{venue}にて行われております、{name}{day_no}日目{tail}についてお知らせいたします。\n"
    )

    # サマリー(種目ごとに名大クルーを1行)
    out.append(f"【{day_no}日目のレース結果】")
    for code, name_jp, entries_by_crew in _group_nagoya_by_crew(result_races):
        for team, (races_of_crew, e_first) in entries_by_crew.items():
            out.append(_kansen_summary_line(name_jp, code, races_of_crew, e_first))
    # CR注記
    if any("CR" in r.round_name for r in result_races):
        out.append(
            "CRとは敗者戦(Consolation Race)の略で、準決勝に進めなかったクルーでの"
            "レースを実施しました。"
        )
    out.append("")
    out.append(
        "以下、結果の詳細をお伝えします。（記載されているタイムは1000m地点、"
        "2000m地点でのタイムです。）\n"
    )

    for r in result_races:
        out.append(_kansen_detail(r))
        out.append("")

    if sched_races:
        out.append(f"【{day_no + 1}日目のレーススケジュール】\n")
        for r in sched_races:
            out.append(_kansen_schedule(r))
            out.append("")

    # 配信URL
    stream = cfg.get("stream_url_nurc") or ""
    out.append("【配信URL】")
    if stream:
        out.append(f"配信は以下のリンクよりご覧ください。\n\n{stream}\n")
    else:
        out.append("配信は以下のリンクよりご覧ください。\n\n【配信URLをここに貼付】\n")
    out.append("あたたかなご声援をよろしくお願いいたします。\n")

    out.append(_load_footer("footer_kansen.txt", cfg))
    return "\n".join(out)


# ------------------------- インカレスタイル -------------------------

def _round_ja(round_name: str) -> str:
    return ROUND_JA.get(round_name.strip(), round_name.strip())


def _intercollege_label(race: Race) -> str:
    """'Heat 1組' / 'Final A' のようなラウンド+組表記(英名は組の前に空白)。"""
    if race.group:
        return f"{race.round_name} {race.group}"
    return race.round_name


def _intercollege_detail(race: Race) -> str:
    lines = [f"No.{race.no} {race.time} {race.event_name} {_intercollege_label(race)}".rstrip()]
    for e in sorted(race.entries, key=_bno_int):
        if e.status:
            lines.append(f"{e.bno}.{e.team}　{e.status}")
            continue
        t_mid = _fmt_time(e.split("500m"))
        t_fin = _fmt_time(e.final_time)
        time_str = " ".join(t for t in (t_mid, t_fin) if t)
        nm = f"({e.overall_rank}/{e.overall_total})" if e.overall_rank else ""
        dest = e.qualify_raw.replace("→", "").strip()
        arrow = ""
        if dest and e.rank:
            arrow = f" →{e.rank}着　{dest}"
        elif dest:
            arrow = f" →{dest}"
        lines.append(f"{e.bno}.{e.team}　{time_str}{nm}{arrow}".rstrip())
    return "\n".join(lines)


def _intercollege_schedule(race: Race) -> str:
    lines = [f"No.{race.no} {race.time} {race.event_name} {_intercollege_label(race)}".rstrip()]
    for e in sorted(race.entries, key=_bno_int):
        lines.append(f"{e.bno}.{e.team}")
    return "\n".join(lines)


def _render_intercollege(regatta: Regatta, target: date, cfg: dict) -> str:
    dates = _distinct_dates(regatta)
    day_no = dates.index(target) + 1 if target in dates else 1
    next_date = _next_race_date(regatta, target)

    result_races = sorted(
        [r for r in regatta.races
         if r.date == target and r.has_nagoya and r.has_result],
        key=_race_no_int,
    )
    sched_races = sorted(
        [r for r in regatta.races
         if next_date and r.date == next_date and r.has_nagoya],
        key=_race_no_int,
    ) if next_date else []

    out: list[str] = []
    out.append("名古屋大学漕艇部公式インフォメーションをお送りいたします。\n")
    venue = regatta.venue or "戸田ボートコース"
    name = regatta.name or "全日本大学ローイング選手権"
    out.append(
        f"本日、{venue}にて行われました、{name}{day_no}日目の結果をお知らせ致します。\n"
    )

    # サマリー: 各名大クルーの「種目　当日ラウンドX着（n/m）→ 明日の◯◯へ / （本日終了）」
    # 対象日の結果を種目ごとに(同日複数レースなら後のレースで上書き=当日の最終結果)
    day_by_event: dict[str, tuple[Race, Entry]] = {}
    for r in result_races:
        for e in r.nagoya_entries:
            day_by_event[r.event_code] = (r, e)
    # 翌日の行き先(種目ごと)
    next_by_event: dict[str, str] = {}
    for r in sched_races:
        for e in r.nagoya_entries:
            next_by_event.setdefault(r.event_code, _round_ja(r.round_name))
    for code, (r, e) in day_by_event.items():
        rd = _round_ja(r.round_name)
        if e.rank:
            res = f"{rd}{e.rank}着"
        elif e.status:
            res = f"{rd}{e.status}"
        else:
            res = rd
        nm = f"（{e.overall_rank}/{e.overall_total}）" if e.overall_rank else ""
        dest = next_by_event.get(code)
        tail = f"→ 明日の{dest}へ" if dest else "（本日終了）"
        out.append(f"{r.event_name}　{res}{nm}{tail}\n")

    out.append(
        "以下が結果の詳細です。500m 地点、2000m 地点でのタイムを記載しています。\n"
    )
    for r in result_races:
        out.append(_intercollege_detail(r))
        out.append("")

    if sched_races:
        out.append("続いて翌日行われますレースのスケジュールをお知らせいたします。\n")
        for r in sched_races:
            out.append(_intercollege_schedule(r))
            out.append("")

    # 配信URL
    su_nurc = cfg.get("stream_url_nurc") or "【名大漕艇部 配信URLを貼付】"
    su_off = cfg.get("stream_url_official") or "【大会公式 配信URLを貼付】"
    out.append("本大会は名古屋大学漕艇部と大会公式よりライブ配信がございます。\n")
    out.append(f"・名大漕艇部\n{su_nurc}\n")
    out.append(f"・大会公式\n{su_off}\n")

    out.append(_load_footer("footer_intercollege.txt", cfg))
    return "\n".join(out)


# ------------------------- 補助 -------------------------

def _group_nagoya_by_crew(races: list[Race]):
    """結果レース群を種目コード順にまとめ、各種目内で名大クルー別に
    (そのクルーが出た全レース, 代表Entry) を返す。
    yield (event_code, event_name, {team: (races_of_crew, entry0)})。
    """
    by_event: dict[str, list[Race]] = {}
    for r in races:
        by_event.setdefault(r.event_code, []).append(r)

    for code in sorted(by_event, key=lambda c: min(_race_no_int(r) for r in by_event[c])):
        ev_races = sorted(by_event[code], key=_race_no_int)
        name_jp = ev_races[0].event_name
        crews: dict[str, tuple[list[Race], Entry]] = {}
        for r in ev_races:
            for e in r.nagoya_entries:
                if e.team not in crews:
                    crews[e.team] = ([], e)
                crews[e.team][0].append(r)
        # 団体名(A,B,C…)順に整列
        ordered = dict(sorted(crews.items(), key=lambda kv: kv[0]))
        yield code, name_jp, ordered


def _load_footer(filename: str, cfg: dict) -> str:
    path = _TEMPLATE_DIR / filename
    text = path.read_text(encoding="utf-8")
    replacements = {
        "accountant_title": cfg.get("accountant_title", "会計担当"),
        "accountant_kanji": cfg.get("accountant_kanji", "（会計担当氏名）"),
        "accountant_kana": cfg.get("accountant_kana", "（カナ）"),
        "accountant_email": cfg.get("accountant_email", "（会計メールアドレス）"),
    }
    for k, v in replacements.items():
        text = text.replace("{" + k + "}", v or f"（{k}）")
    return text


# ------------------------- エントリポイント -------------------------

def generate(regatta: Regatta, target: date | None, cfg: dict) -> str:
    assign_overall_ranks(regatta)
    tgt = _resolve_target_date(regatta, target)
    if tgt is None:
        return "（対象となるレース日が特定できませんでした。ページ構造をご確認ください。）"
    if regatta.site == "karal":
        return _render_kansen(regatta, tgt, cfg)
    if regatta.site == "jara":
        return _render_intercollege(regatta, tgt, cfg)
    raise ValueError(f"未対応サイト: {regatta.site}")
