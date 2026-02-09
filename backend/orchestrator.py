import logging
from datetime import datetime, timezone
from database import SessionLocal
from models import (
    Document, AgentResult, GroupAgentResult,
    AgentType, AgentStatus, DocumentStatus,
)

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

        # Check if all documents in the group are now completed → trigger group agents
        if doc.upload_group_id:
            group_docs = (
                db.query(Document)
                .filter(Document.upload_group_id == doc.upload_group_id)
                .all()
            )
            all_done = all(d.status == DocumentStatus.COMPLETED.value for d in group_docs)
            if all_done and len(group_docs) > 1:
                logger.info(
                    f"🔗 All {len(group_docs)} documents in group {doc.upload_group_id} completed "
                    f"— triggering group-level agents"
                )
                try:
                    run_group_agents(doc.upload_group_id)
                except Exception as ge:
                    logger.error(f"Group agents failed for {doc.upload_group_id}: {ge}")

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


def run_group_agents(upload_group_id: str):
    """Run group-level aggregation agents after all documents in a group are processed.

    This runs AFTER all individual document agents have completed.
    It performs cross-statement analysis for:
      - Insights: aggregated trends, multi-month patterns
      - Fraud: cross-statement anomaly detection
      - Tampering: cross-document consistency checks
    """
    db = SessionLocal()
    try:
        docs = (
            db.query(Document)
            .filter(Document.upload_group_id == upload_group_id)
            .all()
        )
        if not docs:
            logger.error(f"No documents found for group {upload_group_id}")
            return

        # Check if all documents have completed extraction
        all_completed = all(d.status == DocumentStatus.COMPLETED.value for d in docs)
        if not all_completed:
            logger.warning(
                f"  ⏳ Not all documents completed yet for group {upload_group_id} "
                f"({sum(1 for d in docs if d.status == DocumentStatus.COMPLETED.value)}/{len(docs)})"
            )
            return

        if len(docs) < 2:
            logger.info(f"  📄 Single document in group {upload_group_id} — skipping group agents")
            return

        logger.info(
            f"🔮 Starting GROUP-LEVEL analysis for {len(docs)} documents "
            f"(group: {upload_group_id})"
        )

        from agents.insights import InsightsAgent
        from agents.fraud import FraudAgent
        from agents.tampering import TamperingAgent

        group_agents = [
            (AgentType.TAMPERING, TamperingAgent()),
            (AgentType.FRAUD, FraudAgent()),
            (AgentType.INSIGHTS, InsightsAgent()),  # Last — needs extraction data
        ]

        for agent_type, agent in group_agents:
            # Get or create group agent result
            group_result = (
                db.query(GroupAgentResult)
                .filter(
                    GroupAgentResult.upload_group_id == upload_group_id,
                    GroupAgentResult.agent_type == agent_type.value,
                )
                .first()
            )

            if not group_result:
                group_result = GroupAgentResult(
                    upload_group_id=upload_group_id,
                    agent_type=agent_type.value,
                )
                db.add(group_result)
                db.flush()
            elif group_result.status == AgentStatus.COMPLETED.value:
                logger.info(f"  ⏭️  Skipping group {agent_type.value} (already completed)")
                continue

            group_result.status = AgentStatus.RUNNING.value
            group_result.started_at = datetime.now(timezone.utc)
            db.commit()

            try:
                logger.info(f"  🤖 Running GROUP {agent_type.value} agent...")
                result = agent.run_group(upload_group_id, db)

                group_result.status = AgentStatus.COMPLETED.value
                group_result.results = result.get("results", {})
                group_result.summary = result.get("summary", "")
                group_result.risk_level = result.get("risk_level", "low")
                group_result.completed_at = datetime.now(timezone.utc)
                db.commit()

                logger.info(
                    f"  ✅ Group {agent_type.value} completed (risk: {group_result.risk_level})"
                )

            except Exception as e:
                logger.error(f"  ❌ Group {agent_type.value} failed: {str(e)}")
                import traceback
                traceback.print_exc()
                group_result.status = AgentStatus.FAILED.value
                group_result.error_message = str(e)
                group_result.completed_at = datetime.now(timezone.utc)
                db.commit()

        logger.info(f"🔮 Group analysis complete for {upload_group_id}")

    except Exception as e:
        logger.error(f"Group orchestrator error for {upload_group_id}: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()
