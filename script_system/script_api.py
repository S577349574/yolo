"""
Lua 脚本 API 实现 - 暴露给脚本的所有接口
"""

import math
import time

import win32api

import utils
from config_manager import get_config, set_config, save_config
from .rate_limiter import RateLimiter


class ScriptAPI:
    """脚本 API 管理器"""

    def __init__(
            self,
            mouse_controller,
            auto_fire_controller,
            target_selector,
            yolo_detector,
            screen_capture
    ):
        """
        初始化 API

        Args:
            mouse_controller: 鼠标控制器实例
            auto_fire_controller: 自动开火控制器实例
            target_selector: 目标选择器实例
            yolo_detector: YOLO检测器实例
            screen_capture: 屏幕捕获实例
        """
        self.mouse = mouse_controller
        self.auto_fire = auto_fire_controller
        self.target_selector = target_selector
        self.yolo = yolo_detector
        self.capture = screen_capture

        # 速率限制器
        self.rate_limiter = RateLimiter()

        # 屏幕信息缓存
        self.screen_width = win32api.GetSystemMetrics(0)
        self.screen_height = win32api.GetSystemMetrics(1)
        self.center_x = self.screen_width // 2
        self.center_y = self.screen_height // 2

        # 启动时间
        self.start_time = time.time()

        # 上一帧时间（用于计算 delta_time）
        self.last_frame_time = time.time()

        utils.log("[ScriptAPI] API 管理器已初始化")

    def create_api_table(self, lua_runtime):
        """
        创建完整的 API 表

        Args:
            lua_runtime: Lua 运行时实例

        Returns:
            Lua table: API 表对象
        """
        api = lua_runtime.table()

        # 注册各个子模块
        api.target = self._create_target_api(lua_runtime)
        api.config = self._create_config_api(lua_runtime)
        api.mouse = self._create_mouse_api(lua_runtime)
        api.input = self._create_input_api(lua_runtime)
        api.recoil = self._create_recoil_api(lua_runtime)
        api.system = self._create_system_api(lua_runtime)
        api.log = self._create_log_api(lua_runtime)
        api.utils = self._create_utils_api(lua_runtime)

        def get_length(obj):
            """获取 Python 对象的长度"""
            try:
                return len(obj)
            except:
                return 0

        api["getLength"] = get_length

        # 或者更通用的名称
        api["len"] = get_length
        utils.log("[ScriptAPI] ✅ API 表已创建")
        return api

    # ==================== 目标信息 API ====================

    """
    优化后的目标信息 API - 使用 Python 对象代理
    """

    def _create_target_api(self, lua):
        """创建 target API（优化版本）"""
        target = lua.table()

        # ==================== 方案 1：直接返回 Python 对象 ====================
        def get_all():
            """
            返回所有目标（零拷贝）

            Returns:
                Python list: 目标列表（Lua 可直接访问）
            """
            if not hasattr(self.target_selector, 'last_targets'):
                return []

            # 直接返回 Python 列表，无需转换
            return self.target_selector.last_targets

        def get_locked():
            """
            返回锁定目标（零拷贝）

            Returns:
                Python object or None: 当前锁定的目标
            """
            if not hasattr(self.target_selector, 'current_target'):
                return None

            # 直接返回 Python 对象
            return self.target_selector.current_target

        # ==================== 辅助函数（Lua 友好） ====================

        def to_lua_table(python_target):
            """
            将 Python 目标对象转换为 Lua table（按需转换）

            Args:
                python_target: Python 目标对象

            Returns:
                Lua table: 转换后的表
            """
            if python_target is None:
                return None

            lua_target = lua.table()
            lua_target.x = int(python_target.x)
            lua_target.y = int(python_target.y)
            lua_target.width = int(python_target.width)
            lua_target.height = int(python_target.height)
            lua_target.class_id = int(python_target.class_id)
            lua_target.class_name = str(python_target.class_name)
            lua_target.confidence = float(python_target.confidence)
            lua_target.locked = bool(python_target.is_locked)
            lua_target.lock_frames = int(python_target.lock_frames)
            lua_target.distance = float(python_target.distance_to_crosshair)
            lua_target.aim_x = int(python_target.aim_x)
            lua_target.aim_y = int(python_target.aim_y)

            return lua_target

        def to_lua_array(python_targets):
            """
            批量转换为 Lua table 数组（按需）

            Args:
                python_targets: Python 列表

            Returns:
                Lua table: 数组表
            """
            lua_array = lua.table()
            for i, t in enumerate(python_targets, start=1):
                lua_array[i] = to_lua_table(t)
            return lua_array

        # ==================== 注册函数 ====================

        target.get_all = get_all
        target.get_locked = get_locked
        target.to_lua_table = to_lua_table
        target.to_lua_array = to_lua_array

        # 保留其他函数
        target.is_locked = lambda: bool(
            hasattr(self.target_selector, 'current_target') and
            self.target_selector.current_target is not None
        )
        target.get_lock_frames = lambda: int(
            self.target_selector.current_target.lock_frames
            if hasattr(self.target_selector, 'current_target') and
               self.target_selector.current_target
            else 0
        )
        target.get_distance = lambda: float(
            self.target_selector.current_target.distance_to_crosshair
            if hasattr(self.target_selector, 'current_target') and
               self.target_selector.current_target
            else float('inf')
        )
        target.get_count = lambda: int(
            len(self.target_selector.last_targets)
            if hasattr(self.target_selector, 'last_targets')
            else 0
        )
        target.has_class = lambda class_id: any(
            t.class_id == class_id
            for t in getattr(self.target_selector, 'last_targets', [])
        )

        return target

    # ==================== 配置管理 API ====================

    def _create_config_api(self, lua):
        """创建 config API"""
        config_api = lua.table()

        # 读取配置
        def config_get(key, default=None):
            return get_config(key, default)

        # 写入配置（带速率限制）
        def config_set(key, value):
            if not self.rate_limiter.check("config_write"):
                return False

            try:
                set_config(key, value)
                return True
            except Exception as e:
                utils.log(f"[ScriptAPI] 配置写入失败: {key} = {value}, 错误: {e}")
                return False

        # 批量设置
        def config_set_batch(lua_table):
            if not self.rate_limiter.check("config_batch"):
                return False

            # 转换 Lua table 为 Python dict
            config_dict = {}
            for key in lua_table:
                config_dict[key] = lua_table[key]

            try:
                for key, value in config_dict.items():
                    set_config(key, value)
                return True
            except Exception as e:
                utils.log(f"[ScriptAPI] 批量配置写入失败: {e}")
                return False

        config_api.get = config_get
        config_api.set = config_set
        config_api.set_batch = config_set_batch
        config_api.save = lambda: save_config()
        config_api.has = lambda key: get_config(key) is not None

        return config_api

    # ==================== 鼠标控制 API ====================

    def _create_mouse_api(self, lua):
        """创建 mouse API"""
        mouse_api = lua.table()

        # 相对移动
        def move_relative(dx, dy):
            if not self.rate_limiter.check("mouse_move"):
                return False
            return self.mouse.move_relative(int(dx), int(dy))

        # 移动到目标
        def move_to(x, y, delay_ms=None):
            if not self.rate_limiter.check("mouse_move"):
                return False
            return self.mouse.move_to_target(int(x), int(y), delay_ms)

        # 瞬移
        def move_instant(x, y):
            if not self.rate_limiter.check("mouse_move"):
                return False
            if hasattr(self.mouse, 'move_to_target_instant'):
                return self.mouse.move_to_target_instant(int(x), int(y))
            return False

        # 点击
        def click(button="left", delay_ms=50):
            if not self.rate_limiter.check("mouse_click"):
                return False

            button_map = {
                "left": self.mouse.BUTTON_LEFT_DOWN,
                "right": self.mouse.BUTTON_RIGHT_DOWN,
                "middle": self.mouse.BUTTON_MIDDLE_DOWN
            }

            button_flag = button_map.get(button, self.mouse.BUTTON_LEFT_DOWN)
            return self.mouse.click(button_flag, int(delay_ms))

        # 按下/释放
        def mouse_down(button="left"):
            button_map = {
                "left": self.mouse.BUTTON_LEFT_DOWN,
                "right": self.mouse.BUTTON_RIGHT_DOWN,
                "middle": self.mouse.BUTTON_MIDDLE_DOWN
            }
            button_flag = button_map.get(button, self.mouse.BUTTON_LEFT_DOWN)
            return self.mouse.mouse_down(button_flag)

        def mouse_up(button="left"):
            button_map = {
                "left": self.mouse.BUTTON_LEFT_UP,
                "right": self.mouse.BUTTON_RIGHT_UP,
                "middle": self.mouse.BUTTON_MIDDLE_UP
            }
            button_flag = button_map.get(button, self.mouse.BUTTON_LEFT_UP)
            return self.mouse.mouse_up(button_flag)

        mouse_api.move_relative = move_relative
        mouse_api.move_to = move_to
        mouse_api.move_instant = move_instant
        mouse_api.click = click
        mouse_api.down = mouse_down
        mouse_api.up = mouse_up
        mouse_api.get_mode = lambda: self.mouse.get_mode()
        mouse_api.is_ready = lambda: self.mouse.is_ready()
        mouse_api.reset_pid = lambda: self.mouse.reset_pid()

        return mouse_api

    # ==================== 输入监听 API ====================

    def _create_input_api(self, lua):
        """创建 input API"""
        input_api = lua.table()
        KEY_MAP = {
            "shift": 0x10, "ctrl": 0x11, "alt": 0x12,
            "space": 0x20, "enter": 0x0D, "esc": 0x1B, "tab": 0x09,
            "w": 0x57, "a": 0x41, "s": 0x53, "d": 0x44,
            "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
            "f1": 0x70, "f2": 0x71  # 可按需扩充
        }
        def _get_vk(key):
            """获取虚拟键码"""
            if isinstance(key, int): return key
            return KEY_MAP.get(str(key).lower(), 0)
        # 鼠标按钮状态
        def is_mouse_down(button="left"):
            button_map = {
                "left": 0x01,
                "right": 0x02,
                "middle": 0x04
            }
            vk_code = button_map.get(button, 0x01)
            return win32api.GetKeyState(vk_code) < 0

        # 键盘按键状态
        def is_key_down(key):
            # 支持虚拟键码或名称
            if isinstance(key, str):
                key_map = {
                    "ctrl": 0x11,
                    "shift": 0x10,
                    "alt": 0x12,
                    "space": 0x20,
                    "enter": 0x0D,
                    "esc": 0x1B,
                    "tab": 0x09
                }
                vk_code = key_map.get(key.lower(), 0)
                if vk_code == 0:
                    return False
            else:
                vk_code = int(key)

            return win32api.GetKeyState(vk_code) < 0
        def key_down(key):
            vk = _get_vk(key)
            if vk and self.rate_limiter.check("input_key"):
                # 0 = KeyDown
                win32api.keybd_event(vk, 0, 0, 0)
                return True
            return False

        def key_up(key):
            vk = _get_vk(key)
            if vk and self.rate_limiter.check("input_key"):
                # 2 = KeyUp (KEYEVENTF_KEYUP)
                win32api.keybd_event(vk, 0, 2, 0)
                return True
            return False
        def key_press(key, delay_ms=50):
            if key_down(key):
                # 注意：由于这是阻塞的 sleep，建议在 Lua 协程或非阻塞逻辑中使用
                # 这里简单实现，可能会轻微卡顿主线程
                time.sleep(delay_ms / 1000.0)
                key_up(key)
                return True
            return False


        input_api.is_mouse_down = is_mouse_down
        input_api.is_key_down = is_key_down
        input_api.key_down = key_down
        input_api.key_up = key_up
        input_api.key_press = key_press

        return input_api

    # ==================== 压枪控制 API ====================

    def _create_recoil_api(self, lua):
        """创建 recoil API"""
        recoil_api = lua.table()

        recoil_api.is_active = lambda: self.auto_fire.is_recoil_active()

        def get_stats():
            stats = lua.table()
            stats.total_offset_x = float(self.auto_fire.total_offset_x)
            stats.total_offset_y = float(self.auto_fire.total_offset_y)
            stats.shot_count = int(self.auto_fire.shot_count)
            stats.fire_duration = float(
                time.time() - self.auto_fire.fire_start_time
                if self.auto_fire.is_firing
                else 0
            )
            return stats

        recoil_api.get_stats = get_stats
        recoil_api.reset = lambda: self.auto_fire._reset_recoil_state()

        return recoil_api

    # ==================== 系统信息 API ====================

    def _create_system_api(self, lua):
        """创建 system API"""
        system_api = lua.table()

        # 时间相关
        system_api.time = lambda: time.time()

        def delta_time():
            current_time = time.time()
            delta = current_time - self.last_frame_time
            self.last_frame_time = current_time
            return delta

        system_api.delta_time = delta_time
        system_api.uptime = lambda: time.time() - self.start_time

        # 屏幕信息（缓存）
        system_api.get_screen_size = lambda: (self.screen_width, self.screen_height)
        system_api.get_screen_center = lambda: (self.center_x, self.center_y)

        # 性能统计
        system_api.get_capture_fps = lambda: float(
            self.capture.fps if hasattr(self.capture, 'fps') else 0
        )
        system_api.get_inference_fps = lambda: float(
            self.yolo.fps if hasattr(self.yolo, 'fps') else 0
        )

        return system_api

    # ==================== 日志输出 API ====================

    def _create_log_api(self, lua):
        """创建 log API"""
        log_api = lua.table()

        def log_output(*args):
            if not self.rate_limiter.check("log_output"):
                return
            message = " ".join(str(arg) for arg in args)
            utils.log(f"[Script] {message}")

        log_api.__call = log_output  # 支持 api.log(...) 调用
        log_api.info = lambda *args: log_output("ℹ️", *args)
        log_api.warning = lambda *args: log_output("⚠️", *args)
        log_api.error = lambda *args: log_output("❌", *args)
        log_api.debug = lambda *args: (
            log_output("🔍", *args) if get_config("SCRIPT_DEBUG_MODE", False) else None
        )

        return log_api

    # ==================== 工具函数 API ====================

    def _create_utils_api(self, lua):
        """创建 utils API"""
        utils_api = lua.table()

        # 数学工具
        utils_api.distance = lambda x1, y1, x2, y2: math.sqrt(
            (x2 - x1) ** 2 + (y2 - y1) ** 2
        )
        utils_api.to_radians = lambda degrees: math.radians(degrees)
        utils_api.to_degrees = lambda radians: math.degrees(radians)
        utils_api.clamp = lambda value, min_val, max_val: max(min_val, min(max_val, value))
        utils_api.lerp = lambda a, b, t: a + (b - a) * t

        return utils_api
