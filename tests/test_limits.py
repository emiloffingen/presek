from core.config import API_MAX_Q_LEN
from core.limits import MAX_QUERY_PARAM_LENGTH, MAX_REQUEST_BODY_SIZE
from routes.security import MAX_HEADER_VALUE_LENGTH


def test_limits_match_security_middleware():
    assert MAX_QUERY_PARAM_LENGTH == API_MAX_Q_LEN
    assert MAX_REQUEST_BODY_SIZE == 10 * 1024 * 1024
    assert MAX_HEADER_VALUE_LENGTH == 2000
