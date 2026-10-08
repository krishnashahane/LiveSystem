#!/usr/bin/env python3
"""LiveSystem: real-time terminal system monitor."""

import os
import platform
import subprocess
import time
from collections import deque
from datetime import datetime, timedelta

import psutil
from rich import box
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

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

HISTORY_LEN = 60
cpu_history = deque(maxlen=HISTORY_LEN)
ram_history = deque(maxlen=HISTORY_LEN)
net_sent_history = deque(maxlen=HISTORY_LEN)
net_recv_history = deque(maxlen=HISTORY_LEN)
gpu_history = deque(maxlen=HISTORY_LEN)
per_core_history = []

start_time = datetime.now()
prev_net = psutil.net_io_counters()
prev_time = time.monotonic()
frame_count = 0
_gpu_name_cache = None
_gpu_name_fetched = False

SPARK = "▁▂▃▄▅▆▇█"


def cycle_color(offset=0):
    palette = [
        "#00ffff", "#00e5ff", "#00ccff", "#00b3ff", "#009fff",
        "#0088ff", "#0070ff", "#005cff", "#4d4dff", "#6b3fff",
        "#8833ff", "#a600ff", "#bf00ff", "#d400ff", "#e600ff",
        "#ff00ff", "#ff00cc", "#ff0099", "#ff0066", "#ff0033",
        "#ff0000", "#ff3300", "#ff6600", "#ff9900", "#ffcc00",
        "#ffff00", "#ccff00", "#99ff00", "#66ff00", "#39ff14",
        "#00ff33", "#00ff66", "#00ff99", "#00ffcc",
    ]
    return palette[(frame_count + offset) % len(palette)]


def color_for_pct(pct):
    if pct < 40:
        return NEON_GREEN
    if pct < 70:
        return NEON_YELLOW
    if pct < 85:
        return NEON_ORANGE
    return NEON_RED


def fmt_bytes(value):
    value = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024:
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}PB"


def sparkline(data, width=40):
    if not data:
        return Text("─" * width, style=GHOST)
    recent = list(data)[-width:]
    recent = [0] * (width - len(recent)) + recent
    max_value = max(recent) or 1
    result = Text()
    for value in recent:
        normalized = value / max_value
        idx = min(int(normalized * (len(SPARK) - 1)), len(SPARK) - 1)
        color_idx = min(int(normalized * 33), 33)
        result.append(SPARK[idx], style=cycle_color(-frame_count + color_idx))
    return result


def sparkline_dual(data1, data2, width=32):
    def line(data, color):
        values = list(data)[-width:]
        values = [0] * (width - len(values)) + values
        max_value = max(values) or 1
        result = Text()
        for value in values:
            idx = min(int((value / max_value) * (len(SPARK) - 1)), len(SPARK) - 1)
            result.append(SPARK[idx], style=color)
        return result

    return line(data1, NEON_GREEN), line(data2, NEON_CYAN)


