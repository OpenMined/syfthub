"""RSA Key Management for Identity Provider.

This module provides RSA key management for the SyftHub Identity Provider (IdP).
It handles key generation, loading, and JWKS (JSON Web Key Set) generation
for stateless token verification by satellite services.

Multi-Worker Support:
    When running with multiple workers (e.g., uvicorn --workers 4), each worker
    is a separate process with its own memory. To ensure all workers use the
    same RSA keys, auto-generated keys are persisted to the filesystem and
    loaded by subsequent workers. File locking prevents race conditions during
    key generation.
"""

from __future__ import annotations

import base64
import fcntl
import logging
import os
import stat
import time
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, cast

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from syfthub.core.config import settings
from syfthub.domain.exceptions import KeyLoadError, KeyNotConfiguredError

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.rsa import (
        RSAPrivateKey,
        RSAPublicKey,
    )

logger = logging.getLogger(__name__)

# Constants for file-based key persistence
KEY_FILE_PRIVATE = "private.pem"
KEY_FILE_PUBLIC = "public.pem"
KEY_FILE_LOCK = ".rsa_keys.lock"
LOCK_TIMEOUT_SECONDS = 10


def _int_to_base64url(num: int) -> str:
    """Convert a big integer to Base64URL encoding (no padding).

    JWK uses Base64URL encoding for RSA modulus (n) and exponent (e).
    This is different from standard Base64 - it uses URL-safe characters
    and strips padding.

    Args:
        num: The integer to encode (e.g., RSA modulus or exponent)

    Returns:
        Base64URL encoded string without padding
    """
    # Calculate the number of bytes needed
    byte_length = (num.bit_length() + 7) // 8
    # Convert to bytes (big-endian)
    num_bytes = num.to_bytes(byte_length, byteorder="big")
    # Encode as Base64URL without padding
    return base64.urlsafe_b64encode(num_bytes).rstrip(b"=").decode("ascii")


