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
        """默认配置（精简版）"""
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
            "MOUSE_REQUEST": (0x00000022 << 16) | (0 << 14) | (0x666 << 2) | 0x00000000,

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

        # 基础参数限制
        clamp("PRECISION_DEAD_ZONE", 0, 50, int, 2)
        clamp("MAX_SINGLE_MOVE_PX", 1, 500, int, 200)
        clamp("DEFAULT_DELAY_MS_PER_STEP", 1, 100, int, 2)

        # PID 参数限制
        clamp("PID_KP", 0.0, 5.0, float, 0.95)
        clamp("PID_KD", 0.0, 5.0, float, 0.05)

        # 帧率限制
        clamp("CAPTURE_FPS", 1, 300, int, 60)
        clamp("INFERENCE_FPS", 1, 300, int, 60)

    def load_config(self, force_reload=False):
        """加载配置，支持动态重载"""
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
