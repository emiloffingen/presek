import pytest
from unittest.mock import patch
from api_helpers import is_safe_url

@patch("socket.getaddrinfo")
def test_is_safe_url_valid_public(mock_getaddrinfo):
    mock_getaddrinfo.return_value = [(2, 1, 6, '', ('93.184.216.34', 0))]
    assert is_safe_url("https://google.com") is True
    assert is_safe_url("http://presek.live") is True

def test_is_safe_url_blocked_hostnames():
    assert is_safe_url("http://localhost") is False
    assert is_safe_url("http://127.0.0.1") is False
    assert is_safe_url("http://0.0.0.0") is False
    assert is_safe_url("http://metadata.google.internal") is False
    assert is_safe_url("http://169.254.169.254") is False

def test_is_safe_url_private_ips():
    assert is_safe_url("http://192.168.1.1") is False
    assert is_safe_url("http://10.0.0.1") is False
    assert is_safe_url("http://172.16.0.1") is False

@patch("socket.getaddrinfo")
def test_is_safe_url_dns_rebinding(mock_getaddrinfo):
    # Mock resolving to a private IP
    mock_getaddrinfo.return_value = [(2, 1, 6, '', ('192.168.1.1', 0))]
    assert is_safe_url("http://evil-dns-rebinding.com") is False
    
    # Mock resolving to multiple IPs, one of which is private
    mock_getaddrinfo.return_value = [
        (2, 1, 6, '', ('93.184.216.34', 0)), # example.com public IP
        (2, 1, 6, '', ('127.0.0.1', 0))      # localhost
    ]
    assert is_safe_url("http://mixed-ips.com") is False

def test_is_safe_url_invalid_scheme():
    assert is_safe_url("ftp://google.com") is False
    assert is_safe_url("file:///etc/passwd") is False
    assert is_safe_url("gopher://localhost") is False

def test_is_safe_url_metadata_markers():
    assert is_safe_url("http://metadata.internal.evil.com") is False
    assert is_safe_url("http://169.254.1.1.evil.com") is False
