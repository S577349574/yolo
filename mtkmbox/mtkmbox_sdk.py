"""
MTKMBOX 硬件 SDK 封装
基于串口直接通信，无需额外依赖
"""
import serial
import time
import threading
from typing import Optional, Dict, Tuple
import logging


class MTKMBOXError(Exception):
    """MTKMBOX 错误基类"""
    pass


class MTKMBOXConnectionError(MTKMBOXError):
    """连接错误"""
    pass


class MTKMBOXCommandError(MTKMBOXError):
    """命令执行错误"""
    pass


class MTKMBOX:
    """MTKMBOX 硬件控制器"""

    # 按键代码映射
    BUTTON_MAP = {
        'left': {'press': 'km.left(1)', 'release': 'km.left(0)', 'state': 'km.left()'},
        'right': {'press': 'km.right(1)', 'release': 'km.right(0)', 'state': 'km.right()'},
        'middle': {'press': 'km.middle(1)', 'release': 'km.middle(0)', 'state': 'km.middle()'},
        'x1': {'press': 'km.side1(1)', 'release': 'km.side1(0)', 'state': 'km.side1()'},
        'x2': {'press': 'km.side2(1)', 'release': 'km.side2(0)', 'state': 'km.side2()'},
    }

    def __init__(
            self,
            port: Optional[str] = None,
            vid: int = 0x0416,
            pid: int = 0x5020,
            baudrate: int = 115200,
            timeout: float = 0.1,
            debug: bool = False
    ):
        """
        初始化 MTKMBOX 控制器

        Args:
            port: 串口号（如 'COM3'），None 表示自动检测
            vid: USB VID（十进制）
            pid: USB PID（十进制）
            baudrate: 波特率
            timeout: 串口超时时间
            debug: 调试模式
        """
        self.port = port
        self.vid = vid
        self.pid = pid
        self.baudrate = baudrate
        self.timeout = timeout
        self.debug = debug

        self.ser: Optional[serial.Serial] = None
        self._lock = threading.Lock()  # 串口操作锁
        self._connected = False

        # 设置日志
        self.logger = logging.getLogger('MTKMBOX')
        if debug:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)

        # 自动连接
        self._connect()

    def _connect(self):
        """连接设备"""
        if self.port:
            # 使用指定端口
            ports_to_try = [self.port]
        else:
            # 自动检测端口
            ports_to_try = self._find_ports()

        if not ports_to_try:
            raise MTKMBOXConnectionError("未找到可用的串口设备")

        # 尝试连接
        last_error = None
        for port_name in ports_to_try:
            try:
                self.logger.info(f"尝试连接端口: {port_name}")
                self.ser = serial.Serial(
                    port=port_name,
                    baudrate=self.baudrate,
                    timeout=self.timeout
                )
                time.sleep(0.1)  # 等待设备稳定

                # 初始化 km 模块
                self._send_command('import km', wait_response=False)
                time.sleep(0.1)

                # 验证连接
                response = self._send_command('km.left()')
                if response is not None:
                    self._connected = True
                    self.port = port_name
                    self.logger.info(f"✅ 已连接到设备: {port_name}")
                    return
                else:
                    self.ser.close()
                    self.logger.warning(f"端口 {port_name} 无响应")

            except Exception as e:
                last_error = e
                self.logger.debug(f"连接 {port_name} 失败: {e}")
                if self.ser and self.ser.is_open:
                    self.ser.close()

        raise MTKMBOXConnectionError(
            f"无法连接到 MTKMBOX 设备。最后错误: {last_error}"
        )

    def _find_ports(self) -> list:
        """自动检测可用串口（优先匹配 VID/PID）"""
        try:
            import serial.tools.list_ports

            matched_ports = []  # VID/PID 匹配的端口
            other_ports = []  # 其他端口

            for port in serial.tools.list_ports.comports():
                # 打印调试信息
                if self.debug:
                    self.logger.debug(
                        f"发现端口: {port.device} | "
                        f"VID={port.vid} PID={port.pid} | "
                        f"描述={port.description}"
                    )

                # 优先匹配 VID/PID
                if port.vid == self.vid and port.pid == self.pid:
                    matched_ports.append(port.device)
                    self.logger.info(f"✅ VID/PID 匹配: {port.device}")
                else:
                    other_ports.append(port.device)

            # 匹配的端口优先
            return matched_ports + other_ports

        except Exception as e:
            self.logger.warning(f"端口扫描失败: {e}")
            return []

    # mtkmbox_sdk.py 改进
    def _send_command(self, command: str, wait_response: bool = True) -> Optional[str]:
        """简化版：移除重试循环（对于鼠标移动不需要）"""
        if not self.ser or not self.ser.is_open:
            raise MTKMBOXCommandError("串口未打开")

        with self._lock:
            try:
                self.ser.reset_input_buffer()
                self.ser.write(f'{command}\r\n'.encode('utf-8'))

                if not wait_response:
                    return None

                # ⭐ 使用非阻塞读取 + 短暂重试
                for _ in range(5):  # 最多等待 5 次
                    if self.ser.in_waiting > 0:
                        response = self.ser.read(self.ser.in_waiting)
                        return self._clean_response(response.decode('utf-8', errors='ignore'))
                    time.sleep(0.002)  # 2ms 轮询间隔

                return None  # 超时无响应

            except Exception as e:
                raise MTKMBOXCommandError(f"命令执行失败: {e}")

    def _clean_response(self, raw_response: str) -> str:
        """
        清理串口响应，提取有效数据

        Args:
            raw_response: 原始响应字符串

        Returns:
            str: 清理后的有效数据
        """
        import re

        # 移除提示符和特殊字符
        response = raw_response.replace('>>>', '').replace('\r', '').strip()

        # 按行分割
        lines = [line.strip() for line in response.split('\n') if line.strip()]

        if not lines:
            return ""

        # ⭐ 移除所有包含 'km.' 的行（命令回显）
        lines = [line for line in lines if not line.startswith('km.')]

        # ⭐ 优先返回纯数字行
        for line in lines:
            if re.match(r'^-?\d+$', line):
                return line

        # 返回最后一行
        return lines[-1] if lines else ""

    # ==================== 公共 API ====================

    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._connected and self.ser is not None and self.ser.is_open

    def move(self, dx: int, dy: int) -> bool:
        """
        移动鼠标

        Args:
            dx: X 方向移动量（-127 到 127）
            dy: Y 方向移动量（-127 到 127）

        Returns:
            bool: 是否成功
        """
        try:
            # 限制范围
            dx = max(-127, min(127, dx))
            dy = max(-127, min(127, dy))

            self._send_command(f'km.move({dx},{dy})', wait_response=False)
            return True
        except Exception as e:
            self.logger.error(f"移动失败: {e}")
            return False

    def press(self, button: str) -> bool:
        """
        按下按键

        Args:
            button: 'left', 'right', 'middle', 'x1', 'x2'

        Returns:
            bool: 是否成功
        """
        if button not in self.BUTTON_MAP:
            raise ValueError(f"未知按键: {button}")

        try:
            cmd = self.BUTTON_MAP[button]['press']
            self._send_command(cmd, wait_response=False)
            return True
        except Exception as e:
            self.logger.error(f"按下按键失败 ({button}): {e}")
            return False

    def release(self, button: str) -> bool:
        """
        释放按键

        Args:
            button: 'left', 'right', 'middle', 'x1', 'x2'

        Returns:
            bool: 是否成功
        """
        if button not in self.BUTTON_MAP:
            raise ValueError(f"未知按键: {button}")

        try:
            cmd = self.BUTTON_MAP[button]['release']
            self._send_command(cmd, wait_response=False)
            return True
        except Exception as e:
            self.logger.error(f"释放按键失败 ({button}): {e}")
            return False

    def click(self, button: str = 'left', delay: float = 0.05) -> bool:
        """
        点击按键

        Args:
            button: 按键名称
            delay: 按下和释放之间的延迟（秒）

        Returns:
            bool: 是否成功
        """
        if not self.press(button):
            return False
        time.sleep(delay)
        return self.release(button)

    def get_button_state(self, button: str) -> int:
        """
        获取按键状态

        Args:
            button: 按键名称

        Returns:
            int: 1=按下, 0=松开, -1=错误
        """
        if button not in self.BUTTON_MAP:
            raise ValueError(f"未知按键: {button}")

        try:
            cmd = self.BUTTON_MAP[button]['state']
            response = self._send_command(cmd)

            if response is None or response == "":
                return -1

            # ⭐ 添加：尝试从响应中提取数字
            import re
            match = re.search(r'\b([01])\b', response)
            if match:
                return int(match.group(1))

            # 如果没有匹配到 0 或 1，尝试直接转换
            return int(response)

        except ValueError as e:
            self.logger.error(f"解析按键状态失败 ({button}): {response} -> {e}")
            return -1
        except Exception as e:
            self.logger.error(f"获取按键状态失败 ({button}): {e}")
            return -1

    def get_device_info(self) -> Dict:
        """
        获取设备信息

        Returns:
            dict: 设备信息字典
        """
        return {
            'port': self.port,
            'vid': f"0x{self.vid:04X}",
            'pid': f"0x{self.pid:04X}",
            'baudrate': self.baudrate,
            'connected': self._connected,
            'version': 'MTKMBOX v1.0'  # 如有版本查询命令可替换
        }

    def close(self):
        """关闭连接"""
        if self.ser and self.ser.is_open:
            try:
                # 释放所有按键
                for button in self.BUTTON_MAP.keys():
                    try:
                        self.release(button)
                    except:
                        pass

                self.ser.close()
                self._connected = False
                self.logger.info("设备已断开")
            except Exception as e:
                self.logger.error(f"关闭串口时出错: {e}")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.close()
        return False

    def __del__(self):
        """析构函数"""
        self.close()
