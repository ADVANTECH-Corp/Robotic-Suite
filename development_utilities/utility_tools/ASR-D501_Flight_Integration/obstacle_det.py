#!/usr/bin/env python3
"""
Orbbec ROS Topic + QCS6490 NPU YOLO + Nearest Obstacle (Bird) + Person Marker

Input:
  /camera/color/image_raw
  /camera/depth/image_raw

NPU path:
  ROS color image
  -> appsrc
  -> qtimlvconverter engine=fcv image-disposition=stretch
  -> qtimltflite QNN HTP/NPU
  -> tensor appsink
  -> Python YOLO parser

Logic:
  - Filter detections to person (class 0) and bird/obstacle (class 14)
  - Estimate depth for detected obstacles using depth ROI
  - Select and highlight the nearest obstacle
  - Draw crosshair marker for detected persons
  - Display real-time bounding boxes, distance, and FPS
  - Press 'q' or ESC to quit
"""

import os
import time
import signal
import threading

import cv2
import numpy as np

import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from cv_bridge import CvBridge

# ─────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────

COLOR_TOPIC = "/camera/color/image_raw"
DEPTH_TOPIC = "/camera/depth/image_raw"

FRAME_W = 640
FRAME_H = 480
FPS = 30

MODEL_FILE = "yolov8_det.tflite"
MODEL_INPUT_SIZE = 640

# Target filter IDs (COCO: 0 = person, 14 = bird)
TARGET_CLASS_PERSON = 0
TARGET_CLASS_BIRD = 14

CONF_THRESHOLD = 0.55
NMS_THRESHOLD = 0.45
DEPTH_UNIT_SCALE = 1000.0

ROI_INNER_MIN = 0.3
ROI_INNER_MAX = 0.7

DEADZONE_L_FRAC = 0.38
DEADZONE_R_FRAC = 0.62

WINDOW_NAME = "Obstacle Detected"
MIRROR_IMAGE = True


# ─────────────────────────────────────────────────────────
# GSTREAMER HELPERS
# ─────────────────────────────────────────────────────────

def pull_sample(sink, timeout_ns):
    try:
        return sink.emit("try-pull-sample", timeout_ns)
    except Exception:
        return None

def sample_to_bytes(sample):
    buf = sample.get_buffer()
    ok, mapinfo = buf.map(Gst.MapFlags.READ)
    if not ok:
        return None
    try:
        return bytes(mapinfo.data)
    finally:
        buf.unmap(mapinfo)

# ─────────────────────────────────────────────────────────
# YOLO PARSER
# ─────────────────────────────────────────────────────────

def parse_yolov8_tensors(raw_bytes):
    floats = np.frombuffer(raw_bytes, dtype=np.float32)
    if len(floats) != 50400:
        return []

    boxes = floats[:8400 * 4].reshape(8400, 4)
    scores = floats[8400 * 4: 8400 * 4 + 8400]
    classes = floats[8400 * 4 + 8400:]

    indices = np.where(scores >= CONF_THRESHOLD)[0]
    detections = []

    for idx in indices:
        b0, b1, b2, b3 = boxes[idx]
        cls = int(round(classes[idx]))
        conf = float(scores[idx])

        # Filter only target classes (person and bird)
        if cls in (TARGET_CLASS_PERSON, TARGET_CLASS_BIRD):
            detections.append({
                "class_id": cls,
                "conf": conf,
                "b0": float(b0),
                "b1": float(b1),
                "b2": float(b2),
                "b3": float(b3),
            })

    return detections

def is_normalized_box(det):
    b0, b1, b2, b3 = det["b0"], det["b1"], det["b2"], det["b3"]
    return (0.0 <= b0 <= 1.5 and 0.0 <= b1 <= 1.5 and 0.0 <= b2 <= 1.5 and 0.0 <= b3 <= 1.5)

def clamp_box(x1, y1, x2, y2):
    x1 = int(max(0, min(FRAME_W - 1, x1)))
    y1 = int(max(0, min(FRAME_H - 1, y1)))
    x2 = int(max(0, min(FRAME_W - 1, x2)))
    y2 = int(max(0, min(FRAME_H - 1, y2)))
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return x1, y1, x2, y2

