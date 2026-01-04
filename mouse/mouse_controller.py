# mouse_controller.py (完整修复版 - 支持动态准星位置)

"""
鼠标控制器基类 - 包含所有公共逻辑（支持配置热重载 + 动态准星）
"""

import math
import queue as thread_queue
import time
from abc import ABC, abstractmethod
from threading import Thread, Event as ThreadEvent, Lock

import win32api

import utils
from config_manager import get_config, on_config_change
from pid_controller import PIDController


class MouseControllerBase(ABC):
    """鼠标控制器抽象基类（支持动态准星位置）"""

    # 统一的按钮标志常量
    BUTTON_NONE = 0
    BUTTON_LEFT_DOWN = 1
    BUTTON_LEFT_UP = 2
    BUTTON_RIGHT_DOWN = 4
    BUTTON_RIGHT_UP = 8
    BUTTON_MIDDLE_DOWN = 16
    BUTTON_MIDDLE_UP = 32

    BUTTON_4_DOWN = 7
    BUTTON_4_UP = 8
    BUTTON_5_DOWN = 9
    BUTTON_5_UP = 10

    def __init__(self):
        """初始化公共组件"""
        self.move_queue = thread_queue.Queue(maxsize=1)
        self.mouse_thread = None
        self.stop_event = ThreadEvent()
        self._is_initialized = False

        # 屏幕信息
        self.screen_width = win32api.GetSystemMetrics(0)
        self.screen_height = win32api.GetSystemMetrics(1)

        # ⭐ 默认准星位置（屏幕中心）
        self._crosshair_x = self.screen_width // 2
        self._crosshair_y = self.screen_height // 2
        self._crosshair_lock = Lock()  # 线程安全锁

        # 从配置加载参数
        self._load_config()

        # 注册配置热重载回调
        self._register_config_callbacks()

        # 初始化 PID 控制器
        self.pid = PIDController()

        # 按钮映射
        self.button_up_map = {
            self.BUTTON_LEFT_DOWN: self.BUTTON_LEFT_UP,
            self.BUTTON_RIGHT_DOWN: self.BUTTON_RIGHT_UP,
            self.BUTTON_MIDDLE_DOWN: self.BUTTON_MIDDLE_UP,
            # ⭐ 新增侧键映射
            self.BUTTON_4_DOWN: self.BUTTON_4_UP,
            self.BUTTON_5_DOWN: self.BUTTON_5_UP,
        }

        # 统计信息
        self.move_count = 0
        self.overshoot_count = 0
        self.total_error = 0.0

        if self.debug_mode:
            utils.log(f"[{self.get_mode()}] 屏幕: {self.screen_width}x{self.screen_height}")
            utils.log(f"[{self.get_mode()}] 默认准星: ({self._crosshair_x}, {self._crosshair_y})")
            utils.log(f"[{self.get_mode()}] 死区: {math.sqrt(self.dead_zone_sq):.1f}px")
            utils.log(f"[{self.get_mode()}] 最大步进: {self.max_step}px")

    def _load_config(self):
        """加载配置参数"""
        # 死区配置
        dead_zone = get_config("PRECISION_DEAD_ZONE", 2)
        self.dead_zone_sq = dead_zone * dead_zone

        # 移动限制
        self.max_step = get_config("MAX_SINGLE_MOVE_PX", 80)
        self.max_step_sq = self.max_step * self.max_step
        self.max_mickey = get_config("MAX_MICKEY", 500)

        # 时间配置
        self.ms_to_sec = 0.001
        self.default_delay_sec = get_config("DEFAULT_DELAY_MS_PER_STEP", 2) * self.ms_to_sec

        # 调试模式
        self.debug_mode = get_config("DEBUG_MODE", False)

    def _register_config_callbacks(self):
        """注册配置变更回调（实现热重载）"""

        # 死区配置
        def update_dead_zone(value):
            self.dead_zone_sq = value * value
            if self.debug_mode:
                utils.log(f"[{self.get_mode()}] 🔄 死区更新: {value}px")
        on_config_change("PRECISION_DEAD_ZONE", update_dead_zone)

        # 最大步进
        def update_max_step(value):
            self.max_step = value
            self.max_step_sq = value * value
            if self.debug_mode:
                utils.log(f"[{self.get_mode()}] 🔄 最大步进更新: {value}px")
        on_config_change("MAX_SINGLE_MOVE_PX", update_max_step)

        # Mickey 限制
        def update_max_mickey(value):
            self.max_mickey = value
            if self.debug_mode:
                utils.log(f"[{self.get_mode()}] 🔄 Mickey限制更新: {value}")
        on_config_change("MAX_MICKEY", update_max_mickey)

        # 默认延迟
        def update_delay(value):
            self.default_delay_sec = value * self.ms_to_sec
            if self.debug_mode:
                utils.log(f"[{self.get_mode()}] 🔄 默认延迟更新: {value}ms")
        on_config_change("DEFAULT_DELAY_MS_PER_STEP", update_delay)

        # 调试模式
        def update_debug(value):
            self.debug_mode = value
            utils.log(f"[{self.get_mode()}] 🔄 调试模式: {'开启' if value else '关闭'}")
        on_config_change("DEBUG_MODE", update_debug)

    # ==================== ⭐ 新增：准星位置管理 ====================

    def update_crosshair_position(self, x: float, y: float):
        """
        更新准星位置（线程安全）

        Args:
            x: 准星 X 坐标
            y: 准星 Y 坐标
        """
        with self._crosshair_lock:
            old_x, old_y = self._crosshair_x, self._crosshair_y
            self._crosshair_x = int(x)
            self._crosshair_y = int(y)

    def get_crosshair_position(self) -> tuple[int, int]:
        """
        获取当前准星位置（线程安全）

        Returns:
            (x, y): 准星坐标
        """
        with self._crosshair_lock:
            return self._crosshair_x, self._crosshair_y

    def reset_crosshair_to_center(self):
        """重置准星位置到屏幕中心"""
        center_x = self.screen_width // 2
        center_y = self.screen_height // 2
        self.update_crosshair_position(center_x, center_y)

        if self.debug_mode:
            utils.log(f"[{self.get_mode()}] 🎯 准星已重置到屏幕中心")

    # ==================== 修改：使用动态准星位置 ====================

    def _start_worker_thread(self):
        """启动工作线程"""
        self.mouse_thread = Thread(target=self._mouse_worker, daemon=True)
        self.mouse_thread.start()
        self._is_initialized = True

    def _mouse_worker(self):
        """主工作线程 - PID 控制循环"""
        utils.log(f"[{self.get_mode()} Thread] 工作线程已启动")

        try:
            while not self.stop_event.is_set():
                try:
                    move_command = self.move_queue.get(timeout=0.01)
                    self._process_move_command(move_command)
                except thread_queue.Empty:
                    pass
        finally:
            utils.log(f"[{self.get_mode()} Thread] 工作线程已终止")

    def _process_move_command(self, move_command):
        """处理移动命令（使用动态准星位置）"""
        target_x, target_y, _, delay_ms, button_flags = move_command

        # 计算延迟
        sleep_time = (delay_ms * self.ms_to_sec) if delay_ms else self.default_delay_sec
        self.move_count += 1

        # ⭐ 修复：使用当前准星位置计算误差
        crosshair_x, crosshair_y = self.get_crosshair_position()
        error_x = target_x - crosshair_x
        error_y = target_y - crosshair_y
        distance_sq = error_x * error_x + error_y * error_y

        # 死区判断
        if distance_sq < self.dead_zone_sq:
            if self.debug_mode and self.move_count % 10 == 1:
                utils.log(
                    f"[{self.get_mode()}] 在死区内，跳过 "
                    f"[准星:({crosshair_x},{crosshair_y}) 目标:({target_x},{target_y})]"
                )
            self.pid.reset()
            time.sleep(sleep_time)
            return

        # PID 计算
        move_x_raw, move_y_raw = self.pid.compute(error_x, error_y)

        # 限幅
        move_x, move_y = self._clamp_movement(move_x_raw, move_y_raw)

        # 发送移动指令
        if move_x != 0 or move_y != 0:
            self._send_move(move_x, move_y)

        time.sleep(sleep_time)

        # 处理按钮
        if button_flags != self.BUTTON_NONE:
            self._send_button(button_flags)

    def _clamp_movement(self, move_x_raw, move_y_raw):
        """限制移动幅度"""
        move_sq = move_x_raw * move_x_raw + move_y_raw * move_y_raw

        if move_sq > self.max_step_sq:
            scale = self.max_step / math.sqrt(move_sq)
            move_x_raw *= scale
            move_y_raw *= scale

            if self.debug_mode and self.move_count % 10 == 1:
                utils.log(f"[{self.get_mode()}] 限幅: {math.sqrt(move_sq):.1f}px → {self.max_step}px")

        # 四舍五入
        move_x = int(move_x_raw + 0.5 if move_x_raw > 0 else move_x_raw - 0.5)
        move_y = int(move_y_raw + 0.5 if move_y_raw > 0 else move_y_raw - 0.5)

        # Mickey 限幅
        move_x = max(-self.max_mickey, min(self.max_mickey, move_x))
        move_y = max(-self.max_mickey, min(self.max_mickey, move_y))

        return move_x, move_y

    # ==================== 抽象方法 ====================

    @abstractmethod
    def get_mode(self) -> str:
        """获取当前模式名称"""
        pass

    @abstractmethod
    def _send_move(self, dx: int, dy: int) -> bool:
        """发送鼠标移动指令"""
        pass

    @abstractmethod
    def _send_button(self, button_flags: int) -> bool:
        """发送鼠标按钮指令"""
        pass

    @abstractmethod
    def _do_close(self):
        """执行关闭操作（子类实现）"""
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """检查控制器是否就绪"""
        pass

    # ==================== 公共接口 ====================

    def move_to_target(self, target_x, target_y, delay_ms=None, button_flags=None):
        """
        将目标坐标加入移动队列

        Args:
            target_x: 目标 X 坐标（绝对坐标）
            target_y: 目标 Y 坐标（绝对坐标）
            delay_ms: 延迟毫秒数
            button_flags: 按钮标志

        Returns:
            bool: 是否成功加入队列
        """
        if button_flags is None:
            button_flags = self.BUTTON_NONE

        if not self.is_ready():
            utils.log(f"[{self.get_mode()}] ⚠ 控制器未就绪")
            return False

        actual_delay_ms = delay_ms if delay_ms is not None else get_config("DEFAULT_DELAY_MS_PER_STEP", 2)
        move_command = (target_x, target_y, 0, actual_delay_ms, button_flags)

        # 清空旧指令
        if self.move_queue.full():
            try:
                self.move_queue.get_nowait()
            except thread_queue.Empty:
                pass

        try:
            self.move_queue.put_nowait(move_command)
            return True
        except thread_queue.Full:
            return False
        except Exception as e:
            utils.log(f"[{self.get_mode()}] 队列操作失败: {e}")
            return False

    def move_relative(self, dx, dy):
        """
        直接相对移动（不经过队列和PID）

        Args:
            dx: X 方向移动量
            dy: Y 方向移动量

        Returns:
            bool: 是否成功
        """
        if not self.is_ready():
            return False
        return self._send_move(int(dx), int(dy))

    def click(self, button=None, delay_ms=50):
        """
        点击鼠标

        Args:
            button: 按钮类型（默认左键）
            delay_ms: 按下和释放之间的延迟

        Returns:
            bool: 是否成功
        """
        if button is None:
            button = self.BUTTON_LEFT_DOWN

        if not self.is_ready():
            utils.log(f"[{self.get_mode()}] ⚠ 控制器未就绪，点击失败")
            return False

        up_flag = self.button_up_map.get(button)
        if not up_flag:
            utils.log(f"[{self.get_mode()}] 未知按钮类型: {button}")
            return False

        if self.debug_mode:
            utils.log(f"[{self.get_mode()}] 执行点击: button={button}, delay={delay_ms}ms")

        if not self._send_button(button):
            return False
        time.sleep(delay_ms * self.ms_to_sec)
        return self._send_button(up_flag)

    def mouse_down(self, button=None):
        """按下鼠标按钮"""
        if button is None:
            button = self.BUTTON_LEFT_DOWN
        return self._send_button(button) if self.is_ready() else False

    def mouse_up(self, button=None):
        """释放鼠标按钮"""
        if button is None:
            button = self.BUTTON_LEFT_UP
        return self._send_button(button) if self.is_ready() else False

    def reset_pid(self):
        """重置 PID 控制器"""
        self.pid.reset()

    def get_stats(self):
        """获取统计信息"""
        crosshair_x, crosshair_y = self.get_crosshair_position()
        return {
            "mode": self.get_mode(),
            "move_count": self.move_count,
            "overshoot_count": self.overshoot_count,
            "is_ready": self.is_ready(),
            "crosshair_position": (crosshair_x, crosshair_y),  # ⭐ 新增
            "pid_params": self.pid.get_params() if hasattr(self.pid, 'get_params') else {},
        }

    def move_to_target_instant(self, target_x, target_y):
        """
        直接移动到目标位置（瞬移，不使用PID）

        Args:
            target_x: 目标 X 坐标（绝对坐标）
            target_y: 目标 Y 坐标（绝对坐标）

        Returns:
            bool: 是否成功
        """
        if not self.is_ready():
            utils.log(f"[{self.get_mode()}] ⚠ 控制器未就绪")
            return False

        # ⭐ 修复：使用当前准星位置计算移动量
        crosshair_x, crosshair_y = self.get_crosshair_position()
        dx = target_x - crosshair_x
        dy = target_y - crosshair_y

        # 限幅（可选，防止过大的移动）
        dx = max(-self.max_mickey, min(self.max_mickey, int(dx)))
        dy = max(-self.max_mickey, min(self.max_mickey, int(dy)))

        if self.debug_mode:
            utils.log(
                f"[{self.get_mode()}] 瞬移: ({dx}, {dy}) "
                f"[准星:({crosshair_x},{crosshair_y}) → 目标:({target_x},{target_y})]"
            )

        return self._send_move(dx, dy)

    def close(self):
        """关闭控制器"""
        utils.log(f"[{self.get_mode()}] 开始关闭控制器...")

        self.stop_event.set()

        if self.mouse_thread and self.mouse_thread.is_alive():
            utils.log(f"[{self.get_mode()}] 等待工作线程结束...")
            self.mouse_thread.join(timeout=2.0)

        self._do_close()
        self._is_initialized = False

        utils.log(f"[{self.get_mode()}] 已关闭")

        if self.debug_mode:
            utils.log(f"[{self.get_mode()}] 最终统计: 总移动次数 {self.move_count}")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close()
        return False
