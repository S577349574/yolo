import socket
import json

class CommandSender:
    """通用指令发送器：仅负责将字典数据序列化并发送"""
    def __init__(self, target_host: str, target_port: int = 27016):
        self.target_addr = (target_host, target_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send_custom(self, data: dict):
        """发送自定义字典数据包"""
        try:
            # 确保数据可以被 JSON 序列化
            msg = json.dumps(data).encode('utf-8')
            self.sock.sendto(msg, self.target_addr)
            return True
        except Exception as e:
            print(f"[CommandSender] 自定义包发送失败: {e}")
            return False

    def close(self):
        self.sock.close()
