"""
MTKMBOX 硬件控制 SDK
支持串口通信的键鼠控制
"""
from .mtkmbox_sdk import MTKMBOX, MTKMBOXError, MTKMBOXConnectionError, MTKMBOXCommandError

__version__ = '1.0.0'
__all__ = ['MTKMBOX', 'MTKMBOXError', 'MTKMBOXConnectionError', 'MTKMBOXCommandError']
