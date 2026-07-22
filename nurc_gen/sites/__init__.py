"""サイト別アダプタ。URLのドメインから適切なアダプタを選ぶ。"""

from __future__ import annotations

from urllib.parse import urlparse

from . import jara, karal

# ドメイン(部分一致) -> アダプタモジュール
_ADAPTERS = {
    "karal.jp": karal,
    "jara.or.jp": jara,
}


def get_adapter(url: str):
    """URLに対応するアダプタモジュールを返す。未対応なら ValueError。"""
    host = (urlparse(url).hostname or "").lower()
    for key, mod in _ADAPTERS.items():
        if key in host:
            return mod
    supported = ", ".join(_ADAPTERS)
    raise ValueError(
        f"未対応のサイトです: {host or url}\n"
        f"現在対応しているのは次のドメインです: {supported}"
    )
