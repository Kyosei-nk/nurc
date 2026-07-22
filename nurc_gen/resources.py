"""リソースパス解決。

通常実行ではプロジェクトルート基準、PyInstallerで凍結(.exe)された場合は
展開先(sys._MEIPASS)基準でファイルを探す。設定ファイルだけは「exeの隣」に
置いた編集可能なものを優先する(会計担当名など年度で変わるため)。
"""

from __future__ import annotations

import sys
from pathlib import Path

# nurc_gen/ の1つ上 = プロジェクトルート(ソース実行時)
_SOURCE_ROOT = Path(__file__).resolve().parent.parent


def _frozen() -> bool:
    return getattr(sys, "frozen", False)


def bundled_path(rel: str) -> Path:
    """同梱リソース(テンプレート等)の絶対パス。"""
    if _frozen():
        base = Path(getattr(sys, "_MEIPASS", _SOURCE_ROOT))
        return base / rel
    return _SOURCE_ROOT / rel


def external_config_path(filename: str = "config.yaml") -> Path:
    """ユーザーが編集する設定ファイルのパス。
    .exe実行時はexeと同じフォルダを優先し、無ければ同梱版にフォールバック。
    """
    if _frozen():
        beside_exe = Path(sys.executable).resolve().parent / filename
        if beside_exe.exists():
            return beside_exe
        return bundled_path(filename)
    return _SOURCE_ROOT / filename
