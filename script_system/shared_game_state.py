"""
共享游戏状态 - 全局单例，避免数据传递开销
"""

from typing import List, Optional
import threading
from dataclasses import dataclass, field


@dataclass
class Target:
    """目标对象（使用 slots 优化内存）"""
    x: float
    y: float
    width: float
    height: float
    confidence: float
    class_id: int
    class_name: str
    distance: float

    # 有默认值的字段必须用 field()
    aim_x: float = field(default=0.0)
    aim_y: float = field(default=0.0)
    is_locked: bool = field(default=False)
    lock_frames: int = field(default=0)


class GameState:
    """全局游戏状态（线程安全）"""

    def __init__(self):
        self._lock = threading.RLock()

        # ========== 核心数据 ==========
        self.targets: List[Target] = []
        self.best_target: Optional[Target] = None

        # ========== 性能数据 ==========
        self.current_fps: float = 0.0
        self.delta_time: float = 0.0
        self.frame_count: int = 0

        # ========== 状态标志 ==========
        self.is_aiming: bool = False
        self.is_firing: bool = False
        self.is_locked: bool = False
        self.lock_frames: int = 0

        # ========== 压枪数据 ==========
        self.recoil_active: bool = False
        self.total_offset_x: float = 0.0
        self.total_offset_y: float = 0.0
        self.shot_count: int = 0

        # ========== 屏幕信息 ==========
        self.screen_width: int = 0
        self.screen_height: int = 0
        self.center_x: int = 0
        self.center_y: int = 0

        # ========== 对象池（复用 Target 实例） ==========
        self._target_pool: List[Target] = []
        self._pool_size: int = 100  # 预分配 100 个
        self._init_pool()

    def _init_pool(self):
        """初始化对象池"""
        self._target_pool = [
            Target(0, 0, 0, 0, 0.0, 0, "", 0.0)
            for _ in range(self._pool_size)
        ]

    def update_targets(self, raw_targets: list):
        """
        更新目标列表（使用对象池，避免创建新对象）

        Args:
            raw_targets: 原始目标字典列表
        """
        with self._lock:
            num_targets = len(raw_targets)

            # 扩展对象池（如果需要）
            if num_targets > len(self._target_pool):
                for _ in range(num_targets - len(self._target_pool)):
                    self._target_pool.append(
                        Target(0, 0, 0, 0, 0.0, 0, "", 0.0)
                    )

            # 复用对象池中的对象
            self.targets = self._target_pool[:num_targets]

            for i, raw in enumerate(raw_targets):
                t = self.targets[i]
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

    def update_best_target(self, x: Optional[float], y: Optional[float],
                           is_locked: bool = False, lock_frames: int = 0):
        """
        更新最佳目标

        Args:
            x: 目标 X 坐标
            y: 目标 Y 坐标
            is_locked: 是否锁定
            lock_frames: 锁定帧数
        """
        with self._lock:
            if x is not None and y is not None:
                if self.best_target is None:
                    self.best_target = Target(x, y, 0, 0, 0, 0, "", 0)
                else:
                    self.best_target.x = x
                    self.best_target.y = y
                    self.best_target.is_locked = is_locked
                    self.best_target.lock_frames = lock_frames
            else:
                self.best_target = None

    def update_recoil_state(self, active: bool, offset_x: float = 0.0,
                            offset_y: float = 0.0, shot_count: int = 0):
        """更新压枪状态"""
        with self._lock:
            self.recoil_active = active
            self.total_offset_x = offset_x
            self.total_offset_y = offset_y
            self.shot_count = shot_count

    def get_target_count(self) -> int:
        """获取目标数量（线程安全）"""
        with self._lock:
            return len(self.targets)

    def get_targets_copy(self) -> List[Target]:
        """获取目标列表副本（用于需要持久化的场景）"""
        with self._lock:
            return list(self.targets)  # 浅拷贝


# ========== 全局单例 ==========
_game_state = GameState()


def get_game_state() -> GameState:
    """获取全局游戏状态实例"""
    return _game_state


def init_screen_info(width: int, height: int):
    """初始化屏幕信息"""
    state = get_game_state()
    state.screen_width = width
    state.screen_height = height
    state.center_x = width // 2
    state.center_y = height // 2
