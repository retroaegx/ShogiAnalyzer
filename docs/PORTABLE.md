# Python不要版（ネイティブ配布）

WindowsはZIPをすべて展開し、Start.batを起動します。Windows 10以降が対象です。必要なVisual C++ランタイムDLLを同梱しているため、利用者によるランタイムの別途インストールは不要です。Linuxはtar.gzを展開してターミナルで `./ShogiAnalyzer`、macOSは展開後のStart.commandから起動します。フォルダー内の `_internal` も必要です。書き込み可能な場所へ置いてください。

Python・PHPを別途入れる必要はありません。エンジン・評価関数は同梱していません。初回設定で配布元・利用規約を確認して同意すると、正規配布元から利用者のPCへ取得します。同意しない場合は取得しません。手動設定や解析なしでの利用も可能です。

OS・CPUの異なるパッケージは共用できません。Windows x64、Linux x64、Mac Intel、Mac Apple Siliconはそれぞれの環境でビルドします。エンジン自動導入で対応するものがない環境では、利用できるUSIエンジンを手動設定してください。Linuxの一部エンジンは利用者のPCでソースからビルドするため、makeとC++コンパイラーが別途必要です。Python製の生成スクリプトには同梱ランタイムを使います。

設定は実行ファイル横の `.env`、棋譜・パスワード等のデータは `server/data/` に保存します。既存環境から移す場合は停止してからこれらと `engines/`、`tools/cloudflared/` を利用者自身で移してください。別の保存先を使う場合は環境変数 `SHOGI_ANALYZER_HOME` に絶対パスを指定します。更新時はユーザーデータを残してアプリのファイルを置き換えます。

終了する場合は起動したターミナルでCtrl+Cを押してください。常駐運用は `ShogiAnalyzer --serve` を使用できます。この場合、事前に `.env` にエンジンのパス等を設定してください。

macOS版は署名・公証していません。OSの警告が出る場合は、提供元と取得元を確認したうえでOSの許可操作が必要です。Linuxはビルド環境より古いglibcでは動作しない場合があります。配布先を考慮し古い対応環境でビルドします。

開発者向け: クリーンな仮想環境へ `tools/requirements-portable.txt` を入れ、`python tools/build_portable.py` を実行します。続いて `python tools/smoke_portable.py <生成された実行ファイル>` で、PythonがPATHにない状態での通常起動とHTTP配信を検証します。生成したbuild-report.json・build-requirements.lockにはサイズ・ハッシュ・使用した依存バージョンを記録します。

Windows版をビルド・再配布する環境には、再配布権を持つVisual Studioの利用許諾とVisual Studio 2022のC++ REDISTファイルが必要です。ビルド時に署名・版・出所を検査します。これは配布者側の条件で、通常利用者にVisual Studioの導入は不要です。

同梱物の著作権・ライセンス・対応ソース・差し替え方法は、配布物のTHIRD_PARTY.txtを参照してください。開発テストには別途tests/requirements.txtを使います。

Windows版に含むMicrosoft製ランタイムにはMicrosoftの条件が適用されます。利用・再配布する場合はTHIRD_PARTY.txtの「Windowsの実行環境」と、そこに記載した付属条件を確認し、同意したうえで利用・再配布してください。これらの条件はMicrosoft製コードに対するもので、ShogiAnalyzer本体のMITライセンスを変更しません。
