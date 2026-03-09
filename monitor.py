#!/usr/bin/env python3
"""
██╗     ██╗██╗   ██╗███████╗    ███████╗██╗   ██╗███████╗
██║     ██║██║   ██║██╔════╝    ██╔════╝╚██╗ ██╔╝██╔════╝
██║     ██║██║   ██║█████╗      ███████╗ ╚████╔╝ ███████╗
██║     ██║╚██╗ ██╔╝██╔══╝      ╚════██║  ╚██╔╝  ╚════██║
███████╗██║ ╚████╔╝ ███████╗    ███████║   ██║   ███████║
╚══════╝╚═╝  ╚═══╝  ╚══════╝    ╚══════╝   ╚═╝   ╚══════╝
          Terminal System Monitor — Cinematic Edition
"""

import math
import os
import platform
import random
import re
import subprocess
import time
from collections import deque
from datetime import datetime, timedelta

import psutil
from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# NEON THEME
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NEON_CYAN = "#00ffff"
NEON_GREEN = "#39ff14"
NEON_PINK = "#ff6ec7"
NEON_PURPLE = "#bf40bf"
NEON_ORANGE = "#ff6600"
NEON_RED = "#ff073a"
NEON_YELLOW = "#ffff33"
NEON_BLUE = "#4d4dff"
DIM = "dim"
GHOST = "#555555"
WHITE = "#e0e0e0"

# Color cycling palette for animated effects
CYCLE_COLORS = [
    "#00ffff", "#00e5ff", "#00ccff", "#00b3ff", "#009fff",
    "#0088ff", "#0070ff", "#005cff", "#4d4dff", "#6b3fff",
    "#8833ff", "#a600ff", "#bf00ff", "#d400ff", "#e600ff",
    "#ff00ff", "#ff00cc", "#ff0099", "#ff0066", "#ff0033",
    "#ff0000", "#ff3300", "#ff6600", "#ff9900", "#ffcc00",
    "#ffff00", "#ccff00", "#99ff00", "#66ff00", "#39ff14",
    "#00ff33", "#00ff66", "#00ff99", "#00ffcc",
]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STATE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HISTORY_LEN = 60
cpu_history = deque(maxlen=HISTORY_LEN)
ram_history = deque(maxlen=HISTORY_LEN)
net_sent_history = deque(maxlen=HISTORY_LEN)
net_recv_history = deque(maxlen=HISTORY_LEN)
gpu_history = deque(maxlen=HISTORY_LEN)
per_core_history: list[deque] = []

SPARK = "▁▂▃▄▅▆▇█"
BLOCKS = " ░▒▓█"
BRAILLE_EMPTY = "⠀"

start_time = datetime.now()
prev_net = psutil.net_io_counters()
prev_time = time.time()
frame_count = 0

# Cache GPU name (expensive call)
_gpu_name_cache = None
_gpu_name_fetched = False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UTILITIES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def cycle_color(offset=0):
    """Get a color from the cycling palette based on current frame."""
    idx = (frame_count + offset) % len(CYCLE_COLORS)
    return CYCLE_COLORS[idx]


def pulse_intensity():
    """Returns a 0.0-1.0 sine-wave pulse synced to frame_count."""
    return (math.sin(frame_count * 0.3) + 1) / 2


def sparkline(data, width=40):
    """Generate a sparkline with gradient coloring."""
    if not data:
        return Text("─" * width, style=GHOST)

    recent = list(data)[-width:]
    if len(recent) < width:
        recent = [0] * (width - len(recent)) + recent
    max_val = max(recent) if max(recent) > 0 else 1

    text = Text()
    for i, v in enumerate(recent):
        normalized = v / max_val
        char_idx = min(int(normalized * (len(SPARK) - 1)), len(SPARK) - 1)
        # Color gradient from cyan (low) to pink (high)
        color_idx = min(int(normalized * (len(CYCLE_COLORS) - 1)), len(CYCLE_COLORS) - 1)
        text.append(SPARK[char_idx], style=CYCLE_COLORS[color_idx])
    return text


