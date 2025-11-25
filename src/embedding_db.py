import numpy as np
import ast
from sentence_transformers import SentenceTransformer
from supabase import create_client

# -----------------------
# CONFIG
# -----------------------
SUPABASE_URL = "https://fvqnabzyhdfqjyiymgkq.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZ2cW5hYnp5aGRmcWp5aXltZ2txIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjM1NTAzNDcsImV4cCI6MjA3OTEyNjM0N30.7ipg_sFgSa0hRIWFX96iv180cL9X54vHVpj4nmmQYnM"   
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

DEFAULT_MODEL_NAME = "all-mpnet-base-v2"
EMBED_DIM = 768

class EmbedderDB:
    def __init__(self, model_name: str = DEFAULT_MODEL_NAME):
        self.model = SentenceTransformer(model_name)

    def embed_text(self, text: str):
        """Return embedding as numpy array."""
        vec = self.model.encode(text, convert_to_numpy=True)
        return vec

    def save_chunk(self, file_id: str, chunk_text: str):
        """Save chunk with embedding."""
        emb = self.embed_text(chunk_text).tolist()
        res = supabase.table("file_chunks").insert({
            "file_id": file_id,
            "chunk_text": chunk_text,
            "embedding": emb
        }).execute()
        return res

    def cosine_similarity(self, a, b):
        """Compute cosine similarity between two vectors."""
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

    def search(self, file_id: str, query: str, top_k: int = 5, min_score: float = 0.65):

    # ----------- Embed Query -----------
        q_emb = self.embed_text(query)

        resp = supabase.rpc("match_chunks", {
        "query_embedding": q_emb.tolist(),
        "file_id": file_id,
        "match_count": top_k * 10
    }).execute()

    # No chunks returned from DB
        if not resp.data:
            return []

        query_words = set(query.lower().split())
        all_scores = []

        ABS_MIN_SEMANTIC = 0.15   # HARD semantic threshold
        HARD_KEYWORD_REQ = True   # require at least one word match

    # ----------- Score Chunks -----------
        for row in resp.data:
            emb = row.get("embedding")

            if isinstance(emb, str):
                emb = ast.literal_eval(emb)
            emb = np.array(emb, dtype=float)

            semantic = self.cosine_similarity(q_emb, emb)
            text = row["chunk_text"].lower()

        # Skip chunks failing absolute semantic threshold
            if semantic < ABS_MIN_SEMANTIC:
                continue

        # keyword overlap
            matches = sum(1 for w in query_words if w in text)
            keyword_score = matches / max(1, len(query_words))

        # Hard requirement: at least 1 matching word
            if HARD_KEYWORD_REQ and matches == 0:
                continue

            all_scores.append((row["chunk_text"], semantic, keyword_score))

    # No chunk survived → irrelevant query → return nothing
        if not all_scores:
            return []

    # ----------- Normalization -----------
        sems = [x[1] for x in all_scores]
        min_s, max_s = min(sems), max(sems) if sems else (0, 1)

        normalized = []
        for text, sim, kscore in all_scores:
            sim_n = (sim - min_s) / (max_s - min_s + 1e-6)
            final = (0.7 * sim_n) + (0.3 * kscore)
            normalized.append((text, final))

    # ----------- Select Top Chunks -----------
        normalized.sort(key=lambda x: x[1], reverse=True)

        filtered = [text for text, score in normalized if score >= min_score]

        if not filtered:
            return []

        return filtered[:top_k]
