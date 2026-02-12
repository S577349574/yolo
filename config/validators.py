"""配置参数验证器"""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .defaults import get_default_config


# ========== 数值范围验证规则 ==========
# 格式: key -> (min_val, max_val, type, default)
VALIDATION_RULES: Dict[str, tuple] = {
    # 预览窗口
    "PREVIEW_BOX_THICKNESS": (1, 5, int, 2),
    "PREVIEW_TEXT_SCALE": (0.3, 1.5, float, 0.5),
    "PREVIEW_FRAME_SKIP": (0, 10, int, 0),

    # 图像源
    "FRAME_PORT": (1024, 65535, int, 27015),
    "FRAME_WIDTH": (64, 1920, int, 256),
    "FRAME_HEIGHT": (64, 1080, int, 256),
    "FRAME_CHANNELS": (3, 4, int, 3),
    "CROP_SIZE": (64, 1280, int, 320),

    # YOLO 检测
    "CONF_THRESHOLD": (0.1, 0.99, float, 0.60),
    "IOU_THRESHOLD": (0.1, 0.99, float, 0.45),

    # 目标分组
    "TARGET_GROUP_DISTANCE_THRESHOLD": (10, 500, int, 100),

    # 目标选择
    "MIN_TARGET_LOCK_FRAMES": (1, 100, int, 10),
    "TARGET_SWITCH_DISTANCE_THRESHOLD": (10, 500, int, 50),
    "TARGET_IDENTITY_DISTANCE": (10, 500, int, 100),
    "MAX_LOST_FRAMES": (1, 300, int, 30),

    # 头部优先
    "HEAD_CLASS_ID": (0, 100, int, 1),
    "HEAD_PRIORITY_RANGE": (0, 500, int, 80),
    "SMALL_TARGET_AREA_THRESHOLD": (10, 1000, int, 40),

    # 瞄准点
    "AIM_Y_RATIO": (0.0, 1.0, float, 0.5),
    "AIM_X_OFFSET": (-100, 100, float, 0.5),

    # 平滑
    "AIM_POINT_SMOOTH_ALPHA": (0.01, 1.0, float, 0.25),

    # 卡尔曼滤波
    "KALMAN_PROCESS_NOISE": (0.01, 10.0, float, 0.1),
    "KALMAN_MEASUREMENT_NOISE": (0.1, 50.0, float, 5.0),
    "KALMAN_MAX_PREDICT_FRAMES": (0, 60, int, 5),

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

    # 鼠标控制（通用）
    "MAX_MICKEY": (100, 2000, int, 500),

    # ⭐ Makcu 配置
    "MAKCU_MIN_SEND_INTERVAL": (0.001, 0.100, float, 0.012),
    "MAKCU_QUEUE_SIZE": (10, 1000, int, 50),

    # ⭐ MTKmbox 配置
    "MTKMBOX_VID": (0x0000, 0xFFFF, int, 0x0416),
    "MTKMBOX_PID": (0x0000, 0xFFFF, int, 0x5020),
    "MTKMBOX_MAX_MOVE": (1, 127, int, 127),
    "SERIAL_MIN_SEND_INTERVAL": (0.001, 0.100, float, 0.012),

    # 系统配置
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

    # 准星检测
    "CROSSHAIR_STATS_INTERVAL": (60, 1800, int, 300),
    "CROSSHAIR_SMOOTH_FACTOR": (0.0, 1.0, float, 0.3),
    "CROSSHAIR_MAX_LOST_FRAMES": (1, 60, int, 5),
}


# ========== 枚举值验证规则 ==========
# 格式: key -> (valid_values, default)
ENUM_RULES: Dict[str, tuple] = {
    "IMAGE_SOURCE_TYPE": (["local", "network"], "local"),
    "FORCE_BACKEND": ([None, "tensorrt", "cuda", "dml", "ncnn_vulkan", "ncnn_cpu", "cpu"], None),
    "LOG_LEVEL": (["DEBUG", "INFO", "WARNING", "ERROR"], "INFO"),
    "RECOIL_PATTERN": (["linear", "exponential", "custom"], "linear"),
    "MANUAL_RECOIL_TRIGGER_MODE": (["left_only", "left_right", "left_button4", "left_button5"], "left_only"),
    "CROSSHAIR_DETECTOR_TYPE": (["color", "template", "cross_shape", "red_dot"], "template"),
}


