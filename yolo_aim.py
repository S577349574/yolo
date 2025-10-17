import ast
import ctypes
import math
import queue as thread_queue
import time
from multiprocessing import Process, Queue, Event
from threading import Thread, Event as ThreadEvent

import cv2
import keyboard
import mss
import numpy as np
import onnxruntime as ort
import win32api
import win32file

# =========================================================================
# 1. YOLOv8 模型和屏幕捕获配置
# =========================================================================
MODEL = '320.onnx'
CROP_SIZE = 320
CONF_THRESHOLD = 0.55
IOU_THRESHOLD = 0.45
TARGET_CLASS_NAMES = ['敌人']

# 新增：瞄准偏移配置
AIM_OFFSET_Y = 0.5  # 垂直偏移比例 (0.0=顶部, 0.5=中心, 1.0=底部)
AIM_OFFSET_X = 0.0  # 水平偏移像素 (正值向右，负值向左)


# 新增：自由移动区域配置
FREE_ZONE_RADIUS = 5  # 目标周围±50像素内可自由移动
ENABLE_FREE_ZONE = False  # 是否启用自由区域功能
# =========================================================================
# 2. 鼠标驱动通信相关定义
# =========================================================================
MOUSE_REQUEST = (0x00000022 << 16) | (0 << 14) | (0x666 << 2) | 0x00000000


class KMouseRequest(ctypes.Structure):
    _fields_ = [
        ("x", ctypes.c_long),
        ("y", ctypes.c_long),
        ("button_flags", ctypes.c_ubyte)
    ]


APP_MOUSE_NO_BUTTON = 0x00
APP_MOUSE_LEFT_DOWN = 0x01
APP_MOUSE_LEFT_UP = 0x02
APP_MOUSE_RIGHT_DOWN = 0x04
APP_MOUSE_RIGHT_UP = 0x08
APP_MOUSE_MIDDLE_DOWN = 0x10
APP_MOUSE_MIDDLE_UP = 0x20


def get_button_flag_description(flags):
    if flags == APP_MOUSE_NO_BUTTON: return "无按钮事件"
    desc = []
    if flags & APP_MOUSE_LEFT_DOWN: desc.append("左键按下")
    if flags & APP_MOUSE_LEFT_UP: desc.append("左键抬起")
    if flags & APP_MOUSE_RIGHT_DOWN: desc.append("右键按下")
    if flags & APP_MOUSE_RIGHT_UP: desc.append("右键抬起")
    if flags & APP_MOUSE_MIDDLE_DOWN: desc.append("中键按下")
    if flags & APP_MOUSE_MIDDLE_UP: desc.append("中键抬起")
    if not desc: return "未知标志"
    return " ".join(desc)


