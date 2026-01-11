# crosshair/detectors/red_dot_detector.py
"""
红点准星专用检测器（v4.3 - 完整调试版）

优化调试信息:
- ✅ 完整坐标追踪链
- ✅ 偏移距离可视化
- ✅ 决策依据说明
- ✅ 阈值边界诊断
"""

from typing import Optional, Tuple, List
import cv2
import numpy as np

import utils
from crosshair import CrosshairDetector


class EnhancedRedDotDetector(CrosshairDetector):
    """增强版红点检测器（完整调试版）⭐"""

    def __init__(self, enable_debug: bool = False):
        super().__init__()

        self.enable_debug = enable_debug

        # ===== 红色 HSV 范围 =====
        self.red_lower1 = np.array([0, 100, 80])
        self.red_upper1 = np.array([10, 255, 255])
        self.red_lower2 = np.array([170, 100, 80])
        self.red_upper2 = np.array([180, 255, 255])

        # ===== 高亮中心检测 =====
        self.bright_center_threshold = 120
        self.min_center_area = 3
        self.max_center_area = 50

        # ===== 面积 & 尺度 =====
        self.min_area = 8
        self.max_area = 150
        self.min_radius = 2.0
        self.max_radius = 5.0

        # ===== 形状 =====
        self.min_circularity = 0.5

        # ===== 结构验证参数 =====
        self.ring_sample_points = 24
        self.min_ring_completeness = 0.25

        # ===== 调试统计 =====
        self._frame_count = 0
        self._stats = {
            'found_bright_centers': 0,
            'passed_brightness': 0,
            'passed_red_ring': 0,
            'passed_clean_circle': 0,
            'passed_gradient': 0,
            'passed_geometric': 0,
            'final_success': 0,
            'total_offset': 0.0,
            'max_offset': 0.0
        }

        utils.log(f"🔴 {self.get_name()} 初始化完成")
        if enable_debug:
            utils.log("   🐛 详细调试模式已启用（完整坐标追踪）")

    def get_name(self) -> str:
        return "增强红点检测器（完整调试版）"

    # ==========================================================
    # 主检测逻辑
    # ==========================================================
    def _detect_impl(self, roi: np.ndarray) -> Optional[Tuple[int, int]]:
        """主检测入口"""
        self._frame_count += 1

        if self.enable_debug:
            utils.log("\n" + "=" * 60)
            utils.log(f"🎯 帧 #{self._frame_count} - 开始检测")
            utils.log(f"   ROI尺寸: {roi.shape}")

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

        roi_cx = roi.shape[1] / 2
        roi_cy = roi.shape[0] / 2

        if self.enable_debug:
            utils.log(f"\n📍 ROI理论中心: ({roi_cx:.1f}, {roi_cy:.1f})")

        # 方法1：结构化检测
        if self.enable_debug:
            utils.log("\n🔍 方法1: 结构化检测")

        result = self._detect_with_structure(roi, hsv, gray, roi_cx, roi_cy)
        if result:
            self._stats['final_success'] += 1
            offset = np.hypot(result[0] - roi_cx, result[1] - roi_cy)
            self._stats['total_offset'] += offset
            self._stats['max_offset'] = max(self._stats['max_offset'], offset)

            if self.enable_debug:
                utils.log(f"\n✅ 成功: {result}, 偏移ROI中心: {offset:.2f}px")
            return result

        # 方法2：兜底检测
        if self.enable_debug:
            utils.log("\n🔍 方法2: 兜底检测")

        result = self._detect_red_fallback(hsv, gray, roi_cx, roi_cy)
        if result:
            self._stats['final_success'] += 1
            if self.enable_debug:
                utils.log(f"\n✅ 兜底成功: {result}")
            return result

        if self.enable_debug:
            utils.log("\n❌ 所有方法均失败")
            self._print_stats()

        return None

    def _detect_with_structure(self, roi, hsv, gray, roi_cx, roi_cy):
        """结构化检测（完整追踪版）"""

        if self.enable_debug:
            utils.log("\n🔍 步骤1: 查找高亮中心")

        bright_centers = self._find_bright_centers(gray, roi_cx, roi_cy)
        if not bright_centers:
            if self.enable_debug:
                utils.log("   ❌ 未找到高亮中心")
            return None

        self._stats['found_bright_centers'] += 1

        red_mask = self._create_red_mask(hsv, roi_cx, roi_cy)

        total_red = np.sum(red_mask > 0)
        if self.enable_debug:
            utils.log(f"\n🎨 红色像素: {total_red} 个")
            if total_red == 0:
                utils.log("   ⚠️  警告: 无红色像素!")

        candidates = []

        for idx, (cx, cy, intensity) in enumerate(bright_centers):
            if self.enable_debug:
                offset = np.hypot(cx - roi_cx, cy - roi_cy)
                utils.log(f"\n   {'=' * 50}")
                utils.log(f"   🎯 候选{idx + 1}: ({cx},{cy}), 距ROI中心: {offset:.2f}px")

            # 亮度验证
            margin = intensity - self.bright_center_threshold
            if intensity < self.bright_center_threshold:
                if self.enable_debug:
                    utils.log(f"   1️⃣ 亮度: ❌ {intensity:.0f} (差{-margin:.0f})")
                continue

            self._stats['passed_brightness'] += 1
            if self.enable_debug:
                utils.log(f"   1️⃣ 亮度: ✅ {intensity:.0f} (余量+{margin:.0f})")

            # 红色环验证
            ring_score = self._verify_ring(red_mask, cx, cy)
            ring_margin = ring_score - self.min_ring_completeness

            if ring_score < self.min_ring_completeness:
                if self.enable_debug:
                    utils.log(f"   2️⃣ 红环: ❌ {ring_score:.2%} (差{-ring_margin:.2%})")
                continue

            self._stats['passed_red_ring'] += 1
            if self.enable_debug:
                utils.log(f"   2️⃣ 红环: ✅ {ring_score:.2%} (余量+{ring_margin:.2%})")

            # 圆形验证
            is_clean, circularity, circle_center = self._verify_circle(red_mask, cx, cy)

            if not is_clean:
                if self.enable_debug:
                    utils.log(f"   2.5️⃣ 圆形: ❌ (圆形度{circularity:.3f})")
                continue

            self._stats['passed_clean_circle'] += 1
            if self.enable_debug:
                utils.log(f"   2.5️⃣ 圆形: ✅ (圆形度{circularity:.3f})")
                if circle_center:
                    circle_offset = np.hypot(circle_center[0] - cx, circle_center[1] - cy)
                    utils.log(
                        f"         外接圆心: ({circle_center[0]:.1f},{circle_center[1]:.1f}), 偏离亮点{circle_offset:.2f}px")

            # 梯度验证
            gradient = self._verify_gradient(gray, cx, cy)
            if gradient >= 0.2:
                self._stats['passed_gradient'] += 1

            if self.enable_debug:
                status = "✅" if gradient >= 0.2 else "⚠️ "
                utils.log(f"   3️⃣ 梯度: {status} {gradient:.2f}")

            # 几何验证
            geo_ok, red_center, geo_offset = self._verify_geometry(red_mask, cx, cy)
            if geo_ok:
                self._stats['passed_geometric'] += 1

            if self.enable_debug:
                status = "✅" if geo_ok else "⚠️ "
                utils.log(f"   4️⃣ 几何: {status}")
                if red_center:
                    utils.log(f"         红环质心: ({red_center[0]:.1f},{red_center[1]:.1f}), 偏离{geo_offset:.2f}px")

            # 中心修正
            final_cx, final_cy, info = self._refine_center(cx, cy, red_mask)

            if self.enable_debug and info:
                utils.log(f"\n   🎯 中心修正:")
                utils.log(f"      亮点: ({cx},{cy})")
                if info['red_center']:
                    utils.log(f"      红环质心: ({info['red_center'][0]:.1f},{info['red_center'][1]:.1f})")
                if info['circle_center']:
                    utils.log(f"      外接圆心: ({info['circle_center'][0]:.1f},{info['circle_center'][1]:.1f})")
                utils.log(f"      融合权重: 红环×{info['red_weight']:.1f} + 亮点×{info['bright_weight']:.1f}")
                utils.log(f"      ✅ 最终: ({final_cx},{final_cy})")

                final_offset = np.hypot(final_cx - cx, final_cy - cy)
                utils.log(f"      📏 修正幅度: {final_offset:.2f}px")

            # 综合得分
            distance_score = 1.0 - (np.hypot(final_cx - roi_cx, final_cy - roi_cy) / np.hypot(roi_cx, roi_cy))
            final_score = ring_score * 0.4 + (intensity / 255) * 0.3 + distance_score * 0.2 + gradient * 0.1

            candidates.append((final_score, (final_cx, final_cy)))

        if not candidates:
            if self.enable_debug:
                utils.log("\n   ❌ 无候选通过验证")
            return None

        candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_pos = candidates[0]

        if self.enable_debug:
            utils.log(f"\n   {'=' * 50}")
            utils.log(f"   ✅ 最终选中: {best_pos}, 得分{best_score:.3f}")

        return best_pos

    # ==========================================================
    # 辅助方法
    # ==========================================================
    def _find_bright_centers(self, gray, roi_cx, roi_cy):
        """查找高亮中心"""
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(gray)

        if max_val < self.bright_center_threshold:
            if self.enable_debug:
                utils.log(f"      最大亮度{max_val:.0f} < 阈值{self.bright_center_threshold}")
            return []

        cx, cy = max_loc
        offset = np.hypot(cx - roi_cx, cy - roi_cy)

        if self.enable_debug:
            utils.log(f"      ✅ 最亮点: ({cx},{cy}), 亮度{max_val:.0f}, 距ROI中心{offset:.2f}px")

        return [(cx, cy, max_val)]

    def _create_red_mask(self, hsv, roi_cx, roi_cy):
        """创建红色掩码（带颜色诊断）"""
        mask1 = cv2.inRange(hsv, self.red_lower1, self.red_upper1)
        mask2 = cv2.inRange(hsv, self.red_lower2, self.red_upper2)
        red_mask = cv2.bitwise_or(mask1, mask2)

        if self.enable_debug:
            # 分析中心区域颜色
            h, w = hsv.shape[:2]
            cx, cy = int(roi_cx), int(roi_cy)
            margin = 10

            cx_start = max(0, cx - margin)
            cx_end = min(w, cx + margin)
            cy_start = max(0, cy - margin)
            cy_end = min(h, cy + margin)

            center_region = hsv[cy_start:cy_end, cx_start:cx_end]

            if center_region.size > 0:
                avg_h = np.mean(center_region[:, :, 0])
                avg_s = np.mean(center_region[:, :, 1])
                avg_v = np.mean(center_region[:, :, 2])

                utils.log(f"\n      🎨 中心区域HSV: H={avg_h:.1f}°, S={avg_s:.0f}, V={avg_v:.0f}")
                utils.log(f"         期望: H=[0-10 或 170-180], S≥100, V≥80")

                is_red_h = (0 <= avg_h <= 10) or (170 <= avg_h <= 180)
                is_red_s = avg_s >= 100
                is_red_v = avg_v >= 80
                is_red = is_red_h and is_red_s and is_red_v

                utils.log(f"         判定: {'✅红色' if is_red else '❌非红色'}")

                if not is_red:
                    utils.log(f"         💡 不匹配原因:")
                    if not is_red_h:
                        utils.log(f"            色相H={avg_h:.1f}° 不在红色范围")
                    if not is_red_s:
                        utils.log(f"            饱和度S={avg_s:.0f} 过低(颜色太淡)")
                    if not is_red_v:
                        utils.log(f"            明度V={avg_v:.0f} 过低(颜色太暗)")

        # 形态学闭运算
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_CLOSE, kernel)

        if self.enable_debug:
            red1 = np.sum(mask1 > 0)
            red2 = np.sum(mask2 > 0)
            utils.log(f"      范围1(0-10°): {red1}像素, 范围2(170-180°): {red2}像素")

        return red_mask

    def _verify_ring(self, red_mask, cx, cy):
        """验证红色环"""
        radii = [int(self.min_radius + 1), int((self.min_radius + self.max_radius) / 2), int(self.max_radius - 1)]
        best_score = 0.0

        for r in radii:
            score = 0
            total = 0
            for angle in np.linspace(0, 360, self.ring_sample_points, endpoint=False):
                x = int(cx + r * np.cos(np.deg2rad(angle)))
                y = int(cy + r * np.sin(np.deg2rad(angle)))
                if 0 <= x < red_mask.shape[1] and 0 <= y < red_mask.shape[0]:
                    total += 1
                    if red_mask[y, x] > 0:
                        score += 1

            current = score / total if total > 0 else 0
            best_score = max(best_score, current)

            if self.enable_debug:
                utils.log(f"         半径{r}px: {current:.2%} ({score}/{total})")

        return best_score

    def _verify_circle(self, red_mask, cx, cy):
        """验证圆形边界"""
        contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for c in contours:
            if cv2.pointPolygonTest(c, (float(cx), float(cy)), False) >= 0:
                area = cv2.contourArea(c)
                perimeter = cv2.arcLength(c, True)

                if perimeter == 0 or area < self.min_area:
                    continue

                circularity = 4 * np.pi * area / (perimeter ** 2)

                if circularity < 0.6:
                    return False, circularity, None

                (ccx, ccy), radius = cv2.minEnclosingCircle(c)

                if radius < self.min_radius or radius > self.max_radius:
                    return False, circularity, (ccx, ccy)

                # 验证圆形内外比例
                circle_mask = np.zeros_like(red_mask)
                cv2.circle(circle_mask, (int(ccx), int(ccy)), int(radius), 255, -1)

                outer_radius = int(radius * 1.3)
                outer_mask = np.zeros_like(red_mask)
                cv2.circle(outer_mask, (int(ccx), int(ccy)), outer_radius, 255, -1)

                ring_mask = cv2.bitwise_and(outer_mask, cv2.bitwise_not(circle_mask))

                inside = np.sum(cv2.bitwise_and(red_mask, circle_mask) > 0)
                total_inside = np.sum(circle_mask > 0)
                ring = np.sum(cv2.bitwise_and(red_mask, ring_mask) > 0)
                total_ring = np.sum(ring_mask > 0)

                inside_ratio = inside / total_inside if total_inside > 0 else 0
                ring_ratio = ring / total_ring if total_ring > 0 else 0

                is_clean = inside_ratio >= 0.40 and ring_ratio <= 0.15 and inside >= ring * 3

                return is_clean, circularity, (ccx, ccy)

        return False, 0.0, None

    def _verify_gradient(self, gray, cx, cy):
        """验证径向梯度"""
        r_inner = max(1, int(self.min_radius * 0.5))
        r_outer = int(self.max_radius * 1.2)

        def sample(r):
            samples = []
            for angle in range(0, 360, 30):
                x = int(cx + r * np.cos(np.deg2rad(angle)))
                y = int(cy + r * np.sin(np.deg2rad(angle)))
                if 0 <= x < gray.shape[1] and 0 <= y < gray.shape[0]:
                    samples.append(gray[y, x])
            return np.mean(samples) if samples else 0

        inner = sample(r_inner)
        outer = sample(r_outer)

        if inner > outer:
            return min(1.0, (inner - outer) / 255)
        return 0.0

    def _verify_geometry(self, red_mask, cx, cy):
        """验证几何中心"""
        contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for c in contours:
            M = cv2.moments(c)
            if M["m00"] == 0:
                continue

            rcx = int(M["m10"] / M["m00"])
            rcy = int(M["m01"] / M["m00"])
            dist = np.hypot(cx - rcx, cy - rcy)

            if dist < 6:
                return True, (rcx, rcy), dist

        return False, None, 0.0

    def _refine_center(self, cx, cy, red_mask):
        """中心修正（带追踪）"""
        info = {'red_center': None, 'circle_center': None, 'red_weight': 0.3, 'bright_weight': 0.7}

        contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        best_contour = None
        best_area = 0

        for c in contours:
            if cv2.pointPolygonTest(c, (float(cx), float(cy)), False) >= 0:
                area = cv2.contourArea(c)
                if area > best_area:
                    best_area = area
                    best_contour = c

        if best_contour is None:
            return cx, cy, info

        M = cv2.moments(best_contour)
        if M["m00"] != 0:
            rcx = M["m10"] / M["m00"]
            rcy = M["m01"] / M["m00"]
            info['red_center'] = (rcx, rcy)

        (ccx, ccy), radius = cv2.minEnclosingCircle(best_contour)
        info['circle_center'] = (ccx, ccy)

        final_cx = int(0.3 * ccx + 0.7 * cx)
        final_cy = int(0.3 * ccy + 0.7 * cy)

        return final_cx, final_cy, info

    def _detect_red_fallback(self, hsv, gray, roi_cx, roi_cy):
        """兜底检测"""
        red_mask = self._create_red_mask(hsv, roi_cx, roi_cy)
        contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            if self.enable_debug:
                utils.log("   ❌ 无红色轮廓")
            return None

        best = None
        best_dist = float("inf")

        for c in contours:
            area = cv2.contourArea(c)
            if area < self.min_area or area > self.max_area:
                continue

            M = cv2.moments(c)
            if M["m00"] == 0:
                continue

            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])

            d = np.hypot(cx - roi_cx, cy - roi_cy)
            if d < best_dist:
                best_dist = d
                best = (cx, cy)

        if self.enable_debug and best:
            utils.log(f"   ✅ 最佳候选: {best}, 距ROI中心{best_dist:.1f}px")

        return best

    def _print_stats(self):
        """打印统计"""
        utils.log(f"\n📊 统计 (共{self._frame_count}帧):")
        utils.log(f"   找到高亮中心: {self._stats['found_bright_centers']}次")
        utils.log(f"   通过亮度: {self._stats['passed_brightness']}次")
        utils.log(f"   通过红环: {self._stats['passed_red_ring']}次")
        utils.log(f"   通过圆形: {self._stats['passed_clean_circle']}次")
        utils.log(f"   通过梯度: {self._stats['passed_gradient']}次")
        utils.log(f"   通过几何: {self._stats['passed_geometric']}次")
        utils.log(
            f"   最终成功: {self._stats['final_success']}次 ({self._stats['final_success'] / self._frame_count * 100:.1f}%)")

        if self._stats['final_success'] > 0:
            avg = self._stats['total_offset'] / self._stats['final_success']
            utils.log(f"\n📏 偏移统计:")
            utils.log(f"   平均偏移: {avg:.2f}px")
            utils.log(f"   最大偏移: {self._stats['max_offset']:.2f}px")

    def reset_stats(self):
        """重置统计"""
        self._frame_count = 0
        for key in self._stats:
            self._stats[key] = 0
