import numpy as np

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

class Embeddings:
    def __init__(self, model_name="all-MiniLM-L6-v2"):
        if SentenceTransformer is None:
            self.model = None
        else:
            self.model = SentenceTransformer(model_name)

    def get_embedding(self, text: str) -> np.ndarray:
        if self.model is None:
            return np.zeros(384) # fallback
        return self.model.encode(text)

    def get_embeddings(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.array([])
        if self.model is None:
            return np.zeros((len(texts), 384)) # fallback
        return self.model.encode(texts)
