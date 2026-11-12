/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __lib_base_filepush_h
#define __lib_base_filepush_h

#include <lib/base/thread.h>
#include <lib/base/ioprio.h>
#include <libsig_comp.h>
#include <lib/base/message.h>
#include <sys/types.h>
#include <lib/base/rawfile.h>

class iFilePushScatterGather
{
public:
	virtual void getNextSourceSpan(off_t current_offset, size_t bytes_read, off_t &start, size_t &size)=0;
	virtual ~iFilePushScatterGather() {}
};

class eFilePushThread: public eThread, public sigc::trackable
{
	int prio_class, prio;
public:
	eFilePushThread(int prio_class=IOPRIO_CLASS_BE, int prio_level=0, int blocksize=188);
	void thread();
	void stop();
	void start(int sourcefd, int destfd);
	int start(const char *filename, int destfd);

	void start(ePtr<iTsSource> &source, int destfd);

	void pause();
	void resume();
	
		/* flushes the internal readbuffer */ 
	void flush();
	void enablePVRCommit(int);
	
		/* stream mode will wait on EOF until more data is available. */
	void setStreamMode(int);
	
	void setScatterGather(iFilePushScatterGather *);

		/* playback into the dvr of a demux (scatter-gather set, a file as source): while the decoder is paused
		   (true), the HiSilicon thread stops writing once the TS buffer of the driver is full and waits outside the
		   driver until the hold is lifted or the thread is stopped (see HISI_DVR_WAIT_US in filepush.cpp). Other
		   boxes: only kept, nothing changes. */
	void setHoldWhenFull(bool hold);

		/* SoftCSA (lib/service/servicedvbsoftdecoder.h): the source is a live demux and the target the dvr of a playback
		   demux. Set before start(). On HiSilicon writes go in parts of at most DVR_LOOP_PART bytes; a part the driver has
		   no room for (EAGAIN) is dropped and the thread waits DVR_LOOP_FULL_US outside the driver before it reads on (a
		   live stream cannot wait, and a wait inside the driver is state D, which the watchdog of the image takes for a
		   hung thread). On every other receiver the generic path of filepush.cpp (LOOP_GATHER_BYTES) reads the demux
		   without blocking, gathers by size and age, writes parts of whole packets and drops what finds no room for
		   LOOP_DROP_MS. */
	void setDvrLoop(bool loop) { m_dvr_loop = loop ? 1 : 0; }
	bool dvrLoop() const { return m_dvr_loop != 0; }
	
	enum { evtEOF, evtReadError, evtWriteError, evtUser };
	sigc::signal<void(int)> m_event;

	void installSigUSR1Handler();
	void before_set_thread_alive();

		/* you can send private events if you want */
	void sendEvent(int evt);
protected:
	virtual int filterRecordData(const unsigned char *data, int len, size_t &current_span_remaining);
private:
	iFilePushScatterGather *m_sg;
	int m_stop;
	/* READ_SIZE bytes per read; the recording of a demux on HiSilicon reads up to BUFFER_SIZE (5 blocks of the
	   recording buffer of the chip, 48128 bytes = 256 packets each), see eFilePushThread::thread */
	enum { READ_SIZE = 65536, BUFFER_SIZE = 5 * 48128 };
	unsigned char m_buffer[BUFFER_SIZE];
	int m_buf_start, m_buf_end, m_filter_end;
	int m_fd_dest;
	int m_send_pvr_commit;
	int m_stream_mode;
	int m_blocksize;
	off_t m_current_position;
	int m_fd_source; /* descriptor given to start(int, int), or -1: the thread may wait on it with poll */
	volatile int m_hold_when_full = 0; /* setHoldWhenFull */
	int m_dvr_loop = 0; /* setDvrLoop */
	enum { DVR_LOOP_PART = 348 * 188 }; /* 65424 bytes, whole packets, about the write of a playback (READ_SIZE) */

	ePtr<iTsSource> m_source;

	eFixedMessagePump<int> m_messagepump;

	void recvEvent(const int &evt);
};

#endif
