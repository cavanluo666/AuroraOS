#哈希值计算代码：python -c "import hashlib; print(hashlib.sha256(open('你的文件名.zip', 'rb').read()).hexdigest())"
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, colorchooser
import subprocess
import os
import tempfile
import re
import threading
import queue
from datetime import datetime
import ctypes
from ctypes import wintypes
import sys
import hashlib

# ================== 哈希校验功能（新增） ==================
def calculate_file_hash(filepath, algorithm="sha256", chunk_size=65536):
    """
    计算文件的哈希值（分块读取，支持大文件）
    返回哈希字符串或错误信息（以"错误："开头）
    """
    try:
        hash_obj = hashlib.new(algorithm)
        with open(filepath, "rb") as f:
            while chunk := f.read(chunk_size):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()
    except FileNotFoundError:
        return f"错误：文件 '{filepath}' 不存在"
    except Exception as e:
        return f"错误：{e}"

def verify_file_hash(filepath, expected_hash, algorithm="sha256"):
    """
    校验文件哈希是否与期望值匹配
    返回 (是否匹配, 实际哈希或错误信息)
    """
    actual = calculate_file_hash(filepath, algorithm)
    if "错误" in actual:
        return False, actual
    match = actual.lower() == expected_hash.lower()
    return match, actual

def check_integrity_before_gui():
    """
    在 GUI 启动前校验关键文件，失败则弹窗并退出。
    如果文件不存在或哈希不匹配，会弹出错误框。
    """
    # 先创建一个临时根窗口用于弹窗（此时还未创建主窗口）
    temp_root = tk.Tk()
    temp_root.withdraw()  # 隐藏窗口

    files_to_check = [
        ("about.png", "d294486a0e680c8664e5a148dc578208df0214b7222827ebce0e0194a121f33c"),
        ("360Chrome.exe", "216d330bb5a5a4b7b6655bf78b9b2810ef7f1859f48c2ce901e31707e75678cd"),
        ("360Chrome.png", "527f467e9955ebfd1505ce7a34fd512c48af0702d18fb4365072de550b9d32e9")        
    ]

    all_ok = True
    for fname, expected in files_to_check:
        ok, actual = verify_file_hash(fname, expected, "sha256")
        if not ok:
            messagebox.showerror(
                "完整性校验失败",
                f"文件 '{fname}' 校验不通过！\n\n"
                f"期望哈希：{expected}\n"
                f"实际哈希：{actual}\n\n"
                "程序文件可能已被篡改或损坏，程序将退出。",
                parent=temp_root
            )
            all_ok = False
            break   # 只要有一个失败就停止

    temp_root.destroy()
    if not all_ok:
        sys.exit(1)   # 退出程序
    # 校验通过，正常继续

# ========== Windows API 常量（用于窗口置顶） ==========
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001

# ---------- Windows API 函数声明 ----------
user32 = ctypes.windll.user32
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

def enum_windows_proc(hwnd, lparam):
    """回调函数，用于枚举窗口并检查是否属于目标进程"""
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value == lparam and user32.IsWindowVisible(hwnd):
        global found_hwnd
        found_hwnd = hwnd
        return False  # 停止枚举
    return True

