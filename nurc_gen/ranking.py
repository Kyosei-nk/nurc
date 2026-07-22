"""(n/m) 総合順位の算出。

NURC本文に載る `(20/29)` のような表記はソースHTMLには無く、NURC作成者が
手計算していた値。規則(サンプルから逆算):
- m = その種目の予選(Heat)に出漕し、ゴールタイムを持つ全クルー数
- n = 同種目の予選全組を通したゴールタイム(最終地点)昇順での順位
- 予選以外(CR/敗者復活/決勝等)に同一クルーが登場する場合は、予選で得た (n/m) を
  そのまま再掲する(サンプルのCR行が予選と同じ数値だったことに基づく)
"""

from __future__ import annotations

import re

from .models import Regatta

# 予選相当のラウンド名(この集合を母数計算の対象にする)
_HEAT_ROUNDS = ("予選", "Heat", "heat")


def _time_to_seconds(t: str) -> float | None:
    """'8:19.28' や '01:42.68' を秒に変換。パース不能なら None。"""
    if not t:
        return None
    t = t.strip()
    m = re.match(r"(?:(\d+):)?(\d+(?:\.\d+)?)$", t)
    if not m:
        # 'M:SS.xx' 形式
        m = re.match(r"(\d+):(\d+(?:\.\d+)?)$", t)
        if not m:
            return None
        return int(m.group(1)) * 60 + float(m.group(2))
    minutes = int(m.group(1)) if m.group(1) else 0
    return minutes * 60 + float(m.group(2))


def _is_heat(round_name: str) -> bool:
    return any(h in round_name for h in _HEAT_ROUNDS)


def assign_overall_ranks(regatta: Regatta) -> None:
    """Regatta内の全Entryに overall_rank/overall_total を付与(破壊的更新)。"""
    # 種目ごとに予選エントリを集約
    by_event: dict[str, list] = {}
    for race in regatta.races:
        if not _is_heat(race.round_name):
            continue
        for e in race.entries:
            secs = _time_to_seconds(e.final_time) if e.final_time else None
            if secs is not None:
                by_event.setdefault(race.event_code, []).append((secs, e))

    # 種目内でタイム昇順に順位付け
    team_rank: dict[tuple[str, str], tuple[int, int]] = {}
    for code, items in by_event.items():
        items.sort(key=lambda x: x[0])
        total = len(items)
        for i, (_secs, e) in enumerate(items, start=1):
            e.overall_rank = i
            e.overall_total = total
            team_rank[(code, e.team)] = (i, total)

    # 予選以外の同一クルーへ (n/m) を再掲
    for race in regatta.races:
        if _is_heat(race.round_name):
            continue
        for e in race.entries:
            key = (race.event_code, e.team)
            if key in team_rank:
                e.overall_rank, e.overall_total = team_rank[key]
