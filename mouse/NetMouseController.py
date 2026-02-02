# kmnet_mouse_controller.py
"""基于 kmNet 硬件的鼠标控制器（完整修复版）"""

import time
import kmNet  # type: ignore
import utils
from mouse_controller import MouseControllerBase


class KmNetMouseController(MouseControllerBase):
    """基于 kmNet 硬件的鼠标控制器"""

    def __init__(
            self,
            ip: str = '192.168.1.10',
            port: int = 1000,
            uuid: str = '25ABDBB2',
            auto_reconnect: bool = True,
            debug: bool = False
    ):
        """
        初始化 kmNet 鼠标控制器

        Args:
            ip: kmNet 设备 IP 地址
            port: 端口号（会自动转换为字符串）
            uuid: 设备 UUID
            auto_reconnect: 是否自动重连
            debug: 是否启用调试模式
        """
        self.ip = ip
        self.port = port  # 保存为 int
        self.uuid = uuid
        self.auto_reconnect = auto_reconnect
        self._connected = False

        # 重连配置
        self.reconnect_interval = 5.0
        self.last_reconnect_time = 0
        self._max_connection_attempts = 3

        # 先连接 kmNet（如果失败会抛出异常）
        self._connect()

        # 再初始化基类（会启动工作线程）
        super().__init__()

        # 覆盖基类的 debug_mode
        self.debug_mode = debug

    def _connect(self):
        """连接 kmNet 硬件（带重试机制）"""
        for attempt in range(1, self._max_connection_attempts + 1):
            try:
                utils.log(
                    f"[KmNet] 正在连接到 {self.ip}:{self.port} "
                    f"(尝试 {attempt}/{self._max_connection_attempts})..."
                )

                # ⭐ 关键修复：将 port 转换为字符串
                kmNet.init(self.ip, str(self.port), self.uuid)

                # 等待连接稳定
                time.sleep(0.3)

                self._connected = True
                utils.log(f"[KmNet] ✅ 已连接到 {self.ip}:{self.port}")
                return

            except Exception as e:
                utils.log(
                    f"[KmNet] ❌ 连接失败 "
                    f"(尝试 {attempt}/{self._max_connection_attempts}): {e}"
                )
                self._connected = False

                if attempt < self._max_connection_attempts:
                    time.sleep(1.0)  # 重试前等待
                else:
                    raise RuntimeError(
                        f"kmNet 连接失败，已尝试 {self._max_connection_attempts} 次"
                    )

    def _check_connection(self) -> bool:
        """检查连接状态并尝试重连"""
        if self._connected:
            return True

        if not self.auto_reconnect:
            return False

        # 限制重连频率
        current_time = time.time()
        if current_time - self.last_reconnect_time < self.reconnect_interval:
            return False

        self.last_reconnect_time = current_time
        utils.log("[KmNet] ⚠️ 连接已断开，尝试重连...")

        try:
            self._connect()
            return True
        except Exception as e:
            utils.log(f"[KmNet] ❌ 重连失败: {e}")
            return False

    # ==================== 实现抽象方法 ====================

    def get_mode(self) -> str:
        return "KmNet"

    def is_ready(self) -> bool:
        """检查控制器是否就绪"""
        return self._connected and self._is_initialized

    def _send_move(self, dx: int, dy: int) -> bool:
        """发送鼠标移动指令"""
        if not self._check_connection():
            return False

        try:
            kmNet.move(int(dx), int(dy))

            # ⭐ 关键：更新准星位置
            crosshair_x, crosshair_y = self.get_crosshair_position()
            self.update_crosshair_position(
                crosshair_x + dx,
                crosshair_y + dy
            )

            if self.debug_mode and self.move_count % 50 == 0:
                utils.log(
                    f"[KmNet] 移动: ({dx}, {dy}) -> "
                    f"准星: ({crosshair_x + dx}, {crosshair_y + dy})"
                )

            return True

        except Exception as e:
            utils.log(f"[KmNet] ❌ 移动失败: {e}")
            self._connected = False  # 标记连接断开
            return False

    def _send_button(self, button_flags: int) -> bool:
        """发送鼠标按钮指令"""
        if not self._check_connection():
            return False

        try:
            # ⭐ 使用字典映射简化代码
            button_actions = {
                self.BUTTON_LEFT_DOWN: lambda: kmNet.left(1),
                self.BUTTON_LEFT_UP: lambda: kmNet.left(0),
                self.BUTTON_RIGHT_DOWN: lambda: kmNet.right(1),
                self.BUTTON_RIGHT_UP: lambda: kmNet.right(0),
                self.BUTTON_MIDDLE_DOWN: lambda: kmNet.middle(1),
                self.BUTTON_MIDDLE_UP: lambda: kmNet.middle(0),
            }

            action = button_actions.get(button_flags)
            if action is None:
                utils.log(f"[KmNet] ⚠️ 不支持的按钮: {button_flags}")
                return False

            action()  # 执行按钮操作

            if self.debug_mode:
                button_names = {
                    self.BUTTON_LEFT_DOWN: "左键按下",
                    self.BUTTON_LEFT_UP: "左键释放",
                    self.BUTTON_RIGHT_DOWN: "右键按下",
                    self.BUTTON_RIGHT_UP: "右键释放",
                    self.BUTTON_MIDDLE_DOWN: "中键按下",
                    self.BUTTON_MIDDLE_UP: "中键释放",
                }
                utils.log(f"[KmNet] 按钮操作: {button_names.get(button_flags, button_flags)}")

            return True

        except Exception as e:
            utils.log(f"[KmNet] ❌ 按钮操作失败: {e}")
            self._connected = False  # 标记连接断开
            return False

    def _do_close(self):
        """关闭 kmNet 连接"""
        if self._connected:
            try:
                # kmNet 可能没有显式关闭方法
                # 如果有 close() 或 disconnect() 方法，取消下面的注释
                # kmNet.close()

                self._connected = False
                utils.log("[KmNet] ✅ 连接已关闭")
            except Exception as e:
                utils.log(f"[KmNet] ⚠️ 关闭失败: {e}")

    # ==================== 辅助方法 ====================

    def is_connected(self) -> bool:
        """检查设备连接状态"""
        return self._connected

    def force_reconnect(self):
        """强制重新连接"""
        utils.log("[KmNet] 🔄 强制重新连接...")
        self._connected = False
        time.sleep(0.5)
        self._connect()

    def get_connection_info(self) -> dict:
        """获取连接信息"""
        return {
            "ip": self.ip,
            "port": self.port,
            "uuid": self.uuid,
            "connected": self._connected,
            "auto_reconnect": self.auto_reconnect,
        }

    # ==================== 高级功能（如果 kmNet 支持）====================

    def move_smooth(self, target_x: int, target_y: int, duration_ms: int = 200):
        """
        平滑移动到目标位置（使用 kmNet 的 move_auto）

        Args:
            target_x: 目标 X 坐标（绝对坐标）
            target_y: 目标 Y 坐标（绝对坐标）
            duration_ms: 移动时间（毫秒）

        Returns:
            bool: 是否成功
        """
        if not self._check_connection():
            return False

        try:
            # 计算相对移动量
            crosshair_x, crosshair_y = self.get_crosshair_position()
            dx = target_x - crosshair_x
            dy = target_y - crosshair_y

            # 使用 kmNet 的平滑移动功能
            kmNet.move_auto(int(dx), int(dy), duration_ms)

            # 更新准星位置
            self.update_crosshair_position(target_x, target_y)

            if self.debug_mode:
                utils.log(
                    f"[KmNet] 平滑移动: ({dx}, {dy}) "
                    f"耗时: {duration_ms}ms"
                )

            return True

        except Exception as e:
            utils.log(f"[KmNet] ❌ 平滑移动失败: {e}")
            return False

    def move_bezier(
            self,
            target_x: int,
            target_y: int,
            control_x1: int = None,
            control_y1: int = None,
            control_x2: int = None,
            control_y2: int = None,
            duration_ms: int = 300
    ):
        """
        贝塞尔曲线移动（使用 kmNet 的 move_beizer）

        Args:
            target_x: 目标 X 坐标
            target_y: 目标 Y 坐标
            control_x1, control_y1: 控制点1（默认自动计算）
            control_x2, control_y2: 控制点2（默认自动计算）
            duration_ms: 移动时间（毫秒）

        Returns:
            bool: 是否成功
        """
        if not self._check_connection():
            return False

        try:
            # 获取当前位置
            crosshair_x, crosshair_y = self.get_crosshair_position()

            # 自动计算控制点（如果未提供）
            if control_x1 is None or control_y1 is None:
                control_x1 = crosshair_x + (target_x - crosshair_x) // 3
                control_y1 = crosshair_y + (target_y - crosshair_y) // 3

            if control_x2 is None or control_y2 is None:
                control_x2 = crosshair_x + (target_x - crosshair_x) * 2 // 3
                control_y2 = crosshair_y + (target_y - crosshair_y) * 2 // 3

            # 使用 kmNet 的贝塞尔曲线移动
            kmNet.move_beizer(
                control_x1, control_y1,
                control_x2, control_y2,
                target_x, target_y,
                duration_ms
            )

            # 更新准星位置
            self.update_crosshair_position(target_x, target_y)

            if self.debug_mode:
                utils.log(
                    f"[KmNet] 贝塞尔移动: "
                    f"({crosshair_x},{crosshair_y}) -> ({target_x},{target_y}) "
                    f"耗时: {duration_ms}ms"
                )

            return True

        except Exception as e:
            utils.log(f"[KmNet] ❌ 贝塞尔移动失败: {e}")
            return False
