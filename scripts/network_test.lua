-- scripts/auto_capture.lua

function getScriptConfig()
    return { execution_mode = "async" }
end

-- ==================== 配置 ====================
local CAPTURE_INTERVAL = 60.0  -- 截图间隔：60秒
local last_capture_time = 0

function onInit()
    api.log.info("📸 自动截图脚本已启动，当前频率：每 " .. CAPTURE_INTERVAL .. " 秒一次")
    -- 初始化时间，确保脚本启动时不立即触发，而是等待一个周期
    last_capture_time = api.system.time()
end

function onFrame(targets, delta_time)
    local current_time = api.system.time()

    -- 检查是否到达 60 秒间隔
    if current_time - last_capture_time >= CAPTURE_INTERVAL then

        -- 1. 构造 CommandHandler 识别的指令格式
        local cmd = {
            action = "capture",
            width = 640,
            height = 640,
            label = "lua_auto"
        }

        -- 2. 调用网络 API 发送给 Python 端
        if api.network and api.network.send_packet then
            local success = api.network.send_packet(cmd)

            if success then
                api.log.info("📤 [Lua -> Python] 截图指令已发出")
                last_capture_time = current_time -- 重置计时器
            else
                api.log.warning("⚠️ 发送失败，请检查 Python 接收端是否在线")
            end
        else
            api.log.error("❌ api.network 未注册")
        end
    end
end
