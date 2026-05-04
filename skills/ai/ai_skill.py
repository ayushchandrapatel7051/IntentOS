"""
OpenClaw Skill — AI Reasoning
================================
Provides LLM capabilities to the agent to summarize text, analyze data, and answer questions.
"""

import asyncio

class AISkill:
    def __init__(self, planner):
        self.planner = planner

    async def execute(self, action: str, params: dict) -> str:
        if action in ("ask", "summarize", "analyze"):
            prompt = params.get("prompt", "")
            context = params.get("context", "")
            
            if not prompt and not context:
                return "Error: Nothing to summarize or ask. Provide 'prompt' or 'context'."
                
            full_prompt = prompt
            if context:
                if full_prompt:
                    full_prompt += f"\n\nContext:\n{context}"
                else:
                    full_prompt = f"Please summarize the following:\n\n{context}"
                
            if getattr(self.planner, "client", None) is None:
                return "Offline Mode: AI skill requires Gemini API key or Vertex AI config."
                
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.planner.client.models.generate_content,
                        model=self.planner.model_name,
                        contents=full_prompt,
                    ),
                    timeout=60.0,
                )
                return self.planner._safe_text(response)
            except asyncio.TimeoutError:
                return "Error: LLM request timed out after 60 seconds."
            except Exception as e:
                return f"Error from LLM: {str(e)}"
        
        raise ValueError(f"Unknown AI action: {action}")
