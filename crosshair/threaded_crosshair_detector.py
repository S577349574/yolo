import threading
import queue
from typing import Optional, Tuple
import numpy as np


class ThreadedCrosshairDetector:
    """多线程准星检测器"""

    def __init__(self, crosshair_manager):
        self.crosshair_manager = crosshair_manager
        self.latest_position: Optional[Tuple[int, int]] = None
        self.position_lock = threading.Lock()  # 保护准星位置

        # 图像队列（主循环 → 检测线程）
        self.image_queue = queue.Queue(maxsize=2)  # 最多缓存2帧

        # 控制标志
        self.running = False
        self.detection_thread: Optional[threading.Thread] = None

        # 统计信息
        self.detection_count = 0
        self.success_count = 0

    def start(self):
        """启动检测线程"""
        if self.running:
            return

        self.running = True
        self.detection_thread = threading.Thread(
            target=self._detection_loop,
            name="CrosshairDetectionThread",
            daemon=True  # 守护线程，主程序退出时自动结束
        )
        self.detection_thread.start()
        print("✅ 准星检测线程已启动")

    def stop(self):
        """停止检测线程"""
        self.running = False
        if self.detection_thread:
            self.detection_thread.join(timeout=1.0)
        print("⏹️ 准星检测线程已停止")

    def submit_frame(self, img_bgra: np.ndarray, capture_area: dict, fallback_center: Tuple[int, int]):
        """
        提交新帧供检测（非阻塞）

        Args:
            img_bgra: BGRA图像
            capture_area: 捕获区域信息
            fallback_center: 后备中心点
        """
        try:
            # 非阻塞放入队列，如果队列满了就丢弃旧帧
            self.image_queue.put_nowait({
                'img': img_bgra.copy(),  # ⚠️ 必须复制，避免数据竞争
                'area': capture_area,
                'fallback': fallback_center
            })
        except queue.Full:
            # 队列满了，丢弃当前帧（准星检测不需要每帧都检测）
            pass

    def get_position(self, fallback_center: Tuple[int, int]) -> Tuple[int, int]:
        """
        获取最新准星位置（非阻塞）

        Args:
            fallback_center: 后备中心点

        Returns:
            准星位置 (x, y)
        """
        with self.position_lock:
            if self.latest_position is not None:
                return self.latest_position
            else:
                return fallback_center

    def _detection_loop(self):
        """检测线程主循环"""
        while self.running:
            try:
                # 阻塞获取新帧（最多等待0.1秒）
                frame_data = self.image_queue.get(timeout=0.1)

                # 执行检测
                self.detection_count += 1
                position = self.crosshair_manager.detect(
                    img=frame_data['img'],
                    capture_area=frame_data['area'],
                    fallback_center=frame_data['fallback']
                )

                # 更新最新位置（线程安全）
                with self.position_lock:
                    if position is not None:
                        self.latest_position = position
                        self.success_count += 1

            except queue.Empty:
                # 队列空了，继续等待
                continue
            except Exception as e:
                print(f"❌ 准星检测线程异常: {e}")

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            'total': self.detection_count,
            'success': self.success_count,
            'success_rate': self.success_count / max(1, self.detection_count) * 100
        }
