"""
End-to-end tests for ollama request signing functionality.

Creates temporary test keys and validates the complete signing workflow.
"""

import base64
import os
import struct
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
import httpx

from ollama import Client
from ollama._auth import sign_challenge, DEFAULT_KEY_PATH


def create_test_ed25519_key():
    """Create a temporary Ed25519 key pair for testing."""
    # Generate key pair
    private_key = ed25519.Ed25519PrivateKey.generate()
    
    # Serialize private key in PEM format first, then load and convert to OpenSSH
    pem_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    # Load and convert to OpenSSH format
    loaded_key = serialization.load_pem_private_key(pem_bytes, password=None)
    openssh_bytes = loaded_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    return private_key, openssh_bytes


def unpack_ssh_string(data: bytes, offset: int = 0):
    """Unpack SSH wire-format string from data at offset."""
    if len(data) < offset + 4:
        raise ValueError("Data too short for SSH string")
    
    length = struct.unpack(">I", data[offset:offset+4])[0]
    if len(data) < offset + 4 + length:
        raise ValueError("Data too short for SSH string content")
    
    return data[offset+4:offset+4+length], offset+4+length


def verify_signature_format(token: str, challenge: bytes, expected_public_key: bytes):
    """Verify that a token has the correct format and valid signature."""
    # Split token
    if ":" not in token:
        raise ValueError("Token missing ':' separator")
    
    pub_b64, sig_b64 = token.split(":", 1)
    
    # Decode blobs
    pub_blob = base64.b64decode(pub_b64)
    sig_blob = base64.b64decode(sig_b64)
    
    # Parse public key blob
    pub_name, offset = unpack_ssh_string(pub_blob, 0)
    if pub_name != b"ssh-ed25519":
        raise ValueError(f"Expected ssh-ed25519, got {pub_name}")
    
    pub_key_data, offset = unpack_ssh_string(pub_blob, offset)
    if len(pub_key_data) != 32:
        raise ValueError(f"Expected 32-byte public key, got {len(pub_key_data)}")
    
    if offset != len(pub_blob):
        raise ValueError("Extra data in public key blob")
    
    # Parse signature blob
    sig_name, offset = unpack_ssh_string(sig_blob, 0)
    if sig_name != b"ssh-ed25519":
        raise ValueError(f"Expected ssh-ed25519 sig, got {sig_name}")
    
    sig_data, offset = unpack_ssh_string(sig_blob, offset)
    if len(sig_data) != 64:
        raise ValueError(f"Expected 64-byte signature, got {len(sig_data)}")
    
    if offset != len(sig_blob):
        raise ValueError("Extra data in signature blob")
    
    # Verify public key matches expected
    if pub_key_data != expected_public_key:
        raise ValueError("Public key doesn't match expected")
    
    # Verify signature
    public_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_key_data)
    try:
        public_key.verify(sig_data, challenge)
    except Exception as e:
        raise ValueError(f"Signature verification failed: {e}")
    
    return True


