import dearpygui.dearpygui as dpg
from gui.theme.colors import UIColors
from gui.widgets.basic import add_input_text, add_combo, add_bool, add_int
from config import config_manager as cfg


def build_system_tab(blue_notice_theme):
    with dpg.tab(label="基础 & 系统"):
        # ========== 原有配置（保持不变） ==========
        dpg.add_text("许可证配置", color=UIColors.APPLE_BLUE)
        add_input_text("LICENSE_KEY", "许可证密钥 (License)")
        # ========== 🔥 新增：核心模型配置 ========== ⭐
        dpg.add_text("核心模型配置", color=UIColors.APPLE_BLUE)

        add_input_text("MODEL_PATH", "YOLO 模型路径 (.onnx)")
        with dpg.tooltip(dpg.last_item()):
            dpg.add_text(
                "此目录是绝对路径，你模型存放的文件在哪里，就直接复制路径填入输入框，模型名字要包含.onnx\n"
                "比如我模型放的目录是在，C盘模型文件夹下面叫320.onnx的话\n"
                "那路径就是C:\\模型\\320.onnx"
            )
        add_combo(
            "MODEL_TYPE",
            "YOLO 模型类型",
            ["v5", "v8", "v10", "v11", "v26"]
        )
        with dpg.tooltip(dpg.last_item()):
            dpg.add_text("根据不同模型训练方式选择不同的类型，一般模型名字上都会标注出是v5或者v8\n"
                         "比如我有一个模型名叫：0923lqm320v5s.onnx\n"
                         "0923是训练日期、lqm是作者的名字、320是模型的尺寸、v5s就是模型的类型\n"
                         "如果要使用这个模型，那么此处就要选择V5\n"
                         "如果你无法判断模型是V几的，优先选择v8，打开预览窗口后如果发现花屏，在尝试V5\n"
                         )

        add_combo(
            "FORCE_BACKEND",
            "推理后端 (留空自动)",
            ["tensorrt", "cuda", "dml", "ncnn_vulkan", "ncnn_cpu", "cpu"]
        )
        with dpg.tooltip(dpg.last_item()):
            dpg.add_text(
                "tensorrt = TensorRT (仅NVIDIA)\n"
                "cuda = CUDA (NVIDIA)\n"
                "dml = DirectML (AMD/Intel)\n"
                "ncnn_vulkan = ncnn Vulkan (AMD推荐)\n"
                "ncnn_cpu = ncnn CPU模式\n"
                "cpu = 纯CPU模式"
            )

        dpg.add_separator()

        # ========== 🔥 新增：推理引擎高级配置（可折叠） ========== ⭐
        with dpg.collapsing_header(label="推理引擎高级配置", default_open=False):
            dpg.add_text("ONNX Runtime 配置", color=UIColors.SECTION_HEADER)
            add_bool("USE_TENSORRT", "启用 TensorRT 加速 (仅NVIDIA)")
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text("需要安装 TensorRT 并配置环境变量")

            dpg.add_separator()
            dpg.add_text("ncnn 模型文件配置", color=UIColors.SECTION_HEADER)
            dpg.add_text("说明：留空则自动从 MODEL_PATH 推断", color=UIColors.TEXT_GRAY, indent=20)

            add_input_text("NCNN_PARAM_PATH", "ncnn 参数文件 (.param)")
            add_input_text("NCNN_BIN_PATH", "ncnn 权重文件 (.bin)")

            dpg.add_separator()
            dpg.add_text("ncnn 网络结构配置", color=UIColors.SECTION_HEADER)
            dpg.add_text("说明：留空则自动从 .param 文件检测", color=UIColors.TEXT_GRAY, indent=20)

            add_input_text("NCNN_INPUT_NAME", "输入层名称")
            # NCNN_OUTPUT_NAMES 是列表，需要特殊处理
            current_outputs = cfg.get_config("NCNN_OUTPUT_NAMES", None)
            output_str = "" if current_outputs is None else ",".join(current_outputs)
            dpg.add_input_text(
                label="输出层名称（逗号分隔）",
                default_value=output_str,
                callback=lambda s, a: cfg.set_config(
                    "NCNN_OUTPUT_NAMES",
                    [x.strip() for x in a.split(",") if x.strip()] if a.strip() else None
                ),
                width=280
            )
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text("示例: out0,out1,out2\n留空自动检测")

            dpg.add_separator()
            dpg.add_text("ncnn 性能优化", color=UIColors.SECTION_HEADER)
            add_bool("NCNN_USE_FP16", "启用 FP16 加速 (仅GPU)")
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text("半精度浮点运算，提升 AMD GPU 性能")

            dpg.add_separator()
            dpg.add_text("类别名称配置", color=UIColors.SECTION_HEADER)
            add_input_text("CLASS_NAMES_PATH", "类别名称文件路径")
            with dpg.tooltip(dpg.last_item()):
                dpg.add_text("示例: models/names.txt\n留空则从模型目录自动加载 names.txt")

        dpg.add_separator()
        dpg.add_text("系统性能", color=UIColors.APPLE_BLUE)
        add_bool("ENABLE_LOGGING", "启用日志记录")
        add_combo("LOG_LEVEL", "日志等级", ["DEBUG", "INFO", "WARNING", "ERROR"])
        add_bool("DEBUG_MODE", "调试模式 (显示画框)")
        add_bool("MAKCU_DEBUG_MODE", "Makcu调试模式")

        add_int("CAPTURE_FPS", "截图帧率限制", 1, 500)
        with dpg.tooltip(dpg.last_item()):
            dpg.add_text("截图帧数限制，这个设置要超过你屏幕刷新率\n"
                         "在右键显示设置-高级显示设置中可以看到屏幕刷新率\n"
                         )
        add_int("INFERENCE_FPS", "推理帧率限制", 1, 500)
        with dpg.tooltip(dpg.last_item()):
            dpg.add_text("推理帧数可以设置的很高，因为在游戏环境中，GPU会优先把资源给游戏，程序的AI推理只能吃剩下的\n"
                         "如果你发现推理很低，那么你就需要限制一下游戏的fps或者画质，让程序推理有资源可吃\n"
                         "如果想要实现精准的锁抢，那么你推理的速度一定要比你游戏fps速度高。比如游戏120fps的，推理就需要130fps\n"
                         )
        add_int("CONFIG_MONITOR_INTERVAL_SEC", "配置热重载间隔 (秒)", 1, 60)
