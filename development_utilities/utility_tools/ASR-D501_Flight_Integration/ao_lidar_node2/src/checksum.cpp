// Custom headers
#include <checksum.h>

namespace aolidar
{
	static const uint16_t POLY16 = 0x1021;
	static const uint16_t CRC_SEED = 0xffff;
	
	bool CalCsum_XOR(const uint8_t *arr, uint16_t start, uint16_t end)
	{
		int size = sizeof(arr) / sizeof(arr[0]);
		uint16_t rdcsum, csum = 0;
		for(int i=start; i<=end; i++) {
			csum ^= arr[i];
		}
		rdcsum = arr[size-1];
		return csum == rdcsum;				
	}
	
	bool CalCsum_CCITT16(const uint8_t *arr, uint16_t length)
	{
		uint16_t rdcsum, csum = CRC_SEED;
		for(int i=0; i<length-2; i++) {
			uint8_t val = arr[i];
			csum = (uint16_t)(csum ^ (val << 8));
			for(int j=0; j<8; j++) {
				if((csum & 0x8000) != 0)
					csum = (uint16_t)((csum << 1) ^ POLY16);
				else
					csum = (uint16_t)(csum << 1);
			}
		}
		rdcsum = (uint16_t)(arr[length-2] | (arr[length-1] << 8));
		return csum == rdcsum;				
	}	
}