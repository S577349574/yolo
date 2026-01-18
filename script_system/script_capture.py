# script_capture.py
"""
Lua 脚本专用截图模块
与 YOLO 推理完全解耦，支持任意尺寸截图
"""

import os
import re
import time
import numpy as np
import utils

try:
    import mss

    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False
    utils.log("⚠️ mss 未安装，脚本截图功能不可用")

try:
    import cv2

    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    utils.log("⚠️ opencv-python 未安装，脚本截图功能不可用")


class ScriptScreenCapture:
    """
    脚本专用屏幕截图器

    特点：
    - 独立于 YOLO 推理
    - 支持任意尺寸截图
    - 自动处理中文路径
    - 按类别自动分类存储
    """

    def __init__(self, save_dir: str = "collected_images"):
        """
        初始化截图器

        Args:
            save_dir: 图片保存根目录
        """
        if not MSS_AVAILABLE or not CV2_AVAILABLE:
            raise RuntimeError("缺少必要库：mss 和 opencv-python")

        self.save_dir = save_dir
        self.sct = mss.mss()

        # 获取主屏幕尺寸
        self.monitor = self.sct.monitors[1]
        self.screen_width = self.monitor['width']
        self.screen_height = self.monitor['height']

        # 统计信息
        self._capture_count = 0
        self._last_capture_time = 0

        utils.log(f"[ScriptCapture] 初始化完成 | 屏幕: {self.screen_width}x{self.screen_height}")

    def capture_center_region(self, width: int, height: int) -> np.ndarray:
        """
        截取屏幕中心区域

        Args:
            width: 截图宽度
            height: 截图高度

        Returns:
            np.ndarray: BGR 格式图像 (height, width, 3)
        """
        try:
            # 计算中心区域坐标
            left = (self.screen_width - width) // 2
            top = (self.screen_height - height) // 2

            # 边界检查
            left = max(0, left)
            top = max(0, top)
            width = min(width, self.screen_width - left)
            height = min(height, self.screen_height - top)

            capture_region = {
                "left": left,
                "top": top,
                "width": width,
                "height": height
            }

            # 执行截图
            screenshot = self.sct.grab(capture_region)
            img = np.array(screenshot)

            # 转换 BGRA -> BGR
            if img.shape[2] == 4:
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

            return img

        except Exception as e:
            utils.log(f"[ScriptCapture] 截图失败: {e}")
            return None

    def save_screenshot(
            self,
            category: str,
            label: str = None,
            width: int = 640,
            height: int = 640
    ) -> bool:
        """
        截图并保存到分类文件夹

        Args:
            category: 类别名（如 "enemy", "friend"）
            label: 文件名前缀（可选）
            width: 截图宽度
            height: 截图高度

        Returns:
            bool: 是否成功保存
        """
        try:
            # 1. 清洗文件名（防止路径注入）
            category = self._sanitize_filename(category)
            label = label or category
            label = self._sanitize_filename(label)

            # 2. 创建目标目录
            target_dir = os.path.join(self.save_dir, category)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)
                utils.log(f"[ScriptCapture] 创建目录: {category}/")

            # 3. 截取图像
            t_start = time.perf_counter()
            img = self.capture_center_region(width, height)

            if img is None:
                utils.log("[ScriptCapture] 截图失败: 图像为空")
                return False

            # 4. 生成文件名
            timestamp = int(time.time() * 1000)
            file_name = f"{label}_{timestamp}.bmp"
            save_path = os.path.join(target_dir, file_name)

            # 5. 保存图片（使用二进制写入避免中文路径问题）
            is_success, buffer = cv2.imencode(".bmp", img)
            if not is_success:
                utils.log("[ScriptCapture] BMP 编码失败")
                return False

            with open(save_path, "wb") as f:
                f.write(buffer)

            # 6. 统计信息
            self._capture_count += 1
            self._last_capture_time = time.perf_counter()

            elapsed = (time.perf_counter() - t_start) * 1000
            file_size = len(buffer) / 1024

            utils.log(
                f"[ScriptCapture] 已保存: {category}/{file_name} "
                f"({width}x{height}, {file_size:.1f}KB, 耗时 {elapsed:.2f}ms)"
            )

            return True

        except Exception as e:
            utils.log(f"[ScriptCapture] 保存失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _sanitize_filename(self, name: str) -> str:
        """
        清洗文件名，移除非法字符

        Args:
            name: 原始文件名

        Returns:
            str: 清洗后的文件名
        """
        # 保留：字母、数字、中文、下划线、连字符
        cleaned = re.sub(r'[^\w\u4e00-\u9fa5\-]', '_', str(name))
        # 限制长度
        return cleaned[:100]

    def get_screen_info(self) -> dict:
        """
        获取屏幕信息

        Returns:
            dict: {"width": int, "height": int, "capture_count": int}
        """
        return {
            "width": self.screen_width,
            "height": self.screen_height,
            "capture_count": self._capture_count
        }

    def cleanup(self):
        """清理资源"""
        try:
            if hasattr(self, 'sct'):
                self.sct.close()
                utils.log("[ScriptCapture] 资源已释放")
        except Exception as e:
            utils.log(f"[ScriptCapture] 清理异常: {e}")
