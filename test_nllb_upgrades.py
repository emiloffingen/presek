import logging
import nllb_translate
import time

logging.basicConfig(level=logging.INFO)

def test_masking_and_cache():
    text = "Сиљановска-Давкова го потпиша указот за новиот состав на Владата."
    print(f"\nOriginal: {text}")
    
    # First run (should mask, translate and cache)
    t0 = time.time()
    translated1 = nllb_translate.translate(text, "mk", "en")
    t1 = time.time()
    print(f"Translated 1: {translated1} (Time: {t1-t0:.2f}s)")
    
    if "Христијан Мицкоски" in translated1 and "Урсула фон дер Лајен" in translated1:
        print("SUCCESS: Entities preserved through masking!")
    else:
        print("FAILURE: Entities were mangled or translated.")
        
    # Second run (should hit cache)
    t2 = time.time()
    translated2 = nllb_translate.translate(text, "mk", "en")
    t3 = time.time()
    print(f"Translated 2: {translated2} (Time: {t3-t2:.2f}s)")
    
    if (t3-t2) < 0.1:
        print("SUCCESS: Cache hit!")
    else:
        print(f"FAILURE: Cache miss? (Time: {t3-t2:.2f}s)")

if __name__ == "__main__":
    test_masking_and_cache()
