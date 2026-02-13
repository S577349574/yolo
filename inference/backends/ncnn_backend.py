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
from config.config_manager import get_config
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
        # ✅ 优先从模型自动检测
        self.img_size = self._detect_input_size()

        self._conf_threshold = get_config('CONF_THRESHOLD', 0.5)
        self._iou_threshold = get_config('IOU_THRESHOLD', 0.45)

        utils.log(f"[ncnn] 输入尺寸: {self.img_size}x{self.img_size}")
        utils.log(f"[ncnn] 阈值: conf={self._conf_threshold}, iou={self._iou_threshold}")

    def _detect_input_size(self) -> int:
        """
        从 ncnn 模型的 .param 文件自动检测输入尺寸

        Returns:
            int: 输入尺寸（如 640）
        """
        try:
            # 获取 .param 文件路径
            onnx_path = get_config('MODEL_PATH')
            param_path = get_config('NCNN_PARAM_PATH', None)

            if param_path is None:
                base_path = os.path.splitext(onnx_path)[0]
                param_path = base_path + '.param'

            if not os.path.exists(param_path):
                raise FileNotFoundError(f"找不到 .param 文件: {param_path}")

            # 解析 .param 文件
            with open(param_path, 'r') as f:
                lines = f.readlines()

            # 查找 Input 层的形状信息
            # 格式示例: "Input in0 0 1 in0 0=640 1=640 2=3"
            for line in lines:
                if line.strip().startswith('Input'):
                    parts = line.split()

                    # 查找 0=height 1=width 2=channels
                    height, width = None, None
                    for part in parts:
                        if part.startswith('0='):
                            height = int(part.split('=')[1])
                        elif part.startswith('1='):
                            width = int(part.split('=')[1])

                    if height and width:
                        if height != width:
                            utils.log(f"⚠️ ncnn模型输入非正方形: {height}x{width}，使用较小值")
                            size = min(height, width)
                        else:
                            size = height

                        utils.log(f"[ncnn] 从 .param 自动检测输入尺寸: {size}x{size}")
                        return size

            utils.log("⚠️ 未能从 .param 解析输入尺寸")

        except Exception as e:
            utils.log(f"⚠️ ncnn 自动检测输入尺寸失败: {e}")

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
        """优化预处理：一步到位减少内存拷贝"""
        img_resized = cv2.resize(img_bgr, (self.img_size, self.img_size))

        # 归一化参数：1/255 = 0.00392156
        mean_vals = [0, 0, 0]
        norm_vals = [0.00392156, 0.00392156, 0.00392156]

        # 直接在创建时处理 BGR2RGB 和 归一化
        mat_in = ncnn.Mat.from_pixels_resize(
            img_resized,
            ncnn.Mat.PixelType.PIXEL_BGR2RGB,
            self.img_size, self.img_size,
            self.img_size, self.img_size
        )
        mat_in.substract_mean_normalize(mean_vals, norm_vals)
        return mat_in

    def _inference(self, img_bgr):
        """执行推理 - 修复 AttributeError 并优化性能"""
        mat_in = self.preprocess(img_bgr)

        ex = self.net.create_extractor()
        # 显式设置线程数（注意：如果使用了 Vulkan GPU，CPU 线程数影响较小）
        # 在 Python 中，通常在 net.opt 中统一设置，但也可以在此处确保
        # 如果需要设置线程，请确保在 net.opt 中已经设置过，或者调用全局函数：
        # import ncnn
        # ncnn.set_omp_num_threads(4)

        ex.set_light_mode(True)
        # 移除 ex.set_num_threads(4) -> 这一行在 Python API 中不存在

        # 输入数据
        ex.input(self.input_name, mat_in)

        # 提取所有输出
        outputs = []
        for output_name in self.output_names:
            ret, mat_out = ex.extract(output_name)

            if ret != 0:
                utils.log(f"⚠️ ncnn提取输出 {output_name} 失败，错误码: {ret}")
                continue

            # 转换为 numpy 数组
            outputs.append(np.array(mat_out))

        if not outputs:
            return None

        # 如果只有一个输出（如日志显示自动检测到了 out0），直接返回第一个
        if len(outputs) == 1:
            return outputs[0]

        # 多输出需要合并（针对没有在导出时合并头的 YOLOv8）
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

    def postprocess(self, output: np.ndarray, conf_threshold: float, iou_threshold: float) -> List[Dict[str, Any]]:
        """
        高性能后处理实现

        Args:
            output: 模型推理输出，形状应为 [1, 84, 8400] 或 [84, 8400]
            conf_threshold: 置信度阈值
            iou_threshold: NMS IOU 阈值

        Returns:
            List[Dict]: 包含 box, confidence, class_id 的结果列表
        """
        if output is None or output.size == 0:
            return []

        # 1. 维度对齐 [1, 84, 8400] -> [84, 8400]
        if output.ndim == 3:
            output = output[0]

        # 2. 转置确保形状为 [8400, 84] (即 [候选框数量, 4个坐标+类别分数])
        if output.shape[0] < output.shape[1]:
            output = output.T

        # 3. 快速过滤 (Vectorized Filtering)
        # 提取类别分数并找到每个框的最大分数
        scores = output[:, 4:]
        max_scores = np.max(scores, axis=1)

        # 仅保留大于阈值的索引，大幅减少后续运算量
        keep_idx = max_scores > conf_threshold
        if not np.any(keep_idx):
            return []

        # 过滤数据
        filtered_output = output[keep_idx]
        filtered_max_scores = max_scores[keep_idx]
        filtered_class_ids = np.argmax(filtered_output[:, 4:], axis=1)

        # 4. 坐标转换 (仅针对过滤后的框)
        # YOLOv8 输出通常是 cx, cy, w, h
        boxes_xywh = filtered_output[:, :4]
        boxes_xyxy = self._xywh2xyxy(boxes_xywh)

        # 5. 非极大值抑制 (NMS)
        # 使用 OpenCV 的 NMSBoxes，其内部由 C++ 实现，速度极快
        indices = cv2.dnn.NMSBoxes(
            boxes_xyxy.tolist(),
            filtered_max_scores.tolist(),
            conf_threshold,
            iou_threshold
        )

        # 6. 组装最终结果
        final_results = []
        if len(indices) > 0:
            # 兼容不同版本的 OpenCV NMS 返回格式
            if isinstance(indices, np.ndarray):
                indices = indices.flatten()
            else:
                indices = [i[0] if isinstance(i, (list, tuple)) else i for i in indices]

            for idx in indices:
                # 注意：这里的 idx 是 filtered_output 中的索引
                final_results.append({
                    'box': boxes_xyxy[idx].tolist(),
                    'confidence': float(filtered_max_scores[idx]),
                    'class_id': int(filtered_class_ids[idx]),
                    'class_name': self.get_class_name(int(filtered_class_ids[idx]))
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