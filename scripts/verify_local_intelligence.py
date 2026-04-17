import sys
import os
import logging

# Ensure project root is in path
sys.path.insert(0, os.getcwd())

logging.basicConfig(level=logging.INFO)
from entities import extract_entities
from nlp.sentiment import analyze_sentiment_locally

def verify():
    print("--- Testing Local Entity Extraction (spaCy) ---")
    text = "Христијан Мицкоски оствари средба со амбасадорот на Германија во Скопје. ВМРО-ДПМНЕ најави нови реформи."
    entities = extract_entities(text)
    print(f"Text: {text}")
    print(f"Extracted Entities: {entities}")
    
    # Check if we got the expected ones
    names = [e['name'] for e in entities]
    assert "Христијан Мицкоски" in names, "Failed to extract person from lexicon/spacy"
    assert "ВМРО-ДПМНЕ" in names, "Failed to extract organization from lexicon"
    
    print("\n--- Testing Local Sentiment Analysis ---")
    pos_text = "Одличен напредок и голем успех за македонската економија."
    neg_text = "Страшен скандал и корупција во здравството предизвикаа хаос."
    
    pos_score = analyze_sentiment_locally(pos_text)
    neg_score = analyze_sentiment_locally(neg_text)
    
    print(f"Positive Text: {pos_text} | Score: {pos_score}")
    print(f"Negative Text: {neg_text} | Score: {neg_score}")
    
    assert pos_score > 0, "Positive sentiment not detected"
    assert neg_score < 0, "Negative sentiment not detected"
    
    print("\n✓ Local Intelligence Verification Passed!")

if __name__ == "__main__":
    try:
        verify()
    except Exception as e:
        print(f"\nx Verification Failed: {e}")
        sys.exit(1)
