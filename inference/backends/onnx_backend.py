"""ONNX Runtime 后端实现"""
import ast
import os
import tempfile
import time
from typing import List, Dict, Any

import cv2
import numpy as np
import onnxruntime as ort

import utils
from config_manager import get_config
from ..base import BaseDetector
from ..exceptions import ModelLoadError


class ONNXDetector(BaseDetector):
    """ONNX Runtime检测器(支持TensorRT/CUDA/DML/CPU)"""

    def __init__(self, preferred_backend: str = 'auto'):
        """
        Args:
            preferred_backend: 'tensorrt' | 'cuda' | 'dml' | 'cpu' | 'auto'
        """
        self._load_model(preferred_backend)
        self._load_config()
        self._warmup()

    def _load_model(self, preferred_backend: str):
        """加载ONNX模型"""
        model_path = get_config('MODEL_PATH')

        # 路径验证(你原来的逻辑)
        if not model_path or not isinstance(model_path, str):
            raise ModelLoadError("MODEL_PATH 配置为空")

        if not os.path.isfile(model_path):
            raise ModelLoadError(f"模型文件不存在: {model_path}")

        _, ext = os.path.splitext(model_path)
        if ext.lower() != '.onnx':
            utils.log(f"⚠️ 模型扩展名异常: {ext} (预期.onnx)")

        # 配置Session
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.intra_op_num_threads = 4
        sess_options.inter_op_num_threads = 2
        sess_options.enable_mem_pattern = True
        sess_options.enable_cpu_mem_arena = True

        # 选择Providers
        providers = self._get_providers(preferred_backend)

        try:
            self.session = ort.InferenceSession(model_path, sess_options, providers=providers)
        except Exception as e:
            raise ModelLoadError(f"ONNX Runtime 加载失败: {e}")

        self._active_provider = self.session.get_providers()[0]
        utils.log(f"✓ 使用后端: {self._active_provider}")

        # 获取输入输出信息
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]

        # 加载类别名称
        self.names = self._load_names_from_metadata()
        if self.names:
            utils.log(f"[ONNX] 类别数量: {len(self.names)}")

    def _get_providers(self, preferred: str) -> List:
        """获取Provider优先级列表"""
        available = ort.get_available_providers()
        priority = []

        use_tensorrt = get_config('USE_TENSORRT', True)

        # TensorRT
        if use_tensorrt and 'TensorrtExecutionProvider' in available:
            trt_options = self._get_trt_options()
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

        # DML
        if 'DmlExecutionProvider' in available:
            priority.append('DmlExecutionProvider')

        # CPU兜底
        priority.append('CPUExecutionProvider')

        return priority

    def _get_trt_options(self) -> Dict:
        """获取TensorRT配置"""
        from config_manager import ConfigManager
        app_dir = ConfigManager().app_dir

        trt_cache_dir = os.path.join(app_dir, 'trt_cache')
        try:
            os.makedirs(trt_cache_dir, exist_ok=True)
        except:
            trt_cache_dir = os.path.join(tempfile.gettempdir(), 'onnx_trt_cache')
            os.makedirs(trt_cache_dir, exist_ok=True)

        return {
            'trt_fp16_enable': True,
            'trt_engine_cache_enable': True,
            'trt_engine_cache_path': trt_cache_dir,
            'trt_max_workspace_size': 2147483648,
            'trt_builder_optimization_level': 5,
            'trt_timing_cache_enable': True,
        }

    def _load_config(self):
        """加载配置"""
        self.img_size = get_config('CROP_SIZE', 640)
        self._conf_threshold = get_config('CONF_THRESHOLD', 0.5)
        self._iou_threshold = get_config('IOU_THRESHOLD', 0.45)

        # 输出格式标志(首次推理时确定)
        self._output_needs_transpose = None
        self._output_needs_squeeze = None

    def _load_names_from_metadata(self) -> Dict[int, str]:
        """从模型元数据加载类别名称"""
        try:
            metadata = self.session.get_modelmeta().custom_metadata_map or {}
            raw_names = metadata.get('names')
            if raw_names:
                return {int(k): v for k, v in ast.literal_eval(raw_names).items()}
        except Exception as e:
            utils.log(f"[ONNX] 加载类别名称失败: {e}")
        return {}

    def _warmup(self, iterations: int = 10):
        """预热模型"""
        utils.log("[ONNX] 正在预热模型...")

        dummy = np.random.randint(50, 200, (self.img_size, self.img_size, 3), dtype=np.uint8)

        times = []
        for i in range(iterations):
            start = time.perf_counter()

            if i == 0:
                # 首次推理确定输出格式
                input_data = self.preprocess(dummy)
                outputs = self.session.run(self.output_names, {self.input_name: input_data})
                predictions = outputs[0]

                self._output_needs_squeeze = predictions.ndim == 3
                if self._output_needs_squeeze:
                    predictions = predictions[0]
                self._output_needs_transpose = predictions.shape[0] < predictions.shape[1]
            else:
                self.predict(dummy)

            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg = sum(times) / len(times)
        utils.log(f"✓ ONNX预热完成: 平均 {avg:.2f}ms")

    def preprocess(self, img_bgr):
        """预处理"""
        return cv2.dnn.blobFromImage(
            img_bgr,
            scalefactor=1.0 / 255.0,
            size=(self.img_size, self.img_size),
            swapRB=True,
            crop=False,
            ddepth=cv2.CV_32F
        )

    def postprocess(self, output, conf_threshold, iou_threshold) -> List[Dict[str, Any]]:
        """后处理(修复版)"""
        predictions = output[0]

        if self._output_needs_squeeze:
            predictions = predictions[0]
        if self._output_needs_transpose:
            predictions = predictions.T

        boxes = predictions[:, :4]
        scores = predictions[:, 4:]

        max_scores = scores.max(axis=1)
        mask = np.asarray(max_scores > conf_threshold)  # ← 显式转换

        if not mask.any():
            return []

        boxes = boxes[mask]
        scores = scores[mask]
        max_scores = max_scores[mask]
        class_ids = scores.argmax(axis=1)

        boxes_xyxy = self._xywh2xyxy(boxes)

        # 按类别NMS
        final_results = []
        for class_id in np.unique(class_ids):
            class_mask = class_ids == class_id
            class_boxes = boxes_xyxy[class_mask]
            class_scores = max_scores[class_mask]

            indices = cv2.dnn.NMSBoxes(
                class_boxes.tolist(),
                class_scores.tolist(),
                conf_threshold,
                iou_threshold
            )

            if len(indices) == 0:
                continue

            # === 修复：统一处理索引格式 ===
            if isinstance(indices, tuple):
                # OpenCV 4.5.x: tuple of arrays
                indices = [i[0] if isinstance(i, (list, np.ndarray)) else i for i in indices]
            elif isinstance(indices, np.ndarray):
                # OpenCV 4.6+: 可能是二维或一维
                if indices.ndim == 2:
                    indices = indices.flatten()
                # 确保是整数列表
                indices = indices.tolist()

            # 现在 indices 是纯 Python 整数列表
            original_indices = np.where(class_mask)[0]

            for idx in indices:
                final_results.append({
                    'box': boxes_xyxy[original_indices[idx]].tolist(),
                    'confidence': float(max_scores[original_indices[idx]]),
                    'class_id': int(class_id)
                })

        return final_results

    @staticmethod
    def _xywh2xyxy(boxes):
        xy = boxes[:, :2]
        wh = boxes[:, 2:4]
        half_wh = wh * 0.5
        return np.concatenate([xy - half_wh, xy + half_wh], axis=1)

    def predict(self, img_bgr, conf_threshold=None, iou_threshold=None) -> List[Dict[str, Any]]:
        """主推理接口"""
        conf = conf_threshold if conf_threshold is not None else self._conf_threshold
        iou = iou_threshold if iou_threshold is not None else self._iou_threshold

        input_data = self.preprocess(img_bgr)
        outputs = self.session.run(self.output_names, {self.input_name: input_data})
        return self.postprocess(outputs, conf, iou)

    def update_thresholds(self):
        """更新阈值"""
        self._conf_threshold = get_config('CONF_THRESHOLD', 0.5)
        self._iou_threshold = get_config('IOU_THRESHOLD', 0.45)

    def get_class_name(self, class_id: int) -> str:
        return self.names.get(class_id, f"class_{class_id}")

    @property
    def backend_name(self) -> str:
        return f"ONNX-{self._active_provider}"

    def __del__(self):
        try:
            if hasattr(self, 'session'):
                del self.session
        except:
            pass
