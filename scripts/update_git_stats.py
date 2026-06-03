import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATS_FILE = ROOT / "web" / "src" / "git_stats.json"

def get_git_stats():
    try:
        # 1. Total commits
        commit_count_res = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True
        )
        commits = int(commit_count_res.stdout.strip())
        
        # 2. First commit date
        first_date_res = subprocess.run(
            ["git", "log", "--reverse", "--format=%ad", "--date=short"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True
        )
        first_date_str = first_date_res.stdout.splitlines()[0].strip()
        
        # 3. Latest commit date
        latest_date_res = subprocess.run(
            ["git", "log", "-n", "1", "--format=%ad", "--date=short"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True
        )
        latest_date_str = latest_date_res.stdout.strip()
        
        # Calculate days online (inclusive of start date)
        d1 = datetime.strptime(first_date_str, "%Y-%m-%d")
        d2 = datetime.strptime(latest_date_str, "%Y-%m-%d")
        days = (d2 - d1).days + 1
        
        return {
            "commits": commits,
            "days": days
        }
    except Exception as e:
        print(f"Error getting git stats: {e}")
        # Fallback values
        return {
            "commits": 2347,
            "days": 79
        }

def main():
    stats = get_git_stats()
    STATS_FILE.write_text(json.dumps(stats, indent=2) + "\n", encoding="utf-8")
    print(f"Updated git stats: {stats}")

if __name__ == "__main__":
    main()
