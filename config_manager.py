import json
import os
from typing import Any


class ConfigManager:
    def __init__(self, config_path: str, panel_config: dict[str, Any] | None = None):
        self.config_path = config_path
        file_config = self._load_config()
        self.config = self._merge_config(file_config, panel_config or {})

    def _merge_config(
        self, file_config: dict[str, Any], panel_config: dict[str, Any]
    ) -> dict[str, Any]:
        if not panel_config:
            return file_config

        merged = dict(file_config)
        for key, value in panel_config.items():
            if value not in (None, "", [], {}):
                merged[key] = value
        return merged

    def _load_config(self) -> dict[str, Any]:
        if not os.path.exists(self.config_path):
            # 创建默认配置
            default_config = {
                "webManager": {
                    "baseUrl": "",
                    "username": "",
                    "password": "",
                },
                "serverAddress": "127.0.0.1:27015",
                "groupIds": [],
                "adminUsers": [],
            }
            self._save_config(default_config)
            return default_config

        try:
            with open(self.config_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            # 如果加载失败，返回空配置
            return {}

    def _save_config(self, config: dict[str, Any]):
        # 确保目录存在
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

    def get_group_config(self, group_id: str) -> dict[str, Any] | None:
        """根据群号获取配置"""
        configured_group_ids = self.get_group_ids()
        if str(group_id) in configured_group_ids:
            return {
                "group_id": str(group_id),
                "admin_users": self.get_admin_users(),
                "servers": [self.get_server_config()],
            }

        return None

    def get_group_ids(self) -> list[str]:
        """获取允许响应的群号列表，兼容旧版 groupId。"""
        value = self.config.get("groupIds", [])
        if isinstance(value, str):
            items = [item.strip() for item in value.replace("，", ",").split(",")]
        elif isinstance(value, list):
            items = [str(item).strip() for item in value]
        else:
            items = []

        legacy_group_id = str(self.config.get("groupId") or "").strip()
        if legacy_group_id:
            items.append(legacy_group_id)

        return list(dict.fromkeys(item for item in items if item))

    def get_admin_users(self) -> list[str]:
        """获取配置的群管理员 QQ 列表。"""
        value = self.config.get("adminUsers", [])
        if isinstance(value, str):
            items = [item.strip() for item in value.replace("，", ",").split(",")]
        elif isinstance(value, list):
            items = [str(item).strip() for item in value]
        else:
            items = []
        return [item for item in items if item]

    def get_server_config(self) -> dict[str, str]:
        """获取唯一服务器配置。"""
        address = self.config.get("serverAddress")
        if address:
            return {"name": "求生之路服务器", "address": str(address)}

        return {"name": "求生之路服务器", "address": "127.0.0.1:27015"}

    def get_web_manager_base_url(self) -> str:
        """获取 L4D2 Web 管理器地址"""
        web_manager = self.config.get("webManager")
        if isinstance(web_manager, dict):
            return str(web_manager.get("baseUrl", "") or "")
        return ""

    def get_web_manager_token(self) -> str:
        """获取 L4D2 Web 管理器 Bearer Token"""
        web_manager = self.config.get("webManager")
        if isinstance(web_manager, dict):
            return str(web_manager.get("password", "") or "")
        return ""
