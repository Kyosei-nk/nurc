# NURC自動生成ツール

大会HPのURLから名古屋大学の出場レース・結果を抽出し、定型フォーマットの
結果報告文（NURC）を自動生成するツール。大会途中（1日目終了時など）の
速報出力にも対応する。

## マネージャー向け（配布された .exe を使う場合）

Pythonのインストールは不要です。

1. `NURC生成ツール.exe` をダブルクリックで起動。
2. 「大会結果ページのURL」に大会HPのURLを貼り付け（例は下記「対応サイト」）。
3. 「対象日」は空欄でOK（掲載済みの最新日を自動判定）。1日目終了時の速報など
   特定の日で出したいときだけ `2026-07-04` の形式で入力。
4. **「NURC生成」** を押すと本文が表示される。
5. **「全文コピー」** でクリップボードにコピー → メールに貼り付けて送信。
   （**「テキスト保存」** で .txt 保存も可能）

会計担当者名や配信URLを変更したいときは、exe と同じフォルダに `config.yaml` を
置いて編集してください（無ければ内蔵の既定値が使われます）。

## Mac・スマホで使う（Webアプリ版）

`.exe` はWindows専用です。Mac・iPad・スマホでも使いたい場合は、ブラウザで動く
Webアプリ版（`webapp.py`）を使います。会計担当名・配信URLは画面の「詳細設定」から
入力できます。

**方法A: 1台のPCで起動し、同じWi-Fiの端末から開く（無料・準備が最小）**

```bash
pip install -r requirements.txt -r requirements-web.txt
streamlit run webapp.py
```

起動時に表示される `Network URL`（例 `http://10.0.0.5:8501`）を、同じWi-Fiに
つないだMac・スマホのブラウザで開けば使えます（起動PCは点けたままにする）。

**方法B: クラウドに公開して、どこからでもスマホで開く（常時アクセス）**

無料の [Streamlit Community Cloud](https://share.streamlit.io) にデプロイします。
このリポジトリには必要な `webapp.py` と `requirements.txt`（requests・beautifulsoup4）が
既に入っているので、追加設定はほぼ不要です。

1. リポジトリをGitHubにpushする（`webapp.py` と `requirements.txt` がリポジトリ直下に
   あることを確認）。
2. ブラウザで **https://share.streamlit.io** を開き、GitHubアカウントでサインイン。
3. 右上の **「Create app」**（または「New app」）→ **「Deploy a public app from GitHub」** を選ぶ。
4. 入力欄を次のように設定：
   - **Repository**: 自分のリポジトリ（例 `yourname/NURC_auto_mail`）
   - **Branch**: `main`
   - **Main file path**: `webapp.py`
5. **「Deploy」** を押す。数分でビルドが終わり、`https://<好きな名前>.streamlit.app` の
   URLが発行される。これをスマホでブックマークすれば、インストール不要で常時使える。

補足：
- Streamlit本体はクラウド側に最初から入っているため、`requirements.txt` に streamlit を
  書く必要はない（requests・beautifulsoup4 だけでよい）。
- 無料アプリはしばらくアクセスが無いとスリープし、次に開くと30秒ほどで復帰する。
- 会計情報（`config.yaml` の口座・氏名）を公開したくない場合は、`config.yaml` を
  コミットせず（`.gitignore`済み）、画面の「詳細設定」から都度入力する。もしくは
  リポジトリを **Private** にしてデプロイする（Community Cloudは非公開リポジトリも可）。

## 対応サイト

| 大会 | ドメイン | 文体 |
|------|----------|------|
| 関西選手権 | `karal.jp` | 1000m/2000mタイム、`(n/m)`総合順位、【N日目のレース結果】形式 |
| インカレ（全日本大学選手権） | `jara.or.jp` | 500m/2000mタイム、「種目 → 明日の◯◯へ」サマリー形式 |

## 開発者向け: セットアップ

```bash
pip install -r requirements.txt
```

`config.yaml` に会計担当者名や配信URLを記入しておくと、フッター等に差し込まれる
（空欄なら本文中に `【…】` プレースホルダが入る）。

### .exe のビルド（マネージャーへ配布する版を作る）

Windowsで以下を実行（`build_exe.bat` をダブルクリックでも可）。PyInstallerで
`gui.py` を単一exeに固め、`templates/` と `config.yaml` を同梱する。

```bash
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller nurc.spec
```

生成物は `dist/NURC生成ツール.exe`。これ1つを共有ドライブ等に置いて配布する。

### GUIをソースから起動

```bash
python gui.py
```

### テスト（ネットワーク不要のオフライン回帰）

```bash
python tests/test_offline.py
```

## 使い方（コマンドライン）

```bash
# 結果掲載済みの最終日で自動生成（output/ に保存）
python main.py https://karal.jp/news_flash/result.htm

# 特定の日を「N日目」として速報生成（その日の結果＋翌日スケジュール）
python main.py https://karal.jp/news_flash/result.htm --date 2026-07-04
python main.py https://www.jara.or.jp/race/2025/2025intercollege.html --date 2025-09-03

# ファイル保存せず標準出力へ
python main.py <URL> --date 2025-09-04 --stdout

# 出力先を指定
python main.py <URL> --out mydraft.txt
```

生成された `.txt` を確認のうえ、メール送信は手動で行う想定（送信は本ツールの
スコープ外）。

## 仕組み

1. **抽出** (`nurc_gen/sites/`): URLのドメインでアダプタを選び、種目別結果ページを
   巡回して全レースを共通モデル（`nurc_gen/models.py`）へ正規化する。
2. **名大フィルタ**: クルー名が「名古屋大学」のレースのみ抽出（「名古屋工業大学」は除外）。
3. **順位算出** (`nurc_gen/ranking.py`): `(n/m)` はソースHTMLに無い手計算値のため、
   種目内の予選（Heat）全組を2000mタイム昇順に並べて算出する。
4. **生成** (`nurc_gen/generate.py`): サイト別スタイルで本文を組み立て、
   `templates/footer_*.txt` の定型フッターを連結する。
5. **日付フィルタ**: `--date` 指定日の結果を「本文」、翌開催日のレースを
   「翌日スケジュール（タイムなし）」として出し分ける＝途中速報に対応。

## 注意・制約

- `(n/m)` はライブページの現時点データから計算するため、過去に手作業で作られた
  NURCサンプルの数値と数点ズレることがある（大会中の記録訂正・確定タイミングの差）。
  データ値自体は取得元HTMLに忠実。
- 選手氏名に空白が無い場合（例「宮地真未」）は姓のみ抽出できず氏名全体を括弧書きする。
- 大会ごとにページ構成が変わり得るため、想定と異なるテーブルは該当レースを
  スキップして警告を出す防御的な作りになっている。
- インカレのスケジュール欄にある「→1,2,3着 Quarter-Final」等の進出条件注記は、
  進出規定を要するため自動付与しない（必要なら手動追記）。
