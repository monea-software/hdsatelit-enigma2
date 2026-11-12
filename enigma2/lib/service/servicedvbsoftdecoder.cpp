/* SoftCSA: the loop that feeds the hardware decoder with the stream descrambled in software. GPL-2.0-only.
 * Authors: WXbet, Betacentauri, 2026.
 * Modificat de moneasoftware.com si hdsatelit.com, 2026: only the loop (see servicedvbsoftdecoder.h). */
#include <lib/service/servicedvbsoftdecoder.h>
#include <lib/dvb/csaengine.h>
#include <lib/dvb/dvb.h>
#include <lib/base/eerror.h>
#include <algorithm>
#include <iterator>
#include <fcntl.h>
#include <unistd.h>
#include <time.h>

DEFINE_REF(eDVBSoftDecoder);

eDVBSoftDecoder::eDVBSoftDecoder(eDVBServicePMTHandler& source_handler)
	: m_source_handler(source_handler)
	, m_dvr_fd(-1)
	, m_running(false)
	, m_stopping(false)
	, m_paused(false)
	, m_last_pts(0)
	, m_stall_count(0)
	, m_recovery_attempts(0)
	, m_stream_stalled(false)
	, m_last_health_check(0)
	, m_writer_restarts(0)
{
	m_health_timer = eTimer::create(eApp);
	CONNECT(m_health_timer->timeout, eDVBSoftDecoder::streamHealthCheck);
	m_writer_restart_timer = eTimer::create(eApp);
	CONNECT(m_writer_restart_timer->timeout, eDVBSoftDecoder::restartWriter);
	eDebug("[eDVBSoftDecoder] Created");
}

eDVBSoftDecoder::~eDVBSoftDecoder()
{
	stop();
	eDebug("[eDVBSoftDecoder] Destroyed");
}

void eDVBSoftDecoder::setDescrambler(ePtr<iServiceScrambled> descrambler)
{
	m_descrambler = descrambler;
	if (m_record)
		m_record->setDescrambler(m_descrambler);
}

void eDVBSoftDecoder::setPaused(bool paused)
{
	if (paused == m_paused)
		return;
	m_paused = paused;
	if (!m_running || m_stopping)
		return;
	if (paused)
	{
		eDebug("[eDVBSoftDecoder] decoder paused: the writer stops");
		m_writer_restart_timer->stop();
		if (m_record)
		{
			m_record->stop();
			m_record->setDescrambler(0);
			m_record_event_conn = 0;
			m_record = 0;
		}
	}
	else
	{
		eDebug("[eDVBSoftDecoder] decoder playing again: a new writer");
		m_stall_count = 0;
		m_last_pts = 0;
		m_stream_stalled = false;
		if (startRecorder() < 0)
			m_writer_restart_timer->start(WRITER_RESTART_DELAY, true);
	}
}

void eDVBSoftDecoder::setDecoder(ePtr<iTSMPEGDecoder> decoder)
{
	/* the decoder of the loop goes (its owner drops it now, or dropped it already and this is the last reference): its
	   filters are closed without DMX_STOP while the loop may still write (iTSMPEGDecoder::freeDecoder: needed on
	   Broadcom, nothing on HiSilicon) */
	if (m_decoder && (iTSMPEGDecoder*)m_decoder != (iTSMPEGDecoder*)decoder)
		m_decoder->freeDecoder();
	m_decoder = decoder;
	m_last_pts = 0;
	m_stall_count = 0;
	m_stream_stalled = false;
	m_last_health_check = 0;
	if (m_decoder && m_running)
		m_health_timer->start(500, false);
	else
		m_health_timer->stop();
}

