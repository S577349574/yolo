"""
脚本管理器 - 负责脚本的加载、卸载、热重载和生命周期管理
每个脚本拥有独立的 Lua 运行时，实现完全隔离
"""

import os
import time
from typing import Dict, Set, Optional, List
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .script_engine import ScriptEngine
from .script_api import ScriptAPI
from config_manager import get_config
import utils


class ScriptFileHandler(FileSystemEventHandler):
    """监控脚本文件变化"""

    def __init__(self, manager):
        self.manager = manager
        self._debounce_timers = {}  # 防抖动
        self._debounce_delay = 0.5  # 500ms 防抖

    def on_modified(self, event):
        if event.is_directory or not event.src_path.endswith('.lua'):
            return

        script_path = event.src_path
        script_name = os.path.splitext(os.path.basename(script_path))[0]

        # 防抖动检查
        current_time = time.time()
        if script_name in self._debounce_timers:
            if current_time - self._debounce_timers[script_name] < self._debounce_delay:
                return

        self._debounce_timers[script_name] = current_time
        utils.log(f"[ScriptManager] 📝 检测到文件变化: {script_name}")

        # 热重载脚本
        self.manager.reload_script(script_name)


class ScriptManager:
    """
    脚本管理器 - 独立运行时架构

    特性：
    - 每个脚本拥有独立的 Lua 运行时
    - 完全隔离，无函数名冲突
    - 支持热重载
    - 支持启用/禁用控制
    """

    def __init__(self, script_api_factory, event_system, scripts_dir: str = "scripts"):
        """
        初始化脚本管理器

        Args:
            script_api_factory: ScriptAPI 工厂函数或类
            event_system: 事件系统实例
            scripts_dir: 脚本目录路径
        """
        self.script_api_factory = script_api_factory
        self.event_system = event_system
        self.scripts_dir = scripts_dir

        # 脚本引擎存储 {script_name: ScriptEngine}
        self.script_engines: Dict[str, ScriptEngine] = {}

        # 脚本 API 实例存储 {script_name: ScriptAPI}
        self.script_apis: Dict[str, ScriptAPI] = {}

        # 脚本元数据 {script_name: {path, loaded_time, enabled}}
        self.script_metadata: Dict[str, dict] = {}

        # 已启用的脚本集合
        self.enabled_scripts: Set[str] = set()

        # 文件监控
        self.observer: Optional[Observer] = None

        # 确保脚本目录存在
        os.makedirs(scripts_dir, exist_ok=True)

        # 启动文件监控
        self._start_file_watcher()

        utils.log(f"[ScriptManager] 初始化完成，脚本目录: {scripts_dir}")

    def _start_file_watcher(self):
        """启动文件监控"""
        try:
            self.observer = Observer()
            event_handler = ScriptFileHandler(self)
            self.observer.schedule(event_handler, self.scripts_dir, recursive=False)
            self.observer.start()
            utils.log("[ScriptManager] ✅ 文件监控已启动")
        except Exception as e:
            utils.log(f"[ScriptManager] ⚠️ 文件监控启动失败: {e}")

    def load_all_scripts(self):
        """加载所有脚本"""
        if not os.path.exists(self.scripts_dir):
            utils.log(f"[ScriptManager] ⚠️ 脚本目录不存在: {self.scripts_dir}")
            return

        # 获取所有 .lua 文件
        script_files = [
            f for f in os.listdir(self.scripts_dir)
            if f.endswith('.lua')
        ]

        if not script_files:
            utils.log("[ScriptManager] 未找到任何脚本文件")
            return

        utils.log(f"[ScriptManager] 开始加载 {len(script_files)} 个脚本...")

        # 加载每个脚本
        for script_file in script_files:
            script_path = os.path.join(self.scripts_dir, script_file)
            self.load_script(script_path)

    def load_script(self, script_path: str) -> bool:
        """
        加载单个脚本（独立运行时）

        Args:
            script_path: 脚本文件路径

        Returns:
            bool: 是否加载成功
        """
        script_name = os.path.splitext(os.path.basename(script_path))[0]

        try:
            # 如果脚本已存在，先卸载
            if script_name in self.script_engines:
                self.unload_script(script_name)

            # 🆕 创建独立的脚本引擎
            engine = ScriptEngine()

            # 🆕 创建独立的 API 实例
            script_api = self.script_api_factory()

            # 🆕 为引擎注册 API
            api_table = script_api.create_api_table(engine.lua)
            engine.register_api("api", api_table)

            # 读取脚本内容
            with open(script_path, 'r', encoding='utf-8') as f:
                script_code = f.read()

            # 执行脚本代码
            success = engine.execute_code(script_code, chunk_name=script_name)

            if not success:
                utils.log(f"[ScriptManager] ❌ 脚本执行失败: {script_name}")
                return False

            # 保存引擎和 API 实例
            self.script_engines[script_name] = engine
            self.script_apis[script_name] = script_api

            # 保存元数据
            self.script_metadata[script_name] = {
                "path": script_path,
                "loaded_time": time.time(),
                "enabled": False
            }

            utils.log(f"[ScriptManager] ✅ 脚本已加载: {script_name}")

            return True

        except Exception as e:
            utils.log(f"[ScriptManager] ❌ 加载脚本失败 {script_name}: {e}")
            import traceback
            utils.log(traceback.format_exc())
            return False

    def enable_script(self, script_name: str) -> bool:
        """
        启用脚本

        Args:
            script_name: 脚本名称

        Returns:
            bool: 是否成功启用
        """
        if script_name not in self.script_engines:
            utils.log(f"[ScriptManager] ⚠️ 脚本未加载: {script_name}")
            return False

        if script_name in self.enabled_scripts:
            utils.log(f"[ScriptManager] ⚠️ 脚本已启用: {script_name}")
            return True

        try:
            # 调用脚本的 onInit 函数
            engine = self.script_engines[script_name]
            engine.call_function("onInit")

            # 标记为已启用
            self.enabled_scripts.add(script_name)
            self.script_metadata[script_name]["enabled"] = True

            utils.log(f"[ScriptManager] ✅ 脚本已启用: {script_name}")
            return True

        except Exception as e:
            utils.log(f"[ScriptManager] ❌ 启用脚本失败 {script_name}: {e}")
            return False

    def disable_script(self, script_name: str) -> bool:
        """
        禁用脚本

        Args:
            script_name: 脚本名称

        Returns:
            bool: 是否成功禁用
        """
        if script_name not in self.enabled_scripts:
            return True

        try:
            # 调用脚本的 onCleanup 函数
            engine = self.script_engines[script_name]
            engine.call_function("onCleanup")

            # 移除启用标记
            self.enabled_scripts.discard(script_name)
            self.script_metadata[script_name]["enabled"] = False

            utils.log(f"[ScriptManager] ✅ 脚本已禁用: {script_name}")
            return True

        except Exception as e:
            utils.log(f"[ScriptManager] ❌ 禁用脚本失败 {script_name}: {e}")
            return False

    def unload_script(self, script_name: str):
        """
        卸载脚本

        Args:
            script_name: 脚本名称
        """
        # 先禁用
        if script_name in self.enabled_scripts:
            self.disable_script(script_name)

        # 清理资源
        if script_name in self.script_engines:
            del self.script_engines[script_name]

        if script_name in self.script_apis:
            del self.script_apis[script_name]

        if script_name in self.script_metadata:
            del self.script_metadata[script_name]

        utils.log(f"[ScriptManager] ✅ 脚本已卸载: {script_name}")

    def reload_script(self, script_name: str) -> bool:
        """
        热重载脚本

        Args:
            script_name: 脚本名称

        Returns:
            bool: 是否重载成功
        """
        if script_name not in self.script_metadata:
            utils.log(f"[ScriptManager] ⚠️ 脚本未加载，无法重载: {script_name}")
            return False

        # 记录是否启用
        was_enabled = script_name in self.enabled_scripts
        script_path = self.script_metadata[script_name]["path"]

        # 卸载旧脚本
        self.unload_script(script_name)

        # 重新加载
        success = self.load_script(script_path)

        if success and was_enabled:
            # 如果之前是启用的，重新启用
            self.enable_script(script_name)

        utils.log(f"[ScriptManager] ✅ 脚本已重载: {script_name}")
        return success

    def call_event(self, event_name: str, *args):
        """
        触发事件（调用所有已启用脚本的对应函数）

        Args:
            event_name: 事件名称（如 "onFrame"）
            *args: 传递给事件函数的参数
        """
        for script_name in list(self.enabled_scripts):
            try:
                engine = self.script_engines.get(script_name)
                if engine:
                    engine.call_function(event_name, *args)
            except Exception as e:
                utils.log(f"[ScriptManager] ⚠️ 脚本 {script_name} 事件 {event_name} 执行失败: {e}")

    def get_loaded_scripts(self) -> List[str]:
        """获取所有已加载的脚本名称"""
        return list(self.script_engines.keys())

    def get_enabled_scripts(self) -> List[str]:
        """获取所有已启用的脚本名称"""
        return list(self.enabled_scripts)

    def is_script_enabled(self, script_name: str) -> bool:
        """检查脚本是否已启用"""
        return script_name in self.enabled_scripts

    def cleanup(self):
        """清理所有资源"""
        utils.log("[ScriptManager] 开始清理...")

        # 禁用所有脚本
        for script_name in list(self.enabled_scripts):
            self.disable_script(script_name)

        # 停止文件监控
        if self.observer:
            self.observer.stop()
            self.observer.join()

        # 清理所有引擎
        self.script_engines.clear()
        self.script_apis.clear()
        self.script_metadata.clear()

        utils.log("[ScriptManager] ✅ 清理完成")
