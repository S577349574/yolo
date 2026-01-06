# yolo_detector.py (性能优化终极版)
"""
YOLOv8 检测器 - 性能优化版
- 移除冗余代码
- 消除不必要的计时开销
- 使用 OpenCV NMS 加速
- 预确定输出格式避免重复判断
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
        # ⭐ 直接获取 ConfigManager 中已经确定的路径 ⭐
        from config_manager import ConfigManager
        config_mgr = ConfigManager()
        app_dir = config_mgr.app_dir  # 使用已验证的路径

        trt_cache_dir = os.path.join(app_dir, 'trt_cache')

        try:
            os.makedirs(trt_cache_dir, exist_ok=True)
            test_file = os.path.join(trt_cache_dir, '.write_test')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            utils.log(f"✓ TensorRT 缓存路径: {trt_cache_dir}")
        except (PermissionError, OSError):
            trt_cache_dir = os.path.join(tempfile.gettempdir(), 'onnx_trt_cache')
            os.makedirs(trt_cache_dir, exist_ok=True)
            utils.log(f"⚠️ 使用临时目录: {trt_cache_dir}")

        cache_files = [f for f in os.listdir(trt_cache_dir) if f.endswith(('.engine', '.cache'))]
        if cache_files:
            utils.log(f"✓ 找到 {len(cache_files)} 个 TensorRT 缓存文件")
        else:
            utils.log(f"⚠️ TensorRT 缓存为空，首次运行将编译引擎（约10-30秒）")

        trt_options = {
            'trt_fp16_enable': True,
            'trt_engine_cache_enable': True,
            'trt_engine_cache_path': trt_cache_dir,
            'trt_max_workspace_size': 2147483648,  # 2GB
            'trt_builder_optimization_level': 5,
            'trt_timing_cache_enable': True,
        }
        priority.append(('TensorrtExecutionProvider', trt_options))

    # CUDA
    if 'CUDAExecutionProvider' in available:
        cuda_options = {
            'device_id': 0,
            'arena_extend_strategy': 'kSameAsRequested',
            'cudnn_conv_algo_search': 'EXHAUSTIVE',
            'do_copy_in_default_stream': True,
            'gpu_mem_limit': 2 * 1024 * 1024 * 1024,
        }
        priority.append(('CUDAExecutionProvider', cuda_options))

    if 'DmlExecutionProvider' in available:
        priority.append('DmlExecutionProvider')

    priority.append('CPUExecutionProvider')

    return priority


class YOLOv8Detector:
    """YOLOv8 目标检测器（ONNX Runtime 推理）"""

    def __init__(self):
        model_path = get_config('MODEL_PATH')

        # 验证模型文件
        if not model_path:
            raise ValueError("MODEL_PATH 配置为空")
        if not os.path.isfile(model_path):
            utils.log(f"❌ 模型文件不存在: {model_path}")
            raise FileNotFoundError(f"模型文件未找到: {model_path}")

        self.img_size = get_config('CROP_SIZE', 640)
        utils.log(f"[YOLO] 加载模型: {model_path}")
        utils.log(f"[YOLO] 输入尺寸: {self.img_size}x{self.img_size}")

        # 配置 Session 选项
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.intra_op_num_threads = 4
        sess_options.inter_op_num_threads = 2
        sess_options.enable_mem_pattern = True
        sess_options.enable_cpu_mem_arena = True

        providers = _get_best_providers()

        try:
            self.session = ort.InferenceSession(model_path, sess_options, providers=providers)
        except Exception as e:
            utils.log(f"❌ 加载模型失败: {e}")
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

        # 缓存配置值
        self._conf_threshold = get_config('CONF_THRESHOLD', 0.5)
        self._iou_threshold = get_config('IOU_THRESHOLD', 0.45)
        utils.log(f"[YOLO] 置信度阈值: {self._conf_threshold}, IOU阈值: {self._iou_threshold}")

        # 性能统计开关（生产环境建议关闭）
        self._enable_timing = get_config('YOLO_ENABLE_TIMING', False)
        self._enable_anomaly_detection = get_config('YOLO_ENABLE_ANOMALY_DETECTION', False)

        # 预确定输出格式（避免每次推理时判断）
        self._output_needs_transpose = None
        self._output_needs_squeeze = None

        # 模型预热
        self._warmup()

    def _warmup(self, iterations=10):
        """预热模型，消除首次推理延迟"""
        utils.log("[YOLO] 正在预热模型...")

        dummy_input = np.random.randint(
            50, 200,
            (self.img_size, self.img_size, 3),
            dtype=np.uint8
        )

        warmup_times = []
        for i in range(iterations):
            start = time.perf_counter()

            # 第一次推理时确定输出格式
            if i == 0:
                input_data = self.preprocess(dummy_input)
                outputs = self.session.run(self.output_names, {self.input_name: input_data})
                predictions = outputs[0] if isinstance(outputs, list) else outputs

                # 记住输出格式（避免后续每次判断）
                self._output_needs_squeeze = predictions.ndim == 3
                if self._output_needs_squeeze:
                    predictions = predictions[0]
                self._output_needs_transpose = predictions.shape[0] < predictions.shape[1]

                utils.log(
                    f"[YOLO] 输出格式: squeeze={self._output_needs_squeeze}, transpose={self._output_needs_transpose}")
            else:
                self._predict_internal(dummy_input)

            elapsed = (time.perf_counter() - start) * 1000
            warmup_times.append(elapsed)

            if (i + 1) % 3 == 0 or i == iterations - 1:
                utils.log(f"   预热进度: {i + 1}/{iterations}, 当前耗时: {elapsed:.2f}ms")

        avg_time = sum(warmup_times) / len(warmup_times)
        min_time = min(warmup_times)
        max_time = max(warmup_times)

        utils.log(f"✓ 模型预热完成:")
        utils.log(f"   平均: {avg_time:.2f}ms, 最小: {min_time:.2f}ms, 最大: {max_time:.2f}ms")

        if max_time > 10.0:
            utils.log(f"⚠️ 检测到异常长的推理时间，可能原因:")
            utils.log(f"   1. TensorRT 正在编译引擎（首次运行正常）")
            utils.log(f"   2. GPU 被其他程序占用")
            utils.log(f"   3. 系统后台任务干扰")

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
        预处理图像（使用 OpenCV DNN 优化）

        Args:
            img_bgr: BGR 格式的输入图像 (H, W, 3)

        Returns:
            np.ndarray: 预处理后的张量 (1, 3, H, W)
        """
        blob = cv2.dnn.blobFromImage(
            img_bgr,
            scalefactor=1.0 / 255.0,
            size=(self.img_size, self.img_size),
            swapRB=True,  # BGR -> RGB
            crop=False,
            ddepth=cv2.CV_32F
        )
        return blob

    def postprocess(self, output, conf_threshold, iou_threshold):
        """
        后处理：解析模型输出，过滤低置信度检测，执行按类别分组的NMS

        Args:
            output: 模型原始输出
            conf_threshold: 置信度阈值
            iou_threshold: NMS IOU阈值

        Returns:
            list: 检测结果列表 [{'box': [x1,y1,x2,y2], 'confidence': float, 'class_id': int}, ...]
        """
        predictions = output[0] if isinstance(output, list) else output

        # 使用预先确定的格式（避免每次判断）
        if self._output_needs_squeeze:
            predictions = predictions[0]
        if self._output_needs_transpose:
            predictions = predictions.T

        # 提取 boxes 和 scores
        boxes = predictions[:, :4]
        scores = predictions[:, 4:]

        # 提前过滤低置信度
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

        # ⭐⭐⭐ 关键改进：按类别分组执行 NMS ⭐⭐⭐
        final_results = []
        unique_classes = np.unique(class_ids)

        for class_id in unique_classes:
            # 获取当前类别的所有检测框
            class_mask = class_ids == class_id
            class_boxes = boxes_xyxy[class_mask]
            class_scores = max_scores[class_mask]

            # 对当前类别单独执行 NMS
            class_indices = cv2.dnn.NMSBoxes(
                class_boxes.tolist(),
                class_scores.tolist(),
                conf_threshold,
                iou_threshold
            )

            if len(class_indices) == 0:
                continue

            # 处理 OpenCV 返回的索引格式
            if isinstance(class_indices, np.ndarray):
                class_indices = class_indices.flatten()
            else:
                class_indices = [i[0] if isinstance(i, (list, tuple)) else i
                                 for i in class_indices]

            # 映射回原始索引
            original_indices = np.where(class_mask)[0]

            for local_idx in class_indices:
                global_idx = original_indices[local_idx]
                final_results.append({
                    'box': boxes_xyxy[global_idx].tolist(),
                    'confidence': float(max_scores[global_idx]),
                    'class_id': int(class_id)
                })

        return final_results

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

        # 只在需要时才启用计时（避免不必要的性能开销）
        if self._enable_timing or self._enable_anomaly_detection:
            t_start = time.perf_counter()
            input_data = self.preprocess(img_bgr)
            t_preprocess = time.perf_counter()
            outputs = self.session.run(self.output_names, {self.input_name: input_data})
            t_inference = time.perf_counter()
            results = self.postprocess(outputs, conf, iou)
            t_postprocess = time.perf_counter()

            # 异常检测（可选）
            if self._enable_anomaly_detection:
                inference_time = (t_inference - t_preprocess) * 1000
                if inference_time > 10.0:
                    utils.log(f"⚠️ 异常推理时间: {inference_time:.2f}ms (正常应为2-4ms)")
                    utils.log(f"   预处理: {(t_preprocess - t_start) * 1000:.2f}ms")
                    utils.log(f"   推理: {inference_time:.2f}ms")
                    utils.log(f"   后处理: {(t_postprocess - t_inference) * 1000:.2f}ms")
        else:
            # 快速路径（无计时开销）
            input_data = self.preprocess(img_bgr)
            outputs = self.session.run(self.output_names, {self.input_name: input_data})
            results = self.postprocess(outputs, conf, iou)

        return results

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
