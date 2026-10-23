/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/base/filepush.h>
#include <lib/base/eerror.h>
#include <errno.h>
#include <fcntl.h>
#include <sys/ioctl.h>

#define PVR_COMMIT 1

//FILE *f = fopen("/log.ts", "wb");

eFilePushThread::eFilePushThread(int io_prio_class, int io_prio_level, int blocksize)
	:prio_class(io_prio_class), prio(io_prio_level), m_messagepump(eApp, 0)
{
	m_stop = 0;
	m_sg = 0;
	m_send_pvr_commit = 0;
	m_stream_mode = 0;
	m_blocksize = blocksize;
	m_fd_source = -1;
	flush();
	enablePVRCommit(0);
	CONNECT(m_messagepump.recv_msg, eFilePushThread::recvEvent);
}

static void signal_handler(int x)
{
}

#if HAVE_HISILICON
#include <poll.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/syscall.h>

/* Waits until fd has data to read, for at most timeout_ms. SIGUSR1 from stop() ends the wait early (the handler is
   installed without SA_RESTART), and a closed descriptor returns at once (POLLNVAL). */
static void hisiWaitReadable(int fd, int timeout_ms)
{
	struct pollfd pfd;
	pfd.fd = fd;
	pfd.events = POLLIN;
	pfd.revents = 0;
	poll(&pfd, 1, timeout_ms);
}

/* Pause before the next read of the recording demux, once the driver has no more data: without it the thread reads
   and writes as soon as the driver has queued anything, down to one packet per wake-up, which is thousands of small
   writes per second. The pause lasts about the time the service needs for HISI_GATHER_BYTES (from the rate read so
   far), between HISI_GATHER_MIN_MS and HISI_GATHER_MS: 14 ms at 37 Mbit/s, the longest one for radio. The demux
   buffer of a recording holds 1 MB (eDVBTSRecorder::start), 220 ms at 37 Mbit/s. */
#define HISI_GATHER_MS 40
#define HISI_GATHER_MIN_MS 4
#define HISI_GATHER_BYTES 65536

/* A read that did not fill the buffer is followed at once by the next one when the demux still has data (poll without
   waiting): a read of the demux can end at the end of a block or of the ring of the driver while more data waits
   behind it. After a read below HISI_FULL_READ this happens only once in a row, so a fast service where every look
   finds one new packet does not turn into one read per packet. */
#define HISI_FULL_READ 16384

/* Counters of a recording thread, written to /tmp/hds-inregistrare-<thread id>.stat at most every HISI_STAT_MS while
   it runs; at the end the file becomes /tmp/hds-inregistrare-ultima.stat (the last recording that ended). */
#define HISI_STAT_MS 2000

/* A read of the recording demux that fails (an error other than EAGAIN, EINTR, EBUSY, EOVERFLOW) or returns 0 is
   repeated after HISI_RETRY_MS instead of ending the thread: the demux of a live service has no end, and the end of the
   thread is not reported to the recording or to the stream server (eDVBTSRecorder::filepushEvent passes on only the
   write errors), so one failed read used to stop the data of a recording or of a 8001 session for good. The thread
   ends as before only after HISI_FAIL_MS of failed reads with no data between them. */
#define HISI_RETRY_MS 20
#define HISI_FAIL_MS 10000

/* Playback into the dvr of a demux (a file as source, the scatter-gather of eDVBChannel). The driver of these boxes keeps
   a TS buffer of 12 MB per RAM port, and its write never waits in an interruptible way: with less than 1 MB free it
   sleeps 100 ms (msleep, state D) and returns EAGAIN; after a write that leaves the buffer more than half used it
   sleeps 10 ms (msleep). The thread reads the file much faster than the decoder plays it, so the buffer is soon full;
   retrying at once, the thread spent almost all its time in those sleeps, in state D at every look (the watchdog of
   the image takes a thread that stays in D for a hung one and restarts the receiver) and with a kernel line 10 times a
   second. Now a write that comes back EAGAIN, or that took HISI_DVR_SLOW_US or more (the 10 ms sleep), means "full":
   the thread waits HISI_DVR_WAIT_US outside the driver (nanosleep, state S) while the decoder still has half of the
   buffer at least (6 MB, more than a second even at 40 Mbit/s), then fills it again. While the decoder is paused
   (setHoldWhenFull) it writes nothing more once the buffer is full: it waits in steps of HISI_DVR_HOLD_US until the
   hold is lifted. stop() and setHoldWhenFull(false) end the wait at once (SIGUSR1, the handler is installed without
   SA_RESTART). */
