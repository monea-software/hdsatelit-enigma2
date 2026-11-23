/* Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 * DM900/DM920: native Silicon tuner units, selected by the running board.
 * Other boards and USB frontends keep their original values.
 *
 * Broadcom FBC tuners of DM900/DM920 (name "BCM45308X" in /proc/bus/nim_sockets, "BCM45208" from FE_GET_INFO):
 * the dm900 driver gives in FE_READ_SNR the Broadcom SNR estimate in 1/256 dB and always 0 in
 * FE_READ_SIGNAL_STRENGTH (no AGC reading). Without a formula the bar showed the raw SNR / 65536 (3 %) and 0 %.
 * Quality: raw * 100 / 256 hundredths of dB (same unit as the BCM4505/BCM4506 branch of frontend.cpp).
 * Level: when the driver gives no AGC (0..255), estimated from the quality percent with the usual three-segment
 * curve (under 35 % x1.8; under 70 % 63 + 0.8 per point; above 91 + 0.3 per point).
 */
#ifndef __lib_base_hdsdm920_h
#define __lib_base_hdsdm920_h

#include <stdio.h>
#include <string.h>
#include <time.h>

namespace hdsdm920
{
	inline bool esteModel()
	{
		static const bool nativ = []() {
			char model[32] = {0};
			FILE *f = fopen("/proc/stb/info/model", "r");
			if (!f)
				return false;
			bool valid = fscanf(f, "%31s", model) == 1;
			fclose(f);
			return valid && (!strcmp(model, "dm900") || !strcmp(model, "dm920"));
		}();
		return nativ;
	}

	inline bool tunerSilicon(const char *name)
	{
		return name && (!strcmp(name, "Si2166B") || !strcmp(name, "Si2166D") ||
			!strcmp(name, "Si2169C") ||
			!strcmp(name, "Si2169C DVB-C/MCNS") || !strcmp(name, "Si2169C DVB-T/DVB-T2") ||
			!strcmp(name, "Si2169D") ||
			!strcmp(name, "Si2169D DVB-C/MCNS") || !strcmp(name, "Si2169D DVB-T/DVB-T2"));
	}

	inline bool tunerBroadcom(const char *name)
	{
		return name && (strstr(name, "BCM45208") || strstr(name, "BCM45308"));
	}

	inline bool calitate(const char *name, int raw, int &db)
	{
		if (!esteModel())
			return false;
		if (tunerSilicon(name))
		{
			// si2166b/si2183: CNR quarter-dB byte multiplied by 25.
			db = raw;
			return true;
		}
		if (tunerBroadcom(name))
		{
			// BSAT SNR estimate, 1/256 dB -> hundredths of dB
			db = raw < 0 ? 0 : (raw * 100) >> 8;
			return true;
		}
		return false;
	}

	/* true when the level must be estimated from the quality: Broadcom tuner without an AGC reading */
	inline bool nivelEstimat(const char *name, int raw)
	{
		return esteModel() && tunerBroadcom(name) && raw >= 0 && raw <= 255;
	}

	/* quality on the 0..65536 scale -> estimated level on the 0..65535 scale */
	inline int nivelDinCalitate(int calitate16)
	{
		if (calitate16 <= 0)
			return 0;
		double p = calitate16 * 100.0 / 65535.0;
		double a = p < 35.0 ? p * 1.8 : (p < 70.0 ? 63.0 + (p - 35.0) * 0.8 : 91.0 + (p - 70.0) * 0.3);
		if (a > 100.0)
			a = 100.0;
		return (int)(a * 65535.0 / 100.0 + 0.5);
	}

	/* one raw-values log line per tuner and minute */
	inline bool jurnalAcum(int slot, time_t acum)
	{
		static time_t ultim[32];
		if (slot < 0 || slot >= 32)
			return false;
		if (ultim[slot] && acum >= ultim[slot] && acum - ultim[slot] < 60)
			return false;
		ultim[slot] = acum ? acum : 1;
		return true;
	}

	inline int nivel(const char *name, int raw)
	{
		// These drivers return one AGC byte through the uint16 DVB ioctl.
		return esteModel() && tunerSilicon(name) && raw >= 0 && raw <= 255 ? raw * 257 : raw;
	}
}
#endif
