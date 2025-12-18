"""
异步脚本执行器 - 严格模式版
(移除自动切换逻辑，完全尊重 Lua 开发者的配置)
"""

import time
import traceback
from threading import Thread, Lock
from queue import Queue, Empty
from typing import Callable, Any, Dict, Optional
from enum import Enum

import utils


class ExecutionMode(Enum):
    """执行模式"""
    SYNC = "sync"    # 同步：阻塞主线程，保证时序（默认）
    ASYNC = "async"  # 异步：丢入线程池，不阻塞，用于耗时操作


class AsyncTask:
    """任务封装"""
    def __init__(self, script_name: str, event_name: str, callback: Callable, args: tuple):
        self.script_name = script_name
        self.event_name = event_name
        self.callback = callback
        self.args = args
        self.result = None
        self.error = None
        self.start_time = 0
        self.end_time = 0
        self.completed = False

    @property
    def execution_time(self) -> float:
        if self.end_time > 0:
            return self.end_time - self.start_time
        return 0


class AsyncScriptExecutor:
    """脚本执行器"""

    def __init__(self,
                 max_workers: int = 4,
                 verbose: bool = False):
        """
        Args:
            max_workers: 异步线程池大小
            verbose: 是否输出详细日志
        """
        self.max_workers = max_workers
        self.verbose = verbose

        # 任务队列
        self.task_queue = Queue()
        self.workers = []
        self.running = False

        # 性能统计
        self.stats_lock = Lock()
        self.execution_stats: Dict[str, Dict] = {}

        # ⚠️ 性能警告阈值 (仅记录日志，不改变行为)
        self.warn_threshold_ms = 10.0

        # 模式配置 {script_name: ExecutionMode}
        self.script_modes: Dict[str, ExecutionMode] = {}

        if self.verbose:
            utils.log("[AsyncExecutor] 执行器已初始化 (严格模式)")

    def start(self):
        """启动后台线程"""
        if self.running: return
        self.running = True
        for i in range(self.max_workers):
            worker = Thread(target=self._worker_loop, name=f"ScriptWorker-{i}", daemon=True)
            worker.start()
            self.workers.append(worker)

    def stop(self):
        """停止"""
        self.running = False
        self.task_queue.join()
        for worker in self.workers:
            if worker.is_alive():
                worker.join(timeout=1.0)
        self.workers.clear()

    def set_script_mode(self, script_name: str, mode: ExecutionMode):
        """设置脚本模式 (由 Lua 配置决定)"""
        # 如果配置为 AUTO，在这个版本中我们将其视为 SYNC（为了安全）
        if mode == "auto":
             mode = ExecutionMode.SYNC

        self.script_modes[script_name] = mode
        if self.verbose:
            utils.log(f"[AsyncExecutor] 脚本 {script_name} 模式设置为: {mode.value}")

    def execute(self,
                script_name: str,
                event_name: str,
                callback: Callable,
                args: tuple = (),
                force_mode: Optional[ExecutionMode] = None) -> Optional[Any]:
        """
        执行脚本
        严格遵循配置模式，不进行动态切换。
        """
        # 1. 获取模式 (默认为 SYNC，保证安全)
        mode = force_mode or self.script_modes.get(script_name, ExecutionMode.SYNC)

        # 2. 根据模式执行
        if mode == ExecutionMode.SYNC:
            return self._execute_sync(script_name, event_name, callback, args)
        else:
            self._execute_async(script_name, event_name, callback, args)
            return None

    def _execute_sync(self, script_name: str, event_name: str, callback: Callable, args: tuple) -> Any:
        """同步执行"""
        task = AsyncTask(script_name, event_name, callback, args)
        task.start_time = time.perf_counter()

        try:
            task.result = callback(*args)
        except Exception as e:
            task.error = e
            utils.log(f"[ScriptError] {script_name}.{event_name}: {e}")
            traceback.print_exc()
        finally:
            task.end_time = time.perf_counter()
            self._update_stats(task)

            # ⚠️ 性能警告：只警告，不干预
            exec_ms = task.execution_time * 1000
            if exec_ms > self.warn_threshold_ms and self.verbose:
                utils.log(f"⚠️ [性能警告] {script_name}.{event_name} 耗时 {exec_ms:.2f}ms (可能导致掉帧)")

        return task.result

    def _execute_async(self, script_name: str, event_name: str, callback: Callable, args: tuple):
        """异步执行"""
        task = AsyncTask(script_name, event_name, callback, args)
        self.task_queue.put(task)

    def _worker_loop(self):
        """后台线程循环"""
        while self.running:
            try:
                task = self.task_queue.get(timeout=0.1)
            except Empty:
                continue

            task.start_time = time.perf_counter()
            try:
                task.callback(*task.args)
            except Exception as e:
                utils.log(f"[AsyncError] {task.script_name}.{task.event_name}: {e}")
                traceback.print_exc()
            finally:
                task.end_time = time.perf_counter()
                self._update_stats(task)
                self.task_queue.task_done()

    def _update_stats(self, task: AsyncTask):
        """仅用于统计显示，不再影响逻辑"""
        with self.stats_lock:
            if task.script_name not in self.execution_stats:
                self.execution_stats[task.script_name] = {}
            if task.event_name not in self.execution_stats[task.script_name]:
                self.execution_stats[task.script_name][task.event_name] = {
                    'total_calls': 0, 'total_time': 0.0, 'max_time': 0.0, 'errors': 0
                }

            stats = self.execution_stats[task.script_name][task.event_name]
            time_spent = task.execution_time
            stats['total_calls'] += 1
            stats['total_time'] += time_spent
            stats['max_time'] = max(stats['max_time'], time_spent)
            if task.error: stats['errors'] += 1

    def get_stats(self, script_name: Optional[str] = None) -> Dict:
        with self.stats_lock:
            return self.execution_stats.get(script_name, {}) if script_name else self.execution_stats.copy()
    def print_stats(self):
        """打印性能统计（优化格式）"""
        with self.stats_lock:
            if not self.execution_stats:
                return

            utils.log("\n" + "=" * 60)
            utils.log("📊 脚本性能统计")
            utils.log("=" * 60)

            for script_name, events in self.execution_stats.items():
                # ⭐ 计算脚本总调用次数
                total_calls = sum(stats['total_calls'] for stats in events.values())

                utils.log(f"\n📜 {script_name} (总调用: {total_calls})")

                for event_name, stats in events.items():
                    avg_time = stats['total_time'] / stats['total_calls'] * 1000
                    max_time = stats['max_time'] * 1000
                    error_rate = stats['errors'] / stats['total_calls'] * 100 if stats['total_calls'] > 0 else 0

                    # ⭐ 只显示关键指标
                    utils.log(f"  └─ {event_name}: "
                              f"平均 {avg_time:.2f}ms | "
                              f"最大 {max_time:.2f}ms | "
                              f"调用 {stats['total_calls']} 次"
                              + (f" | 错误 {error_rate:.1f}%" if stats['errors'] > 0 else ""))

            utils.log("=" * 60 + "\n")
