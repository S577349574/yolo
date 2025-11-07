# test_aim_simulator.py (完全修复版 v3.0)
"""
自瞄系统测试模拟器 - 完全修复版
直接使用屏幕坐标系测试，正确验证速度预测功能
"""
import math
import time
from typing import List, Tuple, Dict
import matplotlib.pyplot as plt
import numpy as np

from config_manager import load_config, get_config
from target_selector import TargetSelector
from pid_controller import PIDController
import utils


class TargetSimulator:
    """模拟移动目标"""

    def __init__(self, screen_width=1920, screen_height=1080):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.targets = []
        self.time_start = time.time()

    def add_static_target(self, x: int, y: int, confidence: float = 0.9):
        """添加静止目标"""
        self.targets.append({
            'type': 'static',
            'x': x,
            'y': y,
            'confidence': confidence
        })

    def add_linear_target(self, start_x: int, start_y: int,
                          velocity_x: float, velocity_y: float,
                          confidence: float = 0.85):
        """添加匀速直线运动目标"""
        self.targets.append({
            'type': 'linear',
            'start_x': start_x,
            'start_y': start_y,
            'velocity_x': velocity_x,
            'velocity_y': velocity_y,
            'confidence': confidence
        })

    def add_circular_target(self, center_x: int, center_y: int,
                            radius: int, angular_speed: float,
                            confidence: float = 0.88):
        """添加圆周运动目标"""
        self.targets.append({
            'type': 'circular',
            'center_x': center_x,
            'center_y': center_y,
            'radius': radius,
            'angular_speed': angular_speed,
            'confidence': confidence
        })

    def add_zigzag_target(self, start_x: int, start_y: int,
                          velocity_x: float, amplitude: int,
                          frequency: float, confidence: float = 0.82):
        """添加 Z 字形运动目标"""
        self.targets.append({
            'type': 'zigzag',
            'start_x': start_x,
            'start_y': start_y,
            'velocity_x': velocity_x,
            'amplitude': amplitude,
            'frequency': frequency,
            'confidence': confidence
        })

    def get_targets_at_time(self, current_time: float = None) -> List[Dict]:
        """获取当前时刻所有目标的位置（屏幕坐标系）"""
        if current_time is None:
            current_time = time.time()

        elapsed = current_time - self.time_start
        results = []

        for target in self.targets:
            if target['type'] == 'static':
                x, y = target['x'], target['y']

            elif target['type'] == 'linear':
                x = target['start_x'] + target['velocity_x'] * elapsed
                y = target['start_y'] + target['velocity_y'] * elapsed

            elif target['type'] == 'circular':
                angle = target['angular_speed'] * elapsed
                x = target['center_x'] + target['radius'] * math.cos(angle)
                y = target['center_y'] + target['radius'] * math.sin(angle)

            elif target['type'] == 'zigzag':
                x = target['start_x'] + target['velocity_x'] * elapsed
                y = target['start_y'] + target['amplitude'] * math.sin(
                    2 * math.pi * target['frequency'] * elapsed
                )

            # 边界检查
            if 0 <= x < self.screen_width and 0 <= y < self.screen_height:
                results.append({
                    'x': int(x),
                    'y': int(y),
                    'confidence': target['confidence']
                })

        return results


