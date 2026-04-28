#!/bin/bash
# Presek Git Cleanup Assistant
# This script identifies large blobs in git history and provides commands to prune them.

echo "--- GIT HISTORY AUDIT ---"
# Find top 10 largest objects in git history
large_objects=$(git verify-pack -v .git/objects/pack/*.idx | sort -k 3 -n | tail -10)

echo "Largest objects in history:"
while read -r line; do
    hash=$(echo $line | awk '{print $1}')
    size=$(echo $line | awk '{print $3}')
    path=$(git rev-list --objects --all | grep $hash | awk '{print $2}')
    printf "%-10s %-10s %s\n" "$hash" "$(numfmt --to=iec $size)" "$path"
done <<< "$large_objects"

echo ""
echo "--- RECOMMENDATION ---"
echo "To permanently remove these files from history and shrink your .git directory,"
echo "you should use 'git-filter-repo' (recommended) or 'bfg-repo-cleaner'."
echo ""
echo "Example using git-filter-repo:"
echo "git filter-repo --path-glob 'screenshots/*' --path 'presek.log.2' --invert-paths"
echo ""
echo "WARNING: This will rewrite git history and requires a forced push to remote."
echo "Make sure to coordinate with other developers before running this."