def activate_window_by_pid(pid):
    """通过进程 ID 激活其主窗口，并临时置顶 200ms"""
    global found_hwnd
    found_hwnd = None
    enum_proc = WNDENUMPROC(enum_windows_proc)
    user32.EnumWindows(enum_proc, pid)
    if found_hwnd:
        user32.SetForegroundWindow(found_hwnd)
        user32.ShowWindow(found_hwnd, 5)  # SW_SHOW

        # 临时置顶
        user32.SetWindowPos(found_hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)

        def unset_topmost():
            user32.SetWindowPos(found_hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
        threading.Timer(0.2, unset_topmost).start()
        return True
    else:
        return False

# ---------- Wi-Fi 扫描与连接功能 ----------
def scan_wifi(timeout=5):
    try:
        result = subprocess.run(
            ['netsh', 'wlan', 'show', 'networks'],
            capture_output=True,
            text=True,
            encoding='gbk',
            errors='ignore',
            timeout=timeout
        )
        output = result.stdout if result.stdout is not None else ""
    except subprocess.TimeoutExpired:
        return [], "扫描超时，请检查网络适配器状态"
    except Exception as e:
        return [], f"扫描失败: {e}"

    networks = []
    lines = output.splitlines()
    current_ssid = None

    for line in lines:
        ssid_match = re.search(r'^\s*SSID\s*\d+\s*:\s*(.+)$', line, re.IGNORECASE)
        if ssid_match:
            current_ssid = ssid_match.group(1).strip()
            continue
        signal_match = re.search(r'信号\s*:\s*(\d+)%', line) or \
                       re.search(r'Signal\s*:\s*(\d+)%', line, re.IGNORECASE)
        if signal_match and current_ssid:
            signal = signal_match.group(1) + '%'
            networks.append((current_ssid, signal))
            current_ssid = None
        if not line.strip():
            current_ssid = None

    if not networks and ("没有" in output or "0" in output):
        return [], "未发现可用 Wi-Fi"
    return networks, None

def connect_to_wifi(ssid, password):
    if not ssid or password is None:
        return

    xml_template = '''<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid}</name>
    <SSIDConfig>
        <SSID>
            <name>{ssid}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>WPA2PSK</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{password}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>'''
    xml_content = xml_template.format(ssid=ssid, password=password)

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False, encoding='utf-8') as f:
            f.write(xml_content)
            temp_path = f.name

        subprocess.run(['netsh', 'wlan', 'add', 'profile', f'filename={temp_path}'],
                       capture_output=True, check=True, encoding='gbk', errors='ignore', timeout=5)
        result = subprocess.run(['netsh', 'wlan', 'connect', f'name={ssid}'],
                                capture_output=True, encoding='gbk', errors='ignore', timeout=5)
        if result.returncode == 0:
            messagebox.showinfo("成功", f"已连接到 {ssid}")
        else:
            messagebox.showerror("连接失败", result.stderr)

    except subprocess.TimeoutExpired:
        messagebox.showerror("超时", "连接操作超时")
    except subprocess.CalledProcessError as e:
        messagebox.showerror("错误", f"添加配置文件失败: {e.stderr}")
    except Exception as e:
        messagebox.showerror("错误", str(e))
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

def show_wifi_window(parent):
    wifi_win = tk.Toplevel(parent)
    wifi_win.title("选择 Wi-Fi")
    wifi_win.geometry("450x350")
    wifi_win.configure(bg='#f0f0f0')
    wifi_win.transient(parent)
    wifi_win.grab_set()

    tk.Label(wifi_win, text="可用 Wi-Fi 列表:", font=("Arial", 12), bg='#f0f0f0').pack(pady=5)

    frame = tk.Frame(wifi_win, bg='#f0f0f0')
    frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

    scrollbar = tk.Scrollbar(frame)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    listbox = tk.Listbox(frame, yscrollcommand=scrollbar.set, font=("Arial", 10))
    listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.config(command=listbox.yview)

    status_label = tk.Label(wifi_win, text="正在扫描...", bg='#f0f0f0', fg='blue')
    status_label.pack(pady=2)

    btn_frame = tk.Frame(wifi_win, bg='#f0f0f0')
    btn_frame.pack(pady=10)

    wifi_win.networks = []
    result_queue = queue.Queue()

    def refresh_list():
        refresh_btn.config(state=tk.DISABLED)
        status_label.config(text="正在扫描...", fg='blue')
        listbox.delete(0, tk.END)
        listbox.insert(tk.END, "扫描中，请稍候...")

        def scan_thread():
            networks, error = scan_wifi(timeout=8)
            result_queue.put((networks, error))

        threading.Thread(target=scan_thread, daemon=True).start()
        check_queue()

    def check_queue():
        try:
            networks, error = result_queue.get_nowait()
        except queue.Empty:
            wifi_win.after(100, check_queue)
            return

        refresh_btn.config(state=tk.NORMAL)
        listbox.delete(0, tk.END)
        if error:
            listbox.insert(tk.END, f"扫描失败: {error}")
            status_label.config(text="扫描出错", fg='red')
            wifi_win.networks = []
        elif not networks:
            listbox.insert(tk.END, "未发现可用 Wi-Fi")
            status_label.config(text="无可用网络", fg='orange')
            wifi_win.networks = []
        else:
            for ssid, signal in networks:
                listbox.insert(tk.END, f"{ssid}  (信号: {signal})")
            status_label.config(text=f"找到 {len(networks)} 个网络", fg='green')
            wifi_win.networks = networks

    def connect_selected():
        selection = listbox.curselection()
        if not selection:
            messagebox.showwarning("未选择", "请先选择一个 Wi-Fi")
            return
        index = selection[0]
        if index >= len(wifi_win.networks):
            return
        ssid, _ = wifi_win.networks[index]
        password = simpledialog.askstring("输入密码", f"请输入 {ssid} 的密码:", show='*', parent=wifi_win)
        if password is None:
            return
        connect_to_wifi(ssid, password)

    refresh_btn = tk.Button(btn_frame, text="刷新", command=refresh_list, width=10)
    refresh_btn.pack(side=tk.LEFT, padx=5)

    connect_btn = tk.Button(btn_frame, text="连接", command=connect_selected, width=10, bg="#4CAF50", fg="white")
    connect_btn.pack(side=tk.LEFT, padx=5)

    close_btn = tk.Button(btn_frame, text="关闭", command=wifi_win.destroy, width=10)
    close_btn.pack(side=tk.LEFT, padx=5)

    refresh_list()

