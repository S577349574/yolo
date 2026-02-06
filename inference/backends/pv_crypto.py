"""
pv_crypto.py
用于 .pv 模型文件的解密（仅在内存中）
"""

import hashlib
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


# ⚠️ 必须与加密工具完全一致
_FIXED_SECRET = b"MyFixedSecret_v1"


class PVDecryptError(Exception):
    """PV 模型解密异常"""
    pass


def _derive_key(card_key: str, salt: bytes) -> bytes:
    """
    从 固定密钥 + salt + card_key 派生 AES-256 key
    """
    return hashlib.sha256(
        _FIXED_SECRET + salt + card_key.encode("utf-8")
    ).digest()


def decrypt_pv_bytes(pv_data: bytes, card_key: str) -> bytes:
    """
    解密 pv 文件内容，返回 onnx bytes（不落盘）

    pv 格式：
        [0:16]   salt
        [16:32]  iv
        [32:]    AES-CBC ciphertext
    """
    if not pv_data or len(pv_data) < 32:
        raise PVDecryptError("PV 文件格式错误或数据不完整")

    salt = pv_data[:16]
    iv = pv_data[16:32]
    ciphertext = pv_data[32:]

    key = _derive_key(card_key, salt)
    cipher = AES.new(key, AES.MODE_CBC, iv)

    try:
        plain = cipher.decrypt(ciphertext)
        return unpad(plain, AES.block_size)
    except ValueError:
        # padding 错误，99% 是卡密不对
        raise PVDecryptError("PV 模型解密失败（卡密错误或文件被篡改）")


def decrypt_pv_file(pv_path: str, card_key: str) -> bytes:
    """
    从 pv 文件路径解密，返回 onnx bytes
    """
    with open(pv_path, "rb") as f:
        pv_data = f.read()

    return decrypt_pv_bytes(pv_data, card_key)