# ========== 布尔值键列表 ==========
BOOL_KEYS: List[str] = [
    # 预览窗口
    "ENABLE_PREVIEW_WINDOW",
    "PREVIEW_SHOW_BOXES",
    "PREVIEW_SHOW_LABELS",
    "PREVIEW_SHOW_CONFIDENCE",
    "PREVIEW_SHOW_FPS",
    "PREVIEW_SHOW_CROSSHAIR",
    "PREVIEW_SHOW_AIM_POINT",
    "PREVIEW_SHOW_SEARCH_AREA",

    # 鼠标控制
    "USE_MAKCU",
    "MAKCU_AUTO_RECONNECT",
    "USE_MTKMBOX",  # ⭐ 新增
    "USE_DRIVER_MODE",
    "MOUSE_MODE_AUTO_FALLBACK",

    # 头部优先
    "ENABLE_HEAD_PRIORITY",
    "IGNORE_SMALL_TARGET_HEAD",

    # 按键监控
    "MAKCU_USE_HARDWARE_MONITOR",      # Makcu 特定
    "MAKCU_FALLBACK_TO_PYNPUT",        # Makcu 特定
    "MTKMBOX_USE_HARDWARE_MONITOR",    # ⭐ MTKmbox 特定
    "MTKMBOX_FALLBACK_TO_PYNPUT",      # ⭐ MTKmbox 特定

    # 系统配置
    "ENABLE_LOGGING",
    "DEBUG_MODE",
    "MAKCU_DEBUG_MODE",
    "MTKMBOX_DEBUG_MODE",  # ⭐ 新增

    # 功能开关
    "USE_KALMAN_FILTER",
    "ENABLE_LEAD_TARGET",
    "ENABLE_AUTO_FIRE",
    "AUTO_FIRE_DEBUG_MODE",
    "ENABLE_MANUAL_RECOIL",
    "ENABLE_RECOIL_CONTROL",
    "RECOIL_REQUIRE_TARGET",
    "RECOIL_REQUIRE_LOCK",

    # 脚本系统
    "ENABLE_SCRIPT_SYSTEM",
    "SCRIPT_AUTO_RELOAD",
    "SCRIPT_DEBUG_MODE",

    # 推理后端
    "USE_TENSORRT",
    "NCNN_USE_FP16",

    # 准星检测
    "ENABLE_CROSSHAIR_DETECTION",
    "CROSSHAIR_USE_FALLBACK_CENTER",
    "CROSSHAIR_DEBUG_MODE",
]


# ========== 字符串类型键（特殊处理）==========
STRING_KEYS: List[str] = [
    "MAKCU_PORT",     # Makcu 串口（可选字符串）
    "MTKMBOX_PORT",   # ⭐ MTKmbox 串口（必须字符串）
]


# ========== 列表类型键 ==========
LIST_KEYS: List[str] = [
    "TARGET_CLASS_NAMES",
    "RECOIL_CUSTOM_PATTERN",
    "ENABLED_SCRIPTS",
]


# ========== 路径类型键 ==========
PATH_KEYS: List[str] = [
    "MODEL_PATH",
    "NCNN_PARAM_PATH",
    "NCNN_BIN_PATH",
    "CLASS_NAMES_PATH",
    "CROSSHAIR_TEMPLATE_PATH",
]


# ========== 过期配置项（需要清理）==========
DEPRECATED_KEYS: List[str] = [
    "HEAD_PRIORITY_BONUS",
    "DISTANCE_WEIGHT",
    "TARGET_SWITCH_THRESHOLD",
    "CONFIDENCE_HISTORY_SIZE",
    "CONFIDENCE_DROP_THRESHOLD",
    "ATTACK_PROTECTION_TRIGGER_FRAMES",
    "LOCKED_TARGET_BONUS",
    "USE_LZ4",
    "ENABLE_LEFT_MOUSE_MONITOR",
    "ENABLE_RIGHT_MOUSE_MONITOR",
    "ENABLE_MOUSE4_MONITOR",
    "ENABLE_MOUSE5_MONITOR",

]


