# benchmark.py
"""
性能基准测试 - 多后端版本
支持测试: ONNX Runtime / ncnn
"""

import time
import numpy as np
import mss
import cv2

from config_manager import get_config


def get_detector(backend='ncnn'):
    """
    获取指定后端的检测器

    Args:
        backend: 'onnx' | 'ncnn' | 'auto'

    Returns:
        detector 实例
    """
    if backend == 'auto':
        # 使用重构后的 InferenceManager
        from inference.manager import get_detector
        return get_detector()

    elif backend == 'onnx':
        from inference.backends.onnx_backend import ONNXDetector
        return ONNXDetector(preferred_backend='auto')

    elif backend == 'ncnn':
        from inference.backends.ncnn_backend import NCNNDetector
        return NCNNDetector(use_gpu=True)

    else:
        raise ValueError(f"不支持的后端: {backend}")


def test_capture_and_inference(backend='ncnn', duration=10.0):
    """测试截图+推理完整流程"""
    print("\n" + "=" * 60)
    print(f"完整流程测试 (后端: {backend.upper()}, 运行 {duration} 秒)")
    print("=" * 60)

    # 初始化
    model = get_detector(backend)
    crop_size = get_config('CROP_SIZE', 320)

    print(f"\n配置:")
    print(f"   后端类型: {model.backend_name}")
    print(f"   截图区域: {crop_size}x{crop_size}")

    # 根据后端类型获取输入尺寸
    if hasattr(model, 'img_size'):
        img_size = model.img_size
    else:
        img_size = crop_size

    print(f"   模型输入: {img_size}x{img_size}")

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
    print("   预热中...")
    for _ in range(20):
        model.predict(img_bgr)

    inference_times = []
    for i in range(1000):
        start = time.perf_counter()
        model.predict(img_bgr)
        elapsed = (time.perf_counter() - start) * 1000
        inference_times.append(elapsed)

        # 每100次打印进度
        if (i + 1) % 100 == 0:
            print(f"   进度: {i + 1}/1000 (当前: {elapsed:.3f}ms)")

    avg_infer = sum(inference_times) / len(inference_times)
    min_infer = min(inference_times)
    max_infer = max(inference_times)
    p99_infer = sorted(inference_times)[int(len(inference_times) * 0.99)]

    print(f"\n   平均: {avg_infer:.3f}ms")
    print(f"   最小: {min_infer:.3f}ms")
    print(f"   最大: {max_infer:.3f}ms")
    print(f"   P99:  {p99_infer:.3f}ms")
    print(f"   标准差: {np.std(inference_times):.3f}ms")
    print(f"   理论最大 FPS: {1000 / avg_infer:.1f}")

    # ==================== 阶段3: 完整流程 (持续测试) ====================
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
    print(f"   • 后端类型: {model.backend_name}")
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

    return {
        'backend': model.backend_name,
        'avg_total': avg_total,
        'avg_inference': avg_inf,
        'fps': frame_count / elapsed_total
    }


def compare_backends(duration=10.0):
    """对比测试所有可用后端"""
    backends_to_test = []

    # 检测可用后端
    try:
        from inference.backends.onnx_backend import ONNXDetector
        backends_to_test.append('onnx')
    except:
        pass

    try:
        from inference.backends.ncnn_backend import NCNNDetector
        backends_to_test.append('ncnn')
    except:
        pass

    if not backends_to_test:
        print("❌ 没有可用的后端")
        return

    print("\n" + "=" * 60)
    print("多后端对比测试")
    print("=" * 60)
    print(f"检测到可用后端: {', '.join(backends_to_test)}")

    results = {}

    for backend in backends_to_test:
        try:
            print(f"\n{'=' * 60}")
            print(f"正在测试: {backend.upper()}")
            print(f"{'=' * 60}")

            result = test_capture_and_inference(backend=backend, duration=duration)
            results[backend] = result

            # 释放资源
            import gc
            gc.collect()
            time.sleep(2)

        except Exception as e:
            print(f"\n❌ {backend.upper()} 测试失败: {e}")
            import traceback
            traceback.print_exc()

    # ==================== 对比结果 ====================
    if len(results) > 1:
        print("\n" + "=" * 60)
        print("后端性能对比")
        print("=" * 60)

        print(f"\n   ┌──────────────┬──────────┬──────────┬──────────┐")
        print(f"   │  后端        │  总耗时  │  推理    │  FPS     │")
        print(f"   ├──────────────┼──────────┼──────────┼──────────┤")

        for backend, data in results.items():
            print(f"   │ {data['backend']:12} │ {data['avg_total']:7.3f}  │ "
                  f"{data['avg_inference']:7.3f}  │ {data['fps']:7.1f}  │")

        print(f"   └──────────────┴──────────┴──────────┴──────────┘")

        # 找出最快的后端
        fastest = min(results.items(), key=lambda x: x[1]['avg_total'])
        print(f"\n   🏆 最快后端: {fastest[0].upper()} "
              f"({fastest[1]['avg_total']:.3f}ms, {fastest[1]['fps']:.1f} FPS)")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='YOLO 推理性能测试')
    parser.add_argument('--backend', type=str, default='ncnn',
                        choices=['auto', 'onnx', 'ncnn', 'compare'],
                        help='选择后端 (auto=自动选择, compare=对比所有后端)')
    parser.add_argument('--duration', type=float, default=10.0,
                        help='完整流程测试时长(秒)')

    args = parser.parse_args()

    if args.backend == 'compare':
        compare_backends(duration=args.duration)
    else:
        test_capture_and_inference(backend=args.backend, duration=args.duration)
