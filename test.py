import win32api
import win32file
import ctypes
import time
import numpy as np
from scipy.interpolate import CubicSpline


class KMouseRequest(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
        ("button_flags", ctypes.c_ubyte),
    ]


class MickeyToPixelCompensator:
    """完美补偿 Windows 鼠标非线性映射（支持样条插值）"""

    def __init__(self, calibration_data=None, use_spline=True):
        if calibration_data is None:
            self.calibration_points = np.array([
                [0, 0],
                [7, 10],
                [24, 20],
                [89, 50],
                [197, 100],
                [412, 200],
            ], dtype=float)
        else:
            calibration_data = np.array(calibration_data, dtype=float)
            calibration_data = calibration_data[calibration_data[:, 0].argsort()]
            self.calibration_points = calibration_data

        # 初始化样条插值
        self.use_spline = use_spline and len(self.calibration_points) >= 4
        if self.use_spline:
            try:
                pixels = self.calibration_points[:, 0]
                mickeys = self.calibration_points[:, 1]

                self.inverse_spline = CubicSpline(
                    pixels, mickeys,
                    bc_type='clamped',
                    extrapolate=False
                )
                self.forward_spline = CubicSpline(
                    mickeys, pixels,
                    bc_type='clamped',
                    extrapolate=False
                )
                print("✅ 使用三次样条插值")
            except Exception as e:
                print(f"⚠️ 样条初始化失败: {e}，回退到线性插值")
                self.use_spline = False

        # 输出标定点
        print("\n📊 补偿器标定点:")
        print("   像素   →  Mickey")
        for px, mk in self.calibration_points:
            print(f"  {px:6.1f}px → {mk:3.0f}")
        print()

    def pixel_to_mickey(self, target_pixels):
        """像素 → Mickey（自适应插值）"""
        sign = 1 if target_pixels >= 0 else -1
        abs_target = abs(target_pixels)

        if abs_target == 0:
            return 0

        pixels = self.calibration_points[:, 0]
        mickeys = self.calibration_points[:, 1]

        if abs_target <= pixels[0]:
            mickey_value = 0
        elif abs_target >= pixels[-1]:
            slope = (mickeys[-1] - mickeys[-2]) / (pixels[-1] - pixels[-2])
            mickey_value = mickeys[-1] + slope * (abs_target - pixels[-1])
        else:
            if self.use_spline:
                try:
                    mickey_value = float(self.inverse_spline(abs_target))
                except:
                    mickey_value = np.interp(abs_target, pixels, mickeys)
            else:
                mickey_value = np.interp(abs_target, pixels, mickeys)

        result = mickey_value * sign

        # 安全检查
        MAX_MICKEY = 500
        if abs(result) > MAX_MICKEY:
            print(f"⚠️ Mickey 值异常: 目标 {target_pixels}px → Mickey {result:.0f}，限制到 ±{MAX_MICKEY}")
            result = MAX_MICKEY * sign

        return int(result)

    def mickey_to_pixel(self, mickey_value):
        """Mickey → 像素（验证用）"""
        sign = 1 if mickey_value >= 0 else -1
        abs_mickey = abs(mickey_value)

        pixels = self.calibration_points[:, 0]
        mickeys = self.calibration_points[:, 1]

        if abs_mickey <= mickeys[0]:
            pixel_value = 0
        elif abs_mickey >= mickeys[-1]:
            slope = (pixels[-1] - pixels[-2]) / (mickeys[-1] - mickeys[-2])
            pixel_value = pixels[-1] + slope * (abs_mickey - mickeys[-1])
        else:
            if self.use_spline:
                try:
                    pixel_value = float(self.forward_spline(abs_mickey))
                except:
                    pixel_value = np.interp(abs_mickey, mickeys, pixels)
            else:
                pixel_value = np.interp(abs_mickey, mickeys, pixels)

        return int(pixel_value * sign)


