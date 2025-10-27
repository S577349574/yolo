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

                # 创建样条（防止外推异常，设置边界条件）
                self.inverse_spline = CubicSpline(
                    pixels, mickeys,
                    bc_type='clamped',  # 边界夹紧
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
        abs_target = abs(target_pixels)

        if abs_target == 0:
            return 0

        pixels = self.calibration_points[:, 0]
        mickeys = self.calibration_points[:, 1]

        # 边界检查
        if abs_target <= pixels[0]:
            mickey_value = 0
        elif abs_target >= pixels[-1]:
            # 超出范围：使用最后一段斜率外推
            slope = (mickeys[-1] - mickeys[-2]) / (pixels[-1] - pixels[-2])
            mickey_value = mickeys[-1] + slope * (abs_target - pixels[-1])
        else:
            # 使用样条或线性插值
            if self.use_spline:
                try:
                    mickey_value = float(self.inverse_spline(abs_target))
                except:
                    # 样条失败回退
                    mickey_value = np.interp(abs_target, pixels, mickeys)
            else:
                mickey_value = np.interp(abs_target, pixels, mickeys)

        return int(mickey_value * np.sign(target_pixels))

    def mickey_to_pixel(self, mickey_value):
        """Mickey → 像素（验证用）"""
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

        return int(pixel_value * np.sign(mickey_value))

    def test_accuracy(self):
        """理论验证"""
        print("\n" + "=" * 60)
        print("🧪 Mickey ↔ 像素转换测试（理论验证）")
        print("=" * 60)

        test_pixels = [10, 50, 100, 200]

        for target_px in test_pixels:
            mickey = self.pixel_to_mickey(target_px)
            back_px = self.mickey_to_pixel(mickey)
            error = abs(back_px - target_px)

            status = "✅" if error < 3 else "⚠️"
            print(f"{status} 目标 {target_px:3d}px → Mickey {mickey:3d} → 验证 {back_px:3d}px (误差 {error}px)")

        print("=" * 60)


def test_driver_movement_enhanced():
    """增强型基线测试：小值密集采样"""
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
        return None, None

    def send_move(dx, dy):
        req = KMouseRequest(x=int(dx), y=int(dy), button_flags=0)
        try:
            win32file.DeviceIoControl(handle, MOUSE_REQUEST, bytes(req), 0, None)
            return True
        except:
            return False

    print("\n" + "=" * 60)
    print("🧪 增强型基线测试（小值密集采样）")
    print("=" * 60)
    print("⚠️  请保持鼠标在屏幕中央，勿触碰！")
    time.sleep(3)

    # 🆕 增强测试用例
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

            for round in range(3):
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

    calibration_data.sort(key=lambda x: x[0])
    return handle, calibration_data


def test_compensated_accuracy(handle, compensator):
    """补偿精度验证"""
    MOUSE_REQUEST = (0x00000022 << 16) | (0 << 14) | (0x666 << 2) | 0x00000000

    def send_compensated_move(target_px_x, target_px_y):
        mickey_x = compensator.pixel_to_mickey(target_px_x)
        mickey_y = compensator.pixel_to_mickey(target_px_y)

        req = KMouseRequest(x=int(mickey_x), y=int(mickey_y), button_flags=0)
        try:
            win32file.DeviceIoControl(handle, MOUSE_REQUEST, bytes(req), 0, None)
            return True, mickey_x, mickey_y
        except:
            return False, 0, 0

    print("\n" + "=" * 60)
    print("🎯 补偿精度验证（实际驱动测试）")
    print("=" * 60)
    print("⚠️  请保持鼠标静止！")
    time.sleep(2)

    # 🆕 扩展测试范围
    test_cases = [8, 15, 25, 50, 100, 200]

    for target_px in test_cases:
        actual_movements = []
        mickey_values = []

        for _ in range(3):
            start_pos = win32api.GetCursorPos()
            time.sleep(0.1)

            success, mickey_x, mickey_y = send_compensated_move(target_px, 0)
            if not success:
                continue

            mickey_values.append(mickey_x)
            time.sleep(0.15)

            end_pos = win32api.GetCursorPos()
            actual = end_pos[0] - start_pos[0]
            actual_movements.append(actual)

            send_compensated_move(-target_px, 0)
            time.sleep(0.2)

        if not actual_movements:
            continue

        avg_actual = sum(actual_movements) / len(actual_movements)
        avg_mickey = sum(mickey_values) / len(mickey_values)
        error = abs(avg_actual - target_px)
        error_rate = (error / target_px) * 100 if target_px > 0 else 0

        status = "✅" if error < 3 else "⚠️"
        print(f"{status} 目标 {target_px:3d}px → Mickey {avg_mickey:6.1f} → 实际 {avg_actual:6.2f}px "
              f"(误差 {error:.1f}px, {error_rate:.1f}%)")

    print("=" * 60)


def main():
    """主测试流程（增强版）"""
    print("=" * 60)
    print("🚀 Mickey 补偿器增强测试（三次样条 + 密集采样）")
    print("=" * 60)

    # 步骤 1：使用增强型基线测试
    print("\n【步骤 1/2】密集标定数据收集")
    handle, calibration_data = test_driver_movement_enhanced()

    if handle is None:
        print("❌ 驱动连接失败，测试终止")
        return

    if calibration_data:
        # 添加原点
        calibration_data.insert(0, [0, 0])

        # 创建补偿器（启用样条）
        compensator = MickeyToPixelCompensator(calibration_data, use_spline=True)

        # 步骤 2：精度验证
        print("\n【步骤 2/2】补偿精度验证")
        test_compensated_accuracy(handle, compensator)

    win32file.CloseHandle(handle)

    print("\n" + "=" * 60)
    print("✅ 测试完成！")
    print("=" * 60)
    print("\n📊 如果误差 < 3px，可以集成到主代码")


if __name__ == "__main__":
    main()