#define HISI_DVR_SLOW_US 5000
#define HISI_DVR_WAIT_US 400000L
#define HISI_DVR_HOLD_US 200000L

/* Sleeps for us microseconds; SIGUSR1 from stop() ends the sleep early (nanosleep is not restarted after a signal
   handler, it returns EINTR). */
static void hisiPause(long us)
{
	struct timespec t;
	t.tv_sec = us / 1000000L;
	t.tv_nsec = (us % 1000000L) * 1000L;
	nanosleep(&t, NULL);
}

/* the descriptor has data to read now (a look without waiting) */
static bool hisiReadable(int fd)
{
	struct pollfd pfd;
	pfd.fd = fd;
	pfd.events = POLLIN;
	pfd.revents = 0;
	return poll(&pfd, 1, 0) > 0 && (pfd.revents & POLLIN);
}

static int64_t hisiNowUs()
{
	struct timespec t;
	clock_gettime(CLOCK_MONOTONIC, &t);
	return (int64_t)t.tv_sec * 1000000 + t.tv_nsec / 1000;
}

struct hisiRecordStats
{
	int64_t start_us, saved_us;
	unsigned long long bytes;
	unsigned long reads, full, short_big, small, at_once, eagain, eoverflow, errors, zero_reads, retries, skipped, pauses,
		writes, max_read;
	int64_t read_us, read_max_us, pause_us, write_us, write_max_us;
	long last_pause_us;
	int last_errno;
	const char *target;
	char path[64];

