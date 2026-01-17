-- scripts/auto_capture.lua

function getScriptConfig()
    return { execution_mode = "async" }
end

-- 配置项
local TIMER_NAME = "capture_cooldown"
local INTERVAL = 10.0

function onInit()
    api.log.info("📸 自动截图系统已就绪")
    -- 启动时先设置一个计时器，这样脚本运行 60s 后才会进行第一次截图
    -- 如果你想启动时立刻截一张，就把下面这一行删掉
    api.timer.start(TIMER_NAME, INTERVAL)
end

function onFrame(targets, delta_time)
    -- 1. 使用 API 内置的定时器检查是否就绪（冷却结束）
    if api.timer.is_ready(TIMER_NAME) then

        -- 2. 构造指令
        local cmd = {
            action = "capture",
            width = 640,
            height = 640,
            label = "auto_lua"
        }

        -- 3. 发送指令
        local success = api.network.send_packet(cmd)

        if success then
            api.log.info("📤 [Timer] 60秒周期已到，已请求截图")
            -- 4. 重新启动 60 秒计时器
            api.timer.start(TIMER_NAME, INTERVAL)
        end
    end
end