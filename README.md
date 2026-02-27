# Shogi Kifu Analyzer (Minimal Build)

`shogi_kifu_analyzer_design.md` をベースにした最小構成プロトタイプです。

## 実装済み (最小)

- FastAPI ベースの HTTP + WebSocket 骨格
- SQLite (`games`, `nodes`, `analysis_snapshots`, `app_state`)
- 分岐付きゲーム木 (`node:play_move`, `node:jump`, `node:reorder_children`, `node:set_comment`)
- USI `position ... moves ...` の import/export
- 単一セッション制御 (`session:busy` / `session:takeover`)
- 静的UI (ビルド不要) + `Sample` の `sfen.js`, `usi.js`, `themeLoader.js`, `board-theme` 資産流用

## 未実装 / スタブ

- KIF / KIF2(KI2) import/export
- USI エンジン連携 / 解析ストリーミング
- React/Vite フロント移植 (`ShogiBoard.jsx` は `docs/reference_sample/ShogiBoard.jsx` に参照コピー)

## 起動

`installer/run.py` は `.venv` を作成し、依存未導入なら手動インストール手順を表示して停止します。

- Windows: `run.bat`
- Linux/macOS: `sh run.sh`

