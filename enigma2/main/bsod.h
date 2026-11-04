#ifndef __main_bsod_h
#define __main_bsod_h

#include <string>

void bsodLogInit();
void bsodCatchSignals();
void bsodFatal(const char *component);
/* HDSatelit: the last 16 KiB of the log (the ring buffer of the crash log), for the report of an external plugin */
std::string bsodLogBuffer();

#endif
