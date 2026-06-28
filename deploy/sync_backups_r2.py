#!/usr/bin/env python3
import os
import sys
import glob
from pathlib import Path
import boto3
from botocore.client import Config

def main():
    # Find app root and load env file
    app_dir = Path(__file__).resolve().parents[1]
    runtime_dir = Path.home() / "presek-runtime"
    app_root = runtime_dir if (runtime_dir / "shared").is_dir() else app_dir
    
    env_file = app_root / "shared" / ".env"
    if not env_file.is_file():
        env_file = app_dir / ".env"
        
    if env_file.is_file():
        from dotenv import load_dotenv
        load_dotenv(env_file)
        
    access_key_id = os.environ.get("R2_ACCESS_KEY_ID")
    secret_access_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    endpoint_url = os.environ.get("R2_ENDPOINT_URL")
    bucket_name = os.environ.get("R2_BUCKET_NAME", "presek-backups")
    
    if not all([access_key_id, secret_access_key, endpoint_url]):
        print("Cloudflare R2 backup settings not configured in .env; skipping sync.")
        return 0
        
    backup_dir = Path(os.environ.get("BACKUP_DIR", app_root / "shared" / "backups"))
    if not backup_dir.is_dir():
        backup_dir = app_dir / "shared" / "backups"
        
    if not backup_dir.is_dir():
        print(f"Backup directory not found: {backup_dir}")
        return 1
        
    # Get local backups
    local_files = []
    for pattern in ["presek-*.sql.gz", "presek-*.sql.gz.gpg"]:
        local_files.extend(glob.glob(str(backup_dir / pattern)))
        
    if not local_files:
        print("No local backups found to sync.")
        return 0

    print(f"Initializing R2 connection to {endpoint_url}...")
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        config=Config(signature_version="s3v4"),
    )
    
    # 1. Upload local files to R2
    for file_path_str in local_files:
        file_path = Path(file_path_str)
        key = file_path.name
        
        # Check if already exists in bucket
        try:
            s3.head_object(Bucket=bucket_name, Key=key)
            print(f"  - {key} already exists in R2; skipping upload.")
        except Exception:
            # Does not exist or error, upload it
            print(f"  - Uploading {key} to R2...")
            try:
                s3.upload_file(str(file_path), bucket_name, key)
                print(f"    ✓ Upload complete")
            except Exception as e:
                print(f"    x Upload failed: {e}", file=sys.stderr)
                
    # 2. Prune old backups in R2 to match local directory (sync deletion)
    print("Pruning old backups from R2...")
    try:
        response = s3.list_objects_v2(Bucket=bucket_name)
        if "Contents" in response:
            local_basenames = {Path(p).name for p in local_files}
            for obj in response["Contents"]:
                key = obj["Key"]
                if (key.startswith("presek-") and 
                    (key.endswith(".sql.gz") or key.endswith(".sql.gz.gpg")) and
                    key not in local_basenames):
                    print(f"  - Deleting old backup from R2: {key}...")
                    s3.delete_object(Bucket=bucket_name, Key=key)
                    print(f"    ✓ Deleted")
    except Exception as e:
        print(f"Failed to list or delete objects from R2: {e}", file=sys.stderr)
        
    print("Cloudflare R2 backup sync completed.")
    return 0

if __name__ == '__main__':
    sys.exit(main())
