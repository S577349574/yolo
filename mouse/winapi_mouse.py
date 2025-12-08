"""
WinAPI 模式鼠标控制器
"""

import ctypes

import utils
from .mouse_controller import MouseControllerBase


class MOUSEINPUT(ctypes.Structure):
    """WinAPI MOUSEINPUT 结构体"""
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]


class INPUT(ctypes.Structure):
    """WinAPI INPUT 结构体"""
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("mi", MOUSEINPUT)
    ]


class WinAPIMouseController(MouseControllerBase):
    """WinAPI 模式鼠标控制器"""

    # WinAPI 常量
    INPUT_MOUSE = 0
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040
    MOUSEEVENTF_ABSOLUTE = 0x8000

    def __init__(self):
        """初始化 WinAPI 模式控制器"""
        # 先调用基类初始化
        super().__init__()

        # 加载 user32.dll
        self.user32 = ctypes.windll.user32

        # 重用结构体对象
        self._input = INPUT()
        self._input.type = self.INPUT_MOUSE

        # 按钮标志映射: 内部标志 -> WinAPI 标志
        self._button_flag_map = {
            self.BUTTON_LEFT_DOWN: self.MOUSEEVENTF_LEFTDOWN,
            self.BUTTON_LEFT_UP: self.MOUSEEVENTF_LEFTUP,
            self.BUTTON_RIGHT_DOWN: self.MOUSEEVENTF_RIGHTDOWN,
            self.BUTTON_RIGHT_UP: self.MOUSEEVENTF_RIGHTUP,
            self.BUTTON_MIDDLE_DOWN: self.MOUSEEVENTF_MIDDLEDOWN,
            self.BUTTON_MIDDLE_UP: self.MOUSEEVENTF_MIDDLEUP,
        }

        # 启动工作线程
        self._start_worker_thread()

        utils.log("[WinAPIMouse] 初始化完成")

    # ==================== 实现抽象方法 ====================

    def get_mode(self) -> str:
        return "WinAPI"

    def is_ready(self) -> bool:
        return (
                self._is_initialized and
                self.mouse_thread is not None and
                self.mouse_thread.is_alive()
        )

    def _send_move(self, dx: int, dy: int) -> bool:
        """发送移动指令"""
        return self._send_input(dx, dy, self.MOUSEEVENTF_MOVE)

    def _send_button(self, button_flags: int) -> bool:
        """发送按钮指令"""
        winapi_flags = self._button_flag_map.get(button_flags, 0)
        if winapi_flags == 0:
            utils.log(f"[WinAPIMouse] 未知按钮标志: {button_flags}")
            return False
        return self._send_input(0, 0, winapi_flags)

    def _send_input(self, dx: int, dy: int, flags: int) -> bool:
        """发送 WinAPI 输入"""
        # 限幅
        dx = max(-self.max_mickey, min(self.max_mickey, dx))
        dy = max(-self.max_mickey, min(self.max_mickey, dy))

        # 填充结构体
        self._input.mi.dx = dx
        self._input.mi.dy = dy
        self._input.mi.mouseData = 0
        self._input.mi.dwFlags = flags
        self._input.mi.time = 0
        self._input.mi.dwExtraInfo = None

        try:
            result = self.user32.SendInput(
                1,
                ctypes.byref(self._input),
                ctypes.sizeof(self._input)
            )
            return result == 1
        except Exception as e:
            utils.log(f"[WinAPIMouse] SendInput 失败: {e}")
            return False

    def _do_close(self):
        """WinAPI 模式无需特殊清理"""
        pass

    def move_relative(self, dx, dy):
        """直接相对移动，不使用PID"""
        return self._send_move(int(dx), int(dy))
    # ==================== WinAPI 特有方法 ====================

    def move_absolute(self, x: int, y: int) -> bool:
        """
        绝对位置移动（WinAPI 特有）

        Args:
            x: 屏幕 X 坐标
            y: 屏幕 Y 坐标

        Returns:
            bool: 是否成功
        """
        if not self.is_ready():
            return False

        # 转换为 0-65535 范围
        abs_x = int(x * 65535 / self.screen_width)
        abs_y = int(y * 65535 / self.screen_height)

        flags = self.MOUSEEVENTF_MOVE | self.MOUSEEVENTF_ABSOLUTE

        self._input.mi.dx = abs_x
        self._input.mi.dy = abs_y
        self._input.mi.mouseData = 0
        self._input.mi.dwFlags = flags
        self._input.mi.time = 0
        self._input.mi.dwExtraInfo = None

        try:
            result = self.user32.SendInput(
                1,
                ctypes.byref(self._input),
                ctypes.sizeof(self._input)
            )
            return result == 1
        except Exception as e:
            utils.log(f"[WinAPIMouse] 绝对移动失败: {e}")
            return False
