-- scripts/local_auto_capture.lua

function getScriptConfig()
    return { execution_mode = "async" }
end

-- ⭐ 配置项
local CHECK_INTERVAL = 1.0     -- 每1秒检测一次目标
local CAPTURE_INTERVAL = 1.0  -- 两次截图之间的最小间隔
local CONF_THRESHOLD = 0.7     -- 置信度阈值

function onInit()
    -- ⭐ 初始化定时器（关键！）
    api.timer.start("check", CHECK_INTERVAL)
    api.timer.start("capture", 0)  -- 初始冷却为0，允许立即触发

    -- 获取屏幕信息
    local info = api.capture.get_info()
    api.log.info(string.format("[截图器] 屏幕: %dx%d", info.width, info.height))
    api.log.info(string.format("[配置] 检测频率: %.1fs, 截图间隔: %.1fs, 阈值: %.2f",
        CHECK_INTERVAL, CAPTURE_INTERVAL, CONF_THRESHOLD))
end

function onFrame(targets, delta_time)
    -- 1. ⭐ 频率限制（每1秒检测一次）
    if not api.timer.is_ready("check") then return end
    api.timer.start("check", CHECK_INTERVAL)  -- ⭐ 重新启动检测定时器

    local target_count = api.len(targets)
    if target_count == 0 then return end

    -- 2. 遍历目标
    for i = 1, target_count do
        local t = targets[i]

        -- 3. 高置信度 + 冷却就绪
        if t.confidence >= CONF_THRESHOLD and api.timer.is_ready("capture") then

            -- 4. ⭐ 调用独立截图器
            local success = api.capture.save(
                t.class_name,           -- 类别（如 "enemy", "friend"）
                "id_" .. t.class_id,    -- 文件名前缀
                640,                    -- 宽度
                640                     -- 高度
            )

            if success then
                api.log.info(string.format("[截图] %s (置信度: %.2f) 已保存",
                    t.class_name, t.confidence))
                api.timer.start("capture", CAPTURE_INTERVAL)  -- ⭐ 启动60秒冷却
            else
                api.log.warning("[截图] 保存失败")
            end

            -- 触发一次后跳出循环，避免同帧多次截图
            break
        end
    end
end
