# Example Workflows

This section contains ready-to-run, teaching-oriented examples demonstrating common perception, AMR, and manipulator workflows.

Many examples include recorded ROS bags, allowing users to observe system behavior and understand the workflow without requiring physical sensors or robots.

The examples are organized into the following categories:

- **[ISAAC ROS](./isaac_ros/)**  
  GPU-accelerated perception and advanced robotics workflows using NVIDIA Isaac ROS, including multi-sensor integration, 3D scene reconstruction, and obstacle avoidance.

- **[QIR ROS](./qir_ros/)**  
  Qualcomm-accelerated perception workflows and teaching applications that demonstrate how multiple QIR ROS SDK packages can share sensor data and operate together.

- **[ROS Base](./ros2/)**  
  Core ROS 2 examples covering the following robotics application areas:

  - **Mobility** – Mapping, localization, navigation, and obstacle avoidance workflows for mobile robots.
  - **[Manipulation](./ros2/manipulator/)** – A ROS bag–supported teaching example showing a recorded vision-based manipulator workflow, from color-block perception and camera-frame position estimation to robot-arm motion visualization.

These examples can be used as:

- Interactive demonstrations for understanding robotics concepts and system behavior.
- Reference configurations for learning how ROS 2 components and platform SDK pipelines work together.
- Starting points for adapting the workflows to your own sensors, robots, and applications.

The examples are intended for teaching and evaluation. They demonstrate important concepts and integration patterns rather than complete solutions that can be applied unchanged to every robot platform.