def sparkline_dual(data1, data2, width=40):
    """Interleaved dual sparkline (e.g., TX above, RX below using braille-ish)."""
    line1 = Text()
    line2 = Text()
    r1 = list(data1)[-width:]
    r2 = list(data2)[-width:]
    if len(r1) < width:
        r1 = [0] * (width - len(r1)) + r1
    if len(r2) < width:
        r2 = [0] * (width - len(r2)) + r2
    max1 = max(r1) if max(r1) > 0 else 1
    max2 = max(r2) if max(r2) > 0 else 1
    for i in range(width):
        n1 = r1[i] / max1
        n2 = r2[i] / max2
        c1 = min(int(n1 * (len(SPARK) - 1)), len(SPARK) - 1)
        c2 = min(int(n2 * (len(SPARK) - 1)), len(SPARK) - 1)
        line1.append(SPARK[c1], style=NEON_GREEN)
        line2.append(SPARK[c2], style=NEON_CYAN)
    return line1, line2


def gauge_ring(pct, size=5):
    """Create a circular gauge visualization."""
    segments = [
        ("╭", "─", "╮"),
        ("│", " ", "│"),
        ("╰", "─", "╯"),
    ]
    filled = int(pct / 100 * (size * 2 + size * 2))
    color = color_for_pct(pct)
    # Simple arc gauge
    total_chars = size * 2
    fill_chars = int(pct / 100 * total_chars)
    bar = ""
    for i in range(total_chars):
        if i < fill_chars:
            bar += "━"
        else:
            bar += "╌"
    return f"[{color}]╺{bar}╸[/{color}]"


def color_for_pct(pct):
    if pct < 40:
        return NEON_GREEN
    elif pct < 70:
        return NEON_YELLOW
    elif pct < 85:
        return NEON_ORANGE
    return NEON_RED


def fmt_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


def neon_bar(pct, width=25, char_fill="█", char_empty="░"):
    """A gradient neon progress bar."""
    filled = int(pct / 100 * width)
    empty = width - filled
    color = color_for_pct(pct)
    text = Text()
    # Gradient fill
    for i in range(filled):
        ratio = i / max(width - 1, 1)
        ci = min(int(ratio * 20), len(CYCLE_COLORS) - 1)
        text.append(char_fill, style=f"bold {CYCLE_COLORS[ci]}")
    text.append(char_empty * empty, style=GHOST)
    return text


def matrix_rain_line(width):
    """Generate a matrix-style rain string for decoration."""
    chars = "ﾊﾐﾋｰｳｼﾅﾓﾆｻﾜﾂｵﾘｱﾎﾃﾏｹﾒｴｶｷﾑﾕﾗｾﾈｽﾀﾇﾍ012345789ABCDEF"
    text = Text()
    for _ in range(width):
        if random.random() < 0.7:
            text.append(" ")
        else:
            c = random.choice(chars)
            brightness = random.choice(["#003300", "#006600", "#009900", "#00cc00", NEON_GREEN])
            text.append(c, style=brightness)
    return text


def hex_stream(length=40):
    """Generate a fake hex data stream for decoration."""
    text = Text()
    for i in range(length):
        if random.random() < 0.15:
            text.append(" ", style=DIM)
        else:
            byte = f"{random.randint(0, 255):02X}"
            shade = random.choice([GHOST, "#00aa66", NEON_GREEN, NEON_CYAN])
            text.append(byte, style=shade)
    return text


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GPU DETECTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_gpu_name():
    global _gpu_name_cache, _gpu_name_fetched
    if _gpu_name_fetched:
        return _gpu_name_cache

    _gpu_name_fetched = True
    if platform.system() != "Darwin":
        _gpu_name_cache = "N/A"
        return _gpu_name_cache

    try:
        sp = subprocess.run(
            ["system_profiler", "SPDisplaysDataType"],
            capture_output=True, text=True, timeout=5
        )
        for line in sp.stdout.splitlines():
            s = line.strip()
            if "Chipset Model:" in s or "Chip:" in s:
                _gpu_name_cache = s.split(":", 1)[1].strip()
                return _gpu_name_cache
    except Exception:
        pass

    try:
        chip = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True, text=True, timeout=3
        )
        if chip.returncode == 0 and chip.stdout.strip():
            _gpu_name_cache = chip.stdout.strip() + " GPU"
            return _gpu_name_cache
    except Exception:
        pass

    _gpu_name_cache = "Unknown GPU"
    return _gpu_name_cache


