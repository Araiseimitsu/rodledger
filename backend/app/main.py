"""
RodLedger β - FastAPI アプリケーション
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.transactions import router as api_router
from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """アプリケーションライフサイクル管理"""
    # 起動時: データベース初期化
    await init_db()
    yield
    # 終了時: クリーンアップ（必要に応じて）


app = FastAPI(
    title="RodLedger β",
    description="NC旋盤用棒材管理デモAPI",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS設定（フロントエンド連携用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# APIルーター登録
app.include_router(api_router)


@app.get("/")
async def root():
    """ヘルスチェック"""
    return {"status": "ok", "app": "RodLedger β", "version": "0.1.0"}
