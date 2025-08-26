"""
Integration tests for ollama client signing functionality.

Tests the full integration between client, signing logic, and auth modules.
"""

import os
import urllib.parse
from unittest.mock import Mock, patch, MagicMock

import httpx

from ollama import Client, AsyncClient


class TestClientSigningIntegration:
    """Test client integration with signing functionality."""
    
    def test_client_no_signing_by_default(self):
        """Test that clients don't sign requests by default."""
        # Mock transport to capture requests
        requests_captured = []
        
        def capture_request(request):
            requests_captured.append(request)
            return httpx.Response(200, json={"ok": True})
        
        transport = httpx.MockTransport(capture_request)
        client = Client(host="http://localhost:11434", transport=transport)
        
        # Make a request
        response = client._request_raw("GET", "/api/version")
        
        # Check that no signing happened
        assert len(requests_captured) == 1
        request = requests_captured[0]
        
        # Should not have timestamp in query
        assert "ts=" not in str(request.url.query)
        # Should not have authorization header
        assert "authorization" not in request.headers
    
    def test_client_signs_with_ollama_auth_env(self):
        """Test that clients sign when OLLAMA_AUTH is set."""
        requests_captured = []
        
        def capture_request(request):
            requests_captured.append(request)
            return httpx.Response(200, json={"ok": True})
        
        transport = httpx.MockTransport(capture_request)
        
        # Mock the signing function to avoid needing real keys
        with patch('ollama._signing.sign_challenge') as mock_sign:
            mock_sign.return_value = "mock_token"
            
            with patch.dict(os.environ, {"OLLAMA_AUTH": "1"}):
                client = Client(host="http://localhost:11434", transport=transport)
                response = client._request_raw("GET", "/api/version")
        
        # Check that signing happened
        assert len(requests_captured) == 1
        request = requests_captured[0]
        
        # Should have timestamp in query
        assert "ts=" in str(request.url.query)
        # Should have authorization header
        assert "authorization" in request.headers
        assert request.headers["authorization"] == "mock_token"
    
    def test_client_signs_with_ollama_com_hostname(self):
        """Test that clients sign when connecting to ollama.com."""
        requests_captured = []
        
        def capture_request(request):
            requests_captured.append(request)
            return httpx.Response(200, json={"ok": True})
        
        transport = httpx.MockTransport(capture_request)
        
        # Mock the signing function
        with patch('ollama._signing.sign_challenge') as mock_sign:
            mock_sign.return_value = "mock_token_ollama"
            
            # Clear OLLAMA_AUTH to test hostname-based signing
            with patch.dict(os.environ, {}, clear=True):
                client = Client(host="https://ollama.com", transport=transport)
                response = client._request_raw("POST", "/api/generate")
        
        # Check that signing happened
        assert len(requests_captured) == 1
        request = requests_captured[0]
        
        # Should have timestamp in query
        assert "ts=" in str(request.url.query)
        # Should have authorization header
        assert "authorization" in request.headers
        assert request.headers["authorization"] == "mock_token_ollama"
    
    def test_client_preserves_existing_headers(self):
        """Test that client preserves existing headers when signing."""
        requests_captured = []
        
        def capture_request(request):
            requests_captured.append(request)
            return httpx.Response(200, json={"ok": True})
        
        transport = httpx.MockTransport(capture_request)
        
        with patch('ollama._signing.sign_challenge') as mock_sign:
            mock_sign.return_value = "mock_token"
            
            with patch.dict(os.environ, {"OLLAMA_AUTH": "1"}):
                client = Client(host="http://localhost:11434", transport=transport)
                response = client._request_raw(
                    "POST", 
                    "/api/generate",
                    headers={"Custom-Header": "custom-value", "Content-Type": "application/json"}
                )
        
        request = requests_captured[0]
        
        # Should have both custom headers and authorization
        assert request.headers["custom-header"] == "custom-value"
        assert request.headers["content-type"] == "application/json"
        assert request.headers["authorization"] == "mock_token"
    
    def test_client_handles_query_params_correctly(self):
        """Test that client correctly handles existing query parameters."""
        requests_captured = []
        
        def capture_request(request):
            requests_captured.append(request)
            return httpx.Response(200, json={"ok": True})
        
        transport = httpx.MockTransport(capture_request)
        
        with patch('ollama._signing.sign_challenge') as mock_sign:
            mock_sign.return_value = "mock_token"
            
            with patch.dict(os.environ, {"OLLAMA_AUTH": "1"}):
                client = Client(host="http://localhost:11434", transport=transport)
                response = client._request_raw("GET", "/api/tags?model=llama3")
        
        request = requests_captured[0]
        
        # Handle the case where query might be bytes or string
        query_string = request.url.query
        if isinstance(query_string, bytes):
            query_string = query_string.decode('utf-8')
        
        # Should preserve existing query params and add timestamp
        query_params = urllib.parse.parse_qs(query_string or "")
        
        assert "model" in query_params, f"model not found in {query_params}"
        assert query_params["model"] == ["llama3"]
        assert "ts" in query_params, f"ts not found in {query_params}"
        assert len(query_params["ts"]) == 1  # Should have exactly one timestamp
    
    def test_client_only_signs_relative_paths(self):
        """Test that client only signs relative path requests."""
        requests_captured = []
        
        def capture_request(request):
            requests_captured.append(request)
            return httpx.Response(200, json={"ok": True})
        
        transport = httpx.MockTransport(capture_request)
        
        with patch('ollama._signing.sign_challenge') as mock_sign:
            mock_sign.return_value = "mock_token"
            
            with patch.dict(os.environ, {"OLLAMA_AUTH": "1"}):
                client = Client(host="http://localhost:11434", transport=transport)
                
                # This should be signed (relative path)
                response1 = client._request_raw("GET", "/api/version")
                
                # This should NOT be signed (absolute URL)
                response2 = client._request_raw("GET", "http://external.com/api/data")
        
        assert len(requests_captured) == 2
        
        # First request (relative path) should be signed
        relative_request = requests_captured[0]
        assert "ts=" in str(relative_request.url.query)
        assert "authorization" in relative_request.headers
        
        # Second request (absolute URL) should NOT be signed
        absolute_request = requests_captured[1]
        assert "ts=" not in str(absolute_request.url.query)
        assert "authorization" not in absolute_request.headers


