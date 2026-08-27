"""(n/m) 総合順位の算出。

NURC本文に載る `(20/29)` のような表記はソースHTMLには無く、NURC作成者が
手計算していた値。サイトで規則が異なる:

- 関西(karal): m = その種目の予選(Heat)に出漕しゴールタイムを持つ全クルー数、
  n = 予選全組を通したタイム昇順順位。予選以外(CR/敗者復活/決勝)に同一クルーが
  登場する場合は予選で得た (n/m) をそのまま再掲する(サンプルのCR行が予選と同じ
  数値だったことに基づく)。
- インカレ(jara): 各ラウンド(予選/準々決勝/準決勝/各決勝)ごとに、その日そのラウンドの
  ゴールタイム昇順で順位付けする。予選の順位を後続ラウンドへ引き継がず、
  「今日のタイムの順位」を出す(準々決勝なら準々決勝全組中の順位)。
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
    """Regatta内の全Entryに overall_rank/overall_total を付与(破壊的更新)。
    サイトにより規則が異なる(モジュール冒頭のdocstring参照)。"""
    if regatta.site == "jara":
        _assign_per_round(regatta)
    else:
        _assign_heat_carried(regatta)


def _assign_per_round(regatta: Regatta) -> None:
    """インカレ: 各ラウンド(種目コード+ラウンド名)内で、ゴールタイムを持つ
    全クルーをタイム昇順に順位付け。予選の値を後続ラウンドへ引き継がない。
    タイム未確定(スケジュールのみ)のエントリは順位を付けない。"""
    groups: dict[tuple[str, str], list] = {}
    for race in regatta.races:
        for e in race.entries:
            secs = _time_to_seconds(e.final_time) if e.final_time else None
            if secs is not None:
                groups.setdefault((race.event_code, race.round_name), []).append((secs, e))
    for items in groups.values():
        items.sort(key=lambda x: x[0])
        total = len(items)
        for i, (_secs, e) in enumerate(items, start=1):
            e.overall_rank = i
            e.overall_total = total


def _assign_heat_carried(regatta: Regatta) -> None:
    """関西: 予選タイム順位を算出し、予選以外の同一クルーへは予選の (n/m) を再掲。"""
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
