#ifndef __CHECKSUM_H
#define __CHECKSUM_H

#include <stdint.h>

namespace aolidar
{
	bool CalCsum_XOR(const uint8_t *arr, uint16_t start, uint16_t end);
	bool CalCsum_CCITT16(const uint8_t *arr, uint16_t length);
}

#endif // __CHECKSUM_H