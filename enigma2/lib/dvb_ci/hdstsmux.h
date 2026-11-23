/* HD Satelit (moneasoftware.com si hdsatelit.com, 2026): rutarea fluxului prin /proc/stb/tsmux.
   input<N> primeste sursa tunerului sau CI<slot>; ci<slot>_input primeste sursa tunerului.
   Implementare proprie: numele numerotate din nim_sockets au prioritate numai cand apar exact in choices.
   Driverele cu A..Z si cele fara choices pastreaza rutarea veche, inclusiv demodulatoarele FBC.
   Aceeasi functie alege sursa la pornire, la alocarea/eliberarea CI si la autentificarea CI+.
   Probe PC: test_tsm1_tsmux_078.py, test_cip_rutare_tsmux_077.py, test_cir_tunere_ci_077.py. */
#ifndef __hdstsmux_h
#define __hdstsmux_h

#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <string>
#include <fstream>
#include <sstream>

#define HDS_TSMUX_DOSAR "/proc/stb/tsmux"
/* literele tunerelor, A..Z */
#define HDS_TSMUX_TUNERE 26

/* Numele intrarii fizice, publicat de driver. Nu deducem ordinea A1/A2 din choices. */
static inline std::string hdsTsmuxNumeTuner(int tuner)
{
	std::ifstream f("/proc/bus/nim_sockets");
	std::string rand;
	int slot = -1;
	while (std::getline(f, rand))
	{
		int n;
		if (sscanf(rand.c_str(), " NIM Socket %d:", &n) == 1)
			slot = n;
		else if (slot == tuner)
		{
			std::istringstream camp(rand);
			std::string cheie, valoare, rest;
			if (camp >> cheie >> valoare && cheie == "Input_Name:" && !(camp >> rest) &&
				valoare.size() <= 16 && valoare.find_first_not_of("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789") == std::string::npos)
				return valoare;
		}
	}
	return std::string();
}

/* Sursa tunerului: numele real numai daca driverul il accepta; A..Z pe placile vechi/FBC. */
static inline std::string hdsTsmuxLitera(int tuner)
{
	if (tuner < 0 || tuner >= HDS_TSMUX_TUNERE)
		return std::string();
	std::string litera(1, (char)('A' + tuner));
	char fisier[48];
	snprintf(fisier, sizeof(fisier), "/input%d_choices", tuner);
	std::ifstream f((std::string(HDS_TSMUX_DOSAR) + fisier).c_str());
	if (!f)
		return litera;
	std::string nume = hdsTsmuxNumeTuner(tuner), alegere;
	bool are_litera = false;
	while (f >> alegere)
	{
		// Numai numele numerotate schimba litera; un Input_Name comun FBC nu identifica demodulatorul.
		if (nume.size() > 1 && nume[0] >= 'A' && nume[0] <= 'Z' &&
			nume.find_first_not_of("0123456789", 1) == std::string::npos && alegere == nume)
			return nume;
		if (alegere == litera)
			are_litera = true;
	}
	return are_litera ? litera : std::string();
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

/* true cand input<tuner> primeste litera lui la pornirea interfetei: primele intrari (cele scrise si inainte: 4 cu doua
   sau mai multe sloturi, 2 cu unul) mereu, iar de la a cincea (input4) numai cand placa are input<tuner>_choices */
static inline bool hdsTsmuxIntrareLaPornire(const char *dosar, int tuner, int primele)
{
	if (tuner < 0 || tuner >= HDS_TSMUX_TUNERE)
		return false;
	if (tuner < primele)
		return true;
	if (tuner < 4)
		return false;
	char fisier[48];
	snprintf(fisier, sizeof(fisier), "/input%d_choices", tuner);
	std::string cale = std::string(dosar) + fisier;
	return access(cale.c_str(), R_OK) == 0;
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
