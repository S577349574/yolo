"""
MTKMBOX SDK 功能测试
测试所有核心功能是否正常工作
"""
import os
import sys
import time
import logging
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mtkmbox import MTKMBOXConnectionError, MTKMBOX

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('MTKMBOX_TEST')


def print_section(title: str):
    """打印测试章节标题"""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def test_connection():
    """测试 1: 设备连接"""
    print_section("测试 1: 设备连接")

    try:
        # 测试自动连接
        logger.info("尝试自动连接设备...")
        device = MTKMBOX(debug=True)

        if device.is_connected():
            logger.info("✅ 设备连接成功")

            # 打印设备信息
            info = device.get_device_info()
            logger.info(f"设备信息: {info}")

            device.close()
            return True
        else:
            logger.error("❌ 设备连接失败")
            return False

    except MTKMBOXConnectionError as e:
        logger.error(f"❌ 连接错误: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ 未知错误: {e}")
        return False


def test_mouse_movement(device: MTKMBOX):
    """测试 2: 鼠标移动"""
    print_section("测试 2: 鼠标移动")

    try:
        logger.info("测试鼠标移动...")

        # 测试小幅移动
        logger.info("向右移动 50 像素")
        device.move(50, 0)
        time.sleep(0.5)

        logger.info("向下移动 50 像素")
        device.move(0, 50)
        time.sleep(0.5)

        logger.info("向左移动 50 像素")
        device.move(-50, 0)
        time.sleep(0.5)

        logger.info("向上移动 50 像素")
        device.move(0, -50)
        time.sleep(0.5)

        # 测试对角线移动
        logger.info("对角线移动")
        device.move(30, 30)
        time.sleep(0.5)
        device.move(-30, -30)

        logger.info("✅ 鼠标移动测试通过")
        return True

    except Exception as e:
        logger.error(f"❌ 鼠标移动测试失败: {e}")
        return False


def test_button_click(device: MTKMBOX):
    """测试 3: 按键点击"""
    print_section("测试 3: 按键点击")

    buttons = ['left', 'right', 'middle', 'x1', 'x2']

    try:
        for button in buttons:
            logger.info(f"测试 {button} 按键点击...")

            # 点击测试
            if device.click(button):
                logger.info(f"  ✅ {button} 点击成功")
            else:
                logger.error(f"  ❌ {button} 点击失败")
                return False

            time.sleep(0.3)

        logger.info("✅ 所有按键点击测试通过")
        return True

    except Exception as e:
        logger.error(f"❌ 按键点击测试失败: {e}")
        return False


def test_button_press_release(device: MTKMBOX):
    """测试 4: 按键按下/释放"""
    print_section("测试 4: 按键按下/释放")

    try:
        button = 'left'
        logger.info(f"测试 {button} 按键按下/释放...")

        # 按下
        logger.info("  按下按键")
        device.press(button)
        time.sleep(0.5)

        # 检查状态
        state = device.get_button_state(button)
        logger.info(f"  按键状态: {state} (期望: 1)")

        # 释放
        logger.info("  释放按键")
        device.release(button)
        time.sleep(0.2)

        # 再次检查状态
        state = device.get_button_state(button)
        logger.info(f"  按键状态: {state} (期望: 0)")

        logger.info("✅ 按键按下/释放测试通过")
        return True

    except Exception as e:
        logger.error(f"❌ 按键按下/释放测试失败: {e}")
        return False


def test_button_state(device: MTKMBOX):
    """测试 5: 按键状态查询"""
    print_section("测试 5: 按键状态查询")

    buttons = ['left', 'right', 'middle', 'x1', 'x2']

    try:
        for button in buttons:
            state = device.get_button_state(button)
            logger.info(f"{button} 按键状态: {state}")

            if state == -1:
                logger.warning(f"  ⚠️ {button} 状态查询失败")

        logger.info("✅ 按键状态查询测试完成")
        return True

    except Exception as e:
        logger.error(f"❌ 按键状态查询测试失败: {e}")
        return False


