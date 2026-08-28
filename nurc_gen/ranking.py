"""(n/m) 総合順位の算出。

NURC本文に載る `(20/29)` のような表記はソースHTMLには無く、NURC作成者が
手計算していた値。規則(関西・インカレ共通):

- 各ラウンド(予選/準々決勝/準決勝/CR 等)ごとに、そのラウンドに出漕し
  ゴールタイムを持つ全クルーを、ゴールタイム(最終地点)昇順で順位付けする。
- m = そのラウンドの計時クルー数、n = その中でのタイム順位。
- 予選の順位を後続ラウンドへ引き継がず「そのラウンドのタイム順位」を出す
  (準々決勝なら準々決勝全組中、準決勝なら準決勝全組中の順位)。
- 決勝(A決勝/B決勝/Final A〜H 等)には (n/m) を付けない。決勝は1レース＝
  1組しか無く、順位を出しても組内着順の焼き直しにしかならないため
  (「E決勝2着」という表記自体が順位を表している)。CRは複数組あり得るので対象。
- タイム未確定(スケジュールのみ)のエントリには順位を付けない。
"""

from __future__ import annotations

import re

from .models import Regatta


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


def is_final_round(round_name: str) -> bool:
    """A決勝/B決勝/Final A〜H など「決勝」ラウンドなら True。

    準決勝・準々決勝は決勝ではない。CR(敗者戦)も複数組あり得るため除外しない。
    """
    name = (round_name or "").strip()
    if re.match(r"final\b", name, re.I):
        return True
    return name.endswith("決勝") and "準決勝" not in name and "準々決勝" not in name


def assign_overall_ranks(regatta: Regatta) -> None:
    """Regatta内の全Entryに overall_rank/overall_total を付与(破壊的更新)。

    各ラウンド(種目コード+ラウンド名)内で、ゴールタイムを持つ全クルーを
    タイム昇順に順位付けする。同一ラウンドが複数組に分かれていても、組を
    またいでまとめて順位を出す(予選全組中・準々決勝全組中 の順位)。
    決勝ラウンドは1組しか無く組内着順と同義になるため順位を付けない。
    """
    groups: dict[tuple[str, str], list] = {}
    for race in regatta.races:
        if is_final_round(race.round_name):
            continue
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
