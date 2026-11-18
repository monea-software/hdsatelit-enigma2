/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 */
#ifndef __lib_dvb_hdspazaphi_h
#define __lib_dvb_hdspazaphi_h

/*
 * Guard of the audio delay writes (/proc/stb/audio/audio_delay_pcm and audio_delay_bitstream) on the HiSilicon boxes
 * with the platform daemon libreader (HAVE_HISILICON_LIBREADER: Octagon SF8008 and the others of that family).
 *
 * Read from the code of hi-dvb.ko of the SF8008: the driver registers the misc device /dev/phi. The process that opens
 * it for reading only (the platform daemon, one at a time) gets a small status memory: hi_open maps 44 bytes
 * (HI_DRV_MMZ_AllocAndMap) and keeps their kernel address in the device context; hi_close unmaps them and does not
 * clear that address. The two delay handlers queue their command for the daemon and then store the value at that
 * address (offset 4 for pcm, 8 for bitstream); the read handlers of /proc/stb/audio, avs/0/volume, video/alpha and
 * video/zapmode read from it. So while no process holds /dev/phi for reading (the daemon stopped by enigma2.sh after an
 * exit of enigma2, a daemon still exiting, one that ended by itself) a delay write stores into memory that is gone: a
 * kernel oops in proc_audio_delay_bitstream_write when the page is no longer mapped (seen on an SF8008 at the first
 * zap after a restart of the interface), or a silent write into whatever took that address since. enigma2 writes both
 * delays at the first zap of every run, because the cached values start at -1.
 *
 * The guard: on a box with /dev/phi a delay is written only while some process has /dev/phi open for reading only (a
 * link /proc/<pid>/fd/<n> to /dev/phi whose /proc/<pid>/fdinfo/<n> flags have the access mode O_RDONLY). A process that
 * is exiting has no fd links left, so it does not count. The holder is found by that link, not by its name, so another
 * daemon name on another board of the family is found as well. The pid and fd found are kept: while they still match,
 * a check is one readlink and one small read; the whole /proc is walked only when they do not. Without /dev/phi
 * (every other box) nothing is checked. The root is a parameter only for the tests on the PC ("" on the receiver).
 */

#include <dirent.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <string>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

namespace hdspazaphi
{

enum Stare
{
	FARA_PHI,	/* no /dev/phi: not this driver, write as before */
	TINUT,		/* a process holds /dev/phi for reading only: the status memory is mapped */
	NETINUT		/* /dev/phi exists and nothing holds it for reading: do not write */
};

struct Detinator
{
	int pid;
	int fd;
	Detinator() : pid(-1), fd(-1) {}
};

/* true when <radacina>/proc/<pid>/fd/<fd> links to /dev/phi and its fdinfo has the access mode O_RDONLY */
inline bool fdCitirePhi(const std::string &radacina, int pid, int fd)
{
	char cale[64];
	snprintf(cale, sizeof(cale), "/proc/%d/fd/%d", pid, fd);
	char tinta[16];
	ssize_t n = ::readlink((radacina + cale).c_str(), tinta, sizeof(tinta));
	if (n != 8 || memcmp(tinta, "/dev/phi", 8) != 0)
		return false;
	snprintf(cale, sizeof(cale), "/proc/%d/fdinfo/%d", pid, fd);
	int f = ::open((radacina + cale).c_str(), O_RDONLY | O_CLOEXEC);
	if (f < 0)
		return false;
	char text[256];
	ssize_t m = ::read(f, text, sizeof(text) - 1);
	::close(f);
	if (m <= 0)
		return false;
	text[m] = 0;
	const char *p = strstr(text, "flags:");
	if (!p)
		return false;
	char *sfarsit = 0;
	unsigned long flags = strtoul(p + 6, &sfarsit, 8);
	if (sfarsit == p + 6)
		return false;
	return (flags & O_ACCMODE) == O_RDONLY;
}

/* the fd on which pid holds /dev/phi for reading only, or -1 */
inline int fdPhiAlLui(const std::string &radacina, int pid)
{
	char cale[32];
	snprintf(cale, sizeof(cale), "/proc/%d/fd", pid);
	DIR *d = ::opendir((radacina + cale).c_str());
	if (!d)
		return -1;
	int gasit = -1;
	struct dirent *e;
	while (gasit < 0 && (e = ::readdir(d)) != 0)
	{
		if (e->d_name[0] < '0' || e->d_name[0] > '9')
			continue;
		int fd = atoi(e->d_name);
		if (fdCitirePhi(radacina, pid, fd))
			gasit = fd;
	}
	::closedir(d);
	return gasit;
}

/* whether a delay may be written now; d keeps the holder found last (kept by the caller between calls) */
inline Stare stare(const std::string &radacina, Detinator &d)
{
	struct stat st;
	if (::stat((radacina + "/dev/phi").c_str(), &st) != 0)
		return FARA_PHI;
	if (d.pid > 0 && d.fd >= 0 && fdCitirePhi(radacina, d.pid, d.fd))
		return TINUT;
	d = Detinator();
	DIR *p = ::opendir((radacina + "/proc").c_str());
	if (!p)
		return NETINUT;
	struct dirent *e;
	while ((e = ::readdir(p)) != 0)
	{
		if (e->d_name[0] < '1' || e->d_name[0] > '9')
			continue;
		int pid = atoi(e->d_name);
		int fd = fdPhiAlLui(radacina, pid);
		if (fd >= 0)
		{
			d.pid = pid;
			d.fd = fd;
			break;
		}
	}
	::closedir(p);
	return d.pid > 0 ? TINUT : NETINUT;
}

}

#endif
