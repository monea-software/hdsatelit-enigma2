/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __dvb_demux_h
#define __dvb_demux_h

#include <atomic>
#include <vector>
#include <lib/base/thread.h>
#include <lib/dvb/idvb.h>
#include <lib/dvb/idemux.h>

class eDVBDemux: public iDVBDemux
{
	DECLARE_REF(eDVBDemux);
public:
	enum {
		evtFlush
	};
	eDVBDemux(int adapter, int demux);
	virtual ~eDVBDemux();
	
	RESULT setSourceFrontend(int fenum);
	int getSource() { return source; }
	RESULT setSourcePVR(int pvrnum);
	
	RESULT createSectionReader(eMainloop *context, ePtr<iDVBSectionReader> &reader);
	RESULT createPESReader(eMainloop *context, ePtr<iDVBPESReader> &reader);
	RESULT createTSRecorder(ePtr<iDVBTSRecorder> &recorder);
	RESULT createBitrateCounter(ePtr<iDVBBitrateCounter> &counter);
	RESULT createCountingRecorder(ePtr<iDVBTSRecorder> &recorder);
	RESULT getMPEGDecoder(ePtr<iTSMPEGDecoder> &reader, int primary);
	RESULT getSTC(pts_t &pts, int num);
	RESULT getCADemuxID(uint8_t &id) { id = demux; return 0; }
	RESULT flush();
	RESULT connectEvent(const sigc::slot<void(int)> &event, ePtr<eConnection> &conn);
	int openDVR(int flags);

	int getRefCount() { return ref; }
private:
	int adapter, demux, source;
	
	int m_dvr_busy;
	friend class eDVBSectionReader;
	friend class eDVBPESReader;
	friend class eDVBBitrateCounter;
	friend class eDVBAudio;
	friend class eDVBVideo;
	friend class eDVBPCR;
	friend class eDVBTText;
	friend class eDVBTSRecorder;
	friend class eDVBCAService;
	sigc::signal<void(int)> m_event;
	
	int openDemux(void);
};

class eDVBSectionReader: public iDVBSectionReader, public sigc::trackable
{
	DECLARE_REF(eDVBSectionReader);
	int fd;
	sigc::signal<void(const __u8*)> read;
	ePtr<eDVBDemux> demux;
	int active;
	int checkcrc;
	void data(int);
	ePtr<eSocketNotifier> notifier;
public:
	eDVBSectionReader(eDVBDemux *demux, eMainloop *context, RESULT &res);
	virtual ~eDVBSectionReader();
	RESULT setBufferSize(int size);
	RESULT start(const eDVBSectionFilterMask &mask);
	RESULT stop();
	RESULT connectRead(const sigc::slot<void(const __u8*)> &read, ePtr<eConnection> &conn);
};

class eDVBPESReader: public iDVBPESReader, public sigc::trackable
{
	DECLARE_REF(eDVBPESReader);
	int m_fd;
	sigc::signal<void(const __u8*, int)> m_read;
	ePtr<eDVBDemux> m_demux;
	int m_active;
	void data(int);
	ePtr<eSocketNotifier> m_notifier;
public:
	eDVBPESReader(eDVBDemux *demux, eMainloop *context, RESULT &res);
	virtual ~eDVBPESReader();
	RESULT setBufferSize(int size);
	RESULT start(int pid);
	RESULT stop();
	RESULT connectRead(const sigc::slot<void(const __u8*, int)> &read, ePtr<eConnection> &conn);
};

/* The live bitrate of one PID (sVideoBitrate / sAudioBitrate of eDVBServicePlay). From the GPL-2.0 sources of a public
 * enigma2 (commits 2d5bc2b55524 "[Bitrate] embed in enigma" and ce2af803e20f, Huevos, 17-18.10.2026; licence GPL-2.0
 * like enigma2), adapted for this tree.
 *
 * The thread only reads one PID of a demux and adds up the bytes, nothing is written anywhere. It starts on a PES tap.
 * A tap that stays silent for TAP_FALLBACK_US is opened again, as the other kind of tap if it never delivered a byte, so
 * a stream that stalls or starts late is picked up again. It gives the demux filter back after IDLE_US without a
 * getKbps() call and getKbps() starts it again: nothing is read while no skin asks for the rate.
 *
 * Changed here: on the HiSilicon boxes the TS tap is never opened. There a TSDEMUX_TAP filter is a
 * record channel of the driver, one per demux, shared with the recordings, timeshift and streams, and every time it is
 * destroyed its 4 MB buffer stays lost until the next boot (lib/dvb/hdspazademux.h); a counter that comes and goes with
 * the infobar would eat that memory. The PES tap is what the equalizer uses there too (lib/service/hdsegalizator.cpp).
 *
 * Packets (start(pid, true), BR2 16.11.2026, for an encrypted service): only the TS tap, never the PES tap, and the TS
 * payload is counted packet by packet (tsPayloadBytes: the TS header and the adaptation field are always in clear), so
 * a scrambled PID gives the same number as a clear one. A PES tap of a scrambled PID gets no clear packets to build
 * PES from: on an Octagon SF8008 it counted 1-4 Mbit/s of a 1080i video and 10-70 kbit/s of a constant 448 kbit/s
 * AC-3. Where the TS tap is not allowed (HiSilicon, old API) start(pid, true) fails. A TS tap counts the payload the
 * same way for a clear PID too, so the TS and the PES tap give the same kind of number. */
	/* the payload bytes of one TS packet: after the 4 byte header and the adaptation field, both never scrambled */