class ConfigValidator:
    """配置验证器"""

    def __init__(self, app_dir: Path, logger: Optional[Callable[[str], None]] = None):
        """
        初始化验证器

        Args:
            app_dir: 应用程序根目录（用于解析相对路径）
            logger: 日志函数，默认为 print
        """
        self.app_dir = app_dir
        self._log = logger or (lambda msg: print(f"[ConfigValidator] {msg}"))
        self._defaults = get_default_config()

    def validate(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        完整验证流程

        Args:
            config: 待验证的配置字典

        Returns:
            验证并修正后的配置字典
        """
        c = config.copy()

        # 按顺序执行验证
        c = self._clean_deprecated(c)
        c = self._validate_numeric(c)
        c = self._validate_enums(c)
        c = self._validate_booleans(c)
        c = self._validate_strings(c)  # ⭐ 新增
        c = self._validate_lists(c)
        c = self._validate_paths(c)
        c = self._validate_special_fields(c)

        return c

    def _clean_deprecated(self, c: Dict[str, Any]) -> Dict[str, Any]:
        """清理过期配置项"""
        removed = [k for k in DEPRECATED_KEYS if k in c]
        for key in removed:
            del c[key]
        if removed:
            self._log(f"⚠️ 已清理 {len(removed)} 个过期配置项: {', '.join(removed)}")
        return c

    def _validate_numeric(self, c: Dict[str, Any]) -> Dict[str, Any]:
        """验证数值范围"""
        for key, (min_val, max_val, typ, default) in VALIDATION_RULES.items():
            v = c.get(key, default)
            try:
                v = typ(v)
                v = max(min_val, min(max_val, v))
            except (ValueError, TypeError):
                self._log(f"⚠️ 配置项 {key} 值无效，使用默认值: {default}")
                v = default
            c[key] = v
        return c

    def _validate_enums(self, c: Dict[str, Any]) -> Dict[str, Any]:
        """验证枚举值"""
        for key, (valid_values, default) in ENUM_RULES.items():
            if c.get(key) not in valid_values:
                self._log(f"⚠️ 配置项 {key} 值无效，使用默认值: {default}")
                c[key] = default
        return c

    def _validate_booleans(self, c: Dict[str, Any]) -> Dict[str, Any]:
        """验证布尔值"""
        for key in BOOL_KEYS:
            if not isinstance(c.get(key), bool):
                default = self._defaults.get(key, False)
                c[key] = default
        return c

    def _validate_strings(self, c: Dict[str, Any]) -> Dict[str, Any]:
        """验证字符串类型（⭐ 新增方法）"""
        for key in STRING_KEYS:
            val = c.get(key)

            # 特殊处理：MAKCU_PORT 允许为空字符串
            if key == "MAKCU_PORT":
                if val is None or not isinstance(val, str):
                    c[key] = ""
                continue

            # 特殊处理：MTKMBOX_PORT 必须是有效字符串
            if key == "MTKMBOX_PORT":
                if not isinstance(val, str) or not val.strip():
                    default = self._defaults.get(key, "COM6")
                    self._log(f"⚠️ {key} 无效，使用默认值: {default}")
                    c[key] = default
                continue

            # 其他字符串配置
            if val is not None and not isinstance(val, str):
                default = self._defaults.get(key, "")
                c[key] = default

        return c

    def _validate_lists(self, c: Dict[str, Any]) -> Dict[str, Any]:
        """验证列表类型"""
        for key in LIST_KEYS:
            if not isinstance(c.get(key), list):
                c[key] = self._defaults.get(key, [])

        # NCNN_OUTPUT_NAMES 特殊处理（允许 None）
        if "NCNN_OUTPUT_NAMES" in c:
            val = c["NCNN_OUTPUT_NAMES"]
            if val is not None and not isinstance(val, list):
                c["NCNN_OUTPUT_NAMES"] = None

        return c

    def _validate_paths(self, c: Dict[str, Any]) -> Dict[str, Any]:
        """验证路径配置"""
        for key in PATH_KEYS:
            val = c.get(key)
            if val is None:
                continue
            if not isinstance(val, str) or not val.strip():
                continue

            p = Path(val)
            if not p.is_absolute():
                p = (self.app_dir / p).resolve()

            # 检查文件是否存在（仅警告，不修改值）
            if key == "MODEL_PATH" and not p.exists():
                self._log(f"⚠️ 模型文件不存在: {p}")

            c[key] = str(p)

        return c

    def _validate_special_fields(self, c: Dict[str, Any]) -> Dict[str, Any]:
        """验证特殊字段"""

        # TARGET_CLASS_IDS: 必须是整数列表
        if "TARGET_CLASS_IDS" in c:
            try:
                val = c["TARGET_CLASS_IDS"]
                if isinstance(val, list):
                    c["TARGET_CLASS_IDS"] = [int(x) for x in val]
                else:
                    c["TARGET_CLASS_IDS"] = [0, 1]
            except (ValueError, TypeError):
                c["TARGET_CLASS_IDS"] = [0, 1]

        # CROSSHAIR_SEARCH_BOUNDS: 必须是包含特定键的字典
        c = self._validate_crosshair_bounds(c)

        # ⭐ 硬件互斥性检查
        c = self._validate_hardware_exclusivity(c)

        # ==================== 按键-参数组绑定（新方案）校验 ====================

        # ENABLE_KEY_PROFILE_BINDING
        if not isinstance(c.get("ENABLE_KEY_PROFILE_BINDING", True), bool):
            c["ENABLE_KEY_PROFILE_BINDING"] = True

        # KEY_PROFILE_DEFAULT_MODE
        mode = c.get("KEY_PROFILE_DEFAULT_MODE", "hold")
        if mode not in ["hold", "toggle"]:
            c["KEY_PROFILE_DEFAULT_MODE"] = "hold"

        # KEY_PROFILE_BINDINGS
        bindings = c.get("KEY_PROFILE_BINDINGS", {})
        if not isinstance(bindings, dict):
            c["KEY_PROFILE_BINDINGS"] = {}
        else:
            # bindings 的 value 允许 str 或 dict

            # KEY_PROFILE_BINDINGS（不允许简写；必须包含所有键；每个键必须包含 profile/mode/trigger）
            allowed_keys = {"left", "right", "mouse4", "mouse5"}

            # 从 defaults 里拿默认 bindings（如果没有就用通用默认）
            default_mode = c.get("KEY_PROFILE_DEFAULT_MODE", "hold")
            default_bindings = self._defaults.get("KEY_PROFILE_BINDINGS", {})

            def _default_binding_for(key: str) -> Dict[str, Any]:
                dv = default_bindings.get(key)
                if isinstance(dv, dict):
                    # 确保 defaults 里也有完整字段
                    return {
                        "profile": str(dv.get("profile", "default")) if dv.get("profile",
                                                                               "default") is not None else "default",
                        "mode": dv.get("mode", default_mode) if dv.get("mode", default_mode) in ["hold",
                                                                                                 "toggle"] else default_mode,
                        "trigger": dv.get("trigger", True) if isinstance(dv.get("trigger", True), bool) else True,
                    }
                # 通用默认
                return {"profile": "default", "mode": default_mode, "trigger": True}

            bindings = c.get("KEY_PROFILE_BINDINGS", {})
            if not isinstance(bindings, dict):
                bindings = {}

            fixed: Dict[str, Dict[str, Any]] = {}

            # 1) 强制包含所有 allowed_keys
            for k in allowed_keys:
                fixed[k] = _default_binding_for(k)

            # 2) 校验/覆盖用户输入（不接受 str 简写；非 dict 直接忽略）
            for k, v in bindings.items():
                if k not in allowed_keys:
                    continue

                if not isinstance(v, dict):
                    # 不允许简写/其它类型，直接丢弃，保留默认
                    self._log(f"⚠️ KEY_PROFILE_BINDINGS.{k} 必须是 dict，已忽略非法值并使用默认")
                    continue

                # 必须包含所有字段：profile/mode/trigger（缺失则补默认）
                dv = _default_binding_for(k)

                profile = v.get("profile", dv["profile"])
                mode = v.get("mode", dv["mode"])
                trigger = v.get("trigger", dv["trigger"])

                # profile 必须是 str（允许空字符串？这里按“必须是有效字符串”处理：空/非str -> 默认）
                if not isinstance(profile, str) or not profile.strip():
                    profile = dv["profile"]

                # mode 必须 hold/toggle
                if mode not in ["hold", "toggle"]:
                    mode = dv["mode"]

                # trigger 必须 bool
                if not isinstance(trigger, bool):
                    trigger = dv["trigger"]

                fixed[k] = {"profile": profile, "mode": mode, "trigger": trigger}

            c["KEY_PROFILE_BINDINGS"] = fixed

        # KEY_PROFILE_PRIORITY
        if not isinstance(c.get("KEY_PROFILE_PRIORITY"), list):
            c["KEY_PROFILE_PRIORITY"] = ["left","right", "mouse5", "mouse4"]

        # KEY_PROFILE_FALLBACK
        fallback = c.get("KEY_PROFILE_FALLBACK", "default")
        if fallback is not None and not isinstance(fallback, str):
            c["KEY_PROFILE_FALLBACK"] = "default"

        # HOLD_FALLBACK_POLICY
        policy = c.get("HOLD_FALLBACK_POLICY", "previous")
        if policy not in ["previous", "fallback"]:
            c["HOLD_FALLBACK_POLICY"] = "previous"

        return c

    def _validate_crosshair_bounds(self, c: Dict[str, Any]) -> Dict[str, Any]:
        """验证准星搜索区域边界"""
        default_bounds = self._defaults.get("CROSSHAIR_SEARCH_BOUNDS", {
            "x_left": -30,
            "x_right": 30,
            "y_up": -150,
            "y_down": 20
        })

        bounds = c.get("CROSSHAIR_SEARCH_BOUNDS", {})

        if not isinstance(bounds, dict):
            c["CROSSHAIR_SEARCH_BOUNDS"] = default_bounds
            return c

        # 验证每个边界值
        validated_bounds = {}
        for key in ["x_left", "x_right", "y_up", "y_down"]:
            if key not in bounds:
                validated_bounds[key] = default_bounds[key]
            else:
                try:
                    val = int(bounds[key])
                    # 限制范围：-500 到 500
                    validated_bounds[key] = max(-500, min(500, val))
                except (ValueError, TypeError):
                    validated_bounds[key] = default_bounds[key]

        c["CROSSHAIR_SEARCH_BOUNDS"] = validated_bounds
        return c

    def _validate_hardware_exclusivity(self, c: Dict[str, Any]) -> Dict[str, Any]:
        """
        验证硬件互斥性（⭐ 新增方法）

        确保同时只启用一种硬件模式：
        优先级：MTKmbox > Makcu > Driver > WinAPI
        """
        use_mtkmbox = c.get("USE_MTKMBOX", False)
        use_makcu = c.get("USE_MAKCU", False)
        use_driver = c.get("USE_DRIVER_MODE", False)

        # 统计启用的硬件数量
        enabled_count = sum([use_mtkmbox, use_makcu, use_driver])

        if enabled_count > 1:
            self._log("⚠️ 检测到多个硬件模式同时启用，应用优先级规则...")

            # 优先级：MTKmbox > Makcu > Driver
            if use_mtkmbox:
                self._log("  ✅ 保留 MTKmbox 模式")
                c["USE_MAKCU"] = False
                c["USE_DRIVER_MODE"] = False
            elif use_makcu:
                self._log("  ✅ 保留 Makcu 模式")
                c["USE_MTKMBOX"] = False
                c["USE_DRIVER_MODE"] = False
            elif use_driver:
                self._log("  ✅ 保留 Driver 模式")
                c["USE_MTKMBOX"] = False
                c["USE_MAKCU"] = False

        return c


def validate_config(config: Dict[str, Any], app_dir: Path,
                    logger: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """
    便捷函数:验证配置

    Args:
        config: 待验证的配置字典
        app_dir: 应用程序根目录
        logger: 日志函数

    Returns:
        验证并修正后的配置字典
    """
    validator = ConfigValidator(app_dir, logger)
    return validator.validate(config)
