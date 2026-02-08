# onnx_backend.py
"""ONNX Runtime 后端实现（精简日志版）"""
import ast
import os
import tempfile
import time
from typing import List, Dict, Any, Optional

import cv2
import numpy as np
import onnxruntime as ort

import utils
from config_manager import get_config
from ..base import BaseDetector
from ..exceptions import ModelLoadError
from .pv_crypto import decrypt_pv_file, PVDecryptError


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

    # -----------------------------
    # Model loading
    # -----------------------------
    def _load_model(self, preferred_backend: str):
        """加载ONNX模型"""
        model_path = get_config('MODEL_PATH')

        if not model_path or not isinstance(model_path, str):
            raise ModelLoadError("MODEL_PATH 配置为空")
        if not os.path.isfile(model_path):
            raise ModelLoadError(f"模型文件不存在: {model_path}")

        _, ext = os.path.splitext(model_path)
        if ext.lower() not in ('.onnx', '.pv'):
            raise ModelLoadError(f"不支持的模型格式: {ext} (仅支持 .onnx / .pv)")

        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        sess_options.intra_op_num_threads = 4
        sess_options.inter_op_num_threads = 2
        sess_options.enable_mem_pattern = True
        sess_options.enable_cpu_mem_arena = True

        providers = self._get_providers(preferred_backend)

        try:
            if model_path.lower().endswith(".pv"):
                utils.log("[ONNX] 检测到 PV 加密模型，正在解密到内存")
                card_key = get_config("LICENSE_KEY", None)
                if not card_key:
                    raise ModelLoadError("未配置 LICENSE_KEY，无法解密 PV 模型")
                model_bytes = decrypt_pv_file(model_path, card_key)
                self.session = ort.InferenceSession(model_bytes, sess_options, providers=providers)
            else:
                self.session = ort.InferenceSession(model_path, sess_options, providers=providers)
        except PVDecryptError as e:
            raise ModelLoadError(f"PV 模型解密失败: {e}")
        except Exception as e:
            raise ModelLoadError(f"ONNX Runtime 加载失败: {e}")

        self._active_provider = self.session.get_providers()[0]
        utils.log(f"[ONNX] ✓ 推理后端加载成功: ONNX-{self._active_provider}")

        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]

        # 类别名称
        self.names = self._load_names_from_metadata()
        if self.names:
            utils.log(f"[ONNX] 类别数量: {len(self.names)}")

        # 模型类型
        self.model_type = self._get_model_type()

    def _get_providers(self, preferred: str = 'auto') -> List:
        """获取Provider优先级列表（尊重preferred_backend）"""
        available = ort.get_available_providers()

        priority = []
        use_tensorrt = get_config('USE_TENSORRT', True)

        trt_options = self._get_trt_options()
        cuda_options = {
            'device_id': 0,
            'arena_extend_strategy': 'kSameAsRequested',
            'cudnn_conv_algo_search': 'EXHAUSTIVE',
            'do_copy_in_default_stream': True,
            'gpu_mem_limit': 2 * 1024 * 1024 * 1024,
        }

        preferred = preferred.lower() if preferred else 'auto'

        if preferred == 'tensorrt':
            if 'TensorrtExecutionProvider' in available and use_tensorrt:
                priority.append(('TensorrtExecutionProvider', trt_options))
            else:
                utils.log("[ONNX] 请求 TensorRT 但不可用，将 fallback")

        elif preferred == 'cuda':
            if 'CUDAExecutionProvider' in available:
                priority.append(('CUDAExecutionProvider', cuda_options))
            else:
                utils.log("[ONNX] 请求 CUDA 但不可用，将 fallback")

        elif preferred == 'dml':
            if 'DmlExecutionProvider' in available:
                priority.append('DmlExecutionProvider')
            else:
                utils.log("[ONNX] 请求 DML 但不可用，将 fallback")

        elif preferred == 'cpu':
            priority.append('CPUExecutionProvider')
            utils.log("[ONNX] 强制使用 CPU 后端")
            return priority

        # 追加剩余可用后端（避免重复）
        if 'TensorrtExecutionProvider' in available and use_tensorrt:
            if not any(isinstance(p, tuple) and p[0] == 'TensorrtExecutionProvider' for p in priority):
                priority.append(('TensorrtExecutionProvider', trt_options))
        if 'CUDAExecutionProvider' in available:
            if not any(isinstance(p, tuple) and p[0] == 'CUDAExecutionProvider' for p in priority):
                priority.append(('CUDAExecutionProvider', cuda_options))
        if 'DmlExecutionProvider' in available:
            if not any(isinstance(p, str) and p == 'DmlExecutionProvider' for p in priority):
                priority.append('DmlExecutionProvider')

        if 'CPUExecutionProvider' not in [p[0] if isinstance(p, tuple) else p for p in priority]:
            priority.append('CPUExecutionProvider')

        return priority

    def _get_trt_options(self) -> Dict:
        """获取TensorRT配置"""
        from config_manager import ConfigManager
        app_dir = ConfigManager().app_dir

        trt_cache_dir = os.path.join(app_dir, 'trt_cache')
        try:
            os.makedirs(trt_cache_dir, exist_ok=True)
        except Exception:
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

    # -----------------------------
    # Config
    # -----------------------------
    def _load_config(self):
        """加载配置"""
        self.img_size = self._detect_input_size()
        if not self.img_size:
            self.img_size = int(get_config('IMG_SIZE', 640))

        self._conf_threshold = float(get_config('CONF_THRESHOLD', 0.5))
        self._iou_threshold = float(get_config('IOU_THRESHOLD', 0.45))

        # v26 默认端到端
        self._end2end = get_config('END2END', True if self.model_type == 'v26' else False)

        # 输出格式标志(首次推理时确定)
        self._output_needs_transpose = None
        self._output_needs_squeeze = None

        # v26 box format cache（避免每帧都猜）
        self._v26_box_format: Optional[str] = None  # 'xyxy' | 'cxcywh' | 'tlwh'

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
            'v5' | 'v8' | 'v10' | 'v11' | 'v26'
        """
        model_type = str(get_config('MODEL_TYPE', 'v8')).lower()
        valid_types = ['v5', 'v8', 'v10', 'v11', 'v26']
        if model_type not in valid_types:
            utils.log(f"[ONNX] 无效 MODEL_TYPE: '{model_type}'，使用默认 'v8'")
            return 'v8'
        utils.log(f"[ONNX] 模型类型: YOLO{model_type.upper()}")
        return model_type

    # -----------------------------
    # Warmup
    # -----------------------------
    def _warmup(self, iterations: int = 10):
        """预热模型"""
        dummy = np.random.randint(50, 200, (self.img_size, self.img_size, 3), dtype=np.uint8)

        times = []
        for i in range(iterations):
            start = time.perf_counter()

            if i == 0:
                input_data = self.preprocess(dummy)
                outputs = self.session.run(self.output_names, {self.input_name: input_data})
                predictions = outputs[0]

                # 初始化 squeeze/transpose 规则
                self._output_needs_squeeze = predictions.ndim == 3
                if self._output_needs_squeeze:
                    predictions = predictions[0]

                # 兼容 (C,N) vs (N,C)
                self._output_needs_transpose = predictions.shape[0] < predictions.shape[1]

                # v26 e2e：预热时猜一次 box format（只会打印一次）
                if self.model_type == 'v26' and self._end2end and predictions.ndim == 2 and predictions.shape[1] == 6:
                    _ = self._v26_decode_boxes(predictions[:, :4].copy())

            else:
                self.predict(dummy)

            times.append((time.perf_counter() - start) * 1000)

        avg = sum(times) / len(times)
        utils.log(f"[ONNX] 预热完成: 平均 {avg:.2f}ms")

    # -----------------------------
    # Preprocess
    # -----------------------------
    def preprocess(self, img_bgr):
        """预处理"""
        blob = cv2.dnn.blobFromImage(
            img_bgr,
            scalefactor=1.0 / 255.0,
            size=(self.img_size, self.img_size),
            swapRB=True,
            crop=False,
            ddepth=cv2.CV_32F
        )
        return blob

    # -----------------------------
    # Postprocess helpers
    # -----------------------------
    @staticmethod
    def _xywh2xyxy_from_center(boxes_cxcywh: np.ndarray) -> np.ndarray:
        """cxcywh(中心点) -> xyxy"""
        xy = boxes_cxcywh[:, :2]
        wh = boxes_cxcywh[:, 2:4]
        half_wh = wh * 0.5
        return np.concatenate([xy - half_wh, xy + half_wh], axis=1)

    @staticmethod
    def _tlwh2xyxy(boxes_tlwh: np.ndarray) -> np.ndarray:
        """tlwh(左上+宽高) -> xyxy"""
        x1 = boxes_tlwh[:, 0]
        y1 = boxes_tlwh[:, 1]
        x2 = x1 + boxes_tlwh[:, 2]
        y2 = y1 + boxes_tlwh[:, 3]
        return np.stack([x1, y1, x2, y2], axis=1)

    @staticmethod
    def _sanitize_xyxy(
        boxes_xyxy: np.ndarray,
        w: int,
        h: int,
        min_size: float = 2.0
    ) -> np.ndarray:
        """修正顺序 + clip + 过滤无效框（返回过滤后的 boxes）"""
        if boxes_xyxy.size == 0:
            return boxes_xyxy

        x1 = np.minimum(boxes_xyxy[:, 0], boxes_xyxy[:, 2])
        y1 = np.minimum(boxes_xyxy[:, 1], boxes_xyxy[:, 3])
        x2 = np.maximum(boxes_xyxy[:, 0], boxes_xyxy[:, 2])
        y2 = np.maximum(boxes_xyxy[:, 1], boxes_xyxy[:, 3])

        x1 = np.clip(x1, 0, w - 1)
        y1 = np.clip(y1, 0, h - 1)
        x2 = np.clip(x2, 0, w - 1)
        y2 = np.clip(y2, 0, h - 1)

        ww = x2 - x1
        hh = y2 - y1
        keep = (ww >= min_size) & (hh >= min_size)

        return np.stack([x1, y1, x2, y2], axis=1)[keep]

    def _v26_pick_format(self, b4: np.ndarray) -> str:
        """猜测 YOLOv26 one-to-one 头 (N,300,6) 的前 4 维格式"""
        if self._v26_box_format:
            return self._v26_box_format

        cand_xyxy = b4.copy()
        cand_cxcywh = self._xywh2xyxy_from_center(b4)
        cand_tlwh = self._tlwh2xyxy(b4)

        def score(xyxy: np.ndarray) -> float:
            w = h = self.img_size
            x1, y1, x2, y2 = xyxy[:, 0], xyxy[:, 1], xyxy[:, 2], xyxy[:, 3]
            valid = (x2 > x1) & (y2 > y1)
            if valid.sum() == 0:
                return -1e9
            inside = (x1 >= -5) & (y1 >= -5) & (x2 <= w + 5) & (y2 <= h + 5)
            area = (x2 - x1) * (y2 - y1)
            huge = area > (0.85 * w * h)
            return float(valid.mean() * 10.0 + inside.mean() * 5.0 - huge.mean() * 3.0)

        scores = {
            'xyxy': score(cand_xyxy),
            'cxcywh': score(cand_cxcywh),
            'tlwh': score(cand_tlwh),
        }
        best = max(scores, key=scores.get)
        self._v26_box_format = best

        # 只打印一次：方便确认格式
        utils.log(f"[ONNX] YOLOv26 box format: {best}")
        return best

    def _v26_decode_boxes(self, b4: np.ndarray) -> np.ndarray:
        """YOLOv26 one-to-one: 将前 4 维解码为 xyxy（模型输入坐标系）"""
        b4 = b4.astype(np.float32)

        # 常见：归一化 0~1
        if np.nanmax(b4) <= 1.5:
            b4[:, [0, 2]] *= float(self.img_size)
            b4[:, [1, 3]] *= float(self.img_size)

        fmt = self._v26_pick_format(b4)

        if fmt == 'xyxy':
            xyxy = b4
        elif fmt == 'tlwh':
            xyxy = self._tlwh2xyxy(b4)
        else:
            xyxy = self._xywh2xyxy_from_center(b4)

        return self._sanitize_xyxy(xyxy, self.img_size, self.img_size, min_size=1.0)

    # -----------------------------
    # Postprocess
    # -----------------------------
    def postprocess(self, output, conf_threshold, iou_threshold, original_shape=None) -> List[Dict[str, Any]]:
        """
        Args:
            output: 模型输出
            conf_threshold: 置信度阈值
            iou_threshold: IOU阈值
            original_shape: 原始图像形状 (height, width)
        """
        predictions = output[0]

        if self._output_needs_squeeze:
            predictions = predictions[0]
        if self._output_needs_transpose:
            predictions = predictions.T

        # -----------------------------
        # YOLOv26 end2end one-to-one (M,6)
        # -----------------------------
        if self.model_type == 'v26' and self._end2end:
            if predictions.ndim != 2 or predictions.shape[1] != 6:
                # 容错：格式不符走传统
                return self._postprocess_traditional(predictions, conf_threshold, iou_threshold, original_shape)

            b4 = predictions[:, :4]
            confs = predictions[:, 4].astype(np.float32)
            class_ids = predictions[:, 5].astype(np.int32)

            mask = confs >= conf_threshold
            if not np.any(mask):
                return []

            b4 = b4[mask]
            confs = confs[mask]
            class_ids = class_ids[mask]

            boxes_xyxy = self._v26_decode_boxes(b4)

            # decode 可能过滤无效框：对齐长度
            n = min(len(boxes_xyxy), len(confs))
            boxes_xyxy = boxes_xyxy[:n]
            confs = confs[:n]
            class_ids = class_ids[:n]

            # 按置信度降序
            order = np.argsort(-confs)
            boxes_xyxy = boxes_xyxy[order]
            confs = confs[order]
            class_ids = class_ids[order]

            # 缩放到原图
            if original_shape is not None:
                orig_h, orig_w = original_shape
                scale_x = orig_w / float(self.img_size)
                scale_y = orig_h / float(self.img_size)

                boxes_xyxy[:, [0, 2]] *= scale_x
                boxes_xyxy[:, [1, 3]] *= scale_y

                boxes_xyxy = self._sanitize_xyxy(boxes_xyxy, orig_w, orig_h, min_size=2.0)

                n2 = min(len(boxes_xyxy), len(confs))
                boxes_xyxy = boxes_xyxy[:n2]
                confs = confs[:n2]
                class_ids = class_ids[:n2]

            return [
                {'box': box.tolist(), 'confidence': float(conf), 'class_id': int(cid)}
                for box, conf, cid in zip(boxes_xyxy, confs, class_ids)
            ]

        # -----------------------------
        # Others / traditional
        # -----------------------------
        return self._postprocess_traditional(predictions, conf_threshold, iou_threshold, original_shape)

    def _postprocess_traditional(
        self,
        predictions,
        conf_threshold,
        iou_threshold,
        original_shape=None
    ) -> List[Dict[str, Any]]:
        """传统后处理逻辑（v5/v8/v10/v11/v26 one-to-many）"""
        if predictions.ndim != 2 or predictions.shape[1] < 6:
            return []

        boxes = predictions[:, :4]

        if self.model_type == 'v5':
            objectness = predictions[:, 4:5]
            class_scores = predictions[:, 5:]
            scores = objectness * class_scores
        else:
            scores = predictions[:, 4:]

        max_scores = scores.max(axis=1)
        class_ids = scores.argmax(axis=1)

        mask = max_scores > conf_threshold
        if not mask.any():
            return []

        boxes = boxes[mask]
        max_scores = max_scores[mask].astype(np.float32)
        class_ids = class_ids[mask].astype(np.int32)

        # 默认传统输出是 cxcywh
        boxes_xyxy = self._xywh2xyxy_from_center(boxes.astype(np.float32))

        # scale to original shape
        if original_shape is not None:
            orig_h, orig_w = original_shape
            scale_x = orig_w / float(self.img_size)
            scale_y = orig_h / float(self.img_size)
            boxes_xyxy[:, [0, 2]] *= scale_x
            boxes_xyxy[:, [1, 3]] *= scale_y

            boxes_xyxy = self._sanitize_xyxy(boxes_xyxy, orig_w, orig_h, min_size=2.0)

            n = min(len(boxes_xyxy), len(max_scores))
            boxes_xyxy = boxes_xyxy[:n]
            max_scores = max_scores[:n]
            class_ids = class_ids[:n]

        final_results = []

        # OpenCV NMSBoxes 需要 xywh
        for class_id in np.unique(class_ids):
            class_mask = class_ids == class_id
            class_boxes_xyxy = boxes_xyxy[class_mask]
            class_scores = max_scores[class_mask]

            if len(class_boxes_xyxy) == 0:
                continue

            x1 = class_boxes_xyxy[:, 0]
            y1 = class_boxes_xyxy[:, 1]
            x2 = class_boxes_xyxy[:, 2]
            y2 = class_boxes_xyxy[:, 3]
            class_boxes_xywh = np.stack([x1, y1, x2 - x1, y2 - y1], axis=1)

            indices = cv2.dnn.NMSBoxes(
                bboxes=class_boxes_xywh.tolist(),
                scores=class_scores.tolist(),
                score_threshold=float(conf_threshold),
                nms_threshold=float(iou_threshold)
            )

            if len(indices) == 0:
                continue

            if isinstance(indices, tuple):
                indices = [i[0] if isinstance(i, (list, np.ndarray)) else i for i in indices]
            elif isinstance(indices, np.ndarray):
                indices = indices.flatten().tolist()

            kept_boxes = class_boxes_xyxy[indices]
            kept_scores = class_scores[indices]

            for b, s in zip(kept_boxes, kept_scores):
                final_results.append({
                    'box': b.tolist(),
                    'confidence': float(s),
                    'class_id': int(class_id)
                })

        return final_results

    # -----------------------------
    # Predict
    # -----------------------------
    def predict(self, img_bgr, conf_threshold=None, iou_threshold=None) -> List[Dict[str, Any]]:
        """主推理接口"""
        conf = float(conf_threshold) if conf_threshold is not None else self._conf_threshold
        iou = float(iou_threshold) if iou_threshold is not None else self._iou_threshold

        original_shape = img_bgr.shape[:2]  # (h, w)

        input_data = self.preprocess(img_bgr)
        outputs = self.session.run(self.output_names, {self.input_name: input_data})
        return self.postprocess(outputs, conf, iou, original_shape)

    # -----------------------------
    # Utilities
    # -----------------------------
    def _detect_input_size(self) -> Optional[int]:
        """从模型输入形状自动检测图像尺寸"""
        try:
            input_shape = self.session.get_inputs()[0].shape
            if len(input_shape) == 4:
                # NCHW
                if input_shape[1] == 3:
                    height, width = input_shape[2], input_shape[3]
                # NHWC
                elif input_shape[3] == 3:
                    height, width = input_shape[1], input_shape[2]
                else:
                    raise ValueError(f"无法识别的输入形状: {input_shape}")

                size = int(min(height, width))
                return size
        except Exception:
            return None

        return None

    def update_thresholds(self):
        """更新阈值"""
        self._conf_threshold = float(get_config('CONF_THRESHOLD', 0.5))
        self._iou_threshold = float(get_config('IOU_THRESHOLD', 0.45))

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
        except Exception:
            pass
