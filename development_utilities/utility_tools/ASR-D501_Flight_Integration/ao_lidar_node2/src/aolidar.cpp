#include "topaz_lidar_node.h"

using namespace aolidar;

int main(int argc, char * argv[])
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<Topaz_Lidar_Node>());
  rclcpp::shutdown();
  return 0;
}
