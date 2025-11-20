import hashlib
import hmac
import time
import uuid
from typing import Optional, Tuple
import requests
import platform
import socket


class LicenseAuthenticator:
    """许可证验证器 - 集成到你的应用中"""

    def __init__(self, server_url: str, secret_key: str, app_name: str = "MyApp"):
        """
        初始化验证器

        Args:
            server_url: 服务器地址，例如 "http://1.14.184.43:45000"
            secret_key: 与服务器约定的密钥
            app_name: 应用名称（可选）
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

    def _generate_machine_code(self) -> str:
        """
        生成机器码 - 基于硬件信息
        包含: 计算机名称 + MAC地址 + 操作系统
        """
        try:
            # 获取计算机名称
            hostname = socket.gethostname()

            # 获取MAC地址
            mac_address = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff)
                                    for elements in range(0, 2 * 6, 8)][::-1])

            # 获取操作系统信息
            system = platform.system()

            # 组合信息
            machine_info = f"{hostname}|{mac_address}|{system}"

            # 生成机器码哈希
            machine_code = hashlib.sha256(machine_info.encode()).hexdigest()

            print(f"[LicenseAuth] 机器码已生成: {machine_code[:16]}...")
            return machine_code

        except Exception as e:
            print(f"[LicenseAuth] 生成机器码失败: {e}，使用UUID替代")
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
        # 签名数据中使用machine_code而不是device_id
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

                # 保存验证信息
                self.card_key = card_key
                self.is_authenticated = True
                self.expire_date = result.get('expire_date')
                self.max_devices = result.get('max_devices')

                # 同步服务器时间
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
        """
        发送心跳保持在线状态

        Returns:
            是否成功
        """
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
