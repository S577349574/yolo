"""
Lua 脚本引擎 - 核心运行时环境
"""

import time
from typing import Optional, Dict, Any

try:
    from lupa import LuaRuntime, LuaError

    LUPA_AVAILABLE = True
except ImportError:
    LUPA_AVAILABLE = False
    LuaRuntime = None
    LuaError = Exception

import utils
from config.config_manager import get_config


class ScriptEngine:
    """Lua 脚本引擎"""

    def __init__(self, verbose=False):
        self.verbose = verbose
        """初始化脚本引擎"""
        self.script_name = "unknown"  # ⭐ 默认名称
        if not LUPA_AVAILABLE:
            raise RuntimeError("Lupa 未安装，请运行: pip install lupa")

        # 创建 Lua 运行时
        self.lua = LuaRuntime(unpack_returned_tuples=True)

        # 性能统计
        self.total_calls = 0
        self.total_time = 0.0
        self.last_error = None

        # 执行超时设置（毫秒）
        self.timeout_ms = get_config("SCRIPT_TIMEOUT_MS", 10)

        # 初始化环境
        self._setup_sandbox()
        self._setup_globals()

        if self.verbose:
            utils.log("[ScriptEngine] Lua 运行时初始化完成")

    def _setup_sandbox(self):
        """配置沙箱环境 - 禁用危险函数"""
        sandbox_code = """
        -- ==================== 禁用危险函数 ====================
        os = nil
        io = nil
        package = nil
        loadfile = nil
        dofile = nil
        require = nil
        load = nil

        -- ==================== 保留安全函数 ====================
        -- 数学库
        math = math

        -- 字符串库
        string = string

        -- 表操作
        table = table

        -- 基础函数
        tonumber = tonumber
        tostring = tostring
        type = type
        pairs = pairs
        ipairs = ipairs
        next = next

        -- 控制流
        pcall = pcall
        xpcall = xpcall
        error = error
        assert = assert

        -- ==================== 限制递归深度 ====================
        local function set_recursion_limit()
            local depth = 0
            local max_depth = 100

            local old_pcall = pcall
            pcall = function(f, ...)
                depth = depth + 1
                if depth > max_depth then
                    error("递归深度超过限制")
                end
                local results = {old_pcall(f, ...)}
                depth = depth - 1
                return table.unpack(results)
            end
        end

        set_recursion_limit()

        -- ==================== 工具函数 ====================
        function printf(fmt, ...)
            print(string.format(fmt, ...))
        end
        """

        try:
            self.lua.execute(sandbox_code)
        except LuaError as e:
            utils.log(f"[ScriptEngine] ❌ 沙箱配置失败: {e}")
            raise

    def _setup_globals(self):
        """设置全局变量"""
        self.lua.globals().SCRIPT_VERSION = "1.0.0"
        self.lua.globals().ENGINE_NAME = "YOLOAimAssist"

    def execute_code(self, code: str, chunk_name: str = "script") -> bool:
        """
        执行 Lua 代码

        Args:
            code: Lua 代码
            chunk_name: 代码块名称（用于错误追踪）

        Returns:
            bool: 是否成功
        """
        start_time = time.perf_counter()

        try:
            self.lua.execute(code)

            elapsed = time.perf_counter() - start_time
            self.total_calls += 1
            self.total_time += elapsed

            if get_config("SCRIPT_DEBUG_MODE", False):
                utils.log(f"[ScriptEngine] 执行 {chunk_name}: {elapsed * 1000:.2f}ms")

            return True

        except LuaError as e:
            self.last_error = str(e)
            utils.log(f"[ScriptEngine] ❌ 执行错误 ({chunk_name}): {e}")
            return False

        except Exception as e:
            self.last_error = str(e)
            utils.log(f"[ScriptEngine] ❌ 未知错误 ({chunk_name}): {e}")
            return False

    def call_function(self, func_name: str, *args):
        """调用 Lua 函数"""
        if func_name not in self.lua.globals():
            return None

        lua_func = self.lua.globals()[func_name]

        try:
            # ✅ 自动转换 Python 对象为 Lua 兼容类型
            lua_args = []
            for arg in args:
                if isinstance(arg, list):
                    # 转换列表为 Lua table
                    lua_table = self.lua.table()
                    for i, item in enumerate(arg, start=1):
                        lua_table[i] = item
                    lua_args.append(lua_table)
                elif isinstance(arg, dict):
                    # 转换字典为 Lua table
                    lua_table = self.lua.table()
                    for k, v in arg.items():
                        lua_table[k] = v
                    lua_args.append(lua_table)
                else:
                    lua_args.append(arg)

            return lua_func(*lua_args)
        except Exception as e:
            utils.log(f"[ScriptEngine] ❌ 调用 {func_name} 失败: {e}")
            return None

    def get_global(self, name: str) -> Optional[Any]:
        """获取全局变量"""
        try:
            return self.lua.globals()[name]
        except Exception as e:
            utils.log(f"[ScriptEngine] 获取全局变量 {name} 失败: {e}")
            return None

    def set_global(self, name: str, value: Any) -> bool:
        """设置全局变量"""
        try:
            self.lua.globals()[name] = value
            return True
        except Exception as e:
            utils.log(f"[ScriptEngine] 设置全局变量 {name} 失败: {e}")
            return False

    def register_api(self, api_name: str, api_table: Any):
        """
        注册 API 到 Lua 全局作用域

        Args:
            api_name: API 名称（如 "api"）
            api_table: API 表对象
        """
        try:
            self.lua.globals()[api_name] = api_table
            if self.verbose:
                # ⭐ 显示脚本名而不是 API 名
                utils.log(f"[{self.script_name}] API 已注册")
        except Exception as e:
            utils.log(f"[{self.script_name}] ❌ 注册 API 失败: {e}")

    def reset(self):
        """重置运行时环境"""
        utils.log("[ScriptEngine] 重置运行时...")

        # 重新创建运行时
        self.lua = LuaRuntime(unpack_returned_tuples=True)

        # 重新配置
        self._setup_sandbox()
        self._setup_globals()

        # 清空统计
        self.total_calls = 0
        self.total_time = 0.0
        self.last_error = None

        utils.log("[ScriptEngine] ✅ 运行时已重置")

    def get_stats(self) -> Dict[str, Any]:
        """获取性能统计"""
        avg_time = self.total_time / self.total_calls if self.total_calls > 0 else 0

        return {
            "total_calls": self.total_calls,
            "total_time": self.total_time,
            "avg_time_ms": avg_time * 1000,
            "last_error": self.last_error
        }

    def __del__(self):
        """析构函数"""
        if hasattr(self, 'lua') and self.lua is not None:
            utils.log("[ScriptEngine] 引擎已关闭")
