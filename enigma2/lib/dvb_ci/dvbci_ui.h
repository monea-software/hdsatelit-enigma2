/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __dvbci_ui_h
#define __dvbci_ui_h

#include <string>
#include <lib/mmi/mmi_ui.h>
#include <lib/python/connections.h>

class eDVBCI_UI: public eMMI_UI
{
	static eDVBCI_UI *instance;
#ifdef SWIG
	eDVBCI_UI();
#endif
	void stateChanged(int val) { ciStateChanged(val); }
public:
	enum { rateNormal, rateHigh, rateExtraHigh };
	PSignal1<void,int> ciStateChanged;
#ifndef SWIG
	eDVBCI_UI();
#endif
	static eDVBCI_UI *getInstance();
	void setInit(int slot);
	void setReset(int slot);
	int startMMI(int slot);
	int stopMMI(int slot);
	int getMMIState(int slot);
	int answerMenu(int slot, int answer);
	int answerEnq(int slot, char *val);
	int cancelEnq(int slot);
	int setClockRate(int slot, int rate);
	/* slot pornit/oprit (ca setEnabled din enigma2 OE-Alliance, commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4) */
	int setEnabled(int slot, bool enabled);
	/* CI+ (din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4): managerul de
	   continut spune cand slotul descifreaza; getCIPlusState: 0 = CI simplu, 1 = autentificare CI+, 2 = cheile primite */
	void setDecodingState(int slot, int state);
	int getDecodingState(int slot);
	int getCIPlusState(int slot);
#ifndef SWIG
private:
	int m_decoding[4];
#endif
};

#endif