def get_gpu_utilization():
    if platform.system() != "Darwin":
        return None
    try:
        ioreg = subprocess.run(
            ["ioreg", "-r", "-d", "1", "-c", "IOAccelerator"],
            capture_output=True, text=True, timeout=3
        )
        for line in ioreg.stdout.splitlines():
            if "Device Utilization" in line or "GPU Activity" in line:
                nums = re.findall(r'(\d+)', line)
                if nums:
                    val = int(nums[-1])
                    if 0 <= val <= 100:
                        return val
    except Exception:
        pass
    return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PANEL BUILDERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_header():
    now = datetime.now()
    session = str(timedelta(seconds=int((now - start_time).total_seconds())))
    boot = str(timedelta(seconds=int(time.time() - psutil.boot_time())))
    host = platform.node() or "UNKNOWN"
    os_ver = f"{platform.system()} {platform.release()}"

    # Animated title with color cycling
    title_chars = "◤ L I V E   S Y S T E M   M O N I T O R ◢"
    title = Text()
    for i, ch in enumerate(title_chars):
        title.append(ch, style=f"bold {cycle_color(i * 2)}")

    # Subtitle hex stream
    subtitle = hex_stream(50)

    # Blinking indicator
    blink = "●" if frame_count % 2 == 0 else "○"
    blink_color = NEON_GREEN if frame_count % 2 == 0 else NEON_CYAN

    grid = Table.grid(expand=True)
    grid.add_column(justify="left", ratio=1)
    grid.add_column(justify="center", ratio=2)
    grid.add_column(justify="right", ratio=1)

    left_info = Text()
    left_info.append(f" {blink} ", style=blink_color)
    left_info.append(host.upper(), style=f"bold {NEON_CYAN}")
    left_info.append(f"  {os_ver}", style=GHOST)

    right_info = Text()
    right_info.append(now.strftime("%H:%M:%S"), style=f"bold {NEON_GREEN}")
    right_info.append(f"  SYS {boot}", style=GHOST)
    right_info.append(f"  SES {session} ", style=GHOST)

    grid.add_row(left_info, title, right_info)
    grid.add_row(Text(""), Align.center(subtitle), Text(""))

    # Animated border color
    border_color = cycle_color(0)

    return Panel(
        grid,
        border_style=border_color,
        box=box.HEAVY,
        padding=(0, 1),
    )


def build_cpu_panel():
    global per_core_history

    cpu_overall = psutil.cpu_percent(interval=0)
    cpu_per = psutil.cpu_percent(interval=0, percpu=True)
    cpu_freq = psutil.cpu_freq()
    cpu_history.append(cpu_overall)

    # Initialize per-core history
    if not per_core_history:
        per_core_history = [deque(maxlen=20) for _ in range(len(cpu_per))]
    for i, pct in enumerate(cpu_per):
        if i < len(per_core_history):
            per_core_history[i].append(pct)

    text = Text()

    # Overall with big gauge
    color = color_for_pct(cpu_overall)
    text.append("  TOTAL ", style=f"bold {NEON_CYAN}")
    gauge_w = 20
    filled = int(cpu_overall / 100 * gauge_w)
    for i in range(gauge_w):
        if i < filled:
            ratio = i / max(gauge_w - 1, 1)
            ci = min(int(ratio * 25), len(CYCLE_COLORS) - 1)
            text.append("▰", style=f"bold {CYCLE_COLORS[ci]}")
        else:
            text.append("▱", style=GHOST)
    text.append(f"  {cpu_overall:5.1f}%", style=f"bold {color}")
    if cpu_freq:
        text.append(f"  {cpu_freq.current:.0f}MHz", style=GHOST)
    text.append("\n")

    # Per-core mini sparklines (compact & sexy)
    cols = 2
    num_cores = len(cpu_per)
    rows_needed = (num_cores + cols - 1) // cols

    for row_i in range(rows_needed):
        for col_i in range(cols):
            idx = row_i + col_i * rows_needed
            if idx < num_cores:
                pct = cpu_per[idx]
                c = color_for_pct(pct)
                # Mini bar for this core
                text.append(f"  C{idx:<2}", style=GHOST)
                bar_w = 8
                f_count = int(pct / 100 * bar_w)
                for bi in range(bar_w):
                    if bi < f_count:
                        text.append("█", style=c)
                    else:
                        text.append("░", style=GHOST)
                text.append(f" {pct:4.0f}%", style=c)
                # Mini sparkline per core
                if idx < len(per_core_history) and per_core_history[idx]:
                    hist = list(per_core_history[idx])[-6:]
                    mx = max(hist) if max(hist) > 0 else 1
                    for v in hist:
                        si = min(int(v / mx * 7), 7)
                        text.append(SPARK[si], style=c)
                text.append("  ")
        text.append("\n")

    # Overall sparkline history
    text.append("\n  ")
    text.append_text(sparkline(cpu_history, width=36))
    text.append("\n")

    load1, load5, load15 = os.getloadavg()
    text.append(f"  LOAD ", style=GHOST)
    for val, label in [(load1, "1m"), (load5, "5m"), (load15, "15m")]:
        lc = NEON_GREEN if val < 4 else NEON_YELLOW if val < 8 else NEON_RED
        text.append(f"{val:.1f}", style=lc)
        text.append(f"({label}) ", style=GHOST)

    return Panel(
        text,
        title=f"[bold {NEON_CYAN}]◈ CPU ◈[/]",
        subtitle=f"[{GHOST}]{len(cpu_per)} cores[/]",
        border_style=NEON_CYAN,
        box=box.HEAVY,
        padding=(0, 0),
    )


