import time
import win32api
from mouse_controller import MouseController

controller = MouseController()

screen_width = win32api.GetSystemMetrics(0)
screen_height = win32api.GetSystemMetrics(1)
center_x = screen_width // 2
center_y = screen_height // 2

print("=" * 60)
print("🔍 PID精度测试（修正版）")
print("=" * 60)
print(f"📊 屏幕尺寸: {screen_width}x{screen_height}")
print(f"📊 屏幕中心: ({center_x}, {center_y})")

# 🆕 自动将鼠标移动到屏幕中心
print("\n🎯 正在将鼠标移动到屏幕中心...")
current_pos = win32api.GetCursorPos()
print(f"   当前位置: ({current_pos[0]}, {current_pos[1]})")

# 🔧 修复：传入屏幕中心的绝对坐标
controller.move_to_target(center_x, center_y)
time.sleep(0.3)

# 验证是否到达中心
final_pos = win32api.GetCursorPos()
distance_from_center = ((final_pos[0] - center_x) ** 2 + (final_pos[1] - center_y) ** 2) ** 0.5

if distance_from_center < 10:
    print(f"   ✅ 已移动到中心: ({final_pos[0]}, {final_pos[1]}) | 偏差: {distance_from_center:.1f}px")
else:
    print(f"   ⚠️ 未完全到达中心: ({final_pos[0]}, {final_pos[1]}) | 偏差: {distance_from_center:.1f}px")
    print(f"   正在手动调整...")
    win32api.SetCursorPos((center_x, center_y))
    time.sleep(0.1)
    final_pos = win32api.GetCursorPos()
    print(f"   ✅ 强制居中完成: ({final_pos[0]}, {final_pos[1]})")

print("\n⚠️  2秒后开始测试...")
time.sleep(2)

# 测试不同距离
test_distances = [30, 50, 80, 120, 200]

for target_distance in test_distances:
    print(f"\n{'=' * 60}")
    print(f"📌 测试移动: X+{target_distance}px")
    print(f"{'=' * 60}")

    measurements = []

    for round_num in range(3):
        # 1. 记录起始位置
        start_pos = win32api.GetCursorPos()
        start_x, start_y = start_pos

        # 2. 🔧 修复：计算目标的屏幕绝对坐标
        target_screen_x = start_x + target_distance
        target_screen_y = start_y

        print(f"\n第 {round_num + 1} 次:")
        print(f"  起始: ({start_x}, {start_y})")
        print(f"  目标: ({target_screen_x}, {target_screen_y})")

        # 边界检查
        if target_screen_x < 100 or target_screen_x > screen_width - 100:
            print(f"  ⚠️ 目标超出屏幕，跳过")
            break

        # 3. 🔧 修复：传入屏幕绝对坐标
        start_time = time.time()
        controller.move_to_target(target_screen_x, target_screen_y)

        # 4. 等待移动完成
        time.sleep(0.15)

        # 5. 记录结束位置
        end_pos = win32api.GetCursorPos()
        end_x, end_y = end_pos
        elapsed = (time.time() - start_time) * 1000

        # 6. 计算实际移动
        actual_move_x = end_x - start_x
        actual_move_y = end_y - start_y
        actual_distance = (actual_move_x ** 2 + actual_move_y ** 2) ** 0.5

        error = actual_distance - target_distance
        error_percent = (error / target_distance) * 100 if target_distance > 0 else 0

        measurements.append({
            'actual': actual_distance,
            'error': error,
            'x': actual_move_x,
            'y': actual_move_y
        })

        # 7. 输出结果
        status = "✅" if abs(error) < 3 else "❌"
        print(f"  {status} 目标{target_distance}px → 实际{actual_distance:.2f}px "
              f"(X:{actual_move_x:+.0f}, Y:{actual_move_y:+.0f})")
        print(f"     误差: {error:+.2f}px ({error_percent:+.1f}%) | 用时: {elapsed:.1f}ms")

        # 8. 🔧 修复：复位到起始的屏幕绝对坐标
        print(f"  复位中...")
        controller.move_to_target(start_x, start_y)
        time.sleep(0.2)

        final_pos = win32api.GetCursorPos()
        reset_error = ((final_pos[0] - start_x) ** 2 + (final_pos[1] - start_y) ** 2) ** 0.5

        if reset_error < 5:
            print(f"  ✅ 复位完成")
        else:
            print(f"  ⚠️ 复位偏差 {reset_error:.1f}px，正在强制复位...")
            win32api.SetCursorPos((start_x, start_y))
            time.sleep(0.1)
            print(f"  ✅ 强制复位完成")

        time.sleep(0.2)

    # 9. 统计
    if measurements:
        avg = sum(m['actual'] for m in measurements) / len(measurements)
        avg_error = sum(m['error'] for m in measurements) / len(measurements)
        max_error = max(m['error'] for m in measurements)
        min_error = min(m['error'] for m in measurements)

        status = "✅" if abs(avg_error) < 3 else "❌"
        print(f"\n📊 {target_distance}px 统计（{len(measurements)}次）:")
        print(f"  {status} 平均实际: {avg:.2f}px | 平均误差: {avg_error:+.2f}px")
        print(f"     误差范围: {min_error:+.2f} ~ {max_error:+.2f}px")
        print(f"  详细: {[f'{m["actual"]:.1f}' for m in measurements]}")

    # 🆕 每组测试后重新居中
    print(f"\n🎯 重新居中鼠标...")
    win32api.SetCursorPos((center_x, center_y))
    time.sleep(0.3)

controller.close()
print("\n" + "=" * 60)
print("✅ 测试完成")
print("=" * 60)
