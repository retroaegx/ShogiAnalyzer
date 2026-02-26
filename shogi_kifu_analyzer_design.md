# 棋譜整理・検討アプリ（オンプレ + Cloudflare Tunnel）設計書（Codex 実装用）

作成日: 2026-02-26  
目的: この設計書の内容をそのまま Codex に渡して実装を進められるよう、仕様・構成・API・データモデル・インストーラ要件を固定する。

---

## 0. ゴール / スコープ

### ゴール
- オンプレ環境で動作する **棋譜整理・検討**アプリを新規構築する
- Web UI は Cloudflare Tunnel（Quick Tunnel または既存トンネル）経由で外部からアクセス可能
- 盤面表示・駒操作（ドラッグ等）・USI解釈・画像資産を既存コードから流用し、UI/データモデル/通信/保存は新規設計で再実装する
- 棋譜形式: **KIF / KIF2(KI2想定) / USI** の読み込み・貼り付け・保存（ローカル/サーバ）に対応
- 分岐（変化）を **保存・読み込み** できる
- エンジン解析を **ストリーミング**表示（最初の 5 秒は 0.5 秒ごと、その後は 1 秒ごと）
- WSS(WebSocket over TLS) で **同時 1 セッションのみ有効**（奪取 UI あり）

### 非ゴール
- 対局機能（共有盤・退室・マッチング・観戦・ロビー）は実装しない
- アカウント/ログイン機能は実装しない（オンプレ前提、単一セッション制御で代替）
- 常駐ミドルウェア（MongoDB/Redis 等）の導入はしない

---

## 1. 既存コードからの流用範囲（確定）

### 1.1 流用する（コピーベースで新規リポジトリに移植）
- 盤描画・ドラッグ&ドロップ・テーマ適用
  - `frontend/shogi-frontend/src/components/game/ShogiBoard.jsx`
  - `frontend/shogi-frontend/src/config/themeLoader.js`
- USI/座標/SFENの最小ユーティリティ（UI側に必要なものだけ）
  - `src/utils/usi.js`
  - `src/utils/shogiCoords.js`
  - `src/utils/sfen.js`（parse など）
- 画像・テーマ・効果音（ただしライセンス監査が必要）
  - `public/board-theme/*`
  - `public/sounds/*`

### 1.2 流用しない（参考のみ）
- 既存のロビー・対局・複数ルーム WS 管理・認証・Redisワーカー等
- 既存の KIF ルート（対局システム寄りで、今回の分岐・汎用入出力に不適）

---

## 2. ユーザー体験（UI）仕様

### 2.1 画面は 1 つ（ヘッダー/フッターなし）
- 左: 盤面 + 持ち駒
- 中央: 棋譜操作バー（戻る/進む/最初/最後/分岐移動等）
- 右: 棋譜ツリー（分岐） + 解析候補リスト + 解析グラフ

### 2.2 操作要件
- 駒をドラッグして移動・打つ
- 棋譜をクリックして局面移動
- 分岐（変化）はツリーで表示し、任意ノードへジャンプできる
- 「解析ON/OFF」ボタン
- 「解析候補数（MultiPV）」プルダウン（例: 1/3/5/10/20）
- 設定: Threads（= CPUコア数）、Hash(MB)、Engine 選択
- 「棋譜」メニュー:
  - 新規作成（初期局面）
  - 読み込み: ローカルファイル / サーバ保存一覧
  - 貼り付け: テキスト入力
  - 保存: ローカルへエクスポート / サーバへ保存
  - 形式: KIF / KIF2(KI2) / USI（エクスポート時に選択）

### 2.3 復元要件
- 接続時に前回の状態（棋譜 + 現在ノード + UI設定）を復元
- 前回が無ければ初期局面

---

## 3. システム構成（推奨）

### 3.1 ランタイム
- Backend: Python + FastAPI
  - HTTP: 静的 Web 配信 + API
  - WebSocket: 状態同期 / 解析ストリーミング
