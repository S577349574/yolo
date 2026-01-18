-- scripts/debug_system.lua
-- 统一的调试系统 - 分级别控制调试信息输出
function getScriptConfig()
    return {
        execution_mode = "async",  -- "sync" | "async" | "auto"
    }
end
-- ==================== 调试级别配置 ====================
local DEBUG_LEVELS = {
    STARTUP = true,        -- 启动信息（初始化、配置加载）
    TARGET = true,         -- 目标检测信息
    PERFORMANCE = true,    -- 性能监控（FPS、帧间隔）
    STATISTICS = true,     -- 统计分析（累计数据）
    FIRE = false,           -- 射击状态
    MOVEMENT = false,      -- 鼠标移动详情
    DETAILED = false       -- 详细调试（每帧目标详情）
}

-- ==================== 输出频率控制 ====================
local LOG_INTERVALS = {
    TARGET = 1.0,          -- 目标检测日志间隔（秒）
    STATISTICS = 1.0,      -- 统计信息日志间隔（秒）
    PERFORMANCE = 10.0     -- 性能信息日志间隔（秒）
}

-- ==================== 全局状态 ====================
local stats = {
    -- 启动信息
    init_time = 0,

    -- 帧统计
    frame_count = 0,
    last_fps_log_time = 0,
    fps_window_start = 0,
    fps_frame_count = 0,

    -- 目标统计
    total_targets_detected = 0,
    target_detection_count = 0,
    last_target_time = 0,
    last_target_log_time = 0,  -- ✅ 新增：上次目标日志时间

    -- 射击统计
    fire_start_count = 0,
    fire_stop_count = 0,
    total_fire_time = 0,
    last_fire_start_time = 0,

    -- 性能统计
    frame_times = {},
    last_performance_log_time = 0,  -- ✅ 新增：上次性能日志时间

    -- 移动统计
    total_movements = 0,
    skipped_movements = 0,

    -- 状态跟踪
    last_lock_status = false,
    last_mouse_active = false,

    -- 累计窗口数据（用于统计）
    window_targets = 0,
    window_frames = 0
}

-- ==================== 辅助函数 ====================
local function format_time(seconds)
    if seconds < 60 then
        return string.format("%.1f秒", seconds)
    elseif seconds < 3600 then
        return string.format("%.1f分钟", seconds / 60)
    else
        return string.format("%.1f小时", seconds / 3600)
    end
end

local function get_avg(tbl)
    if #tbl == 0 then return 0 end
    local sum = 0
    for i = 1, #tbl do
        sum = sum + tbl[i]
    end
    return sum / #tbl
end

-- ==================== 初始化 ====================
function onInit()
    stats.init_time = api.system.time()
    stats.fps_window_start = stats.init_time
    stats.last_target_log_time = stats.init_time
    stats.last_performance_log_time = stats.init_time

    if DEBUG_LEVELS.STARTUP then
        api.log.info("")
        api.log.info("=" .. string.rep("=", 58))
        api.log.info("🛠️  调试系统已启用")
        api.log.info("=" .. string.rep("=", 58))

        -- 显示启用的调试级别
        local enabled_levels = {}
        for level, enabled in pairs(DEBUG_LEVELS) do
            if enabled then
                table.insert(enabled_levels, level)
            end
        end

        api.log.info(string.format("📊 启用的调试级别: %s", table.concat(enabled_levels, ", ")))
        api.log.info(string.format("⏰ 初始化时间: %.3f", stats.init_time))

        -- 读取当前配置
        local recoil_speed = api.config.get("RECOIL_VERTICAL_SPEED")
        local inference_fps = api.config.get("INFERENCE_FPS")

        api.log.info(string.format("⚙️  压枪速度: %.1f px/s", recoil_speed or 0))
        api.log.info(string.format("🎯 推理帧率: %d FPS", inference_fps or 0))

        -- 显示日志间隔配置
        api.log.info(string.format("⏱️  日志间隔: 目标=%.1fs, 统计=%.1fs, 性能=%.1fs",
            LOG_INTERVALS.TARGET, LOG_INTERVALS.STATISTICS, LOG_INTERVALS.PERFORMANCE))

        api.log.info("=" .. string.rep("=", 58))
        api.log.info("")
    end
end

