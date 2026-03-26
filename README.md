# RodLedger β

NC旋盤用棒材（SUM22 φ8.0 × 2500mm）の発注・入庫・持ち出し・戻しを履歴ベースで管理するデモアプリ。

## 概要

- **在庫ではなく履歴を管理する** - 在庫は履歴の集計結果として算出
- ロット単位での管理
- 重量ベースでの金額計算

## 技術スタック

| レイヤー | 技術 |
|---------|------|
| Backend | Python 3.13 + FastAPI + SQLite |
| Frontend | Svelte 5 + TailwindCSS |
| パッケージ管理 | uv (Python), pnpm (Node.js) |

## プロジェクト構成

```
rodledger_beta/
├── backend/
│   ├── app/
│   │   ├── api/          # APIルーター
│   │   ├── models/       # データモデル
│   │   ├── services/     # ビジネスロジック
│   │   ├── database.py   # DB接続
│   │   └── main.py       # FastAPIアプリ
│   ├── data/             # SQLiteデータファイル
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── lib/          # 共通モジュール
│   │   └── routes/       # ページコンポーネント
│   └── package.json
└── .docs/                # 仕様書・デザインサンプル
```

## セットアップ

### 前提条件

- Python 3.13+
- Node.js 18+
- uv (Python パッケージマネージャー)
- pnpm (Node.js パッケージマネージャー)

### Backend セットアップ

```bash
cd backend
uv venv
uv sync
```

`uv run` で起動する前に、必ず `uv sync` を実行してください。これで backend の実行環境に `uvicorn` などの依存が入ります。

### Frontend セットアップ

```bash
cd frontend
pnpm install
```

### フロントエンドの API 接続先

本番配信ではフロントエンドも backend の `http://localhost:8020` から同一オリジンで配信します。別ホストへ接続する場合は、`frontend/.env` に `VITE_API_BASE_URL` を設定してください。

例:

```bash
VITE_API_BASE_URL=http://社内サーバーPCのIPまたはホスト名:8020/api
```

## 起動方法

### 1. Backend 起動

```bash
cd backend
uv run python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8020
```

APIサーバーが http://localhost:8020 で起動し、build 済み frontend も同じ URL で配信されます。ほか PC から使う場合は `http://社内サーバーPCのIPまたはホスト名:8020` でアクセスしてください。

起動時に `No module named uvicorn` が出る場合は、`backend` ディレクトリで `uv sync` を再実行してから、もう一度起動してください。

### 3. 社内サーバー / NSSM 運用メモ

- SQLite は `backend/data/rodledger.db` を直接更新するため、DB ファイルはネットワーク共有ではなくローカルディスクに置いてください。
- NSSM の `AppDirectory` は `backend` ディレクトリに設定してください。作業ディレクトリがずれると DB パスやログ確認が不安定になります。
- 社内LANから直接 frontend を配信する場合は backend を `--host 0.0.0.0` で待ち受けてください。localhost バインドのままだと他PCから接続できません。
- frontend を別オリジンで配信する場合は backend 側に `CORS_ALLOW_ORIGINS` で許可元を追加してください。例: `CORS_ALLOW_ORIGINS=http://192.168.0.10:5173,http://server-pc:5173`
- Windows サーバーでは SQLite のファイルロック待ちが起きやすいため、backend 側で `WAL` と `busy_timeout` を有効化しています。
- それでも入出庫で待ちが出る場合は、まず `/api/health` が応答するかと、サービス標準出力に `database is locked` が出ていないかを確認してください。

### 2. Frontend build

```bash
cd frontend
pnpm build
```

build 出力は `frontend/build` に作成され、backend から配信されます。

## 機能

### ダッシュボード (/)
- 現在在庫（kg / 本数）
- 在庫金額
- 最近の取引履歴

### 入庫登録 (/in)
- ロット選択
- 数量入力（重量自動計算）
- メモ入力

### 出庫・戻し (/out)
- 出庫/戻しモード切替
- 数量入力
- メモ入力

### 履歴 (/history)
- 時系列表示
- 種別フィルタ
- 検索機能
- 削除機能

## API エンドポイント

| メソッド | パス | 説明 |
|---------|------|------|
| GET | /api/dashboard | ダッシュボード統計 |
| GET | /api/transactions | トランザクション一覧 |
| POST | /api/transactions | トランザクション作成 |
| PUT | /api/transactions/{id} | トランザクション更新 |
| DELETE | /api/transactions/{id} | トランザクション削除 |
| GET | /api/lots/{material_id} | ロット一覧 |

## 在庫計算式

```
在庫重量 = Σ(入庫 + 戻し) - Σ(出庫)
在庫金額 = Σ(入庫金額 + 戻し金額) - Σ(出庫金額)
```

## ライセンス

MIT
