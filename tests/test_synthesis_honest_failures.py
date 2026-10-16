"""The homepage synthesis script must not report a cluster as upgraded when nothing was persisted,
and must pace its requests and retry the clusters that failed (rate limits recover)."""

from types import SimpleNamespace

import pytest

from scripts import synthesize_homepage as hp


def _args(**kw):
    base = dict(dry_run=False, provider=None, fast=False, no_force_llm=False, pause=0, retries=0, retry_wait=0)
    base.update(kw)
    return SimpleNamespace(**base)


def _stub(monkeypatch, outcomes):
    """outcomes: cluster id -> value (or list of values, one per call) returned by run_cluster_synthesis."""
    calls = []
    sleeps = []

    def fake_run(cid, content, **kw):
        calls.append(cid)
        value = outcomes[cid]
        return value.pop(0) if isinstance(value, list) else value

    monkeypatch.setattr(hp, "_targets", lambda args: list(outcomes))
    monkeypatch.setattr(hp, "_load_cluster_articles_for_synthesis", lambda cid: [])
    monkeypatch.setattr(hp, "_build_cluster_synthesis_content", lambda rows: "")
    monkeypatch.setattr(hp, "_summarize", lambda cid: [])
    monkeypatch.setattr(hp, "run_cluster_synthesis", fake_run)
    monkeypatch.setattr(hp.time, "sleep", lambda s: sleeps.append(s))
    return calls, sleeps


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


def test_failed_cluster_is_retried_and_recovers(monkeypatch, capsys):
    calls, sleeps = _stub(monkeypatch, {"good": True, "flaky": [False, True]})
    hp._run(_args(retries=1, retry_wait=90))
    assert "done: upgraded 2, failed 0, of 2" in capsys.readouterr().out
    assert calls == ["good", "flaky", "flaky"]  # only the failed cluster is retried
    assert sleeps == [90]


def test_retries_are_bounded(monkeypatch, capsys):
    calls, _ = _stub(monkeypatch, {"good": True, "never": [False, False, False, False]})
    hp._run(_args(retries=2, retry_wait=1))
    assert "done: upgraded 1, failed 1, of 2" in capsys.readouterr().out
    assert calls.count("never") == 3  # first pass + 2 retries


def test_pause_between_clusters_but_not_before_the_first(monkeypatch):
    _, sleeps = _stub(monkeypatch, {"a": True, "b": True, "c": True})
    hp._run(_args(pause=2.5))
    assert sleeps == [2.5, 2.5]
