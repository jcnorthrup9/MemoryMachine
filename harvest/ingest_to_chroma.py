import os
import chromadb
import uuid

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root (this file lives one level down)
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(BASE_DIR, "db")

print("🧠 Booting up ChromaDB Vector Engine...")

# Connect to the exact same database the FastAPI server uses
chroma_client = chromadb.PersistentClient(path=DB_PATH)
collection = chroma_client.get_or_create_collection(name="memory_machine_corpus")

docs = []
metadatas = []
ids = []

print("🗄️ Chunking and cataloging raw data files...")

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
        
        for chunk in chunks:
            if len(chunk.strip()) > 40:  # Ignore tiny useless fragments
                docs.append(chunk.strip())
                metadatas.append({"site": site_name, "source": filename})
                ids.append(str(uuid.uuid4()))

if docs:
    print(f"📦 Embedding and storing {len(docs)} memories into the latent space...")
    # Add all the chunks to the database
    # ChromaDB will automatically convert the text into numerical vectors using its built-in embedding model!
    collection.add(documents=docs, metadatas=metadatas, ids=ids)
    print("\n✅ INGESTION COMPLETE! The Memory Machine AI Agent is fully loaded.")
else:
    print("⚠️ No data found to ingest.")