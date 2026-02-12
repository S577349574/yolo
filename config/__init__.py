"""配置模块 - 统一对外接口"""

from .manager import ConfigManager
from .callbacks import get_callback_manager
from .profile_manager import ProfileManager, Profile
from .events import (
    get_events,
    signal_resume, signal_reload, signal_stop,
    wait_resume, wait_reload, wait_stop,
    clear_resume, clear_reload, clear_stop,
    is_resume_set, is_reload_set, is_stop_set,
    clear_all_events, get_events_status
)
from .defaults import (
    get_default_config,
    CONFIG_GROUPS,
    PROFILE_KEYS,
    DEFAULT_PROFILE_NAME
)

# ========== 全局单例实例 ==========

_config_manager = ConfigManager()
_callback_manager = get_callback_manager()
_profile_manager = ProfileManager(_config_manager)


# ========== 核心配置 API ==========

def load_config(force_reload: bool = False):
    """
    加载配置文件

    Args:
        force_reload: 是否强制重新加载（忽略缓存）

    Returns:
        配置字典
    """
    return _config_manager.load_config(force_reload=force_reload)


def get_config(key: str, default=None):
    """
    获取配置值（带缓存）

    Args:
        key: 配置项键名
        default: 默认值

    Returns:
        配置值
    """
    return _config_manager.get(key, default)


def set_config(key: str, value):
    """
    设置配置值（会触发变更回调）

    Args:
        key: 配置项键名
        value: 新值
    """
    _config_manager.set(key, value)


def save_config() -> bool:
    """
    保存配置到文件

    Returns:
        是否保存成功
    """
    return _config_manager.save_config()


def get_all_config():
    """
    获取所有配置（副本）

    Returns:
        配置字典的副本
    """
    return _config_manager.get_all()


# ========== 自动重载 API ==========

def start_auto_reload(interval_sec: int = None):
    """
    启动自动配置重载

    Args:
        interval_sec: 检查间隔（秒），None 则使用配置中的值
    """
    _config_manager.start_auto_reload(interval_sec)


def stop_auto_reload():
    """停止自动重载"""
    _config_manager.stop_auto_reload()


# ========== 回调注册 API ==========

def on_config_change(key: str, callback):
    """
    注册配置变更回调

    Args:
        key: 配置项键名
        callback: 回调函数，签名为 callback(new_value)
    """
    _callback_manager.register(key, callback)


def off_config_change(key: str, callback):
    """
    取消配置变更回调

    Args:
        key: 配置项键名
        callback: 要取消的回调函数

    Returns:
        是否成功取消
    """
    return _callback_manager.unregister(key, callback)


def on_any_config_change(callback):
    """
    注册全局配置变更回调

    Args:
        callback: 回调函数，签名为 callback(key, new_value, old_value)
    """
    _callback_manager.register_global(callback)


def off_any_config_change(callback):
    """
    取消全局配置变更回调

    Args:
        callback: 要取消的回调函数

    Returns:
        是否成功取消
    """
    return _callback_manager.unregister_global(callback)


# ========== 参数组管理 API ========== ✅ 新增

def create_profile(name: str, base_profile: str = None) -> Profile:
    """
    创建新参数组

    Args:
        name: 参数组名称
        base_profile: 基于哪个参数组创建

    Returns:
        创建的参数组实例
    """
    return _profile_manager.create_profile(name, base_profile)


def delete_profile(name: str) -> bool:
    """
    删除参数组

    Args:
        name: 参数组名称

    Returns:
        是否删除成功
    """
    return _profile_manager.delete_profile(name)


def get_profile(name: str) -> Profile:
    """
    获取参数组实例

    Args:
        name: 参数组名称

    Returns:
        参数组实例
    """
    return _profile_manager.get_profile(name)


def list_profiles() -> list:
    """
    列出所有参数组名称

    Returns:
        参数组名称列表
    """
    return _profile_manager.list_profiles()


