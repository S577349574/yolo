# recoil_tester.py
"""压枪参数测试工具（修复亚像素问题）"""

import time
import threading
from typing import Optional

import win32api
import win32con

from config_manager import get_config, load_config
from mouse_controller import MouseController
import utils


class RecoilTester:
    """压枪参数测试工具类（按住模式 - 累积发送版本）"""

    def __init__(self):
        load_config()

        try:
            self.mouse_controller = MouseController()
            utils.log("✅ 鼠标控制器初始化成功")
        except Exception as e:
            utils.log(f"❌ 鼠标控制器初始化失败: {e}")
            raise

        # 测试状态
        self.is_testing = False
        self.test_start_time = 0.0
        self.last_recoil_time = 0.0
        self.shot_count = 0
        self.total_offset_y = 0.0

        # 🆕 累积缓冲（解决亚像素问题）
        self.accumulated_offset_x = 0.0
        self.accumulated_offset_y = 0.0

        # 线程控制
        self.stop_flag = False
        self.test_thread: Optional[threading.Thread] = None

    def _apply_linear_recoil(self) -> None:
        """应用线性压枪（累积发送版本）"""
        current_time = time.time()
        delta_time = current_time - self.last_recoil_time

        if delta_time < 0.001:
            return

        self.last_recoil_time = current_time

        # 读取配置
        vertical_speed = get_config('RECOIL_VERTICAL_SPEED', 150.0)

        # 计算理论偏移（浮点数）
        offset_y = vertical_speed * delta_time

        # 🆕 累积偏移（包含亚像素部分）
        self.accumulated_offset_y += offset_y
        self.total_offset_y += offset_y
        self.shot_count += 1

        # 🆕 只在累积值 >= 1 像素时才发送
        if abs(self.accumulated_offset_y) >= 1.0:
            # 取整数部分发送
            move_y = int(self.accumulated_offset_y)

            # 保留小数部分继续累积
            self.accumulated_offset_y -= move_y

            # 发送鼠标移动
            self.mouse_controller._send_mouse_request(
                0,
                move_y,
                get_config('APP_MOUSE_NO_BUTTON', 0)
            )

            # 调试输出
            if self.shot_count % 50 == 1:
                elapsed = current_time - self.test_start_time
                current_speed = self.total_offset_y / elapsed if elapsed > 0 else 0
                utils.log(
                    f"[压枪] 第{self.shot_count}次 | "
                    f"delta: {delta_time * 1000:.2f}ms | "
                    f"理论: {offset_y:.2f}px | "
                    f"实际移动: {move_y}px | "
                    f"累积缓冲: {self.accumulated_offset_y:.2f}px | "
                    f"总累积: {self.total_offset_y:.1f}px | "
                    f"速度: {current_speed:.1f} px/s"
                )

    def _test_loop(self) -> None:
        """测试主循环"""
        utils.log("\n" + "=" * 60)
        utils.log("🎯 压枪测试已启动（累积发送模式）")
        utils.log(f"📊 当前配置:")
        utils.log(f"   - RECOIL_VERTICAL_SPEED: {get_config('RECOIL_VERTICAL_SPEED', 150.0)} px/s")
        utils.log("\n操作说明:")
        utils.log("   - 按住鼠标左键：开始测试压枪（自动射击）")
        utils.log("   - 松开鼠标左键：停止测试")
        utils.log("   - 按 ESC：退出程序")
        utils.log("=" * 60 + "\n")

        last_button_state = False

        try:
            while not self.stop_flag:
                if win32api.GetAsyncKeyState(win32con.VK_ESCAPE) & 0x8000:
                    utils.log("\n🛑 用户按下 ESC，退出测试")
                    break

                current_button_state = win32api.GetKeyState(0x01) < 0

                # 按下瞬间
                if current_button_state and not last_button_state:
                    self.is_testing = True
                    self.test_start_time = time.time()
                    self.last_recoil_time = time.time()
                    self.shot_count = 0
                    self.total_offset_y = 0.0
                    self.accumulated_offset_x = 0.0  # 🆕 重置累积缓冲
                    self.accumulated_offset_y = 0.0

                    utils.log("\n🔥 开始测试压枪（按住中）...")

                    left_down = get_config('APP_MOUSE_LEFT_DOWN', 1)
                    self.mouse_controller._send_mouse_request(0, 0, left_down)

                # 松开瞬间
                elif not current_button_state and last_button_state:
                    self.is_testing = False

                    test_duration = time.time() - self.test_start_time
                    actual_speed = self.total_offset_y / test_duration if test_duration > 0 else 0
                    theoretical_speed = get_config('RECOIL_VERTICAL_SPEED', 150.0)
                    error_percent = abs(actual_speed - theoretical_speed) / theoretical_speed * 100

                    utils.log(f"\n🛑 测试结束:")
                    utils.log(f"   - 持续时间: {test_duration:.2f}s")
                    utils.log(f"   - 累积下移: {self.total_offset_y:.1f}px")
                    utils.log(f"   - 未发送缓冲: {self.accumulated_offset_y:.2f}px")
                    utils.log(f"   - 更新次数: {self.shot_count}")
                    utils.log(f"   - 实际速度: {actual_speed:.1f} px/s")
                    utils.log(f"   - 理论速度: {theoretical_speed:.1f} px/s")
                    utils.log(f"   - 误差: {abs(actual_speed - theoretical_speed):.1f} px/s ({error_percent:.1f}%)")

                    if error_percent < 5:
                        utils.log(f"   ✅ 压枪参数准确")
                    elif error_percent < 10:
                        utils.log(f"   ⚠️ 压枪参数可接受")
                    else:
                        utils.log(f"   ❌ 压枪参数需要调整")

                    utils.log("")

                    left_up = get_config('APP_MOUSE_LEFT_UP', 2)
                    self.mouse_controller._send_mouse_request(0, 0, left_up)

                last_button_state = current_button_state

                if self.is_testing:
                    self._apply_linear_recoil()

                time.sleep(0.001)

        except KeyboardInterrupt:
            utils.log("\n⚠ 用户中断测试")
        finally:
            if self.is_testing:
                left_up = get_config('APP_MOUSE_LEFT_UP', 2)
                self.mouse_controller._send_mouse_request(0, 0, left_up)

    def start_test(self) -> None:
        """启动测试"""
        if self.test_thread and self.test_thread.is_alive():
            utils.log("⚠️ 测试已在运行中")
            return

        self.stop_flag = False
        self.test_thread = threading.Thread(target=self._test_loop, daemon=False)
        self.test_thread.start()

    def stop_test(self) -> None:
        """停止测试"""
        self.stop_flag = True
        if self.test_thread:
            self.test_thread.join(timeout=2.0)

        self.mouse_controller.close()
        utils.log("\n✅ 测试工具已关闭")


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("🔧 压枪参数测试工具（累积发送版本）")
    print("=" * 60)
    print("\n正在初始化...\n")

    try:
        tester = RecoilTester()
        tester.start_test()

        if tester.test_thread:
            tester.test_thread.join()

    except Exception as e:
        utils.log(f"\n❌ 测试工具启动失败: {e}")
    finally:
        utils.log("\n程序已退出")


if __name__ == "__main__":
    main()
