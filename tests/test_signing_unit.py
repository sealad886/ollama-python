"""
Unit tests for ollama request signing functionality.

These tests verify the signing logic without requiring real SSH keys,
using mocked cryptography components where needed.
"""

import os
import time
import urllib.parse
from unittest.mock import Mock, patch, MagicMock

from ollama._signing import (
    _env_truthy, 
    should_sign, 
    prepare_signed_request,
    OLLAMA_AUTH_ENV
)


class TestEnvTruthy:
    """Test environment variable truth value parsing."""
    
    def test_env_truthy_with_truthy_values(self):
        """Test that truthy string values return True."""
        truthy_values = ["1", "true", "yes", "on", "TRUE", "Yes", "ON"]
        
        for value in truthy_values:
            with patch.dict(os.environ, {"TEST_VAR": value}):
                assert _env_truthy("TEST_VAR") is True
    
    def test_env_truthy_with_falsy_values(self):
        """Test that falsy string values return False."""
        falsy_values = ["0", "false", "no", "off", "FALSE", "No", "OFF", ""]
        
        for value in falsy_values:
            with patch.dict(os.environ, {"TEST_VAR": value}):
                assert _env_truthy("TEST_VAR") is False
    
    def test_env_truthy_missing_var(self):
        """Test that missing environment variables return False."""
        with patch.dict(os.environ, {}, clear=True):
            assert _env_truthy("MISSING_VAR") is False


class TestShouldSign:
    """Test the should_sign decision logic."""
    
    def test_should_sign_with_ollama_auth_env(self):
        """Test signing when OLLAMA_AUTH environment variable is set."""
        with patch.dict(os.environ, {OLLAMA_AUTH_ENV: "1"}):
            assert should_sign("http://localhost:11434") is True
            assert should_sign("https://example.com") is True
            assert should_sign("https://ollama.com") is True
    
    def test_should_sign_with_ollama_com_hostname(self):
        """Test signing when hostname is ollama.com."""
        with patch.dict(os.environ, {}, clear=True):
            assert should_sign("https://ollama.com") is True
            assert should_sign("http://ollama.com") is True
            assert should_sign("https://ollama.com:8080") is True
            assert should_sign("http://ollama.com/some/path") is True
    
    def test_should_not_sign_other_hostnames(self):
        """Test that other hostnames don't trigger signing."""
        with patch.dict(os.environ, {}, clear=True):
            assert should_sign("http://localhost:11434") is False
            assert should_sign("https://example.com") is False
            assert should_sign("http://127.0.0.1:11434") is False
            assert should_sign("https://api.openai.com") is False
    
    def test_should_sign_with_invalid_url(self):
        """Test error handling with invalid URLs."""
        with patch.dict(os.environ, {}, clear=True):
            # Should not crash and return False for invalid URLs
            assert should_sign("not-a-url") is False
            assert should_sign("") is False


