"""参数组管理器 - 管理多个配置预设"""

import json
import threading
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Any
import copy

from .defaults import (
    get_default_config,
    PROFILE_KEYS,
    DEFAULT_PROFILE_NAME,
    PROFILES_FILE_NAME
)
from .manager import ConfigManager


class Profile:
    """单个参数组配置"""

    def __init__(self, name: str):
        """
        初始化参数组

        Args:
            name: 参数组名称
        """
        self.name = name
        self.config: Dict[str, Any] = {}

    def load_from_dict(self, data: Dict[str, Any]):
        """
        从字典加载配置

        Args:
            data: 配置字典
        """
        self.config = copy.deepcopy(data)

    def to_dict(self) -> Dict[str, Any]:
        """
        导出为字典

        Returns:
            配置字典的深拷贝
        """
        return copy.deepcopy(self.config)

    def get(self, key: str, default=None) -> Any:
        """
        获取参数值

        Args:
            key: 配置键
            default: 默认值

        Returns:
            配置值
        """
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        """
        设置参数值

        Args:
            key: 配置键
            value: 配置值
        """
        # 字典类型需要深拷贝
        if isinstance(value, (dict, list)):
            value = copy.deepcopy(value)
        self.config[key] = value

    def update(self, config: Dict[str, Any]):
        """
        批量更新配置

        Args:
            config: 配置字典
        """
        for key, value in config.items():
            self.set(key, value)

    def clear(self):
        """清空配置"""
        self.config.clear()

    def __repr__(self):
        return f"Profile(name='{self.name}', keys={len(self.config)})"