- Frontend: React + Vite（ビルド成果物は server から配信）
- DB: SQLite（単一ファイル、常駐不要）
- Engine: USI エンジン（例: やねうら王系など。導入はインストーラから）

### 3.2 ポート
- ローカル待受: `31145`（HTTP + WS 同一ポート）
- 外部公開: Cloudflare Tunnel 側（通常の https URL / 80 相当）

---

## 4. データモデル（分岐を正として設計）

### 4.1 内部表現（保存の正）
「棋譜 = 変化木」として保存する。一本道を正にしない。

#### Game（棋譜1本）
- `game_id: str`（UUID）
- `title: str`
- `created_at, updated_at`
- `initial_sfen: str`（通常は平手初期局面）
- `root_node_id: str`
- `current_node_id: str`（復元用）
- `meta: json`
  - 先手名/後手名/棋戦名/開始日時/手合割 など
- `ui_state: json`
  - 盤向き、解析候補数、解析ON/OFF（※復元時はONを自動再開しない推奨）、表示スケール等

#### Node（局面ノード）
- `node_id: str`（UUID）
- `game_id: str`
- `parent_id: str | null`
- `order_index: int`（兄弟順）
- `move_usi: str | null`（root は null）
- `move_label: str`（表示用。例: "▲７六歩"）
- `comment: str`
- `position_sfen: str`（キャッシュ。root は initial_sfen）
- `created_at`

#### AnalysisSnapshot（解析結果の履歴）
- `snapshot_id: str`
- `node_id: str`
- `elapsed_ms: int`
- `multipv: int`
- `lines: json`（PV配列）
  - PVLine:
    - `pv_index: int`
    - `score_type: "cp" | "mate" | "unknown"`
    - `score_value: int`（cp または mate）
    - `depth: int`
    - `seldepth: int`
    - `nodes: int`
    - `nps: int`
    - `hashfull: int`
    - `pv_usi: str[]`（USI move list）
- `created_at`

### 4.2 SQLite スキーマ（例）
Codex は SQLAlchemy/SQLModel で実装し、マイグレーションは Alembic を使う。

---

## 5. 通信仕様（HTTP + WebSocket）

### 5.1 HTTP（最小）
- `GET /` : SPA 配信
- `GET /healthz` : OK
- `GET /api/games` : サーバ保存棋譜一覧（ページング）
- `POST /api/games` : 新規棋譜作成
- `GET /api/games/{game_id}` : 棋譜取得（ツリー含む）
- `PUT /api/games/{game_id}` : メタ/タイトル更新
- `DELETE /api/games/{game_id}` : 削除（任意。UIに出すかは後で）
- `POST /api/import` : テキスト/ファイル内容を渡してインポート（KIF/KIF2/USI auto-detect）
- `GET /api/export/{game_id}?format=kif|kif2|usi` : エクスポート（ダウンロード）

※ 実装を単純にするなら、ゲームのロード/保存もすべて WS 経由にして良い。HTTP は「サーバ一覧」と「エクスポート/インポート」だけでも成立する。

### 5.2 WebSocket（正）
- `GET /ws` : WebSocket 接続（同一ポート）

#### 5.2.1 セッション制御（1セッションのみ）
- サーバは「オーナー接続」を 1 つだけ保持
- 既にオーナーが存在する状態で新規接続が来た場合:
  - 新規接続へ `session:busy` を送信
  - UI は「既存セッションを切って接続しますか？」を表示
  - OK なら `session:takeover` を送る
  - サーバは既存オーナーへ `session:kicked` → 切断
  - 新規接続をオーナーに昇格して `session:granted`
- 既存オーナーが切断されたら、解析は強制 OFF（要件）

#### 5.2.2 メッセージ一覧（提案）
すべて JSON。`type` で分岐。

##### サーバ→クライアント
- `session:granted`
  - payload: `{ game: FullGameState, server_capabilities, engine_status }`
- `session:busy`
  - payload: `{ owner_since, owner_hint }`
