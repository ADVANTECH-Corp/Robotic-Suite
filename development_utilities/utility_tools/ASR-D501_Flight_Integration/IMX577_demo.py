#!/usr/bin/env python3
"""
IMX577 MIPI demo for ASR-D501

This script provides a real-time object detection demonstration using the IMX577 MIPI camera on the ASR-D501 platform.
It leverages GStreamer for hardware-accelerated video capture, processing, and NPU-accelerated inference.

Pipeline:
qtiqmmfsrc camera=0
→ NV12 640x480
→ horizontal flip
→ tee
  ├─ clean branch → videomixer → appsink → OpenCV black style window
  └─ NPU inference → qtimlpostprocess → overlay → videomixer
"""

import os
import time
import signal

import cv2
import numpy as np

import gi
gi.require_version("Gst", "1.0")
from gi.repository import Gst


# ─────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────

# Camera original output size
WIDTH = 640
HEIGHT = 480

FPS = 30

CAMERA_ID = 0

MODEL_PATH = "./yolov8_det.tflite"
LABEL_PATH = "./labels.txt"

WINDOW_NAME = "MIPI YOLO NPU View"

# Display canvas size. You can adjust the width or height as needed.
CANVAS_WIDTH = 640
CANVAS_HEIGHT = 480

# Use OpenCV resizable window.
WINDOW_RESIZABLE = True

# Overlay style
SHOW_TITLE = True
SHOW_FPS = True


# ─────────────────────────────────────────────────────────
# GSTREAMER PIPELINE
# ─────────────────────────────────────────────────────────

def build_pipeline():
    pipeline = f"""
    qtiqmmfsrc name=camsrc camera={CAMERA_ID}
    ! video/x-raw,format=NV12,width={WIDTH},height={HEIGHT},framerate={FPS}/1
    ! videoflip method=horizontal-flip
    ! tee name=split

    split. ! queue max-size-buffers=20 leaky=no
      ! videoconvert
      ! video/x-raw,format=BGRA,width={WIDTH},height={HEIGHT},framerate={FPS}/1
      ! videomixer name=mix
      ! queue
      ! videoconvert
      ! video/x-raw,format=BGR,width={WIDTH},height={HEIGHT},framerate={FPS}/1
      ! appsink name=sink sync=false max-buffers=2 drop=true emit-signals=false

    split. ! queue max-size-buffers=2 leaky=downstream
      ! qtimlvconverter engine=fcv
      ! qtimltflite delegate=external
          external-delegate-path=libQnnTFLiteDelegate.so
          external-delegate-options="QNNExternalDelegate,backend_type=htp;"
          model={MODEL_PATH}
      ! qtimlpostprocess
          module=yolov8
          labels={LABEL_PATH}
          results=10
      ! video/x-raw,format=BGRA,width={WIDTH},height={HEIGHT},framerate={FPS}/1
      ! queue max-size-buffers=2 leaky=downstream
      ! mix.
    """

    return pipeline


# ─────────────────────────────────────────────────────────
# APPSINK HELPERS
# ─────────────────────────────────────────────────────────

def pull_sample(appsink, timeout_ns):
    try:
        return appsink.emit("try-pull-sample", timeout_ns)
    except Exception:
        return None


def sample_to_bgr(sample):
    buffer = sample.get_buffer()
    caps = sample.get_caps()
    structure = caps.get_structure(0)

    width = structure.get_value("width")
    height = structure.get_value("height")
    fmt = structure.get_value("format")

    if fmt != "BGR":
        raise RuntimeError(f"Unexpected format: {fmt}, expected BGR")

    ok, map_info = buffer.map(Gst.MapFlags.READ)
    if not ok:
        raise RuntimeError("Failed to map GstBuffer")

    try:
        frame = np.frombuffer(map_info.data, dtype=np.uint8)

        expected_size = width * height * 3
        if frame.size < expected_size:
            raise RuntimeError(
                f"Frame size mismatch: got {frame.size}, expected {expected_size}"
            )

        frame = frame[:expected_size].reshape((height, width, 3)).copy()
        return frame

    finally:
        buffer.unmap(map_info)


# ─────────────────────────────────────────────────────────
# DISPLAY HELPERS
# ─────────────────────────────────────────────────────────

