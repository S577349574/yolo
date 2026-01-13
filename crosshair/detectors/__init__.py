# crosshair/detectors/__init__.py
from .color_detector import ColorCrosshairDetector
from .template_detector import TemplateCrosshairDetector
from .cross_shape_detector import CrossShapeDetector
from .red_dot_detector import SimpleRedDotDetector

__all__ = [
    'ColorCrosshairDetector',
    'TemplateCrosshairDetector',
    'CrossShapeDetector',
    'SimpleRedDotDetector'
]
