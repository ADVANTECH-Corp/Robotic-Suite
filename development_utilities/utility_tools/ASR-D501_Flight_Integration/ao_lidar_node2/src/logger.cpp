// Custom headers
#include "logger.h"

LOG* LOG::pLOG = NULL;
std::mutex LOG::glock;

LOG::LOG()
{

}

LOG::~LOG()
{

}

LOG* LOG::GetInstance(LOG::LOG_LEVEL level)
{
    if(pLOG == nullptr) {
        glock.lock();
        pLOG = new LOG();
        glock.unlock();
    }
    pLOG->log_level_ = level;
    return pLOG;
}

void LOG::OutputToConsole(char* format,...) {
    if((int)this->log_level_ < DEFAULT_LOG_LEVEL) return;

    std::string str_temp;
    str_temp += "[" + GetCurrentTime() + "]";
    str_temp += "[" + GetLevelString(this->log_level_) + "] ";

    va_list ap;
    va_start(ap, format);
    char buf[256];
    int ret = vsnprintf(buf, 256, format, ap);

    va_end(ap);
    str_temp.append(buf);
    
    //output to console
    printf("%s\n", str_temp.c_str());
}

void LOG::SetLogLevel(LOG_LEVEL log_level)
{
    this->log_level_ = log_level;
}

void LOG::SetLogTarget(LOG_TARGET log_target)
{
    this->log_target_ = log_target;
}

std::string LOG::GetLevelString(LOG::LOG_LEVEL level) 
{
    std::string str_loglevel = "";
    switch(level) 
    {
        case LOG::LOG_LEVEL::NONE:
            str_loglevel = "NONE";
            break;
        case LOG::LOG_LEVEL::DEBUG:
            str_loglevel = "DEBUG";
            break;
        case LOG::LOG_LEVEL::INFO:
            str_loglevel = "INFO";
            break;
        case LOG::LOG_LEVEL::WARN:
            str_loglevel = "WARN";
            break;
        case LOG::LOG_LEVEL::ERROR:
            str_loglevel = "ERROR";
            break;
    }
    return str_loglevel;
}