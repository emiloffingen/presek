import json
from core.health import get_source_statuses

def check_health():
    statuses = get_source_statuses()
    print(f"Checking health for {len(statuses)} sources:")
    
    # Group by country? health.py doesn't seem to store country in Redis status.
    # I'll just list those with errors or low quality.
    
    sorted_sources = sorted(statuses.items(), key=lambda x: x[1].get('quality_score', 1.0))
    
    for name, data in sorted_sources:
        if data.get('quality_score', 1.0) < 0.7 or data.get('status') == 'error':
            print(f"  {name:25} | Score: {data.get('quality_score'):4} | Status: {data.get('status'):8} | Error: {data.get('error')}")

if __name__ == "__main__":
    check_health()
