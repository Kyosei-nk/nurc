"""関西選手権 (karal.jp) アダプタ。

構造:
- インデックス `news_flash/result.htm`: 大会名・会場テキスト + 種目×ラウンドのリンク表。
  各リンクは `result/result{code}.htm#result{番号}` で種目別ページを指す。
- 種目別ページ: 1レース = 1つの <table>。先頭行がヘッダ(№/BNo/Crew/各距離/Rank/Qualify)、
  2行目の rowspan セルにレースメタ「No / 日付 / 時刻 / ラウンド / 組 / 進出条件」。
- 文字コードは Shift_JIS。壊れたタグ(</tb> 等)を含むため html.parser で寛容にパースする。
"""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..models import Entry, Race, Regatta

SITE = "karal"
# cp932 は Shift_JIS の Windows拡張。髙(U+9AD9)等の外字を含むページを正しく復号する。
ENCODING = "cp932"

# 種目コード -> 関西選手権スタイルの和名
EVENT_NAMES = {
    "m8+": "男子エイト",
    "m4+": "男子舵手つきフォア",
    "m4-": "男子舵手なしフォア",
    "m4x": "男子クォドルプル",
    "m2x": "男子ダブルスカル",
    "m2-": "男子舵手なしペア",
    "m1x": "男子シングルスカル",
    "w4+": "女子舵手つきフォア",
    "w4x": "女子クォドルプル",
    "w2x": "女子ダブルスカル",
    "w2-": "女子舵手なしペア",
    "w1x": "女子シングルスカル",
    "msm1x": "マスターズ男子シングルスカル",
    "hmm1x": "ハンディキャップ男子シングルスカル",
    "hmm8+": "ハンディキャップ男子エイト",
    "hmm4+": "ハンディキャップ男子舵手つきフォア",
    "hmw4x+": "ハンディキャップ女子クォドルプル",
}

_ZEN2HAN = str.maketrans("０１２３４５６７８９", "0123456789")


def _fetch(url: str) -> str:
    resp = requests.get(url, timeout=30)
    resp.encoding = ENCODING
    return resp.text


def _event_code_from_href(href: str) -> str | None:
    m = re.search(r"result([a-z0-9+\-]+)\.htm", href, re.I)
    return m.group(1).lower() if m else None


def _parse_meta(cell_text: str) -> dict:
    """rowspanメタセル 'No 日付 時刻 ラウンド 組 進出条件' を分解。"""
    # <br> は改行に変換済み。空行を除去して行リスト化
    lines = [ln.strip() for ln in re.split(r"[\n\r]+", cell_text) if ln.strip()]
    meta: dict = {"no": "", "date_str": "", "time": "", "round": "", "group": "", "prog": ""}
    if lines:
        meta["no"] = lines[0]
    for ln in lines[1:]:
        if re.match(r"\d+月\d+日", ln):
            meta["date_str"] = ln
        elif re.match(r"\d{1,2}:\d{2}", ln):
            meta["time"] = ln
        elif "上り" in ln or "上がり" in ln:
            meta["prog"] = ln
        elif re.search(r"組", ln):
            meta["group"] = ln.translate(_ZEN2HAN)
        elif ln:
            # ラウンド名 (予選/準決勝/ＣＲ/Ｂ決勝/Ａ決勝/Pre 等)
            meta["round"] = _normalize_round(ln)
    return meta


def _normalize_round(text: str) -> str:
    t = text.strip()
    # 全角英字ＣＲ -> CR、全角Ａ/Ｂ -> 半角
    t = t.replace("ＣＲ", "CR").replace("Ｃ", "C").replace("Ｒ", "R")
    t = t.replace("Ａ", "A").replace("Ｂ", "B")
    # 略記の展開(サンプルの表記に合わせる)
    if t == "準決":
        return "準決勝"
    if t == "準々決":
        return "準々決勝"
    return t


def _parse_date(date_str: str, year: int) -> date | None:
    m = re.match(r"(\d+)月(\d+)日", date_str)
    if not m:
        return None
    return date(year, int(m.group(1)), int(m.group(2)))


def _split_crew(crew_raw: str) -> tuple[str, str | None]:
    """Crewセルを (team, athlete) に分解。
    個人種目 '余井 快翼(名古屋大学B)' -> team='名古屋大学B', athlete='余井 快翼'。
    団体種目 '同志社大学C' -> team='同志社大学C', athlete=None。
    """
    crew_raw = crew_raw.strip()
    m = re.match(r"^(.*?)[（(]([^（）()]+)[)）]\s*$", crew_raw)
    if m:
        athlete = m.group(1).strip()
        team = m.group(2).strip()
        return team, (athlete or None)
    return crew_raw, None