def test_desktop_calibration():
    """桌面环境标定（自动测试）"""
    DRIVER_PATH = r"\\.\infestation"
    MOUSE_REQUEST = (0x00000022 << 16) | (0 << 14) | (0x666 << 2) | 0x00000000

    try:
        handle = win32file.CreateFile(
            DRIVER_PATH,
            0x80000000 | 0x40000000,
            0, None, 3, 0, None
        )
        print("✅ 驱动已连接")
    except Exception as e:
        print(f"❌ 驱动打开失败: {e}")
        return None

    def send_move(dx, dy):
        req = KMouseRequest(x=int(dx), y=int(dy), button_flags=0)
        try:
            win32file.DeviceIoControl(handle, MOUSE_REQUEST, bytes(req), 0, None)
            return True
        except:
            return False

    print("\n" + "=" * 60)
    print("🧪 桌面环境标定")
    print("=" * 60)
    print("⚠️  请将鼠标移至屏幕中央")
    print("⚠️  2 秒后自动开始测试...")
    time.sleep(2)

    # 密集采样测试用例
    test_cases = [
        {"name": "X轴微小值", "values": [5, 8, 12, 15]},
        {"name": "X轴小值", "values": [18, 25, 35, 45]},
        {"name": "X轴中值", "values": [60, 80, 100]},
        {"name": "X轴大值", "values": [150, 200]},
    ]

    calibration_data = []

    for case in test_cases:
        print(f"\n📌 {case['name']}")

        for val in case['values']:
            measurements = []

            for round_num in range(3):
                start = win32api.GetCursorPos()
                time.sleep(0.1)

                send_move(val, 0)
                time.sleep(0.15)

                end = win32api.GetCursorPos()
                actual = end[0] - start[0]
                measurements.append(actual)

                send_move(-val, 0)
                time.sleep(0.2)

            avg = sum(measurements) / len(measurements)
            scale = avg / val if val > 0 else 0

            calibration_data.append([avg, val])
            print(f"  X 驱动{val:3d} → {avg:6.2f}px ({scale:.3f}x) | {measurements}")

    print("\n" + "=" * 60)
    print(f"🎯 收集了 {len(calibration_data)} 个标定点")
    print("=" * 60)

    # 排序并添加原点
    calibration_data.sort(key=lambda x: x[0])
    calibration_data.insert(0, [0, 0])

    # 保存到文件
    import json
    output_data = {
        "calibration_points": calibration_data,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "environment": "desktop"
    }

    with open("desktop_calibration.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print("\n✅ 标定数据已保存到 desktop_calibration.json")
    print("\n📋 配置文件格式：")
    print('"MICKEY_CALIBRATION_POINTS": [')
    for px, mk in calibration_data:
        print(f'  [{px:.1f}, {mk:.0f}],')
    print(']')

    win32file.CloseHandle(handle)
    return calibration_data


def manual_game_test():
    """手动游戏测试模式（交互式发送移动指令）"""
    DRIVER_PATH = r"\\.\infestation"
    MOUSE_REQUEST = (0x00000022 << 16) | (0 << 14) | (0x666 << 2) | 0x00000000

    try:
        handle = win32file.CreateFile(
            DRIVER_PATH,
            0x80000000 | 0x40000000,
            0, None, 3, 0, None
        )
        print("✅ 驱动已连接")
    except Exception as e:
        print(f"❌ 驱动打开失败: {e}")
        return

    def send_move(dx, dy):
        req = KMouseRequest(x=int(dx), y=int(dy), button_flags=0)
        try:
            win32file.DeviceIoControl(handle, MOUSE_REQUEST, bytes(req), 0, None)
            return True
        except:
            return False

    # 尝试加载桌面标定数据
    try:
        import json
        with open("desktop_calibration.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        desktop_calibration = data["calibration_points"]
        print("✅ 已加载桌面标定数据（可用于参考）")

        print("\n📊 桌面参考数据：")
        reference_mickeys = [50, 100, 150, 200]
        for mickey_val in reference_mickeys:
            desktop_px = np.interp(
                mickey_val,
                [p[1] for p in desktop_calibration],
                [p[0] for p in desktop_calibration]
            )
            print(f"  Mickey {mickey_val:3d} → 桌面约 {desktop_px:6.1f}px")
    except FileNotFoundError:
        print("⚠️ 未找到桌面标定数据（可选）")
        desktop_calibration = None

    print("\n" + "=" * 60)
    print("🎮 手动游戏测试模式")
    print("=" * 60)
    print("\n使用说明：")
    print("  1. 进入游戏并将准心对准参照物")
    print("  2. 输入 Mickey 值（如 100）发送水平移动")
    print("  3. 观察准心移动距离并记录")
    print("  4. 输入 'r' 复位（反向移动）")
    print("  5. 输入 'q' 退出")
    print("\n提示：")
    print("  - 正数向右，负数向左")
    print("  - 可重复测试同一值以验证稳定性")
    print("  - 建议先测试小值（50）再测大值（200）")
    print("=" * 60)

    last_mickey = 0  # 记录上次发送的值，用于复位

    while True:
        print("\n" + "-" * 60)
        user_input = input("请输入 Mickey 值（或 'r' 复位 / 'q' 退出）: ").strip().lower()

        if user_input == 'q':
            print("👋 退出手动测试")
            break
        elif user_input == 'r':
            if last_mickey != 0:
                print(f"  正在复位（发送 Mickey {-last_mickey}）...")
                # 连续发送增强效果
                for _ in range(5):
                    send_move(-last_mickey, 0)
                    time.sleep(0.02)
                last_mickey = 0
                print("  ✅ 复位完成")
            else:
                print("  ⚠️ 无需复位（上次未移动）")
            continue

        # 解析 Mickey 值
        try:
            mickey_x = int(user_input)

            if abs(mickey_x) > 500:
                print("  ⚠️ Mickey 值过大，限制到 ±500")
                mickey_x = 500 if mickey_x > 0 else -500

            # 显示即将发送的信息
            print(f"\n  📤 即将发送：Mickey X = {mickey_x:+d}")

            # 如果有桌面数据，显示预期移动
            if desktop_calibration and abs(mickey_x) <= 200:
                expected_px = np.interp(
                    abs(mickey_x),
                    [p[1] for p in desktop_calibration],
                    [p[0] for p in desktop_calibration]
                )
                print(f"  💡 桌面环境预期移动：约 {expected_px:+.1f}px")

            print(f"  ⏳ 2 秒后发送...")
            time.sleep(2)

            # 连续发送（增强可见性）
            print(f"  发送中...")
            for i in range(5):
                send_move(mickey_x, 0)
                time.sleep(0.02)

            last_mickey = mickey_x
            print(f"  ✅ 已发送 Mickey {mickey_x:+d}")

            # 提示用户记录
            print("\n  📝 请记录以下信息：")
            print(f"     - 发送的 Mickey 值: {mickey_x:+d}")
            print(f"     - 观察到的准心移动距离（像素）: ______")

        except ValueError:
            print("  ⚠️ 无效输入，请输入整数 Mickey 值（如 100）")

    win32file.CloseHandle(handle)
    print("\n💾 建议：将测试数据记录在笔记中，格式如下：")
    print("Mickey 50  → 游戏约 XX px")
    print("Mickey 100 → 游戏约 XX px")
    print("Mickey 150 → 游戏约 XX px")


def verify_calibration():
    """验证标定精度（使用保存的数据）"""
    DRIVER_PATH = r"\\.\infestation"
    MOUSE_REQUEST = (0x00000022 << 16) | (0 << 14) | (0x666 << 2) | 0x00000000

    try:
        handle = win32file.CreateFile(
            DRIVER_PATH,
            0x80000000 | 0x40000000,
            0, None, 3, 0, None
        )
    except Exception as e:
        print(f"❌ 驱动打开失败: {e}")
        return

    def send_move(dx, dy):
        req = KMouseRequest(x=int(dx), y=int(dy), button_flags=0)
        try:
            win32file.DeviceIoControl(handle, MOUSE_REQUEST, bytes(req), 0, None)
            return True
        except:
            return False

    # 加载标定数据
    try:
        import json
        with open("desktop_calibration.json", "r", encoding="utf-8") as f:
            data = json.load(f)
        calibration_data = data["calibration_points"]
        print("✅ 已加载标定数据")
    except FileNotFoundError:
        print("❌ 未找到标定数据，请先运行桌面标定")
        return

    # 创建补偿器
    compensator = MickeyToPixelCompensator(calibration_data, use_spline=True)

    print("\n" + "=" * 60)
    print("🎯 补偿精度验证")
    print("=" * 60)
    print("⚠️  2 秒后开始测试...")
    time.sleep(2)

    test_cases = [8, 15, 25, 50, 100, 200]

    for target_px in test_cases:
        actual_movements = []
        mickey_values = []

        for _ in range(3):
            start_pos = win32api.GetCursorPos()
            time.sleep(0.1)

            mickey_x = compensator.pixel_to_mickey(target_px)
            mickey_y = 0
            mickey_values.append(mickey_x)

            send_move(mickey_x, mickey_y)
            time.sleep(0.15)

            end_pos = win32api.GetCursorPos()
            actual = end_pos[0] - start_pos[0]
            actual_movements.append(actual)

            # 复位
            send_move(-mickey_x, 0)
            time.sleep(0.2)

        avg_actual = sum(actual_movements) / len(actual_movements)
        avg_mickey = sum(mickey_values) / len(mickey_values)
        error = abs(avg_actual - target_px)
        error_rate = (error / target_px) * 100 if target_px > 0 else 0

        status = "✅" if error < 3 else "⚠️"
        print(f"{status} 目标 {target_px:3d}px → Mickey {avg_mickey:6.1f} → 实际 {avg_actual:6.2f}px "
              f"(误差 {error:.1f}px, {error_rate:.1f}%)")

    print("=" * 60)
    win32file.CloseHandle(handle)


def main_menu():
    """主菜单"""
    print("\n" + "=" * 60)
    print("🎯 Mickey 补偿器测试工具")
    print("=" * 60)
    print("\n请选择测试模式：")
    print("  1. 桌面环境标定（自动测试 + 保存数据）")
    print("  2. 验证标定精度（使用保存的数据）")
    print("  3. 手动游戏测试（交互式发送移动指令）")
    print("  4. 退出")

    while True:
        try:
            choice = input("\n请输入选项 (1-4): ").strip()

            if choice == '1':
                test_desktop_calibration()
                break
            elif choice == '2':
                verify_calibration()
                break
            elif choice == '3':
                manual_game_test()
                break
            elif choice == '4':4
                print("👋 再见！")
                break
            else:
                print("⚠️ 无效选项，请重新输入")
        except KeyboardInterrupt:
            print("\n\n👋 用户中断，退出")
            break


if __name__ == "__main__":
    try:
        main_menu()
    except Exception as e:
        print(f"\n❌ 程序错误: {e}")
        import traceback

        traceback.print_exc()
