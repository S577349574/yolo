import socket
import struct
import threading
import time
import simplejpeg


class FrameReceiver:
    """画面接收器：simplejpeg 解码 + 抗漂移时钟校准"""
    FRAME_TIMEOUT = 0.1

    def __init__(self, listen_port: int = 27015, frame_width: int = 320, frame_height: int = 320):
        self.port = listen_port
        self.frame_width = frame_width
        self.frame_height = frame_height

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 32 * 1024 * 1024)
        self.sock.bind(("0.0.0.0", listen_port))
        self.sock.settimeout(0.1)

        self.packets = {}
        self.current_frame = None
        self.frame_lock = threading.Lock()

        # 抗漂移时钟映射
        self.wall_to_perf_offset = time.time() - time.perf_counter()
        self.offset_samples = []
        self.OFFSET_WINDOW = 60
        self.OFFSET_ALPHA = 0.02

        # 统计数据
        self._frame_count = 0
        self.latency_sum = 0.0
        self.latency_count = 0
        self.latency_min = float('inf')
        self.latency_max = 0.0

        self._running = False
        self._thread = None

    def start(self):
        if self._running: return
        self._running = True
        self._thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._thread.start()

    def get_latest_frame(self):
        with self.frame_lock:
            return self.current_frame

    def _receive_loop(self):
        while self._running:
            try:
                data, _ = self.sock.recvfrom(65535)
                if len(data) < 20: continue

                # 1. 解析包头 (完全匹配 agent 发送端的 struct.pack)
                frame_id, total_packets, packet_idx, _, send_ts_wall = struct.unpack('<IHHId', data[:20])
                chunk = data[20:]

                if frame_id not in self.packets:
                    self.packets[frame_id] = {
                        'chunks': {},
                        'send_ts_wall': send_ts_wall,
                        'first_recv_time': time.perf_counter(),
                        'total_packets': total_packets
                    }

                self.packets[frame_id]['chunks'][packet_idx] = chunk

                # 2. 检查是否组包完成
                if len(self.packets[frame_id]['chunks']) == total_packets:
                    pkt = self.packets.pop(frame_id)
                    full_data = b''.join(pkt['chunks'][i] for i in range(total_packets))

                    # 3. simplejpeg 解码
                    try:
                        img = simplejpeg.decode_jpeg(full_data, colorspace='BGR')

                        # 时钟校准与延迟计算
                        perf_now = time.perf_counter()
                        send_ts_perf = pkt['send_ts_wall'] - self.wall_to_perf_offset
                        latency = (perf_now - send_ts_perf) * 1000.0

                        # 更新偏移量 (抗漂移)
                        self.offset_samples.append(pkt['send_ts_wall'] - perf_now)
                        if len(self.offset_samples) > self.OFFSET_WINDOW: self.offset_samples.pop(0)
                        self.wall_to_perf_offset = ((1 - self.OFFSET_ALPHA) * self.wall_to_perf_offset +
                                                    self.OFFSET_ALPHA * min(self.offset_samples))

                        with self.frame_lock:
                            self.current_frame = img

                        self._frame_count += 1
                        self._update_stats(latency)

                    except Exception as e:
                        print(f"Decode Error: {e}")

            except socket.timeout:
                continue
            except Exception as e:
                print(f"Receiver Error: {e}")

    def _update_stats(self, latency):
        self.latency_sum += max(0, latency)
        self.latency_count += 1
        self.latency_min = min(self.latency_min, latency)
        self.latency_max = max(self.latency_max, latency)

    def stop(self):
        self._running = False
        self.sock.close()
