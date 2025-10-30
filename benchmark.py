import time
import numpy as np
import mss
import cv2
from yolo_detector import YOLOv8Detector

print("=" * 60)
print("🔍 性能基准测试")
print("=" * 60)

# 初始化
model = YOLOv8Detector()

with mss.mss() as sct:
    monitor = sct.monitors[1]
    crop_size = 320

    crop_area = {
        'left': monitor['width'] // 2 - crop_size // 2,
        'top': monitor['height'] // 2 - crop_size // 2,
        'width': crop_size,
        'height': crop_size
    }

    print(f"\n📊 测试配置:")
    print(f"   截图区域: {crop_size}x{crop_size}")
    print(f"   YOLO 模型: {model.img_size}x{model.img_size}")
    print(f"   Provider: {model.session.get_providers()[0]}")

    # ==================== 测试1：纯截图速度 ====================
    print("\n" + "=" * 60)
    print("📸 测试1: 纯截图速度（100次）")
    print("=" * 60)

    capture_times = []
    for i in range(100):
        start = time.perf_counter()
        img = np.array(sct.grab(crop_area))
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
    print("🧠 测试2: 纯 YOLO 推理速度（100次）")
    print("=" * 60)

    # 先截一张图
    img_bgra = np.array(sct.grab(crop_area))
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

    # ==================== 测试3：完整流程 ====================
    print("\n" + "=" * 60)
    print("🔄 测试3: 完整流程（截图+推理，100次）")
    print("=" * 60)

    full_times = []
    for i in range(100):
        start = time.perf_counter()

        # 截图
        img_bgra = np.array(sct.grab(crop_area))
        img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)

        # 推理
        results = model.predict(img_bgr)

        full_times.append((time.perf_counter() - start) * 1000)

    avg_full = sum(full_times) / len(full_times)
    min_full = min(full_times)
    max_full = max(full_times)

    print(f"   平均: {avg_full:.2f}ms")
    print(f"   最快: {min_full:.2f}ms")
    print(f"   最慢: {max_full:.2f}ms")
    print(f"   实际最大 FPS: {1000 / avg_full:.1f}")

    # ==================== 性能分析 ====================
    print("\n" + "=" * 60)
    print("📊 性能瓶颈分析")
    print("=" * 60)

    capture_percent = (avg_capture / avg_full) * 100
    inference_percent = (avg_inference / avg_full) * 100
    overhead_percent = 100 - capture_percent - inference_percent

    print(f"   截图耗时: {avg_capture:.2f}ms ({capture_percent:.1f}%)")
    print(f"   推理耗时: {avg_inference:.2f}ms ({inference_percent:.1f}%)")
    print(f"   其他开销: {overhead_percent:.1f}%")

    # 判断瓶颈
    if inference_percent > 60:
        print(f"\n   ⚠️ 瓶颈: YOLO 推理（{inference_percent:.1f}%）")
        print(f"   建议: 降低 INFERENCE_FPS 到 {int(1000 / avg_inference)}")
    elif capture_percent > 60:
        print(f"\n   ⚠️ 瓶颈: 屏幕截图（{capture_percent:.1f}%）")
        print(f"   建议: 降低 CAPTURE_FPS 到 {int(1000 / avg_capture)}")
    else:
        print(f"\n   ✅ 性能均衡")

    # ==================== 推荐配置 ====================
    print("\n" + "=" * 60)
    print("🎯 推荐配置")
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

print("\n" + "=" * 60)
print("✅ 测试完成")
print("=" * 60)
