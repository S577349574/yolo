"""配置文件管理器（精简版 - 支持热重载、性能优化、安全验证）"""

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

        # 自动检测运行环境
        is_frozen = getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS")

        if is_frozen:
            try:
                import __compiled__
                self.app_dir = Path(__compiled__.__file__).parent.resolve()
            except (ImportError, AttributeError):
                self.app_dir = Path(sys.argv[0]).parent.resolve()
        else:
            self.app_dir = Path(__file__).parent.resolve()

        self.config_file = self.app_dir / "config.json"
        self.config: Dict[str, Any] = {}
        self.last_modified_time: float = 0

        self._rw_lock = threading.RLock()
        self._cache: Dict[str, tuple] = {}
        self._cache_ttl = 0.1

        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_monitor = False

    def _log(self, message: str):
        """安全日志"""
        print(f"[ConfigManager] {message}")

    def get_default_config(self) -> Dict[str, Any]:
        """最小化默认配置（只包含必要项）"""
        return {
            # 许可证
            "LICENSE_KEY": "",

            # YOLO 检测
            "MODEL_PATH": "320.onnx",
            "CROP_SIZE": 320,
            "CONF_THRESHOLD": 0.60,
            "IOU_THRESHOLD": 0.45,
            "TARGET_CLASS_IDS": [1, 0],
            "TARGET_CLASS_NAMES": ["敌"],

            # 优先锁定
            "ENABLE_HEAD_PRIORITY": True,
            "HEAD_CLASS_ID": 1,
            "HEAD_PRIORITY_BONUS": 1000.0,

            # 瞄准点
            "AIM_Y_RATIO": 0.5,
            "AIM_X_OFFSET": 0.5,

            # 目标跟踪
            "MIN_TARGET_LOCK_FRAMES": 3,
            "TARGET_SWITCH_THRESHOLD": 0.15,
            "TARGET_IDENTITY_DISTANCE": 100,
            "MAX_LOST_FRAMES": 30,
            "DISTANCE_WEIGHT": 0.8,
            "AIM_POINT_SMOOTH_ALPHA": 0.8,

            # 特效干扰抵抗
            "CONFIDENCE_HISTORY_SIZE": 10,
            "CONFIDENCE_DROP_THRESHOLD": 0.15,
            "ATTACK_PROTECTION_TRIGGER_FRAMES": 3,
            "LOCKED_TARGET_BONUS": 0.15,

            # 卡尔曼滤波
            "USE_KALMAN_FILTER": True,
            "KALMAN_PROCESS_NOISE": 0.2,
            "KALMAN_MEASUREMENT_NOISE": 1.0,
            "KALMAN_MAX_PREDICT_FRAMES": 3,

            # 预判瞄准
            "ENABLE_LEAD_TARGET": False,
            "LEAD_FRAMES": 2,

            # PID 控制
            "PID_KP_X": 0.15,
            "PID_KD_X": 0.05,
            "PID_KI_X": 0.05,
            "PID_KP_Y": 0.15,
            "PID_KD_Y": 0.05,
            "PID_KI_Y": 0.05,
            "MAX_SINGLE_MOVE_PX": 400,
            "PRECISION_DEAD_ZONE": 5,
            "DEFAULT_DELAY_MS_PER_STEP": 1,

            # 鼠标控制
            "USE_DRIVER_MODE": False,
            "MOUSE_MODE_AUTO_FALLBACK": True,
            "MAX_MICKEY": 500,

            # 驱动配置
            "DRIVER_PATH": r"\\.\infestation",
            "MOUSE_REQUEST": 2234776,

            # 按键定义
            "APP_MOUSE_NO_BUTTON": 0,
            "APP_MOUSE_LEFT_DOWN": 1,
            "APP_MOUSE_LEFT_UP": 2,
            "APP_MOUSE_RIGHT_DOWN": 4,
            "APP_MOUSE_RIGHT_UP": 8,
            "APP_MOUSE_MIDDLE_DOWN": 16,
            "APP_MOUSE_MIDDLE_UP": 32,

            # 按键监控
            "ENABLE_LEFT_MOUSE_MONITOR": False,
            "ENABLE_RIGHT_MOUSE_MONITOR": True,
            "KEY_MONITOR_INTERVAL_MS": 50,

            # 系统配置
            "ENABLE_LOGGING": True,
            "LOG_LEVEL": "INFO",
            "DEBUG_MODE": False,
            "CONFIG_MONITOR_INTERVAL_SEC": 5,
            "CAPTURE_FPS": 144,
            "INFERENCE_FPS": 300,

            # 自动开火
            "ENABLE_AUTO_FIRE": False,
            "AUTO_FIRE_ACCURACY_THRESHOLD": 0.5,
            "AUTO_FIRE_DISTANCE_THRESHOLD": 15.0,
            "AUTO_FIRE_MIN_LOCK_FRAMES": 3,
            "AUTO_FIRE_DEBUG_MODE": False,

            # 压枪模式
            "ENABLE_MANUAL_RECOIL": True,
            "ENABLE_RECOIL_CONTROL": True,
            "MANUAL_RECOIL_TRIGGER_MODE": "both_buttons",

            # 压枪触发条件
            "RECOIL_REQUIRE_TARGET": False,
            "RECOIL_REQUIRE_LOCK": False,
            "RECOIL_TARGET_TIMEOUT": 0.5,
            "RECOIL_MIN_LOCK_FRAMES": 0,

            # 压枪速度
            "RECOIL_PATTERN": "linear",
            "RECOIL_VERTICAL_SPEED": 180.0,
            "RECOIL_HORIZONTAL_SPEED": 0.0,
            "RECOIL_INCREMENT_Y": 0.5,

            # 压枪限制
            "RECOIL_MAX_SINGLE_MOVE_X": 50.0,
            "RECOIL_MAX_SINGLE_MOVE_Y": 50.0,
            "RECOIL_CUSTOM_PATTERN": [],

            # 其他
            "RECOIL_HORIZONTAL_VARIANCE": 0,
            "RECOIL_MAX_SINGLE_MOVE": 110.0,

            # 脚本系统
            "SCRIPT_AUTO_RELOAD": True,
            "SCRIPT_TIMEOUT_MS": 10,
            "SCRIPT_DEBUG_MODE": False,
            "ENABLED_SCRIPTS": ["auto_key_large_target"]
        }

    def _validate_and_clamp(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """精简版参数验证（合并重复逻辑）"""
        c = config.copy()

        # 数值范围验证规则（格式：key: (min, max, type, default)）
        validation_rules = {
            # YOLO 检测
            "CROP_SIZE": (64, 1280, int, 320),
            "CONF_THRESHOLD": (0.1, 0.99, float, 0.60),
            "IOU_THRESHOLD": (0.1, 0.99, float, 0.45),

            # 优先锁定
            "HEAD_CLASS_ID": (0, 100, int, 1),
            "HEAD_PRIORITY_BONUS": (0.0, 10000.0, float, 1000.0),

            # 瞄准点
            "AIM_Y_RATIO": (0.0, 1.0, float, 0.5),
            "AIM_X_OFFSET": (-100, 100, float, 0.5),

            # 目标跟踪
            "MIN_TARGET_LOCK_FRAMES": (1, 100, int, 3),
            "TARGET_SWITCH_THRESHOLD": (0.01, 1.0, float, 0.15),
            "TARGET_IDENTITY_DISTANCE": (10, 500, int, 100),
            "MAX_LOST_FRAMES": (1, 300, int, 30),
            "DISTANCE_WEIGHT": (0.0, 1.0, float, 0.8),
            "AIM_POINT_SMOOTH_ALPHA": (0.01, 1.0, float, 0.8),

            # 特效干扰
            "CONFIDENCE_HISTORY_SIZE": (3, 50, int, 10),
            "CONFIDENCE_DROP_THRESHOLD": (0.05, 0.5, float, 0.15),
            "ATTACK_PROTECTION_TRIGGER_FRAMES": (1, 20, int, 3),
            "LOCKED_TARGET_BONUS": (0.0, 0.5, float, 0.15),

            # 卡尔曼滤波
            "KALMAN_PROCESS_NOISE": (0.01, 10.0, float, 0.2),
            "KALMAN_MEASUREMENT_NOISE": (0.1, 50.0, float, 1.0),
            "KALMAN_MAX_PREDICT_FRAMES": (0, 60, int, 3),

            # 预判瞄准
            "LEAD_FRAMES": (0, 30, int, 2),

            # PID 控制
            "PID_KP_X": (0.0, 10.0, float, 0.15),
            "PID_KD_X": (0.0, 5.0, float, 0.05),
            "PID_KI_X": (0.0, 1.0, float, 0.05),
            "PID_KP_Y": (0.0, 10.0, float, 0.15),
            "PID_KD_Y": (0.0, 5.0, float, 0.05),
            "PID_KI_Y": (0.0, 1.0, float, 0.05),
            "MAX_SINGLE_MOVE_PX": (1, 1000, int, 400),
            "PRECISION_DEAD_ZONE": (0, 50, int, 5),
            "DEFAULT_DELAY_MS_PER_STEP": (1, 100, int, 1),

            # 鼠标控制
            "MAX_MICKEY": (100, 2000, int, 500),

            # 系统配置
            "KEY_MONITOR_INTERVAL_MS": (10, 1000, int, 50),
            "CONFIG_MONITOR_INTERVAL_SEC": (1, 60, int, 5),
            "CAPTURE_FPS": (1, 500, int, 144),
            "INFERENCE_FPS": (1, 500, int, 300),

            # 自动开火
            "AUTO_FIRE_ACCURACY_THRESHOLD": (0.1, 0.99, float, 0.5),
            "AUTO_FIRE_DISTANCE_THRESHOLD": (1.0, 200.0, float, 15.0),
            "AUTO_FIRE_MIN_LOCK_FRAMES": (1, 100, int, 3),

            # 压枪触发
            "RECOIL_TARGET_TIMEOUT": (0.1, 5.0, float, 0.5),
            "RECOIL_MIN_LOCK_FRAMES": (0, 100, int, 0),

            # 压枪速度
            "RECOIL_VERTICAL_SPEED": (0.0, 1000.0, float, 180.0),
            "RECOIL_HORIZONTAL_SPEED": (-500.0, 500.0, float, 0.0),
            "RECOIL_INCREMENT_Y": (0.0, 10.0, float, 0.5),

            # 压枪限制
            "RECOIL_MAX_SINGLE_MOVE_X": (1.0, 200.0, float, 50.0),
            "RECOIL_MAX_SINGLE_MOVE_Y": (1.0, 200.0, float, 50.0),
            "RECOIL_MAX_SINGLE_MOVE": (1.0, 500.0, float, 110.0),

            # 脚本系统
            "SCRIPT_TIMEOUT_MS": (1, 1000, int, 10),
        }

        # 批量验证数值范围
        for key, (min_val, max_val, typ, default) in validation_rules.items():
            v = c.get(key, default)
            try:
                v = typ(v)
                v = max(min_val, min(max_val, v))
            except (ValueError, TypeError):
                v = default
            c[key] = v

        # 枚举值验证
        if c.get("MANUAL_RECOIL_TRIGGER_MODE") not in ["left_only", "both_buttons"]:
            c["MANUAL_RECOIL_TRIGGER_MODE"] = "both_buttons"
        if c.get("RECOIL_PATTERN") not in ["linear", "exponential", "custom"]:
            c["RECOIL_PATTERN"] = "linear"
        if c.get("LOG_LEVEL") not in ["DEBUG", "INFO", "WARNING", "ERROR"]:
            c["LOG_LEVEL"] = "INFO"

        # 列表类型验证
        for key in ["TARGET_CLASS_NAMES", "RECOIL_CUSTOM_PATTERN", "ENABLED_SCRIPTS"]:
            if not isinstance(c.get(key), list):
                c[key] = self.get_default_config()[key]

        # TARGET_CLASS_IDS 特殊处理
        if "TARGET_CLASS_IDS" in c:
            try:
                c["TARGET_CLASS_IDS"] = [int(x) for x in c["TARGET_CLASS_IDS"]] if isinstance(c["TARGET_CLASS_IDS"], list) else []
            except (ValueError, TypeError):
                c["TARGET_CLASS_IDS"] = [1, 0]

        # 布尔值验证（批量处理）
        bool_keys = [
            "ENABLE_HEAD_PRIORITY", "ENABLE_LEFT_MOUSE_MONITOR", "ENABLE_RIGHT_MOUSE_MONITOR",
            "ENABLE_LOGGING", "DEBUG_MODE", "ENABLE_AUTO_FIRE", "AUTO_FIRE_DEBUG_MODE",
            "ENABLE_MANUAL_RECOIL", "ENABLE_RECOIL_CONTROL", "USE_DRIVER_MODE",
            "MOUSE_MODE_AUTO_FALLBACK", "RECOIL_REQUIRE_TARGET", "RECOIL_REQUIRE_LOCK",
            "USE_KALMAN_FILTER", "ENABLE_LEAD_TARGET", "SCRIPT_AUTO_RELOAD", "SCRIPT_DEBUG_MODE"
        ]
        for key in bool_keys:
            if not isinstance(c.get(key), bool):
                c[key] = self.get_default_config().get(key, False)

        # MODEL_PATH 路径处理
        model_path = c.get("MODEL_PATH", "320.onnx")
        if isinstance(model_path, str) and model_path.strip():
            p = Path(model_path)
            if not p.is_absolute():
                p = (self.app_dir / p).resolve()
            if not p.exists():
                self._log(f"⚠ 模型文件不存在: {p}")
            c["MODEL_PATH"] = str(p)

        # 互斥模式验证
        if c.get("ENABLE_AUTO_FIRE") and c.get("ENABLE_MANUAL_RECOIL"):
            self._log("⚠ 自动开火和手动压枪不能同时启用，已禁用自动开火")
            c["ENABLE_AUTO_FIRE"] = False

        return c

    def load_config(self, force_reload: bool = False) -> Dict[str, Any]:
        """线程安全的配置加载"""
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
                self._log(f"⚠ 未找到配置文件，创建默认配置: {self.config_file}")
                default = self._validate_and_clamp(self.get_default_config())
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
                default_config = self.get_default_config()
                updated = False
                for key, value in default_config.items():
                    if key not in new_config or new_config[key] is None:
                        new_config[key] = value
                        updated = True

                # 验证和规范化
                new_config = self._validate_and_clamp(new_config)

                self.config = new_config
                self.last_modified_time = current_mtime
                self._cache.clear()

                # 如果有更新，重新保存
                if updated:
                    self._log("检测到配置更新，正在保存...")
                    self._write_config(new_config)

                self._log(f"✅ 已加载配置: {self.config_file}")
                return self.config

            except json.JSONDecodeError as e:
                self._log(f"❌ 配置文件格式错误: {e}")
                # 备份损坏文件
                try:
                    import shutil
                    backup_path = self.config_file.with_suffix('.json.broken')
                    shutil.copy2(self.config_file, backup_path)
                    self._log(f"   已备份到: {backup_path}")
                except Exception:
                    pass

                # 使用默认配置
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
        """写入配置文件（带格式化注释）"""
        try:
            formatted = self._format_with_comments(config)
            with open(self.config_file, "w", encoding="utf-8") as f:
                f.write(formatted)
            return True
        except Exception as e:
            self._log(f"❌ 写入配置失败: {e}")
            return False

    def _format_with_comments(self, config: Dict[str, Any]) -> str:
        """格式化配置文件（添加分组注释）"""
        lines = ["{\n"]

        # 配置分组（按功能划分）
        groups = {
            "许可证配置": ["LICENSE_KEY"],
            "YOLO 检测": ["MODEL_PATH", "CROP_SIZE", "CONF_THRESHOLD", "IOU_THRESHOLD",
                         "TARGET_CLASS_IDS", "TARGET_CLASS_NAMES", "ENABLE_HEAD_PRIORITY",
                         "HEAD_CLASS_ID", "HEAD_PRIORITY_BONUS"],
            "瞄准点配置": ["AIM_Y_RATIO", "AIM_X_OFFSET"],
            "目标选择与跟踪": ["MIN_TARGET_LOCK_FRAMES", "TARGET_SWITCH_THRESHOLD",
                              "TARGET_IDENTITY_DISTANCE", "MAX_LOST_FRAMES",
                              "DISTANCE_WEIGHT", "AIM_POINT_SMOOTH_ALPHA"],
            "特效干扰抵抗": ["CONFIDENCE_HISTORY_SIZE", "CONFIDENCE_DROP_THRESHOLD",
                           "ATTACK_PROTECTION_TRIGGER_FRAMES", "LOCKED_TARGET_BONUS"],
            "卡尔曼滤波": ["USE_KALMAN_FILTER", "KALMAN_PROCESS_NOISE",
                          "KALMAN_MEASUREMENT_NOISE", "KALMAN_MAX_PREDICT_FRAMES"],
            "预判瞄准": ["ENABLE_LEAD_TARGET", "LEAD_FRAMES"],
            "PID 控制": ["PID_KP_X", "PID_KD_X", "PID_KI_X", "PID_KP_Y", "PID_KD_Y", "PID_KI_Y",
                        "MAX_SINGLE_MOVE_PX", "PRECISION_DEAD_ZONE", "DEFAULT_DELAY_MS_PER_STEP"],
            "鼠标控制模式": ["USE_DRIVER_MODE", "MOUSE_MODE_AUTO_FALLBACK", "MAX_MICKEY"],
            "驱动配置": ["DRIVER_PATH", "MOUSE_REQUEST"],
            "按键定义": ["APP_MOUSE_NO_BUTTON", "APP_MOUSE_LEFT_DOWN", "APP_MOUSE_LEFT_UP",
                        "APP_MOUSE_RIGHT_DOWN", "APP_MOUSE_RIGHT_UP", "APP_MOUSE_MIDDLE_DOWN",
                        "APP_MOUSE_MIDDLE_UP"],
            "按键监控": ["ENABLE_LEFT_MOUSE_MONITOR", "ENABLE_RIGHT_MOUSE_MONITOR",
                        "KEY_MONITOR_INTERVAL_MS"],
            "系统配置": ["ENABLE_LOGGING", "LOG_LEVEL", "DEBUG_MODE",
                        "CONFIG_MONITOR_INTERVAL_SEC", "CAPTURE_FPS", "INFERENCE_FPS"],
            "自动开火": ["ENABLE_AUTO_FIRE", "AUTO_FIRE_ACCURACY_THRESHOLD",
                        "AUTO_FIRE_DISTANCE_THRESHOLD", "AUTO_FIRE_MIN_LOCK_FRAMES",
                        "AUTO_FIRE_DEBUG_MODE"],
            "压枪模式": ["ENABLE_MANUAL_RECOIL", "ENABLE_RECOIL_CONTROL",
                        "MANUAL_RECOIL_TRIGGER_MODE"],
            "压枪触发条件": ["RECOIL_REQUIRE_TARGET", "RECOIL_REQUIRE_LOCK",
                           "RECOIL_TARGET_TIMEOUT", "RECOIL_MIN_LOCK_FRAMES"],
            "压枪速度配置": ["RECOIL_PATTERN", "RECOIL_VERTICAL_SPEED", "RECOIL_HORIZONTAL_SPEED",
                           "RECOIL_INCREMENT_Y"],
            "压枪限制": ["RECOIL_MAX_SINGLE_MOVE_X", "RECOIL_MAX_SINGLE_MOVE_Y",
                        "RECOIL_CUSTOM_PATTERN"],
            "其他": ["RECOIL_HORIZONTAL_VARIANCE", "RECOIL_MAX_SINGLE_MOVE"],
            "脚本": ["SCRIPT_AUTO_RELOAD", "SCRIPT_TIMEOUT_MS", "SCRIPT_DEBUG_MODE",
                    "ENABLED_SCRIPTS"]
        }

        processed_keys = set()

        # 按分组输出
        for group_name, keys in groups.items():
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

    def save_config(self) -> bool:
        """保存配置"""
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
        """获取配置值（带缓存）"""
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
        """设置配置值"""
        with self._rw_lock:
            self.config[key] = value
            self._cache.pop(key, None)

    def get_all(self) -> Dict[str, Any]:
        """获取所有配置（副本）"""
        with self._rw_lock:
            return self.config.copy()

    def start_auto_reload(self, interval_sec: Optional[int] = None) -> None:
        """启动自动配置重载"""
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

                    # 监控关键参数变化
                    critical_keys = [
                        "CONFIDENCE_DROP_THRESHOLD", "TARGET_SWITCH_THRESHOLD",
                        "ENABLE_HEAD_PRIORITY", "HEAD_PRIORITY_BONUS",
                        "PID_KP_X", "PID_KP_Y", "USE_DRIVER_MODE",
                        "RECOIL_REQUIRE_TARGET", "RECOIL_VERTICAL_SPEED"
                    ]
                    changed = [k for k in critical_keys if old_config.get(k) != self.config.get(k)]
                    if changed:
                        self._log(f"🔥 关键参数变化: {', '.join(changed)}")

        self._stop_monitor = False
        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop_auto_reload(self) -> None:
        """停止自动重载"""
        self._stop_monitor = True
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
            self._log("⏹ 配置自动重载已停止")


# ========== 全局单例 ==========
_config_manager = ConfigManager()


def load_config(force_reload: bool = False) -> Dict[str, Any]:
    """加载配置"""
    return _config_manager.load_config(force_reload=force_reload)


def get_config(key: str, default: Any = None) -> Any:
    """获取配置值"""
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
    print(f"✅ 配置加载成功，共 {len(config)} 项")
    print(f"📁 配置文件: {_config_manager.config_file}")
    print(f"\n🎯 优先锁定配置:")
    print(f"  启用: {get_config('ENABLE_HEAD_PRIORITY')}")
    print(f"  头部ID: {get_config('HEAD_CLASS_ID')}")
    print(f"  加分权重: {get_config('HEAD_PRIORITY_BONUS')}")
