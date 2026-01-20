# crosshair/crosshair_manager.py
"""
准星检测管理器（改进版 v2.0）
- ✅ 修复模板加载逻辑
- ✅ 优化小红点准星支持
- ✅ 改进错误处理和日志
- ⭐ 新增位置缓存机制（解决抖动问题）
- ⭐ 新增平滑过渡选项
- ⭐ 增强初始化日志输出
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
            enable_detection: bool = True,
            max_consecutive_misses: int = 10,
            enable_smooth: bool = False,
            smooth_factor: float = 0.7,
            enable_debug=True,  # ⭐ 开启调试
    ):
        """
        初始化准星管理器

        Args:
            detector_type: 检测器类型 ('color', 'template', 'cross_shape', 'red_dot')
            valorant_config_code: Valorant准星配置代码（可选）
            enable_detection: 是否启用检测
            max_consecutive_misses: 连续失败多少次后使用回退中心（默认10次）
            enable_smooth: 是否启用位置平滑（默认False）
            smooth_factor: 平滑系数 0~1（越大越平滑，默认0.7）
            enable_debug: 是否开启调试日志
        """
        self.enable_debug = enable_debug
        self.detector_type = detector_type
        self.enabled = enable_detection

        # ⭐ 位置缓存与平滑配置
        self._last_valid_position: Optional[Tuple[int, int]] = None
        self._consecutive_misses = 0
        self._max_consecutive_misses = max_consecutive_misses
        self._enable_smooth = enable_smooth
        self._smooth_factor = max(0.0, min(1.0, smooth_factor))

        # 统计信息
        self._total_frames = 0
        self._success_frames = 0
        self._miss_count = 0

        # ⭐ 打印初始化配置信息
        self._print_init_header()

        if not enable_detection:
            utils.log("⚠️ 准星检测已禁用")
            self.detector = None
            return

        # 初始化检测器
        self._init_detector(detector_type, valorant_config_code)

        # ⭐ 打印最终配置总结
        self._print_init_summary()

    def _print_init_header(self):
        """打印初始化配置头部信息"""
        utils.log("\n" + "=" * 60)
        utils.log("🎯 准星管理器初始化")
        utils.log("=" * 60)
        utils.log(f"📋 配置参数:")
        utils.log(f"   • 检测器类型: {self.detector_type}")
        utils.log(f"   • 检测启用状态: {'✅ 启用' if self.enabled else '❌ 禁用'}")
        utils.log(f"   • 位置平滑: {'✅ 启用' if self._enable_smooth else '❌ 禁用'}")

        if self._enable_smooth:
            utils.log(f"     └─ 平滑系数: {self._smooth_factor:.2f} (0=无平滑, 1=最大平滑)")

        utils.log(f"   • 容错机制: 连续失败 {self._max_consecutive_misses} 次后回退中心")
        utils.log(f"   • 调试模式: {'✅ 启用' if self.enable_debug else '❌ 禁用'}")

    def _print_init_summary(self):
        """打印初始化完成总结"""
        utils.log("\n" + "-" * 60)
        utils.log("✅ 准星管理器初始化完成")
        utils.log("-" * 60)

        if self.detector:
            utils.log(f"🔧 检测器详情:")
            utils.log(f"   • 名称: {self.detector.get_name()}")

            if hasattr(self.detector, 'threshold'):
                utils.log(f"   • 匹配阈值: {self.detector.threshold:.2f}")

            if hasattr(self.detector, 'search_radius'):
                utils.log(f"   • 搜索半径: {self.detector.search_radius}px")

            if hasattr(self.detector, 'template_w'):
                utils.log(f"   • 模板尺寸: {self.detector.template_w}x{self.detector.template_h}px")

            if hasattr(self.detector, 'color_tolerance'):
                utils.log(f"   • 颜色容差: {self.detector.color_tolerance}")

        utils.log(f"\n📊 运行策略:")
        utils.log(f"   • 位置平滑: {'开启' if self._enable_smooth else '关闭'}")

        if self._enable_smooth:
            utils.log(f"     └─ 权重分配: 新位置 {self._smooth_factor:.0%} | 历史位置 {(1 - self._smooth_factor):.0%}")

        utils.log(f"   • 失败处理: 缓存上次位置最多 {self._max_consecutive_misses} 帧")
        utils.log("=" * 60 + "\n")

    def _init_detector(self, detector_type: str, valorant_config_code: Optional[str]):
        """初始化检测器"""

        if detector_type == 'color':
            self._init_color_detector()

        elif detector_type == 'template':
            self._init_template_detector(valorant_config_code)

        elif detector_type == 'cross_shape':
            self._init_cross_shape_detector()

        elif detector_type == 'red_dot':
            self._init_red_dot_detector()

        else:
            utils.log(f"❌ 未知的检测器类型: {detector_type}，回退到颜色检测")
            self._init_color_detector()

    def _init_color_detector(self):
        """初始化颜色检测器"""
        from crosshair.detectors.color_detector import ColorCrosshairDetector

        utils.log("\n🎨 初始化颜色检测器...")
        self.detector = ColorCrosshairDetector()
        utils.log("   ✅ 颜色检测器加载完成")

    def _init_red_dot_detector(self):
        """初始化红点准星检测器"""
        utils.log("\n🔴 初始化红点检测器...")
        from crosshair.detectors.red_dot_detector import SimpleRedDotDetector
        self.detector = SimpleRedDotDetector()
        utils.log("   ✅ 增强版红点检测器加载完成")

    def _init_template_detector(self, valorant_config_code: Optional[str]):
        """初始化模板检测器（传递颜色信息）"""
        from crosshair.detectors.template_detector import TemplateCrosshairDetector

        utils.log("\n🖼️ 初始化模板匹配检测器...")

        template_bgr = None
        is_dot_only = False
        target_color_bgr = None
        target_color_name = None

        # ========== 方式1：从 Valorant 配置代码生成 ==========
        if valorant_config_code:
            utils.log("   📝 从Valorant配置代码生成模板...")
            result = self._generate_valorant_template(valorant_config_code)
            if result:
                template_bgr, is_dot_only, target_color_bgr, target_color_name = result

        # ========== 方式2：从外部文件加载 ==========
        if template_bgr is None:
            utils.log("   📂 尝试从外部文件加载模板...")
            template_bgr = self._load_external_template()

        # ========== 检查是否成功获取模板 ==========
        if template_bgr is None:
            utils.log("   ❌ 无可用模板，回退到颜色检测模式")
            self._init_color_detector()
            return

        # ========== 创建模板检测器（传递颜色信息）==========
        utils.log("   🔧 配置检测器参数...")
        self.detector = TemplateCrosshairDetector(
            template_img=template_bgr,
            target_color_bgr=target_color_bgr,
            target_color_name=target_color_name
        )

        # ========== 配置检测参数 ==========
        self.detector.threshold = 0.75
        self.detector.smooth_factor = 0.2
        self.detector.color_tolerance = 40

        # ========== 打印配置信息 ==========
        bounds = self.detector.search_bounds
        search_width = bounds['x_right'] - bounds['x_left']
        search_height = abs(bounds['y_up']) + bounds['y_down']

        utils.log(f"   ✅ 检测器配置完成:")
        utils.log(f"     • 阈值: {self.detector.threshold}")
        utils.log(f"     • 颜色容差: {self.detector.color_tolerance}")
        utils.log(f"     • 搜索区域: {search_width}×{search_height}px")
        utils.log(f"       └─ 水平: [{bounds['x_left']}, +{bounds['x_right']}]px")
        utils.log(f"       └─ 垂直: [{bounds['y_up']}, +{bounds['y_down']}]px")

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
            utils.log(f"     └─ 准星配置: {desc}")

            if self.enable_debug:
                print(f"\n     🔍 配置详情:")
                print(f"        • 颜色: {config['color_name']} ({config['color_hex']}) - BGR: {config['color_bgr']}")
                print(f"        • 描边: {'启用' if config['outline']['enabled'] else '禁用'}")
                print(f"        • 中心点: {'启用' if config['center_dot']['enabled'] else '禁用'}")

            # 判断是否为纯中心点
            is_dot_only = (
                    config.get('center_dot', {}).get('enabled', False) and
                    not config.get('inner_lines', {}).get('enabled', True) and
                    not config.get('outer_lines', {}).get('enabled', False)
            )

            # 提取颜色信息
            target_color_bgr = tuple(config['color_bgr'])
            target_color_name = config['color_name']

            # 根据准星类型选择模板尺寸
            if is_dot_only:
                template_size = 300
                utils.log(f"     └─ 纯中心点模式，使用大模板: {template_size}x{template_size}px")
            else:
                template_size = 180
                utils.log(f"     └─ 标准模式，使用常规模板: {template_size}x{template_size}px")

            # 渲染模板
            utils.log(f"     └─ 正在渲染模板...")
            template_img = CrosshairVisualizer.render(config, size=template_size)

            # 保存模板（带Alpha通道）
            if template_img.shape[2] == 4:
                from PIL import Image
                img_rgba = cv2.cvtColor(template_img, cv2.COLOR_BGRA2RGBA)
                pil_img = Image.fromarray(img_rgba, 'RGBA')
                pil_img.save("crosshair.png", 'PNG')
                utils.log(
                    f"     ✅ 模板已保存: crosshair.png (透明背景, {template_img.shape[1]}x{template_img.shape[0]})")
            else:
                cv2.imwrite("crosshair.png", template_img)
                utils.log(f"     ✅ 模板已保存: crosshair.png ({template_img.shape[1]}x{template_img.shape[0]})")

            return (template_img, is_dot_only, target_color_bgr, target_color_name)

        except Exception as e:
            utils.log(f"     ❌ Valorant配置解析失败: {e}")
            if self.enable_debug:
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
            utils.log(f"     ⚠️ 外部模板不存在: {template_path}")
            return None

        utils.log(f"     📂 加载外部模板: {template_path}")
        template_bgr = cv2.imread(template_path)

        if template_bgr is None:
            utils.log(f"     ❌ 模板加载失败（文件损坏或格式错误）")
            return None

        utils.log(f"     ✅ 模板加载成功: {template_bgr.shape[1]}x{template_bgr.shape[0]}px")
        return template_bgr

    def _init_cross_shape_detector(self):
        """初始化十字形状检测器"""
        try:
            from crosshair.detectors.cross_shape_detector import CrossShapeDetector

            utils.log("\n➕ 初始化十字形状检测器...")
            self.detector = CrossShapeDetector()
            utils.log("   ✅ 十字形状检测器加载完成")

        except ImportError:
            utils.log("   ❌ 十字形状检测器不可用，回退到颜色检测")
            self._init_color_detector()

    def _smooth_position(self, new_pos: Tuple[int, int]) -> Tuple[int, int]:
        """
        对检测位置进行平滑处理

        Args:
            new_pos: 新检测到的位置

        Returns:
            平滑后的位置
        """
        if not self._enable_smooth or self._last_valid_position is None:
            return new_pos

        # 加权平均：new_pos 占 (1 - smooth_factor)，last_pos 占 smooth_factor
        x = int(new_pos[0] * (1 - self._smooth_factor) +
                self._last_valid_position[0] * self._smooth_factor)
        y = int(new_pos[1] * (1 - self._smooth_factor) +
                self._last_valid_position[1] * self._smooth_factor)

        return (x, y)

    def detect(
            self,
            img: np.ndarray,
            capture_area: Dict[str, int],
            fallback_center: Optional[Tuple[int, int]] = None
    ) -> Optional[Tuple[int, int]]:
        """
        检测准星位置（改进版 - 带缓存与平滑）

        Args:
            img: 图像帧（BGR或BGRA格式）
            capture_area: 捕获区域信息 {'left', 'top', 'width', 'height'}
            fallback_center: 检测失败时的回退中心点

        Returns:
            (x, y): 屏幕坐标系下的准星位置
        """
        if not self.enabled or self.detector is None:
            return fallback_center

        self._total_frames += 1

        # ========== 执行检测 ==========
        result = self.detector.detect(img, capture_area)

        # ========== 检测成功 ==========
        if result:
            self._success_frames += 1
            self._consecutive_misses = 0

            # 平滑处理（可选）
            smoothed_result = self._smooth_position(result)
            self._last_valid_position = smoothed_result

            return smoothed_result

        # ========== 检测失败 ==========
        else:
            self._consecutive_misses += 1
            self._miss_count += 1

            # 策略1：优先使用上次有效位置
            if self._last_valid_position is not None:
                if self._consecutive_misses < self._max_consecutive_misses:
                    # 短期失败：继续使用上次位置
                    return self._last_valid_position
                else:
                    # 长期失败：使用回退中心，并重置缓存
                    if self.enable_debug:
                        utils.log(f"⚠️ 连续{self._consecutive_misses}次检测失败，使用回退中心")
                    self._last_valid_position = None
                    return fallback_center

            # 策略2：从未检测成功过，直接用回退中心
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
            'consecutive_misses': self._consecutive_misses,
            'detector_type': self.detector_type,
            'enabled': self.enabled,
            'smooth_enabled': self._enable_smooth,
            'smooth_factor': self._smooth_factor,
            'max_consecutive_misses': self._max_consecutive_misses
        }

    def reset(self):
        """重置统计与缓存"""
        self._total_frames = 0
        self._success_frames = 0
        self._miss_count = 0
        self._consecutive_misses = 0
        self._last_valid_position = None

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
            utils.log(f"🔧 阈值调整: {old_threshold:.2f} → {self.detector.threshold:.2f}")
        else:
            utils.log("⚠️ 当前检测器不支持阈值调整")

    def set_smooth_factor(self, factor: float):
        """
        设置平滑系数

        Args:
            factor: 平滑系数 0~1（越大越平滑）
        """
        old_factor = self._smooth_factor
        self._smooth_factor = max(0.0, min(1.0, factor))
        utils.log(f"🔧 平滑系数调整: {old_factor:.2f} → {self._smooth_factor:.2f}")

    def set_max_consecutive_misses(self, count: int):
        """
        设置最大连续失败次数

        Args:
            count: 次数（建议3-10）
        """
        old_count = self._max_consecutive_misses
        self._max_consecutive_misses = max(1, count)
        utils.log(f"🔧 最大连续失败次数调整: {old_count} → {self._max_consecutive_misses}")

    def enable(self):
        """启用检测"""
        self.enabled = True
        utils.log("✅ 准星检测已启用")

    def disable(self):
        """禁用检测"""
        self.enabled = False
        utils.log("⏸️ 准星检测已禁用")

    def enable_smooth(self):
        """启用平滑"""
        self._enable_smooth = True
        utils.log("✅ 位置平滑已启用")

    def disable_smooth(self):
        """禁用平滑"""
        self._enable_smooth = False
        utils.log("⏸️ 位置平滑已禁用")

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

        info += f", 平滑: {'开' if self._enable_smooth else '关'}"
        info += f", 容错: {self._max_consecutive_misses}次"

        return info

    def __str__(self):
        """字符串表示"""
        stats = self.get_stats()
        return (
            f"CrosshairManager("
            f"type={self.detector_type}, "
            f"enabled={self.enabled}, "
            f"success_rate={stats['success_rate']}, "
            f"smooth={'ON' if self._enable_smooth else 'OFF'}"
            f")"
        )

    def __repr__(self):
        return self.__str__()


# ============================================================
# 便捷工厂函数
# ============================================================

def create_crosshair_manager(
        config_code: Optional[str] = None,
        detector_type: str = 'template',
        max_consecutive_misses: int = 10,
        enable_smooth: bool = False,
        smooth_factor: float = 0.7
) -> CrosshairManager:
    """
    创建准星管理器的便捷函数

    Args:
        config_code: Valorant准星配置代码
        detector_type: 检测器类型
        max_consecutive_misses: 容错次数
        enable_smooth: 是否启用平滑
        smooth_factor: 平滑系数

    Returns:
        CrosshairManager实例
    """
    return CrosshairManager(
        detector_type=detector_type,
        valorant_config_code=config_code,
        enable_detection=True,
        max_consecutive_misses=max_consecutive_misses,
        enable_smooth=enable_smooth,
        smooth_factor=smooth_factor
    )
