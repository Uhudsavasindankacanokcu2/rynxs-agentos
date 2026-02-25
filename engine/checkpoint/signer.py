"""
Ed25519 signing for checkpoints.

Key management:
- Dev mode: ~/.rynxs/keys/
- Prod mode: K8s Secret mount
"""

import hashlib
import base64
import os
from pathlib import Path
from typing import Optional, Tuple
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives import serialization
from ..core.canonical import canonical_json_bytes


class SigningKey:
    """
    Ed25519 signing key wrapper.

    Provides:
    - Key generation
    - Key loading from file
    - Signing with deterministic payload
    - Public key derivation
    """

    def __init__(self, private_key: Ed25519PrivateKey):
        self.private_key = private_key
        self.public_key = private_key.public_key()

    @classmethod
    def generate(cls) -> "SigningKey":
        """Generate new Ed25519 keypair."""
        private_key = Ed25519PrivateKey.generate()
        return cls(private_key)

    @classmethod
    def load_from_file(cls, path: str) -> "SigningKey":
        """
        Load private key from PEM file.

        Args:
            path: Path to private key file

        Returns:
            SigningKey instance

        Raises:
            FileNotFoundError: If key file doesn't exist
            ValueError: If key format is invalid
        """
        with open(path, "rb") as f:
            private_key = serialization.load_pem_private_key(
                f.read(),
                password=None,
            )

        if not isinstance(private_key, Ed25519PrivateKey):
            raise ValueError("Key file is not Ed25519 private key")

        return cls(private_key)

    def save_to_file(self, path: str, public_path: Optional[str] = None) -> None:
        """
        Save private key to PEM file.

        Args:
            path: Path to save private key
            public_path: Optional path to save public key
        """
        # Ensure directory exists
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

        # Save private key
        private_pem = self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        with open(path, "wb") as f:
            f.write(private_pem)

        # Save public key if requested
        if public_path:
            public_pem = self.public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            with open(public_path, "wb") as f:
                f.write(public_pem)

    def sign(self, payload: dict) -> bytes:
        """
        Sign payload using Ed25519.

        Args:
            payload: Dict to sign (will be canonicalized)

        Returns:
            Signature bytes
        """
        canonical_bytes = canonical_json_bytes(payload)
        return self.private_key.sign(canonical_bytes)

    def sign_base64(self, payload: dict) -> str:
        """
        Sign payload and return base64-encoded signature.

        Args:
            payload: Dict to sign

        Returns:
            Base64-encoded signature
        """
        signature_bytes = self.sign(payload)
        return base64.b64encode(signature_bytes).decode("ascii")

    def get_pubkey_id(self) -> str:
        """
        Get public key identifier (SHA-256 hash, first 16 chars).

        Returns:
            Hex string (16 characters)
        """
        public_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        full_hash = hashlib.sha256(public_pem).hexdigest()
        return full_hash[:16]

    def get_public_key_pem(self) -> bytes:
        """Get public key in PEM format."""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )


class VerifyingKey:
    """
    Ed25519 verifying key (public key only).

    Used for signature verification without private key access.
    """

    def __init__(self, public_key: Ed25519PublicKey):
        self.public_key = public_key

    @classmethod
    def load_from_file(cls, path: str) -> "VerifyingKey":
        """
        Load public key from PEM file.

        Args:
            path: Path to public key file

        Returns:
            VerifyingKey instance
        """
        with open(path, "rb") as f:
            public_key = serialization.load_pem_public_key(f.read())

        if not isinstance(public_key, Ed25519PublicKey):
            raise ValueError("Key file is not Ed25519 public key")

        return cls(public_key)

    @classmethod
    def from_signing_key(cls, signing_key: SigningKey) -> "VerifyingKey":
        """Extract verifying key from signing key."""
        return cls(signing_key.public_key)

    def verify(self, payload: dict, signature: bytes) -> bool:
        """
        Verify signature on payload.

        Args:
            payload: Dict that was signed (will be canonicalized)
            signature: Signature bytes

        Returns:
            True if signature is valid, False otherwise
        """
        canonical_bytes = canonical_json_bytes(payload)

        try:
            self.public_key.verify(signature, canonical_bytes)
            return True
        except Exception:
            return False

    def verify_base64(self, payload: dict, signature_b64: str) -> bool:
        """
        Verify base64-encoded signature on payload.

        Args:
            payload: Dict that was signed
            signature_b64: Base64-encoded signature

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            signature_bytes = base64.b64decode(signature_b64)
            return self.verify(payload, signature_bytes)
        except Exception:
            return False

    def get_pubkey_id(self) -> str:
        """
        Get public key identifier (SHA-256 hash, first 16 chars).

        Returns:
            Hex string (16 characters)
        """
        public_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        full_hash = hashlib.sha256(public_pem).hexdigest()
        return full_hash[:16]


def get_default_key_path() -> Path:
    """
    Get default key path (~/.rynxs/keys/checkpoint_ed25519).

    Returns:
        Path object
    """
    home = Path.home()
    return home / ".rynxs" / "keys" / "checkpoint_ed25519"


def ensure_keypair(key_path: Optional[str] = None) -> Tuple[str, str]:
    """
    Ensure keypair exists (generate if missing).

    Args:
        key_path: Optional custom key path (default: ~/.rynxs/keys/checkpoint_ed25519)

    Returns:
        (private_key_path, public_key_path) tuple
    """
    if key_path is None:
        key_path = str(get_default_key_path())

    public_key_path = key_path + ".pub"

    # Generate if missing
    if not os.path.exists(key_path):
        signing_key = SigningKey.generate()
        signing_key.save_to_file(key_path, public_key_path)

    return key_path, public_key_path
