import asyncio
import httpx
import sys

async def test_search():
    async with httpx.AsyncClient(base_url="http://localhost:5001") as client:
        try:
            response = await client.get("/api/news?q=test")
            print(f"Status: {response.status_code}")
            if response.status_code != 200:
                print(f"Error: {response.text}")
            else:
                print(f"Success: {len(response.json().get('clusters', []))} clusters found")
        except Exception as e:
            print(f"Connection error: {e}")

if __name__ == "__main__":
    asyncio.run(test_search())