def make_black_style_view(frame, fps_display):

    canvas = np.zeros((CANVAS_HEIGHT, CANVAS_WIDTH, 3), dtype=np.uint8)

    src_h, src_w = frame.shape[:2]

    available_w = CANVAS_WIDTH
    available_h = CANVAS_HEIGHT

    if SHOW_TITLE:
        # Reserve a small header region.
        available_h -= 44
        top_offset = 44
    else:
        top_offset = 0

    scale = min(available_w / src_w, available_h / src_h)
    new_w = max(1, int(src_w * scale))
    new_h = max(1, int(src_h * scale))

    if new_w != src_w or new_h != src_h:
        frame_show = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
    else:
        frame_show = frame

    x0 = (CANVAS_WIDTH - new_w) // 2
    y0 = top_offset + (available_h - new_h) // 2

    canvas[y0:y0 + new_h, x0:x0 + new_w] = frame_show

    # Thin border around video
    cv2.rectangle(
        canvas,
        (x0 - 1, y0 - 1),
        (x0 + new_w + 1, y0 + new_h + 1),
        (38, 50, 68),
        1,
    )

    if SHOW_TITLE:
        cv2.putText(
            canvas,
            "IMX577",
            (420, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

    if SHOW_FPS:
        fps_text = f"FPS: {fps_display:.1f}"

        # Top-right FPS card
        card_w = 120
        card_h = 30
        card_x1 = CANVAS_WIDTH - card_w - 12
        card_y1 = 10
        card_x2 = CANVAS_WIDTH - 12
        card_y2 = card_y1 + card_h

        cv2.rectangle(
            canvas,
            (card_x1, card_y1),
            (card_x2, card_y2),
            (17, 24, 39),
            -1,
        )
        cv2.rectangle(
            canvas,
            (card_x1, card_y1),
            (card_x2, card_y2),
            (38, 50, 68),
            1,
        )
        cv2.putText(
            canvas,
            fps_text,
            (card_x1 + 12, card_y1 + 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

    return canvas


# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────

def main():
    os.environ.setdefault("XDG_RUNTIME_DIR", "/run/user/1000")
    os.environ.setdefault("WAYLAND_DISPLAY", "wayland-0")

    Gst.init(None)

    running = True

    def on_sigint(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, on_sigint)

    pipeline_desc = build_pipeline()

    print("[INFO] Launching MIPI YOLO NPU pipeline...")
    print(f"[INFO] Camera: qtiqmmfsrc camera={CAMERA_ID}")
    print(f"[INFO] Source Format : NV12 {WIDTH}x{HEIGHT} {FPS}fps")
    print(f"[INFO] Display Format: BGR {CANVAS_WIDTH}x{CANVAS_HEIGHT} {FPS}fps")
    print("[INFO] Display Style: OpenCV black canvas")
    print(f"[INFO] Model : {MODEL_PATH}")

    try:
        pipeline = Gst.parse_launch(pipeline_desc)
    except Exception as e:
        print("[ERROR] Failed to create pipeline:")
        print(e)
        return

    appsink = pipeline.get_by_name("sink")
    if appsink is None:
        print("[ERROR] Failed to get appsink named 'sink'")
        pipeline.set_state(Gst.State.NULL)
        return

    bus = pipeline.get_bus()

    # WINDOW_GUI_NORMAL removes the Qt toolbar buttons such as zoom/pan/save
    # when OpenCV is built with Qt support.
    if WINDOW_RESIZABLE:
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL | cv2.WINDOW_GUI_NORMAL)
    else:
        cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE | cv2.WINDOW_GUI_NORMAL)

    cv2.resizeWindow(WINDOW_NAME, CANVAS_WIDTH, CANVAS_HEIGHT)

    ret = pipeline.set_state(Gst.State.PLAYING)

    if ret == Gst.StateChangeReturn.FAILURE:
        print("[ERROR] Failed to set pipeline to PLAYING")
        pipeline.set_state(Gst.State.NULL)
        cv2.destroyAllWindows()
        return

    print("[INFO] Pipeline PLAYING — NPU inference active")
    print("[INFO] Press q / ESC / Ctrl+C to quit")

    fps_display = 0.0
    frame_counter = 0
    last_fps_time = time.time()

    try:
        while running:
            msg = bus.timed_pop_filtered(
                1 * Gst.MSECOND,
                Gst.MessageType.ERROR | Gst.MessageType.EOS
            )

            if msg:
                if msg.type == Gst.MessageType.ERROR:
                    err, debug = msg.parse_error()
                    print("[ERROR] GStreamer error:", err)
                    print("[ERROR] Debug info:", debug)
                    break

                if msg.type == Gst.MessageType.EOS:
                    print("[INFO] EOS received")
                    break

            sample = pull_sample(appsink, 100_000_000)

            if sample is None:
                continue

            frame = sample_to_bgr(sample)

            # FPS calculation
            frame_counter += 1
            now = time.time()
            elapsed = now - last_fps_time

            if elapsed >= 1.0:
                fps_display = frame_counter / elapsed
                frame_counter = 0
                last_fps_time = now

            display = make_black_style_view(frame, fps_display)

            cv2.imshow(WINDOW_NAME, display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q") or key == 27:
                print("[INFO] Quit requested")
                break

    except KeyboardInterrupt:
        print("[INFO] Interrupted by user")

    except Exception as e:
        print("[ERROR] Runtime exception:")
        print(e)

    finally:
        print("[INFO] Stopping pipeline...")
        pipeline.set_state(Gst.State.NULL)
        cv2.destroyAllWindows()
        print("[INFO] Done.")


if __name__ == "__main__":
    main()

