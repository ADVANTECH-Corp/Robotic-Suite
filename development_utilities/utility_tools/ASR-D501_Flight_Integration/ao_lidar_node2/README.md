# ROS 2 Package for 2D LiDAR

A simple sample for using ASIA OPTICAL 2D LiDAR (OASAB0649) with ROS 2.

## Requirements

`ao_lidar_node2` has been developed and verified with ROS 2 Jazzy on the ASR-D501 platform (Ubuntu 24.04).
It should also be compatible with other ROS 2 versions (but not fully tested).

## Installation

1. Creating a workspace `<your_ros2_ws>`

   ```bash
   source /opt/ros/jazzy/setup.bash
   mkdir -p ~/<your_ros2_ws>/src
   ```

2. Copy the `ao_lidar_node2` folder to `<your_ros2_ws>/src`
3. Installing dependencies

   Change to `<your_ros2_ws>` and check missing dependencies before building.

   ```bash
   cd ~/<your_ros2_ws>
   rosdep update && rosdep install --from-path src --ignore-src -y
   ```
4. Building packages

   ```bash
   colcon build --packages-select ao_lidar_node2
   ```

## Usage

1. Open a new terminal and source the setup files

   ```bash
   source ~/<your_ros2_ws>/install/setup.bash
   ```

2. Run the ao_lidar_node2

   ```bash
   ros2 launch ao_lidar_node2 topaz_b.launch.py
   ```

3. Viewing LiDAR point clouds with RViz

   ```bash
   ros2 launch ao_lidar_node2 topaz_b_rviz.launch.py
   ```
