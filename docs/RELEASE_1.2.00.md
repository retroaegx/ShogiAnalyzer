# ShogiAnalyzer v1.2.00

## 主な更新

- Python・PHPの追加インストールが不要な配布版を追加しました。Windows x64、Linux x64、Mac Intel、Mac Apple Silicon向けに、それぞれの実行環境とライブラリーを同梱しています。
- 再接続中の案内は、応答がない状態が3秒以上続いたときに表示します。再接続が終わる前でも一手だけ操作でき、接続回復後に同期します。重複適用や別の棋譜への誤適用を防ぎます。
- 複数候補の一覧をコンパクトにし、グラフや棋譜欄が押し潰される表示を調整しました。盤横の縦の評価値バーを削除しました。
- HTTPSはWindows・MacでOSの証明書を使用し、LinuxもOSの証明書を優先します。LinuxでOSの証明書が使えない場合は、同梱の証明書を使います。
- 外部プロセスの日本語出力、OS・CPUに対応するエンジンの選択、認証情報の保存権限を修正しました。別サイトからの不正な初期設定・接続を拒否する処理も追加しました。
- READMEを実際の初回設定・OS別手順に合わせました。同梱物のライセンス原文と必要な対応ソースを配布物に含め、アプリ内から確認できるようにしました。

## ダウンロード

| 利用環境 | ファイル | 起動方法 |
| --- | --- | --- |
| Windows x64（Windows 10以降） | `ShogiAnalyzer-v1.2.00-windows-amd64.zip` | すべて展開して`Start.bat` |
| Linux x64（glibc 2.35以降） | `ShogiAnalyzer-v1.2.00-linux-amd64.tar.gz` | 展開して`./ShogiAnalyzer` |
| Mac Intel | `ShogiAnalyzer-v1.2.00-macos-amd64.tar.gz` | 展開して`Start.command` |
| Mac Apple Silicon | `ShogiAnalyzer-v1.2.00-macos-arm64.tar.gz` | 展開して`Start.command` |
| Pythonを使うソース版 | `ShogiAnalyzer-v1.2.00.zip` | READMEのソース版手順を参照 |

実行ファイルだけを取り出さず、フォルダー全体を展開してください。Linuxでエンジンを自動導入する場合は、従来と同様にmake・C++コンパイラー等が必要です。Ubuntuでは`sudo apt install build-essential git ca-certificates`で準備できます。Mac版は署名・公証していません。

エンジン・評価関数・cloudflaredは同梱していません。エンジンと評価関数は、初回設定で配布元の利用条件に同意してから取得します。同梱ライブラリーの条件・対応ソースは、配布物の`THIRD_PARTY.txt`とアプリ内のライセンス画面を参照してください。

## 更新方法

1. ShogiAnalyzerを停止し、既存フォルダーをバックアップします。
2. `.env`、`server/data/`、`engines/`、`tools/cloudflared/`を保持して、新しいアプリのファイルを配置します。ソース版から配布版へ移る場合は、新しいフォルダーへ展開してからこれらの設定・データをコピーします。
3. 新しいアプリを起動し、ブラウザーを再読み込みします。常駐サービスで運用している場合は、起動対象のパスも確認してください。

ソース版をGitで導入している場合は、mainを更新してサービスを再起動できます。配布物にユーザーの設定・棋譜DB・共有画像は含めていません。

## 検証範囲

Windows x64・Linux x64・Mac Intel・Mac Apple Siliconのビルド、起動・配信、HTTPS、ライセンス同梱検査と、PythonのないUbuntuコンテナーでの起動をCIで確認します。Windows/Linuxの実エンジン解析・初回設定・画面操作の点検内容は`docs/COMPREHENSIVE_AUDIT.md`を参照してください。Macの初期OS環境での画面操作は未検証です。
