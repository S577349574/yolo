-- scripts/auto_key_large_target.lua

-- ==================== 配置区 ====================
local CONFIG = {
    -- 目标尺寸阈值（像素）
    min_width = 80,   -- 最小宽度（建议 80-120）
    min_height = 120,  -- 最小高度（建议 120-180）

    -- 目标类别
    target_class_id = 0,
    target_class_name = "敌",  -- 匹配你的模型类别名

    -- 按键设置
    press_key = "shift",
    press_mode = "hold",   -- "hold"=持续按住, "press"=单次按下

    -- 冷却时间（秒）
    cooldown = 0.3,

    -- 置信度阈值
    min_confidence = 0.7,

    -- 调试模式
    debug = true,
}

-- ==================== 状态变量 ====================
local state = {
    is_pressing = false,
    last_press_time = 0,
    debug_frame_count = 0,
    last_match_time = 0,  -- 上次匹配成功的时间
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
    api.log.info("✅ [AutoKey] 大目标自动按键脚本已启动")
    api.log.info("   配置参数:")
    api.log.info(string.format("   - 尺寸阈值: %dx%d", CONFIG.min_width, CONFIG.min_height))
    api.log.info(string.format("   - 目标类别: %s (ID:%d)", CONFIG.target_class_name, CONFIG.target_class_id))
    api.log.info(string.format("   - 触发按键: %s (模式: %s)", CONFIG.press_key, CONFIG.press_mode))
    api.log.info(string.format("   - 置信度阈值: %.0f%%", CONFIG.min_confidence * 100))
end

-- ==================== 每帧更新 ====================
function onFrame(targets, dt)
    local target_count = api.len(targets)

    -- 1. 如果没有目标
    if target_count == 0 then
        if state.is_pressing and CONFIG.press_mode == "hold" then
            api.input.key_up(CONFIG.press_key)
            state.is_pressing = false
            if CONFIG.debug then
                api.log.info("⚪ [AutoKey] 目标丢失，释放按键")
            end
        end
        return
    end

    -- 2. 遍历所有目标，找到第一个符合条件的
    local matched_target

    for i = 1, target_count do
        local target = targets[i]

        if is_target_match(target) then
            matched_target = target

            -- 更新最后匹配时间
            state.last_match_time = api.system.time()

            -- 调试模式下打印目标信息（降低频率）
            if CONFIG.debug then
                state.debug_frame_count = state.debug_frame_count + 1
                if state.debug_frame_count % 30 == 0 then
                    print_target_info(target)
                end
            end

            break
        end
    end

    -- 3. 处理按键逻辑
    local should_press = (matched_target ~= nil)
    handle_key_press(should_press)
end

-- ==================== 清理 ====================
function onCleanup()
    if state.is_pressing then
        api.input.key_up(CONFIG.press_key)
        state.is_pressing = false
    end

    -- 输出统计信息
    local total_time = api.system.time()
    local match_duration = state.last_match_time > 0 and (total_time - state.last_match_time) or 0

    api.log.info("⛔ [AutoKey] 脚本已卸载")
    api.log.info(string.format("   统计: 最后匹配于 %.1f 秒前", match_duration))
end

-- ==================== 辅助函数 ====================

-- 打印目标详情
function print_target_info(target)
    if not target then return end

    local width = safe_get(target, "width", 0)
    local height = safe_get(target, "height", 0)
    local class_name = safe_get(target, "class_name", "?")
    local class_id = safe_get(target, "class_id", -1)
    local confidence = safe_get(target, "confidence", 0)

    api.log.info(string.format(
        "📊 [AutoKey] 目标: %s(%d) | 尺寸: %.0fx%.0f | 置信度: %.0f%%",
        class_name, class_id, width, height, confidence * 100
    ))
end

-- 判断目标是否符合条件
function is_target_match(target)
    if not target then return false end

    -- 1. 获取属性
    local class_id = safe_get(target, "class_id", -1)
    local class_name = safe_get(target, "class_name", nil)
    local confidence = safe_get(target, "confidence", 0)
    local width = safe_get(target, "width", 0)
    local height = safe_get(target, "height", 0)

    -- 2. 检查类别（优先匹配类别名）
    local class_match = false
    if CONFIG.target_class_name and class_name then
        class_match = (class_name == CONFIG.target_class_name)
    else
        class_match = (class_id == CONFIG.target_class_id)
    end

    if not class_match then
        return false
    end

    -- 3. 检查置信度
    if confidence < CONFIG.min_confidence then
        return false
    end

    -- 4. 检查尺寸
    local width_ok = width >= CONFIG.min_width
    local height_ok = height >= CONFIG.min_height

    return width_ok and height_ok
end

-- 执行按键逻辑
function handle_key_press(should_press)
    local current_time = api.system.time()

    -- 冷却检查
    if current_time - state.last_press_time < CONFIG.cooldown then
        return
    end

    if CONFIG.press_mode == "hold" then
        -- 模式：持续按住
        if should_press and not state.is_pressing then
            api.input.key_down(CONFIG.press_key)
            state.is_pressing = true
            state.last_press_time = current_time
            api.log.info("🔴 [AutoKey] 按下: " .. CONFIG.press_key)

        elseif not should_press and state.is_pressing then
            api.input.key_up(CONFIG.press_key)
            state.is_pressing = false
            api.log.info("🟢 [AutoKey] 释放: " .. CONFIG.press_key)
        end

    elseif CONFIG.press_mode == "press" then
        -- 模式：单次点击
        if should_press then
            api.input.key_press(CONFIG.press_key, 50)
            state.last_press_time = current_time
            api.log.info("⚡ [AutoKey] 单次触发: " .. CONFIG.press_key)
        end
    end
end
