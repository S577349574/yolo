"""推理管理器 - 统一入口"""
import utils
from config_manager import get_config
from .exceptions import BackendNotAvailableError
from .utils.detector import select_best_backend


class InferenceManager:
    """推理管理器 - 自动选择最优后端"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._detector = None
        self._current_backend = None
        self._initialized = True

        self.reload()

    def reload(self):
        """重新加载检测器(配置变更时调用)"""
        force_backend = get_config('FORCE_BACKEND', None)
        selected_backend = select_best_backend(force_backend)

        utils.log(f"[推理] 选择后端: {selected_backend}")

        try:
            if selected_backend in ['tensorrt', 'cuda', 'dml', 'cpu']:
                from .backends.onnx_backend import ONNXDetector
                self._detector = ONNXDetector(preferred_backend=selected_backend)

            elif selected_backend in ['ncnn_vulkan', 'ncnn_cpu']:
                from .backends.ncnn_backend import NCNNDetector
                self._detector = NCNNDetector(use_gpu=(selected_backend == 'ncnn_vulkan'))

            else:
                raise BackendNotAvailableError(f"不支持的后端: {selected_backend}")

            self._current_backend = selected_backend
            utils.log(f"✓ 推理后端加载成功: {self._detector.backend_name}")

        except Exception as e:
            utils.log(f"❌ 加载后端失败: {e}")
            raise

    def predict(self, img_bgr, conf_threshold=None, iou_threshold=None):
        """执行推理"""
        if self._detector is None:
            raise RuntimeError("推理后端未初始化")
        return self._detector.predict(img_bgr, conf_threshold, iou_threshold)

    def get_class_name(self, class_id: int) -> str:
        """获取类别名称"""
        return self._detector.get_class_name(class_id)

    def update_thresholds(self):
        """更新阈值"""
        if self._detector:
            self._detector.update_thresholds()

    # ========== 🔥 新增：兼容旧代码的属性 🔥 ==========
    @property
    def names(self) -> dict:
        """
        获取类别名称字典（兼容旧代码）

        Returns:
            {0: 'person', 1: 'car', ...}
        """
        if self._detector is None:
            return {}

        # 如果后端有 names 属性，直接返回
        if hasattr(self._detector, 'names'):
            return self._detector.names

        # 否则通过 get_class_name 构建
        # （某些后端可能只实现了 get_class_name）
        return {}

    @property
    def backend_name(self) -> str:
        """当前后端名称"""
        return self._current_backend if self._current_backend else "未初始化"

    # ========== 🔥 新增：兼容尺寸获取 🔥 ==========
    @property
    def img_size(self) -> int:
        """
        获取模型输入尺寸（动态从底层检测器获取）
        """
        if self._detector is None:
            return 640  # 默认兜底值

        # 1. 尝试从底层检测器获取 (ONNXDetector 或 NCNNDetector 应该存有这个值)
        # 尝试常见的变量名：img_size, input_size, imgsz
        for attr in ['img_size', 'input_size', 'imgsz']:
            if hasattr(self._detector, attr):
                val = getattr(self._detector, attr)
                # 如果是元组 (320, 320)，取第一个值
                if isinstance(val, (list, tuple)):
                    return val[0]
                return val

        # 2. 如果底层也没有，尝试从配置读取
        from config_manager import get_config
        return get_config('CROP_SIZE', 640)

# 全局单例
def get_detector() -> InferenceManager:
    """获取推理器实例(推荐用法)"""
    return InferenceManager()


# 向后兼容
class YOLOv8Detector:
    """兼容旧代码的包装类"""

    def __new__(cls):
        return get_detector()
