import multiprocessing as mp
import time

import cv2

from yolo_detector import YOLOv8Detector


def run_benchmark():
    """主测试函数"""
    print("=" * 60)
    print("性能基准测试（使用真实截图流程）")
    print("=" * 60)

    # 初始化
    model = YOLOv8Detector()
    crop_size = 256

    print(f"\n测试配置:")
    print(f"   截图区域: {crop_size}x{crop_size}")
    print(f"   YOLO 模型: {model.img_size}x{model.img_size}")
    print(f"   Provider: {model.session.get_providers()[0]}")

    # ==================== 测试1：纯截图速度（使用 screen_capture）====================
    print("\n" + "=" * 60)
    print("测试1: 纯截图速度（使用真实捕获流程，100次）")
    print("=" * 60)

    from screen_capture import capture_screen

    frame_queue = mp.Queue(maxsize=10)
    capture_ready_event = mp.Event()

    # 启动截图进程
    capture_process = mp.Process(
        target=capture_screen,
        args=(frame_queue, capture_ready_event, crop_size),
        daemon=True
    )
    capture_process.start()
    capture_ready_event.wait()  # 等待截图进程就绪
    time.sleep(0.5)  # 让队列填充

    capture_times = []
    for i in range(100):
        start = time.perf_counter()
        img = frame_queue.get()  # 从队列获取
        capture_times.append((time.perf_counter() - start) * 1000)

    avg_capture = sum(capture_times) / len(capture_times)
    min_capture = min(capture_times)
    max_capture = max(capture_times)

    print(f"   平均: {avg_capture:.2f}ms")
    print(f"   最快: {min_capture:.2f}ms")
    print(f"   最慢: {max_capture:.2f}ms")
    print(f"   理论最大 FPS: {1000 / avg_capture:.1f}")

    # ==================== 测试2：纯 YOLO 推理速度 ====================
    print("\n" + "=" * 60)
    print("测试2: 纯 YOLO 推理速度（100次）")
    print("=" * 60)

    # 先从队列获取一张图
    img_bgra = frame_queue.get()
    img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)

    inference_times = []
    for i in range(100):
        start = time.perf_counter()
        results = model.predict(img_bgr)
        inference_times.append((time.perf_counter() - start) * 1000)

    avg_inference = sum(inference_times) / len(inference_times)
    min_inference = min(inference_times)
    max_inference = max(inference_times)

    print(f"   平均: {avg_inference:.2f}ms")
    print(f"   最快: {min_inference:.2f}ms")
    print(f"   最慢: {max_inference:.2f}ms")
    print(f"   理论最大 FPS: {1000 / avg_inference:.1f}")

    # ==================== 测试3：完整流程（模拟真实运行）====================
    print("\n" + "=" * 60)
    print("测试3: 完整流程（队列 + 截图 + 推理，100次）")
    print("=" * 60)

    full_times = []
    queue_wait_times = []
    conversion_times = []
    actual_inference_times = []

    for i in range(100):
        full_start = time.perf_counter()

        # 1. 从队列获取图像（模拟进程间通信）
        queue_start = time.perf_counter()
        img_bgra = frame_queue.get()
        queue_wait_times.append((time.perf_counter() - queue_start) * 1000)

        # 2. 颜色转换
        conversion_start = time.perf_counter()
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        conversion_times.append((time.perf_counter() - conversion_start) * 1000)

        # 3. 推理
        inference_start = time.perf_counter()
        results = model.predict(img_bgr)
        actual_inference_times.append((time.perf_counter() - inference_start) * 1000)

        full_times.append((time.perf_counter() - full_start) * 1000)

    avg_full = sum(full_times) / len(full_times)
    min_full = min(full_times)
    max_full = max(full_times)
    avg_queue_wait = sum(queue_wait_times) / len(queue_wait_times)
    avg_conversion = sum(conversion_times) / len(conversion_times)
    avg_actual_inference = sum(actual_inference_times) / len(actual_inference_times)

    print(f"   平均: {avg_full:.2f}ms")
    print(f"   最快: {min_full:.2f}ms")
    print(f"   最慢: {max_full:.2f}ms")
    print(f"   实际最大 FPS: {1000 / avg_full:.1f}")

    # ==================== 性能分析（详细版）====================
    print("\n" + "=" * 60)
    print("性能瓶颈分析（详细）")
    print("=" * 60)

    queue_percent = (avg_queue_wait / avg_full) * 100
    conversion_percent = (avg_conversion / avg_full) * 100
    inference_percent = (avg_actual_inference / avg_full) * 100
    overhead_percent = 100 - queue_percent - conversion_percent - inference_percent

    print(f"   队列等待: {avg_queue_wait:.2f}ms ({queue_percent:.1f}%)")
    print(f"   颜色转换: {avg_conversion:.2f}ms ({conversion_percent:.1f}%)")
    print(f"   推理耗时: {avg_actual_inference:.2f}ms ({inference_percent:.1f}%)")
    print(f"   其他开销: {overhead_percent:.1f}%")

    # 判断瓶颈
    if inference_percent > 50:
        print(f"\n   🔴 主要瓶颈: YOLO 推理（{inference_percent:.1f}%）")
        print(f"   建议: 降低模型分辨率或使用量化模型")
    elif queue_percent > 30:
        print(f"\n   🟡 次要瓶颈: 队列等待（{queue_percent:.1f}%）")
        print(f"   建议: 增大队列大小或优化截图频率")
    else:
        print(f"\n   ✅ 性能均衡")

    # ==================== 推荐配置 ====================
    print("\n" + "=" * 60)
    print("推荐配置")
    print("=" * 60)

    max_fps = int(1000 / avg_full * 0.9)  # 留 10% 余量

    # 根据实际 FPS 计算 KP
    target_fps = 60
    delay_factor = target_fps / max_fps
    safe_kp = 0.95 / delay_factor
    recommended_kp = round(safe_kp * 0.9, 2)  # 保守估计

    print(f'''
{{
    "CAPTURE_FPS": {max_fps},
    "INFERENCE_FPS": {max_fps},
    "PID_KP": {recommended_kp},
    "PID_KD": {0.05 + (delay_factor - 1) * 0.1:.2f}
}}
''')

    # ==================== 与简单测试对比 ====================
    print("\n" + "=" * 60)
    print("与直接 mss 测试的对比")
    print("=" * 60)

    import mss
    import numpy as np

    with mss.mss() as sct:
        monitor = sct.monitors[1]
        crop_area = {
            'left': monitor['width'] // 2 - crop_size // 2,
            'top': monitor['height'] // 2 - crop_size // 2,
            'width': crop_size,
            'height': crop_size
        }

        direct_times = []
        for i in range(100):
            start = time.perf_counter()
            img = np.array(sct.grab(crop_area))
            img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            results = model.predict(img_bgr)
            direct_times.append((time.perf_counter() - start) * 1000)

    avg_direct = sum(direct_times) / len(direct_times)

    print(f"   直接 mss 测试: {avg_direct:.2f}ms ({1000/avg_direct:.1f} FPS)")
    print(f"   真实流程测试: {avg_full:.2f}ms ({1000/avg_full:.1f} FPS)")
    print(f"   性能差距: {((avg_full - avg_direct) / avg_direct * 100):.1f}%")
    print(f"   差距来源: 队列通信开销 ({avg_queue_wait:.2f}ms)")

    # 清理进程
    capture_process.terminate()
    capture_process.join()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == '__main__':
    # Windows 多进程必需
    mp.freeze_support()
    run_benchmark()
