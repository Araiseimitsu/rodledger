PROJECT CORE RULE（最小憲法）
1. 原則
技術は可変、設計思想は固定

依存は一方向

再現性を最優先

AIが迷わない構造にする


2. 全体構造
project-root/
├─ backend/
├─ frontend/
├─ docker/
├─ tests/
├─ .docs/
└─ README.md
勝手に構造を崩さない。

3. Frontend Rule（技術非依存）
レイヤー固定
Presentation → State → Application → Infrastructure
Shared（utils / types / constants）は全層参照可。
禁止
UIでAPI直呼び

レイヤー逆流

循環依存

1000行超の単一ファイル


4. Backend Rule（Python）
必須
Python管理は uv

pyproject.toml + uv.lock 使用

uv.lock は必ずコミット

禁止
pip単独使用

poetry併用

requirements.txt手動管理

直接 python 実行

実行例
uv venv
uv add fastapi
uv run python app/main.py
uv run pytest

5. Docker Rule
Docker内でも uv 使用

lockベースで依存同期

開発と本番の差異を最小化


6. テスト方針
Application層は必ずテスト

Infrastructureはモック可能設計

UIテストは任意


7. 強制分離
必ず外部化：
API通信

状態管理

ビジネスロジック

型・定数

共通関数

UI内に閉じ込めない。

8. AI実装規律
AIは：
レイヤー越境しない

APIをUIに直書きしない

uv前提で依存追加

テスト可能構造で実装