def det_to_frame_box_xyxy(det):
    x1, y1, x2, y2 = det["b0"], det["b1"], det["b2"], det["b3"]
    if is_normalized_box(det):
        x1 *= FRAME_W
        x2 *= FRAME_W
        y1 *= FRAME_H
        y2 *= FRAME_H
    else:
        sx = FRAME_W / MODEL_INPUT_SIZE
        sy = FRAME_H / MODEL_INPUT_SIZE
        x1 *= sx
        x2 *= sx
        y1 *= sy
        y2 *= sy
    return clamp_box(x1, y1, x2, y2)

def box_iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    return inter / (area_a + area_b - inter + 1e-6)

def nms_detections(dets):
    if not dets:
        return []
    dets = sorted(dets, key=lambda d: d["conf"], reverse=True)
    kept = []
    for det in dets:
        box = det_to_frame_box_xyxy(det)
        keep = True
        for kept_det in kept:
            kept_box = det_to_frame_box_xyxy(kept_det)
            if box_iou(box, kept_box) > NMS_THRESHOLD:
                keep = False
                break
        if keep:
            kept.append(det)
    return kept

# ─────────────────────────────────────────────────────────
# ROS NODE
# ─────────────────────────────────────────────────────────

class OrbbecTopicNPUPersonBirdVision(Node):
    def __init__(self):
        super().__init__("orbbec_topic_npu_person_bird_vision")

        os.environ.setdefault("XDG_RUNTIME_DIR", "/run/user/1000")
        os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")

        Gst.init(None)
        self.bridge = CvBridge()

        self.lock = threading.Lock()
        self.latest_frame = None
        self.latest_depth = None

        self.pipeline = None
        self.appsrc = None
        self.tensor_sink = None

        self.frame_index = 0
        self.frame_duration = Gst.SECOND // FPS

        self.fps_display = 0.0
        self.fps_counter = 0
        self.last_fps_time = time.time()

        self.left_boundary = int(FRAME_W * DEADZONE_L_FRAC)
        self.right_boundary = int(FRAME_W * DEADZONE_R_FRAC)

        self.setup_gstreamer()

        self.create_subscription(Image, COLOR_TOPIC, self.color_callback, 10)
        self.create_subscription(Image, DEPTH_TOPIC, self.depth_callback, 10)

        self.timer = self.create_timer(1.0 / 30.0, self.process_once)

        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL | cv2.WINDOW_GUI_NORMAL)
        cv2.resizeWindow(WINDOW_NAME, FRAME_W, FRAME_H)

        self.get_logger().info("Vision node started (Target: Person & Bird)")

    def setup_gstreamer(self):
        pipeline_str = f"""
        appsrc name=src
            is-live=true
            block=false
            format=time
            do-timestamp=true
            caps=video/x-raw,format=RGB,width={FRAME_W},height={FRAME_H},framerate={FPS}/1
        ! queue max-size-buffers=2 leaky=downstream
        ! qtimlvconverter engine=fcv image-disposition=stretch
        ! qtimltflite delegate=external
            external-delegate-path=libQnnTFLiteDelegate.so
            external-delegate-options="QNNExternalDelegate,backend_type=htp;"
            model={MODEL_FILE}
        ! appsink name=tensor_sink
            sync=false
            max-buffers=2
            drop=true
            emit-signals=false
        """
        self.pipeline = Gst.parse_launch(pipeline_str)
        self.appsrc = self.pipeline.get_by_name("src")
        self.tensor_sink = self.pipeline.get_by_name("tensor_sink")

        if self.appsrc is None or self.tensor_sink is None:
            raise RuntimeError("Could not find appsrc or tensor_sink")

        ret = self.pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            self.pipeline.set_state(Gst.State.NULL)
            raise RuntimeError("Failed to set NPU pipeline to PLAYING")

    def color_callback(self, msg):
        try:
            bgr = self.bridge.imgmsg_to_cv2(msg, "bgr8")
        except Exception as e:
            self.get_logger().warn(f"Color conversion failed: {e}")
            return

        if bgr.shape[1] != FRAME_W or bgr.shape[0] != FRAME_H:
            bgr = cv2.resize(bgr, (FRAME_W, FRAME_H), interpolation=cv2.INTER_LINEAR)

        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        with self.lock:
            self.latest_frame = bgr.copy()

        self.push_rgb_to_npu(rgb)

    def depth_callback(self, msg):
        try:
            depth = self.bridge.imgmsg_to_cv2(msg, "passthrough")
        except Exception as e:
            self.get_logger().warn(f"Depth conversion failed: {e}")
            return

        with self.lock:
            self.latest_depth = depth.copy()

    def push_rgb_to_npu(self, rgb):
        if self.appsrc is None:
            return

        if not rgb.flags["C_CONTIGUOUS"]:
            rgb = np.ascontiguousarray(rgb)

        data = rgb.tobytes()
        buf = Gst.Buffer.new_allocate(None, len(data), None)
        buf.fill(0, data)
        buf.pts = self.frame_index * self.frame_duration
        buf.dts = buf.pts
        buf.duration = self.frame_duration
        self.frame_index += 1

        self.appsrc.emit("push-buffer", buf)

    def get_distance_from_depth(self, depth, box):
        if depth is None:
            return None

        x1, y1, x2, y2 = box
        dh, dw = depth.shape[:2]
        sx = dw / FRAME_W
        sy = dh / FRAME_H

        dx1 = int(max(0, min(dw - 1, x1 * sx)))
        dx2 = int(max(0, min(dw - 1, x2 * sx)))
        dy1 = int(max(0, min(dh - 1, y1 * sy)))
        dy2 = int(max(0, min(dh - 1, y2 * sy)))

        if dx2 <= dx1 or dy2 <= dy1:
            return None

        cx1 = dx1 + int((dx2 - dx1) * ROI_INNER_MIN)
        cx2 = dx1 + int((dx2 - dx1) * ROI_INNER_MAX)
        cy1 = dy1 + int((dy2 - dy1) * ROI_INNER_MIN)
        cy2 = dy1 + int((dy2 - dy1) * ROI_INNER_MAX)

        if cx2 <= cx1 or cy2 <= cy1:
            return None

        roi = depth[cy1:cy2, cx1:cx2]
        if roi.size == 0:
            return None

        roi = roi.astype(np.float32)
        valid = roi[np.isfinite(roi)]
        valid = valid[valid > 0]
        if valid.size == 0:
            return None

        value = float(np.percentile(valid, 30))
        return value / DEPTH_UNIT_SCALE if value > 20.0 else value

    def get_direction(self, cx):
        if cx < self.left_boundary:
            return "LEFT"
        if cx > self.right_boundary:
            return "RIGHT"
        return "CENTER"

    def process_once(self):
        with self.lock:
            if self.latest_frame is None:
                return
            raw_frame = self.latest_frame
            depth = self.latest_depth

        frame = cv2.flip(raw_frame, 1) if MIRROR_IMAGE else raw_frame.copy()
        tensor_sample = pull_sample(self.tensor_sink, 0)

        obstacle_candidates = []
        person_markers = []

        if tensor_sample is not None:
            raw_bytes = sample_to_bytes(tensor_sample)
            if raw_bytes is not None:
                all_dets = parse_yolov8_tensors(raw_bytes)

                obstacle_dets = [d for d in all_dets if d["class_id"] == TARGET_CLASS_BIRD]
                person_dets = [d for d in all_dets if d["class_id"] == TARGET_CLASS_PERSON]

                obstacle_dets = nms_detections(obstacle_dets)
                person_dets = nms_detections(person_dets)

                for det in obstacle_dets:
                    x1, y1, x2, y2 = det_to_frame_box_xyxy(det)
                    distance = self.get_distance_from_depth(depth, (x1, y1, x2, y2))
                    if distance is None:
                        continue

                    raw_cx = (x1 + x2) / 2.0
                    raw_cy = (y1 + y2) / 2.0

                    if MIRROR_IMAGE:
                        mx1 = FRAME_W - 1 - x2
                        mx2 = FRAME_W - 1 - x1
                        cx = FRAME_W - 1 - raw_cx
                        cy = raw_cy
                        display_box = (mx1, y1, mx2, y2)
                    else:
                        cx = raw_cx
                        cy = raw_cy
                        display_box = (x1, y1, x2, y2)

                    obstacle_candidates.append({
                        "distance": distance,
                        "conf": det["conf"],
                        "box": display_box,
                        "cx": cx,
                        "cy": cy,
                    })

                for det in person_dets:
                    x1, y1, x2, y2 = det_to_frame_box_xyxy(det)
                    raw_cx = (x1 + x2) / 2.0
                    raw_cy = (y1 + y2) / 2.0

                    cx = (FRAME_W - 1 - raw_cx) if MIRROR_IMAGE else raw_cx
                    cy = raw_cy

                    person_markers.append({
                        "conf": det["conf"],
                        "cx": cx,
                        "cy": cy,
                    })

        # Draw person markers
        for marker in person_markers:
            pcx = int(marker["cx"])
            pcy = int(marker["cy"])

            cv2.drawMarker(
                frame,
                (pcx, pcy),
                (102, 255, 255),
                markerType=cv2.MARKER_CROSS,
                markerSize=18,
                thickness=2
            )
            cv2.putText(
                frame,
                f"Person {marker['conf']:.2f}",
                (pcx + 8, max(25, pcy - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (102, 255, 255),
                2
            )

        # Highlight nearest obstacle
        nearest = None
        if obstacle_candidates:
            nearest = min(obstacle_candidates, key=lambda p: p["distance"])
            x1, y1, x2, y2 = nearest["box"]
            cx = nearest["cx"]
            distance = nearest["distance"]

            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 2)
            cv2.putText(
                frame,
                f"Obstacle_Bird {distance:.2f}m",
                (x1, max(30, y1 - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2
            )
            cv2.circle(frame, (int(cx), int((y1 + y2) / 2)), 5, (0, 255, 255), -1)

        self.draw_deadzone(frame)
        self.update_fps()
        self.draw_status(frame, depth, nearest)

        cv2.imshow(WINDOW_NAME, frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q") or key == 27:
            rclpy.shutdown()

    def draw_deadzone(self, frame):
        cv2.line(frame, (self.left_boundary, 0), (self.left_boundary, FRAME_H), (255, 255, 255), 1)
        cv2.line(frame, (self.right_boundary, 0), (self.right_boundary, FRAME_H), (255, 255, 255), 1)

    def draw_status(self, frame, depth, nearest):
        cv2.putText(
            frame,
            f"FPS: {self.fps_display:.1f}",
            (15, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 255),
            2
        )

        if depth is None:
            status = "Depth: waiting..."
            color = (0, 0, 255)
        elif nearest is None:
            status = "Nearest Obstacle: none"
            color = (0, 0, 255)
        else:
            direction = self.get_direction(nearest["cx"])
            status = f"Obstacle: {nearest['distance']:.2f}m [{direction}]"
            color = (0, 255, 0)

        cv2.putText(frame, status, (15, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

    def update_fps(self):
        self.fps_counter += 1
        now = time.time()
        elapsed = now - self.last_fps_time
        if elapsed >= 1.0:
            self.fps_display = self.fps_counter / elapsed
            self.fps_counter = 0
            self.last_fps_time = now

    def destroy_node(self):
        if self.appsrc is not None:
            try:
                self.appsrc.emit("end-of-stream")
            except Exception:
                pass
        if self.pipeline is not None:
            self.pipeline.set_state(Gst.State.NULL)
        cv2.destroyAllWindows()
        super().destroy_node()

def main():
    rclpy.init()
    node = None
    signal.signal(signal.SIGINT, lambda s, f: rclpy.shutdown())

    try:
        node = OrbbecTopicNPUPersonBirdVision()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

if __name__ == "__main__":
    main()