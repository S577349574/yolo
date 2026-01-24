"""核心配置管理器"""

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .defaults import get_default_config, CONFIG_GROUPS
from .validators import ConfigValidator
from .callbacks import get_callback_manager


class ConfigManager:
    """
    配置管理器（单例模式）

    功能：
    - 加载/保存配置文件
    - 参数验证和自动修正
    - 缓存机制（减少磁盘 I/O）
    - 热重载监控
    - 变更通知
    """

    _instance = None
    _initialized = False
    _lock = threading.Lock()

    def __new__(cls):
        """单例模式"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if ConfigManager._initialized:
            return

        ConfigManager._initialized = True

        # ========== 路径检测 ==========
        self.app_dir = self._detect_app_dir()
        self.config_file = self.app_dir / "config.json"

        # ========== 配置数据 ==========
        self.config: Dict[str, Any] = {}
        self.last_modified_time: float = 0

        # ========== 线程安全 ==========
        self._rw_lock = threading.RLock()

        # ========== 缓存机制 ==========
        self._cache: Dict[str, tuple] = {}  # key -> (value, expire_time)
        self._cache_ttl = 0.1  # 缓存过期时间（秒）

        # ========== 验证器和回调 ==========
        self._validator = ConfigValidator(self.app_dir, self._log)
        self._callback_manager = get_callback_manager()

        # ========== 热重载监控 ==========
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitor = False

    def _detect_app_dir(self) -> Path:
        """智能检测应用目录（兼容打包工具）"""
        argv0_path = Path(sys.argv[0]).resolve()
        is_exe = argv0_path.suffix.lower() == '.exe'

        try:
            import __compiled__
            is_nuitka = True
        except ImportError:
            is_nuitka = False

        is_frozen = getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS")
        is_packaged = is_exe or is_nuitka or is_frozen

        if is_packaged:
            if is_exe and argv0_path.exists():
                return argv0_path.parent
            return Path(sys.executable).resolve().parent

        # 开发环境：返回 config 模块的上级目录
        return Path(__file__).parent.parent.resolve()

    def _log(self, message: str):
        """安全日志输出"""
        print(f"[ConfigManager] {message}")

    # ========== 配置加载 ==========

    def load_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """
        线程安全的配置加载

        Args:
            force_reload: 是否强制重新加载（忽略缓存）

        Returns:
            配置字典
        """
        with self._rw_lock:
            try:
                current_mtime = os.path.getmtime(self.config_file) if self.config_file.exists() else 0
            except OSError:
                current_mtime = 0

            # 缓存命中检查
            if not force_reload and self.last_modified_time == current_mtime and self.config:
                return self.config

            # 配置文件不存在，创建默认配置
            if not self.config_file.exists():
                self._log(f"未找到配置文件，创建默认配置: {self.config_file}")
                default = self._validator.validate(get_default_config())
                self._write_config(default)
                self.config = default
                self.last_modified_time = current_mtime
                self._cache.clear()
                return self.config

            try:
                # 加载配置文件
                with open(self.config_file, "r", encoding="utf-8") as f:
                    new_config = json.load(f)

                # 补全缺失配置项
                default_config = get_default_config()
                updated = False
                for key, value in default_config.items():
                    if key not in new_config or new_config[key] is None:
                        new_config[key] = value
                        updated = True

                # 验证和规范化
                new_config = self._validator.validate(new_config)

                # 检测变更
                changes = self._detect_changes(self.config, new_config)

                self.config = new_config
                self.last_modified_time = current_mtime
                self._cache.clear()

                # 如果有更新，重新保存
                if updated:
                    self._log("检测到新配置项，已自动补全")
                    self._write_config(new_config)

                # 通知变更
                if changes:
                    self._callback_manager.notify_batch(changes)

                self._log(f"已加载配置: {self.config_file}")
                return self.config

            except json.JSONDecodeError as e:
                self._log(f"配置文件格式错误: {e}")
                self._backup_broken_config()
                default = self._validator.validate(get_default_config())
                self._write_config(default)
                self.config = default
                self._cache.clear()
                return self.config

            except Exception as e:
                self._log(f"加载配置失败: {e}")
                default = self._validator.validate(get_default_config())
                self.config = default
                self._cache.clear()
                return self.config

    def _backup_broken_config(self):
        """备份损坏的配置文件"""
        try:
            import shutil
            backup_path = self.config_file.with_suffix('.json.broken')
            shutil.copy2(self.config_file, backup_path)
            self._log(f"   已备份损坏文件到: {backup_path}")
        except Exception as e:
            self._log(f"   备份失败: {e}")

    def _detect_changes(self, old_config: Dict[str, Any],
                        new_config: Dict[str, Any]) -> Dict[str, tuple]:
        """
        检测配置变更

        Returns:
            变更字典 {key: (old_value, new_value)}
        """
        changes = {}
        all_keys = set(old_config.keys()) | set(new_config.keys())

        for key in all_keys:
            old_val = old_config.get(key)
            new_val = new_config.get(key)
            if old_val != new_val:
                changes[key] = (old_val, new_val)

        return changes

    # ========== 配置保存 ==========

    def save_config(self) -> bool:
        """
        保存配置到文件

        Returns:
            是否保存成功
        """
        with self._rw_lock:
            if self._write_config(self.config):
                self._log(f"配置已保存: {self.config_file}")
                try:
                    self.last_modified_time = os.path.getmtime(self.config_file)
                except OSError:
                    pass
                self._cache.clear()
                return True
            return False

    def _write_config(self, config: Dict[str, Any]) -> bool:
        """写入配置文件（带格式化注释）"""
        try:
            formatted = self._format_with_comments(config)
            with open(self.config_file, "w", encoding="utf-8") as f:
                f.write(formatted)
            return True
        except Exception as e:
            self._log(f"写入配置失败: {e}")
            return False

    def _format_with_comments(self, config: Dict[str, Any]) -> str:
        """格式化配置文件（添加分组注释）"""
        lines = ["{\n"]
        processed_keys = set()

        # 按分组输出
        for group_name, keys in CONFIG_GROUPS.items():
            lines.append(f'    "_comment_{group_name}": "========== {group_name} ==========",\n')
            for key in keys:
                if key in config:
                    value = json.dumps(config[key], ensure_ascii=False)
                    lines.append(f'    "{key}": {value},\n')
                    processed_keys.add(key)

        # 移除最后一个逗号
        if lines[-1].endswith(',\n'):
            lines[-1] = lines[-1][:-2] + '\n'

        lines.append("}\n")
        return "".join(lines)

    # ========== 配置读写 ==========

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值（带缓存）

        Args:
            key: 配置项键名
            default: 默认值

        Returns:
            配置值
        """
        current_time = time.time()

        # 检查缓存
        if key in self._cache:
            cached_value, expire_time = self._cache[key]
            if current_time < expire_time:
                return cached_value

        with self._rw_lock:
            if not self.config:
                self.load_config()

            value = self.config.get(key, default)
            self._cache[key] = (value, current_time + self._cache_ttl)
            return value

    def set(self, key: str, value: Any) -> None:
        """
        设置配置值（带变更通知）

        Args:
            key: 配置项键名
            value: 新值
        """
        with self._rw_lock:
            old_value = self.config.get(key)
            self.config[key] = value
            self._cache.pop(key, None)

        # 通知变更（在锁外执行，避免死锁）
        if old_value != value:
            self._callback_manager.notify(key, value, old_value)

    def get_all(self) -> Dict[str, Any]:
        """
        获取所有配置（副本）

        Returns:
            配置字典的副本
        """
        with self._rw_lock:
            return self.config.copy()

    # ========== 热重载监控 ==========

    def start_auto_reload(self, interval_sec: Optional[int] = None) -> None:
        """
        启动自动配置重载

        Args:
            interval_sec: 检查间隔（秒），None 则使用配置中的值
        """
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            self._log("配置监控线程已在运行")
            return

        if interval_sec is None:
            interval_sec = self.get("CONFIG_MONITOR_INTERVAL_SEC", 5)

        def monitor_loop():
            self._log(f"配置自动重载已启动 (间隔: {interval_sec}秒)")

            # 关键参数列表（用于日志）
            critical_keys = [
                "TARGET_GROUP_DISTANCE_THRESHOLD",
                "MIN_TARGET_LOCK_FRAMES",
                "TARGET_SWITCH_DISTANCE_THRESHOLD",
                "ENABLE_HEAD_PRIORITY",
                "HEAD_PRIORITY_RANGE",
                "USE_KALMAN_FILTER",
                "KALMAN_PROCESS_NOISE",
                "KALMAN_MEASUREMENT_NOISE",
                "PID_KP_X", "PID_KP_Y",
                "USE_DRIVER_MODE",
                "USE_MAKCU",
                "RECOIL_VERTICAL_SPEED",
                "ENABLE_AUTO_FIRE"
            ]

            while not self._stop_monitor:
                time.sleep(interval_sec)
                if not self._stop_monitor:
                    old_config = self.config.copy()
                    self.load_config()

                    # 检测关键参数变化
                    changed = [k for k in critical_keys if old_config.get(k) != self.config.get(k)]
                    if changed:
                        self._log(f"关键参数变化: {', '.join(changed)}")

        self._stop_monitor = False
        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop_auto_reload(self) -> None:
        """停止自动重载"""
        self._stop_monitor = True
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
            self._log("配置自动重载已停止")