class TestEndToEndSigning:
    """End-to-end tests with real cryptography but temporary keys."""
    
    def test_complete_signing_workflow(self):
        """Test the complete signing workflow with a temporary key."""
        # Create temporary key
        private_key, private_key_bytes = create_test_ed25519_key()
        
        # Get public key bytes for verification
        public_key = private_key.public_key()
        public_key_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        
        # Create temporary key file
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='_ed25519') as f:
            f.write(private_key_bytes)
            temp_key_path = f.name
        
        try:
            # Test signing with the temporary key
            challenge = b"GET,/api/version?ts=1234567890"
            token = sign_challenge(challenge, key_path=temp_key_path)
            
            # Verify the token format and signature
            verify_signature_format(token, challenge, public_key_bytes)
            
            print("✅ Complete signing workflow test passed!")
            
        finally:
            # Clean up temporary key
            Path(temp_key_path).unlink()
    
    def test_client_with_temporary_key(self):
        """Test full client integration with a temporary key."""
        # Create temporary key
        private_key, private_key_bytes = create_test_ed25519_key()
        public_key = private_key.public_key()
        public_key_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw
        )
        
        # Create temporary key file
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='_ed25519') as f:
            f.write(private_key_bytes)
            temp_key_path = f.name
        
        try:
            # Capture requests
            captured_requests = []
            
            def capture_request(request):
                captured_requests.append(request)
                return httpx.Response(200, json={"status": "ok"})
            
            transport = httpx.MockTransport(capture_request)
            
            # Test with environment variable triggering signing
            with patch.dict(os.environ, {"OLLAMA_AUTH": "1"}):
                # Patch the key path to use our temporary key
                with patch('ollama._auth.DEFAULT_KEY_PATH', Path(temp_key_path)):
                    client = Client(host="http://localhost:11434", transport=transport)
                    response = client._request_raw("GET", "/api/version")
            
            # Verify request was signed
            assert len(captured_requests) == 1
            request = captured_requests[0]
            
            # Extract query parameters
            query_string = request.url.query
            if isinstance(query_string, bytes):
                query_string = query_string.decode('utf-8')
            
            assert "ts=" in query_string
            
            # Extract timestamp
            import urllib.parse
            query_params = urllib.parse.parse_qs(query_string)
            ts = query_params["ts"][0]
            
            # Verify authorization header
            assert "authorization" in request.headers
            token = request.headers["authorization"]
            
            # Reconstruct and verify challenge
            challenge = f"GET,/api/version?ts={ts}".encode('utf-8')
            verify_signature_format(token, challenge, public_key_bytes)
            
            print("✅ Client integration with temporary key test passed!")
            
        finally:
            # Clean up
            Path(temp_key_path).unlink()
    
    def test_client_with_ollama_com_hostname(self):
        """Test that client signs requests to ollama.com even without OLLAMA_AUTH."""
        # Create temporary key
        private_key, private_key_bytes = create_test_ed25519_key()
        
        with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='_ed25519') as f:
            f.write(private_key_bytes)
            temp_key_path = f.name
        
        try:
            captured_requests = []
            
            def capture_request(request):
                captured_requests.append(request)
                return httpx.Response(200, json={"status": "ok"})
            
            transport = httpx.MockTransport(capture_request)
            
            # Clear OLLAMA_AUTH environment
            with patch.dict(os.environ, {}, clear=True):
                # Use ollama.com hostname
                with patch('ollama._auth.DEFAULT_KEY_PATH', Path(temp_key_path)):
                    client = Client(host="https://ollama.com", transport=transport)
                    response = client._request_raw("POST", "/api/generate")
            
            # Verify request was signed
            assert len(captured_requests) == 1
            request = captured_requests[0]
            
            # Should have timestamp and authorization header
            query_string = request.url.query
            if isinstance(query_string, bytes):
                query_string = query_string.decode('utf-8')
            
            assert "ts=" in query_string
            assert "authorization" in request.headers
            
            print("✅ ollama.com hostname signing test passed!")
            
        finally:
            Path(temp_key_path).unlink()


def test_error_conditions():
    """Test various error conditions."""
    
    print("\n=== Testing Error Conditions ===")
    
    # Test missing key file
    try:
        sign_challenge(b"test", key_path="/nonexistent/key/path")
        assert False, "Should have raised FileNotFoundError"
    except FileNotFoundError:
        print("✅ Missing key file error handled correctly")
    
    # Test with cryptography unavailable (mock)
    with patch('ollama._auth._ensure_cryptography_available', side_effect=ImportError("cryptography not available")):
        try:
            sign_challenge(b"test")
            assert False, "Should have raised ImportError"
        except ImportError as e:
            assert "cryptography" in str(e)
            print("✅ Missing cryptography error handled correctly")
    
    # Test wrong key type (create an RSA key and try to load it as ed25519)
    from cryptography.hazmat.primitives.asymmetric import rsa
    rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rsa_key_bytes = rsa_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    with tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix='_rsa') as f:
        f.write(rsa_key_bytes)
        rsa_key_path = f.name
    
    try:
        sign_challenge(b"test", key_path=rsa_key_path)
        assert False, "Should have raised ValueError for wrong key type"
    except ValueError as e:
        # Could be either "Not OpenSSH private key format" or "ed25519" error
        error_msg = str(e).lower()
        assert "openssh" in error_msg or "ed25519" in error_msg, f"Unexpected error: {e}"
        print("✅ Wrong key type error handled correctly")
    finally:
        Path(rsa_key_path).unlink()


if __name__ == "__main__":
    print("=== Running End-to-End Signing Tests ===")
    
    # Test error conditions first
    test_error_conditions()
    
    # Run main tests
    test_instance = TestEndToEndSigning()
    
    try:
        test_instance.test_complete_signing_workflow()
        test_instance.test_client_with_temporary_key()
        test_instance.test_client_with_ollama_com_hostname()
        
        print("\n🎉 All end-to-end tests passed!")
        
    except Exception as e:
        print(f"\n❌ End-to-end test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)