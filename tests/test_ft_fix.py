import os
import pytest

fasttext = pytest.importorskip("fasttext")


def test_fasttext():
    cache_dir = os.path.expanduser("~/.cache/fasttext")
    model_path = os.path.join(cache_dir, "lid.176.ftz")
    if not os.path.exists(model_path):
        print("Model not found")
        return

    model = fasttext.load_model(model_path)
    text = "Ovo je test rečenica."

    print("Testing single string:")
    try:
        res = model.predict(text, k=1)
        print(f"Success: {res}")
    except Exception as e:
        print(f"Failed: {e}")

    print("\nTesting list of strings:")
    try:
        res = model.predict([text], k=1)
        print(f"Success: {res}")
    except Exception as e:
        print(f"Failed: {e}")


if __name__ == "__main__":
    test_fasttext()
