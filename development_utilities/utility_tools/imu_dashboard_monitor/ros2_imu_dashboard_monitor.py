#!/usr/bin/env python3
"""
ROS 2 IMU Dashboard Monitor

Displayed data:
  1. 3-axis acceleration       sensor_msgs/msg/Imu
  2. 3-axis angular velocity   sensor_msgs/msg/Imu
  3. 3-axis magnetic field     sensor_msgs/msg/MagneticField
  4. Roll / Pitch / Yaw        geometry_msgs/msg/Vector3Stamped

This sample is a ROS 2 topic monitor and dashboard.
It does not publish commands and does not control hardware.

Example:
  python3 ros2_imu_dashboard_monitor.py --ros-args \
    -p imu_topic:=/imu/data \
    -p mag_topic:=/imu/mag \
    -p euler_topic:=/filter/euler \
    -p euler_auto_zero_sec:=10.0
"""

import math
import threading
import time
import tkinter as tk
from collections import deque
from dataclasses import dataclass

import rclpy
from rclpy.node import Node

from sensor_msgs.msg import Imu, MagneticField
from geometry_msgs.msg import Vector3Stamped

from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


# ============================================================
# Configuration
# ============================================================
@dataclass
class DashboardConfig:
    # ROS topics
    imu_topic: str = "/imu/data"
    mag_topic: str = "/imu/mag"
    euler_topic: str = "/filter/euler"

    # UI update behavior
    ui_update_ms: int = 100
    plot_update_ms: int = 150
    plot_buffer_len: int = 200

    # Euler input unit
    # False: /filter/euler is already in degrees.
    # True : /filter/euler is in radians and will be converted to degrees.
    euler_rad_to_deg: bool = False

    # Demo-friendly Roll/Pitch/Yaw behavior
    # The first Euler sample becomes the 0-degree reference.
    # If euler_auto_zero_sec > 0, the current attitude becomes the new 0-degree
    # reference periodically to reduce visible drift during a live demo.
    euler_auto_zero_sec: float = 10.0
    euler_enable_unwrap: bool = True
    euler_enable_smoothing: bool = True
    euler_smooth_alpha: float = 0.25

    # Plot range and display clipping are in degrees.
    rpy_plot_y_limit_deg: float = 90.0
    rpy_display_clip_deg: float = 90.0

    # Window text
    window_title: str = "ROS 2 IMU Dashboard Monitor"
    header_title: str = "ROS 2 IMU Dashboard"


def load_config_from_ros_params(node: Node) -> DashboardConfig:
    """Declare and read ROS 2 parameters for the dashboard."""

    defaults = DashboardConfig()

    node.declare_parameter("imu_topic", defaults.imu_topic)
    node.declare_parameter("mag_topic", defaults.mag_topic)
    node.declare_parameter("euler_topic", defaults.euler_topic)

    node.declare_parameter("ui_update_ms", defaults.ui_update_ms)
    node.declare_parameter("plot_update_ms", defaults.plot_update_ms)
    node.declare_parameter("plot_buffer_len", defaults.plot_buffer_len)

    node.declare_parameter("euler_rad_to_deg", defaults.euler_rad_to_deg)
    node.declare_parameter("euler_auto_zero_sec", defaults.euler_auto_zero_sec)
    node.declare_parameter("euler_enable_unwrap", defaults.euler_enable_unwrap)
    node.declare_parameter("euler_enable_smoothing", defaults.euler_enable_smoothing)
    node.declare_parameter("euler_smooth_alpha", defaults.euler_smooth_alpha)

    node.declare_parameter("rpy_plot_y_limit_deg", defaults.rpy_plot_y_limit_deg)
    node.declare_parameter("rpy_display_clip_deg", defaults.rpy_display_clip_deg)

    node.declare_parameter("window_title", defaults.window_title)
    node.declare_parameter("header_title", defaults.header_title)

    config = DashboardConfig(
        imu_topic=str(node.get_parameter("imu_topic").value),
        mag_topic=str(node.get_parameter("mag_topic").value),
        euler_topic=str(node.get_parameter("euler_topic").value),

        ui_update_ms=int(node.get_parameter("ui_update_ms").value),
        plot_update_ms=int(node.get_parameter("plot_update_ms").value),
        plot_buffer_len=int(node.get_parameter("plot_buffer_len").value),

        euler_rad_to_deg=bool(node.get_parameter("euler_rad_to_deg").value),
        euler_auto_zero_sec=float(node.get_parameter("euler_auto_zero_sec").value),
        euler_enable_unwrap=bool(node.get_parameter("euler_enable_unwrap").value),
        euler_enable_smoothing=bool(node.get_parameter("euler_enable_smoothing").value),
        euler_smooth_alpha=float(node.get_parameter("euler_smooth_alpha").value),

        rpy_plot_y_limit_deg=float(node.get_parameter("rpy_plot_y_limit_deg").value),
        rpy_display_clip_deg=float(node.get_parameter("rpy_display_clip_deg").value),

        window_title=str(node.get_parameter("window_title").value),
        header_title=str(node.get_parameter("header_title").value),
    )

    return validate_config(config)


