"""
OpenClaw Memory — YAML Workflow Store
========================================
Persists executed workflows, steps, outcomes, and timestamps.
Enables pattern recognition and learned step skipping.
"""

import os
import yaml
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional


class WorkflowStore:
    """
    YAML-based workflow persistence store.
    
    Records every executed workflow with its steps, outcomes, and timestamps.
    The agent queries this store to recognize repeated patterns and skip
    steps it has already learned.
    """

    def __init__(self, store_path: str = ""):
        self.store_path = Path(store_path or os.getenv("MEMORY_STORE_PATH", "./memory/workflows"))
        self.store_path.mkdir(parents=True, exist_ok=True)

    def _workflow_id(self, intent: str) -> str:
        """Generate a unique ID for a workflow based on intent."""
        normalized = intent.lower().strip()
        hash_val = hashlib.md5(normalized.encode()).hexdigest()[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{timestamp}_{hash_val}"

    def _intent_fingerprint(self, intent: str) -> str:
        """Generate a fingerprint for intent matching."""
        # Normalize the intent for similarity matching
        words = intent.lower().strip().split()
        # Remove common stop words for better matching
        stop_words = {"the", "a", "an", "to", "my", "in", "on", "for", "and", "or", "is", "it", "do", "please"}
        key_words = sorted(set(w for w in words if w not in stop_words))
        return " ".join(key_words)

    def save_workflow(self, intent: str, plan_data: dict, outcome: str = "completed") -> str:
        """
        Save a completed workflow to the store.
        
        Args:
            intent: Original user intent
            plan_data: The ActionPlan as a dict
            outcome: Final outcome (completed, failed, aborted)
            
        Returns:
            Path to the saved workflow file
        """
        workflow_id = self._workflow_id(intent)
        
        workflow = {
            "id": workflow_id,
            "intent": intent,
            "fingerprint": self._intent_fingerprint(intent),
            "outcome": outcome,
            "created_at": datetime.now().isoformat(),
            "plan": plan_data,
        }

        file_path = self.store_path / f"{workflow_id}.yaml"
        
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(workflow, f, default_flow_style=False, allow_unicode=True)

        return str(file_path)

    def find_similar_workflow(self, intent: str) -> Optional[dict]:
        """
        Find a previously executed workflow similar to the given intent.
        
        Uses fingerprint matching to identify repeated patterns.
        Returns the most recent matching workflow, or None.
        """
        target_fingerprint = self._intent_fingerprint(intent)
        target_words = set(target_fingerprint.split())

        best_match = None
        best_score = 0.0

        for file_path in sorted(self.store_path.glob("*.yaml"), reverse=True):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    workflow = yaml.safe_load(f)

                if not workflow or workflow.get("outcome") != "completed":
                    continue

                stored_fingerprint = workflow.get("fingerprint", "")
                stored_words = set(stored_fingerprint.split())

                # Jaccard similarity
                if target_words and stored_words:
                    intersection = target_words & stored_words
                    union = target_words | stored_words
                    score = len(intersection) / len(union)

                    if score > best_score and score >= 0.6:
                        best_score = score
                        best_match = workflow
            except Exception:
                continue

        return best_match

    def get_recent_workflows(self, limit: int = 10) -> list:
        """Get the most recent workflows."""
        workflows = []
        
        for file_path in sorted(self.store_path.glob("*.yaml"), reverse=True)[:limit]:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    workflow = yaml.safe_load(f)
                    if workflow:
                        workflows.append({
                            "id": workflow.get("id"),
                            "intent": workflow.get("intent"),
                            "outcome": workflow.get("outcome"),
                            "created_at": workflow.get("created_at"),
                        })
            except Exception:
                continue

        return workflows

    def get_workflow_by_id(self, workflow_id: str) -> Optional[dict]:
        """Load a specific workflow by ID."""
        file_path = self.store_path / f"{workflow_id}.yaml"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return None

    def get_stats(self) -> dict:
        """Get workflow statistics."""
        total = 0
        completed = 0
        failed = 0

        for file_path in self.store_path.glob("*.yaml"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    workflow = yaml.safe_load(f)
                    if workflow:
                        total += 1
                        outcome = workflow.get("outcome", "")
                        if outcome == "completed":
                            completed += 1
                        elif outcome == "failed":
                            failed += 1
            except Exception:
                continue

        return {
            "total_workflows": total,
            "completed": completed,
            "failed": failed,
            "success_rate": f"{(completed / total * 100):.1f}%" if total > 0 else "N/A",
        }
