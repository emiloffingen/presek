
with open('tasks/intelligence.py', 'r') as f:
    lines = f.readlines()

is_grounded_idx = -1
for i, line in enumerate(lines):
    if line.startswith('def _is_grounded_synthesis('):
        is_grounded_idx = i
        break

from_idx = -1
for i, line in enumerate(lines):
    if "source_lower = source_context.casefold()" in line:
        from_idx = i
        break

if is_grounded_idx != -1 and from_idx != -1:
    top_part = lines[:is_grounded_idx + 6] # Up to the end of the top part of _is_grounded_synthesis
    
    # find where _is_grounded_synthesis continues
    bottom_part = lines[from_idx:]
    
    # find where backfill_cluster_summaries_task ends (before from_idx)
    middle_part = lines[is_grounded_idx + 6:from_idx]
    
    new_lines = top_part + bottom_part + middle_part
    
    with open('tasks/intelligence.py', 'w') as f:
        f.writelines(new_lines)
    print("Fixed!")
else:
    print("Could not find boundaries")
