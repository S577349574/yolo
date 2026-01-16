"""推理后端模块"""
from .onnx_backend import ONNXDetector
from .ncnn_backend import NCNNDetector

__all__ = ['ONNXDetector', 'NCNNDetector']
