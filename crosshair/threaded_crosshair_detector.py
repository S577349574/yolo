# crosshair/threaded_crosshair_detector.py
import threading
import queue
from typing import Optional, Tuple

import multiprocessing as mp
import numpy as np
import time

class ThreadedCrosshairDetector:
    """多线程准星检测器"""

    def __init__(self, crosshair_manager, img_shape: Tuple[int, int, int] = (720, 1280, 4)):
        """
        Args:
            crosshair_manager: 准星管理器实例
            img_shape: 图像形状 (height, width, channels)，默认 720p BGRA
        """
        self.crosshair_manager = crosshair_manager
        self.img_shape = img_shape  # ✅ 先保存 img_shape
        self.latest_position: Optional[Tuple[int, int]] = None
        self.position_lock = threading.Lock()

        # 图像队列（主循环 → 检测线程）
        self.image_queue = queue.Queue(maxsize=2)

        # 控制标志
        self.running = False
        self.detection_thread: Optional[threading.Thread] = None

        # 统计信息
        self.detection_count = 0
        self.success_count = 0
        self.last_report_time = time.time()
        self.frames_processed = 0

        # ✅ 共享内存初始化（必须在 img_shape 定义后）
        self.shared_img = mp.Array('B', int(np.prod(img_shape)))
        self.img_lock = threading.Lock()

    def start(self):
        """启动检测线程"""
        if self.running:
            return

        self.running = True
        self.detection_thread = threading.Thread(
            target=self._detection_loop,
            name="CrosshairDetectionThread",
            daemon=True
        )
        self.detection_thread.start()
        print("✅ 准星检测线程已启动")

    def stop(self):
        """停止检测线程"""
        self.running = False
        if self.detection_thread:
            self.detection_thread.join(timeout=1.0)
        print("⏹️ 准星检测线程已停止")

    def submit_frame(self, img_bgra, capture_area, fallback_center):
        """提交新帧进行检测"""
        # 快速写入共享内存
        with self.img_lock:
            np.copyto(
                np.frombuffer(self.shared_img.get_obj(), dtype=np.uint8).reshape(self.img_shape),
                img_bgra
            )

        # 只传递元数据
        try:
            self.image_queue.put_nowait({
                'area': capture_area,
                'fallback': fallback_center,
                'timestamp': time.time()
            })
        except queue.Full:
            pass

    def get_position(self, fallback_center: Tuple[int, int]) -> Tuple[int, int]:
        """获取最新准星位置（非阻塞）"""
        with self.position_lock:
            if self.latest_position is not None:
                return self.latest_position
            else:
                return fallback_center

    def _detection_loop(self):
        """检测线程主循环"""
        while self.running:
            try:
                meta = self.image_queue.get(timeout=0.1)

                # 从共享内存读取图像
                with self.img_lock:
                    img = np.frombuffer(
                        self.shared_img.get_obj(),
                        dtype=np.uint8
                    ).reshape(self.img_shape).copy()

                self.detection_count += 1
                position = self.crosshair_manager.detect(
                    img=img,
                    capture_area=meta['area'],
                    fallback_center=meta['fallback']
                )

                # 更新位置
                with self.position_lock:
                    self.latest_position = position
                    if position != meta['fallback']:
                        self.success_count += 1

                self.frames_processed += 1

            except queue.Empty:
                continue
            except Exception as e:
                print(f"❌ 检测线程异常: {e}")

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            'total': self.detection_count,
            'success': self.success_count,
            'success_rate': self.success_count / max(1, self.detection_count) * 100,
            'frames_processed': self.frames_processed
        }
