#ifndef __LOGGER_H
#define __LOGGER_H

// C library headers
#include <stdarg.h>

// C++ library headers
#include <iostream>
#include <mutex>
#include <ctime>

#define ENABLE_LOG
#define DEFAULT_LOG_LEVEL	2

class LOG
{
    std::ostream* out_;
    
    public:
        enum class LOG_LEVEL {
            NONE,
            DEBUG,
            INFO,
            WARN,
            ERROR
        };

        enum class LOG_TARGET {
            NONE,
            CONSOLE,
            FILE
        };

    public:
        static LOG* GetInstance(LOG::LOG_LEVEL level);

        void OutputToConsole(char* format,...);

        void show_display() {
            out_ = &std::cout;
        }

        void hide_display() {
            out_ = nullptr;
        }

    private:
        LOG();
        
        ~LOG();

        void SetLogLevel(LOG_LEVEL log_level);

        LOG_LEVEL GetLogLevelValue(void) { return log_level_;};

        void SetLogTarget(LOG_TARGET log_target);
        
        LOG_TARGET GetLogTargetValue(void) { return log_target_;};

        std::string GetCurrentTime(void) {
            time_t rawtime;
            struct tm * timeinfo;
            char buf[80];

            time(&rawtime);
            timeinfo = localtime(&rawtime);

            strftime(buf, sizeof(buf), "%d-%m-%Y %H:%M:%S", timeinfo);
            std::string str(buf);
            return str;
        }

        inline uint64_t GetCurrentTimeStamp(void) {
            auto now = std::chrono::system_clock::now();
            auto now_ms = std::chrono::time_point_cast<std::chrono::milliseconds>(now);
            auto value = now_ms.time_since_epoch();
            return value.count();
        }

        std::string GetLevelString(LOG::LOG_LEVEL level);

        static LOG* pLOG;
        static std::mutex glock;
        static std::string out_buffer;

        LOG_LEVEL log_level_;
        LOG_TARGET log_target_;

};

//define DEBUG(format,...) printf("File: " __FILE__ ", Line: %05d: " format "\n", __LINE__, ##__VA_ARGS__)
#define DEBUG_PRINTF(level, format, ...)  LOG::GetInstance(level)->OutputToConsole(format, ## __VA_ARGS__);
#ifdef ENABLE_LOG
#define LOG_DEBUG(format,...)    DEBUG_PRINTF(LOG::LOG_LEVEL::DEBUG, format, ## __VA_ARGS__)
#define LOG_INFO(format,...)     DEBUG_PRINTF(LOG::LOG_LEVEL::INFO, format, ## __VA_ARGS__)
#define LOG_WARN(format,...)     DEBUG_PRINTF(LOG::LOG_LEVEL::WARN, format, ## __VA_ARGS__)
#define LOG_ERROR(format,...)    DEBUG_PRINTF(LOG::LOG_LEVEL::ERROR, format, ## __VA_ARGS__)
#else
#define LOG_DEBUG(format,...)    do {} while(0)
#define LOG_INFO(format,...)     do {} while(0)
#define LOG_WARN(format,...)     do {} while(0)
#define LOG_ERROR(format,...)    do {} while(0)
#endif

#endif //__LOGGER_H