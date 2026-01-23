"""
串口硬件鼠标控制器通用基类
提供命令队列、线程管理、统计等通用功能
"""
import time
import queue
import threading
from typing import Optional
from abc import abstractmethod
import utils
from config_manager import get_config
from mouse.mouse_controller import MouseControllerBase


class SerialMouseControllerBase(MouseControllerBase):
    """串口硬件鼠标控制器抽象基类"""

    def __init__(self, shared_controller=None):
        """
        Args:
            shared_controller: 共享的硬件控制器实例(避免重复打开串口)
        """
        # ==================== 硬件控制器 ====================
        if shared_controller is not None:
            utils.log(f"[{self.get_mode()}] 使用共享的硬件控制器实例")
            self.controller = shared_controller
            self._is_shared = True
        else:
            utils.log(f"[{self.get_mode()}] 创建独立的硬件控制器实例")
            self.controller = None
            self._is_shared = False
            # ⭐ 只有在独立模式下才连接设备
            self._connect_device()

        # ==================== 命令队列系统 ====================
        self.command_queue = queue.Queue(maxsize=50)
        self.serial_lock = threading.Lock()

        # 消费者线程控制
        self.consumer_running = False
        self.consumer_thread: Optional[threading.Thread] = None

        # ==================== 性能统计 ====================
        self.stats = {
            'sent': 0,
            'dropped': 0,
            'merged': 0,
            'errors': 0
        }
        self.last_stats_log = 0

        # 初始化父类(PID、配置等)
        super().__init__()

        # 启动消费者线程
        self._start_consumer_thread()

        # 启动工作线程(PID循环)
        self._start_worker_thread()

        utils.log(f"[{self.get_mode()}] 初始化完成(队列模式已激活)")

    # ==================== 抽象方法:由子类实现 ====================

    @abstractmethod
    def _connect_device(self):
        """连接硬件设备(子类必须实现)"""
        pass

    @abstractmethod
    def _hardware_move(self, dx: int, dy: int):
        """
        发送移动指令到硬件(子类必须实现)

        Args:
            dx: X方向移动量
            dy: Y方向移动量

        Raises:
            Exception: 硬件通信失败
        """
        pass

    @abstractmethod
    def _hardware_button(self, button_flags: int):
        """
        发送按键指令到硬件(子类必须实现)

        Args:
            button_flags: 按键标志

        Raises:
            Exception: 硬件通信失败
        """
        pass

    @abstractmethod
    def _disconnect_device(self):
        """断开硬件连接(子类必须实现)"""
        pass

    # ==================== 队列消费者线程 ====================

    def _start_consumer_thread(self):
        """启动命令队列消费者线程"""
        if self.consumer_thread and self.consumer_thread.is_alive():
            utils.log(f"[{self.get_mode()}] 消费者线程已在运行")
            return

        self.consumer_running = True
        self.consumer_thread = threading.Thread(
            target=self._worker_process_queue,
            daemon=True,
            name=f"{self.get_mode()}Consumer"
        )
        self.consumer_thread.start()
        utils.log(f"[{self.get_mode()}] 消费者线程已启动")

    def _worker_process_queue(self):
        """优化后的消费者线程"""
        last_send_time = 0
        min_interval = get_config('SERIAL_MIN_SEND_INTERVAL', 0.012)

        while self.consumer_running:
            try:
                # ⭐ 使用更短的超时，提高响应速度
                try:
                    cmd_type, data = self.command_queue.get(timeout=0.1)  # 100ms
                except queue.Empty:
                    continue

                if cmd_type == 'move':
                    dx, dy = data

                    # ⭐ 限制合并次数，避免过度延迟
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

                    # ⭐ 智能延迟：只在需要时等待
                    now = time.time()
                    elapsed = now - last_send_time
                    if elapsed < min_interval:
                        time.sleep(min_interval - elapsed)

                    # 发送命令
                    with self.serial_lock:
                        self._hardware_move(int(dx), int(dy))
                        last_send_time = time.time()

                elif cmd_type == 'button':
                    button_flags = data
                    self._send_button_direct(button_flags)

                self.command_queue.task_done()
                self._log_stats()

            except Exception as e:
                utils.log(f"[{self.get_mode()}Queue] 消费者线程错误:{e}")
                time.sleep(0.1)

        utils.log(f"[{self.get_mode()}Queue] 消费者线程已退出")

    def _log_stats(self):
        """定期输出性能统计"""
        now = time.time()
        if now - self.last_stats_log > 10.0:
            utils.log_debug(
                f"[{self.get_mode()}Queue] 统计 - 已发送:{self.stats['sent']} | "
                f"已丢弃:{self.stats['dropped']} | "
                f"已合并:{self.stats['merged']} | "
                f"错误:{self.stats['errors']}"
            )
            self.last_stats_log = now

    # ==================== 实现抽象方法 ====================

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

    def _send_button_direct(self, button_flags: int) -> bool:
        """直接发送按键指令(绕过队列,但使用锁)"""
        if not self.controller:
            return False

        with self.serial_lock:
            try:
                self._hardware_button(button_flags)
                return True
            except Exception as e:
                utils.log(f"[{self.get_mode()}] 按键操作失败:{e}")
                return False

    def _send_button(self, button_flags: int) -> bool:
        """发送按键指令(公开接口)"""
        return self._send_button_direct(button_flags)

    def _do_close(self):
        """清理资源"""
        # 停止消费者线程
        utils.log(f"[{self.get_mode()}] 停止消费者线程...")
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
                utils.log(f"[{self.get_mode()}] 断开设备连接...")
                self._disconnect_device()
            except Exception as e:
                utils.log(f"[{self.get_mode()}] 断开连接时出错:{e}")

        self.controller = None
        utils.log(f"[{self.get_mode()}] 资源已清理")
