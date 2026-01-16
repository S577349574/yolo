"""GPU检测工具"""
from typing import List

import utils


def detect_gpu_vendor() -> str:
    """
    检测GPU厂商

    Returns:
        'nvidia' | 'amd' | 'intel' | 'unknown'
    """
    # 方法1: 通过ncnn检测
    try:
        import ncnn
        if ncnn.get_gpu_count() > 0:
            gpu_info = str(ncnn.get_gpu_info(0)).lower()
            if 'nvidia' in gpu_info or 'geforce' in gpu_info:
                return 'nvidia'
            elif 'amd' in gpu_info or 'radeon' in gpu_info:
                return 'amd'
            elif 'intel' in gpu_info:
                return 'intel'
    except:
        pass

    # 方法2: 通过ONNX Runtime检测
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        if 'CUDAExecutionProvider' in providers or 'TensorrtExecutionProvider' in providers:
            return 'nvidia'
        if 'DmlExecutionProvider' in providers:
            # DML主要用于AMD/Intel
            return _detect_dml_vendor()
    except:
        pass

    # 方法3: Windows WMI
    try:
        import subprocess
        result = subprocess.run(
            ['wmic', 'path', 'win32_VideoController', 'get', 'name'],
            capture_output=True, text=True, timeout=3
        )
        output = result.stdout.lower()
        if 'nvidia' in output:
            return 'nvidia'
        elif 'amd' in output or 'radeon' in output:
            return 'amd'
        elif 'intel' in output:
            return 'intel'
    except:
        pass

    return 'unknown'


def _detect_dml_vendor() -> str:
    """通过DirectX诊断工具检测DML对应的GPU"""
    try:
        import subprocess
        result = subprocess.run(['dxdiag', '/t', 'dxdiag_temp.txt'], timeout=5)
        with open('dxdiag_temp.txt', 'r', encoding='utf-16') as f:
            content = f.read().lower()
            if 'amd' in content or 'radeon' in content:
                return 'amd'
            elif 'intel' in content and 'arc' in content:
                return 'intel'
    except:
        pass
    return 'amd'  # DML默认假设AMD


def get_available_backends() -> List[str]:
    """
    获取所有可用后端

    Returns:
        ['tensorrt', 'cuda', 'dml', 'ncnn_vulkan', 'cpu']
    """
    backends = []

    # ONNX Runtime
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()

        if 'TensorrtExecutionProvider' in providers:
            backends.append('tensorrt')
        if 'CUDAExecutionProvider' in providers:
            backends.append('cuda')
        if 'DmlExecutionProvider' in providers:
            backends.append('dml')
    except:
        pass

    # ncnn
    try:
        import ncnn
        if ncnn.get_gpu_count() > 0:
            backends.append('ncnn_vulkan')
        backends.append('ncnn_cpu')
    except:
        pass

    # CPU兜底
    backends.append('cpu')

    return backends


def select_best_backend(force_backend: str = None) -> str:
    """
    自动选择最优后端

    Args:
        force_backend: 强制使用的后端(可选)

    Returns:
        最优后端名称
    """
    if force_backend:
        utils.log(f"[推理] 用户强制指定后端: {force_backend}")
        return force_backend

    gpu_vendor = detect_gpu_vendor()
    available = get_available_backends()

    utils.log(f"[推理] 检测到GPU: {gpu_vendor}")
    utils.log(f"[推理] 可用后端: {', '.join(available)}")

    # NVIDIA: TensorRT > CUDA > 通用
    if gpu_vendor == 'nvidia':
        if 'tensorrt' in available:
            return 'tensorrt'
        if 'cuda' in available:
            return 'cuda'

    # AMD: ncnn Vulkan > DML
    if gpu_vendor == 'amd':
        if 'ncnn_vulkan' in available:
            return 'ncnn_vulkan'
        if 'dml' in available:
            return 'dml'

    # Intel: DML > ncnn Vulkan
    if gpu_vendor == 'intel':
        if 'dml' in available:
            return 'dml'
        if 'ncnn_vulkan' in available:
            return 'ncnn_vulkan'

    # 兜底策略
    if 'ncnn_vulkan' in available:
        return 'ncnn_vulkan'
    if 'dml' in available:
        return 'dml'

    return 'cpu'
