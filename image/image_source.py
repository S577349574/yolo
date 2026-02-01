# image_source.py
"""
统一图像源接口 - 支持多种图像获取方式
"""
from abc import ABC, abstractmethod
from typing import Optional

import numpy as np

import utils
from network.video_receiver import FrameReceiver


class ImageSource(ABC):
    """图像源抽象基类"""

    @abstractmethod
    def start(self):
        """启动图像源"""
        pass

    @abstractmethod
    def stop(self):
        """停止图像源"""
        pass

    @abstractmethod
    def get_frame(self, timeout: float = 0.016) -> Optional[np.ndarray]:
        """
        获取最新帧

        Args:
            timeout: 超时时间（秒）

        Returns:
            np.ndarray (H, W, 3) BGR, or None
        """
        pass

    @abstractmethod
    def get_stats(self) -> dict:
        """获取统计信息"""
        pass

    @abstractmethod
    def is_running(self) -> bool:
        """检查是否正在运行"""
        pass


# ============================================================
# 实现1: 本地屏幕捕获
# ============================================================

class LocalScreenSource(ImageSource):
    """本地屏幕捕获源（基于 shared_capture）"""

    def __init__(self, crop_size: int = 640):
        self.crop_size = crop_size
        self.frame_buffer = None
        self.capture_process = None
        self.stop_event = None
        self._running = False

    def start(self):
        if self._running:
            return

        utils.log("\n📸 启动本地屏幕捕获...")
        from image.shared_capture import start_capture_process

        self.frame_buffer, self.capture_process, self.stop_event = \
            start_capture_process(crop_size=self.crop_size)

        self._running = True
        utils.log(f"✅ 本地捕获已就绪 | 尺寸: {self.crop_size}x{self.crop_size}")

    def stop(self):
        if not self._running:
            return

        utils.log("🛑 停止本地屏幕捕获...")

        if self.stop_event:
            self.stop_event.set()

        if self.capture_process and self.capture_process.is_alive():
            self.capture_process.join(timeout=2.0)
            if self.capture_process.is_alive():
                self.capture_process.terminate()
                self.capture_process.join(timeout=1.0)

        if self.frame_buffer:
            self.frame_buffer.cleanup()

        self._running = False
        utils.log("✅ 本地捕获已停止")

    def get_frame(self, timeout: float = 0.016) -> Optional[np.ndarray]:
        if not self._running or not self.frame_buffer:
            return None

        frame = self.frame_buffer.read_frame(timeout=timeout)
        if frame is None:
            return None

        # frame: BGRA (H, W, 4) → BGR (H, W, 3)
        if frame.ndim == 3 and frame.shape[2] == 4:
            frame = frame[:, :, :3]

        return frame

    def get_stats(self) -> dict:
        if self.frame_buffer:
            return self.frame_buffer.get_stats()
        return {'frames': 0, 'fps': 0, 'memory_mb': 0}

    def is_running(self) -> bool:
        return self._running


# ============================================================
# 实现2: UDP网络接收
# ============================================================

class NetworkSource(ImageSource):
    """网络画面接收源（基于 frame_receiver + simplejpeg）"""

    def __init__(
            self,
            listen_port: int = 27015,
            frame_width: int = 320,
            frame_height: int = 320,
    ):
        self.receiver = FrameReceiver(
            listen_port=listen_port,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        self._running = False

    def start(self):
        if self._running:
            return

        utils.log("\n🌐 启动UDP网络画面接收...")
        self.receiver.start()
        self._running = True
        utils.log(f"✅ 网络接收已启动 | 端口: {self.receiver.port}")

    def stop(self):
        if not self._running:
            return

        utils.log("🛑 停止网络画面接收...")
        self.receiver.stop()
        self._running = False
        utils.log("✅ 网络接收已停止")

    def get_frame(self, timeout: float = 0.016) -> Optional[np.ndarray]:
        if not self._running:
            return None

        # ✅ 获取最新帧（RGB 格式）
        frame = self.receiver.get_latest_frame()

        return frame

    def get_stats(self) -> dict:
        if not self._running:
            return {'frames': 0, 'fps': 0, 'latency_avg': 0}

        # 从 FrameReceiver 获取统计信息
        return {
            'frames': self.receiver._frame_count,
            'fps': 0,  # 可以根据需要添加 FPS 计算
            'latency_avg': (
                self.receiver.latency_sum / self.receiver.latency_count
                if self.receiver.latency_count > 0 else 0
            ),
            'latency_min': self.receiver.latency_min,
            'latency_max': self.receiver.latency_max
        }

    def is_running(self) -> bool:
        return self._running


# ============================================================
# 工厂函数
# ============================================================

def create_image_source(target_size: Optional[int] = None) -> ImageSource:
    """
    从配置文件创建图像源（自动读取配置）

    Args:
        target_size: 目标图像尺寸（优先级高于配置文件）
                    - 对于 local 模式：设置 crop_size
                    - 对于 network 模式：设置 frame_width 和 frame_height

    Returns:
        ImageSource 实例
    """
    from config_manager import get_config

    source_type = get_config('IMAGE_SOURCE_TYPE', 'local')

    if source_type == 'local':
        # ✅ 优先使用传入的 target_size，否则使用配置文件
        crop_size = target_size
        utils.log(f"🖼️ 图像源: 本地屏幕捕获 ({crop_size}x{crop_size})")
        return LocalScreenSource(crop_size=crop_size)

    elif source_type == 'network':
        frame_port = get_config('FRAME_PORT', 27015)

        # ✅ 优先使用传入的 target_size，否则使用配置文件
        if target_size is not None:
            frame_width = target_size
            frame_height = target_size
        else:
            frame_width = get_config('FRAME_WIDTH', 320)
            frame_height = get_config('FRAME_HEIGHT', 320)

        utils.log(f"🖼️ 图像源: UDP网络接收 (simplejpeg)")
        utils.log(f"   监听端口: {frame_port}")
        utils.log(f"   帧尺寸: {frame_width}x{frame_height}x3 (RGB)")

        return NetworkSource(
            listen_port=frame_port,
            frame_width=frame_width,
            frame_height=frame_height,
        )

    else:
        raise ValueError(f"不支持的图像源类型: {source_type}，请在 config.json 中设置为 'local' 或 'network'")
