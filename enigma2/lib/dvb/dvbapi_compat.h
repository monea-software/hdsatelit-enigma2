/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 */
#ifndef __lib_dvb_dvbapi_compat_h
#define __lib_dvb_dvbapi_compat_h

/*
 * DMX_SET_SOURCE, dmx_source_t si VIDEO_GET_FRAME_RATE au fost scoase din antetele
 * Linux (include/uapi/linux/dvb) incepand cu nucleul 4.14, dar driverele receptoarelor
 * le folosesc in continuare. Valorile sunt cele din antetele Linux v4.9:
 *   include/uapi/linux/dvb/dmx.h   (dmx_source, DMX_SET_SOURCE _IOW('o', 49, dmx_source_t))
 *   include/uapi/linux/dvb/video.h (VIDEO_GET_FRAME_RATE _IOR('o', 56, unsigned int))
 * Se definesc doar daca antetele sistemului nu le au deja.
 */

#include <sys/ioctl.h>
#include <linux/dvb/dmx.h>
#include <linux/dvb/video.h>

#ifndef DMX_SET_SOURCE
typedef enum dmx_source {
	DMX_SOURCE_FRONT0 = 0,
	DMX_SOURCE_FRONT1,
	DMX_SOURCE_FRONT2,
	DMX_SOURCE_FRONT3,
	DMX_SOURCE_DVR0   = 16,
	DMX_SOURCE_DVR1,
	DMX_SOURCE_DVR2,
	DMX_SOURCE_DVR3
} dmx_source_t;
#define DMX_SET_SOURCE _IOW('o', 49, dmx_source_t)
#endif

#ifndef VIDEO_GET_FRAME_RATE
#define VIDEO_GET_FRAME_RATE _IOR('o', 56, unsigned int)
#endif

#endif
