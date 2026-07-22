"""全日本大学ローイング選手権(インカレ, jara.or.jp) アダプタ。

構造:
- トップ `2025intercollege.html`: `2025intercollege_{code}.html` への種目別リンク。
- 種目別ページ: 1レース = `div.panel.race-result`。
  `panel-heading` に "Race No: N"、`race-info` に発艇時刻 "MM/DD HH:MM" と組別
  (例 "Heat1組" / "Repechage1組" / "Quarter finals1組" / "Final A")。
  本体テーブルは Rank / クルー(大学名) / 500m..2000m / BNo. / Qualify。
  各クルー行の後に tr.collapse でシート順・選手名のサブテーブルが続く(本ツールは無視)。
- 文字コードは UTF-8。
"""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..models import Entry, Race, Regatta

SITE = "jara"

# 種目コード -> インカレスタイルの和名 (「舵手付き」表記)
EVENT_NAMES = {
    "m8+": "男子エイト",
    "m4+": "男子舵手付きフォア",
    "m4-": "男子舵手なしフォア",
    "m4x": "男子クォドルプル",
    "m2x": "男子ダブルスカル",
    "m2-": "男子舵手なしペア",
    "m1x": "男子シングルスカル",
    "w8+": "女子エイト",
    "w4+": "女子舵手付きフォア",
    "w4x": "女子クォドルプル",
    "w2x": "女子ダブルスカル",
    "w2-": "女子舵手なしペア",
    "w1x": "女子シングルスカル",
    "jom8+": "男子ジュニアエイト",
    "jow8+": "女子ジュニアエイト",
    "oxm8+": "男子オープンエイト",
}

# 種目リンクだが結果ページではないもの
_NON_EVENT = {"tt", "et", "point", "bulletin"}

# ラウンド名(英語) -> 敗者戦/決勝の日本語(サマリー用)
ROUND_JA = {
    "Heat": "予選",
    "Repechage": "敗者復活戦",
    "Quarter finals": "準々決勝",
    "Quarterfinals": "準々決勝",
    "SemiFinal": "準決勝",
    "Semi-Final": "準決勝",
    "Semifinal": "準決勝",
    "Final A": "A決勝",
    "Final B": "B決勝",
    "Final C": "C決勝",
    "Final D": "D決勝",
}

_YEAR_RE = re.compile(r"/(\d{4})/")


def _fetch(url: str) -> str:
    resp = requests.get(url, timeout=30)
    resp.encoding = "utf-8"
    return resp.text


def _event_code_from_href(href: str) -> str | None:
    m = re.search(r"intercollege_([a-z0-9+\-]+)\.html", href, re.I)
    return m.group(1).lower() if m else None


def _split_round_group(kumibetu: str) -> tuple[str, str]:
    """'Heat1組' -> ('Heat','1組')、'Final A' -> ('Final A','')。"""
    kumibetu = kumibetu.strip()
    m = re.search(r"(\d+組)\s*$", kumibetu)
    if m:
        group = m.group(1)
        round_name = kumibetu[: m.start()].strip()
        return round_name, group
    return kumibetu, ""


def _parse_race_date(hassou: str, year: int) -> tuple[date | None, str]:
    """'09/03 09:10' -> (date(year,9,3), '9:10')。"""
    m = re.search(r"(\d{1,2})/(\d{1,2})\s+(\d{1,2}:\d{2})", hassou)
    if not m:
        return None, ""
    d = date(year, int(m.group(1)), int(m.group(2)))
    # 時刻は先頭ゼロを除いて 9:10 形式に
    hhmm = re.sub(r"^0", "", m.group(3))
    return d, hhmm


def _parse_event_page(html: str, event_code: str, event_name: str, year: int) -> list[Race]:
    soup = BeautifulSoup(html, "html.parser")
    races: list[Race] = []
    for panel in soup.select("div.panel.race-result"):
        heading = panel.select_one(".panel-heading")
        no = ""
        if heading:
            hm = re.search(r"Race No:\s*(\d+)", heading.get_text(" ", strip=True))
            no = hm.group(1) if hm else ""

        infos = [c.get_text(" ", strip=True) for c in panel.select(".race-info div")]
        hassou = next((t for t in infos if "発艇" in t), "")
        kumibetu = next((t for t in infos if "組別" in t), "")
        rdate, rtime = _parse_race_date(hassou, year)
        round_name, group = _split_round_group(re.sub(r".*[:：]", "", kumibetu).strip())

        race = Race(
            no=no, date=rdate, time=rtime,
            event_code=event_code, event_name=event_name,
            round_name=round_name, group=group,
        )

        table = panel.select_one(".table-responsive table")
        if not table:
            continue
        for tr in table.find_all("tr", recursive=False):
            classes = tr.get("class") or []
            if "active" in classes or "collapse" in classes:
                continue
            tds = tr.find_all("td", recursive=False)
            if len(tds) < 8:
                continue
            rank_txt = tds[0].get_text(" ", strip=True)
            crew = tds[1].get_text(" ", strip=True).strip()
            times = [tds[i].get_text(" ", strip=True) for i in range(2, 6)]
            splits = {lbl: t for lbl, t in
                      zip(("500m", "1000m", "1500m", "2000m"), times) if t}
            bno = tds[6].get_text(" ", strip=True)
            qualify = tds[7].get_text(" ", strip=True)
            if not crew:
                continue

            status = ""
            if re.search(r"除外|DNS|DSQ|DNF|失格|棄権", qualify):
                status = qualify.strip()
                qualify = ""

            entry = Entry(
                bno=bno,
                crew_raw=crew,
                team=crew,          # インカレは団体名のみ(選手名はサブテーブル)
                athlete=None,
                times=[t for t in times if t],
                splits=splits,
                rank=int(rank_txt) if rank_txt.isdigit() else None,
                qualify_raw=qualify.strip(),
                status=status,
            )
            race.entries.append(entry)
        if race.entries and race.no:
            races.append(race)
    return races


def normalize_url(url: str) -> str:
    """種目ページ(..._m4+.html 等)を直接渡された場合は大会トップに補正する。"""
    m = re.match(r"(.*intercollege)_[A-Za-z0-9+\-]+\.html(?:[?#].*)?$", url)
    return m.group(1) + ".html" if m else url


def parse(url: str) -> Regatta:
    url = normalize_url(url)
    top_html = _fetch(url)
    soup = BeautifulSoup(top_html, "html.parser")

    title = soup.title.get_text(strip=True) if soup.title else ""
    name_m = re.search(r"(第\d+回[^|｜]*大会)", title)
    name = name_m.group(1).strip() if name_m else title
    ym = _YEAR_RE.search(url)
    year = int(ym.group(1)) if ym else date.today().year

    body_text = soup.get_text("\n", strip=True)
    venue_m = re.search(r"(戸田[^\n、]*ボートコース|[^\n、]*ボートコース)", body_text)
    venue = venue_m.group(1).strip() if venue_m else ""

    event_pages: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        code = _event_code_from_href(a["href"])
        if code and code in EVENT_NAMES and code not in _NON_EVENT:
            event_pages.setdefault(code, urljoin(url, a["href"].split("#")[0]))

    regatta = Regatta(name=name, venue=venue, site=SITE)
    for code, page_url in event_pages.items():
        try:
            html = _fetch(page_url)
            regatta.races.extend(
                _parse_event_page(html, code, EVENT_NAMES[code], year)
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[警告] 種目 {code} の取得/解析に失敗: {exc}")
    return regatta
