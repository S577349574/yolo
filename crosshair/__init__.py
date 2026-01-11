# crosshair/__init__.py
"""
准星检测器模块 - 统一导出接口
"""
from .base import CrosshairDetector
from config_manager import get_config
import utils


def create_crosshair_detector() -> CrosshairDetector:
    """
    根据配置创建准星检测器

    Returns:
        CrosshairDetector 实例
    """
    detector_type = get_config('CROSSHAIR_DETECTOR_TYPE', 'color')

    utils.log(f"🔍 请求创建检测器类型: {detector_type}")

    # ===== 通用检测器 =====
    if detector_type == 'color':
        from .detectors.color_detector import ColorCrosshairDetector
        return ColorCrosshairDetector()

    elif detector_type == 'template':
        from .detectors.template_detector import TemplateCrosshairDetector
        return TemplateCrosshairDetector()

    elif detector_type == 'cross_shape':
        from .detectors.cross_shape_detector import CrossShapeDetector
        return CrossShapeDetector()

    # ===== 红点准星检测器 =====
    elif detector_type == 'red_dot':
        from .detectors.red_dot_detector import RedDotCrosshairDetector
        utils.log("🔴 创建红点准星检测器")
        return RedDotCrosshairDetector()
    # ===== 未知类型回退 =====
    else:
        utils.log(f"❌ 未知的检测器类型: {detector_type}，回退到颜色检测")
        from .detectors.color_detector import ColorCrosshairDetector
        return ColorCrosshairDetector()


__all__ = ['CrosshairDetector', 'create_crosshair_detector']
