"""基于 MTKmbox 硬件的鼠标控制器（简化版）"""

import time
import queue
import threading
from typing import Optional
import utils
from config.config_manager import get_config
from mouse.mouse_controller import MouseControllerBase


class MTKMBOXMouseController(MouseControllerBase):
    """MTKmbox 硬件鼠标控制器"""

    def __init__(self, shared_device=None, app_state=None, debug: bool = False):
        """
        初始化 MTKmbox 鼠标控制器

        Args:
            shared_device: 共享的 MTKMBOX 设备实例
            app_state: 应用状态对象
            debug: 是否启用调试模式
        """
        self.debug = debug
        self._log_prefix = "[MTKMBOX]"

        # ==================== 硬件控制器 ====================
        if shared_device is not None:
            self._log("使用共享的硬件控制器实例")
            self.controller = shared_device
            self._is_shared = True
        else:
            self._log("创建独立的硬件控制器实例")
            self.controller = None
            self._is_shared = False
            self._connect_device()

        # ==================== 命令队列系统 ====================
        self.command_queue = queue.Queue(maxsize=50)
        self.serial_lock = threading.Lock()
        self.consumer_running = False
        self.consumer_thread: Optional[threading.Thread] = None

        # ==================== 模拟按住状态 ====================
        self._simulated_hold_active = False

        # ==================== 性能统计 ====================
        self.stats = {'sent': 0, 'dropped': 0, 'merged': 0, 'errors': 0}
        self.last_stats_log = 0

        # 初始化父类(PID、配置等)
        super().__init__()

        # 启动消费者线程
        self._start_consumer_thread()

        # 启动工作线程(PID循环)
        self._start_worker_thread()

        self._log("初始化完成(队列模式已激活)")

    # ==================== 设备连接 ====================

    def _connect_device(self):
        """连接 MTKmbox 设备（仅在独立模式下调用）"""
        if self._is_shared:
            self._log("⚠️ 共享模式下不应调用 _connect_device()")
            return

        try:
            from mtkmbox import MTKMBOX

            port = get_config("MTKMBOX_PORT", "COM6")
            vid = get_config("MTKMBOX_VID", 0x0416)
            pid = get_config("MTKMBOX_PID", 0x5020)

            self.controller = MTKMBOX(port=port, vid=vid, pid=pid, debug=self.debug)
            time.sleep(0.3)

            if not self.controller.is_connected():
                raise RuntimeError("MTKmbox 设备连接失败")

            self._log("✅ MTKmbox 设备连接成功")

        except Exception as e:
            self._log(f"❌ MTKmbox 设备初始化失败: {e}")
            raise

    # ==================== 队列消费者线程 ====================

    def _start_consumer_thread(self):
        """启动命令队列消费者线程"""
        if self.consumer_thread and self.consumer_thread.is_alive():
            self._log("消费者线程已在运行")
            return

        self.consumer_running = True
        self.consumer_thread = threading.Thread(
            target=self._worker_process_queue,
            daemon=True,
            name="MTKMBOXConsumer"
        )
        self.consumer_thread.start()
        self._log("消费者线程已启动")

    def _worker_process_queue(self):
        """队列消费者线程"""
        last_send_time = 0
        min_interval = get_config('SERIAL_MIN_SEND_INTERVAL', 0.012)

        while self.consumer_running:
            try:
                try:
                    cmd_type, data = self.command_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                if cmd_type == 'move':
                    dx, dy = data

                    # 合并连续移动指令
                    merge_count = 0
                    max_merge = 10

                    while merge_count < max_merge and not self.command_queue.empty():
                        try:
                            next_cmd, next_data = self.command_queue.get_nowait()
                            if next_cmd == 'move':
                                dx += next_data[0]
                                dy += next_data[1]
                                merge_count += 1
                            self.command_queue.task_done()
                        except queue.Empty:
                            break

                    # 智能延迟
                    now = time.time()
                    elapsed = now - last_send_time
                    if elapsed < min_interval:
                        time.sleep(min_interval - elapsed)

                    # 发送移动指令
                    with self.serial_lock:
                        self._hardware_move(int(dx), int(dy))
                        last_send_time = time.time()

                elif cmd_type == 'button':
                    button_flags = data
                    self._send_button_direct(button_flags)

                self.command_queue.task_done()
                self._log_stats()

            except Exception as e:
                self._log(f"消费者线程错误: {e}")
                time.sleep(0.1)

        self._log("消费者线程已退出")

    def _log_stats(self):
        """定期输出性能统计"""
        now = time.time()
        if now - self.last_stats_log > 10.0:
            utils.log_debug(
                f"{self._log_prefix} 统计 - 已发送:{self.stats['sent']} | "
                f"已丢弃:{self.stats['dropped']} | "
                f"已合并:{self.stats['merged']} | "
                f"错误:{self.stats['errors']}"
            )
            self.last_stats_log = now

    # ==================== 硬件操作 ====================

    def _hardware_move(self, dx: int, dy: int):
        """发送移动指令到 MTKmbox 硬件"""
        if not self.controller:
            raise RuntimeError("MTKmbox 设备未初始化")

        max_move = get_config("MTKMBOX_MAX_MOVE", 127)

        # 分段大幅移动
        while dx != 0 or dy != 0:
            step_dx = max(-max_move, min(max_move, dx))
            step_dy = max(-max_move, min(max_move, dy))

            self.controller.move(step_dx, step_dy)

            dx -= step_dx
            dy -= step_dy

    def _hardware_button(self, button_flags: int):
        """发送按键指令到 MTKmbox 硬件"""
        if not self.controller:
            raise RuntimeError("MTKmbox 设备未初始化")

        button_action_map = {
            self.BUTTON_LEFT_DOWN: ('left', 'press'),
            self.BUTTON_LEFT_UP: ('left', 'release'),
            self.BUTTON_RIGHT_DOWN: ('right', 'press'),
            self.BUTTON_RIGHT_UP: ('right', 'release'),
            self.BUTTON_MIDDLE_DOWN: ('middle', 'press'),
            self.BUTTON_MIDDLE_UP: ('middle', 'release'),
            self.BUTTON_4_DOWN: ('x1', 'press'),
            self.BUTTON_4_UP: ('x1', 'release'),
            self.BUTTON_5_DOWN: ('x2', 'press'),
            self.BUTTON_5_UP: ('x2', 'release'),
        }

        if button_flags not in button_action_map:
            self._log(f"⚠️ 未知按钮标志: {button_flags}")
            return

        button_name, action = button_action_map[button_flags]

        try:
            if action == 'press':
                result = self.controller.press(button_name)
            else:
                result = self.controller.release(button_name)

            if self.debug:
                self._log(f"按钮操作: {button_name} {action} -> {result}")

        except Exception as e:
            self._log(f"❌ 按键操作失败 ({button_name} {action}): {e}")
            raise

    # ==================== 实现抽象方法 ====================

    def get_mode(self) -> str:
        return "MTKMBOX"

    def is_ready(self) -> bool:
        return (
            self.controller is not None and
            hasattr(self.controller, 'is_connected') and
            self.controller.is_connected() and
            self._is_initialized and
            self.consumer_running and
            self.consumer_thread is not None and
            self.consumer_thread.is_alive()
        )

    def _send_move(self, dx: int, dy: int) -> bool:
        """发送移动指令(生产者模式 - 非阻塞)"""
        if not self.controller:
            return False

        try:
            self.command_queue.put_nowait(('move', (dx, dy)))
            return True
        except queue.Full:
            self.stats['dropped'] += 1
            return False

    def _send_button(self, button_flags: int) -> bool:
        """发送按键指令（左键使用模拟按住）"""
        if not self.controller:
            return False

        # 拦截左键按下：使用模拟按住
        if button_flags == self.BUTTON_LEFT_DOWN:
            if self._simulated_hold_active:
                if self.debug:
                    self._log("⚠️ 左键已在模拟按住中，跳过")
                return True

            try:
                fire_rate = get_config('AUTO_FIRE_RATE', 100)
                interval = 1.0 / fire_rate if fire_rate > 0 else 0.01
                click_duration = get_config('AUTO_FIRE_CLICK_DURATION', 0.001)

                success = self.controller.hold('left', interval, click_duration)

                if success:
                    self._simulated_hold_active = True
                    self._log(f"✅ 左键按下 → 开始模拟按住 (射速: {fire_rate}Hz)")
                else:
                    self._log("❌ 开始模拟按住失败")

                return success

            except Exception as e:
                self._log(f"❌ 开始模拟按住异常: {e}")
                return False

        # 拦截左键释放：停止模拟按住
        elif button_flags == self.BUTTON_LEFT_UP:
            if not self._simulated_hold_active:
                if self.debug:
                    self._log("⚠️ 左键未在模拟按住中，使用普通释放")
                return self._send_button_direct(button_flags)

            try:
                success = self.controller.release_hold('left')

                if success:
                    self._simulated_hold_active = False
                    self._log("✅ 左键释放 → 停止模拟按住")
                else:
                    self._log("⚠️ 停止模拟按住失败")

                return success

            except Exception as e:
                self._log(f"❌ 停止模拟按住异常: {e}")
                return False

        # 其他按键：直接发送
        else:
            return self._send_button_direct(button_flags)

    def _send_button_direct(self, button_flags: int) -> bool:
        """直接发送按键指令（不使用模拟按住）"""
        with self.serial_lock:
            try:
                self._hardware_button(button_flags)
                return True
            except Exception as e:
                self._log(f"❌ 按键操作失败: {e}")
                return False

    def _do_close(self):
        """清理资源"""
        # 停止模拟按住
        if self._simulated_hold_active:
            try:
                self.controller.release_hold('left')
                self._simulated_hold_active = False
                self._log("✅ 断开前停止模拟按住")
            except Exception as e:
                self._log(f"⚠️ 停止模拟按住失败: {e}")

        # 停止消费者线程
        self._log("停止消费者线程...")
        self.consumer_running = False

        if self.consumer_thread:
            self.consumer_thread.join(timeout=2.0)

        # 清空队列
        while not self.command_queue.empty():
            try:
                self.command_queue.get_nowait()
                self.command_queue.task_done()
            except queue.Empty:
                break

        # 断开设备(仅非共享模式)
        if self.controller and not self._is_shared:
            try:
                self._log("断开设备连接...")
                self.controller.close()
                self._log("✅ MTKmbox 设备已断开")
            except Exception as e:
                self._log(f"⚠️ 断开设备时出错: {e}")

        self.controller = None
        self._log("资源已清理")

    # ==================== 辅助方法 ====================

    def is_connected(self) -> bool:
        return bool(self.controller and self.controller.is_connected())

    def get_device_info(self) -> dict:
        if not self.controller:
            return {
                'connected': False,
                'mode': self.get_mode(),
                'simulated_hold_active': self._simulated_hold_active
            }

        try:
            info = self.controller.get_device_info()
            info['mode'] = self.get_mode()
            info['simulated_hold_active'] = self._simulated_hold_active
            return info
        except Exception as e:
            self._log(f"❌ 获取设备信息失败: {e}")
            return {
                'connected': self.is_connected(),
                'mode': self.get_mode(),
                'simulated_hold_active': self._simulated_hold_active,
                'error': str(e)
            }

    def _log(self, msg: str):
        if self.debug or "❌" in msg or "⚠️" in msg:
            utils.log(f"{self._log_prefix} {msg}")
