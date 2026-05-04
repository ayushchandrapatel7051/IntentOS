"""
OpenClaw Memory — RAG Store (ChromaDB + Sentence Transformers)
===============================================================
Provides semantic search over:
  1. Past workflow executions (steps, results, outcomes)
  2. User knowledge snippets (saved page content, notes)
  3. SOUL.md rules and macros

Used by the Planner to:
  - Retrieve similar past workflows → skip re-planning from scratch
  - Find relevant knowledge before executing a command
  - Learn from failures (avoid repeating failed strategies)
"""

import json
import os
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    _RAG_OK = True
except ImportError:
    _RAG_OK = False


class RAGStore:
    """
    Semantic memory store backed by ChromaDB.

    Collections:
        workflows   — past execution plans + outcomes
        knowledge   — extracted page content, notes, facts
        failures    — failed steps with error messages (avoid repeating)
    """

    def __init__(self, persist_dir: str = ""):
        self.persist_dir = Path(persist_dir or os.getenv("RAG_STORE_PATH", "./memory/rag"))
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self._ready = False

        if not _RAG_OK:
            print("[RAG] chromadb/sentence-transformers not installed — RAG disabled")
            return

        try:
            # Embedding model (runs locally, no API cost)
            self._model = SentenceTransformer("all-MiniLM-L6-v2")

            # ChromaDB persistent client
            self._client = chromadb.PersistentClient(
                path=str(self.persist_dir),
                settings=Settings(anonymized_telemetry=False),
            )

            # Collections
            self._workflows = self._client.get_or_create_collection(
                name="workflows",
                metadata={"hnsw:space": "cosine"},
            )
            self._knowledge = self._client.get_or_create_collection(
                name="knowledge",
                metadata={"hnsw:space": "cosine"},
            )
            self._failures = self._client.get_or_create_collection(
                name="failures",
                metadata={"hnsw:space": "cosine"},
            )

            self._ready = True
            print(f"[RAG] Ready — {self._workflows.count()} workflows, "
                  f"{self._knowledge.count()} knowledge docs, "
                  f"{self._failures.count()} failures")
        except Exception as e:
            print(f"[RAG] Init failed: {e}")

    @property
    def is_ready(self) -> bool:
        return self._ready

    # ------------------------------------------------------------------
    # Embedding
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> list[float]:
        """Embed text using the local sentence transformer model."""
        return self._model.encode(text, normalize_embeddings=True).tolist()

    def _doc_id(self, text: str) -> str:
        """Stable ID from content hash."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # Workflows
    # ------------------------------------------------------------------

    def add_workflow(
        self,
        intent: str,
        plan_dict: dict,
        outcome: str,
        execution_time: float = 0.0,
    ) -> str:
        """
        Store a completed workflow for future retrieval.

        Args:
            intent: Original user intent string
            plan_dict: ActionPlan.to_dict() output
            outcome: 'completed' | 'failed' | 'aborted'
            execution_time: Seconds taken

        Returns:
            Document ID
        """
        if not self._ready:
            return ""

        doc_id = self._doc_id(intent + datetime.now().isoformat())

        # Build searchable text: intent + step descriptions
        steps_text = " | ".join(
            f"{s.get('skill','')}.{s.get('action','')} ({s.get('description','')})"
            for s in plan_dict.get("steps", [])
        )
        document = f"INTENT: {intent}\nSTEPS: {steps_text}\nOUTCOME: {outcome}"

        metadata = {
            "intent": intent[:500],
            "outcome": outcome,
            "step_count": len(plan_dict.get("steps", [])),
            "execution_time": execution_time,
            "timestamp": datetime.now().isoformat(),
            "plan_json": json.dumps(plan_dict)[:4096],  # ChromaDB metadata limit
        }

        try:
            self._workflows.upsert(
                ids=[doc_id],
                embeddings=[self._embed(document)],
                documents=[document],
                metadatas=[metadata],
            )
            return doc_id
        except Exception as e:
            print(f"[RAG] add_workflow error: {e}")
            return ""

    def search_workflows(
        self,
        intent: str,
        n_results: int = 3,
        outcome_filter: Optional[str] = "completed",
    ) -> list[dict]:
        """
        Find semantically similar past workflows.

        Args:
            intent: Query intent
            n_results: Max results to return
            outcome_filter: Filter by outcome ('completed', None = any)

        Returns:
            List of dicts with keys: intent, outcome, plan_json, similarity
        """
        if not self._ready or self._workflows.count() == 0:
            return []

        try:
            where = {"outcome": outcome_filter} if outcome_filter else None
            results = self._workflows.query(
                query_embeddings=[self._embed(intent)],
                n_results=min(n_results, self._workflows.count()),
                where=where,
                include=["metadatas", "distances"],
            )

            hits = []
            for meta, dist in zip(
                results["metadatas"][0], results["distances"][0]
            ):
                similarity = 1 - dist  # cosine distance → similarity
                if similarity < 0.5:   # skip low-relevance results
                    continue
                hits.append({
                    "intent": meta.get("intent", ""),
                    "outcome": meta.get("outcome", ""),
                    "step_count": meta.get("step_count", 0),
                    "plan_json": meta.get("plan_json", "{}"),
                    "similarity": round(similarity, 3),
                    "timestamp": meta.get("timestamp", ""),
                })
            return hits
        except Exception as e:
            print(f"[RAG] search_workflows error: {e}")
            return []

    # ------------------------------------------------------------------
    # Knowledge / Content
    # ------------------------------------------------------------------

    def add_knowledge(
        self,
        content: str,
        source: str = "",
        tags: list[str] = None,
        title: str = "",
    ) -> str:
        """
        Store extracted page content or user notes.

        Args:
            content: Text content to store
            source: URL or file path
            tags: List of topic tags
            title: Human-readable title

        Returns:
            Document ID
        """
        if not self._ready or not content.strip():
            return ""

        # Chunk long content
        chunks = self._chunk(content, max_chars=1500)
        ids = []

        for i, chunk in enumerate(chunks):
            doc_id = self._doc_id(source + str(i) + chunk[:50])
            document = f"SOURCE: {source}\nTITLE: {title}\n\n{chunk}"

            metadata = {
                "source": source[:500],
                "title": title[:200],
                "tags": json.dumps(tags or []),
                "chunk_index": i,
                "total_chunks": len(chunks),
                "timestamp": datetime.now().isoformat(),
            }

            try:
                self._knowledge.upsert(
                    ids=[doc_id],
                    embeddings=[self._embed(document)],
                    documents=[document],
                    metadatas=[metadata],
                )
                ids.append(doc_id)
            except Exception as e:
                print(f"[RAG] add_knowledge error: {e}")

        return ",".join(ids)

    def search_knowledge(
        self,
        query: str,
        n_results: int = 5,
        source_filter: Optional[str] = None,
    ) -> list[dict]:
        """
        Semantic search over stored knowledge.

        Args:
            query: Search query
            n_results: Max results
            source_filter: Optional source URL/path to filter by

        Returns:
            List of dicts with keys: title, source, content, similarity
        """
        if not self._ready or self._knowledge.count() == 0:
            return []

        try:
            where = {"source": source_filter} if source_filter else None
            results = self._knowledge.query(
                query_embeddings=[self._embed(query)],
                n_results=min(n_results, self._knowledge.count()),
                where=where,
                include=["documents", "metadatas", "distances"],
            )

            hits = []
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                similarity = 1 - dist
                if similarity < 0.4:
                    continue
                hits.append({
                    "title": meta.get("title", ""),
                    "source": meta.get("source", ""),
                    "content": doc,
                    "similarity": round(similarity, 3),
                    "tags": json.loads(meta.get("tags", "[]")),
                })
            return hits
        except Exception as e:
            print(f"[RAG] search_knowledge error: {e}")
            return []

    # ------------------------------------------------------------------
    # Failures (avoid repeating failed strategies)
    # ------------------------------------------------------------------

    def add_failure(
        self,
        intent: str,
        step_skill: str,
        step_action: str,
        error: str,
        params: dict = None,
    ) -> str:
        """Record a failed step for future avoidance."""
        if not self._ready:
            return ""

        doc_id = self._doc_id(intent + step_skill + step_action + error[:50])
        document = (
            f"INTENT: {intent}\n"
            f"FAILED: {step_skill}.{step_action}\n"
            f"ERROR: {error}\n"
            f"PARAMS: {json.dumps(params or {})}"
        )

        metadata = {
            "intent": intent[:500],
            "skill": step_skill,
            "action": step_action,
            "error": error[:500],
            "timestamp": datetime.now().isoformat(),
        }

        try:
            self._failures.upsert(
                ids=[doc_id],
                embeddings=[self._embed(document)],
                documents=[document],
                metadatas=[metadata],
            )
            return doc_id
        except Exception as e:
            print(f"[RAG] add_failure error: {e}")
            return ""

    def search_failures(
        self,
        intent: str,
        n_results: int = 3,
    ) -> list[dict]:
        """Find past failures similar to current intent (to avoid repeating them)."""
        if not self._ready or self._failures.count() == 0:
            return []

        try:
            results = self._failures.query(
                query_embeddings=[self._embed(intent)],
                n_results=min(n_results, self._failures.count()),
                include=["metadatas", "distances"],
            )

            hits = []
            for meta, dist in zip(
                results["metadatas"][0], results["distances"][0]
            ):
                similarity = 1 - dist
                if similarity < 0.6:
                    continue
                hits.append({
                    "skill": meta.get("skill", ""),
                    "action": meta.get("action", ""),
                    "error": meta.get("error", ""),
                    "similarity": round(similarity, 3),
                })
            return hits
        except Exception as e:
            print(f"[RAG] search_failures error: {e}")
            return []

    # ------------------------------------------------------------------
    # Bulk load from YAML workflow store
    # ------------------------------------------------------------------

    def sync_from_yaml_store(self, yaml_store_path: str = "./memory/workflows") -> int:
        """
        Import all YAML workflows into ChromaDB for semantic search.
        Call once on startup or after many new workflows accumulate.

        Returns number of workflows imported.
        """
        if not self._ready:
            return 0

        import yaml
        store_path = Path(yaml_store_path)
        if not store_path.exists():
            return 0

        imported = 0
        for file_path in store_path.glob("*.yaml"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    wf = yaml.safe_load(f)
                if not wf:
                    continue
                self.add_workflow(
                    intent=wf.get("intent", ""),
                    plan_dict=wf.get("plan", {}),
                    outcome=wf.get("outcome", "unknown"),
                )
                imported += 1
            except Exception:
                continue

        print(f"[RAG] Synced {imported} workflows from YAML store")
        return imported

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _chunk(self, text: str, max_chars: int = 1500) -> list[str]:
        """Split text into overlapping chunks for better retrieval."""
        if len(text) <= max_chars:
            return [text]

        chunks = []
        overlap = 200
        start = 0
        while start < len(text):
            end = min(start + max_chars, len(text))
            # Try to break at sentence boundary
            if end < len(text):
                last_period = text.rfind(". ", start, end)
                if last_period > start + max_chars // 2:
                    end = last_period + 1
            chunks.append(text[start:end])
            start = end - overlap
        return chunks

    def stats(self) -> dict:
        """Return collection statistics."""
        if not self._ready:
            return {"ready": False}
        return {
            "ready": True,
            "workflows": self._workflows.count(),
            "knowledge": self._knowledge.count(),
            "failures": self._failures.count(),
        }
