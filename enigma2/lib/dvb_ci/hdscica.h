/* HD Satelit (moneasoftware.com si hdsatelit.com, 2026): dispozitivul /dev/dvb/adapter0/caN care primeste cheia CI+
   (Content Control) data de modul. In enigma2 OE-Alliance dispozitivul e ca<demuxul canalului>, sau ca<demux+1> cu
   „Descrambling options” 2/3 (config.ci.N.alternative_ca_handling), implicit 0 pe toate placile. Pe unele placi (AX HD51,
   Broadcom: forumul 479, 13.11.2026) driverul refuza cheia si PID-urile pe ca<demux> („set key failed”): modulul da
   imaginea in clar ~2 s, trece pe cheia CI+, iar imaginea sta. Aici, cu „Automat” (implicit), receptorul incearca singur
   dispozitivele potrivite canalului si il pastreaza pe cel care primeste cheia. Fara nimic de la enigma2: se probeaza pe PC
   (teste/test_ci_dispozitiv_ca_075.py). */
#ifndef __hdscica_h
#define __hdscica_h

#include <stdlib.h>
#include <string.h>

/* felurile dispozitivului, fata de demuxul canalului (acelasi numar se tine minte pe disc) */
enum
{
	HDS_CA_DATE = 0,         /* ca<demuxul de date al canalului>, ca in OE-Alliance cu optiunea 0 */
	HDS_CA_DATE_PLUS1 = 1,   /* ca<demux+1>, ca in OE-Alliance cu optiunea 2 („Offset CA device index”) */
	HDS_CA_DECODOR = 2,      /* ca<demuxul decodorului>, cand e altul decat cel de date */
	HDS_CA_FELURI = 3
};

/* config.ci.N.alternative_ca_handling = „auto”: dispozitivul il alege receptorul */
#define HDS_CA_AUTOMAT (-1)

/* felul care a primit cheia ultima data, pe slot (un rand: 0, 1 sau 2) */
#define HDS_CA_FISIER "/etc/enigma2/hdsatelit/ci%d-dispozitiv-ca"

/* felul incercat intai pe placa (configure.ac: HDS_CI_CA_INTAI, dupa masina); altfel ca in OE-Alliance */
#ifdef HDS_CI_CA_INTAI
#define HDS_CA_INTAI_PLACA HDS_CI_CA_INTAI
#else
#define HDS_CA_INTAI_PLACA HDS_CA_DATE
#endif

/* textul setarii -> optiunea: „0”-„3” alese de mana (ca in OE-Alliance), orice altceva (auto, lipsa) = automat */
static inline int hdsCaOptiune(const char *text)
{
	if (text && text[0] >= '0' && text[0] <= '3' && text[1] == '\0')
		return text[0] - '0';
	return HDS_CA_AUTOMAT;
}

/* felul tinut minte pe disc: „0”-„2”, altfel -1 (necunoscut) */
static inline int hdsCaFel(const char *text)
{
	if (text && text[0] >= '0' && text[0] < '0' + HDS_CA_FELURI && (text[1] == '\0' || text[1] == '\n'))
		return text[0] - '0';
	return -1;
}

/* Dispozitivele de incercat, in ordine, fara dubluri: ca[] numerele caN, fel[] felul fiecaruia; intoarce cate sunt.
   optiune: hdsCaOptiune (alese de mana = un singur dispozitiv, exact ca in OE-Alliance); ales: felul care a primit
   cheia ultima data (-1 necunoscut); intai: felul placii (HDS_CA_INTAI_PLACA); demux, decodor: demuxul de date si al
   decodorului canalului (-1 necunoscut). Fara demux de date nu e nimic de incercat. */
static inline int hdsCaCandidati(int optiune, int ales, int intai, int demux, int decodor, int *ca, int *fel, int max)
{
	if (demux < 0 || max <= 0)
		return 0;
	if (optiune != HDS_CA_AUTOMAT)
	{
		ca[0] = optiune > 1 ? demux + 1 : demux;
		fel[0] = optiune > 1 ? HDS_CA_DATE_PLUS1 : HDS_CA_DATE;
		return 1;
	}
	const int ordine[5] = { ales, intai, HDS_CA_DATE, HDS_CA_DECODOR, HDS_CA_DATE_PLUS1 };
	int n = 0;
	for (int i = 0; i < 5 && n < max; i++)
	{
		int d;
		switch (ordine[i])
		{
		case HDS_CA_DATE: d = demux; break;
		case HDS_CA_DATE_PLUS1: d = demux + 1; break;
		case HDS_CA_DECODOR: d = decodor; break;
		default: continue;
		}
		if (d < 0 || d > 15)
			continue;
		bool dublu = false;
		for (int j = 0; j < n; j++)
			if (ca[j] == d)
				dublu = true;
		if (dublu)
			continue;
		ca[n] = d;
		fel[n] = ordine[i];
		n++;
	}
	return n;
}

#endif