def build_ram_panel():
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    ram_history.append(mem.percent)

    text = Text()

    # RAM main gauge with donut-style ring
    color = color_for_pct(mem.percent)
    text.append("  RAM   ", style=f"bold {NEON_PINK}")

    # Neon bar
    bar_w = 22
    filled = int(mem.percent / 100 * bar_w)
    for i in range(bar_w):
        if i < filled:
            # Pink gradient
            shades = ["#ff1493", "#ff3399", "#ff4da6", "#ff66b3", "#ff80bf", "#ff99cc"]
            text.append("▰", style=f"bold {shades[i % len(shades)]}")
        else:
            text.append("▱", style=GHOST)
    text.append(f"  {mem.percent:4.1f}%\n", style=f"bold {color}")

    text.append(f"  {fmt_bytes(mem.used)}", style=NEON_PINK)
    text.append(f" / {fmt_bytes(mem.total)}", style=GHOST)
    text.append(f"   free ", style=GHOST)
    text.append(f"{fmt_bytes(mem.available)}\n", style=NEON_GREEN)

    # Memory blocks visualization
    text.append("  ")
    block_w = 30
    used_blocks = int(mem.percent / 100 * block_w)
    wired_blocks = int((mem.wired / mem.total) * block_w) if hasattr(mem, 'wired') else 0
    active_blocks = int((mem.active / mem.total) * block_w) if hasattr(mem, 'active') else 0

    for i in range(block_w):
        if i < wired_blocks:
            text.append("■", style=NEON_RED)
        elif i < wired_blocks + active_blocks:
            text.append("■", style=NEON_PINK)
        elif i < used_blocks:
            text.append("■", style=NEON_PURPLE)
        else:
            text.append("□", style=GHOST)
    text.append("\n")
    text.append("  ", style="")
    text.append("■", style=NEON_RED)
    text.append("Wired ", style=GHOST)
    text.append("■", style=NEON_PINK)
    text.append("Active ", style=GHOST)
    text.append("■", style=NEON_PURPLE)
    text.append("Inactive ", style=GHOST)
    text.append("□", style=GHOST)
    text.append("Free\n", style=GHOST)

    # Swap
    text.append("\n  SWAP  ", style=f"bold {NEON_PURPLE}")
    sw_w = 22
    sw_filled = int(swap.percent / 100 * sw_w)
    for i in range(sw_w):
        text.append("▰" if i < sw_filled else "▱", style=NEON_PURPLE if i < sw_filled else GHOST)
    text.append(f"  {swap.percent:4.1f}%\n", style=color_for_pct(swap.percent))
    text.append(f"  {fmt_bytes(swap.used)} / {fmt_bytes(swap.total)}\n", style=GHOST)

    # Sparkline
    text.append("\n  ")
    text.append_text(sparkline(ram_history, width=36))

    return Panel(
        text,
        title=f"[bold {NEON_PINK}]◈ MEMORY ◈[/]",
        subtitle=f"[{GHOST}]{fmt_bytes(mem.total)} total[/]",
        border_style=NEON_PINK,
        box=box.HEAVY,
        padding=(0, 0),
    )


