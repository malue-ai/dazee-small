---
name: local-file-encrypt
description: Encrypt and decrypt local files using strong encryption. Protect sensitive documents with password-based AES-256 encryption, all processed locally.
metadata:
  xiaodazi:
    dependency_level: lightweight
    os: [common]
    backend_type: local
    user_facing: true
    python_packages:
      - cryptography
---

# 本地文件加密

帮助用户加密和解密本地文件：使用 AES-256 强加密保护敏感文档，全程本地处理。

## 使用场景

- 用户说「帮我加密这个文件」「给这份合同加个密码」
- 用户说「解密这个文件」「打开加密的文档」
- 用户说「批量加密这个文件夹里的文件」

## 依赖安装

首次使用时自动安装：

```bash
pip install cryptography
```

## 执行方式

通过 Python 使用 cryptography 库实现 AES-256 加密。

### 加密文件

```python
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

def derive_key(password: str, salt: bytes) -> bytes:
    """From password derive encryption key."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

def encrypt_file(input_path: str, output_path: str, password: str):
    """Encrypt a file with password."""
    salt = os.urandom(16)
    key = derive_key(password, salt)
    f = Fernet(key)

    with open(input_path, 'rb') as file:
        data = file.read()

    encrypted = f.encrypt(data)

    with open(output_path, 'wb') as file:
        file.write(salt + encrypted)  # salt prepended

    print(f"Encrypted: {output_path} ({len(data)} -> {len(encrypted)+16} bytes)")

# Usage
encrypt_file("/path/to/secret.pdf", "/path/to/secret.pdf.enc", "user_password")
```

### 解密文件

```python
def decrypt_file(input_path: str, output_path: str, password: str):
    """Decrypt a file with password."""
    with open(input_path, 'rb') as file:
        raw = file.read()

    salt = raw[:16]
    encrypted = raw[16:]
    key = derive_key(password, salt)
    f = Fernet(key)

    decrypted = f.decrypt(encrypted)

    with open(output_path, 'wb') as file:
        file.write(decrypted)

    print(f"Decrypted: {output_path} ({len(decrypted)} bytes)")

# Usage
decrypt_file("/path/to/secret.pdf.enc", "/path/to/secret.pdf", "user_password")
```

### 批量加密

```python
import os

def encrypt_directory(dir_path: str, password: str):
    """Encrypt all files in a directory."""
    encrypted_dir = dir_path + "_encrypted"
    os.makedirs(encrypted_dir, exist_ok=True)

    count = 0
    for filename in os.listdir(dir_path):
        filepath = os.path.join(dir_path, filename)
        if os.path.isfile(filepath):
            encrypt_file(filepath, os.path.join(encrypted_dir, filename + ".enc"), password)
            count += 1

    print(f"Encrypted {count} files -> {encrypted_dir}")
```

## 安全规则

- **密码由用户提供**：通过 HITL 工具安全获取密码，不在对话中明文显示
- **不存储密码**：加密/解密完成后不保留密码
- **不删除原文件**：加密后保留原文件，用户自行决定是否删除
- **提醒密码重要性**：忘记密码将无法恢复文件
- **加密后验证**：加密完成后尝试解密验证，确保加密正确

## 输出规范

- 加密前确认文件名和大小
- 加密后报告：输出文件路径、文件大小变化
- 强烈提醒用户牢记密码
- 批量操作报告文件数量
