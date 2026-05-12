from utils.metadata import get_metadata
import pytest

def test_get_metadata():
    assert get_metadata('JUNK_KEYWORDS') is not None
    assert isinstance(get_metadata('JUNK_KEYWORDS'), list)
