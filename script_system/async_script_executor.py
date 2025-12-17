"""
异步脚本执行器 - 支持同步/异步双模式
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
    SYNC = "sync"  # 同步（主线程）
    ASYNC = "async"  # 异步（线程池）
    AUTO = "auto"  # 自动（根据耗时切换）


class AsyncTask:
    """异步任务"""

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
        """执行时间（秒）"""
        if self.end_time > 0:
            return self.end_time - self.start_time
        return 0


class AsyncScriptExecutor:
    """异步脚本执行器"""

    def __init__(self,
                 max_workers: int = 4,
                 sync_threshold_ms: float = 5.0,
                 auto_switch_enabled: bool = True,
                 verbose: bool = False):  # ⭐ 新增参数
        """
        初始化执行器

        Args:
            max_workers: 最大工作线程数
            sync_threshold_ms: 同步执行阈值（超过此时间自动切换到异步）
            auto_switch_enabled: 是否启用自动切换
        """
        self.max_workers = max_workers
        self.sync_threshold_ms = sync_threshold_ms
        self.auto_switch_enabled = auto_switch_enabled
        self.verbose = verbose  # ⭐ 保存配置

        # 任务队列
        self.task_queue = Queue()

        # 工作线程池
        self.workers = []
        self.running = False

        # 性能统计
        self.stats_lock = Lock()
        self.execution_stats: Dict[str, Dict] = {}  # {script_name: {event_name: stats}}

        # 模式配置
        self.script_modes: Dict[str, ExecutionMode] = {}  # {script_name: mode}

        # ⭐ 只在详细模式下输出初始化日志
        if self.verbose:
            utils.log("[AsyncExecutor] 异步执行器已初始化")
            utils.log(f"  工作线程数: {max_workers}")
            utils.log(f"  同步阈值: {sync_threshold_ms}ms")
            utils.log(f"  自动切换: {'启用' if auto_switch_enabled else '禁用'}")

    def start(self):
        """启动工作线程池"""
        if self.running:
            return

        self.running = True

        for i in range(self.max_workers):
            worker = Thread(
                target=self._worker_loop,
                name=f"ScriptWorker-{i}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)

        if self.verbose:
            utils.log(f"[AsyncExecutor] ✅ 已启动 {self.max_workers} 个工作线程")

    def stop(self):
        """停止所有工作线程"""
        if not self.running:
            return

        if self.verbose:
            utils.log("[AsyncExecutor] 正在停止工作线程...")
        self.running = False

        # 等待所有任务完成
        self.task_queue.join()

        # 停止所有工作线程
        for worker in self.workers:
            if worker.is_alive():
                worker.join(timeout=1.0)

        self.workers.clear()
        if self.verbose:
            utils.log("[AsyncExecutor] ✅ 所有工作线程已停止")
    def set_script_mode(self, script_name: str, mode: ExecutionMode):
        """
        设置脚本执行模式

        Args:
            script_name: 脚本名称
            mode: 执行模式
        """
        self.script_modes[script_name] = mode
        if self.verbose:
            utils.log(f"[AsyncExecutor] 设置 {script_name} 执行模式: {mode.value}")

    def execute(self,
                script_name: str,
                event_name: str,
                callback: Callable,
                args: tuple = (),
                force_mode: Optional[ExecutionMode] = None) -> Optional[Any]:
        """
        执行脚本事件（智能选择同步/异步）

        Args:
            script_name: 脚本名称
            event_name: 事件名称
            callback: 回调函数
            args: 参数
            force_mode: 强制执行模式

        Returns:
            同步执行时返回结果，异步执行时返回 None
        """
        # 确定执行模式
        mode = force_mode or self.script_modes.get(script_name, ExecutionMode.AUTO)

        if mode == ExecutionMode.SYNC:
            return self._execute_sync(script_name, event_name, callback, args)

        elif mode == ExecutionMode.ASYNC:
            self._execute_async(script_name, event_name, callback, args)
            return None

        else:  # AUTO
            return self._execute_auto(script_name, event_name, callback, args)

    def _execute_sync(self,
                      script_name: str,
                      event_name: str,
                      callback: Callable,
                      args: tuple) -> Any:
        """同步执行（主线程）"""
        task = AsyncTask(script_name, event_name, callback, args)
        task.start_time = time.perf_counter()

        try:
            task.result = callback(*args)
        except Exception as e:
            task.error = e
            utils.log(f"[AsyncExecutor] ❌ {script_name}.{event_name} 执行失败: {e}")
        finally:
            task.end_time = time.perf_counter()
            task.completed = True
            self._update_stats(task)

        return task.result

    def _execute_async(self,
                       script_name: str,
                       event_name: str,
                       callback: Callable,
                       args: tuple):
        """异步执行（工作线程）"""
        task = AsyncTask(script_name, event_name, callback, args)
        self.task_queue.put(task)

    def _execute_auto(self,
                      script_name: str,
                      event_name: str,
                      callback: Callable,
                      args: tuple) -> Optional[Any]:
        """自动选择执行模式"""
        if not self.auto_switch_enabled:
            return self._execute_sync(script_name, event_name, callback, args)

        # 获取历史统计
        avg_time = self._get_average_execution_time(script_name, event_name)

        # 根据历史耗时选择模式
        if avg_time > self.sync_threshold_ms / 1000.0:
            # 超过阈值，使用异步
            self._execute_async(script_name, event_name, callback, args)
            return None
        else:
            # 未超过阈值，使用同步
            return self._execute_sync(script_name, event_name, callback, args)

    def _worker_loop(self):
        """工作线程主循环"""
        while self.running:
            try:
                task = self.task_queue.get(timeout=0.1)
            except Empty:
                continue

            task.start_time = time.perf_counter()

            try:
                task.result = task.callback(*task.args)
            except Exception as e:
                task.error = e
                utils.log(f"[AsyncExecutor] ❌ {task.script_name}.{task.event_name} 执行失败: {e}")
                traceback.print_exc()
            finally:
                task.end_time = time.perf_counter()
                task.completed = True
                self._update_stats(task)
                self.task_queue.task_done()

    def _update_stats(self, task: AsyncTask):
        """更新性能统计"""
        with self.stats_lock:
            if task.script_name not in self.execution_stats:
                self.execution_stats[task.script_name] = {}

            if task.event_name not in self.execution_stats[task.script_name]:
                self.execution_stats[task.script_name][task.event_name] = {
                    'total_calls': 0,
                    'total_time': 0.0,
                    'max_time': 0.0,
                    'min_time': float('inf'),
                    'errors': 0,
                    'recent_times': []  # 保留最近 100 次
                }

            stats = self.execution_stats[task.script_name][task.event_name]
            exec_time = task.execution_time

            stats['total_calls'] += 1
            stats['total_time'] += exec_time
            stats['max_time'] = max(stats['max_time'], exec_time)
            stats['min_time'] = min(stats['min_time'], exec_time)

            if task.error:
                stats['errors'] += 1

            stats['recent_times'].append(exec_time)
            if len(stats['recent_times']) > 100:
                stats['recent_times'].pop(0)

    def _get_average_execution_time(self, script_name: str, event_name: str) -> float:
        """获取平均执行时间（秒）"""
        with self.stats_lock:
            if script_name not in self.execution_stats:
                return 0.0

            if event_name not in self.execution_stats[script_name]:
                return 0.0

            stats = self.execution_stats[script_name][event_name]
            recent_times = stats['recent_times']

            if not recent_times:
                return 0.0

            return sum(recent_times) / len(recent_times)

    def get_stats(self, script_name: Optional[str] = None) -> Dict:
        """
        获取性能统计

        Args:
            script_name: 脚本名称（None = 所有脚本）
        """
        with self.stats_lock:
            if script_name:
                return self.execution_stats.get(script_name, {})
            else:
                return self.execution_stats.copy()

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
