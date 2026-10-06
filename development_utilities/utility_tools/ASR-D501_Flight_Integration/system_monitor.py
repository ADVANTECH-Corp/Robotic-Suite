#!/usr/bin/env python3

"""
ASR-D501 (QCS6490) System Monitor

This script provides a graphical user interface (GUI) using Tkinter to monitor
system health metrics on the QCS6490 platform. It continuously reads standard
Linux system files to extract and display real-time hardware status.

Key Features:
- Thermal Monitoring: Reads hardware temperature sensors from `/sys/class/thermal`
  to display the maximum temperatures for the CPU, GPU, NPU (NSP), and DDR.
- CPU Usage: Calculates real-time overall CPU utilization by parsing `/proc/stat`.
- GUI Dashboard: Presents the metrics in a clean vertical card layout, featuring
  progress bars to intuitively indicate temperature levels and usage percentages.
"""

import os
import time
import tkinter as tk
from tkinter import ttk


THERMAL_PATH = "/sys/class/thermal"


# =========================
# Basic sysfs helpers
# =========================

def read_text(path):
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except Exception:
        return None


def read_float(path):
    value = read_text(path)
    if value is None:
        return None

    try:
        return float(value)
    except Exception:
        return None


def read_thermal_zones():
    """
    Return:
        {
            "cpu0-thermal": 39.1,
            "gpuss0-thermal": 36.2,
            "nspss0-thermal": 34.6,
            "ddr-thermal": 37.0,
            ...
        }
    """
    zones = {}

    if not os.path.isdir(THERMAL_PATH):
        return zones

    for name in os.listdir(THERMAL_PATH):
        if not name.startswith("thermal_zone"):
            continue

        zone_path = os.path.join(THERMAL_PATH, name)
        type_path = os.path.join(zone_path, "type")
        temp_path = os.path.join(zone_path, "temp")

        zone_type = read_text(type_path)
        temp_raw = read_float(temp_path)

        if zone_type is None or temp_raw is None:
            continue

        temp_c = temp_raw / 1000.0
        zones[zone_type] = temp_c

    return zones


def filter_temps(zones, keywords):
    result = {}

    for zone_type, temp in zones.items():
        for keyword in keywords:
            if keyword in zone_type:
                result[zone_type] = temp
                break

    return result


def max_temp(temp_dict):
    if not temp_dict:
        return None
    return max(temp_dict.values())


def fmt_temp(value):
    if value is None:
        return "N/A"
    return f"{value:.1f} °C"


def fmt_percent(value):
    if value is None:
        return "N/A"
    return f"{value:.1f} %"


# =========================
# CPU usage helper
# =========================

def read_cpu_stat():
    """
    Read /proc/stat first line.

    Example:
        cpu  123 0 456 7890 0 0 0 0 0 0

    Return:
        total_time, idle_time
    """
    text = read_text("/proc/stat")
    if not text:
        return None

    first_line = text.splitlines()[0]
    parts = first_line.split()

    if len(parts) < 5 or parts[0] != "cpu":
        return None

    try:
        values = [int(x) for x in parts[1:]]

        user = values[0]
        nice = values[1]
        system = values[2]
        idle = values[3]
        iowait = values[4] if len(values) > 4 else 0
        irq = values[5] if len(values) > 5 else 0
        softirq = values[6] if len(values) > 6 else 0
        steal = values[7] if len(values) > 7 else 0

        idle_time = idle + iowait
        non_idle_time = user + nice + system + irq + softirq + steal
        total_time = idle_time + non_idle_time

        return total_time, idle_time

    except Exception:
        return None


# =========================
# UI widgets
# =========================

class MetricCard(ttk.Frame):
    def __init__(self, master, title):
        super().__init__(master, padding=16)

        self.configure(style="Card.TFrame")

        self.title_label = ttk.Label(
            self,
            text=title,
            style="CardTitle.TLabel"
        )
        self.title_label.pack(anchor="w")

        self.value_label = ttk.Label(
            self,
            text="N/A",
            style="CardValue.TLabel"
        )
        self.value_label.pack(anchor="w", pady=(6, 10))

        self.progress = ttk.Progressbar(
            self,
            orient="horizontal",
            mode="determinate",
            maximum=100
        )
        self.progress.pack(fill="x")

        self.detail_label = ttk.Label(
            self,
            text="",
            style="CardDetail.TLabel"
        )
        self.detail_label.pack(anchor="w", pady=(8, 0))

    def update_metric(self, value_text, progress_value=None, detail_text=""):
        self.value_label.config(text=value_text)

        if progress_value is None:
            self.progress["value"] = 0
        else:
            self.progress["value"] = max(0, min(100, progress_value))

        self.detail_label.config(text=detail_text)


# =========================
# Main UI
# =========================