def validate_config(config: DashboardConfig) -> DashboardConfig:
    """Keep parameter values in a safe and usable range."""

    config.ui_update_ms = max(20, int(config.ui_update_ms))
    config.plot_update_ms = max(20, int(config.plot_update_ms))
    config.plot_buffer_len = max(10, int(config.plot_buffer_len))

    # euler_auto_zero_sec <= 0 means: only zero at startup, no periodic re-zero.
    config.euler_auto_zero_sec = max(0.0, float(config.euler_auto_zero_sec))
    config.euler_smooth_alpha = clamp(float(config.euler_smooth_alpha), 0.0, 1.0)

    config.rpy_plot_y_limit_deg = max(1.0, float(config.rpy_plot_y_limit_deg))
    config.rpy_display_clip_deg = max(1.0, float(config.rpy_display_clip_deg))

    return config


# ============================================================
# Helpers
# ============================================================
def clamp(value, low, high):
    return max(low, min(high, value))


def vector_magnitude(x, y, z):
    return math.sqrt(x * x + y * y + z * z)


def maybe_rad_to_deg(value, config: DashboardConfig):
    return math.degrees(value) if config.euler_rad_to_deg else value


def normalize_angle_delta(value, half_range, full_range):
    """
    Normalize an angle delta into [-half_range, +half_range].

    Example in degrees:
      previous = 179, current = -179
      raw delta = -358
      normalized delta = +2

    This keeps internal angle changes continuous when the Euler output
    crosses the +180/-180 boundary.
    """
    while value > half_range:
        value -= full_range
    while value < -half_range:
        value += full_range
    return value


def limit_angle_for_demo_display(value, half_range):
    """
    Clip/saturate the display value instead of wrapping it.

    This avoids visible jumps such as +181 -> -179 and also avoids confusing
    values such as +200, -200, or +2000 deg on the UI.
    """
    return clamp(value, -half_range, half_range)


