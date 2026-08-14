import hashlib
import os
import sys
import chromadb

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root (this file lives one level down)
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(BASE_DIR, "db")


def _log(msg):
    """print(), but survives emoji/non-Latin text on a Windows console
    stuck on a narrow codepage (e.g. cp1252) -- same fix as
    fetch_park_precedent.py / logic/free_scraper.py's helper of the same name."""
    enc = sys.stdout.encoding or "utf-8"
    print(msg.encode(enc, errors="replace").decode(enc, errors="replace"))


_log("🧠 Booting up ChromaDB Vector Engine...")

# Connect to the exact same database the FastAPI server uses
chroma_client = chromadb.PersistentClient(path=DB_PATH)
collection = chroma_client.get_or_create_collection(name="memory_machine_corpus")

docs = []
metadatas = []
ids = []

_log("🗄️ Chunking and cataloging raw data files...")

for filename in os.listdir(DATA_DIR):
    if filename.endswith(".txt") or filename.endswith(".md"):
        # Skip the compiled dossiers to avoid duplicating data in the vector space
        if filename in ["ParksInfoCompiled.md", "ParksRawDataArchive.md"]:
            continue

        filepath = os.path.join(DATA_DIR, filename)
        site_name = filename.split("_")[0].replace(".md", "")

        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()

        # Chunking Strategy: Split by double newlines to keep paragraphs/thoughts together
        chunks = text.split("\n\n")

        for i, chunk in enumerate(chunks):
            if len(chunk.strip()) > 40:  # Ignore tiny useless fragments
                clean = chunk.strip()
                docs.append(clean)
                metadatas.append({"site": site_name, "source": filename})
                # Deterministic id (file + chunk index + content hash) so re-running
                # this script after a re-scrape upserts in place instead of piling
                # up duplicate embeddings for unchanged files.
                digest = hashlib.sha1(clean.encode("utf-8")).hexdigest()[:12]
                ids.append(f"{filename}:{i}:{digest}")

if docs:
    _log(f"📦 Embedding and storing {len(docs)} memories into the latent space...")
    # Upsert (not add) so re-runs update/replace existing chunks by their
    # deterministic id instead of erroring or duplicating.
    collection.upsert(documents=docs, metadatas=metadatas, ids=ids)
    _log("\n✅ INGESTION COMPLETE! The Memory Machine AI Agent is fully loaded.")
else:
    _log("⚠️ No data found to ingest.")