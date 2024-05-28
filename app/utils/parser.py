import os
import json
from fastapi import HTTPException, status, Depends
from sqlalchemy.orm import Session
from PyPDF2 import PdfReader
from app.model.model import Documents
import redis.asyncio as redis
from datetime import datetime
from typing import Annotated
import httpx
from app.utils.auth import get_current_user, get_db

redis_host = os.getenv('REDIS_HOST', 'localhost')
redis_port = os.getenv('REDIS_PORT', 6379)

redis_client = redis.Redis(host=redis_host, port=int(redis_port), db=0)

db_dependency = Annotated[Session, Depends(get_db)]
user_dependency = Annotated[dict, Depends(get_current_user)]

stored_dir = "uploaded_pdfs"

async def parse_pdf(user: user_dependency, db: db_dependency, file_name: str):
    result = {"text": {}}
    sanitized_filename = file_name.replace(" ", "_").replace("-", "_").replace("/", "_").lower() 
    file_path = db.query(Documents).filter_by(filename=sanitized_filename).first().file_location

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    

    with open(file_path, 'rb') as file:
        pdf = PdfReader(file)
        for index, page in enumerate(pdf.pages):
            page_text = page.extract_text()
            if page_text:
                result["text"][index] = page_text.split('\n')
    
    file_key = f"PDF:{user['id']}:{sanitized_filename}"
    await redis_client.setex(file_key, 600, json.dumps(result))  # 10 minutes
    if user["id"] == "CRON":
        result["redis-key"] = file_key
        os.makedirs(f"{stored_dir}/CRON", exist_ok=True)
        with open(f"{stored_dir}/CRON/{file_name}.json", 'w') as json_file:
            json_file.write(json.dumps(result, indent=4))
        document = db.query(Documents).filter_by(filename=sanitized_filename).first()
        document.processed = True
        db.commit()

    document = db.query(Documents).filter_by(filename=sanitized_filename, user_id=user['id']).first()
    if document:
        document.processed = True
        db.commit()

    event = {
        "event": "text_extracted",
        "id": user['id'],
        "username": user['username'],
        "filename": sanitized_filename,
        "event_time": datetime.utcnow().isoformat()
    }
    webhook_url = "http://127.0.0.1:8000/webhook"
    async with httpx.AsyncClient() as client:
        await client.post(webhook_url, json=event)
    
    return {"redis-key": file_key, "text": result['text']}