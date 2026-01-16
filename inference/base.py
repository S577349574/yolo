"""推理后端基类"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseDetector(ABC):
    """检测器基类 - 所有后端必须实现这些接口"""

    @abstractmethod
    def predict(self, img_bgr, conf_threshold=None, iou_threshold=None) -> List[Dict[str, Any]]:
        """
        执行推理

        Args:
            img_bgr: BGR格式图像(numpy.ndarray)
            conf_threshold: 置信度阈值(可选)
            iou_threshold: IOU阈值(可选)

        Returns:
            检测结果列表，每个元素包含:
            {
                'box': [x1, y1, x2, y2],
                'confidence': float,
                'class_id': int
            }
        """
        pass

    @abstractmethod
    def get_class_name(self, class_id: int) -> str:
        """获取类别名称"""
        pass

    @abstractmethod
    def update_thresholds(self):
        """更新置信度和IOU阈值(从配置热更新)"""
        pass

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """返回后端名称(用于日志)"""
        pass

    def warmup(self, iterations: int = 5):
        """预热模型(可选重写)"""
        pass