int eDVBSoftDecoder::start()
{
	if (m_running)
		return 0;

	eDebug("[eDVBSoftDecoder] Starting");

	ePtr<iDVBDemux> demux;
	if (m_source_handler.getDataDemux(demux) || !demux)
	{
		eWarning("[eDVBSoftDecoder] no data demux");
		return -1;
	}
	uint8_t data_demux_id = 0;
	demux->getCADemuxID(data_demux_id);

	ePtr<eDVBResourceManager> res_mgr;
	if (eDVBResourceManager::getInstance(res_mgr) || !res_mgr)
		return -2;
	// a playback channel of our own: its demux has a dvr device (on HiSilicon the RAM port of that same demux)
	if (res_mgr->allocatePVRChannel(m_pvr_channel) || !m_pvr_channel)
	{
		eWarning("[eDVBSoftDecoder] allocatePVRChannel failed");
		return -3;
	}
	// cap 0 first: the channel keeps this demux; the decoder role asked later gets the same one
	if (m_pvr_channel->getDemux(m_decode_demux, 0) || !m_decode_demux)
	{
		eWarning("[eDVBSoftDecoder] no playback demux");
		m_pvr_channel = 0;
		return -4;
	}
	uint8_t decode_demux_id = 0;
	m_decode_demux->getCADemuxID(decode_demux_id);

	m_dvr_fd = m_decode_demux->openDVR(O_WRONLY | O_NONBLOCK | O_CLOEXEC);
	if (m_dvr_fd < 0)
	{
		eWarning("[eDVBSoftDecoder] cannot open the dvr of demux %d for writing (%m)", decode_demux_id);
		m_decode_demux = 0;
		m_pvr_channel = 0;
		return -5;
	}

	m_running = true;
	m_stopping = false;
	int ret = startRecorder();
	if (ret < 0)
	{
		stop();
		return ret;
	}
	eDebug("[eDVBSoftDecoder] loop running: demux %d (live) -> software %s -> dvr of demux %d", data_demux_id,
		m_descrambler ? "on" : "off", decode_demux_id);
	return 0;
}

int eDVBSoftDecoder::startRecorder()
{
	if (m_record)
	{
		m_record->stop();
		m_record->setDescrambler(0);
		m_record_event_conn = 0;
		m_record = 0;
	}
	ePtr<iDVBDemux> demux;
	if (m_source_handler.getDataDemux(demux) || !demux)
		return -1;
	demux->createTSRecorder(m_record);
	if (!m_record)
	{
		eWarning("[eDVBSoftDecoder] no ts recorder available");
		return -6;
	}
	if (m_record->setDvrLoop(true) < 0)
	{
		eWarning("[eDVBSoftDecoder] the recorder of this receiver cannot loop into a dvr");
		m_record = 0;
		return -9;
	}
	m_record->setTargetFD(m_dvr_fd);
	m_record->setDescrambler(m_descrambler);
	m_record->connectEvent(sigc::mem_fun(*this, &eDVBSoftDecoder::recordEvent), m_record_event_conn);
	m_pids_active.clear();
	updatePids();
	if (m_pids_active.empty())
	{
		eWarning("[eDVBSoftDecoder] no PIDs");
		return -7;
	}
	/* HDSatelit 0.7.4: room in the demux for the wait of the engine for a late key (eDVBCSAEngine::HOLD_MAX_MS): the 1 MiB
	   of eDVBTSRecorder::start is ~0.7 s of an HD channel, then packets are lost and the picture jumps forward
	   (Octagon SF8008, 11.11.2026: +3.5 s and +5.1 s after a wait of 2 s). Given before start: the HiSilicon driver
	   refuses the change while the filter runs. */
	m_record->setBufferSize(LOOP_BUFFER_SIZE);
	if (m_record->start() < 0)
	{
		eWarning("[eDVBSoftDecoder] recorder start failed");
		return -8;
	}
	return 0;
}

void eDVBSoftDecoder::stop()
{
	if (!m_running)
		return;

	eDebug("[eDVBSoftDecoder] Stopping");
	m_stopping = true;
	m_health_timer->stop();
	m_writer_restart_timer->stop();
	m_writer_restarts = 0;
	// the owner released its decoder before; a reference still held here is the last one (see setDecoder)
	if (m_decoder)
		m_decoder->freeDecoder();
	m_decoder = 0;

	if (m_record)
	{
		m_record->stop();
		m_record->setDescrambler(0);
		m_record_event_conn = 0;
		m_record = 0;
	}
	if (m_dvr_fd >= 0)
	{
		::close(m_dvr_fd);
		m_dvr_fd = -1;
	}
	m_decode_demux = 0;
	m_pvr_channel = 0;

	m_pids_active.clear();
	m_running = false;
	m_stopping = false;
	m_paused = false;
	m_last_pts = 0;
	m_stall_count = 0;
	m_stream_stalled = false;
	m_last_health_check = 0;
	eDebug("[eDVBSoftDecoder] Stop complete");
}

