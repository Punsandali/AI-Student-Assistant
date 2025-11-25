# ingestion_store.py
import os
from src.ingestion import ingest_file  # your existing ingestion.py that returns chunks list
from src.embedding_db import EmbedderDB
from supabase import create_client
import datetime

# -----------------------
# CONFIG
# -----------------------
SUPABASE_URL = "https://fvqnabzyhdfqjyiymgkq.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZ2cW5hYnp5aGRmcWp5aXltZ2txIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjM1NTAzNDcsImV4cCI6MjA3OTEyNjM0N30.7ipg_sFgSa0hRIWFX96iv180cL9X54vHVpj4nmmQYnM"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

embedder = EmbedderDB()

def ingest_and_store_file(local_path: str, user_id: str):
    """
    1) insert file metadata into user_files
    2) ingest_file -> get chunk_data (list of dicts with 'text')
    3) for each chunk: save_chunk(file_id, chunk_text)
    returns file_id (uuid)
    """
    file_name = os.path.basename(local_path)

    # 1) Save file metadata
    insert = supabase.table("user_files").insert({
        "user_id": user_id,
        "file_name": file_name,
        "file_path": local_path  # optional: you can instead upload to Supabase Storage and store path
    }).execute()

    if not insert.data:
        raise RuntimeError("Failed to insert user_files record.")

    file_id = insert.data[0]["id"]

    # 2) Extract chunks using your existing ingestion
    chunks = ingest_file(local_path)  # returns list [{"id":..., "text":...}, ...]
    for c in chunks:
        text = c.get("text") if isinstance(c, dict) else c
        if not text:
            continue
        embedder.save_chunk(file_id=file_id, chunk_text=text)

    return file_id
