import subprocess
import sys
import os


def build():
    """执行 Nuitka 打包"""
    print("=" * 50)
    print("     开始打包 YOLOv8 项目")
    print("=" * 50)
    print()

    # 激活虚拟环境（Windows）
    if sys.platform == "win32":
        activate_script = os.path.join(".venv", "Scripts", "activate.bat")
        if os.path.exists(activate_script):
            print("激活虚拟环境...")
            # 注意：在 subprocess 中激活虚拟环境需要特殊处理

    # 清理旧文件
    print("[1/3] 清理旧文件...")
    files_to_remove = ["main.exe"]
    dirs_to_remove = ["main.dist", "main.build", "main.onefile-build"]

    for file in files_to_remove:
        if os.path.exists(file):
            os.remove(file)
            print(f"  删除: {file}")

    for dir_name in dirs_to_remove:
        if os.path.exists(dir_name):
            import shutil
            shutil.rmtree(dir_name)
            print(f"  删除目录: {dir_name}")

    # 开始编译
    print("\n[2/3] 开始编译...")

    nuitka_cmd = [
        sys.executable,  # 使用当前 Python 解释器
        "-m", "nuitka",
        "--standalone",
        "--onefile",
        "--windows-console-mode=force",
        "--assume-yes-for-downloads",
        "--include-package=lupa",
        "--include-package-data=lupa",
        "--nofollow-import-to=pytest",
        "--nofollow-import-to=scipy",
        "--nofollow-import-to=tkinter",
        "main.py"
    ]

    try:
        result = subprocess.run(
            nuitka_cmd,
            check=True,
            capture_output=False,  # 实时显示输出
            text=True
        )

        print("\n[3/3] 打包完成！")
        print("\n生成文件: main.exe")

        if os.path.exists("main.exe"):
            size = os.path.getsize("main.exe") / (1024 * 1024)  # MB
            print(f"文件大小: {size:.2f} MB")

        print("\n" + "=" * 50)
        print("     打包成功完成！")
        print("=" * 50)

    except subprocess.CalledProcessError as e:
        print(f"\n❌ 编译失败！错误代码: {e.returncode}")
        sys.exit(e.returncode)
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    build()
