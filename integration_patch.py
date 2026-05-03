"""
OpenClaw — Integration Patch (apply to main.py)
================================================
This patches the existing system at startup to add:
  1. RAG memory (ChromaDB semantic search)
  2. Planner improvements (direct URLs, template fix, RAG context)
  3. Executor augmentation (records workflows/failures/knowledge)
  4. API endpoint for RAG search

HOW TO APPLY to main.py:
  Add these lines AFTER creating executor and BEFORE starting the server:

    from integration_patch import apply_patches
    apply_patches(executor, planner, app)

  Also add this import at the top of main.py:
    from memory.rag_store import RAGStore
"""

import os
import sys
import json
import re
from pathlib import Path


def apply_patches(executor, planner, app, yaml_store_path="./memory/workflows"):
    """
    Apply all fixes and enhancements to the running OpenClaw instance.
    
    1. Initialize RAG store
    2. Sync existing YAML workflows into ChromaDB
    3. Patch executor for RAG recording
    4. Patch planner for better routing + template fix
    5. Add RAG API endpoints
    
    Args:
        executor: The Executor instance from main.py
        planner: The Planner instance from main.py  
        app: The FastAPI app instance
        yaml_store_path: Path to existing YAML workflow files
    """
    print("[Patch] Applying OpenClaw fixes and RAG integration...")

    # ── 1. Initialize RAG Store ──────────────────────────────────────
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from memory.rag_store import RAGStore
        rag_store = RAGStore()

        # Sync existing YAML workflows on first run
        if rag_store.is_ready:
            synced = rag_store.sync_from_yaml_store(yaml_store_path)
            print(f"[Patch] ✓ RAG store initialized — synced {synced} past workflows")
        else:
            print("[Patch] ⚠ RAG store not available (missing dependencies)")
    except Exception as e:
        print(f"[Patch] ⚠ RAG init failed: {e}")
        rag_store = None

    # ── 2. Patch Executor ────────────────────────────────────────────
    if rag_store:
        try:
            from agent.rag_executor import augment_executor
            augment_executor(executor, rag_store)
            print("[Patch] ✓ Executor augmented with RAG recording")
        except Exception as e:
            print(f"[Patch] ⚠ Executor augmentation failed: {e}")

    # ── 3. Patch Planner ─────────────────────────────────────────────
    try:
        _patch_planner(planner, rag_store)
        print("[Patch] ✓ Planner patched (better routing + template fix)")
    except Exception as e:
        print(f"[Patch] ⚠ Planner patch failed: {e}")

    # ── 4. Add RAG API Endpoints ─────────────────────────────────────
    if rag_store:
        try:
            _add_rag_routes(app, rag_store)
            print("[Patch] ✓ RAG API endpoints registered at /api/rag/*")
        except Exception as e:
            print(f"[Patch] ⚠ RAG routes failed: {e}")

    # Store on app state for access in routes
    app.state.rag_store = rag_store

    print("[Patch] All patches applied successfully\n")
    return rag_store


