-- scripts/detect_large_target.lua

-- ==================== 配置区 ====================
local CONFIG = {
    -- 目标尺寸阈值（像素）
    min_width = 80,   -- 最小宽度（建议 80-120）
    min_height = 120,  -- 最小高度（建议 120-180）

    -- 目标类别 ID
    target_class_id = 0,  -- 只判断类别 ID

    -- 置信度阈值
    min_confidence = 0.7,

    -- 日志打印频率（每 N 帧打印一次，避免刷屏）
    log_interval = 30,  -- 每 30 帧 = 约 0.5 秒（60FPS 时）

    -- 调试模式
    debug = true,
}

-- ==================== 状态变量 ====================
local state = {
    frame_count = 0,           -- 总帧数
    match_frame_count = 0,     -- 匹配成功的帧数
    last_match_time = 0,       -- 上次匹配成功的时间
    current_target = nil,      -- 当前匹配的目标
    is_target_locked = false,  -- 是否持续锁定目标
}

-- ==================== 辅助函数：安全获取属性 ====================
local function safe_get(obj, key, default)
    local ok, value = pcall(function() return obj[key] end)
    if ok and value ~= nil then
        return value
    end
    return default
end

-- ==================== 初始化 ====================
function onInit()
    api.log.info("✅ [DetectLarge] 大目标检测脚本已启动")
    api.log.info("   配置参数:")
    api.log.info(string.format("   - 尺寸阈值: %dx%d 像素", CONFIG.min_width, CONFIG.min_height))
    api.log.info(string.format("   - 目标类别 ID: %d", CONFIG.target_class_id))
    api.log.info(string.format("   - 置信度阈值: %.0f%%", CONFIG.min_confidence * 100))
    api.log.info(string.format("   - 日志频率: 每 %d 帧", CONFIG.log_interval))
end

-- ==================== 每帧更新 ====================
function onFrame(targets, dt)
    state.frame_count = state.frame_count + 1
    local target_count = api.len(targets)

    -- 1. 如果没有目标
    if target_count == 0 then
        if state.is_target_locked then
            api.log.info("⚪ [DetectLarge] 目标丢失")
            state.is_target_locked = false
            state.current_target = nil
        end
        return
    end

    -- 2. 遍历所有目标，找到第一个符合条件的大目标
    local matched_target = nil

    for i = 1, target_count do
        local target = targets[i]

        if is_target_match(target) then
            matched_target = target
            state.match_frame_count = state.match_frame_count + 1
            state.last_match_time = api.system.time()
            state.current_target = target
            break
        end
    end

    -- 3. 处理日志输出
    if matched_target then
        -- 刚检测到大目标
        if not state.is_target_locked then
            state.is_target_locked = true
            print_target_detected(matched_target)
        end

        -- 定期打印目标信息（避免刷屏）
        if state.frame_count % CONFIG.log_interval == 0 then
            print_target_info(matched_target)
        end
    else
        -- 目标消失
        if state.is_target_locked then
            api.log.info("⚪ [DetectLarge] 目标已离开检测区域")
            state.is_target_locked = false
            state.current_target = nil
        end
    end
end

-- ==================== 清理 ====================
function onCleanup()
    -- 输出统计信息
    local total_time = api.system.uptime()
    local match_rate = state.frame_count > 0 and (state.match_frame_count / state.frame_count * 100) or 0

    api.log.info("⛔ [DetectLarge] 脚本已卸载")
    api.log.info(string.format("   统计数据:"))
    api.log.info(string.format("   - 总帧数: %d", state.frame_count))
    api.log.info(string.format("   - 匹配帧数: %d (%.1f%%)", state.match_frame_count, match_rate))
    api.log.info(string.format("   - 运行时长: %.1f 秒", total_time))
end

-- ==================== 辅助函数 ====================

-- 打印目标检测成功信息
function print_target_detected(target)
    if not target then return end

    local width = safe_get(target, "width", 0)
    local height = safe_get(target, "height", 0)
    local class_id = safe_get(target, "class_id", -1)
    local confidence = safe_get(target, "confidence", 0)
    local x = safe_get(target, "x", 0)
    local y = safe_get(target, "y", 0)

    api.log.info("🎯 [DetectLarge] 检测到大目标！")
    api.log.info(string.format(
        "   类别ID: %d | 尺寸: %.0fx%.0f | 置信度: %.0f%%",
        class_id, width, height, confidence * 100
    ))
    api.log.info(string.format(
        "   位置: (%.0f, %.0f)",
        x, y
    ))
end

-- 打印目标详细信息（定期更新）
function print_target_info(target)
    if not target then return end

    local width = safe_get(target, "width", 0)
    local height = safe_get(target, "height", 0)
    local class_id = safe_get(target, "class_id", -1)
    local confidence = safe_get(target, "confidence", 0)
    local distance = safe_get(target, "distance", 0)

    api.log.info(string.format(
        "📊 [DetectLarge] 类别ID:%d | 尺寸: %.0fx%.0f | 置信度: %.0f%% | 距离: %.1f",
        class_id, width, height, confidence * 100, distance
    ))
end

-- 判断目标是否符合条件
function is_target_match(target)
    if not target then return false end

    -- 1. 获取属性
    local class_id = safe_get(target, "class_id", -1)
    local confidence = safe_get(target, "confidence", 0)
    local width = safe_get(target, "width", 0)
    local height = safe_get(target, "height", 0)

    -- 2. 检查类别 ID
    if class_id ~= CONFIG.target_class_id then
        return false
    end

    -- 3. 检查置信度
    if confidence < CONFIG.min_confidence then
        return false
    end

    -- 4. 检查尺寸（核心逻辑）
    local width_ok = width >= CONFIG.min_width
    local height_ok = height >= CONFIG.min_height

    return width_ok and height_ok
end

-- ==================== 可选：返回脚本配置 ====================
function getScriptConfig()
    return {
        name = "大目标检测器",
        version = "1.0",
        author = "Auto",
        description = "检测超过指定尺寸的目标并打印日志",
        execution_mode = "sync"  -- 同步模式
    }
end
