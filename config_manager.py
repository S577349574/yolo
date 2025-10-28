# config_manager.py
"""配置文件管理器（管理加载、保存、导出配置文件）"""

import os
import sys
import json
from pathlib import Path


class ConfigManager:
    def __init__(self):
        # 打包 or 开发环境目录
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
        self.config = {}
        self.last_modified_time = 0

    def _log(self, message):
        import utils
        utils.log(message)

    def get_default_config(self):
        """默认配置"""
        return {
            # YOLO
            "MODEL_PATH": "320.onnx",
            "CROP_SIZE": 320,
            "CONF_THRESHOLD": 0.75,
            "IOU_THRESHOLD": 0.45,
            "TARGET_CLASS_NAMES": ["敌人"],

            # 瞄准点
            "AIM_POINTS": {
                "close": {"height_threshold": 10000, "y_ratio": 0.55, "x_offset": 0},
                "medium": {"height_threshold": 0, "y_ratio": 0.55, "x_offset": 0},
                "far": {"height_threshold": 0, "y_ratio": 0.55, "x_offset": 0}
            },

            # 目标切换
            "MIN_TARGET_LOCK_FRAMES": 15,
            "TARGET_SWITCH_THRESHOLD": 0.2,
            "TARGET_IDENTITY_DISTANCE": 100,

            # 智能阈值
            "ENABLE_SMART_THRESHOLD": True,
            "MOVEMENT_THRESHOLD_PIXELS": 3,
            "INITIAL_LOCK_THRESHOLD": 2,
            "ARRIVAL_THRESHOLD_ENTER": 3,
            "ARRIVAL_THRESHOLD_EXIT": 20,
            "MIN_SEND_INTERVAL_MS": 10,
            "STABLE_FRAMES_REQUIRED": 2,
            "COOLDOWN_AFTER_ARRIVAL_MS": 50,

            # 鼠标控制
            "GAME_MODE": True,
            "GAME_DEAD_ZONE": 1,
            "GAME_DAMPING_FACTOR": 0.90,
            "MOUSE_ARRIVAL_THRESHOLD": 3,
            "MOUSE_PROPORTIONAL_FACTOR": 0.15,
            "MOUSE_MAX_PIXELS_PER_STEP": 6,
            "DEFAULT_DELAY_MS_PER_STEP": 2,

            # 驱动
            "DRIVER_PATH": r"\\.\infestation",

            # 跟踪
            "MAX_LOST_FRAMES": 30,
            "DISTANCE_WEIGHT": 0.80,
            "COMMAND_UPDATE_THRESHOLD": 15,

            # 按键 flag
            "APP_MOUSE_NO_BUTTON": 0x00,
            "APP_MOUSE_LEFT_DOWN": 0x01,
            "APP_MOUSE_LEFT_UP": 0x02,
            "APP_MOUSE_RIGHT_DOWN": 0x04,
            "APP_MOUSE_RIGHT_UP": 0x08,
            "APP_MOUSE_MIDDLE_DOWN": 0x10,
            "APP_MOUSE_MIDDLE_UP": 0x20,

            # IOCTL
            "MOUSE_REQUEST": (0x00000022 << 16) | (0 << 14) | (0x666 << 2) | 0x00000000,

            # 监视与日志
            "ENABLE_LEFT_MOUSE_MONITOR": False,
            "ENABLE_RIGHT_MOUSE_MONITOR": True,
            "KEY_MONITOR_INTERVAL_MS": 50,
            "ENABLE_LOGGING": False,

            # 校准/阻尼
            "AUTO_CALIBRATE_ON_START": True,
            "CALIBRATION_SAMPLES": 5,
            "ANTI_OVERSHOOT_ENABLED": True,
            "ADAPTIVE_DAMPING_ENABLED": True,
            "DAMPING_NEAR_DISTANCE": 30,
            "DAMPING_FAR_DISTANCE": 80,
            "CALIBRATION_TEST_ROUNDS": 3,
            "MAX_DRIVER_STEP_SIZE": 8,

            # PID / 模式
            "PID_KP": 0.5,
            "PID_KD": 0.08,
            "HYBRID_MODE_THRESHOLD": 40,
            "PRECISION_DEAD_ZONE": 2,
            "NEAR_DIST_KP_BOOST": 2.0,
            "D_CLAMP_LIMIT": 0.5,
            "PREDICT_PUSH_PX": 1.0,
            "MIN_MOVE_THRESHOLD": 0.5,
            "MAX_SINGLE_MOVE_PX": 12,

            # 直驱护栏（新增）
            "FAR_GAIN": 0.6,
            "FAR_MAX_STEP": 20,
            "NEAR_GATE_RATIO": 0.6,

            # 配置监控
            "CONFIG_MONITOR_INTERVAL_SEC": 5,

            "CAPTURE_FPS": 60,
            "INFERENCE_FPS": 60,


           "AIM_POINT_SMOOTH_ALPHA": 0.25,  # 0.1=最平滑，0.5=快速响应
        }

    def export_default_config(self):
        default_config = self.get_default_config()
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
            self._log(f"✅ 已导出默认配置到: {self.config_file}")
            return True
        except Exception as e:
            self._log(f"❌ 导出配置失败: {e}")
            return False

    def _postprocess_config(self):
        """载入/合并配置后的规范化与兜底"""
        c = self.config

        # 1) MODEL_PATH 绝对化
        model_path = c.get("MODEL_PATH")
        if isinstance(model_path, str) and model_path.strip():
            p = Path(model_path)
            if not p.is_absolute():
                p = (self.app_dir / p).resolve()
            c["MODEL_PATH"] = str(p)

        # 2) clamp 工具
        def clamp(name, lo=None, hi=None, typ=float, default=None):
            v = c.get(name, default)
            try:
                v = typ(v)
            except Exception:
                v = default if default is not None else (lo if lo is not None else v)
            if lo is not None and v < lo:
                v = lo
            if hi is not None and v > hi:
                v = hi
            c[name] = v

        clamp("PRECISION_DEAD_ZONE", 0, 50, int, 4)
        clamp("MOUSE_ARRIVAL_THRESHOLD", 0, 50, int, 4)
        clamp("HYBRID_MODE_THRESHOLD", 5, 200, int, 40)
        clamp("MAX_SINGLE_MOVE_PX", 1, 100, int, 8)
        clamp("MAX_DRIVER_STEP_SIZE", 1, 100, int, 8)
        clamp("DEFAULT_DELAY_MS_PER_STEP", 1, 100, int, 3)
        clamp("MIN_SEND_INTERVAL_MS", 1, 100, int, 18)

        clamp("GAME_DAMPING_FACTOR", 0.80, 0.995, float, 0.94)

        clamp("PID_KP", 0.0, 5.0, float, 0.18)
        clamp("PID_KD", 0.0, 5.0, float, 0.06)
        clamp("D_CLAMP_LIMIT", 0.0, 10.0, float, 0.35)

        clamp("FAR_GAIN", 0.1, 0.95, float, 0.6)
        clamp("FAR_MAX_STEP", 4, 64, int, 24)
        clamp("NEAR_GATE_RATIO", 0.1, 0.95, float, 0.6)

        # 到达判定 ≥ 死区
        if c["MOUSE_ARRIVAL_THRESHOLD"] < c["PRECISION_DEAD_ZONE"]:
            c["MOUSE_ARRIVAL_THRESHOLD"] = c["PRECISION_DEAD_ZONE"]

        # 混合阈值 >= 到达/死区的 3 倍
        min_hybrid = max(c["MOUSE_ARRIVAL_THRESHOLD"], c["PRECISION_DEAD_ZONE"]) * 3
        if c["HYBRID_MODE_THRESHOLD"] < min_hybrid:
            c["HYBRID_MODE_THRESHOLD"] = int(min_hybrid)

        # 阻尼距离基本边界
        for k, default in [("DAMPING_NEAR_DISTANCE", 30), ("DAMPING_FAR_DISTANCE", 90)]:
            try:
                v = int(c.get(k, default))
            except Exception:
                v = default
            v = max(1, min(v, 500))
            c[k] = v

    def load_config(self, force_reload=False):
        """加载配置，支持动态重载"""
        self._log("📝 执行到了加载配置")
        current_modified_time = os.path.getmtime(self.config_file) if self.config_file.exists() else 0

        # 仅在：文件存在 + 曾加载过 + 未变化 时早退
        if (
            not force_reload
            and self.config_file.exists()
            and self.last_modified_time != 0
            and current_modified_time == self.last_modified_time
        ):
            return self.config

        # 若文件缺失，导出默认并载入
        if not self.config_file.exists():
            self._log(f"⚠️ 未找到配置文件: {self.config_file}")
            self._log("📝 正在创建默认配置...")
            self.export_default_config()
            self.config = self.get_default_config()
            self.last_modified_time = os.path.getmtime(self.config_file)
            self._postprocess_config()
            return self.config

        # 读取
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                new_config = json.load(f)
            self._log(f"✅ 已加载配置文件: {self.config_file}")

            # 合并默认（缺键或为 None 的覆盖）
            default_config = self.get_default_config()
            updated = False
            for key, value in default_config.items():
                if key not in new_config or new_config[key] is None:
                    new_config[key] = value
                    updated = True
                    self._log(f"➕ 使用默认值覆盖/补全配置项: {key}")

            self.config = new_config
            self.last_modified_time = current_modified_time

            if updated:
                self.save_config()

            self._postprocess_config()
            return self.config

        except json.JSONDecodeError as e:
            self._log(f"❌ 配置文件格式错误: {e}")
            self._log("📝 使用默认配置...")
            self.config = self.get_default_config()
            self.last_modified_time = current_modified_time
            self._postprocess_config()
            return self.config
        except Exception as e:
            self._log(f"❌ 加载配置失败: {e}")
            self._log("📝 使用默认配置...")
            self.config = self.get_default_config()
            self.last_modified_time = current_modified_time
            self._postprocess_config()
            return self.config

    def save_config(self):
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            self._log(f"✅ 配置已保存: {self.config_file}")
            return True
        except Exception as e:
            self._log(f"❌ 保存配置失败: {e}")
            return False

    def get(self, key, default=None):
        if not self.config:
            self.load_config()
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value

    def get_all(self):
        return self.config


# 全局实例与便捷函数
_config_manager = ConfigManager()


def load_config(force_reload=False):
    return _config_manager.load_config(force_reload=force_reload)


def get_config(key, default=None):
    return _config_manager.get(key, default)


def save_config():
    return _config_manager.save_config()
