"""
RodLedger β - FastAPI アプリケーション
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.api.transactions import router as api_router
from app.database import init_db


FRONTEND_BUILD_DIR = Path(__file__).resolve().parents[2] / "frontend" / "build"


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


@app.get("/api/health")
async def health_check():
    """ヘルスチェック"""
    return {"status": "ok", "app": "RodLedger β", "version": "0.1.0"}


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    """build 済みフロントエンドを配信する"""
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")

    if not FRONTEND_BUILD_DIR.exists():
        raise HTTPException(
            status_code=503,
            detail="Frontend build not found. Run pnpm build in frontend first.",
        )

    requested_file = (FRONTEND_BUILD_DIR / full_path).resolve()
    build_root = FRONTEND_BUILD_DIR.resolve()

    try:
        requested_file.relative_to(build_root)
    except ValueError:
        requested_file = build_root / "index.html"

    if requested_file.is_file():
        return FileResponse(requested_file)

    index_file = build_root / "index.html"
    if index_file.is_file():
        return FileResponse(index_file)

    raise HTTPException(
        status_code=503,
        detail="Frontend build not found. Run pnpm build in frontend first.",
    )