class QCS6490SimpleMonitorUI:
    def __init__(self, root):
        self.root = root
        self.root.title("QCS6490 Monitor")

        # Vertical layout window size
        self.root.geometry("520x1080")
        self.root.minsize(460, 620)

        self.update_interval_ms = 1000

        self.prev_cpu_total = None
        self.prev_cpu_idle = None

        self.setup_style()
        self.build_ui()
        self.update_loop()

    def setup_style(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(
            "Main.TFrame",
            background="#101418"
        )

        style.configure(
            "Header.TLabel",
            background="#101418",
            foreground="#F5F7FA",
            font=("Arial", 24, "bold")
        )

        style.configure(
            "SubHeader.TLabel",
            background="#101418",
            foreground="#AAB4C0",
            font=("Arial", 11)
        )

        style.configure(
            "Card.TFrame",
            background="#1A2027",
            relief="flat"
        )

        style.configure(
            "CardTitle.TLabel",
            background="#1A2027",
            foreground="#AAB4C0",
            font=("Arial", 12, "bold")
        )

        style.configure(
            "CardValue.TLabel",
            background="#1A2027",
            foreground="#FFFFFF",
            font=("Arial", 28, "bold")
        )

        style.configure(
            "CardDetail.TLabel",
            background="#1A2027",
            foreground="#8B96A3",
            font=("Arial", 9)
        )

        style.configure(
            "Status.TLabel",
            background="#101418",
            foreground="#AAB4C0",
            font=("Arial", 10)
        )

    def build_ui(self):
        main = ttk.Frame(self.root, style="Main.TFrame", padding=20)
        main.pack(fill="both", expand=True)

        header = ttk.Label(
            main,
            text="D501 System Monitor",
            style="Header.TLabel"
        )
        header.pack(anchor="w")

        subheader = ttk.Label(
            main,
            text="CPU / GPU / NPU / DDR temperature and CPU usage",
            style="SubHeader.TLabel"
        )
        subheader.pack(anchor="w", pady=(2, 18))

        card_frame = ttk.Frame(main, style="Main.TFrame")
        card_frame.pack(fill="both", expand=True)

        # Vertical layout: one column, five rows
        card_frame.columnconfigure(0, weight=1)

        for row in range(5):
            card_frame.rowconfigure(row, weight=1)

        self.cpu_temp_card = MetricCard(card_frame, "CPU Temp")
        self.gpu_temp_card = MetricCard(card_frame, "GPU Temp")
        self.npu_temp_card = MetricCard(card_frame, "NPU / NSP Temp")
        self.ddr_temp_card = MetricCard(card_frame, "DDR Temp")
        self.cpu_usage_card = MetricCard(card_frame, "CPU Usage")

        cards = [
            self.cpu_temp_card,
            self.gpu_temp_card,
            self.npu_temp_card,
            self.ddr_temp_card,
            self.cpu_usage_card,
        ]

        for i, card in enumerate(cards):
            card.grid(row=i, column=0, padx=8, pady=8, sticky="nsew")

        bottom_frame = ttk.Frame(main, style="Main.TFrame")
        bottom_frame.pack(fill="x", pady=(12, 0))

        self.status_label = ttk.Label(
            bottom_frame,
            text="Last update: N/A",
            style="Status.TLabel"
        )
        self.status_label.pack(side="right")

    def temp_to_progress(self, temp):
        """
        Simple temperature display mapping:
            0°C   -> 0%
            100°C -> 100%

        Example:
            40°C -> progress bar 40%
            75°C -> progress bar 75%
        """
        if temp is None:
            return None
        return temp

    def read_cpu_usage(self):
        stat = read_cpu_stat()
        if stat is None:
            return None

        total, idle = stat

        # First sample cannot calculate delta yet
        if self.prev_cpu_total is None or self.prev_cpu_idle is None:
            self.prev_cpu_total = total
            self.prev_cpu_idle = idle
            return None

        total_delta = total - self.prev_cpu_total
        idle_delta = idle - self.prev_cpu_idle

        self.prev_cpu_total = total
        self.prev_cpu_idle = idle

        if total_delta <= 0:
            return None

        usage = (1.0 - idle_delta / total_delta) * 100.0
        usage = max(0.0, min(100.0, usage))

        return usage

    def update_loop(self):
        zones = read_thermal_zones()

        cpu_temps = filter_temps(zones, ["cpu", "cpuss"])
        gpu_temps = filter_temps(zones, ["gpu", "gpuss"])
        npu_temps = filter_temps(zones, ["nsp", "nspss", "npu", "htp"])
        ddr_temps = filter_temps(zones, ["ddr"])

        cpu_max = max_temp(cpu_temps)
        gpu_max = max_temp(gpu_temps)
        npu_max = max_temp(npu_temps)
        ddr_max = max_temp(ddr_temps)

        cpu_usage = self.read_cpu_usage()

        self.cpu_temp_card.update_metric(
            fmt_temp(cpu_max),
            self.temp_to_progress(cpu_max),
            f"{len(cpu_temps)} CPU zones"
        )

        self.gpu_temp_card.update_metric(
            fmt_temp(gpu_max),
            self.temp_to_progress(gpu_max),
            ", ".join(gpu_temps.keys()) if gpu_temps else "No GPU thermal zone"
        )

        self.npu_temp_card.update_metric(
            fmt_temp(npu_max),
            self.temp_to_progress(npu_max),
            ", ".join(npu_temps.keys()) if npu_temps else "No NPU/NSP thermal zone"
        )

        self.ddr_temp_card.update_metric(
            fmt_temp(ddr_max),
            self.temp_to_progress(ddr_max),
            ", ".join(ddr_temps.keys()) if ddr_temps else "No DDR thermal zone"
        )

        self.cpu_usage_card.update_metric(
            fmt_percent(cpu_usage),
            cpu_usage,
            "/proc/stat"
        )

        now_text = time.strftime("%Y-%m-%d %H:%M:%S")
        self.status_label.config(
            text=f"Last update: {now_text}"
        )

        self.root.after(self.update_interval_ms, self.update_loop)


def main():
    root = tk.Tk()
    app = QCS6490SimpleMonitorUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
