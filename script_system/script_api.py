"""
Lua 脚本 API 实现 - 优化版（使用共享状态）
"""

import math
import time

import utils
from config_manager import get_config, set_config, save_config
from .rate_limiter import RateLimiter
from .script_capture import ScriptScreenCapture
from .shared_game_state import get_game_state


class ScriptAPI:
    def __init__(
        self,
        mouse_controller,
        auto_fire_controller,
        target_selector,
        yolo_detector,
        screen_capture,
        key_monitor, 
        command_sender,
        verbose=False
    ):
        self.command_sender = command_sender
        self.verbose = verbose
        self.mouse = mouse_controller
        self.auto_fire = auto_fire_controller
        self.target_selector = target_selector
        self.yolo = yolo_detector
        self.capture = screen_capture
        self.key_monitor = key_monitor
        self.game_state = get_game_state()

        self._app_state_getter = None
        self.rate_limiter = RateLimiter()

        # 启动时间
        self.start_time = time.time()
        self.last_frame_time = time.time()
        try:
            self.script_capture = ScriptScreenCapture(save_dir="collected_images")
        except Exception as e:
            utils.log(f"[ScriptAPI] 脚本截图器初始化失败: {e}")
            self.script_capture = None

        self.script_storage = {}  # 用于存储跨帧数据
        self.script_timers = {}   # 用于存储定时器

    def bind_app_state(self, app_state):
        """绑定 app_state"""
        self._app_state_getter = lambda: app_state

    def create_api_table(self, lua_runtime):
        """创建完整的 API 表"""
        api = lua_runtime.table()

        # 注册各个子模块
        api.state = self._create_state_api(lua_runtime)
        api.config = self._create_config_api(lua_runtime)
        api.mouse = self._create_mouse_api(lua_runtime)
        api.input = self._create_input_api(lua_runtime)
        api.recoil = self._create_recoil_api(lua_runtime)
        api.system = self._create_system_api(lua_runtime)
        api.log = self._create_log_api(lua_runtime)
        api.utils = self._create_utils_api(lua_runtime)

        api.network = self._create_network_api(lua_runtime)

        api.storage = self._create_storage_api(lua_runtime)
        api.timer = self._create_timer_api(lua_runtime)
        api.capture = self._create_capture_api(lua_runtime)
        # 辅助函数
        api["getLength"] = lambda obj: len(obj) if hasattr(obj, '__len__') else 0
        api["len"] = api["getLength"]

        return api


    def _create_state_api(self, lua):
        """创建游戏状态 API（零拷贝访问）"""
        state = lua.table()

        # ========== 目标信息 ==========
        def get_targets():
            """获取所有目标（返回 Lua table 数组）"""
            targets = []
            for t in self.game_state.targets:
                target = lua.table()
                target.x = int(t.x)
                target.y = int(t.y)
                target.width = int(t.width)
                target.height = int(t.height)
                target.confidence = float(t.confidence)
                target.class_id = int(t.class_id)
                target.class_name = str(t.class_name)
                target.distance = float(t.distance)
                target.aim_x = int(t.aim_x)
                target.aim_y = int(t.aim_y)
                target.is_locked = bool(t.is_locked)
                target.lock_frames = int(t.lock_frames)
                targets.append(target)
            return targets

        def get_best_target():
            """获取最佳目标"""
            if self.game_state.best_target:
                t = self.game_state.best_target
                target = lua.table()
                target.x = int(t.x)
                target.y = int(t.y)
                target.is_locked = bool(t.is_locked)
                target.lock_frames = int(t.lock_frames)
                return target
            return None

        def get_target_count():
            """获取目标数量"""
            return self.game_state.get_target_count()

        # ========== 状态标志 ==========
        def is_aiming():
            """是否正在瞄准"""
            return self.game_state.is_aiming

        def is_firing():
            """是否正在开火"""
            return self.game_state.is_firing

        def is_locked():
            """是否锁定目标"""
            return self.game_state.is_locked

        def get_lock_frames():
            """获取锁定帧数"""
            return self.game_state.lock_frames

        # ========== 性能数据 ==========
        def get_fps():
            """获取当前 FPS"""
            return self.game_state.current_fps

        def get_delta_time():
            """获取帧间隔（秒）"""
            return self.game_state.delta_time

        def get_frame_count():
            """获取总帧数"""
            return self.game_state.frame_count

        # ========== 压枪数据 ==========
        def get_recoil_stats():
            """获取压枪统计"""
            stats = lua.table()
            stats.active = self.game_state.recoil_active
            stats.offset_x = self.game_state.total_offset_x
            stats.offset_y = self.game_state.total_offset_y
            stats.shot_count = self.game_state.shot_count
            return stats

        # ========== 屏幕信息 ==========
        def get_screen_size():
            """获取屏幕尺寸"""
            return (self.game_state.screen_width, self.game_state.screen_height)

        def get_screen_center():
            """获取屏幕中心"""
            return (self.game_state.center_x, self.game_state.center_y)

        # ========== 完整状态快照 ==========
        def get_full_state():
            """获取完整游戏状态（一次性读取所有数据）"""
            full = lua.table()
            full.target_count = get_target_count()
            full.fps = get_fps()
            full.delta_time = get_delta_time()
            full.frame_count = get_frame_count()
            full.is_aiming = is_aiming()
            full.is_firing = is_firing()
            full.is_locked = is_locked()
            full.lock_frames = get_lock_frames()
            return full

        # 注册函数
        state.get_targets = get_targets
        state.get_best_target = get_best_target
        state.get_target_count = get_target_count
        state.is_aiming = is_aiming
        state.is_firing = is_firing
        state.is_locked = is_locked
        state.get_lock_frames = get_lock_frames
        state.get_fps = get_fps
        state.get_delta_time = get_delta_time
        state.get_frame_count = get_frame_count
        state.get_recoil_stats = get_recoil_stats
        state.get_screen_size = get_screen_size
        state.get_screen_center = get_screen_center
        state.get_full_state = get_full_state

        return state

    # ==================== 配置管理 API ====================

    def _create_config_api(self, lua):
        """创建 config API"""
        config_api = lua.table()

        def config_get(key, default=None):
            return get_config(key, default)

        def config_set(key, value):
            if not self.rate_limiter.check("config_write"):
                return False
            try:
                set_config(key, value)
                return True
            except Exception as e:
                utils.log(f"[ScriptAPI] 配置写入失败: {key} = {value}, 错误: {e}")
                return False

        def config_set_batch(lua_table):
            if not self.rate_limiter.check("config_batch"):
                return False
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

        def move_relative(dx, dy):
            if not self.rate_limiter.check("mouse_move"):
                return False
            return self.mouse.move_relative(int(dx), int(dy))

        def move_to(x, y, delay_ms=None):
            if not self.rate_limiter.check("mouse_move"):
                return False
            return self.mouse.move_to_target(int(x), int(y), delay_ms)

        def move_instant(x, y):
            if not self.rate_limiter.check("mouse_move"):
                return False
            if hasattr(self.mouse, 'move_to_target_instant'):
                return self.mouse.move_to_target_instant(int(x), int(y))
            return False

        def click(button="left", delay_ms=50):
            if not self.rate_limiter.check("mouse_click"):
                return False
            button_map = {
                "left": self.mouse.BUTTON_LEFT_DOWN,
                "right": self.mouse.BUTTON_RIGHT_DOWN,
                "middle": self.mouse.BUTTON_MIDDLE_DOWN,
                "mouse4": self.mouse.BUTTON_4_DOWN,
                "mouse5": self.mouse.BUTTON_5_DOWN,
                # 别名支持
                "side4": self.mouse.BUTTON_4_DOWN,
                "side5": self.mouse.BUTTON_5_DOWN,
            }
            button_flag = button_map.get(button, self.mouse.BUTTON_LEFT_DOWN)
            return self.mouse.click(button_flag, int(delay_ms))

        def mouse_down(button="left"):
            button_map = {
                "left": self.mouse.BUTTON_LEFT_DOWN,
                "right": self.mouse.BUTTON_RIGHT_DOWN,
                "middle": self.mouse.BUTTON_MIDDLE_DOWN,
                "mouse4": self.mouse.BUTTON_4_DOWN,
                "mouse5": self.mouse.BUTTON_5_DOWN,
            }
            button_flag = button_map.get(button, self.mouse.BUTTON_LEFT_DOWN)
            return self.mouse.mouse_down(button_flag)

        def mouse_up(button="left"):
            button_map = {
                "left": self.mouse.BUTTON_LEFT_UP,
                "right": self.mouse.BUTTON_RIGHT_UP,
                "middle": self.mouse.BUTTON_MIDDLE_UP,
                "mouse4": self.mouse.BUTTON_4_UP,
                "mouse5": self.mouse.BUTTON_5_UP,
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
        """创建 input API（重构版 - 使用统一接口）"""
        input_api = lua.table()

        def is_key_down(key):
            """检查按键是否按下（使用统一接口）"""
            if not self.key_monitor:
                return False
            return self.key_monitor.is_key_pressed(str(key))

        def is_mouse_down(button="left"):
            """检查鼠标按键是否按下（使用统一接口）"""
            if not self.key_monitor:
                return False
            button_name_map = {
                "left": "left",
                "right": "right",
                "middle": "middle",
                "mouse4": "mouse4",
                "mouse5": "mouse5",
            }

            mapped_button = button_name_map.get(button.lower(), "left")
            return self.key_monitor.is_key_pressed(mapped_button)

        def get_all_button_states():
            """获取所有按键状态（使用统一接口）"""
            if not self.key_monitor:
                return {}
            return self.key_monitor.get_button_states()

        def is_aim_active():
            state = self._app_state_getter()
            return state.is_mouse_active() if state else False

        def is_left_pressed():
            state = self._app_state_getter()
            return state.is_left_pressed() if state else False

        def is_right_pressed():
            state = self._app_state_getter()
            return state.is_right_pressed() if state else False

        # 注册函数
        input_api.is_key_down = is_key_down
        input_api.is_mouse_down = is_mouse_down
        input_api.get_all_states = get_all_button_states
        input_api.is_aim_active = is_aim_active
        input_api.is_left_pressed = is_left_pressed
        input_api.is_right_pressed = is_right_pressed


        return input_api

    # ==================== 压枪控制 API ====================

    def _create_recoil_api(self, lua):
        """创建 recoil API"""
        recoil_api = lua.table()

        recoil_api.is_active = lambda: self.game_state.recoil_active
        recoil_api.get_stats = lambda: self._create_state_api(lua).get_recoil_stats()
        recoil_api.reset = lambda: self.auto_fire._reset_recoil_state()

        return recoil_api

    # ==================== 系统信息 API ====================

    def _create_system_api(self, lua):
        """创建 system API"""
        system_api = lua.table()

        system_api.time = lambda: time.time()
        system_api.delta_time = lambda: self.game_state.delta_time
        system_api.uptime = lambda: time.time() - self.start_time
        system_api.get_screen_size = lambda: (
            self.game_state.screen_width,
            self.game_state.screen_height
        )
        system_api.get_screen_center = lambda: (
            self.game_state.center_x,
            self.game_state.center_y
        )
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

        log_api.__call = log_output
        log_api.info = lambda *args: log_output("ℹ️", *args)
        log_api.warning = lambda *args: log_output("⚠️", *args)
        log_api.error = lambda *args: log_output("❌", *args)
        log_api.debug = lambda *args: (
            log_output("🔍", *args) if get_config("SCRIPT_DEBUG_MODE", False) else None
        )

        return log_api

    def _create_storage_api(self, lua):
        """创建全局存储 API（跨帧数据持久化）"""
        storage_api = lua.table()

        def storage_set(key, value):
            """设置全局变量"""
            self.script_storage[str(key)] = value
            return True

        def storage_get(key, default=None):
            """获取全局变量"""
            return self.script_storage.get(str(key), default)

        def storage_has(key):
            """检查变量是否存在"""
            return str(key) in self.script_storage

        def storage_delete(key):
            """删除全局变量"""
            if str(key) in self.script_storage:
                del self.script_storage[str(key)]
                return True
            return False

        def storage_clear():
            """清空所有变量"""
            self.script_storage.clear()
            return True

        def storage_increment(key, delta=1, default=0):
            """增加计数器（原子操作）"""
            current = self.script_storage.get(str(key), default)
            new_value = current + delta
            self.script_storage[str(key)] = new_value
            return new_value

        def storage_get_all():
            """获取所有变量（调试用）"""
            result = lua.table()
            for k, v in self.script_storage.items():
                result[k] = v
            return result

        # 注册函数
        storage_api.set = storage_set
        storage_api.get = storage_get
        storage_api.has = storage_has
        storage_api.delete = storage_delete
        storage_api.clear = storage_clear
        storage_api.increment = storage_increment
        storage_api.get_all = storage_get_all

        return storage_api

    # ====================网络发包 API ====================

    def _create_network_api(self, lua):
        network_api = lua.table()

        def send_packet(lua_table):
            """
            Lua 调用示例:
            api.network.send_packet({ action = "aim", x = 10, y = 20 })
            api.network.send_packet({ action = "capture", label = "boss" })
            """
            if not self.command_sender:
                return False

            # 每秒限制发包数量，防止 Lua 脚本死循环打死网络
            if not self.rate_limiter.check("network_custom_send"):
                return False

            try:
                # 将 Lua table 转换为 Python dict
                py_dict = {}
                for key in lua_table:
                    py_dict[key] = lua_table[key]
                return self.command_sender.send_custom(py_dict)
            except Exception as e:
                utils.log(f"[ScriptAPI] Lua 发包转换失败: {e}")
                return False

        network_api.send_packet = send_packet
        return network_api

    # script_api.py (在 ScriptAPI 类中添加)
    def _create_capture_api(self, lua):
        """创建 Lua 截图 API"""
        capture_api = lua.table()

        def save_screenshot(category, label=None, width=640, height=640):
            """保存截图"""
            # ⭐ 检查速率限制
            if not self.rate_limiter.check("local_capture"):
                return False

            # ⭐ 检查截图器是否可用
            if self.script_capture is None:
                utils.log("[Capture] 截图器未初始化")
                return False

            # ⭐ 调用独立截图器
            return self.script_capture.save_screenshot(
                category=category,
                label=label,
                width=int(width),
                height=int(height)
            )

        def get_screen_info():
            """获取屏幕信息"""
            info = lua.table()
            if self.script_capture:
                screen_info = self.script_capture.get_screen_info()
                info.width = screen_info['width']
                info.height = screen_info['height']
                info.capture_count = screen_info['capture_count']
            else:
                info.width = 0
                info.height = 0
                info.capture_count = 0
            return info

        # 注册函数
        capture_api.save = save_screenshot
        capture_api.get_info = get_screen_info

        return capture_api

    def cleanup(self):
        """清理资源"""
        if self.script_capture:
            self.script_capture.cleanup()
    def _create_timer_api(self, lua):
        """创建定时器 API（用于冷却时间管理）"""
        timer_api = lua.table()

        def timer_start(name, duration_sec):
            """启动定时器（duration_sec 秒后过期）"""
            self.script_timers[str(name)] = time.time() + duration_sec
            return True

        def timer_is_ready(name):
            """检查定时器是否已就绪（冷却结束）"""
            if str(name) not in self.script_timers:
                return True  # 未设置的定时器默认就绪
            return time.time() >= self.script_timers[str(name)]

        def timer_remaining(name):
            """获取定时器剩余时间（秒）"""
            if str(name) not in self.script_timers:
                return 0
            remaining = self.script_timers[str(name)] - time.time()
            return max(0, remaining)

        def timer_reset(name):
            """重置定时器"""
            if str(name) in self.script_timers:
                del self.script_timers[str(name)]
                return True
            return False

        def timer_clear_all():
            """清空所有定时器"""
            self.script_timers.clear()
            return True

        # 注册函数
        timer_api.start = timer_start
        timer_api.is_ready = timer_is_ready
        timer_api.remaining = timer_remaining
        timer_api.reset = timer_reset
        timer_api.clear_all = timer_clear_all

        return timer_api
    # ==================== 工具函数 API ====================
    @staticmethod
    def _create_utils_api(lua):
        """创建 utils API"""
        utils_api = lua.table()

        utils_api.distance = lambda x1, y1, x2, y2: math.sqrt(
            (x2 - x1) ** 2 + (y2 - y1) ** 2
        )
        utils_api.to_radians = lambda degrees: math.radians(degrees)
        utils_api.to_degrees = lambda radians: math.degrees(radians)
        utils_api.clamp = lambda value, min_val, max_val: max(min_val, min(max_val, value))
        utils_api.lerp = lambda a, b, t: a + (b - a) * t

        return utils_api
