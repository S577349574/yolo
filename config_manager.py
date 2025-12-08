"""配置文件管理器（支持热重载、性能优化、安全验证 - 适配智能压枪系统）"""

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigManager:
    _instance = None
    _initialized = False
    _lock = threading.Lock()

    def __new__(cls):
        """单例模式：确保全局只有一个 ConfigManager 实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if ConfigManager._initialized:
            return

        ConfigManager._initialized = True

        is_frozen = (
                getattr(sys, "frozen", False) or
                hasattr(sys, "_MEIPASS") or
                "__compiled__" in sys.modules or
                Path(sys.argv[0]).suffix.lower() == ".exe"
        )

        if is_frozen:
            try:
                import __compiled__
                self.app_dir = Path(__compiled__.__file__).parent.resolve()
                self._log(f"使用__compiled__路径: {self.app_dir}")
            except (ImportError, AttributeError):
                self.app_dir = Path(sys.argv[0]).parent.resolve()
                self._log(f"使用argv[0]路径: {self.app_dir}")
        else:
            self.app_dir = Path(__file__).parent.resolve()
            self._log(f"使用开发目录: {self.app_dir}")

        self.config_file = self.app_dir / "config.json"
        self.config: Dict[str, Any] = {}
        self.last_modified_time: float = 0

        self._rw_lock = threading.RLock()
        self._cache: Dict[str, tuple] = {}
        self._cache_ttl = 0.1

        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitor = False

    def _log(self, message: str):
        """安全日志输出"""
        print(f"[ConfigManager] {message}")

    def get_default_config(self) -> Dict[str, Any]:
        """默认配置（带类型注释和安全范围）"""
        return {
            # ========== 许可证配置 ==========
            "LICENSE_KEY": "",

            # ========== YOLO 检测 ==========
            "MODEL_PATH": "320.onnx",
            "CROP_SIZE": 320,
            "CONF_THRESHOLD": 0.55,
            "IOU_THRESHOLD": 0.45,
            "TARGET_CLASS_NAMES": ["敌"],

            # ========== 瞄准点配置 ==========
            "AIM_Y_RATIO": 0.45,
            "AIM_X_OFFSET": 0.3,

            # ========== 目标选择与跟踪 ==========
            "MIN_TARGET_LOCK_FRAMES": 8,
            "TARGET_SWITCH_THRESHOLD": 0.15,
            "TARGET_IDENTITY_DISTANCE": 100,
            "MAX_LOST_FRAMES": 30,
            "DISTANCE_WEIGHT": 0.8,
            "AIM_POINT_SMOOTH_ALPHA": 0.12,

            # 🔥 特效干扰抵抗参数
            "CONFIDENCE_HISTORY_SIZE": 10,
            "CONFIDENCE_DROP_THRESHOLD": 0.15,
            "ATTACK_PROTECTION_TRIGGER_FRAMES": 3,
            "LOCKED_TARGET_BONUS": 0.15,

            # ========== PID 控制参数 ==========
            "PID_KP_X": 0.2,
            "PID_KD_X": 0.05,
            "PID_KI_X": 0.02,
            "PID_KP_Y": 0.4,
            "PID_KI_Y": 0.0,
            "PID_KD_Y": 0.06,
            "MAX_SINGLE_MOVE_PX": 400,
            "PRECISION_DEAD_ZONE": 2,
            "DEFAULT_DELAY_MS_PER_STEP": 1,

            # ========== 鼠标控制模式 ==========
            "USE_DRIVER_MODE": True,
            "MOUSE_MODE_AUTO_FALLBACK": True,
            "MAX_MICKEY": 500,

            # ========== 驱动配置 ==========
            "DRIVER_PATH": r"\\.\infestation",
            "MOUSE_REQUEST": 2234776,

            # ========== 按键定义 ==========
            "APP_MOUSE_NO_BUTTON": 0x00,
            "APP_MOUSE_LEFT_DOWN": 0x01,
            "APP_MOUSE_LEFT_UP": 0x02,
            "APP_MOUSE_RIGHT_DOWN": 0x04,
            "APP_MOUSE_RIGHT_UP": 0x08,
            "APP_MOUSE_MIDDLE_DOWN": 0x10,
            "APP_MOUSE_MIDDLE_UP": 0x20,

            # ========== 按键监控 ==========
            "ENABLE_LEFT_MOUSE_MONITOR": False,
            "ENABLE_RIGHT_MOUSE_MONITOR": True,
            "KEY_MONITOR_INTERVAL_MS": 50,

            # ========== 系统配置 ==========
            "ENABLE_LOGGING": True,
            "LOG_LEVEL": "INFO",
            "DEBUG_MODE": False,
            "CONFIG_MONITOR_INTERVAL_SEC": 5,
            "CAPTURE_FPS": 300,
            "INFERENCE_FPS": 300,

            # ========== 自动开火配置 ==========
            "ENABLE_AUTO_FIRE": False,
            "AUTO_FIRE_ACCURACY_THRESHOLD": 0.5,
            "AUTO_FIRE_DISTANCE_THRESHOLD": 15.0,
            "AUTO_FIRE_MIN_LOCK_FRAMES": 3,
            "AUTO_FIRE_DEBUG_MODE": False,

            # ========== 压枪模式配置 ==========
            "ENABLE_MANUAL_RECOIL": True,
            "ENABLE_RECOIL_CONTROL": True,
            "MANUAL_RECOIL_TRIGGER_MODE": "both_buttons",  # "left_only" 或 "both_buttons"

            # ⭐ 压枪触发条件（智能压枪）
            "RECOIL_REQUIRE_TARGET": True,      # 是否需要检测到目标才压枪
            "RECOIL_REQUIRE_LOCK": False,       # 是否需要锁定目标才压枪（更严格）
            "RECOIL_TARGET_TIMEOUT": 0.5,       # 目标丢失后多久停止压枪（秒）
            "RECOIL_MIN_LOCK_FRAMES": 0,        # 需要锁定多少帧才压枪

            # ⭐ 压枪速度配置（XY双轴）
            "RECOIL_PATTERN": "linear",         # "linear", "exponential", "custom"
            "RECOIL_VERTICAL_SPEED": 110.0,     # Y轴压枪速度（像素/秒）
            "RECOIL_HORIZONTAL_SPEED": 0.0,     # X轴压枪速度（像素/秒，正=右，负=左）
            "RECOIL_INCREMENT_Y": 0.5,          # 指数模式：速度增量系数

            # ⭐ 压枪限制（XY双轴独立限制）
            "RECOIL_MAX_SINGLE_MOVE_X": 50.0,   # X轴单次最大移动（像素）
            "RECOIL_MAX_SINGLE_MOVE_Y": 50.0,   # Y轴单次最大移动（像素）

            # 自定义压枪轨迹
            "RECOIL_CUSTOM_PATTERN": [],        # [[x1,y1], [x2,y2], ...] 或 [y1, y2, ...]
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

        # ========== 基础参数范围限制 ==========
        clamp("CROP_SIZE", 64, 1280, int, 320)
        clamp("CONF_THRESHOLD", 0.1, 0.99, float, 0.55)
        clamp("IOU_THRESHOLD", 0.1, 0.99, float, 0.45)

        # 瞄准点参数
        clamp("AIM_Y_RATIO", 0.0, 1.0, float, 0.45)
        clamp("AIM_X_OFFSET", -100, 100, float, 0.3)

        # 目标选择参数
        clamp("MIN_TARGET_LOCK_FRAMES", 1, 100, int, 8)
        clamp("TARGET_SWITCH_THRESHOLD", 0.01, 1.0, float, 0.15)
        clamp("TARGET_IDENTITY_DISTANCE", 10, 500, int, 100)
        clamp("MAX_LOST_FRAMES", 1, 300, int, 30)
        clamp("DISTANCE_WEIGHT", 0.0, 1.0, float, 0.8)
        clamp("AIM_POINT_SMOOTH_ALPHA", 0.01, 1.0, float, 0.12)

        # 🔥 特效干扰抵抗参数
        clamp("CONFIDENCE_HISTORY_SIZE", 3, 50, int, 10)
        clamp("CONFIDENCE_DROP_THRESHOLD", 0.05, 0.5, float, 0.15)
        clamp("ATTACK_PROTECTION_TRIGGER_FRAMES", 1, 20, int, 3)
        clamp("LOCKED_TARGET_BONUS", 0.0, 0.5, float, 0.15)

        # PID 参数
        clamp("PID_KP_X", 0.0, 10.0, float, 0.2)
        clamp("PID_KD_X", 0.0, 5.0, float, 0.05)
        clamp("PID_KI_X", 0.0, 1.0, float, 0.02)
        clamp("PID_KP_Y", 0.0, 10.0, float, 0.4)
        clamp("PID_KD_Y", 0.0, 5.0, float, 0.06)
        clamp("PID_KI_Y", 0.0, 1.0, float, 0.0)
        clamp("MAX_SINGLE_MOVE_PX", 1, 1000, int, 400)
        clamp("PRECISION_DEAD_ZONE", 0, 50, int, 2)
        clamp("DEFAULT_DELAY_MS_PER_STEP", 1, 100, int, 1)

        # 鼠标控制模式参数
        clamp("MAX_MICKEY", 100, 2000, int, 500)

        # 系统参数
        clamp("KEY_MONITOR_INTERVAL_MS", 10, 1000, int, 50)
        clamp("CONFIG_MONITOR_INTERVAL_SEC", 1, 60, int, 5)
        clamp("CAPTURE_FPS", 1, 500, int, 300)
        clamp("INFERENCE_FPS", 1, 500, int, 300)

        # 自动开火参数
        clamp("AUTO_FIRE_ACCURACY_THRESHOLD", 0.1, 0.99, float, 0.5)
        clamp("AUTO_FIRE_DISTANCE_THRESHOLD", 1.0, 200.0, float, 15.0)
        clamp("AUTO_FIRE_MIN_LOCK_FRAMES", 1, 100, int, 3)

        # ⭐ 压枪触发条件参数
        clamp("RECOIL_TARGET_TIMEOUT", 0.1, 5.0, float, 0.5)
        clamp("RECOIL_MIN_LOCK_FRAMES", 0, 100, int, 0)

        # ⭐ 压枪速度参数（XY双轴）
        clamp("RECOIL_VERTICAL_SPEED", 0.0, 1000.0, float, 110.0)
        clamp("RECOIL_HORIZONTAL_SPEED", -500.0, 500.0, float, 0.0)  # 支持负值（向左）
        clamp("RECOIL_INCREMENT_Y", 0.0, 10.0, float, 0.5)

        # ⭐ 压枪限制参数（XY双轴）
        clamp("RECOIL_MAX_SINGLE_MOVE_X", 1.0, 200.0, float, 50.0)
        clamp("RECOIL_MAX_SINGLE_MOVE_Y", 1.0, 200.0, float, 50.0)

        # ========== 验证枚举值 ==========
        if c.get("MANUAL_RECOIL_TRIGGER_MODE") not in ["left_only", "both_buttons"]:
            c["MANUAL_RECOIL_TRIGGER_MODE"] = "both_buttons"
        if c.get("RECOIL_PATTERN") not in ["linear", "exponential", "custom"]:
            c["RECOIL_PATTERN"] = "linear"

        # ========== 验证列表 ==========
        if not isinstance(c.get("TARGET_CLASS_NAMES"), list):
            c["TARGET_CLASS_NAMES"] = ["敌人"]
        if not isinstance(c.get("RECOIL_CUSTOM_PATTERN"), list):
            c["RECOIL_CUSTOM_PATTERN"] = []

        # ========== 验证布尔值 ==========
        bool_keys = [
            "ENABLE_LEFT_MOUSE_MONITOR", "ENABLE_RIGHT_MOUSE_MONITOR",
            "ENABLE_LOGGING", "ENABLE_AUTO_FIRE", "ENABLE_MANUAL_RECOIL",
            "AUTO_FIRE_DEBUG_MODE", "ENABLE_RECOIL_CONTROL",
            "USE_DRIVER_MODE", "MOUSE_MODE_AUTO_FALLBACK", "DEBUG_MODE",
            "RECOIL_REQUIRE_TARGET", "RECOIL_REQUIRE_LOCK"  # ⭐ 新增
        ]
        bool_defaults = {
            "USE_DRIVER_MODE": True,
            "MOUSE_MODE_AUTO_FALLBACK": True,
            "DEBUG_MODE": False,
            "RECOIL_REQUIRE_TARGET": True,   # ⭐ 默认需要目标
            "RECOIL_REQUIRE_LOCK": False,    # ⭐ 默认不需要锁定
            "ENABLE_MANUAL_RECOIL": True,
            "ENABLE_RECOIL_CONTROL": True,
        }
        for key in bool_keys:
            if not isinstance(c.get(key), bool):
                c[key] = bool_defaults.get(key, False)

        # LOG_LEVEL 特殊处理
        if c.get("LOG_LEVEL") not in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            c["LOG_LEVEL"] = "INFO"

        # ========== MODEL_PATH 处理 ==========
        model_path = c.get("MODEL_PATH", "320.onnx")
        if isinstance(model_path, str) and model_path.strip():
            p = Path(model_path)
            if not p.is_absolute():
                p = (self.app_dir / p).resolve()

            if not p.exists():
                self._log(f"⚠ 模型文件不存在: {p}")
                self._log(f"   请确保 {p.name} 在程序目录: {self.app_dir}")

            c["MODEL_PATH"] = str(p)

        # ========== 互斥模式验证 ==========
        if c.get("ENABLE_AUTO_FIRE") and c.get("ENABLE_MANUAL_RECOIL"):
            self._log("⚠ 自动开火和手动压枪不能同时启用，已禁用自动开火")
            c["ENABLE_AUTO_FIRE"] = False

        return c

    def load_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """✅ 线程安全的配置加载"""
        with self._rw_lock:
            try:
                current_modified_time = (
                    os.path.getmtime(self.config_file)
                    if self.config_file.exists()
                    else 0
                )
            except OSError:
                current_modified_time = 0

            if (
                    not force_reload
                    and self.config_file.exists()
                    and self.last_modified_time != 0
                    and current_modified_time == self.last_modified_time
            ):
                return self.config

            if not self.config_file.exists():
                self._log(f"⚠未找到配置文件: {self.config_file}")
                self._log("正在创建默认配置...")
                default = self._validate_and_clamp(self.get_default_config())
                self._write_config(default)
                self.config = default
                self.last_modified_time = current_modified_time
                self._cache.clear()
                return self.config

            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    new_config = json.load(f)

                default_config = self.get_default_config()
                updated = False
                for key, value in default_config.items():
                    if key not in new_config or new_config[key] is None:
                        new_config[key] = value
                        updated = True
                        self._log(f"补全配置项: {key} = {value}")

                new_config = self._validate_and_clamp(new_config)

                self.config = new_config
                self.last_modified_time = current_modified_time
                self._cache.clear()

                if updated:
                    self._log("检测到配置更新，正在保存...")
                    self._write_config(new_config)

                self._log(f"已加载配置文件: {self.config_file}")
                return self.config

            except json.JSONDecodeError as e:
                self._log(f"配置文件格式错误: {e}")
                self._log("使用默认配置并备份损坏文件...")

                backup_path = self.config_file.with_suffix('.json.broken')
                try:
                    import shutil
                    shutil.copy2(self.config_file, backup_path)
                    self._log(f"   已备份到: {backup_path}")
                except Exception:
                    pass

                default = self._validate_and_clamp(self.get_default_config())
                self._write_config(default)
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
            formatted_config = self._format_config_with_comments(config)
            with open(self.config_file, "w", encoding="utf-8") as f:
                f.write(formatted_config)
            return True
        except Exception as e:
            self._log(f"❌ 写入配置失败: {e}")
            return False

    def _format_config_with_comments(self, config: Dict[str, Any]) -> str:
        """🔥 格式化配置文件（添加分组注释）"""
        lines = ["{\n"]

        # ⭐ 更新分组：适配智能压枪系统
        groups = {
            "许可证配置": [
                "LICENSE_KEY"
            ],
            "YOLO 检测": [
                "MODEL_PATH", "CROP_SIZE", "CONF_THRESHOLD",
                "IOU_THRESHOLD", "TARGET_CLASS_NAMES"
            ],
            "瞄准点配置": [
                "AIM_Y_RATIO", "AIM_X_OFFSET"
            ],
            "目标选择与跟踪": [
                "MIN_TARGET_LOCK_FRAMES", "TARGET_SWITCH_THRESHOLD",
                "TARGET_IDENTITY_DISTANCE", "MAX_LOST_FRAMES",
                "DISTANCE_WEIGHT", "AIM_POINT_SMOOTH_ALPHA"
            ],
            "特效干扰抵抗": [
                "CONFIDENCE_HISTORY_SIZE", "CONFIDENCE_DROP_THRESHOLD",
                "ATTACK_PROTECTION_TRIGGER_FRAMES", "LOCKED_TARGET_BONUS"
            ],
            "PID 控制": [
                "PID_KP_X", "PID_KD_X", "PID_KI_X",
                "PID_KP_Y", "PID_KD_Y", "PID_KI_Y",
                "MAX_SINGLE_MOVE_PX", "PRECISION_DEAD_ZONE", "DEFAULT_DELAY_MS_PER_STEP"
            ],
            "鼠标控制模式": [
                "USE_DRIVER_MODE", "MOUSE_MODE_AUTO_FALLBACK", "MAX_MICKEY"
            ],
            "驱动配置": [
                "DRIVER_PATH", "MOUSE_REQUEST"
            ],
            "按键定义": [
                "APP_MOUSE_NO_BUTTON", "APP_MOUSE_LEFT_DOWN",
                "APP_MOUSE_LEFT_UP", "APP_MOUSE_RIGHT_DOWN",
                "APP_MOUSE_RIGHT_UP", "APP_MOUSE_MIDDLE_DOWN",
                "APP_MOUSE_MIDDLE_UP"
            ],
            "按键监控": [
                "ENABLE_LEFT_MOUSE_MONITOR", "ENABLE_RIGHT_MOUSE_MONITOR",
                "KEY_MONITOR_INTERVAL_MS"
            ],
            "系统配置": [
                "ENABLE_LOGGING", "LOG_LEVEL", "DEBUG_MODE",
                "CONFIG_MONITOR_INTERVAL_SEC", "CAPTURE_FPS", "INFERENCE_FPS"
            ],
            "自动开火": [
                "ENABLE_AUTO_FIRE", "AUTO_FIRE_ACCURACY_THRESHOLD",
                "AUTO_FIRE_DISTANCE_THRESHOLD", "AUTO_FIRE_MIN_LOCK_FRAMES",
                "AUTO_FIRE_DEBUG_MODE"
            ],
            "压枪模式": [  # ⭐ 重新组织压枪配置
                "ENABLE_MANUAL_RECOIL", "ENABLE_RECOIL_CONTROL",
                "MANUAL_RECOIL_TRIGGER_MODE"
            ],
            "压枪触发条件": [  # ⭐ 新增分组
                "RECOIL_REQUIRE_TARGET", "RECOIL_REQUIRE_LOCK",
                "RECOIL_TARGET_TIMEOUT", "RECOIL_MIN_LOCK_FRAMES"
            ],
            "压枪速度配置": [  # ⭐ 新增分组
                "RECOIL_PATTERN", "RECOIL_VERTICAL_SPEED", "RECOIL_HORIZONTAL_SPEED",
                "RECOIL_INCREMENT_Y"
            ],
            "压枪限制": [  # ⭐ 新增分组
                "RECOIL_MAX_SINGLE_MOVE_X", "RECOIL_MAX_SINGLE_MOVE_Y",
                "RECOIL_CUSTOM_PATTERN"
            ]
        }

        processed_keys = set()

        for group_name, keys in groups.items():
            lines.append(f'    "_comment_{group_name}": "========== {group_name} ==========",\n')
            for key in keys:
                if key in config:
                    value = json.dumps(config[key], ensure_ascii=False)
                    lines.append(f'    "{key}": {value},\n')
                    processed_keys.add(key)

        remaining_keys = set(config.keys()) - processed_keys
        # 过滤掉注释键
        remaining_keys = {k for k in remaining_keys if not k.startswith("_comment")}
        if remaining_keys:
            lines.append('    "_comment_其他": "========== 其他配置 ==========",\n')
            for key in sorted(remaining_keys):
                value = json.dumps(config[key], ensure_ascii=False)
                lines.append(f'    "{key}": {value},\n')

        if lines[-1].endswith(',\n'):
            lines[-1] = lines[-1][:-2] + '\n'

        lines.append("}\n")
        return "".join(lines)

    def save_config(self) -> bool:
        """✅ 线程安全的配置保存"""
        with self._rw_lock:
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
        """✅ 线程安全的配置设置"""
        with self._rw_lock:
            self.config[key] = value
            self._cache.pop(key, None)

    def get_all(self) -> Dict[str, Any]:
        """获取所有配置（副本）"""
        with self._rw_lock:
            return self.config.copy()

    def start_auto_reload(self, interval_sec: Optional[int] = None) -> None:
        """✅ 启动自动配置重载线程"""
        if self._monitor_thread is not None and self._monitor_thread.is_alive():
            self._log("⚠ 配置监控线程已在运行")
            return

        if interval_sec is None:
            interval_sec = self.get("CONFIG_MONITOR_INTERVAL_SEC", 5)

        def monitor_loop():
            self._log(f"配置自动重载已启动 (间隔: {interval_sec}秒)")
            while not self._stop_monitor:
                time.sleep(interval_sec)
                if not self._stop_monitor:
                    old_config = self.config.copy()
                    self.load_config()

                    # ⭐ 更新关键参数监控列表
                    critical_keys = [
                        # 目标检测相关
                        "CONFIDENCE_DROP_THRESHOLD", "ATTACK_PROTECTION_TRIGGER_FRAMES",
                        "LOCKED_TARGET_BONUS", "TARGET_SWITCH_THRESHOLD",
                        # PID 控制
                        "PID_KP_X", "PID_KD_X", "PID_KI_X",
                        "PID_KP_Y", "PID_KD_Y", "PID_KI_Y",
                        # 鼠标模式
                        "USE_DRIVER_MODE",
                        # ⭐ 压枪相关（新增）
                        "RECOIL_REQUIRE_TARGET", "RECOIL_VERTICAL_SPEED",
                        "RECOIL_HORIZONTAL_SPEED", "MANUAL_RECOIL_TRIGGER_MODE"
                    ]
                    changed = [k for k in critical_keys if old_config.get(k) != self.config.get(k)]
                    if changed:
                        self._log(f"🔥 检测到关键参数变化: {', '.join(changed)}")

        self._stop_monitor = False
        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop_auto_reload(self) -> None:
        """停止自动重载"""
        self._stop_monitor = True
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
            self._log("⏹ 配置自动重载已停止")


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


if __name__ == "__main__":
    config = load_config()
    print(f"配置加载成功，共 {len(config)} 项")
    print(f"配置文件位置: {_config_manager.config_file}")
    print(f"\n鼠标模式配置:")
    print(f"  USE_DRIVER_MODE: {get_config('USE_DRIVER_MODE')}")
    print(f"  MOUSE_MODE_AUTO_FALLBACK: {get_config('MOUSE_MODE_AUTO_FALLBACK')}")
    print(f"  MAX_MICKEY: {get_config('MAX_MICKEY')}")
