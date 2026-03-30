# Development Utilities

This section provides development resources to help users quickly explore and build robotics applications using Robotic Suite.

It is organized into two main parts:

- **Example Workflows** – Ready-to-run examples demonstrating common AMR use cases such as perception, mapping, and navigation  
- **Development Environment** – Pre-configured environments for ISAAC ROS and Autoware to accelerate development

## Example Workflows
These examples demonstrate common AMR workflows and can be used as:

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

### ROS Base
- [2D Mapping with LiDAR](./example/ros2/2d_mapping_with_lidar)  
  Create a 2D occupancy grid map from a 2D LiDAR using slam_toolbox, and visualize it in RViz.  
  
- [2D LiDAR Navigation (AMR)](./example/ros2/2d_lidar_navigation)  
  Learn the basic concepts of Nav2-based navigation and obstacle avoidance with a 2D LiDAR.
  
- [3D Mapping with LiDAR](./example/ros2/3d_mapping_with_lidar)  
  Generate a 3D map from a 3D LiDAR using `lidarslam_ros2`, and inspect the result in RViz.

## Development Environment  
Robotic Suite provides pre-configured development environments to help users quickly get started with robotics application development.
- [ROS Humble](https://docs.ros.org/en/humble/index.html)  
ROS 2 Humble is pre-installed and configured on the host system, providing a stable and ready-to-use foundation for ROS-based development.
- [ISAAC ROS](https://github.com/NVIDIA-ISAAC-ROS)  
A fully integrated Docker-based environment is provided, including pre-installed ISAAC ROS dependencies.
This allows users to quickly build and run GPU-accelerated perception and AI applications without complex setup.
- [Autoware](https://github.com/autowarefoundation/autoware)  
A containerized Autoware environment is provided, enabling users to explore autonomous driving workflows such as perception, planning, and control with minimal setup effort.
