"""
OpenClaw — RAG-Aware Executor Mixin
=====================================
Drop-in additions to agent/executor.py:
  - Records every step result to RAG knowledge store
  - Records failures to avoid repeating broken strategies
  - Saves extracted page content (getPageText results) to knowledge store
  - Queries RAG before replanning to suggest better alternatives

Usage: import and call augment_executor(executor, rag_store) at startup.
"""

from typing import TYPE_CHECKING
import json

if TYPE_CHECKING:
    from memory.rag_store import RAGStore


def augment_executor(executor, rag_store: "RAGStore"):
    """
    Monkey-patch the executor to integrate RAG memory.
    Wraps execute_plan and _execute_step to record outcomes.
    """
    original_execute_plan = executor.execute_plan
    original_execute_step = executor._execute_step
    original_handle_failure = executor._handle_failure

    async def rag_execute_plan(plan):
        """Wrapped execute_plan that records workflow to RAG after completion."""
        import time
        start = time.time()

        # Check RAG for similar past workflows
        if rag_store.is_ready:
            similar = rag_store.search_workflows(plan.intent, n_results=2)
            if similar:
                best = similar[0]
                executor.context and executor.context.add_log(
                    "INFO",
                    f"[RAG] Found similar past workflow (sim={best['similarity']:.2f}): "
                    f"'{best['intent'][:60]}' → {best['outcome']}",
                )

        # Run original
        context = await original_execute_plan(plan)

        # Record to RAG
        if rag_store.is_ready:
            elapsed = time.time() - start
            rag_store.add_workflow(
                intent=plan.intent,
                plan_dict=plan.to_dict(),
                outcome=plan.status,
                execution_time=elapsed,
            )

        return context

    async def rag_execute_step(step):
        """Wrapped _execute_step that saves extracted content to knowledge store."""
        success = await original_execute_step(step)

        # If this was a content extraction step, save to RAG knowledge
        if success and rag_store.is_ready and step.result:
            action_key = step.action.lower().replace("_", "").replace("-", "")
            if action_key in ("getpagetext", "pagetext", "extracttext"):
                # Save extracted page content
                params = step.params or {}
                source_url = params.get("url", params.get("tab_id", "unknown"))
                if isinstance(step.result, str) and len(step.result) > 100:
                    rag_store.add_knowledge(
                        content=step.result,
                        source=str(source_url),
                        title=f"Page content from step {step.id}",
                        tags=["web_content", "extracted"],
                    )
                    executor.context and executor.context.add_log(
                        "INFO",
                        f"[RAG] Saved {len(step.result)} chars of page content to knowledge store",
                        step.id,
                    )

        return success

    async def rag_handle_failure(failed_step):
        """Wrapped failure handler that records failures to RAG."""
        # Record failure before attempting recovery
        if rag_store.is_ready and executor.context:
            rag_store.add_failure(
                intent=executor.context.plan.intent,
                step_skill=failed_step.skill,
                step_action=failed_step.action,
                error=failed_step.error or "unknown",
                params=failed_step.params,
            )

            # Warn if same failure pattern seen before
            similar_failures = rag_store.search_failures(
                intent=executor.context.plan.intent, n_results=2
            )
            if similar_failures:
                executor.context.add_log(
                    "WARN",
                    f"[RAG] This failure pattern was seen before: "
                    f"{similar_failures[0]['skill']}.{similar_failures[0]['action']} — "
                    f"{similar_failures[0]['error'][:80]}",
                    failed_step.id,
                )

        return await original_handle_failure(failed_step)

    # Attach wrapped methods
    executor.execute_plan = rag_execute_plan
    executor._execute_step = rag_execute_step
    executor._handle_failure = rag_handle_failure

    return executor
