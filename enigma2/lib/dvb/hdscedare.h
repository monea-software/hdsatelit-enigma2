/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 */
#ifndef __lib_dvb_hdscedare_h
#define __lib_dvb_hdscedare_h

/*
 * Channel uses that give way to a zap.
 *
 * A channel (one transponder on one tuner) is shared by everything that needs that transponder. Each
 * eDVBServicePMTHandler holds two uses of it: its own and the one of its SDT scan; the resource manager holds one more
 * while it is the cached channel. canAllocateChannel takes the channel of the live service (the "ignore" channel) as
 * free when only the live service uses it: 2 uses, or 3 when it is also the cached channel.
 *
 * Some users of a channel are network streams which stop as soon as the live service needs their tuner: the TV in the
 * browser and the external players (Components/HdsTransmisie.py, Navigation.playServiceExtensions) and the local stream
 * server of the DAB+ / DVB-T2 relays (Hds/DabT2/server8001.py, stopped by the zap extension of the relays). Their
 * recordings are marked (iRecordableService::setYieldsToZap). The PMT handler of a marked recording adds the uses it
 * holds on its channel to the yielding uses of that channel (eDVBChannel::getYieldingUseCount) and takes exactly the
 * same number back before it lets the channel go (free(), also from its destructor), so a count cannot outlive the
 * recording that holds it.
 *
 * Only a zap query leaves the yielding uses out (eDVBZapQuery: the channel list opens one while it paints, so a
 * channel that the live service could switch to is not drawn grey). Every other question, such as whether a stream or
 * a recording can start now without stopping anything, still sees the tuner as busy. A real recording (timer, instant
 * recording) is never marked: the channels it keeps from starting stay grey.
 */

// ==== HDS_CEDARE_INCEPUT ====
// The arithmetic, without headers and side effects: built and tested alone on a PC (teste/test_lista_gri_transmisie.py).
// eDVBResourceManager::canAllocateChannel (dvb.cpp) does what it decides.
namespace hdscedare
{
	enum
	{
		LIVE_USES = 2,   // one PMT handler: its own use of the channel and the one of its SDT scan
		CACHE_USES = 1   // the resource manager while the channel is its cached channel
	};

	/* the uses of a channel that do not give way: all of them, or without the yielding ones in a zap query */
	inline int fixedUses(int uses, int yielding, bool zap)
	{
		int fixed = zap ? uses - yielding : uses;
		return fixed > 0 ? fixed : 0;
	}

	/* the channel of the live service (the ignored one) is used by the live service alone (and the cache): its tuner
	   counts as free, because the live service would leave it */
	inline bool liveOnly(int uses, int yielding, bool cached, bool zap)
	{
		return fixedUses(uses, yielding, zap) == LIVE_USES + (cached ? CACHE_USES : 0);
	}

	/* in a zap query, any channel held only by users that give way (and the cache) counts as free as well */
	inline bool yieldingOnly(int uses, int yielding, bool cached, bool zap)
	{
		return zap && yielding > 0 && fixedUses(uses, yielding, zap) == (cached ? CACHE_USES : 0);
	}

	/* the tuner of the channel counts as free for this question */
	inline bool tunerFree(bool ignored, int uses, int yielding, bool cached, bool zap)
	{
		if (ignored && liveOnly(uses, yielding, cached, zap))
			return true;
		return yieldingOnly(uses, yielding, cached, zap);
	}

	/* the uses a PMT handler holds on its channel: its own and the one of its SDT scan, when it has one */
	inline int handlerUses(bool has_channel, bool has_scan)
	{
		return has_channel ? 1 + (has_scan ? 1 : 0) : 0;
	}
}
// ==== HDS_CEDARE_SFARSIT ====

#endif
