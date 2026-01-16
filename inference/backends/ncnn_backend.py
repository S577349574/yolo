import os
import time
from typing import List, Dict, Any

import cv2
import numpy as np

try:
    import ncnn
    NCNN_AVAILABLE = True
except ImportError:
    NCNN_AVAILABLE = False

import utils
from config_manager import get_config
from ..base import BaseDetector
from ..exceptions import ModelLoadError, BackendNotAvailableError


class NCNNDetector(BaseDetector):
    """ncnn 检测器 - Vulkan GPU加速"""

    def __init__(self, use_gpu: bool = True):
        """
        Args:
            use_gpu: 是否使用Vulkan GPU加速
        """
        if not NCNN_AVAILABLE:
            raise BackendNotAvailableError(
                "ncnn 未安装，请运行: pip install ncnn"
            )

        self.use_gpu = use_gpu
        self._load_model()
        self._load_config()
        self._warmup()

    def _load_model(self):
        """加载ncnn模型"""
        # 获取模型路径
        onnx_path = get_config('MODEL_PATH')

        # 尝试从配置获取ncnn模型路径
        param_path = get_config('NCNN_PARAM_PATH', None)
        bin_path = get_config('NCNN_BIN_PATH', None)

        # 如果没有配置，从ONNX路径推断
        if param_path is None or bin_path is None:
            base_path = os.path.splitext(onnx_path)[0]
            param_path = base_path + '.param'
            bin_path = base_path + '.bin'

        # 验证文件存在
        if not os.path.exists(param_path):
            raise ModelLoadError(
                f"❌ ncnn模型文件不存在: {param_path}\n\n"
                f"请使用以下工具转换ONNX模型:\n"
                f"  方法1: onnx2ncnn {onnx_path} {param_path} {bin_path}\n"
                f"  方法2: pnnx (推荐，效果更好)\n\n"
                f"或在配置中指定 NCNN_PARAM_PATH 和 NCNN_BIN_PATH"
            )

        if not os.path.exists(bin_path):
            raise ModelLoadError(
                f"❌ ncnn权重文件不存在: {bin_path}"
            )

        utils.log(f"[ncnn] 加载模型:")
        utils.log(f"  Param: {param_path}")
        utils.log(f"  Bin:   {bin_path}")

        # 初始化ncnn网络
        self.net = ncnn.Net()

        # GPU配置
        gpu_count = ncnn.get_gpu_count()
        if self.use_gpu and gpu_count > 0:
            self.net.opt.use_vulkan_compute = True

            # 获取GPU信息
            try:
                gpu_info = ncnn.get_gpu_info(0)
                utils.log(f"✓ ncnn Vulkan GPU: {gpu_info}")
            except:
                utils.log(f"✓ ncnn Vulkan GPU 已启用 (检测到 {gpu_count} 个GPU)")

            # 性能优化选项
            use_fp16 = get_config('NCNN_USE_FP16', True)
            if use_fp16:
                self.net.opt.use_fp16_packed = True
                self.net.opt.use_fp16_storage = True
                self.net.opt.use_fp16_arithmetic = True
                utils.log("✓ ncnn FP16 加速已启用")
        else:
            self.net.opt.use_vulkan_compute = False
            if self.use_gpu:
                utils.log("⚠️ 未检测到Vulkan GPU，使用CPU模式")
            else:
                utils.log("[ncnn] 使用CPU模式")

        # 通用优化
        self.net.opt.use_packing_layout = True
        self.net.opt.lightmode = True  # 减少内存占用

        # 加载模型文件
        try:
            ret_param = self.net.load_param(param_path)
            ret_bin = self.net.load_model(bin_path)

            if ret_param != 0:
                raise ModelLoadError(f"加载 .param 失败，错误码: {ret_param}")
            if ret_bin != 0:
                raise ModelLoadError(f"加载 .bin 失败，错误码: {ret_bin}")

            utils.log("✓ ncnn模型加载成功")

        except Exception as e:
            raise ModelLoadError(f"ncnn模型加载失败: {e}")

        # 设置输入输出层名称 (根据实际模型调整)
        # 1. 尝试从配置读取
        self.input_name = get_config('NCNN_INPUT_NAME', None)

        # 2. 如果配置为空，自动检测
        if self.input_name is None:
            self.input_name = self._auto_detect_input(param_path)
            utils.log(f"[ncnn] 自动检测到输入层: {self.input_name}")

        # 3. 输出层同理
        output_names = get_config('NCNN_OUTPUT_NAMES', None)
        if output_names is None:
            self.output_names = self._auto_detect_outputs(param_path)
            utils.log(f"[ncnn] 自动检测到输出层: {', '.join(self.output_names)}")
        else:
            self.output_names = output_names

        # 加载类别名称
        self.names = self._load_names()

    def _load_names(self) -> Dict[int, str]:
        """加载类别名称"""
        # 方法1: 从配置文件加载
        names_path = get_config('CLASS_NAMES_PATH', None)

        # 方法2: 从模型同目录的names.txt加载
        if names_path is None:
            onnx_path = get_config('MODEL_PATH')
            names_path = os.path.join(os.path.dirname(onnx_path), 'names.txt')

        if os.path.exists(names_path):
            try:
                with open(names_path, 'r', encoding='utf-8') as f:
                    names = {i: name.strip() for i, name in enumerate(f.readlines())}
                utils.log(f"[ncnn] 加载类别名称: {len(names)} 个类别")
                return names
            except Exception as e:
                utils.log(f"[ncnn] 加载类别名称失败: {e}")

        return {}

    def _load_config(self):
        """加载配置"""
        self.img_size = get_config('CROP_SIZE', 640)
        self._conf_threshold = get_config('CONF_THRESHOLD', 0.5)
        self._iou_threshold = get_config('IOU_THRESHOLD', 0.45)

        utils.log(f"[ncnn] 输入尺寸: {self.img_size}x{self.img_size}")
        utils.log(f"[ncnn] 阈值: conf={self._conf_threshold}, iou={self._iou_threshold}")

    def _warmup(self, iterations: int = 5):
        """预热模型"""
        utils.log("[ncnn] 正在预热模型...")

        dummy = np.random.randint(0, 255, (self.img_size, self.img_size, 3), dtype=np.uint8)

        times = []
        for i in range(iterations):
            start = time.perf_counter()
            self.predict(dummy)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)

        avg = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)

        utils.log(f"✓ ncnn预热完成:")
        utils.log(f"   平均: {avg:.2f}ms, 最小: {min_time:.2f}ms, 最大: {max_time:.2f}ms")

    def preprocess(self, img_bgr):
        """预处理 - 转换为ncnn.Mat格式"""
        # Resize
        img_resized = cv2.resize(img_bgr, (self.img_size, self.img_size))

        # BGR -> RGB, 归一化, 转ncnn.Mat
        mat_in = ncnn.Mat.from_pixels(
            img_resized,
            ncnn.Mat.PixelType.PIXEL_BGR2RGB,
            self.img_size,
            self.img_size
        )

        # 归一化 (mean=0, norm=1/255)
        mean_vals = [0.0, 0.0, 0.0]
        norm_vals = [1.0/255.0, 1.0/255.0, 1.0/255.0]
        mat_in.substract_mean_normalize(mean_vals, norm_vals)

        return mat_in

    def _inference(self, img_bgr):
        """执行推理 - 支持多输出"""
        mat_in = self.preprocess(img_bgr)

        ex = self.net.create_extractor()
        ex.set_light_mode(True)

        # 输入数据
        ex.input(self.input_name, mat_in)

        # 提取所有输出
        outputs = []
        for output_name in self.output_names:
            ret, mat_out = ex.extract(output_name)

            if ret != 0:
                utils.log(f"⚠️ ncnn提取输出 {output_name} 失败，错误码: {ret}")
                return None

            outputs.append(np.array(mat_out))

        # 如果只有一个输出，直接返回
        if len(outputs) == 1:
            return outputs[0]

        # 多输出需要合并（YOLOv8的三个检测头）
        return self._merge_multi_scale_outputs(outputs)

    def _merge_multi_scale_outputs(self, outputs):
        """
        合并多尺度输出

        YOLOv8的三个输出:
        - out0: [1, 84, 6400]   (80×80网格)
        - out1: [1, 84, 1600]   (40×40网格)
        - out2: [1, 84, 400]    (20×20网格)

        合并成: [1, 84, 8400]
        """
        merged = []

        for output in outputs:
            # 确保是3维 [1, C, H*W]
            if output.ndim == 4:
                # [1, C, H, W] -> [1, C, H*W]
                batch, channels, h, w = output.shape
                output = output.reshape(batch, channels, h * w)
            elif output.ndim == 2:
                # [C, H*W] -> [1, C, H*W]
                output = output[np.newaxis, :]

            merged.append(output)

        # 在最后一维拼接
        return np.concatenate(merged, axis=2)

    def postprocess(self, output, conf_threshold, iou_threshold) -> List[Dict[str, Any]]:
        """后处理 - NMS"""
        if output is None:
            return []

        predictions = output

        # 处理输出形状 [1, 84, 8400] -> [8400, 84]
        if predictions.ndim == 3:
            predictions = predictions[0]  # 去掉batch维度
        if predictions.shape[0] < predictions.shape[1]:
            predictions = predictions.T  # 转置

        # 分离boxes和scores
        boxes = predictions[:, :4]  # [N, 4] (x,y,w,h)
        scores = predictions[:, 4:]  # [N, num_classes]

        # 获取最大置信度和类别
        max_scores = scores.max(axis=1)
        mask = np.asarray(max_scores > conf_threshold)  # ← 显式转换

        if not mask.any():
            return []

        boxes = boxes[mask]
        scores = scores[mask]
        max_scores = max_scores[mask]
        class_ids = scores.argmax(axis=1)

        # xywh -> xyxy
        boxes_xyxy = self._xywh2xyxy(boxes)

        # 按类别分组NMS
        final_results = []
        unique_classes = np.unique(class_ids)

        for class_id in unique_classes:
            class_mask = class_ids == class_id
            class_boxes = boxes_xyxy[class_mask]
            class_scores = max_scores[class_mask]

            # OpenCV NMS
            indices = cv2.dnn.NMSBoxes(
                class_boxes.tolist(),
                class_scores.tolist(),
                conf_threshold,
                iou_threshold
            )

            if len(indices) == 0:
                continue

            # 处理返回格式
            if isinstance(indices, np.ndarray):
                indices = indices.flatten()
            else:
                indices = [i[0] if isinstance(i, (list, tuple)) else i for i in indices]

            # 获取原始索引
            original_indices = np.where(class_mask)[0]

            for idx in indices:
                global_idx = original_indices[idx]
                final_results.append({
                    'box': boxes_xyxy[global_idx].tolist(),
                    'confidence': float(max_scores[global_idx]),
                    'class_id': int(class_id)
                })

        return final_results

    @staticmethod
    def _xywh2xyxy(boxes):
        """坐标转换 xywh -> xyxy"""
        xy = boxes[:, :2]
        wh = boxes[:, 2:4]
        half_wh = wh * 0.5
        return np.concatenate([xy - half_wh, xy + half_wh], axis=1)

    def predict(self, img_bgr, conf_threshold=None, iou_threshold=None) -> List[Dict[str, Any]]:
        """主推理接口"""
        conf = conf_threshold if conf_threshold is not None else self._conf_threshold
        iou = iou_threshold if iou_threshold is not None else self._iou_threshold

        output = self._inference(img_bgr)
        return self.postprocess(output, conf, iou)

    def update_thresholds(self):
        """更新阈值"""
        old_conf = self._conf_threshold
        old_iou = self._iou_threshold

        self._conf_threshold = get_config('CONF_THRESHOLD', 0.5)
        self._iou_threshold = get_config('IOU_THRESHOLD', 0.45)

        if old_conf != self._conf_threshold or old_iou != self._iou_threshold:
            utils.log(
                f"[ncnn] 阈值已更新: "
                f"conf={self._conf_threshold}, iou={self._iou_threshold}"
            )

    def get_class_name(self, class_id: int) -> str:
        return self.names.get(class_id, f"class_{class_id}")

    @property
    def backend_name(self) -> str:
        if self.use_gpu and self.net.opt.use_vulkan_compute:
            return "ncnn-Vulkan"
        return "ncnn-CPU"

    def __del__(self):
        """清理资源"""
        try:
            if hasattr(self, 'net'):
                del self.net
        except:
            pass

    def _auto_detect_input(self, param_path) -> str:
        """从 .param 自动检测输入层名称"""
        try:
            with open(param_path, 'r') as f:
                for line in f:
                    if line.strip().startswith('Input'):
                        # "Input in0 0 1 in0"
                        parts = line.split()
                        return parts[-1]  # 最后一个单词是输入层名称
        except:
            pass

        # 兜底：使用常见默认值
        return 'images'

    def _auto_detect_outputs(self, param_path) -> List[str]:
        """从 .param 自动检测输出层名称"""
        try:
            with open(param_path, 'r') as f:
                lines = f.readlines()

            output_names = []
            # 倒序查找最后几个 Concat 层
            for line in reversed(lines):
                parts = line.strip().split()
                if len(parts) < 2:
                    continue

                # 找 Concat 层且输出名称以 out 开头
                if parts[0] == 'Concat':
                    for part in parts:
                        if part.startswith('out'):
                            output_names.insert(0, part)
                            break

                # 找到3个输出层就停止
                if len(output_names) >= 3:
                    break

            if output_names:
                return output_names
        except:
            pass

        # 兜底：使用常见默认值
        return ['output0']