class AimTestHarness:
    """瞄准系统测试框架（完全修复版 v3.0）"""

    def __init__(self):
        load_config()
        self.screen_width = 1920
        self.screen_height = 1080
        self.screen_center_x = self.screen_width // 2
        self.screen_center_y = self.screen_height // 2

        self.target_selector = TargetSelector()
        self.pid = PIDController(
            kp=get_config('PID_KP', 1.2),
            ki=get_config('PID_KI', 0.02),
            kd=get_config('PID_KD', 0.15)
        )

        # 统计数据
        self.history = {
            'time': [],
            'target_x': [],
            'target_y': [],
            'aim_x': [],
            'aim_y': [],
            'error_distance': [],
            'velocity_x': [],
            'velocity_y': [],
            'true_velocity': []  # 🆕 记录真实速度（用于验证）
        }

        self.current_mouse_x = self.screen_center_x
        self.current_mouse_y = self.screen_center_y

        # 🆕 记录上一帧的目标位置（用于计算真实速度）
        self.last_true_target_x = None
        self.last_true_target_y = None
        self.last_true_target_time = time.time()

    def simulate_frame(self, targets: List[Dict]) -> Tuple[int, int, float]:
        """模拟一帧处理（直接使用屏幕坐标）"""
        # ✅ 直接使用目标的屏幕坐标（不经过 calculate_aim_point）
        candidate_targets = [{
            'x': t['x'],
            'y': t['y'],
            'confidence': t['confidence']
        } for t in targets]

        # 选择最佳目标（内部会应用预测）
        aim_x, aim_y = self.target_selector.select_best_target(
            candidate_targets,
            self.screen_width,
            self.screen_height
        )

        if aim_x is None:
            return None, None, 0.0

        # 计算误差
        error_x = aim_x - self.current_mouse_x
        error_y = aim_y - self.current_mouse_y
        error_distance = math.hypot(error_x, error_y)

        # PID 计算
        pid_output_x, pid_output_y = self.pid.calculate(error_x, error_y)

        # 模拟鼠标移动
        self.current_mouse_x += pid_output_x
        self.current_mouse_y += pid_output_y

        return aim_x, aim_y, error_distance

    def run_test(self, simulator: TargetSimulator,
                 duration: float = 5.0, fps: int = 60):
        """运行测试"""
        # 显示预测配置状态
        vel_pred = get_config('ENABLE_VELOCITY_PREDICTION', False)
        accel_pred = get_config('ENABLE_ACCEL_PREDICTION', False)
        predict_delay = get_config('PREDICT_DELAY_SEC', 0.025)

        print(f"\n{'=' * 60}")
        print(f"🧪 开始测试 (时长: {duration}s, FPS: {fps})")
        print(f"🎯 速度预测: {'✅' if vel_pred else '❌'} | "
              f"加速度预测: {'✅' if accel_pred else '❌'} | "
              f"预测延迟: {predict_delay * 1000:.1f}ms")
        print(f"{'=' * 60}\n")

        frame_interval = 1.0 / fps
        start_time = time.time()
        frame_count = 0

        while time.time() - start_time < duration:
            frame_start = time.time()

            # 获取当前帧的目标
            targets = simulator.get_targets_at_time()

            # 🆕 计算真实速度（用于对比）
            true_velocity = 0.0
            if targets and self.last_true_target_x is not None:
                current_time = time.time()
                dt = current_time - self.last_true_target_time
                if dt > 0:
                    dx = targets[0]['x'] - self.last_true_target_x
                    dy = targets[0]['y'] - self.last_true_target_y
                    true_velocity = math.hypot(dx, dy) / dt

            if targets:
                self.last_true_target_x = targets[0]['x']
                self.last_true_target_y = targets[0]['y']
                self.last_true_target_time = time.time()

            # 模拟检测
            aim_x, aim_y, error = self.simulate_frame(targets)

            # 记录数据
            if aim_x is not None:
                elapsed = time.time() - start_time
                self.history['time'].append(elapsed)

                # 记录真实目标位置
                if targets:
                    self.history['target_x'].append(targets[0]['x'])
                    self.history['target_y'].append(targets[0]['y'])
                else:
                    self.history['target_x'].append(None)
                    self.history['target_y'].append(None)

                self.history['aim_x'].append(aim_x)
                self.history['aim_y'].append(aim_y)
                self.history['error_distance'].append(error)

                # 记录估算速度
                self.history['velocity_x'].append(self.target_selector.target_velocity_x)
                self.history['velocity_y'].append(self.target_selector.target_velocity_y)
                self.history['true_velocity'].append(true_velocity)

                # 每秒输出
                frame_count += 1
                if frame_count % fps == 0:
                    avg_error = np.mean(self.history['error_distance'][-fps:])
                    max_error = np.max(self.history['error_distance'][-fps:])

                    # 估算速度
                    avg_est_vel = math.hypot(
                        np.mean(self.history['velocity_x'][-fps:]),
                        np.mean(self.history['velocity_y'][-fps:])
                    )

                    # 真实速度
                    avg_true_vel = np.mean(self.history['true_velocity'][-fps:])

                    print(f"⏱ {elapsed:.1f}s | 平均误差: {avg_error:.1f}px | "
                          f"最大误差: {max_error:.1f}px | "
                          f"估算速度: {avg_est_vel:.0f}px/s | "
                          f"真实速度: {avg_true_vel:.0f}px/s | "
                          f"锁定: {self.target_selector.is_locked}")

            # 帧率控制
            elapsed_frame = time.time() - frame_start
            if elapsed_frame < frame_interval:
                time.sleep(frame_interval - elapsed_frame)

        self.print_summary()

    def print_summary(self):
        """打印测试总结"""
        if not self.history['error_distance']:
            print("⚠️ 无有效数据")
            return

        errors = self.history['error_distance']
        avg_error = np.mean(errors)
        max_error = np.max(errors)
        min_error = np.min(errors)
        std_error = np.std(errors)

        # 稳定性指标
        stable_frames = sum(1 for e in errors if e < 10)
        stability = (stable_frames / len(errors)) * 100

        # 速度统计
        est_velocities = [math.hypot(vx, vy) for vx, vy in
                          zip(self.history['velocity_x'], self.history['velocity_y'])]
        avg_est_velocity = np.mean(est_velocities) if est_velocities else 0

        true_velocities = [v for v in self.history['true_velocity'] if v > 0]
        avg_true_velocity = np.mean(true_velocities) if true_velocities else 0

        # 速度估算准确度
        velocity_accuracy = 0
        if avg_true_velocity > 0:
            velocity_accuracy = (avg_est_velocity / avg_true_velocity) * 100

        print(f"\n{'=' * 60}")
        print(f"📊 测试总结")
        print(f"{'=' * 60}")
        print(f"总帧数: {len(errors)}")
        print(f"平均误差: {avg_error:.2f}px")
        print(f"最大误差: {max_error:.2f}px")
        print(f"最小误差: {min_error:.2f}px")
        print(f"标准差: {std_error:.2f}px")
        print(f"稳定性 (<10px): {stability:.1f}%")
        print(f"真实平均速度: {avg_true_velocity:.0f}px/s")
        print(f"估算平均速度: {avg_est_velocity:.0f}px/s")
        print(f"速度估算准确度: {velocity_accuracy:.1f}%")
        print(f"{'=' * 60}\n")

    def plot_results(self):
        """可视化结果"""
        if not self.history['time']:
            print("⚠️ 无数据可绘制")
            return

        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('自瞄系统测试结果（完全修复版）', fontsize=16, fontproperties='SimHei')

        # 1. 轨迹对比
        ax1 = axes[0, 0]
        ax1.plot(self.history['target_x'], self.history['target_y'],
                 'r-', label='目标轨迹', linewidth=2)
        ax1.plot(self.history['aim_x'], self.history['aim_y'],
                 'b--', label='瞄准轨迹', linewidth=1.5, alpha=0.7)
        ax1.scatter(self.screen_center_x, self.screen_center_y,
                    c='green', s=100, marker='+', label='屏幕中心')
        ax1.set_xlabel('X (px)', fontproperties='SimHei')
        ax1.set_ylabel('Y (px)', fontproperties='SimHei')
        ax1.set_title('轨迹对比', fontproperties='SimHei')
        ax1.legend(prop={'family': 'SimHei'})
        ax1.grid(True, alpha=0.3)

        # 2. 误差随时间变化
        ax2 = axes[0, 1]
        ax2.plot(self.history['time'], self.history['error_distance'],
                 'purple', linewidth=1)
        ax2.axhline(y=10, color='orange', linestyle='--',
                    label='稳定阈值 (10px)')
        ax2.set_xlabel('时间 (s)', fontproperties='SimHei')
        ax2.set_ylabel('误差 (px)', fontproperties='SimHei')
        ax2.set_title('瞄准误差', fontproperties='SimHei')
        ax2.legend(prop={'family': 'SimHei'})
        ax2.grid(True, alpha=0.3)

        # 3. X 轴位置对比
        ax3 = axes[1, 0]
        ax3.plot(self.history['time'], self.history['target_x'],
                 'r-', label='目标 X')
        ax3.plot(self.history['time'], self.history['aim_x'],
                 'b--', label='瞄准 X')
        ax3.set_xlabel('时间 (s)', fontproperties='SimHei')
        ax3.set_ylabel('X 坐标 (px)', fontproperties='SimHei')
        ax3.set_title('X 轴跟踪', fontproperties='SimHei')
        ax3.legend(prop={'family': 'SimHei'})
        ax3.grid(True, alpha=0.3)

        # 4. 速度对比
        ax4 = axes[1, 1]
        est_velocities = [math.hypot(vx, vy) for vx, vy in
                          zip(self.history['velocity_x'], self.history['velocity_y'])]
        ax4.plot(self.history['time'], est_velocities,
                 'b-', label='估算速度', linewidth=1.5)
        ax4.plot(self.history['time'], self.history['true_velocity'],
                 'r--', label='真实速度', linewidth=1.5, alpha=0.7)
        ax4.set_xlabel('时间 (s)', fontproperties='SimHei')
        ax4.set_ylabel('速度 (px/s)', fontproperties='SimHei')
        ax4.set_title('速度估算对比', fontproperties='SimHei')
        ax4.legend(prop={'family': 'SimHei'})
        ax4.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.show()


