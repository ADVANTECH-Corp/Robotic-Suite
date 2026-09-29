# Development Utilities

This section provides development resources to help users quickly explore and build robotics applications using Robotic Suite.

It is organized into three main parts:

- **Example Workflows** – Ready-to-run examples demonstrating common perception, AMR, and manipulator workflows, including mapping, navigation, multi-function perception, and vision-based manipulation.
- **Core Techniques** – Code-level tutorials covering reusable robotics techniques that can be integrated into your own applications.
- **Development Environment** – Pre-configured environments for ROS 2, ISAAC ROS, QIR ROS SDK, and Autoware to accelerate development.

## Example Workflows

These examples demonstrate common perception, AMR, and manipulator workflows and can be used as:

- Interactive demos to understand system behavior  
- Reference configurations for building your own applications  

### ISAAC ROS

- [Multi-Sensor Function](./example/isaac_ros/multi_sensor_function)  
  Combine multiple sensors into a unified perception pipeline using Isaac ROS.

- [3D Scene Persistence](./example/isaac_ros/3d_scene_persistence)  
  Build and maintain a 3D representation of the environment for long-term perception.

- [3D Camera Obstacle Avoidance](./example/isaac_ros/3d_camera_obstacle_avoidance)  
  Use 3D cameras and Isaac ROS to detect obstacles and plan safe motion around them.

---

### QIR ROS

- [2D Object Depth Estimation](./example/qir_ros/2d_object_depth_estimation)  
  Use a recorded 2D camera stream to run `sample_depth_estimation` and `sample_apriltag` simultaneously, demonstrating how multiple QIR ROS SDK packages can share the same sensor input.

---

### ROS Base

- [2D LiDAR Mapping](./example/ros2/2d_mapping_with_lidar)  
  Create a 2D occupancy grid map from a 2D LiDAR using slam_toolbox, and visualize it in RViz.  
  
- [2D LiDAR Navigation](./example/ros2/2d_lidar_navigation)  
  Learn the basic concepts of Nav2-based navigation and obstacle avoidance with a 2D LiDAR.
  
- [3D LiDAR Mapping](./example/ros2/3d_mapping_with_lidar)  
  Generate a 3D map from a 3D LiDAR using `lidarslam_ros2`, and inspect the result in RViz.

- [Manipulator](./example/ros2/manipulator)  
  Explore a recorded vision-based manipulator workflow that connects color-block perception and camera-frame position estimation with robot-arm motion visualization.

## Core Techniques

These tutorials explain small, reusable robotics techniques that can be studied independently and integrated into larger applications.

- [Color Profile Creation](./core_techniques/color_profile_creation)  
  Collect HSV samples from an RGB image and create reusable color profiles for color-based detection.

- [Color Block Detection & Position Estimation](./core_techniques/color_block_detection_position_estimation)  
  Detect colored blocks and estimate their camera-frame position and approximate orientation using RGB, aligned depth, and camera information.

## Development Environment  

Robotic Suite provides pre-configured development environments to help users quickly get started with robotics application development.

- [ROS Jazzy](https://docs.ros.org/en/jazzy/index.html)  
ROS 2 Jazzy is pre-installed and configured on the host system, providing a stable and ready-to-use foundation for ROS-based development.

- [ROS Humble](https://docs.ros.org/en/humble/index.html)  
ROS 2 Humble is pre-installed and configured on the host system, providing a stable and ready-to-use foundation for ROS-based development.

- [ISAAC ROS](https://github.com/NVIDIA-ISAAC-ROS)  
A fully integrated Docker-based environment is provided, including pre-installed ISAAC ROS dependencies.  
This allows users to quickly build and run GPU-accelerated perception and AI applications without complex setup.

- [QIR ROS SDK](https://github.com/qualcomm-linux/meta-qcom-robotics-sdk)  
A fully integrated Docker-based environment is provided, including pre-installed QIR ROS SDK dependencies.  
This allows users to quickly build and run applications without complex setup.

- [Autoware](https://github.com/autowarefoundation/autoware)  
A containerized Autoware environment is provided, enabling users to explore autonomous driving workflows such as perception, planning, and control with minimal setup effort.
