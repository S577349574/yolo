# driver_loader.py
import sys
import time
from pathlib import Path

import pywintypes
import win32service
import win32serviceutil

import utils
from config_manager import get_config

# 错误码常量
ERROR_SERVICE_DOES_NOT_EXIST = 1060
ERROR_SERVICE_ALREADY_RUNNING = 1056
ERROR_SERVICE_NOT_ACTIVE = 1062
ERROR_GEN_FAILURE = 31


def _get_driver_sys_path() -> str:
    """获取驱动 .sys 的绝对路径"""
    cfg_path = str(get_config("DRIVER_SYS_PATH", "") or "").strip()

    if getattr(sys, "frozen", False):
        base_dir = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base_dir = Path(__file__).parent

    if cfg_path:
        p = Path(cfg_path)
        if not p.is_absolute():
            p = (base_dir / p).resolve()
    else:
        p = (base_dir / "mouse.sys").resolve()

    return str(p)


def _get_service_binary_path(service_name: str) -> str:
    """获取现有服务配置的驱动路径"""
    h_scm = None
    h_svc = None
    try:
        h_scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
        h_svc = win32service.OpenService(h_scm, service_name, win32service.SERVICE_QUERY_CONFIG)
        config = win32service.QueryServiceConfig(h_svc)
        return config[3]  # lpBinaryPathName
    except Exception:
        return ""
    finally:
        if h_svc:
            win32service.CloseServiceHandle(h_svc)
        if h_scm:
            win32service.CloseServiceHandle(h_scm)


def _service_exists(service_name: str) -> tuple[bool, int]:
    """
    检查服务是否存在
    返回: (是否存在, 当前状态)
    状态: 1=STOPPED, 4=RUNNING, 0=不存在
    """
    h_scm = None
    h_svc = None
    try:
        h_scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
        h_svc = win32service.OpenService(h_scm, service_name, win32service.SERVICE_QUERY_STATUS)
        status = win32service.QueryServiceStatus(h_svc)
        return True, status[1]
    except pywintypes.error as e:
        if e.winerror == ERROR_SERVICE_DOES_NOT_EXIST:
            return False, 0
        raise
    finally:
        if h_svc:
            win32service.CloseServiceHandle(h_svc)
        if h_scm:
            win32service.CloseServiceHandle(h_scm)


def _delete_service(service_name: str) -> bool:
    """删除现有服务"""
    h_scm = None
    h_svc = None
    try:
        # 先尝试停止服务
        try:
            win32serviceutil.StopService(service_name)
            time.sleep(0.3)
        except Exception:
            pass

        h_scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
        h_svc = win32service.OpenService(h_scm, service_name, win32service.SERVICE_ALL_ACCESS)
        win32service.DeleteService(h_svc)
        utils.log(f"[Driver] 已删除旧服务: {service_name}")
        return True
    except pywintypes.error as e:
        utils.log(f"[Driver] 删除服务失败: {e}")
        return False
    finally:
        if h_svc:
            win32service.CloseServiceHandle(h_svc)
        if h_scm:
            win32service.CloseServiceHandle(h_scm)


