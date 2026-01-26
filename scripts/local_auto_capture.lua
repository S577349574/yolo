-- scripts/local_auto_capture.lua

function getScriptConfig()
    return { execution_mode = "async" }
end

local AUTO_CAPTURE_FRAME_INTERVAL = 40  -- 每60帧自动截一张
local CLICK_CAPTURE_FRAME_COOLDOWN = 20 -- 左键截图冷却帧数
local CONF_THRESHOLD = 0.6              -- 置信度阈值

local frame_counter = 0
local last_click_capture_frame = -999

function onInit()
    api.storage.set("last_left_state", false)
    api.storage.set("click_capture_count", 0)
    api.storage.set("auto_capture_count", 0)

    local info = api.capture.get_info()
    api.log.info(string.format("[截图器] 屏幕: %dx%d", info.width, info.height))
    api.log.info(string.format(
        "[配置] 自动截图帧间隔: %d, 左键冷却帧数: %d, 置信度阈值: %.2f",
        AUTO_CAPTURE_FRAME_INTERVAL, CLICK_CAPTURE_FRAME_COOLDOWN, CONF_THRESHOLD
    ))
end

function onFrame(targets, delta_time)
    frame_counter = frame_counter + 1
    local captured_this_frame = false

    local is_left_down = api.input.is_left_pressed()
    local last_left_state = api.storage.get("last_left_state", false)

    if is_left_down and not last_left_state then
        api.storage.set("last_left_state", true)

        local frames_since_last_click = frame_counter - last_click_capture_frame
        if frames_since_last_click >= CLICK_CAPTURE_FRAME_COOLDOWN then
            local target_count = api.len(targets)
            local best_target = nil

            if target_count > 0 then
                best_target = targets[1]
            end

            local label = best_target and
                string.format("click_%s_%.2f_f%d",
                    best_target.class_name,
                    best_target.confidence,
                    frame_counter) or
                string.format("click_no_target_f%d", frame_counter)

            local success = api.capture.save(
                "manual_click",
                label,
                640,
                640
            )

            if success then
                captured_this_frame = true
                last_click_capture_frame = frame_counter
                local count = api.storage.increment("click_capture_count")
                api.log.info(string.format(
                    "[左键截图 #%d] Frame %d | %s",
                    count, frame_counter, label
                ))
            else
                api.log.warning("[左键截图] 保存失败")
            end
        else
            local remaining_frames = CLICK_CAPTURE_FRAME_COOLDOWN - frames_since_last_click
            api.log.debug(string.format(
                "[左键截图] 冷却中 (剩余 %d 帧)",
                remaining_frames
            ))
        end
    end

    -- 更新左键状态
    if not is_left_down then
        api.storage.set("last_left_state", false)
    end

    if captured_this_frame then return end

    if frame_counter % AUTO_CAPTURE_FRAME_INTERVAL ~= 0 then
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
                string.format("auto_id%d_f%d_%.2f",
                    t.class_id,
                    frame_counter,
                    t.confidence),
                640,
                640
            )

            if success then
                local count = api.storage.increment("auto_capture_count")
                api.log.info(string.format(
                    "[自动截图 #%d] Frame %d | %s | conf=%.2f",
                    count, frame_counter, t.class_name, t.confidence
                ))
            else
                api.log.warning("[自动截图] 保存失败")
            end

            break  -- 只截取一个目标
        end
    end
end

function onDestroy()
    local click_count = api.storage.get("click_capture_count", 0)
    local auto_count = api.storage.get("auto_capture_count", 0)
    api.log.info(string.format(
        "[统计] 左键截图: %d次, 自动截图: %d次, 总计: %d次, 总帧数: %d",
        click_count, auto_count, click_count + auto_count, frame_counter
    ))
end
