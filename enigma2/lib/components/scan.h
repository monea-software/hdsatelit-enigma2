/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __lib_components_scan_h
#define __lib_components_scan_h

#include <lib/base/object.h>
#include <lib/dvb/idvb.h>

class eDVBScan;

class eComponentScan: public sigc::trackable, public iObject
{
	DECLARE_REF(eComponentScan);
#ifndef SWIG
	void scanEvent(int event);
	ePtr<eConnection> m_scan_event_connection;
	ePtr<eDVBScan> m_scan;
	
	int m_done, m_failed;
	eSmartPtrList<iDVBFrontendParameters> m_initial;
#endif
public:
	eComponentScan();
	~eComponentScan();
	
	PSignal0<void> statusChanged;
	PSignal0<void> newService;
	
		/* progress between 0 and 100 */
	int getProgress();
	
		/* get number of services */
	int getNumServices();
	
		/* true when done or error */
	int isDone();
	
		/* get last added service */
	void getLastServiceName(std::string &SWIG_OUTPUT);
	
	int getError();

		/* HDSatelit: counters for the scan screen (time left, "12 of 89", final summary) */
		/* transponders finished (scanned + without signal) */
	int getTranspondersDone();
		/* finished + still to scan; grows when a NIT brings new transponders */
	int getTranspondersTotal();
		/* transponders without signal (tuning failed) */
	int getTranspondersUnavailable();
		/* DVB service type of the last added service, -1 when none */
	int getLastServiceType();
		/* services that were not in the channel list before this scan; -1 until the scan has finished */
	int getNewServices();
		/* every service read in this scan, old and new, and every transponder tried (lib/dvb/scan.h);
		   read only, empty lists before start */
	PyObject *getFoundServices();
	PyObject *getScannedTransponders();
		/* every network whose NIT the scan read (network id and name, announced transponders, logical channel
		   numbers; lib/dvb/scan.h), read only, empty list before start */
	PyObject *getNetworks();

	void clear();
	void addInitial(const eDVBFrontendParametersSatellite &p);
	void addInitial(const eDVBFrontendParametersCable &p);
	void addInitial(const eDVBFrontendParametersTerrestrial &p);
	
		/* please keep the flags in sync with lib/dvb/scan.h ! */
	enum { scanNetworkSearch=1, scanRemoveServices=4, scanDontRemoveFeeds=8, scanDontRemoveUnscanned=16, clearToScanOnFirstNIT = 32, scanOnlyFree = 64,
		/* HDSatelit: NIT citit numai pentru informatie (cablu pe o frecventa), lib/dvb/scan.h */
		hdsNitInformativ = 128 };

	int start(int feid, int flags=0 );
	SWIG_VOID(RESULT) getFrontend(ePtr<iDVBFrontend> &SWIG_OUTPUT);
	SWIG_VOID(RESULT) getCurrentTransponder(ePtr<iDVBFrontendParameters> &SWIG_OUTPUT);
};

#endif
