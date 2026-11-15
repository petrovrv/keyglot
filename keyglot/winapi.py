"""Win32 declarations used by Keyglot (ctypes only)."""
import ctypes
import os
from ctypes import wintypes as w

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t

VK_BACK, VK_TAB, VK_RETURN, VK_SHIFT, VK_CONTROL, VK_MENU = 0x08, 0x09, 0x0D, 0x10, 0x11, 0x12
VK_PAUSE, VK_CAPITAL, VK_SPACE = 0x13, 0x14, 0x20
VK_LWIN, VK_RWIN = 0x5B, 0x5C
WM_INPUTLANGCHANGEREQUEST = 0x0050


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", w.DWORD), ("scanCode", w.DWORD), ("flags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD), ("dwFlags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", w.DWORD), ("u", _INPUTUNION)]


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("flags", w.DWORD), ("hwndActive", w.HWND), ("hwndFocus", w.HWND),
                ("hwndCapture", w.HWND), ("hwndMenuOwner", w.HWND), ("hwndMoveSize", w.HWND),
                ("hwndCaret", w.HWND), ("rcCaret", w.RECT)]


HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, w.WPARAM, w.LPARAM)
WINEVENTPROC = ctypes.WINFUNCTYPE(None, w.HANDLE, w.DWORD, w.HWND, w.LONG, w.LONG, w.DWORD, w.DWORD)

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, w.HINSTANCE, w.DWORD]
user32.SetWindowsHookExW.restype = w.HHOOK
user32.CallNextHookEx.argtypes = [w.HHOOK, ctypes.c_int, w.WPARAM, w.LPARAM]
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = [w.HHOOK]
user32.SetWinEventHook.argtypes = [w.DWORD, w.DWORD, w.HMODULE, WINEVENTPROC, w.DWORD, w.DWORD, w.DWORD]
user32.SetWinEventHook.restype = w.HANDLE
user32.ToUnicodeEx.argtypes = [w.UINT, w.UINT, ctypes.c_char_p, w.LPWSTR, ctypes.c_int, w.UINT, ctypes.c_void_p]
user32.MapVirtualKeyExW.argtypes = [w.UINT, w.UINT, ctypes.c_void_p]
user32.GetKeyboardLayout.argtypes = [w.DWORD]
user32.GetKeyboardLayout.restype = ctypes.c_void_p
user32.GetKeyboardLayoutList.argtypes = [ctypes.c_int, ctypes.c_void_p]
user32.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.SendInput.argtypes = [w.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
user32.GetGUIThreadInfo.argtypes = [w.DWORD, ctypes.POINTER(GUITHREADINFO)]
user32.GetWindowLongW.argtypes = [w.HWND, ctypes.c_int]
user32.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
user32.GetForegroundWindow.restype = w.HWND
kernel32.OpenProcess.restype = w.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, w.BOOL, w.LPCWSTR]
kernel32.CreateMutexW.restype = w.HANDLE

PRIMARY_LANG = {0x09: "en", 0x13: "nl", 0x19: "ru", 0x22: "uk"}
MAGIC = 0x4B47  # dwExtraInfo of Keyglot's own injected input


def installed_layouts():
    n = user32.GetKeyboardLayoutList(0, None)
    arr = (ctypes.c_void_p * n)()
    user32.GetKeyboardLayoutList(n, arr)
    return [h for h in arr if h]


def hkl_lang(hkl):
    return PRIMARY_LANG.get((hkl or 0) & 0x3FF)


def window_exe(hwnd):
    pid = w.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        size = w.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
    finally:
        kernel32.CloseHandle(h)
    return ""


def window_title(hwnd):
    buf = ctypes.create_unicode_buffer(300)
    user32.GetWindowTextW(hwnd, buf, 300)
    return buf.value


def window_class(hwnd):
    buf = ctypes.create_unicode_buffer(200)
    user32.GetClassNameW(hwnd, buf, 200)
    return buf.value


def window_hkl(hwnd):
    tid = user32.GetWindowThreadProcessId(hwnd, None)
    return user32.GetKeyboardLayout(tid)


def focus_hwnd(hwnd):
    tid = user32.GetWindowThreadProcessId(hwnd, None)
    gi = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
    if user32.GetGUIThreadInfo(tid, ctypes.byref(gi)) and gi.hwndFocus:
        return gi.hwndFocus
    return None


def focus_is_win32_password(hwnd):
    f = focus_hwnd(hwnd)
    return bool(f and user32.GetWindowLongW(f, -16) & 0x20)  # ES_PASSWORD


def key_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def _key_input(vk=0, scan=0, flags=0):
    i = INPUT(type=1)
    i.u.ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=MAGIC)
    return i


def send_rewrite(n_back, text, boundary_vk=None):
    """One atomic SendInput: n_back Backspaces, the text as Unicode, then the boundary key."""
    seq = []
    for _ in range(n_back):
        seq += [_key_input(VK_BACK), _key_input(VK_BACK, flags=2)]
    for unit in _utf16_units(text):
        seq += [_key_input(scan=unit, flags=4), _key_input(scan=unit, flags=4 | 2)]
    if boundary_vk:
        seq += [_key_input(boundary_vk), _key_input(boundary_vk, flags=2)]
    if seq:
        arr = (INPUT * len(seq))(*seq)
        user32.SendInput(len(seq), arr, ctypes.sizeof(INPUT))


def _utf16_units(text):
    data = text.encode("utf-16-le")
    return [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]


def request_layout(hwnd, hkl):
    user32.PostMessageW(hwnd, WM_INPUTLANGCHANGEREQUEST, 0, hkl)


def single_instance(name):
    """True if this is the only instance holding the named mutex."""
    kernel32.CreateMutexW(None, False, name)
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS
