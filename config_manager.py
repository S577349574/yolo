# config_manager.py
"""配置文件管理器（支持热重载、性能优化、安全验证）"""

import os
import sys
import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigManager:
    def __init__(self):
        # 确定应用目录
        if getattr(sys, "frozen", False):
            if hasattr(sys, "_MEIPASS"):
                self.app_dir = Path(sys._MEIPASS)
            else:
                self.app_dir = Path(os.getcwd())
            try:
                exe_final_path = Path(sys.executable).resolve()
                if exe_final_path.exists():
                    self.app_dir = exe_final_path.parent
                    self._log(f"[ConfigManager] ✅ 使用EXE目录: {self.app_dir}")
            except Exception:
                pass
        else:
            self.app_dir = Path(os.getcwd())
            self._log(f"[ConfigManager] ✅ 使用开发目录: {self.app_dir}")

        self.config_file = self.app_dir / "config.json"
        self.config: Dict[str, Any] = {}
        self.last_modified_time: float = 0

        # ✅ 线程安全：读写锁
        self._lock = threading.RLock()

        # ✅ 性能优化：缓存常用配置（带过期时间）
        self._cache: Dict[str, tuple] = {}  # key -> (value, expire_time)
        self._cache_ttl = 0.1  # 缓存100ms，平衡性能和实时性

        # 自动重载线程
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitor = False

    def _log(self, message: str):
        """安全日志输出"""
        try:
            import utils
            utils.log(message)
        except Exception:
            print(message)

    def get_default_config(self) -> Dict[str, Any]:
        """默认配置（带类型注释和安全范围）"""
        return {
            # YOLO 检测
            "MODEL_PATH": "320.onnx",
            "CROP_SIZE": 320,
            "CONF_THRESHOLD": 0.75,
            "IOU_THRESHOLD": 0.45,
            "TARGET_CLASS_NAMES": ["敌人"],

            # 瞄准点配置
            "AIM_Y_RATIO": 0.55,
            "AIM_X_OFFSET": 0,

            # 目标选择与跟踪
            "MIN_TARGET_LOCK_FRAMES": 15,
            "TARGET_SWITCH_THRESHOLD": 0.2,
            "TARGET_IDENTITY_DISTANCE": 100,
            "MAX_LOST_FRAMES": 30,
            "DISTANCE_WEIGHT": 0.80,
            "AIM_POINT_SMOOTH_ALPHA": 0.25,

            # PID 控制参数
            "PID_KP": 0.95,
            "PID_KD": 0.05,
            "MAX_SINGLE_MOVE_PX": 200,
            "PRECISION_DEAD_ZONE": 2,
            "DEFAULT_DELAY_MS_PER_STEP": 2,

            # 驱动配置
            "DRIVER_PATH": r"\\.\infestation",
            "MOUSE_REQUEST": 2234776,

            # 按键定义
            "APP_MOUSE_NO_BUTTON": 0x00,
            "APP_MOUSE_LEFT_DOWN": 0x01,
            "APP_MOUSE_LEFT_UP": 0x02,
            "APP_MOUSE_RIGHT_DOWN": 0x04,
            "APP_MOUSE_RIGHT_UP": 0x08,
            "APP_MOUSE_MIDDLE_DOWN": 0x10,
            "APP_MOUSE_MIDDLE_UP": 0x20,

            # 按键监控
            "ENABLE_LEFT_MOUSE_MONITOR": False,
            "ENABLE_RIGHT_MOUSE_MONITOR": True,
            "KEY_MONITOR_INTERVAL_MS": 50,

            # 系统配置
            "ENABLE_LOGGING": False,
            "CONFIG_MONITOR_INTERVAL_SEC": 5,
            "CAPTURE_FPS": 60,
            "INFERENCE_FPS": 60,

            "ENABLE_VELOCITY_PREDICTION": True,
            "PREDICT_DELAY_SEC": 0.030,
            "VELOCITY_SMOOTH_ALPHA": 0.3,
            "ENABLE_ACCEL_PREDICTION": False,
            "ACCEL_SMOOTH_ALPHA": 0.2
        }

    def _validate_and_clamp(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """✅ 安全性：验证和限制配置值范围"""
        c = config.copy()

        def clamp(name: str, lo: Optional[float] = None, hi: Optional[float] = None,
                  typ: type = float, default: Any = None) -> None:
            v = c.get(name, default)
            try:
                v = typ(v)
            except (ValueError, TypeError):
                v = default if default is not None else (lo if lo is not None else 0)

            if lo is not None and v < lo:
                v = typ(lo)
            if hi is not None and v > hi:
                v = typ(hi)
            c[name] = v

        # ✅ 严格的参数范围限制（防止恶意配置）
        clamp("CROP_SIZE", 64, 1280, int, 320)
        clamp("CONF_THRESHOLD", 0.1, 0.99, float, 0.75)
        clamp("IOU_THRESHOLD", 0.1, 0.99, float, 0.45)

        clamp("AIM_Y_RATIO", 0.0, 1.0, float, 0.55)
        clamp("AIM_X_OFFSET", -100, 100, int, 0)

        clamp("MIN_TARGET_LOCK_FRAMES", 1, 100, int, 15)
        clamp("TARGET_SWITCH_THRESHOLD", 0.01, 1.0, float, 0.2)
        clamp("TARGET_IDENTITY_DISTANCE", 10, 500, int, 100)
        clamp("MAX_LOST_FRAMES", 1, 300, int, 30)
        clamp("DISTANCE_WEIGHT", 0.0, 1.0, float, 0.8)
        clamp("AIM_POINT_SMOOTH_ALPHA", 0.01, 1.0, float, 0.25)

        clamp("PID_KP", 0.0, 10.0, float, 0.95)
        clamp("PID_KD", 0.0, 5.0, float, 0.05)
        clamp("MAX_SINGLE_MOVE_PX", 1, 1000, int, 200)
        clamp("PRECISION_DEAD_ZONE", 0, 50, int, 2)
        clamp("DEFAULT_DELAY_MS_PER_STEP", 1, 100, int, 2)

        clamp("KEY_MONITOR_INTERVAL_MS", 10, 1000, int, 50)
        clamp("CONFIG_MONITOR_INTERVAL_SEC", 1, 60, int, 5)
        clamp("CAPTURE_FPS", 1, 500, int, 60)
        clamp("INFERENCE_FPS", 1, 500, int, 60)

        # ✅ 验证 TARGET_CLASS_NAMES 是列表
        if not isinstance(c.get("TARGET_CLASS_NAMES"), list):
            c["TARGET_CLASS_NAMES"] = ["敌人"]

        # ✅ MODEL_PATH 绝对化
        model_path = c.get("MODEL_PATH", "320.onnx")
        if isinstance(model_path, str) and model_path.strip():
            p = Path(model_path)
            if not p.is_absolute():
                p = (self.app_dir / p).resolve()
            c["MODEL_PATH"] = str(p)

        return c

    def load_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """✅ 线程安全的配置加载"""
        with self._lock:
            try:
                current_modified_time = (
                    os.path.getmtime(self.config_file)
                    if self.config_file.exists()
                    else 0
                )
            except OSError:
                current_modified_time = 0

            # 文件未变化且不强制重载
            if (
                    not force_reload
                    and self.config_file.exists()
                    and self.last_modified_time != 0
                    and current_modified_time == self.last_modified_time
            ):
                return self.config

            # 文件不存在：导出默认配置
            if not self.config_file.exists():
                self._log(f"⚠️ 未找到配置文件: {self.config_file}")
                self._log("📝 正在创建默认配置...")
                default = self._validate_and_clamp(self.get_default_config())
                self._write_config(default)
                self.config = default
                self.last_modified_time = current_modified_time
                self._cache.clear()  # 清空缓存
                return self.config

            # 读取配置文件
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    new_config = json.load(f)

                # ✅ 合并默认值
                default_config = self.get_default_config()
                updated = False
                for key, value in default_config.items():
                    if key not in new_config or new_config[key] is None:
                        new_config[key] = value
                        updated = True
                        self._log(f"➕ 补全配置项: {key}")

                # ✅ 验证和限制范围
                new_config = self._validate_and_clamp(new_config)

                self.config = new_config
                self.last_modified_time = current_modified_time
                self._cache.clear()  # 清空缓存

                if updated:
                    self._write_config(new_config)

                self._log(f"✅ 已加载配置文件: {self.config_file}")
                return self.config

            except json.JSONDecodeError as e:
                self._log(f"❌ 配置文件格式错误: {e}")
                self._log("📝 使用默认配置...")
                default = self._validate_and_clamp(self.get_default_config())
                self.config = default
                self._cache.clear()
                return self.config
            except Exception as e:
                self._log(f"❌ 加载配置失败: {e}")
                default = self._validate_and_clamp(self.get_default_config())
                self.config = default
                self._cache.clear()
                return self.config

    def _write_config(self, config: Dict[str, Any]) -> bool:
        """内部：写入配置文件"""
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            self._log(f"❌ 写入配置失败: {e}")
            return False

    def save_config(self) -> bool:
        """✅ 线程安全的配置保存"""
        with self._lock:
            if self._write_config(self.config):
                self._log(f"✅ 配置已保存: {self.config_file}")
                try:
                    self.last_modified_time = os.path.getmtime(self.config_file)
                except OSError:
                    pass
                self._cache.clear()
                return True
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """✅ 性能优化：带缓存的配置读取"""
        current_time = time.time()

        # 检查缓存
        if key in self._cache:
            cached_value, expire_time = self._cache[key]
            if current_time < expire_time:
                return cached_value

        # 缓存未命中或过期
        with self._lock:
            if not self.config:
                self.load_config()

            value = self.config.get(key, default)

            # 更新缓存
            self._cache[key] = (value, current_time + self._cache_ttl)
            return value

    def set(self, key: str, value: Any) -> None:
        """✅ 线程安全的配置设置"""
        with self._lock:
            self.config[key] = value
            # 立即使缓存失效
            self._cache.pop(key, None)

    def get_all(self) -> Dict[str, Any]:
        """获取所有配置（副本）"""
        with self._lock:
            return self.config.copy()

    def start_auto_reload(self, interval_sec: Optional[int] = None) -> None:
        """✅ 启动自动配置重载线程"""
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            self._log("⚠️ 配置监控线程已在运行")
            return

        if interval_sec is None:
            interval_sec = self.get("CONFIG_MONITOR_INTERVAL_SEC", 5)

        def monitor_loop():
            self._log(f"✅ 配置自动重载已启动 (间隔: {interval_sec}秒)")
            while not self._stop_monitor:
                time.sleep(interval_sec)
                if not self._stop_monitor:
                    self.load_config()

        self._stop_monitor = False
        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop_auto_reload(self) -> None:
        """停止自动重载"""
        self._stop_monitor = True
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
            self._log("✅ 配置自动重载已停止")


# ✅ 全局单例
_config_manager = ConfigManager()


def load_config(force_reload: bool = False) -> Dict[str, Any]:
    """加载配置"""
    return _config_manager.load_config(force_reload=force_reload)


def get_config(key: str, default: Any = None) -> Any:
    """获取配置值（带缓存优化）"""
    return _config_manager.get(key, default)


def set_config(key: str, value: Any) -> None:
    """设置配置值"""
    _config_manager.set(key, value)


def save_config() -> bool:
    """保存配置"""
    return _config_manager.save_config()


def start_auto_reload(interval_sec: Optional[int] = None) -> None:
    """启动自动重载"""
    _config_manager.start_auto_reload(interval_sec)


def stop_auto_reload() -> None:
    """停止自动重载"""
    _config_manager.stop_auto_reload()
