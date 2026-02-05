"""客户端许可证验证器 - 仅保留验证功能"""

import hashlib
import hmac
import time
import uuid
from typing import Optional, Tuple
import requests
import platform
import subprocess
import os

# ==================== 配置区域 ====================
SERVER_URL = "http://1.14.184.43:45000"
SECRET_KEY = "your_secret_key_change_this"
APP_NAME = "MyApp"
# =================================================


class LicenseAuthenticator:
    """许可证验证器 - 客户端版本（无管理功能）"""

    def __init__(self, server_url: str = SERVER_URL, secret_key: str = SECRET_KEY, app_name: str = APP_NAME):
        """
        初始化验证器

        Args:
            server_url: 服务器地址
            secret_key: 与服务器约定的密钥
            app_name: 应用名称
        """
        self.server_url = server_url.rstrip('/')
        self.secret_key = secret_key
        self.app_name = app_name

        # 获取机器码
        self.machine_code = self._generate_machine_code()

        # 当前登录状态
        self.card_key: Optional[str] = None
        self.is_authenticated = False
        self.server_time_offset = 0

        # 许可证信息
        self.expire_date: Optional[str] = None
        self.max_devices: Optional[int] = None

    def _get_hardware_info_windows(self) -> dict:
        """获取 Windows 硬件信息"""
        hardware_info = {
            'disk_id': '',
            'motherboard_serial': '',
            'cpu_id': ''
        }

        # 获取硬盘序列号
        try:
            result = subprocess.check_output(
                'wmic diskdrive get serialnumber',
                shell=True,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            ).decode('utf-8', errors='ignore').strip()
            lines = [line.strip() for line in result.split('\n') if line.strip()]
            if len(lines) > 1 and lines[1]:
                hardware_info['disk_id'] = lines[1]
        except:
            try:
                ps_command = "Get-PhysicalDisk | Select-Object -First 1 -ExpandProperty SerialNumber"
                result = subprocess.check_output(
                    ['powershell', '-Command', ps_command],
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                ).decode('utf-8', errors='ignore').strip()
                if result:
                    hardware_info['disk_id'] = result
            except:
                pass

        # 获取主板序列号
        try:
            result = subprocess.check_output(
                'wmic baseboard get serialnumber',
                shell=True,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            ).decode('utf-8', errors='ignore').strip()
            lines = [line.strip() for line in result.split('\n') if line.strip()]
            if len(lines) > 1 and lines[1]:
                hardware_info['motherboard_serial'] = lines[1]
        except:
            try:
                ps_command = "Get-CimInstance Win32_BaseBoard | Select-Object -ExpandProperty SerialNumber"
                result = subprocess.check_output(
                    ['powershell', '-Command', ps_command],
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                ).decode('utf-8', errors='ignore').strip()
                if result:
                    hardware_info['motherboard_serial'] = result
            except:
                pass

        # 获取CPU信息
        try:
            result = subprocess.check_output(
                'wmic cpu get processorid',
                shell=True,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            ).decode('utf-8', errors='ignore').strip()
            lines = [line.strip() for line in result.split('\n') if line.strip()]
            if len(lines) > 1 and lines[1]:
                hardware_info['cpu_id'] = lines[1]
        except:
            try:
                ps_command = "Get-CimInstance Win32_Processor | Select-Object -ExpandProperty Name"
                result = subprocess.check_output(
                    ['powershell', '-Command', ps_command],
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                ).decode('utf-8', errors='ignore').strip()
                if result:
                    hardware_info['cpu_id'] = result
            except:
                try:
                    cpu_info = f"{platform.processor()}_{os.cpu_count()}"
                    hardware_info['cpu_id'] = cpu_info
                except:
                    pass

        return hardware_info

    def _get_hardware_info_linux(self) -> dict:
        """获取 Linux 硬件信息"""
        hardware_info = {
            'disk_id': '',
            'motherboard_serial': '',
            'cpu_id': ''
        }

        try:
            result = subprocess.check_output(
                "lsblk -d -o serial | grep -v SERIAL | head -n 1",
                shell=True,
                stderr=subprocess.DEVNULL
            ).decode('utf-8').strip()
            hardware_info['disk_id'] = result
        except:
            pass

        try:
            result = subprocess.check_output(
                "cat /sys/class/dmi/id/board_serial 2>/dev/null || sudo dmidecode -s baseboard-serial-number 2>/dev/null",
                shell=True,
                stderr=subprocess.DEVNULL
            ).decode('utf-8').strip()
            hardware_info['motherboard_serial'] = result
        except:
            pass

        try:
            result = subprocess.check_output(
                "cat /proc/cpuinfo | grep 'model name' | head -n 1 | cut -d ':' -f 2",
                shell=True,
                stderr=subprocess.DEVNULL
            ).decode('utf-8').strip()
            hardware_info['cpu_id'] = result
        except:
            pass

        return hardware_info

    def _get_hardware_info_macos(self) -> dict:
        """获取 macOS 硬件信息"""
        hardware_info = {
            'disk_id': '',
            'motherboard_serial': '',
            'cpu_id': ''
        }

        try:
            result = subprocess.check_output(
                "system_profiler SPSerialATADataType | grep 'Serial Number' | head -n 1",
                shell=True,
                stderr=subprocess.DEVNULL
            ).decode('utf-8').strip()
            if ':' in result:
                hardware_info['disk_id'] = result.split(':')[1].strip()
        except:
            pass

        try:
            result = subprocess.check_output(
                "system_profiler SPHardwareDataType | grep 'Serial Number'",
                shell=True,
                stderr=subprocess.DEVNULL
            ).decode('utf-8').strip()
            if ':' in result:
                hardware_info['motherboard_serial'] = result.split(':')[1].strip()
        except:
            pass

        try:
            result = subprocess.check_output(
                "sysctl -n machdep.cpu.brand_string",
                shell=True,
                stderr=subprocess.DEVNULL
            ).decode('utf-8').strip()
            hardware_info['cpu_id'] = result
        except:
            pass

        return hardware_info

    def _get_hardware_info(self) -> dict:
        """获取硬件信息"""
        system = platform.system()

        if system == "Windows":
            return self._get_hardware_info_windows()
        elif system == "Linux":
            return self._get_hardware_info_linux()
        elif system == "Darwin":
            return self._get_hardware_info_macos()
        else:
            return {'disk_id': '', 'motherboard_serial': '', 'cpu_id': ''}

    def _generate_machine_code(self) -> str:
        """生成机器码"""
        try:
            hardware_info = self._get_hardware_info()
            machine_info = f"{hardware_info['disk_id']}|{hardware_info['motherboard_serial']}|{hardware_info['cpu_id']}"

            if not any(hardware_info.values()):
                machine_code = str(uuid.uuid4())
            else:
                machine_code = hashlib.sha256(machine_info.encode()).hexdigest()

            return machine_code

        except Exception as e:
            return str(uuid.uuid4())

    def _generate_signature(self, data: str, timestamp: int) -> str:
        """生成HMAC-SHA256签名"""
        message = f"{data}|{timestamp}"
        return hmac.new(
            self.secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()

    def _get_timestamp(self) -> int:
        """获取同步后的时间戳"""
        return int(time.time()) + self.server_time_offset

    def _sync_server_time(self, server_time: int):
        """同步服务器时间"""
        local_time = int(time.time())
        self.server_time_offset = server_time - local_time

    def verify(self, card_key: str) -> Tuple[bool, str]:
        """
        验证卡密

        Args:
            card_key: 用户输入的卡密

        Returns:
            (是否成功, 消息)
        """
        timestamp = self._get_timestamp()
        data = f"{card_key}|{self.machine_code}"
        signature = self._generate_signature(data, timestamp)

        url = f"{self.server_url}/verify"
        request_data = {
            "card_key": card_key,
            "machine_code": self.machine_code,
            "timestamp": timestamp,
            "signature": signature
        }

        try:
            response = requests.post(url, json=request_data, timeout=10)

            if response.status_code == 200:
                result = response.json()

                self.card_key = card_key
                self.is_authenticated = True
                self.expire_date = result.get('expire_date')
                self.max_devices = result.get('max_devices')

                if 'server_time' in result:
                    self._sync_server_time(result['server_time'])

                return True, f"验证成功，过期时间: {self.expire_date}"

            elif response.status_code == 429:
                return False, "请求过于频繁，请稍后再试"
            else:
                error_msg = response.json().get('detail', '未知错误')
                return False, f"验证失败: {error_msg}"

        except requests.exceptions.ConnectionError:
            return False, "无法连接到服务器"
        except requests.exceptions.Timeout:
            return False, "连接超时"
        except Exception as e:
            return False, f"验证错误: {str(e)}"

    def send_heartbeat(self) -> bool:
        """发送心跳保持在线状态"""
        if not self.is_authenticated or not self.card_key:
            return False

        timestamp = self._get_timestamp()
        data = f"{self.card_key}|{self.machine_code}"
        signature = self._generate_signature(data, timestamp)

        url = f"{self.server_url}/heartbeat"
        request_data = {
            "card_key": self.card_key,
            "machine_code": self.machine_code,
            "timestamp": timestamp,
            "signature": signature
        }

        try:
            response = requests.post(url, json=request_data, timeout=5)
            if response.status_code == 200:
                result = response.json()
                if 'server_time' in result:
                    self._sync_server_time(result['server_time'])
                return True
            else:
                self.is_authenticated = False
                return False
        except:
            return False

    def logout(self) -> bool:
        """登出"""
        if not self.card_key:
            return True

        timestamp = self._get_timestamp()
        data = f"{self.card_key}|{self.machine_code}"
        signature = self._generate_signature(data, timestamp)

        url = f"{self.server_url}/logout"
        request_data = {
            "card_key": self.card_key,
            "machine_code": self.machine_code,
            "timestamp": timestamp,
            "signature": signature
        }

        try:
            requests.post(url, json=request_data, timeout=5)
        except:
            pass

        self.is_authenticated = False
        self.card_key = None
        return True

    def is_valid(self) -> bool:
        """检查当前是否已验证"""
        return self.is_authenticated

    def get_machine_code(self) -> str:
        """获取机器码（用于显示给用户）"""
        return self.machine_code
