// C++ library headers
#include <chrono>
#include <cmath>

// Custom headers
#include <lipkt.h>
#include <checksum.h>
#include <logger.h>

namespace aolidar
{
	LiPkt::LiPkt() 
		: frame_id("laser")
		, points_per_sec(10800)
		, scanning_freq(10.0)
		, intensity_on(1)
		, dense_on(0)
	{
		clock = std::make_shared<rclcpp::Clock>(RCL_ROS_TIME);
		ts.attachClock(clock);
		this->points_per_scan = (int) this->points_per_sec / this->scanning_freq;
		this->angle_increment = 360.0 * this->scanning_freq / this->points_per_sec;
		this->angle_increment_half = this->angle_increment / 2.0;
	}
	
	LiPkt::LiPkt(float scanning_frequency, int points_per_second) 
		: frame_id("laser")
		, intensity_on(1)
		, dense_on(0)
	{
		clock = std::make_shared<rclcpp::Clock>(RCL_ROS_TIME);
		ts.attachClock(clock);
		this->points_per_scan = (int) points_per_second / scanning_frequency;
		this->angle_increment = 360.0 * scanning_frequency / points_per_second;
		this->angle_increment_half = this->angle_increment / 2.0;
	}
	
	LiPkt::LiPkt(float scanning_frequency, int points_per_second, int intensity_on) 
		: frame_id("laser")
		, dense_on(0)
	{
		clock = std::make_shared<rclcpp::Clock>(RCL_ROS_TIME);
		ts.attachClock(clock);
		this->points_per_scan = (int) points_per_second / scanning_frequency;
		this->angle_increment = 360.0 * scanning_frequency / points_per_second;
		this->angle_increment_half = this->angle_increment / 2.0;
		this->intensity_on = intensity_on;
	}
	
	LiPkt::LiPkt(float scanning_frequency, int points_per_second, int intensity_on, int dense_on) 
		: frame_id("laser")
	{
		clock = std::make_shared<rclcpp::Clock>(RCL_ROS_TIME);
		ts.attachClock(clock);
		this->points_per_scan = (int) points_per_second / scanning_frequency;
		this->angle_increment = 360.0 * scanning_frequency / points_per_second;
		this->angle_increment_half = this->angle_increment / 2.0;
		this->intensity_on = intensity_on;
		this->dense_on = dense_on;
	}
	
    void LiPkt::RecvCallback(const char *data, size_t len)
    {
        if(Parse((uint8_t *)data, len)) {
            Assemble_Packets();
        }
    }
	
	#define bytes_to_u16(MSB, LSB) (((unsigned int) ((unsigned char) MSB )) & 0xff ) << 8 | (((unsigned char) LSB ) & 0xff )
	bool LiPkt::Parse(const uint8_t *data, size_t len)
	{
        static enum {
            HUNT,
            LOF,
            SYNC,
        } state = HUNT;
		
		static uint8_t head_buf[2] = {0};
		static int good_count = 0, count = 0;
		static uint8_t temp[384];
		static uint16_t header;
		static int ccount = 0;
		
		for(int i=0; i<len; i++) {
			uint8_t byte = data[i];
			switch(state) {
				case HUNT:
					{
						 head_buf[1] = head_buf[0];
						 head_buf[0] = byte;
						 header = bytes_to_u16(head_buf[0], head_buf[1]);
						 if(IsPacket(header)) {
							state = LOF;
							good_count = GetGoodCount(header);
							temp[count++] = head_buf[1];
							temp[count++] = head_buf[0];
						 }
						 else {
							good_count = 0;
							count = 0;
							state = HUNT;
						 }
					}
					break;
				case LOF:
					{
						temp[count++] = byte;
						if(count >= good_count) {
							if(Checksum(header, temp, good_count)) {
								ccount++;
								state = SYNC;
							}
							else {
								good_count = 0;
								count = 0;
								head_buf[0] = byte;
								head_buf[1] = 0;
								state = HUNT;
							}
						}
					}
					break;
				case SYNC:
					{
						ParsePacket(header, temp, good_count);
						good_count = 0;
						count = 0;
						head_buf[0] = byte;
						head_buf[1] = 0;
						state = HUNT;
					}
					break;
			}
		}
		return point_data_tmp.size() >= points_per_scan || lidar_MsgQueue.size();
	}

	void LiPkt::Assemble_Packets(void)
	{
		if(point_data_tmp.size() >= points_per_scan) {
			
			vPointData tmp;

			tmp.insert(tmp.begin(), point_data_tmp.begin(), point_data_tmp.begin() + points_per_scan);
			//std::sort(tmp.begin(), tmp.end(), [](PointDataTypeDef a, PointDataTypeDef b) { return a.stamp < b.stamp;} );
			point_data_tmp.erase(point_data_tmp.begin(), point_data_tmp.begin() + points_per_scan);
			ToLaserScan(tmp);
			SetFrameReady();
		}
		
		if(lidar_MsgQueue.size()) {
			SetMessageReady();
		}
	}
	
