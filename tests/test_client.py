import requests
import time
import threading
import uuid
from datetime import datetime
from typing import Optional

# 🆕 服务器配置
SERVER_URL = "http://1.14.184.43:45000"  # 修改为你的服务器地址
ADMIN_KEY = "change_me_in_production"  # 如果修改了管理员密钥也在这里改


class LicenseClient:
    """许可证客户端类"""

    def __init__(self, server_url: str = SERVER_URL):
        self.server_url = server_url.rstrip('/')
        self.card_key: Optional[str] = None
        self.device_id = str(uuid.uuid4())  # 生成唯一设备ID
        self.is_online = False
        self.heartbeat_thread: Optional[threading.Thread] = None

    def verify_login(self, card_key: str) -> dict:
        """登录验证"""
        url = f"{self.server_url}/verify"
        data = {
            "card_key": card_key,
            "device_id": self.device_id
        }

        try:
            response = requests.post(url, json=data)
            if response.status_code == 200:
                self.card_key = card_key
                self.is_online = True
                print(f"✅ 登录成功!")
                print(f"   卡密: {card_key}")
                print(f"   设备ID: {self.device_id}")
                print(f"   过期时间: {response.json()['expire_date']}")
                print(f"   最大设备数: {response.json()['max_devices']}")
                print(f"   当前在线: {response.json()['current_online']}")
                return response.json()
            else:
                print(f"❌ 登录失败: {response.json()['detail']}")
                return {"error": response.json()['detail']}
        except Exception as e:
            print(f"❌ 连接错误: {str(e)}")
            return {"error": str(e)}

    def send_heartbeat(self) -> bool:
        """发送心跳"""
        if not self.card_key or not self.is_online:
            return False

        url = f"{self.server_url}/heartbeat"
        data = {
            "card_key": self.card_key,
            "device_id": self.device_id
        }

        try:
            response = requests.post(url, json=data)
            if response.status_code == 200:
                return True
            else:
                print(f"⚠️ 心跳失败: {response.json()['detail']}")
                self.is_online = False
                return False
        except Exception as e:
            print(f"⚠️ 心跳错误: {str(e)}")
            return False

    def logout(self):
        """登出"""
        if not self.card_key:
            return

        url = f"{self.server_url}/logout"
        data = {
            "card_key": self.card_key,
            "device_id": self.device_id
        }

        try:
            response = requests.post(url, json=data)
            if response.status_code == 200:
                print(f"✅ 登出成功")
                self.is_online = False
                self.card_key = None
        except Exception as e:
            print(f"❌ 登出错误: {str(e)}")

    def start_heartbeat(self, interval: int = 30):
        """启动心跳线程"""

        def heartbeat_worker():
            while self.is_online:
                time.sleep(interval)
                if self.is_online:
                    success = self.send_heartbeat()
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    if success:
                        print(f"💓 [{timestamp}] 心跳成功")
                    else:
                        print(f"💔 [{timestamp}] 心跳失败，停止心跳")
                        break

        self.heartbeat_thread = threading.Thread(target=heartbeat_worker, daemon=True)
        self.heartbeat_thread.start()
        print(f"💓 心跳线程已启动 (间隔: {interval}秒)")


