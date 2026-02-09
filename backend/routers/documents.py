import os
import uuid
import logging
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Document, DocumentStatus, User
from schemas import DocumentResponse, UploadResponse
from config import settings
from routers.auth import get_current_user_dep
import fitz  # PyMuPDF

logger = logging.getLogger("ThirdEye.Documents")

router = APIRouter()


@router.post("/upload", response_model=UploadResponse)
async def upload_documents(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """Upload one or more PDF bank statements for analysis."""
    upload_group_id = str(uuid.uuid4())
    documents = []

    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"Only PDF files are supported. Got: {file.filename}")

        # Generate unique filename
        file_id = str(uuid.uuid4())
        safe_filename = f"{file_id}.pdf"
        file_path = os.path.join(settings.UPLOAD_DIR, safe_filename)

        # Save file
        content = await file.read()
        file_size = len(content)

        if file_size > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"File {file.filename} exceeds {settings.MAX_FILE_SIZE_MB}MB limit",
            )

        with open(file_path, "wb") as f:
            f.write(content)

        # Get page count
        try:
            doc = fitz.open(file_path)
            page_count = doc.page_count
            doc.close()
        except Exception:
            page_count = None

        # Create DB record
        db_doc = Document(
            id=file_id,
            user_id=current_user.id,
            filename=safe_filename,
            original_filename=file.filename,
            file_path=file_path,
            file_size=file_size,
            page_count=page_count,
            status=DocumentStatus.UPLOADED.value,
            upload_group_id=upload_group_id,
        )
        db.add(db_doc)
        documents.append(db_doc)

    db.commit()
    for doc in documents:
        db.refresh(doc)

    logger.info(f"Uploaded {len(documents)} document(s) in group {upload_group_id}")

    return UploadResponse(
        upload_group_id=upload_group_id,
        documents=[DocumentResponse.model_validate(d) for d in documents],
        message=f"Successfully uploaded {len(documents)} document(s)",
    )


@router.get("/documents", response_model=list[DocumentResponse])
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """List all uploaded documents for the current user."""
    docs = (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .all()
    )
    return [DocumentResponse.model_validate(d) for d in docs]


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """Get a specific document (must belong to current user)."""
    doc = db.query(Document).filter(Document.id == document_id, Document.user_id == current_user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentResponse.model_validate(doc)


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """Delete a document and its associated data."""
    doc = db.query(Document).filter(Document.id == document_id, Document.user_id == current_user.id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete file from disk
    if os.path.exists(doc.file_path):
        os.remove(doc.file_path)

    db.delete(doc)
    db.commit()
    return {"message": "Document deleted successfully"}


@router.get("/groups")
def list_upload_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_dep),
):
    """List all upload groups with their documents for the current user."""
    docs = (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .all()
    )
    groups = {}
    for doc in docs:
        gid = doc.upload_group_id
        if gid not in groups:
            groups[gid] = {
                "upload_group_id": gid,
                "documents": [],
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
        groups[gid]["documents"].append(DocumentResponse.model_validate(doc).model_dump())

    return list(groups.values())
