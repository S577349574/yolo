import ast
import cv2
import numpy as np
import onnxruntime as ort

import utils
from config_manager import get_config


class YOLOv8Detector:
    def __init__(self):
        model_path = get_config('MODEL_PATH')
        img_size = get_config('CROP_SIZE')
        self.img_size = img_size

        if model_path is None:
            raise ValueError("MODEL_PATH is None. Check config loading.")

        # 智能选择 Provider（优先 TensorRT）
        providers = self._get_best_providers()
        self.session = ort.InferenceSession(model_path, providers=providers)

        active_provider = self.session.get_providers()[0]
        utils.log(f"✓ 使用 Provider: {active_provider}")

        self.names = self._load_names_from_metadata()
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]

    def _get_best_providers(self):
        """根据硬件自动选择最优 Provider（优先 TensorRT）"""
        available = ort.get_available_providers()

        # 定义优先级（从高到低）
        priority = []

        # 第一优先级：TensorRT（NVIDIA GPU 极致性能）
        if 'TensorrtExecutionProvider' in available:
            trt_options = {
                'trt_fp16_enable': True,  # 启用 FP16 加速
                'trt_engine_cache_enable': True,  # 启用引擎缓存
                'trt_engine_cache_path': './trt_cache',  # 缓存路径
                'trt_max_workspace_size': 2147483648,  # 2GB workspace
            }
            priority.append(('TensorrtExecutionProvider', trt_options))
            utils.log("✓ TensorRT 可用，已设置为第一优先级")

        # 第二优先级：CUDA（NVIDIA GPU 稳定方案）
        if 'CUDAExecutionProvider' in available:
            priority.append('CUDAExecutionProvider')

        # 第三优先级：DirectML（AMD/Intel 显卡）
        if 'DmlExecutionProvider' in available:
            priority.append('DmlExecutionProvider')

        # 兜底：CPU
        priority.append('CPUExecutionProvider')

        utils.log(f"可用 Providers: {available}")
        utils.log(f"选择 Providers: {[p if isinstance(p, str) else p[0] for p in priority]}")

        return priority

    def _load_names_from_metadata(self):
        try:
            metadata = self.session.get_modelmeta().custom_metadata_map or {}
            raw_names = metadata.get('names')
            if raw_names:
                return {int(k): v for k, v in ast.literal_eval(raw_names).items()}
        except Exception as e:
            utils.log(f"Warning: {e}")
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
        boxes, confidences, class_ids = boxes[mask], confidences[mask], class_ids[mask]

        if len(boxes) == 0:
            return []

        boxes_xyxy = self._xywh2xyxy(boxes)
        indices = self._nms(boxes_xyxy, confidences, iou_threshold)

        return [{
            'box': boxes_xyxy[idx],
            'confidence': confidences[idx],
            'class_id': class_ids[idx]
        } for idx in indices]

    @staticmethod
    def _xywh2xyxy(boxes):
        boxes_xyxy = np.copy(boxes)
        boxes_xyxy[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
        boxes_xyxy[:, 1] = boxes[:, 1] - boxes[:, 3] / 2
        boxes_xyxy[:, 2] = boxes[:, 0] + boxes[:, 2] / 2
        boxes_xyxy[:, 3] = boxes[:, 1] + boxes[:, 3] / 2
        return boxes_xyxy

    @staticmethod
    def _nms(boxes, scores, iou_threshold):
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

    def predict(self, img_bgr, conf_threshold=None, iou_threshold=None):
        if conf_threshold is None:
            conf_threshold = get_config('CONF_THRESHOLD')
        if iou_threshold is None:
            iou_threshold = get_config('IOU_THRESHOLD')
        input_data = self.preprocess(img_bgr)
        outputs = self.session.run(self.output_names, {self.input_name: input_data})
        return self.postprocess(outputs[0], conf_threshold, iou_threshold)