# =========================================================================
# 3. 鼠标控制器类（修复版）
# =========================================================================
class MouseController:
    # 游戏模式参数
    GAME_MODE = True  # 设为True启用游戏内相对移动模式
    GAME_DEAD_ZONE = 0  # 目标在中心15像素内不移动
    GAME_DAMPING_FACTOR = 0.85  # 阻尼系数（防止过冲）

    # 通用参数
    MOUSE_ARRIVAL_THRESHOLD = 3
    MOUSE_PROPORTIONAL_FACTOR = 0.15
    MOUSE_MAX_PIXELS_PER_STEP = 10
    DEFAULT_DELAY_MS_PER_STEP = 3

    def __init__(self, device_path=r"\\.\infestation"):
        self.driver_handle = None
        self.device_path = device_path
        self.move_queue = thread_queue.Queue(maxsize=1)
        self.mouse_thread = None
        self.stop_event = ThreadEvent()

        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        OPEN_EXISTING = 3

        try:
            self.driver_handle = win32file.CreateFile(
                self.device_path,
                GENERIC_READ | GENERIC_WRITE,
                0,
                None,
                OPEN_EXISTING,
                0,
                None
            )
            print(f"[MouseController] 成功打开驱动程序 '{self.device_path}'")

            self.mouse_thread = Thread(target=self._mouse_worker)
            self.mouse_thread.daemon = True
            self.mouse_thread.start()
            print("[MouseController] 鼠标控制线程已启动（游戏模式:%s）" % ("开启" if self.GAME_MODE else "关闭"))

        except win32api.error as e:
            print(f"[MouseController] ERROR: 无法打开驱动程序。错误码: {e.winerror}")
            self.close()
            raise

    def _send_mouse_request(self, x, y, button_flags):
        if not self.driver_handle:
            return False

        mouse_req_data = KMouseRequest(x=x, y=y, button_flags=button_flags)
        in_buffer = bytes(mouse_req_data)

        try:
            win32file.DeviceIoControl(self.driver_handle, MOUSE_REQUEST, in_buffer, 0, None)
            return True
        except win32api.error:
            return False
        except Exception as e:
            print(f"[MouseController] _send_mouse_request ERROR: {e}")
            return False

    def _mouse_worker(self):
        print("[MouseController Thread] 线程已启动")
        try:
            while not self.stop_event.is_set():
                try:
                    move_command = self.move_queue.get(timeout=0.01)
                    target_x_screen, target_y_screen, _, delay_ms_per_step, button_flags_at_end = move_command
                    current_delay_ms = delay_ms_per_step if delay_ms_per_step > 0 else self.DEFAULT_DELAY_MS_PER_STEP

                    # ===== 游戏模式：相对移动 =====
                    if self.GAME_MODE:
                        screen_width = win32api.GetSystemMetrics(0)
                        screen_height = win32api.GetSystemMetrics(1)
                        center_x = screen_width // 2
                        center_y = screen_height // 2

                        # 计算相对偏移（应用阻尼系数）
                        offset_x = int((target_x_screen - center_x) * self.GAME_DAMPING_FACTOR)
                        offset_y = int((target_y_screen - center_y) * self.GAME_DAMPING_FACTOR)

                        # 死区检测
                        if abs(offset_x) < self.GAME_DEAD_ZONE and abs(offset_y) < self.GAME_DEAD_ZONE:
                            continue

                        # 分步发送
                        distance = math.sqrt(offset_x ** 2 + offset_y ** 2)
                        steps = max(1, int(distance / self.MOUSE_MAX_PIXELS_PER_STEP))
                        step_x = offset_x / steps
                        step_y = offset_y / steps

                        for i in range(steps):
                            if self.stop_event.is_set():
                                break

                            move_x = round(step_x)
                            move_y = round(step_y)

                            if move_x != 0 or move_y != 0:
                                if not self._send_mouse_request(move_x, move_y, APP_MOUSE_NO_BUTTON):
                                    print("[MouseController] 游戏模式移动失败")
                                    break

                            time.sleep(current_delay_ms / 1000.0)

                        if button_flags_at_end != APP_MOUSE_NO_BUTTON:
                            self._send_mouse_request(0, 0, button_flags_at_end)

                    # ===== 桌面模式：绝对坐标 =====
                    else:
                        while not self.stop_event.is_set():
                            actual_x, actual_y = win32api.GetCursorPos()
                            remaining_dx = target_x_screen - actual_x
                            remaining_dy = target_y_screen - actual_y
                            distance = math.sqrt(remaining_dx ** 2 + remaining_dy ** 2)

                            if distance <= self.MOUSE_ARRIVAL_THRESHOLD:
                                if remaining_dx != 0 or remaining_dy != 0 or button_flags_at_end != APP_MOUSE_NO_BUTTON:
                                    self._send_mouse_request(remaining_dx, remaining_dy, button_flags_at_end)
                                break

                            step_dx = round(remaining_dx * self.MOUSE_PROPORTIONAL_FACTOR)
                            step_dy = round(remaining_dy * self.MOUSE_PROPORTIONAL_FACTOR)

                            if step_dx == 0 and remaining_dx != 0:
                                step_dx = 1 if remaining_dx > 0 else -1
                            if step_dy == 0 and remaining_dy != 0:
                                step_dy = 1 if remaining_dy > 0 else -1

                            current_step_distance = math.sqrt(step_dx ** 2 + step_dy ** 2)
                            if current_step_distance > self.MOUSE_MAX_PIXELS_PER_STEP:
                                scale_factor = self.MOUSE_MAX_PIXELS_PER_STEP / current_step_distance
                                step_dx = round(step_dx * scale_factor)
                                step_dy = round(step_dy * scale_factor)

                            if step_dx != 0 or step_dy != 0:
                                if not self._send_mouse_request(step_dx, step_dy, APP_MOUSE_NO_BUTTON):
                                    break

                            time.sleep(current_delay_ms / 1000.0)

                except thread_queue.Empty:
                    pass
                except Exception as e:
                    print(f"[MouseController Thread] ERROR: {e}")
        finally:
            print("[MouseController Thread] 线程已终止")

    def move_to_absolute(self, target_x_screen, target_y_screen, num_steps=None, delay_ms_per_step=None,
                         button_flags_at_end=APP_MOUSE_NO_BUTTON):
        if not self.driver_handle or not self.mouse_thread or not self.mouse_thread.is_alive():
            return False

        actual_delay_ms = delay_ms_per_step if delay_ms_per_step is not None else self.DEFAULT_DELAY_MS_PER_STEP
        move_command = (target_x_screen, target_y_screen, 0, actual_delay_ms, button_flags_at_end)

        # 清空旧指令
        while not self.move_queue.empty():
            try:
                self.move_queue.get_nowait()
            except thread_queue.Empty:
                pass

        try:
            self.move_queue.put(move_command, block=False)
            return True
        except:
            return False

    def click(self, button=APP_MOUSE_LEFT_DOWN, delay_between_down_up_ms=50):
        if not self.driver_handle:
            return False

        down_flag = 0
        up_flag = 0
        if button == APP_MOUSE_LEFT_DOWN:
            down_flag = APP_MOUSE_LEFT_DOWN
            up_flag = APP_MOUSE_LEFT_UP
        elif button == APP_MOUSE_RIGHT_DOWN:
            down_flag = APP_MOUSE_RIGHT_DOWN
            up_flag = APP_MOUSE_RIGHT_UP
        elif button == APP_MOUSE_MIDDLE_DOWN:
            down_flag = APP_MOUSE_MIDDLE_DOWN
            up_flag = APP_MOUSE_MIDDLE_UP
        else:
            return False

        if not self._send_mouse_request(0, 0, down_flag):
            return False

        time.sleep(delay_between_down_up_ms / 1000.0)

        if not self._send_mouse_request(0, 0, up_flag):
            return False
        return True

    def close(self):
        if self.driver_handle:
            self.stop_event.set()
            if self.mouse_thread and self.mouse_thread.is_alive():
                self.mouse_thread.join(timeout=2.0)
            win32file.CloseHandle(self.driver_handle)
            self.driver_handle = None
            print("[MouseController] 已关闭")