# ==================== 预设测试场景 ====================

def test_static_target():
    """测试1: 静止目标"""
    print("\n🎯 测试场景1: 静止目标")
    simulator = TargetSimulator()
    simulator.add_static_target(1000, 540)

    test = AimTestHarness()
    test.run_test(simulator, duration=3.0, fps=60)
    test.plot_results()


def test_linear_moving_target():
    """测试2: 匀速直线运动"""
    print("\n🎯 测试场景2: 匀速直线运动")
    simulator = TargetSimulator()
    simulator.add_linear_target(400, 540, velocity_x=200, velocity_y=0)

    test = AimTestHarness()
    test.run_test(simulator, duration=5.0, fps=60)
    test.plot_results()


def test_circular_target():
    """测试3: 圆周运动"""
    print("\n🎯 测试场景3: 圆周运动")
    simulator = TargetSimulator()
    simulator.add_circular_target(960, 540, radius=150, angular_speed=math.pi / 2)

    test = AimTestHarness()
    test.run_test(simulator, duration=5.0, fps=60)
    test.plot_results()


def test_zigzag_target():
    """测试4: Z 字形运动"""
    print("\n🎯 测试场景4: Z 字形运动")
    simulator = TargetSimulator()
    simulator.add_zigzag_target(400, 540, velocity_x=150,
                                amplitude=100, frequency=0.5)

    test = AimTestHarness()
    test.run_test(simulator, duration=6.0, fps=60)
    test.plot_results()