-- ==================== 每帧更新 ====================
function onFrame(targets, delta_time)
    stats.frame_count = stats.frame_count + 1
    stats.fps_frame_count = stats.fps_frame_count + 1
    local current_time = api.system.time()

    -- 记录性能数据
    if DEBUG_LEVELS.PERFORMANCE then
        table.insert(stats.frame_times, delta_time)
        if #stats.frame_times > 100 then
            table.remove(stats.frame_times, 1)
        end
    end

    -- 目标检测统计（不立即输出日志）
    local target_count = api.len(targets)  -- ✅ 使用 api.len()
    stats.window_frames = stats.window_frames + 1

    if target_count > 0 then
        stats.total_targets_detected = stats.total_targets_detected + target_count
        stats.target_detection_count = stats.target_detection_count + 1
        stats.window_targets = stats.window_targets + target_count
        stats.last_target_time = current_time
    end

    -- ✅ 目标检测信息（按时间间隔输出）
    if DEBUG_LEVELS.TARGET then
        local time_since_log = current_time - stats.last_target_log_time

        if time_since_log >= LOG_INTERVALS.TARGET then
            if stats.target_detection_count > 0 then
                local avg_targets_per_frame = stats.window_targets / stats.window_frames

                api.log.info(string.format(
                    "🎯 [目标] 当前: %d 个 | 累计检测: %d 次 | 平均: %.2f 个/帧",
                    target_count,
                    stats.target_detection_count,
                    avg_targets_per_frame
                ))
            else
                api.log.info("🎯 [目标] 暂无目标检测")
            end

            -- 重置窗口数据
            stats.last_target_log_time = current_time
            stats.window_targets = 0
            stats.window_frames = 0
        end
    end

    -- 详细目标信息（低频输出）
    if DEBUG_LEVELS.DETAILED and target_count > 0 then
        local time_since_log = current_time - stats.last_target_log_time

        if time_since_log >= LOG_INTERVALS.TARGET then
            for i = 1, math.min(target_count, 3) do
                local t = targets[i]
                api.log.debug(string.format(
                    "   └─ 目标%d: (%.1f, %.1f) | 置信度: %.2f | 类别: %d",
                    i, t.x or 0, t.y or 0, t.confidence or 0, t.class_id or -1
                ))
            end
        end
    end

    -- ✅ 统计信息（按时间间隔输出）
    if DEBUG_LEVELS.STATISTICS then
        local elapsed_since_log = current_time - stats.fps_window_start

        if elapsed_since_log >= LOG_INTERVALS.STATISTICS then
            local fps = stats.fps_frame_count / elapsed_since_log
            local total_elapsed = current_time - stats.init_time
            local avg_fps = stats.frame_count / total_elapsed
            local avg_targets = stats.total_targets_detected / math.max(stats.frame_count, 1)

            -- 构建状态信息
            local status_parts = {}
            table.insert(status_parts, string.format("FPS: %.1f", fps))
            table.insert(status_parts, string.format("当前目标: %d", target_count))

            -- 锁定状态
            if target_count > 0 then
                table.insert(status_parts, "🎯已锁定")
            else
                local time_no_target = current_time - stats.last_target_time
                if stats.last_target_time > 0 and time_no_target < 5.0 then
                    table.insert(status_parts, string.format("❌丢失%.1fs", time_no_target))
                else
                    table.insert(status_parts, "⭕待检测")
                end
            end

            -- 平均统计
            table.insert(status_parts, string.format("平均: %.2f个/帧", avg_targets))

            api.log.info(string.format("📊 [统计] %s", table.concat(status_parts, " | ")))

            -- 重置窗口
            stats.fps_window_start = current_time
            stats.fps_frame_count = 0
        end
    end

    -- ✅ 性能监控（按时间间隔输出）
    if DEBUG_LEVELS.PERFORMANCE then
        local time_since_log = current_time - stats.last_performance_log_time

        if time_since_log >= LOG_INTERVALS.PERFORMANCE then
            local avg_frame_time = get_avg(stats.frame_times)
            local theoretical_fps = 0
            if avg_frame_time > 0 then
                theoretical_fps = 1.0 / avg_frame_time
            end

            api.log.info(string.format(
                "⏱️  [性能] 平均帧间隔: %.3f ms | 理论FPS: %.1f | 实际FPS: %.1f",
                avg_frame_time * 1000,
                theoretical_fps,
                stats.frame_count / (current_time - stats.init_time)
            ))

            stats.last_performance_log_time = current_time
        end
    end
end

-- ==================== 射击开始 ====================
function onFireStart()
    stats.fire_start_count = stats.fire_start_count + 1
    stats.last_fire_start_time = api.system.time()

    if DEBUG_LEVELS.FIRE then
        api.log.info(string.format(
            "🔫 [射击] 开始射击（第 %d 次）",
            stats.fire_start_count
        ))
    end
end

-- ==================== 射击停止 ====================
function onFireStop()
    stats.fire_stop_count = stats.fire_stop_count + 1
    local current_time = api.system.time()

    if stats.last_fire_start_time > 0 then
        local fire_duration = current_time - stats.last_fire_start_time
        stats.total_fire_time = stats.total_fire_time + fire_duration

        if DEBUG_LEVELS.FIRE then
            api.log.info(string.format(
                "🛑 [射击] 停止射击 | 持续: %.2f秒 | 累计: %.1f秒",
                fire_duration,
                stats.total_fire_time
            ))
        end
    end
end

-- ==================== 清理 ====================
function onCleanup()
    local total_time = api.system.time() - stats.init_time

    if DEBUG_LEVELS.STARTUP or DEBUG_LEVELS.STATISTICS then
        api.log.info("")
        api.log.info("=" .. string.rep("=", 58))
        api.log.info("📊 调试系统 - 最终统计报告")
        api.log.info("=" .. string.rep("=", 58))
        api.log.info(string.format("⏱️  总运行时间: %s", format_time(total_time)))
        api.log.info(string.format("🎞️  处理帧数: %d", stats.frame_count))
        api.log.info(string.format("📈 平均帧率: %.1f FPS", stats.frame_count / total_time))
        api.log.info(string.format("🎯 检测到目标: %d 次 (%d 个)",
            stats.target_detection_count,
            stats.total_targets_detected
        ))
        api.log.info(string.format("🔫 射击次数: %d 次 | 总时长: %.1f秒",
            stats.fire_start_count,
            stats.total_fire_time
        ))

        if stats.last_target_time > 0 then
            local time_since = api.system.time() - stats.last_target_time
            api.log.info(string.format("⏰ 距上次检测目标: %.1f秒", time_since))
        end

        api.log.info("=" .. string.rep("=", 58))
        api.log.info("✅ 调试系统已安全卸载")
        api.log.info("=" .. string.rep("=", 58))
    end
end
