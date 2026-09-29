#!/usr/bin/env python3
"""Interactive HSV color profile picker for ROS 2.

This tool helps users create HSV color profiles from a live RGB camera stream.
It is intended to be used before color-based object detection.

Workflow:
  1. Start a camera node that publishes a color image topic.
  2. Run this node and click several points on the target color block.
  3. Press 's' to save the computed HSV range to a JSON file.
  4. Use the generated JSON file in the color block detection node.

Controls:
  - Left mouse click: collect one HSV sample from the clicked patch
  - s: save the current profile
  - c: clear collected samples
  - q: quit

Output JSON format:
{
  "profiles": {
    "blue": {
      "ranges": [
        {"lower": [H, S, V], "upper": [H, S, V]}
      ],
      "created_from": {
        "rgb_topic": "/camera/color/image_raw",
        "note": "sample note",
        "samples": 8
      }
    }
  }
}

Notes:
  - OpenCV uses Hue in the range [0, 180], not [0, 360].
  - Saturation and Value are in the range [0, 255].
  - Click multiple bright/dark regions and different viewing angles to make the
    profile more robust to lighting changes.
"""

import json
import os
from dataclasses import dataclass
from typing import List, Tuple

import cv2
import numpy as np

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge


# OpenCV HSV value limits.
# Hue is stored as [0, 180] in OpenCV, while S and V are stored as [0, 255].
H_MIN = 0
H_MAX = 180
SV_MIN = 0
SV_MAX = 255

# A small number of samples can still be saved, but the result may be unstable.
RECOMMENDED_MIN_SAMPLES = 3


@dataclass
class HSVSample:
    """One representative HSV sample collected from a clicked image patch."""

    h: int
    s: int
    v: int


def clamp_int(value, lower_bound, upper_bound):
    """Clamp a numeric value to an integer range."""

    return int(max(lower_bound, min(upper_bound, int(value))))


