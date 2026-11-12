/* Din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4, lib/dvb_ci/dvbci_hlcmgr.h;
   licenta GPLv2 a enigma2. Modificat de moneasoftware.com si hdsatelit.com, 2026: numai legarea de slotul si
   jurnalul nostru (dvbci_hds_compat.h). */
#ifndef __dvbci_dvbci_hlcmgr_h
#define __dvbci_dvbci_hlcmgr_h

#include <lib/dvb_ci/dvbci_session.h>

class eDVBCIHostLanguageAndCountrySession: public eDVBCISession
{
	enum {
		stateCountryEnquiry=statePrivate,
		stateLanguageEnquiry,
		stateFinal
	};

	static const std::map<std::string, std::string> m_languageMap;
	static std::map<std::string, std::string> createLanguageMap();

	int receivedAPDU(const unsigned char *tag, const void *data, int len);
	int doAction();
};

#endif
