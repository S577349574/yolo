"""
驱动模式鼠标控制器
"""

import ctypes

import win32api
import win32file

import utils
from config_manager import get_config
from .mouse_controller import MouseControllerBase


class KMouseRequest(ctypes.Structure):
    """驱动通信结构体"""
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
        ("button_flags", ctypes.c_ubyte),
    ]


class DriverMouseController(MouseControllerBase):
    """驱动模式鼠标控制器"""

    def __init__(self, device_path=None):
        """
        初始化驱动模式控制器

        Args:
            device_path: 驱动设备路径，默认从配置读取

        Raises:
            RuntimeError: 无法打开驱动时抛出
        """
        # 先调用基类初始化
        super().__init__()

        # 驱动相关
        if device_path is None:
            device_path = get_config("DRIVER_PATH")
        self.device_path = device_path
        self.driver_handle = None
        self.mouse_request_code = get_config("MOUSE_REQUEST")

        # 重用结构体对象
        self._mouse_req = KMouseRequest()

        # 检查环境
        self._check_environment()

        # 打开驱动
        self._open_driver()

        # 启动工作线程
        self._start_worker_thread()

        utils.log("[DriverMouse] 初始化完成")

    def _check_environment(self):
        """检查运行环境"""
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Control Panel\Mouse",
                0,
                winreg.KEY_READ
            )

            sensitivity, _ = winreg.QueryValueEx(key, "MouseSensitivity")
            speed, _ = winreg.QueryValueEx(key, "MouseSpeed")
            winreg.CloseKey(key)

            is_ideal = (6 <= int(sensitivity) <= 14) and (speed == '0')

            if is_ideal:
                utils.log(f"[DriverMouse] 理想配置: 速度 {sensitivity}/20, EPP 关闭")
            else:
                utils.log(f"[DriverMouse] 非理想配置: 速度 {sensitivity}/20, EPP {speed}")

        except Exception as e:
            utils.log(f"[DriverMouse] 无法检测环境: {e}")

    def _open_driver(self):
        """打开驱动句柄"""
        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        OPEN_EXISTING = 3

        try:
            self.driver_handle = win32file.CreateFile(
                self.device_path,
                GENERIC_READ | GENERIC_WRITE,
                0,
                None,
                OPEN_EXISTING,
                0,
                None,
            )
            utils.log("[DriverMouse] 成功打开驱动")
        except win32api.error as e:
            error_msg = f"无法打开驱动 '{self.device_path}': 错误码 {e.winerror}"
            utils.log(f"[DriverMouse] {error_msg}")
            raise RuntimeError(error_msg) from e

    # ==================== 实现抽象方法 ====================

    def get_mode(self) -> str:
        return "Driver"

    def is_ready(self) -> bool:
        return (
                self.driver_handle is not None and
                self._is_initialized and
                self.mouse_thread is not None and
                self.mouse_thread.is_alive()
        )

    def _send_move(self, dx: int, dy: int) -> bool:
        """发送移动指令"""
        return self._send_driver_request(dx, dy, self.BUTTON_NONE)

    def _send_button(self, button_flags: int) -> bool:
        """发送按钮指令"""
        return self._send_driver_request(0, 0, button_flags)

    def _send_driver_request(self, x: int, y: int, button_flags: int) -> bool:
        """发送驱动请求"""
        if not self.driver_handle:
            return False

        # 限幅
        x = max(-self.max_mickey, min(self.max_mickey, x))
        y = max(-self.max_mickey, min(self.max_mickey, y))

        # 填充结构体
        self._mouse_req.x = x
        self._mouse_req.y = y
        self._mouse_req.button_flags = button_flags

        try:
            win32file.DeviceIoControl(
                self.driver_handle,
                self.mouse_request_code,
                bytes(self._mouse_req),
                0,
                None,
            )
            return True
        except Exception as e:
            utils.log(f"[DriverMouse] 驱动调用失败: {e}")
            return False

    def _do_close(self):
        """关闭驱动句柄"""
        if self.driver_handle:
            try:
                win32file.CloseHandle(self.driver_handle)
            except Exception as e:
                utils.log(f"[DriverMouse] 关闭驱动句柄失败: {e}")
            finally:
                self.driver_handle = None