- `session:kicked`
  - payload: `{ reason }`
- `game:state`
  - payload: `{ game: FullGameState }`（ツリー + current node + sfen + move list）
- `analysis:update`
  - payload: `{ node_id, elapsed_ms, multipv, lines, bestline }`
- `analysis:stopped`
  - payload: `{ reason }`
- `toast`
  - payload: `{ level, message }`

##### クライアント→サーバ
- `session:takeover`
- `game:new`
  - payload: `{ title?, initial_sfen? }`
- `game:load`
  - payload: `{ game_id }`
- `game:save`
  - payload: `{ game_id, title?, meta?, ui_state?, current_node_id? }`
- `node:play_move`
  - payload: `{ from_node_id, move_usi }`
  - 既存子があるならそこへ移動、なければ新規ノードを追加（分岐）
- `node:jump`
  - payload: `{ node_id }`
- `node:reorder_children`
  - payload: `{ parent_id, ordered_child_ids[] }`
- `node:set_comment`
  - payload: `{ node_id, comment }`
- `analysis:set_enabled`
  - payload: `{ enabled: boolean }`
- `analysis:set_multipv`
  - payload: `{ multipv: int }`
- `analysis:start`
  - payload: `{ node_id }`
- `analysis:stop`

#### 5.2.3 状態同期の原則
- サーバが単一の「正」を持つ（DB + in-memory）
- UI はサーバの `game:state` を描画するだけにする
- UI 側で先読み反映しない（単一ユーザー想定なので体感問題は少ない）

---

## 6. 解析（USI エンジン）仕様

### 6.1 エンジン管理
- EngineManager（サーバ側クラス）
  - エンジンプロセス起動（複数候補から選択）
  - USI handshake: `usi` → `isready` → `usinewgame`
  - setoption:
    - Threads: `Threads`
    - Hash: `USI_Hash` または `Hash`（エンジン差を吸収）
    - MultiPV: `MultiPV`
  - 解析セッションは **1つ**（単一UI/単一セッションのため）

### 6.2 解析開始/停止
- `analysis:start` を受けたら
  - 現在ノードの `position sfen ... moves ...` を組み立て
  - `go infinite`（または `go ponder` 相当）で開始
  - エンジン出力 `info ...` を読み取り、最新の PV 群を保持
  - UI への送信は間引き:
    - 開始 0–5000ms: 500ms 間隔
    - 5000ms 以降: 1000ms 間隔
  - `analysis:stop` または局面変更、WS切断で停止
    - `stop` → `bestmove` を受け取って終了

### 6.3 解析対象の切替
- 局面移動（node:jump / node:play_move）時:
  - 解析ONなら、前解析を stop して新局面で start
- WS切断:
  - 解析を OFF とみなし、エンジンも停止

---

## 7. 棋譜入出力（KIF/KIF2/USI）仕様

### 7.1 基本方針
- パース/書き出しは **サーバ側で正として実装**する
  - UI はテキスト/ファイル内容を送るだけ
  - 形式の揺れ・分岐対応をサーバに集中させる

### 7.2 インポート
- `POST /api/import` または WS `game:import_text`
- auto-detect:
  - KIF: ヘッダ行、手数形式、"手合割" 等の存在
  - KIF2(KI2): "▲７六歩" が連続する短形式など
  - USI: `position sfen ... moves ...`
- 失敗時はエラーメッセージを返す

### 7.3 エクスポート
- 形式選択でダウンロード
- 分岐の表現:
  - KIF/KIF2 は「変化」記法で表現
  - USI は分岐を表現しにくいので、原則「現在の主線」を出力（オプションで "全変化を複数USIとして出す" も可）

---

## 8. 保存（サーバ/ローカル）

### 8.1 サーバ保存
- SQLite に保存（games, nodes, analysis_snapshots）
- UI の「サーバ一覧」から選択してロード

