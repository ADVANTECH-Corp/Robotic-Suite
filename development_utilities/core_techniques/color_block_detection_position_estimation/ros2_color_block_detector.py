#!/usr/bin/env python3
"""Color block detection and position estimation (ROS 2).

This teaching sample detects colored blocks using HSV color profiles created by
the Color Profile Creation tool. It also estimates each detected block position
from aligned depth data and camera intrinsics.

Main pipeline:
    RGB image + aligned depth + CameraInfo
        -> BGR to HSV
        -> HSV mask from color_profiles.json
        -> contour detection
        -> center point estimation
        -> median depth lookup
        -> pixel + depth to 3D camera-frame position
        -> approximate yaw estimation
        -> publish debug image and detection result

The current output message type is AprilTagDetectionArray for compatibility
with existing downstream robot-arm workflows. The detected object is a color
block, not a real AprilTag.

Notes:
    - The depth image should be aligned to the RGB image.
    - The 3D position is estimated in the camera coordinate frame.
    - OpenCV HSV uses H in [0, 180], S/V in [0, 255].
"""

import json
import os
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

import rclpy
from rclpy.node import Node

from cv_bridge import CvBridge
from geometry_msgs.msg import Point
from sensor_msgs.msg import CameraInfo, Image

from isaac_ros_apriltag_interfaces.msg import (
    AprilTagDetection,
    AprilTagDetectionArray,
)


