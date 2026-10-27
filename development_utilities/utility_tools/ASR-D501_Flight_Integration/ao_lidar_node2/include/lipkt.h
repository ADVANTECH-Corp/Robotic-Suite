#ifndef __LIPKT_H
#define __LIPKT_H

// C++ library headers
#include <cstring>
#include <mutex>
#include <vector>
#include <iomanip>
#include <queue>

// ROS headers
#include <sensor_msgs/msg/laser_scan.hpp>
#include <rclcpp/clock.hpp>
#include <rclcpp/time_source.hpp>

// Custom headers
#include <topaz_datatype.h>

namespace aolidar
{
	struct PointDataTypeDef {
        float angle;
        uint16_t distance;
        uint16_t intensity;
        uint64_t stamp;
        double x;
        double y;

        PointDataTypeDef(float angle, uint16_t distance, uint16_t intensity, uint64_t stamp = 0, double x = 0, double y = 0) {
            this->angle = angle;
            this->distance = distance;
            this->intensity = intensity;
            this->stamp = stamp;
            this->x = x;
            this->y = y;
        }
        PointDataTypeDef(){}
    };

    typedef std::vector<PointDataTypeDef> vPointData;
	
	class LiPkt 
	{
		public:
			LiPkt();
			LiPkt(float scanning_frequency, int points_per_second);
			LiPkt(float scanning_frequency, int points_per_second, int intensity_on);
			LiPkt(float scanning_frequency, int points_per_second, int intensity_on, int dense_on);

			void RecvCallback(const char *data, size_t len);
			bool IsFrameReady(void) { 
				std::lock_guard<std::mutex> lock(lock1);
				return is_frame_rdy; 
			}
			void ResetFrameReady(void) { 
				std::lock_guard<std::mutex> lock(lock1);
				is_frame_rdy = false; 
			}
			bool IsMessageReady(void) { return is_msg_rdy; }
			void ResetMessageReady(void) { is_msg_rdy = false; }
			
			void SetFrame(const std::string _frame_id) { frame_id = _frame_id; }
			void SetAngleMin(const float _angle_min) { angle_min = _angle_min; }
			void SetAngleMax(const float _angle_max) { angle_max = _angle_max; }
			void SetRangeMin(const float _range_min) { range_min = _range_min; }
			void SetRangeMax(const float _range_max) { range_max = _range_max; }
			void SetAngleAlign(const float _angle_align) { angle_align = _angle_align; }

			bool Parse(const uint8_t *data, size_t len);
			void Assemble_Packets(void);
			void ToLaserScan(vPointData src);
			sensor_msgs::msg::LaserScan GetLaserScan() { return pub_out; }
			
			int MsgQueueSize() { return lidar_MsgQueue.size(); }
			bool MsgQueueEmpty() { return lidar_MsgQueue.empty(); }
			std::pair<long,  std::string> GetMsg() { return lidar_MsgQueue.front(); }
			void MsgQueuePop() { 
				if (lidar_MsgQueue.size()) 
					lidar_MsgQueue.pop(); 
			}
			
			bool Checksum(const uint16_t header, const uint8_t* arr, uint16_t length);
			
		private:
			std::string frame_id;
			float angle_increment;
			float angle_increment_half;
			float angle_min;
			float angle_max;
			float range_min;
			float range_max;
			float angle_align;
			int intensity_on;
			int dense_on;
			
			int points_per_sec;
			int points_per_scan;
			float scanning_freq;
			
            LidarDataTypeDef liData;
			LidarDataSimpTypeDef liData_Simp;
            LidarAttributeTypeDef liAttr;
            LidarErrorTypeDef liError;
            LidarAckTypeDef liAck;		
			
			bool is_frame_rdy;
			bool is_msg_rdy;

			const int max_queue_len = 100;
			std::queue<std::pair<long,  std::string>> lidar_MsgQueue;
			vPointData point_data_tmp;
            vPointData point_data_out;
            std::mutex lock1;
            std::mutex lock2;
			std::mutex lock3;
			
			sensor_msgs::msg::LaserScan pub_out;
			rclcpp::Clock::SharedPtr clock;
			rclcpp::TimeSource ts;
			
			//func
			void SetFrameReady(void) {
				std::lock_guard<std::mutex> lock(lock1);
				is_frame_rdy = true;
			}
			void SetScanData(vPointData& src) {
				std::lock_guard<std::mutex> lock(lock2);
				point_data_out = src;
			}
			void SetMessageReady(void) {
				std::lock_guard<std::mutex> lock(lock3);
				is_msg_rdy = true;
			}

			bool IsPacket(uint16_t header) {
				if (header == RANGE_PACKET_HEADER ||
						header == ERROR_PACKET_HEADER ||
						header == ACK_PACKET_HEADER ||
						header == ATTRIBUTE_PACKET_HEADER)
					return true;
			
				return false;
			}
			int GetGoodCount(uint16_t header) {
				if (header == RANGE_PACKET_HEADER) 					return sizeof(LidarDataTypeDef);
				else if (header == ERROR_PACKET_HEADER) 		return sizeof(LidarErrorTypeDef);
				else if (header == ACK_PACKET_HEADER) 				return sizeof(LidarAckTypeDef);
				else if (header == ATTRIBUTE_PACKET_HEADER) return sizeof(LidarAttributeTypeDef);
				else return 0;
			}
			void ParsePacket(uint16_t header, const uint8_t *data, size_t len);
			void ParseRangePacket(const uint8_t *data, size_t len);
			void ParseRangePacket_Simp(const uint8_t *data, size_t len);
			void ParseErrorPacket(const uint8_t *data, size_t len);
			void ParseAckPacket(const uint8_t *data, size_t len);
			void ParseAttributePacket(const uint8_t *data, size_t len);
			
			long GetNowTime(void) {
				auto now = std::chrono::system_clock::now();
				auto now_ms = std::chrono::time_point_cast<std::chrono::milliseconds>(now);
				auto value = now_ms.time_since_epoch();
				return (long)value.count();
			}
			std::string Integer2HexStr(int n) {
				std::stringstream ss;
				ss << std::hex << std::setw(2) << std::setfill('0') << (int)n;
				std::string out = ss.str();
				return out;
			}
			std::string to_string_with_precision(const float fvalue, const int n = 2);
            std::string to_string_with_setfill(const int i, const int n = 2);
			
	};
}

#endif // __LIPKT_H