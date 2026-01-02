# crosshair/crosshair_manager.py
"""
准星检测管理器（修复版）
- 修复模板加载逻辑
- 优化小红点准星支持
- 改进错误处理和日志
"""
import cv2
import numpy as np
import os
from typing import Optional, Tuple, Dict

import utils
from crosshair.games.valorant.config_parser import ValorantConfigParser
from crosshair.games.valorant.crosshair_visualizer import CrosshairVisualizer


class CrosshairManager:
    """准星检测管理器"""

    def __init__(
        self,
        detector_type: str = 'template',
        valorant_config_code: Optional[str] = None,
        enable_detection: bool = True
    ):
        """
        初始化准星管理器

        Args:
            detector_type: 检测器类型 ('color', 'template', 'cross_shape')
            valorant_config_code: Valorant准星配置代码（可选）
            enable_detection: 是否启用检测
        """
        self.detector_type = detector_type
        self.enabled = enable_detection
        self.detector = None

        # 统计信息
        self._total_frames = 0
        self._success_frames = 0
        self._miss_count = 0

        if not enable_detection:
            utils.log("⚠️ 准星检测已禁用")
            return

        # 初始化检测器
        self._init_detector(detector_type, valorant_config_code)

    def _init_detector(self, detector_type: str, valorant_config_code: Optional[str]):
        """初始化检测器"""

        if detector_type == 'color':
            self._init_color_detector()

        elif detector_type == 'template':
            self._init_template_detector(valorant_config_code)

        elif detector_type == 'cross_shape':
            self._init_cross_shape_detector()

        else:
            utils.log(f"❌ 未知的检测器类型: {detector_type}，回退到颜色检测")
            self._init_color_detector()

    def _init_color_detector(self):
        """初始化颜色检测器"""
        from crosshair.detectors.color_detector import ColorCrosshairDetector

        utils.log("\n🎯 初始化准星检测（颜色检测模式）")
        self.detector = ColorCrosshairDetector()
        utils.log("   ✅ 颜色检测器初始化完成")

    def _init_template_detector(self, valorant_config_code: Optional[str]):
        """初始化模板检测器（传递颜色信息）"""
        from crosshair.detectors.template_detector import TemplateCrosshairDetector

        utils.log("\n🎯 初始化准星检测（模板匹配模式）")

        template_bgr = None
        is_dot_only = False
        target_color_bgr = None  # ⭐ 新增
        target_color_name = None  # ⭐ 新增

        # ========== 方式1：从 Valorant 配置代码生成 ==========
        if valorant_config_code:
            result = self._generate_valorant_template(valorant_config_code)
            if result:
                template_bgr, is_dot_only, target_color_bgr, target_color_name = result

        # ========== 方式2：从外部文件加载 ==========
        if template_bgr is None:
            template_bgr = self._load_external_template()

        # ========== 检查是否成功获取模板 ==========
        if template_bgr is None:
            utils.log("   ❌ 无可用模板，回退到颜色检测模式")
            self._init_color_detector()
            return

        # ========== 创建模板检测器（传递颜色信息）==========
        self.detector = TemplateCrosshairDetector(
            template_img=template_bgr,
            target_color_bgr=target_color_bgr,  # ⭐ 传递颜色
            target_color_name=target_color_name  # ⭐ 传递颜色名称
        )

        # ========== 针对小红点优化参数 ==========
        if is_dot_only:
            utils.log("   🔴 检测到纯中心点准星，应用优化配置")
            self.detector.threshold = 0.6
            self.detector.search_radius = 120
            self.detector.smooth_factor = 0.3
            self.detector.color_tolerance = 50  # ⭐ 小红点颜色容差更宽松
            utils.log(f"   优化参数: 阈值={self.detector.threshold}, "
                      f"搜索半径={self.detector.search_radius}px, "
                      f"颜色容差={self.detector.color_tolerance}")
        else:
            self.detector.threshold = 0.75
            self.detector.search_radius = 120
            self.detector.smooth_factor = 0.2
            self.detector.color_tolerance = 40

        utils.log(f"   模板尺寸: {self.detector.template_w}x{self.detector.template_h}")
        utils.log(f"   匹配阈值: {self.detector.threshold}")

    def _generate_valorant_template(self, config_code: str):
        """
        从 Valorant 配置代码生成模板（返回颜色信息）

        Returns:
            (template_bgr, is_dot_only, target_color_bgr, target_color_name) 或 None
        """
        try:
            # 解析配置
            config = ValorantConfigParser.parse(config_code)
            desc = ValorantConfigParser.describe(config)
            utils.log(f"   准星配置: {desc}")

            print(f"\n🔍 解析后的配置:")
            print(f"  颜色: {config['color_name']} ({config['color_hex']}) - BGR: {config['color_bgr']}")
            print(f"  描边: enabled={config['outline']['enabled']}")
            print(f"  中心点: enabled={config['center_dot']['enabled']}")

            # 判断是否为纯中心点
            is_dot_only = (
                    config.get('center_dot', {}).get('enabled', False) and
                    not config.get('inner_lines', {}).get('enabled', True) and
                    not config.get('outer_lines', {}).get('enabled', False)
            )

            # ⭐ 提取颜色信息
            target_color_bgr = tuple(config['color_bgr'])  # BGR格式
            target_color_name = config['color_name']

            # 根据准星类型选择模板尺寸
            # 根据准星类型选择模板尺寸
            if is_dot_only:
                template_size = 300
                utils.log(f"   纯中心点准星，使用大模板: {template_size}x{template_size}")
            else:
                template_size = 180
                utils.log(f"   标准准星,使用常规模板: {template_size}x{template_size}")

            # 渲染模板
            template_img = CrosshairVisualizer.render(config, size=template_size)

            # 保存模板（带Alpha通道）
            if template_img.shape[2] == 4:
                from PIL import Image
                img_rgba = cv2.cvtColor(template_img, cv2.COLOR_BGRA2RGBA)
                pil_img = Image.fromarray(img_rgba, 'RGBA')
                pil_img.save("crosshair.png", 'PNG')
                utils.log(f"   ✅ 准星模板已生成: crosshair.png (透明背景)")
            else:
                cv2.imwrite("crosshair.png", template_img)
                utils.log(f"   ✅ 准星模板已生成: crosshair.png")

            return (template_img, is_dot_only, target_color_bgr, target_color_name)  # ⭐ 返回4个值

        except Exception as e:
            utils.log(f"   ⚠️ Valorant配置解析失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _load_external_template(self) -> Optional[np.ndarray]:
        """
        从外部文件加载模板

        Returns:
            template_bgr: 模板图像，失败则返回 None
        """
        template_path = "templates/crosshair.png"

        if not os.path.exists(template_path):
            utils.log(f"   ⚠️ 外部模板不存在: {template_path}")
            return None

        utils.log(f"   尝试加载外部模板: {template_path}")
        template_bgr = cv2.imread(template_path)

        if template_bgr is None:
            utils.log(f"   ❌ 外部模板加载失败（文件损坏或格式错误）")
            return None

        utils.log(f"   ✅ 外部模板加载成功: {template_bgr.shape}")
        return template_bgr

    def _init_cross_shape_detector(self):
        """初始化十字形状检测器"""
        try:
            from crosshair.detectors.cross_shape_detector import CrossShapeDetector

            utils.log("\n🎯 初始化准星检测（十字形状检测模式）")
            self.detector = CrossShapeDetector()
            utils.log("   ✅ 十字形状检测器初始化完成")

        except ImportError:
            utils.log("   ❌ 十字形状检测器不可用，回退到颜色检测")
            self._init_color_detector()

    def detect(
        self,
        img: np.ndarray,
        capture_area: Dict[str, int],
        fallback_center: Optional[Tuple[int, int]] = None
    ) -> Optional[Tuple[int, int]]:
        """
        检测准星位置

        Args:
            img: 图像帧（BGR或BGRA格式）
            capture_area: 捕获区域信息 {'left', 'top', 'width', 'height'}
            fallback_center: 检测失败时的回退中心点

        Returns:
            (x, y): 屏幕坐标系下的准星位置，失败则返回回退中心点
        """
        if not self.enabled or self.detector is None:
            return fallback_center

        self._total_frames += 1

        # 执行检测
        result = self.detector.detect(img, capture_area)

        # 统计
        if result:
            self._success_frames += 1
            self._miss_count = 0
            return result
        else:
            self._miss_count += 1

            # 连续丢失告警
            if self._miss_count == 60:
                utils.log(f"⚠️ 准星检测连续丢失 {self._miss_count} 帧")
            elif self._miss_count % 120 == 0:
                utils.log(f"⚠️ 准星检测连续丢失 {self._miss_count} 帧")

            return fallback_center

    def get_stats(self) -> Dict:
        """
        获取统计信息

        Returns:
            统计字典
        """
        success_rate = (
            f"{self._success_frames / self._total_frames * 100:.1f}%"
            if self._total_frames > 0
            else "N/A"
        )

        return {
            'total': self._total_frames,
            'success': self._success_frames,
            'success_rate': success_rate,
            'miss_count': self._miss_count,
            'detector_type': self.detector_type,
            'enabled': self.enabled
        }

    def reset(self):
        """重置统计"""
        self._total_frames = 0
        self._success_frames = 0
        self._miss_count = 0

        if self.detector and hasattr(self.detector, 'reset'):
            self.detector.reset()

        utils.log("📊 准星检测统计已重置")

    def set_threshold(self, threshold: float):
        """
        设置匹配阈值（仅模板检测有效）

        Args:
            threshold: 新阈值（0.0 ~ 1.0）
        """
        if self.detector and hasattr(self.detector, 'threshold'):
            old_threshold = self.detector.threshold
            self.detector.threshold = max(0.0, min(1.0, threshold))
            utils.log(f"阈值调整: {old_threshold:.2f} → {self.detector.threshold:.2f}")
        else:
            utils.log("⚠️ 当前检测器不支持阈值调整")

    def enable(self):
        """启用检测"""
        self.enabled = True
        utils.log("✅ 准星检测已启用")

    def disable(self):
        """禁用检测"""
        self.enabled = False
        utils.log("⏸️ 准星检测已禁用")

    def get_detector_info(self) -> str:
        """获取检测器信息"""
        if not self.detector:
            return "未初始化"

        info = f"类型: {self.detector.get_name()}"

        if hasattr(self.detector, 'threshold'):
            info += f", 阈值: {self.detector.threshold:.2f}"

        if hasattr(self.detector, 'search_radius'):
            info += f", 搜索半径: {self.detector.search_radius}px"

        if hasattr(self.detector, 'template_w'):
            info += f", 模板尺寸: {self.detector.template_w}x{self.detector.template_h}"

        return info

    def __str__(self):
        """字符串表示"""
        return (
            f"CrosshairManager("
            f"type={self.detector_type}, "
            f"enabled={self.enabled}, "
            f"success_rate={self.get_stats()['success_rate']}"
            f")"
        )

    def __repr__(self):
        return self.__str__()


# ============================================================
# 便捷工厂函数
# ============================================================

def create_crosshair_manager(
    config_code: Optional[str] = None,
    detector_type: str = 'template'
) -> CrosshairManager:
    """
    创建准星管理器的便捷函数

    Args:
        config_code: Valorant准星配置代码
        detector_type: 检测器类型

    Returns:
        CrosshairManager实例
    """
    return CrosshairManager(
        detector_type=detector_type,
        valorant_config_code=config_code,
        enable_detection=True
    )