class TestPrepareSignedRequest:
    """Test the prepare_signed_request function."""
    
    def test_no_signing_required(self):
        """Test that requests are passed through unchanged when signing not required."""
        with patch.dict(os.environ, {}, clear=True):
            headers = {"content-type": "application/json", "Custom-Header": "value"}
            path, returned_headers = prepare_signed_request(
                "http://localhost:11434", "GET", "/api/generate", headers
            )
            
            assert path == "/api/generate"
            # Headers should be lowercased but otherwise unchanged
            assert returned_headers == {
                "content-type": "application/json",
                "custom-header": "value"
            }
    
    @patch('ollama._signing.sign_challenge')
    @patch('ollama._signing.time.time')
    def test_basic_signing_behavior(self, mock_time, mock_sign):
        """Test basic signing behavior with mocked dependencies."""
        # Mock current time
        mock_time.return_value = 1234567890
        mock_sign.return_value = "mock_token"
        
        with patch.dict(os.environ, {OLLAMA_AUTH_ENV: "1"}):
            headers = {"content-type": "application/json"}
            path, returned_headers = prepare_signed_request(
                "http://localhost:11434", "GET", "/api/generate", headers
            )
            
            # Check that timestamp was added to path
            assert "ts=1234567890" in path
            assert path.startswith("/api/generate?")
            
            # Check that authorization header was added
            assert returned_headers["authorization"] == "mock_token"
            assert returned_headers["content-type"] == "application/json"
            
            # Verify sign_challenge was called with correct challenge
            mock_sign.assert_called_once()
            call_args = mock_sign.call_args[0]
            challenge = call_args[0].decode('utf-8')
            assert challenge == "GET,/api/generate?ts=1234567890"
    
    @patch('ollama._signing.sign_challenge')
    @patch('ollama._signing.time.time')
    def test_signing_with_existing_query_params(self, mock_time, mock_sign):
        """Test signing when path already has query parameters."""
        mock_time.return_value = 1234567890
        mock_sign.return_value = "mock_token"
        
        with patch.dict(os.environ, {OLLAMA_AUTH_ENV: "1"}):
            path, _ = prepare_signed_request(
                "http://localhost:11434", "POST", "/api/generate?model=llama3", {}
            )
            
            # Should preserve existing query params and add timestamp
            parsed = urllib.parse.urlparse(path)
            query_params = urllib.parse.parse_qs(parsed.query)
            
            assert "model" in query_params
            assert query_params["model"] == ["llama3"]
            assert "ts" in query_params
            assert query_params["ts"] == ["1234567890"]
            
            # Verify challenge construction with complex query string
            mock_sign.assert_called_once()
            challenge = mock_sign.call_args[0][0].decode('utf-8')
            # Challenge should include the full query string with ts parameter
            assert challenge.startswith("POST,/api/generate?")
            assert "ts=1234567890" in challenge
            assert "model=llama3" in challenge
    
    @patch('ollama._signing.sign_challenge')
    @patch('ollama._signing.time.time')
    def test_different_http_methods(self, mock_time, mock_sign):
        """Test signing with different HTTP methods."""
        mock_time.return_value = 1234567890
        mock_sign.return_value = "mock_token"
        
        methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
        
        with patch.dict(os.environ, {OLLAMA_AUTH_ENV: "1"}):
            for method in methods:
                mock_sign.reset_mock()
                prepare_signed_request(
                    "http://localhost:11434", method, "/api/test", {}
                )
                
                challenge = mock_sign.call_args[0][0].decode('utf-8')
                assert challenge.startswith(f"{method},")
    
    def test_headers_case_insensitive_handling(self):
        """Test that headers are properly normalized to lowercase."""
        with patch.dict(os.environ, {}, clear=True):
            headers = {
                "Content-Type": "application/json",
                "CUSTOM-HEADER": "value",
                "User-Agent": "test-agent"
            }
            
            _, returned_headers = prepare_signed_request(
                "http://localhost:11434", "GET", "/api/test", headers
            )
            
            expected_headers = {
                "content-type": "application/json",
                "custom-header": "value", 
                "user-agent": "test-agent"
            }
            assert returned_headers == expected_headers
    
    def test_none_headers_handling(self):
        """Test that None headers are handled gracefully."""
        with patch.dict(os.environ, {}, clear=True):
            path, headers = prepare_signed_request(
                "http://localhost:11434", "GET", "/api/test", None
            )
            
            assert path == "/api/test"
            assert headers == {}


class TestChallengeConstruction:
    """Test specific aspects of challenge string construction."""
    
    @patch('ollama._signing.sign_challenge')
    @patch('ollama._signing.time.time')
    def test_challenge_format_no_existing_query(self, mock_time, mock_sign):
        """Test challenge format when no existing query parameters."""
        mock_time.return_value = 1234567890
        mock_sign.return_value = "mock_token"
        
        with patch.dict(os.environ, {OLLAMA_AUTH_ENV: "1"}):
            prepare_signed_request("http://localhost:11434", "GET", "/api/test", {})
            
            challenge = mock_sign.call_args[0][0].decode('utf-8')
            assert challenge == "GET,/api/test?ts=1234567890"
    
    @patch('ollama._signing.sign_challenge')
    @patch('ollama._signing.time.time')
    def test_challenge_format_with_existing_query(self, mock_time, mock_sign):
        """Test challenge format when existing query parameters are present."""
        mock_time.return_value = 1234567890
        mock_sign.return_value = "mock_token"
        
        with patch.dict(os.environ, {OLLAMA_AUTH_ENV: "1"}):
            prepare_signed_request(
                "http://localhost:11434", "POST", "/api/test?param=value", {}
            )
            
            challenge = mock_sign.call_args[0][0].decode('utf-8')
            # Should include both existing params and timestamp
            assert challenge.startswith("POST,/api/test?")
            assert "param=value" in challenge
            assert "ts=1234567890" in challenge


if __name__ == "__main__":
    # Simple test runner if pytest is not available
    import sys
    
    test_classes = [TestEnvTruthy, TestShouldSign, TestPrepareSignedRequest, TestChallengeConstruction]
    
    all_passed = True
    
    for test_class in test_classes:
        print(f"\n=== Running {test_class.__name__} ===")
        instance = test_class()
        
        for method_name in dir(instance):
            if method_name.startswith('test_'):
                try:
                    print(f"  {method_name}... ", end="")
                    method = getattr(instance, method_name)
                    method()
                    print("PASSED")
                except Exception as e:
                    print(f"FAILED: {e}")
                    all_passed = False
    
    if all_passed:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)