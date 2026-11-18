/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#ifndef __dvb_idemux_h
#define __dvb_idemux_h

#include <stdint.h>
#include <lib/dvb/idvb.h>
#include <lib/service/iservicescrambled.h>

class iDVBSectionReader: public iObject
{
public:
	virtual RESULT setBufferSize(int size)=0;
	virtual RESULT start(const eDVBSectionFilterMask &mask)=0;
	virtual RESULT stop()=0;
	virtual RESULT connectRead(const sigc::slot<void(const __u8*)> &read, ePtr<eConnection> &conn)=0;
	virtual ~iDVBSectionReader() { };
};

class iDVBPESReader: public iObject
{
public:
	virtual RESULT setBufferSize(int size)=0;
	virtual RESULT start(int pid)=0;
	virtual RESULT stop()=0;
	virtual RESULT connectRead(const sigc::slot<void(const __u8*, int)> &read, ePtr<eConnection> &conn)=0;
	virtual ~iDVBPESReader() { };
};

	/* records a given set of pids into a file descriptor. */
	/* the FD must not be modified between start() and stop() ! */
class iDVBTSRecorder: public iObject
{
public:
	virtual RESULT setBufferSize(int size) = 0;
	virtual RESULT start() = 0;
	virtual RESULT addPID(int pid) = 0;
	virtual RESULT removePID(int pid) = 0;
	
	virtual RESULT setTimingPID(int pid, int type) = 0;
	
	virtual RESULT setTargetFD(int fd) = 0;
		/* for saving additional meta data. */
	virtual RESULT setTargetFilename(const char *filename) = 0;
	virtual RESULT setBoundary(off_t max) = 0;
	
	virtual RESULT stop() = 0;

	virtual RESULT getCurrentPCR(pts_t &pcr) = 0;
	
	enum {
		eventWriteError,
				/* a write error has occured. data won't get lost if fd is writable after return. */
				/* you MUST respond with either stop() or fixing the problems, else you get the error */
				/* again. */
		eventReachedBoundary,
				/* the programmed boundary was reached. you might set a new target fd. you can close the */
				/* old one. */
	};
	virtual RESULT connectEvent(const sigc::slot<void(int)> &event, ePtr<eConnection> &conn)=0;

		/* SoftCSA (lib/dvb/csasession.h): the packets are descrambled in place before they are parsed and written; 0 = none.
		   May be changed while the recording runs: the thread never descrambles with a descrambler being replaced.
		   eDVBTSRecorder does it on every receiver; -1 from a recorder that cannot. */
	virtual RESULT setDescrambler(ePtr<iServiceScrambled> descrambler) { return -1; }
		/* the target is the dvr of a playback demux fed from the live demux (lib/service/servicedvbsoftdecoder.h): writes in
		   parts of whole packets, and data the driver has no room for is dropped (the thread waits outside the driver, or
		   for a bounded time) instead of waiting in it for good; must be set before start(). eDVBTSRecorder does it on
		   every receiver (HiSilicon and the generic path, lib/base/filepush.cpp); -1 from a recorder that cannot. */
	virtual RESULT setDvrLoop(bool loop) { return -1; }
		/* counting only, nothing is written (sVideoBitrate / sAudioBitrate of a live service, lib/service/servicedvb.cpp
		   getLiveBitrate): the TS payload bytes (after the TS header and the adaptation field, both always in clear) of up
		   to two PIDs that pass through the recorder, slot 0 and 1, after the descrambler. pid -1 stops a slot, a new PID
		   starts it at 0 bytes; getCountPID gives the PID a slot counts (-1: none). Last in the class, with bodies, so the
		   slots above keep their place; eDVBTSRecorder counts on every receiver, -1 / 0 from a recorder that cannot. */
	virtual RESULT setCountPID(int slot, int pid) { (void)slot; (void)pid; return -1; }
	virtual int getCountPID(int slot) { (void)slot; return -1; }
	virtual uint64_t getCountedBytes(int slot) { (void)slot; return 0; }
};

#endif