	void begin(int fd_dest)
	{
		*this = hisiRecordStats();
		start_us = saved_us = hisiNowUs();
		struct stat st;
		target = "other";
		if (fstat(fd_dest, &st) == 0)
			target = S_ISFIFO(st.st_mode) ? "pipe" : S_ISREG(st.st_mode) ? "file" : S_ISSOCK(st.st_mode) ? "socket" : "other";
		snprintf(path, sizeof(path), "/tmp/hds-inregistrare-%ld.stat", (long)syscall(SYS_gettid));
	}
	void readDone(int64_t us, int n, size_t maxread)
	{
		read_us += us;
		if (us > read_max_us)
			read_max_us = us;
		if (n > 0)
		{
			reads++;
			bytes += n;
			if ((unsigned long)n > max_read)
				max_read = n;
			if ((size_t)n >= maxread)
				full++;
			else if (n >= HISI_FULL_READ)
				short_big++;
			else
				small++;
		}
		else if (n < 0 && errno == EAGAIN)
			eagain++;
		else if (n < 0 && errno == EOVERFLOW)
			eoverflow++;
		else if (n < 0 && errno != EINTR)
		{
			errors++;
			last_errno = errno;
		}
		else if (n == 0)
			zero_reads++;
	}
	void wrote(int64_t us)
	{
		writes++;
		write_us += us;
		if (us > write_max_us)
			write_max_us = us;
	}
	/* key=value lines, written to a temporary file and renamed, so a reader never sees half a file */
	void save(bool final)
	{
		int64_t now = hisiNowUs();
		if (!final && now - saved_us < HISI_STAT_MS * 1000)
			return;
		saved_us = now;
		int64_t run = now - start_us;
		char text[1024];
		int n = snprintf(text, sizeof(text),
			"target=%s\nrunning=%d\nseconds=%.1f\nbytes=%llu\nmbit_s=%.2f\nreads=%lu\nreads_full=%lu\nreads_short=%lu\n"
			"reads_small=%lu\nread_at_once=%lu\nmax_read=%lu\neagain=%lu\neoverflow=%lu\nread_errors=%lu\n"
			"last_errno=%d\nzero_reads=%lu\nretries=%lu\nskipped=%lu\n"
			"read_ms=%lld\nread_max_ms=%.1f\npauses=%lu\npause_ms=%lld\nlast_pause_ms=%.1f\nwrites=%lu\nwrite_ms=%lld\n"
			"write_max_ms=%.1f\n",
			target, final ? 0 : 1, run / 1e6, bytes, run > 0 ? bytes * 8.0 / run : 0.0, reads, full, short_big, small,
			at_once, max_read, eagain, eoverflow, errors, last_errno, zero_reads, retries, skipped,
			(long long)(read_us / 1000), read_max_us / 1000.0, pauses, (long long)(pause_us / 1000),
			last_pause_us / 1000.0, writes, (long long)(write_us / 1000), write_max_us / 1000.0);
		if (n <= 0 || n >= (int)sizeof(text))
			return;
		char tmp[80];
		snprintf(tmp, sizeof(tmp), "%s.tmp", path);
		int fd = ::open(tmp, O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
		if (fd < 0)
			return;
		bool ok = ::write(fd, text, n) == n;
		::close(fd);
		if (!ok || ::rename(tmp, final ? "/tmp/hds-inregistrare-ultima.stat" : path) < 0)
			::unlink(tmp);
		else if (final)
			::unlink(path);
	}
};

#endif
void eFilePushThread::thread()
{
	setIoPrio(prio_class, prio);

	off_t dest_pos = 0;
	size_t bytes_read = 0;
	
	off_t current_span_offset = 0;
	size_t current_span_remaining = 0;
	
	size_t written_since_last_sync = 0;
#if HAVE_HISILICON
	bool hisi_gather = true; /* the last read of a descriptor source did not fill the buffer */
	bool hisi_small = true;   /* ... and it brought less than HISI_FULL_READ (or nothing) */
	bool hisi_at_once = false; /* the last read came at once after a short one, without a pause */
	int64_t hisi_cycle_us = 0; /* start of the last pause */
	unsigned long long hisi_cycle_bytes = 0; /* bytes read since then */
	double hisi_rate = 0;      /* bytes per microsecond, smoothed over the pauses */
	int hisi_skip = 0;         /* bytes of a broken packet still to drop from the next reads (alignment) */
	int64_t hisi_fail_us = 0;  /* start of the current run of failed reads, 0 = the last read brought data */
	bool hisi_live = m_fd_source >= 0 && !m_sg; /* the source is the demux of a live service */
	bool hisi_dvr = m_fd_source < 0 && m_sg; /* playback into the dvr (see HISI_DVR_WAIT_US) */
	bool hisi_dvr_full = false; /* the last write into the dvr found the TS buffer of the driver full */
	hisiRecordStats hisi_stats;
	if (m_fd_source >= 0)
	{
		hisi_stats.begin(m_fd_dest);
		hisi_cycle_us = hisiNowUs();
	}
#endif

	eDebug("FILEPUSH THREAD START");
	
		/* we set the signal to not restart syscalls, so we can detect our signal. */
	struct sigaction act;
	act.sa_handler = signal_handler; // no, SIG_IGN doesn't do it. we want to receive the -EINTR
	act.sa_flags = 0;
	sigaction(SIGUSR1, &act, 0);
	
	hasStarted();

		/* m_stop must be evaluated after each syscall. */
	while (!m_stop)
	{
#if HAVE_HISILICON
		if (hisi_dvr_full)
		{
			hisi_dvr_full = false;
			if (m_hold_when_full)
			{
				eDebug("[eFilePushThread] playback paused, the buffer of the driver is full: waiting outside the driver");
				while (m_hold_when_full && !m_stop)
					hisiPause(HISI_DVR_HOLD_US);
				eDebug("[eFilePushThread] playback goes on");
			}
			else
				hisiPause(HISI_DVR_WAIT_US);
			continue; /* m_stop is checked by the loop */
		}
#endif
			/* first try flushing the bufptr */
		if (m_buf_start != m_buf_end)
		{
				/* filterRecordData wants to work on multiples of blocksize.
				   if it returns a negative result, it means that this many bytes should be skipped
				   *in front* of the buffer. Then, it will be called again. with the newer, shorter buffer.
				   if filterRecordData wants to skip more data then currently available, it must do that internally.
				   Skipped bytes will also not be output.

				   if it returns a positive result, that means that only these many bytes should be used
				   in the buffer. 
				   
				   In either case, current_span_remaining is given as a reference and can be modified. (Of course it 
				   doesn't make sense to decrement it to a non-zero value unless you return 0 because that would just
				   skip some data). This is probably a very special application for fast-forward, where the current
				   span is to be cancelled after a complete iframe has been output.

				   we always call filterRecordData with our full buffer (otherwise we couldn't easily strip from the end)
				   
				   we filter data only once, of course, but it might not get immediately written.
				   that's what m_filter_end is for - it points to the start of the unfiltered data.
				*/
			
			int filter_res;
			
			do
			{
				filter_res = filterRecordData(m_buffer + m_filter_end, m_buf_end - m_filter_end, current_span_remaining);

				if (filter_res < 0)
				{
					eDebug("[eFilePushThread] filterRecordData re-syncs and skips %d bytes", -filter_res);
					m_buf_start = m_filter_end + -filter_res;  /* this will also drop unwritten data */
					ASSERT(m_buf_start <= m_buf_end); /* otherwise filterRecordData skipped more data than available. */
					continue; /* try again */
				}
				
					/* adjust end of buffer to strip dropped tail bytes */
				m_buf_end = m_filter_end + filter_res;
					/* mark data as filtered. */
				m_filter_end = m_buf_end;
			} while (0);
			
			ASSERT(m_filter_end == m_buf_end);
			
			if (m_buf_start == m_buf_end)
				continue;

				/* now write out data. it will be 'aligned' (according to filterRecordData). 
				   absolutely forbidden is to return EINTR and consume a non-aligned number of bytes. 
				*/
#if HAVE_HISILICON
			int64_t hisi_w0 = (m_fd_source >= 0 || hisi_dvr) ? hisiNowUs() : 0;
#endif
			int w = write(m_fd_dest, m_buffer + m_buf_start, m_buf_end - m_buf_start);
#if HAVE_HISILICON
			int hisi_errno = errno; /* the checks below look at errno: the statistics write files */
			if (m_fd_source >= 0)
			{
				hisi_stats.wrote(hisiNowUs() - hisi_w0);
				hisi_stats.save(false);
			}
			else if (hisi_dvr)
				hisi_dvr_full = (w < 0 && hisi_errno == EAGAIN) || (w > 0 && hisiNowUs() - hisi_w0 >= HISI_DVR_SLOW_US);
			errno = hisi_errno;
#endif
//			fwrite(m_buffer + m_buf_start, 1, m_buf_end - m_buf_start, f);
//			eDebug("wrote %d bytes", w);
			if (w <= 0)
			{
				if (errno == EINTR || errno == EAGAIN || errno == EBUSY)
					continue;
				eDebug("eFilePushThread WRITE ERROR");
				sendEvent(evtWriteError);
				break;
				// ... we would stop the thread
			}

			written_since_last_sync += w;

			if (written_since_last_sync >= 512*1024)
			{
				int toflush = written_since_last_sync > 2*1024*1024 ?
					2*1024*1024 : written_since_last_sync &~ 4095; // write max 2MB at once
				dest_pos = lseek(m_fd_dest, 0, SEEK_CUR);
				dest_pos -= toflush;
				posix_fadvise(m_fd_dest, dest_pos, toflush, POSIX_FADV_DONTNEED);
				written_since_last_sync -= toflush;
			}

//			printf("FILEPUSH: wrote %d bytes\n", w);
			m_buf_start += w;
			continue;
		}

			/* now fill our buffer. */
			
		if (m_sg && !current_span_remaining)
		{
			m_sg->getNextSourceSpan(m_current_position, bytes_read, current_span_offset, current_span_remaining);
			ASSERT(!(current_span_remaining % m_blocksize));
			m_current_position = current_span_offset;
			bytes_read = 0;
		}

		size_t maxread = READ_SIZE;
#if HAVE_HISILICON
		/* the demux of a recording: up to 5 blocks of the recording buffer of the chip in one read, so one read takes
		   what the driver gathered during a pause */
		if (m_fd_source >= 0 && !m_sg)
			maxread = sizeof(m_buffer);
#endif
		
			/* if we have a source span, don't read past the end */
		if (m_sg && maxread > current_span_remaining)
			maxread = current_span_remaining;

			/* align to blocksize */
		maxread -= maxread % m_blocksize;

		m_buf_start = 0;
		m_filter_end = 0;
		m_buf_end = 0;

#if HAVE_HISILICON
		/* gather: a read that filled the buffer is followed at once by the next one; after a short read of the demux
		   (read without blocking) the next one also comes at once while the demux still has data (HISI_FULL_READ),
		   otherwise the thread lets it fill for a pause sized by the rate (HISI_GATHER_BYTES) */
		bool hisi_now = false; /* this read comes at once after a short one */
		if (m_fd_source >= 0 && hisi_gather && maxread)
		{
			hisi_now = !(hisi_small && hisi_at_once) && hisiReadable(m_fd_source);
			if (hisi_now)
				hisi_stats.at_once++;
			else
			{
				int64_t t0 = hisiNowUs();
				if (t0 > hisi_cycle_us && hisi_cycle_bytes)
				{
					double r = (double)hisi_cycle_bytes / (t0 - hisi_cycle_us);
					hisi_rate = hisi_rate > 0 ? 0.75 * hisi_rate + 0.25 * r : r;
				}
				long us = HISI_GATHER_MS * 1000L;
				if (hisi_rate > 0 && HISI_GATHER_BYTES / hisi_rate < us)
					us = HISI_GATHER_BYTES / hisi_rate < HISI_GATHER_MIN_MS * 1000L ? HISI_GATHER_MIN_MS * 1000L
						: (long)(HISI_GATHER_BYTES / hisi_rate);
				hisiPause(us);
				hisi_stats.pauses++;
				hisi_stats.pause_us += hisiNowUs() - t0;
				hisi_stats.last_pause_us = us;
				hisi_stats.save(false);
				hisi_cycle_us = t0;
				hisi_cycle_bytes = 0;
				if (m_stop)
					break;
			}
		}
		hisi_at_once = hisi_now;
		int64_t hisi_r0 = m_fd_source >= 0 ? hisiNowUs() : 0;
#endif
		if (maxread)
			m_buf_end = m_source->read(m_current_position, m_buffer, maxread);
#if HAVE_HISILICON
		hisi_gather = m_buf_end < (int)maxread;
		hisi_small = m_buf_end < HISI_FULL_READ;
		if (m_fd_source >= 0 && maxread)
			hisi_stats.readDone(hisiNowUs() - hisi_r0, m_buf_end, maxread);
#endif

		if (m_buf_end < 0)
		{
			m_buf_end = 0;
#if HAVE_HISILICON
			/* the demux of a recording is read without blocking here: with no data yet, wait for it instead of
			   reading again at once (which would keep one core busy); m_stop is checked right after the wait */
			if (errno == EAGAIN && m_fd_source >= 0)
			{
				hisi_fail_us = 0; /* the demux answers, it only has no data yet */
				hisiWaitReadable(m_fd_source, 100);
				hisi_at_once = true; /* the first packets wake the thread: let them gather before the next read */
				continue;
			}
#endif
			if (errno == EINTR || errno == EBUSY || errno == EAGAIN)
				continue;
			if (errno == EOVERFLOW)
			{
				eWarning("OVERFLOW while recording");
				continue;
			}
#if HAVE_HISILICON
			if (hisi_live)
			{
				if (!hisi_fail_us)
					eWarning("[eFilePushThread] read error on the recording demux (%m), reading again");
			}
			else
#endif
			eDebug("eFilePushThread *read error* (%m) - not yet handled");
		}

#if HAVE_HISILICON
		if (hisi_live && maxread)
		{
			if (m_buf_end > 0)
				hisi_fail_us = 0;
			else
			{
				int64_t now = hisiNowUs();
				if (!hisi_fail_us)
					hisi_fail_us = now;
				if (now - hisi_fail_us < HISI_FAIL_MS * 1000LL)
				{
					hisi_stats.retries++;
					hisi_stats.save(false);
					hisiPause(HISI_RETRY_MS * 1000L);
					hisi_at_once = true;
					continue;
				}
				eWarning("[eFilePushThread] no data from the recording demux for %d ms, stopping", HISI_FAIL_MS);
			}
		}
		/* the rest of a packet whose start was dropped (its completion failed): drop it from this read too, before the
		   completion below, so the output stays aligned; the position follows every byte taken from the demux, so the
		   source is never asked to seek */
		bool hisi_dropped = false;
		if (hisi_live && hisi_skip > 0 && m_buf_end > 0)
		{
			int k = hisi_skip < m_buf_end ? hisi_skip : m_buf_end;
			memmove(m_buffer, m_buffer + k, m_buf_end - k);
			m_buf_end -= k;
			hisi_skip -= k;
			m_current_position += k;
			hisi_stats.skipped += k;
			hisi_dropped = true;
		}
		/* A read without blocking can end inside a TS packet, when it meets the demux buffer while the driver is
		   still copying into it. The part already read is gone from the demux: read the rest of that packet, which
		   follows at once, instead of dropping the part below (the recording would lose its packet alignment). */
		if (m_fd_source >= 0 && m_buf_end > 0)
		{
			int missing = (m_blocksize - m_buf_end % m_blocksize) % m_blocksize;
			int waits = 0; /* at most 50 waits for the rest: then the packet is dropped (hisi_skip) */
			while (missing > 0 && !m_stop)
			{
				ssize_t r = m_source->read(m_current_position + m_buf_end, m_buffer + m_buf_end, missing);
				if (r > 0)
				{
					m_buf_end += r;
					missing -= r;
					hisi_stats.bytes += r;
				}
				else if (((r < 0 && errno == EAGAIN) || r == 0) && ++waits <= 50)
					hisiWaitReadable(m_fd_source, 100);
				else if (r < 0 && errno == EINTR)
					continue; /* m_stop is checked by the loop */
				else
					break;
			}
		}
		if (m_fd_source >= 0 && m_buf_end > 0)
			hisi_cycle_bytes += m_buf_end;
#endif
			/* a read might be mis-aligned in case of a short read. */
		int d = m_buf_end % m_blocksize;
		if (d)
		{
			m_buf_end -= d;
#if HAVE_HISILICON
			if (hisi_live)
			{
				hisi_skip = m_blocksize - d;
				m_current_position += d;
				hisi_stats.skipped += d;
				hisi_dropped = true;
			}
#endif
		}
#if HAVE_HISILICON
		/* this read brought only bytes of a broken packet, now dropped: read again, it is not the end */
		if (hisi_dropped && m_buf_end == 0 && !m_stop)
			continue;
#endif

		if (m_buf_end == 0)
		{
				/* on EOF, try COMMITting once. */
			if (m_send_pvr_commit)
			{
				struct pollfd pfd;
				pfd.fd = m_fd_dest;
				pfd.events = POLLIN;
				switch (poll(&pfd, 1, 250)) // wait for 250ms
				{
					case 0:
						eDebug("wait for driver eof timeout");
						continue;
					case 1:
						eDebug("wait for driver eof ok");
						break;
					default:
						eDebug("wait for driver eof aborted by signal");
						continue;
				}
			}
			
				/* in stream_mode, we are sending EOF events 
				   over and over until somebody responds.
				   
				   in stream_mode, think of evtEOF as "buffer underrun occured". */
			sendEvent(evtEOF);

			if (m_stream_mode)
			{
				eDebug("reached EOF, but we are in stream mode. delaying 1 second.");
				sleep(1);
				continue;
			}
			break;
		} else
		{
			m_current_position += m_buf_end;
			bytes_read += m_buf_end;
			if (m_sg)
				current_span_remaining -= m_buf_end;
		}
//		printf("FILEPUSH: read %d bytes\n", m_buf_end);
	}
	fdatasync(m_fd_dest);
#if HAVE_HISILICON
	if (m_fd_source >= 0)
		hisi_stats.save(true);
#endif

	eDebug("FILEPUSH THREAD STOP");
}

void eFilePushThread::start(int fd, int fd_dest)
{
	eRawFile *f = new eRawFile();
	ePtr<iTsSource> source = f;
	f->setfd(fd);
	m_fd_source = fd;
	start(source, fd_dest);
}

int eFilePushThread::start(const char *file, int fd_dest)
{
	eRawFile *f = new eRawFile();
	ePtr<iTsSource> source = f;
	if (f->open(file) < 0)
		return -1;
	m_fd_source = -1;
	start(source, fd_dest);
	return 0;
}

void eFilePushThread::start(ePtr<iTsSource> &source, int fd_dest)
{
	m_source = source;
	m_fd_dest = fd_dest;
	m_current_position = 0;
	resume();
}

void eFilePushThread::stop()
{
		/* if we aren't running, don't bother stopping. */
	if (!sync())
		return;

	m_stop = 1;

	eDebug("stopping thread."); /* just do it ONCE. it won't help to do this more than once. */
	sendSignal(SIGUSR1);
	kill(0);
}

void eFilePushThread::pause()
{
	stop();
}

void eFilePushThread::resume()
{
	m_stop = 0;
	run();
}

void eFilePushThread::flush()
{
	m_buf_start = m_buf_end = m_filter_end = 0;
}

#if HAVE_HISILICON
void eFilePushThread::setHoldWhenFull(bool hold)
{
	m_hold_when_full = hold ? 1 : 0;
	/* a thread waiting outside the driver goes on at once */
	if (!hold && sync())
		sendSignal(SIGUSR1);
}

#endif
void eFilePushThread::enablePVRCommit(int s)
{
	m_send_pvr_commit = s;
}

void eFilePushThread::setStreamMode(int s)
{
	m_stream_mode = s;
}

void eFilePushThread::setScatterGather(iFilePushScatterGather *sg)
{
	m_sg = sg;
}

void eFilePushThread::sendEvent(int evt)
{
	m_messagepump.send(evt);
}

void eFilePushThread::recvEvent(const int &evt)
{
	m_event(evt);
}

int eFilePushThread::filterRecordData(const unsigned char *data, int len, size_t &current_span_remaining)
{
	return len;
}
