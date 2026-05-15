from core.health import get_source_statuses

def count_broken_feeds():
    statuses = get_source_statuses()
    error_sources = [name for name, data in statuses.items() if data.get('status') == 'error']
    
    print(f"Total sources tracked in health: {len(statuses)}")
    print(f"Sources in 'error' state: {len(error_sources)}")
    
    # Optional: categorizing errors
    error_types = {}
    for name in error_sources:
        err_msg = statuses[name].get('error', 'Unknown error')
        # Simplify error message for grouping
        if "404" in err_msg:
            kind = "404 Not Found"
        elif "Timeout" in err_msg:
            kind = "Timeout"
        elif "Connection error" in err_msg:
            kind = "Connection error / DNS"
        elif "Cloudflare" in err_msg:
            kind = "Cloudflare / Blocked"
        elif "520" in err_msg or "526" in err_msg:
            kind = "Server error (5xx)"
        else:
            kind = "Other"
        error_types[kind] = error_types.get(kind, 0) + 1
        
    print("\nError Breakdown:")
    for kind, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {kind}: {count}")

if __name__ == "__main__":
    count_broken_feeds()
