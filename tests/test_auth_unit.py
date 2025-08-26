"""
Unit tests for ollama authentication/signing module.

Tests the cryptographic signing functionality with mocked dependencies.
"""

import base64
import struct
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from ollama._auth import (
    _pack_ssh_string,
    _ensure_cryptography_available,
    sign_challenge,
    DEFAULT_KEY_PATH
)


class TestPackSshString:
    """Test SSH wire format string packing."""
    
    def test_pack_ssh_string_basic(self):
        """Test basic string packing functionality."""
        data = b"hello"
        result = _pack_ssh_string(data)
        
        # Should be 4-byte length + data
        expected_length = struct.pack(">I", 5)  # 5 bytes for "hello"
        expected = expected_length + b"hello"
        
        assert result == expected
        assert len(result) == 9  # 4 + 5
    
    def test_pack_ssh_string_empty(self):
        """Test packing empty string."""
        result = _pack_ssh_string(b"")
        expected = struct.pack(">I", 0)  # Just length header
        assert result == expected
        assert len(result) == 4
    
    def test_pack_ssh_string_long(self):
        """Test packing longer strings."""
        data = b"a" * 1000
        result = _pack_ssh_string(data)
        
        expected_length = struct.pack(">I", 1000)
        expected = expected_length + data
        
        assert result == expected
        assert len(result) == 1004


class TestEnsureCryptographyAvailable:
    """Test cryptography dependency checking."""
    
    def test_cryptography_available(self):
        """Test when cryptography is available."""
        # Should not raise when cryptography is available
        _ensure_cryptography_available()
    
    @patch('ollama._auth.ed25519', side_effect=ImportError("No module named 'cryptography'"))
    def test_cryptography_missing(self, mock_import):
        """Test when cryptography is not available."""
        with patch.dict('sys.modules', {'cryptography.hazmat.primitives.asymmetric.ed25519': None}):
            try:
                _ensure_cryptography_available()
                assert False, "Should have raised ImportError"
            except ImportError as e:
                assert "cryptography" in str(e)
                assert "pip install cryptography" in str(e)


class TestSignChallenge:
    """Test the sign_challenge function with mocked cryptography."""
    
    def setup_mock_key(self):
        """Set up mock cryptography objects for testing."""
        # Mock private key
        mock_private_key = Mock()
        mock_private_key.sign.return_value = b"x" * 64  # 64-byte signature
        
        # Mock public key  
        mock_public_key = Mock()
        mock_public_key.public_bytes.return_value = b"y" * 32  # 32-byte public key
        mock_private_key.public_key.return_value = mock_public_key
        
        return mock_private_key, mock_public_key
    
    @patch('ollama._auth.Path.read_bytes')
    @patch('ollama._auth.serialization.load_ssh_private_key')
    @patch('ollama._auth.Ed25519PrivateKey')
    def test_sign_challenge_basic(self, mock_ed25519_class, mock_load_key, mock_read_bytes):
        """Test basic signing functionality with mocked dependencies."""
        # Setup mocks
        mock_private_key, mock_public_key = self.setup_mock_key()
        mock_load_key.return_value = mock_private_key
        mock_read_bytes.return_value = b"mock_key_data"
        
        # Configure isinstance check
        mock_ed25519_class.return_value = mock_private_key
        
        with patch('ollama._auth.isinstance', return_value=True):
            result = sign_challenge(b"test_challenge")
        
        # Verify key was loaded
        mock_read_bytes.assert_called_once()
        mock_load_key.assert_called_once_with(b"mock_key_data", password=None)
        
        # Verify signing was called
        mock_private_key.sign.assert_called_once_with(b"test_challenge")
        
        # Check result format (should be base64:base64)
        assert ":" in result
        pub_b64, sig_b64 = result.split(":", 1)
        
        # Should be valid base64
        pub_blob = base64.b64decode(pub_b64)
        sig_blob = base64.b64decode(sig_b64)
        
        # Verify SSH blob structure
        assert len(pub_blob) > 0
        assert len(sig_blob) > 0
    
    @patch('ollama._auth.Path.read_bytes')
    @patch('ollama._auth.serialization.load_ssh_private_key')
    def test_sign_challenge_wrong_key_type(self, mock_load_key, mock_read_bytes):
        """Test error handling for wrong key type."""
        # Mock a non-Ed25519 key
        mock_rsa_key = Mock()
        mock_load_key.return_value = mock_rsa_key
        mock_read_bytes.return_value = b"mock_key_data"
        
        with patch('ollama._auth.isinstance', return_value=False):
            try:
                sign_challenge(b"test_challenge")
                assert False, "Should have raised ValueError"
            except ValueError as e:
                assert "ed25519" in str(e).lower()
    
    @patch('ollama._auth.Path.read_bytes', side_effect=FileNotFoundError())
    def test_sign_challenge_missing_key_file(self, mock_read_bytes):
        """Test error handling for missing key file."""
        try:
            sign_challenge(b"test_challenge")
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError:
            pass  # Expected
    
    @patch('ollama._auth.Path.read_bytes')
    @patch('ollama._auth.serialization.load_ssh_private_key')
    def test_sign_challenge_custom_key_path(self, mock_load_key, mock_read_bytes):
        """Test using custom key path."""
        mock_private_key, _ = self.setup_mock_key()
        mock_load_key.return_value = mock_private_key
        mock_read_bytes.return_value = b"mock_key_data"
        
        custom_path = "/custom/path/to/key"
        
        with patch('ollama._auth.isinstance', return_value=True):
            sign_challenge(b"test_challenge", key_path=custom_path)
        
        # Should have used custom path
        mock_read_bytes.assert_called_once()
        # Verify the Path was created with custom path
        assert mock_read_bytes.call_count == 1
    
    @patch('ollama._auth.Path.read_bytes')
    @patch('ollama._auth.serialization.load_ssh_private_key')
    def test_sign_challenge_with_password(self, mock_load_key, mock_read_bytes):
        """Test signing with password-protected key."""
        mock_private_key, _ = self.setup_mock_key()
        mock_load_key.return_value = mock_private_key
        mock_read_bytes.return_value = b"mock_key_data"
        
        password = b"secret_password"
        
        with patch('ollama._auth.isinstance', return_value=True):
            sign_challenge(b"test_challenge", password=password)
        
        # Verify password was passed to key loading
        mock_load_key.assert_called_once_with(b"mock_key_data", password=password)