# =========================================================================
# 4. YOLOv8检测器类
# =========================================================================
class YOLOv8Detector:
    def __init__(self, model_path, img_size=320):
        self.img_size = img_size
        providers = ['DmlExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']
        available_providers = ort.get_available_providers()
        active_providers = [p for p in providers if p in available_providers]

        self.session = ort.InferenceSession(model_path, providers=active_providers)
        print(f"✓ 使用Provider: {self.session.get_providers()[0]}")

        self.names = self._load_names_from_metadata()
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]

    def _load_names_from_metadata(self):
        try:
            metadata = self.session.get_modelmeta().custom_metadata_map or {}
            raw_names = metadata.get('names')
            if raw_names:
                return {int(k): v for k, v in ast.literal_eval(raw_names).items()}
        except Exception as e:
            print(f"Warning: {e}")
        return {}

    def preprocess(self, img_bgr):
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        img_resized = cv2.resize(img_rgb, (self.img_size, self.img_size))
        img_norm = img_resized.astype(np.float32) / 255.0
        img_transposed = np.transpose(img_norm, (2, 0, 1))
        return np.expand_dims(img_transposed, axis=0)

    def postprocess(self, output, conf_threshold, iou_threshold):
        predictions = np.squeeze(output[0])
        predictions = np.transpose(predictions)

        boxes = predictions[:, :4]
        scores = predictions[:, 4:]
        class_ids = np.argmax(scores, axis=1)
        confidences = np.max(scores, axis=1)

        mask = confidences > conf_threshold
        boxes = boxes[mask]
        confidences = confidences[mask]
        class_ids = class_ids[mask]

        if len(boxes) == 0:
            return []

        boxes_xyxy = self._xywh2xyxy(boxes)
        indices = self._nms(boxes_xyxy, confidences, iou_threshold)

        return [{
            'box': boxes_xyxy[idx],
            'confidence': confidences[idx],
            'class_id': class_ids[idx]
        } for idx in indices]

    def _xywh2xyxy(self, boxes):
        boxes_xyxy = np.copy(boxes)
        boxes_xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
        boxes_xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2
        boxes_xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2
        boxes_xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2
        return boxes_xyxy

    def _nms(self, boxes, scores, iou_threshold):
        x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]

        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)

            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])

            w = np.maximum(0.0, xx2 - xx1)
            h = np.maximum(0.0, yy2 - yy1)
            inter = w * h

            iou = inter / (areas[i] + areas[order[1:]] - inter)
            inds = np.where(iou <= iou_threshold)[0]
            order = order[inds + 1]

        return keep

    def predict(self, img_bgr, conf_threshold=0.25, iou_threshold=0.45):
        input_data = self.preprocess(img_bgr)
        outputs = self.session.run(self.output_names, {self.input_name: input_data})
        return self.postprocess(outputs[0], conf_threshold, iou_threshold)


