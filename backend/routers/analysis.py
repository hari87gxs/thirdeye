import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.orm import Session
from database import get_db
from models import Document, AgentResult, GroupAgentResult, AgentType, AgentStatus, DocumentStatus, RawTransaction, StatementMetrics, AggregatedMetrics
from schemas import AgentResultResponse, GroupAgentResultResponse, DocumentAnalysisResponse, DocumentResponse, TransactionResponse, StatementMetricsResponse, AggregatedMetricsResponse
from orchestrator import run_all_agents

logger = logging.getLogger("ThirdEye.Analysis")

router = APIRouter()


@router.post("/analyze/{document_id}")
async def analyze_document(
    document_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Trigger all 4 agents for a specific document."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status == DocumentStatus.PROCESSING.value:
        raise HTTPException(status_code=409, detail="Document is already being analyzed")

    # Update status
    doc.status = DocumentStatus.PROCESSING.value
    db.commit()

    # Create agent result placeholders
    for agent_type in AgentType:
        existing = (
            db.query(AgentResult)
            .filter(AgentResult.document_id == document_id, AgentResult.agent_type == agent_type.value)
            .first()
        )
        if not existing:
            agent_result = AgentResult(
                document_id=document_id,
                upload_group_id=doc.upload_group_id,
                agent_type=agent_type.value,
                status=AgentStatus.PENDING.value,
            )
            db.add(agent_result)
    db.commit()

    # Run agents in background
    background_tasks.add_task(run_all_agents, document_id)

    return {"message": "Analysis started", "document_id": document_id}


@router.post("/analyze/group/{upload_group_id}")
async def analyze_group(
    upload_group_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Trigger analysis for all documents in an upload group."""
    docs = db.query(Document).filter(Document.upload_group_id == upload_group_id).all()
    if not docs:
        raise HTTPException(status_code=404, detail="No documents found for this upload group")

    for doc in docs:
        doc.status = DocumentStatus.PROCESSING.value
        for agent_type in AgentType:
            existing = (
                db.query(AgentResult)
                .filter(AgentResult.document_id == doc.id, AgentResult.agent_type == agent_type.value)
                .first()
            )
            if not existing:
                agent_result = AgentResult(
                    document_id=doc.id,
                    upload_group_id=upload_group_id,
                    agent_type=agent_type.value,
                    status=AgentStatus.PENDING.value,
                )
                db.add(agent_result)
    db.commit()

    for doc in docs:
        background_tasks.add_task(run_all_agents, doc.id)

    return {
        "message": f"Analysis started for {len(docs)} document(s)",
        "upload_group_id": upload_group_id,
        "document_ids": [d.id for d in docs],
    }


@router.get("/results/group/{upload_group_id}")
def get_group_results(upload_group_id: str, db: Session = Depends(get_db)):
    """Get results for all documents in an upload group, including group-level agent results."""
    docs = db.query(Document).filter(Document.upload_group_id == upload_group_id).all()
    if not docs:
        raise HTTPException(status_code=404, detail="No documents found for this upload group")

    per_doc_results = []
    for doc in docs:
        results = db.query(AgentResult).filter(AgentResult.document_id == doc.id).all()
        per_doc_results.append({
            "document": DocumentResponse.model_validate(doc).model_dump(),
            "agents": {
                r.agent_type: AgentResultResponse.model_validate(r).model_dump() for r in results
            },
        })

    # Group-level agent results
    group_agent_results = (
        db.query(GroupAgentResult)
        .filter(GroupAgentResult.upload_group_id == upload_group_id)
        .all()
    )

    # Aggregated metrics
    agg = db.query(AggregatedMetrics).filter(AggregatedMetrics.upload_group_id == upload_group_id).first()

    return {
        "upload_group_id": upload_group_id,
        "documents": per_doc_results,
        "group_agents": {
            r.agent_type: GroupAgentResultResponse.model_validate(r).model_dump()
            for r in group_agent_results
        } if group_agent_results else {},
        "aggregated_metrics": AggregatedMetricsResponse.model_validate(agg).model_dump() if agg else None,
    }


@router.get("/results/{document_id}")
def get_results(document_id: str, db: Session = Depends(get_db)):
    """Get all agent results for a document."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    results = db.query(AgentResult).filter(AgentResult.document_id == document_id).all()

    return {
        "document": DocumentResponse.model_validate(doc).model_dump(),
        "agents": {
            r.agent_type: AgentResultResponse.model_validate(r).model_dump() for r in results
        },
    }


@router.get("/results/{document_id}/{agent_type}")
def get_agent_result(document_id: str, agent_type: str, db: Session = Depends(get_db)):
    """Get a specific agent's result for a document."""
    result = (
        db.query(AgentResult)
        .filter(AgentResult.document_id == document_id, AgentResult.agent_type == agent_type)
        .first()
    )
    if not result:
        raise HTTPException(status_code=404, detail=f"No {agent_type} result found for this document")

    return AgentResultResponse.model_validate(result).model_dump()


@router.get("/status/group/{upload_group_id}")
def get_group_status(upload_group_id: str, db: Session = Depends(get_db)):
    """Get processing status for an upload group — used by frontend polling."""
    docs = db.query(Document).filter(Document.upload_group_id == upload_group_id).all()
    if not docs:
        raise HTTPException(status_code=404, detail="No documents found for this upload group")

    total = len(docs)
    completed = sum(1 for d in docs if d.status == DocumentStatus.COMPLETED.value)
    failed = sum(1 for d in docs if d.status == DocumentStatus.FAILED.value)
    processing = sum(1 for d in docs if d.status == DocumentStatus.PROCESSING.value)

    # Group-level agent status
    group_agent_results = (
        db.query(GroupAgentResult)
        .filter(GroupAgentResult.upload_group_id == upload_group_id)
        .all()
    )
    group_agents_status = {
        r.agent_type: r.status for r in group_agent_results
    }

    # Overall group status
    if all(d.status == DocumentStatus.COMPLETED.value for d in docs):
        if len(docs) > 1 and group_agent_results:
            if all(r.status == AgentStatus.COMPLETED.value for r in group_agent_results):
                overall = "completed"
            elif any(r.status == AgentStatus.FAILED.value for r in group_agent_results):
                overall = "completed"  # individual docs done, group analysis partial
            else:
                overall = "group_processing"
        else:
            overall = "completed"
    elif failed == total:
        overall = "failed"
    elif processing > 0 or completed < total:
        overall = "processing"
    else:
        overall = "uploaded"

    return {
        "upload_group_id": upload_group_id,
        "overall_status": overall,
        "total_documents": total,
        "completed": completed,
        "processing": processing,
        "failed": failed,
        "documents": [
            {"id": d.id, "filename": d.original_filename, "status": d.status}
            for d in docs
        ],
        "group_agents": group_agents_status,
    }


# ─── Extraction Data Endpoints ────────────────────────────────────────────────

@router.get("/transactions/{document_id}")
def get_transactions(
    document_id: str,
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    transaction_type: str = Query(None, description="Filter by: credit, debit"),
    category: str = Query(None, description="Filter by category"),
    db: Session = Depends(get_db),
):
    """Get extracted transactions for a document."""
    query = db.query(RawTransaction).filter(RawTransaction.document_id == document_id)
    if transaction_type:
        query = query.filter(RawTransaction.transaction_type == transaction_type)
    if category:
        query = query.filter(RawTransaction.category == category)

    total = query.count()
    txns = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "transactions": [TransactionResponse.model_validate(t).model_dump() for t in txns],
    }


@router.get("/metrics/{document_id}")
def get_metrics(document_id: str, db: Session = Depends(get_db)):
    """Get computed metrics for a document."""
    metrics = db.query(StatementMetrics).filter(StatementMetrics.document_id == document_id).first()
    if not metrics:
        raise HTTPException(status_code=404, detail="Metrics not found — run extraction first")
    return StatementMetricsResponse.model_validate(metrics).model_dump()


@router.get("/metrics/group/{upload_group_id}")
def get_group_metrics(upload_group_id: str, db: Session = Depends(get_db)):
    """Get aggregated metrics for an upload group."""
    agg = db.query(AggregatedMetrics).filter(AggregatedMetrics.upload_group_id == upload_group_id).first()
    per_statement = (
        db.query(StatementMetrics)
        .filter(StatementMetrics.upload_group_id == upload_group_id)
        .all()
    )
    return {
        "aggregated": AggregatedMetricsResponse.model_validate(agg).model_dump() if agg else None,
        "per_statement": [StatementMetricsResponse.model_validate(m).model_dump() for m in per_statement],
    }