	void LiPkt::ToLaserScan(vPointData src)
	{
		std::lock_guard<std::mutex> lock(lock2);
		
        pub_out.header.frame_id = frame_id;
		pub_out.header.stamp = clock->now();
		pub_out.angle_increment = angle_increment * M_PI / 180;
        pub_out.angle_min = angle_min * M_PI / 180;
        pub_out.angle_max = angle_max * M_PI / 180;
        pub_out.range_min = range_min;
        pub_out.range_max = range_max;
        pub_out.scan_time = 1.0 / scanning_freq;

		int output_size = (angle_max - angle_min) / angle_increment;
		pub_out.ranges.resize(output_size);
		pub_out.intensities.resize(output_size);
		
        for(auto p : src) {
            float angle = fmod(360.0 + angle_align - p.angle - angle_min, 360.0);
            int index = (int)(angle / angle_increment);
                
            if(index < 0) index += output_size;
            else if(index >= output_size) continue;

            pub_out.ranges[index] = p.distance / 1000.0;
            if(intensity_on)
                pub_out.intensities[index] = p.intensity;
        }
	}
	
	bool LiPkt::Checksum(const uint16_t header, const uint8_t* arr, uint16_t length)
	{
		if (header == RANGE_PACKET_HEADER ||
			header == ERROR_PACKET_HEADER) 					return CalCsum_CCITT16(arr, length);
		else if (header == ACK_PACKET_HEADER) 				return CalCsum_XOR(arr, 2, 5);
		else if (header == ATTRIBUTE_PACKET_HEADER) return CalCsum_XOR(arr, 0, length-1);
		else 																					return false;
	}
	
	void LiPkt::ParsePacket(uint16_t header, const uint8_t *data, size_t len) 
	{
		if (lidar_MsgQueue.size() >= max_queue_len) return;
		
		if (header == RANGE_PACKET_HEADER) 	{
			if(dense_on)  																ParseRangePacket_Simp(data, len);
			else 																				ParseRangePacket(data, len);
		}		
		else if (header == ERROR_PACKET_HEADER) 		ParseErrorPacket(data, len);
		else if (header == ACK_PACKET_HEADER) 				ParseAckPacket(data, len);
		else if (header == ATTRIBUTE_PACKET_HEADER) ParseAttributePacket(data, len);		
	}
	
	void LiPkt::ParseRangePacket(const uint8_t *data, size_t len)
	{
		LidarDataTypeDef *ptr = &liData;
		memcpy((uint8_t *)&liData, data, len);
		
		float start_angle = (float) ptr->angle / 100.0f;
		float speed = (float) ptr->speed;
		
		auto now = std::chrono::system_clock::now();
        auto now_ms = std::chrono::time_point_cast<std::chrono::milliseconds>(now);
        auto value = now_ms.time_since_epoch();
        long duration = value.count();
		
		PointDataTypeDef tmp;
        for(int i=0; i<POINTS_PER_RANGE_PACKET; i++) {
			tmp.angle = start_angle + angle_increment * i;
			if(tmp.angle >= 360) {
				tmp.angle -= 360;
			}				
			tmp.distance = ptr->pts[i].distance;
			tmp.intensity = ptr->pts[i].energy;
			point_data_tmp.push_back(PointDataTypeDef(tmp.angle, tmp.distance, tmp.intensity, duration));				
        }
	}
	
	void LiPkt::ParseRangePacket_Simp(const uint8_t *data, size_t len)
	{
		LidarDataSimpTypeDef *ptr = &liData_Simp;
		memcpy((uint8_t *)&liData_Simp, data, len);
		
		float start_angle = (float) ptr->angle / 100.0f;
		float speed = (float) ptr->speed;
		
		auto now = std::chrono::system_clock::now();
        auto now_ms = std::chrono::time_point_cast<std::chrono::milliseconds>(now);
        auto value = now_ms.time_since_epoch();
        long duration = value.count();
		
		PointDataTypeDef tmp;
        for(int i=0; i<POINTS_PER_RANGE_PACKET_SIMP; i++) {
			tmp.angle = start_angle + angle_increment * i;
			if(tmp.angle >= 360) {
				tmp.angle -= 360;
			}				
			tmp.distance = ptr->pts[i].dist;
			tmp.intensity = ptr->pts[i].engy;
			point_data_tmp.push_back(PointDataTypeDef(tmp.angle, tmp.distance, tmp.intensity, duration));			
        }		
	}
	
