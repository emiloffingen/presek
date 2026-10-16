"""The homepage synthesis script must not report a cluster as upgraded when nothing was persisted."""

from types import SimpleNamespace

import pytest

from scripts import synthesize_homepage as hp


def _args():
    return SimpleNamespace(dry_run=False, provider=None, fast=False, no_force_llm=False)


def _stub(monkeypatch, outcomes):
    """outcomes: cluster id -> value returned by run_cluster_synthesis."""
    monkeypatch.setattr(hp, "_targets", lambda args: list(outcomes))
    monkeypatch.setattr(hp, "_load_cluster_articles_for_synthesis", lambda cid: [])
    monkeypatch.setattr(hp, "_build_cluster_synthesis_content", lambda rows: "")
    monkeypatch.setattr(hp, "_summarize", lambda cid: [])
    monkeypatch.setattr(hp, "run_cluster_synthesis", lambda cid, content, **kw: outcomes[cid])


def test_unpersisted_cluster_counts_as_failed(monkeypatch, capsys):
    _stub(monkeypatch, {"good": True, "bad": False})
    hp._run(_args())
    assert "done: upgraded 1, failed 1, of 2" in capsys.readouterr().out


def test_none_return_is_still_counted_as_upgraded(monkeypatch, capsys):
    # Older callers/stubs return None; only an explicit False means "nothing persisted".
    _stub(monkeypatch, {"a": None})
    hp._run(_args())
    assert "done: upgraded 1, failed 0, of 1" in capsys.readouterr().out


def test_all_unpersisted_exits_nonzero(monkeypatch, capsys):
    _stub(monkeypatch, {"a": False, "b": False})
    with pytest.raises(SystemExit) as exc:
        hp._run(_args())
    assert exc.value.code == 1
    assert "upgraded 0, failed 2" in capsys.readouterr().out
