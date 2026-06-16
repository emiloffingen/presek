from unittest.mock import patch

from tasks.intelligence import synthesis as synthesis_mod


def test_schedule_copy_purity_retry_uses_synthesis_queue():
    with patch.object(synthesis_mod, "schedule_task_once", return_value=True) as mock_schedule:
        ok = synthesis_mod._schedule_copy_purity_retry(
            "cluster-1",
            "legacy",
            lang="sr",
            fast_mode=False,
        )
    assert ok is True
    mock_schedule.assert_called_once()
    kwargs = mock_schedule.call_args.kwargs
    assert kwargs["queue"] == "synthesis"
    assert kwargs["countdown"] == synthesis_mod._COPY_PURITY_RETRY_DELAY_SECONDS


def test_schedule_copy_purity_retry_uses_fast_track_when_fast_mode():
    with patch.object(synthesis_mod, "schedule_task_once", return_value=True) as mock_schedule:
        synthesis_mod._schedule_copy_purity_retry(
            "cluster-2",
            None,
            lang="mk",
            fast_mode=True,
        )
    assert mock_schedule.call_args.kwargs["queue"] == "fast-track"
