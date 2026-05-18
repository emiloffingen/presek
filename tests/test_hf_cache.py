import os

import core.hf_cache as hf_cache


def test_configure_model_cache_uses_app_owned_paths(monkeypatch, tmp_path):
    app_root = tmp_path / "runtime" / "current"
    shared_root = tmp_path / "runtime" / "shared"
    app_root.mkdir(parents=True)
    shared_root.mkdir(parents=True)
    module_path = app_root / "hf_cache.py"
    module_path.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(hf_cache, "__file__", str(module_path))
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_CACHE", raising=False)
    monkeypatch.delenv("SENTENCE_TRANSFORMERS_HOME", raising=False)

    hf_cache.configure_huggingface_cache()

    expected_root = os.path.join(str(shared_root), "huggingface")
    assert os.environ["HF_HOME"] == expected_root
    assert os.environ["HF_HUB_CACHE"] == os.path.join(expected_root, "hub")
    assert "TRANSFORMERS_CACHE" not in os.environ
    assert os.environ["SENTENCE_TRANSFORMERS_HOME"] == os.path.join(expected_root, "sentence_transformers")


def test_configure_model_cache_falls_back_inside_repo(monkeypatch, tmp_path):
    app_root = tmp_path / "repo"
    app_root.mkdir(parents=True)
    module_path = app_root / "hf_cache.py"
    module_path.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(hf_cache, "__file__", str(module_path))
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.delenv("HF_HUB_CACHE", raising=False)
    monkeypatch.delenv("TRANSFORMERS_CACHE", raising=False)
    monkeypatch.delenv("SENTENCE_TRANSFORMERS_HOME", raising=False)

    hf_cache.configure_huggingface_cache()

    expected_root = os.path.join(str(app_root), ".cache", "huggingface")
    assert os.environ["HF_HOME"] == expected_root
    assert os.environ["HF_HUB_CACHE"] == os.path.join(expected_root, "hub")
    assert "TRANSFORMERS_CACHE" not in os.environ
    assert os.environ["SENTENCE_TRANSFORMERS_HOME"] == os.path.join(expected_root, "sentence_transformers")
