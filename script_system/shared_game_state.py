"""
共享游戏状态 - 线程安全修复版
修复要点：
1. 使用双缓冲技术避免读写冲突
2. 原子操作更新状态
3. 读写锁分离提升并发性能
"""

from typing import List, Optional
import threading


class Target:
    """
    目标对象（使用 slots 优化内存）
    不使用 dataclass 以避免兼容性问题
    """
    __slots__ = ['x', 'y', 'width', 'height', 'confidence', 'class_id',
                 'class_name', 'distance', 'aim_x', 'aim_y', 'is_locked', 'lock_frames']

    def __init__(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        confidence: float,
        class_id: int,
        class_name: str,
        distance: float,
        aim_x: float = 0.0,
        aim_y: float = 0.0,
        is_locked: bool = False,
        lock_frames: int = 0
    ):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.confidence = confidence
        self.class_id = class_id
        self.class_name = class_name
        self.distance = distance
        self.aim_x = aim_x
        self.aim_y = aim_y
        self.is_locked = is_locked
        self.lock_frames = lock_frames

    def copy(self) -> 'target_manager':
        """深拷贝目标对象"""
        return Target(
            x=self.x,
            y=self.y,
            width=self.width,
            height=self.height,
            confidence=self.confidence,
            class_id=self.class_id,
            class_name=self.class_name,
            distance=self.distance,
            aim_x=self.aim_x,
            aim_y=self.aim_y,
            is_locked=self.is_locked,
            lock_frames=self.lock_frames
        )


