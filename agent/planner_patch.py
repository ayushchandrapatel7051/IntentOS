def fix_template_syntax(plan_dict: dict) -> dict:
    import re
    if not plan_dict or "steps" not in plan_dict:
        return plan_dict
    
    for step in plan_dict["steps"]:
        if "params" in step and step["params"]:
            for k, v in step["params"].items():
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
                    # FIX result.text missing access
                    if isinstance(v, str) and ".result}}" in v and ".text" not in v:
                        # automatically convert {{steps.step_X.result}} → {{steps.step_X.result.text}}
                        v = v.replace(".result}}", ".result.text}}")

                    step["params"][k] = v
    return plan_dict

def build_rag_context(rag_store, intent: str) -> str:
    similar = rag_store.search_workflows(intent, n_results=2)
    failures = rag_store.search_failures(intent, n_results=2)
    
    context = ""
    if similar:
        context += "SUCCESSFUL PAST WORKFLOWS (Use as reference):\n"
        for wf in similar:
            context += f"- Intent: {wf['intent']}\n  Plan: {wf['plan_json']}\n\n"
    
    if failures:
        context += "PAST FAILURES (AVOID THESE STRATEGIES):\n"
        for f in failures:
            context += f"- Action: {f['skill']}.{f['action']}\n  Error: {f['error']}\n\n"
            
    return context.strip()

def get_patched_planner_instructions() -> str:
    return """
ADDITIONAL INSTRUCTIONS:
- Pay close attention to SUCCESSFUL PAST WORKFLOWS provided in the prompt. If your current task is similar, adapt the past plan.
- Pay close attention to PAST FAILURES. Do NOT repeat failed strategies. Use alternative approaches.
"""
