/* Din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4, lib/dvb_ci/dvbci_cam_upgrade.cpp;
   licenta GPLv2 a enigma2. Modificat de moneasoftware.com si hdsatelit.com, 2026: numai legarea de slotul si
   jurnalul nostru (dvbci_hds_compat.h). */
#include <lib/dvb_ci/dvbci_hds_compat.h>
/* DVB CI CAM Firmware Upgrade Manager */

#include <lib/base/eerror.h>
#include <lib/dvb_ci/dvbci_cam_upgrade.h>

int eDVBCICAMUpgradeSession::receivedAPDU(const unsigned char *tag,const void *data, int len)
{
	eTraceNoNewLine("[CI%d CAMUP] SESSION(%d)/CAMUP %02x %02x %02x: ", slot->getSlotID(), session_nb, tag[0], tag[1], tag[2]);
	for (int i=0; i<len; i++)
		eTraceNoNewLine("%02x ", ((const unsigned char*)data)[i]);
	eTraceNoNewLine("\n");
	if ((tag[0]==0x9f) && (tag[1]==0x9d))
	{
		switch (tag[2])
		{
		default:
			eWarning("[CI%d CAMUP] unknown APDU tag 9F 9D %02x", slot->getSlotID(), tag[2]);
			break;
		}
	}

	return 0;
}

int eDVBCICAMUpgradeSession::doAction()
{
	switch (state)
	{
	default:
		eWarning("[CI%d CAMUP] unknown state", slot->getSlotID());
		break;
	}

	return 0;
}
