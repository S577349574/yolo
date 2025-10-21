"""配置文件管理器"""
import os
import sys
import json
from pathlib import Path

import utils


class ConfigManager:
    def __init__(self):
        # ========== 终极修复：兼容所有打包模式 ==========
        if getattr(sys, 'frozen', False):
            # 打包后运行
            if hasattr(sys, '_MEIPASS'):  # PyInstaller
                # OneFile: 使用临时解压目录
                # OneDir: 使用 _MEIPASS（实际资源目录）
                self.app_dir = Path(sys._MEIPASS)
            else:  # Nuitka等其他打包工具
                try:
                    exe_path = Path(sys.argv[0]).resolve()
                    if exe_path.exists():
                        self.app_dir = exe_path.parent
                    else:
                        self.app_dir = Path(os.getcwd())
                except:
                    self.app_dir = Path(os.getcwd())
        else:
            # 开发环境
            self.app_dir = Path(__file__).parent

        # ========== 新增：强制使用EXE最终运行目录 ==========
        try:
            # 获取EXE实际文件位置（而非临时位置）
            exe_final_path = Path(sys.executable).resolve()
            if exe_final_path.exists():
                self.app_dir = exe_final_path.parent
                utils.log(f"[ConfigManager] ✅ 使用EXE目录: {self.app_dir}")
        except:
            pass  # 保持原有逻辑

        self.config_file = self.app_dir / "config.json"
        self.config = {}



    def get_default_config(self):
        """返回默认配置（所有默认值集中在此处定义）"""
        return {
            # ========== YOLO模型配置 ==========
            "MODEL_PATH": "320.onnx",
            "CROP_SIZE": 320,
            "CONF_THRESHOLD": 0.55,
            "IOU_THRESHOLD": 0.45,
            "TARGET_CLASS_NAMES": ["敌人"],

            # ========== 瞄准精度优化 ==========
            "AIM_POINTS": {
                "close": {"height_threshold": 150, "y_ratio": 0.45, "x_offset": 0},
                "medium": {"height_threshold": 80, "y_ratio": 0.45, "x_offset": 0},
                "far": {"height_threshold": 0, "y_ratio": 0.80, "x_offset": 0}
            },

            # ========== 目标切换控制 ==========
            "MIN_TARGET_LOCK_FRAMES": 15,
            "TARGET_SWITCH_THRESHOLD": 0.2,
            "TARGET_IDENTITY_DISTANCE": 100,


            # ========== 智能阈值控制 ==========
            "ENABLE_SMART_THRESHOLD": True,
            "MOVEMENT_THRESHOLD_PIXELS": 3,
            "INITIAL_LOCK_THRESHOLD": 2,
            "ARRIVAL_THRESHOLD_ENTER": 3,
            "ARRIVAL_THRESHOLD_EXIT": 20,
            "MIN_SEND_INTERVAL_MS": 10,
            "STABLE_FRAMES_REQUIRED": 2,
            "COOLDOWN_AFTER_ARRIVAL_MS": 50,

            # ========== 鼠标控制配置 ==========
            "GAME_MODE": True,
            "GAME_DEAD_ZONE": 8,
            "GAME_DAMPING_FACTOR": 0.9,
            "MOUSE_ARRIVAL_THRESHOLD": 2,
            "MOUSE_PROPORTIONAL_FACTOR": 0.15,
            "MOUSE_MAX_PIXELS_PER_STEP": 6,
            "DEFAULT_DELAY_MS_PER_STEP": 2,

            # ========== 驱动路径 ==========
            "DRIVER_PATH": r"\\.\infestation",

            # ========== 目标跟踪配置 ==========
            "MAX_LOST_FRAMES": 30,
            "DISTANCE_WEIGHT": 0.80,
            "COMMAND_UPDATE_THRESHOLD": 15,

            # ========== 鼠标按钮标志 ==========
            "APP_MOUSE_NO_BUTTON": 0x00,
            "APP_MOUSE_LEFT_DOWN": 0x01,
            "APP_MOUSE_LEFT_UP": 0x02,
            "APP_MOUSE_RIGHT_DOWN": 0x04,
            "APP_MOUSE_RIGHT_UP": 0x08,
            "APP_MOUSE_MIDDLE_DOWN": 0x10,
            "APP_MOUSE_MIDDLE_UP": 0x20,

            # ========== IOCTL请求码 ==========
            "MOUSE_REQUEST": (0x00000022 << 16) | (0 << 14) | (0x666 << 2) | 0x00000000,
            # ========== 新增：鼠标监视配置 ==========
            "ENABLE_LEFT_MOUSE_MONITOR": False,  # 是否开启鼠标左键监视
            "ENABLE_RIGHT_MOUSE_MONITOR": True,  # 是否开启鼠标右键监视

            # ========== 新增：按键监控间隔配置 ==========
            "KEY_MONITOR_INTERVAL_MS": 50,  # 按键监控轮询间隔（毫秒）
            "ENABLE_LOGGING": False,# ========== 鼠标灵敏度校准 ==========
            "AUTO_CALIBRATE_ON_START": True,  # 启动时自动校准
            "CALIBRATION_SAMPLES": 5,  # 校准样本数量
            "ANTI_OVERSHOOT_ENABLED": True,  # 启用过冲补偿

            # ========== 自适应阻尼 ==========
            "ADAPTIVE_DAMPING_ENABLED": True,  # 启用自适应阻尼
            "DAMPING_NEAR_DISTANCE": 30,  # 近距离阈值(px)
            "DAMPING_FAR_DISTANCE": 80,  # 远距离阈值(px)
            "CALIBRATION_TEST_ROUNDS": 3,
            "MAX_DRIVER_STEP_SIZE": 8,
            "PID_KP": 0.35,
            "PID_KI": 0.0,
            "PID_KD": 0.12,
            "MAX_SINGLE_MOVE_PX": 25,
            "AIM_POINT_SMOOTH_ALPHA": 0.35,
            "PRECISION_DEAD_ZONE": 20

        }

    def export_default_config(self):
        """导出默认配置到文件"""
        default_config = self.get_default_config()
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
            utils.log(f"✅ 已导出默认配置到: {self.config_file}")
            return True
        except Exception as e:
            utils.log(f"❌ 导出配置失败: {e}")
            return False

    def load_config(self):
        """加载配置文件"""
        # 检查配置文件是否存在
        if not self.config_file.exists():
            utils.log(f"⚠️ 未找到配置文件: {self.config_file}")
            utils.log("📝 正在创建默认配置...")
            self.export_default_config()
            self.config = self.get_default_config()
            return self.config

        # 读取配置文件
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            utils.log(f"✅ 已加载配置文件: {self.config_file}")

            # 合并默认配置（处理新增的配置项）
            default_config = self.get_default_config()
            updated = False
            for key, value in default_config.items():
                if key not in self.config:
                    self.config[key] = value
                    updated = True
                    utils.log(f"➕ 添加新配置项: {key}")

            # 如果有新增配置项，更新文件
            if updated:
                self.save_config()

            return self.config
        except json.JSONDecodeError as e:
            utils.log(f"❌ 配置文件格式错误: {e}")
            utils.log("📝 使用默认配置...")
            self.config = self.get_default_config()
            return self.config
        except Exception as e:
            utils.log(f"❌ 加载配置失败: {e}")
            utils.log("📝 使用默认配置...")
            self.config = self.get_default_config()
            return self.config

    def save_config(self):
        """保存当前配置到文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            utils.log(f"✅ 配置已保存: {self.config_file}")
            return True
        except Exception as e:
            utils.log(f"❌ 保存配置失败: {e}")
            return False

    def get(self, key, default=None):
        """获取配置项"""
        return self.config.get(key, default)

    def set(self, key, value):
        """设置配置项"""
        self.config[key] = value

    def get_all(self):
        """获取所有配置"""
        return self.config


# 全局配置管理器实例
_config_manager = ConfigManager()


def load_config():
    """加载配置（供其他模块调用）"""
    return _config_manager.load_config()


def get_config(key, default=None):
    """获取配置项（供其他模块调用）"""
    return _config_manager.get(key, default)


def save_config():
    """保存配置（供其他模块调用）"""
    return _config_manager.save_config()