def get_gpu_name():
    global _gpu_name_cache, _gpu_name_fetched
    if _gpu_name_fetched:
        return _gpu_name_cache

    _gpu_name_fetched = True
    if platform.system() != "Darwin":
        _gpu_name_cache = "Unsupported on this platform"
        return _gpu_name_cache

    try:
        result = subprocess.run(
            ["system_profiler", "SPDisplaysDataType"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith(("Chipset Model:", "Chip:")):
                _gpu_name_cache = stripped.split(":", 1)[1].strip()
                return _gpu_name_cache
    except (OSError, subprocess.SubprocessError):
        pass

    _gpu_name_cache = "GPU information unavailable"
    return _gpu_name_cache


def get_gpu_utilization():
    # psutil does not expose a portable GPU utilization API.
    return None


def build_header():
    now = datetime.now()
    session = str(timedelta(seconds=int((now - start_time).total_seconds())))
    boot = str(timedelta(seconds=int(time.time() - psutil.boot_time())))
    host = platform.node() or "UNKNOWN"
    os_version = f"{platform.system()} {platform.release()}"

    title = Text()
    title_chars = "◤ L I V E   S Y S T E M   M O N I T O R ◢"
    for index, char in enumerate(title_chars):
        title.append(char, style=f"bold {cycle_color(index * 2)}")

    grid = Table.grid(expand=True)
    grid.add_column(justify="left", ratio=1)
    grid.add_column(justify="center", ratio=2)
    grid.add_column(justify="right", ratio=1)

    left = Text()
    blink = "●" if frame_count % 2 == 0 else "○"
    left.append(f" {blink} ", style=NEON_GREEN if frame_count % 2 == 0 else NEON_CYAN)
    left.append(host.upper(), style=f"bold {NEON_CYAN}")
    left.append(f"  {os_version}", style=GHOST)

    right = Text()
    right.append(now.strftime("%H:%M:%S"), style=f"bold {NEON_GREEN}")
    right.append(f"  SYS {boot}", style=GHOST)
    right.append(f"  SES {session} ", style=GHOST)

    grid.add_row(left, title, right)
    grid.add_row(Text(""), Text("real-time system telemetry", style=GHOST), Text(""))

    return Panel(grid, border_style=cycle_color(), box=box.HEAVY, padding=(0, 1))


def build_cpu_panel():
    global per_core_history

    cpu_overall = psutil.cpu_percent(interval=None)
    cpu_per = psutil.cpu_percent(interval=None, percpu=True)
    cpu_freq = psutil.cpu_freq()
    cpu_history.append(cpu_overall)

    if len(per_core_history) != len(cpu_per):
        per_core_history = [deque(maxlen=20) for _ in cpu_per]
    for index, pct in enumerate(cpu_per):
        per_core_history[index].append(pct)

    text = Text()
    text.append("  TOTAL ", style=f"bold {NEON_CYAN}")
    bar_width = 20
    filled = min(int(cpu_overall / 100 * bar_width), bar_width)
    for i in range(bar_width):
        text.append("▰" if i < filled else "▱", style=color_for_pct(cpu_overall) if i < filled else GHOST)
    text.append(f"  {cpu_overall:5.1f}%", style=f"bold {color_for_pct(cpu_overall)}")
    if cpu_freq:
        text.append(f"  {cpu_freq.current:.0f}MHz", style=GHOST)
    text.append("\n")

    columns = 2
    rows = (len(cpu_per) + columns - 1) // columns
    for row in range(rows):
        for column in range(columns):
            index = row + column * rows
            if index >= len(cpu_per):
                continue
            pct = cpu_per[index]
            color = color_for_pct(pct)
            text.append(f"  C{index:<2}", style=GHOST)
            mini_width = 8
            mini_fill = min(int(pct / 100 * mini_width), mini_width)
            for i in range(mini_width):
                text.append("█" if i < mini_fill else "░", style=color if i < mini_fill else GHOST)
            text.append(f" {pct:4.0f}%  ", style=color)
        text.append("\n")

    text.append("\n  ")
    text.append_text(sparkline(cpu_history, width=36))
    load = getattr(os, "getloadavg", None)
    if load:
        load1, load5, load15 = load()
        text.append("\n  LOAD ", style=GHOST)
        for value, label in ((load1, "1m"), (load5, "5m"), (load15, "15m")):
            load_color = NEON_GREEN if value < 4 else NEON_YELLOW if value < 8 else NEON_RED
            text.append(f"{value:.1f}", style=load_color)
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
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    ram_history.append(memory.percent)

    text = Text()
    color = color_for_pct(memory.percent)
    text.append("  RAM   ", style=f"bold {NEON_PINK}")
    bar_width = 22
    filled = min(int(memory.percent / 100 * bar_width), bar_width)
    for i in range(bar_width):
        text.append("▰" if i < filled else "▱", style=f"bold {NEON_PINK}" if i < filled else GHOST)
    text.append(f"  {memory.percent:4.1f}%\n", style=f"bold {color}")
    text.append(f"  {fmt_bytes(memory.used)}", style=NEON_PINK)
    text.append(f" / {fmt_bytes(memory.total)}", style=GHOST)
    text.append("   free ", style=GHOST)
    text.append(f"{fmt_bytes(memory.available)}\n", style=NEON_GREEN)

    text.append("  ")
    bar_width = 30
    used_blocks = min(int(memory.percent / 100 * bar_width), bar_width)
    active_ratio = getattr(memory, "active", 0) / memory.total if memory.total else 0
    active_blocks = min(int(active_ratio * bar_width), bar_width)
    for i in range(bar_width):
        if i < active_blocks:
            text.append("■", style=NEON_PINK)
        elif i < used_blocks:
            text.append("■", style=NEON_PURPLE)
        else:
            text.append("□", style=GHOST)
    text.append("\n  ")
    text.append("■", style=NEON_PINK)
    text.append("Active ", style=GHOST)
    text.append("■", style=NEON_PURPLE)
    text.append("Used ", style=GHOST)
    text.append("□", style=GHOST)
    text.append("Free\n", style=GHOST)

    text.append("\n  SWAP  ", style=f"bold {NEON_PURPLE}")
    swap_width = 22
    swap_fill = min(int(swap.percent / 100 * swap_width), swap_width)
    for i in range(swap_width):
        text.append("▰" if i < swap_fill else "▱", style=NEON_PURPLE if i < swap_fill else GHOST)
    text.append(f"  {swap.percent:4.1f}%\n", style=color_for_pct(swap.percent))
    text.append(f"  {fmt_bytes(swap.used)} / {fmt_bytes(swap.total)}\n", style=GHOST)
    text.append("\n  ")
    text.append_text(sparkline(ram_history, width=36))

    return Panel(
        text,
        title=f"[bold {NEON_PINK}]◈ MEMORY ◈[/]",
        subtitle=f"[{GHOST}]{fmt_bytes(memory.total)} total[/]",
        border_style=NEON_PINK,
        box=box.HEAVY,
        padding=(0, 0),
    )


def build_network_panel():
    global prev_net, prev_time

    current_time = time.monotonic()
    net = psutil.net_io_counters()
    interval = max(current_time - prev_time, 0.1)
    sent_rate = max(0, (net.bytes_sent - prev_net.bytes_sent) / interval)
    recv_rate = max(0, (net.bytes_recv - prev_net.bytes_recv) / interval)

    net_sent_history.append(sent_rate)
    net_recv_history.append(recv_rate)
    prev_net = net
    prev_time = current_time

    text = Text()
    signal_frames = ("◜", "◝", "◞", "◟")
    signal = signal_frames[frame_count % len(signal_frames)]

    text.append(f"  {signal} ", style=f"bold {NEON_GREEN}")
    text.append("▲ TX ", style=f"bold {NEON_GREEN}")
    text.append(f"{fmt_bytes(sent_rate)}/s", style=f"bold {NEON_GREEN}")
    text.append(f"  total {fmt_bytes(net.bytes_sent)}\n", style=GHOST)

    text.append(f"  {signal} ", style=f"bold {NEON_CYAN}")
    text.append("▼ RX ", style=f"bold {NEON_CYAN}")
    text.append(f"{fmt_bytes(recv_rate)}/s", style=f"bold {NEON_CYAN}")
    text.append(f"  total {fmt_bytes(net.bytes_recv)}\n", style=GHOST)

    text.append("\n  TX ")
    tx, rx = sparkline_dual(net_sent_history, net_recv_history)
    text.append_text(tx)
    text.append("\n  RX ")
    text.append_text(rx)
    text.append("\n\n  ")
    flow_chars = "·∘○◌●◉◎"
    for i in range(30):
        text.append(flow_chars[(frame_count + i) % len(flow_chars)], style=(NEON_GREEN, NEON_CYAN, GHOST)[(frame_count + i) % 3])
    text.append("\n")

    text.append("  PKT ", style=GHOST)
    text.append(f"▲{net.packets_sent:>10,}", style=NEON_GREEN)
    text.append(f"  ▼{net.packets_recv:>10,}\n", style=NEON_CYAN)

    errors = net.errin + net.errout
    drops = net.dropin + net.dropout
    text.append("  ERR ", style=GHOST)
    text.append(f"{errors:,}", style=NEON_RED if errors else GHOST)
    text.append("  DROP ", style=GHOST)
    text.append(f"{drops:,}", style=NEON_ORANGE if drops else GHOST)

    try:
        connections = psutil.net_connections(kind="inet")
        established = sum(c.status == "ESTABLISHED" for c in connections)
        listening = sum(c.status == "LISTEN" for c in connections)
        text.append("  CONN ", style=GHOST)
        text.append(str(established), style=NEON_CYAN)
        text.append(f"/{listening}", style=GHOST)
    except (psutil.AccessDenied, OSError):
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
    processes = []
    for process in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent", "status"]):
        try:
            info = process.info
            processes.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    processes.sort(key=lambda item: item.get("cpu_percent") or 0, reverse=True)

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

    for index, process in enumerate(processes[:15]):
        cpu = process.get("cpu_percent") or 0
        memory = process.get("memory_percent") or 0
        name = (process.get("name") or "?")[:22]
        status = process.get("status") or "?"
        status_color, status_icon = status_map.get(status, (GHOST, "?"))

        table.add_row(
            str(process.get("pid", "?")),
            Text(name, style=f"bold {NEON_CYAN}" if index == 0 and cpu > 5 else WHITE if index < 3 else GHOST),
            Text(f"{cpu:5.1f}%", style=color_for_pct(cpu)),
            Text(f"{memory:5.1f}%", style=color_for_pct(memory * 10)),
            Text(status_icon, style=status_color),
        )

    header = Text()
    header.append(f"  {len(processes)} processes", style=GHOST)
    header.append("  ─── top by CPU ───", style=GHOST)
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
    name = get_gpu_name()
    utilization = get_gpu_utilization()
    gpu_history.append(utilization if utilization is not None else 0)

    text = Text()
    text.append(f"  {name}\n", style=f"bold {NEON_ORANGE}")

    if utilization is not None:
        text.append("  LOAD  ", style=GHOST)
        width = 18
        fill = min(int(utilization / 100 * width), width)
        for i in range(width):
            text.append("▰" if i < fill else "▱", style=NEON_ORANGE if i < fill else GHOST)
        text.append(f"  {utilization:4.1f}%\n", style=f"bold {color_for_pct(utilization)}")
    else:
        text.append("  LOAD  unavailable\n", style=GHOST)

    text.append("  ")
    text.append_text(sparkline(gpu_history, width=30))
    text.append("\n")

    try:
        disk = psutil.disk_io_counters()
        if disk:
            text.append("\n  DISK I/O  ", style=f"bold {GHOST}")
            text.append("R ", style=NEON_CYAN)
            text.append(fmt_bytes(disk.read_bytes), style=WHITE)
            text.append("  W ", style=NEON_PINK)
            text.append(fmt_bytes(disk.write_bytes), style=WHITE)
    except OSError:
        pass

    if platform.system() == "Darwin":
        try:
            thermal = subprocess.run(
                ["sysctl", "-n", "kern.thermalmonitor.cpu_thermal_level"],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if thermal.returncode == 0 and thermal.stdout.strip():
                level = int(thermal.stdout.strip())
                labels = {
                    0: (NEON_GREEN, "COOL"),
                    1: (NEON_YELLOW, "WARM"),
                    2: (NEON_ORANGE, "HOT"),
                    3: (NEON_RED, "CRIT"),
                }
                thermal_color, label = labels.get(level, (GHOST, f"LVL{level}"))
                text.append("\n  THERMAL ", style=GHOST)
                text.append(f"[{label}]", style=thermal_color)
        except (OSError, ValueError, subprocess.SubprocessError):
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

    for partition in partitions:
        try:
            usage = psutil.disk_usage(partition.mountpoint)
        except (OSError, PermissionError):
            continue

        mount = partition.mountpoint
        if len(mount) > 15:
            mount = "…" + mount[-14:]
        color = color_for_pct(usage.percent)
        text.append(f"  {mount:<15} ", style=GHOST)

        width = 15
        fill = min(int(usage.percent / 100 * width), width)
        for i in range(width):
            text.append("▰" if i < fill else "▱", style=color if i < fill else GHOST)

        text.append(f" {usage.percent:4.1f}%", style=f"bold {color}")
        text.append(f"  {fmt_bytes(usage.used)}/{fmt_bytes(usage.total)}\n", style=GHOST)

    if not text.plain.strip():
        text.append("  No readable partitions found", style=GHOST)

    return Panel(
        text,
        title=f"[bold {NEON_BLUE}]◈ DISKS ◈[/]",
        border_style=NEON_BLUE,
        box=box.HEAVY,
        padding=(0, 0),
    )


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

    footer = Text()
    footer.append("  ◈ ", style=cycle_color())
    footer.append(f"FRAME {frame_count:05d}", style=NEON_GREEN)
    footer.append("  ◈ ", style=cycle_color(5))
    footer.append("REFRESH 1.0s", style=GHOST)
    footer.append("  ◈ ", style=cycle_color(10))
    footer.append(f"PY {platform.python_version()}", style=GHOST)
    footer.append("  ◈ ", style=cycle_color(15))
    footer.append(f"PID {os.getpid()}", style=GHOST)
    footer.append("  ◈ ", style=cycle_color(20))
    footer.append("CTRL+C EXIT", style=f"bold {NEON_RED}")

    layout["footer"].update(Panel(footer, border_style=GHOST, box=box.HORIZONTALS, padding=(0, 0)))
    return layout


def boot_sequence(console):
    console.clear()
    if console.is_terminal:
        print("\033[?25l", end="", flush=True)

    lines = [
        (NEON_GREEN, "BIOS", "Initializing system monitor..."),
        (NEON_CYAN, "KERN", f"Kernel {platform.release()} detected"),
        (NEON_CYAN, "HOST", f"Node: {platform.node() or 'UNKNOWN'}"),
        (NEON_CYAN, "ARCH", f"Platform: {platform.machine()}"),
        (NEON_GREEN, "CPU ", f"Detecting {psutil.cpu_count()} logical CPUs..."),
        (NEON_PINK, "MEM ", f"Mapping {fmt_bytes(psutil.virtual_memory().total)} RAM..."),
        (NEON_GREEN, "NET ", "Reading network counters..."),
        (NEON_ORANGE, "GPU ", "Probing graphics subsystem..."),
        (NEON_BLUE, "DISK", f"Reading {len(psutil.disk_partitions(all=False))} volumes..."),
        (NEON_YELLOW, "PROC", "Enumerating processes..."),
        (NEON_GREEN, "DONE", "Launching dashboard..."),
    ]

    for color, tag, message in lines:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        console.print(
            f"  [{GHOST}]{timestamp}[/]  [{color}][{tag}][/]  {message}",
            highlight=False,
        )
        time.sleep(0.04)


def main():
    console = Console()
    psutil.cpu_percent(interval=None, percpu=True)
    boot_sequence(console)

    try:
        with Live(
            render_dashboard(),
            console=console,
            screen=console.is_terminal,
            refresh_per_second=2,
        ) as live:
            while True:
                time.sleep(1.0)
                live.update(render_dashboard())
    except KeyboardInterrupt:
        pass
    finally:
        if console.is_terminal:
            print("\033[?25h", end="", flush=True)
            console.clear()
        session = str(timedelta(seconds=int((datetime.now() - start_time).total_seconds())))
        console.print(
            Panel(
                f"[bold {NEON_GREEN}]◈ LiveSystem stopped cleanly ◈  "
                f"Session: {session}  Frames: {frame_count}[/]",
                border_style=NEON_GREEN,
                box=box.DOUBLE_EDGE,
            )
        )


if __name__ == "__main__":
    main()
