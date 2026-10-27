#ifndef __SERIAL_DRIVER_LINUX_H
#define __SERIAL_DRIVER_LINUX_H

// C library headers
#include <stdio.h>
#include <string.h>

// C++ library headers
#include <iostream>
#include <chrono>
#include <atomic>
#include <thread>
#include <functional>

// Linux headers
#include <time.h>
#include <fcntl.h>
#include <errno.h>
#include <unistd.h>
#include <sys/ioctl.h> 
//#include <termios.h> // Contains POSIX terminal control definitions
#include <asm/termbits.h>

namespace aolidar 
{
    class SerialDriverLinux 
    {
        public:
          SerialDriverLinux();
          ~SerialDriverLinux();

          bool Open(std::string &port_name, uint32_t baudrate);
          bool Close(void);
          bool Read(uint8_t *rx_buf, uint32_t rx_buf_len, uint32_t *act_rx_len);
          bool Write(uint8_t *tx_buf, uint32_t tx_buf_len, uint32_t *act_tx_len);
          void SetRecvCallback(std::function<void(const char *, size_t)> callback) {
            recv_callback = callback;
          };
          bool IsOpened(void) { return is_opened.load(); };

        private:
          int32_t hdl;
          uint32_t baud;
          std::function<void(const char *, size_t)> recv_callback;
          std::atomic<bool> is_opened, is_recv_thread_exit;
          std::thread *recv_thread;

          static void RecvThreadProc(void *pdriver, uint32_t buf_len);

          bool Port_Open(std::string &port_name);
          bool Port_Config(uint32_t baudrate);
          int32_t Port_Read(uint8_t *msg, uint32_t len);
          int32_t Port_Write(uint8_t *msg, uint32_t len);
    };
} // namespace aolidar

#endif // __SERIAL_DRIVER_LINUX_H