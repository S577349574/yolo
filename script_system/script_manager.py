"""
脚本管理器 - 优化日志输出版本
"""

import os
import time
from typing import Dict, Set, Optional, List
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .script_engine import ScriptEngine
from .script_api import ScriptAPI
from .async_script_executor import AsyncScriptExecutor, ExecutionMode
from config_manager import get_config
import utils


class ScriptFileHandler(FileSystemEventHandler):
    """监控脚本文件变化"""

    def __init__(self, manager):
        self.manager = manager
        self._debounce_timers = {}
        self._debounce_delay = 0.5

    def on_modified(self, event):
        if event.is_directory or not event.src_path.endswith('.lua'):
            return

        script_path = event.src_path
        script_name = os.path.splitext(os.path.basename(script_path))[0]

        current_time = time.time()
        if script_name in self._debounce_timers:
            if current_time - self._debounce_timers[script_name] < self._debounce_delay:
                return

        self._debounce_timers[script_name] = current_time
        utils.log(f"[脚本热重载] 📝 {script_name}")

        self.manager.reload_script(script_name)


class ScriptManager:
    """脚本管理器 - 独立运行时 + 异步执行"""

    def __init__(self, script_api_factory, event_system, scripts_dir="scripts"):
        self.script_api_factory = script_api_factory
        self.event_system = event_system
        self.scripts_dir = scripts_dir

        self.script_engines: Dict[str, ScriptEngine] = {}
        self.script_apis: Dict[str, ScriptAPI] = {}
        self.script_metadata: Dict[str, dict] = {}
        self.enabled_scripts: Set[str] = set()
        self.observer: Optional[Observer] = None

        # ⭐ 读取日志配置
        self.verbose_logging = get_config("SCRIPT_VERBOSE_LOGGING", False)

        # ⭐ 创建异步执行器（静默初始化）
        self.async_executor = AsyncScriptExecutor(
            max_workers=get_config("SCRIPT_MAX_WORKERS", 4),
            sync_threshold_ms=get_config("SCRIPT_SYNC_THRESHOLD_MS", 5.0),
            auto_switch_enabled=get_config("SCRIPT_AUTO_ASYNC", True),
            verbose=self.verbose_logging  # 传递日志配置
        )

        self.async_executor.start()

        os.makedirs(scripts_dir, exist_ok=True)
        self._start_file_watcher()

        # ⭐ 只输出一条初始化日志
        if self.verbose_logging:
            utils.log(f"[ScriptManager] 初始化完成，脚本目录: {scripts_dir}")

    def _start_file_watcher(self):
        """启动文件监控（静默）"""
        try:
            self.observer = Observer()
            event_handler = ScriptFileHandler(self)
            self.observer.schedule(event_handler, self.scripts_dir, recursive=False)
            self.observer.start()

            if self.verbose_logging:
                utils.log("[ScriptManager] ✅ 文件监控已启动")
        except Exception as e:
            utils.log(f"[ScriptManager] ⚠️ 文件监控启动失败: {e}")

    def load_all_scripts(self):
        """加载所有脚本（优化输出）"""
        if not os.path.exists(self.scripts_dir):
            utils.log(f"⚠️ 脚本目录不存在: {self.scripts_dir}")
            return

        script_files = [f for f in os.listdir(self.scripts_dir) if f.endswith('.lua')]

        if not script_files:
            utils.log("ℹ️ 未找到任何脚本文件")
            return

        # ⭐ 统一输出加载进度
        utils.log(f"📂 正在加载 {len(script_files)} 个脚本...")

        success_count = 0
        failed_scripts = []

        for script_file in script_files:
            script_path = os.path.join(self.scripts_dir, script_file)
            if self.load_script(script_path):
                success_count += 1
            else:
                failed_scripts.append(os.path.splitext(script_file)[0])

        # ⭐ 输出汇总结果
        if success_count == len(script_files):
            utils.log(f"✅ 所有脚本加载成功 ({success_count}/{len(script_files)})")
        else:
            utils.log(f"⚠️ 加载完成: {success_count}/{len(script_files)} 个成功")
            if failed_scripts:
                utils.log(f"   失败的脚本: {', '.join(failed_scripts)}")

    def load_script(self, script_path: str) -> bool:
        """加载单个脚本（静默加载）"""
        script_name = os.path.splitext(os.path.basename(script_path))[0]

        try:
            if script_name in self.script_engines:
                self.unload_script(script_name)

            # ⭐ 静默创建组件
            engine = ScriptEngine(verbose=self.verbose_logging)
            script_api = self.script_api_factory()
            api_table = script_api.create_api_table(engine.lua)

            engine.script_name = script_name
            engine.register_api("api", api_table)

            with open(script_path, 'r', encoding='utf-8') as f:
                script_code = f.read()

            success = engine.execute_code(script_code, chunk_name=script_name)

            if not success:
                utils.log(f"   ❌ {script_name} - 执行失败")
                return False

            self.script_engines[script_name] = engine
            self.script_apis[script_name] = script_api

            # ⭐ 读取执行模式（静默）
            execution_mode = ExecutionMode.AUTO
            try:
                config_func = engine.lua.globals().getScriptConfig
                if config_func:
                    config = config_func()
                    mode_str = config.get("execution_mode", "auto")

                    mode_map = {
                        "sync": ExecutionMode.SYNC,
                        "async": ExecutionMode.ASYNC,
                        "auto": ExecutionMode.AUTO
                    }

                    execution_mode = mode_map.get(mode_str, ExecutionMode.AUTO)
                    self.async_executor.set_script_mode(script_name, execution_mode)
            except:
                pass

            self.script_metadata[script_name] = {
                "path": script_path,
                "loaded_time": time.time(),
                "enabled": False,
                "execution_mode": execution_mode
            }

            # ⭐ 只在详细模式下输出单个脚本日志
            if self.verbose_logging:
                utils.log(f"   ✅ {script_name} ({execution_mode.value})")

            return True

        except Exception as e:
            utils.log(f"   ❌ {script_name} - {str(e)[:50]}")
            if self.verbose_logging:
                import traceback
                utils.log(traceback.format_exc())
            return False

    def enable_script(self, script_name: str) -> bool:
        """启用脚本"""
        if script_name not in self.script_engines:
            utils.log(f"⚠️ 脚本未加载: {script_name}")
            return False

        if script_name in self.enabled_scripts:
            return True

        try:
            engine = self.script_engines[script_name]
            engine.call_function("onInit")

            self.enabled_scripts.add(script_name)
            self.script_metadata[script_name]["enabled"] = True

            # ⭐ 简化日志（只输出关键信息）
            mode = self.script_metadata[script_name]["execution_mode"].value
            utils.log(f"   🟢 {script_name} ({mode} 模式)")

            return True

        except Exception as e:
            utils.log(f"   ❌ {script_name} 启用失败: {e}")
            return False

    def disable_script(self, script_name: str) -> bool:
        """禁用脚本"""
        if script_name not in self.enabled_scripts:
            return True

        try:
            engine = self.script_engines[script_name]
            engine.call_function("onCleanup")

            self.enabled_scripts.discard(script_name)
            self.script_metadata[script_name]["enabled"] = False

            if self.verbose_logging:
                utils.log(f"   ⭕ {script_name} 已禁用")

            return True

        except Exception as e:
            utils.log(f"   ❌ {script_name} 禁用失败: {e}")
            return False

    def unload_script(self, script_name: str):
        """卸载脚本（静默）"""
        if script_name in self.enabled_scripts:
            self.disable_script(script_name)

        if script_name in self.script_engines:
            del self.script_engines[script_name]

        if script_name in self.script_apis:
            del self.script_apis[script_name]

        if script_name in self.script_metadata:
            del self.script_metadata[script_name]

    def reload_script(self, script_name: str) -> bool:
        """热重载脚本"""
        if script_name not in self.script_metadata:
            return False

        was_enabled = script_name in self.enabled_scripts
        script_path = self.script_metadata[script_name]["path"]

        self.unload_script(script_name)
        success = self.load_script(script_path)

        if success and was_enabled:
            self.enable_script(script_name)

        if success:
            utils.log(f"   ✅ {script_name} 已重载")

        return success

    def call_event(self, event_name: str, *args):
        """触发事件（静默执行）"""
        for script_name in list(self.enabled_scripts):
            try:
                engine = self.script_engines.get(script_name)
                if not engine:
                    continue

                self.async_executor.execute(
                    script_name=script_name,
                    event_name=event_name,
                    callback=lambda e=engine, fn=event_name, a=args: e.call_function(fn, *a),
                    args=()
                )

            except Exception as e:
                if self.verbose_logging:
                    utils.log(f"⚠️ {script_name}.{event_name} 执行失败: {e}")

    def get_loaded_scripts(self) -> List[str]:
        return list(self.script_engines.keys())

    def get_enabled_scripts(self) -> List[str]:
        return list(self.enabled_scripts)

    def is_script_enabled(self, script_name: str) -> bool:
        return script_name in self.enabled_scripts

    def get_execution_stats(self, script_name: Optional[str] = None) -> Dict:
        return self.async_executor.get_stats(script_name)

    def print_performance_report(self):
        """打印性能报告（如果有数据）"""
        stats = self.async_executor.get_stats()
        if stats:
            self.async_executor.print_stats()

    def stop(self):
        self.cleanup()

    def cleanup(self):
        """清理资源（优化输出）"""
        utils.log("🧹 正在清理脚本系统...")

        # 禁用所有脚本（静默）
        for script_name in list(self.enabled_scripts):
            self.disable_script(script_name)

        # 停止异步执行器
        self.async_executor.stop()

        # 只在有性能数据时才打印报告
        if self.verbose_logging or get_config("SCRIPT_SHOW_STATS_ON_EXIT", False):
            self.print_performance_report()

        # 停止文件监控
        if self.observer:
            self.observer.stop()
            self.observer.join()

        self.script_engines.clear()
        self.script_apis.clear()
        self.script_metadata.clear()

        utils.log("✅ 脚本系统已清理")