class ProfileManager:
    """参数组管理器（单例）"""

    _instance = None
    _lock = threading.RLock()

    def __init__(self, config_manager: ConfigManager):
        if hasattr(self, '_initialized'):
            return

        self._config_manager = config_manager
        self._profiles: Dict[str, Profile] = {}
        self._active_profile: str = DEFAULT_PROFILE_NAME

        # ✅ 修复点：固定 profiles.json 路径
        self._profiles_file = self._config_manager.app_dir / PROFILES_FILE_NAME

        # 验证 PROFILE_KEYS 的有效性
        self._validate_profile_keys()

        # 加载参数组配置
        self.load_profiles()

        # 确保存在默认参数组
        if DEFAULT_PROFILE_NAME not in self._profiles:
            self.create_profile(DEFAULT_PROFILE_NAME)
            self.sync_from_global()

        self._initialized = True


    # ========== 参数组管理 ==========

    def create_profile(self, name: str, base_profile: Optional[str] = None) -> Profile:
        """
        创建新参数组

        Args:
            name: 参数组名称
            base_profile: 基于哪个参数组创建（None 则使用默认配置）

        Returns:
            创建的参数组实例

        Raises:
            ValueError: 参数组已存在
        """
        with self._lock:
            if name in self._profiles:
                raise ValueError(f"参数组 '{name}' 已存在")

            profile = Profile(name)

            # 基于现有参数组或默认配置初始化
            if base_profile and base_profile in self._profiles:
                profile.load_from_dict(self._profiles[base_profile].to_dict())
            else:
                # 从默认配置中提取 PROFILE_KEYS 对应的值
                default_config = get_default_config()
                profile_data = {key: default_config[key] for key in PROFILE_KEYS if key in default_config}
                profile.load_from_dict(profile_data)

            self._profiles[name] = profile
            return profile

    def delete_profile(self, name: str) -> bool:
        """
        删除参数组

        Args:
            name: 参数组名称

        Returns:
            是否删除成功

        Raises:
            ValueError: 尝试删除默认参数组或当前激活的参数组
        """
        with self._lock:
            if name == DEFAULT_PROFILE_NAME:
                raise ValueError(f"不能删除默认参数组 '{DEFAULT_PROFILE_NAME}'")

            if name == self._active_profile:
                raise ValueError(f"不能删除当前激活的参数组 '{name}'，请先切换到其他参数组")

            if name not in self._profiles:
                return False

            del self._profiles[name]
            return True

    def get_profile(self, name: str) -> Optional[Profile]:
        """
        获取参数组实例

        Args:
            name: 参数组名称

        Returns:
            参数组实例，不存在则返回 None
        """
        return self._profiles.get(name)

    def list_profiles(self) -> List[str]:
        """
        列出所有参数组名称

        Returns:
            参数组名称列表
        """
        return list(self._profiles.keys())

    def rename_profile(self, old_name: str, new_name: str) -> bool:
        """
        重命名参数组

        Args:
            old_name: 旧名称
            new_name: 新名称

        Returns:
            是否重命名成功

        Raises:
            ValueError: 新名称已存在或尝试重命名默认参数组
        """
        with self._lock:
            if old_name == DEFAULT_PROFILE_NAME:
                raise ValueError(f"不能重命名默认参数组 '{DEFAULT_PROFILE_NAME}'")

            if old_name not in self._profiles:
                return False

            if new_name in self._profiles:
                raise ValueError(f"参数组 '{new_name}' 已存在")

            profile = self._profiles.pop(old_name)
            profile.name = new_name
            self._profiles[new_name] = profile

            # 更新激活的参数组名称
            if self._active_profile == old_name:
                self._active_profile = new_name

            return True

    # ========== 参数组切换 ==========

    def set_active(self, name: str) -> bool:
        """
        切换激活的参数组，并将其参数应用到全局配置

        Args:
            name: 参数组名称

        Returns:
            是否切换成功

        Raises:
            ValueError: 参数组不存在
        """
        with self._lock:
            if name not in self._profiles:
                raise ValueError(f"参数组 '{name}' 不存在")

            # 应用参数组到全局配置
            self.sync_to_global(name)

            # 更新激活状态
            self._active_profile = name

            return True

    def get_active(self) -> str:
        """
        获取当前激活的参数组名称

        Returns:
            参数组名称
        """
        return self._active_profile

    def get_active_profile(self) -> Profile:
        """
        获取当前激活的参数组实例

        Returns:
            参数组实例
        """
        return self._profiles[self._active_profile]

    # ========== 参数读写（快捷方法）==========

    def get(self, profile_name: str, key: str, default=None) -> Any:
        """
        直接获取指定参数组的参数

        Args:
            profile_name: 参数组名称
            key: 配置键
            default: 默认值

        Returns:
            配置值
        """
        profile = self.get_profile(profile_name)
        if profile is None:
            return default
        return profile.get(key, default)

    def set(self, profile_name: str, key: str, value: Any):
        """
        直接设置指定参数组的参数

        Args:
            profile_name: 参数组名称
            key: 配置键
            value: 配置值

        Raises:
            ValueError: 参数组不存在或键不在 PROFILE_KEYS 中
        """
        with self._lock:
            profile = self.get_profile(profile_name)
            if profile is None:
                raise ValueError(f"参数组 '{profile_name}' 不存在")

            if key not in PROFILE_KEYS:
                warnings.warn(f"配置键 '{key}' 不在 PROFILE_KEYS 中，可能不会被参数组管理")

            profile.set(key, value)

    # ========== 同步操作 ==========

    def sync_from_global(self, profile_name: Optional[str] = None):
        """
        从全局配置同步到参数组

        Args:
            profile_name: 参数组名称，None 则同步到当前激活的参数组
        """
        with self._lock:
            if profile_name is None:
                profile_name = self._active_profile

            profile = self.get_profile(profile_name)
            if profile is None:
                raise ValueError(f"参数组 '{profile_name}' 不存在")

            # 从全局配置中提取 PROFILE_KEYS 对应的值
            for key in PROFILE_KEYS:
                value = self._config_manager.get(key)
                if value is not None:
                    profile.set(key, value)

    def sync_to_global(self, profile_name: str):
        """
        将参数组的参数应用到全局配置

        Args:
            profile_name: 参数组名称

        Raises:
            ValueError: 参数组不存在
        """
        with self._lock:
            profile = self.get_profile(profile_name)
            if profile is None:
                raise ValueError(f"参数组 '{profile_name}' 不存在")

            # 批量应用参数到全局配置
            for key in PROFILE_KEYS:
                value = profile.get(key)
                if value is not None:
                    # 字典/列表类型需要深拷贝
                    if isinstance(value, (dict, list)):
                        value = copy.deepcopy(value)
                    self._config_manager.set(key, value)

            # 可选：立即保存全局配置
            # self._config_manager.save_config()

    # ========== 持久化 ==========

    def load_profiles(self) -> bool:
        """
        从 profiles.json 加载所有参数组

        Returns:
            是否加载成功
        """
        with self._lock:
            if not self._profiles_file.exists():
                return False

            try:
                with open(self._profiles_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 加载激活的参数组
                self._active_profile = data.get('active_profile', DEFAULT_PROFILE_NAME)

                # 加载所有参数组
                profiles_data = data.get('profiles', {})
                for name, config in profiles_data.items():
                    profile = Profile(name)
                    profile.load_from_dict(config)
                    self._profiles[name] = profile

                return True

            except Exception as e:
                warnings.warn(f"加载参数组配置失败: {e}")
                return False

    def save_profiles(self) -> bool:
        """保存所有参数组到文件"""
        try:
            data = {
                "active_profile": self._active_profile,
                "profiles": {name: profile.to_dict() for name, profile in self._profiles.items()}
            }

            # 保存到 profiles.json 文件
            with open(self._profiles_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print("[ProfileManager] 参数组已保存至 profiles.json")
            return True
        except Exception as e:
            print(f"[ProfileManager] 保存参数组失败: {e}")
            return False

    # ========== 实用工具 ==========

    def _validate_profile_keys(self):
        """验证 PROFILE_KEYS 中的键是否都存在于默认配置中"""
        default_config = get_default_config()
        invalid_keys = [key for key in PROFILE_KEYS if key not in default_config]

        if invalid_keys:
            warnings.warn(
                f"PROFILE_KEYS 中存在无效的键: {invalid_keys}\n"
                f"这些键在默认配置中不存在，可能导致运行时错误"
            )

    def export_profile(self, profile_name: str, file_path: Path) -> bool:
        """
        导出参数组到文件

        Args:
            profile_name: 参数组名称
            file_path: 导出文件路径

        Returns:
            是否导出成功
        """
        profile = self.get_profile(profile_name)
        if profile is None:
            return False

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(profile.to_dict(), f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            warnings.warn(f"导出参数组失败: {e}")
            return False

    def import_profile(self, name: str, file_path: Path) -> bool:
        """
        从文件导入参数组

        Args:
            name: 参数组名称
            file_path: 导入文件路径

        Returns:
            是否导入成功
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # 创建或更新参数组
            if name in self._profiles:
                profile = self._profiles[name]
                profile.clear()
            else:
                profile = Profile(name)
                self._profiles[name] = profile

            profile.load_from_dict(config)
            return True

        except Exception as e:
            warnings.warn(f"导入参数组失败: {e}")
            return False

    def __repr__(self):
        return (f"ProfileManager(profiles={len(self._profiles)}, "
                f"active='{self._active_profile}')")
