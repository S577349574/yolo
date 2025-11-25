# driver_loader.py
import sys
from pathlib import Path

import win32api
import win32con
import win32service
import win32serviceutil

import utils
from config_manager import get_config


def _get_driver_sys_path() -> str:
    """
    获得驱动 .sys 的绝对路径：
    - 优先读取 config.json 中的 DRIVER_SYS_PATH
    - 否则默认使用 程序同目录下的 mouse.sys
    """
    cfg_path = str(get_config("DRIVER_SYS_PATH", "") or "").strip()

    if cfg_path:
        p = Path(cfg_path)
        if not p.is_absolute():
            # 相对路径则认为是相对 exe / 脚本所在目录
            if getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS"):
                base_dir = Path(sys.executable).parent
            else:
                base_dir = Path(__file__).parent
            p = (base_dir / p).resolve()
    else:
        # 默认：同目录 mouse.sys
        if getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS"):
            base_dir = Path(sys.executable).parent
        else:
            base_dir = Path(__file__).parent
        p = (base_dir / "mouse.sys").resolve()

    return str(p)


def ensure_driver_loaded() -> bool:
    """
    确保驱动服务已安装并启动（相当于你之前用 InstDrv 的“Load + Start”）：
    - 如果服务不存在：CreateService + StartService
    - 如果服务已存在但未运行：StartService
    - 如果已经在运行：直接通过
    返回 True 表示成功，False 表示失败
    """
    service_name = get_config("DRIVER_SERVICE_NAME", "mouse")
    driver_path = _get_driver_sys_path()

    p = Path(driver_path)
    if not p.exists():
        utils.log(f"❌ 驱动文件不存在: {driver_path}")
        return False

    utils.log(f"[Driver] 准备加载驱动: {driver_path}")
    utils.log(f"[Driver] 服务名: {service_name}")

    # 1) 尝试查询服务是否已存在
    try:
        status = win32serviceutil.QueryServiceStatus(service_name)
        utils.log(f"[Driver] 已存在服务: {service_name}，当前状态={status[1]}")
        service_exists = True
    except win32api.error as e:
        if e.winerror == win32con.ERROR_SERVICE_DOES_NOT_EXIST:
            service_exists = False
        else:
            utils.log(f"[Driver] 查询服务失败: {e}")
            return False

    # 2) 不存在则创建服务（等价于 InstDrv 里“Install Driver”）
    if not service_exists:
        utils.log(f"[Driver] 服务不存在，正在创建服务 {service_name} ...")
        h_scm = None
        h_svc = None
        try:
            h_scm = win32service.OpenSCManager(
                None, None, win32con.SC_MANAGER_ALL_ACCESS
            )

            h_svc = win32service.CreateService(
                h_scm,
                service_name,           # 服务名
                service_name,           # 显示名
                win32con.SERVICE_ALL_ACCESS,
                win32service.SERVICE_KERNEL_DRIVER,
                win32service.SERVICE_DEMAND_START,
                win32service.SERVICE_ERROR_NORMAL,
                driver_path,
                None,
                0,
                None,
                None,
                None,
            )
            utils.log(f"[Driver] 已创建驱动服务: {service_name}")
        except Exception as e:
            utils.log(f"[Driver] 创建驱动服务失败: {e}")
            return False
        finally:
            if h_svc:
                win32service.CloseServiceHandle(h_svc)
            if h_scm:
                win32service.CloseServiceHandle(h_scm)

    # 3) 确保服务启动（等价于 InstDrv 里“Start Service”）
    try:
        status = win32serviceutil.QueryServiceStatus(service_name)
        current_state = status[1]

        if current_state != win32service.SERVICE_RUNNING:
            utils.log(f"[Driver] 正在启动驱动服务 {service_name} ...")
            win32serviceutil.StartService(service_name)
            utils.log(f"[Driver] 驱动服务已启动: {service_name}")
        else:
            utils.log(f"[Driver] 驱动服务已经在运行: {service_name}")
    except Exception as e:
        utils.log(f"[Driver] 启动驱动服务失败: {e}")
        return False

    return True


def unload_driver(delete_service: bool = False) -> None:
    """
    可选：程序结束时停止驱动服务，必要时顺便删除服务
    - delete_service=False：只 Stop，不 Delete（类似 InstDrv 里的 Stop）
    - delete_service=True：Stop + Delete（类似 InstDrv 里的 Remove driver）
    """
    service_name = get_config("DRIVER_SERVICE_NAME", "mouse")

    try:
        status = win32serviceutil.QueryServiceStatus(service_name)
    except Exception:
        # 服务不存在，直接忽略
        return

    # 先尝试停止服务
    try:
        if status[1] == win32service.SERVICE_RUNNING:
            utils.log(f"[Driver] 正在停止驱动服务 {service_name} ...")
            win32serviceutil.StopService(service_name)
            utils.log(f"[Driver] 驱动服务已停止: {service_name}")
    except Exception as e:
        utils.log(f"[Driver] 停止服务失败: {e}")

    # 再选择性删除服务
    if delete_service:
        try:
            utils.log(f"[Driver] 正在删除驱动服务 {service_name} ...")
            win32serviceutil.RemoveService(service_name)
            utils.log(f"[Driver] 已删除驱动服务: {service_name}")
        except Exception as e:
            utils.log(f"[Driver] 删除服务失败: {e}")
