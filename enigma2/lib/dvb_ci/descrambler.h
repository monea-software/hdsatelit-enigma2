/* Din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4, lib/dvb_ci/descrambler.h;
   licenta GPLv2 a enigma2. Modificat de moneasoftware.com si hdsatelit.com, 2026: numai legarea de slotul si
   jurnalul nostru (dvbci_hds_compat.h). */
#ifndef __DESCR_H_
#define __DESCR_H_

#include <linux/dvb/ca.h>
#include <lib/dvb_ci/dvbci.h>

/**
 * CA_SET_PID and ca_pid struct removed on 4.14 kernel
 * Check commit         833ff5e7feda1a042b83e82208cef3d212ca0ef1
 **/
#ifndef CA_SET_PID
struct ca_pid
{
	unsigned int pid;
	int index; /* -1 == disable*/
};
#define CA_SET_PID _IOW('o', 135, struct ca_pid)
#endif

int descrambler_init(eDVBCISlot *slot, uint8_t ca_demux_id);
void descrambler_deinit(int desc_fd);
int descrambler_set_key(int &desc_fd, eDVBCISlot *slot, int parity, unsigned char *data);
int descrambler_set_pid(int desc_fd, eDVBCISlot *slot, int enable, int pid);

#endif
