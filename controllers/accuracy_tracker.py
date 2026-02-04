# controllers/accuracy_tracker.py
"""准确率跟踪器"""

from typing import List


class AccuracyTracker:
    """
    准确率跟踪器（基于误差距离）

    功能：
    - 记录最近N次的误差距离
    - 计算平均准确率
    - 提供统计信息
    """

    def __init__(self, max_history: int = 30, base_error: float = 10.0):
        """
        初始化准确率跟踪器

        Args:
            max_history: 最大历史记录数
            base_error: 基准误差（用于归一化）
        """
        self.recent_errors: List[float] = []
        self.max_history = max_history
        self.base_error = base_error

    def update(self, error_distance: float) -> float:
        """
        更新误差并返回当前准确率

        Args:
            error_distance: 当前误差距离（像素）

        Returns:
            float: 准确率 (0.0 ~ 1.0)
        """
        self.recent_errors.append(error_distance)

        # 限制历史记录长度
        if len(self.recent_errors) > self.max_history:
            self.recent_errors.pop(0)

        return self.get_accuracy()

    def get_accuracy(self) -> float:
        """
        计算当前准确率

        Returns:
            float: 准确率 (0.0 ~ 1.0)
        """
        if not self.recent_errors:
            return 0.0

        avg_error = sum(self.recent_errors) / len(self.recent_errors)

        # 使用反比例函数计算准确率
        # accuracy = 1 / (1 + avg_error / base_error)
        accuracy = 1.0 / (1.0 + avg_error / self.base_error)

        return accuracy

    def get_average_error(self) -> float:
        """
        获取平均误差

        Returns:
            float: 平均误差（像素）
        """
        if not self.recent_errors:
            return 0.0
        return sum(self.recent_errors) / len(self.recent_errors)

    def get_min_error(self) -> float:
        """获取最小误差"""
        if not self.recent_errors:
            return 0.0
        return min(self.recent_errors)

    def get_max_error(self) -> float:
        """获取最大误差"""
        if not self.recent_errors:
            return 0.0
        return max(self.recent_errors)

    def get_sample_count(self) -> int:
        """获取样本数量"""
        return len(self.recent_errors)

    def reset(self) -> None:
        """重置历史记录"""
        self.recent_errors.clear()

    def get_statistics(self) -> dict:
        """
        获取统计信息

        Returns:
            dict: 包含准确率、平均误差等信息
        """
        return {
            'accuracy': self.get_accuracy(),
            'avg_error': self.get_average_error(),
            'min_error': self.get_min_error(),
            'max_error': self.get_max_error(),
            'sample_count': self.get_sample_count(),
        }