### 8.2 ローカル保存
- エクスポートでファイルをダウンロード（KIF/KIF2/USI）
- 解析履歴や UI 状態はローカルエクスポートに含めない（内部保存のみ）

---

## 9. インストーラ / 起動（run.bat / run.sh）

### 9.1 目的
- 初回: 依存導入（Python venv + pip）→ エンジン/評価関数導入 → 起動
- 2回目以降: そのまま起動
- 起動後: コンソールにアクセスURLを出力
  - `http://localhost:31145`
  - `https://<random>.trycloudflare.com`（Quick Tunnel 成功時）
  - 既存トンネルがあるなら、その情報も併記（list できた範囲）

### 9.2 禁止事項
- 事前常駐が必要な DB（MongoDB/Redis）はインストールしない
- エンジン/評価関数の「再配布」はしない（原則: 公式配布元から取得）
  - ダウンロード前に利用規約/ライセンスURLを表示し同意させる
  - 同意ログを SQLite に保存（日時・対象・URL・hash）

### 9.3 実装構成（提案）
- `installer/run.py`（共通エントリ）
  - OS検出、Pythonバージョンチェック
  - venv 構築
  - pip install -r requirements.txt
  - cloudflared 導入確認
  - Engine/Eval 取得（manifest 参照）
  - DB初期化
  - サーバ起動（uvicorn）
  - cloudflared 起動（オプション）
- `run.bat` / `run.sh` は `python installer/run.py` を呼ぶだけにする

### 9.4 Cloudflare Quick Tunnel
- Quick Tunnel 実行例:
  - `cloudflared tunnel --url http://localhost:31145`
- 注意:
  - cloudflared の config がある場合に Quick Tunnel が動作しないケースがあるため、
    - 作業ディレクトリを一時ディレクトリにして実行する
    - もしくは Quick Tunnel を諦め、既存トンネル（login済み）を案内する

### 9.5 既存トンネルの検出
- `cloudflared tunnel list` を試行し、成功したら一覧を表示
- 既存トンネルを「起動する」かどうかは、ユーザーの環境依存が強いので **このバージョンでは一覧表示まで**を必須要件とする
  - 既存トンネル起動までやる場合は `config.yml` の場所や ingress 設定が必要で、誤爆が怖い

### 9.6 CPU命令セット対応（エンジン選択/ビルド）
- Windows:
  - manifest に複数 variant（AVX2/SSE4.1 等）を持ち、CPU feature detect で最適を選択
- Linux:
  - 公式に適切なバイナリがあるならそれを使用
  - 無い場合はソースからビルド（make）するフローを用意（build-essential の導入が必要になるため、ここは「選択式」にする）

---

## 10. セキュリティ / 安全性

- 単一セッション制御のため、UI 側で「セッション奪取」操作を明示する
- WS メッセージには `session_id` と `owner_token` を持たせ、奪取後の古いクライアントからの操作を無視
- CORS は原則不要（同一オリジン配信）。必要なら allowlist
- ファイルアップロードは「棋譜テキスト」だけに限定（サイズ上限）
- 例外・ログに棋譜全文を吐かない（必要時はサニタイズ）

---

## 11. ロギング / デバッグ

- `logs/app.log`（ローテーション）
- 解析ログは別ファイル（`logs/engine.log`）
- WS の重要イベント（takeover/analysis start/stop）は info で記録
- `GET /healthz` に DB・エンジンの簡易チェックを含める（重くしない）

---

## 12. テスト方針（最低限）

### サーバ
- KIF/KIF2/USI パーサ単体テスト（正常/異常/分岐）
- 分岐ツリー操作（play_move/jump/reorder）のテスト
- WS セッション奪取の競合テスト（同時接続）
- 解析ストリーミングの送信間隔テスト（タイマー）

### フロント
- 盤描画のスナップショットテスト（主要局面）
- ドラッグ操作→USI move 生成のテスト
- session:busy → takeover UI のテスト

---

## 13. リポジトリ構造（Codex 生成ターゲット）

