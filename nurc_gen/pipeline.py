"""URL入力からNURC本文までの一連の処理(GUI/CLI共通)。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .generate import _resolve_target_date, generate, load_config
from .resources import external_config_path
from .sites import get_adapter


@dataclass
class Result:
    text: str                 # 生成されたNURC本文
    site: str                 # "karal" / "jara"
    total_races: int          # 検出した全レース数
    nagoya_races: int         # 大会全体での名古屋大学の出場レース数
    day_result_races: int     # 今回のNURC本文に載せた「対象日」の名大結果レース数
    resolved_target: date | None  # 実際に対象とした日(未指定時は自動判定結果)
    target_specified: bool    # ユーザーが日付を明示したか


def generate_nurc(url: str, target: date | None = None,
                  config_path: str | None = None,
                  config_overrides: dict | None = None) -> Result:
    """大会URLからNURCを生成して返す。例外はそのまま呼び出し側へ送出。

    config_overrides を渡すと、設定ファイルの値の上に(空文字は無視して)上書きする。
    Webアプリ等で会計担当名・配信URLを画面から指定する用途に使う。
    """
    cfg = load_config(config_path or external_config_path())
    if config_overrides:
        for k, v in config_overrides.items():
            if v:  # 空欄は既定値/設定ファイルの値を残す
                cfg[k] = v
    adapter = get_adapter(url)               # 未対応ドメインは ValueError
    regatta = adapter.parse(url)
    nagoya = sum(1 for r in regatta.races if r.has_nagoya)
    resolved = _resolve_target_date(regatta, target)
    day_results = sum(
        1 for r in regatta.races
        if r.date == resolved and r.has_nagoya and r.has_result
    )
    text = generate(regatta, target, cfg)
    return Result(
        text=text,
        site=regatta.site,
        total_races=len(regatta.races),
        nagoya_races=nagoya,
        day_result_races=day_results,
        resolved_target=resolved,
        target_specified=target is not None,
    )
