"""抽出データの正規化モデル。

サイト(karal / jara)ごとにHTML構造は異なるが、パース結果はこの
共通モデルに落とし込み、以降のランキング算出・本文生成はサイト非依存で扱う。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

NAGOYA = "名古屋大学"


def _extract_surname(athlete: Optional[str]) -> Optional[str]:
    """氏名から姓(スペース区切りの先頭)を取り出す。'余井 快翼' -> '余井'。"""
    if not athlete:
        return None
    # 全角/半角スペースで分割
    parts = re.split(r"[\s　]+", athlete.strip())
    return parts[0] if parts and parts[0] else None


@dataclass
class Entry:
    """1レース中の1クルー(1レーン)の記録。"""

    bno: str = ""                      # ボート番号 / レーン番号
    crew_raw: str = ""                 # ソースのクルー表記そのまま
    team: str = ""                     # 大学・団体名 (例: 名古屋大学A)
    athlete: Optional[str] = None      # 個人種目の選手氏名 (例: 余井 快翼)
    times: list[str] = field(default_factory=list)  # 通過タイム(距離順)
    splits: dict[str, str] = field(default_factory=dict)  # 距離ラベル->タイム (例 {"1000m":"4:12.01"})
    rank: Optional[int] = None         # 組内着順
    qualify_raw: str = ""              # 進出情報の生テキスト (例: →準決勝)
    status: str = ""                   # DNS / 除外 / DSQ など特殊状態
    overall_rank: Optional[int] = None  # (n/m) の n。ranking.py で後付け
    overall_total: Optional[int] = None  # (n/m) の m。ranking.py で後付け

    @property
    def surname(self) -> Optional[str]:
        return _extract_surname(self.athlete)

    @property
    def team_suffix(self) -> str:
        """団体名末尾の A/B/C を返す。'名古屋大学B' -> 'B'、無ければ ''。"""
        m = re.search(r"([A-ZＡ-Ｚ])\s*$", self.team)
        if not m:
            return ""
        # 全角英字を半角へ
        ch = m.group(1)
        return chr(ord(ch) - 0xFEE0) if "Ａ" <= ch <= "Ｚ" else ch

    @property
    def team_base(self) -> str:
        """末尾の A/B/C を除いた団体名。'名古屋大学B' -> '名古屋大学'。"""
        return re.sub(r"[A-ZＡ-Ｚ]\s*$", "", self.team).strip()

    @property
    def is_nagoya(self) -> bool:
        # 「名古屋工業大学」を誤マッチさせない
        base = self.team_base
        return base == NAGOYA or self.team.startswith(NAGOYA + "A") or \
            self.team.startswith(NAGOYA + "B") or self.team.startswith(NAGOYA + "C") \
            or self.team == NAGOYA

    @staticmethod
    def _dist(label: str) -> int:
        m = re.match(r"(\d+)m", label)
        return int(m.group(1)) if m else -1

    @property
    def final_time(self) -> Optional[str]:
        """最終地点(2000m等)のタイム。splits優先、無ければtimesの末尾有効値。"""
        valid = {k: v for k, v in self.splits.items() if v and v.strip()}
        if valid:
            far = max(valid, key=self._dist)
            return valid[far].strip()
        for t in reversed(self.times):
            if t and t.strip() and t.strip() not in ("&nbsp;", ""):
                return t.strip()
        return None

    def split(self, label: str) -> Optional[str]:
        """指定距離ラベルのタイム。無ければ None。"""
        v = self.splits.get(label)
        return v.strip() if v and v.strip() else None

    @property
    def has_result(self) -> bool:
        """タイムが1件でもあれば実施済みとみなす。"""
        return self.final_time is not None or bool(self.status)


@dataclass
class Race:
    """1レース(1組)。"""

    no: str = ""                       # レース番号 (例: 4)
    date: Optional[date] = None        # レース実施日
    time: str = ""                     # 発艇時刻 (例: 9:00)
    event_code: str = ""               # 種目コード (例: m1x)
    event_name: str = ""               # 種目和名 (例: 男子シングルスカル)
    round_name: str = ""               # ラウンド (予選/準決勝/CR/Ｂ決勝/Ａ決勝/Heat/Repechage 等)
    group: str = ""                    # 組 (例: 4組)。決勝など無い場合は空
    progression: str = ""              # 「4上り」等の進出条件メモ
    entries: list[Entry] = field(default_factory=list)

    @property
    def has_result(self) -> bool:
        return any(e.has_result for e in self.entries)

    @property
    def nagoya_entries(self) -> list[Entry]:
        return [e for e in self.entries if e.is_nagoya]

    @property
    def has_nagoya(self) -> bool:
        return bool(self.nagoya_entries)

    def label(self) -> str:
        """'予選4組' のようなラウンド+組の表示。"""
        return f"{self.round_name}{self.group}".strip()


@dataclass
class Regatta:
    """大会全体。"""

    name: str = ""                     # 大会名
    venue: str = ""                    # 会場
    races: list[Race] = field(default_factory=list)
    site: str = ""                     # "karal" / "jara"
