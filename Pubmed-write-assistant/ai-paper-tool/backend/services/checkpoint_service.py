"""
Checkpoint Service — saves and restores pipeline progress.
Enables recovery from interruptions during long generation sessions.
"""
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CHECKPOINT_DIR = Path(__file__).parent.parent.parent / "checkpoints"


def _ensure_checkpoint_dir():
    """Ensure checkpoint directory exists."""
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Checkpoint:
    """Saved state of a pipeline run."""
    topic: str
    timestamp: str
    current_phase: str  # "research" | "write" | "review" | "edit" | "finalize"
    current_round: int  # 0=search, 1=first write, 2+=review/edit rounds
    citation_map: dict
    current_draft: str
    rounds: list  # list of RoundRecord dicts
    references: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class CheckpointService:
    """
    Service for saving/restoring pipeline checkpoints.
    Checkpoints are stored as JSON files for manual inspection.
    """

    def __init__(self, topic: str):
        _ensure_checkpoint_dir()
        # Sanitize topic for filename
        safe_topic = "".join(c if c.isalnum() else "_" for c in topic[:50])
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._filename = CHECKPOINT_DIR / f"checkpoint_{safe_topic}_{timestamp}.json"
        self._topic = topic
        logger.info(f"CheckpointService initialized: {self._filename}")

    @property
    def checkpoint_exists(self) -> bool:
        """Check if there's a recoverable checkpoint for this topic."""
        return self._filename.exists()

    def save(self, checkpoint: Checkpoint) -> None:
        """Save a checkpoint to disk."""
        try:
            with open(self._filename, "w", encoding="utf-8") as f:
                json.dump(checkpoint.to_dict(), f, ensure_ascii=False, indent=2)
            logger.info(f"Checkpoint saved: phase={checkpoint.current_phase}, round={checkpoint.current_round}")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")

    def load(self) -> Optional[Checkpoint]:
        """Load the latest checkpoint for this topic."""
        if not self._filename.exists():
            return None
        try:
            with open(self._filename, "r", encoding="utf-8") as f:
                data = json.load(f)
            checkpoint = Checkpoint(**data)
            logger.info(f"Checkpoint loaded: phase={checkpoint.current_phase}, round={checkpoint.current_round}")
            return checkpoint
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return None

    def delete(self) -> None:
        """Delete the checkpoint file after successful completion."""
        try:
            if self._filename.exists():
                self._filename.unlink()
                logger.info("Checkpoint deleted")
        except Exception as e:
            logger.error(f"Failed to delete checkpoint: {e}")

    @classmethod
    def list_checkpoints(cls) -> list[Path]:
        """List all checkpoint files."""
        _ensure_checkpoint_dir()
        return sorted(CHECKPOINT_DIR.glob("checkpoint_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)

    @classmethod
    def delete_all(cls) -> None:
        """Delete all checkpoints."""
        for cp in cls.list_checkpoints():
            try:
                cp.unlink()
            except Exception as e:
                logger.error(f"Failed to delete {cp}: {e}")