# ============================================================
# Shared State
# ============================================================
class ImuDashboardState:
    def __init__(self, config: DashboardConfig):
        self.config = config
        self.lock = threading.Lock()

        self.last_any_msg_time = 0.0

        self.imu_hz = 0.0
        self.mag_hz = 0.0
        self.euler_hz = 0.0

        self._imu_count = 0
        self._mag_count = 0
        self._euler_count = 0

        self._imu_last_count_time = time.time()
        self._mag_last_count_time = time.time()
        self._euler_last_count_time = time.time()

        self.acc = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.gyro = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.mag = {"x": 0.0, "y": 0.0, "z": 0.0}

        self.euler = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
        self.euler_unit = "deg"

        self.euler_zero_offset = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
        self._euler_zero_initialized = False
        self._euler_last_zero_time = 0.0

        # For demo-friendly Roll/Pitch/Yaw plotting:
        # _last_raw_euler tracks the previous raw Euler sample.
        # _continuous_euler accumulates corrected angle deltas so the line stays continuous.
        # _smooth_euler is the final plotted value after light smoothing.
        self._last_raw_euler = {"roll": None, "pitch": None, "yaw": None}
        self._continuous_euler = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
        self._smooth_euler = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
        self._smooth_initialized = False

        self.roll_buf = deque(maxlen=config.plot_buffer_len)
        self.pitch_buf = deque(maxlen=config.plot_buffer_len)
        self.yaw_buf = deque(maxlen=config.plot_buffer_len)

    def _update_hz(self, count_attr, last_time_attr, hz_attr):
        now = time.time()
        count = getattr(self, count_attr)
        last = getattr(self, last_time_attr)
        dt = now - last

        if dt >= 1.0:
            setattr(self, hz_attr, count / dt)
            setattr(self, count_attr, 0)
            setattr(self, last_time_attr, now)

    def update_imu(self, msg: Imu):
        now = time.time()
        with self.lock:
            self.last_any_msg_time = now

            self.acc["x"] = msg.linear_acceleration.x
            self.acc["y"] = msg.linear_acceleration.y
            self.acc["z"] = msg.linear_acceleration.z

            self.gyro["x"] = msg.angular_velocity.x
            self.gyro["y"] = msg.angular_velocity.y
            self.gyro["z"] = msg.angular_velocity.z

            self._imu_count += 1
            self._update_hz("_imu_count", "_imu_last_count_time", "imu_hz")

    def update_mag(self, msg: MagneticField):
        now = time.time()
        with self.lock:
            self.last_any_msg_time = now

            self.mag["x"] = msg.magnetic_field.x
            self.mag["y"] = msg.magnetic_field.y
            self.mag["z"] = msg.magnetic_field.z

            self._mag_count += 1
            self._update_hz("_mag_count", "_mag_last_count_time", "mag_hz")

    def update_euler(self, msg: Vector3Stamped):
        now = time.time()
        cfg = self.config

        with self.lock:
            self.last_any_msg_time = now

            raw_roll = maybe_rad_to_deg(msg.vector.x, cfg)
            raw_pitch = maybe_rad_to_deg(msg.vector.y, cfg)
            raw_yaw = maybe_rad_to_deg(msg.vector.z, cfg)

            # Demo zeroing:
            # 1. The first received Euler value becomes Roll/Pitch/Yaw = 0.
            # 2. If euler_auto_zero_sec > 0, the current attitude becomes the
            #    new zero point periodically to reduce visible drift.
            # 3. Set euler_auto_zero_sec:=0.0 to disable periodic re-zero.
            need_initial_zero = not self._euler_zero_initialized
            need_periodic_zero = (
                self._euler_zero_initialized
                and cfg.euler_auto_zero_sec > 0.0
                and (now - self._euler_last_zero_time) >= cfg.euler_auto_zero_sec
            )
            need_rezero = need_initial_zero or need_periodic_zero

            if need_rezero:
                self.euler_zero_offset["roll"] = raw_roll
                self.euler_zero_offset["pitch"] = raw_pitch
                self.euler_zero_offset["yaw"] = raw_yaw

                self._last_raw_euler["roll"] = raw_roll
                self._last_raw_euler["pitch"] = raw_pitch
                self._last_raw_euler["yaw"] = raw_yaw

                self._continuous_euler["roll"] = 0.0
                self._continuous_euler["pitch"] = 0.0
                self._continuous_euler["yaw"] = 0.0

                self._smooth_euler["roll"] = 0.0
                self._smooth_euler["pitch"] = 0.0
                self._smooth_euler["yaw"] = 0.0
                self._smooth_initialized = True

                self._euler_zero_initialized = True
                self._euler_last_zero_time = now

            # After maybe_rad_to_deg(), raw_roll/raw_pitch/raw_yaw are always
            # handled in degrees. The unwrap range is therefore always 180/360.
            half_range = 180.0
            full_range = 360.0

            # Angle unwrap:
            # Instead of plotting raw Euler angle directly, accumulate the
            # corrected delta. This fixes cases like 179 -> -179, which should
            # be +2 degrees, not -358 degrees.
            for key, raw_value in (
                ("roll", raw_roll),
                ("pitch", raw_pitch),
                ("yaw", raw_yaw),
            ):
                last_raw = self._last_raw_euler[key]

                if last_raw is None:
                    delta = 0.0
                else:
                    delta = raw_value - last_raw
                    if cfg.euler_enable_unwrap:
                        delta = normalize_angle_delta(delta, half_range, full_range)

                self._continuous_euler[key] += delta
                self._last_raw_euler[key] = raw_value

            roll = self._continuous_euler["roll"]
            pitch = self._continuous_euler["pitch"]
            yaw = self._continuous_euler["yaw"]

            # Light smoothing for demo visualization.
            # Larger alpha = faster response, smaller alpha = smoother line.
            if cfg.euler_enable_smoothing:
                alpha = clamp(cfg.euler_smooth_alpha, 0.0, 1.0)

                if not self._smooth_initialized:
                    self._smooth_euler["roll"] = roll
                    self._smooth_euler["pitch"] = pitch
                    self._smooth_euler["yaw"] = yaw
                    self._smooth_initialized = True
                else:
                    self._smooth_euler["roll"] = (
                        alpha * roll + (1.0 - alpha) * self._smooth_euler["roll"]
                    )
                    self._smooth_euler["pitch"] = (
                        alpha * pitch + (1.0 - alpha) * self._smooth_euler["pitch"]
                    )
                    self._smooth_euler["yaw"] = (
                        alpha * yaw + (1.0 - alpha) * self._smooth_euler["yaw"]
                    )

                roll = self._smooth_euler["roll"]
                pitch = self._smooth_euler["pitch"]
                yaw = self._smooth_euler["yaw"]

            display_roll = limit_angle_for_demo_display(roll, cfg.rpy_display_clip_deg)
            display_pitch = limit_angle_for_demo_display(pitch, cfg.rpy_display_clip_deg)
            display_yaw = limit_angle_for_demo_display(yaw, cfg.rpy_display_clip_deg)

            self.euler["roll"] = display_roll
            self.euler["pitch"] = display_pitch
            self.euler["yaw"] = display_yaw

            self.roll_buf.append(display_roll)
            self.pitch_buf.append(display_pitch)
            self.yaw_buf.append(display_yaw)

            self._euler_count += 1
            self._update_hz("_euler_count", "_euler_last_count_time", "euler_hz")

    def snapshot(self):
        with self.lock:
            return {
                "last_any_msg_time": self.last_any_msg_time,

                "imu_hz": self.imu_hz,
                "mag_hz": self.mag_hz,
                "euler_hz": self.euler_hz,

                "acc": dict(self.acc),
                "gyro": dict(self.gyro),
                "mag": dict(self.mag),
                "euler": dict(self.euler),
                "euler_unit": self.euler_unit,

                "roll_buf": list(self.roll_buf),
                "pitch_buf": list(self.pitch_buf),
                "yaw_buf": list(self.yaw_buf),
            }


