import multiprocessing as mp
import time
import cv2
import numpy as np
import mss
from yolo_detector import YOLOv8Detector
from config_manager import get_config


def run_benchmark():
    """修正后的性能测试"""
    print("=" * 60)
    print("性能基准测试（修正版）")
    print("=" * 60)

    model = YOLOv8Detector()
    crop_size = get_config('CROP_SIZE', 320)

    print(f"\n测试配置:")
    print(f"   截图区域: {crop_size}x{crop_size}")
    print(f"   YOLO 输入: {model.img_size}x{model.img_size}")
    print(f"   Provider: {model.session.get_providers()[0]}")

    # ==================== 测试1：纯mss截图速度 ====================
    print("\n" + "=" * 60)
    print("测试1: 纯 mss 截图速度（无队列，1000次）")
    print("=" * 60)

    with mss.mss() as sct:
        monitor = sct.monitors[1]
        crop_area = {
            'left': monitor['width'] // 2 - crop_size // 2,
            'top': monitor['height'] // 2 - crop_size // 2,
            'width': crop_size,
            'height': crop_size
        }

        # 预热
        for _ in range(10):
            sct.grab(crop_area)

        capture_times = []
        for _ in range(1000):
            start = time.perf_counter()
            img = sct.grab(crop_area)
            _ = np.array(img)  # 包含转换时间
            capture_times.append((time.perf_counter() - start) * 1000)

    avg_capture = sum(capture_times) / len(capture_times)
    p50 = sorted(capture_times)[500]
    p99 = sorted(capture_times)[990]

    print(f"   平均: {avg_capture:.2f}ms")
    print(f"   P50:  {p50:.2f}ms")
    print(f"   P99:  {p99:.2f}ms")
    print(f"   理论最大 FPS: {1000 / avg_capture:.1f}")

    # ==================== 测试2：纯YOLO推理 ====================
    print("\n" + "=" * 60)
    print("测试2: 纯 YOLO 推理速度（1000次）")
    print("=" * 60)

    with mss.mss() as sct:
        img = np.array(sct.grab(crop_area))
        img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    # 预热
    for _ in range(10):
        model.predict(img_bgr)

    inference_times = []
    for _ in range(1000):
        start = time.perf_counter()
        model.predict(img_bgr)
        inference_times.append((time.perf_counter() - start) * 1000)

    avg_inference = sum(inference_times) / len(inference_times)
    p50_inf = sorted(inference_times)[500]
    p99_inf = sorted(inference_times)[990]

    print(f"   平均: {avg_inference:.2f}ms")
    print(f"   P50:  {p50_inf:.2f}ms")
    print(f"   P99:  {p99_inf:.2f}ms")
    print(f"   理论最大 FPS: {1000 / avg_inference:.1f}")

    # ==================== 测试3：串行完整流程 ====================
    print("\n" + "=" * 60)
    print("测试3: 串行完整流程（截图+转换+推理，500次）")
    print("=" * 60)

    with mss.mss() as sct:
        full_times = []
        capture_only = []
        convert_only = []
        infer_only = []

        for _ in range(500):
            t0 = time.perf_counter()

            img = sct.grab(crop_area)
            img_np = np.array(img)
            t1 = time.perf_counter()

            img_bgr = cv2.cvtColor(img_np, cv2.COLOR_BGRA2BGR)
            t2 = time.perf_counter()

            model.predict(img_bgr)
            t3 = time.perf_counter()

            capture_only.append((t1 - t0) * 1000)
            convert_only.append((t2 - t1) * 1000)
            infer_only.append((t3 - t2) * 1000)
            full_times.append((t3 - t0) * 1000)

    avg_full = sum(full_times) / len(full_times)

    print(
        f"   截图:   {sum(capture_only) / len(capture_only):.2f}ms ({sum(capture_only) / sum(full_times) * 100:.1f}%)")
    print(
        f"   转换:   {sum(convert_only) / len(convert_only):.2f}ms ({sum(convert_only) / sum(full_times) * 100:.1f}%)")
    print(f"   推理:   {sum(infer_only) / len(infer_only):.2f}ms ({sum(infer_only) / sum(full_times) * 100:.1f}%)")
    print(f"   总计:   {avg_full:.2f}ms")
    print(f"   串行 FPS: {1000 / avg_full:.1f}")

    # ==================== 测试4：并行流程（真实场景）====================
    print("\n" + "=" * 60)
    print("测试4: 并行流程（截图进程+推理进程，2秒）")
    print("=" * 60)

    from screen_capture import capture_screen

    frame_queue = mp.Queue(maxsize=5)
    capture_ready_event = mp.Event()

    capture_process = mp.Process(
        target=capture_screen,
        args=(frame_queue, capture_ready_event, crop_size),
        daemon=True
    )
    capture_process.start()
    capture_ready_event.wait()

    # 清空队列（消除启动延迟）
    time.sleep(0.2)
    while not frame_queue.empty():
        try:
            frame_queue.get_nowait()
        except:
            break

    # 测试：尽可能快地处理帧
    frame_count = 0
    start_time = time.perf_counter()
    test_duration = 2.0  # 测试2秒

    process_times = []

    while time.perf_counter() - start_time < test_duration:
        try:
            img_bgra = frame_queue.get(timeout=0.1)
        except:
            continue

        t0 = time.perf_counter()
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
        model.predict(img_bgr)
        process_times.append((time.perf_counter() - t0) * 1000)

        frame_count += 1

    elapsed = time.perf_counter() - start_time
    actual_fps = frame_count / elapsed
    avg_process = sum(process_times) / len(process_times) if process_times else 0

    print(f"   处理帧数: {frame_count}")
    print(f"   实际 FPS: {actual_fps:.1f}")
    print(f"   每帧处理: {avg_process:.2f}ms")
    print(f"   队列利用率: {frame_count / (elapsed * get_config('CAPTURE_FPS', 120)) * 100:.1f}%")

    capture_process.terminate()
    capture_process.join()

    # ==================== 瓶颈分析 ====================
    print("\n" + "=" * 60)
    print("瓶颈分析")
    print("=" * 60)

    theoretical_max = 1000 / (avg_capture + avg_inference)
    parallel_max = 1000 / max(avg_capture, avg_inference)

    print(f"\n   理论极限（串行）: {theoretical_max:.1f} FPS")
    print(f"   理论极限（并行）: {parallel_max:.1f} FPS")
    print(f"   实际达成: {actual_fps:.1f} FPS")
    print(f"   效率: {actual_fps / parallel_max * 100:.1f}%")

    if avg_inference > avg_capture:
        print(f"\n   🔴 瓶颈: YOLO推理 ({avg_inference:.2f}ms)")
        print(f"   建议: 降低模型分辨率、使用FP16模型")
    else:
        print(f"\n   🟡 瓶颈: 屏幕截图 ({avg_capture:.2f}ms)")
        print(f"   建议: 当前已达硬件极限，可考虑DXcam")

    # ==================== 最终建议 ====================
    print("\n" + "=" * 60)
    print("推荐配置")
    print("=" * 60)

    safe_fps = int(actual_fps * 0.9)

    print(f'''
{{
    "CAPTURE_FPS": {min(144, int(1000 / avg_capture))},
    "INFERENCE_FPS": {safe_fps},
    "CROP_SIZE": {crop_size}
}}
''')

    print("=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == '__main__':
    mp.freeze_support()
    run_benchmark()
