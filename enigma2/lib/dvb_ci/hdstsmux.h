/* HD Satelit (moneasoftware.com si hdsatelit.com, 2026): sursele fluxului din /proc/stb/tsmux, ca in enigma2 OE-Alliance de
   azi (sursele GPLv2 ale enigma2 OE-Alliance, lib/dvb_ci/dvbci.cpp: eDVBCIInterfaces::setInputSource scrie „CI<slot>” sau
   litera tunerului in input<tuner>, eDVBCISlot::setSource scrie litera tunerului in ci<slot>_input; la fel celelalte imagini
   OE-Alliance), oricate sloturi CI ar avea placa. Ramura veche „DM7025” din enigma2 (un singur slot: „CI” in input<tuner> si
   sursa modulului in input2) nu se mai foloseste: pe placile de azi cu un slot (AX HD51: alegerile „CI0 CI1 A B C D”, forumul
   479) „CI” singur nu e o sursa, iar input2 e intrarea demuxului 2. Fara enigma2: se probeaza pe PC
   (teste/test_cip_rutare_tsmux_077.py). */
/* Litera tunerului e 'A' + numarul lui, pana la Z (eDVBCISlot::getTunerLetter in OE-Alliance): tunerele FBC au 8
   demodulatoare pe un loc (Vu+ Duo 4K SE: input0..input19, alegerile A..V, CI0, CI1), deci tunerul 4 si urmatoarele sunt
   E, F, ... si nu A. Proba pe PC: teste/test_cir_tunere_ci_077.py. */
#ifndef __hdstsmux_h
#define __hdstsmux_h

#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <string>

#define HDS_TSMUX_DOSAR "/proc/stb/tsmux"
/* literele tunerelor, A..Z */
#define HDS_TSMUX_TUNERE 26

/* litera tunerului cu numarul dat (0 = A ... 25 = Z); gol in afara */
static inline std::string hdsTsmuxLitera(int tuner)
{
	if (tuner < 0 || tuner >= HDS_TSMUX_TUNERE)
		return std::string();
	return std::string(1, (char)('A' + tuner));
}

/* sursa modulului din slotul dat: CI<slot>; gol pentru un slot negativ */
static inline std::string hdsTsmuxCi(int slot)
{
	if (slot < 0)
		return std::string();
	char buf[16];
	snprintf(buf, sizeof(buf), "CI%d", slot);
	return std::string(buf);
}

/* numele vechi ale surselor, dupa numarul lor (0..3 = tunerele A..D, 4..7 = CI0..CI3); 0 = necunoscut. Raman pentru probe:
   hdsTsmuxLitera si hdsTsmuxCi dau aceleasi siruri pentru ele */
static inline const char *hdsTsmuxNume(int fel)
{
	static const char *nume[8] = { "A", "B", "C", "D", "CI0", "CI1", "CI2", "CI3" };
	return fel >= 0 && fel < 8 ? nume[fel] : 0;
}

/* scrie sursa in <dosar>/<fisier>; true cand driverul a primit-o (eroarea unei scrieri amanate o da fclose); in eroare,
   errno-ul (sau 0) */
static inline bool hdsTsmuxScrie(const char *dosar, const char *fisier, const char *sursa, int *eroare)
{
	std::string cale = std::string(dosar) + "/" + fisier;
	if (eroare)
		*eroare = 0;
	FILE *f = fopen(cale.c_str(), "w");
	if (!f)
	{
		if (eroare)
			*eroare = errno;
		return false;
	}
	bool bun = fputs(sursa, f) >= 0;
	if (fclose(f) != 0)
		bun = false;
	if (!bun && eroare)
		*eroare = errno;
	return bun;
}

/* primul cuvant din <dosar>/<fisier> (sursa aleasa acum); gol cand nu se poate citi */
static inline std::string hdsTsmuxCiteste(const char *dosar, const char *fisier)
{
	std::string cale = std::string(dosar) + "/" + fisier;
	char buf[32] = {0};
	FILE *f = fopen(cale.c_str(), "r");
	if (!f)
		return std::string();
	if (fscanf(f, "%31s", buf) != 1)
		buf[0] = 0;
	fclose(f);
	return std::string(buf);
}

#endif
