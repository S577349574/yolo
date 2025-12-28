"""
画面接收模块（UDP + simplejpeg JPEG解码 + 抗漂移时钟校准 + 延迟测量）
不依赖联网，长期运行不漂移
"""
import socket
import struct
import threading
import time
import simplejpeg  # ✅ 改用 simplejpeg

import utils


class FrameReceiver:
    """画面接收器（simplejpeg 解码 + perf_counter 时间轴 + 在线时间映射校准）"""

    RECENT_LATENCY_MAX = 100
    OFFSET_WINDOW = 60
    OFFSET_ALPHA = 0.02
    CLAMP_NEGATIVE = True
    FRAME_TIMEOUT = 0.1  # 100ms超时

    def __init__(
        self,
        listen_port: int = 27015,
        frame_width: int = 320,
        frame_height: int = 320,
    ):
        self.port = listen_port

        # 帧尺寸配置
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.frame_channels = 3  # RGB固定3通道

        # ✅ simplejpeg 不需要初始化
        print("[FrameReceiver] ✓ simplejpeg JPEG解码已启用")

        # UDP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32 * 1024 * 1024)
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

        # 统计
        self._last_cleanup_time = time.perf_counter()
        self._packet_counts = []
        self._timeout_count = 0
        self._total_packets_received = 0
        self._decode_times = []
        self._jpeg_sizes = []

        print(f"[FrameReceiver] 初始化完成，监听端口: {listen_port}")
        print(f"[FrameReceiver] 帧尺寸: {frame_width}x{frame_height}x{self.frame_channels}")
        print(f"[ClockSync] 初始 wall→perf offset = {self.wall_to_perf_offset * 1000:.2f} ms")

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

    def _cleanup_timeout_frames(self, now: float):
        """清理超时的不完整帧"""
        timeout_frames = []

        for frame_id, pkt in self.packets.items():
            age = now - pkt.get('first_recv_time', now)
            if age > self.FRAME_TIMEOUT:
                timeout_frames.append(frame_id)
                self._timeout_count += 1

                # 统计丢包
                received = len(pkt['chunks'])
                total = pkt.get('total_packets', 0)
                lost = total - received

                if lost > 0:
                    utils.log_debug(
                        f"⚠️ [FrameReceiver] 帧 {frame_id} 超时: "
                        f"丢失 {lost}/{total} 包 ({age*1000:.1f}ms)"
                    )

        for frame_id in timeout_frames:
            del self.packets[frame_id]

    def _receive_loop(self):
        print("[FrameReceiver] 等待画面数据...")

        while self._running:
            try:
                data, _ = self.sock.recvfrom(65535)
                if len(data) < 20:
                    continue

                # 解析包头
                frame_id, total_packets, packet_idx, _, send_ts_wall = \
                    struct.unpack('<IHHId', data[:20])
                chunk = data[20:]

                # 记录首次接收时间和总包数
                if frame_id not in self.packets:
                    self.packets[frame_id] = {
                        'chunks': {},
                        'send_ts_wall': send_ts_wall,
                        'first_recv_time': time.perf_counter(),
                        'total_packets': total_packets
                    }

                self.packets[frame_id]['chunks'][packet_idx] = chunk

                # 定期清理超时帧
                perf_now = time.perf_counter()
                if perf_now - self._last_cleanup_time > 0.1:
                    self._cleanup_timeout_frames(perf_now)
                    self._last_cleanup_time = perf_now

                # 检查是否接收完整
                if len(self.packets[frame_id]['chunks']) != total_packets:
                    continue

                pkt = self.packets.pop(frame_id)

                # 统计包数量
                packets_in_frame = len(pkt['chunks'])
                self._packet_counts.append(packets_in_frame)
                self._total_packets_received += packets_in_frame

                # 组装完整JPEG数据
                full_data = b''.join(
                    pkt['chunks'][i] for i in range(total_packets)
                )

                # 统计JPEG大小
                jpeg_size = len(full_data)
                self._jpeg_sizes.append(jpeg_size)

                # ✅ simplejpeg 解码（BGR格式，转成RGB）
                decode_start = time.perf_counter()
                try:
                    # simplejpeg 返回 BGR，需要转 RGB
                    bgr = simplejpeg.decode_jpeg(full_data, colorspace='BGR')
                    img = bgr

                    decode_end = time.perf_counter()
                    decode_time = (decode_end - decode_start) * 1000
                    self._decode_times.append(decode_time)
                except Exception as e:
                    utils.log_debug(f"[FrameReceiver] JPEG解码失败: {e}")
                    continue

                # 验证尺寸
                if img.shape != (self.frame_height, self.frame_width, 3):
                    utils.log_debug(
                        f"[FrameReceiver] 帧尺寸不匹配 "
                        f"(期望 {self.frame_height}x{self.frame_width}x3, "
                        f"实际 {img.shape})"
                    )
                    continue

                # 更新当前帧
                with self.frame_lock:
                    self.current_frame = img

                self._frame_count += 1

                # 计算延迟（时钟校准）
                send_ts_perf = pkt['send_ts_wall'] - self.wall_to_perf_offset
                latency = (perf_now - send_ts_perf) * 1000.0

                # 更新时钟偏移（抗漂移）
                offset_candidate = pkt['send_ts_wall'] - perf_now
                self.offset_samples.append(offset_candidate)
                if len(self.offset_samples) > self.OFFSET_WINDOW:
                    self.offset_samples.pop(0)

                self.wall_to_perf_offset = (
                    (1 - self.OFFSET_ALPHA) * self.wall_to_perf_offset +
                    self.OFFSET_ALPHA * min(self.offset_samples)
                )

                # 延迟统计
                if self.CLAMP_NEGATIVE and latency < 0:
                    latency = 0.0

                self.latency_sum += latency
                self.latency_count += 1
                self.latency_min = min(self.latency_min, latency)
                self.latency_max = max(self.latency_max, latency)

                # ✅ 增强统计输出
                if self._frame_count % 240 == 0:
                    now = time.perf_counter()
                    fps = 240 / (now - self._last_stats_time)
                    self._last_stats_time = now

                    avg_latency = self.latency_sum / self.latency_count

                    # 包数量统计
                    if self._packet_counts:
                        avg_packets = sum(self._packet_counts) / len(self._packet_counts)
                        min_packets = min(self._packet_counts)
                        max_packets = max(self._packet_counts)
                    else:
                        avg_packets = min_packets = max_packets = 0

                    # JPEG大小统计
                    if self._jpeg_sizes:
                        avg_jpeg_kb = sum(self._jpeg_sizes) / len(self._jpeg_sizes) / 1024
                        min_jpeg_kb = min(self._jpeg_sizes) / 1024
                        max_jpeg_kb = max(self._jpeg_sizes) / 1024
                    else:
                        avg_jpeg_kb = min_jpeg_kb = max_jpeg_kb = 0

                    # 解码时间统计
                    if self._decode_times:
                        avg_decode = sum(self._decode_times) / len(self._decode_times)
                        min_decode = min(self._decode_times)
                        max_decode = max(self._decode_times)
                    else:
                        avg_decode = min_decode = max_decode = 0

                    utils.log_debug(
                        f"[FrameReceiver] FPS: {fps:.1f} | "
                        f"延迟: {avg_latency:.2f}ms ({self.latency_min:.2f}-{self.latency_max:.2f}) | "
                        f"JPEG: {avg_jpeg_kb:.0f}KB ({min_jpeg_kb:.0f}-{max_jpeg_kb:.0f}) | "
                        f"解码: {avg_decode:.2f}ms ({min_decode:.2f}-{max_decode:.2f}) | "
                        f"包数: {avg_packets:.1f} ({min_packets}-{max_packets}) | "
                        f"超时: {self._timeout_count}"
                    )

                    # 重置统计
                    self.latency_sum = 0.0
                    self.latency_count = 0
                    self.latency_min = float('inf')
                    self.latency_max = 0.0
                    self._packet_counts.clear()
                    self._jpeg_sizes.clear()
                    self._decode_times.clear()

            except socket.timeout:
                # 超时时也清理
                perf_now = time.perf_counter()
                if perf_now - self._last_cleanup_time > 0.1:
                    self._cleanup_timeout_frames(perf_now)
                    self._last_cleanup_time = perf_now
                continue
            except Exception as e:
                if self._running:
                    print(f"[FrameReceiver] 错误: {e}")
                    import traceback
                    traceback.print_exc()

        self.packets.clear()
