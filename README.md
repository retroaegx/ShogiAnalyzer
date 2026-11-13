# ShogiAnalyzer

自分の PC を将棋の検討サーバーにするアプリです。  
PC で起動しておけば、同じ PC のブラウザやスマートフォン、出先からでも、棋譜の整理と解析エンジン（AobaNNUE、やねうら王 + つようら王11mini／水匠5）による検討ができます。

- 盤面操作・分岐つき棋譜・KIF / KI2 / USI の読み込みと書き出し
- 常時解析（候補手の矢印・評価値・読み筋）と全解析（評価値グラフ）
- エンジン設定（スレッド数・ハッシュなど）は画面から変更
- スマートフォン向けの画面

### ライセンス

ShogiAnalyzer 本体は **MIT ライセンス**です（[LICENSE](LICENSE)）。  
ネイティブ配布版に含むPython・実行ライブラリー・Windows用VC++ DLLなどには、個別の条件が適用されます。[同梱物のライセンスと対応ソース](docs/THIRD_PARTY.md)を参照してください。アプリの「ライセンス表記」からも、実際の配布物の一覧・原文を開けます。MPLのcertifiはLinuxでCA証明書がない場合のために同梱し、LGPLの展開ライブラリー5件とともに対応ソースを添付します。Microsoft製DLLをMIT/PSFで再許諾するものではありません。

Web画面の文字はOSにあるフォントで表示します。画像共有用フォントは本プロジェクトで生成したものです。

### 画面を修正する場合

画面のマークアップは `server/assets_web/index.html` にあります。アイコンの図形は `icons/ui.svg` のシンボルで管理します。HTMLでは `<use href="/icons/ui.svg#i-名前">`、JavaScriptでは `js/icons.js` の `icon("名前")` で参照します。盤上の候補手や分岐の矢印は、局面に合わせて座標を計算する描画です。

スタイルの読み込み順は `app.css` にあります。色や背景は `css/themes.css`、画面幅に応じた配置は `css/responsive.css` を確認してください。後から適用される操作欄・棋譜欄などの調整は `css/components.css` にあります。共有ダイアログ、共通ダイアログ、ホーム画面への追加案内は、それぞれ `js/share_dialog.js`、`js/dialogs.js`、`js/install_suggestion.js` で管理します。表示設定の既定値、旧設定の読み替え、サーバーとの同期は `js/preferences.js` にあります。

解析エンジン・評価関数・cloudflared は同梱していません。解析エンジンと評価関数は、初回起動時に利用者の同意を得てそれぞれの配布元からダウンロード（Linux ではビルド）します。cloudflared は、外部公開に Quick Tunnel を使うとき（固定アドレス未設定で `SHOGI_ANALYZER_TUNNEL` が TRUE のとき）に配布元から `tools/cloudflared/` へダウンロードします。

| ソフト | 種類 | ライセンス | 配布元 |
|---|---|---|---|
| やねうら王（つようら王11mini 対応版） | 解析エンジン | GPLv3 | https://yaneurao.fanbox.cc/posts/12761272 （Linux は https://github.com/yaneurao/YaneuraOu からビルド） |
| つようら王11mini (nn.bin, progress.bin) | 評価関数 | MIT | https://yaneurao.fanbox.cc/posts/12761272 |
| AobaNNUE | 解析エンジン | GPLv3 | https://github.com/yssaya/AobaNNUE |
| AobaNNUE 評価関数 (nn.bin) | 評価関数 | 配布元に明記なし | https://github.com/yssaya/AobaNNUE/releases/tag/v1.1 |
| やねうら王 | 解析エンジン | GPLv3 | https://github.com/yaneurao/YaneuraOu |
| 水匠5 (nn.bin) | 評価関数 | 配布元に明記なし | https://github.com/yaneurao/YaneuraOu/releases/tag/suisho5 |
| cloudflared | 外部公開用トンネル（Quick Tunnel） | Apache License 2.0 | https://github.com/cloudflare/cloudflared |

