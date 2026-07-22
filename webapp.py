"""NURC自動生成ツール Webアプリ(Streamlit)。

Mac・スマホを含め、ブラウザだけで使える版。ローカル起動でもクラウド公開でも動く。

ローカル起動:
    pip install -r requirements.txt streamlit
    streamlit run webapp.py
  → 同じWi-Fi内なら他端末(Mac/スマホ)から http://<起動PCのIP>:8501 で開ける。

クラウド公開(常時アクセス):
    GitHubにpushし、Streamlit Community Cloud(https://streamlit.io/cloud)で
    webapp.py を指定してデプロイ。ブックマークしたURLをスマホで開くだけ。
    ※ 会計情報を公開リポジトリに含めたくない場合は config.yaml をコミットせず、
      画面の「詳細設定」から入力するか、Streamlitのsecretsを使う。
"""

from __future__ import annotations

from datetime import date

import streamlit as st

from nurc_gen.pipeline import generate_nurc

st.set_page_config(page_title="NURC生成ツール", page_icon="🚣", layout="centered")

# 緑×白のシンプルデザイン + スマホでのタイトル折り返し対策・文字サイズ調整
_GREEN = "#006E4F"
st.markdown(
    f"""
    <style>
      /* 全体を少しコンパクトに */
      html, body, [data-testid="stAppViewContainer"] {{ font-size: 15px; }}
      .block-container {{ max-width: 720px; padding-top: 2.2rem; }}

      /* タイトル: 緑・小さめ・日本語を不自然な位置で改行しない */
      h1 {{
        color: {_GREEN};
        font-size: 1.55rem !important;
        line-height: 1.3;
        word-break: keep-all;
        overflow-wrap: anywhere;
      }}
      @media (max-width: 480px) {{
        h1 {{ font-size: 1.25rem !important; }}
      }}

      /* 見出し・展開ヘッダを緑に */
      h2, h3 {{ color: {_GREEN}; }}
      summary p {{ color: {_GREEN}; font-weight: 600; }}

      /* プライマリボタンを緑基調に(theme primaryColorの補強) */
      .stButton > button[kind="primary"],
      .stDownloadButton > button {{
        background-color: {_GREEN};
        border-color: {_GREEN};
        color: #FFFFFF;
      }}
      .stButton > button[kind="primary"]:hover,
      .stDownloadButton > button:hover {{
        background-color: #005A41;
        border-color: #005A41;
        color: #FFFFFF;
      }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🚣 NURC生成ツール")
st.caption("大会HPのURLから名古屋大学の結果報告文(NURC)を自動生成します。")

url = st.text_input(
    "大会結果ページのURL",
    placeholder="https://karal.jp/news_flash/result.htm",
)

use_date = st.checkbox("対象日を指定する（オフ=掲載済みの最新日を自動判定）", value=False)
if use_date:
    picked = st.date_input("対象日", value=date.today(), format="YYYY-MM-DD")
else:
    picked = None

with st.expander("詳細設定（会計担当・配信URL / 任意）"):
    st.caption("記入しない項目は既定値が使われます。")
    acc_title = st.text_input("会計担当 学年")
    acc_kanji = st.text_input("会計担当 氏名")
    acc_kana = st.text_input("会計担当 氏名カナ")
    acc_email = st.text_input("会計担当 メール")
    stream_nurc = st.text_input("配信URL（名大漕艇部）")
    stream_off = st.text_input("配信URL（大会公式）")

submitted = st.button("NURC生成", type="primary")

if submitted:
    if not url.strip():
        st.warning("大会結果ページのURLを入力してください。")
        st.stop()

    target = picked
    overrides = {
        "accountant_title": acc_title,
        "accountant_kanji": acc_kanji,
        "accountant_kana": acc_kana,
        "accountant_email": acc_email,
        "stream_url_nurc": stream_nurc,
        "stream_url_official": stream_off,
    }

    with st.spinner("ページを取得・解析しています…（数十秒かかることがあります）"):
        try:
            result = generate_nurc(url.strip(), target, config_overrides=overrides)
        except ValueError as exc:
            st.error(str(exc))
            st.stop()
        except Exception as exc:  # noqa: BLE001
            st.error(f"生成中にエラーが発生しました: {exc}")
            st.stop()

    site_ja = "関西選手権" if result.site == "karal" else "インカレ"
    day = result.resolved_target
    day_str = f"{day:%Y-%m-%d}" if day else "（日付不明）"
    auto = "" if result.target_specified else "（自動判定）"

    if result.nagoya_races == 0:
        st.warning(
            f"{site_ja}として解析しましたが、名古屋大学の出場が見つかりませんでした。"
            "URLをご確認ください。"
        )
    elif result.day_result_races == 0:
        st.warning(
            f"{site_ja}: 対象日 {day_str}{auto} には名古屋大学の結果がありません"
            f"（大会全体では{result.nagoya_races}件出場）。対象日をご確認ください。"
        )
    else:
        st.success(
            f"{site_ja} 対象日 {day_str}{auto}: 名古屋大学の結果"
            f"{result.day_result_races}件を反映しました。"
        )

    st.caption("下のテキスト右上のコピーアイコンで全文をコピーできます。")
    st.code(result.text, language=None)

    st.download_button(
        "テキストで保存",
        data=result.text.encode("utf-8"),
        file_name=f"NURC_{result.site}_{(day or date.today()):%Y%m%d}.txt",
        mime="text/plain",
    )
