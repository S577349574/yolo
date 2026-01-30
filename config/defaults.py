"""默认配置定义"""

from typing import Any, Dict


# 配置分组（用于格式化输出）
CONFIG_GROUPS = {
    "许可证配置": ["LICENSE_KEY"],

    "模型配置": [
        # 通用模型配置
        "MODEL_PATH",
        "MODEL_TYPE",
        "CLASS_NAMES_PATH",

        # 后端选择
        "FORCE_BACKEND",

        # ONNX Runtime 配置
        "USE_TENSORRT",

        # ncnn 配置
        "NCNN_PARAM_PATH",
        "NCNN_BIN_PATH",
        "NCNN_INPUT_NAME",
        "NCNN_OUTPUT_NAMES",
        "NCNN_USE_FP16"
    ],

    "图像源配置": [
        "IMAGE_SOURCE_TYPE", "CROP_SIZE",
        "FRAME_PORT", "FRAME_WIDTH", "FRAME_HEIGHT", "FRAME_CHANNELS",
        "PREVIEW_FRAME_SKIP", "ENABLE_PREVIEW_WINDOW", "PREVIEW_WINDOW_WIDTH", "PREVIEW_WINDOW_HEIGHT",
        "PREVIEW_SHOW_BOXES", "PREVIEW_SHOW_LABELS", "PREVIEW_SHOW_CONFIDENCE",
        "PREVIEW_SHOW_FPS", "PREVIEW_SHOW_CROSSHAIR", "PREVIEW_SHOW_AIM_POINT",
        "PREVIEW_BOX_THICKNESS", "PREVIEW_SHOW_SEARCH_AREA", "PREVIEW_TEXT_SCALE"
    ],

    "YOLO 检测": [
        "CONF_THRESHOLD", "IOU_THRESHOLD",
        "TARGET_CLASS_IDS", "TARGET_CLASS_NAMES"
    ],

    "目标分组": [
        "TARGET_GROUP_DISTANCE_THRESHOLD"
    ],

    "准星检测配置": [
        "ENABLE_CROSSHAIR_DETECTION",
        "CROSSHAIR_DETECTOR_TYPE",
        "CROSSHAIR_VALORANT_CONFIG",
        "CROSSHAIR_TEMPLATE_PATH",
        "CROSSHAIR_USE_FALLBACK_CENTER",
        "CROSSHAIR_DEBUG_MODE",
        "CROSSHAIR_STATS_INTERVAL",
        "CROSSHAIR_SEARCH_BOUNDS",
        "CROSSHAIR_SMOOTH_FACTOR",
        "CROSSHAIR_MAX_LOST_FRAMES"
    ],

    "目标选择": [
        "MIN_TARGET_LOCK_FRAMES", "TARGET_SWITCH_DISTANCE_THRESHOLD",
        "TARGET_IDENTITY_DISTANCE", "MAX_LOST_FRAMES", "TARGET_ID_GRID_SIZE"
    ],

    "头部优先": [
        "ENABLE_HEAD_PRIORITY", "HEAD_CLASS_ID", "HEAD_PRIORITY_RANGE",
        "IGNORE_SMALL_TARGET_HEAD", "SMALL_TARGET_AREA_THRESHOLD"
    ],

    "瞄准点配置": [
        "AIM_Y_RATIO", "AIM_X_OFFSET"
    ],

    "卡尔曼滤波": [
        "USE_KALMAN_FILTER", "KALMAN_PROCESS_NOISE",
        "KALMAN_MEASUREMENT_NOISE", "KALMAN_MAX_PREDICT_FRAMES"
    ],

    "EMA平滑(备用)": [
        "AIM_POINT_SMOOTH_ALPHA"
    ],

    "预判瞄准": [
        "ENABLE_LEAD_TARGET", "LEAD_FRAMES"
    ],

    "PID 控制": [
        "PID_KP_X", "PID_KD_X", "PID_KI_X",
        "PID_KP_Y", "PID_KD_Y", "PID_KI_Y",
        "MAX_SINGLE_MOVE_PX", "PRECISION_DEAD_ZONE", "DEFAULT_DELAY_MS_PER_STEP"
    ],

    # ⭐ 更新：鼠标控制模式（添加 MTKmbox）
    "鼠标控制模式": [
        "USE_MAKCU", "MAKCU_PORT", "MAKCU_AUTO_RECONNECT",
        "MAKCU_MIN_SEND_INTERVAL", "MAKCU_QUEUE_SIZE",
        "USE_MTKMBOX", "MTKMBOX_PORT", "MTKMBOX_VID", "MTKMBOX_PID",  # ⭐ 新增
        "MTKMBOX_MAX_MOVE", "SERIAL_MIN_SEND_INTERVAL",  # ⭐ 新增
        "USE_DRIVER_MODE", "MOUSE_MODE_AUTO_FALLBACK", "MAX_MICKEY"
    ],

    "驱动配置": [
        "DRIVER_PATH", "MOUSE_REQUEST"
    ],

    "按键定义": [
        "APP_MOUSE_NO_BUTTON", "APP_MOUSE_LEFT_DOWN", "APP_MOUSE_LEFT_UP",
        "APP_MOUSE_RIGHT_DOWN", "APP_MOUSE_RIGHT_UP",
        "APP_MOUSE_MIDDLE_DOWN", "APP_MOUSE_MIDDLE_UP"
    ],

    # ⭐ 更新：按键监控（添加 MTKmbox）
    "按键监控": [
        "ENABLE_LEFT_MOUSE_MONITOR", "ENABLE_RIGHT_MOUSE_MONITOR",
        "ENABLE_MOUSE4_MONITOR", "ENABLE_MOUSE5_MONITOR",
        "KEY_MONITOR_INTERVAL_MS",
        "MAKCU_USE_HARDWARE_MONITOR", "MAKCU_FALLBACK_TO_PYNPUT",  # Makcu 特定
        "MTKMBOX_USE_HARDWARE_MONITOR", "MTKMBOX_FALLBACK_TO_PYNPUT"  # ⭐ MTKmbox 特定
    ],

    "系统配置": [
        "ENABLE_LOGGING", "LOG_LEVEL", "DEBUG_MODE",
        "MAKCU_DEBUG_MODE", "MTKMBOX_DEBUG_MODE",  # ⭐ 新增
        "CONFIG_MONITOR_INTERVAL_SEC", "CAPTURE_FPS", "INFERENCE_FPS"
    ],

    "自动开火": [
        "ENABLE_AUTO_FIRE", "AUTO_FIRE_ACCURACY_THRESHOLD",
        "AUTO_FIRE_DISTANCE_THRESHOLD", "AUTO_FIRE_MIN_LOCK_FRAMES",
        "AUTO_FIRE_DEBUG_MODE"
    ],

    "压枪模式": [
        "ENABLE_MANUAL_RECOIL", "ENABLE_RECOIL_CONTROL",
        "MANUAL_RECOIL_TRIGGER_MODE"
    ],

    "压枪触发条件": [
        "RECOIL_REQUIRE_TARGET", "RECOIL_REQUIRE_LOCK",
        "RECOIL_TARGET_TIMEOUT", "RECOIL_MIN_LOCK_FRAMES"
    ],

    "压枪速度配置": [
        "RECOIL_PATTERN", "RECOIL_VERTICAL_SPEED",
        "RECOIL_HORIZONTAL_SPEED", "RECOIL_INCREMENT_Y"
    ],

    "压枪限制": [
        "RECOIL_MAX_SINGLE_MOVE_X", "RECOIL_MAX_SINGLE_MOVE_Y",
        "RECOIL_CUSTOM_PATTERN", "RECOIL_HORIZONTAL_VARIANCE",
        "RECOIL_MAX_SINGLE_MOVE"
    ],

    "脚本系统": [
        "ENABLE_SCRIPT_SYSTEM",
        "SCRIPT_AUTO_RELOAD", "SCRIPT_TIMEOUT_MS",
        "SCRIPT_DEBUG_MODE", "ENABLED_SCRIPTS"
    ]
}


