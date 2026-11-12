#ifndef __dvbci_dvbci_datetimemgr_h
#define __dvbci_dvbci_datetimemgr_h

#include <lib/base/ebase.h>
#include <lib/dvb_ci/dvbci_session.h>

class eDVBCIDateTimeSession: public eDVBCISession, public sigc::trackable
{
	enum {
		stateFinal=statePrivate, stateSendDateTime
	};
	/* HD Satelit: ora adevarata (hdsdatetimeci.h), trimisa din nou la intervalul cerut de modul */
	ePtr<eTimer> m_timer;
	int m_interval;     /* response_interval din date_time_enquiry, in secunde; 0 = o singura data */
	int m_waitClock;    /* secundele asteptate pana se pune ceasul */
	bool m_logNext;     /* scriem in jurnal numai raspunsul la cerere, nu fiecare trimitere periodica */
	void sendDateTime();
	void timeout();
	int receivedAPDU(const unsigned char *tag, const void *data, int len);
	int doAction();
public:
	eDVBCIDateTimeSession();
	~eDVBCIDateTimeSession();
};

#endif
