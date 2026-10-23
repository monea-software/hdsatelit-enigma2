/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __servicedvbrecord_h
#define __servicedvbrecord_h

#include <lib/service/iservice.h>
#include <lib/dvb/idvb.h>

#include <lib/dvb/pmt.h>
#include <lib/dvb/eit.h>
#include <set>

#include <lib/service/servicedvb.h>

class eDVBServiceRecord: public eDVBServiceBase,
	public iRecordableService, 
	public iStreamableService,
	public iSubserviceList,
	public sigc::trackable
{
	DECLARE_REF(eDVBServiceRecord);
public:
	RESULT connectEvent(const sigc::slot<void(iRecordableService*, int)> &event, ePtr<eConnection> &connection);
	RESULT prepare(const char *filename, time_t begTime, time_t endTime, int eit_event_id, const char *name, const char *descr, const char *tags);
	RESULT prepareStreaming();
	RESULT start(bool simulate=false);
	RESULT stop();
	RESULT stream(ePtr<iStreamableService> &ptr);
	RESULT getError(int &error) { error = m_error; return 0; }
	RESULT frontendInfo(ePtr<iFrontendInformation> &ptr);
	RESULT subServices(ePtr<iSubserviceList> &ptr);
	RESULT setYieldsToZap(bool yields);
	RESULT setDecodareMaiTarziu(bool on, bool pe_televizor);

		// iStreamableService
	PyObject *getStreamingData();

		// iSubserviceList
	int getNumberOfSubservices();
	RESULT getSubservice(eServiceReference &subservice, unsigned int n);
private:
	enum { stateIdle, statePrepared, stateRecording };
	bool m_simulate;
	int m_state, m_want_record;
	friend class eServiceFactoryDVB;
	eDVBServiceRecord(const eServiceReferenceDVB &ref);
	
	eDVBServiceEITHandler m_event_handler;
	
	eServiceReferenceDVB m_ref;
	
	ePtr<iDVBTSRecorder> m_record;
	ePtr<eConnection> m_con_record_event;
	
	int m_recording, m_tuned, m_error;
	std::set<int> m_pids_active;
	std::string m_filename;

	std::map<int,pts_t> m_event_timestamps;
	int m_target_fd;
	int m_streaming;
	int m_last_event_id;
	
	int doPrepare();
	int doRecord();

		/* "decodeaza mai tarziu" (setDecodareMaiTarziu): semnul, serviciul era pe televizor la pornire si ce s-a scris
		   ultima data in <fisier>.hdsdecodare (se rescrie numai cand se schimba) */
	bool m_decodare_mai_tarziu;
	bool m_decodare_pe_televizor;
	std::string m_decodare_scris;
	void scrieDecodare(const eDVBServicePMTHandler::program &program, const std::set<int> &pids);

			/* events */
	void serviceEvent(int event);
	sigc::signal<void(iRecordableService*, int)> m_event;
	
			/* recorder events */
	void recordEvent(int event);

			/* eit updates */
	void gotNewEvent();
	void saveCutlist();
};

#endif
