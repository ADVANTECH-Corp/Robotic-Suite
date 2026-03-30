#!/bin/bash
set -e
script_path="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd $script_path
APP_PATH="/usr/local/Advantech/ros/container/ros-demokit/isaac_ros_kit/apps/advanced_examples/${APP_NAME}"

source /opt/ros/$ROS_DISTRO/setup.bash
source /workspaces/rviz2_plugin/install/setup.bash
export FASTDDS_DEFAULT_PROFILES_FILE="$APP_PATH/config/fastdds_shm_config.xml"

KEEP_ALL=true
DEMO_MODE=2
CAMERA_OPTICAL_FRAMES="['camera_0_left_ir_optical_frame', 'camera_0_right_ir_optical_frame']"

kill_tree() {
    local _pid=$1
    # Recursively find and kill all child processes first
    for child in $(pgrep -P $_pid); do
        kill_tree $child
    done
    # Finally kill the parent process itself
    kill -9 $_pid 2>/dev/null
}

# Check parameter
for arg in "$@"; do
    case $arg in
        demo_mode=*)
            DEMO_MODE="${arg#*=}"
            shift
            ;;
        keep_all=*)
            KEEP_ALL="${arg#*=}"
            shift
            ;;
        camera_optical_frames=*)
            CAMERA_OPTICAL_FRAMES="${arg#*=}"
            shift
            ;;
    esac
done

# Start Visual SLAM example
start_visual_slam() {
    local Camera_Optical_Frames=""
    if [ "$DEMO_MODE" -eq 0 ]; then
        Camera_Optical_Frames="['camera_infra1_optical_frame', 'camera_infra2_optical_frame']"
    elif [ "$DEMO_MODE" -eq 1 ]; then
        Camera_Optical_Frames="['camera_left_ir_optical_frame', 'camera_right_ir_optical_frame']"
    elif [ "$DEMO_MODE" -eq 2 ]; then
        Camera_Optical_Frames="['camera_infra1_optical_frame', 'camera_infra2_optical_frame']"
        if [ -n "$CAMERA_OPTICAL_FRAMES" ]; then
            Camera_Optical_Frames=$CAMERA_OPTICAL_FRAMES
        fi
    fi
    
    ros2 launch isaac_ros_examples isaac_ros_examples.launch.py \
    launch_fragments:=visual_slam \
    interface_specs_file:=$APP_PATH/config/quickstart_interface_specs.json \
    base_frame:=camera_0_link \
    camera_optical_frames:="$Camera_Optical_Frames" &
    vslam_PID=$!
}

# Start Nvblox node (camera-only mode, no LiDAR)
start_nvblox() {
    if [ "$KEEP_ALL" = "true" ]; then
        ros2 run nvblox_ros nvblox_node \
          --ros-args \
          --params-file "/opt/ros/$ROS_DISTRO/share/nvblox_examples_bringup/config/nvblox/specializations/nvblox_dynamics.yaml" \
          -p use_lidar:=false \
          -p mapping_type:=dynamic \
          -p voxel_size:=0.04 \
          -p decay_tsdf_rate_hz:=0.0 \
          -p decay_dynamic_occupancy_rate_hz:=0.0 \
          -p dynamic_mapper.occupancy_decay_to_free:=false \
          -p static_mapper.occupancy_decay_to_free:=false \
          -p clear_map_outside_radius_rate_hz:=0.0 &
        nvblox_PID=$!
    else
        ros2 run nvblox_ros nvblox_node \
          --ros-args \
          --params-file "/opt/ros/$ROS_DISTRO/share/nvblox_examples_bringup/config/nvblox/specializations/nvblox_dynamics.yaml" \
          -p use_lidar:=false \
          -p mapping_type:=dynamic &
        nvblox_PID=$!
    fi
    sleep 3
}

# Start RealSense D457 camera
start_realsense() {
    $APP_PATH/intel_d457/nvblox-intel_d457-play.sh &
    sleep 5
}

# Start Orbbec Gemini-335L camera
start_orbbec() {
    $APP_PATH/orb_335L/nvblox-orb_335L-play.sh &
    sleep 5
}

# Play ros2 bag and perform topic remapping
play_rosbag() {
    $APP_PATH/rosbag/nvblox-bg-play.sh &
    ROSBAG_PID=$!
    sleep 5
}

# Publish a static TF transform (camera_link -> base_link)
publish_static_tf() {
    sleep 3
    ros2 run tf2_ros static_transform_publisher \
        --x 0 --y 0 --z 0 \
        --roll 0 --pitch 0 --yaw 0 \
        --frame-id camera_0_link \
        --child-frame-id base_link &
    tf_PID=$!
}

# Start YOLOv8 object detection
start_yolov8() {
    cd $APP_PATH/config
    ros2 launch isaac_ros_yolov8_visualize.launch.py \
        confidence_threshold:=0.25 \
        nms_threshold:=0.45 \
        input_image_width:=640 \
        input_image_height:=480 \
        network_image_width:=640 \
        network_image_height:=640 \
        image_mean:='[0.0, 0.0, 0.0]' \
        image_stddev:='[1.0, 1.0, 1.0]' \
        engine_file_path:=${ISAAC_ROS_WS}/isaac_ros_assets/models/yolov8/yolov8s.plan \
        input_tensor_names:=["input_tensor"] \
        input_binding_names:='["images"]' \
        output_tensor_names:='["output_tensor"]' \
        output_binding_names:='["output0"]' &
}

# Start UNet segmentation model
start_unet() {
    cd $APP_PATH/config
    ros2 launch isaac_ros_unet_tensor_rt.launch.py \
        engine_file_path:=${ISAAC_ROS_WS}/isaac_ros_assets/models/peoplesemsegnet/optimized_deployable_shuffleseg_unet_amr_v1.0/1/model.plan \
        input_binding_names:=['input_2'] \
        output_binding_names:=['argmax_1'] \
        use_planar_input:='False' \
        network_output_type:='argmax' &
}

# Start RViz2 with predefined visualization configurations
start_rviz() {
    rviz2 -d $APP_PATH/config/nvblox_demo.rviz &
    rviz2 -d $APP_PATH/config/2d_lidar.rviz &
}

main() {
    start_visual_slam
    start_nvblox
    start_yolov8
    start_unet
    
    if [ "$DEMO_MODE" -eq 0 ]; then
        echo "Use RealSense D457 camera"
        start_realsense
        publish_static_tf
        start_rviz
    elif [ "$DEMO_MODE" -eq 1 ]; then
        echo "Use Orbbec Gemini-335l camera"
        start_orbbec
        publish_static_tf
        start_rviz
    elif [ "$DEMO_MODE" -eq 2 ]; then
        echo "Use rosbag"
        play_rosbag
        publish_static_tf
        start_rviz &

        # Infinite loop: restart rosbag playback after it finishes
        while true; do
            wait $ROSBAG_PID
            echo "================== loop =================="
            # Terminate related processes
            kill_tree $vslam_PID
            kill_tree $nvblox_PID
            kill_tree $tf_PID
            sleep 5
            # Restart everything
            ros2 service call /rviz/reset_time std_srvs/srv/Empty &
            start_visual_slam
            start_nvblox
            play_rosbag
            publish_static_tf
        done
    fi
}

main
