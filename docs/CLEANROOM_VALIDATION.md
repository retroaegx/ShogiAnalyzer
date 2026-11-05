# Python未導入環境での検証（2026-11-05）

## 初回ダウンロードのHTTPS修正と再検証

ネット接続ありの初回設定用Sandboxで、cloudflared取得時に`CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`が発生した。旧Python処理では、初期状態のWindows証明書ストアをOpenSSLへ読み込んだだけでは配布先の証明書チェーンを検証できなかった。ネットワークを無効にした回帰テストでは、この初回ダウンロードを検証できていなかった。

Windows/macOSではtruststoreを使用してOSの証明書検証・チェーン構築を利用し、LinuxではOSのCAを優先し、CAがない最小環境だけcertifiを使用するように修正した。インストーラーの取得と更新確認で共通のHTTPS処理を使用する。証明書検証とホスト名検証は有効のままで、OSへ手作業で証明書を追加する修正や検証の無効化は行わない。

同じWindows Sandboxで、旧処理はGitHubのリリース取得先・storage.yaneu.com・Google Driveの3か所ですべて証明書エラーを再現。修正版のネイティブ実行ファイルでは、リダイレクト先も含めて3か所すべてのHTTPS接続が成功した。実際のダウンロード関数で公開Pythonライセンス文書13,936 bytesを取得し、更新確認のAPI呼び出しも成功。自己署名証明書とホスト名不一致の証明書は拒否した。エンジン・評価関数の本体を取得したという意味ではなく、これらの配布先にはHEADで接続している。

修正版ZIPは31,204,034 bytes、SHA256は`2e29988b751b2c43a8bf12ab26be02baef4d05b6e6679418c3c1c32905e3f1c8`、ビルド元は`3a6b0b64d5125307257f276336ea849c7d192b16`。Sandboxを閉じずに、デスクトップのShogiAnalyzerをこの版へ更新した。.envのハッシュが更新前後で同一であることを確認し、選択済みのパスワード保護を含む設定を保持した。

証跡はwindows-first-run-resultsのtls-probe.json（旧処理とOS検証の比較）、tls-fixed-https.json、tls-update-applied.json、tls-applied-https.json。最初の診断には一時的な公開アセットURLが含まれるため、共有時はクエリー文字列を除くこと。恒久的なtools/probe_https.pyは最終ホスト名だけを記録する。

