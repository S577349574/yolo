# yolo_detector.py (优化版 - 修复版)
"""
YOLOv8 检测器 - 性能优化版
"""
import ast
import os
import tempfile
import time

import cv2
import numpy as np
import onnxruntime as ort

import utils
from config_manager import get_config


def _get_best_providers():
    """根据硬件自动选择最优 Provider"""
    available = ort.get_available_providers()
    priority = []

    use_tensorrt = get_config('USE_TENSORRT', True)

    if use_tensorrt and 'TensorrtExecutionProvider' in available:
        # ⭐ 方案1：使用程序目录（推荐）
        import sys
        if getattr(sys, 'frozen', False):
            # 打包后的 exe
            app_dir = os.path.dirname(sys.executable)
        else:
            # 开发环境
            app_dir = os.path.dirname(os.path.abspath(__file__))

        trt_cache_dir = os.path.join(app_dir, 'trt_cache')
        try:
            os.makedirs(trt_cache_dir, exist_ok=True)
        except PermissionError:
            # 如果程序目录没有写权限，回退到临时目录
            trt_cache_dir = os.path.join(tempfile.gettempdir(), 'onnx_trt_cache')
            os.makedirs(trt_cache_dir, exist_ok=True)
            utils.log(f"[YOLO] 警告：无法写入程序目录，使用临时目录")

        trt_options = {
            'trt_fp16_enable': True,
            'trt_engine_cache_enable': True,
            'trt_engine_cache_path': trt_cache_dir,
            'trt_max_workspace_size': 2147483648,
            'trt_builder_optimization_level': 3,
        }
        priority.append(('TensorrtExecutionProvider', trt_options))
        utils.log(f"✓ TensorRT 缓存路径: {trt_cache_dir}")

    # CUDA
    if 'CUDAExecutionProvider' in available:
        cuda_options = {
            'device_id': 0,
            'arena_extend_strategy': 'kSameAsRequested',
            'cudnn_conv_algo_search': 'EXHAUSTIVE',
            'do_copy_in_default_stream': True,
        }
        priority.append(('CUDAExecutionProvider', cuda_options))

    if 'DmlExecutionProvider' in available:
        priority.append('DmlExecutionProvider')

    priority.append('CPUExecutionProvider')

    utils.log(f"可用 Providers: {available}")
    utils.log(f"选择 Providers: {[p if isinstance(p, str) else p[0] for p in priority]}")

    return priority