# ============================================================
# ROS 2 Node
# ============================================================
class ImuDashboardNode(Node):
    def __init__(self):
        super().__init__("imu_dashboard_monitor")

        self.config = load_config_from_ros_params(self)
        self.state = ImuDashboardState(self.config)

        self.create_subscription(Imu, self.config.imu_topic, self.imu_callback, 10)
        self.create_subscription(MagneticField, self.config.mag_topic, self.mag_callback, 10)
        self.create_subscription(Vector3Stamped, self.config.euler_topic, self.euler_callback, 10)

        self.get_logger().info("ROS 2 IMU Dashboard Monitor started")
        self.get_logger().info(f"Subscribing to IMU   : {self.config.imu_topic}")
        self.get_logger().info(f"Subscribing to Mag   : {self.config.mag_topic}")
        self.get_logger().info(f"Subscribing to Euler : {self.config.euler_topic}")
        self.get_logger().info(
            "Euler options: "
            f"rad_to_deg={self.config.euler_rad_to_deg}, "
            f"auto_zero_sec={self.config.euler_auto_zero_sec}, "
            f"unwrap={self.config.euler_enable_unwrap}, "
            f"smoothing={self.config.euler_enable_smoothing}, "
            f"alpha={self.config.euler_smooth_alpha}"
        )

    def imu_callback(self, msg):
        self.state.update_imu(msg)

    def mag_callback(self, msg):
        self.state.update_mag(msg)

    def euler_callback(self, msg):
        self.state.update_euler(msg)