class RSAKeyManager:
    """Manages RSA keys for the Identity Provider.

    This class handles:
    - Loading RSA keys from environment variables (Base64-encoded PEM)
    - Loading RSA keys from file paths
    - Auto-generating keys in development mode
    - Converting public keys to JWKS format for satellite services
    - Supporting key rotation with multiple active keys

    The manager uses a singleton pattern to ensure consistent key state
    across the application.
    """

    _instance: Optional[RSAKeyManager] = None
    _initialized: bool = False

    def __new__(cls) -> RSAKeyManager:
        """Create singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize key manager (only runs once due to singleton)."""
        if self._initialized:
            return

        self._private_key: Optional[RSAPrivateKey] = None
        self._public_keys: Dict[str, RSAPublicKey] = {}  # kid -> public key
        self._current_key_id: str = ""
        self._initialized = False
        self._lock_file: Optional[int] = None  # File descriptor for lock file

    def _get_keys_directory(self) -> Path:
        """Get the directory for persisted RSA keys.

        Returns:
            Path to the keys directory
        """
        return Path(settings.rsa_keys_directory)

    def _get_key_file_paths(self) -> Tuple[Path, Path, Path]:
        """Get paths for private key, public key, and lock files.

        Returns:
            Tuple of (private_key_path, public_key_path, lock_file_path)
        """
        keys_dir = self._get_keys_directory()
        return (
            keys_dir / KEY_FILE_PRIVATE,
            keys_dir / KEY_FILE_PUBLIC,
            keys_dir / KEY_FILE_LOCK,
        )

    def _ensure_keys_directory(self) -> None:
        """Ensure the keys directory exists with proper permissions."""
        keys_dir = self._get_keys_directory()
        if not keys_dir.exists():
            keys_dir.mkdir(parents=True, mode=0o700)
            logger.debug(f"Created RSA keys directory: {keys_dir}")

    def _acquire_lock(self, lock_path: Path) -> bool:
        """Acquire an exclusive lock for key generation.

        Uses file locking to prevent race conditions when multiple workers
        try to generate keys simultaneously.

        Args:
            lock_path: Path to the lock file

        Returns:
            True if lock was acquired, False if timeout
        """
        self._ensure_keys_directory()

        start_time = time.time()
        try:
            # Open or create lock file
            self._lock_file = os.open(
                str(lock_path),
                os.O_CREAT | os.O_RDWR,
                stat.S_IRUSR | stat.S_IWUSR,
            )

            # Try to acquire exclusive lock with timeout
            while time.time() - start_time < LOCK_TIMEOUT_SECONDS:
                try:
                    fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    logger.debug("Acquired RSA key generation lock")
                    return True
                except BlockingIOError:
                    # Lock is held by another process, wait and retry
                    time.sleep(0.1)

            logger.warning(
                f"Timeout waiting for RSA key lock after {LOCK_TIMEOUT_SECONDS}s"
            )
            return False

        except OSError as e:
            logger.error(f"Failed to acquire RSA key lock: {e}")
            return False

    def _release_lock(self) -> None:
        """Release the exclusive lock."""
        if self._lock_file is not None:
            try:
                fcntl.flock(self._lock_file, fcntl.LOCK_UN)
                os.close(self._lock_file)
                logger.debug("Released RSA key generation lock")
            except OSError as e:
                logger.warning(f"Error releasing RSA key lock: {e}")
            finally:
                self._lock_file = None

    def _load_persisted_keys(self) -> bool:
        """Try to load keys from persisted files.

        Returns:
            True if keys were loaded successfully, False otherwise
        """
        private_path, public_path, _ = self._get_key_file_paths()

        if not private_path.exists() or not public_path.exists():
            return False

        try:
            self._load_from_files(
                str(private_path),
                str(public_path),
                settings.rsa_key_id,
            )
            logger.info(
                f"Loaded persisted RSA keys from {self._get_keys_directory()}. "
                f"Key ID: {self._current_key_id}"
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to load persisted RSA keys: {e}")
            return False

    def _save_keys_to_files(self) -> None:
        """Save current keys to files for persistence across workers.

        Sets restrictive file permissions (600) for security.
        """
        if self._private_key is None:
            return

        private_path, public_path, _ = self._get_key_file_paths()
        self._ensure_keys_directory()

        try:
            # Save private key with restrictive permissions
            private_pem = self._private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            private_path.write_bytes(private_pem)
            os.chmod(private_path, stat.S_IRUSR | stat.S_IWUSR)  # 600

            # Save public key
            public_key = self._public_keys.get(self._current_key_id)
            if public_key:
                public_pem = public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo,
                )
                public_path.write_bytes(public_pem)
                os.chmod(public_path, stat.S_IRUSR | stat.S_IWUSR)  # 600

            logger.info(
                f"Persisted auto-generated RSA keys to {self._get_keys_directory()}"
            )

        except OSError as e:
            logger.error(f"Failed to persist RSA keys: {e}")
            raise KeyLoadError(f"Failed to save RSA keys: {e}") from e

    def initialize(self) -> None:
        """Initialize keys from configuration.

        This method should be called once at application startup.
        It attempts to load keys in the following order:
        1. From Base64-encoded PEM environment variables
        2. From file paths
        3. Auto-generate if enabled in settings

        Raises:
            KeyLoadError: If keys cannot be loaded and auto-generation is disabled
        """
        if self._initialized:
            logger.warning("RSA Key Manager already initialized")
            return

        logger.info("Initializing RSA Key Manager...")

        # Try loading from environment variables (Base64-encoded PEM)
        if settings.rsa_private_key_pem and settings.rsa_public_key_pem:
            logger.info("Loading RSA keys from environment variables...")
            try:
                self._load_from_pem_strings(
                    settings.rsa_private_key_pem,
                    settings.rsa_public_key_pem,
                    settings.rsa_key_id,
                )
                self._initialized = True
                logger.info(
                    f"RSA keys loaded from environment. Key ID: {self._current_key_id}"
                )
                return
            except Exception as e:
                logger.warning(f"Failed to load keys from environment: {e}")

        # Try loading from file paths
        if settings.rsa_private_key_path and settings.rsa_public_key_path:
            logger.info("Loading RSA keys from file paths...")
            try:
                self._load_from_files(
                    settings.rsa_private_key_path,
                    settings.rsa_public_key_path,
                    settings.rsa_key_id,
                )
                self._initialized = True
                logger.info(
                    f"RSA keys loaded from files. Key ID: {self._current_key_id}"
                )
                return
            except Exception as e:
                logger.warning(f"Failed to load keys from files: {e}")

        # Auto-generate keys if enabled (development mode)
        # For multi-worker support, keys are persisted to filesystem
        if settings.auto_generate_rsa_keys:
            # First, try to load already-persisted keys (created by another worker)
            if self._load_persisted_keys():
                self._initialized = True
                logger.warning(
                    "WARNING: Using auto-generated keys. "
                    "For production, configure explicit RSA keys via environment variables."
                )
                return

            # No persisted keys found - need to generate
            # Use file locking to prevent race conditions with other workers
            _, _, lock_path = self._get_key_file_paths()

            logger.info(
                "No persisted RSA keys found. Acquiring lock for key generation..."
            )

            if not self._acquire_lock(lock_path):
                # Lock timeout - another worker might be generating keys
                # Try loading persisted keys one more time
                logger.warning(
                    "Could not acquire lock for RSA key generation. "
                    "Attempting to load keys that may have been created by another worker..."
                )
                if self._load_persisted_keys():
                    self._initialized = True
                    return
                else:
                    raise KeyLoadError(
                        "Failed to acquire lock and no persisted keys found. "
                        "RSA key initialization failed."
                    )

            try:
                # Double-check: another worker might have created keys while we waited
                if self._load_persisted_keys():
                    self._initialized = True
                    logger.info(
                        "Another worker created RSA keys while waiting for lock."
                    )
                    return

                # Generate new keys and persist them
                logger.info("Generating new RSA keypair...")
                self._generate_keypair(settings.rsa_key_id)
                self._save_keys_to_files()
                self._initialized = True

                logger.info(
                    f"RSA keys auto-generated and persisted. Key ID: {self._current_key_id}"
                )
                logger.warning(
                    "WARNING: Using auto-generated keys. "
                    "For production, configure explicit RSA keys via environment variables."
                )
                return

            except Exception as e:
                logger.error(f"Failed to generate RSA keys: {e}")
                raise KeyLoadError(f"Auto-generation failed: {e}") from e

            finally:
                self._release_lock()

        # No keys configured
        logger.warning(
            "RSA keys not configured. Satellite token endpoints will be unavailable. "
            "Set RSA_PRIVATE_KEY_PEM/RSA_PUBLIC_KEY_PEM environment variables or "
            "enable AUTO_GENERATE_RSA_KEYS for development."
        )
        self._initialized = True  # Mark as initialized but unconfigured

    def _load_from_pem_strings(
        self, private_pem_b64: str, public_pem_b64: str, key_id: str
    ) -> None:
        """Load RSA keys from Base64-encoded PEM strings.

        Args:
            private_pem_b64: Base64-encoded private key PEM
            public_pem_b64: Base64-encoded public key PEM
            key_id: Key identifier for JWKS

        Raises:
            KeyLoadError: If keys cannot be decoded or parsed
        """
        try:
            # Decode Base64 to get PEM bytes
            private_pem = base64.b64decode(private_pem_b64)
            public_pem = base64.b64decode(public_pem_b64)

            # Load private key (cast to RSAPrivateKey - we know it's RSA)
            self._private_key = cast(
                "RSAPrivateKey",
                serialization.load_pem_private_key(private_pem, password=None),
            )

            # Load public key (cast to RSAPublicKey - we know it's RSA)
            public_key = cast(
                "RSAPublicKey",
                serialization.load_pem_public_key(public_pem),
            )

            # Store public key with key ID
            self._public_keys[key_id] = public_key
            self._current_key_id = key_id

        except Exception as e:
            raise KeyLoadError(f"Failed to load keys from PEM strings: {e}") from e

    def _load_from_files(
        self, private_path: str, public_path: str, key_id: str
    ) -> None:
        """Load RSA keys from PEM files.

        Args:
            private_path: Path to private key PEM file
            public_path: Path to public key PEM file
            key_id: Key identifier for JWKS

        Raises:
            KeyLoadError: If files cannot be read or parsed
        """
        try:
            # Read private key file
            with open(private_path, "rb") as f:
                private_pem = f.read()

            # Read public key file
            with open(public_path, "rb") as f:
                public_pem = f.read()

            # Load private key (cast to RSAPrivateKey - we know it's RSA)
            self._private_key = cast(
                "RSAPrivateKey",
                serialization.load_pem_private_key(private_pem, password=None),
            )

            # Load public key (cast to RSAPublicKey - we know it's RSA)
            public_key = cast(
                "RSAPublicKey",
                serialization.load_pem_public_key(public_pem),
            )

            # Store public key with key ID
            self._public_keys[key_id] = public_key
            self._current_key_id = key_id

        except FileNotFoundError as e:
            raise KeyLoadError(f"Key file not found: {e}") from e
        except Exception as e:
            raise KeyLoadError(f"Failed to load keys from files: {e}") from e

    def _generate_keypair(self, key_id: str) -> None:
        """Generate a new RSA keypair.

        Args:
            key_id: Key identifier for JWKS

        Raises:
            KeyLoadError: If key generation fails
        """
        try:
            # Generate private key
            self._private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=settings.rsa_key_size,
            )

            # Extract public key
            public_key = self._private_key.public_key()

            # Store public key with key ID
            self._public_keys[key_id] = public_key
            self._current_key_id = key_id

        except Exception as e:
            raise KeyLoadError(f"Failed to generate RSA keypair: {e}") from e

    @property
    def is_configured(self) -> bool:
        """Check if RSA keys are configured and available."""
        return self._private_key is not None

    @property
    def private_key(self) -> RSAPrivateKey:
        """Get the private key for signing tokens.

        Returns:
            RSA private key

        Raises:
            KeyNotConfiguredError: If keys are not configured
        """
        if self._private_key is None:
            raise KeyNotConfiguredError()
        return self._private_key

    @property
    def current_key_id(self) -> str:
        """Get the current key ID."""
        return self._current_key_id

    def get_public_key(self, kid: str) -> Optional[RSAPublicKey]:
        """Get a public key by its key ID.

        Args:
            kid: Key identifier

        Returns:
            RSA public key or None if not found
        """
        return self._public_keys.get(kid)

    def add_public_key(self, kid: str, public_key: RSAPublicKey) -> None:
        """Add a public key for key rotation.

        This allows adding additional public keys for verification
        during key rotation periods.

        Args:
            kid: Key identifier
            public_key: RSA public key to add
        """
        self._public_keys[kid] = public_key
        logger.info(f"Added public key with ID: {kid}")

    def get_jwks(self) -> Dict[str, List[Dict[str, str]]]:
        """Generate JSON Web Key Set (JWKS) for all public keys.

        Returns a JWKS containing all active public keys. Satellite services
        cache this and use it to verify tokens locally.

        Returns:
            JWKS dictionary with 'keys' array containing JWK objects

        Raises:
            KeyNotConfiguredError: If no keys are configured
        """
        if not self._public_keys:
            raise KeyNotConfiguredError()

        keys = []
        for kid, public_key in self._public_keys.items():
            jwk = self._rsa_public_key_to_jwk(public_key, kid)
            keys.append(jwk)

        return {"keys": keys}

    def _rsa_public_key_to_jwk(
        self, public_key: RSAPublicKey, kid: str
    ) -> Dict[str, str]:
        """Convert RSA public key to JWK format.

        Args:
            public_key: RSA public key to convert
            kid: Key identifier

        Returns:
            JWK dictionary with kty, kid, use, alg, n, e fields
        """
        # Get RSA public numbers (modulus n and exponent e)
        public_numbers = public_key.public_numbers()

        return {
            "kty": "RSA",
            "kid": kid,
            "use": "sig",
            "alg": "RS256",
            "n": _int_to_base64url(public_numbers.n),
            "e": _int_to_base64url(public_numbers.e),
        }

    def get_private_key_pem(self) -> bytes:
        """Get the private key in PEM format (for debugging/export).

        Returns:
            Private key as PEM bytes

        Raises:
            KeyNotConfiguredError: If keys are not configured
        """
        if self._private_key is None:
            raise KeyNotConfiguredError()

        return self._private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def get_public_key_pem(self, kid: Optional[str] = None) -> bytes:
        """Get a public key in PEM format (for debugging/export).

        Args:
            kid: Key identifier (defaults to current key)

        Returns:
            Public key as PEM bytes

        Raises:
            KeyNotConfiguredError: If keys are not configured
        """
        key_id = kid or self._current_key_id
        public_key = self._public_keys.get(key_id)

        if public_key is None:
            raise KeyNotConfiguredError()

        return public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )


# Global singleton instance
key_manager = RSAKeyManager()
