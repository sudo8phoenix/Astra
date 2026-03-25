"""
Security & Secrets Management Module

Implements secure credential handling, encryption, and secrets management strategies.
"""

import hashlib
import hmac
import os
from typing import Any, Optional

from app.core.config import settings


# ============================================================================
# SECRETS MANAGEMENT STRATEGIES
# ============================================================================


class SecretsManager:
    """
    Manages sensitive data with support for multiple backends.
    
    Strategies:
    1. Environment variables (development)
    2. Vault (production) - HashiCorp Vault / AWS Secrets Manager
    3. Encrypted local storage (staging)
    """
    
    @staticmethod
    def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get secret from configured backend.
        
        Priority:
        1. Environment variable
        2. Vault (if configured)
        3. Default value
        
        Args:
            key: Secret key/name
            default: Default value if not found
        
        Returns:
            Secret value or None
        """
        # Try environment variable first
        value = os.getenv(key)
        if value:
            return value
        
        # Try vault in production
        if settings.app_env == "production":
            return SecretsManager._get_from_vault(key)
        
        return default
    
    @staticmethod
    def _get_from_vault(key: str) -> Optional[str]:
        """
        Retrieve secret from HashiCorp Vault or AWS Secrets Manager.
        
        In production, implement actual vault integration:
        - HashiCorp Vault: Use hvac library
        - AWS: Use boto3 with secretsmanager
        - Azure: Use azure-identity and azure-keyvault-secrets
        
        Example with AWS:
            import boto3
            client = boto3.client('secretsmanager')
            response = client.get_secret_value(SecretId=key)
            return response['SecretString']
        """
        # Placeholder for actual vault integration
        return None
    
    @staticmethod
    def store_secret(key: str, value: str) -> None:
        """
        Store secret in configured backend.
        
        Args:
            key: Secret key/name
            value: Secret value
        """
        if settings.app_env == "production":
            SecretsManager._store_in_vault(key, value)
        else:
            os.environ[key] = value
    
    @staticmethod
    def _store_in_vault(key: str, value: str) -> None:
        """Store secret in vault (production only)."""
        # TODO: Implement actual vault storage
        pass


# ============================================================================
# ENCRYPTION & HASHING
# ============================================================================


class CryptoUtils:
    """Cryptographic utilities for data encryption and hashing."""
    
    @staticmethod
    def hash_password(password: str, salt_rounds: int = 10) -> str:
        """
        Hash password using PBKDF2 (production: use bcrypt or argon2).
        
        For production, use bcrypt:
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            pwd_context.hash(password)
        
        Args:
            password: Plain text password
            salt_rounds: Number of hash iterations
        
        Returns:
            Hashed password
        """
        # Use bcrypt in production
        # For now: basic PBKDF2
        salt = os.urandom(32)
        key = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            salt,
            salt_rounds,
        )
        return salt.hex() + ":" + key.hex()
    
    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """
        Verify password against hash.
        
        Args:
            password: Plain text password to verify
            hashed: Hashed password from storage
        
        Returns:
            True if password matches, False otherwise
        """
        try:
            salt_hex, key_hex = hashed.split(":")
            salt = bytes.fromhex(salt_hex)
            stored_key = bytes.fromhex(key_hex)
            
            computed_key = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode(),
                salt,
                10,
            )
            
            return hmac.compare_digest(computed_key, stored_key)
        except (ValueError, AttributeError):
            return False
    
    @staticmethod
    def generate_api_key(prefix: str = "sk") -> str:
        """
        Generate secure API key.
        
        Format: {prefix}_{random_base64}
        
        Args:
            prefix: Key prefix (e.g., 'sk', 'pk')
        
        Returns:
            Generated API key
        """
        import base64
        random_bytes = os.urandom(32)
        encoded = base64.urlsafe_b64encode(random_bytes).decode().rstrip("=")
        return f"{prefix}_{encoded}"
    
    @staticmethod
    def generate_state_token() -> str:
        """Generate secure state token for OAuth flows."""
        import secrets
        return secrets.token_urlsafe(32)


# ============================================================================
# CREDENTIAL STORAGE & ACCESS
# ============================================================================


class CredentialStore:
    """Store and retrieve user credentials (OAuth tokens, API keys)."""
    
    @staticmethod
    def encrypt_token(token: str, encryption_key: Optional[str] = None) -> str:
        """
        Encrypt OAuth token for storage.
        
        In production, use proper encryption (Fernet, AES-256):
            from cryptography.fernet import Fernet
            fernet = Fernet(encryption_key.encode())
            encrypted = fernet.encrypt(token.encode())
        
        Args:
            token: Token to encrypt
            encryption_key: Encryption key (uses app secret by default)
        
        Returns:
            Encrypted token
        """
        if encryption_key is None:
            encryption_key = settings.jwt_secret_key
        
        # Basic XOR encryption (NOT for production - use Fernet/AES)
        key_bytes = hashlib.sha256(encryption_key.encode()).digest()
        token_bytes = token.encode()
        
        encrypted = bytes(a ^ b for a, b in zip(
            token_bytes,
            (key_bytes * (len(token_bytes) // len(key_bytes) + 1))[:len(token_bytes)]
        ))
        
        import base64
        return base64.b64encode(encrypted).decode()
    
    @staticmethod
    def decrypt_token(encrypted_token: str, encryption_key: Optional[str] = None) -> str:
        """Decrypt stored OAuth token."""
        if encryption_key is None:
            encryption_key = settings.jwt_secret_key
        
        import base64
        encrypted = base64.b64decode(encrypted_token.encode())
        key_bytes = hashlib.sha256(encryption_key.encode()).digest()
        
        decrypted = bytes(a ^ b for a, b in zip(
            encrypted,
            (key_bytes * (len(encrypted) // len(key_bytes) + 1))[:len(encrypted)]
        ))
        
        return decrypted.decode()


# ============================================================================
# AUDIT & COMPLIANCE
# ============================================================================


class SecurityAudit:
    """Security event tracking and compliance logging."""
    
    @staticmethod
    def log_authentication_event(
        user_id: str,
        event_type: str,  # login, logout, failed_login, token_refresh
        success: bool,
        ip_address: str,
        user_agent: str,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Log authentication event for audit trail.
        
        Args:
            user_id: User identifier
            event_type: Type of authentication event
            success: Whether event was successful
            ip_address: Client IP address
            user_agent: Client user agent
            details: Additional event details
        """
        # TODO: Store in audit_logs table
        # See audit.py for schema
        pass
    
    @staticmethod
    def log_authorization_event(
        user_id: str,
        resource: str,
        action: str,
        allowed: bool,
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Log authorization event (access control).
        
        Args:
            user_id: User identifier
            resource: Resource accessed
            action: Action attempted
            allowed: Whether action was allowed
            details: Additional details
        """
        # TODO: Store in audit_logs table
        pass


# ============================================================================
# ENVIRONMENT-SPECIFIC SECURITY SETTINGS
# ============================================================================


class SecurityConfig:
    """Environment-specific security configurations."""
    
    # Development
    DEV_CONFIG = {
        "token_expiration_minutes": 60,
        "refresh_token_expiration_days": 7,
        "password_min_length": 8,
        "require_https": False,
        "cors_allow_all": True,
        "log_sql_queries": True,
        "jwt_algorithm": "HS256",
    }
    
    # Staging
    STAGING_CONFIG = {
        "token_expiration_minutes": 60,
        "refresh_token_expiration_days": 7,
        "password_min_length": 12,
        "require_https": True,
        "cors_allow_all": False,
        "log_sql_queries": False,
        "jwt_algorithm": "HS256",
    }
    
    # Production
    PROD_CONFIG = {
        "token_expiration_minutes": 30,
        "refresh_token_expiration_days": 30,
        "password_min_length": 16,
        "require_https": True,
        "cors_allow_all": False,
        "log_sql_queries": False,
        "jwt_algorithm": "RS256",  # Use RSA public-private key
    }
    
    @staticmethod
    def get_config(env: str) -> dict[str, Any]:
        """Get security config for environment."""
        configs = {
            "development": SecurityConfig.DEV_CONFIG,
            "staging": SecurityConfig.STAGING_CONFIG,
            "production": SecurityConfig.PROD_CONFIG,
        }
        return configs.get(env, SecurityConfig.DEV_CONFIG)
