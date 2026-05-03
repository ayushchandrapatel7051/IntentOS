import os
import json
import time

class RAGStore:
    def __init__(self, db_path="memory/rag_store.json", max_executions=100):
        self.db_path = db_path
        self.max_executions = max_executions
        self.executions = []
        self.load_from_disk()

    def add_execution(self, intent: str, steps: list, result: str, success: bool):
        entry = {
            "intent": intent,
            "steps": steps,
            "result": result,
            "success": success,
            "timestamp": time.time(),
            "type": "execution"
        }
        self.executions.append(entry)
        
        if len(self.executions) > self.max_executions:
            self.executions.sort(key=lambda x: x["timestamp"])
            self.executions = self.executions[-self.max_executions:]
            
        self.save_to_disk()

    def get_executions(self):
        return self.executions

    def save_to_disk(self):
        os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(self.executions, f, indent=2)
        except Exception as e:
            print(f"[RAGStore] Failed to save DB: {e}")

    def load_from_disk(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    self.executions = json.load(f)
            except Exception as e:
                print(f"[RAGStore] Failed to load DB: {e}")
                self.executions = []
