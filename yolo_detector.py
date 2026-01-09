# yolo_detector.py (优化异常处理版本)
"""
YOLOv8 检测器 - 性能优化版 + 友好的异常处理
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


class ModelLoadError(Exception):
    """模型加载错误（自定义异常）"""
    pass


def _get_best_providers():
    """根据硬件自动选择最优 Provider"""
    # ... (保持不变)
    available = ort.get_available_providers()
    priority = []

    use_tensorrt = get_config('USE_TENSORRT', True)

    if use_tensorrt and 'TensorrtExecutionProvider' in available:
        from config_manager import ConfigManager
        config_mgr = ConfigManager()
        app_dir = config_mgr.app_dir

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
            'trt_max_workspace_size': 2147483648,
            'trt_builder_optimization_level': 5,
            'trt_timing_cache_enable': True,
        }
        priority.append(('TensorrtExecutionProvider', trt_options))

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

        # ========== 🔥 优化的模型路径验证 🔥 ==========
        # 1. 检查配置是否为空
        if not model_path or not isinstance(model_path, str):
            error_msg = (
                "❌ 模型路径配置错误\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "问题：配置文件中的 MODEL_PATH 为空或无效\n"
                "\n"
                "解决方案：\n"
                "1️⃣  打开 GUI 配置界面\n"
                "2️⃣  在「基础 & 系统」标签页中\n"
                "3️⃣  填写正确的模型路径，例如：\n"
                "    D:\\models\\yolov8.onnx\n"
                "4️⃣  点击「保存所有配置」按钮\n"
                "5️⃣  点击「重载配置/模型」按钮\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            utils.log(error_msg)
            self._pause_system_and_raise(error_msg)

        # 2. 检查文件是否存在
        if not os.path.isfile(model_path):
            # 提取目录和文件名
            model_dir = os.path.dirname(model_path) or "当前目录"
            model_name = os.path.basename(model_path)

            error_msg = (
                "❌ 模型文件不存在\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"配置的路径：{model_path}\n"
                f"文件名：{model_name}\n"
                f"所在目录：{model_dir}\n"
                "\n"
                "可能的原因：\n"
                "1️⃣  文件路径输入错误（检查拼写和扩展名）\n"
                "2️⃣  文件被移动或删除\n"
                "3️⃣  文件名后缀错误（应为 .onnx）\n"
                "\n"
                "解决方案：\n"
                "• 确认模型文件确实存在于该路径\n"
                "• 在 GUI 中重新选择正确的模型路径\n"
                "• 检查文件扩展名（当前显示为 .onnx1？）\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            utils.log(error_msg)

            # 尝试查找可能的模型文件
            self._suggest_alternative_models(model_dir)

            self._pause_system_and_raise(error_msg)

        # 3. 检查文件扩展名
        _, ext = os.path.splitext(model_path)
        if ext.lower() != '.onnx':
            warning_msg = (
                f"⚠️  模型文件扩展名异常\n"
                f"当前扩展名：{ext}\n"
                f"预期扩展名：.onnx\n"
                f"将尝试加载，但可能失败..."
            )
            utils.log(warning_msg)

        # ========== 正常加载流程 ==========
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
            error_msg = (
                f"❌ ONNX Runtime 加载模型失败\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"模型路径：{model_path}\n"
                f"错误信息：{str(e)}\n"
                f"\n"
                f"可能的原因：\n"
                f"1️⃣  模型文件已损坏\n"
                f"2️⃣  ONNX 版本不兼容\n"
                f"3️⃣  GPU 驱动问题（尝试禁用 TensorRT）\n"
                f"\n"
                f"解决方案：\n"
                f"• 重新导出 ONNX 模型\n"
                f"• 更新 onnxruntime-gpu 版本\n"
                f"• 在配置中禁用 USE_TENSORRT\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            utils.log(error_msg)
            self._pause_system_and_raise(error_msg)

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

        # 性能统计开关
        self._enable_timing = get_config('YOLO_ENABLE_TIMING', False)
        self._enable_anomaly_detection = get_config('YOLO_ENABLE_ANOMALY_DETECTION', False)

        # 预确定输出格式
        self._output_needs_transpose = None
        self._output_needs_squeeze = None

        # 模型预热
        self._warmup()

    def _suggest_alternative_models(self, search_dir):
        """在目录中查找可能的模型文件"""
        try:
            if not os.path.isdir(search_dir):
                search_dir = os.getcwd()

            onnx_files = []
            for root, dirs, files in os.walk(search_dir):
                for file in files:
                    if file.endswith('.onnx'):
                        onnx_files.append(os.path.join(root, file))
                # 只搜索一层子目录
                if root != search_dir:
                    break

            if onnx_files:
                utils.log("\n💡 在附近找到以下 ONNX 模型文件：")
                for i, file in enumerate(onnx_files[:5], 1):
                    utils.log(f"   {i}. {file}")
                if len(onnx_files) > 5:
                    utils.log(f"   ... 还有 {len(onnx_files) - 5} 个文件")
            else:
                utils.log("\n💡 在当前目录及子目录中未找到 .onnx 文件")

        except Exception as e:
            utils.log(f"⚠️  查找替代模型时出错: {e}")

    def _pause_system_and_raise(self, error_msg):
        """暂停主线程并抛出异常"""
        try:
            # 获取 ConfigManager 的事件
            from config_manager import get_events
            resume_event, _, _ = get_events()

            # 暂停主线程
            resume_event.clear()
            utils.log("\n⏸️  系统已自动暂停，请修复配置后点击「重载配置/模型」")

        except Exception as e:
            utils.log(f"⚠️  暂停系统时出错: {e}")

        # 抛出自定义异常
        raise ModelLoadError(error_msg)

    # ========== 以下方法保持不变 ==========

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

            if i == 0:
                input_data = self.preprocess(dummy_input)
                outputs = self.session.run(self.output_names, {self.input_name: input_data})
                predictions = outputs[0] if isinstance(outputs, list) else outputs

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
        """预处理图像"""
        blob = cv2.dnn.blobFromImage(
            img_bgr,
            scalefactor=1.0 / 255.0,
            size=(self.img_size, self.img_size),
            swapRB=True,
            crop=False,
            ddepth=cv2.CV_32F
        )
        return blob

    def postprocess(self, output, conf_threshold, iou_threshold):
        """后处理：按类别分组的NMS"""
        predictions = output[0] if isinstance(output, list) else output

        if self._output_needs_squeeze:
            predictions = predictions[0]
        if self._output_needs_transpose:
            predictions = predictions.T

        boxes = predictions[:, :4]
        scores = predictions[:, 4:]

        max_scores = scores.max(axis=1)
        mask = max_scores > conf_threshold

        if not mask.any():
            return []

        boxes = boxes[mask]
        scores = scores[mask]
        max_scores = max_scores[mask]
        class_ids = scores.argmax(axis=1)

        boxes_xyxy = self._xywh2xyxy_vectorized(boxes)

        final_results = []
        unique_classes = np.unique(class_ids)

        for class_id in unique_classes:
            class_mask = class_ids == class_id
            class_boxes = boxes_xyxy[class_mask]
            class_scores = max_scores[class_mask]

            class_indices = cv2.dnn.NMSBoxes(
                class_boxes.tolist(),
                class_scores.tolist(),
                conf_threshold,
                iou_threshold
            )

            if len(class_indices) == 0:
                continue

            if isinstance(class_indices, np.ndarray):
                class_indices = class_indices.flatten()
            else:
                class_indices = [i[0] if isinstance(i, (list, tuple)) else i
                                 for i in class_indices]

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
        """向量化坐标转换"""
        xy = boxes[:, :2]
        wh = boxes[:, 2:4]
        half_wh = wh * 0.5
        return np.concatenate([xy - half_wh, xy + half_wh], axis=1)

    def _predict_internal(self, img_bgr):
        """内部预测方法"""
        input_data = self.preprocess(img_bgr)
        return self.session.run(self.output_names, {self.input_name: input_data})

    def predict(self, img_bgr, conf_threshold=None, iou_threshold=None):
        """主预测接口"""
        conf = conf_threshold if conf_threshold is not None else self._conf_threshold
        iou = iou_threshold if iou_threshold is not None else self._iou_threshold

        if self._enable_timing or self._enable_anomaly_detection:
            t_start = time.perf_counter()
            input_data = self.preprocess(img_bgr)
            t_preprocess = time.perf_counter()
            outputs = self.session.run(self.output_names, {self.input_name: input_data})
            t_inference = time.perf_counter()
            results = self.postprocess(outputs, conf, iou)
            t_postprocess = time.perf_counter()

            if self._enable_anomaly_detection:
                inference_time = (t_inference - t_preprocess) * 1000
                if inference_time > 10.0:
                    utils.log(f"⚠️ 异常推理时间: {inference_time:.2f}ms (正常应为2-4ms)")
                    utils.log(f"   预处理: {(t_preprocess - t_start) * 1000:.2f}ms")
                    utils.log(f"   推理: {inference_time:.2f}ms")
                    utils.log(f"   后处理: {(t_postprocess - t_inference) * 1000:.2f}ms")
        else:
            input_data = self.preprocess(img_bgr)
            outputs = self.session.run(self.output_names, {self.input_name: input_data})
            results = self.postprocess(outputs, conf, iou)

        return results

    def update_thresholds(self):
        """配置热更新时调用"""
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
        """获取类别名称"""
        return self.names.get(class_id, f"class_{class_id}")

    def __del__(self):
        """析构函数"""
        try:
            if hasattr(self, 'session'):
                del self.session
        except Exception:
            pass
