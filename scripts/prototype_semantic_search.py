
import asyncio
import logging
import sys
from database import db_manager as db
from embeddings import generate_query_embedding

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek.semantic_prototype")

async def run_semantic_search_test(query: str, limit: int = 5):
    print(f"\n--- Presek Semantic Search Prototype (MiniLM) ---")
    print(f"Query: \"{query}\"")
    print(f"Goal: Find Macedonian news semantically related to this (even if English).\n")

    # 1. Generate the embedding for the query (English or Macedonian)
    vector = generate_query_embedding(query)
    if not vector:
        print("Failed to generate query embedding.")
        return

    # 2. Perform the semantic search in pgvector
    # search_semantic already handles the vector distance calculation
    results = db.search_semantic(vector, limit=limit)

    if not results:
        print("No semantically similar articles found in the last 7 days.")
        return

    print(f"Found {len(results)} matches:\n")
    for i, res in enumerate(results, 1):
        similarity = res.get('similarity', 0)
        source = res.get('source', 'Unknown')
        title = res.get('title', 'No Title')
        
        print(f"{i}. [{source}] (Similarity: {similarity:.4f})")
        print(f"   {title}")
        print("-" * 40)

if __name__ == "__main__":
    # Default query if none provided
    test_query = "energy crisis and electricity prices"
    if len(sys.argv) > 1:
        test_query = " ".join(sys.argv[1:])
    
    asyncio.run(run_semantic_search_test(test_query))
