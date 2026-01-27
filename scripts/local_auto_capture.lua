-- scripts/local_auto_capture.lua

function getScriptConfig()
    return { execution_mode = "async" }
end

local CAPTURE_FRAME_INTERVAL = 60  -- 每30帧截一张（根据你的帧率调整）
local CONF_THRESHOLD = 0.8         -- 置信度阈值
local frame_counter = 0

function onInit()
    local info = api.capture.get_info()
    api.log.info(string.format("[截图器] 屏幕: %dx%d", info.width, info.height))
    api.log.info(string.format(
        "[配置] 帧间隔: %d, 置信度阈值: %.2f",
        CAPTURE_FRAME_INTERVAL, CONF_THRESHOLD
    ))
end

function onFrame(targets, delta_time)
    frame_counter = frame_counter + 1

    if frame_counter % CAPTURE_FRAME_INTERVAL ~= 0 then
        return
    end

    local target_count = api.len(targets)
    if target_count == 0 then
        return
    end

    for i = 1, target_count do
        local t = targets[i]

        if t.confidence >= CONF_THRESHOLD then
            local success = api.capture.save(
                t.class_name,
                "id_" .. t.class_id .. "_f" .. frame_counter,
                640,
                640
            )

            if success then
                api.log.info(string.format(
                    "[截图] Frame %d | %s | conf=%.2f | 已保存",
                    frame_counter, t.class_name, t.confidence
                ))
            else
                api.log.warning("[截图] 保存失败")
            end

            break
        end
    end
end