void eDVBSoftDecoder::recordEvent(int event)
{
	if (m_stopping)
		return;

	switch (event)
	{
	case iDVBTSRecorder::eventWriteError:
		// The record thread has exited, nothing reaches the decoder anymore
		if (m_writer_restarts < MAX_WRITER_RESTARTS)
		{
			eWarning("[eDVBSoftDecoder] TS write error - restarting writer in %dms", WRITER_RESTART_DELAY);
			m_writer_restart_timer->start(WRITER_RESTART_DELAY, true);
		}
		else
			eWarning("[eDVBSoftDecoder] TS write error - giving up after %d writer restarts", m_writer_restarts);
		break;
	default:
		eDebug("[eDVBSoftDecoder] Unhandled record event %d", event);
		break;
	}
}

void eDVBSoftDecoder::restartWriter()
{
	if (!m_running || m_stopping || m_paused)
		return;

	m_writer_restarts++;
	eWarning("[eDVBSoftDecoder] Restarting writer (%d/%d)", m_writer_restarts, MAX_WRITER_RESTARTS);
	if (int ret = startRecorder(); ret < 0)
	{
		eWarning("[eDVBSoftDecoder] Writer restart failed (%d)", ret);
		if (m_writer_restarts < MAX_WRITER_RESTARTS)
			m_writer_restart_timer->start(WRITER_RESTART_DELAY, true);
		return;
	}
	m_stall_count = 0;
	m_recovery_attempts = 0;
	m_stream_stalled = false;
}

void eDVBSoftDecoder::streamHealthCheck()
{
	if (!m_decoder || !m_running || m_stopping)
		return;

	// Don't check for stalls while paused - PTS naturally stops
	if (m_paused)
		return;

	// Detect MainLoop hangs: if this timer callback comes much later than
	// expected (>2s instead of 500ms), the MainLoop was blocked.
	// In that case, skip the stall check - the stream kept running fine
	// via the record thread, only our monitoring was paused.
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	int64_t now = (int64_t)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
	if (m_last_health_check > 0)
	{
		int64_t elapsed = now - m_last_health_check;
		if (elapsed > 2000)
		{
			eDebug("[eDVBSoftDecoder] MainLoop was blocked for %lldms, skipping stall check", (long long)elapsed);
			m_stall_count = 0;
			m_stream_stalled = false;
			m_last_pts = 0;
			m_last_health_check = now;
			// Restart timer to discard all queued callbacks from the freeze
			m_health_timer->start(500, false);
			return;
		}
	}
	m_last_health_check = now;

	pts_t current_pts = 0;
	if (m_decoder->getPTS(0, current_pts) != 0)
		return;
	/* HDSatelit 0.7.4: the engine holds the packets for a late key (eDVBCSAEngine::waitForKey) or did so in the last
	   HOLD_GRACE_MS: the picture waits for the key, the decoder is not hung; a pause/play here would drop what the
	   decoder holds and jump forward (Octagon SF8008, 11.11.2026: „attempting recovery” and +5 s after a wait) */
	if (g_csa_counters.waiting_now.load(std::memory_order_relaxed) > 0 ||
		now - g_csa_counters.wait_end_ms.load(std::memory_order_relaxed) < HOLD_GRACE_MS)
	{
		m_stall_count = 0;
		m_stream_stalled = false;
		m_last_pts = current_pts < 0 ? 0 : current_pts;
		return;
	}
	// no picture decoded yet (-1 on HiSilicon, e.g. no control word yet or a wrong one): nothing to recover
	if (current_pts < 0)
		current_pts = 0;

	// During startup, PTS=0 is normal (waiting for CW/data)
	// Only monitor for stalls once stream has actually started (PTS > 0)
	if (current_pts == 0 && m_last_pts == 0)
		return;

	if (current_pts == m_last_pts)
	{
		m_stall_count++;
		if (m_stall_count == 3)
		{
			eWarning("[eDVBSoftDecoder] Stream stalled (PTS=%lld)", (long long)current_pts);
			m_stream_stalled = true;
		}
		else if (m_stall_count == 6)
		{
			m_recovery_attempts++;
			if (m_recovery_attempts >= 5)
			{
				// the decoder did not come back: the writer starts again too (its buffers are dropped)
				eWarning("[eDVBSoftDecoder] Recovery failed %d times - a new writer, decoder paused and played", m_recovery_attempts);
				m_decoder->pause();
				startRecorder();
				m_decoder->play();
				m_recovery_attempts = 0;
			}
			else
			{
				eWarning("[eDVBSoftDecoder] Stream stalled too long - attempting recovery (%d/5)", m_recovery_attempts);
				m_decoder->pause();
				m_decoder->play();
			}
			m_stall_count = 0;
			m_stream_stalled = false;
		}
	}
	else
	{
		if (m_stream_stalled)
			eDebug("[eDVBSoftDecoder] Stream recovered (PTS: %lld -> %lld)", (long long)m_last_pts, (long long)current_pts);
		m_stall_count = 0;
		m_writer_restarts = 0;
		m_stream_stalled = false;
		m_recovery_attempts = 0;
	}

	m_last_pts = current_pts;
}

