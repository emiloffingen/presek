import asyncio
from database import db_manager
from embeddings import generate_query_embedding
import logging

logging.basicConfig(level=logging.INFO)

async def test_direct_search():
    q = "test"
    print(f"Testing search for: {q}")
    try:
        query_vec = generate_query_embedding(q)
        print(f"Generated embedding: {query_vec[:5] if query_vec else 'None'}...")
        
        row_limit = 6
        sort_by = "hybrid"
        
        print("Executing hybrid_search...")
        rows = await db_manager.async_hybrid_search(q, query_vec, limit=row_limit, sort_by=sort_by)
        print(f"Success! Found {len(rows)} rows")
    except Exception as e:
        print(f"Search failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_direct_search())
