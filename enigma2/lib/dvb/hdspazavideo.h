/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 */
#ifndef __lib_dvb_hdspazavideo_h
#define __lib_dvb_hdspazavideo_h

/*
 * Guard of the writes on video0 and audio0 on the HiSilicon boxes.
 *
 * The ES of still pictures and of files (films, music, streams) reach the decoder through a memory the video driver
 * shares with the platform daemon. Every write() on video0 and on audio0 goes through a check in the driver that
 * reads a pointer to that memory without testing it for NULL; the ioctls test it, so only the writes need this
 * guard. The daemon has that memory mapped into the kernel when it starts: one vmalloc range of HISI_ES_MAP_SIZE
 * bytes (guard page included), listed in /proc/vmallocinfo while it exists. When the kernel has no free range that
 * large the mapping fails ("vmap allocation for size 34611200 failed", then "[HI_DRV_SMMU_Map] Remap buf failed"),
 * the pointer stays NULL until the next start of the daemon, live channels still play (they do not use that memory)
 * and the first write() on video0 or audio0 is a kernel oops, after which the device stays busy until a reboot.
 *
 * Used only in HiSilicon builds: by lib/dvb/decoder.cpp before the still picture of a radio channel is written
 * (showSinglePic) and by lib/service/servicemp3.cpp before the pipeline of a file is built (its sinks, dvbvideosink
 * and dvbaudiosink, write to video0 and audio0). The functions are small and keep no state, so they are inline here;
 * the tests on the PC build them alone.
 */

#include <fcntl.h>
#include <stddef.h>
#include <string>
#include <unistd.h>

#define HISI_ES_MAP_SIZE 34611200ULL

/* The number of lines of /proc/vmallocinfo ("0x<start>-0x<end> <size> <caller> ...") with the size HISI_ES_MAP_SIZE */
inline int hisiCountEsMaps(const char *text, size_t len)
{
	int count = 0;
	size_t pos = 0;
	while (pos < len)
	{
		size_t end = pos;
		while (end < len && text[end] != '\n')
			++end;
		if (end - pos > 2 && text[pos] == '0' && text[pos + 1] == 'x')
		{
			size_t i = pos;
			while (i < end && text[i] != ' ' && text[i] != '\t')
				++i;
			while (i < end && (text[i] == ' ' || text[i] == '\t'))
				++i;
			unsigned long long size = 0;
			int digits = 0;
			while (i < end && text[i] >= '0' && text[i] <= '9' && digits < 16)
			{
				size = size * 10 + (unsigned)(text[i] - '0');
				++i;
				++digits;
			}
			if (digits && digits < 16 && (i == end || text[i] == ' ' || text[i] == '\t') && size == HISI_ES_MAP_SIZE)
				++count;
		}
		pos = end + 1;
	}
	return count;
}

/* 1 when /proc/vmallocinfo lists the memory the driver shares with the platform daemon, 0 when it does not, -1 when
   the file cannot be read */
inline int hisiEsMemoryMapped()
{
	int fd = open("/proc/vmallocinfo", O_RDONLY | O_CLOEXEC);
	if (fd < 0)
		return -1;
	std::string text;
	char buf[4096];
	ssize_t n;
	while ((n = read(fd, buf, sizeof(buf))) > 0 && text.size() < (8u << 20))
		text.append(buf, n);
	close(fd);
	if (n < 0 || text.empty())
		return -1;
	return hisiCountEsMaps(text.data(), text.size()) > 0 ? 1 : 0;
}

#endif
