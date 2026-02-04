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

        # 路径验证
        if not model_path or not isinstance(model_path, str):
            raise ModelLoadError("MODEL_PATH 配置为空")

        if not os.path.isfile(model_path):
            raise ModelLoadError(f"模型文件不存在: {model_path}")

        _, ext = os.path.splitext(model_path)
        if ext.lower() != '.onnx':
            utils.log(f"模型扩展名异常: {ext} (预期.onnx)")

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
        utils.log(f"使用后端: {self._active_provider}")

        # 获取输入输出信息
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]

        # 加载类别名称
        self.names = self._load_names_from_metadata()
        if self.names:
            utils.log(f"[ONNX] 类别数量: {len(self.names)}")

        # ✅ 从配置获取模型类型
        self.model_type = self._get_model_type()

    def _get_providers(self, preferred: str = 'auto') -> List:
        """获取Provider优先级列表（修复版：尊重preferred_backend并添加调试日志）"""
        available = ort.get_available_providers()
        utils.log(f"[ONNX] 系统可用 providers: {available}")

        priority = []
        use_tensorrt = get_config('USE_TENSORRT', True)

        # 推荐的 TRT 和 CUDA 配置
        trt_options = self._get_trt_options()
        cuda_options = {
            'device_id': 0,
            'arena_extend_strategy': 'kSameAsRequested',
            'cudnn_conv_algo_search': 'EXHAUSTIVE',
            'do_copy_in_default_stream': True,
            'gpu_mem_limit': 2 * 1024 * 1024 * 1024,
        }

        preferred = preferred.lower() if preferred else 'auto'

        # === 根据 preferred_backend 构建优先级 ===
        if preferred == 'tensorrt':
            if 'TensorrtExecutionProvider' in available and use_tensorrt:
                priority.append(('TensorrtExecutionProvider', trt_options))
            else:
                utils.log("请求 TensorRT 但不可用，将 fallback 到其他后端")

        elif preferred == 'cuda':
            if 'CUDAExecutionProvider' in available:
                priority.append(('CUDAExecutionProvider', cuda_options))
            else:
                utils.log("请求 CUDA 但不可用，将 fallback 到 CPU")

        elif preferred == 'dml':
            if 'DmlExecutionProvider' in available:
                priority.append('DmlExecutionProvider')
            else:
                utils.log("请求 DML 但不可用，将 fallback 到 CPU")

        elif preferred == 'cpu':
            priority.append('CPUExecutionProvider')
            utils.log("[ONNX] 强制使用 CPU 后端")
            utils.log(f"[ONNX] 最终 providers 优先级: {[p[0] if isinstance(p, tuple) else p for p in priority]}")
            return priority

        # === 添加剩余可用后端（避免重复）===
        if 'TensorrtExecutionProvider' in available and use_tensorrt:
            if not any(isinstance(p, tuple) and p[0] == 'TensorrtExecutionProvider' for p in priority):
                priority.append(('TensorrtExecutionProvider', trt_options))

        if 'CUDAExecutionProvider' in available:
            if not any(isinstance(p, tuple) and p[0] == 'CUDAExecutionProvider' for p in priority):
                priority.append(('CUDAExecutionProvider', cuda_options))

        if 'DmlExecutionProvider' in available:
            if not any(isinstance(p, str) and p == 'DmlExecutionProvider' for p in priority):
                priority.append('DmlExecutionProvider')

        # CPU 永远作为兜底（除非强制 cpu 且只返回 cpu）
        if 'CPUExecutionProvider' not in [p[0] if isinstance(p, tuple) else p for p in priority]:
            priority.append('CPUExecutionProvider')

        utils.log(f"[ONNX] 最终 providers 优先级: {[p[0] if isinstance(p, tuple) else p for p in priority]}")
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
        self.img_size = self._detect_input_size()
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

    def _get_model_type(self) -> str:
        """
        从配置获取模型类型

        Returns:
            'v5' | 'v8' | 'v10' | 'v11'
        """
        model_type = get_config('MODEL_TYPE', 'v8').lower()

        # 验证配置值
        valid_types = ['v5', 'v8', 'v10', 'v11']
        if model_type not in valid_types:
            utils.log(f"无效的 MODEL_TYPE: '{model_type}'，使用默认值 'v8'")
            utils.log(f"   有效值: {', '.join(valid_types)}")
            return 'v8'

        utils.log(f"[ONNX] 模型类型: YOLO{model_type}")
        return model_type

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

                # 输出调试信息
                utils.log(f"[DEBUG] 输出形状: {predictions.shape}")
            else:
                self.predict(dummy)

            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg = sum(times) / len(times)
        utils.log(f"ONNX预热完成: 平均 {avg:.2f}ms")

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
        """后处理（支持YOLOv5/v8/v10/v11）"""
        predictions = output[0]

        if self._output_needs_squeeze:
            predictions = predictions[0]
        if self._output_needs_transpose:
            predictions = predictions.T

        boxes = predictions[:, :4]

        # ✅ 根据模型类型处理分数
        if self.model_type == 'v5':
            objectness = predictions[:, 4:5]
            class_scores = predictions[:, 5:]
            scores = objectness * class_scores  # objectness * class_score
        else:
            # YOLOv8/v10/v11: [x,y,w,h, class1, class2, ...]
            scores = predictions[:, 4:]

        max_scores = scores.max(axis=1)
        mask = np.asarray(max_scores > conf_threshold)

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

            # 统一处理索引格式
            if isinstance(indices, tuple):
                # OpenCV 4.5.x: tuple of arrays
                indices = [i[0] if isinstance(i, (list, np.ndarray)) else i for i in indices]
            elif isinstance(indices, np.ndarray):
                # OpenCV 4.6+: 可能是二维或一维
                if indices.ndim == 2:
                    indices = indices.flatten()
                indices = indices.tolist()

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
        """中心点格式转左上右下格式"""
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

    def _detect_input_size(self) -> int:
        """
        从模型输入形状自动检测图像尺寸

        Returns:
            int: 输入尺寸（如 640）
        """
        try:
            # 获取模型输入形状
            input_shape = self.session.get_inputs()[0].shape

            # 常见格式: [batch, channels, height, width] 或 [batch, height, width, channels]
            # ONNX 通常是 NCHW: [1, 3, 640, 640]
            if len(input_shape) == 4:
                # 假设是 NCHW 格式
                if input_shape[1] == 3:  # channels = 3
                    height, width = input_shape[2], input_shape[3]
                # 或者是 NHWC 格式
                elif input_shape[3] == 3:
                    height, width = input_shape[1], input_shape[2]
                else:
                    raise ValueError(f"无法识别的输入形状: {input_shape}")

                # 验证是否为正方形输入
                if height != width:
                    utils.log(f"模型输入非正方形: {height}x{width}，使用较小值")
                    size = min(height, width)
                else:
                    size = height

                utils.log(f"[ONNX] 从模型自动检测输入尺寸: {size}x{size}")
                return int(size)

        except Exception as e:
            utils.log(f"自动检测输入尺寸失败: {e}")

    def update_thresholds(self):
        """更新阈值"""
        self._conf_threshold = get_config('CONF_THRESHOLD', 0.5)
        self._iou_threshold = get_config('IOU_THRESHOLD', 0.45)

    def get_class_name(self, class_id: int) -> str:
        """获取类别名称"""
        return self.names.get(class_id, f"class_{class_id}")

    @property
    def backend_name(self) -> str:
        """获取后端名称"""
        return f"ONNX-{self._active_provider}"

    def __del__(self):
        """清理资源"""
        try:
            if hasattr(self, 'session'):
                del self.session
        except:
            pass