void eDVBSoftDecoder::updatePids()
{
	if (!m_record)
		return;  // paused: the next writer takes the PIDs when it starts

	eDVBServicePMTHandler::program program;
	if (m_source_handler.getProgramInfo(program))
	{
		eDebug("[eDVBSoftDecoder] getting program info failed.");
		return;
	}

	int timing_pid = -1, timing_type = -1;
	std::set<int> pids_to_record;
	pids_to_record.insert(0); // PAT
	if (program.pmtPid != -1)
		pids_to_record.insert(program.pmtPid); // PMT

	for (std::vector<eDVBServicePMTHandler::videoStream>::const_iterator i(program.videoStreams.begin());
		i != program.videoStreams.end(); ++i)
	{
		pids_to_record.insert(i->pid);
		if (timing_pid == -1)
		{
			timing_pid = i->pid;
			timing_type = i->type;
		}
	}
	for (std::vector<eDVBServicePMTHandler::audioStream>::const_iterator i(program.audioStreams.begin());
		i != program.audioStreams.end(); ++i)
	{
		pids_to_record.insert(i->pid);
		if (timing_pid == -1)
		{
			timing_pid = i->pid;
			timing_type = i->type;
		}
	}
	for (std::vector<eDVBServicePMTHandler::subtitleStream>::const_iterator i(program.subtitleStreams.begin());
		i != program.subtitleStreams.end(); ++i)
		pids_to_record.insert(i->pid);
	if (program.pcrPid >= 0 && program.pcrPid < 0x1fff)
		pids_to_record.insert(program.pcrPid);
	if (program.textPid != -1)
		pids_to_record.insert(program.textPid); // Videotext

	std::set<int> new_pids, obsolete_pids;
	std::set_difference(pids_to_record.begin(), pids_to_record.end(), m_pids_active.begin(), m_pids_active.end(),
		std::inserter(new_pids, new_pids.begin()));
	std::set_difference(m_pids_active.begin(), m_pids_active.end(), pids_to_record.begin(), pids_to_record.end(),
		std::inserter(obsolete_pids, obsolete_pids.begin()));

	for (std::set<int>::iterator i(new_pids.begin()); i != new_pids.end(); ++i)
		m_record->addPID(*i);
	for (std::set<int>::iterator i(obsolete_pids.begin()); i != obsolete_pids.end(); ++i)
		m_record->removePID(*i);

	m_pids_active = pids_to_record;
	if (timing_pid != -1)
		m_record->setTimingPID(timing_pid, timing_type);
	eDebug("[eDVBSoftDecoder] %zu PIDs in the loop (%zu new, %zu removed)", m_pids_active.size(), new_pids.size(),
		obsolete_pids.size());
}
