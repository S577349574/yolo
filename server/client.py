import time
from datetime import datetime

import requests

from license_auth import LicenseAuthenticator

# 服务器配置
SERVER_URL = "http://1.14.184.43:45000"
ADMIN_KEY = "change_me_in_production"
SECRET_KEY = "your_secret_key_change_this"


class AdminClient:
    """管理员客户端类"""

    def __init__(self, server_url: str = SERVER_URL, admin_key: str = ADMIN_KEY):
        self.server_url = server_url.rstrip('/')
        self.admin_key = admin_key

    def create_license(self, days: int = 30, max_devices: int = 1,
                       remark: str = None) -> dict:
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
                    online = f"🟢在线({lic['current_online']}/{lic['max_devices']})" if lic[
                                                                                           'current_online'] > 0 else "⚪离线"

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
        """列出有效卡密（过滤掉已封禁和已过期的）"""
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
                    online = f"🟢在线({lic['current_online']}/{lic['max_devices']})" if lic[
                                                                                           'current_online'] > 0 else "⚪离线"

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
        params = {
            "admin_key": self.admin_key,
            "limit": limit
        }

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

    def kick_device(self, card_key: str, machine_code: str):
        """踢出设备"""
        url = f"{self.server_url}/admin/kick"
        params = {
            "card_key": card_key,
            "machine_code": machine_code,
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


def connection():
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


def scenario_1():
    """测试场景1: 基础登录和心跳"""
    print("\n" + "=" * 50)
    print("测试场景1: 基础登录和心跳")
    print("=" * 50)

    admin = AdminClient()
    license_info = admin.create_license(days=30, max_devices=1, remark="测试账号1")
    if not license_info:
        return

    card_key = license_info['card_key']

    auth = LicenseAuthenticator(SERVER_URL, SECRET_KEY)
    success, message = auth.verify(card_key)

    if success:
        print(f"✅ {message}")

        print("\n⏳ 保持在线30秒，每10秒发送一次心跳...")
        for i in range(3):
            time.sleep(10)
            if auth.send_heartbeat():
                print(f"💓 心跳#{i + 1} 成功")
            else:
                print(f"❌ 心跳#{i + 1} 失败")

        auth.logout()
        print("✅ 已登出")
    else:
        print(f"❌ {message}")


def scenario_2():
    """测试场景2: 多设备登录限制"""
    print("\n" + "=" * 50)
    print("测试场景2: 多设备登录限制（机器码绑定）")
    print("=" * 50)

    admin = AdminClient()
    license_info = admin.create_license(days=30, max_devices=1, remark="多设备测试")
    if not license_info:
        return

    card_key = license_info['card_key']

    print("\n--- 设备1尝试登录 ---")
    auth1 = LicenseAuthenticator(SERVER_URL, SECRET_KEY)
    success1, msg1 = auth1.verify(card_key)
    print(f"结果: {msg1}")
    print(f"设备1机器码: {auth1.machine_code}")

    if success1:
        time.sleep(2)

        print("\n--- 设备2尝试登录 (应该失败 - 机器码不同) ---")
        auth2 = LicenseAuthenticator(SERVER_URL, SECRET_KEY)
        success2, msg2 = auth2.verify(card_key)
        print(f"结果: {msg2}")
        print(f"设备2机器码: {auth2.machine_code}")

        if not success2:
            print("✅ 多设备限制生效，第二台设备登录被拒绝")
        else:
            print("⚠️ 多设备限制未生效")

        time.sleep(2)

        print("\n--- 设备1登出 ---")
        auth1.logout()
        print("✅ 设备1已登出")

        time.sleep(2)

        print("\n--- 设备2再次尝试登录 (应该成功) ---")
        success2_retry, msg2_retry = auth2.verify(card_key)
        print(f"结果: {msg2_retry}")

        if success2_retry:
            print("✅ 设备1登出后，设备2成功登录")
            auth2.logout()
        else:
            print("❌ 设备2仍然无法登录")


def scenario_3():
    """测试场景3: 管理员功能测试"""
    print("\n" + "=" * 50)
    print("测试场景3: 管理员功能测试（含安全日志）")
    print("=" * 50)

    admin = AdminClient()

    print("\n--- 创建3个卡密 ---")
    licenses = []
    for i in range(3):
        lic = admin.create_license(days=30, max_devices=2, remark=f"管理测试账号{i + 1}")
        if lic:
            licenses.append(lic['card_key'])
        time.sleep(0.5)

    print("\n--- 模拟3个客户端登录 ---")
    clients = []
    for i, card_key in enumerate(licenses):
        auth = LicenseAuthenticator(SERVER_URL, SECRET_KEY)
        success, msg = auth.verify(card_key)
        if success:
            clients.append(auth)
            print(f"✅ 客户端{i + 1}登录成功")
        time.sleep(1)

    time.sleep(5)

    print("\n--- 查看在线设备 ---")
    admin.get_online_devices()

    print("\n--- 查看所有卡密 ---")
    admin.list_licenses()

    print("\n--- 查看安全日志 ---")
    admin.get_security_logs(limit=20)

    if licenses:
        print(f"\n--- 更新卡密备注: {licenses[0][:8]}... ---")
        admin.update_remark(licenses[0], "已被修改的测试卡密")

    time.sleep(2)

    print("\n--- 再次查看卡密列表（验证备注更新） ---")
    admin.list_licenses()

    time.sleep(2)

    print("\n--- 所有客户端登出 ---")
    for i, auth in enumerate(clients):
        auth.logout()
        print(f"✅ 客户端{i + 1}已登出")


def scenario_4():
    """测试场景4: 安全防护测试"""
    print("\n" + "=" * 50)
    print("测试场景4: 安全防护测试")
    print("=" * 50)

    admin = AdminClient()

    print("\n--- 创建测试卡密 ---")
    license_info = admin.create_license(days=30, max_devices=1, remark="安全测试账号")
    if not license_info:
        return

    card_key = license_info['card_key']

    print("\n--- 测试1: 正常登录 ---")
    auth = LicenseAuthenticator(SERVER_URL, SECRET_KEY)
    success, message = auth.verify(card_key)

    if success:
        print("✅ 正常登录成功")
        time.sleep(2)
        auth.logout()
    else:
        print(f"❌ 登录失败: {message}")

    print("\n--- 测试2: 频率限制测试 ---")
    print("连续发送15次快速请求...")
    rate_limited = False
    for i in range(15):
        auth_temp = LicenseAuthenticator(SERVER_URL, SECRET_KEY)
        success, msg = auth_temp.verify(card_key)
        if "频繁" in msg or "429" in msg:
            print(f"✅ 第{i + 1}次请求被频率限制拦截")
            rate_limited = True
            break
        time.sleep(0.05)

    if not rate_limited:
        print("⚠️ 频率限制可能未启用或未触发")

    time.sleep(5)

    print("\n--- 查看安全日志 ---")
    admin.get_security_logs(limit=10)


def scenario_5():
    """测试场景5: 机器码一致性验证"""
    print("\n" + "=" * 50)
    print("测试场景5: 机器码一致性验证")
    print("=" * 50)

    admin = AdminClient()
    license_info = admin.create_license(days=30, max_devices=1, remark="机器码一致性测试")
    if not license_info:
        return

    card_key = license_info['card_key']

    print("\n--- 首次登录，绑定机器码 ---")
    auth1 = LicenseAuthenticator(SERVER_URL, SECRET_KEY)
    machine_code_1 = auth1.machine_code
    success1, msg1 = auth1.verify(card_key)
    print(f"结果: {msg1}")
    print(f"绑定机器码: {machine_code_1}")
    auth1.logout()

    time.sleep(2)

    print("\n--- 第二次登录，验证机器码一致性 ---")
    auth2 = LicenseAuthenticator(SERVER_URL, SECRET_KEY)
    machine_code_2 = auth2.machine_code
    success2, msg2 = auth2.verify(card_key)
    print(f"结果: {msg2}")
    print(f"当前机器码: {machine_code_2}")

    if machine_code_1 == machine_code_2:
        print("✅ 机器码一致性验证通过 - 相同设备可以重复登录")
    else:
        print("⚠️ 机器码不一致 - 这可能表示硬件信息已变化")

    auth2.logout()


def interactive_mode():
    """交互式测试模式"""
    print("\n" + "=" * 50)
    print("交互式测试工具（新版本）")
    print("=" * 50)

    admin = AdminClient()
    auth = LicenseAuthenticator(SERVER_URL, SECRET_KEY)

    while True:
        print("\n--- 菜单 ---")
        print("1. 创建卡密")
        print("2. 登录")
        print("3. 登出")
        print("4. 发送心跳")
        print("5. 查看所有卡密")
        print("6. 查看有效卡密")
        print("7. 查看在线设备")
        print("8. 查看安全日志")
        print("9. 更新卡密备注")
        print("10. 封禁卡密")
        print("11. 踢出设备")
        print("12. 测试服务器连接")
        print("13. 查看本机机器码")
        print("0. 退出")

        choice = input("\n请选择: ").strip()

        if choice == "1":
            days = int(input("有效期(天): ") or "30")
            max_devices = int(input("最大设备数: ") or "1")
            remark = input("备注(可选): ").strip() or None
            admin.create_license(days, max_devices, remark)

        elif choice == "2":
            card_key = input("输入卡密: ").strip()
            success, message = auth.verify(card_key)
            print(f"结果: {message}")

        elif choice == "3":
            auth.logout()

        elif choice == "4":
            if auth.send_heartbeat():
                print("✅ 心跳发送成功")
            else:
                print("❌ 心跳发送失败")

        elif choice == "5":
            admin.list_licenses()

        elif choice == "6":
            admin.list_valid_licenses()

        elif choice == "7":
            admin.get_online_devices()

        elif choice == "8":
            limit = int(input("显示条数(默认50): ") or "50")
            admin.get_security_logs(limit)

        elif choice == "9":
            card_key = input("输入卡密: ").strip()
            remark = input("输入新备注: ").strip()
            admin.update_remark(card_key, remark)

        elif choice == "10":
            card_key = input("输入要封禁的卡密: ").strip()
            admin.ban_license(card_key)

        elif choice == "11":
            card_key = input("输入卡密: ").strip()
            machine_code = input("输入机器码: ").strip()
            admin.kick_device(card_key, machine_code)

        elif choice == "12":
            connection()

        elif choice == "13":
            print(f"\n🆔 本机机器码: {auth.machine_code}")

        elif choice == "0":
            auth.logout()
            print("再见！")
            break

        else:
            print("❌ 无效选择，请重试")


if __name__ == "__main__":
    print("=" * 50)
    print("许可证服务器测试工具 v4.0")
    print("（适配machine_code版本）")
    print("=" * 50)
    print(f"服务器地址: {SERVER_URL}")
    print(f"管理员密钥: {ADMIN_KEY}")
    print(f"密钥: {'*' * len(SECRET_KEY)}")

    if not connection():
        print("\n⚠️ 无法连接到服务器，请解决连接问题后再试")
        input("\n按回车键退出...")
        exit(1)

    print("\n选择测试模式:")
    print("1. 基础登录和心跳测试")
    print("2. 多设备限制测试（机器码绑定）")
    print("3. 管理员功能测试")
    print("4. 安全防护测试")
    print("5. 机器码一致性验证")
    print("6. 交互式模式")

    mode = input("\n请选择(1-6): ").strip()

    if mode == "1":
        scenario_1()
    elif mode == "2":
        scenario_2()
    elif mode == "3":
        scenario_3()
    elif mode == "4":
        scenario_4()
    elif mode == "5":
        scenario_5()
    elif mode == "6":
        interactive_mode()
    else:
        print("❌ 无效选择")

    print("\n测试完成！")
