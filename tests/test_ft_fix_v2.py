import os
import pytest

fasttext = pytest.importorskip("fasttext")


def test_fasttext():
    cache_dir = os.path.expanduser("~/.cache/fasttext")
    model_path = os.path.join(cache_dir, "lid.176.ftz")
    model = fasttext.load_model(model_path)

    texts = ["Ова е македонски текст.", "Ovo je srpska latinica.", "Danas je lep dan u Beogradu."]

    for text in texts:
        res = model.predict([text], k=1)
        label = res[0][0][0].replace("__label__", "")
        prob = res[1][0][0]
        print(f"Text: {text} | Label: {label} | Prob: {prob:.4f}")


if __name__ == "__main__":
    test_fasttext()
