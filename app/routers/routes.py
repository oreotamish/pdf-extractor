from fastapi import APIRouter, File, UploadFile, Depends, HTTPException
from datetime import datetime  
from app.model.model import Documents
from PyPDF2 import PdfReader
from sqlalchemy.orm import Session
from pydantic import BaseModel
from fastapi_limiter.depends import RateLimiter
from typing import Annotated, IO
from app.utils.auth import get_current_user, get_db
import redis.asyncio as redis
import json
import os
from starlette import status
import httpx
import aiofiles
import filetype
from app.utils.parser import parse_pdf

router = APIRouter(
    prefix="/pdf",
    tags=["pdf"]
)
redis_host = os.getenv('REDIS_HOST', 'localhost')
redis_port = os.getenv('REDIS_PORT', 6379)

redis_client = redis.Redis(host=redis_host, port=int(redis_port), db=0)

stored_dir = "uploaded_pdfs"
os.makedirs(stored_dir, exist_ok=True)

db_dependency = Annotated[Session, Depends(get_db)]
user_dependency = Annotated[dict, Depends(get_current_user)]

@router.post('/upload', status_code=status.HTTP_201_CREATED, dependencies=[Depends(RateLimiter(times=5, minutes=1))])
async def upload_pdf(user: user_dependency, db: db_dependency, file: UploadFile = File(...)):
    """
        Upload a PDF file to the server. This does not process the PDF for text. 

    SCHEMA {
        id = Column(Integer, primary_key=True, index=True)
        filename = Column(String)
        file_location = Column(String)
        file_size = Column(Integer)
        created_at = Column(DateTime)
        user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'))
        processed = Column(Boolean, default=0)
    }
    """
    validate_file_type(file.file)
    sanitized_filename = file.filename.replace(" ", "_").replace("-", "_").replace("/", "_").lower() 
    # check = db.query(Documents).filter(Documents.user_id == user['id'], Documents.filename == sanitized_filename).first()
    check = os.path.exists(os.path.join(stored_dir, f"{user['id']}_{user['username']}", sanitized_filename))
    print(check)
    if check:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="File already exists."
        )

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication Failed"
        )
    max_file_size = 104857600 #100MB
    content = await file.read()

    if len(content) >= max_file_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File size is too large. Max file size is {max_file_size/1024/1024} MB"
        )
    user_dir = os.path.join(stored_dir, f"{user['id']}_{user['username']}")
    os.makedirs(user_dir, exist_ok=True)

    file_location = os.path.join(user_dir, f"{sanitized_filename}")

    document = Documents(
        filename=sanitized_filename,
        file_location=file_location,
        file_size=round(len(content)/1024/1024, 1),
        created_at=datetime.now(),
        user_id=user['id'],
        processed=False
    )
    db.add(document)
    db.commit()
    async with aiofiles.open(file_location, 'wb') as out:
        await out.write(content)
    event = {
        "event": "upload",
        "id": user['id'],
        "username": user['username'],
        "filename": sanitized_filename,
        "event_time": datetime.utcnow().isoformat()
    }
    webhook_url = "http://127.0.0.1:8000/webhook"
    async with httpx.AsyncClient() as client:
        await client.post(webhook_url, json=event)

    return {"info": f"file '{sanitized_filename}' saved at '{file_location}'"}

def validate_file_type(file: IO):
    accepted_file_types = ['pdf']

    file_type = filetype.guess(file)
    if file_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unable to determine file type",
        )
    
    if file_type.extension.lower() not in accepted_file_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {file_type.extension}",
        )

@router.get('/', status_code=status.HTTP_200_OK, dependencies=[Depends(RateLimiter(times=5, minutes=1))])
async def get_all_pdfs(user: user_dependency):
    """
        Get list of all the PDFs uploaded by the user.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    user_dir = os.path.join(stored_dir, f"{user['id']}_{user['username']}")
    os.makedirs(user_dir, exist_ok=True)
    files = os.listdir(user_dir)
    return {"files": files}

@router.get('/metadata/{file_name}', status_code=status.HTTP_200_OK, dependencies=[Depends(RateLimiter(times=5, minutes=1))])
async def get_pdf_metadata(user: user_dependency, db: db_dependency, file_name: str):
    """
        Get metadata of a specific PDF file.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    result = db.query(Documents).filter(Documents.user_id == user['id'], Documents.filename == file_name).first()
    
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    return {"metadata": result}

@router.delete('/delete/{file_name}', status_code=status.HTTP_200_OK, dependencies=[Depends(RateLimiter(times=5, minutes=1))])
async def delete_pdf(user: user_dependency, db: db_dependency, file_name: str):
    """
        Delete a specific PDF file.
    """
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    
    result = db.query(Documents).filter(Documents.user_id == user['id'], Documents.filename == file_name).first()
    # result = db.query(Documents).filter().all()
    
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )
    else:
        db.delete(result)
        db.commit()
        os.remove(result.file_location)
        return {"info": f"{file_name} deleted"}

@router.get('/text/{file_name}', status_code=status.HTTP_200_OK, dependencies=[Depends(RateLimiter(times=5, minutes=1))])
async def parse_pdf_for_text(user: user_dependency, db: db_dependency, file_name: str):
    """
        Parse the PDF file for text and return the text and redis-key where it is stored.
    """
    sanitized_filename = file_name.replace(" ", "_").replace("-", "_").replace("/", "_").lower() 
    file_path = db.query(Documents).filter_by(filename=sanitized_filename).first().file_location

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found")
    return await parse_pdf(user, db, file_name)

@router.get('/text-redis/{file_key}', status_code=status.HTTP_200_OK, dependencies=[Depends(RateLimiter(times=5, minutes=1))])
async def get_temporary_pdf_text_from_redis(user: user_dependency, file_key: str):
    """
        Get the text of the PDF file from redis using the redis-key.
    """
    file_key_parts = file_key.split(":")
    if int(file_key_parts[1]) != user['id']:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated for this redis key user_id"
        )
    result = await redis_client.get(file_key)
    ttl = await redis_client.ttl(file_key)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Key not found"
        )
    text = json.loads(result)['text']
    return {"ttl": f"{ttl} Seconds Left", "text": text}
