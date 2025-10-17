"""全局配置（兼容旧代码）"""
from config_manager import load_config, get_config

# 加载配置
_config = load_config()

# ========== YOLO模型配置 ==========
MODEL_PATH = _config.get('MODEL_PATH', '320.onnx')
CROP_SIZE = _config.get('CROP_SIZE', 320)
CONF_THRESHOLD = _config.get('CONF_THRESHOLD', 0.55)
IOU_THRESHOLD = _config.get('IOU_THRESHOLD', 0.45)
TARGET_CLASS_NAMES = _config.get('TARGET_CLASS_NAMES', ['敌人'])

# ========== 瞄准精度优化 ==========
AIM_POINTS = _config.get('AIM_POINTS', {
    'close': {'height_threshold': 150, 'y_ratio': 0.45, 'x_offset': 0},
    'medium': {'height_threshold': 80, 'y_ratio': 0.45, 'x_offset': 0},
    'far': {'height_threshold': 0, 'y_ratio': 0.80, 'x_offset': 0}
})

# ========== 目标切换控制 ==========
MIN_TARGET_LOCK_FRAMES = _config.get('MIN_TARGET_LOCK_FRAMES', 15)
TARGET_SWITCH_THRESHOLD = _config.get('TARGET_SWITCH_THRESHOLD', 0.2)
TARGET_IDENTITY_DISTANCE = _config.get('TARGET_IDENTITY_DISTANCE', 100)

# ========== 后坐力补偿配置 ==========
RECOIL_COMPENSATION_MODE = _config.get('RECOIL_COMPENSATION_MODE', True)
RECOIL_DETECTION_THRESHOLD = _config.get('RECOIL_DETECTION_THRESHOLD', 15)
RECOIL_RESPONSE_MULTIPLIER = _config.get('RECOIL_RESPONSE_MULTIPLIER', 2.0)

# ========== 智能阈值控制 ==========
ENABLE_SMART_THRESHOLD = _config.get('ENABLE_SMART_THRESHOLD', True)
MOVEMENT_THRESHOLD_PIXELS = _config.get('MOVEMENT_THRESHOLD_PIXELS', 3)
INITIAL_LOCK_THRESHOLD = _config.get('INITIAL_LOCK_THRESHOLD', 2)
ARRIVAL_THRESHOLD_ENTER = _config.get('ARRIVAL_THRESHOLD_ENTER', 3)
ARRIVAL_THRESHOLD_EXIT = _config.get('ARRIVAL_THRESHOLD_EXIT', 20)
MIN_SEND_INTERVAL_MS = _config.get('MIN_SEND_INTERVAL_MS', 8)
STABLE_FRAMES_REQUIRED = _config.get('STABLE_FRAMES_REQUIRED', 2)
COOLDOWN_AFTER_ARRIVAL_MS = _config.get('COOLDOWN_AFTER_ARRIVAL_MS', 50)

# ========== 鼠标控制配置 ==========
GAME_MODE = _config.get('GAME_MODE', True)
GAME_DEAD_ZONE = _config.get('GAME_DEAD_ZONE', 0)
GAME_DAMPING_FACTOR = _config.get('GAME_DAMPING_FACTOR', 0.90)
MOUSE_ARRIVAL_THRESHOLD = _config.get('MOUSE_ARRIVAL_THRESHOLD', 2)
MOUSE_PROPORTIONAL_FACTOR = _config.get('MOUSE_PROPORTIONAL_FACTOR', 0.15)
MOUSE_MAX_PIXELS_PER_STEP = _config.get('MOUSE_MAX_PIXELS_PER_STEP', 8)
DEFAULT_DELAY_MS_PER_STEP = _config.get('DEFAULT_DELAY_MS_PER_STEP', 2)

# ========== 驱动路径 ==========
DRIVER_PATH = _config.get('DRIVER_PATH', r"\\.\infestation")

# ========== 目标跟踪配置 ==========
MAX_LOST_FRAMES = _config.get('MAX_LOST_FRAMES', 30)
DISTANCE_WEIGHT = _config.get('DISTANCE_WEIGHT', 0.80)
COMMAND_UPDATE_THRESHOLD = _config.get('COMMAND_UPDATE_THRESHOLD', 15)

# ========== 鼠标按钮标志 ==========
APP_MOUSE_NO_BUTTON = _config.get('APP_MOUSE_NO_BUTTON', 0x00)
APP_MOUSE_LEFT_DOWN = _config.get('APP_MOUSE_LEFT_DOWN', 0x01)
APP_MOUSE_LEFT_UP = _config.get('APP_MOUSE_LEFT_UP', 0x02)
APP_MOUSE_RIGHT_DOWN = _config.get('APP_MOUSE_RIGHT_DOWN', 0x04)
APP_MOUSE_RIGHT_UP = _config.get('APP_MOUSE_RIGHT_UP', 0x08)
APP_MOUSE_MIDDLE_DOWN = _config.get('APP_MOUSE_MIDDLE_DOWN', 0x10)
APP_MOUSE_MIDDLE_UP = _config.get('APP_MOUSE_MIDDLE_UP', 0x20)

# ========== IOCTL请求码 ==========
MOUSE_REQUEST = _config.get('MOUSE_REQUEST', (0x00000022 << 16) | (0 << 14) | (0x666 << 2) | 0x00000000)