class AdminClient:
    """管理员客户端类"""

    def __init__(self, server_url: str = SERVER_URL, admin_key: str = ADMIN_KEY):
        self.server_url = server_url.rstrip('/')
        self.admin_key = admin_key

    def create_license(self, days: int = 30, max_devices: int = 1) -> dict:
        """创建卡密"""
        url = f"{self.server_url}/admin/create"
        data = {
            "days": days,
            "max_devices": max_devices,
            "admin_key": self.admin_key
        }

        try:
            response = requests.post(url, json=data)
            if response.status_code == 200:
                result = response.json()
                print(f"✅ 卡密创建成功!")
                print(f"   卡密: {result['card_key']}")
                print(f"   过期时间: {result['expire_date']}")
                print(f"   最大设备数: {result['max_devices']}")
                return result
            else:
                print(f"❌ 创建失败: {response.json()['detail']}")
                return {}
        except Exception as e:
            print(f"❌ 连接错误: {str(e)}")
            return {}

    def list_licenses(self):
        """列出所有卡密"""
        url = f"{self.server_url}/admin/list"
        params = {"admin_key": self.admin_key}

        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                licenses = response.json()['licenses']
                print(f"\n📋 卡密列表 (共 {len(licenses)} 个):")
                print("-" * 100)
                for i, lic in enumerate(licenses, 1):
                    status = "🚫已封禁" if lic['is_banned'] else "✅正常"
                    online = f"🟢在线({lic['current_online']}/{lic['max_devices']})" if lic[
                                                                                           'current_online'] > 0 else "⚪离线"
                    print(f"{i}. {lic['card_key']}")
                    print(f"   状态: {status} | {online}")
                    print(f"   过期: {lic['expire_date']}")
                    print(f"   设备: {lic['device_id'] or '未绑定'}")
                    print(f"   最后登录: {lic['last_login'] or '从未登录'}")
                    print()
            else:
                print(f"❌ 查询失败: {response.json()['detail']}")
        except Exception as e:
            print(f"❌ 连接错误: {str(e)}")

    def get_online_devices(self):
        """查看在线设备"""
        url = f"{self.server_url}/admin/online"
        params = {"admin_key": self.admin_key}

        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                result = response.json()
                devices = result['online_devices']
                print(f"\n🟢 在线设备 (共 {result['total']} 个):")
                print("-" * 100)
                for i, dev in enumerate(devices, 1):
                    print(f"{i}. 卡密: {dev['card_key']}")
                    print(f"   设备ID: {dev['device_id']}")
                    print(f"   最后心跳: {dev['last_heartbeat']}")
                    print(f"   在线时长: {dev['online_duration']}")
                    print()
            else:
                print(f"❌ 查询失败: {response.json()['detail']}")
        except Exception as e:
            print(f"❌ 连接错误: {str(e)}")

    def ban_license(self, card_key: str):
        """封禁卡密"""
        url = f"{self.server_url}/admin/ban"
        params = {
            "card_key": card_key,
            "admin_key": self.admin_key
        }

        try:
            response = requests.post(url, params=params)
            if response.status_code == 200:
                print(f"✅ 卡密已封禁: {card_key}")
            else:
                print(f"❌ 封禁失败: {response.json()['detail']}")
        except Exception as e:
            print(f"❌ 连接错误: {str(e)}")

    def kick_device(self, card_key: str, device_id: str):
        """踢出设备"""
        url = f"{self.server_url}/admin/kick"
        params = {
            "card_key": card_key,
            "device_id": device_id,
            "admin_key": self.admin_key
        }

        try:
            response = requests.post(url, params=params)
            if response.status_code == 200:
                print(f"✅ 设备已踢出")
            else:
                print(f"❌ 踢出失败: {response.json()['detail']}")
        except Exception as e:
            print(f"❌ 连接错误: {str(e)}")


def test_connection():
    """测试服务器连接"""
    print("\n正在测试服务器连接...")
    print(f"服务器地址: {SERVER_URL}")

    try:
        response = requests.get(f"{SERVER_URL}/", timeout=5)
        if response.status_code == 200:
            print("✅ 服务器连接成功!")
            data = response.json()
            print(f"   在线用户: {data['online_users']}")
            print(f"   在线设备: {data['total_devices']}")
            return True
        else:
            print(f"❌ 服务器响应异常: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务器，请检查:")
        print("   1. 服务器是否正在运行")
        print("   2. 服务器 IP 地址是否正确")
        print("   3. 防火墙是否开放 45000 端口")
        print("   4. 云服务器安全组是否配置正确")
        return False
    except requests.exceptions.Timeout:
        print("❌ 连接超时，服务器可能响应过慢")
        return False
    except Exception as e:
        print(f"❌ 连接错误: {str(e)}")
        return False


def test_scenario_1():
    """测试场景1: 基础登录和心跳"""
    print("\n" + "=" * 50)
    print("测试场景1: 基础登录和心跳")
    print("=" * 50)

    # 创建管理员客户端
    admin = AdminClient()

    # 创建一个卡密
    license_info = admin.create_license(days=30, max_devices=1)
    if not license_info:
        return

    card_key = license_info['card_key']

    # 创建客户端并登录
    client = LicenseClient()
    client.verify_login(card_key)

    # 启动心跳
    client.start_heartbeat(interval=10)

    # 保持在线30秒
    print("\n⏳ 保持在线30秒...")
    time.sleep(30)

    # 登出
    client.logout()