def rename_profile(old_name: str, new_name: str) -> bool:
    """
    重命名参数组

    Args:
        old_name: 旧名称
        new_name: 新名称

    Returns:
        是否重命名成功
    """
    return _profile_manager.rename_profile(old_name, new_name)


def set_active_profile(name: str) -> bool:
    """
    切换激活的参数组

    Args:
        name: 参数组名称

    Returns:
        是否切换成功
    """
    return _profile_manager.set_active(name)


def get_active_profile() -> str:
    """
    获取当前激活的参数组名称

    Returns:
        参数组名称
    """
    return _profile_manager.get_active()


def sync_profile_from_global(profile_name: str = None):
    """
    从全局配置同步到参数组

    Args:
        profile_name: 参数组名称，None 则同步到当前激活的参数组
    """
    _profile_manager.sync_from_global(profile_name)


def sync_profile_to_global(profile_name: str):
    """
    将参数组应用到全局配置

    Args:
        profile_name: 参数组名称
    """
    _profile_manager.sync_to_global(profile_name)


def save_profiles() -> bool:
    """
    保存所有参数组到文件

    Returns:
        是否保存成功
    """
    return _profile_manager.save_profiles()


def export_profile(profile_name: str, file_path: str) -> bool:
    """
    导出参数组到文件

    Args:
        profile_name: 参数组名称
        file_path: 导出文件路径

    Returns:
        是否导出成功
    """
    from pathlib import Path
    return _profile_manager.export_profile(profile_name, Path(file_path))


def import_profile(name: str, file_path: str) -> bool:
    """
    从文件导入参数组

    Args:
        name: 参数组名称
        file_path: 导入文件路径

    Returns:
        是否导入成功
    """
    from pathlib import Path
    return _profile_manager.import_profile(name, Path(file_path))


# ========== 实用工具 API ==========

def get_app_dir():
    """
    获取应用程序根目录

    Returns:
        Path 对象
    """
    return _config_manager.app_dir


def get_config_file():
    """
    获取配置文件路径

    Returns:
        Path 对象
    """
    return _config_manager.config_file


def reset_to_defaults() -> bool:
    """
    重置配置为默认值

    Returns:
        是否重置成功
    """
    default = get_default_config()
    _config_manager.config = default
    return _config_manager.save_config()


# ========== 导出列表 ==========

__all__ = [

    "create_profile",
    "delete_profile",
    "get_profile",
    "list_profiles",
    "rename_profile",
    "set_active_profile",
    "get_active_profile",
    "sync_profile_from_global",
    "sync_profile_to_global",
    "save_profiles",
    "export_profile",
    "import_profile",
    # 核心配置
    "load_config",
    "get_config",
    "set_config",
    "save_config",
    "get_all_config",

    # 自动重载
    "start_auto_reload",
    "stop_auto_reload",

    # 回调注册
    "on_config_change",
    "off_config_change",
    "on_any_config_change",
    "off_any_config_change",

    # ✅ 参数组管理
    "create_profile",
    "delete_profile",
    "get_profile",
    "list_profiles",
    "rename_profile",
    "set_active_profile",
    "get_active_profile",
    "sync_profile_from_global",
    "sync_profile_to_global",
    "save_profiles",
    "export_profile",
    "import_profile",

    # 控制事件
    "get_events",
    "signal_resume",
    "signal_reload",
    "signal_stop",
    "wait_resume",
    "wait_reload",
    "wait_stop",
    "clear_resume",
    "clear_reload",
    "clear_stop",
    "is_resume_set",
    "is_reload_set",
    "is_stop_set",
    "clear_all_events",
    "get_events_status",
    "save_profiles",

    # 实用工具
    "get_app_dir",
    "get_config_file",
    "get_default_config",
    "reset_to_defaults",

    # 常量
    "CONFIG_GROUPS",
    "PROFILE_KEYS",          # ✅ 新增
    "DEFAULT_PROFILE_NAME",  # ✅ 新增

    # 类型
    "Profile",               # ✅ 新增
]

# ========== 版本信息 ==========

__version__ = "1.0.0"
__author__ = "Your Name"
