import os
from typing import Annotated
from fastapi import FastAPI, status, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.utils.auth import router as auth_router
from app.routers.routes import router as upload_router
from sqlalchemy.orm import Session
from app.utils.database import engine
import app.model.model as models
from dotenv import load_dotenv
from app.utils.auth import get_current_user, get_db
from fastapi_limiter import FastAPILimiter
from fastapi_limiter.depends import RateLimiter
from contextlib import asynccontextmanager
from app.routers.scheduler import router as scheduler_router
import redis.asyncio as redis

redis_host = os.getenv('REDIS_HOST', 'localhost')
redis_port = os.getenv('REDIS_PORT', 6379)

redis_url = f"redis://{redis_host}:{redis_port}"

@asynccontextmanager
async def lifespan(_: FastAPI):
    redis_connection = redis.from_url(redis_url, encoding="utf8")
    await FastAPILimiter.init(redis_connection)
    yield
    await FastAPILimiter.close()

app: FastAPI = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(scheduler_router)

models.Base.metadata.create_all(bind=engine)

db_dependency = Annotated[Session, Depends(get_db)]
user_dependency = Annotated[dict, Depends(get_current_user)]

@app.get("/", status_code=status.HTTP_200_OK,
         dependencies=[Depends(RateLimiter(times=5, minutes=1))])
async def health_check(user: user_dependency, db: db_dependency):
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication Failed"
        )
    return {"user": user}

@app.post("/webhook", status_code=status.HTTP_200_OK)
async def handle_event_webhook(body: dict):
    return body