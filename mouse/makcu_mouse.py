"""
Makcu 硬件模式鼠标控制器 (队列优化版)
基于 Makcu v2.3.0 API 适配
"""
import time
import queue
import threading
from typing import Optional, Tuple
import utils
from config_manager import get_config
from makcu import create_controller, MouseButton
from mouse import MouseControllerBase


class MakcuMouseController(MouseControllerBase):
    """Makcu 硬件鼠标控制器 (带命令队列)"""

    def __init__(self, shared_controller=None):
        super().__init__()

        # ==================== Makcu 控制器 ====================
        if shared_controller is not None:
            utils.log("[MakcuMouse] 使用共享的 Makcu controller 实例")
            self.controller = shared_controller
            self._is_shared = True
        else:
            utils.log("[MakcuMouse] 创建独立的 Makcu controller 实例")
            self.controller = None
            self._is_shared = False
            self._connect_device()

        # ==================== 命令队列系统 ====================
        # 限制队列大小防止内存溢出 (实时性优先策略)
        self.command_queue = queue.Queue(maxsize=50)

        # 串口硬件锁 (保护串口物理访问)
        self.serial_lock = threading.Lock()

        # 消费者线程控制
        self.consumer_running = False
        self.consumer_thread: Optional[threading.Thread] = None

        # 性能统计
        self.stats = {
            'sent': 0,        # 实际发送的指令数
            'dropped': 0,     # 丢弃的指令数 (队列满)
            'merged': 0,      # 合并的指令数
            'errors': 0       # 通信错误数
        }
        self.last_stats_log = 0

        # ==================== 按键映射 ====================
        self.btn_map = {
            self.BUTTON_LEFT_DOWN:   (MouseButton.LEFT, 'press'),
            self.BUTTON_LEFT_UP:     (MouseButton.LEFT, 'release'),
            self.BUTTON_RIGHT_DOWN:  (MouseButton.RIGHT, 'press'),
            self.BUTTON_RIGHT_UP:    (MouseButton.RIGHT, 'release'),
            self.BUTTON_MIDDLE_DOWN: (MouseButton.MIDDLE, 'press'),
            self.BUTTON_MIDDLE_UP:   (MouseButton.MIDDLE, 'release'),
            self.BUTTON_4_DOWN:      (MouseButton.MOUSE4, 'press'),
            self.BUTTON_4_UP:        (MouseButton.MOUSE4, 'release'),
            self.BUTTON_5_DOWN:      (MouseButton.MOUSE5, 'press'),
            self.BUTTON_5_UP:        (MouseButton.MOUSE5, 'release'),
        }

        # 启动消费者线程
        self._start_consumer_thread()

        # 启动工作线程 (PID循环 - 来自父类)
        self._start_worker_thread()

        utils.log("[MakcuMouse] 初始化完成 (队列模式已激活)")

    def _connect_device(self):
        """连接 Makcu 硬件"""
        try:
            port = get_config("MAKCU_PORT", "")
            auto_reconnect = get_config("MAKCU_AUTO_RECONNECT", True)

            self.controller = create_controller(
                fallback_com_port=port,
                debug=self.debug_mode,
                auto_reconnect=auto_reconnect
            )

            time.sleep(0.5)

            if not self.controller.is_connected():
                utils.log("[MakcuMouse] 警告: 控制器对象已创建但硬件未连接")
            else:
                info = self.controller.get_device_info()
                utils.log(f"[MakcuMouse] 设备已连接: {info.get('version', 'Unknown Ver')}")

        except Exception as e:
            utils.log(f"[MakcuMouse] 设备连接失败: {e}")
            raise RuntimeError(f"Makcu 连接失败: {e}")

    # ==================== 队列消费者线程 ====================

    def _start_consumer_thread(self):
        """启动命令队列消费者线程"""
        if self.consumer_thread and self.consumer_thread.is_alive():
            utils.log("[MakcuMouse] 消费者线程已在运行")
            return

        self.consumer_running = True
        self.consumer_thread = threading.Thread(
            target=self._worker_process_queue,
            daemon=True,
            name="MakcuConsumer"
        )
        self.consumer_thread.start()
        utils.log("[MakcuMouse] 消费者线程已启动")

    def _worker_process_queue(self):
        """
        队列消费者线程 (唯一真正写串口的地方)

        核心功能:
        1. 从队列读取指令
        2. 合并连续的移动指令 (减少串口压力)
        3. 控制发送频率 (防止缓冲区溢出)
        """
        last_send_time = 0
        # 硬件最小物理间隔 (根据实测调整, 建议 10-20ms)
        min_interval = get_config('MAKCU_MIN_SEND_INTERVAL', 0.012)

        utils.log(f"[MakcuQueue] 消费者线程启动 (最小间隔: {min_interval*1000:.1f}ms)")

        while self.consumer_running:
            try:
                # 阻塞获取第一个任务 (1秒超时用于检查退出标志)
                try:
                    cmd_type, data = self.command_queue.get(timeout=1.0)
                except queue.Empty:
                    continue

                if cmd_type == 'move':
                    dx, dy = data
                    merge_count = 0

                    # ⭐ 关键优化: 合并队列中积压的移动指令
                    while not self.command_queue.empty():
                        try:
                            next_cmd, next_data = self.command_queue.get_nowait()
                            if next_cmd == 'move':
                                dx += next_data[0]
                                dy += next_data[1]
                                merge_count += 1
                            self.command_queue.task_done()
                        except queue.Empty:
                            break

                    if merge_count > 0:
                        self.stats['merged'] += merge_count

                    # 频率控制: 确保不超过硬件处理能力
                    now = time.time()
                    elapsed = now - last_send_time
                    if elapsed < min_interval:
                        time.sleep(min_interval - elapsed)

                    # 执行真正的串口写入
                    with self.serial_lock:
                        try:
                            self.controller.move(int(dx), int(dy))
                            self.stats['sent'] += 1
                            last_send_time = time.time()
                        except Exception as e:
                            self.stats['errors'] += 1
                            if self.debug_mode:
                                utils.log(f"[MakcuQueue] 移动失败: {e}")

                elif cmd_type == 'button':
                    # 按键指令优先级高, 立即执行
                    button_flags = data
                    self._send_button_direct(button_flags)

                self.command_queue.task_done()

                # 定期输出统计信息
                self._log_stats()

            except Exception as e:
                utils.log(f"[MakcuQueue] 消费者线程错误: {e}")
                time.sleep(0.1)

        utils.log("[MakcuQueue] 消费者线程已退出")

    def _log_stats(self):
        """定期输出性能统计"""
        now = time.time()
        if now - self.last_stats_log > 10.0:  # 每10秒
            utils.log_debug(
                f"[MakcuQueue] 统计 - 已发送: {self.stats['sent']} | "
                f"已丢弃: {self.stats['dropped']} | "
                f"已合并: {self.stats['merged']} | "
                f"错误: {self.stats['errors']}"
            )
            self.last_stats_log = now

    # ==================== 实现抽象方法 ====================

    def get_mode(self) -> str:
        return "Makcu-Queue"

    def is_ready(self) -> bool:
        return (
            self.controller is not None and
            self.controller.is_connected() and
            self._is_initialized and
            self.consumer_running and
            self.consumer_thread is not None and
            self.consumer_thread.is_alive()
        )

    def _send_move(self, dx: int, dy: int) -> bool:
        """
        发送移动指令 (生产者模式 - 非阻塞)

        Returns:
            True: 指令已加入队列
            False: 队列已满, 指令被丢弃
        """
        if not self.controller:
            return False

        try:
            # 使用 put_nowait 保证非阻塞
            self.command_queue.put_nowait(('move', (dx, dy)))
            return True
        except queue.Full:
            # 队列满了说明串口速度跟不上, 直接丢弃 (保证实时性)
            self.stats['dropped'] += 1
            return False

    def _send_button_direct(self, button_flags: int) -> bool:
        """
        直接发送按键指令 (绕过队列, 但使用锁)

        按键操作需要即时响应, 不能等待队列
        """
        if not self.controller:
            return False

        mapping = self.btn_map.get(button_flags)
        if not mapping:
            utils.log(f"[MakcuMouse] 未知按键标志: {button_flags}")
            return False

        btn_enum, action = mapping

        with self.serial_lock:
            try:
                if action == 'press':
                    self.controller.press(btn_enum)
                elif action == 'release':
                    self.controller.release(btn_enum)
                return True
            except Exception as e:
                utils.log(f"[MakcuMouse] 按键操作失败 ({action}): {e}")
                return False

    def _send_button(self, button_flags: int) -> bool:
        """
        发送按键指令 (公开接口)

        策略: 按键直接发送, 不进队列 (实时性要求高)
        """
        return self._send_button_direct(button_flags)

    def _do_close(self):
        """清理资源"""
        # 停止消费者线程
        utils.log("[MakcuMouse] 停止消费者线程...")
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

        # 断开设备
        if self.controller and not self._is_shared:
            try:
                utils.log("[MakcuMouse] 断开设备连接...")
                self.controller.disconnect()
            except Exception as e:
                utils.log(f"[MakcuMouse] 断开连接时出错: {e}")

        self.controller = None
        utils.log("[MakcuMouse] 资源已清理")
