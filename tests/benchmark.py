# benchmark.py
"""
性能基准测试 - MSS vs DXcam 对比版
"""

import multiprocessing as mp
import time
import cv2
import numpy as np
import mss

from yolo_detector import YOLOv8Detector
from config_manager import get_config


def test_mss_capture(crop_size, iterations=1000):
    """测试 MSS 截图性能"""
    print("\n" + "-" * 50)
    print(f"MSS 截图测试 ({iterations}次)")
    print("-" * 50)

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
        for _ in range(iterations):
            start = time.perf_counter()
            img = sct.grab(crop_area)
            _ = np.array(img)
            capture_times.append((time.perf_counter() - start) * 1000)

    avg = sum(capture_times) / len(capture_times)
    p50 = sorted(capture_times)[len(capture_times) // 2]
    p99 = sorted(capture_times)[int(len(capture_times) * 0.99)]

    print(f"   平均: {avg:.3f}ms")
    print(f"   P50:  {p50:.3f}ms")
    print(f"   P99:  {p99:.3f}ms")
    print(f"   理论最大 FPS: {1000 / avg:.1f}")

    return avg, crop_area


def test_dxcam_capture(crop_size, iterations=1000):
    """测试 DXcam 截图性能"""
    print("\n" + "-" * 50)
    print(f"DXcam 截图测试 ({iterations}次)")
    print("-" * 50)

    try:
        import dxcam
    except ImportError:
        print("   ⚠️ DXcam 未安装，跳过测试")
        print("   安装命令: pip install dxcam")
        return None, None

    camera = None
    try:
        camera = dxcam.create(output_idx=0, output_color="BGR")

        if camera is None:
            print("   ⚠️ 无法创建 DXcam 相机")
            return None, None

        # 计算捕获区域
        screen_width = camera.width
        screen_height = camera.height
        left = screen_width // 2 - crop_size // 2
        top = screen_height // 2 - crop_size // 2
        right = left + crop_size
        bottom = top + crop_size
        region = (left, top, right, bottom)

        print(f"   屏幕分辨率: {screen_width}x{screen_height}")
        print(f"   捕获区域: {region}")

        # ==================== 测试1：单帧截图模式 ====================
        print("\n   [模式1] 单帧截图 (grab):")

        # 预热
        for _ in range(10):
            camera.grab(region=region)

        grab_times = []
        for _ in range(iterations):
            start = time.perf_counter()
            frame = camera.grab(region=region)
            if frame is not None:
                grab_times.append((time.perf_counter() - start) * 1000)

        if grab_times:
            avg_grab = sum(grab_times) / len(grab_times)
            p50_grab = sorted(grab_times)[len(grab_times) // 2]
            p99_grab = sorted(grab_times)[int(len(grab_times) * 0.99)]

            print(f"      平均: {avg_grab:.3f}ms")
            print(f"      P50:  {p50_grab:.3f}ms")
            print(f"      P99:  {p99_grab:.3f}ms")
            print(f"      理论最大 FPS: {1000 / avg_grab:.1f}")
        else:
            avg_grab = None
            print("      ⚠️ 未获取到有效帧")

        # ==================== 测试2：连续捕获模式 ====================
        print("\n   [模式2] 连续捕获 (start + get_latest_frame):")

        target_fps = 240  # 测试用高帧率
        camera.start(region=region, target_fps=target_fps, video_mode=True)

        # 等待启动稳定
        time.sleep(0.5)

        stream_times = []
        null_frames = 0

        for _ in range(iterations):
            start = time.perf_counter()
            frame = camera.get_latest_frame()
            elapsed = (time.perf_counter() - start) * 1000

            if frame is not None:
                stream_times.append(elapsed)
            else:
                null_frames += 1

        camera.stop()

        if stream_times:
            avg_stream = sum(stream_times) / len(stream_times)
            p50_stream = sorted(stream_times)[len(stream_times) // 2]
            p99_stream = sorted(stream_times)[int(len(stream_times) * 0.99)]

            print(f"      平均: {avg_stream:.3f}ms")
            print(f"      P50:  {p50_stream:.3f}ms")
            print(f"      P99:  {p99_stream:.3f}ms")
            print(f"      空帧率: {null_frames / iterations * 100:.1f}%")
            print(f"      理论最大 FPS: {1000 / avg_stream:.1f}")
        else:
            avg_stream = None
            print("      ⚠️ 未获取到有效帧")

        # ==================== 测试3：实际吞吐量测试 ====================
        print("\n   [模式3] 实际吞吐量测试 (2秒):")

        camera.start(region=region, target_fps=target_fps, video_mode=True)
        time.sleep(0.2)  # 稳定

        frame_count = 0
        start_time = time.perf_counter()
        test_duration = 2.0

        while time.perf_counter() - start_time < test_duration:
            frame = camera.get_latest_frame()
            if frame is not None:
                frame_count += 1

        elapsed = time.perf_counter() - start_time
        actual_fps = frame_count / elapsed

        camera.stop()

        print(f"      捕获帧数: {frame_count}")
        print(f"      实际 FPS: {actual_fps:.1f}")
        print(f"      每帧耗时: {1000 / actual_fps:.3f}ms")

        return avg_stream if avg_stream else avg_grab, region

    except Exception as e:
        print(f"   ⚠️ DXcam 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None, None

    finally:
        if camera is not None:
            try:
                camera.stop()
            except:
                pass
            del camera


def test_inference(model, img_bgr, iterations=1000):
    """测试 YOLO 推理性能"""
    print("\n" + "-" * 50)
    print(f"YOLO 推理测试 ({iterations}次)")
    print("-" * 50)

    # 预热
    for _ in range(20):
        model.predict(img_bgr)

    inference_times = []
    for _ in range(iterations):
        start = time.perf_counter()
        model.predict(img_bgr)
        inference_times.append((time.perf_counter() - start) * 1000)

    avg = sum(inference_times) / len(inference_times)
    p50 = sorted(inference_times)[len(inference_times) // 2]
    p99 = sorted(inference_times)[int(len(inference_times) * 0.99)]
    min_time = min(inference_times)
    max_time = max(inference_times)

    print(f"   平均: {avg:.3f}ms")
    print(f"   P50:  {p50:.3f}ms")
    print(f"   P99:  {p99:.3f}ms")
    print(f"   最小: {min_time:.3f}ms")
    print(f"   最大: {max_time:.3f}ms")
    print(f"   理论最大 FPS: {1000 / avg:.1f}")

    return avg


def test_full_pipeline_mss(model, crop_area, iterations=500):
    """测试 MSS 完整流程"""
    print("\n" + "-" * 50)
    print(f"MSS 完整流程测试 ({iterations}次)")
    print("-" * 50)

    with mss.mss() as sct:
        capture_times = []
        convert_times = []
        infer_times = []
        total_times = []

        for _ in range(iterations):
            t0 = time.perf_counter()

            img = sct.grab(crop_area)
            img_np = np.array(img)
            t1 = time.perf_counter()

            img_bgr = cv2.cvtColor(img_np, cv2.COLOR_BGRA2BGR)
            t2 = time.perf_counter()

            model.predict(img_bgr)
            t3 = time.perf_counter()

            capture_times.append((t1 - t0) * 1000)
            convert_times.append((t2 - t1) * 1000)
            infer_times.append((t3 - t2) * 1000)
            total_times.append((t3 - t0) * 1000)

    avg_total = sum(total_times) / len(total_times)

    print(f"   截图:  {sum(capture_times) / len(capture_times):.3f}ms "
          f"({sum(capture_times) / sum(total_times) * 100:.1f}%)")
    print(f"   转换:  {sum(convert_times) / len(convert_times):.3f}ms "
          f"({sum(convert_times) / sum(total_times) * 100:.1f}%)")
    print(f"   推理:  {sum(infer_times) / len(infer_times):.3f}ms "
          f"({sum(infer_times) / sum(total_times) * 100:.1f}%)")
    print(f"   总计:  {avg_total:.3f}ms")
    print(f"   串行 FPS: {1000 / avg_total:.1f}")

    return avg_total


def test_full_pipeline_dxcam(model, crop_size, iterations=500):
    """测试 DXcam 完整流程"""
    print("\n" + "-" * 50)
    print(f"DXcam 完整流程测试 ({iterations}次)")
    print("-" * 50)

    try:
        import dxcam
    except ImportError:
        print("   ⚠️ DXcam 未安装，跳过测试")
        return None

    camera = None
    try:
        camera = dxcam.create(output_idx=0, output_color="BGR")

        if camera is None:
            print("   ⚠️ 无法创建 DXcam 相机")
            return None

        # 计算区域
        left = camera.width // 2 - crop_size // 2
        top = camera.height // 2 - crop_size // 2
        right = left + crop_size
        bottom = top + crop_size
        region = (left, top, right, bottom)

        # 启动连续捕获
        camera.start(region=region, target_fps=240, video_mode=True)
        time.sleep(0.3)

        capture_times = []
        infer_times = []
        total_times = []

        for _ in range(iterations):
            t0 = time.perf_counter()

            frame = camera.get_latest_frame()
            t1 = time.perf_counter()

            if frame is None:
                continue

            # DXcam 输出已经是 BGR，无需转换
            model.predict(frame)
            t2 = time.perf_counter()

            capture_times.append((t1 - t0) * 1000)
            infer_times.append((t2 - t1) * 1000)
            total_times.append((t2 - t0) * 1000)

        camera.stop()

        if not total_times:
            print("   ⚠️ 未获取到有效帧")
            return None

        avg_total = sum(total_times) / len(total_times)

        print(f"   截图:  {sum(capture_times) / len(capture_times):.3f}ms "
              f"({sum(capture_times) / sum(total_times) * 100:.1f}%)")
        print(f"   推理:  {sum(infer_times) / len(infer_times):.3f}ms "
              f"({sum(infer_times) / sum(total_times) * 100:.1f}%)")
        print(f"   总计:  {avg_total:.3f}ms")
        print(f"   串行 FPS: {1000 / avg_total:.1f}")
        print(f"   (无需颜色转换，节省约 0.3-0.5ms)")

        return avg_total

    except Exception as e:
        print(f"   ⚠️ DXcam 测试失败: {e}")
        return None

    finally:
        if camera is not None:
            try:
                camera.stop()
            except:
                pass
            del camera


def test_parallel_dxcam(model, crop_size, duration=3.0):
    """测试 DXcam 并行流程"""
    print("\n" + "-" * 50)
    print(f"DXcam 并行流程测试 ({duration}秒)")
    print("-" * 50)

    try:
        from screen_capture import capture_screen
    except ImportError:
        print("   ⚠️ screen_capture 模块不可用")
        return None

    frame_queue = mp.Queue(maxsize=5)
    capture_ready_event = mp.Event()
    stop_event = mp.Event()

    capture_process = mp.Process(
        target=capture_screen,
        args=(frame_queue, capture_ready_event, crop_size, stop_event),
        daemon=True
    )
    capture_process.start()

    if not capture_ready_event.wait(timeout=10):
        print("   ⚠️ 捕获进程启动超时")
        capture_process.terminate()
        return None

    # 等待稳定并清空队列
    time.sleep(0.3)
    while not frame_queue.empty():
        try:
            frame_queue.get_nowait()
        except:
            break

    # 测试
    frame_count = 0
    process_times = []
    queue_wait_times = []
    start_time = time.perf_counter()

    while time.perf_counter() - start_time < duration:
        try:
            t0 = time.perf_counter()
            img_bgr = frame_queue.get(timeout=0.1)
            t1 = time.perf_counter()

            model.predict(img_bgr)
            t2 = time.perf_counter()

            queue_wait_times.append((t1 - t0) * 1000)
            process_times.append((t2 - t1) * 1000)
            frame_count += 1

        except:
            continue

    elapsed = time.perf_counter() - start_time

    # 清理
    stop_event.set()
    capture_process.join(timeout=2)
    if capture_process.is_alive():
        capture_process.terminate()

    if frame_count == 0:
        print("   ⚠️ 未处理任何帧")
        return None

    actual_fps = frame_count / elapsed
    avg_process = sum(process_times) / len(process_times)
    avg_queue_wait = sum(queue_wait_times) / len(queue_wait_times)

    print(f"   处理帧数: {frame_count}")
    print(f"   实际 FPS: {actual_fps:.1f}")
    print(f"   队列等待: {avg_queue_wait:.3f}ms")
    print(f"   推理耗时: {avg_process:.3f}ms")
    print(f"   每帧总计: {1000 / actual_fps:.3f}ms")

    return actual_fps


def run_benchmark():
    """完整性能基准测试"""
    print("=" * 60)
    print("性能基准测试 (MSS vs DXcam)")
    print("=" * 60)

    # 初始化
    model = YOLOv8Detector()
    crop_size = get_config('CROP_SIZE', 320)

    print(f"\n测试配置:")
    print(f"   截图区域: {crop_size}x{crop_size}")
    print(f"   YOLO 输入: {model.img_size}x{model.img_size}")
    print(f"   Provider: {model.session.get_providers()[0]}")

    # ==================== 截图性能对比 ====================
    print("\n" + "=" * 60)
    print("测试1: 截图性能对比")
    print("=" * 60)

    mss_time, mss_area = test_mss_capture(crop_size, 1000)
    dxcam_time, dxcam_region = test_dxcam_capture(crop_size, 1000)

    if mss_time and dxcam_time:
        speedup = mss_time / dxcam_time
        print(f"\n   📊 对比结果:")
        print(f"      MSS:    {mss_time:.3f}ms")
        print(f"      DXcam:  {dxcam_time:.3f}ms")
        print(f"      提升:   {speedup:.1f}x {'✓' if speedup > 1 else ''}")

    # ==================== 推理性能 ====================
    print("\n" + "=" * 60)
    print("测试2: YOLO 推理性能")
    print("=" * 60)

    # 获取测试图像
    with mss.mss() as sct:
        img = np.array(sct.grab(mss_area))
        img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    infer_time = test_inference(model, img_bgr, 1000)

    # ==================== 完整流程对比 ====================
    print("\n" + "=" * 60)
    print("测试3: 完整流程对比 (串行)")
    print("=" * 60)

    mss_full_time = test_full_pipeline_mss(model, mss_area, 500)
    dxcam_full_time = test_full_pipeline_dxcam(model, crop_size, 500)

    if mss_full_time and dxcam_full_time:
        speedup = mss_full_time / dxcam_full_time
        print(f"\n   📊 对比结果:")
        print(f"      MSS 串行:    {mss_full_time:.3f}ms ({1000 / mss_full_time:.1f} FPS)")
        print(f"      DXcam 串行:  {dxcam_full_time:.3f}ms ({1000 / dxcam_full_time:.1f} FPS)")
        print(f"      提升:        {speedup:.2f}x")

    # ==================== 并行流程测试 ====================
    print("\n" + "=" * 60)
    print("测试4: DXcam 并行流程 (真实场景)")
    print("=" * 60)

    parallel_fps = test_parallel_dxcam(model, crop_size, 3.0)

    # ==================== 综合分析 ====================
    print("\n" + "=" * 60)
    print("综合分析")
    print("=" * 60)

    print(f"\n   各环节耗时:")
    print(f"   ┌─────────────────────────────────────────┐")
    print(f"   │ MSS 截图:      {mss_time:.3f}ms              │")
    if dxcam_time:
        print(f"   │ DXcam 截图:    {dxcam_time:.3f}ms              │")
    print(f"   │ YOLO 推理:     {infer_time:.3f}ms              │")
    print(f"   └─────────────────────────────────────────┘")

    # 瓶颈分析
    capture_time = dxcam_time if dxcam_time else mss_time

    print(f"\n   瓶颈分析:")
    if infer_time > capture_time:
        bottleneck_ratio = infer_time / capture_time
        print(f"   🔴 瓶颈: YOLO 推理 ({infer_time:.2f}ms)")
        print(f"      推理耗时是截图的 {bottleneck_ratio:.1f} 倍")
        print(f"      建议: 使用更小模型 / FP16 / TensorRT")
    else:
        bottleneck_ratio = capture_time / infer_time
        print(f"   🟡 瓶颈: 屏幕截图 ({capture_time:.2f}ms)")
        print(f"      截图耗时是推理的 {bottleneck_ratio:.1f} 倍")
        print(f"      建议: 已达硬件极限")

    # 理论极限
    theoretical_serial = 1000 / (capture_time + infer_time)
    theoretical_parallel = 1000 / max(capture_time, infer_time)

    print(f"\n   理论极限:")
    print(f"      串行: {theoretical_serial:.1f} FPS")
    print(f"      并行: {theoretical_parallel:.1f} FPS")

    if parallel_fps:
        efficiency = parallel_fps / theoretical_parallel * 100
        print(f"      实际: {parallel_fps:.1f} FPS (效率 {efficiency:.1f}%)")

    # ==================== 推荐配置 ====================
    print("\n" + "=" * 60)
    print("推荐配置")
    print("=" * 60)

    if parallel_fps:
        safe_fps = int(parallel_fps * 0.9)
    else:
        safe_fps = int(theoretical_serial * 0.8)

    capture_fps = min(240, int(1000 / capture_time * 1.2))

    print(f'''
{{
    "_comment": "基于测试结果的推荐配置",
    "CAPTURE_FPS": {capture_fps},
    "INFERENCE_FPS": {safe_fps},
    "CROP_SIZE": {crop_size},
    "USE_DXCAM": true
}}
''')

    # DXcam vs MSS 总结
    print("\n" + "-" * 50)
    print("MSS vs DXcam 总结")
    print("-" * 50)

    print("""
    ┌──────────────┬─────────────┬─────────────┐
    │     特性     │     MSS     │    DXcam    │
    ├──────────────┼─────────────┼─────────────┤
    │   截图速度   │    较慢     │   极快 ⭐   │
    │   CPU 占用   │    较高     │     低      │
    │   兼容性     │   全平台    │  仅 Windows │
    │   颜色格式   │    BGRA     │ BGR (可选)  │
    │   需要转换   │     是      │     否      │
    └──────────────┴─────────────┴─────────────┘
    """)

    if dxcam_time and mss_time:
        print(f"    📊 本机测试: DXcam 比 MSS 快 {mss_time / dxcam_time:.1f}x")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == '__main__':
    mp.freeze_support()
    run_benchmark()