def build_network_panel():
    global prev_net, prev_time

    now_time = time.time()
    net = psutil.net_io_counters()
    dt = max(now_time - prev_time, 0.1)

    sent_rate = (net.bytes_sent - prev_net.bytes_sent) / dt
    recv_rate = (net.bytes_recv - prev_net.bytes_recv) / dt

    net_sent_history.append(sent_rate)
    net_recv_history.append(recv_rate)
    prev_net = net
    prev_time = now_time

    text = Text()

    # Signal strength animation
    signal_frames = ["◜", "◝", "◞", "◟"]
    sig = signal_frames[frame_count % 4]
    text.append(f"  {sig} ", style=f"bold {NEON_GREEN}")

    # Upload
    text.append("▲ TX ", style=f"bold {NEON_GREEN}")
    text.append(f"{fmt_bytes(sent_rate)}/s", style=f"bold {NEON_GREEN}")
    text.append(f"  total {fmt_bytes(net.bytes_sent)}\n", style=GHOST)

    # Download
    text.append(f"  {sig} ", style=f"bold {NEON_CYAN}")
    text.append("▼ RX ", style=f"bold {NEON_CYAN}")
    text.append(f"{fmt_bytes(recv_rate)}/s", style=f"bold {NEON_CYAN}")
    text.append(f"  total {fmt_bytes(net.bytes_recv)}\n", style=GHOST)

    # Dual sparklines
    text.append("\n  TX ")
    line_tx, line_rx = sparkline_dual(net_sent_history, net_recv_history, width=32)
    text.append_text(line_tx)
    text.append("\n  RX ")
    text.append_text(line_rx)
    text.append("\n")

    # Live traffic visualization — animated data flow
    text.append("\n  ")
    flow_chars = "·∘○◌●◉◎"
    for i in range(30):
        idx = (frame_count + i) % len(flow_chars)
        shade = random.choice([NEON_GREEN, NEON_CYAN, GHOST])
        text.append(flow_chars[idx], style=shade)
    text.append("\n")

    # Stats
    text.append(f"  PKT ", style=GHOST)
    text.append(f"▲{net.packets_sent:>10,}", style=NEON_GREEN)
    text.append(f"  ▼{net.packets_recv:>10,}\n", style=NEON_CYAN)

    errs = net.errin + net.errout
    drops = net.dropin + net.dropout
    err_color = NEON_RED if errs > 0 else GHOST
    drop_color = NEON_ORANGE if drops > 0 else GHOST
    text.append(f"  ERR ", style=GHOST)
    text.append(f"{errs:,}", style=err_color)
    text.append(f"  DROP ", style=GHOST)
    text.append(f"{drops:,}", style=drop_color)

    # Connection count
    try:
        conns = psutil.net_connections(kind="inet")
        est = sum(1 for c in conns if c.status == "ESTABLISHED")
        listen = sum(1 for c in conns if c.status == "LISTEN")
        text.append(f"  CONN ", style=GHOST)
        text.append(f"{est}", style=NEON_CYAN)
        text.append(f"/{listen}", style=GHOST)
    except (psutil.AccessDenied, PermissionError):
        pass

    return Panel(
        text,
        title=f"[bold {NEON_GREEN}]◈ NETWORK ◈[/]",
        subtitle=f"[{GHOST}]live traffic[/]",
        border_style=NEON_GREEN,
        box=box.HEAVY,
        padding=(0, 0),
    )


