"""扫描没有 embedding 的 memories，逐条生成 embedding 并写回。

手动运行：
    .\.venv\Scripts\python.exe scripts\backfill_embeddings.py

如果遇到编码问题，运行：
    set PYTHONIOENCODING=utf-8 && .\.venv\Scripts\python.exe scripts\backfill_embeddings.py
"""
import sys
sys.path.insert(0, ".")

import db
import embedder

db.init_db()

rows = db.all_memory_rows(9999)
missing = [r for r in rows if not r.get("embedding")]

if not missing:
    print("All memories already have embeddings, nothing to do.")
else:
    print(f"Found {len(missing)} memories without embedding, backfilling...")
    for i, row in enumerate(missing):
        fact = row["fact"]
        vec = embedder.embed(fact)
        if vec:
            db.update_memory_embedding(fact, vec)
            print(f"  [{i+1}/{len(missing)}] OK {fact[:40]}")
        else:
            print(f"  [{i+1}/{len(missing)}] FAIL {fact[:40]}")
    print("Done!")
