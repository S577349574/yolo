"""
画面接收模块（UDP + LZ4 + 抗漂移时钟校准 + 延迟测量）
不依赖联网，长期运行不漂移
"""
import socket
import struct
import threading
import time
import numpy as np
import lz4.frame


class FrameReceiver:
    """画面接收器（perf_counter 时间轴 + 在线时间映射校准）"""

    RECENT_LATENCY_MAX = 100
    OFFSET_WINDOW = 60
    OFFSET_ALPHA = 0.02
    CLAMP_NEGATIVE = True

    def __init__(
        self,
        listen_port: int = 27015,
        use_lz4: bool = True,
        frame_width: int = 320,
        frame_height: int = 320,
        frame_channels: int = 3
    ):
        self.port = listen_port
        self.use_lz4 = use_lz4

        # 帧尺寸配置
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.frame_channels = frame_channels
        self.expected_frame_size = (
            frame_width * frame_height * frame_channels
        )

        # UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        self.sock.bind(("0.0.0.0", listen_port))
        self.sock.settimeout(0.1)

        # 分包缓存
        self.packets = {}
        self.current_frame = None
        self.frame_lock = threading.Lock()

        # 延迟统计
        self.latency_sum = 0.0
        self.latency_count = 0
        self.latency_min = float('inf')
        self.latency_max = 0.0
        self.recent_latencies = []

        # 时间映射（抗漂移）
        self.wall_to_perf_offset = time.time() - time.perf_counter()
        self.offset_samples = []

        # 状态
        self._running = False
        self._thread = None
        self._frame_count = 0
        self._last_stats_time = time.perf_counter()

        print(f"[FrameReceiver] 初始化完成，监听端口: {listen_port}")
        print(f"[FrameReceiver] 帧尺寸: "
              f"{frame_width}x{frame_height}x{frame_channels}")
        print(f"[ClockSync] 初始 wall→perf offset = "
              f"{self.wall_to_perf_offset * 1000:.2f} ms")

    # --------------------------------------------------

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._thread.start()
        print("[FrameReceiver] 接收线程已启动")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self.sock.close()
        print(f"[FrameReceiver] 已停止，共接收 {self._frame_count} 帧")

    def get_latest_frame(self):
        with self.frame_lock:
            return self.current_frame

    # --------------------------------------------------

    def _receive_loop(self):
        print("[FrameReceiver] 等待画面数据...")

        while self._running:
            try:
                data, _ = self.sock.recvfrom(65535)
                if len(data) < 20:
                    continue

                frame_id, total_packets, packet_idx, _, send_ts_wall = \
                    struct.unpack('<IHHId', data[:20])
                chunk = data[20:]

                if frame_id not in self.packets:
                    self.packets[frame_id] = {
                        'chunks': {},
                        'send_ts_wall': send_ts_wall
                    }

                self.packets[frame_id]['chunks'][packet_idx] = chunk

                if len(self.packets[frame_id]['chunks']) != total_packets:
                    continue

                pkt = self.packets.pop(frame_id)

                perf_now = time.perf_counter()

                full_data = b''.join(
                    pkt['chunks'][i] for i in range(total_packets)
                )

                raw = lz4.frame.decompress(full_data) if self.use_lz4 else full_data

                if len(raw) != self.expected_frame_size:
                    print(f"[FrameReceiver] 帧大小不匹配 "
                          f"(期望 {self.expected_frame_size}, 实际 {len(raw)})")
                    continue

                img = np.frombuffer(raw, dtype=np.uint8).reshape(
                    (self.frame_height, self.frame_width, self.frame_channels)
                )

                with self.frame_lock:
                    self.current_frame = img

                self._frame_count += 1

                send_ts_perf = pkt['send_ts_wall'] - self.wall_to_perf_offset
                latency = (perf_now - send_ts_perf) * 1000.0

                offset_candidate = pkt['send_ts_wall'] - perf_now
                self.offset_samples.append(offset_candidate)
                if len(self.offset_samples) > self.OFFSET_WINDOW:
                    self.offset_samples.pop(0)

                self.wall_to_perf_offset = (
                    (1 - self.OFFSET_ALPHA) * self.wall_to_perf_offset +
                    self.OFFSET_ALPHA * min(self.offset_samples)
                )

                if self.CLAMP_NEGATIVE and latency < 0:
                    latency = 0.0

                self.latency_sum += latency
                self.latency_count += 1
                self.latency_min = min(self.latency_min, latency)
                self.latency_max = max(self.latency_max, latency)

                if self._frame_count % 240 == 0:
                    now = time.perf_counter()
                    fps = 240 / (now - self._last_stats_time)
                    self._last_stats_time = now

                    avg = self.latency_sum / self.latency_count
                    print(f"[FrameReceiver] FPS: {fps:.1f} | "
                          f"延迟: {avg:.2f}ms "
                          f"(min {self.latency_min:.2f}, "
                          f"max {self.latency_max:.2f})")

                    self.latency_sum = 0.0
                    self.latency_count = 0
                    self.latency_min = float('inf')
                    self.latency_max = 0.0

            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    print(f"[FrameReceiver] 错误: {e}")

        self.packets.clear()
