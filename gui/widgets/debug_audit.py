import dearpygui.dearpygui as dpg
import config_manager as cfg
from gui.widgets import tagged as tagged_mod


def audit_profile_ui_sync(
    title: str = "UI Sync Audit",
    extra_key_tag_map: dict[str, str] | None = None,
    include_profile_keys_check: bool = True,
    print_ok: bool = False,
):
    """
    参数组切换后的 UI 自检：
    - 检查 tagged 控件是否与 cfg.get_config 一致
    - 检查 tagged 映射中是否存在“控件不存在”的 tag
    - 可选：检查 PROFILE_KEYS 是否有 key 没进入 tagged 体系（常见：用 basic.add_* 或忘记传 tag）

    Args:
        title: 输出标题
        extra_key_tag_map: 额外的 key->tag 映射（用于非 tagged 控件，例如 TARGET_CLASS_IDS 那种）
        include_profile_keys_check: 是否检查 PROFILE_KEYS 覆盖情况
        print_ok: 是否输出一致的项目（默认不输出，避免刷屏）

    Returns:
        report: dict，包含 mismatched / missing_widgets / untagged_profile_keys / ok 等列表
    """
    active = cfg.get_active_profile()
    print(f"\n========== {title} | active_profile={active} ==========")

    mapping = getattr(tagged_mod, "_TAGGED_KEY_TO_TAG", {})
    report = {
        "mismatched": [],            # (key, tag, ui_value, cfg_value)
        "missing_widgets": [],       # (key, tag)
        "ok": [],                    # (key, tag)
        "untagged_profile_keys": [], # PROFILE_KEYS 中但 mapping 里没有的 key
    }

    # 1) tagged 控件一致性检查
    for key, tag in mapping.items():
        if not dpg.does_item_exist(tag):
            report["missing_widgets"].append((key, tag))
            continue

        cfg_val = cfg.get_config(key)
        try:
            ui_val = dpg.get_value(tag)
        except Exception as e:
            report["mismatched"].append((key, tag, f"<get_value_error:{e}>", cfg_val))
            continue

        if ui_val != cfg_val:
            report["mismatched"].append((key, tag, ui_val, cfg_val))
        else:
            report["ok"].append((key, tag))

    # 2) 额外非-tagged控件检查（可选）
    if extra_key_tag_map:
        for key, tag in extra_key_tag_map.items():
            if not dpg.does_item_exist(tag):
                report["missing_widgets"].append((key, tag))
                continue
            cfg_val = cfg.get_config(key)
            ui_val = dpg.get_value(tag)
            if ui_val != cfg_val:
                report["mismatched"].append((key, tag, ui_val, cfg_val))
            else:
                report["ok"].append((key, tag))

    # 3) PROFILE_KEYS 覆盖检查（可选）：谁没进入 tagged 体系
    if include_profile_keys_check:
        try:
            profile_keys = getattr(cfg, "PROFILE_KEYS", [])
            for k in profile_keys:
                if k not in mapping:
                    report["untagged_profile_keys"].append(k)
        except Exception:
            # cfg 不一定暴露 PROFILE_KEYS，就忽略
            pass

    # ===== 输出汇总 =====
    if report["mismatched"]:
        print(f"\n[!] 值不一致: {len(report['mismatched'])} 项")
        for key, tag, ui_val, cfg_val in report["mismatched"]:
            print(f"  - key={key} tag={tag}\n      UI={ui_val}\n      CFG={cfg_val}")

    if report["missing_widgets"]:
        print(f"\n[!] 映射存在但控件不存在: {len(report['missing_widgets'])} 项")
        for key, tag in report["missing_widgets"]:
            print(f"  - key={key} tag={tag}")

    if report["untagged_profile_keys"]:
        print(f"\n[!] PROFILE_KEYS 中未进入 tagged 体系(常见原因：用 basic.add_* 或忘传 tag): "
              f"{len(report['untagged_profile_keys'])} 项")
        # 只打印前 40 个，避免刷屏
        for k in report["untagged_profile_keys"][:40]:
            print(f"  - {k}")
        if len(report["untagged_profile_keys"]) > 40:
            print("  ... (more)")

    if print_ok:
        print(f"\n[OK] 一致: {len(report['ok'])} 项")
        for key, tag in report["ok"]:
            print(f"  - {key} ({tag})")

    if not report["mismatched"] and not report["missing_widgets"] and not report["untagged_profile_keys"]:
        print("\n✅ 未发现问题：UI 与当前配置一致，PROFILE_KEYS 覆盖完整。")

    return report