# ============================================================
# UI Components
# ============================================================
class MetricCard(tk.Frame):
    def __init__(self, parent, title, value="--", subtitle=""):
        super().__init__(
            parent,
            bg="#111827",
            highlightthickness=1,
            highlightbackground="#263449",
        )

        self.title_label = tk.Label(
            self,
            text=title,
            font=("Segoe UI", 10, "bold"),
            fg="#93A4B8",
            bg="#111827",
            anchor="w",
        )
        self.title_label.pack(fill="x", padx=12, pady=(8, 2))

        self.value_label = tk.Label(
            self,
            text=value,
            font=("Consolas", 16, "bold"),
            fg="#FFFFFF",
            bg="#111827",
            anchor="w",
        )
        self.value_label.pack(fill="x", padx=12)

        self.subtitle_label = tk.Label(
            self,
            text=subtitle,
            font=("Segoe UI", 9),
            fg="#7C8EA3",
            bg="#111827",
            anchor="w",
        )
        self.subtitle_label.pack(fill="x", padx=12, pady=(0, 8))

    def set_value(self, value, subtitle=None, color=None):
        self.value_label.config(text=value)
        if subtitle is not None:
            self.subtitle_label.config(text=subtitle)
        if color is not None:
            self.value_label.config(fg=color)


class ValueBar(tk.Frame):
    def __init__(self, parent, title, unit="", min_value=-10.0, max_value=10.0):
        super().__init__(parent, bg="#101827")

        self.title = title
        self.unit = unit
        self.min_value = min_value
        self.max_value = max_value

        top = tk.Frame(self, bg="#101827")
        top.pack(fill="x")

        self.label_title = tk.Label(
            top,
            text=title,
            font=("Segoe UI", 9, "bold"),
            fg="#DCE7F7",
            bg="#101827",
            anchor="w",
        )
        self.label_title.pack(side="left")

        self.label_value = tk.Label(
            top,
            text="0.000",
            font=("Consolas", 10, "bold"),
            fg="#FFFFFF",
            bg="#101827",
            anchor="e",
        )
        self.label_value.pack(side="right")

        self.canvas = tk.Canvas(
            self,
            height=13,
            bg="#0B1220",
            highlightthickness=0,
        )
        self.canvas.pack(fill="x", pady=(4, 0))

    def update_value(self, value):
        value = float(value)

        self.canvas.delete("all")

        w = max(self.canvas.winfo_width(), 80)
        h = 13

        self.canvas.create_rectangle(0, 0, w, h, fill="#1C2A3A", outline="")

        ratio = 0.5 if self.max_value == self.min_value else (
            (value - self.min_value) / (self.max_value - self.min_value)
        )
        ratio = clamp(ratio, 0.0, 1.0)

        zero_ratio = 0.5 if self.max_value == self.min_value else (
            (0.0 - self.min_value) / (self.max_value - self.min_value)
        )
        zero_ratio = clamp(zero_ratio, 0.0, 1.0)

        zero_x = int(zero_ratio * w)
        value_x = int(ratio * w)

        self.canvas.create_line(zero_x, 0, zero_x, h, fill="#6B7280", width=2)

        if value_x >= zero_x:
            self.canvas.create_rectangle(zero_x, 0, value_x, h, fill="#38BDF8", outline="")
        else:
            self.canvas.create_rectangle(value_x, 0, zero_x, h, fill="#F97316", outline="")

        self.label_value.config(text=f"{value: .5f} {self.unit}")


class Section(tk.LabelFrame):
    def __init__(self, parent, title):
        super().__init__(
            parent,
            text=title,
            font=("Segoe UI", 11, "bold"),
            fg="#FFFFFF",
            bg="#101827",
            bd=1,
            relief="solid",
            labelanchor="nw",
        )
        self.configure(highlightthickness=1, highlightbackground="#263449")


