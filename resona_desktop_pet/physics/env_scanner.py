# resona_desktop_pet/physics/env_scanner.py
import sys
import ctypes
from ctypes import wintypes
from PySide6.QtGui import QGuiApplication
from PySide6.QtCore import QRect

class EnvironmentScanner:
    @staticmethod
    def get_screen_geometry(window=None):
        screen = None
        if window:
            screen = window.screen()
        if not screen:
            screen = QGuiApplication.primaryScreen()
            
        if screen:
            return screen.availableGeometry()
        return QRect(0, 0, 1920, 1080)

    @staticmethod
    def get_screen_refresh_rate(window=None):
        screen = None
        if window:
            screen = window.screen()
        if not screen:
            screen = QGuiApplication.primaryScreen()

        if screen:
            rate = screen.refreshRate()
            if rate and rate > 1:
                return rate
        return 60.0

    @staticmethod
    def _get_primary_screen_geometry():
        screen = QGuiApplication.primaryScreen()
        if screen:
            return screen.geometry()
        return QRect(0, 0, 1920, 1080)

    @staticmethod
    def get_window_rects(ignore_hwnds=None, ignore_maximized=True, ignore_fullscreen=True, ignore_borderless_fullscreen=True):
        if sys.platform != "win32":
            return []

        if ignore_hwnds is None:
            ignore_hwnds = set()
        else:
            ignore_hwnds = set(int(h) for h in ignore_hwnds if h)

        user32 = ctypes.windll.user32
        dwmapi = ctypes.windll.dwmapi
        rects = []

        screen_geo = EnvironmentScanner.get_screen_geometry()
        full_geo = EnvironmentScanner._get_primary_screen_geometry()
        tol = 2
        ignore_classes = {
            "Progman",
            "WorkerW",
            "Shell_TrayWnd",
            "Shell_SecondaryTrayWnd",
            "NotifyIconOverflowWindow",
            "Fences",
            "FencesMainWindow",
            "FencesMenuWindow"
        }
        GWL_EXSTYLE = -20
        WS_EX_TOOLWINDOW = 0x00000080
        DWMWA_CLOAKED = 14

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_uint),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", ctypes.c_uint)
            ]

        class WINDOWPLACEMENT(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_uint),
                ("flags", ctypes.c_uint),
                ("showCmd", ctypes.c_uint),
                ("ptMinPosition", wintypes.POINT),
                ("ptMaxPosition", wintypes.POINT),
                ("rcNormalPosition", wintypes.RECT)
            ]

        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def enum_proc(hwnd, lparam):
            hwnd_int = int(hwnd)
            if hwnd_int in ignore_hwnds:
                return True
            if not user32.IsWindowVisible(hwnd):
                return True
            if user32.IsIconic(hwnd):
                return True
            if ignore_maximized:
                placement = WINDOWPLACEMENT()
                placement.length = ctypes.sizeof(WINDOWPLACEMENT)
                if user32.GetWindowPlacement(hwnd, ctypes.byref(placement)):
                    if placement.showCmd == 3:
                        return True
            class_name = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, class_name, 256)
            if class_name.value in ignore_classes:
                return True
            ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if ex_style & WS_EX_TOOLWINDOW:
                return True
            cloaked = wintypes.DWORD()
            if dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) == 0:
                if cloaked.value != 0:
                    return True

            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            if width <= 0 or height <= 0:
                return True

            qr = QRect(rect.left, rect.top, width, height)
            if not qr.intersects(screen_geo):
                return True

            monitor = user32.MonitorFromWindow(hwnd, 2)
            mon_full = full_geo
            mon_work = screen_geo
            if monitor:
                mi = MONITORINFO()
                mi.cbSize = ctypes.sizeof(MONITORINFO)
                if user32.GetMonitorInfoW(monitor, ctypes.byref(mi)):
                    mon_full = QRect(mi.rcMonitor.left, mi.rcMonitor.top,
                                     mi.rcMonitor.right - mi.rcMonitor.left,
                                     mi.rcMonitor.bottom - mi.rcMonitor.top)
                    mon_work = QRect(mi.rcWork.left, mi.rcWork.top,
                                     mi.rcWork.right - mi.rcWork.left,
                                     mi.rcWork.bottom - mi.rcWork.top)

            if ignore_fullscreen or ignore_borderless_fullscreen:
                if (abs(qr.left() - mon_full.left()) <= tol and 
                    abs(qr.top() - mon_full.top()) <= tol and 
                    abs(qr.right() - mon_full.right()) <= tol and 
                    abs(qr.bottom() - mon_full.bottom()) <= tol):
                    return True

            if ignore_maximized:
                if (abs(qr.left() - mon_work.left()) <= tol and 
                    abs(qr.top() - mon_work.top()) <= tol and 
                    abs(qr.right() - mon_work.right()) <= tol and 
                    abs(qr.bottom() - mon_work.bottom()) <= tol):
                    return True

            if ignore_fullscreen or ignore_borderless_fullscreen or ignore_maximized:
                mon_full_area = max(1, mon_full.width() * mon_full.height())
                mon_work_area = max(1, mon_work.width() * mon_work.height())
                qr_area = max(1, qr.width() * qr.height())
                if (qr_area / mon_full_area) >= 0.95 or (qr_area / mon_work_area) >= 0.95:
                    return True

            rects.append(qr)
            return True

        user32.EnumWindows(EnumWindowsProc(enum_proc), 0)
        return rects
