-- scripts/auto_capture.lua

function getScriptConfig()
    return { execution_mode = "async" }
end

-- ===== 配置项 =====
local CAPTURE_FRAME_INTERVAL = 30  -- 每20帧截一张（300fps下 = 15张/秒）
local CONF_THRESHOLD = 0.7         -- 置信度阈值

-- ===== 全局变量 =====
local frame_counter = 0            -- 帧计数器

function onInit()
    api.log.info("[System] 自动截图脚本已启动")
    api.log.info(string.format(
        "[Config] 帧间隔: %d, 置信度阈值: %.2f",
        CAPTURE_FRAME_INTERVAL, CONF_THRESHOLD
    ))
end

function onFrame(targets, delta_time)
    -- 1. 帧计数递增
    frame_counter = frame_counter + 1

    -- 2. 帧间隔控制 - 不满足间隔直接返回
    if frame_counter % CAPTURE_FRAME_INTERVAL ~= 0 then
        return
    end

    -- 3. 检查是否有目标
    local target_count = api.len(targets)
    if target_count == 0 then
        return
    end

    -- 4. 遍历目标并截图
    for i = 1, target_count do
        local t = targets[i]

        -- 5. 置信度检查
        if t.confidence >= CONF_THRESHOLD then
            -- 构造截图命令
            local cmd = {
                action = "capture",
                category = t.class_name,
                label = "id_" .. t.class_id .. "_f" .. frame_counter,
                width = 640,
                height = 640
            }

            -- 发送网络请求
            local success = api.network.send_packet(cmd)
            if success then
                api.log.info(string.format(
                    "[AutoCapture] Frame %d | %s | conf=%.2f",
                    frame_counter, t.class_name, t.confidence
                ))
            else
                api.log.error("[AutoCapture] 网络发送失败")
            end

            -- 触发一次后跳出，避免同帧多次截图
            break
        end
    end
end
