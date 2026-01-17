import socket
import json

class CommandSender:
    """指令发送器：向游戏机 Agent 发送 UDP 控制指令"""
    def __init__(self, target_host: str, target_port: int = 27016):
        self.target_addr = (target_host, target_port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send_aim(self, dx: int, dy: int):
        """发送鼠标相对移动指令"""
        payload = {
            "action": "aim",
            "data": {"x": dx, "y": dy}
        }
        self._send(payload)

    def send_capture(self, width: int = 640, height: int = 640, label: str = "sample"):
        """触发 Agent 异步保存高质量截图"""
        payload = {
            "action": "capture",
            "width": width,
            "height": height,
            "label": label
        }
        self._send(payload)

    def _send(self, data: dict):
        try:
            msg = json.dumps(data).encode('utf-8')
            self.sock.sendto(msg, self.target_addr)
        except Exception as e:
            print(f"[CommandSender] 发送失败: {e}")

    def close(self):
        self.sock.close()