def test_hold_function(device: MTKMBOX):
    """测试 6: 模拟按住功能"""
    print_section("测试 6: 模拟按住功能")

    try:
        button = 'left'

        # 开始按住
        logger.info(f"开始模拟按住 {button} 按键...")
        device.hold(button, interval=0.05)  # 50ms 间隔

        # 检查按住状态
        time.sleep(0.2)
        if device.is_holding(button):
            logger.info(f"  ✅ {button} 正在按住")
        else:
            logger.error(f"  ❌ {button} 未在按住状态")
            return False

        # 获取按住信息
        hold_info = device.get_hold_info(button)
        if hold_info:
            logger.info(f"  按住信息: 持续 {hold_info['duration']:.2f}s")

        # 持续按住 2 秒
        logger.info("  持续按住 2 秒...")
        time.sleep(2)

        # 停止按住
        logger.info("  停止按住...")
        device.release_hold(button)
        time.sleep(0.2)

        # 验证已停止
        if not device.is_holding(button):
            logger.info(f"  ✅ {button} 已停止按住")
        else:
            logger.error(f"  ❌ {button} 仍在按住状态")
            return False

        logger.info("✅ 模拟按住功能测试通过")
        return True

    except Exception as e:
        logger.error(f"❌ 模拟按住功能测试失败: {e}")
        return False


def test_multiple_hold(device: MTKMBOX):
    """测试 7: 多按键同时按住"""
    print_section("测试 7: 多按键同时按住")

    try:
        buttons = ['left', 'right']

        # 同时按住多个按键
        logger.info("同时按住 left 和 right...")
        for button in buttons:
            device.hold(button, interval=0.05)
            time.sleep(0.1)

        # 检查状态
        time.sleep(0.5)
        for button in buttons:
            if device.is_holding(button):
                logger.info(f"  ✅ {button} 正在按住")
            else:
                logger.error(f"  ❌ {button} 未在按住状态")
                return False

        # 持续 1 秒
        logger.info("  持续 1 秒...")
        time.sleep(1)

        # 依次释放
        logger.info("  依次释放...")
        for button in buttons:
            device.release_hold(button)
            time.sleep(0.2)

        # 验证全部释放
        for button in buttons:
            if not device.is_holding(button):
                logger.info(f"  ✅ {button} 已释放")
            else:
                logger.error(f"  ❌ {button} 仍在按住")
                return False

        logger.info("✅ 多按键同时按住测试通过")
        return True

    except Exception as e:
        logger.error(f"❌ 多按键同时按住测试失败: {e}")
        return False


def test_rapid_operations(device: MTKMBOX):
    """测试 8: 快速连续操作"""
    print_section("测试 8: 快速连续操作")

    try:
        logger.info("执行 10 次快速点击...")
        for i in range(10):
            device.click('left', delay=0.01)
            time.sleep(0.05)

        logger.info("执行快速移动...")
        for i in range(20):
            device.move(5, 5)
            time.sleep(0.01)

        logger.info("✅ 快速连续操作测试通过")
        return True

    except Exception as e:
        logger.error(f"❌ 快速连续操作测试失败: {e}")
        return False


def test_context_manager(device: MTKMBOX):
    """测试 9: 上下文管理器"""
    print_section("测试 9: 上下文管理器")

    try:
        logger.info("测试 with 语句...")

        with MTKMBOX(debug=False) as dev:
            logger.info("  设备已在上下文中打开")
            dev.move(10, 10)
            logger.info("  执行了移动操作")

        logger.info("  上下文已退出，设备应自动关闭")
        logger.info("✅ 上下文管理器测试通过")
        return True

    except Exception as e:
        logger.error(f"❌ 上下文管理器测试失败: {e}")
        return False


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("  MTKMBOX SDK 功能测试套件")
    print("=" * 60)

    results = {}

    # 测试 1: 连接
    results['连接测试'] = test_connection()

    if not results['连接测试']:
        logger.error("\n❌ 设备连接失败，无法继续测试")
        return

    # 创建设备实例用于后续测试
    try:
        device = MTKMBOX(debug=True)

        # 测试 2-8: 功能测试
        results['鼠标移动'] = test_mouse_movement(device)
        results['按键点击'] = test_button_click(device)
        results['按键按下释放'] = test_button_press_release(device)
        results['按键状态查询'] = test_button_state(device)
        results['模拟按住'] = test_hold_function(device)
        results['多按键按住'] = test_multiple_hold(device)
        results['快速操作'] = test_rapid_operations(device)

        # 关闭设备
        device.close()

        # 测试 9: 上下文管理器（独立测试）
        results['上下文管理器'] = test_context_manager(device)

    except Exception as e:
        logger.error(f"测试过程中出错: {e}")
        return

    # 打印测试结果汇总
    print_section("测试结果汇总")

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name:20s} : {status}")

    print(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        print("\n🎉 所有测试通过！SDK 功能正常")
    else:
        print(f"\n⚠️ 有 {total - passed} 个测试失败，请检查")


if __name__ == '__main__':
    try:
        run_all_tests()
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        logger.error(f"测试运行失败: {e}", exc_info=True)