class RpyPlot(tk.Frame):
    def __init__(self, parent, config: DashboardConfig):
        super().__init__(parent, bg="#101827")
        self.config = config

        self.fig = Figure(figsize=(7, 3.0), dpi=100)
        self.ax = self.fig.add_subplot(111)

        self.fig.patch.set_facecolor("#101827")
        self.ax.set_facecolor("#0B1220")

        self.ax.tick_params(colors="#DCE7F7")
        self.ax.xaxis.label.set_color("#DCE7F7")
        self.ax.yaxis.label.set_color("#DCE7F7")
        self.ax.title.set_color("#FFFFFF")

        for spine in self.ax.spines.values():
            spine.set_color("#334155")

        self.ax.set_title("")
        self.ax.set_ylim(-config.rpy_plot_y_limit_deg, config.rpy_plot_y_limit_deg)
        self.ax.set_ylabel("deg")
        self.ax.grid(True, alpha=0.25)

        self.roll_line, = self.ax.plot([], [], label="Roll")
        self.pitch_line, = self.ax.plot([], [], label="Pitch")
        self.yaw_line, = self.ax.plot([], [], label="Yaw")

        legend = self.ax.legend(loc="upper right")
        legend.get_frame().set_facecolor("#111827")
        legend.get_frame().set_edgecolor("#334155")
        for text in legend.get_texts():
            text.set_color("#DCE7F7")

        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=6)

    def update_plot(self, roll_buf, pitch_buf, yaw_buf):
        n = max(len(roll_buf), len(pitch_buf), len(yaw_buf))
        x = list(range(n))

        self.roll_line.set_data(x[:len(roll_buf)], roll_buf)
        self.pitch_line.set_data(x[:len(pitch_buf)], pitch_buf)
        self.yaw_line.set_data(x[:len(yaw_buf)], yaw_buf)

        self.ax.set_ylim(-self.config.rpy_plot_y_limit_deg, self.config.rpy_plot_y_limit_deg)
        self.ax.set_xlim(0, max(1, self.config.plot_buffer_len))
        self.canvas.draw_idle()