# =========================================================================
# 5. 屏幕捕获进程
# =========================================================================
def capture_screen(frame_queue, capture_ready_event, crop_size):
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            center_x = monitor['width'] // 2
            center_y = monitor['height'] // 2

            crop_area = {
                'left': center_x - crop_size // 2,
                'top': center_y - crop_size // 2,
                'width': crop_size,
                'height': crop_size
            }

            print(f"捕获区域: {crop_area}")
            capture_ready_event.set()

            while True:
                img = np.array(sct.grab(crop_area))
                if not frame_queue.full():
                    frame_queue.put(img)
                time.sleep(0.001)
    except Exception as e:
        print(f"捕获进程错误: {e}")


# =========================================================================
# 6. 主逻辑
# =========================================================================
def main_detection_and_control():
    # 加载模型
    try:
        model = YOLOv8Detector(MODEL, img_size=CROP_SIZE)
    except Exception as e:
        print(f"模型加载失败: {e}")
        return

    target_class_ids = [k for k, v in model.names.items() if v in TARGET_CLASS_NAMES] if TARGET_CLASS_NAMES else []

    # 初始化鼠标控制器
    try:
        mouse_controller = MouseController()
    except Exception as e:
        print(f"鼠标控制器初始化失败: {e}")
        return

    # 启动捕获进程
    frame_queue = Queue(maxsize=5)
    capture_ready_event = Event()
    capture_process = Process(target=capture_screen, args=(frame_queue, capture_ready_event, CROP_SIZE))
    capture_process.start()

    capture_ready_event.wait(timeout=10)
    if not capture_ready_event.is_set():
        print("捕获进程未就绪")
        capture_process.terminate()
        capture_process.join()
        mouse_controller.close()
        return

    # 获取屏幕信息
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        screen_width = monitor['width']
        screen_height = monitor['height']
        center_x = screen_width // 2
        center_y = screen_height // 2

        capture_area = {
            'left': center_x - CROP_SIZE // 2,
            'top': center_y - CROP_SIZE // 2,
            'width': CROP_SIZE,
            'height': CROP_SIZE
        }

    # 跟踪变量
    mouse_control_active = True
    last_target_x = None
    last_target_y = None
    frames_without_target = 0
    MAX_LOST_FRAMES = 30
    DISTANCE_WEIGHT = 0.75

    # 新增：指令更新控制
    last_command_x = None
    last_command_y = None
    COMMAND_UPDATE_THRESHOLD = 15

    # 键盘热键
    should_exit = [False]

    def toggle_pause():
        nonlocal mouse_control_active
        mouse_control_active = False
        print("已暂停")

    def toggle_resume():
        nonlocal mouse_control_active
        mouse_control_active = True
        print("已恢复")

    def exit_program():
        should_exit[0] = True

    keyboard.add_hotkey('w', toggle_pause)
    keyboard.add_hotkey('e', toggle_resume)
    keyboard.add_hotkey('q', exit_program)

    try:
        frame_count = 0
        fps_start_time = time.time()

        while not should_exit[0]:
            try:
                img_bgra = frame_queue.get(block=False)
            except thread_queue.Empty:
                time.sleep(0.001)
                continue

            img_bgr = cv2.cvtColor(img_bgra, cv2.COLOR_BGRA2BGR)
            results = model.predict(img_bgr, conf_threshold=CONF_THRESHOLD, iou_threshold=IOU_THRESHOLD)

            best_target_screen_x = None
            best_target_screen_y = None
            best_score = -1.0
            detected_classes = set()
            detected_confidences = []
            candidate_targets = []

            for result in results:
                box = result['box']
                conf = result['confidence']
                cid = result['class_id']

                obj_name = model.names.get(cid, str(cid))
                detected_classes.add(obj_name)
                detected_confidences.append(conf)

                is_target_class = (not target_class_ids) or (cid in target_class_ids)

                if is_target_class:
                    x1, y1, x2, y2 = map(int, box)
                    box_width = x2 - x1
                    box_height = y2 - y1

                    # 根据检测框大小动态调整（目标越大越瞄上方）
                    if box_height > 150:  # 近距离大目标
                        aim_y_ratio = 0.40  # 瞄头部
                    elif box_height > 80:  # 中距离
                        aim_y_ratio = 0.40  # 瞄颈部
                    else:  # 远距离小目标
                        aim_y_ratio = 0.40  # 瞄中心（容错率高）

                    center_x_cropped = int(x1 + box_width * 0.5)
                    center_y_cropped = int(y1 + box_height * aim_y_ratio)

                    target_screen_x = capture_area['left'] + center_x_cropped
                    target_screen_y = capture_area['top'] + center_y_cropped

                    candidate_targets.append({
                        'x': target_screen_x,
                        'y': target_screen_y,
                        'confidence': conf
                    })

            # 选择最佳目标
            if candidate_targets:
                if last_target_x is not None and frames_without_target < MAX_LOST_FRAMES:
                    max_distance = math.sqrt(screen_width ** 2 + screen_height ** 2)

                    for target in candidate_targets:
                        distance = math.sqrt(
                            (target['x'] - last_target_x) ** 2 +
                            (target['y'] - last_target_y) ** 2
                        )
                        normalized_distance = distance / max_distance
                        distance_score = 1 - normalized_distance
                        conf_score = target['confidence']
                        composite_score = (DISTANCE_WEIGHT * distance_score +
                                           (1 - DISTANCE_WEIGHT) * conf_score)

                        if composite_score > best_score:
                            best_score = composite_score
                            best_target_screen_x = target['x']
                            best_target_screen_y = target['y']
                else:
                    best_target = max(candidate_targets, key=lambda t: t['confidence'])
                    best_target_screen_x = best_target['x']
                    best_target_screen_y = best_target['y']

                last_target_x = best_target_screen_x
                last_target_y = best_target_screen_y
                frames_without_target = 0
            else:
                frames_without_target += 1
                if frames_without_target >= MAX_LOST_FRAMES:
                    last_target_x = None
                    last_target_y = None

            # 鼠标控制（新增自由区域判断）
            if mouse_control_active and best_target_screen_x is not None:
                # 获取当前鼠标位置
                current_mouse_x, current_mouse_y = win32api.GetCursorPos()

                # 计算鼠标与目标的距离
                distance_to_target = math.sqrt(
                    (current_mouse_x - best_target_screen_x) ** 2 +
                    (current_mouse_y - best_target_screen_y) ** 2
                )

                # 判断是否需要驱动鼠标
                should_send_command = False

                if ENABLE_FREE_ZONE:
                    # 只有超出自由区域才驱动
                    if distance_to_target > FREE_ZONE_RADIUS:
                        should_send_command = True
                else:
                    # 原逻辑：基于指令距离判断
                    if last_command_x is not None:
                        command_distance = math.sqrt(
                            (best_target_screen_x - last_command_x) ** 2 +
                            (best_target_screen_y - last_command_y) ** 2
                        )
                        if command_distance >= COMMAND_UPDATE_THRESHOLD:
                            should_send_command = True
                    else:
                        should_send_command = True

                if should_send_command:
                    mouse_controller.move_to_absolute(
                        best_target_screen_x,
                        best_target_screen_y
                    )
                    last_command_x = best_target_screen_x
                    last_command_y = best_target_screen_y

            # FPS显示
            frame_count += 1
            if time.time() - fps_start_time >= 1.0:
                fps = frame_count / (time.time() - fps_start_time)

                if detected_confidences:
                    avg_conf = sum(detected_confidences) / len(detected_confidences)
                    max_conf = max(detected_confidences)
                    conf_info = f"置信度: {avg_conf:.2f}(avg) {max_conf:.2f}(max)"
                else:
                    conf_info = "置信度: N/A"

                classes_info = f"类别: {list(detected_classes)}" if detected_classes else "类别: []"
                tracking_info = f"跟踪: {'激活' if last_target_x is not None else '未锁定'}"

                print(f"FPS: {fps:.2f} | {conf_info} | {classes_info} | 检测数: {len(results)} | {tracking_info}")

                frame_count = 0
                fps_start_time = time.time()

    except KeyboardInterrupt:
        print("用户中断")
    except Exception as e:
        print(f"主循环错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        keyboard.unhook_all()
        capture_process.terminate()
        capture_process.join()
        mouse_controller.close()
        print("程序已退出")


if __name__ == "__main__":
    main_detection_and_control()