def get_default_config() -> Dict[str, Any]:
    """获取完整默认配置"""
    return {
        # ========== 许可证 ==========
        "LICENSE_KEY": "",

        # ========== 推理后端配置 ==========
        "FORCE_BACKEND": "dml",  # 强制使用的后端: tensorrt/cuda/dml/ncnn_vulkan/ncnn_cpu/None(自动)

        # ONNX Runtime 配置
        "USE_TENSORRT": True,  # 是否启用TensorRT加速

        # ncnn 配置
        "NCNN_PARAM_PATH": None,
        "NCNN_BIN_PATH": None,
        "NCNN_INPUT_NAME": None,
        "NCNN_OUTPUT_NAMES": None,
        "NCNN_USE_FP16": True,

        # 类别名称配置
        "CLASS_NAMES_PATH": None,

        # ========== 图像源配置 ==========
        "IMAGE_SOURCE_TYPE": "local",
        "CROP_SIZE": 320,

        # 网络画面接收
        "FRAME_PORT": 27015,
        "FRAME_WIDTH": 256,
        "FRAME_HEIGHT": 256,
        "FRAME_CHANNELS": 3,

        # ========== 准星检测配置 ==========
        "ENABLE_CROSSHAIR_DETECTION": False,
        "CROSSHAIR_DETECTOR_TYPE": "template",
        "CROSSHAIR_VALORANT_CONFIG": "",
        "CROSSHAIR_TEMPLATE_PATH": "templates/crosshair.png",
        "CROSSHAIR_USE_FALLBACK_CENTER": True,
        "CROSSHAIR_DEBUG_MODE": False,
        "CROSSHAIR_STATS_INTERVAL": 300,
        "CROSSHAIR_SEARCH_BOUNDS": {
            "x_left": -30,
            "x_right": 30,
            "y_up": -150,
            "y_down": 20
        },
        "CROSSHAIR_SMOOTH_FACTOR": 0.3,
        "CROSSHAIR_MAX_LOST_FRAMES": 5,

        # 预览窗口
        "ENABLE_PREVIEW_WINDOW": False,
        "PREVIEW_WINDOW_WIDTH": 800,
        "PREVIEW_WINDOW_HEIGHT": 800,
        "PREVIEW_FRAME_SKIP": 0,
        "PREVIEW_SHOW_BOXES": True,
        "PREVIEW_SHOW_LABELS": True,
        "PREVIEW_SHOW_CONFIDENCE": True,
        "PREVIEW_SHOW_FPS": True,
        "PREVIEW_SHOW_CROSSHAIR": True,
        "PREVIEW_SHOW_AIM_POINT": True,
        "PREVIEW_SHOW_SEARCH_AREA": True,
        "PREVIEW_BOX_THICKNESS": 2,
        "PREVIEW_TEXT_SCALE": 0.5,

        # ========== YOLO 检测 ==========
        "MODEL_PATH": "320.onnx",
        "MODEL_TYPE": "v8",  #
        "CONF_THRESHOLD": 0.60,
        "IOU_THRESHOLD": 0.45,
        "TARGET_CLASS_IDS": [0, 1],
        "TARGET_CLASS_NAMES": ["身体", "头部"],

        # ========== 目标分组 ==========
        "TARGET_GROUP_DISTANCE_THRESHOLD": 100,

        # ========== 目标选择 ==========
        "MIN_TARGET_LOCK_FRAMES": 20,
        "TARGET_SWITCH_DISTANCE_THRESHOLD": 10,
        "TARGET_IDENTITY_DISTANCE": 10,
        "MAX_LOST_FRAMES": 30,
        "TARGET_ID_GRID_SIZE": 20,

        # ========== 头部优先 ==========
        "ENABLE_HEAD_PRIORITY": True,
        "HEAD_CLASS_ID": 1,
        "HEAD_PRIORITY_RANGE": 80,
        "IGNORE_SMALL_TARGET_HEAD": True,
        "SMALL_TARGET_AREA_THRESHOLD": 200,

        # ========== 瞄准点配置 ==========
        "AIM_Y_RATIO": 0.5,
        "AIM_X_OFFSET": 0.5,

        # ========== 卡尔曼滤波 ==========
        "USE_KALMAN_FILTER": True,
        "KALMAN_PROCESS_NOISE": 0.3,
        "KALMAN_MEASUREMENT_NOISE": 1.0,
        "KALMAN_MAX_PREDICT_FRAMES": 3,

        # ========== EMA 平滑（备用）==========
        "AIM_POINT_SMOOTH_ALPHA": 0.25,

        # ========== 预判瞄准 ==========
        "ENABLE_LEAD_TARGET": False,
        "LEAD_FRAMES": 2,

        # ========== PID 控制 ==========
        "PID_KP_X": 0.15,
        "PID_KD_X": 0.05,
        "PID_KI_X": 0.05,
        "PID_KP_Y": 0.15,
        "PID_KD_Y": 0.05,
        "PID_KI_Y": 0.05,
        "MAX_SINGLE_MOVE_PX": 400,
        "PRECISION_DEAD_ZONE": 5,
        "DEFAULT_DELAY_MS_PER_STEP": 1,

        # ========== 鼠标控制模式 ==========
        # Makcu 配置
        "USE_MAKCU": False,
        "MAKCU_PORT": "",
        "MAKCU_AUTO_RECONNECT": True,
        "MAKCU_MIN_SEND_INTERVAL": 0.012,  # 12ms
        "MAKCU_QUEUE_SIZE": 50,

        # ⭐ MTKmbox 配置
        "USE_MTKMBOX": False,
        "MTKMBOX_PORT": "COM6",
        "MTKMBOX_VID": 1046,       # 0x0416
        "MTKMBOX_PID": 20512,      # 0x5020
        "MTKMBOX_MAX_MOVE": 127,
        "SERIAL_MIN_SEND_INTERVAL": 0.012,  # 12ms 串口最小发送间隔

        # 通用配置
        "USE_DRIVER_MODE": False,
        "MOUSE_MODE_AUTO_FALLBACK": True,
        "MAX_MICKEY": 500,

        # ========== 驱动配置 ==========
        "DRIVER_PATH": r"\\.\infestation",
        "MOUSE_REQUEST": 2234776,

        # ========== 按键定义 ==========
        "APP_MOUSE_NO_BUTTON": 0,
        "APP_MOUSE_LEFT_DOWN": 1,
        "APP_MOUSE_LEFT_UP": 2,
        "APP_MOUSE_RIGHT_DOWN": 4,
        "APP_MOUSE_RIGHT_UP": 8,
        "APP_MOUSE_MIDDLE_DOWN": 16,
        "APP_MOUSE_MIDDLE_UP": 32,

        # ========== 按键监控 ==========
        "ENABLE_LEFT_MOUSE_MONITOR": False,
        "ENABLE_RIGHT_MOUSE_MONITOR": True,
        "ENABLE_MOUSE4_MONITOR": False,
        "ENABLE_MOUSE5_MONITOR": False,
        "KEY_MONITOR_INTERVAL_MS": 50,


        # ========== 系统配置 ==========
        "ENABLE_LOGGING": True,
        "LOG_LEVEL": "INFO",
        "DEBUG_MODE": False,
        "MAKCU_DEBUG_MODE": False,
        "MTKMBOX_DEBUG_MODE": False,  # ⭐ 新增
        "CONFIG_MONITOR_INTERVAL_SEC": 5,
        "CAPTURE_FPS": 144,
        "INFERENCE_FPS": 300,

        # ========== 自动开火 ==========
        "ENABLE_AUTO_FIRE": False,
        "AUTO_FIRE_ACCURACY_THRESHOLD": 0.5,
        "AUTO_FIRE_DISTANCE_THRESHOLD": 15.0,
        "AUTO_FIRE_MIN_LOCK_FRAMES": 3,
        "AUTO_FIRE_DEBUG_MODE": False,

        # ========== 压枪模式 ==========
        "ENABLE_MANUAL_RECOIL": False,
        "ENABLE_RECOIL_CONTROL": True,
        "MANUAL_RECOIL_TRIGGER_MODE": "left_only",

        # ========== 压枪触发条件 ==========
        "RECOIL_REQUIRE_TARGET": False,
        "RECOIL_REQUIRE_LOCK": False,
        "RECOIL_TARGET_TIMEOUT": 0.5,
        "RECOIL_MIN_LOCK_FRAMES": 0,

        # ========== 压枪速度配置 ==========
        "RECOIL_PATTERN": "linear",
        "RECOIL_VERTICAL_SPEED": 180.0,
        "RECOIL_HORIZONTAL_SPEED": 0.0,
        "RECOIL_INCREMENT_Y": 0.5,

        # ========== 压枪限制 ==========
        "RECOIL_MAX_SINGLE_MOVE_X": 50.0,
        "RECOIL_MAX_SINGLE_MOVE_Y": 50.0,
        "RECOIL_CUSTOM_PATTERN": [],
        "RECOIL_HORIZONTAL_VARIANCE": 0,
        "RECOIL_MAX_SINGLE_MOVE": 110.0,

        # ========== 脚本系统 ==========
        "ENABLE_SCRIPT_SYSTEM": True,
        "SCRIPT_AUTO_RELOAD": True,
        "SCRIPT_TIMEOUT_MS": 10,
        "SCRIPT_DEBUG_MODE": False,
        "ENABLED_SCRIPTS": ["auto_key_large_target"],

        "HARDWARE_MONITOR_PRIORITY": True,  # 硬件模式优先使用硬件监视
        "FALLBACK_TO_PYNPUT": True,
    }
