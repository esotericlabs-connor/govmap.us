from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import members, pipeline_status

app = FastAPI(title="GovMap API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(members.router)
app.include_router(pipeline_status.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
