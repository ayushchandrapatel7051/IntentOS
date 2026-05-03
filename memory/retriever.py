import os
import numpy as np
import time
from .embeddings import Embeddings
from .workflow_loader import load_workflows
from .rag_store import RAGStore

class Retriever:
    def __init__(self):
        self.embeddings = Embeddings()
        self.rag_store = RAGStore(db_path="memory/rag_store.json")
        self.workflows = load_workflows("memory/workflows")
        
        self.workflow_texts = []
        self.workflow_embeddings = None
        
        self.execution_texts = []
        self.execution_embeddings = None
        self._last_execution_count = 0
        
        self._build_workflow_index()
        self._update_execution_index()

    def _build_workflow_index(self):
        if not self.workflows:
            return
            
        texts = []
        for w in self.workflows:
            desc = w.get('description', '')
            tags = ', '.join(w.get('tags', []))
            text = f"Intent: {w['name']}\nDescription: {desc}\nTags: {tags}"
            texts.append(text)
            
        self.workflow_texts = texts
        t0 = time.time()
        self.workflow_embeddings = self.embeddings.get_embeddings(texts)
        if hasattr(self.workflow_embeddings, "shape"):
            print(f"[Retriever] Built workflow index for {len(self.workflows)} workflows in {time.time()-t0:.2f}s")

    def _update_execution_index(self):
        executions = self.rag_store.get_executions()
        if len(executions) == self._last_execution_count:
            return
            
        if not executions:
            return
            
        texts = []
        for e in executions:
            res = e.get('result', '')
            text = f"Intent: {e['intent']}\nResult: {res}"
            texts.append(text)
            
        self.execution_texts = texts
        self.execution_embeddings = self.embeddings.get_embeddings(texts)
        self._last_execution_count = len(executions)

    def search(self, query: str, top_k=3):
        query_emb = self.embeddings.get_embedding(query)
        if query_emb is None or (hasattr(query_emb, "shape") and len(query_emb.shape) == 0):
            return [], []
            
        top_workflows = self._search_index(query_emb, self.workflows, self.workflow_embeddings, top_k)
        
        self._update_execution_index()
        
        executions = self.rag_store.get_executions()
        if executions and self.execution_embeddings is not None and len(executions) > 0:
            # Handle list of dicts returning fallback arrays
            if not hasattr(self.execution_embeddings, "shape") or len(self.execution_embeddings.shape) < 2:
                top_executions = executions[:top_k]
            else:
                scores = np.dot(self.execution_embeddings, query_emb)
                norm_query = np.linalg.norm(query_emb)
                norm_docs = np.linalg.norm(self.execution_embeddings, axis=1)
                norms = norm_docs * norm_query
                norms[norms == 0] = 1e-10
                cosine_sims = scores / norms
                
                results = []
                for i, e in enumerate(executions):
                    score = cosine_sims[i]
                    if e.get("success", False):
                        score += 0.1
                    else:
                        score -= 0.1
                    results.append((score, e))
                    
                results.sort(key=lambda x: x[0], reverse=True)
                top_executions = [item[1] for item in results[:top_k]]
        else:
            top_executions = []
            
        return top_executions, top_workflows

    def _search_index(self, query_emb, items, item_embeddings, top_k):
        if not items or item_embeddings is None:
            return []
            
        if not hasattr(item_embeddings, "shape") or len(item_embeddings.shape) < 2:
            return items[:top_k]
            
        scores = np.dot(item_embeddings, query_emb)
        norm_query = np.linalg.norm(query_emb)
        norm_docs = np.linalg.norm(item_embeddings, axis=1)
        norms = norm_docs * norm_query
        norms[norms == 0] = 1e-10
        cosine_sims = scores / norms
        
        # Get top k indices
        k = min(top_k, len(cosine_sims))
        top_indices = np.argsort(cosine_sims)[::-1][:k]
        return [items[i] for i in top_indices]
