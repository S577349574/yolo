"""按键监控抽象基类（新方案：按键绑定参数组 + 触发逻辑，不再使用 ENABLE_*_MONITOR）"""

from abc import ABC, abstractmethod
from threading import Thread, Event
from typing import Dict, Optional, Callable, Any, Tuple, List
import time
import utils


class KeyMonitorBase(ABC):
    """
    新方案说明：

    - 逻辑触发由 KEY_PROFILE_BINDINGS[key].trigger 决定
    - 参数组切换由 KEY_PROFILE_BINDINGS[key].profile + mode(hold/toggle) 决定
    - hold：按住期间临时切 profile；松开后恢复(toggle/previous/fallback)
    - toggle：按下切到指定 profile 并保持（不会再按一次切回），但逻辑触发仍是按住语义（按下触发，松开释放）
    """

    def __init__(
            self,
            app_state,
            # 物理层：是否捕获该按键（工厂可以强制全 True）
            enable_left: bool = False,
            enable_right: bool = True,
            enable_mouse4: bool = False,
            enable_mouse5: bool = False,
            enable_auto_fire: bool = False,
            poll_interval: float = 0.05,
    ):
        self.app_state = app_state

        # 物理捕获开关（底层是否读取该键状态）
        self.enable_left = enable_left
        self.enable_right = enable_right
        self.enable_mouse4 = enable_mouse4
        self.enable_mouse5 = enable_mouse5

        self.enable_auto_fire = enable_auto_fire
        self.poll_interval = poll_interval

        # 线程控制
        self._stop_event = Event()
        self._monitor_thread: Optional[Thread] = None
        self._is_running = False

        # 物理状态缓存（用于变化检测）
        self._last_left_state = False
        self._last_right_state = False
        self._last_mouse4_state = False
        self._last_mouse5_state = False

        # 逻辑触发状态缓存（避免重复触发）
        self._logic_left_state = False
        self._logic_right_state = False
        self._logic_mouse4_state = False
        self._logic_mouse5_state = False

        # 回调函数（逻辑触发事件）
        self._on_left_press: Optional[Callable] = None
        self._on_left_release: Optional[Callable] = None
        self._on_right_press: Optional[Callable] = None
        self._on_right_release: Optional[Callable] = None
        self._on_mouse4_press: Optional[Callable] = None
        self._on_mouse4_release: Optional[Callable] = None
        self._on_mouse5_press: Optional[Callable] = None
        self._on_mouse5_release: Optional[Callable] = None

        # ============ 参数组绑定系统状态 ============
        self._toggle_selected_profile: Optional[str] = None
        self._hold_override_active: bool = False
        self._hold_prev_profile: Optional[str] = None
        self._active_profile_cache: Optional[str] = None
        # 初始化缓存为当前激活参数组（可选）
        try:
            from config.config_manager import get_active_profile
            self._active_profile_cache = get_active_profile()
        except Exception:
            self._active_profile_cache = None

    # ==================== 抽象方法 ====================

    @abstractmethod
    def is_key_pressed(self, key: str) -> bool:
        """检查按键是否按下"""
        raise NotImplementedError

    @abstractmethod
    def get_button_states(self) -> Dict[str, bool]:
        """获取所有鼠标按键状态"""
        raise NotImplementedError

    @abstractmethod
    def _initialize(self) -> bool:
        """初始化监控器（子类实现）"""
        raise NotImplementedError

    @abstractmethod
    def _cleanup(self):
        """清理资源（子类实现）"""
        raise NotImplementedError

    # ==================== 公共方法 ====================

    def start(self) -> bool:
        """启动监控"""
        if self._is_running:
            utils.log("[KeyMonitor] 监控已在运行")
            return True

        if not self._initialize():
            utils.log("[KeyMonitor] 初始化失败")
            return False

        self._stop_event.clear()
        self._monitor_thread = Thread(
            target=self._monitor_loop,
            daemon=True,
            name="KeyMonitorThread"
        )
        self._monitor_thread.start()
        self._is_running = True

        self._print_config()
        utils.log("[KeyMonitor] 监控已启动")
        return True

    def stop(self):
        """停止监控"""
        if not self._is_running:
            return

        utils.log("[KeyMonitor] 正在停止监控...")
        self._stop_event.set()

        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)
            if self._monitor_thread.is_alive():
                utils.log("[KeyMonitor] 监控线程未在超时内退出")

        self._cleanup()
        self._is_running = False
        utils.log("[KeyMonitor] 监控已停止")

    def is_running(self) -> bool:
        return self._is_running

    # ==================== 回调注册 ====================

    def on_left_press(self, callback: Callable):
        self._on_left_press = callback

    def on_left_release(self, callback: Callable):
        self._on_left_release = callback

    def on_right_press(self, callback: Callable):
        self._on_right_press = callback

    def on_right_release(self, callback: Callable):
        self._on_right_release = callback

    def on_mouse4_press(self, callback: Callable):
        self._on_mouse4_press = callback

    def on_mouse4_release(self, callback: Callable):
        self._on_mouse4_release = callback

    def on_mouse5_press(self, callback: Callable):
        self._on_mouse5_press = callback

    def on_mouse5_release(self, callback: Callable):
        self._on_mouse5_release = callback

    # ==================== 绑定配置读取/解析 ====================

    def _get_binding_config(self) -> Tuple[Dict[str, Any], str, List[str], str, str, bool]:
        """
        Returns:
            bindings, default_mode, priority, fallback_profile, hold_policy, enabled_binding
        """
        try:
            from config.config_manager import get_config
            enabled = bool(get_config("ENABLE_KEY_PROFILE_BINDING", True))
            bindings = get_config("KEY_PROFILE_BINDINGS", {}) or {}
            default_mode = get_config("KEY_PROFILE_DEFAULT_MODE", "hold")
            priority = get_config("KEY_PROFILE_PRIORITY", ["left", "right", "mouse5", "mouse4"]) or []
            fallback = get_config("KEY_PROFILE_FALLBACK", "default")
            policy = get_config("HOLD_FALLBACK_POLICY", "previous")
            return bindings, default_mode, priority, fallback, policy, enabled
        except Exception:
            return {}, "hold", ["left", "right", "mouse5", "mouse4"], "default", "previous", True

    def _parse_binding(self, val: Any, default_mode: str) -> Optional[Dict[str, Any]]:
        """
        兼容两种：
          - "mouse4": "profileA"
          - "mouse4": {"profile": "profileA", "mode": "hold/toggle", "trigger": true/false}
        默认 trigger=True（你希望“按住就同时切参数并触发逻辑”）
        """
        if isinstance(val, str):
            return {"profile": val, "mode": default_mode, "trigger": True}

        if isinstance(val, dict):
            profile = val.get("profile")
            mode = val.get("mode", default_mode)
            trigger = val.get("trigger", True)
            return {"profile": profile, "mode": mode, "trigger": bool(trigger)}

        return None

    def _get_binding_for_key(self, key_name: str) -> Optional[Dict[str, Any]]:
        bindings, default_mode, _, _, _, enabled = self._get_binding_config()
        if not enabled or not bindings:
            return None
        return self._parse_binding(bindings.get(key_name), default_mode)

    # ==================== profile 切换（绑定层） ====================

    def _profile_exists(self, name: str) -> bool:
        try:
            from config.config_manager import list_profiles
            return bool(name) and (name in list_profiles())
        except Exception:
            return False

    def _switch_profile(self, name: str):
        """切换激活 profile（带缓存，避免重复 set）"""
        if not name:
            return
        if not self._profile_exists(name):
            return
        if self._active_profile_cache == name:
            return

        try:
            from config.config_manager import set_active_profile
            if set_active_profile(name):
                self._active_profile_cache = name
                utils.log(f"[KeyMonitor] 参数组切换 -> {name}")
        except Exception as e:
            utils.log(f"[KeyMonitor] 参数组切换失败: {e}")

    def _handle_toggle_press(self, key_name: str, binding: Dict[str, Any]):
        """toggle：按下切到指定 profile 并保持（不反向切回）"""
        if binding.get("mode") != "toggle":
            return
        prof = binding.get("profile")
        if not prof or not self._profile_exists(prof):
            return
        self._toggle_selected_profile = prof
        self._switch_profile(prof)

    def _evaluate_hold_profiles(self) -> bool:
        """
        hold：找当前按下的最高优先级 hold 键并切换
        返回：是否存在任何 hold 键按下并生效
        """
        bindings, default_mode, priority, _, _, enabled = self._get_binding_config()
        if not enabled or not bindings:
            return False

        try:
            for key in priority:
                b = self._parse_binding(bindings.get(key), default_mode)
                if not b:
                    continue
                if b.get("mode") != "hold":
                    continue

                prof = b.get("profile")
                if not prof or not self._profile_exists(prof):
                    continue

                if self.is_key_pressed(key):
                    # 第一次进入 hold，记录进入前 profile
                    if not self._hold_override_active:
                        try:
                            from config.config_manager import get_active_profile
                            self._hold_prev_profile = get_active_profile()
                        except Exception:
                            self._hold_prev_profile = None
                        self._hold_override_active = True

                    self._switch_profile(prof)
                    return True

            return False
        except Exception as e:
            utils.log(f"[KeyMonitor] hold 评估异常: {e}")
            return False

    def _handle_hold_release(self):
        """
        任意相关键释放后调用：
          1) 若还有 hold 键按下 -> 切到最高优先级 hold
          2) 否则 -> 恢复 toggle；若没有 toggle -> previous/fallback
        """
        _, _, _, fallback, policy, enabled = self._get_binding_config()
        if not enabled:
            return

        # 仍有 hold 按下就继续保持 hold
        if self._evaluate_hold_profiles():
            return

        # 没有 hold 了
        self._hold_override_active = False

        # 优先恢复 toggle 选择
        if self._toggle_selected_profile and self._profile_exists(self._toggle_selected_profile):
            self._switch_profile(self._toggle_selected_profile)
            return

        # 再按策略回退
        if policy == "previous" and self._hold_prev_profile and self._profile_exists(self._hold_prev_profile):
            self._switch_profile(self._hold_prev_profile)
        else:
            if self._profile_exists(fallback):
                self._switch_profile(fallback)
            else:
                self._switch_profile("default")

    # ==================== 逻辑触发（由 binding.trigger 控制） ====================

    def _recalc_mouse_active(self):
        """
        mouse_active 只由 trigger=true 的绑定键决定：
        只要有任一 trigger 键当前按住 -> mouse_active=True
        """
        try:
            bindings, default_mode, _, _, _, enabled = self._get_binding_config()
            if not enabled or not bindings:
                self.app_state.set_mouse_active(False)
                return

            # 只检查我们支持的几个键（你需要更多键可扩展）
            keys = ["left", "right", "mouse4", "mouse5"]
            for k in keys:
                b = self._parse_binding(bindings.get(k), default_mode) if bindings.get(k) is not None else None
                if not b:
                    continue
                if not b.get("trigger", True):
                    continue
                if self.is_key_pressed(k):
                    self.app_state.set_mouse_active(True)
                    return

            self.app_state.set_mouse_active(False)
        except Exception:
            # 最保守兜底
            self.app_state.set_mouse_active(False)

    def _trigger_press(self, key_name: str):
        """触发对应逻辑 press（只触发一次）"""
        if key_name == "left":
            if self._logic_left_state:
                return
            self._logic_left_state = True
            self.app_state.set_left_pressed(True)
            self.app_state.set_mouse_active(True)
            if self._on_left_press:
                self._on_left_press()
            return

        if key_name == "right":
            if self._logic_right_state:
                return
            self._logic_right_state = True
            self.app_state.set_right_pressed(True)
            self.app_state.set_mouse_active(True)
            if self._on_right_press:
                self._on_right_press()
            return

        if key_name == "mouse4":
            if self._logic_mouse4_state:
                return
            self._logic_mouse4_state = True
            self.app_state.set_mouse_active(True)
            if self._on_mouse4_press:
                self._on_mouse4_press()
            utils.log("[KeyMonitor] 侧键4 按下")
            return

        if key_name == "mouse5":
            if self._logic_mouse5_state:
                return
            self._logic_mouse5_state = True
            self.app_state.set_mouse_active(True)
            if self._on_mouse5_press:
                self._on_mouse5_press()
            utils.log("[KeyMonitor] 侧键5 按下")
            return

    def _trigger_release(self, key_name: str):
        """触发对应逻辑 release（只触发一次），并重算 mouse_active"""
        if key_name == "left":
            if not self._logic_left_state:
                return
            self._logic_left_state = False
            self.app_state.set_left_pressed(False)
            self._recalc_mouse_active()
            if self._on_left_release:
                self._on_left_release()
            return

        if key_name == "right":
            if not self._logic_right_state:
                return
            self._logic_right_state = False
            self.app_state.set_right_pressed(False)
            self._recalc_mouse_active()
            if self._on_right_release:
                self._on_right_release()
            return

        if key_name == "mouse4":
            if not self._logic_mouse4_state:
                return
            self._logic_mouse4_state = False
            self._recalc_mouse_active()
            if self._on_mouse4_release:
                self._on_mouse4_release()
            utils.log("[KeyMonitor] 侧键4 释放")
            return

        if key_name == "mouse5":
            if not self._logic_mouse5_state:
                return
            self._logic_mouse5_state = False
            self._recalc_mouse_active()
            if self._on_mouse5_release:
                self._on_mouse5_release()
            utils.log("[KeyMonitor] 侧键5 释放")
            return

    # ==================== 物理事件入口（按键变化时调用） ====================

    def _on_physical_press(self, key_name: str):
        """
        物理按下时：
          1) toggle（如有）
          2) hold 评估（hold 会覆盖 toggle）
          3) 若 trigger=true -> 触发逻辑 press
        """
        b = self._get_binding_for_key(key_name)
        if not b:
            return

        self._handle_toggle_press(key_name, b)
        self._evaluate_hold_profiles()
        if b.get("trigger", True):
            self._trigger_press(key_name)


    def _on_physical_release(self, key_name: str):
        """
        物理释放时：
          1) 若 trigger=true -> 触发逻辑 release
          2) hold release 回退/评估（可能恢复 toggle/previous/fallback）
        """
        b = self._get_binding_for_key(key_name)

        # 先释放逻辑（只对 trigger=true 的绑定键生效）
        if b and b.get("trigger", True):
            self._trigger_release(key_name)

        self._handle_hold_release()

    # ==================== 监控循环 ====================

    def _monitor_loop(self):
        utils.log("\n[按键监控] 已启动全局监听(物理捕获层)")
        utils.log("  F12：退出程序")
        utils.log("  触发逻辑/参数组切换均由 KEY_PROFILE_BINDINGS 控制（不再使用 ENABLE_*_MONITOR）")

        while not self._stop_event.is_set():
            try:
                # F12 退出
                if self.is_key_pressed('f12'):
                    self.app_state.request_exit()
                    break

                # left
                if self.enable_left:
                    pressed = self.is_key_pressed('left')
                    if pressed != self._last_left_state:
                        self._last_left_state = pressed
                        if pressed:
                            self._on_physical_press("left")
                        else:
                            self._on_physical_release("left")

                # right
                if self.enable_right:
                    pressed = self.is_key_pressed('right')
                    if pressed != self._last_right_state:
                        self._last_right_state = pressed
                        if pressed:
                            self._on_physical_press("right")
                        else:
                            self._on_physical_release("right")

                # mouse4
                if self.enable_mouse4:
                    pressed = self.is_key_pressed('mouse4')
                    if pressed != self._last_mouse4_state:
                        self._last_mouse4_state = pressed
                        if pressed:
                            self._on_physical_press("mouse4")
                        else:
                            self._on_physical_release("mouse4")

                # mouse5
                if self.enable_mouse5:
                    pressed = self.is_key_pressed('mouse5')
                    if pressed != self._last_mouse5_state:
                        self._last_mouse5_state = pressed
                        if pressed:
                            self._on_physical_press("mouse5")
                        else:
                            self._on_physical_release("mouse5")

                time.sleep(self.poll_interval)

            except Exception as e:
                utils.log(f"[KeyMonitor] 监控错误: {e}")
                break

    def _print_config(self):
        """打印配置信息（帮助排查）"""
        utils.log("[KeyMonitor] 配置：")
        utils.log(
            f"  - 物理捕获: left={self.enable_left}, right={self.enable_right}, "
            f"mouse4={self.enable_mouse4}, mouse5={self.enable_mouse5}"
        )
        try:
            from config.config_manager import get_config
            utils.log(f"  - ENABLE_KEY_PROFILE_BINDING={get_config('ENABLE_KEY_PROFILE_BINDING', True)}")
            utils.log(f"  - KEY_PROFILE_DEFAULT_MODE={get_config('KEY_PROFILE_DEFAULT_MODE', 'hold')}")
            utils.log(f"  - KEY_PROFILE_PRIORITY={get_config('KEY_PROFILE_PRIORITY', ['right','mouse5','mouse4'])}")
            utils.log(f"  - HOLD_FALLBACK_POLICY={get_config('HOLD_FALLBACK_POLICY', 'previous')}")
        except Exception:
            pass