def _patch_planner(planner, rag_store):
    """
    Patch the Planner to:
    1. Add better content extraction routing rules to system prompt
    2. Fix template syntax in generated plans
    3. Inject RAG context (past successes/failures) into planning
    """
    from agent.planner_patch import (
        fix_template_syntax,
        build_rag_context,
        get_patched_planner_instructions,
    )

    # Store original methods
    original_system_prompt = planner._system_prompt
    original_user_prompt = planner._user_prompt
    original_create_plan = planner.create_plan
    original_parse = planner._parse

    # Patch _system_prompt to include better routing rules
    def patched_system_prompt():
        base = original_system_prompt()
        extra = get_patched_planner_instructions()
        # Insert before the last section
        return base + "\n\n" + extra

    # Patch create_plan to inject RAG context and fix templates
    async def patched_create_plan(intent: str):
        # Get RAG context if available
        rag_context = ""
        if rag_store and rag_store.is_ready:
            rag_context = build_rag_context(rag_store, intent)

        # If RAG has relevant context, inject into the user prompt
        if rag_context:
            # Temporarily override user prompt to include RAG context
            original_user = original_user_prompt
            
            def user_prompt_with_rag(i):
                base = original_user(i)
                return f"{rag_context}\n\n{base}"
            
            planner._user_prompt = user_prompt_with_rag

        try:
            plan = await original_create_plan(intent)
        finally:
            # Restore original user prompt
            if rag_context:
                planner._user_prompt = original_user_prompt

        # Fix template syntax in the generated plan
        if plan and plan.steps:
            plan_dict = plan.to_dict()
            fixed_dict = fix_template_syntax(plan_dict)
            
            # Apply fixes back to plan steps
            for orig_step, fixed_step in zip(plan.steps, fixed_dict.get("steps", [])):
                orig_step.params = fixed_step.get("params", orig_step.params)

        return plan

    # Patch _parse to also fix templates right after parsing
    def patched_parse(text: str, intent: str):
        plan = original_parse(text, intent)
        
        # Fix template syntax immediately after parsing
        if plan and plan.steps:
            for step in plan.steps:
                step.params = _fix_step_params(step.params)
        
        return plan

    # Apply patches
    planner._system_prompt = patched_system_prompt
    planner.create_plan = patched_create_plan
    planner._parse = patched_parse


def _fix_step_params(params: dict) -> dict:
    """Fix single-brace template syntax in step params."""
    if not params:
        return params
    
    fixed = {}
    for k, v in params.items():
        if isinstance(v, str):
            # Fix {steps.step_N...} → {{steps.step_N...}}
            v = re.sub(
                r'(?<!\{)\{(steps\.step_\w+(?:\.[\w.]+)?)\}(?!\})',
                r'{{\1}}',
                v
            )
            # Fix {step_N...} → {{steps.step_N...}}
            v = re.sub(
                r'(?<!\{)\{(step_\d+(?:\.[\w.]+)?)\}(?!\})',
                r'{{steps.\1}}',
                v
            )
        fixed[k] = v
    return fixed


def _add_rag_routes(app, rag_store):
    """Add RAG-specific REST API endpoints."""
    from fastapi import Request
    from pydantic import BaseModel
    from typing import Optional

    class KnowledgeAddRequest(BaseModel):
        content: str
        source: str = ""
        title: str = ""
        tags: list = []

    class SearchRequest(BaseModel):
        query: str
        n_results: int = 5
        collection: str = "knowledge"  # workflows | knowledge | failures

    @app.get("/api/rag/stats")
    async def rag_stats():
        """Get RAG store statistics."""
        return rag_store.stats()

    @app.post("/api/rag/search")
    async def rag_search(req: SearchRequest):
        """Semantic search across RAG collections."""
        if req.collection == "workflows":
            results = rag_store.search_workflows(req.query, n_results=req.n_results)
        elif req.collection == "failures":
            results = rag_store.search_failures(req.query, n_results=req.n_results)
        else:
            results = rag_store.search_knowledge(req.query, n_results=req.n_results)
        return {"query": req.query, "collection": req.collection, "results": results}

    @app.post("/api/rag/knowledge")
    async def add_knowledge(req: KnowledgeAddRequest):
        """Manually add content to the knowledge store."""
        doc_id = rag_store.add_knowledge(
            content=req.content,
            source=req.source,
            title=req.title,
            tags=req.tags,
        )
        return {"success": bool(doc_id), "doc_id": doc_id}

    @app.get("/api/rag/knowledge/search")
    async def search_knowledge(q: str, n: int = 5):
        """Quick knowledge search via GET."""
        results = rag_store.search_knowledge(q, n_results=n)
        return {"query": q, "results": results}

    @app.post("/api/rag/sync")
    async def sync_workflows():
        """Sync YAML workflow store into ChromaDB."""
        count = rag_store.sync_from_yaml_store()
        return {"synced": count, "stats": rag_store.stats()}
