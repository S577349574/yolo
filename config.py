"""全局配置（兼容旧代码）"""
from config_manager import load_config

# 加载配置（但不再定义常量，这里仅供导入）
# 注意：常量现在在运行时通过 get_config 获取
load_config()  # 可选：如果需要在导入时加载，但最好在 main.py 中调用
