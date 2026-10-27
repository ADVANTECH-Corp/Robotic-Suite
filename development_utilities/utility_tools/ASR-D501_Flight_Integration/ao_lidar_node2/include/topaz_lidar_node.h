#ifndef __TOPAZ_LIDAR_DRIVER_H
#define __TOPAZ_LIDAR_DRIVER_H

// C++ library headers
#include <chrono>
#include <memory>
#include <functional>

// ROS library headers
#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/laser_scan.hpp>
#include <std_msgs/msg/string.hpp>

// Custom library headers
#include <serial_driver_linux.h>
#include <lipkt.h>

using namespace std::chrono_literals;

namespace aolidar 
{
	class Topaz_Lidar_Node : public rclcpp::Node
	{
		public:
			Topaz_Lidar_Node();
		
		private:
			rclcpp::TimerBase::SharedPtr timer_;
			rclcpp::Publisher<sensor_msgs::msg::LaserScan>::SharedPtr publisher_;
			SerialDriverLinux *sp_;
			LiPkt *lidar_;
			
			void timer_callback();
	};	
}

#endif // __TOPAZ_LIDAR_DRIVER_H
