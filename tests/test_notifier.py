import sys
import os
import importlib.util
import logging
from unittest.mock import MagicMock

# Create a mock for tasks.utils
utils_mock = MagicMock()
sys.modules["tasks.utils"] = utils_mock

# Directly load the file to avoid loading the rest of the tasks package
spec = importlib.util.spec_from_file_location(
    "tasks.notifier", os.path.abspath("tasks/notifier.py")
)
notifier_module = importlib.util.module_from_spec(spec)
sys.modules["tasks.notifier"] = notifier_module
spec.loader.exec_module(notifier_module)
Notifier = notifier_module.Notifier


def test_notifier_logs_error(caplog):
    with caplog.at_level(logging.ERROR):
        Notifier.send_alert("TEST_ALERT", "This is a test alert", {"foo": "bar"})

    assert "[ALERT][TEST_ALERT]" in caplog.text
    assert "This is a test alert" in caplog.text
    assert "{'foo': 'bar'}" in caplog.text
