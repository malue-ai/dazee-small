"""
ACP Token 存储

使用 keyring 将 ACP Token、Refresh Token 和云端配置安全存储在系统凭证管理器中：
- macOS: Keychain
- Windows: Credential Manager
- Linux: Secret Service (libsecret) 或明文回退

当 keyring 不可用时，降级为内存缓存（进程重启后失效）
"""

from typing import Optional

from logger import get_logger

logger = get_logger("acp_token_store")

_KEYRING_SERVICE = "zenflux_acp"
_KEY_CLOUD_URL = "cloud_url"
_KEY_DEVICE_ID = "device_id"
_KEY_DEVICE_NAME = "device_name"
_KEY_ACP_TOKEN = "acp_token"
_KEY_REFRESH_TOKEN = "refresh_token"


def _try_import_keyring():
    try:
        import keyring
        return keyring
    except ImportError:
        logger.warning("keyring 未安装，ACP Token 将仅保存在内存中（重启后失效）")
        return None


class TokenStore:
    """
    ACP Token 存储

    优先使用系统 keyring，不可用时降级为内存字典
    """

    def __init__(self) -> None:
        self._keyring = _try_import_keyring()
        self._mem: dict = {}

    # --------------------------------------------------------
    # 内部读写
    # --------------------------------------------------------

    def _set(self, key: str, value: str) -> None:
        if self._keyring:
            try:
                self._keyring.set_password(_KEYRING_SERVICE, key, value)
                return
            except Exception as e:
                logger.warning(f"keyring 写入失败，降级为内存: {e}")
        self._mem[key] = value

    def _get(self, key: str) -> Optional[str]:
        if self._keyring:
            try:
                return self._keyring.get_password(_KEYRING_SERVICE, key)
            except Exception as e:
                logger.warning(f"keyring 读取失败，尝试内存: {e}")
        return self._mem.get(key)

    def _delete(self, key: str) -> None:
        if self._keyring:
            try:
                self._keyring.delete_password(_KEYRING_SERVICE, key)
            except Exception:
                pass
        self._mem.pop(key, None)

    # --------------------------------------------------------
    # 云端配置
    # --------------------------------------------------------

    def save_cloud_config(self, url: str, device_id: str, device_name: str = "") -> None:
        """保存云端连接配置"""
        self._set(_KEY_CLOUD_URL, url.rstrip("/"))
        self._set(_KEY_DEVICE_ID, device_id)
        if device_name:
            self._set(_KEY_DEVICE_NAME, device_name)

    def get_cloud_url(self) -> Optional[str]:
        """获取云端地址"""
        return self._get(_KEY_CLOUD_URL)

    def get_device_id(self) -> Optional[str]:
        """获取设备 ID"""
        return self._get(_KEY_DEVICE_ID)

    def get_device_name(self) -> Optional[str]:
        """获取设备名称"""
        return self._get(_KEY_DEVICE_NAME)

    # --------------------------------------------------------
    # ACP Token
    # --------------------------------------------------------

    def save_acp_token(self, token: str) -> None:
        self._set(_KEY_ACP_TOKEN, token)

    def get_acp_token(self) -> Optional[str]:
        return self._get(_KEY_ACP_TOKEN)

    # --------------------------------------------------------
    # Refresh Token
    # --------------------------------------------------------

    def save_refresh_token(self, token: str) -> None:
        self._set(_KEY_REFRESH_TOKEN, token)

    def get_refresh_token(self) -> Optional[str]:
        return self._get(_KEY_REFRESH_TOKEN)

    # --------------------------------------------------------
    # 状态管理
    # --------------------------------------------------------

    def is_bound(self) -> bool:
        """是否已绑定云端"""
        return bool(self.get_cloud_url() and self.get_device_id() and self.get_acp_token())

    def clear(self) -> None:
        """清除所有 ACP 凭证（解绑）"""
        for key in [_KEY_CLOUD_URL, _KEY_DEVICE_ID, _KEY_DEVICE_NAME, _KEY_ACP_TOKEN, _KEY_REFRESH_TOKEN]:
            self._delete(key)
        logger.info("ACP 凭证已清除（设备解绑）")


# ============================================================
# 单例管理
# ============================================================

_token_store: Optional[TokenStore] = None


def get_token_store() -> TokenStore:
    """获取 TokenStore 单例"""
    global _token_store
    if _token_store is None:
        _token_store = TokenStore()
    return _token_store