class ColorProfilePicker(Node):
    """ROS 2 node for interactively creating HSV color profiles."""

    def __init__(self):
        super().__init__('color_profile_picker')

        # Camera input and output profile settings.
        self.declare_parameter('rgb_topic', '/camera/color/image_raw')
        self.declare_parameter('profile_file', './color_profiles.json')
        self.declare_parameter('profile_name', 'blue')
        self.declare_parameter('note', '')

        # Sampling settings.
        # patch_radius means the half-size of the clicked patch in pixels.
        # Example: radius=4 creates a 9x9 patch around the clicked point.
        self.declare_parameter('patch_radius', 4)
        self.declare_parameter('h_margin', 10)
        self.declare_parameter('s_margin', 40)
        self.declare_parameter('v_margin', 40)

        # Robust range estimation settings.
        # Percentiles help reduce the effect of outlier samples.
        self.declare_parameter('use_percentiles', True)
        self.declare_parameter('low_percentile', 10.0)
        self.declare_parameter('high_percentile', 90.0)

        self.rgb_topic = self.get_parameter('rgb_topic').value
        self.profile_file = self.get_parameter('profile_file').value
        self.profile_name = self.get_parameter('profile_name').value
        self.note = self.get_parameter('note').value

        self.patch_radius = int(self.get_parameter('patch_radius').value)
        self.h_margin = int(self.get_parameter('h_margin').value)
        self.s_margin = int(self.get_parameter('s_margin').value)
        self.v_margin = int(self.get_parameter('v_margin').value)

        self.use_percentiles = bool(self.get_parameter('use_percentiles').value)
        self.low_p = float(self.get_parameter('low_percentile').value)
        self.high_p = float(self.get_parameter('high_percentile').value)

        self._validate_parameters()

        self.bridge = CvBridge()
        self.last_bgr = None
        self.samples: List[HSVSample] = []
        self.sample_points: List[Tuple[int, int]] = []

        self.sub = self.create_subscription(Image, self.rgb_topic, self.cb_rgb, 10)
        self.timer = self.create_timer(0.03, self.loop)  # About 30 Hz UI refresh.

        self.window = 'ColorProfilePicker'
        cv2.namedWindow(self.window, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(self.window, self.on_mouse)

        self.get_logger().info('--- ColorProfilePicker ---')
        self.get_logger().info(f'rgb_topic: {self.rgb_topic}')
        self.get_logger().info(f'profile_file: {self.profile_file}')
        self.get_logger().info(f'profile_name: {self.profile_name}')
        self.get_logger().info(
            'Click multiple regions of the target color, including bright/dark '
            'areas and different angles. Then press s to save.'
        )

    def _validate_parameters(self):
        """Normalize parameters and warn about values that may confuse users."""

        if self.patch_radius < 0:
            self.get_logger().warn('patch_radius cannot be negative. Set to 0.')
            self.patch_radius = 0

        if self.low_p < 0.0 or self.high_p > 100.0 or self.low_p >= self.high_p:
            self.get_logger().warn(
                'Invalid percentile settings. Use low_percentile=10.0 and '
                'high_percentile=90.0 instead.'
            )
            self.low_p = 10.0
            self.high_p = 90.0

    def cb_rgb(self, msg: Image):
        """Convert the latest ROS image message to an OpenCV BGR image."""

        try:
            # OpenCV display and cvtColor commonly use BGR format.
            self.last_bgr = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as exc:
            self.get_logger().warn(f'RGB image conversion failed: {exc}')

    def on_mouse(self, event, x, y, flags, param):
        """Collect one HSV sample when the user clicks on the image."""

        if event != cv2.EVENT_LBUTTONDOWN:
            return
        if self.last_bgr is None:
            self.get_logger().warn('No RGB image received yet. Cannot sample color.')
            return

        bgr = self.last_bgr
        height, width = bgr.shape[:2]
        radius = self.patch_radius

        x0 = max(0, x - radius)
        x1 = min(width, x + radius + 1)
        y0 = max(0, y - radius)
        y1 = min(height, y + radius + 1)

        patch = bgr[y0:y1, x0:x1]
        hsv_patch = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)

        # Use the median HSV value of a small patch instead of a single pixel.
        # This makes the sample more stable against image noise and highlights.
        median_h = int(np.median(hsv_patch[:, :, 0]))
        median_s = int(np.median(hsv_patch[:, :, 1]))
        median_v = int(np.median(hsv_patch[:, :, 2]))

        self.samples.append(HSVSample(median_h, median_s, median_v))
        self.sample_points.append((x, y))

        self.get_logger().info(
            f'Sample #{len(self.samples)} at ({x}, {y}) '
            f'HSV=({median_h}, {median_s}, {median_v})'
        )

    def compute_ranges(self) -> List[Tuple[List[int], List[int]]]:
        """Convert collected HSV samples into one or more HSV ranges.

        The range is estimated from all clicked samples. If percentile mode is
        enabled and enough samples are available, low/high percentiles are used
        instead of min/max to reduce the effect of outlier samples.

        Margins are then added to make the profile more tolerant to lighting
        changes. If the Hue range crosses the OpenCV 0/180 boundary, the range
        is split into two ranges. This is useful for colors such as red.

        Returns:
            A list of (lower, upper) HSV ranges. Each lower/upper value is a
            list in the format [H, S, V].
        """

        if not self.samples:
            return []

        hue_values = np.array([sample.h for sample in self.samples], dtype=np.float32)
        saturation_values = np.array([sample.s for sample in self.samples], dtype=np.float32)
        value_values = np.array([sample.v for sample in self.samples], dtype=np.float32)

        if self.use_percentiles and len(self.samples) >= RECOMMENDED_MIN_SAMPLES:
            h_lo = float(np.percentile(hue_values, self.low_p))
            h_hi = float(np.percentile(hue_values, self.high_p))
            s_lo = float(np.percentile(saturation_values, self.low_p))
            s_hi = float(np.percentile(saturation_values, self.high_p))
            v_lo = float(np.percentile(value_values, self.low_p))
            v_hi = float(np.percentile(value_values, self.high_p))
        else:
            h_lo = float(np.min(hue_values))
            h_hi = float(np.max(hue_values))
            s_lo = float(np.min(saturation_values))
            s_hi = float(np.max(saturation_values))
            v_lo = float(np.min(value_values))
            v_hi = float(np.max(value_values))

        # Add tolerance around the sampled color range.
        h_lo -= self.h_margin
        h_hi += self.h_margin
        s_lo -= self.s_margin
        s_hi += self.s_margin
        v_lo -= self.v_margin
        v_hi += self.v_margin

        # Clamp S and V first. Hue is handled below because it may wrap around.
        s_lo = clamp_int(s_lo, SV_MIN, SV_MAX)
        s_hi = clamp_int(s_hi, SV_MIN, SV_MAX)
        v_lo = clamp_int(v_lo, SV_MIN, SV_MAX)
        v_hi = clamp_int(v_hi, SV_MIN, SV_MAX)

        ranges = []

        # Handle Hue wrap-around.
        # Example: if the computed Hue range is [-5, 12], it should become
        # [0, 12] and [175, 180] in OpenCV Hue space.
        if h_lo < H_MIN:
            ranges.append((
                [H_MIN, s_lo, v_lo],
                [clamp_int(h_hi, H_MIN, H_MAX), s_hi, v_hi]
            ))
            ranges.append((
                [clamp_int(H_MAX + h_lo, H_MIN, H_MAX), s_lo, v_lo],
                [H_MAX, s_hi, v_hi]
            ))
        elif h_hi > H_MAX:
            ranges.append((
                [clamp_int(h_lo, H_MIN, H_MAX), s_lo, v_lo],
                [H_MAX, s_hi, v_hi]
            ))
            ranges.append((
                [H_MIN, s_lo, v_lo],
                [clamp_int(h_hi - H_MAX, H_MIN, H_MAX), s_hi, v_hi]
            ))
        else:
            ranges.append((
                [clamp_int(h_lo, H_MIN, H_MAX), s_lo, v_lo],
                [clamp_int(h_hi, H_MIN, H_MAX), s_hi, v_hi]
            ))

        return ranges

    def _load_profile_data(self):
        """Load an existing profile JSON file, or create an empty structure."""

        data = {'profiles': {}}

        if not os.path.exists(self.profile_file):
            return data

        try:
            with open(self.profile_file, 'r', encoding='utf-8') as json_file:
                data = json.load(json_file)
        except Exception as exc:
            self.get_logger().warn(
                f'Failed to read existing profile file: {self.profile_file}. '
                f'A new profile file will be created. Error: {exc}'
            )
            return {'profiles': {}}

        if 'profiles' not in data or not isinstance(data['profiles'], dict):
            self.get_logger().warn(
                'Existing profile file does not contain a valid "profiles" object. '
                'A new "profiles" object will be created.'
            )
            data['profiles'] = {}

        return data

    def save_profile(self):
        """Save the current HSV range to the configured JSON profile file."""

        ranges = self.compute_ranges()
        if not ranges:
            self.get_logger().warn('No samples to save. Click the target color first.')
            return

        if len(self.samples) < RECOMMENDED_MIN_SAMPLES:
            self.get_logger().warn(
                f'Only {len(self.samples)} sample(s) collected. For a more robust '
                'profile, collect at least 3 samples from bright and dark regions.'
            )

        data = self._load_profile_data()

        if self.profile_name in data['profiles']:
            self.get_logger().warn(
                f'Profile "{self.profile_name}" already exists and will be overwritten.'
            )

        data['profiles'][self.profile_name] = {
            'ranges': [{'lower': lower, 'upper': upper} for (lower, upper) in ranges],
            'created_from': {
                'rgb_topic': self.rgb_topic,
                'note': self.note,
                'samples': len(self.samples),
                'patch_radius': self.patch_radius,
                'h_margin': self.h_margin,
                's_margin': self.s_margin,
                'v_margin': self.v_margin,
                'use_percentiles': self.use_percentiles,
                'low_percentile': self.low_p,
                'high_percentile': self.high_p,
            }
        }

        output_dir = os.path.dirname(self.profile_file) or '.'
        os.makedirs(output_dir, exist_ok=True)

        with open(self.profile_file, 'w', encoding='utf-8') as json_file:
            json.dump(data, json_file, indent=2, ensure_ascii=False)

        self.get_logger().info(
            f'Saved profile "{self.profile_name}" with {len(ranges)} HSV range(s) '
            f'to: {self.profile_file}'
        )
        for index, (lower, upper) in enumerate(ranges):
            self.get_logger().info(f'  range[{index}]: lower={lower} upper={upper}')

    def clear_samples(self):
        """Clear all collected samples and clicked point markers."""

        self.samples.clear()
        self.sample_points.clear()
        self.get_logger().info('Samples cleared.')

    def draw_overlay(self, image):
        """Draw UI text, computed ranges, and clicked sample markers."""

        cv2.putText(
            image,
            f'profile: {self.profile_name}  samples: {len(self.samples)}',
            (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 255),
            2,
        )
        cv2.putText(
            image,
            'click=sample  s=save  c=clear  q=quit',
            (10, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 255),
            2,
        )

        # Draw markers where the user clicked. This helps users confirm which
        # regions were used to build the current color profile.
        for point_index, (point_x, point_y) in enumerate(self.sample_points, start=1):
            cv2.circle(image, (point_x, point_y), 5, (0, 255, 255), 2)
            cv2.putText(
                image,
                str(point_index),
                (point_x + 6, point_y - 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 255),
                1,
            )

        ranges = self.compute_ranges()
        y_position = 90
        for range_index, (lower, upper) in enumerate(ranges):
            cv2.putText(
                image,
                f'range[{range_index}] lower={lower} upper={upper}',
                (10, y_position),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 0),
                2,
            )
            y_position += 25

    def loop(self):
        """Refresh the OpenCV UI and handle keyboard commands."""

        if self.last_bgr is None:
            return

        vis = self.last_bgr.copy()
        self.draw_overlay(vis)

        cv2.imshow(self.window, vis)
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            raise KeyboardInterrupt
        if key == ord('c'):
            self.clear_samples()
        elif key == ord('s'):
            self.save_profile()


def main():
    rclpy.init()
    node = ColorProfilePicker()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
