"""Base agent interface for Third Eye."""
from abc import ABC, abstractmethod
from sqlalchemy.orm import Session


class BaseAgent(ABC):
    """All agents must implement the run method."""

    @abstractmethod
    def run(self, document_id: str, db: Session) -> dict:
        """
        Execute the agent on a document.
        
        Returns:
            dict with keys:
                - results: dict — structured results
                - summary: str — human-readable summary
                - risk_level: str — low, medium, high, critical
        """
        pass
