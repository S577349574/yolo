"""配置文件管理器（管理加载、保存、导出配置文件）"""

import os
import sys
import json
from pathlib import Path

import utils


class ConfigManager:
    def __init__(self):
        # ========== 终极修复：兼容所有打包模式 ==========

        # 确定应用程序目录（支持打包和开发环境）
        if getattr(sys, 'frozen', False):
            # 打包后运行
            if hasattr(sys, '_MEIPASS'):  # PyInstaller 打包模式
                self.app_dir = Path(sys._MEIPASS)
            else:  # 其他打包工具（如Nuitka）
                exe_path = Path(sys.argv[0]).resolve()
                self.app_dir = exe_path.parent if exe_path.exists() else Path(os.getcwd())
        else:
            # 开发环境
            self.app_dir = Path(__file__).parent

        # ========== 强制使用EXE目录（如果运行在EXE中） ==========
        try:
            exe_final_path = Path(sys.executable).resolve()
            if exe_final_path.exists():
                self.app_dir = exe_final_path.parent
                utils.log(f"[ConfigManager] ✅ 使用EXE目录: {self.app_dir}")
        except:
            pass  # 保持原有逻辑

        # 配置文件路径
        self.config_file = self.app_dir / "config.json"
        self.config = {}

    def get_default_config(self):
        """返回默认配置（所有默认值集中在此处定义）"""
        return {
            # ========== YOLO模型配置 ==========
            "MODEL_PATH": "320.onnx",  # YOLO模型文件路径
            "CROP_SIZE": 320,  # 捕获区域尺寸
            "CONF_THRESHOLD": 0.75,  # YOLO模型置信度阈值
            "IOU_THRESHOLD": 0.45,  # IOU阈值
            "TARGET_CLASS_NAMES": ["敌人"],  # 目标类别名称

            # ========== 瞄准精度优化 ==========
            "AIM_POINTS": {
                "close": {"height_threshold": 150, "y_ratio": 0.45, "x_offset": 0},  # 近距离瞄准点
                "medium": {"height_threshold": 80, "y_ratio": 0.45, "x_offset": 0},  # 中距离瞄准点
                "far": {"height_threshold": 0, "y_ratio": 0.90, "x_offset": 0}  # 远距离瞄准点
            },

            # ========== 目标切换控制 ==========
            "MIN_TARGET_LOCK_FRAMES": 15,  # 锁定目标最小帧数
            "TARGET_SWITCH_THRESHOLD": 0.2,  # 目标切换的阈值
            "TARGET_IDENTITY_DISTANCE": 100,  # 目标识别距离

            # ========== 智能阈值控制 ==========
            "ENABLE_SMART_THRESHOLD": True,  # 是否启用智能阈值控制
            "MOVEMENT_THRESHOLD_PIXELS": 3,  # 移动阈值（像素）
            "INITIAL_LOCK_THRESHOLD": 2,  # 初始锁定阈值（像素）
            "ARRIVAL_THRESHOLD_ENTER": 3,  # 目标到达阈值（进入时）
            "ARRIVAL_THRESHOLD_EXIT": 20,  # 目标到达阈值（退出时）
            "MIN_SEND_INTERVAL_MS": 10,  # 发送指令最小间隔（毫秒）
            "STABLE_FRAMES_REQUIRED": 2,  # 锁定目标所需稳定帧数
            "COOLDOWN_AFTER_ARRIVAL_MS": 50,  # 到达目标后的冷却时间（毫秒）

            # ========== 鼠标控制配置 ==========
            "GAME_MODE": True,  # 是否启用游戏模式
            "GAME_DEAD_ZONE": 1,  # 游戏模式下的死区大小
            "GAME_DAMPING_FACTOR": 0.9,  # 游戏模式下的阻尼因子
            "MOUSE_ARRIVAL_THRESHOLD": 2,  # 鼠标到达目标的阈值（像素）
            "MOUSE_PROPORTIONAL_FACTOR": 0.15,  # 鼠标移动的比例因子
            "MOUSE_MAX_PIXELS_PER_STEP": 6,  # 每次鼠标移动的最大像素
            "DEFAULT_DELAY_MS_PER_STEP": 2,  # 每步默认延迟（毫秒）

            # ========== 驱动路径 ==========
            "DRIVER_PATH": r"\\.\infestation",  # 驱动路径

            # ========== 目标跟踪配置 ==========
            "MAX_LOST_FRAMES": 30,  # 目标丢失后的最大帧数
            "DISTANCE_WEIGHT": 0.80,  # 目标选择时的距离权重
            "COMMAND_UPDATE_THRESHOLD": 15,  # 更新目标命令的阈值

            # ========== 鼠标按钮标志 ==========
            "APP_MOUSE_NO_BUTTON": 0x00,  # 无按钮按下
            "APP_MOUSE_LEFT_DOWN": 0x01,  # 左键按下
            "APP_MOUSE_LEFT_UP": 0x02,  # 左键释放
            "APP_MOUSE_RIGHT_DOWN": 0x04,  # 右键按下
            "APP_MOUSE_RIGHT_UP": 0x08,  # 右键释放
            "APP_MOUSE_MIDDLE_DOWN": 0x10,  # 中键按下
            "APP_MOUSE_MIDDLE_UP": 0x20,  # 中键释放

            # ========== IOCTL请求码 ==========
            "MOUSE_REQUEST": (0x00000022 << 16) | (0 << 14) | (0x666 << 2) | 0x00000000,  # 鼠标请求码

            # ========== 新增：鼠标监视配置 ==========
            "ENABLE_LEFT_MOUSE_MONITOR": False,  # 是否启用鼠标左键监视
            "ENABLE_RIGHT_MOUSE_MONITOR": True,  # 是否启用鼠标右键监视

            # ========== 新增：按键监控间隔配置 ==========
            "KEY_MONITOR_INTERVAL_MS": 50,  # 按键监控轮询间隔（毫秒）
            "ENABLE_LOGGING": False,  # 是否启用日志记录

            # ========== 鼠标灵敏度校准 ==========
            "AUTO_CALIBRATE_ON_START": True,  # 启动时自动校准
            "CALIBRATION_SAMPLES": 5,  # 校准样本数量
            "ANTI_OVERSHOOT_ENABLED": True,  # 启用过冲补偿

            # ========== 自适应阻尼 ==========
            "ADAPTIVE_DAMPING_ENABLED": True,  # 启用自适应阻尼
            "DAMPING_NEAR_DISTANCE": 30,  # 近距离阈值（像素）
            "DAMPING_FAR_DISTANCE": 80,  # 远距离阈值（像素）
            "CALIBRATION_TEST_ROUNDS": 3,  # 校准测试轮次
            "MAX_DRIVER_STEP_SIZE": 8,  # 驱动最大步长（像素）
            "PID_KP": 0.35,  # PID比例系数
            "PID_KD": 0.02,  # PID微分系数
            "HYBRID_MODE_THRESHOLD": 20,  # 近中距模式切换阈值（像素）
            "PRECISION_DEAD_ZONE": 2,  # 死区大小（像素）
            "NEAR_DIST_KP_BOOST": 2.0,  # 小距离比例系数倍增
            "D_CLAMP_LIMIT": 0.5,  # PID D项限幅（像素）
            "PREDICT_PUSH_PX": 1.0,  # 预测推移（像素）
            "MIN_MOVE_THRESHOLD": 0.5,  # 最小移动阈值（像素）
            "MAX_SINGLE_MOVE_PX": 12  # 单次最大移动（像素）
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
