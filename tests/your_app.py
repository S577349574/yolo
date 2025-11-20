# your_app.py - 真实应用模拟
import time
import threading
from license_auth import LicenseAuthenticator


def main():
    print("=" * 70)
    print("真实应用模拟 - License验证演示")
    print("=" * 70)

    server_url = "http://1.14.184.43:45000"
    secret_key = "your_secret_key_change_this"

    print(f"服务器: {server_url}")
    print("此程序演示真实应用的工作流程:")
    print("  1. 启动时获取卡密并验证")
    print("  2. 运行时定期发送心跳包")
    print("  3. 关闭时停止心跳并登出")
    print("=" * 70)

    auth = LicenseAuthenticator(server_url, secret_key)

    heartbeat_thread = None

    try:
        print("\n" + "=" * 70)
        print("应用启动中...")
        print("=" * 70)

        print("\n[1/3] 输入卡密...")
        card_key = input("请输入卡密: ")

        print("\n[2/3] 验证License...")
        success, message = auth.verify(card_key)

        if success:
            print(f"✅ {message}")

            print("\n[3/3] 启动心跳线程...")

            def send_heartbeat_loop():
                """后台发送心跳包"""
                count = 0
                while auth.is_valid():
                    time.sleep(30)
                    count += 1
                    if auth.send_heartbeat():
                        print(f"💓 心跳 #{count} 发送成功")
                    else:
                        print(f"❌ 心跳 #{count} 发送失败，停止应用")
                        break

            heartbeat_thread = threading.Thread(target=send_heartbeat_loop, daemon=True)
            heartbeat_thread.start()

            print("\n✅ License验证成功，应用正在运行...")
            print("📊 应用信息:")
            print(f"   - 卡密: {card_key[:8]}...")
            print(f"   - 机器码: {auth.machine_code[:16]}...")
            print(f"   - 过期时间: {auth.expire_date}")
            print(f"   - 最大设备数: {auth.max_devices}")

            print("\n（按 Ctrl+C 停止应用）")

            while auth.is_valid():
                time.sleep(1)
        else:
            print(f"❌ {message}")

    except KeyboardInterrupt:
        print("\n\n⏹️  收到停止信号...")
    except Exception as e:
        print(f"\n❌ 应用异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n" + "=" * 70)
        print("应用关闭中...")
        print("=" * 70)

        if auth.is_valid():
            if auth.logout():
                print("✅ License已注销")
            else:
                print("⚠️  License注销失败")

        if heartbeat_thread and heartbeat_thread.is_alive():
            time.sleep(1)

        print("⚠️  应用已停止")
        print("=" * 70)


if __name__ == "__main__":
    main()