def test_scenario_2():
    """测试场景2: 多设备登录限制"""
    print("\n" + "=" * 50)
    print("测试场景2: 多设备登录限制")
    print("=" * 50)

    admin = AdminClient()

    # 创建只允许1个设备的卡密
    license_info = admin.create_license(days=30, max_devices=1)
    if not license_info:
        return

    card_key = license_info['card_key']

    # 第一个设备登录
    client1 = LicenseClient()
    print("\n--- 设备1尝试登录 ---")
    client1.verify_login(card_key)
    client1.start_heartbeat(interval=10)

    time.sleep(2)

    # 第二个设备尝试登录
    client2 = LicenseClient()
    print("\n--- 设备2尝试登录 (应该失败) ---")
    client2.verify_login(card_key)

    time.sleep(5)

    # 设备1登出
    print("\n--- 设备1登出 ---")
    client1.logout()

    time.sleep(2)

    # 设备2再次尝试登录
    print("\n--- 设备2再次尝试登录 (应该成功) ---")
    client2.verify_login(card_key)
    client2.start_heartbeat(interval=10)

    time.sleep(10)
    client2.logout()


def test_scenario_3():
    """测试场景3: 管理员功能测试"""
    print("\n" + "=" * 50)
    print("测试场景3: 管理员功能测试")
    print("=" * 50)

    admin = AdminClient()

    # 创建多个卡密
    print("\n--- 创建3个卡密 ---")
    licenses = []
    for i in range(3):
        lic = admin.create_license(days=30, max_devices=2)
        if lic:
            licenses.append(lic['card_key'])
        time.sleep(0.5)

    # 模拟多个客户端登录
    print("\n--- 模拟3个客户端登录 ---")
    clients = []
    for i, card_key in enumerate(licenses):
        client = LicenseClient()
        client.verify_login(card_key)
        client.start_heartbeat(interval=10)
        clients.append(client)
        time.sleep(1)

    time.sleep(5)

    # 查看在线设备
    print("\n--- 查看在线设备 ---")
    admin.get_online_devices()

    # 查看所有卡密
    print("\n--- 查看所有卡密 ---")
    admin.list_licenses()

    # 封禁第一个卡密
    if licenses:
        print(f"\n--- 封禁卡密: {licenses[0]} ---")
        admin.ban_license(licenses[0])

    time.sleep(5)

    # 清理
    for client in clients:
        client.logout()


def interactive_mode():
    """交互式测试模式"""
    print("\n" + "=" * 50)
    print("交互式测试工具")
    print("=" * 50)

    admin = AdminClient()
    client = LicenseClient()

    while True:
        print("\n--- 菜单 ---")
        print("1. 创建卡密")
        print("2. 登录")
        print("3. 登出")
        print("4. 查看所有卡密")
        print("5. 查看在线设备")
        print("6. 封禁卡密")
        print("7. 踢出设备")
        print("8. 测试服务器连接")
        print("0. 退出")

        choice = input("\n请选择: ").strip()

        if choice == "1":
            days = int(input("有效期(天): ") or "30")
            max_devices = int(input("最大设备数: ") or "1")
            admin.create_license(days, max_devices)

        elif choice == "2":
            card_key = input("输入卡密: ").strip()
            result = client.verify_login(card_key)
            if result.get('status') == 'success':
                client.start_heartbeat(interval=30)

        elif choice == "3":
            client.logout()

        elif choice == "4":
            admin.list_licenses()

        elif choice == "5":
            admin.get_online_devices()

        elif choice == "6":
            card_key = input("输入要封禁的卡密: ").strip()
            admin.ban_license(card_key)

        elif choice == "7":
            card_key = input("输入卡密: ").strip()
            device_id = input("输入设备ID: ").strip()
            admin.kick_device(card_key, device_id)

        elif choice == "8":
            test_connection()

        elif choice == "0":
            client.logout()
            break


if __name__ == "__main__":
    print("=" * 50)
    print("许可证服务器测试工具")
    print("=" * 50)
    print(f"服务器地址: {SERVER_URL}")
    print(f"管理员密钥: {ADMIN_KEY}")

    # 🆕 先测试连接
    if not test_connection():
        print("\n⚠️ 无法连接到服务器，请解决连接问题后再试")
        input("\n按回车键退出...")
        exit(1)

    print("\n选择测试模式:")
    print("1. 基础登录和心跳测试")
    print("2. 多设备限制测试")
    print("3. 管理员功能测试")
    print("4. 交互式模式")

    mode = input("\n请选择(1-4): ").strip()

    if mode == "1":
        test_scenario_1()
    elif mode == "2":
        test_scenario_2()
    elif mode == "3":
        test_scenario_3()
    elif mode == "4":
        interactive_mode()
    else:
        print("无效选择")