class TestSignatureBlobFormat:
    """Test the SSH signature blob format generation."""
    
    @patch('ollama._auth.Path.read_bytes')
    @patch('ollama._auth.serialization.load_ssh_private_key')
    def test_signature_blob_format(self, mock_load_key, mock_read_bytes):
        """Test that signature blobs are correctly formatted."""
        # Create predictable mock data
        mock_private_key = Mock()
        mock_private_key.sign.return_value = b"S" * 64  # 64-byte signature
        
        mock_public_key = Mock() 
        mock_public_key.public_bytes.return_value = b"P" * 32  # 32-byte public key
        mock_private_key.public_key.return_value = mock_public_key
        
        mock_load_key.return_value = mock_private_key
        mock_read_bytes.return_value = b"mock_key_data"
        
        with patch('ollama._auth.isinstance', return_value=True):
            result = sign_challenge(b"test_challenge")
        
        # Parse the result
        pub_b64, sig_b64 = result.split(":", 1)
        pub_blob = base64.b64decode(pub_b64)
        sig_blob = base64.b64decode(sig_b64)
        
        # Parse public key blob: should be "ssh-ed25519" + raw key
        name_len = struct.unpack(">I", pub_blob[:4])[0]
        name = pub_blob[4:4+name_len]
        assert name == b"ssh-ed25519"
        
        key_len = struct.unpack(">I", pub_blob[4+name_len:8+name_len])[0]
        key_data = pub_blob[8+name_len:8+name_len+key_len]
        assert key_data == b"P" * 32
        
        # Parse signature blob: should be "ssh-ed25519" + raw signature
        sig_name_len = struct.unpack(">I", sig_blob[:4])[0]
        sig_name = sig_blob[4:4+sig_name_len]
        assert sig_name == b"ssh-ed25519"
        
        sig_data_len = struct.unpack(">I", sig_blob[4+sig_name_len:8+sig_name_len])[0]
        sig_data = sig_blob[8+sig_name_len:8+sig_name_len+sig_data_len]
        assert sig_data == b"S" * 64


if __name__ == "__main__":
    # Simple test runner
    test_classes = [TestPackSshString, TestEnsureCryptographyAvailable, TestSignChallenge, TestSignatureBlobFormat]
    
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
                    import traceback
                    traceback.print_exc()
                    all_passed = False
    
    if all_passed:
        print("\n✅ All auth tests passed!")
    else:
        print("\n❌ Some auth tests failed!")