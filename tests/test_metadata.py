from unittest.mock import patch

from utils.metadata import get_metadata


def test_get_metadata():
    mock_data = [{"value": '["keyword1", "keyword2"]'}]
    with patch("utils.metadata.db_manager.execute", return_value=mock_data):
        assert get_metadata("JUNK_KEYWORDS") is not None
        assert isinstance(get_metadata("JUNK_KEYWORDS"), list)
        assert get_metadata("JUNK_KEYWORDS") == ["keyword1", "keyword2"]


def test_get_metadata_empty():
    with patch("utils.metadata.db_manager.execute", return_value=[]):
        assert get_metadata("NON_EXISTENT") is None
        assert get_metadata("NON_EXISTENT", default="fallback") == "fallback"
