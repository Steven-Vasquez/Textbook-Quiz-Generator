#!/usr/bin/env python3
"""
index_and_embed.py
Usage:
    python index_and_embed.py chapters_chunked.json index_dir/
Produces:
    - faiss index
    - metadata.json mapping index->(chapter,title,chunk_text)
"""

import os, sys, json
from sentence_transformers import SentenceTransformer
import numpy as np
import faiss
from tqdm import tqdm

EMBED_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

def load_chapters(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def main(chapters_json, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    chapters = load_chapters(chapters_json)
    model = SentenceTransformer(EMBED_MODEL)

    texts = []
    meta = []
    for chap_key, chap in chapters.items():
        for i, chunk in enumerate(chap["chunks"]):
            texts.append(chunk)
            meta.append({"chapter_key": chap_key, "chapter_title": chap["title"], "chunk_index": i})

    print(f"Encoding {len(texts)} chunks with {EMBED_MODEL}...")
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)

    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)
    faiss.normalize_L2(embeddings)
    index.add(embeddings)

    faiss.write_index(index, os.path.join(out_dir, "faiss.index"))
    with open(os.path.join(out_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta}, f, indent=2, ensure_ascii=False)
    print("Saved index and metadata to", out_dir)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python index_and_embed.py chapters_chunked.json index_dir")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
