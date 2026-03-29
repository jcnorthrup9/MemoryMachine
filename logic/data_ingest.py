import os

def ingest_data():
    """
    Loads data from source files, splits it into chunks, and ingests it into a persistent ChromaDB vector store.
    """
    print("--- Starting Data Ingestion ---")

    # --- CONFIGURATION ---
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        from langchain_community.document_loaders import TextLoader, JSONLoader
        import chromadb
        from chromadb.utils import embedding_functions
    except ImportError:
        print("\n❌ ERROR: Necessary libraries not found.")
        print("   Please run the following command to install them:")
        print("   pip install langchain langchain-community chromadb sentence-transformers\n")
        return

    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    DB_DIR = os.path.join(BASE_DIR, 'db')
    CHUNK_SIZE = 800
    CHUNK_OVERLAP = 100

    # List of all data sources to be ingested into the vector database
    # Curated corpus: outdoor / public spaces only
    SOURCES = [
        {"type": "text", "path": os.path.join(DATA_DIR, "pershing_square_reviews.txt"),       "metadata": {"source": "Pershing Square"}},
        {"type": "text", "path": os.path.join(DATA_DIR, "schouwburgplein_reviews.txt"),        "metadata": {"source": "Schouwburgplein"}},
        {"type": "text", "path": os.path.join(DATA_DIR, "grand_park_la_reviews.txt"),          "metadata": {"source": "Grand Park LA"}},
        {"type": "text", "path": os.path.join(DATA_DIR, "tanner_springs_reviews.txt"),         "metadata": {"source": "Tanner Springs Park"}},
        {"type": "text", "path": os.path.join(DATA_DIR, "gardens_by_the_bay_reviews.txt"),     "metadata": {"source": "Gardens by the Bay"}},
        {"type": "text", "path": os.path.join(DATA_DIR, "superkilen_reviews.txt"),             "metadata": {"source": "Superkilen"}},
        {"type": "text", "path": os.path.join(DATA_DIR, "paley_park_reviews.txt"),             "metadata": {"source": "Paley Park"}},
        {"type": "text", "path": os.path.join(DATA_DIR, "klyde_warren_park_reviews.txt"),      "metadata": {"source": "Klyde Warren Park"}},
        {"type": "text", "path": os.path.join(DATA_DIR, "millennium_park_reviews.txt"),        "metadata": {"source": "Millennium Park"}},
        {"type": "text", "path": os.path.join(DATA_DIR, "parc_de_la_villette_reviews.txt"),    "metadata": {"source": "Parc de la Villette"}},
        {"type": "text", "path": os.path.join(DATA_DIR, "zaryadye_park_reviews.txt"),          "metadata": {"source": "Zaryadye Park"}},
    ]

    documents = []
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)

    # 1. Load and split documents from all sources
    for source in SOURCES:
        if not os.path.exists(source["path"]):
            print(f"⚠️  Warning: Source file not found, skipping: {source['path']}")
            continue
        
        print(f"   -> Loading: {os.path.basename(source['path'])}")
        loader = TextLoader(source["path"], encoding='utf-8')
        docs = loader.load_and_split(text_splitter=text_splitter)
        for doc in docs:
            doc.metadata.update(source["metadata"])
        documents.extend(docs)

    if not documents:
        print("[ERROR] No documents were loaded. Aborting ingestion.")
        return

    print(f"\n[OK] Loaded and split {len(documents)} document chunks.")
    print("--- Initializing Vector Database ---")

    # 2. Initialize ChromaDB client and create/get a collection
    client = chromadb.PersistentClient(path=DB_DIR)
    embedding_function = embedding_functions.DefaultEmbeddingFunction()
    # Delete and recreate the collection to ensure a clean corpus on each run
    try:
        client.delete_collection(name="memory_machine_corpus")
        print("   -> Deleted existing collection for fresh rebuild.")
    except Exception:
        pass
    collection = client.create_collection(
        name="memory_machine_corpus",
        embedding_function=embedding_function,
        metadata={"hnsw:space": "cosine"}
    )

    print(f"[OK] ChromaDB collection 'memory_machine_corpus' is ready.")
    print("--- Ingesting documents into database (this may take a few minutes)... ---")

    # 3. Add documents to the collection
    collection.add(
        ids=[f"doc_{i}" for i in range(len(documents))],
        documents=[doc.page_content for doc in documents],
        metadatas=[doc.metadata for doc in documents]
    )

    print(f"\n[DONE] Ingestion complete! Database now contains {collection.count()} vector entries.")
    print(f"   Database is stored at: {DB_DIR}")

if __name__ == "__main__":
    ingest_data()