from core.config import API_MAX_Q_LEN
from core.runtime_limits import MAX_QUERY_PARAM_LENGTH, MAX_REQUEST_BODY_SIZE
from routes.common import _is_rate_limited_path
from routes.security import MAX_HEADER_VALUE_LENGTH


def test_limits_match_security_middleware():
    assert MAX_QUERY_PARAM_LENGTH == API_MAX_Q_LEN
    assert MAX_REQUEST_BODY_SIZE == 10 * 1024 * 1024
    assert MAX_HEADER_VALUE_LENGTH == 2000


def test_rate_limited_paths_include_versioned_api_routes():
    assert _is_rate_limited_path("/api/news") is True
    assert _is_rate_limited_path("/api/v1/news") is True
    assert _is_rate_limited_path("/api/v1/proxy") is True
    assert _is_rate_limited_path("/api/v1/profile/sync/init") is True
    assert _is_rate_limited_path("/api/health") is False
