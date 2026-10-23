/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __nav_core_h
#define __nav_core_h

#include <lib/base/object.h>
#include <lib/service/iservice.h>
#include <connection.h>
#include <map>
#include <set>

class eNavigation: public iObject, public sigc::trackable
{
	DECLARE_REF(eNavigation);
	ePtr<iServiceHandler> m_servicehandler;

	ePtr<iPlayableService> m_runningService;
	sigc::signal<void(int)> m_event;
	ePtr<eConnection> m_service_event_conn;
	void serviceEvent(iPlayableService* service, int event);

	std::map<ePtr<iRecordableService>, ePtr<eConnection>, std::less<iRecordableService*> > m_recordings;
	std::set<ePtr<iRecordableService>, std::less<iRecordableService*> > m_simulate_recordings;

	sigc::signal<void(ePtr<iRecordableService>, int)> m_record_event;
	void recordEvent(iRecordableService* service, int event);
public:
	
	RESULT playService(const eServiceReference &service);
	RESULT connectEvent(const sigc::slot<void(int)> &event, ePtr<eConnection> &connection);
	RESULT connectRecordEvent(const sigc::slot<void(ePtr<iRecordableService>, int)> &event, ePtr<eConnection> &connection);
/*	int connectServiceEvent(const sigc::slot<void(iPlayableService*, int)> &event, ePtr<eConnection> &connection); */
	RESULT getCurrentService(ePtr<iPlayableService> &service);
	RESULT stopService(void);
	
	RESULT recordService(const eServiceReference &ref, ePtr<iRecordableService> &service, bool simulate=false);
	RESULT stopRecordService(ePtr<iRecordableService> &service);
	PyObject *getRecordings(bool simulate=false);
	
	RESULT pause(int p);
	eNavigation(iServiceHandler *serviceHandler);
	virtual ~eNavigation();
};

#endif