# ---------- 主程序 ----------
def main():
    # ========== 第一步：设置工作目录为程序所在目录 ==========
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(base_dir)

    # ========== 第二步：校验文件完整性（若失败则弹窗退出） ==========
    check_integrity_before_gui()

    # ========== 第三步：创建主窗口 ==========
    root = tk.Tk()
    root.title("AuroraOS")
    root.attributes('-fullscreen', True)
    root.configure(bg='#1a8cff')
    root.lower()

    # 顶部状态栏
    top_bar = tk.Frame(root, bg='#d0d0d0', height=30)
    top_bar.pack(side=tk.TOP, fill=tk.X)

    tk.Label(top_bar, text="AuroraOS", bg='#d0d0d0', font=("Arial", 12, "bold")).pack(side=tk.LEFT, padx=10)
    time_label = tk.Label(top_bar, bg='#d0d0d0', font=("Arial", 11))
    time_label.pack(side=tk.RIGHT, padx=10)

    def update_time():
        time_label.config(text=datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        root.after(1000, update_time)
    update_time()

    tk.Button(top_bar, text="📶 Wi-Fi", command=lambda: show_wifi_window(root),
              bg='#d0d0d0', relief=tk.FLAT, font=("Arial", 10)).pack(side=tk.RIGHT, padx=5)

    # 桌面区域
    desktop = tk.Frame(root, bg='#1a8cff')
    desktop.pack(side=tk.TOP, expand=True, fill=tk.BOTH)

    ICON_SIZE = 64
    ICON_SPACING = 20
    PADDING = 20

    icon_frames = []  # 存储 (frame, img_path, text, command)
    running_apps = []  # 存储运行中的应用 (Popen, 显示名称, PID)

    # ---------- 启动应用函数 ----------
    def launch_app(path, display_name):
        try:
            if not os.path.isabs(path):
                path = os.path.join(os.getcwd(), path)
            proc = subprocess.Popen([path], shell=True)
            running_apps.append((proc, display_name, proc.pid))
            update_taskbar_apps()
        except Exception as e:
            messagebox.showerror("启动失败", f"无法启动 {path}\n错误: {e}")

    # ---------- 图标创建函数 ----------
    def create_icon(parent, img_path, text, command):
        icon_frame = tk.Frame(parent, bg='#1a8cff')
        try:
            img = tk.PhotoImage(file=img_path)
            orig_w = img.width()
            orig_h = img.height()
            if orig_w > ICON_SIZE or orig_h > ICON_SIZE:
                factor_w = orig_w / ICON_SIZE
                factor_h = orig_h / ICON_SIZE
                factor = max(factor_w, factor_h)
                sub = max(1, int(factor))
                if sub > 1:
                    img = img.subsample(sub, sub)
            btn = tk.Button(icon_frame, image=img, borderwidth=0, highlightthickness=0,
                            command=command, bg='#1a8cff', activebackground='#1a8cff')
            btn.image = img
        except Exception as e:
            print(f"图片加载失败: {img_path}, 错误: {e}")
            btn = tk.Button(icon_frame, text=text, command=command,
                            width=10, height=2, bg='#1a8cff', fg='white',
                            font=("Arial", 10))
            btn.image = None
        btn.pack(pady=(5, 0))

        label = tk.Label(icon_frame, text=text, bg='#1a8cff', fg='white', font=("Arial", 10))
        label.pack(pady=(0, 5))
        return icon_frame

    # ---------- 重新排列桌面图标 ----------
    def arrange_icons(event=None):
        avail_width = desktop.winfo_width() - 2 * PADDING
        if avail_width <= 0:
            return
        icon_width = ICON_SIZE + 20
        cols = max(1, avail_width // (icon_width + ICON_SPACING))
        for idx, (frame, _, _, _) in enumerate(icon_frames):
            row = idx // cols
            col = idx % cols
            frame.grid(row=row, column=col, padx=ICON_SPACING//2, pady=ICON_SPACING//2, sticky='nw')

    # ---------- 更换背景颜色 ----------
    def change_background():
        color = colorchooser.askcolor(title="选择背景颜色")[1]
        if color:
            desktop.configure(bg=color)
            for frame, _, _, _ in icon_frames:
                frame.configure(bg=color)
                for child in frame.winfo_children():
                    if isinstance(child, (tk.Button, tk.Label)):
                        child.configure(bg=color)
                        if isinstance(child, tk.Button):
                            child.configure(activebackground=color)

    # ---------- 系统关机/重启命令 ----------
    def system_shutdown():
        if messagebox.askyesno("确认关机", "确定要关闭计算机吗？"):
            subprocess.run(['shutdown', '/s', '/t', '0'])

    def system_restart():
        if messagebox.askyesno("确认重启", "确定要重启计算机吗？"):
            subprocess.run(['shutdown', '/r', '/t', '0'])

    # ---------- 任务栏 ----------
    taskbar = tk.Frame(root, bg='#202020', height=45)
    taskbar.pack(side=tk.BOTTOM, fill=tk.X)

    # ---------- 开始菜单 ----------
    def show_about():
        about_win = tk.Toplevel(root)
        about_win.title("关于")
        about_win.geometry("400x300")
        about_win.transient(root)
        about_win.grab_set()

        try:
            img_path = os.path.join(os.getcwd(), "about.png")
            img = tk.PhotoImage(file=img_path)
            label = tk.Label(about_win, image=img)
            label.image = img
            label.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
        except Exception as e:
            tk.Label(about_win, text=f"加载图片失败:\n{e}", font=("Arial", 12)).pack(expand=True)

        tk.Button(about_win, text="关闭", command=about_win.destroy, width=10).pack(pady=10)

    def show_start_menu():
        menu_win = tk.Toplevel(root)
        menu_win.title("开始菜单")
        menu_win.geometry("200x280")
        menu_win.configure(bg='#e0e0e0')
        menu_win.transient(root)
        menu_win.grab_set()

        tk.Button(menu_win, text="关机", command=system_shutdown, width=15).pack(pady=5)
        tk.Button(menu_win, text="重启", command=system_restart, width=15).pack(pady=5)
        tk.Button(menu_win, text="更换背景", command=change_background, width=15).pack(pady=5)
        tk.Button(menu_win, text="关于", command=show_about, width=15).pack(pady=5)
        tk.Button(menu_win, text="关闭菜单", command=menu_win.destroy, width=15).pack(pady=5)

    start_btn = tk.Button(taskbar, text=" 开始 ", font=("Arial", 10, "bold"),
                          command=show_start_menu, bg='#2a7f2a', fg='white',
                          relief=tk.RAISED, padx=10)
    start_btn.pack(side=tk.LEFT, padx=5, pady=5)

    apps_frame = tk.Frame(taskbar, bg='#202020')
    apps_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)

    task_time = tk.Label(taskbar, bg='#202020', fg='white', font=("Arial", 10))
    task_time.pack(side=tk.RIGHT, padx=10)

    def update_task_time():
        task_time.config(text=datetime.now().strftime("%H:%M"))
        root.after(30000, update_task_time)
    update_task_time()

    # ---------- 更新任务栏运行程序列表 ----------
    def update_taskbar_apps():
        # 清理已结束的进程
        to_remove = []
        for idx, (proc, name, pid) in enumerate(running_apps):
            if proc.poll() is not None:
                to_remove.append(idx)
        for idx in reversed(to_remove):
            del running_apps[idx]

        # 清空并重建按钮
        for widget in apps_frame.winfo_children():
            widget.destroy()

        for proc, name, pid in running_apps:
            btn = tk.Button(apps_frame, text=name, font=("Arial", 9),
                            bg='#404040', fg='white', relief=tk.FLAT,
                            padx=8, pady=2,
                            command=lambda p=pid: activate_window_by_pid(p))
            btn.pack(side=tk.LEFT, padx=2)

        root.after(1000, update_taskbar_apps)

    root.after(1000, update_taskbar_apps)

    # ---------- 桌面图标数据 ----------
    icon_data = [
        ("360Chrome.png", "360浏览器", "360Chrome.exe", "360浏览器"),
        # 可以在这里添加更多图标
    ]

    for img_path, text, exe, task_name in icon_data:
        def make_command(path, disp_name):
            return lambda: launch_app(path, disp_name)
        frame = create_icon(desktop, img_path, text, make_command(exe, task_name))
        icon_frames.append((frame, img_path, text, make_command(exe, task_name)))

    arrange_icons()
    desktop.bind('<Configure>', arrange_icons)
    root.after(100, arrange_icons)

    root.mainloop()

if __name__ == '__main__':
    main()