class ColorBlockDetector(Node):
    """Detect colored blocks and estimate their 3D position from RGB-D data."""

    def __init__(self):
        super().__init__("color_block_detector")

        self._declare_parameters()
        self._read_parameters()
        self._validate_parameters()

        # Runtime state
        self.bridge = CvBridge()
        self.last_rgb_msg: Optional[Image] = None
        self.last_depth_msg: Optional[Image] = None

        self.have_camera_info = False
        self.fx = self.fy = self.cx = self.cy = None

        self._profiles: Optional[Dict] = None
        self._profile_mtime: Optional[float] = None
        self._warned_depth_shape = False
        self._warned_missing_profile = False

        # ROS I/O
        self.create_subscription(Image, self.rgb_topic, self.cb_rgb, 10)
        self.create_subscription(Image, self.depth_topic, self.cb_depth, 10)
        self.create_subscription(CameraInfo, self.camera_info_topic, self.cb_camera_info, 10)

        self.pub_debug = self.create_publisher(Image, self.debug_image_topic, 10)
        self.pub_detection = self.create_publisher(AprilTagDetectionArray, self.detection_topic, 10)

        self.timer = self.create_timer(self.process_period_s, self.process)

        self.get_logger().info("--- ColorBlockDetector ---")
        self.get_logger().info(f"rgb_topic: {self.rgb_topic}")
        self.get_logger().info(f"depth_topic: {self.depth_topic}")
        self.get_logger().info(f"camera_info_topic: {self.camera_info_topic}")
        self.get_logger().info(f"profile_file: {self.profile_file}")
        self.get_logger().info(f"target_color: {self.target_color}")
        self.get_logger().info(f"debug_image_topic: {self.debug_image_topic}")
        self.get_logger().info(f"detection_topic: {self.detection_topic}")

    # ------------------------------------------------------------------
    # Parameters
    # ------------------------------------------------------------------

    def _declare_parameters(self) -> None:
        """Declare ROS 2 parameters used by this teaching sample."""

        # Input topics
        self.declare_parameter("rgb_topic", "/camera/color/image_raw")
        self.declare_parameter("depth_topic", "/camera/aligned_depth_to_color/image_raw")
        self.declare_parameter("camera_info_topic", "/camera/color/camera_info")

        # Output topics
        self.declare_parameter("debug_image_topic", "/color_block/debug_image")
        self.declare_parameter("detection_topic", "/tag_detections")

        # Color profile
        self.declare_parameter("target_color", "blue")
        self.declare_parameter("profile_file", "./color_profiles.json")

        # Depth handling
        self.declare_parameter("depth_unit", "mm")  # "mm" or "m"
        self.declare_parameter("depth_min_m", 0.30)
        self.declare_parameter("depth_max_m", 0.60)
        self.declare_parameter("depth_patch_radius", 2)  # 2 -> 5x5 patch

        # Detection filtering
        self.declare_parameter("min_contour_area", 1000.0)

        # Detection region of interest, normalized image coordinates.
        # Only pixels inside this region are used for detection.
        self.declare_parameter("roi_x_min", 0.20)
        self.declare_parameter("roi_x_max", 0.80)
        self.declare_parameter("roi_y_min", 0.48)
        self.declare_parameter("roi_y_max", 1.00)

        # Pose output
        self.declare_parameter("output_frame_id", "camera_link")
        self.declare_parameter("pose_z_offset_m", 0.03)

        # Optional preprocessing for difficult lighting.
        # Disabled by default to keep the teaching flow simple and predictable.
        self.declare_parameter("enable_preprocess", False)

        # Processing rate
        self.declare_parameter("process_period_s", 0.05)

    def _read_parameters(self) -> None:
        self.rgb_topic = str(self.get_parameter("rgb_topic").value)
        self.depth_topic = str(self.get_parameter("depth_topic").value)
        self.camera_info_topic = str(self.get_parameter("camera_info_topic").value)

        self.debug_image_topic = str(self.get_parameter("debug_image_topic").value)
        self.detection_topic = str(self.get_parameter("detection_topic").value)

        self.target_color = str(self.get_parameter("target_color").value).strip()
        self.profile_file = str(self.get_parameter("profile_file").value)

        self.depth_unit = str(self.get_parameter("depth_unit").value).strip().lower()
        self.depth_min_m = float(self.get_parameter("depth_min_m").value)
        self.depth_max_m = float(self.get_parameter("depth_max_m").value)
        self.depth_patch_radius = int(self.get_parameter("depth_patch_radius").value)

        self.min_contour_area = float(self.get_parameter("min_contour_area").value)

        self.roi_x_min = float(self.get_parameter("roi_x_min").value)
        self.roi_x_max = float(self.get_parameter("roi_x_max").value)
        self.roi_y_min = float(self.get_parameter("roi_y_min").value)
        self.roi_y_max = float(self.get_parameter("roi_y_max").value)

        self.output_frame_id = str(self.get_parameter("output_frame_id").value).strip()
        self.pose_z_offset_m = float(self.get_parameter("pose_z_offset_m").value)

        self.enable_preprocess = bool(self.get_parameter("enable_preprocess").value)
        self.process_period_s = float(self.get_parameter("process_period_s").value)

    def _validate_parameters(self) -> None:
        if self.depth_unit not in ("mm", "m", "meter", "meters"):
            raise ValueError('depth_unit must be "mm" or "m".')

        if self.depth_min_m < 0 or self.depth_max_m <= self.depth_min_m:
            raise ValueError("Invalid depth range. Require 0 <= depth_min_m < depth_max_m.")

        if self.depth_patch_radius < 0:
            raise ValueError("depth_patch_radius must be >= 0.")

        if self.min_contour_area < 0:
            raise ValueError("min_contour_area must be >= 0.")

        roi_values = [self.roi_x_min, self.roi_x_max, self.roi_y_min, self.roi_y_max]
        if any(v < 0.0 or v > 1.0 for v in roi_values):
            raise ValueError("ROI parameters must be normalized values in [0.0, 1.0].")

        if self.roi_x_min >= self.roi_x_max or self.roi_y_min >= self.roi_y_max:
            raise ValueError("Invalid ROI. Require roi_min < roi_max.")

        if self.process_period_s <= 0:
            raise ValueError("process_period_s must be > 0.")

    # ------------------------------------------------------------------
    # ROS callbacks
    # ------------------------------------------------------------------

    def cb_rgb(self, msg: Image) -> None:
        self.last_rgb_msg = msg

    def cb_depth(self, msg: Image) -> None:
        self.last_depth_msg = msg

    def cb_camera_info(self, msg: CameraInfo) -> None:
        """Read camera intrinsics from CameraInfo.K.

        CameraInfo.K:
            [fx, 0,  cx,
             0,  fy, cy,
             0,  0,  1]
        """

        self.fx = float(msg.k[0])
        self.fy = float(msg.k[4])
        self.cx = float(msg.k[2])
        self.cy = float(msg.k[5])
        self.have_camera_info = True

    # ------------------------------------------------------------------
    # Profile loading and mask creation
    # ------------------------------------------------------------------

    def _load_profiles(self) -> Optional[Dict]:
        """Load color profiles from JSON.

        The file is cached and automatically reloaded when its modification
        time changes. This allows users to update color_profiles.json without
        restarting the node.
        """

        if not os.path.exists(self.profile_file):
            self.get_logger().warn(f"Profile file not found: {self.profile_file}")
            return None

        try:
            mtime = os.path.getmtime(self.profile_file)
            if self._profiles is not None and self._profile_mtime == mtime:
                return self._profiles

            with open(self.profile_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            profiles = data.get("profiles")
            if not isinstance(profiles, dict):
                self.get_logger().error('Invalid profile file: missing "profiles" dictionary.')
                return None

            self._profiles = profiles
            self._profile_mtime = mtime
            self._warned_missing_profile = False
            self.get_logger().info(f"Loaded {len(profiles)} color profile(s) from {self.profile_file}")
            return self._profiles

        except Exception as e:
            self.get_logger().error(f"Failed to load profile file: {self.profile_file}. Error: {e}")
            return None

    def _resolve_target_profiles(self) -> Dict[str, Dict]:
        """Return the color profiles selected by target_color.

        target_color:
            - "all": use all profiles
            - otherwise: use one profile name
        """

        profiles = self._load_profiles()
        if not profiles:
            return {}

        if self.target_color.lower() == "all":
            return profiles

        if self.target_color in profiles:
            return {self.target_color: profiles[self.target_color]}

        # Friendly fallback for accidental capitalization differences.
        lower_map = {name.lower(): name for name in profiles.keys()}
        lookup = self.target_color.lower()
        if lookup in lower_map:
            real_name = lower_map[lookup]
            return {real_name: profiles[real_name]}

        if not self._warned_missing_profile:
            self.get_logger().warn(
                f'Target color "{self.target_color}" not found in {self.profile_file}. '
                f"Available profiles: {list(profiles.keys())}"
            )
            self._warned_missing_profile = True

        return {}

    def _mask_from_profile(self, hsv: np.ndarray, profile: Dict) -> Optional[np.ndarray]:
        """Create one binary mask from one HSV color profile."""

        ranges = profile.get("ranges", [])
        if not ranges:
            return None

        mask = None
        for i, hsv_range in enumerate(ranges):
            try:
                lower = np.array(hsv_range["lower"], dtype=np.uint8)
                upper = np.array(hsv_range["upper"], dtype=np.uint8)
            except Exception as e:
                self.get_logger().warn(f"Invalid HSV range at index {i}: {hsv_range}. Error: {e}")
                continue

            current = cv2.inRange(hsv, lower, upper)
            mask = current if mask is None else cv2.bitwise_or(mask, current)

        return mask

    # ------------------------------------------------------------------
    # Image utilities
    # ------------------------------------------------------------------

    def _preprocess_for_lighting(self, bgr: np.ndarray) -> np.ndarray:
        """Optional image preprocessing for difficult lighting.

        This step may help when highlights or shadows make color thresholding
        unstable. It is disabled by default because the basic HSV flow is easier
        to understand for teaching.
        """

        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        h, s, v = cv2.split(hsv)

        # Suppress strong highlights and enhance saturation.
        v = np.minimum(v, 240).astype(np.uint8)
        s = cv2.normalize(s, None, 40, 255, cv2.NORM_MINMAX)

        hsv = cv2.merge((h, s, v))
        bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

        # Normalize brightness with CLAHE in LAB color space.
        lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)

        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        l = clahe.apply(l)

        lab = cv2.merge((l, a, b))
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    def _normalized_roi_to_pixels(
        self,
        width: int,
        height: int,
        x_min: float,
        x_max: float,
        y_min: float,
        y_max: float,
    ) -> Tuple[int, int, int, int]:
        """Convert normalized ROI values into pixel coordinates."""

        x1 = int(x_min * width)
        x2 = int(x_max * width)
        y1 = int(y_min * height)
        y2 = int(y_max * height)
        return x1, y1, x2, y2

    def _apply_roi(self, mask: np.ndarray) -> Tuple[np.ndarray, Tuple[int, int, int, int]]:
        """Apply the detection ROI to a binary mask."""

        h, w = mask.shape[:2]
        x1, y1, x2, y2 = self._normalized_roi_to_pixels(
            w, h, self.roi_x_min, self.roi_x_max, self.roi_y_min, self.roi_y_max
        )

        roi_mask = np.zeros_like(mask)
        roi_mask[y1:y2, x1:x2] = 255

        return cv2.bitwise_and(mask, roi_mask), (x1, y1, x2, y2)

    def _draw_roi(self, image: np.ndarray, roi: Tuple[int, int, int, int]) -> None:
        x1, y1, x2, y2 = roi
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(
            image,
            "ROI",
            (x1 + 5, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
        )

    def _draw_status(self, image: np.ndarray, text: str, color: Tuple[int, int, int] = (0, 0, 255)) -> None:
        cv2.putText(image, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    def _publish_debug(self, image: np.ndarray) -> None:
        self.pub_debug.publish(self.bridge.cv2_to_imgmsg(image, encoding="bgr8"))

    # ------------------------------------------------------------------
    # Geometry and depth utilities
    # ------------------------------------------------------------------

    def _depth_to_meters(self, depth_value: float) -> Optional[float]:
        if depth_value is None or np.isnan(depth_value) or depth_value <= 0:
            return None

        if self.depth_unit == "mm":
            return float(depth_value) / 1000.0

        return float(depth_value)

    def _median_depth_at(self, depth: np.ndarray, u: int, v: int) -> Optional[float]:
        """Return median valid depth around a pixel.

        A small patch is more stable than a single depth pixel because depth
        images may contain noise or missing values.
        """

        h, w = depth.shape[:2]
        r = self.depth_patch_radius

        x1 = max(0, u - r)
        x2 = min(w, u + r + 1)
        y1 = max(0, v - r)
        y2 = min(h, v + r + 1)

        patch = depth[y1:y2, x1:x2]
        valid = patch[patch > 0]

        if valid.size == 0:
            return None

        return float(np.median(valid))

    def _deproject_pixel_to_xyz(self, u: int, v: int, z_m: float) -> Tuple[float, float, float]:
        """Convert pixel coordinate + depth into 3D camera-frame coordinate."""

        x = (u - self.cx) * z_m / self.fx
        y = (v - self.cy) * z_m / self.fy
        return float(x), float(y), float(z_m)

    def _estimate_center_from_contour(self, contour: np.ndarray) -> Optional[Tuple[int, int]]:
        moments = cv2.moments(contour)
        if moments["m00"] == 0:
            return None

        u = int(moments["m10"] / moments["m00"])
        v = int(moments["m01"] / moments["m00"])
        return u, v

    def _estimate_yaw_from_contour(self, contour: np.ndarray) -> Tuple[float, np.ndarray]:
        """Estimate approximate 2D yaw angle from the contour.

        The angle is based on the long side of the rotated rectangle returned
        by OpenCV minAreaRect(). This is simple and useful for teaching, but it
        is not a replacement for a full 6D object pose estimator.
        """

        rect = cv2.minAreaRect(contour)
        (_, _), (w_rect, h_rect), angle = rect

        # Normalize so that yaw follows the longer side of the block.
        if w_rect < h_rect:
            angle += 90.0

        yaw_deg = angle % 360.0
        yaw_rad = np.deg2rad(yaw_deg)

        box = cv2.boxPoints(rect)
        box = np.int32(box)

        return float(yaw_rad), box

    # ------------------------------------------------------------------
    # Publishing helpers
    # ------------------------------------------------------------------

    def _draw_color_for_name(self, name: str) -> Tuple[int, int, int]:
        lower = name.lower()
        if "red" in lower:
            return (0, 0, 255)
        if "green" in lower:
            return (0, 255, 0)
        if "blue" in lower:
            return (255, 0, 0)
        if "yellow" in lower:
            return (0, 255, 255)
        return (255, 255, 255)

    def _make_corner_point(self, det: AprilTagDetection, x: float, y: float) -> Point:
        """Create a corner point compatible with the message definition."""

        try:
            point = type(det.corners[0])()
        except Exception:
            point = Point()

        point.x = float(x)
        point.y = float(y)
        point.z = 0.0
        return point

    def _set_detection_corners(self, det: AprilTagDetection, box: np.ndarray) -> None:
        """Set detection corners from the rotated rectangle box."""

        points = [self._make_corner_point(det, float(x), float(y)) for x, y in box]

        try:
            det.corners = points
            return
        except Exception:
            pass

        try:
            while len(det.corners) > 0:
                det.corners.pop()
        except Exception:
            pass

        try:
            for p in points:
                det.corners.append(p)
            return
        except Exception:
            pass

        try:
            for i, p in enumerate(points):
                if i < len(det.corners):
                    det.corners[i] = p
        except Exception:
            pass

    def _create_detection(
        self,
        color_name: str,
        center_u: int,
        center_v: int,
        box: np.ndarray,
        xyz: Tuple[float, float, float],
        yaw_rad: float,
        header,
    ) -> AprilTagDetection:
        """Create one detection message.

        The output message type is AprilTagDetection for compatibility, but the
        detected object is a color block.
        """

        x, y, z = xyz

        det = AprilTagDetection()
        det.family = str(color_name)
        det.id = 0

        det.center.x = float(center_u)
        det.center.y = float(center_v)
        det.center.z = 0.0

        self._set_detection_corners(det, box)

        try:
            det.pose.header = header
        except Exception:
            pass

        det.pose.pose.pose.position.x = float(x)
        det.pose.pose.pose.position.y = float(y)
        det.pose.pose.pose.position.z = float(z + self.pose_z_offset_m)

        # Yaw-only orientation around Z axis.
        qw = np.cos(yaw_rad / 2.0)
        qz = np.sin(yaw_rad / 2.0)

        det.pose.pose.pose.orientation.x = 0.0
        det.pose.pose.pose.orientation.y = 0.0
        det.pose.pose.pose.orientation.z = float(qz)
        det.pose.pose.pose.orientation.w = float(qw)

        return det

    def _draw_detection(
        self,
        debug: np.ndarray,
        color_name: str,
        contour: np.ndarray,
        center: Tuple[int, int],
        box: np.ndarray,
        xyz: Tuple[float, float, float],
        yaw_rad: float,
        text_y: int,
    ) -> int:
        """Draw one detected object on the debug image."""

        u, v = center
        x, y, z = xyz
        draw_color = self._draw_color_for_name(color_name)

        cv2.drawContours(debug, [contour], -1, draw_color, 2)
        cv2.drawContours(debug, [box], 0, (255, 255, 0), 2)
        cv2.circle(debug, (u, v), 6, (0, 0, 255), -1)

        cv2.putText(debug, color_name, (u + 8, v - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, draw_color, 2)

        arrow_len = 50
        x2 = int(u + arrow_len * np.cos(yaw_rad))
        y2 = int(v + arrow_len * np.sin(yaw_rad))
        cv2.arrowedLine(debug, (u, v), (x2, y2), (0, 255, 255), 2)

        qz = np.sin(yaw_rad / 2.0)
        qw = np.cos(yaw_rad / 2.0)

        cv2.putText(
            debug,
            f"{color_name}: xyz=({x:.2f}, {y:.2f}, {z:.2f}) yaw_qzqw=({qz:.2f}, {qw:.2f})",
            (10, text_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            draw_color,
            2,
        )

        return text_y + 24

    # ------------------------------------------------------------------
    # Main processing loop
    # ------------------------------------------------------------------

    def process(self) -> None:
        if self.last_rgb_msg is None:
            return

        try:
            bgr = self.bridge.imgmsg_to_cv2(self.last_rgb_msg, desired_encoding="bgr8")
        except Exception as e:
            self.get_logger().warn(f"RGB image conversion failed: {e}")
            return

        if self.enable_preprocess:
            bgr_for_detection = self._preprocess_for_lighting(bgr)
        else:
            bgr_for_detection = bgr

        debug = bgr.copy()

        if self.last_depth_msg is None:
            self._draw_status(debug, "WAITING FOR DEPTH")
            self._publish_debug(debug)
            return

        if not self.have_camera_info:
            self._draw_status(debug, "WAITING FOR CAMERA INFO")
            self._publish_debug(debug)
            return

        try:
            depth = self.bridge.imgmsg_to_cv2(self.last_depth_msg, desired_encoding="passthrough")
        except Exception as e:
            self.get_logger().warn(f"Depth image conversion failed: {e}")
            return

        if depth.shape[:2] != bgr.shape[:2] and not self._warned_depth_shape:
            self.get_logger().warn(
                "Depth image size does not match RGB image size. "
                "Make sure the depth image is aligned to the color image."
            )
            self._warned_depth_shape = True

        profiles = self._resolve_target_profiles()
        if not profiles:
            self._draw_status(debug, "NO VALID COLOR PROFILE")
            self._publish_debug(debug)
            return

        hsv = cv2.cvtColor(bgr_for_detection, cv2.COLOR_BGR2HSV)

        detection_msg = AprilTagDetectionArray()
        detection_msg.header = self.last_rgb_msg.header
        if self.output_frame_id:
            detection_msg.header.frame_id = self.output_frame_id

        used_mask = np.zeros((bgr.shape[0], bgr.shape[1]), dtype=np.uint8)
        text_y = 24

        # Draw the actual detection ROI. This makes the debug image match the
        # region used by the algorithm.
        dummy_mask = np.zeros((bgr.shape[0], bgr.shape[1]), dtype=np.uint8)
        _, roi_box = self._apply_roi(dummy_mask)
        self._draw_roi(debug, roi_box)

        for color_name, profile in profiles.items():
            mask = self._mask_from_profile(hsv, profile)
            if mask is None:
                continue

            mask, _ = self._apply_roi(mask)

            # Avoid publishing the same pixels as multiple colors in all-color mode.
            mask = cv2.bitwise_and(mask, cv2.bitwise_not(used_mask))

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for contour in contours:
                area = cv2.contourArea(contour)
                if area < self.min_contour_area:
                    continue

                center = self._estimate_center_from_contour(contour)
                if center is None:
                    continue

                u, v = center
                depth_value = self._median_depth_at(depth, u, v)
                z_m = self._depth_to_meters(depth_value)

                if z_m is None:
                    continue

                if z_m < self.depth_min_m or z_m > self.depth_max_m:
                    continue

                xyz = self._deproject_pixel_to_xyz(u, v, z_m)
                yaw_rad, box = self._estimate_yaw_from_contour(contour)

                detection = self._create_detection(
                    color_name=color_name,
                    center_u=u,
                    center_v=v,
                    box=box,
                    xyz=xyz,
                    yaw_rad=yaw_rad,
                    header=detection_msg.header,
                )
                detection_msg.detections.append(detection)

                text_y = self._draw_detection(
                    debug=debug,
                    color_name=color_name,
                    contour=contour,
                    center=center,
                    box=box,
                    xyz=xyz,
                    yaw_rad=yaw_rad,
                    text_y=text_y,
                )

                cv2.drawContours(used_mask, [contour], -1, 255, -1)

        self.pub_detection.publish(detection_msg)
        self._publish_debug(debug)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ColorBlockDetector()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