def test_fast_moving_target():
    """测试5: 高速移动目标"""
    print("\n🎯 测试场景5: 高速移动目标")
    simulator = TargetSimulator()
    simulator.add_linear_target(300, 300, velocity_x=400, velocity_y=200)

    test = AimTestHarness()
    test.run_test(simulator, duration=3.0, fps=60)
    test.plot_results()


def test_multiple_targets():
    """测试6: 多目标场景"""
    print("\n🎯 测试场景6: 多目标切换")
    simulator = TargetSimulator()
    simulator.add_static_target(800, 400, confidence=0.7)
    simulator.add_linear_target(600, 600, velocity_x=150, velocity_y=-100,
                                confidence=0.9)

    test = AimTestHarness()
    test.run_test(simulator, duration=5.0, fps=60)
    test.plot_results()


def main():
    """主测试菜单"""
    print("\n" + "=" * 60)
    print("🧪 自瞄系统测试工具 v3.0 (完全修复版)")
    print("=" * 60)
    print("请选择测试场景:")
    print("1. 静止目标 (基准测试)")
    print("2. 匀速直线运动")
    print("3. 圆周运动")
    print("4. Z 字形运动")
    print("5. 高速移动目标")
    print("6. 多目标切换")
    print("7. 运行所有测试")
    print("0. 退出")
    print("=" * 60)

    choice = input("\n请输入选项 (0-7): ").strip()

    tests = {
        '1': test_static_target,
        '2': test_linear_moving_target,
        '3': test_circular_target,
        '4': test_zigzag_target,
        '5': test_fast_moving_target,
        '6': test_multiple_targets
    }

    if choice == '0':
        print("👋 退出测试工具")
        return
    elif choice == '7':
        for test_func in tests.values():
            test_func()
            time.sleep(1)
    elif choice in tests:
        tests[choice]()
    else:
        print("❌ 无效选项")
        main()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断测试")
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback

        traceback.print_exc()
