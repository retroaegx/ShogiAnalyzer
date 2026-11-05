# 同梱ソフトウェアと改変・差し替え

ShogiAnalyzer本体のライセンスはMITです。個々の同梱ソフトウェアには、それぞれのライセンスが適用されます。利用者自身による改変、改変したライブラリでの実行、そのデバッグのためのリバースエンジニアリングを禁止する追加条件は設けません。

Python実行環境は同梱しています。アプリ側でCPythonのソースコードは改変していません。PyInstallerでアプリと依存をまとめ、開発用モジュールを除いて配布しています。正確なPythonバージョンと実行時ライブラリのバージョンは `_internal/third_party_notices/INVENTORY.json`、収集したネイティブファイルは同フォルダーの `NATIVE_FILES.txt` に記録しています。

著作権・ライセンス・免責事項は `_internal/third_party_notices/` に保存しています。Python本体のPSFライセンスと過去のライセンス群、組み込みソフトウェアの表示、OpenSSL、Pillowが同梱するライブラリの表示も含みます。`native-library-licenses.rst` は上流の参考文書で、今回使用していないコンポーネントも掲載されています。収集した実物はINVENTORY.jsonとNATIVE_FILES.txtを参照してください。Pillowを通じてFreeTypeを利用しています。関連部分の著作権はThe FreeType Projectに帰属します（https://freetype.org/）。

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

## Windowsのシステム実行環境

MicrosoftのDLLはPSF/MITライセンスの対象ではないため、本ZIPからは除外しています。Windows 10以降と、Microsoft公式のVisual C++ x64 Runtimeを利用します。Start.batはvcruntime140.dllとvcruntime140_1.dllがOS側にあるか確認し、不足時にはMicrosoft公式の導入案内を開きます。必要なPCでは、このランタイムの導入が別途必要です。Pythonの導入は不要です。