# ============================================================
# Main UI
# ============================================================
class ImuDashboardUI:
    def __init__(self, root, state: ImuDashboardState):
        self.root = root
        self.state = state
        self.config = state.config
        self._last_plot_update = 0.0

        self.root.title(self.config.window_title)
        self.root.geometry("1080x610")
        self.root.minsize(720, 460)
        self.root.configure(bg="#0B1220")

        self.build_ui()
        self.update_ui()

    def build_ui(self):
        header = tk.Frame(self.root, bg="#0B1220")
        header.pack(fill="x", padx=18, pady=(12, 6))

        tk.Label(
            header,
            text=self.config.header_title,
            font=("Segoe UI", 22, "bold"),
            fg="#FFFFFF",
            bg="#0B1220",
            anchor="w",
        ).pack(side="left")

        self.header_info = tk.Label(
            header,
            text="ROS 2 Live Monitor",
            font=("Consolas", 10),
            fg="#8CA3B8",
            bg="#0B1220",
            anchor="e",
        )
        self.header_info.pack(side="right")

        mid = tk.Frame(self.root, bg="#0B1220")
        mid.pack(fill="both", expand=False, padx=18, pady=(0, 8))

        mid.grid_columnconfigure(0, weight=1)
        mid.grid_columnconfigure(1, weight=1)
        mid.grid_columnconfigure(2, weight=1)

        acc_sec = Section(mid, "3-Axis Acceleration")
        gyro_sec = Section(mid, "3-Axis Angular Velocity")
        mag_sec = Section(mid, "3-Axis Magnetic Field")

        acc_sec.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        gyro_sec.grid(row=0, column=1, sticky="nsew", padx=6)
        mag_sec.grid(row=0, column=2, sticky="nsew", padx=(6, 0))

        self.acc_x = ValueBar(acc_sec, "Acceleration X", "m/s²", -12, 12)
        self.acc_y = ValueBar(acc_sec, "Acceleration Y", "m/s²", -12, 12)
        self.acc_z = ValueBar(acc_sec, "Acceleration Z", "m/s²", -12, 12)
        self.acc_mag = MetricCard(acc_sec, "Magnitude", "-- m/s²", "sqrt(ax² + ay² + az²)")

        for widget in [self.acc_x, self.acc_y, self.acc_z]:
            widget.pack(fill="x", padx=12, pady=(8, 3))
        self.acc_mag.pack(fill="x", padx=12, pady=(10, 10))

        self.gyro_x = ValueBar(gyro_sec, "Angular Velocity X", "rad/s", -2, 2)
        self.gyro_y = ValueBar(gyro_sec, "Angular Velocity Y", "rad/s", -2, 2)
        self.gyro_z = ValueBar(gyro_sec, "Angular Velocity Z", "rad/s", -2, 2)
        self.gyro_mag = MetricCard(gyro_sec, "Magnitude", "-- rad/s", "sqrt(wx² + wy² + wz²)")

        for widget in [self.gyro_x, self.gyro_y, self.gyro_z]:
            widget.pack(fill="x", padx=12, pady=(8, 3))
        self.gyro_mag.pack(fill="x", padx=12, pady=(10, 10))

        self.mag_x = ValueBar(mag_sec, "Magnetic Field X", "T", -0.0001, 0.0001)
        self.mag_y = ValueBar(mag_sec, "Magnetic Field Y", "T", -0.0001, 0.0001)
        self.mag_z = ValueBar(mag_sec, "Magnetic Field Z", "T", -0.0001, 0.0001)
        self.mag_mag = MetricCard(mag_sec, "Magnitude", "-- T", "sqrt(mx² + my² + mz²)")

        for widget in [self.mag_x, self.mag_y, self.mag_z]:
            widget.pack(fill="x", padx=12, pady=(8, 3))
        self.mag_mag.pack(fill="x", padx=12, pady=(10, 10))

        plot_sec = Section(self.root, "Roll / Pitch / Yaw Live Plot")
        plot_sec.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        self.rpy_plot = RpyPlot(plot_sec, self.config)
        self.rpy_plot.pack(fill="both", expand=True, padx=6, pady=6)

    def update_ui(self):
        data = self.state.snapshot()
        now = time.time()

        ax = data["acc"]["x"]
        ay = data["acc"]["y"]
        az = data["acc"]["z"]

        wx = data["gyro"]["x"]
        wy = data["gyro"]["y"]
        wz = data["gyro"]["z"]

        mx = data["mag"]["x"]
        my = data["mag"]["y"]
        mz = data["mag"]["z"]

        acc_mag = vector_magnitude(ax, ay, az)
        gyro_mag = vector_magnitude(wx, wy, wz)
        mag_mag = vector_magnitude(mx, my, mz)

        self.acc_x.update_value(ax)
        self.acc_y.update_value(ay)
        self.acc_z.update_value(az)
        self.acc_mag.set_value(
            f"{acc_mag:.3f} m/s²",
            f"{self.config.imu_topic} | {data['imu_hz']:.1f} Hz",
        )

        self.gyro_x.update_value(wx)
        self.gyro_y.update_value(wy)
        self.gyro_z.update_value(wz)
        self.gyro_mag.set_value(
            f"{gyro_mag:.5f} rad/s",
            f"{self.config.imu_topic} | {data['imu_hz']:.1f} Hz",
        )

        self.mag_x.update_value(mx)
        self.mag_y.update_value(my)
        self.mag_z.update_value(mz)
        self.mag_mag.set_value(
            f"{mag_mag:.8f} T",
            f"{self.config.mag_topic} | {data['mag_hz']:.1f} Hz",
        )

        if (now - self._last_plot_update) * 1000.0 >= self.config.plot_update_ms:
            self.rpy_plot.update_plot(
                data["roll_buf"],
                data["pitch_buf"],
                data["yaw_buf"],
            )
            self._last_plot_update = now

        if data["last_any_msg_time"] > 0:
            age = now - data["last_any_msg_time"]
            self.header_info.config(
                text=(
                    f"IMU {data['imu_hz']:.1f} Hz | "
                    f"Mag {data['mag_hz']:.1f} Hz | "
                    f"Euler {data['euler_hz']:.1f} Hz | "
                    f"Last {age:.1f}s"
                )
            )
        else:
            self.header_info.config(text="Waiting for ROS 2 topics...")

        self.root.after(self.config.ui_update_ms, self.update_ui)


# ============================================================
# Main
# ============================================================
def main(args=None):
    rclpy.init(args=args)

    node = None
    spin_thread = None

    try:
        node = ImuDashboardNode()

        spin_thread = threading.Thread(
            target=rclpy.spin,
            args=(node,),
            daemon=True,
        )
        spin_thread.start()

        root = tk.Tk()
        ImuDashboardUI(root, node.state)

        def on_close():
            root.quit()

        root.protocol("WM_DELETE_WINDOW", on_close)
        root.mainloop()

    except KeyboardInterrupt:
        pass

    finally:
        if rclpy.ok():
            rclpy.shutdown()

        if spin_thread is not None:
            spin_thread.join(timeout=1.0)

        if node is not None:
            node.destroy_node()


if __name__ == "__main__":
    main()
