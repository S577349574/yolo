"""管理员客户端 - 完整功能（不打包到客户端）"""

import time
from datetime import datetime
import requests

# ==================== 配置区域 ====================
SERVER_URL = "http://1.14.184.43:45000"
ADMIN_KEY = "change_me_in_production"
SECRET_KEY = "your_secret_key_change_this"
# =================================================


class AdminClient:
    """管理员客户端类"""

    def __init__(self, server_url: str = SERVER_URL, admin_key: str = ADMIN_KEY):
        self.server_url = server_url.rstrip('/')
        self.admin_key = admin_key

    def create_license(self, days: int = 30, max_devices: int = 1, remark: str = None) -> dict:
        """创建卡密"""
        url = f"{self.server_url}/admin/create"
        data = {
            "days": days,
            "max_devices": max_devices,
            "remark": remark,
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
                if result.get('remark'):
                    print(f"   备注: {result['remark']}")
                return result
            else:
                print(f"❌ 创建失败: {response.json()['detail']}")
                return {}
        except Exception as e:
            print(f"❌ 连接错误: {str(e)}")
            return {}

    def update_remark(self, card_key: str, remark: str):
        """更新卡密备注"""
        url = f"{self.server_url}/admin/update_remark"
        data = {
            "card_key": card_key,
            "remark": remark,
            "admin_key": self.admin_key
        }

        try:
            response = requests.post(url, json=data)
            if response.status_code == 200:
                print(f"✅ 备注已更新")
                print(f"   卡密: {card_key}")
                print(f"   新备注: {remark}")
            else:
                print(f"❌ 更新失败: {response.json()['detail']}")
        except Exception as e:
            print(f"❌ 连接错误: {str(e)}")

    def list_licenses(self):
        """列出所有卡密"""
        url = f"{self.server_url}/admin/list"
        params = {"admin_key": self.admin_key}

        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                licenses = response.json()['licenses']
                print(f"\n📋 卡密列表 (共 {len(licenses)} 个):")
                print("-" * 130)
                for i, lic in enumerate(licenses, 1):
                    status = "🚫已封禁" if lic['is_banned'] else "✅正常"
                    online = f"🟢在线({lic['current_online']}/{lic['max_devices']})" if lic['current_online'] > 0 else "⚪离线"

                    print(f"{i}. {lic['card_key']}")
                    print(f"   状态: {status} | {online}")
                    print(f"   过期: {lic['expire_date']}")
                    print(f"   机器码: {lic['machine_code'] if lic['machine_code'] else '未绑定'}")
                    if lic.get('remark'):
                        print(f"   备注: {lic['remark']}")
                    print(f"   失败尝试: {lic['login_attempts']}")
                    print(f"   最后登录: {lic['last_login'] or '从未登录'}")
                    print()
            else:
                print(f"❌ 查询失败: {response.json()['detail']}")
        except Exception as e:
            print(f"❌ 连接错误: {str(e)}")

    def list_valid_licenses(self):
        """列出有效卡密"""
        url = f"{self.server_url}/admin/list"
        params = {"admin_key": self.admin_key}

        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                all_licenses = response.json()['licenses']
                valid_licenses = []
                current_time = datetime.now()

                for lic in all_licenses:
                    if lic['is_banned']:
                        continue
                    try:
                        expire_date = datetime.fromisoformat(lic['expire_date'])
                        if expire_date < current_time:
                            continue
                    except:
                        continue
                    valid_licenses.append(lic)

                print(f"\n✅ 有效卡密列表 (共 {len(valid_licenses)} 个):")
                print("-" * 130)

                if not valid_licenses:
                    print("   暂无有效卡密")
                    return

                for i, lic in enumerate(valid_licenses, 1):
                    online = f"🟢在线({lic['current_online']}/{lic['max_devices']})" if lic['current_online'] > 0 else "⚪离线"
                    try:
                        expire_date = datetime.fromisoformat(lic['expire_date'])
                        remaining_days = (expire_date - current_time).days
                        expire_info = f"{lic['expire_date']} (剩余 {remaining_days} 天)"
                    except:
                        expire_info = lic['expire_date']

                    print(f"{i}. {lic['card_key']}")
                    print(f"   状态: {online}")
                    print(f"   过期: {expire_info}")
                    print(f"   机器码: {lic['machine_code'] if lic['machine_code'] else '未绑定'}")
                    if lic.get('remark'):
                        print(f"   备注: {lic['remark']}")
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
                print("-" * 120)
                for i, dev in enumerate(devices, 1):
                    print(f"{i}. 卡密: {dev['card_key']}")
                    print(f"   机器码: {dev['machine_code']}")
                    print(f"   最后心跳: {dev['last_heartbeat']}")
                    print(f"   在线时长: {dev['online_duration']}")
                    print()
            else:
                print(f"❌ 查询失败: {response.json()['detail']}")
        except Exception as e:
            print(f"❌ 连接错误: {str(e)}")

    def get_security_logs(self, limit: int = 50):
        """查看安全日志"""
        url = f"{self.server_url}/admin/security_logs"
        params = {"admin_key": self.admin_key, "limit": limit}

        try:
            response = requests.get(url, params=params)
            if response.status_code == 200:
                logs = response.json()['logs']
                print(f"\n🔒 安全日志 (最近 {len(logs)} 条):")
                print("-" * 130)

                if not logs:
                    print("   暂无安全事件")
                    return

                event_type_names = {
                    "replay_attack": "🔴 重放攻击",
                    "rate_limit": "⚠️ 请求限制",
                    "invalid_signature": "🔴 签名错误",
                    "machine_code_mismatch": "🔴 机器码不匹配"
                }

                for i, log in enumerate(logs, 1):
                    event_name = event_type_names.get(log['event_type'], log['event_type'])
                    print(f"{i}. {event_name}")
                    print(f"   时间: {log['event_time']}")
                    print(f"   IP: {log['ip_address']}")
                    print(f"   卡密: {log['card_key'] or 'N/A'}")
                    print(f"   机器码: {log['machine_code'] if log['machine_code'] else 'N/A'}")
                    print(f"   详情: {log['details'] or 'N/A'}")
                    print()
            else:
                print(f"❌ 查询失败: {response.json()['detail']}")
        except Exception as e:
            print(f"❌ 连接错误: {str(e)}")

    def ban_license(self, card_key: str):
        """封禁卡密"""
        url = f"{self.server_url}/admin/ban"
        params = {"card_key": card_key, "admin_key": self.admin_key}

        try:
            response = requests.post(url, params=params)
            if response.status_code == 200:
                print(f"✅ 卡密已封禁: {card_key}")
            else:
                print(f"❌ 封禁失败: {response.json()['detail']}")
        except Exception as e:
            print(f"❌ 连接错误: {str(e)}")

    def kick_device(self, card_key: str, machine_code: str):
        """踢出设备"""
        url = f"{self.server_url}/admin/kick"
        params = {"card_key": card_key, "machine_code": machine_code, "admin_key": self.admin_key}

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
            print(f"   版本: {data.get('version', 'unknown')}")
            print(f"   在线用户: {data['online_users']}")
            print(f"   在线设备: {data['total_devices']}")
            return True
        else:
            print(f"❌ 服务器响应异常: {response.status_code}")
            return False
    except:
        print("❌ 无法连接到服务器")
        return False


def interactive_mode():
    """交互式管理工具"""
    admin = AdminClient()

    while True:
        print("\n" + "=" * 50)
        print("管理员工具菜单")
        print("=" * 50)
        print("1. 创建卡密")
        print("2. 查看所有卡密")
        print("3. 查看有效卡密")
        print("4. 查看在线设备")
        print("5. 查看安全日志")
        print("6. 更新卡密备注")
        print("7. 封禁卡密")
        print("8. 踢出设备")
        print("9. 测试服务器连接")
        print("0. 退出")

        choice = input("\n请选择: ").strip()

        if choice == "1":
            days = int(input("有效期(天,默认30): ") or "30")
            max_devices = int(input("最大设备数(默认1): ") or "1")
            remark = input("备注(可选): ").strip() or None
            admin.create_license(days, max_devices, remark)
        elif choice == "2":
            admin.list_licenses()

        elif choice == "3":
            admin.list_valid_licenses()

        elif choice == "4":
            admin.get_online_devices()

        elif choice == "5":
            limit = int(input("显示条数(默认50): ") or "50")
            admin.get_security_logs(limit)

        elif choice == "6":
            card_key = input("输入卡密: ").strip()
            remark = input("输入新备注: ").strip()
            admin.update_remark(card_key, remark)

        elif choice == "7":
            card_key = input("输入要封禁的卡密: ").strip()
            confirm = input(f"确认封禁 {card_key}? (y/n): ").strip().lower()
            if confirm == 'y':
                admin.ban_license(card_key)

        elif choice == "8":
            card_key = input("输入卡密: ").strip()
            machine_code = input("输入机器码: ").strip()
            admin.kick_device(card_key, machine_code)

        elif choice == "9":
            test_connection()

        elif choice == "0":
            print("再见！")
            break

        else:
            print("❌ 无效选择，请重试")


if __name__ == "__main__":
    print("=" * 50)
    print("许可证管理工具 v2.0")
    print("=" * 50)
    print(f"服务器地址: {SERVER_URL}")
    print(f"管理员密钥: {ADMIN_KEY[:8]}...")
    print("=" * 50)

    if not test_connection():
        print("\n⚠️ 无法连接到服务器，请检查配置")
        input("\n按回车键退出...")
        exit(1)

    interactive_mode()

