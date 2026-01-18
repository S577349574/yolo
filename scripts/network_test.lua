-- scripts/auto_capture.lua

function getScriptConfig()
    return { execution_mode = "async" }
end

-- 配置项
local CHECK_TIMER = "check_cooldown"
local CAPTURE_TIMER = "capture_cooldown"
local CHECK_INTERVAL = 1.0     -- 每1秒检测一次目标
local CAPTURE_INTERVAL = 60.0  -- 两次截图之间的最小间隔（防止频繁触发）
local CONF_THRESHOLD = 0.7     -- 置信度阈值

function onInit()
    api.log.info("[System] 自动截图脚本已启动")
    api.log.info("[Config] 检测频率: " .. CHECK_INTERVAL .. "s, 阈值: " .. CONF_THRESHOLD)
    
    -- 初始化定时器
    api.timer.start(CHECK_TIMER, CHECK_INTERVAL)
    api.timer.start(CAPTURE_TIMER, 0) -- 初始截图冷却为0，允许立即触发
end

function onFrame(targets, delta_time)
    -- 1. 频率限制
    if not api.timer.is_ready(CHECK_TIMER) then return end
    api.timer.start(CHECK_TIMER, CHECK_INTERVAL)

    local target_count = api.len(targets)
    if target_count > 0 then
        -- 2. 遍历当前所有检测到的目标
        for i = 1, target_count do
            local t = targets[i]

            -- 3. 如果满足高置信度条件，则按其类别保存
            if t.confidence >= CONF_THRESHOLD and api.timer.is_ready(CAPTURE_TIMER) then

                -- ⭐ 动态构造数据包
                local cmd = {
                    action = "capture",
                    category = t.class_name,        -- 动态类别：如 "enemy", "teammate", "boss"
                    label = "id_" .. t.class_id,    -- 文件名前缀
                    width = 640,
                    height = 640
                }

                local success = api.network.send_packet(cmd)
                if success then
                    api.log.info("[AutoCapture] 发现目标: " .. t.class_name .. "，已请求分类存储")
                    api.timer.start(CAPTURE_TIMER, CAPTURE_INTERVAL)
                end

                -- 触发一次后跳出循环，避免同帧多次截图
                break
            end
        end
    end
end