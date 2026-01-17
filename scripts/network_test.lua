
以下是修改后的代码，已去除所有表情符号：

```lua
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
    -- 1. 限制检测频率：每1秒才进入一次逻辑
    if not api.timer.is_ready(CHECK_TIMER) then
        return
    end
    api.timer.start(CHECK_TIMER, CHECK_INTERVAL)

    -- 2. 检查是否有目标
    local target_count = api.len(targets)
    if target_count > 0 then
        
        -- 3. 遍历目标，寻找高置信度对象
        local found_high_conf = false
        for i = 1, target_count do
            if targets[i].confidence >= CONF_THRESHOLD then
                found_high_conf = true
                break
            end
        end

        -- 4. 如果找到目标且截图不在冷却中，则发送命令
        if found_high_conf and api.timer.is_ready(CAPTURE_TIMER) then
            local cmd = {
                action = "capture",
                width = 640,
                height = 640,
                label = "high_conf_target"
            }

            local success = api.network.send_packet(cmd)
            if success then
                api.log.info("[Network] 检测到高置信度目标，已发送截图请求")
                -- 触发后进入 60 秒截图冷却，避免针对同一目标连续截图
                api.timer.start(CAPTURE_TIMER, CAPTURE_INTERVAL)
            end
        end
    end
end
