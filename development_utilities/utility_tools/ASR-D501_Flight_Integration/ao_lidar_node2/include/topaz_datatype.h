#ifndef __TOPAZ_DATATYPE_H
#define __TOPAZ_DATATYPE_H

// C library headers
#include <stdint.h>

namespace aolidar
{
	enum {
		RANGE_PACKET_HEADER = 0x05fa,
		ERROR_PACKET_HEADER = 0xeefa,
		ACK_PACKET_HEADER = 0xacca,
		ATTRIBUTE_PACKET_HEADER = 0x4bb4,
		POINTS_PER_RANGE_PACKET = 24,
		POINTS_PER_RANGE_PACKET_SIMP=32
	};
	
    typedef enum {
        UNDEFINED = 0,
        STARTUP_FAILURE = 0xe0,
        INTERNAL_COMMUNICATION_FAILURE = 0xe1,
        ANTI_CLOCKWISE = 0xe5,
        PACKET_LOSS = 0xe6,
        PARITY_ERROR = 0xe7,
        FRAMING_ERROR = 0xe8,
        NOISE_ERROR = 0xe9,
        OVERRUN_ERROR = 0xea,
        SENSOR_FAILURE = 0xeb
    }ERROR_CODE;

    #pragma pack(1)
    // MEASURING DATA PACKET-----------------------------------------------------------------
    typedef struct
    {
        uint16_t distance;
        uint16_t energy;
    }LidarPointTypeDef;

    typedef struct
    {
        uint16_t header;
        uint16_t angle;
        uint16_t speed;
        LidarPointTypeDef pts[24];
        uint16_t checkSum;
    }LidarDataTypeDef;
	
	// MEASURING DATA PACKET SIMP-----------------------------------------------------------------
    typedef struct
    {
        uint16_t dist;
        uint8_t engy;
    }LidarPointSimpTypeDef;

    typedef struct
    {
        uint16_t header;
        uint16_t angle;
        uint16_t speed;
        LidarPointSimpTypeDef pts[32];
        uint16_t checkSum;
    }LidarDataSimpTypeDef;	

    // ACKNOWLEDGEMENT PACKET----------------------------------------------------------------
    typedef struct
    {
        uint16_t header;
        uint16_t ack;
        uint8_t reserved[2];
        uint8_t xor_;
    }LidarAckTypeDef;

    // EEROR MESSAGE PACKET------------------------------------------------------------------
    typedef struct
    {
        uint16_t header;
        uint16_t errCode;
        uint16_t msg_size;
        uint8_t msg[96];
        uint16_t crc16;
    }LidarErrorTypeDef;

    // ATTRIBUTE PACKET ---------------------------------------------------------------------
    typedef struct
    {
        uint8_t len;
        uint8_t name[32];
    }UidTypeDef;

    typedef struct
    {
        uint16_t year;
        uint8_t month;
        uint8_t day;
    }DateTypeDef;

    typedef struct
    {
        uint8_t dir;
        uint16_t rpm;
    }MotorTypeDef;

    typedef struct
    {
        uint16_t v1;
        uint16_t v2;
        uint32_t v3;
    }LidarVersionTypeDef;

    typedef struct
    {
        uint16_t size;
        UidTypeDef uid;
        LidarVersionTypeDef version;
        DateTypeDef date;
        float opt;
        float plane;
        uint16_t angOffset;
        uint16_t state;
        uint8_t pktFormat;
        uint8_t datFormat;
        MotorTypeDef mot;
        uint8_t reserved[64];
    }AttributeTypeDef;

    typedef struct
    {
        uint16_t header1;
        uint16_t header2;
        uint16_t size;
        AttributeTypeDef sys;
        uint16_t tail;
        uint8_t XOR;
    }LidarAttributeTypeDef;

    // COMMAND PACKET -----------------------------------------------------------------------
    typedef struct
    {
        uint16_t pktHeader;
        uint8_t root;
        uint8_t leaf;
        uint8_t size;
        uint8_t xor_;
    }NormalCmdTypeDef;

    typedef struct
    {
        uint16_t pktHeader;
        uint16_t fmHeader;
        uint16_t size;
        uint16_t rpm;
        uint16_t tail;
        uint8_t xor_;
    }ParamCmdTypeDef;

    #pragma pack()
}

#endif // __TOPAZ_DATATYPE_H