def build_process_panel():
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status", "username"]):
        try:
            info = p.info
            if info["cpu_percent"] is not None:
                procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    procs.sort(key=lambda x: x["cpu_percent"] or 0, reverse=True)

    table = Table(
        box=None,
        show_edge=False,
        padding=(0, 1),
        expand=True,
        show_header=True,
        header_style=f"bold {NEON_CYAN}",
    )
    table.add_column("PID", justify="right", width=7, style=GHOST)
    table.add_column("PROCESS", ratio=1, no_wrap=True)
    table.add_column("CPU", justify="right", width=12)
    table.add_column("MEM", justify="right", width=12)
    table.add_column("ST", justify="center", width=4)

    status_map = {
        "running": (NEON_GREEN, "▶"),
        "sleeping": (GHOST, "◌"),
        "idle": (GHOST, "◌"),
        "stopped": (NEON_RED, "■"),
        "zombie": (NEON_RED, "✖"),
    }

    for i, proc in enumerate(procs[:15]):
        cpu_pct = proc["cpu_percent"] or 0
        mem_pct = proc["memory_percent"] or 0
        name = (proc["name"] or "?")[:22]

        # Color intensity based on usage
        cpu_c = color_for_pct(cpu_pct)
        mem_c = color_for_pct(mem_pct * 10)

        # Inline mini-bar for CPU
        cpu_text = Text()
        mini_w = 5
        mini_fill = min(int(cpu_pct / 100 * mini_w), mini_w)
        for bi in range(mini_w):
            cpu_text.append("▮" if bi < mini_fill else "▯", style=cpu_c if bi < mini_fill else GHOST)
        cpu_text.append(f" {cpu_pct:4.1f}", style=cpu_c)

        # Inline mini-bar for MEM
        mem_text = Text()
        mem_fill = min(int(mem_pct / 10 * mini_w), mini_w)
        for bi in range(mini_w):
            mem_text.append("▮" if bi < mem_fill else "▯", style=mem_c if bi < mem_fill else GHOST)
        mem_text.append(f" {mem_pct:4.1f}", style=mem_c)

        st_color, st_icon = status_map.get(proc["status"], (GHOST, "?"))

        # Highlight top process with glow
        name_style = f"bold {NEON_CYAN}" if i == 0 and cpu_pct > 5 else WHITE if i < 3 else GHOST

        table.add_row(
            str(proc["pid"]),
            Text(name, style=name_style),
            cpu_text,
            mem_text,
            Text(st_icon, style=st_color),
        )

    total = len(list(psutil.process_iter()))
    header = Text()
    header.append(f"  {total} processes", style=GHOST)
    header.append(f"  ─── top by CPU ───", style=GHOST)
    header.append("\n")

    return Panel(
        Group(header, table),
        title=f"[bold {NEON_YELLOW}]◈ PROCESSES ◈[/]",
        subtitle=f"[{GHOST}]top 15[/]",
        border_style=NEON_YELLOW,
        box=box.HEAVY,
        padding=(0, 0),
    )


def build_gpu_panel():
    gpu_name = get_gpu_name()
    gpu_pct = get_gpu_utilization()
    gpu_history.append(gpu_pct if gpu_pct is not None else 0)

    text = Text()
    text.append(f"  {gpu_name}\n", style=f"bold {NEON_ORANGE}")

    if gpu_pct is not None:
        color = color_for_pct(gpu_pct)
        text.append("  LOAD  ", style=GHOST)
        bar_w = 18
        filled = int(gpu_pct / 100 * bar_w)
        for i in range(bar_w):
            if i < filled:
                shades = ["#ff3300", "#ff4400", "#ff5500", "#ff6600", "#ff7700", "#ff8800"]
                text.append("▰", style=f"bold {shades[i % len(shades)]}")
            else:
                text.append("▱", style=GHOST)
        text.append(f"  {gpu_pct:4.1f}%\n", style=f"bold {color}")
    else:
        # Animated scanning indicator
        scan_pos = frame_count % 20
        text.append("  SCAN  ", style=GHOST)
        for i in range(20):
            if i == scan_pos:
                text.append("█", style=NEON_ORANGE)
            elif abs(i - scan_pos) <= 2:
                text.append("▓", style="#884400")
            else:
                text.append("░", style=GHOST)
        text.append("\n")

    text.append("  ")
    text.append_text(sparkline(gpu_history, width=30))
    text.append("\n")

    # Disk I/O
    try:
        disk = psutil.disk_io_counters()
        if disk:
            text.append(f"\n  DISK I/O  ", style=f"bold {GHOST}")
            text.append(f"R ", style=NEON_CYAN)
            text.append(f"{fmt_bytes(disk.read_bytes)}", style=WHITE)
            text.append(f"  W ", style=NEON_PINK)
            text.append(f"{fmt_bytes(disk.write_bytes)}", style=WHITE)
    except Exception:
        pass

    # Thermal
    try:
        tp = subprocess.run(
            ["sysctl", "-n", "kern.thermalmonitor.cpu_thermal_level"],
            capture_output=True, text=True, timeout=2
        )
        if tp.returncode == 0 and tp.stdout.strip():
            level = int(tp.stdout.strip())
            labels = {0: (NEON_GREEN, "COOL"), 1: (NEON_YELLOW, "WARM"),
                      2: (NEON_ORANGE, "HOT"), 3: (NEON_RED, "CRIT")}
            tc, tl = labels.get(level, (GHOST, f"LVL{level}"))
            text.append(f"\n  THERMAL ", style=GHOST)
            text.append(f"[{tl}]", style=tc)
    except Exception:
        pass

    return Panel(
        text,
        title=f"[bold {NEON_ORANGE}]◈ GPU ◈[/]",
        border_style=NEON_ORANGE,
        box=box.HEAVY,
        padding=(0, 0),
    )


