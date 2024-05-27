from fastapi import HTTPException, status, Depends, APIRouter
from app.utils.database import SessionLocal
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.model.model import Documents
from typing import Annotated
from app.utils.auth import get_current_user, get_db
from sqlalchemy.orm import Session
from app.utils.parser import parse_pdf

router = APIRouter(
    prefix="/poll",
    tags=["poll"]
)

@router.get("/", status_code=status.HTTP_200_OK)
async def cron():
    db_dependency = Annotated[Session, Depends(get_db)]
    db: db_dependency = SessionLocal()
    documents_for_processing = db.query(Documents).filter_by(processed=False).all()
    for document in documents_for_processing:
        await parse_pdf({"id": 'CRON', "username": 'CRON'}, db, document.filename)
    return {"message": f"{len(documents_for_processing)} documents processed by CRON"}

            
scheduler = AsyncIOScheduler()
scheduler.add_job(cron, 'interval', minutes=10)  
scheduler.start()