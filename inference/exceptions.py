"""推理相关异常定义"""

class InferenceError(Exception):
    """推理基础异常"""
    pass


class ModelLoadError(InferenceError):
    """模型加载错误"""
    pass


class BackendNotAvailableError(InferenceError):
    """后端不可用"""
    pass


class InvalidModelFormatError(InferenceError):
    """模型格式错误"""
    pass