class YOLOv8Detector:
    """YOLOv8 目标检测器（ONNX Runtime 推理）"""

    def __init__(self):
        model_path = get_config('MODEL_PATH')

        # 验证模型文件
        if not model_path:
            raise ValueError("MODEL_PATH 配置为空")
        if not os.path.isfile(model_path):
            utils.log(f"模型文件不存在: {model_path}")
            utils.log("请检查 MODEL_PATH 是否正确，或模型文件是否放在正确目录。")
            raise FileNotFoundError(f"模型文件未找到: {model_path}")

        self.img_size = get_config('CROP_SIZE', 640)
        utils.log(f"[YOLO] 加载模型: {model_path}")
        utils.log(f"[YOLO] 输入尺寸: {self.img_size}x{self.img_size}")

        # ⭐ 优化1: 配置 Session 选项
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.intra_op_num_threads = 4  # 根据CPU核心数调整
        sess_options.inter_op_num_threads = 2
        sess_options.enable_mem_pattern = True
        sess_options.enable_cpu_mem_arena = True

        # 可选：启用性能分析
        # sess_options.enable_profiling = True

        providers = _get_best_providers()

        try:
            self.session = ort.InferenceSession(model_path, sess_options, providers=providers)
        except Exception as e:
            utils.log(f"[YOLO] 加载模型失败: {e}")
            raise

        active_provider = self.session.get_providers()[0]
        utils.log(f"✓ 使用 Provider: {active_provider}")

        # 加载类别名称
        self.names = self._load_names_from_metadata()
        if self.names:
            utils.log(f"[YOLO] 类别数量: {len(self.names)}")

        # 获取输入输出信息
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]

        input_shape = self.session.get_inputs()[0].shape
        utils.log(f"[YOLO] 模型输入: {self.input_name} {input_shape}")

        # ⭐ 优化2: 预分配缓冲区（避免每帧重新分配内存）
        self._resize_buffer = np.empty((self.img_size, self.img_size, 3), dtype=np.uint8)
        self._input_buffer = np.empty((1, 3, self.img_size, self.img_size), dtype=np.float32)

        # ⭐ 优化3: 预计算归一化系数
        self._norm_factor = np.float32(1.0 / 255.0)

        # ⭐ 优化4: 缓存配置值（避免每次调用get_config）
        self._conf_threshold = get_config('CONF_THRESHOLD', 0.5)
        self._iou_threshold = get_config('IOU_THRESHOLD', 0.45)
        utils.log(f"[YOLO] 置信度阈值: {self._conf_threshold}, IOU阈值: {self._iou_threshold}")

        # 推理时间统计（可选）
        self._enable_timing = get_config('YOLO_ENABLE_TIMING', False)
        self._timing_stats = {
            'preprocess': [],
            'inference': [],
            'postprocess': []
        }

        # ⭐ 优化5: 模型预热（消除首次推理延迟）
        self._warmup()

    def _warmup(self, iterations=5):
        """预热模型，消除首次推理延迟"""
        utils.log("[YOLO] 正在预热模型...")
        dummy_input = np.random.randint(
            0, 255,
            (self.img_size, self.img_size, 3),
            dtype=np.uint8
        )

        warmup_times = []
        for i in range(iterations):
            start = time.perf_counter()
            self._predict_internal(dummy_input)
            elapsed = (time.perf_counter() - start) * 1000
            warmup_times.append(elapsed)

        avg_time = sum(warmup_times) / len(warmup_times)
        utils.log(f"✓ 模型预热完成，平均推理时间: {avg_time:.2f}ms")

    def _load_names_from_metadata(self):
        """从模型元数据加载类别名称"""
        try:
            metadata = self.session.get_modelmeta().custom_metadata_map or {}
            raw_names = metadata.get('names')
            if raw_names:
                names = {int(k): v for k, v in ast.literal_eval(raw_names).items()}
                return names
        except Exception as e:
            utils.log(f"[YOLO] 警告: 加载类别名称失败 - {e}")
        return {}

    def preprocess(self, img_bgr):
        """
        预处理图像

        Args:
            img_bgr: BGR 格式的输入图像 (H, W, 3)

        Returns:
            np.ndarray: 预处理后的张量 (1, 3, H, W)
        """
        h, w = img_bgr.shape[:2]

        # 只在尺寸不同时才 resize
        if h != self.img_size or w != self.img_size:
            cv2.resize(
                img_bgr,
                (self.img_size, self.img_size),
                dst=self._resize_buffer,
                interpolation=cv2.INTER_LINEAR
            )
            img = self._resize_buffer
        else:
            img = img_bgr

        # 转换为浮点并归一化
        img_float = img.astype(np.float32) * self._norm_factor

        # BGR -> RGB + HWC -> CHW
        # ⭐ 修正注释：
        # BGR 索引: img[:,:,0]=B, img[:,:,1]=G, img[:,:,2]=R
        # RGB 输出: buffer[0,0]=R, buffer[0,1]=G, buffer[0,2]=B
        self._input_buffer[0, 0, :, :] = img_float[:, :, 2]  # R通道（从BGR的索引2获取）
        self._input_buffer[0, 1, :, :] = img_float[:, :, 1]  # G通道（从BGR的索引1获取）
        self._input_buffer[0, 2, :, :] = img_float[:, :, 0]  # B通道（从BGR的索引0获取）

        return self._input_buffer

    def preprocess_cv2_dnn(self, img_bgr):
        """
        备选预处理方案：使用 OpenCV DNN 模块（可能更快）

        Args:
            img_bgr: BGR 格式的输入图像

        Returns:
            np.ndarray: 预处理后的张量
        """
        blob = cv2.dnn.blobFromImage(
            img_bgr,
            scalefactor=1.0 / 255.0,
            size=(self.img_size, self.img_size),
            swapRB=True,  # BGR -> RGB
            crop=False
        )
        return blob.astype(np.float32)

    def postprocess(self, output, conf_threshold, iou_threshold):
        """
        后处理：解析模型输出，过滤低置信度检测，执行NMS

        Args:
            output: 模型原始输出
            conf_threshold: 置信度阈值
            iou_threshold: NMS IOU阈值

        Returns:
            list: 检测结果列表 [{'box': [x1,y1,x2,y2], 'confidence': float, 'class_id': int}, ...]
        """
        predictions = output[0] if isinstance(output, list) else output

        # 处理不同的输出形状
        if predictions.ndim == 3:
            predictions = predictions[0]

        # 判断是否需要转置 [84, 8400] -> [8400, 84]
        if predictions.shape[0] < predictions.shape[1]:
            predictions = predictions.T

        # 提取 boxes 和 scores
        boxes = predictions[:, :4]
        scores = predictions[:, 4:]

        # ⭐ 提前过滤低置信度（减少后续计算量）
        max_scores = scores.max(axis=1)
        mask = max_scores > conf_threshold

        if not mask.any():
            return []

        boxes = boxes[mask]
        scores = scores[mask]
        max_scores = max_scores[mask]
        class_ids = scores.argmax(axis=1)

        # 坐标转换 xywh -> xyxy
        boxes_xyxy = self._xywh2xyxy_vectorized(boxes)

        # NMS
        indices = self._nms_optimized(boxes_xyxy, max_scores, iou_threshold)

        return [
            {
                'box': boxes_xyxy[idx].tolist(),
                'confidence': float(max_scores[idx]),
                'class_id': int(class_ids[idx])
            }
            for idx in indices
        ]

    @staticmethod
    def _xywh2xyxy_vectorized(boxes):
        """
        向量化坐标转换 (中心点+宽高) -> (左上右下)

        Args:
            boxes: (N, 4) 格式为 [cx, cy, w, h]

        Returns:
            np.ndarray: (N, 4) 格式为 [x1, y1, x2, y2]
        """
        xy = boxes[:, :2]
        wh = boxes[:, 2:4]
        half_wh = wh * 0.5
        return np.concatenate([xy - half_wh, xy + half_wh], axis=1)

    @staticmethod
    def _nms_optimized(boxes, scores, iou_threshold):
        """
        优化的 NMS (Non-Maximum Suppression) 实现

        Args:
            boxes: (N, 4) 边界框 [x1, y1, x2, y2]
            scores: (N,) 置信度分数
            iou_threshold: IOU 阈值

        Returns:
            list: 保留的索引列表
        """
        if len(boxes) == 0:
            return []

        x1, y1, x2, y2 = boxes.T
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]

        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)

            if order.size == 1:
                break

            rest = order[1:]

            # 向量化 IOU 计算
            xx1 = np.maximum(x1[i], x1[rest])
            yy1 = np.maximum(y1[i], y1[rest])
            xx2 = np.minimum(x2[i], x2[rest])
            yy2 = np.minimum(y2[i], y2[rest])

            inter = np.maximum(0.0, xx2 - xx1) * np.maximum(0.0, yy2 - yy1)
            iou = inter / (areas[i] + areas[rest] - inter + 1e-6)

            # 保留 IOU 低于阈值的框
            order = rest[iou <= iou_threshold]

        return keep

    def _predict_internal(self, img_bgr):
        """内部预测方法（用于预热）"""
        input_data = self.preprocess(img_bgr)
        return self.session.run(self.output_names, {self.input_name: input_data})

    def predict(self, img_bgr, conf_threshold=None, iou_threshold=None):
        """
        主预测接口

        Args:
            img_bgr: BGR 格式的输入图像
            conf_threshold: 置信度阈值（可选，默认使用配置值）
            iou_threshold: IOU 阈值（可选，默认使用配置值）

        Returns:
            list: 检测结果列表
        """
        conf = conf_threshold if conf_threshold is not None else self._conf_threshold
        iou = iou_threshold if iou_threshold is not None else self._iou_threshold

        if self._enable_timing:
            t0 = time.perf_counter()

        input_data = self.preprocess(img_bgr)

        if self._enable_timing:
            t1 = time.perf_counter()

        outputs = self.session.run(self.output_names, {self.input_name: input_data})

        if self._enable_timing:
            t2 = time.perf_counter()

        results = self.postprocess(outputs, conf, iou)

        if self._enable_timing:
            t3 = time.perf_counter()
            self._timing_stats['preprocess'].append((t1 - t0) * 1000)
            self._timing_stats['inference'].append((t2 - t1) * 1000)
            self._timing_stats['postprocess'].append((t3 - t2) * 1000)

            # 每100帧输出一次统计
            if len(self._timing_stats['inference']) >= 100:
                self._print_timing_stats()
                self._clear_timing_stats()

        return results

    def _print_timing_stats(self):
        """打印时间统计"""

        def avg(lst):
            return sum(lst) / len(lst) if lst else 0

        utils.log(
            f"[YOLO] 时间统计 (ms): "
            f"预处理={avg(self._timing_stats['preprocess']):.2f}, "
            f"推理={avg(self._timing_stats['inference']):.2f}, "
            f"后处理={avg(self._timing_stats['postprocess']):.2f}"
        )

    def _clear_timing_stats(self):
        """清空时间统计"""
        for key in self._timing_stats:
            self._timing_stats[key].clear()

    def update_thresholds(self):
        """配置热更新时调用，刷新阈值"""
        old_conf = self._conf_threshold
        old_iou = self._iou_threshold

        self._conf_threshold = get_config('CONF_THRESHOLD', 0.5)
        self._iou_threshold = get_config('IOU_THRESHOLD', 0.45)

        if old_conf != self._conf_threshold or old_iou != self._iou_threshold:
            utils.log(
                f"[YOLO] 阈值已更新: "
                f"conf={self._conf_threshold}, iou={self._iou_threshold}"
            )

    def get_class_name(self, class_id):
        """
        获取类别名称

        Args:
            class_id: 类别ID

        Returns:
            str: 类别名称
        """
        return self.names.get(class_id, f"class_{class_id}")

    def __del__(self):
        """析构函数，清理资源"""
        try:
            if hasattr(self, 'session'):
                del self.session
        except Exception:
            pass
