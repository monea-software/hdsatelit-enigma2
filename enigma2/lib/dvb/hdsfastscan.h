/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsfastscan.h: eFastScan, cautarea rapida a canalelor dupa tabelele FastScan ale operatorilor M7 (Skylink CZ/SK pe 23,5E,
 * Canal Digitaal, TV Vlaanderen, TeleSAT, HD Austria, Diveo pe 19,2E...). Interfata e cea ceruta de pluginul FastScan din
 * OE-Alliance (SystemPlugins/FastScan): acelasi constructor, start(tuner), startFile(fnt, fst), getVersion(), semnalele
 * scanProgress (0..100) si scanCompleted (numarul canalelor gasite, -1 = nereusit). Codul e scris aici, de la zero.
 *
 * Ce face: acordeaza tunerul ales pe transponderul operatorului si citeste de pe PID-ul lui intai FST (0xBD, serviciile),
 * apoi FNT (0xBC, transponderele si numerele canalelor); cu startFile citeste aceleasi tabele din doua fisiere (sectiuni
 * lipite una dupa alta). Apoi, ca in OE-Alliance:
 *   - transponderele intra in lista canalelor (lamedb); cele de pe sateliti nesetati la tuner se sar cand dropUnconfigured;
 *   - serviciile noi intra cu numele, furnizorul, PID-ul video si PCR-ul din tabela (PID-ul de sunet nu: tipul lui nu se
 *     stie, il afla receptorul la prima pornire a canalului) si cu semnul dxNewFound; cele care exista primesc numele din
 *     tabela numai cand fixedserviceinfo (atunci si dxHoldName|dxNoSDT: o scanare obisnuita nu le mai schimba numele);
 *   - buchetul userbouquet.<operator fara spatii>.tv (si .radio, cu createRadioBouquet) se goleste si se umple in ordinea
 *     numerelor de canal; cu originalnumbering, golurile dintre numere se umplu cu semne numerotate „-”, ca numerele
 *     din receptor sa fie cele ale operatorului; fara mai multe buchete (config.usage.multibouquet) se umple Favoritele;
 *   - lista se scrie pe disc (lamedb si buchetele).
 * Tabelele se citesc din cititorul de sectiuni al enigma2 (CRC verificat); citirea lor e lib/dvb/hdsfastscantabele.h.
 */

#ifndef __lib_dvb_hdsfastscan_h
#define __lib_dvb_hdsfastscan_h

#include <lib/base/object.h>
#include <lib/python/connections.h>
#include <lib/dvb/idvb.h>
#include <lib/dvb/frontendparms.h>

#ifndef SWIG
#include <lib/dvb/idemux.h>
#include <lib/dvb/esection.h>
#include <lib/base/ebase.h>
#include <lib/dvb/hdsfastscantabele.h>
#include <map>
#include <string>
#include <vector>

/* adunarea sectiunilor intregi ale unei tabele FastScan (asa cum vin din demux, cu CRC-ul bun), cu progresul */
class eHdsSectiuniFastScan: public eGTable
{
	std::map<unsigned int, std::string> m_sectiuni;
	unsigned int m_cate;
protected:
	int createTable(unsigned int nr, const __u8 *data, unsigned int max);
public:
	eHdsSectiuniFastScan(): eGTable(false), m_cate(0) {}
	/* sectiunile in ordinea numerelor lor */
	std::vector<std::string> sectiuni() const;
	/* o sectiune citita din fisier (fara demux); 1 = tabela e intreaga */
	int adaugaDinFisier(const std::string &sectiune);
	sigc::signal<void(int, int)> progres;
};
#endif

class eFastScan: public sigc::trackable, public iObject
{
	DECLARE_REF(eFastScan);
#ifndef SWIG
	int m_pid;
	std::string m_operator, m_numeFisier;
	eDVBFrontendParametersSatellite m_transponder;
	bool m_numerotareOriginala, m_numeFixe, m_buchetRadio, m_faraNesetati;
	int m_versiune;

	eUsePtr<iDVBChannel> m_canal;
	ePtr<iDVBDemux> m_demux;
	ePtr<eConnection> m_stareConexiune;
	int m_stare;
	int m_rezultat;
	ePtr<eTimer> m_sfarsit, m_paza;
	ePtr<eHdsSectiuniFastScan> m_fst, m_fnt;

	void stareCanal(iDVBChannel *canal);
	void progresFst(int cate, int din);
	void progresFnt(int cate, int din);
	void gataFst(int eroare);
	void gataFnt(int eroare);
	void elibereaza();
	void termina(int rezultat);
	void laSfarsit();
	void faraSemnal();
	int aplica(const std::vector<std::string> &fnt, const std::vector<std::string> &fst);
#endif
public:
	eFastScan(int pid, const char *providername, eDVBFrontendParametersSatellite transponderparameters, bool originalnumbering = false, bool fixedserviceinfo = false, bool createRadioBouquet = false, bool dropunconfigured = true);
	~eFastScan();

	void start(int frontendid = 0);
	void startFile(const char *fnt, const char *fst);
	int getVersion();

	PSignal1<void, int> scanProgress;
	PSignal1<void, int> scanCompleted;
};

#endif
