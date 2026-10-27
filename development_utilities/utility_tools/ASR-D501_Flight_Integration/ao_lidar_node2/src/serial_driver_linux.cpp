// Custom headers
#include <serial_driver_linux.h>

namespace aolidar 
{
    SerialDriverLinux::SerialDriverLinux() 
        : recv_callback(nullptr)
        , recv_thread(nullptr) 
    {
        hdl = -1;
        baud = 0;
    }

    SerialDriverLinux::~SerialDriverLinux() { Close(); }

    bool SerialDriverLinux::Open(std::string &port_name, uint32_t baudrate) 
    {
        const uint32_t buf_size = 384;
        this->baud = baudrate;
        if(!Port_Open(port_name)) {
            return false;
        }

        if(!Port_Config(baudrate)) {
            return false; 
        }
		
        is_recv_thread_exit = false;
        recv_thread = new std::thread(&SerialDriverLinux::RecvThreadProc, this, buf_size);
        return true;
    }

    bool SerialDriverLinux::Close()
    {
        is_recv_thread_exit = true;

        if(hdl != -1) {
            close(hdl);
            hdl = -1;
        }

        if((recv_thread != nullptr) && recv_thread->joinable()) {
            recv_thread->join();
            delete recv_thread;
            recv_thread = nullptr;
        }
        is_opened = false;
        return true;
    }

    bool SerialDriverLinux::Read(uint8_t *buf, uint32_t buf_len, uint32_t *rx_len)
    {
        static timespec timeout = {0, (long)(50 * 1e6)}; // 0s50ms
        int32_t len = -1;

        if(IsOpened()) {
            fd_set rd_fds;
            FD_ZERO(&rd_fds);
            FD_SET(hdl, &rd_fds);
            int r = pselect(hdl+1, &rd_fds, NULL, NULL, &timeout, NULL);

            if(r != 1) return false;
            if (FD_ISSET(hdl, &rd_fds)) {
                len = Port_Read(buf, buf_len);
                if(len != -1) {
                    *rx_len = len;
                }
            }
        }
        return len != -1 ? true : false;
    }

    bool SerialDriverLinux::Port_Open(std::string &port_name)
    {
        hdl = open(port_name.c_str(), (O_RDWR | O_NOCTTY | O_NDELAY | O_NONBLOCK));
        if(hdl == -1) {
			fflush(stdout);
		    return false;
	    }
        is_opened = true;
	    return true;
    }

    bool SerialDriverLinux::Port_Config(uint32_t baudrate)
    {
        struct termios2 tio;

        if(ioctl(hdl, TCGETS2, &tio) == -1) {
            close(hdl);
            hdl = -1;
            return false;
        }

        /**
         * Set the serial port
         */
        tio.c_iflag &= ~(IGNBRK|BRKINT|PARMRK|INPCK|ISTRIP|INLCR|IGNCR|ICRNL|IXON|IXOFF|IXANY); 
        tio.c_iflag |= IGNPAR;
        tio.c_cflag &= ~(CBAUD | CSIZE);

        //Set 8N1, 8bits, no parity, 1 stop_bit
        tio.c_cflag &= ~PARENB;
        tio.c_cflag &= ~CSTOPB;
        tio.c_cflag |= CS8;
        tio.c_cflag &= ~CRTSCTS;
        tio.c_cflag |= (CREAD | CLOCAL); 

	    tio.c_lflag &= ~(ICANON|ECHO|ECHOE|ISIG);

        tio.c_oflag &= ~OPOST;
	    tio.c_oflag &= ~ONLCR;

        tio.c_cflag |= BOTHER;
        tio.c_ispeed = this->baud;
        tio.c_ospeed = this->baud;
		tio.c_cc[VEOF] = 4;
        tio.c_cc[VMIN] = 1;
        tio.c_cc[VTIME] = 2;

	    ioctl(hdl, TCFLSH, 2); 

        if(ioctl(hdl, TCSETS2, &tio) == -1) {
            close(hdl);
            hdl = -1;
            return false;
        }
        return true;        
    }

    int32_t SerialDriverLinux::Port_Read(uint8_t *msg, uint32_t len) 
    {
        return read(hdl, msg, len);
    }

    int32_t SerialDriverLinux::Port_Write(uint8_t *msg, uint32_t len) 
    {
        return write(hdl, msg, len);
    }

    void SerialDriverLinux::RecvThreadProc(void *pdriver, uint32_t buf_len)
    {
        SerialDriverLinux *dev = (SerialDriverLinux *)pdriver;
        char *buf = new char[buf_len];
        while(!dev->is_recv_thread_exit.load()) {
            uint32_t rd_len = 0;
            bool res = dev->Read((uint8_t *)buf, buf_len, &rd_len);
            if(res && rd_len) {
                if(dev->recv_callback != nullptr) {
                    dev->recv_callback(buf, rd_len);
                }
            }
        }
        delete [] buf;
    }
} // namespace aolidar
