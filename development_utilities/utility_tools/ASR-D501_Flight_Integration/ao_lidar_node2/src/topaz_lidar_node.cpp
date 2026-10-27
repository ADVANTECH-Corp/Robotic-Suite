#include "topaz_lidar_node.h"

namespace aolidar 
{
	Topaz_Lidar_Node :: Topaz_Lidar_Node()
		: Node("topaz_node")
		, sp_(new SerialDriverLinux)
	{
		const std::string ros_driver_version = "0.2.1";
		
		std::string topic_name = this->declare_parameter("topic_name", "/scan");
		std::string lidar_frame = this->declare_parameter("lidar_frame", "laser");
		std::string port_name = this->declare_parameter("serial_port", "/dev/ttyACM0"); 
		int baudrate = this->declare_parameter("baudrate", 921600);
		float scanning_frequency = this->declare_parameter("scanning_frequency", 10.0);
		int points_per_second = this->declare_parameter("points_per_second", 10800);
		float angle_min = this->declare_parameter("angle_min", -180.0);
		float angle_max = this->declare_parameter("angle_max", 180.0);
		float range_min = this->declare_parameter("range_min", 0.06);
		float range_max = this->declare_parameter("range_max", 15.0);
		float angle_align = this->declare_parameter("angle_align", 0.0);
		int intensity_on = this->declare_parameter("intensity_on", 1);
		int dense_on = this->declare_parameter("dense_on", 0);
		
		RCLCPP_INFO(rclcpp::get_logger("rclcpp"), "ros_driver_version: %s", ros_driver_version.c_str());
		RCLCPP_INFO(rclcpp::get_logger("rclcpp"), "topic_name: %s", topic_name.c_str());
		RCLCPP_INFO(rclcpp::get_logger("rclcpp"), "lidar_frame: %s", lidar_frame.c_str());
		RCLCPP_INFO(rclcpp::get_logger("rclcpp"), "port_name: %s", port_name.c_str());
		RCLCPP_INFO(rclcpp::get_logger("rclcpp"), "baudrate: %d", baudrate);
		RCLCPP_INFO(rclcpp::get_logger("rclcpp"), "scanning_frequency: %.2f", scanning_frequency);
		RCLCPP_INFO(rclcpp::get_logger("rclcpp"), "points_per_second: %d", points_per_second);
		RCLCPP_INFO(rclcpp::get_logger("rclcpp"), "angle_min: %.2f", angle_min);
		RCLCPP_INFO(rclcpp::get_logger("rclcpp"), "angle_max: %.2f", angle_max);
		RCLCPP_INFO(rclcpp::get_logger("rclcpp"), "range_min: %.2f", range_min);
		RCLCPP_INFO(rclcpp::get_logger("rclcpp"), "range_max: %.2f", range_max);
		RCLCPP_INFO(rclcpp::get_logger("rclcpp"), "intensity_on: %d", intensity_on);
		RCLCPP_INFO(rclcpp::get_logger("rclcpp"), "dense_on: %d", dense_on);
		
		publisher_ = this->create_publisher<sensor_msgs::msg::LaserScan>(topic_name, 20);
		
		lidar_ = new LiPkt(scanning_frequency, points_per_second, intensity_on, dense_on);
		lidar_->SetFrame(lidar_frame);
		lidar_->SetAngleMin(angle_min);
		lidar_->SetAngleMax(angle_max);
		lidar_->SetRangeMin(range_min);
		lidar_->SetRangeMax(range_max);
		lidar_->SetAngleAlign(angle_align);

		if(sp_->Open(port_name, baudrate)) {
			RCLCPP_INFO(rclcpp::get_logger("rclcpp"), "Open Port Successful");
			sp_->SetRecvCallback([this](const char *byte, size_t len) {
				if(lidar_->Parse((uint8_t*)byte, len)) {
					lidar_->Assemble_Packets();
				}
			});
		}
		else {
			RCLCPP_ERROR(rclcpp::get_logger("rclcpp"), "Open Port Failed");
		}
		
		timer_ = this->create_wall_timer(50ms, std::bind(&Topaz_Lidar_Node::timer_callback, this));
	}
	//
	void Topaz_Lidar_Node :: timer_callback()
	{
		auto message = std_msgs::msg::String();
		if(lidar_->IsFrameReady()) {
			publisher_->publish(lidar_->GetLaserScan());
			lidar_->ResetFrameReady();
		}
		
		if(lidar_->IsMessageReady()) {
			while(!lidar_->MsgQueueEmpty()) {
				RCLCPP_INFO(rclcpp::get_logger("rclcpp"), lidar_->GetMsg().second.c_str());
				lidar_->MsgQueuePop();				
			}
			lidar_->ResetMessageReady();
		}
	}	
}