def build_disk_panel():
    partitions = psutil.disk_partitions(all=False)
    text = Text()

    for p in partitions:
        try:
            usage = psutil.disk_usage(p.mountpoint)
        except (PermissionError, OSError):
            continue

        pct = usage.percent
        color = color_for_pct(pct)
        mount = p.mountpoint if len(p.mountpoint) <= 15 else "…" + p.mountpoint[-14:]

        text.append(f"  {mount:<15} ", style=GHOST)

        # Neon fill bar
        bar_w = 15
        filled = int(pct / 100 * bar_w)
        for i in range(bar_w):
            if i < filled:
                text.append("▰", style=f"bold {color}")
            else:
                text.append("▱", style=GHOST)

        text.append(f" {pct:4.1f}%", style=f"bold {color}")
        text.append(f"  {fmt_bytes(usage.used)}/{fmt_bytes(usage.total)}\n", style=GHOST)

    if not text.plain.strip():
        text.append("  No partitions found", style=GHOST)

    return Panel(
        text,
        title=f"[bold {NEON_BLUE}]◈ DISKS ◈[/]",
        border_style=NEON_BLUE,
        box=box.HEAVY,
        padding=(0, 0),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LAYOUT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def build_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=5),
        Layout(name="upper", ratio=2),
        Layout(name="lower", ratio=3),
        Layout(name="footer", size=3),
    )
    layout["upper"].split_row(
        Layout(name="cpu", ratio=1),
        Layout(name="ram", ratio=1),
        Layout(name="network", ratio=1),
    )
    layout["lower"].split_row(
        Layout(name="processes", ratio=3),
        Layout(name="right_col", ratio=2),
    )
    layout["right_col"].split_column(
        Layout(name="gpu", ratio=1),
        Layout(name="disks", ratio=1),
    )
    return layout