class TestAsyncClientSigningIntegration:
    """Test async client integration with signing functionality."""
    
    async def test_async_client_signs_correctly(self):
        """Test that async client signs requests correctly."""
        requests_captured = []
        
        async def capture_request(request):
            requests_captured.append(request)
            return httpx.Response(200, json={"ok": True})
        
        transport = httpx.MockTransport(capture_request)
        
        with patch('ollama._signing.sign_challenge') as mock_sign:
            mock_sign.return_value = "async_mock_token"
            
            with patch.dict(os.environ, {"OLLAMA_AUTH": "1"}):
                client = AsyncClient(host="http://localhost:11434", transport=transport)
                response = await client._request_raw("GET", "/api/version")
        
        # Check that signing happened
        assert len(requests_captured) == 1
        request = requests_captured[0]
        
        # Should have timestamp in query
        assert "ts=" in str(request.url.query)
        # Should have authorization header
        assert "authorization" in request.headers
        assert request.headers["authorization"] == "async_mock_token"


if __name__ == "__main__":
    # Simple test runner for sync tests only (async needs event loop)
    test_classes = [TestClientSigningIntegration]
    
    all_passed = True
    
    for test_class in test_classes:
        print(f"\n=== Running {test_class.__name__} ===")
        instance = test_class()
        
        for method_name in dir(instance):
            if method_name.startswith('test_') and 'async' not in method_name:
                try:
                    print(f"  {method_name}... ", end="")
                    method = getattr(instance, method_name)
                    method()
                    print("PASSED")
                except Exception as e:
                    print(f"FAILED: {e}")
                    import traceback
                    traceback.print_exc()
                    all_passed = False
    
    if all_passed:
        print("\n✅ All client integration tests passed!")
    else:
        print("\n❌ Some client integration tests failed!")