"""
配置管理器中转层 - 向后兼容

此文件为兼容层，所有调用转发到新的 config 模块。
旧代码无需修改，以下导入方式均可正常工作：

    import config_manager
    from config_manager import get_config, load_config
    import config_manager as cfg
"""

# ========== 从新模块导入所有功能 ==========

from config import (
    # 核心配置 API
    load_config,
    get_config,
    set_config,
    save_config,
    get_all_config,

    # 自动重载
    start_auto_reload,
    stop_auto_reload,

    # 回调注册
    on_config_change,
    off_config_change,
    on_any_config_change,
    off_any_config_change,

    # 控制事件
    get_events,
    signal_resume,
    signal_reload,
    signal_stop,
    wait_resume,
    wait_reload,
    wait_stop,
    clear_resume,
    clear_reload,
    clear_stop,
    is_resume_set,
    is_reload_set,
    is_stop_set,
    clear_all_events,
    get_events_status,

    # 实用工具
    get_app_dir,
    get_config_file,
    get_default_config,
    reset_to_defaults,

    # 常量
    CONFIG_GROUPS,
)

from config.manager import ConfigManager as _ConfigManager
from config.callbacks import ConfigCallbackManager


# ========== 兼容性 ConfigManager 类 ==========

class ConfigManager:
    """
    兼容性 ConfigManager 类

    保持与旧代码完全兼容的接口
    """

    _instance = None

    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._manager = _ConfigManager()
        return cls._instance

    def __init__(self):
        pass  # 单例，避免重复初始化

    # ========== 核心方法 ==========

    def load_config(self, force_reload: bool = False):
        """加载配置"""
        return load_config(force_reload)

    def get(self, key: str, default=None):
        """获取配置值"""
        return get_config(key, default)

    def set(self, key: str, value):
        """设置配置值"""
        set_config(key, value)

    def save_config(self) -> bool:
        """保存配置"""
        return save_config()

    def get_all(self):
        """获取所有配置"""
        return get_all_config()

    # ========== 自动重载 ==========

    def start_auto_reload(self, interval_sec: int = None):
        """启动自动重载"""
        start_auto_reload(interval_sec)

    def stop_auto_reload(self):
        """停止自动重载"""
        stop_auto_reload()

    # ========== 属性访问 ==========

    @property
    def config(self):
        """配置字典"""
        return self._manager.config

    @property
    def app_dir(self):
        """应用目录"""
        return self._manager.app_dir

    @property
    def config_file(self):
        """配置文件路径"""
        return self._manager.config_file

    @property
    def last_modified_time(self):
        """最后修改时间"""
        return self._manager.last_modified_time


# ========== 导出列表 ==========

__all__ = [
    # 类
    "ConfigManager",
    "ConfigCallbackManager",

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

    # 实用工具
    "get_app_dir",
    "get_config_file",
    "get_default_config",
    "reset_to_defaults",

    # 常量
    "CONFIG_GROUPS",
]


# ========== 版本信息 ==========

__version__ = "2.0.0"
__doc__ = "配置管理器兼容层 - 转发至 config 模块"
