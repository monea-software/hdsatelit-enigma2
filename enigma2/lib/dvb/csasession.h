/* SoftCSA (software descrambling of CSA-ALT with libdvbcsa). GPL-2.0-only.
 * Authors: WXbet, Betacentauri, 2026.
 * Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __dvbcsasession_h
#define __dvbcsasession_h

#include <lib/service/iservicescrambled.h>
#include <lib/dvb/idvb.h>
#include <lib/dvb/idemux.h>
#include <lib/base/ebase.h>
#include <sigc++/sigc++.h>
#include <functional>

class eDVBCSAEngine;
class eDVBCAHandler;

/**
 * eDVBCSASession - CW-Management per Service with ECM-based CSA-ALT Detection
 *
 * - Receives CWs from softcam via eDVBCAHandler signals
 * - Filters by service reference
 * - Monitors ECM to detect CSA-ALT and ecm_mode
 * - ACTIVATES ITSELF when CSA-ALT is detected from ECM
 * - Delegates descrambling to eDVBCSAEngine
 *
 * The session is created "speculatively" and remains inactive.
 * ECM Monitor analyzes incoming ECMs and activates if CSA-ALT is detected.
 * Detection is fully autonomous - no dependency on external signals.
 *
 * When inactive: descramble() is a passthrough (no changes to data)
 * When active: descramble() delegates to eDVBCSAEngine
 */
class eDVBCSASession : public iServiceScrambled, public sigc::trackable
{
	DECLARE_REF(eDVBCSASession);

public:
	/**
	 * Constructor
	 * @param ref Service reference for CW filtering
	 *
	 * Session starts INACTIVE and activates when CSA-ALT is detected from ECM
	 */
	eDVBCSASession(const eServiceReferenceDVB& ref);
	~eDVBCSASession();

	// Initialization - connects to eDVBCAHandler for CW reception
	bool init();

	// iServiceScrambled Interface
	// Descrambles in-place when active and CW available, otherwise passthrough
	void descramble(unsigned char* packets, int len) override;

	// Status
	bool isActive() const { return m_active; }
	bool hasKeys() const override;
	const eServiceReferenceDVB& getServiceRef() const { return m_service_ref; }

	/**
	 * Start ECM monitoring to detect ecm_mode and CSA-ALT
	 * @param demux Demux to use for filtering
	 * @param ecm_pid ECM PID from PMT
	 * @param caid CA System ID for CSA-ALT detection
	 *
	 * Reads ecm[len-1] and extracts lower nibble for ecm_mode.
	 * Also detects CSA-ALT from ECM using softcam's select_csa_alt() logic:
	 * - CAID is VideoGuard (0x09xx)
	 * - ecm[4] != 0
	 * - (ecm[2] - ecm[4]) == 4
	 */
	void startECMMonitor(iDVBDemux *demux, uint16_t ecm_pid, uint16_t caid);
	void stopECMMonitor();

	uint8_t getEcmMode() const { return m_ecm_mode; }
	bool isEcmModeDetected() const { return m_ecm_mode_detected; }
	bool isEcmAnalyzed() const { return m_ecm_analyzed; }  // true once ECM was analyzed
	bool isCsaAlt() const { return m_csa_alt; }            // true if CSA-ALT was detected

	// Cached CSA-ALT state of a service: -1 = unknown, 0 = no, 1 = CSA-ALT
	static int cachedCsaAlt(const eServiceReferenceDVB& ref);

	// HDSatelit (0.7.4): the cache-hit activation of startECMMonitor, before the PMT (no ECM PID yet), for a service
	// whose CSA-ALT state and ecm_mode came from a real ECM: ecm_mode preloaded, ECM marked analyzed, activation unless
	// shouldSuppressActivation (CI module). True when the session is active.
	bool activateFromCache();
	// HDSatelit (0.7.4): active since activateFromCache (no ECM of this zap seen); the PMT checks it (servicedvb.cpp)
	bool activatedFromCache() const { return m_active && m_activated_from_cache; }
	// HDSatelit (0.7.4): the wait of the engine for a late key (eDVBCSAEngine::releaseHolds): ended before the loop stops,
	// allowed again after it starts
	void releaseHolds();
	void armHolds();

	// HDSatelit: sessions active now (main loop only), for hdsSoftCsaStare()
	static int activeCount() { return s_active_count; }

	/**
	 * Force activation for recording sessions
	 * Recording sessions don't do ECM analysis - they trust that
	 * Live-TV has already detected CSA-ALT for this channel
	 */
	void forceActivate() { setActive(true); }

	/**
	 * Force deactivation for FCC mode switching
	 * When FCC goes back to prepare mode, we need to deactivate
	 * the session but keep it around for the next switch
	 */
	void forceDeactivate() { setActive(false); }

	// Signal when session is activated (for Live-TV decoder setup)
	sigc::signal<void(bool)> activated;  // true=activated, false=deactivated

	// Signal when first CW is received (for decoder start timing)
	sigc::signal<void()> firstCwReceived;

	// Optional callback to check if activation should be suppressed
	// (e.g. CI module handles decryption). Return true to suppress.
	std::function<bool()> shouldSuppressActivation;

private:
	eServiceReferenceDVB m_service_ref;
	ePtr<eDVBCSAEngine> m_engine;

	// Activation status
	bool m_active;      // true when CSA-ALT detected from ECM

	// ECM monitoring for ecm_mode and CSA-ALT detection
	ePtr<iDVBSectionReader> m_ecm_reader;
	ePtr<eConnection> m_ecm_conn;
	uint16_t m_ecm_pid;
	uint16_t m_caid;              // CA System ID for CSA-ALT detection
	uint8_t m_ecm_mode;           // Detected ecm_mode
	uint8_t m_ecm_tail[4];        // Last 4 bytes of ECM for debugging
	bool m_ecm_mode_detected;     // true once first ECM was received
	bool m_ecm_analyzed;          // true once CSA-ALT check was performed
	bool m_csa_alt;               // true if CSA-ALT was detected
	bool m_activated_from_cache;  // HDSatelit: activated by activateFromCache
	void ecmDataReceived(const uint8_t *data);

	// CW Handler (called from eDVBCAHandler signal)
	void onCwReceived(eServiceReferenceDVB ref, int parity, const char* cw, uint16_t caid, uint32_t serviceId);

	// Helper
	bool matchesService(const eServiceReferenceDVB& ref) const;
	void setActive(bool active);

	// eDVBCWHandler registration
	uint32_t m_cw_service_id;       // Softcam's serviceId (set on first CW or pre-registered)
	uint32_t m_cw_alt_service_id;   // Additional serviceId from different namespace variant (0 = none)
	bool m_cw_handler_registered;   // true once registered with eDVBCWHandler
	bool m_first_cw_signaled;       // true once firstCwReceived signal was emitted

	// CW buffer for CWs arriving before activation
	// When a CW arrives while m_active is false, we store it here.
	// On setActive(true), the buffered CW is replayed immediately,
	// avoiding a multi-second wait for the next CW cycle.
	struct PendingCw {
		int parity;
		char cw[8];
		uint16_t caid;
		uint32_t serviceId;
		bool valid;
	};
	PendingCw m_pending_cw;

	static int s_active_count;
};

#endif // __dvbcsasession_h
