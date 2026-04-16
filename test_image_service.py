
import asyncio
import logging
from image_service import image_service
from database import db_manager as db

logging.basicConfig(level=logging.INFO)

async def test():
    # Pick an article that has an image_url but no local_image_path
    row = db.execute_one("SELECT id, image_url FROM articles WHERE image_url LIKE 'http%' AND local_image_path IS NULL LIMIT 1")
    if not row:
        print("No suitable article found")
        return
    
    print(f"Testing article {row['id']} with URL: {row['image_url']}")
    res = await image_service.process_and_save(row['image_url'], row['id'])
    print(f"Result: {res}")

if __name__ == "__main__":
    asyncio.run(test())
