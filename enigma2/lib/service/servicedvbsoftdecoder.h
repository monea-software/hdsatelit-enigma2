/* SoftCSA: the loop that feeds the hardware decoder with the stream descrambled in software. GPL-2.0-only.
 * Authors: WXbet, Betacentauri, 2026.
 * Modificat de moneasoftware.com si hdsatelit.com, 2026: only the loop (recorder, descrambler, dvr of a playback demux,
 * the health check of the stream and the restart of the writer); the decoder itself is made by eDVBServicePlay from the
 * playback demux of the loop, so audio tracks, subtitles, teletext, video information and pause stay on its own code. */
#ifndef __dvbsoftdecoder_h
#define __dvbsoftdecoder_h

#include <lib/base/object.h>
#include <lib/base/ebase.h>
#include <lib/dvb/pmt.h>
#include <lib/dvb/idvb.h>
#include <lib/dvb/idemux.h>
#include <lib/service/iservicescrambled.h>
#include <sigc++/sigc++.h>
#include <set>

/**
 * eDVBSoftDecoder - the descrambling loop of a live service
 *
 * Reads the scrambled TS of the service from its live (data) demux with a TS recorder, descrambles it in place
 * (the session given with setDescrambler, lib/dvb/csasession.h) and writes it into the dvr of a playback demux of its
 * own. The decoder of the service plays from that demux (getDecodeDemux). Data the dvr has no room for is dropped
 * (iDVBTSRecorder::setDvrLoop), a stalled picture is restarted (pause / play) and a writer that stopped on a write
 * error is started again.
 */
class eDVBSoftDecoder : public iObject, public sigc::trackable
{
	DECLARE_REF(eDVBSoftDecoder);

public:
	eDVBSoftDecoder(eDVBServicePMTHandler& source_handler);
	~eDVBSoftDecoder();

	// the descrambler (0: the loop only, for the loop test on a free service)
	void setDescrambler(ePtr<iServiceScrambled> descrambler);

	int start();
	void stop();
	bool isRunning() const { return m_running; }

	// the playback demux fed by the loop: eDVBServicePlay takes its decoder from here
	ePtr<iDVBDemux> getDecodeDemux() { return m_decode_demux; }
	// the decoder playing from that demux, for the health check (0 before it is released)
	void setDecoder(ePtr<iTSMPEGDecoder> decoder);
	// the user paused the picture: no stall check, and the writer stops (a paused decoder takes nothing: the dvr would
	// fill and each write would wait in the driver); on play a new writer goes on with the live stream
	void setPaused(bool paused);
	// a new PMT: the PIDs of the loop again
	void updatePids();

private:
	eDVBServicePMTHandler& m_source_handler;
	ePtr<iServiceScrambled> m_descrambler;

	eUsePtr<iDVBPVRChannel> m_pvr_channel;
	ePtr<iDVBDemux> m_decode_demux;
	ePtr<iTSMPEGDecoder> m_decoder;
	ePtr<iDVBTSRecorder> m_record;
	ePtr<eConnection> m_record_event_conn;

	int m_dvr_fd;
	bool m_running;
	bool m_stopping;
	bool m_paused;
	std::set<int> m_pids_active;

	ePtr<eTimer> m_health_timer;
	pts_t m_last_pts;
	int m_stall_count;
	int m_recovery_attempts;
	bool m_stream_stalled;
	int64_t m_last_health_check;
	void streamHealthCheck();

	// Writer restart: the record thread exits on write errors
	static const int MAX_WRITER_RESTARTS = 5;
	static const int WRITER_RESTART_DELAY = 1000;  // ms
	static const int LOOP_BUFFER_SIZE = 6 * 1024 * 1024;  // HDSatelit 0.7.4: demux buffer of the loop (startRecorder)
	static const int HOLD_GRACE_MS = 4000;  // HDSatelit 0.7.4: no stall recovery this long after a wait for a key
	ePtr<eTimer> m_writer_restart_timer;
	int m_writer_restarts;
	void restartWriter();
	void recordEvent(int event);
	// a new recorder on the data demux into the dvr (start, and a restart: a stopped recorder is not started again)
	int startRecorder();
};

#endif // __dvbsoftdecoder_h
