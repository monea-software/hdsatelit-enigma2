/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsfastscantabele.h: citirea celor doua tabele FastScan ale operatorilor M7 (Skylink, Canal Digitaal, TV Vlaanderen,
 * TeleSAT, HD Austria, Diveo, AustriaSat...), cele pe care le cere cautarea rapida a canalelor (eFastScan, lib/dvb/hdsfastscan.h):
 *   - FNT (table_id 0xBC): reteaua, cu transponderele ei: descriptorul de livrare prin satelit (0x43), lista serviciilor
 *     (0x41: id si tip) si numerele canalelor (0x83, forma FastScan: 14 biti de numar si un semn „ascuns”, nu forma
 *     DVB pe 10 biti);
 *   - FST (table_id 0xBD): serviciile, fiecare cu onid/tsid/sid, PID-urile implicite (video, sunet, ECM, PCR) si
 *     descriptorul de serviciu (0x48: tipul, furnizorul, numele).
 * Sectiunile au forma lunga DVB (EN 300 468 cap. 5.1.1), cu CRC32 la coada; numerele de pe sateliti sunt BCD.
 *
 * Scris de la zero, fara clasele libdvbsi++, ca toata citirea sa fie pazita: fiecare lungime se verifica fata de capatul
 * buclei ei; o bucla care trece de capat strica numai elementul ei si ce urmeaza dupa el in aceeasi bucla, niciodata nu se
 * citeste in afara sectiunii. Numai functii pure, fara enigma2: lib/dvb/hdsfastscan.cpp le foloseste, iar probele de pe
 * PC (teste/fastscan/) le compileaza singure.
 */

#ifndef __lib_dvb_hdsfastscantabele_h
#define __lib_dvb_hdsfastscantabele_h

#include <stdint.h>
#include <stddef.h>
#include <string>
#include <vector>

#ifndef SWIG
namespace hdsfastscan
{

enum
{
	TID_FNT = 0xBC,
	TID_FST = 0xBD
};

/* un numar de canal din descriptorul 0x83 al FNT */
struct Canal
{
	uint16_t sid;
	uint16_t numar;   /* 14 biti */
	bool ascuns;
};

/* un serviciu din descriptorul 0x41 (lista serviciilor) al FNT */
struct ServiciuTp
{
	uint16_t sid;
	uint8_t tip;
};

/* un transponder din bucla FNT; valorile de livrare sunt deja traduse in unitatile enigma2 */
struct Transponder
{
	uint16_t tsid, onid;
	bool areLivrare;          /* descriptorul 0x43 a fost gasit si citit */
	unsigned int frecventa;   /* kHz */
	unsigned int simboluri;   /* simboluri pe secunda */
	int pozitie;              /* zecimi de grad, 0..3599 (vestul ca 3600 - x), ca orbital_position */
	int polarizare;           /* 0 H, 1 V, 2 L, 3 R (ca eDVBFrontendParametersSatellite) */
	int fec;                  /* ca eDVBFrontendParametersSatellite::FEC_* (necunoscut -> FEC_Auto) */
	int sistem;               /* 0 DVB-S, 1 DVB-S2 */
	int modulatie;            /* 0 auto, 1 QPSK, 2 8PSK, 3 16QAM (8PSK pe DVB-S -> QPSK) */
	int rolloff;              /* 0 = 0,35; 1 = 0,25; 2 = 0,20 */
	std::vector<ServiciuTp> servicii;
	std::vector<Canal> canale;
};

/* un serviciu din FST */
struct Serviciu
{
	uint16_t onid, tsid, sid;
	uint16_t pidVideo, pidSunet, pidEcmVideo, pidEcmSunet, pidPcr;
	bool areDescriptor;       /* descriptorul 0x48 a fost gasit */
	uint8_t tip;
	std::string furnizor;     /* octetii din tabela (se trec prin convertDVBUTF8 in enigma2) */
	std::string nume;
};

struct Fnt
{
	int versiune;
	int numarSectiune, ultimaSectiune;
	std::string numeRetea;    /* octetii descriptorului 0x40 */
	std::vector<Transponder> transpondere;
};

struct Fst
{
	int versiune;
	int numarSectiune, ultimaSectiune;
	std::vector<Serviciu> servicii;
};

/* CRC32 MPEG-2 (polinomul 0x04C11DB7) peste toata sectiunea, cu CRC-ul de la coada inclus: 0 = sectiune buna */
uint32_t crc32(const uint8_t *date, size_t lungime);

/* lungimea intreaga a sectiunii (3 + section_length), sau 0 daca antetul nu incape in lungime */
size_t lungimeSectiune(const uint8_t *s, size_t lungime);

/* citeste o sectiune FNT / FST intreaga (antetul, bucla, fara sa verifice CRC-ul: verifica cine o primeste);
   false = nu e tabela ceruta sau antetul e stricat (nimic citit); elementele stricate din bucle sunt sarite */
bool citesteFnt(const uint8_t *s, size_t lungime, Fnt &fnt);
bool citesteFst(const uint8_t *s, size_t lungime, Fst &fst);

/* descriptorul de livrare prin satelit (0x43): d indica eticheta, lungime = cati octeti sunt de la d pana la capatul
   buclei; false daca e prea scurt */
bool citesteLivrareSatelit(const uint8_t *d, size_t lungime, Transponder &tp);

/* pozitia orbitala din BCD (de pilda 0x0235 + est = 235; 0x0010 + vest = 3500) */
int pozitieOrbitala(uint16_t bcd, bool est);

/* imparte un fisier cu sectiuni lipite una dupa alta (forma fisierelor *_FST*.bin / *_FNT*.bin pe care le citeste pluginul
   din /tmp): fiecare element e o sectiune intreaga; o sectiune taiata la coada fisierului se lasa deoparte */
std::vector<std::string> imparteSectiuni(const std::string &continut);

}
#endif

#endif