static inline unsigned tsPayloadBytes(const unsigned char *p)
{
	const unsigned afc = (p[3] >> 4) & 3;
	if (!(afc & 1))
		return 0;	/* adaptation field only */
	if (!(afc & 2))
		return 184;
	return p[4] >= 183 ? 0 : 183 - p[4];
}

class eDVBBitrateCounter: public iDVBBitrateCounter, public eThread
{
	DECLARE_REF(eDVBBitrateCounter);
		/* a demux filter buffer is only a few KB by default, far too small for a video PID */
	static const int BUFFER_SIZE = 1024 * 1024;
	static const int POLL_TIMEOUT_MS = 250;
	static const int64_t IDLE_US = 5000000;
	static const int64_t MIN_WINDOW_US = 500000;
		/* how long a tap may stay silent before it is opened again */
	static const int64_t TAP_FALLBACK_US = 2000000;
		/* the kbit/s of the payload counted are scaled down by this much to leave out the PES headers (a PES tap
		   delivers the payload of the TS packets, a TS tap counts the same payload, tsPayloadBytes) */
	static const int PES_PAYLOAD_PERCENT = 99;

	ePtr<eDVBDemux> m_demux;
	int m_pid;		/* wanted PID, -1 = stopped (main thread only) */
	bool m_packets;		/* start(pid, true): TS tap only (main thread, read by the counting thread while it runs) */
		/* a TS packet cut by a read, finished by the next one (counting thread only) */
	unsigned char m_part[188];
	int m_part_len;
	uint64_t countTs(const unsigned char *buf, int len);
	int m_fd;		/* demux filter: opened by the main thread, closed by the counting thread when it ends */
	int m_wake_fd;		/* eventfd, wakes the counting thread for stop() */
	std::vector<uint8_t> m_buf;
	std::atomic<uint64_t> m_bytes;
	std::atomic<int64_t> m_last_query_us;
	std::atomic<bool> m_exited;
	std::atomic<bool> m_ts_tap;	/* the filter is a TS tap, not a PES tap */
		/* current measuring window (main thread only) */
	uint64_t m_win_bytes;
	int64_t m_win_us;
	int m_kbps;

	static bool tsTapAllowed();
	int openFilter(int pid, bool ts);
	int startThread();
	void stopThread();
	/* override */ void thread();
public:
	eDVBBitrateCounter(eDVBDemux *demux);
	virtual ~eDVBBitrateCounter();
	RESULT start(int pid, bool packets);
	RESULT stop();
	int getKbps();
};

class eDVBRecordFileThread;

class eDVBTSRecorder: public iDVBTSRecorder, public sigc::trackable
{
	DECLARE_REF(eDVBTSRecorder);
public:
	eDVBTSRecorder(eDVBDemux *demux);
	~eDVBTSRecorder();

	RESULT setBufferSize(int size);
	RESULT start();
	RESULT addPID(int pid);
	RESULT removePID(int pid);
	
	RESULT setTimingPID(int pid, int type);
	
	RESULT setTargetFD(int fd);
	RESULT setTargetFilename(const char *filename);
	RESULT setBoundary(off_t max);
	
	RESULT stop();

	RESULT getCurrentPCR(pts_t &pcr);

	RESULT connectEvent(const sigc::slot<void(int)> &event, ePtr<eConnection> &conn);
	RESULT setDescrambler(ePtr<iServiceScrambled> descrambler);
	RESULT setDvrLoop(bool loop);
	RESULT setCountPID(int slot, int pid);
	int getCountPID(int slot);
	uint64_t getCountedBytes(int slot);
private:
	RESULT startPID(int pid);
	void stopPID(int pid);
	
	eDVBRecordFileThread *m_thread;
	void filepushEvent(int event);
	
	std::map<int,int> m_pids;
	sigc::signal<void(int)> m_event;
	
	ePtr<eDVBDemux> m_demux;
	
	int m_running, m_target_fd, m_source_fd;
	int m_buffer_size; /* HDSatelit 0.7.4: the demux buffer of start() (setBufferSize before start) */
	std::string m_target_filename;
};

#endif
