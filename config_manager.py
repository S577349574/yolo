"""配置文件管理器（支持热重载、性能优化、安全验证 - 适配特效干扰抵抗）"""

import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigManager:
    def __init__(self):
        # ✅ 修复：更可靠的打包环境检测
        is_frozen = (
                getattr(sys, "frozen", False) or  # PyInstaller/cx_Freeze
                hasattr(sys, "_MEIPASS") or  # PyInstaller
                "__compiled__" in sys.modules or  # Nuitka
                Path(sys.argv[0]).suffix.lower() == ".exe"  # 任何 exe
        )

        print(f"[DEBUG] is_frozen = {is_frozen}")
        print(f"[DEBUG] sys.frozen = {getattr(sys, 'frozen', None)}")
        print(f"[DEBUG] __compiled__ in modules = {'__compiled__' in sys.modules}")

        if is_frozen:
            # 打包后：使用 exe 所在目录
            try:
                # 方法1：尝试使用 Nuitka 的 __compiled__ 模块
                import __compiled__
                self.app_dir = Path(__compiled__.__file__).parent.resolve()
                self._log(f"[ConfigManager] 使用__compiled__路径: {self.app_dir}")
            except (ImportError, AttributeError):
                # 方法2：使用 sys.argv[0]（命令行第一个参数）
                self.app_dir = Path(sys.argv[0]).parent.resolve()
                self._log(f"[ConfigManager] 使用argv[0]路径: {self.app_dir}")
        else:
            # 开发模式：脚本所在目录
            self.app_dir = Path(__file__).parent.resolve()
            self._log(f"[ConfigManager] 使用开发目录: {self.app_dir}")

        self.config_file = self.app_dir / "config.json"
        self.config: Dict[str, Any] = {}
        self.last_modified_time: float = 0

        # 线程安全：读写锁
        self._lock = threading.RLock()

        # 性能优化：缓存常用配置（带过期时间）
        self._cache: Dict[str, tuple] = {}
        self._cache_ttl = 0.1

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
            # ========== YOLO 检测 ==========
            "MODEL_PATH": "320.onnx",  # ✅ 相对于 exe 运行目录
            "CROP_SIZE": 320,
            "CONF_THRESHOLD": 0.55,
            "IOU_THRESHOLD": 0.45,
            "TARGET_CLASS_NAMES": ["敌人"],

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

            # ========== 速度和加速度预测 ==========
            "ENABLE_VELOCITY_PREDICTION": True,
            "PREDICT_DELAY_SEC": 0.035,
            "VELOCITY_SMOOTH_ALPHA": 0.4,
            "ENABLE_ACCEL_PREDICTION": False,
            "ACCEL_SMOOTH_ALPHA": 0.2,

            # 🔥 新增：特效干扰抵抗参数
            "CONFIDENCE_HISTORY_SIZE": 10,              # 置信度历史记录长度
            "CONFIDENCE_DROP_THRESHOLD": 0.15,          # 置信度骤降阈值（检测攻击）
            "ATTACK_PROTECTION_TRIGGER_FRAMES": 3,      # 激活保护所需连续低置信度帧数
            "LOCKED_TARGET_BONUS": 0.15,                # 锁定目标评分加成（提升粘性）

            # ========== PID 控制参数 ==========
            "PID_KP": 0.2,
            "PID_KD": 0.05,
            "PID_KI": 0.02,
            "MAX_SINGLE_MOVE_PX": 400,
            "PRECISION_DEAD_ZONE": 2,
            "DEFAULT_DELAY_MS_PER_STEP": 1,

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
            "ENABLE_LOGGING": False,
            "CONFIG_MONITOR_INTERVAL_SEC": 5,
            "CAPTURE_FPS": 300,
            "INFERENCE_FPS": 300,

            # ========== 自动开火配置 ==========
            "ENABLE_AUTO_FIRE": False,
            "ENABLE_MANUAL_RECOIL": True,
            "MANUAL_RECOIL_TRIGGER_MODE": "both_buttons",
            "AUTO_FIRE_ACCURACY_THRESHOLD": 0.5,
            "AUTO_FIRE_DISTANCE_THRESHOLD": 15.0,
            "AUTO_FIRE_MIN_LOCK_FRAMES": 3,
            "AUTO_FIRE_DEBUG_MODE": False,

            # ========== 压枪配置 ==========
            "ENABLE_RECOIL_CONTROL": True,
            "RECOIL_PATTERN": "linear",
            "RECOIL_VERTICAL_SPEED": 110.0,
            "RECOIL_INCREMENT_Y": 0.5,
            "RECOIL_HORIZONTAL_VARIANCE": 1.5,
            "RECOIL_MAX_SINGLE_MOVE": 110.0,
            "RECOIL_CUSTOM_PATTERN": [],
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

        # 速度预测参数
        clamp("PREDICT_DELAY_SEC", 0.001, 0.2, float, 0.035)
        clamp("VELOCITY_SMOOTH_ALPHA", 0.01, 1.0, float, 0.4)
        clamp("ACCEL_SMOOTH_ALPHA", 0.01, 1.0, float, 0.2)

        # 🔥 特效干扰抵抗参数
        clamp("CONFIDENCE_HISTORY_SIZE", 3, 50, int, 10)
        clamp("CONFIDENCE_DROP_THRESHOLD", 0.05, 0.5, float, 0.15)
        clamp("ATTACK_PROTECTION_TRIGGER_FRAMES", 1, 20, int, 3)
        clamp("LOCKED_TARGET_BONUS", 0.0, 0.5, float, 0.15)

        # PID 参数
        clamp("PID_KP", 0.0, 10.0, float, 0.2)
        clamp("PID_KD", 0.0, 5.0, float, 0.05)
        clamp("PID_KI", 0.0, 1.0, float, 0.02)
        clamp("MAX_SINGLE_MOVE_PX", 1, 1000, int, 400)
        clamp("PRECISION_DEAD_ZONE", 0, 50, int, 2)
        clamp("DEFAULT_DELAY_MS_PER_STEP", 1, 100, int, 1)

        # 系统参数
        clamp("KEY_MONITOR_INTERVAL_MS", 10, 1000, int, 50)
        clamp("CONFIG_MONITOR_INTERVAL_SEC", 1, 60, int, 5)
        clamp("CAPTURE_FPS", 1, 500, int, 300)
        clamp("INFERENCE_FPS", 1, 500, int, 300)

        # 自动开火参数
        clamp("AUTO_FIRE_ACCURACY_THRESHOLD", 0.1, 0.99, float, 0.5)
        clamp("AUTO_FIRE_DISTANCE_THRESHOLD", 1.0, 200.0, float, 15.0)
        clamp("AUTO_FIRE_MIN_LOCK_FRAMES", 1, 100, int, 3)

        # 压枪参数
        clamp("RECOIL_VERTICAL_SPEED", 10.0, 1000.0, float, 110.0)
        clamp("RECOIL_INCREMENT_Y", 0.0, 10.0, float, 0.5)
        clamp("RECOIL_HORIZONTAL_VARIANCE", 0.0, 20.0, float, 1.5)
        clamp("RECOIL_MAX_SINGLE_MOVE", 1.0, 500.0, float, 110.0)

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
            "ENABLE_LOGGING", "ENABLE_VELOCITY_PREDICTION", "ENABLE_ACCEL_PREDICTION",
            "ENABLE_AUTO_FIRE", "ENABLE_MANUAL_RECOIL", "AUTO_FIRE_DEBUG_MODE",
            "ENABLE_RECOIL_CONTROL"
        ]
        for key in bool_keys:
            if not isinstance(c.get(key), bool):
                c[key] = False

        # ========== MODEL_PATH 处理（基于 exe 运行目录）==========
        model_path = c.get("MODEL_PATH", "320.onnx")
        if isinstance(model_path, str) and model_path.strip():
            p = Path(model_path)
            if not p.is_absolute():
                p = (self.app_dir / p).resolve()

            if not p.exists():
                self._log(f"⚠ 模型文件不存在: {p}")
                self._log(f"   请确保 {p.name} 在程序目录: {self.app_dir}")

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
                self._log(f"⚠未找到配置文件: {self.config_file}")
                self._log("正在创建默认配置...")
                default = self._validate_and_clamp(self.get_default_config())
                self._write_config(default)
                self.config = default
                self.last_modified_time = current_modified_time
                self._cache.clear()
                return self.config

            # 读取配置文件
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    new_config = json.load(f)

                # ✅ 合并默认值（补全缺失的新参数）
                default_config = self.get_default_config()
                updated = False
                for key, value in default_config.items():
                    if key not in new_config or new_config[key] is None:
                        new_config[key] = value
                        updated = True
                        self._log(f"补全配置项: {key} = {value}")

                # ✅ 验证和限制范围
                new_config = self._validate_and_clamp(new_config)

                self.config = new_config
                self.last_modified_time = current_modified_time
                self._cache.clear()

                if updated:
                    self._log("检测到配置更新，正在保存...")
                    self._write_config(new_config)

                self._log(f"✅ 已加载配置文件: {self.config_file}")
                return self.config

            except json.JSONDecodeError as e:
                self._log(f"❌ 配置文件格式错误: {e}")
                self._log("使用默认配置并备份损坏文件...")

                # 备份损坏的配置文件
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
        """内部：写入配置文件（带格式化注释）"""
        try:
            # 🔥 分组写入配置（提升可读性）
            formatted_config = self._format_config_with_comments(config)

            with open(self.config_file, "w", encoding="utf-8") as f:
                f.write(formatted_config)
            return True
        except Exception as e:
            self._log(f"❌ 写入配置失败: {e}")
            return False

    def _format_config_with_comments(self, config: Dict[str, Any]) -> str:
        """🔥 新增：格式化配置文件（添加分组注释）"""
        lines = ["{\n"]

        # 定义分组
        groups = {
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
            "速度和加速度预测": [
                "ENABLE_VELOCITY_PREDICTION", "PREDICT_DELAY_SEC",
                "VELOCITY_SMOOTH_ALPHA", "ENABLE_ACCEL_PREDICTION",
                "ACCEL_SMOOTH_ALPHA"
            ],
            "特效干扰抵抗": [
                "CONFIDENCE_HISTORY_SIZE", "CONFIDENCE_DROP_THRESHOLD",
                "ATTACK_PROTECTION_TRIGGER_FRAMES", "LOCKED_TARGET_BONUS"
            ],
            "PID 控制": [
                "PID_KP", "PID_KD", "PID_KI", "MAX_SINGLE_MOVE_PX",
                "PRECISION_DEAD_ZONE", "DEFAULT_DELAY_MS_PER_STEP"
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
                "ENABLE_LOGGING", "CONFIG_MONITOR_INTERVAL_SEC",
                "CAPTURE_FPS", "INFERENCE_FPS"
            ],
            "自动开火": [
                "ENABLE_AUTO_FIRE", "AUTO_FIRE_ACCURACY_THRESHOLD",
                "AUTO_FIRE_DISTANCE_THRESHOLD", "AUTO_FIRE_MIN_LOCK_FRAMES",
                "AUTO_FIRE_DEBUG_MODE"
            ],
            "压枪配置": [
                "ENABLE_MANUAL_RECOIL", "ENABLE_RECOIL_CONTROL",
                "MANUAL_RECOIL_TRIGGER_MODE", "RECOIL_PATTERN",
                "RECOIL_VERTICAL_SPEED", "RECOIL_INCREMENT_Y",
                "RECOIL_HORIZONTAL_VARIANCE", "RECOIL_MAX_SINGLE_MOVE",
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

        # 添加未分组的配置项
        remaining_keys = set(config.keys()) - processed_keys
        if remaining_keys:
            lines.append('    "_comment_其他": "========== 其他配置 ==========",\n')
            for key in sorted(remaining_keys):
                value = json.dumps(config[key], ensure_ascii=False)
                lines.append(f'    "{key}": {value},\n')

        # 移除最后一个逗号
        if lines[-1].endswith(',\n'):
            lines[-1] = lines[-1][:-2] + '\n'

        lines.append("}\n")
        return "".join(lines)

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
            self._log("⚠ 配置监控线程已在运行")
            return

        if interval_sec is None:
            interval_sec = self.get("CONFIG_MONITOR_INTERVAL_SEC", 5)

        def monitor_loop():
            self._log(f"🔄 配置自动重载已启动 (间隔: {interval_sec}秒)")
            while not self._stop_monitor:
                time.sleep(interval_sec)
                if not self._stop_monitor:
                    old_config = self.config.copy()
                    self.load_config()

                    # 检测关键参数变化并提示
                    critical_keys = [
                        "CONFIDENCE_DROP_THRESHOLD", "ATTACK_PROTECTION_TRIGGER_FRAMES",
                        "LOCKED_TARGET_BONUS", "TARGET_SWITCH_THRESHOLD"
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
