/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
/* DVB CI DateTime Manager */

#include <time.h>
#include <lib/base/eerror.h>
#include <lib/base/hdsjurnal.h>
#include <lib/dvb/dvbtime.h>
#include <lib/dvb_ci/dvbci_datetimemgr.h>
#include <lib/dvb_ci/hdsdatetimeci.h>

eDVBCIDateTimeSession::eDVBCIDateTimeSession()
	:m_timer(eTimer::create(eApp)), m_interval(0), m_waitClock(0), m_logNext(false)
{
	CONNECT(m_timer->timeout, eDVBCIDateTimeSession::timeout);
}

eDVBCIDateTimeSession::~eDVBCIDateTimeSession()
{
	m_timer->stop();
}

int eDVBCIDateTimeSession::receivedAPDU(const unsigned char *tag,const void *data, int len)
{
	eDebugNoNewLine("SESSION(%d)/DATETIME %02x %02x %02x: ", session_nb, tag[0],tag[1], tag[2]);
	for (int i=0; i<len; i++)
		eDebugNoNewLine("%02x ", ((const unsigned char*)data)[i]);
	eDebug("%s", "");

	if ((tag[0]==0x9f) && (tag[1]==0x84))
	{
		switch (tag[2])
		{
		case 0x40: // date_time_enquiry: response_interval (secunde, 0 = o data)
			m_interval = (len >= 1) ? ((const unsigned char*)data)[0] : 0;
			m_waitClock = 0;
			m_logNext = true;
			m_timer->stop();
			state=stateSendDateTime;
			return 1;
			break;
		default:
			eDebug("unknown APDU tag 9F 84 %02x", tag[2]);
			break;
		}
	}
	return 0;
}

/* Trimite date_time_response cu ora adevarata (UTC si diferenta fata de UTC). Cat timp ceasul nu e pus (receptorul
   abia pornit, inca fara ora din satelit sau din retea), asteapta cate o secunda, cel mult ASTEPTARE_CEAS_MAX, apoi
   raspunde cu ce are. Daca modulul a cerut un interval, trimite din nou la fiecare interval. */
void eDVBCIDateTimeSession::sendDateTime()
{
	time_t now = time(NULL);
	eDVBLocalTimeHandler *handler = eDVBLocalTimeHandler::getInstance();
	bool ready = hdsci::ceasPus((long long)now) && (!handler || handler->ready());
	if (!ready && m_waitClock < hdsci::ASTEPTARE_CEAS_MAX)
	{
		++m_waitClock;
		m_timer->start(1000, true);
		return;
	}

	struct tm local;
	int offset = 0;
	if (localtime_r(&now, &local))
		offset = (int)(local.tm_gmtoff / 60);

	unsigned char tag[3]={0x9f, 0x84, 0x41}; // date_time_response
	unsigned char msg[7];
	int len = hdsci::codeazaDataOra((long long)now, offset, msg);
	sendAPDU(tag, msg, len);

	if (m_logNext)
	{
		struct tm utc;
		gmtime_r(&now, &utc);
		eDebug("[CI DateTime] %04d-%02d-%02d %02d:%02d:%02d UTC, offset %+d min, interval %d s",
			utc.tm_year + 1900, utc.tm_mon + 1, utc.tm_mday, utc.tm_hour, utc.tm_min, utc.tm_sec, offset, m_interval);
		hdsjurnal::scrief("ci", hdsjurnal::INFO, "ora",
			"CI ora trimisa modulului: %04d-%02d-%02d %02d:%02d:%02d UTC, diferenta %+d min, interval %d s%s",
			utc.tm_year + 1900, utc.tm_mon + 1, utc.tm_mday, utc.tm_hour, utc.tm_min, utc.tm_sec, offset, m_interval,
			ready ? "" : " (ceasul inca nepus)");
		m_logNext = false;
	}

	if (m_interval > 0)
		m_timer->start(m_interval * 1000, true);
}

void eDVBCIDateTimeSession::timeout()
{
	if (state == stateInDeletion || state == stateFinal)
		return;
	sendDateTime();
}

int eDVBCIDateTimeSession::doAction()
{
	switch (state)
	{
	case stateStarted:
		return 0;
	case stateSendDateTime:
		sendDateTime();
		return 0;
	case stateFinal:
		eDebug("stateFinal und action! kann doch garnicht sein ;)");
	default:
		return 0;
	}
}
