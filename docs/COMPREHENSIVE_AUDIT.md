# 総点検結果（2026-11-05）

対象: codex/reconnect-portable-runtime、VERSION 1.1.10。Windows x64 / Linux x64。本番・main・正式リリースは変更しない。

## 確認結果

「HTTP/API」「実エンジン」「画面操作」を区別した。Windows Sandboxの利用者データと検証用データを混ぜず、Sandboxは閉じていない。

| 項目 | Windows | Linux | 証跡・条件 |
| --- | --- | --- | --- |
| Python/PHP/pip/venvの追加導入なしで起動 | Sandboxで確認 | Ubuntu22.04の新規コンテナーで確認 | 今回の最終CIでも再検査済み |
| VC++ DLL・署名・再配布条件 | DLL2個の同梱・署名・原文・ハッシュ検査 | 対象外 | 利用者によるVC++導入は不要。配布者にはVSの再配布権が必要 |
| HTTPS・証明書/ホスト名検証 | Sandboxで成功 | 新規Ubuntuで成功 | OS優先、LinuxでCAなしならcertifi。TLSの不正証明書拒否も自動試験 |
| 日本語出力 | 実EXEのpipeとSandboxのサーバー認証案内の文字列を確認 | 実EXEのpipeをCI確認 | Windowsコンソール実画面は操作制約で未確認 |
| パスワードON/OFF・設定・ログイン・ログアウト・再起動 | 配布版で自動確認 | 配布版で自動確認 | 専用の使い捨て設定・パスワードのみ使用。認証画面への自動入力はしていない |
| 実エンジン・評価関数の取得 | 利用者のSandbox導入済みデータを保持 | 正規配布元から取得・ソースビルド・評価関数展開に成功 | つようら王11mini対応版。エンジン等は配布物に混ぜない |
| 実エンジン解析・5候補・全解析 | 配布版で成功 | 配布版で成功 | 5候補のPV、4局面の全解析。両OSで5候補すべてのPV合法性も検査 |
| エンジン設定 | Threads=1 / USI_Hash=64の反映を確認 | 同左 | 保存ファイルは検証専用HOME |
| KIF/KI2/USI・不正入力拒否 | 103手で往復成功 | 同左 | 成銀表記を含む報告棋譜 |
| 着手・分岐・コメント・保存・読込・削除 | 実画面＋配布版APIで確認 | 配布版APIで確認 | 新規→2分岐→削除→保存→復元→削除 |
| 再接続の一手制限と同期 | 配布版の実画面で切断→一手戻る→2手目無効→再起動後同期 | 配布版の実画面でも切断→一手戻る→再起動後同期 | 3秒の猶予・重複防止・別棋譜への誤適用拒否は自動試験 |
| PC/スマホ表示・矢印・グラフ | 実画面で確認 | Linux配布版をホストChromeから画面確認 | Linuxデスクトップ環境そのもののブラウザー試験とは区別 |
| 共有画像 | WebP生成・デコード・共有ページ成功 | 同左 | 外部SNSへの投稿は実施しない |
| ライセンス画面 | 配布版で一覧・原文リンクを画面確認 | 配布版でHTTP確認 | Python依存・Windows DLL・元のライセンス・対応ソース案内 |
| ライセンス/対応ソース・LGPL差し替え | 原文・5件のソースSHAと実差し替えを検査 | certifi含む6件のソースSHA・LGPL5件の実差し替えを検査 | ソース実行版と配布版を区別 |
| 素材の出所 | 自作・AI生成と作者確認済み | 同左 | 2026-11-05の回答を画像README・THIRD_PARTYへ反映 |
| README | ネイティブ/ソース手順、保存先、初回設定、更新を修正 | 同左 | Python必須の説明はソース版に限定 |
| Quick Tunnel | 専用環境で外部HTTPS接続・認証に成功 | 同左 | ログイン前401→ログイン後API/PUT成功、Secure/HttpOnly Cookie。一時プロセスは停止 |
| 固定URL・LAN・PWA導入 | 未確認 | 未確認 | DNS変更・実機インストールは実施しない |
| 配布物へのユーザーデータ混入 | ZIPの全316エントリーを検査済み | tarの全エントリー・symlinkを検査済み | .env/DB/share/エンジン/評価関数/cloudflaredを除外 |

## 発見・修正した不備

- アプリ内に同梱ライブラリー一覧と原文への導線がなかった。配布物のINVENTORYを使う画面を追加。文書は許可リストだけ配信し、ユーザーデータやパストラバーサルを拒否する。
- READMEが旧Python必須構成のみ、素材READMEも旧frontend構成だった。実物に合わせた。外部Google FontsのOFL原文・著作権、PyInstallerの同梱例外の参照も追加した。
- 初回パスワード設定への別Origin POST、パスワードOFF時の別Origin WebSocketを拒否できていなかった。拒否処理と実HTTP/WSテストを追加した。直接接続した相手のIPをCFヘッダーで偽装させない。
- 対応バイナリが見つからないときに最大サイズのファイルを選び直す処理が、OS/CPU判定を打ち消していた。代替処理を削除し、非対応なら手動設定を案内する。実ダウンロード経路の回帰テストを追加した。
- 通信切断中に一手操作した後も「一手だけ操作できる」と案内が残った。既に表示した通知も同期待ちの文面へ更新する。
- 狭いスマホ表示で「候補手」「全解析」が折り返した。文字を改行させず、候補ボタン幅・間隔を調整する。

