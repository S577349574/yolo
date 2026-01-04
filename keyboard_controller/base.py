"""键盘控制器抽象基类"""

from abc import ABC, abstractmethod

import utils


class KeyboardControllerBase(ABC):
    """键盘控制器抽象基类"""

    def __init__(self, debug_mode: bool = False):
        """
        初始化键盘控制器

        Args:
            debug_mode: 调试模式
        """
        self.debug_mode = debug_mode
        self._is_initialized = False

    # ==================== 抽象方法（子类必须实现）====================

    @abstractmethod
    def get_mode(self) -> str:
        """
        获取控制器模式名称

        Returns:
            str: 模式名称（如 "WinAPI", "Makcu"）
        """
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """
        检查控制器是否就绪

        Returns:
            bool: 是否就绪
        """
        pass

    @abstractmethod
    def _send_key_down(self, key: str) -> bool:
        """
        发送按键按下指令（底层实现）

        Args:
            key: 按键名称或 HID 码

        Returns:
            bool: 操作是否成功
        """
        pass

    @abstractmethod
    def _send_key_up(self, key: str) -> bool:
        """
        发送按键释放指令（底层实现）

        Args:
            key: 按键名称或 HID 码

        Returns:
            bool: 操作是否成功
        """
        pass

    @abstractmethod
    def _send_key_press(self, key: str, hold_ms: int = 0, rand_ms: int = 0) -> bool:
        """
        发送按键点击指令（底层实现）

        Args:
            key: 按键名称或 HID 码
            hold_ms: 按住时长（毫秒），0=随机35-75ms
            rand_ms: 随机偏移量（毫秒）

        Returns:
            bool: 操作是否成功
        """
        pass

    @abstractmethod
    def _send_string(self, text: str) -> bool:
        """
        发送字符串输入指令（底层实现）

        Args:
            text: 要输入的文本

        Returns:
            bool: 操作是否成功
        """
        pass

    @abstractmethod
    def _is_key_down(self, key: str) -> bool:
        """
        查询按键是否按下（底层实现）

        Args:
            key: 按键名称

        Returns:
            bool: 是否按下
        """
        pass

    @abstractmethod
    def _do_initialize(self) -> bool:
        """
        初始化键盘控制器（底层实现）

        Returns:
            bool: 初始化是否成功
        """
        pass

    @abstractmethod
    def _do_close(self):
        """清理资源（底层实现）"""
        pass

    # ==================== 公共方法（通用逻辑）====================

    def initialize(self) -> bool:
        """
        初始化键盘控制器

        Returns:
            bool: 初始化是否成功
        """
        if self._is_initialized:
            utils.log(f"[{self.get_mode()}Keyboard] 已初始化，跳过")
            return True

        utils.log(f"[{self.get_mode()}Keyboard] 正在初始化...")

        if not self._do_initialize():
            utils.log(f"[{self.get_mode()}Keyboard] ❌ 初始化失败")
            return False

        self._is_initialized = True
        utils.log(f"[{self.get_mode()}Keyboard] ✅ 初始化成功")
        return True

    def press(self, key: str, hold_ms: int = 0, rand_ms: int = 0) -> bool:
        """
        按下并释放按键

        Args:
            key: 按键名称（'a', 'enter', 'ctrl' 等）
            hold_ms: 按住时长（毫秒），0=随机35-75ms
            rand_ms: 随机偏移量（毫秒）

        Returns:
            bool: 操作是否成功
        """
        if not self.is_ready():
            if self.debug_mode:
                utils.log(f"[{self.get_mode()}Keyboard] 控制器未就绪")
            return False

        return self._send_key_press(key, hold_ms, rand_ms)

    def down(self, key: str) -> bool:
        """
        按下按键（不释放）

        Args:
            key: 按键名称

        Returns:
            bool: 操作是否成功
        """
        if not self.is_ready():
            return False

        return self._send_key_down(key)

    def up(self, key: str) -> bool:
        """
        释放按键

        Args:
            key: 按键名称

        Returns:
            bool: 操作是否成功
        """
        if not self.is_ready():
            return False

        return self._send_key_up(key)

    def type_string(self, text: str) -> bool:
        """
        输入字符串（自动处理大小写和符号）

        Args:
            text: 要输入的文本（ASCII，最多256字符）

        Returns:
            bool: 操作是否成功
        """
        if not self.is_ready():
            return False

        if len(text) > 256:
            utils.log(f"[{self.get_mode()}Keyboard] 警告: 文本超过256字符，将被截断")
            text = text[:256]

        return self._send_string(text)

    def combo(self, *keys: str, hold_ms: int = 50) -> bool:
        """
        按下组合键（如 Ctrl+C, Alt+F4）

        Args:
            *keys: 按键序列（从左到右按下，从右到左释放）
            hold_ms: 最后一个键的按住时长

        Example:
            combo('ctrl', 'c')           # Ctrl+C
            combo('ctrl', 'shift', 's')  # Ctrl+Shift+S

        Returns:
            bool: 操作是否成功
        """
        if not self.is_ready():
            return False

        if len(keys) == 0:
            return False

        try:
            # 按下所有修饰键
            for key in keys[:-1]:
                if not self.down(key):
                    return False
                import time
                time.sleep(0.01)  # 10ms 延迟

            # 按下并释放最后一个键
            if not self.press(keys[-1], hold_ms):
                return False

            # 释放修饰键（逆序）
            for key in reversed(keys[:-1]):
                if not self.up(key):
                    return False
                import time
                time.sleep(0.01)

            return True

        except Exception as e:
            if self.debug_mode:
                utils.log(f"[{self.get_mode()}Keyboard] 组合键失败: {e}")
            return False

    def is_key_down(self, key: str) -> bool:
        """
        查询按键是否按下

        Args:
            key: 按键名称

        Returns:
            bool: 是否按下
        """
        if not self.is_ready():
            return False

        return self._is_key_down(key)

    def reset(self) -> bool:
        """
        清除键盘状态（释放所有按键）

        Returns:
            bool: 操作是否成功
        """
        if not self.is_ready():
            return False

        # 子类可以重写此方法提供专门的重置逻辑
        utils.log(f"[{self.get_mode()}Keyboard] 重置键盘状态")
        return True

    def close(self):
        """清理资源"""
        if not self._is_initialized:
            return
 
        utils.log(f"[{self.get_mode()}Keyboard] 正在清理资源...")
        self._do_close()
        self._is_initialized = False
        utils.log(f"[{self.get_mode()}Keyboard] ✅ 资源已清理")

    def __del__(self):
        """析构函数"""
        self.close()
