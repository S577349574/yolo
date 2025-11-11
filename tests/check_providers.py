import onnxruntime as ort

print("=" * 60)
print("🔍 ONNX Runtime Provider 检测")
print("=" * 60)

# 获取所有可用的 Providers
available = ort.get_available_providers()
print(f"\n当前系统支持的 Providers:")
for i, provider in enumerate(available, 1):
    print(f"   {i}. {provider}")

# 检查是否支持 GPU
gpu_providers = [p for p in available if 'CPU' not in p]

if gpu_providers:
    print(f"\n检测到 GPU 支持:")
    for provider in gpu_providers:
        print(f"   • {provider}")

    # 给出建议
    if 'DmlExecutionProvider' in available:
        print("\n建议: 使用 DmlExecutionProvider (适用于 AMD/NVIDIA/Intel)")
    elif 'ROCMExecutionProvider' in available:
        print("\n建议: 使用 ROCMExecutionProvider (AMD 专用)")
    elif 'CUDAExecutionProvider' in available:
        print("\n建议: 使用 CUDAExecutionProvider (NVIDIA 专用)")
else:
    print(f"\n未检测到 GPU 支持，只能使用 CPU")
    print("\n解决方法:")
    print("   1. 确认已安装显卡驱动")
    print("   2. 安装 GPU 版本的 ONNX Runtime:")
    print("      pip uninstall onnxruntime")
    print("      pip install onnxruntime-directml  # Windows (AMD/NVIDIA/Intel)")
    print("      # 或")
    print("      pip install onnxruntime-gpu  # Linux (NVIDIA CUDA)")

print("\n" + "=" * 60)