Pythonのテスト31件には、ローカルHTTPSサーバーを使った正常接続・未知のCAの拒否・信頼したCAでもホスト名が異なる場合の拒否を含む。テスト証明書は実運用には使わず、OSの信頼ストアにも追加しない。[各OSビルドと新規UbuntuでのHTTPS検証の成功](https://github.com/retroaegx/ShogiAnalyzer/actions/runs/41990811136)。Ubuntuのオフライン回帰テストとは別に、OSへPythonやCAパッケージを追加せず、ネット接続ありの新規コンテナーでもHTTPSの実取得を検証した。

## VC++ DLL同梱後の再検証

Windows Sandboxを新規に作成し、Python/PHP/Nodeのコマンド・Pythonのインストール登録・System32のvcruntime140.dllとvcruntime140_1.dllがないことを確認した。同梱版の展開後、OSへ何もインストールせずにEXE直接実行とStart.batの自己検査が成功した。通常ランチャーでの起動、HTTP配信、USIテスト相手との解析通信、103手棋譜の読み込み、再接続時の操作同期、保存、終了、再起動も成功した。終了後にも同じ初期状態のチェックを行い、PythonやVC++ランタイムがOSへ追加されていないことを確認した。

環境はWindows 11 Enterprise build 26100、ネットワーク・クリップボード無効。入力フォルダーは読み取り専用で、VC++ランタイムのインストーラーは渡していない。再現スクリプトはtools/windows_cleanroom.ps1、通常操作の共通プローブはtools/cleanroom_probe.py。

検証ZIPは`ShogiAnalyzer-v1.1.10-windows-amd64.zip`、31,173,268 bytes、SHA256は`05ca0ed79dc4ab0bcad148374b3c48508a9c616130b583e70a2814fbaa393878`。ビルド元は`0217a3801fa504d88c78b394232213114d5d6450`。従来のZIPとの差は204,037 bytes（約0.20 MB）で、ランタイムDLL2個とライセンス文書を含む。

DLLはVisual Studio 2022 Build ToolsのC++ REDISTフォルダーから取得したMicrosoft純正のvcruntime140.dllとvcruntime140_1.dll、バージョン14.44.35211.0。どちらもMicrosoftの電子署名がValidであることを確認して改変せず同梱した。原文と全文テキストのMicrosoft条件、再配布条件の参照文書、Windows版Pythonの追加条件、ファイルごとの出所・ハッシュを配布物に含めている。詳細はdocs/THIRD_PARTY.mdと配布物のWINDOWS_RUNTIME.jsonを参照。

ローカル証跡は`E:\work\ShogiAnalyzer_cleanroom\20261105\windows-bundled-results`に保存。baseline.jsonとafter.jsonがOS側の未導入状態、summary.jsonとprobe.jsonが成功結果。確認用Sandboxは検証後も停止せず残した。中の`C:\ShogiTest\ShogiAnalyzer\Start.bat`から通常起動できるよう、検証用の保存棋譜とUSIテスト相手の設定を用意している。解析相手はRegression engineというテスト用プログラムであり、実際の将棋エンジンではない。

この検証済み設定は通常の初回導入を確認する用途には適さないため、別途ネット接続を有効にした新規Sandboxを用意し、デスクトップのShogiAnalyzerフォルダーへ同じZIPを展開した。展開後の.env・engine_config.jsonが未作成であることと、ネット接続が可能なことを確認した。証跡はwindows-first-run-results/first-run-ready.json。パスワードの選択やエンジン・評価関数の取得は利用者自身が通常の初回手順で行う。今後のハーネスは、回帰テスト用の設定を展開した配布物へコピーせず、プローブ専用のapplication-dataだけに保持する。

## 旧構成（VC++ランタイム非同梱）の検証記録

以下は修正前の記録。現行のDLL同梱版は追加インストール不要であり、下記の旧構成の前提とは異なる。

対象はPR #37のネイティブ配布版（VERSIONは1.1.10のまま）。Windows Sandboxと新規Ubuntuコンテナーで、OS側にPython・PHPを入れずに検証した。

## 結果

| 環境 | 初期状態 | 結果 |
| --- | --- | --- |
| Windows 11 Enterprise x64、build 26100、Windows Sandbox | Python/PHP/Nodeなし。VC++ランタイムもなし | EXE直接実行は依存DLL不足で起動不可。Start.batは不足を検出して公式導入案内を開き、終了コード2で停止 |
| 同じWindows Sandbox、Microsoft公式VC++ x64ランタイム導入後 | Python/PHP/Nodeは引き続き未導入 | 通常起動と下記の操作テストが成功 |
| Ubuntu 22.04.5 x64の新規コンテナー、glibc 2.35 | Python/PHP/Nodeなし | 追加パッケージのインストールなしで、通常起動と下記の操作テストが成功 |

Windowsで「OSに追加ソフトが一切不要」とは言えない。Python・PHPは不要だが、Microsoft Visual C++ x64 Runtimeが必要。アプリのZIPにはMicrosoftランタイムを含めていない。

## 検証した操作

`tools/cleanroom_probe.py`を配布EXE自身の`--engine-python`で実行した。テスト用PythonをOSへインストールしていない。

- 同梱ライブラリー、SQLite、Pillowの日本語フォント描画、7z圧縮・展開。
- 通常ランチャーからの起動と、HTML・JavaScript・CSS・盤駒画像等のHTTP取得。
- WebSocket接続、新規棋譜、一手の着手、同一操作の再送でも二重着手しないこと。
- 別プロセスのUSIテスト相手との解析開始・評価値受信・解析停止。
- 提供された103手棋譜の読み込み、87手目から再接続して88手目へ同期、成銀の重複した「成」の正規化。
- 別棋譜へ切り替えた後に古い操作を拒否すること。
- 棋譜保存、終了時の子プロセス停止、通常ランチャーの再起動とSQLiteからの棋譜復元。
- `.venv`やエンジンを新たに作成・ダウンロードしていないこと。

## 隔離条件と証跡

Windows Sandboxはネットワーク・クリップボードを無効にし、入力ファイルだけを読み取り専用でマウントした。初期状態でPython関連コマンドとインストール登録がないこと、およびVC++ DLLがないことを記録した。

Windowsで検証したZIPは`ShogiAnalyzer-v1.1.10-windows-amd64.zip`、30,969,231 bytes、SHA256は`d2e473f8230af11f97a5972a1191d310d859acadfc410238650392ba96bbda21`。ビルド元は`c37c165893f78eff36378a5ac1f901233fc63d12`。以降の変更は検証スクリプトとCI設定。

VC++ランタイムはMicrosoft公式の`https://aka.ms/vs/17/release/vc_redist.x64.exe`から取得し、署名の発行者がMicrosoft Corporation、署名状態がValidであることを確認した。バージョン14.44.35211.0、SHA256は`cc0ff0eb1dc3f5188ae6300faef32bf5beeba4bdd6e8e445a9184072096b713b`。Sandbox内だけに導入し、インストーラーログの成功・終了コード0を確認した。

Windowsのテストは通常のコンソールを持つプロセスで実行した。コンソールなしのリモート実行ではテスト側のCTRL_BREAK送信が失敗したため、その実行方法は終了テストに使っていない。

LinuxはGitHub Actions上で公式`ubuntu:22.04`イメージを新規起動した。ネットワーク無効、ルート読み取り専用、実行用の一時ファイルシステムだけ`exec`を許可。apt/pipを実行せず、前後のパッケージ・コマンドを記録した。イメージは`ubuntu@sha256:076e7bf82319619f28dd0aa9c02ab34b055ad37100395b4f49a2ffba04fb5e11`。

[GitHub Actionsの成功した検証](https://github.com/retroaegx/ShogiAnalyzer/actions/runs/41983083246)にLinuxのレポートと各OSの配布物を保存している。`ShogiAnalyzer-clean-linux-report`に`baseline.txt`、`after.txt`、`probe.json`、`application.log`、`image-digest.json`がある。

ローカルの証跡は`E:\work\ShogiAnalyzer_cleanroom\20261105\windows-results`と`linux-results`に保存。Windowsの最終結果は`probe.json`、初期状態は`baseline.json`、ランタイム導入後は`after-runtime.json`。初回の検証手順の失敗ログも残しており、最終結果と区別する。

## 今回の確認範囲

ブラウザー上の見た目やクリック操作は未確認。Windows Sandboxの画面操作が操作ツール側で許可されなかったため、HTTP・WebSocket経由で確認した。

USI解析通信には自作のテスト相手を使った。実際の将棋エンジン・評価関数の初回取得、各配布元の利用規約画面、Linuxでのエンジンのソースビルド、Cloudflare経由の外部接続は、この隔離テストの対象外。実エンジンの棋力や探索結果を確認したという意味ではない。

macOS Intel/Apple Siliconのネイティブビルドと既存の自動テストは成功したが、macOSの初期OS環境では今回検証していない。Linuxも上記Ubuntuユーザーランドでの結果であり、全ディストリビューションでの動作保証ではない。

本番アプリの更新・再起動は行っていない。検証調査中に誤って追加されたLXDは削除済み。本番サービスは引き続きactive、MainPID=2920280であることを確認した。