def _create_service(service_name: str, driver_path: str) -> bool:
    """创建驱动服务"""
    h_scm = None
    h_svc = None
    try:
        h_scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_ALL_ACCESS)
        h_svc = win32service.CreateService(
            h_scm,
            service_name,
            service_name,
            win32service.SERVICE_ALL_ACCESS,
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
        utils.log(f"[Driver] 驱动路径: {driver_path}")
        return True
    except pywintypes.error as e:
        utils.log(f"[Driver] 创建驱动服务失败: {e}")
        return False
    finally:
        if h_svc:
            win32service.CloseServiceHandle(h_svc)
        if h_scm:
            win32service.CloseServiceHandle(h_scm)


def _start_service(service_name: str) -> bool:
    """启动服务"""
    h_scm = None
    h_svc = None
    try:
        h_scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
        h_svc = win32service.OpenService(
            h_scm, service_name,
            win32service.SERVICE_START | win32service.SERVICE_QUERY_STATUS
        )

        # 检查当前状态
        status = win32service.QueryServiceStatus(h_svc)
        if status[1] == win32service.SERVICE_RUNNING:
            utils.log(f"[Driver] 服务已在运行")
            return True

        # 启动服务
        win32service.StartService(h_svc, None)
        utils.log(f"[Driver] 驱动服务启动成功")
        return True

    except pywintypes.error as e:
        if e.winerror == ERROR_SERVICE_ALREADY_RUNNING:
            utils.log(f"[Driver] 服务已在运行")
            return True

        utils.log(f"[Driver] 启动驱动服务失败: {e}")

        if e.winerror == ERROR_GEN_FAILURE:
            utils.log(f"[Driver] 错误31可能原因:")
            utils.log(f"[Driver]   1. 驱动文件损坏或不兼容当前系统")
            utils.log(f"[Driver]   2. 驱动未签名且系统启用了驱动签名强制")
            utils.log(f"[Driver]   3. 驱动依赖的设备不存在")
            utils.log(f"[Driver] 请尝试: 禁用驱动签名强制 或 使用已签名的驱动")

        return False
    finally:
        if h_svc:
            win32service.CloseServiceHandle(h_svc)
        if h_scm:
            win32service.CloseServiceHandle(h_scm)


def ensure_driver_loaded() -> bool:
    """
    确保驱动服务已安装并启动
    """
    service_name = get_config("DRIVER_SERVICE_NAME", "mouse")
    driver_path = _get_driver_sys_path()

    p = Path(driver_path)
    if not p.exists():
        utils.log(f"[Driver] 驱动文件不存在: {driver_path}")
        return False

    utils.log(f"[Driver] 准备加载驱动: {driver_path}")
    utils.log(f"[Driver] 服务名: {service_name}")

    # 1) 检查服务是否存在
    try:
        exists, current_state = _service_exists(service_name)
    except Exception as e:
        utils.log(f"[Driver] 查询服务失败: {e}")
        return False

    if exists:
        utils.log(f"[Driver] 服务已存在，当前状态: {current_state}")

        # 检查路径是否匹配
        existing_path = _get_service_binary_path(service_name)
        utils.log(f"[Driver] 现有服务路径: {existing_path}")

        try:
            existing_normalized = Path(existing_path).resolve() if existing_path else None
            current_normalized = Path(driver_path).resolve()

            if existing_normalized != current_normalized:
                utils.log(f"[Driver] 路径不匹配，需要重新创建服务")
                utils.log(f"[Driver]   现有: {existing_normalized}")
                utils.log(f"[Driver]   期望: {current_normalized}")

                if _delete_service(service_name):
                    exists = False
                    time.sleep(0.5)
                else:
                    utils.log(f"[Driver] 无法删除旧服务")
                    # 尝试直接启动，可能路径实际上是对的
        except Exception as e:
            utils.log(f"[Driver] 路径比较出错: {e}")

    # 2) 如果服务不存在，创建服务
    if not exists:
        if not _create_service(service_name, driver_path):
            return False

    # 3) 启动服务
    return _start_service(service_name)


def unload_driver(delete_service: bool = False) -> None:
    """停止并可选删除驱动服务"""
    service_name = get_config("DRIVER_SERVICE_NAME", "mouse")

    try:
        exists, state = _service_exists(service_name)
        if not exists:
            return
    except Exception:
        return

    # 停止服务
    if state == win32service.SERVICE_RUNNING:
        try:
            utils.log(f"[Driver] 正在停止驱动服务...")
            win32serviceutil.StopService(service_name)
            utils.log(f"[Driver] 驱动服务已停止")
        except Exception as e:
            utils.log(f"[Driver] 停止服务失败: {e}")

    # 删除服务
    if delete_service:
        _delete_service(service_name)