def _cell_text(td) -> str:
    txt = td.get_text(" ", strip=True)
    return "" if txt in (" ", "") else txt


def _parse_event_page(html: str, event_code: str, event_name: str, year: int) -> list[Race]:
    soup = BeautifulSoup(html, "html.parser")
    races: list[Race] = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr", recursive=False) or table.find_all("tr")
        if not rows:
            continue
        # ヘッダ行: 'Crew' を含む行を探す
        header_cells = [_cell_text(td) for td in rows[0].find_all(["td", "th"])]
        if "Crew" not in header_cells:
            continue
        # 距離列(500m/1000m/…/2000m) のインデックスを特定
        try:
            crew_idx = header_cells.index("Crew")
            rank_idx = header_cells.index("Rank")
        except ValueError:
            continue
        time_cols = [i for i in range(crew_idx + 1, rank_idx)
                     if re.match(r"\d+m", header_cells[i] or "")]

        race = Race(event_code=event_code, event_name=event_name)
        meta_parsed = False
        for tr in rows[1:]:
            tds = tr.find_all(["td", "th"])
            if not tds:
                continue
            # メタセル(rowspan)を持つ最初のデータ行
            first = tds[0]
            offset = 0
            if not meta_parsed and first.has_attr("rowspan"):
                meta = _parse_meta(first.get_text("\n", strip=True))
                race.no = meta["no"]
                race.time = meta["time"]
                race.round_name = meta["round"]
                race.group = meta["group"]
                race.progression = meta["prog"]
                race.date = _parse_date(meta["date_str"], year)
                meta_parsed = True
                offset = 1  # 実データはメタセルの次から
            # BNo が先頭に来る想定。列数が足りない行(空行)はスキップ
            cells = tds[offset:]
            if len(cells) < 2:
                continue
            # cells は [BNo, Crew, times..., Rank, Qualify] に対応
            # header の列インデックスから offset ぶんズラして参照
            def col(idx: int) -> str:
                j = idx - 1  # メタセル列(0)を除いた相対
                return _cell_text(cells[j]) if 0 <= j < len(cells) else ""

            bno = col(header_cells.index("BNo"))
            crew_raw = col(crew_idx)
            if not crew_raw:
                continue  # 空レーン
            team, athlete = _split_crew(crew_raw)
            times = [col(i) for i in time_cols]
            splits = {header_cells[i]: col(i) for i in time_cols if col(i)}
            rank_txt = col(rank_idx)
            qualify = col(rank_idx + 1) if rank_idx + 1 < len(header_cells) else ""

            status = ""
            if re.search(r"DNS|棄権|除外|DSQ|失格", qualify + rank_txt):
                status = re.sub(r"[→\s]", "", qualify) or "DNS"

            entry = Entry(
                bno=bno,
                crew_raw=crew_raw,
                team=team,
                athlete=athlete,
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
    """種目ページ(result/resultm4+.htm 等)を直接渡された場合は組合せ結果のトップに補正する。"""
    return re.sub(r"/result/result[^/]*\.htm(?:[?#].*)?$", "/result.htm", url)


def parse(url: str) -> Regatta:
    """インデックスURLから大会全体を抽出。"""
    url = normalize_url(url)
    index_html = _fetch(url)
    soup = BeautifulSoup(index_html, "html.parser")

    text = soup.get_text("\n", strip=True)
    name_m = re.search(r"(\d{4}年度[^\n]*大会)", text)
    name = name_m.group(1) if name_m else soup.title.get_text(strip=True) if soup.title else ""
    year_m = re.search(r"(\d{4})年度", text)
    year = int(year_m.group(1)) if year_m else date.today().year
    venue_m = re.search(r"於[:：]\s*([^\n]+)", text)
    venue = venue_m.group(1).strip() if venue_m else ""

    # 種目別ページURLを列挙(重複除去)
    event_pages: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        code = _event_code_from_href(a["href"])
        if code and code in EVENT_NAMES:
            event_pages.setdefault(code, urljoin(url, a["href"].split("#")[0]))

    regatta = Regatta(name=name, venue=venue, site=SITE)
    for code, page_url in event_pages.items():
        try:
            html = _fetch(page_url)
            regatta.races.extend(
                _parse_event_page(html, code, EVENT_NAMES[code], year)
            )
        except Exception as exc:  # noqa: BLE001 - 1種目の失敗で全体を止めない
            print(f"[警告] 種目 {code} の取得/解析に失敗: {exc}")
    return regatta
