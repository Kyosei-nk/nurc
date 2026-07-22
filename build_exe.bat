@echo off
rem NURC生成ツールを単一のexeにビルドする(Windows用)。
rem 使い方: このファイルをダブルクリック、またはコマンドプロンプトで build_exe.bat を実行。

cd /d "%~dp0"

echo [1/2] 必要なライブラリを確認・インストールします...
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
    echo.
    echo pip のインストールに失敗しました。Python が入っているかご確認ください。
    pause
    exit /b 1
)

echo.
echo [2/2] exe をビルドします...
python -m PyInstaller --noconfirm nurc.spec
if errorlevel 1 (
    echo.
    echo ビルドに失敗しました。上のメッセージをご確認ください。
    pause
    exit /b 1
)

echo.
echo 完了しました。 dist\NURC生成ツール.exe を配布してください。
echo (会計担当名や配信URLを変えたいときは、exe と同じフォルダに config.yaml を置いて編集します)
pause
