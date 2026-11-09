# ShogiAnalyzer v1.2.1

## 主な更新

- 棋譜一覧と評価値グラフの分岐マークを、分岐先の手から1手前の「次の手を選ぶ局面」へ移しました。マークの位置を選ぶと、その局面の分岐候補を表示できます。開始局面からの分岐も対象です。
- 更新用の`Update.bat`を復旧し、Linuxの`Update.sh`、Macの`Update.command`を追加しました。ネイティブ配布版では更新時もPython・pip・venvの別途導入が不要です。
- OS・CPUに合った最新の配布物を取得し、SHA256を照合してアプリ部分を更新します。Updateスクリプト自身も更新対象です。
- `.env`、棋譜・解析結果・パスワード等の`server/data/`、`engines/`、`tools/cloudflared/`、別途指定したデータ保存先を保持します。
- アプリ実行中の更新を防ぎ、置換や起動確認に失敗した場合は元のファイルへ戻します。更新担当の実行ファイルは一時フォルダーから動かすため、Windowsでも元のEXEと実行環境を入れ替えられます。
- 更新に使う一時フォルダーは正常終了時に削除します。復旧に必要なファイルは、中断・復旧失敗時に残します。
- READMEに各OSの更新方法と一時フォルダーの扱いを追記しました。

## ダウンロード

| 利用環境 | ファイル | 起動方法 | 更新方法 |
| --- | --- | --- | --- |
| Windows x64（Windows 10以降） | `ShogiAnalyzer-v1.2.1-windows-amd64.zip` | すべて展開して`Start.bat` | `Update.bat` |
| Linux x64（glibc 2.35以降） | `ShogiAnalyzer-v1.2.1-linux-amd64.tar.gz` | 展開して`./ShogiAnalyzer` | `./Update.sh` |
| Mac Intel | `ShogiAnalyzer-v1.2.1-macos-amd64.tar.gz` | 展開して`Start.command` | `Update.command` |
| Mac Apple Silicon | `ShogiAnalyzer-v1.2.1-macos-arm64.tar.gz` | 展開して`Start.command` | `Update.command` |
| Pythonを使うソース版 | `ShogiAnalyzer-v1.2.1.zip` | READMEのソース版手順を参照 | 既存のPython環境でUpdateを実行 |

エンジン・評価関数・cloudflaredは同梱していません。初回設定で配布元の利用条件を確認して取得します。Linuxでエンジンを自動導入する場合はmake・C++コンパイラー等が必要です。Mac版は署名・公証していません。同梱物の利用条件・対応ソースは配布物の`THIRD_PARTY.txt`とアプリ内のライセンス画面にあります。

## 旧版から今回の版への更新

更新機能が入っていない旧配布版からは、今回だけ手動で更新してください。

1. ShogiAnalyzerを終了し、既存フォルダーをバックアップします。
2. 対応する配布物全体を新しいフォルダーへ展開します。
3. 既存の`.env`、`server/data/`、`engines/`、`tools/cloudflared/`を新しいフォルダーへ移して起動します。`SHOGI_ANALYZER_HOME`で別のデータ保存先を指定している場合は、その指定を引き継ぎます。
4. 以後はアプリを終了してから、各OSのUpdateスクリプトを使えます。

ソース版をGitで導入している場合は、設定・データを保持してmainを更新し、サービスを再起動できます。

## 検証

Windows x64・Linux x64・Mac Intel・Mac Apple Siliconで、ネイティブ版のビルド、起動、更新、データ保持、ライセンス同梱を検証しています。Python未導入のUbuntuコンテナーでも起動・更新を確認しています。更新の置換試験は、取得部分をローカルのリリース素材に差し替えて実際の配布アーカイブを使用し、Updateスクリプトからの最新版問い合わせはGitHubへ接続して確認しています。
