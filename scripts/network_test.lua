-- scripts/network_test.lua
-- 用于测试 Lua 自定义网络发包功能的脚本

function getScriptConfig()
    return {
        execution_mode = "async",
    }
end

-- ==================== 配置 ====================
local NET_CONFIG = {
    ENABLE_SEND = true,        -- 是否启用发送
    SEND_INTERVAL = 2.0,       -- 发送间隔（秒）
    LOG_DETAILS = true         -- 是否打印发包详情
}

-- ==================== 全局状态 ====================
local net_stats = {
    init_time = 0,
    last_send_time = 0,
    total_sent = 0,
    total_failed = 0,
    last_packet_data = nil
}

-- ==================== 初始化 ====================
function onInit()
    net_stats.init_time = api.system.time()

    api.log.info("")
    api.log.info("=" .. string.rep("=", 58))
    api.log.info("🌐 网络发包测试系统已启动")
    api.log.info(string.format("⏱️  发送频率: 每 %.1f 秒一次", NET_CONFIG.SEND_INTERVAL))
    api.log.info("=" .. string.rep("=", 58))
end

-- ==================== 每帧更新 ====================
function onFrame(targets, delta_time)
    if not NET_CONFIG.ENABLE_SEND then return end

    local current_time = api.system.time()

    -- 检查是否到达发送间隔
    if current_time - net_stats.last_send_time >= NET_CONFIG.SEND_INTERVAL then

        -- 1. 准备要发送的数据 (Lua Table)
        local packet = {
            type = "script_heartbeat",
            timestamp = current_time,
            uptime = current_time - net_stats.init_time,
            fps = api.state.get_fps(),
            target_count = api.len(targets),
            status = "running"
        }

        -- 2. 调用 API 发送
        -- 注意：确保 script_api.py 中已正确注册了 api.network
        local success = false
        if api.network and api.network.send_packet then
            success = api.network.send_packet(packet)
        else
            api.log.error("❌ 未发现 api.network 模块，请检查 Python 端注册逻辑")
            NET_CONFIG.ENABLE_SEND = false -- 停止尝试
            return
        end

        -- 3. 统计与反馈
        if success then
            net_stats.total_sent = net_stats.total_sent + 1
            net_stats.last_send_time = current_time

            if NET_CONFIG.LOG_DETAILS then
                api.log.info(string.format(
                    "📤 [网络] 发包成功 | 序号: %d | FPS: %.1f | 目标: %d",
                    net_stats.total_sent,
                    packet.fps,
                    packet.target_count
                ))
            end
        else
            net_stats.total_failed = net_stats.total_failed + 1
            api.log.warning("⚠️ [网络] 发包被拦截（可能是 Python 端限流或网络繁忙）")
        end
    end
end

-- ==================== 清理 ====================
function onCleanup()
    api.log.info("")
    api.log.info("=" .. string.rep("=", 58))
    api.log.info("🌐 网络发包测试报告")
    api.log.info("=" .. string.rep("=", 58))
    api.log.info(string.format("🎞️  成功发送: %d 次", net_stats.total_sent))
    api.log.info(string.format("❌ 发送失败: %d 次", net_stats.total_failed))
    api.log.info(string.format("📈 成功率: %.1f%%",
        (net_stats.total_sent / math.max(1, net_stats.total_sent + net_stats.total_failed)) * 100))
    api.log.info("=" .. string.rep("=", 58))
end
