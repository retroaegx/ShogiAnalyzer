# 同梱ソフトウェアと改変・差し替え

ShogiAnalyzer本体のライセンスはMITです。個々の同梱ソフトウェアには、それぞれのライセンスが適用されます。利用者自身による改変、改変したライブラリでの実行、そのデバッグのためのリバースエンジニアリングを禁止する追加条件は設けません。

Python実行環境は同梱しています。アプリ側でCPythonのソースコードは改変していません。PyInstallerでアプリと依存をまとめ、開発用モジュールを除いて配布しています。正確なPythonバージョンと実行時ライブラリのバージョンは `_internal/third_party_notices/INVENTORY.json`、収集したネイティブファイルは同フォルダーの `NATIVE_FILES.txt` に記録しています。

著作権・ライセンス・免責事項は `_internal/third_party_notices/` に保存しています。Python本体のPSFライセンスと過去のライセンス群、組み込みソフトウェアの表示、OpenSSL、Pillowが同梱するライブラリの表示も含みます。`native-library-licenses.rst` は上流の参考文書で、今回使用していないコンポーネントも掲載されています。収集した実物はINVENTORY.jsonとNATIVE_FILES.txtを参照してください。Pillowを通じてFreeTypeを利用しています。関連部分の著作権はThe FreeType Projectに帰属します（https://freetype.org/）。

## HTTPSの証明書検証

HTTPSの証明書検証には、Windows/macOSではtruststore（MIT）を通じてOSの証明書ストアを使用します。LinuxでOS側にCA証明書がない場合はcertifiのMozilla CA証明書集（MPL-2.0）を使用します。証明書の改変や検証無効化は行いません。truststoreとcertifiのライセンス・著作権表示を同梱し、Linux版にはcertifiの同じ版のソース配布物もthird_party_sourcesへ保存します。MPLの対象はcertifiのファイルで、ShogiAnalyzer本体のMITライセンスを変更しません。

## LGPLの展開ライブラリ

py7zr、pybcj（import名bcj）、inflate64、multivolumefile、pyppmdは、それぞれのライセンスに基づいて配布しています。これらのライブラリのソースコード自体は改変していません。PyInstallerの配置方法を変更し、PythonモジュールをPYZに埋め込まず、外部ファイルにしています。

対応するバージョンの完全なソース配布物は、同じ配布物の `third_party_sources/` にあります。ファイル名、配布元、SHA-256は `third_party_sources/SOURCES.json` に記録しています。ソース配布物内には各ライブラリのビルド設定・著作権・ライセンスも含まれます。

差し替える前にアプリを終了し、フォルダー全体をバックアップしてください。

- Python部分は `_internal/py7zr/`、`_internal/bcj/`、`_internal/inflate64/`、`_internal/multivolumefile/`、`_internal/pyppmd/` の `.py` を直接変更できます。
- ネイティブ部分（`.pyd` / `.so`）を変更する場合は、同じPython ABI・OS・CPUの開発環境と、ソースのpyproject.toml等が指定するビルド環境を用意してください。通常利用者にPythonの導入は不要ですが、ネイティブライブラリを再ビルドする開発者にはPythonのヘッダーやコンパイラーが必要です。
- 対応するソースアーカイブを展開して変更し、`python -m pip wheel --no-deps <変更したソースのフォルダー> --wheel-dir <出力先>` でwheelを作成できます。出力wheelをZIPとして展開し、その中の対象モジュールのフォルダーを `_internal` 内の同名フォルダーと置き換えてください。バイナリのABIに合うファイル名を維持します。変更が反映されない場合は、対象フォルダー内の__pycache__をバックアップ側へ退避してから起動してください。
- `ShogiAnalyzer --self-check`（WindowsではShogiAnalyzer.exe）で、モジュールの読み込み元と7zの作成・展開を確認できます。単独のアプリで実行するため、システムにインストールした別のPythonの検索先とは独立しています。
- アプリ本体とライブラリの呼出し部分も変更する場合は、配布元リポジトリ https://github.com/retroaegx/ShogiAnalyzer の同じコミットを取得し、tools/build_portable.pyで再ビルドできます。コミットと依存バージョンは配布物のビルド情報を参照してください。

## 配布しないもの

エンジン・評価関数・cloudflaredは含めていません。エンジンと評価関数は利用者が配布元の条件を確認・同意してから正規配布元より取得します。python-shogiは開発時のテストでのみ利用し、このアプリの実行ファイルには含めません。

## Windowsの実行環境

Windows版には、Visual Studio 2022のC++再配布用フォルダーから取得したvcruntime140.dllとvcruntime140_1.dllを改変せず同梱します。著作権はMicrosoft Corporationに帰属します。Microsoftの有効な電子署名を確認し、これらのDLLをPSF/MITライセンスで再許諾しません。利用者によるVC++ランタイムやVisual Studioの別途インストールは不要です。Windows 10以降に含まれるUCRTを使用し、WindowsのシステムDLLは配布しません。

Microsoft製コードの利用には `_internal/third_party_notices/Microsoft-runtime-terms.txt` のMicrosoftの条件が適用されます。Windows版Pythonの追加条件は同フォルダーのCPython-Windows-conditions.txtです。利用・再配布する方はこれらの条件に同意したうえで利用・再配布してください。著作権・商標等の表示を変更せず、Microsoft公認と誤認させず、Microsoft製コードについて同条件が保護する権利を侵害する利用・再配布を行わないでください。法令上の権利および同梱されるオープンソースの条件による例外は、各原文のとおりです。この条件はMicrosoft製コードに限定され、ShogiAnalyzer本体や別のライセンスを持つライブラリの条件を置き換えません。

公式の原文DOCXと、全文をテキストに変換したものを保存しています。再配布権に関するVisual Studioの条項はMicrosoft-VS2022-terms.txt、対象ファイル一覧はMicrosoft-REDIST.htmlです。再配布者は適用されるVisual Studioの有効な利用許諾および再配布条件を満たす必要があります。単に本書に表示を加えることで再配布権が新たに付与されるわけではありません。

取得元と文書ハッシュはINVENTORY.json、DLLの版・著作権表示・ビルド時の取得元・ハッシュはWINDOWS_RUNTIME.jsonに記録します。DLLは必要な2個だけを同梱し、インストーラー全体は同梱しません。ランタイムの更新はアプリ配布物の更新として行います。