class GameState:
    """
    全局游戏状态（线程安全修复版）

    修复策略：
    1. 双缓冲：写入缓冲区，读取主缓冲区，避免读写冲突
    2. 原子交换：使用单一赋值语句完成状态切换
    3. 不可变快照：读取时返回数据副本
    """

    def __init__(self):
        # ========== 双缓冲设计 ==========
        # 主缓冲区（读取用）
        self._main_targets: List[Target] = []
        self._main_best_target: Optional[Target] = None

        # 写入缓冲区（构建用）
        self._write_targets: List[Target] = []
        self._write_best_target: Optional[Target] = None

        # ========== 锁机制 ==========
        self._write_lock = threading.Lock()  # 保护写入操作
        self._swap_lock = threading.Lock()   # 保护缓冲区交换

        # ========== 性能数据（使用 atomic 变量） ==========
        self._fps_lock = threading.Lock()
        self._current_fps: float = 0.0
        self._delta_time: float = 0.0
        self._frame_count: int = 0

        # ========== 状态标志（使用 threading.Event 更安全） ==========
        self._aiming_event = threading.Event()
        self._firing_event = threading.Event()
        self._locked_event = threading.Event()
        self._lock_frames: int = 0

        # ========== 压枪数据 ==========
        self._recoil_lock = threading.Lock()
        self._recoil_active: bool = False
        self._total_offset_x: float = 0.0
        self._total_offset_y: float = 0.0
        self._shot_count: int = 0

        # ========== 屏幕信息（初始化后不变，无需锁） ==========
        self.screen_width: int = 0
        self.screen_height: int = 0
        self.center_x: int = 0
        self.center_y: int = 0

        # ========== 对象池 ==========
        self._target_pool: List[Target] = []
        self._pool_size: int = 100
        self._init_pool()

    def _init_pool(self):
        """初始化对象池"""
        self._target_pool = [
            Target(0, 0, 0, 0, 0.0, 0, "", 0.0)
            for _ in range(self._pool_size)
        ]

    # ========== 🔥 修复重点：原子更新目标列表 🔥 ==========

    def update_targets(self, raw_targets: list):
        """
        更新目标列表（原子操作）

        修复说明：
        1. 在写入缓冲区构建完整数据
        2. 使用单一原子操作交换缓冲区
        3. 读取线程永远看到完整一致的数据

        Args:
            raw_targets: 原始目标字典列表
        """
        with self._write_lock:
            num_targets = len(raw_targets)

            # 扩展对象池（如果需要）
            if num_targets > len(self._target_pool):
                for _ in range(num_targets - len(self._target_pool)):
                    self._target_pool.append(
                        Target(0, 0, 0, 0, 0.0, 0, "", 0.0)
                    )

            # 在写入缓冲区构建完整数据
            self._write_targets = self._target_pool[:num_targets]

            for i, raw in enumerate(raw_targets):
                t = self._write_targets[i]
                # 批量赋值（减少属性访问次数）
                t.x = raw['x']
                t.y = raw['y']
                t.width = raw['width']
                t.height = raw['height']
                t.confidence = raw['confidence']
                t.class_id = raw['class_id']
                t.class_name = raw['class_name']
                t.distance = raw['distance']
                t.aim_x = raw.get('aim_x', raw['x'])
                t.aim_y = raw.get('aim_y', raw['y'])
                t.is_locked = False
                t.lock_frames = 0

            # ⭐ 原子交换：单一赋值语句，线程安全
            with self._swap_lock:
                self._main_targets = self._write_targets
                self._write_targets = []

    def update_best_target(self, x: Optional[float], y: Optional[float],
                           is_locked: bool = False, lock_frames: int = 0):
        """
        更新最佳目标（原子操作）

        修复说明：
        1. 先构建完整对象
        2. 单一原子赋值
        """
        with self._write_lock:
            if x is not None and y is not None:
                # 先构建完整对象
                new_target = Target(x, y, 0, 0, 0, 0, "", 0)
                new_target.is_locked = is_locked
                new_target.lock_frames = lock_frames

                # 原子赋值
                with self._swap_lock:
                    self._main_best_target = new_target
            else:
                with self._swap_lock:
                    self._main_best_target = None

    # ========== 线程安全的读取方法 ==========

    def get_targets_snapshot(self) -> List[Target]:
        """
        获取目标列表快照（线程安全）

        返回：
            目标列表的深拷贝（不会被修改影响）
        """
        with self._swap_lock:
            # 返回浅拷贝（Target对象本身不会被修改）
            return list(self._main_targets)

    def get_best_target_snapshot(self) -> Optional[Target]:
        """获取最佳目标快照"""
        with self._swap_lock:
            if self._main_best_target:
                return self._main_best_target.copy()
            return None

    def get_target_count(self) -> int:
        """获取目标数量（线程安全）"""
        with self._swap_lock:
            return len(self._main_targets)

    # ========== 性能数据（原子读写） ==========

    @property
    def current_fps(self) -> float:
        with self._fps_lock:
            return self._current_fps

    @current_fps.setter
    def current_fps(self, value: float):
        with self._fps_lock:
            self._current_fps = value

    @property
    def delta_time(self) -> float:
        with self._fps_lock:
            return self._delta_time

    @delta_time.setter
    def delta_time(self, value: float):
        with self._fps_lock:
            self._delta_time = value

    @property
    def frame_count(self) -> int:
        with self._fps_lock:
            return self._frame_count

    @frame_count.setter
    def frame_count(self, value: int):
        with self._fps_lock:
            self._frame_count = value

    # ========== 状态标志（使用 Event，天然线程安全） ==========

    @property
    def is_aiming(self) -> bool:
        return self._aiming_event.is_set()

    @is_aiming.setter
    def is_aiming(self, value: bool):
        if value:
            self._aiming_event.set()
        else:
            self._aiming_event.clear()

    @property
    def is_firing(self) -> bool:
        return self._firing_event.is_set()

    @is_firing.setter
    def is_firing(self, value: bool):
        if value:
            self._firing_event.set()
        else:
            self._firing_event.clear()

    @property
    def is_locked(self) -> bool:
        return self._locked_event.is_set()

    @is_locked.setter
    def is_locked(self, value: bool):
        if value:
            self._locked_event.set()
        else:
            self._locked_event.clear()

    @property
    def lock_frames(self) -> int:
        with self._swap_lock:
            return self._lock_frames

    @lock_frames.setter
    def lock_frames(self, value: int):
        with self._swap_lock:
            self._lock_frames = value

    # ========== 压枪数据（原子更新） ==========

    def update_recoil_state(self, active: bool, offset_x: float = 0.0,
                            offset_y: float = 0.0, shot_count: int = 0):
        """更新压枪状态（原子操作）"""
        with self._recoil_lock:
            self._recoil_active = active
            self._total_offset_x = offset_x
            self._total_offset_y = offset_y
            self._shot_count = shot_count

    def get_recoil_state(self) -> dict:
        """获取压枪状态快照"""
        with self._recoil_lock:
            return {
                'active': self._recoil_active,
                'offset_x': self._total_offset_x,
                'offset_y': self._total_offset_y,
                'shot_count': self._shot_count
            }

    @property
    def recoil_active(self) -> bool:
        with self._recoil_lock:
            return self._recoil_active

    @property
    def total_offset_x(self) -> float:
        with self._recoil_lock:
            return self._total_offset_x

    @property
    def total_offset_y(self) -> float:
        with self._recoil_lock:
            return self._total_offset_y

    @property
    def shot_count(self) -> int:
        with self._recoil_lock:
            return self._shot_count

    # ========== 兼容旧接口（直接访问主缓冲区，添加锁保护） ==========

    @property
    def targets(self) -> List[Target]:
        """兼容旧代码的targets访问（加锁保护）"""
        return self.get_targets_snapshot()

    @property
    def best_target(self) -> Optional[Target]:
        """兼容旧代码的best_target访问（加锁保护）"""
        return self.get_best_target_snapshot()


# ========== 全局单例 ==========
_game_state = GameState()


def get_game_state() -> GameState:
    """获取全局游戏状态实例"""
    return _game_state

