import importlib.util
import logging
import os
import sys
from unittest.mock import MagicMock, patch


def _load_notifier_class():
    """Load SystemNotifier without permanently replacing tasks.utils in sys.modules."""
    module_path = os.path.abspath("core/services/notifier.py")
    utils_mock = MagicMock()
    with patch.dict(sys.modules, {"tasks.utils": utils_mock}):
        spec = importlib.util.spec_from_file_location(
            "core.services.notifier_test",
            module_path,
        )
        notifier_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(notifier_module)
    return notifier_module.SystemNotifier


def test_notifier_logs_error(caplog):
    Notifier = _load_notifier_class()

    with caplog.at_level(logging.ERROR):
        Notifier.send_alert("TEST_ALERT", "This is a test alert", {"foo": "bar"})

    assert "[ALERT][TEST_ALERT]" in caplog.text
    assert "This is a test alert" in caplog.text
    assert "{'foo': 'bar'}" in caplog.text