- Linux/Macの認証情報が標準umaskでは他ユーザーに読める権限で作成される点を修正。秘密を含むファイルを0600で作成し、既存ファイルも起動時に0600へ変更する。POSIX上の実ファイルとHTTP設定経路で回帰テストを追加した。

## 評価値表示について

グラフ・棋譜一覧は各局面の最も深い保存結果を使う。現在の解析欄は現在の候補手数での探索結果を使う。MultiPVを変えて浅い深さから解析し直した際に値が異なるのは、この保存方針による。これを旧局面の解析問題と混同せず、READMEに説明を追加した。報告棋譜の不正な成銀表記による旧局面検索は、既存の103手回帰試験で別に検査する。

## 確認の限界

MacはネイティブCIの範囲で、クリーンOSの画面試験はしていない。Linuxの実エンジン試験はWSL2 Ubuntu24.04・glibc2.39、配布互換性の基準試験はCI Ubuntu22.04。全ディストリビューション/全CPU/全エンジンを確認したとはしない。Linuxの固定ソースビルドはUSI名が9.80git、Windows配布元EXEはV9.90DEVと名乗る。SFNN_ka2_4096_8_64_progress8を指定してビルドし、同じ評価関数での初期化と合法なPVを確認した。

SandboxのWindowsコンソール・認証画面は操作ツールの制約で直接確認できない。許可されたブラウザーで配布版Web UIを確認し、コンソールの日本語は実プロセスの出力を検査した。この範囲を自動テスト結果で目視確認済みとは扱わない。

## ローカル証跡

`E:\work\ShogiAnalyzer_cleanroom\20261105\audit\` にOS別workflows.json・unit-tests.log・ビルドログ・PC/スマホ/同期待ち/ライセンス画面のPNGを保存した。過去のクリーン環境結果はCLEANROOM_VALIDATION.md、今回の追加分は本書で区別する。

## 最終検証の集計

- [最終CI（8fc53f0、5ジョブすべて成功）](https://github.com/retroaegx/ShogiAnalyzer/actions/runs/42023470370): Windows/Linux/Mac Intel/Mac ARMの各ネイティブビルドとクリーンUbuntu。Python38件（WindowsはPOSIX専用1件を対象外）、JavaScript16件、対応ソース・改変版差し替え・文字列出力・HTTP/WS・HTTPSを確認。
- WSLのローカル総合テストではNode.js未導入によりJSを呼ぶ1件が実行できなかった。同項目はNode.js22を用意したCI Linuxで合格。実エンジン操作プローブとPOSIX権限の追加試験はWSLでも合格している。
- CIのGitHub更新APIが403かつX-RateLimit-Remaining=0を返した場合、証明書失敗ではなくAPI制限と記録する。この場合はリリース情報の取得を確認済みには数えない。
- 最終Windows検証ZIPはコード2d0f724、31,224,227 bytes、SHA256 `b45c93157b89cd551672745c403cc9ba5c0dc7d9b3e2a9b1d560c69c43668467`。`E:\work\ShogiAnalyzer_portable_build\audit-reviewed\` に保存。最終CIとの差分はCIのレポート回収設定と本報告書のみで、アプリ本体のコードは同じ。
- 開いたままのSandboxのDesktop\ShogiAnalyzerも2d0f724へ更新。`.env`・認証・棋譜DB・エンジン計25ファイルのSHAが更新前後で一致。`audit-reviewed-console/probe.json`は成功し、最終baselineでもPython/PHP/pip/NodeとSystem32のVC++ DLL2個は未導入だった。更新時にアプリのみ停止しており、利用者はStart.batから再起動できる。Sandbox自体は閉じていない。
- 検証用の一時トンネル、ホスト/WSLのWeb検証サーバー、失敗したコンソールなしテストの残存プロセスは停止済み。本番の更新・再起動、mainへのマージ、Release作成は今回行っていない。

ライセンスの根拠は実際の配布物内のINVENTORY・各原文・対応ソースを照合した。[Pythonの組み込みソフトウェアの条件](https://docs.python.org/3/license.html)、[PyInstallerの同梱例外](https://pyinstaller.org/en/stable/license.html)、[Microsoftの再配布条件](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170)を参照し、条件を一律にMITへ置き換えていない。Windowsの再配布者に必要なVSの利用許諾など、配布者側の条件はTHIRD_PARTY.mdに明記した。