- ShogiAnalyzer本体はMITで提供します。エンジンは別のプログラムとしてUSI（標準入出力）で通信する構成で、エンジン側のGPL等の条件はそのまま適用されます。
- cloudflaredも別のプログラムとして起動します。cloudflaredの利用・再配布は、配布元のライセンスとCloudflareの利用規約に従ってください。
- エンジンを同梱して再配布する場合は、そのエンジンについて GPLv3 の表記（ライセンス全文の添付とソースコードの入手方法の明示）が必要です。評価関数は各配布元の利用条件に従ってください。

---

## ネイティブ配布版を使う場合

ネイティブ配布版にはPythonと実行ライブラリーを含めています。**Python・PHPの別途導入、手動でのvenv構築・pipインストールは不要**です。[リリースページ](https://github.com/retroaegx/ShogiAnalyzer/releases)の添付ファイルから、OS・CPUに合うパッケージを選んでください。GitHubの「Source code (zip)」「Source code (tar.gz)」は、下記のPythonが必要なソース版です。該当OSのネイティブパッケージが添付されていないリリースでは、ソース版の手順を使ってください。

| OS・CPU | ダウンロードするファイルの末尾 | 起動するファイル |
|---|---|---|
| Windows x64（Windows 10以降） | `windows-amd64.zip` | `Start.bat` |
| Linux x64（glibc 2.35以降。Ubuntu 22.04以降など） | `linux-amd64.tar.gz` | `ShogiAnalyzer` |
| Mac Intel | `macos-amd64.tar.gz` | `Start.command` |
| Mac Apple Silicon（M1以降） | `macos-arm64.tar.gz` | `Start.command` |

パッケージはOS・CPU間で共用できません。展開したフォルダー内の`_internal`も必要なので、実行ファイルだけを取り出さず、書き込み可能な場所にフォルダーごと置きます。初回のエンジン・評価関数等の取得にはインターネット接続が必要です。

### Windows

1. `windows-amd64.zip`を右クリックし、「すべて展開」で展開します。
2. 展開先の`ShogiAnalyzer`フォルダーを開き、`Start.bat`をダブルクリックします。
3. 下記の「[初回設定](#first-run-setup)」へ進みます。

必要なVC++ランタイムDLL2個も同梱しています。通常利用者によるPython・Visual Studio・VC++ランタイムの別途インストールは不要です。

### Linux

Linuxでは、アプリ本体にPythonを入れる必要はありませんが、**エンジンの自動導入にはmake・C++コンパイラーが必要**です。やねうら王v8.30のソース取得ではGitも使用します。このエンジンのビルド要件は、従来のPython版でも必要だったものです。

Ubuntu 22.04以降／Debian 12以降での準備例です。ターミナルを開き、次を順に実行します。

```bash
sudo apt update
sudo apt install build-essential git ca-certificates
```

`build-essential`には[makeとg++等が含まれます](https://packages.ubuntu.com/jammy/build-essential)。`sudo`で求められるのはLinuxのログインパスワードです。入力中は文字が表示されません。すでに導入済みなら追加の作業は不要です。他のディストリビューションでは、そのOSのパッケージ管理で同等のツールを用意してください。Linuxの確認環境はUbuntu 22.04／24.04です。

続いて、ダウンロードした`linux-amd64.tar.gz`を展開して起動します。以下はファイルを`~/Downloads`へ保存したv1.2.1の例です。保存先とファイル名は、実際に取得したものに合わせてください。

```bash
cd ~/Downloads
tar -xzf ShogiAnalyzer-v1.2.1-linux-amd64.tar.gz
cd ShogiAnalyzer
./ShogiAnalyzer
```

起動後は「[初回設定](#first-run-setup)」へ進みます。エンジンを選択して同意すると、ソース取得とビルドも自動で進みます。ビルド中は時間がかかるので、ターミナルを閉じずに待ってください。ビルドに使うPython処理には同梱Pythonを使用します。現在のLinux自動ビルドはAVX2またはSSE4.2に対応するx64 CPUが対象です。

`make: not found`や`g++: not found`等が出た場合は、上記ツールの導入を確認して起動し直してください。手持ちのLinux用USIエンジンを使う場合は、初回メニューで`m`を選びます。ビルドツールなしで使う場合は、別途ビルド済みの対応エンジンが必要です。

### macOS

1. Appleメニューの「このMacについて」で、「チップ」がApple Mシリーズなら`macos-arm64.tar.gz`、「プロセッサ」がIntelなら`macos-amd64.tar.gz`を選びます。
2. ダウンロードしたファイルを展開し、`ShogiAnalyzer`フォルダーの`Start.command`をダブルクリックします。
3. 開いたターミナルで「[初回設定](#first-run-setup)」を行います。

ネイティブ版ではPython・Homebrew・Xcodeの導入は不要です。アプリは署名・公証していません。起動がOSに止められた場合は、取得元を確認のうえ[Appleの案内](https://support.apple.com/ja-jp/guide/mac-help/mh40616/mac)に従ってください。

### 自動導入できるエンジン

インストーラーには、使用中のOS・CPUに対応する設定があるエンジンだけが表示されます。**番号はOSによって変わるため、表示されたエンジン名を確認して選んでください。**

| エンジン・評価関数 | Windows x64 | Linux x64 | Mac Intel／Apple Silicon |
|---|---|---|---|
| やねうら王＋つようら王11mini | 実行ファイルを取得 | ソースからビルド | 自動導入対象外 |
| AobaNNUE v1.1 | 実行ファイルを取得 | ソースからビルド | 自動導入対象外 |
| やねうら王v8.30＋水匠5 | 実行ファイルを取得 | ソースからビルド | Mac用の配布物を取得 |

Macにもやねうら王v8.30の自動取得設定があります。取得した配布物にOS・CPU対応の実行ファイルが見つからない場合は、手持ちの対応USIエンジンを手動設定してください。Macの初期OS環境での導入操作は未検証です。

設定`.env`と棋譜等の`server/data/`、取得した`engines/`・`tools/cloudflared/`は、標準では実行ファイルの横に作成されます。アプリを終了してからこれらをバックアップしてください。別の保存先を使う場合は`SHOGI_ANALYZER_HOME`に絶対パスを指定します。更新時はユーザーデータを削除せず、アプリのファイルを置き換えます。詳しくは[ネイティブ配布版の説明](docs/PORTABLE.md)を参照してください。

以下のPython導入・`run.bat`/`run.sh`は、ソースから実行する場合の手順です。ネイティブ配布版では実施しません。

## 1. ソースから実行する場合のPython導入

**Python 3.10 以上**が必要です。

- Windows: コマンドプロンプトで `python --version` を実行して確認します。  
  入っていなければ https://www.python.org/downloads/windows/ から Windows installer (64-bit) を入れてください。  
  インストール時に **「Add Python to PATH」を ON** にしてください。
- macOS: Homebrewを利用する場合は、[Python 3.12の導入方法](https://formulae.brew.sh/formula/python@3.12)に従い、ターミナルで次を実行します。このターミナル内で`python3`が3.12を指すようPATHも設定します。

  ```bash
  brew install python@3.12
  export PATH="$(brew --prefix python@3.12)/libexec/bin:$PATH"
  python3 --version
  ```

- Ubuntu / Debian: `sudo apt update`の後、`sudo apt install python3 python3-venv`を実行します。エンジンを自動ビルドする場合は、上記Linux手順の`build-essential`・`git`・`ca-certificates`も用意してください。

## 2. 起動と初回設定

### ソース版の起動

ソースコードを展開したフォルダーで起動します。ネイティブ版の起動方法は上記OS別手順を使ってください。

- Windows: `run.bat` をダブルクリック
- macOS / Linux: `sh run.sh`

ソース版では、起動時に`.venv`の作成と必要ライブラリーの導入を自動で行います。手動でvenvを作ったり、システム全体へpipでインストールしたりする必要はありません。macOSでHomebrewのPATHを上記のように設定した場合は、同じターミナルで`sh run.sh`を実行してください。

<a id="first-run-setup"></a>

### 初回設定（ネイティブ版・ソース版共通）

1. 「パスワード保護を有効にしますか？」に回答します。外部公開する場合は`y`、このPCだけで利用する場合は`n`で無効にしても使えます。選んだ後にEnterを押します。有効にした場合、パスワード自体は後でブラウザーの初回画面で設定します。
2. エンジン一覧の名前を確認し、使いたいものの番号を入力してEnterを押します。手持ちのUSIエンジンは`m`でパスを指定できます。`s`は解析なしで起動する選択です。
3. 表示されるエンジン・評価関数の配布元と規約・ライセンスを確認し、同意する場合だけ`y`を入力してEnterを押します。別々に取得する評価関数にも確認が出ます。同意しない場合はメニューに戻ります。
4. 取得・展開（Linuxではビルドも）が完了し、`local : http://localhost:31145`等のアドレスが出るまで待ちます。
5. 同じPCのブラウザーを開き、アドレス欄に表示された`local`のURLを入力します。パスワード保護を有効にした場合は、初回の設定画面に従って設定します。スマートフォンから初回設定する場合は、コンソールのセットアップコードも必要です。

エンジン・評価関数はアプリ配布物には含めていません。インストーラーが同意後に取得して、エンジンと評価関数のパスを保存します。すでに設定済みなら、次回からその設定を使って起動します。

起動するとコンソールに URL が表示されます。

```
[installer] URLs
  local : http://localhost:31145
  public: https://xxxx-xxxx.trycloudflare.com  (Quick Tunnel: 起動ごとに変わります)
  log   : <ShogiAnalyzer のフォルダ>\server\data\console.log
  設定  : <ShogiAnalyzer のフォルダ>\.env
```

- `local`: 起動した PC のブラウザで開くアドレス
- `public`: スマートフォンや出先から開けるアドレス（※ 下の注意を参照）
- `log`: コンソールに出た内容はすべてこのファイルにも記録されます。アドレスを見失ったときはここを見てください。
- 終了するときはコンソールで `Ctrl + C` を押すか、ウィンドウを閉じます。

> **注意**
> - `public` の `trycloudflare.com`（Cloudflare Quick Tunnel）は**起動するたびにアドレスが変わります**。また、テスト・開発用のサービスなので常用はできません。続けて使う場合は「[5. 公開アドレスを固定する](#5-公開アドレスを固定する)」で固定アドレスにするか、`SHOGI_ANALYZER_TUNNEL=FALSE` で公開を止めてください。
> - 初回起動でパスワード保護を有効にするか選択します。OFF のままだと、公開アドレスを知っている人は誰でも操作できます。外部公開する場合は「[パスワード保護](#パスワード保護)」を ON にしてください。

## 3. 設定ファイル（.env）

初回起動時に、ShogiAnalyzer のフォルダ（ネイティブ版では実行ファイル、ソース版では`run.bat`がある場所）に設定ファイル `.env` が作られます（中身は `.env.template` と同じ。git の管理外）。`SHOGI_ANALYZER_HOME`を指定した場合は、その保存先に作成します。
メモ帳などで編集して保存し、**アプリを再起動すると反映**されます。  
エンジンの 2 項目は、空欄のまま起動すると実際に使うパスが自動で書き込まれます（自分で書いた値は上書きしません）。

| 項目 | 内容 | 既定値 |
|---|---|---|
| `SHOGI_ANALYZER_PUBLIC_URL` | 固定の公開アドレス。設定すると Quick Tunnel は使わず、このアドレスを表示します | 空（Quick Tunnel） |
| `SHOGI_ANALYZER_TUNNEL` | 公開アドレスが空のとき Quick Tunnel を使うか（`TRUE` / `FALSE`） | `TRUE` |
| `SHOGI_ANALYZER_PASSWORD` | パスワード保護（`TRUE` / `FALSE`）。詳しくは「[パスワード保護](#パスワード保護)」 | **初回起動時に選択**（空欄なら `FALSE` 扱いで、次回また聞かれます） |
| `SHOGI_ANALYZER_UPDATE_CHECK` | 新しいバージョンの確認（`TRUE` / `FALSE`）。詳しくは「[9. バージョンと更新](#9-バージョンと更新)」 | `TRUE` |
| `SHOGI_ANALYZER_UPDATE_CHECK_INTERVAL_HOURS` | 確認する間隔（時間） | `24` |
| `SHOGI_ANALYZER_PORT` | 待ち受けポート | `31145` |
| `SHOGI_ANALYZER_HOST` | `127.0.0.1` = この PC からのみ / `0.0.0.0` = 同じ LAN の端末からも開ける | `127.0.0.1` |
| `SHOGI_ANALYZER_ENGINE_PATH` | 解析エンジン（USI）の exe のパス | **自動設定**（初回起動時に、自動で入れたエンジンのパスが書き込まれます） |
| `SHOGI_ANALYZER_ENGINE_EVAL_DIR` | 評価関数（`nn.bin` など）のフォルダ | **自動設定**（exe の近くの `eval` を探して書き込みます） |
| `SHOGI_ANALYZER_SERVER_LOGLEVEL` | サーバーログの詳しさ（`warning` / `info` / `debug`） | `warning` |

```env
SHOGI_ANALYZER_PUBLIC_URL=https://shogi-sample.f5.si
SHOGI_ANALYZER_HOST=0.0.0.0
SHOGI_ANALYZER_ENGINE_PATH=D:/shogi/engines/YaneuraOu/YaneuraOu_NNUE-avx2.exe
```

パスは `/` でも `\` でも書けます。相対パスは `.env` があるフォルダからの位置になります。  
スレッド数・ハッシュ（メモリ）などのエンジンオプションは `.env` ではなく、画面の「解析」の ⚙ から設定します（エンジンが報告する既定値を読み取って表示します）。

## 4. 同じ LAN のスマートフォン・PC から使う

1. `.env` を `SHOGI_ANALYZER_HOST=0.0.0.0` にして再起動します。
2. コンソールに `lan : http://192.168.x.x:31145` が表示されるので、そのアドレスを同じ Wi-Fi の端末で開きます。

つながらないときは次を確認してください。

- 端末が起動 PC と同じ Wi-Fi / 同じネットワークにつながっているか
- Windows のファイアウォールで `31145` 番ポート（または Python）の通信が許可されているか（初回起動時の確認画面で「プライベート ネットワーク」を許可）
- `127.0.0.1` / `localhost` は自分自身のことなので、別の端末からは使えません

PC のローカル IP アドレスは再起動などで変わることがあります。固定したい場合はルーターの「DHCP 固定割り当て（IP 予約）」を設定してください（方法はルーターごとに異なります）。

## 5. 公開アドレスを固定する

スマートフォンや出先から毎回同じアドレスで使う方法です。  
**Cloudflare Tunnel**（無料）と、**無料の DDNS サービスのサブドメイン**を Cloudflare に委任する方法を紹介します。ここでは DDNS Now を使いますが、MyDNS.JP や、海外の ClouDNS / DigitalPlat (qzz.io) などでも同じことができます。独自ドメインを持っている場合は 5-1 / 5-2 を飛ばして、そのドメインを Cloudflare に追加してください。

### 5-1. DDNS Now でサブドメインを取る

1. [DDNS Now](https://ddns.kuku.lu/) を開き、左メニューの「新規登録」から登録します。
   - 希望サブドメイン：好きな名前（英数字と `-`）
   - パスワード：6 文字以上
2. 取得したアドレス（例: `shogi-sample.f5.si`）をメモしておきます。

### 5-2. Cloudflare にドメインを委任する

1. [Cloudflare](https://dash.cloudflare.com/login) にログインします（アカウントがなければ無料で作成）。
2. ダッシュボード（左上）→「ドメイン」→ 右側の「+ ドメインのオンボード」を押します。
3. 「既存のドメインを入力」に 5-1 のアドレス（例: `shogi-sample.f5.si`）を入れて「続行」。
4. プランは **Free** を選びます。
5. 「DNS レコードを確認する」画面で「アクティベーションを続行」を押します。
6. 「Cloudflare ネームサーバーに置き換える」欄に表示される **ネームサーバー 2 つ**をメモします。
7. [DDNS Now の設定画面](https://ddns.kuku.lu/control.php) を開き、NS レコード欄の下の「認証する」から電話認証をします（表示された番号に自分の電話から発信し、数秒で切るだけです）。
8. 設定画面を開き直し、A / AAAA / CNAME / サブドメイン / ワイルドカードを**すべて空**にして「設定を更新する」を押します。
9. NS レコード欄に 6 でメモした 2 つを**改行して**入力し、「設定を更新する」を押します。

設定画面に戻れば完了です。Cloudflare 側でドメインが「アクティブ」になるまで、数分〜数時間かかることがあります。

### 5-3. Cloudflare Tunnel を作って PC につなぐ

1. Cloudflare の「ドメイン」→ 委任したドメイン →「DNS レコード」を開き、レコードが残っていればチェックを入れて削除します。
2. ダッシュボード →「ネットワーク」→「Tunnels」→「トンネルを作成」を押します。
3. 好きなトンネル名を入れて「トンネルを作成」。
4. 「インストールと実行」に表示される手順どおりに作業します。  
   Windows の場合は、表示される `.msi` をインストールし、**管理者として開いたコマンドプロンプト**で表示されたコマンド（`cloudflared.exe service install …`）を実行します。  
   一番下の「接続状態」に「トンネルが正常に接続されました」と出たら「続行」を押します。  
   （これで PC の起動時に自動でトンネルがつながるようになります。ShogiAnalyzer を起動していないときは開けないだけです。）
5. 作成したトンネルを開き、「Routes」の「+ Add route」→「Published application」を押します。
6. 右上の「Domain」に委任したドメインが表示されていることを確認し、**Service URL** に次を入れて「Add route」を押します。

   ```
   http://127.0.0.1:31145
   ```
   （`.env` でポートを変えた場合はその番号にします）

### 5-4. アプリに固定アドレスを設定する

`.env` に固定アドレスを書いて再起動します。

```env
SHOGI_ANALYZER_PUBLIC_URL=https://shogi-sample.f5.si
```

起動時に `public: https://shogi-sample.f5.si (固定アドレス …)` と表示され、Quick Tunnel は使われなくなります。ブラウザでそのアドレスを開いて確認してください。

### パスワード保護

初回起動時に、コンソールで「パスワード保護を有効にしますか？ [y/N]」と聞かれます。答えは `.env` に保存され、あとから `.env` で切り替えられます。

```env
SHOGI_ANALYZER_PASSWORD=TRUE
```

- 有効（`TRUE`）にして起動したあと、**最初に開いた画面でパスワードを決めます**（4 文字以上）。パスワード自体はコンソールでは入力しません。
- この PC 以外（スマートフォン・公開アドレス）から最初の設定をする場合は、コンソール（と `console.log`）に表示される **6 桁のセットアップコード**も入力します。他人に先に設定されるのを防ぐためです。
- 一度ログインすると、その端末・そのアドレスでは **30 日間**入力不要です（アプリを再起動しても続きます）。ログアウトは「⋯」→ 表示設定の一番下にあります。
- `FALSE` に戻して起動すると、保存されていたパスワード情報は削除されます。パスワードを忘れたときは `FALSE` で一度起動し、`TRUE` に戻して設定し直してください。
- Quick Tunnel（`trycloudflare.com`）はアドレスが毎回変わるため、起動のたびにログインし直しになります。固定アドレスならその必要はありません。

### Cloudflare Access（任意）

さらに厳しくしたい場合は、Cloudflare の Cloudflare の **Access**（Zero Trust、無料枠あり）で「自分のメールアドレスで認証した人だけ開ける」ようにしておくと安心です。  
Cloudflare ダッシュボード →「Zero Trust」→「Access」→「アプリケーション」→「アプリケーションを追加」→「セルフホスト」で、上のドメインを登録し、許可するメールアドレスをポリシーに設定します。

## 6. 解析エンジン・評価関数を変える

- 初回起動時に、解析エンジンを選んで自動で用意します（Enter で 1 を選びます）。
  1. AobaNNUE（エンジンと評価関数。CPU に合ったものを自動選択。Linux では同梱のソースからビルド）
  2. やねうら王（CPU に合ったものを自動選択）と水匠5 の評価関数
- 初回起動後の `.env` には、使っているエンジンと評価関数のパスが書き込まれています。
- 別のエンジンを使うときは、`.env` の `SHOGI_ANALYZER_ENGINE_PATH` を exe のパスに、`SHOGI_ANALYZER_ENGINE_EVAL_DIR` を評価関数のフォルダに書き換えて再起動します（評価関数のフォルダを空にすると exe の近くの `eval` を探して書き込み直します）。
- スレッド数・ハッシュなどは画面の「解析」の ⚙（エンジン設定）から変更します。ハッシュの上限は搭載メモリの半分、スレッド数の上限は論理 CPU 数です。

## 7. データの保存場所

アプリが作るファイルは ShogiAnalyzer のフォルダの中の次の場所に保存されます。どれも `.gitignore` で git の管理外です。

| ファイル / フォルダ | 内容 |
|---|---|
| `.env` | 設定ファイル |
| `.venv/` | Python の実行環境 |
| `engines/` | 自動で入れたエンジンと評価関数 |
| `tools/cloudflared/` | cloudflared |
| `server/data/app.db` | 棋譜・解析結果 |
| `server/data/console.log` | 最後に起動してからのコンソール出力（公開アドレスもここに残ります） |
| `server/data/engine_config.json` | 初回に選んだエンジンの場所 |
| `server/data/engine_options.json` | 画面で変えたエンジン設定 |
| `server/data/auth.json` | パスワード保護の情報（パスワードそのものではなくハッシュ） |

棋譜を全部消して初期状態に戻したい場合は、アプリを止めてから `server/data/app.db*` を削除してください。

## 8. 使い方

### 盤と棋譜
- 駒をドラッグまたはタップして動かします。成れるときは移動先の横に「成 / 不成」が出ます。
- `←` / `→` で 1 手戻る / 進む、`Home` / `End` で最初 / 最後、`F` で盤の反転。盤の上でマウスホイールでも手を進められます。
- 棋譜の手をクリックするとその局面へ移動します。分岐があると「変化」のボタンが出ます。
- 上部のボタン：新規 / 開く（保存した棋譜の一覧。× で削除）/ 読込（KIF・KI2・USI のファイル）/ 貼付（クリップボードの棋譜）/ 書出 / 保存。
- 読込・貼付した棋譜は、どちらも新しい棋譜として開きます。対応していない形式のときは「形式が違います」と表示されます（対応: KIF / KI2 / USI）。
- 棋譜名は上部の ✎ ボタンで変更できます。新規・貼付の棋譜名は `kif_YYYYMMDD_hhmmss` になり、名前を付けずに初めて保存するときは保存名を聞かれます。

### 解析
- 「常時解析」を ON にすると、表示中の局面を解析し続けます（`Space` でも切り替え）。OFF にしても最後の結果は残ります。
- 盤の上に、候補手（緑の矢印と評価値）、棋譜の次の手（オレンジ）、分岐（薄いオレンジ）が表示されます。表示する内容は右上の表示設定で切り替えられます。
- 「候補手」の数字で読み筋の数（MultiPV）を選べます。
- 棋譜一覧・グラフは、各局面で保存された最も深い解析結果を表示します。候補手数を変えて浅い深さから解析し直している間は、現在の解析欄の評価値と異なることがあります。
- 「全解析」で棋譜の最初から最後までを順に解析し、評価値グラフを作ります（1 局面あたりの時間は ⚙ で設定）。実行中は棋譜を操作できません。

### スマートフォン
- スクロールなしで 1 画面に収まります。盤の下に移動ボタン、その下に「解析 ON/OFF・評価値・深さ・最善手」、候補手の数・全解析、評価値グラフが並びます。候補手は盤上の矢印と評価値で表示します（グラフの高さは画面の高さに合わせて自動で調整します。iPhone SE など縦が短い画面では持ち駒を盤の横に置きます）。
- 移動ボタン横の「棋譜」ボタン、または画面の右端から左へスワイプすると棋譜が開きます。
- 移動ボタンの右の「反転」ボタンで盤を上下反転します。
- 新規・棋譜一覧・エクスポート・表示設定・エンジン設定は右上のメニューにあります。読み込みは上部の書類アイコンからも開けます。

### アプリとしてインストール（ホーム画面に追加）
- **Android の Chrome**: アドレスを開き、メニュー（⋮）→「アプリをインストール」（または「ホーム画面に追加」）。
- **iPhone / iPad の Safari**: 共有ボタン →「ホーム画面に追加」。
- **PC の Chrome / Edge**: アドレスバー右端のインストールボタン、またはメニュー →「ShogiAnalyzer をインストール」。
- 追加すると、アイコンからアドレスバーのない専用の画面で開けます。
- インストールできるのは **https のアドレス**（公開アドレス・固定アドレス）か、この PC の `localhost` だけです。LAN の `http://192.168.x.x` からは、ブラウザの制限でアプリとしてはインストールできません（ブックマークは可）。

## 9. バージョンと更新

- 今のバージョンは、ソース版ではフォルダ直下の `VERSION`、ネイティブ版では`_internal/VERSION`と`BUILD_INFO.json`に書かれています。起動時のコンソールと、画面右上の「表示設定」の一番下にも表示されます。
- アプリは起動時と 24 時間ごと、また画面を開いたときに前回の確認から 1 時間以上たっていれば、[GitHub のリリース](https://github.com/retroaegx/ShogiAnalyzer/releases) を確認します。新しいバージョンがあると、画面上部に **「!」** が出て（押すと内容とリリースページへのリンク）、コンソールにも `[update] 新しいバージョン … があります` と表示されます。
- 「表示設定」→「バージョン」の **「更新を確認」** で、すぐに確認することもできます。
- 確認しないようにするには `.env` で `SHOGI_ANALYZER_UPDATE_CHECK=FALSE` にします。

### 更新のしかた

ネイティブ配布版では、アプリを終了してからWindowsの`Update.bat`、Linuxの`./Update.sh`、Macの`Update.command`を実行すると、対応する最新のネイティブ版へ更新できます。外部Pythonの導入は不要です。`.env`・棋譜等の`server/data/`・エンジン・cloudflaredは残し、更新後はShogiAnalyzerを起動し直します。更新の確認だけで自動的に上書きすることはありません。詳しくは[更新用スクリプト](docs/PORTABLE.md#更新用スクリプト)を参照してください。

Updateが入っていない旧版や手動で更新する場合は、以下の手順を使います。

1. アプリを止めます（コンソールで `Ctrl + C`、またはウィンドウを閉じる。Ubuntu などでサービスにしている場合は `sudo systemctl stop shogianalyzer`）。
2. フォルダを新しいバージョンにします。
   - `git clone` で取得した場合: フォルダで `git pull`
   - ネイティブ版の場合: [リリースページ](https://github.com/retroaegx/ShogiAnalyzer/releases)から同じOS・CPU用の新しいZIP／tar.gzを取得し、すべて展開してアプリのファイルを更新します。設定`.env`・棋譜`server/data/`・エンジン`engines/`・`tools/cloudflared/`は残してください。
   - ソース版をZIPで取得した場合: ソース版の新しいZIPを展開してアプリのファイルを更新します。上記の設定・データは残してください。
3. ネイティブ版はWindowsの`Start.bat`、Linuxの`./ShogiAnalyzer`、Macの`Start.command`から再起動します。ソース版は`run.bat`／`sh run.sh`、サービスなら`sudo systemctl start shogianalyzer`です。ソース版のPythonパッケージは起動時に自動で更新されます。

設定（`.env`）・棋譜（`server/data`）・エンジン（`engines`）は git の管理外なので、更新しても消えません。
