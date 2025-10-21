"""YOLOv8目标检测器"""
import ast
import cv2
import numpy as np
import onnxruntime as ort

import utils
from config import *


class YOLOv8Detector:
    def __init__(self, model_path=MODEL_PATH, img_size=CROP_SIZE):
        self.img_size = img_size
        providers = ['DmlExecutionProvider', 'CUDAExecutionProvider', 'CPUExecutionProvider']
        available_providers = ort.get_available_providers()
        active_providers = [p for p in providers if p in available_providers]

        self.session = ort.InferenceSession(model_path, providers=active_providers)
        utils.log(f"✓ 使用Provider: {self.session.get_providers()[0]}")

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

    def predict(self, img_bgr, conf_threshold=CONF_THRESHOLD, iou_threshold=IOU_THRESHOLD):
        input_data = self.preprocess(img_bgr)
        outputs = self.session.run(self.output_names, {self.input_name: input_data})
        return self.postprocess(outputs[0], conf_threshold, iou_threshold)