```
shogi-kifu-analyzer/
  README.md
  run.bat
  run.sh
  installer/
    run.py
    manifest.json
    platform/
      windows.py
      linux.py
  server/
    pyproject.toml or requirements.txt
    app/
      main.py                # FastAPI app
      ws.py                  # WS router
      api.py                 # REST endpoints
      db/
        models.py
        session.py
        migrate/             # alembic
      core/
        gametree.py          # Game/Node/operations
        usi_position.py      # SFEN+move list build
        import_kif.py
        import_kif2.py
        import_usi.py
        export_kif.py
        export_kif2.py
        export_usi.py
      engine/
        manager.py           # EngineManager
        usi_protocol.py      # parse info lines, setoption, go/stop
      services/
        state_store.py       # load/save, current state
        analysis_service.py  # start/stop/stream
      utils/
        cpu_detect.py
        cloudflared.py
        logger.py
    assets_web/              # built UI dist (release時)
  web/
    package.json
    vite.config.ts
    src/
      app/
        App.tsx              # single screen
        layout.tsx
      components/
        Board/
          ShogiBoard.tsx     # ported from existing ShogiBoard.jsx
          themeLoader.ts
        KifuTree.tsx
        ControlBar.tsx
        AnalysisPanel.tsx
        Graph.tsx
        SettingsDialog.tsx
        ImportExportDialog.tsx
      ws/
        client.ts            # WS client + message types
      types/
        protocol.ts
    public/
      board-theme/
      sounds/
```

---

## 14. 実装ステップ（Codex に投げる順）

1) サーバ骨格（FastAPI + StaticFiles + WS echo）  
2) SQLite + Game/Node モデル + CRUD  
3) WS: session 制御（busy/takeover）  
4) WS: game state 同期（new/load/play_move/jump）  
5) UI: 盤面表示（ShogiBoard 移植） + WS state反映  
6) 分岐ツリー UI（node children 表示 + jump）  
7) KIF/KIF2/USI import/export（サーバ）  
8) EngineManager + USI info parse  
9) 解析ストリーミング（0.5秒/1秒間引き）  
10) 設定（Threads/Hash/Engine/MultiPV）永続化  
11) インストーラ（venv + cloudflared + engine/eval manifest + 起動URL表示）  
12) 仕上げ（ログ、テスト、例外、ドキュメント）

---

## 15. 付録: installer/manifest.json（例）

```json
{
  "cloudflared": {
    "windows_amd64_url": "https://example.com/cloudflared-windows-amd64.exe",
    "linux_amd64_url": "https://example.com/cloudflared-linux-amd64"
  },
  "engines": [
    {
      "id": "yaneuraou",
      "name": "YaneuraOu",
      "license_url": "https://github.com/yaneurao/YaneuraOu",
      "terms_url": "https://yaneuraou.yaneu.com/2024/07/01/about-the-redistribution-of-yaneuraou/",
      "variants": [
        {
          "os": "windows",
          "arch": "amd64",
          "cpu_features": ["avx2"],
          "url": "https://example.com/yaneuraou-avx2.exe",
          "sha256": "..."
        },
        {
          "os": "windows",
          "arch": "amd64",
          "cpu_features": ["sse4_1"],
          "url": "https://example.com/yaneuraou-sse41.exe",
          "sha256": "..."
        }
      ]
    }
  ],
  "evals": [
    {
      "id": "nnue_example",
      "name": "NNUE Example",
      "license_url": "https://example.com/license",
      "terms_url": "https://example.com/terms",
      "url": "https://example.com/eval.nnue",
      "sha256": "..."
    }
  ]
}
```

---

## 16. 付録: 解析PVの正規化ルール（USI info）

Engine の `info` 行から最低限取得する:
- `multipv N`
- `depth D`
- `seldepth SD`（あれば）
- `nodes`, `nps`, `hashfull`（あれば）
- `score cp X` or `score mate M`
- `pv ...`（USI move list）

UI は `analysis:update` の `lines[]` を描画する。
