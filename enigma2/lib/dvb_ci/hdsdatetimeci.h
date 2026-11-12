/* HD Satelit (hdsatelit.com, moneasoftware.com), 2026 */
/*
 * Ora trimisa modulului CI (EN 50221, resursa Date-Time 00 24 00 41, obiectul date_time_response 9F 84 41).
 *
 * Raspunsul are 7 octeti: UTC_time (40 de biti: MJD pe 16 biti, apoi ora, minutul si secunda in BCD) si local_offset
 * (16 biti cu semn, in minute: ora locala = UTC + local_offset, adica tm_gmtoff / 60, pozitiv la est de Greenwich).
 * Inainte trimiteam 7 octeti de zero, adica 17.11.1858 00:00:00; unele module CI si CI+ verifica data (drepturi,
 * certificate). Functiile de aici nu au nevoie de enigma2 (numai aritmetica pe secundele din 1970), ca proba unitara
 * sa le compileze singure (teste/test_ora_ci_vu1_074.py).
 *
 * Idee din imaginea oficiala VU+ (depozitul open-vuplus, peticul fix-ci-datetime al enigma2, GPLv2; VU+ / Satco Europe
 * GmbH) si din VDR (aceeasi forma a raspunsului); codul de aici e scris de noi.
 */
#ifndef __dvbci_hdsdatetimeci_h
#define __dvbci_hdsdatetimeci_h

namespace hdsci
{

enum
{
	MJD_1970 = 40587,       /* MJD-ul zilei de 01.01.1970 */
	MJD_CEAS_PUS = 61041,   /* MJD-ul zilei de 01.01.2026: un ceas mai vechi nu e inca pus (nici din satelit, nici din retea) */
	ASTEPTARE_CEAS_MAX = 60 /* cat asteptam ceasul, in secunde, inainte sa raspundem cu ce are receptorul */
};

static inline unsigned char bcd(int v)
{
	return (unsigned char)(((v / 10) << 4) | (v % 10));
}

/* true cand ceasul arata o zi de dupa 01.01.2026 (secundele din 1970, UTC) */
static inline bool ceasPus(long long utc)
{
	return utc >= 0 && utc / 86400 + MJD_1970 >= MJD_CEAS_PUS;
}

/* Umple out[0..6] cu raspunsul date_time_response pentru ora utc (secunde din 1970, UTC) si diferenta fata de UTC
   in minute (ora locala = UTC + diferentaMinute). Intoarce lungimea, 7. */
static inline int codeazaDataOra(long long utc, int diferentaMinute, unsigned char out[7])
{
	if (utc < 0)
		utc = 0;
	long long zile = utc / 86400;
	int secunde = (int)(utc % 86400);
	unsigned int mjd = (unsigned int)((zile + MJD_1970) & 0xffff);
	out[0] = (unsigned char)(mjd >> 8);
	out[1] = (unsigned char)(mjd & 0xff);
	out[2] = bcd(secunde / 3600);
	out[3] = bcd((secunde / 60) % 60);
	out[4] = bcd(secunde % 60);
	/* fusurile reale stau intre -12 h si +14 h; ce e in afara (ceas stricat) se taie la o zi */
	if (diferentaMinute > 1440)
		diferentaMinute = 1440;
	if (diferentaMinute < -1440)
		diferentaMinute = -1440;
	unsigned int dif = (unsigned int)(diferentaMinute & 0xffff); /* complement fata de doi, pe 16 biti */
	out[5] = (unsigned char)(dif >> 8);
	out[6] = (unsigned char)(dif & 0xff);
	return 7;
}

} /* namespace hdsci */

#endif
