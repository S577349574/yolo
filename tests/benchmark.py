# benchmark.py
"""
性能基准测试 - 简化版(10秒测试)
只测试: MSS截图 + YOLO推理
"""

import time
import numpy as np
import mss
import cv2

from yolo_detector import YOLOv8Detector
from config_manager import get_config


def test_capture_and_inference(duration=10.0):
    """测试截图+推理完整流程"""
    print("\n" + "=" * 60)
    print(f"完整流程测试 (运行 {duration} 秒)")
    print("=" * 60)

    # 初始化
    model = YOLOv8Detector()
    crop_size = get_config('CROP_SIZE', 320)

    print(f"\n配置:")
    print(f"   截图区域: {crop_size}x{crop_size}")
    print(f"   YOLO 输入: {model.img_size}x{model.img_size}")
    print(f"   Provider: {model.session.get_providers()[0]}")

    # 计算截图区域
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        crop_area = {
            'left': monitor['width'] // 2 - crop_size // 2,
            'top': monitor['height'] // 2 - crop_size // 2,
            'width': crop_size,
            'height': crop_size
        }

        print(f"   屏幕分辨率: {monitor['width']}x{monitor['height']}")
        print(f"   截图区域: ({crop_area['left']},{crop_area['top']}) → "
              f"({crop_area['left'] + crop_size},{crop_area['top'] + crop_size})")

    # ==================== 阶段1: 单独测试截图 ====================
    print("\n" + "-" * 50)
    print("阶段1: 纯截图性能 (1000次)")
    print("-" * 50)

    with mss.mss() as sct:
        # 预热
        for _ in range(10):
            sct.grab(crop_area)

        capture_times = []
        for _ in range(1000):
            start = time.perf_counter()
            img = sct.grab(crop_area)
            _ = np.array(img)
            capture_times.append((time.perf_counter() - start) * 1000)

    avg_capture = sum(capture_times) / len(capture_times)
    min_capture = min(capture_times)
    max_capture = max(capture_times)
    p99_capture = sorted(capture_times)[int(len(capture_times) * 0.99)]

    print(f"   平均: {avg_capture:.3f}ms")
    print(f"   最小: {min_capture:.3f}ms")
    print(f"   最大: {max_capture:.3f}ms")
    print(f"   P99:  {p99_capture:.3f}ms")
    print(f"   标准差: {np.std(capture_times):.3f}ms")
    print(f"   理论最大 FPS: {1000 / avg_capture:.1f}")

    # ==================== 阶段2: 单独测试推理 ====================
    print("\n" + "-" * 50)
    print("阶段2: 纯推理性能 (1000次)")
    print("-" * 50)

    # 准备测试图像
    with mss.mss() as sct:
        img = np.array(sct.grab(crop_area))
        img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    # 预热
    for _ in range(20):
        model.predict(img_bgr)

    inference_times = []
    for _ in range(1000):
        start = time.perf_counter()
        model.predict(img_bgr)
        inference_times.append((time.perf_counter() - start) * 1000)

    avg_infer = sum(inference_times) / len(inference_times)
    min_infer = min(inference_times)
    max_infer = max(inference_times)
    p99_infer = sorted(inference_times)[int(len(inference_times) * 0.99)]

    print(f"   平均: {avg_infer:.3f}ms")
    print(f"   最小: {min_infer:.3f}ms")
    print(f"   最大: {max_infer:.3f}ms")
    print(f"   P99:  {p99_infer:.3f}ms")
    print(f"   标准差: {np.std(inference_times):.3f}ms")
    print(f"   理论最大 FPS: {1000 / avg_infer:.1f}")

    # ==================== 阶段3: 完整流程 (10秒持续测试) ====================
    print("\n" + "-" * 50)
    print(f"阶段3: 完整流程持续测试 ({duration}秒)")
    print("-" * 50)

    with mss.mss() as sct:
        capture_times = []
        convert_times = []
        infer_times = []
        total_times = []

        frame_count = 0
        start_time = time.perf_counter()
        last_print = start_time

        print("\n   实时监控:")
        print("   " + "-" * 45)

        while time.perf_counter() - start_time < duration:
            t0 = time.perf_counter()

            # 截图
            img = sct.grab(crop_area)
            img_np = np.array(img)
            t1 = time.perf_counter()

            # 转换
            img_bgr = cv2.cvtColor(img_np, cv2.COLOR_BGRA2BGR)
            t2 = time.perf_counter()

            # 推理
            results = model.predict(img_bgr)
            t3 = time.perf_counter()

            # 记录
            capture_times.append((t1 - t0) * 1000)
            convert_times.append((t2 - t1) * 1000)
            infer_times.append((t3 - t2) * 1000)
            total_times.append((t3 - t0) * 1000)
            frame_count += 1

            # 每秒打印一次
            current_time = time.perf_counter()
            if current_time - last_print >= 1.0:
                elapsed = current_time - start_time
                current_fps = frame_count / elapsed
                recent_fps = len(total_times[-100:]) / sum(total_times[-100:]) * 1000

                print(f"   [{elapsed:.1f}s] 总帧数: {frame_count} | "
                      f"平均FPS: {current_fps:.1f} | "
                      f"近期FPS: {recent_fps:.1f}")
                last_print = current_time

    elapsed_total = time.perf_counter() - start_time

    # ==================== 统计分析 ====================
    print("\n" + "=" * 60)
    print("统计结果")
    print("=" * 60)

    avg_total = sum(total_times) / len(total_times)
    avg_cap = sum(capture_times) / len(capture_times)
    avg_cvt = sum(convert_times) / len(convert_times)
    avg_inf = sum(infer_times) / len(infer_times)

    print(f"\n   【各环节平均耗时】")
    print(f"   ┌─────────────────────────────────────────┐")
    print(f"   │ 1. 截图:  {avg_cap:6.3f}ms ({avg_cap / avg_total * 100:5.1f}%) │")
    print(f"   │ 2. 转换:  {avg_cvt:6.3f}ms ({avg_cvt / avg_total * 100:5.1f}%) │")
    print(f"   │ 3. 推理:  {avg_inf:6.3f}ms ({avg_inf / avg_total * 100:5.1f}%) │")
    print(f"   │─────────────────────────────────────────│")
    print(f"   │ 总计:    {avg_total:6.3f}ms (100.0%)        │")
    print(f"   └─────────────────────────────────────────┘")

    print(f"\n   【各环节波动情况】")
    print(f"   ┌──────────┬─────────┬─────────┬─────────┬─────────┐")
    print(f"   │  环节    │  平均   │  最小   │  最大   │  P99    │")
    print(f"   ├──────────┼─────────┼─────────┼─────────┼─────────┤")
    print(f"   │ 截图     │ {avg_cap:6.3f}  │ {min(capture_times):6.3f}  │ "
          f"{max(capture_times):6.3f}  │ {sorted(capture_times)[int(len(capture_times) * 0.99)]:6.3f}  │")
    print(f"   │ 转换     │ {avg_cvt:6.3f}  │ {min(convert_times):6.3f}  │ "
          f"{max(convert_times):6.3f}  │ {sorted(convert_times)[int(len(convert_times) * 0.99)]:6.3f}  │")
    print(f"   │ 推理     │ {avg_inf:6.3f}  │ {min(infer_times):6.3f}  │ "
          f"{max(infer_times):6.3f}  │ {sorted(infer_times)[int(len(infer_times) * 0.99)]:6.3f}  │")
    print(f"   │ 总计     │ {avg_total:6.3f}  │ {min(total_times):6.3f}  │ "
          f"{max(total_times):6.3f}  │ {sorted(total_times)[int(len(total_times) * 0.99)]:6.3f}  │")
    print(f"   └──────────┴─────────┴─────────┴─────────┴─────────┘")

    print(f"\n   【整体性能】")
    print(f"   • 测试时长: {elapsed_total:.2f}s")
    print(f"   • 处理帧数: {frame_count}")
    print(f"   • 平均 FPS: {frame_count / elapsed_total:.1f}")
    print(f"   • 理论 FPS: {1000 / avg_total:.1f}")

    # 瓶颈分析
    print(f"\n   【瓶颈分析】")
    if avg_inf > avg_cap + avg_cvt:
        ratio = avg_inf / (avg_cap + avg_cvt)
        print(f"   🔴 主要瓶颈: YOLO推理 ({avg_inf:.2f}ms)")
        print(f"      推理耗时是截图+转换的 {ratio:.1f} 倍")
        print(f"      建议: 降低模型输入尺寸 / 使用TensorRT FP16")
    else:
        ratio = (avg_cap + avg_cvt) / avg_inf
        print(f"   🟡 主要瓶颈: 截图+转换 ({avg_cap + avg_cvt:.2f}ms)")
        print(f"      截图+转换是推理的 {ratio:.1f} 倍")
        print(f"      建议: 使用DXcam / 降低CROP_SIZE")

    # 推荐配置
    safe_fps = int((1000 / avg_total) * 0.85)

    print(f"\n   【推荐配置】")
    print(f'''
   {{
       "INFERENCE_FPS": {safe_fps},
       "CROP_SIZE": {crop_size}
   }}

   理论极限 FPS: {1000 / avg_total:.1f}
   推荐设置 FPS: {safe_fps} (85%安全裕度)
   ''')

    print("=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == '__main__':
    test_capture_and_inference(duration=10.0)
