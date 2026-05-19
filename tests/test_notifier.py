import importlib.util
import logging
import os
import sys
from unittest.mock import MagicMock

# Create a mock for tasks.utils
utils_mock = MagicMock()
sys.modules["tasks.utils"] = utils_mock

# Directly load the file to avoid loading the rest of the tasks package
spec = importlib.util.spec_from_file_location(
    "core.services.notifier",
    os.path.abspath("core/services/notifier.py"),
)
notifier_module = importlib.util.module_from_spec(spec)
sys.modules["core.services.notifier"] = notifier_module
spec.loader.exec_module(notifier_module)
Notifier = notifier_module.SystemNotifier


def test_notifier_logs_error(caplog):
    with caplog.at_level(logging.ERROR):
        Notifier.send_alert("TEST_ALERT", "This is a test alert", {"foo": "bar"})

    assert "[ALERT][TEST_ALERT]" in caplog.text
    assert "This is a test alert" in caplog.text
    assert "{'foo': 'bar'}" in caplog.text
