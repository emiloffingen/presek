
import logging
from ingestion import ingest_all_sources

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("presek")

def test_ingestion():
    print("Starting test ingestion...")
    count, errors = ingest_all_sources()
    print(f"Ingested {count} new articles.")
    if errors:
        print(f"Errors encountered: {len(errors)}")
        for source, err in errors[:5]:
            print(f"  - {source}: {err}")

if __name__ == "__main__":
    test_ingestion()