	void LiPkt::ParseErrorPacket(const uint8_t *data, size_t len)
	{
		LidarErrorTypeDef *ptr = &liError;
		memcpy((uint8_t *)&liError, data, len);
        const std::string err_str[] =
        {
            "Ranging data timeout",
            "Internal communication abnormal",
            "Counter-clockwise exception",
            "Angular resolution abnormal",
            "Parity error",
            "Framing error",
            "Noise error",
            "Overrun error",
            "Sensor abnormal"
        };

		int i = ptr->errCode & 0xf;
		std::string strErrorCode = "LiDAR error: 0x" + this->Integer2HexStr(ptr->errCode) + ". " + err_str[i];
		lidar_MsgQueue.push(std::pair<long, std::string>(this->GetNowTime(), strErrorCode));
	}
	
	void LiPkt::ParseAckPacket(const uint8_t *data, size_t len)
	{
		LidarAckTypeDef *ptr = &liAck;
		memcpy((uint8_t *)&liAck, data, len);
        const std::string ack_str[] =
        {
            "LiDAR response: ACK",
            "LiDAR response: NACK",
            "LiDAR response: ERROR",
            "LiDAR response: UNDEFINED"
        };
		
		lidar_MsgQueue.push(std::pair<long, std::string>(this->GetNowTime(), ack_str[ptr->ack]));
	}
	
	void LiPkt::ParseAttributePacket(const uint8_t *data, size_t len)
	{
		LidarAttributeTypeDef *ptr = &liAttr;
		memcpy((uint8_t *)&liAttr, data, len);
		
        std::string _uid = "";
        for(int i=0; i<ptr->sys.uid.len; i++) {
            _uid += ptr->sys.uid.name[i];
        }
		
        float _ver1 = (float)ptr->sys.version.v1 / 100.0f;
        float _ver2 = (float)ptr->sys.version.v2 / 100.0f;
        float _ver3 = (float)(ptr->sys.version.v3 >> 16) / 100.0f;
        char _ver3_type = (char)ptr->sys.version.v3 + 97;
        uint8_t _ver3_minor = ptr->sys.version.v3 >> 8;
        float _rps = (float)ptr->sys.mot.rpm / 60.0f;

        std::string _mode = "", _format = "", _rep = "";
        if((ptr->sys.state & 0xff) == 3)
            _mode += "Normal mode";
        else if((ptr->sys.state & 0xff) == 4)
            _mode += "Fast mode";
        else
            _mode += "Test mode";

        if(!ptr->sys.datFormat)
            _format = "1ECHO";
        else
            _format = "2ECHO";
		
		if(ptr->sys.version.v1 % 100 == 3)
			_rep = "21.6kHz";
		else if(ptr->sys.version.v1 % 100 == 1)
			_rep = "10.8kHz";		
		else if(ptr->sys.version.v1 % 100 == 2)
			_rep = "5.4kHz";
		
		std::string strUID = "UID: " + _uid;
		std::string strVer = "Version: " + to_string_with_precision(_ver3) + 
										_ver3_type + 
										std::to_string(_ver3_minor) + "_" + \
										to_string_with_precision(_ver2) + "_" + \
										to_string_with_precision(_ver1);
										
		std::string strBuildNo = "Build No. " + to_string_with_setfill(ptr->sys.date.year) + \
												to_string_with_setfill(ptr->sys.date.month) + \
												to_string_with_setfill(ptr->sys.date.day);

		std::string strMode = "Working State: " + _mode + ", " + _format + ", " + _rep;
		std::string strRPS = "Scanning Frequency: " + to_string_with_precision(_rps);
		
		
		long nowTime = this->GetNowTime();
		lidar_MsgQueue.push(std::pair<long, std::string>(nowTime, "-------------|LIDAR ATTRIBUTE|-------------"));
		lidar_MsgQueue.push(std::pair<long, std::string>(nowTime, strUID.c_str()));
		lidar_MsgQueue.push(std::pair<long, std::string>(nowTime, strVer.c_str()));
		lidar_MsgQueue.push(std::pair<long, std::string>(nowTime, strBuildNo.c_str()));
		lidar_MsgQueue.push(std::pair<long, std::string>(nowTime, strMode.c_str()));
		lidar_MsgQueue.push(std::pair<long, std::string>(nowTime, strRPS.c_str()));
		lidar_MsgQueue.push(std::pair<long, std::string>(nowTime, "-------------|LIDAR ATTRIBUTE|-------------"));
	}
	
    std::string LiPkt::to_string_with_precision(const float f, const int n)
    {
        std::ostringstream out;
        out.precision(n);
        out << std::fixed << f;
        return std::move(out).str();
    }

    std::string LiPkt::to_string_with_setfill(const int i, const int n)
    {
        std::stringstream ss;
        ss << std::setw(n) << std::setfill('0') << i;
        std::string str;
        ss >> str;
        return str;
    }
	
}