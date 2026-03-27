import sqlite3
import os
import re

def patch_server():
    print("--- Patch Server Initialized ---")
    
    # 1. Database operation: Create table in presek.db
    try:
        conn = sqlite3.connect('presek.db')
        conn.execute("CREATE TABLE IF NOT EXISTS cluster_summaries (cluster_id TEXT PRIMARY KEY, summary TEXT, created_at TEXT)")
        conn.commit()
        conn.close()
        print("[DB] Verified table 'cluster_summaries' in 'presek.db'.")
    except Exception as e:
        print(f"[DB Error] {e}")

    # 2. Patch app.py
    if not os.path.exists('app.py'):
        print("[Error] app.py not found in current directory.")
        return

    try:
        with open('app.py', 'r', encoding='utf-8') as f:
            code = f.read()

        # Find the Gemini call inside the api_cluster_summary route.
        # It currently looks like: summary, tier = _call_ai(f"Наслови:\n{headlines}", SYNTHESIS_SYSTEM_PROMPT)
        # We use a regex that matches the line while preserving its indentation.
        
        # We target specifically the synthesis call which matches the error message provided by the user.
        target_pattern = r'(\s+)(summary, tier = _call_ai\(f"Наслови:\\n\{headlines\}", SYNTHESIS_SYSTEM_PROMPT\))'
        
        match = re.search(target_pattern, code)
        if match:
            indent = match.group(1)
            original_call = match.group(2)
            
            # Construct the replacement block
            # Note: We return the specific JSON if a 429/ResourceExhausted error is detected.
            patch_block = (
                f"{indent}try:\n"
                f"{indent}    {original_call}\n"
                f"{indent}except Exception as e:\n"
                f"{indent}    if '429' in str(e) or 'ResourceExhausted' in str(e):\n"
                f"{indent}        return jsonify({{\"error\": \"Синтезата се подготвува... Ве молиме обидете се повторно за некоја минута.\"}})\n"
                f"{indent}    summary, tier = None, None"
            )
            
            new_code = code.replace(match.group(0), patch_block)
            
            with open('app.py', 'w', encoding='utf-8') as f:
                f.write(new_code)
            print("[Patch] app.py successfully updated with try-except wrapper.")
        else:
            print("[Patch] Could not find the exact Gemini API call in app.py.")
            print("Target pattern looked for: summary, tier = _call_ai(f\"Наслови:\\n{headlines}\", SYNTHESIS_SYSTEM_PROMPT)")

    except Exception as e:
        print(f"[Patch Error] {e}")

if __name__ == "__main__":
    patch_server()
