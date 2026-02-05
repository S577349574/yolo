import os
import dearpygui.dearpygui as dpg
def setup_chinese_font():
    """配置中文字体支持"""
    with dpg.font_registry():
        # 尝试多个字体路径
        font_paths = [
            r"C:\Windows\Fonts\msyh.ttc",  # 微软雅黑
            r"C:\Windows\Fonts\simhei.ttf",  # 黑体
            r"C:\Windows\Fonts\simsun.ttc",  # 宋体
        ]

        font_path = None
        for path in font_paths:
            if os.path.exists(path):
                font_path = path
                break

        if font_path:
            # ✅ 修复：使用 add_font() 而不是 with dpg.font()
            with dpg.font(font_path, 18) as font_cn:
                # ✅ 添加字符范围提示（关键修复）
                dpg.add_font_range_hint(dpg.mvFontRangeHint_Chinese_Simplified_Common)
                dpg.add_font_range_hint(dpg.mvFontRangeHint_Chinese_Full)

                # 手动添加常用字符范围
                dpg.add_font_range(0x0020, 0x00FF)  # 基本拉丁字母
                dpg.add_font_range(0x4E00, 0x9FFF)  # 中日韩统一表意文字（扩大范围）
                dpg.add_font_range(0x3000, 0x303F)  # 中日韩符号和标点

            dpg.bind_font(font_cn)
            print(f"[GUI] 已加载中文字体: {font_path}")
        else:
            print("[GUI] 未找到中文字体，部分中文可能显示为问号")