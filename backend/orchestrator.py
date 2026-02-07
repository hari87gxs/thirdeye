import logging
from datetime import datetime, timezone
from database import SessionLocal
from models import Document, AgentResult, AgentType, AgentStatus, DocumentStatus

logger = logging.getLogger("ThirdEye.Orchestrator")


def run_all_agents(document_id: str):
    """Run all 4 agents for a document. Called as a background task."""
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.error(f"Document {document_id} not found")
            return

        logger.info(f"🔮 Starting analysis for document: {doc.original_filename}")

        # Import agents
        from agents.extraction import ExtractionAgent
        from agents.insights import InsightsAgent
        from agents.tampering import TamperingAgent
        from agents.fraud import FraudAgent

        agents = [
            (AgentType.EXTRACTION, ExtractionAgent()),
            (AgentType.TAMPERING, TamperingAgent()),
            (AgentType.FRAUD, FraudAgent()),
            (AgentType.INSIGHTS, InsightsAgent()),  # Runs last — needs extraction data
        ]

        for agent_type, agent in agents:
            agent_result = (
                db.query(AgentResult)
                .filter(
                    AgentResult.document_id == document_id,
                    AgentResult.agent_type == agent_type.value,
                )
                .first()
            )

            if not agent_result:
                agent_result = AgentResult(
                    document_id=document_id,
                    upload_group_id=doc.upload_group_id,
                    agent_type=agent_type.value,
                )
                db.add(agent_result)
                db.flush()
            elif agent_result.status == AgentStatus.COMPLETED.value:
                logger.info(f"  ⏭️  Skipping {agent_type.value} agent (already completed)")
                continue

            # Mark as running
            agent_result.status = AgentStatus.RUNNING.value
            agent_result.started_at = datetime.now(timezone.utc)
            db.commit()

            try:
                logger.info(f"  🤖 Running {agent_type.value} agent...")
                result = agent.run(document_id, db)

                agent_result.status = AgentStatus.COMPLETED.value
                agent_result.results = result.get("results", {})
                agent_result.summary = result.get("summary", "")
                agent_result.risk_level = result.get("risk_level", "low")
                agent_result.completed_at = datetime.now(timezone.utc)
                db.commit()

                logger.info(f"  ✅ {agent_type.value} agent completed (risk: {agent_result.risk_level})")

            except Exception as e:
                logger.error(f"  ❌ {agent_type.value} agent failed: {str(e)}")
                agent_result.status = AgentStatus.FAILED.value
                agent_result.error_message = str(e)
                agent_result.completed_at = datetime.now(timezone.utc)
                db.commit()

        # Mark document as completed
        doc.status = DocumentStatus.COMPLETED.value
        db.commit()
        logger.info(f"🔮 Analysis complete for: {doc.original_filename}")

    except Exception as e:
        logger.error(f"Orchestrator error for document {document_id}: {str(e)}")
        try:
            doc = db.query(Document).filter(Document.id == document_id).first()
            if doc:
                doc.status = DocumentStatus.FAILED.value
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
