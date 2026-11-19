import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

_NONCE_SIZE = 12


def _key() -> bytes:
    if not settings.log_enc_key:
        raise RuntimeError("LOG_ENC_KEY 未配置，无法加解密敏感字段")
    key = base64.b64decode(settings.log_enc_key)
    if len(key) != 32:
        raise RuntimeError("LOG_ENC_KEY 必须是 base64 编码的 32 字节密钥")
    return key


def encrypt_text(plain: str) -> bytes:
    """AES-256-GCM 加密，返回 `nonce + ciphertext`。"""
    nonce = os.urandom(_NONCE_SIZE)
    ciphertext = AESGCM(_key()).encrypt(nonce, plain.encode("utf-8"), None)
    return nonce + ciphertext


def decrypt_text(blob: bytes) -> str:
    nonce, ciphertext = blob[:_NONCE_SIZE], blob[_NONCE_SIZE:]
    return AESGCM(_key()).decrypt(nonce, ciphertext, None).decode("utf-8")
