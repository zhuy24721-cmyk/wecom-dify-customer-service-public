import base64
import hashlib
import struct
from Crypto.Cipher import AES


class WeComCryptoError(Exception):
    pass


def verify_signature(token: str, timestamp: str, nonce: str, encrypt: str, msg_signature: str) -> bool:
    """
    校验企业微信回调签名。
    """
    values = [token, timestamp, nonce, encrypt]
    values.sort()

    raw = "".join(values)
    calculated_signature = hashlib.sha1(raw.encode("utf-8")).hexdigest()

    return calculated_signature == msg_signature


def decode_aes_key(encoding_aes_key: str) -> bytes:
    """
    将企业微信后台的 EncodingAESKey 转成 AES 密钥。
    """
    if len(encoding_aes_key) != 43:
        raise WeComCryptoError("EncodingAESKey 长度必须是 43 位")

    return base64.b64decode(encoding_aes_key + "=")


def unpad(data: bytes) -> bytes:
    """
    去掉 PKCS#7 padding。
    """
    pad = data[-1]

    if pad < 1 or pad > 32:
        raise WeComCryptoError("非法 padding")

    return data[:-pad]


def decrypt_message(encoding_aes_key: str, encrypted_text: str) -> str:
    """
    解密企业微信回调里的 echostr 或 Encrypt 消息。
    """
    aes_key = decode_aes_key(encoding_aes_key)
    iv = aes_key[:16]

    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    encrypted_data = base64.b64decode(encrypted_text)

    decrypted = cipher.decrypt(encrypted_data)
    decrypted = unpad(decrypted)

    # 企业微信明文结构：
    # 16字节随机字符串 + 4字节消息长度 + 消息内容 + receiveid
    msg_len = struct.unpack(">I", decrypted[16:20])[0]
    msg = decrypted[20:20 + msg_len]

    return msg.decode("utf-8")