def render_dashboard():
    global frame_count
    frame_count += 1

    layout = build_layout()
    layout["header"].update(build_header())
    layout["cpu"].update(build_cpu_panel())
    layout["ram"].update(build_ram_panel())
    layout["network"].update(build_network_panel())
    layout["processes"].update(build_process_panel())
    layout["gpu"].update(build_gpu_panel())
    layout["disks"].update(build_disk_panel())

    # Footer with matrix rain decoration
    footer = Text()
    footer.append("  ◈ ", style=cycle_color(0))
    footer.append(f"FRAME {frame_count:05d}", style=NEON_GREEN)
    footer.append("  ◈ ", style=cycle_color(5))
    footer.append(f"REFRESH 1.0s", style=GHOST)
    footer.append("  ◈ ", style=cycle_color(10))
    footer.append(f"PY {platform.python_version()}", style=GHOST)
    footer.append("  ◈ ", style=cycle_color(15))
    footer.append(f"PID {os.getpid()}", style=GHOST)
    footer.append("  ◈ ", style=cycle_color(20))
    footer.append("CTRL+C EXIT", style=f"bold {NEON_RED}")
    footer.append("  ◈ ", style=cycle_color(25))

    # Fill remaining with matrix characters
    remaining = 40
    for i in range(remaining):
        c = random.choice("ﾊﾐﾋｰｳｼﾅﾓﾆｻﾜﾂ01234")
        shade = random.choice(["#001100", "#003300", "#005500"])
        footer.append(c, style=shade)

    layout["footer"].update(
        Panel(footer, border_style=GHOST, box=box.HORIZONTALS, padding=(0, 0))
    )
    return layout


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# BOOT SEQUENCE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def boot_sequence(console):
    """Cinematic boot-up animation."""
    console.clear()
    print("\033[?25l", end="", flush=True)

    boot_lines = [
        (NEON_GREEN, "BIOS", "Initializing system monitor..."),
        (NEON_CYAN, "KERN", f"Kernel {platform.release()} detected"),
        (NEON_CYAN, "HOST", f"Node: {platform.node()}"),
        (NEON_CYAN, "ARCH", f"Platform: {platform.machine()}"),
        (NEON_GREEN, "CPU ", f"Detecting {psutil.cpu_count()} cores..."),
        (NEON_PINK, "MEM ", f"Mapping {fmt_bytes(psutil.virtual_memory().total)} RAM..."),
        (NEON_GREEN, "NET ", "Scanning network interfaces..."),
        (NEON_ORANGE, "GPU ", "Probing graphics subsystem..."),
        (NEON_BLUE, "DISK", f"Mounting {len(psutil.disk_partitions(all=False))} volumes..."),
        (NEON_YELLOW, "PROC", "Enumerating processes..."),
        (NEON_GREEN, "DONE", "All systems operational. Launching dashboard..."),
    ]

    # ASCII art header
    logo = """
    [bright_cyan]╔═══════════════════════════════════════════════════════╗
    ║[/][bold bright_green]  ██╗     ██╗██╗   ██╗███████╗    ███████╗██╗   ██╗███████╗[/][bright_cyan]║
    ║[/][bold bright_green]  ██║     ██║██║   ██║██╔════╝    ██╔════╝╚██╗ ██╔╝██╔════╝[/][bright_cyan]║
    ║[/][bold bright_green]  ██║     ██║██║   ██║█████╗      ███████╗ ╚████╔╝ ███████╗[/][bright_cyan]║
    ║[/][bold bright_green]  ██║     ██║╚██╗ ██╔╝██╔══╝      ╚════██║  ╚██╔╝  ╚════██║[/][bright_cyan]║
    ║[/][bold bright_green]  ███████╗██║ ╚████╔╝ ███████╗    ███████║   ██║   ███████║[/][bright_cyan]║
    ║[/][bold bright_green]  ╚══════╝╚═╝  ╚═══╝  ╚══════╝    ╚══════╝   ╚═╝   ╚══════╝[/][bright_cyan]║
    ╚═══════════════════════════════════════════════════════╝[/]
"""
    console.print(logo)
    time.sleep(0.3)

    for color, tag, msg in boot_lines:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        console.print(
            f"  [{GHOST}]{timestamp}[/]  [{color}][{tag}][/]  {msg}",
            highlight=False,
        )
        time.sleep(0.12)

    # Loading bar
    console.print()
    bar_width = 50
    for i in range(bar_width + 1):
        pct = i / bar_width * 100
        filled = "█" * i
        empty = "░" * (bar_width - i)
        console.print(
            f"\r  [{NEON_GREEN}]LOADING [{filled}{empty}] {pct:5.1f}%[/]",
            end="",
            highlight=False,
        )
        time.sleep(0.02)

    console.print("\n")
    time.sleep(0.3)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    console = Console()

    # Initial CPU probe
    psutil.cpu_percent(interval=0, percpu=True)

    # Boot sequence
    boot_sequence(console)

    try:
        with Live(
            render_dashboard(),
            console=console,
            screen=True,
            refresh_per_second=2,
        ) as live:
            while True:
                time.sleep(0.5)
                live.update(render_dashboard())
    except KeyboardInterrupt:
        pass
    finally:
        print("\033[?25h", end="", flush=True)
        console.clear()
        console.print(
            Panel(
                f"[bold {NEON_GREEN}]◈ LIVE SYS terminated cleanly ◈  "
                f"Session: {str(timedelta(seconds=int((datetime.now() - start_time).total_seconds())))}  "
                f"Frames: {frame_count}[/]",
                border_style=NEON_GREEN,
                box=box.DOUBLE_EDGE,
            )
        )


if __name__ == "__main__":
    main()
