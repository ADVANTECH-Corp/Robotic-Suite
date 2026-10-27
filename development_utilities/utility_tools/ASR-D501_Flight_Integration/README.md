# ASR-D501 Flight Integration

This document provides an overview of the demonstrated Advantech Drone Module Solution, powered by the **ASR-D501 (QCS6490)** platform.

##  Official Documentation
For comprehensive technical details, system architecture, and step-by-step setup guides, please refer to the official Advantech Robotic Suite website:
* [ASR-D501 Flight Integration Overview](https://docs.robotic-suite.advantech.com/docs/Solution/cognitive-autopilot/d501-autonomous-flight-core/)

##  System Components

The drone module solution is divided into five key subsystems. The table below outlines each component and its associated source files. 

| # | Component | Description | Associated File(s) | Status | Documentation |
|:-:| :--- | :--- | :---: | :---: | :---: |
| **1** | **MIPI Camera Demo** | Real-time visual inspection and object detection using the IMX577 MIPI camera. | `IMX577_demo.py` | ✅ Active | [View Guide 🔗](https://docs.robotic-suite.advantech.com/docs/Solution/cognitive-autopilot/mipi_camera/) |
| **2** | **Obstacle Avoidance** | Edge AI obstacle detection and depth estimation using USB camera. | `obstacle_det.py` | ✅ Active | [View Guide 🔗](https://docs.robotic-suite.advantech.com/docs/Solution/cognitive-autopilot/obstacle_avoidance/) |
| **3** | **LiDAR Integration** | Spatial mapping and long-range detection capabilities using a 2D LiDAR sensor. | `ao_lidar_node2` folder | ✅ Active | [View Guide 🔗](https://docs.robotic-suite.advantech.com/docs/Solution/cognitive-autopilot/lidar_integration/) |
| **4** | **IMU Dashboard** | IMU data monitoring for accurate flight orientation and attitude estimation. | check [ROS 2 IMU Dashboard Monitor](https://github.com/ADVANTECH-Corp/Robotic-Suite/tree/2.1/development_utilities/utility_tools/imu_dashboard_monitor) | ✅ Active | [View Guide 🔗](https://docs.robotic-suite.advantech.com/docs/Solution/cognitive-autopilot/imu_dashboard/) |
| **5** | **System Monitor** | Real-time hardware monitoring tool. | `system_monitor.py` | ✅ Active | [View Guide 🔗](https://docs.robotic-suite.advantech.com/docs/Solution/cognitive-autopilot/system_monitor/) |
