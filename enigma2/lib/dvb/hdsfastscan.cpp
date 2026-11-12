/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsfastscan.cpp: eFastScan, cautarea rapida a canalelor dupa tabelele FastScan (vezi hdsfastscan.h).
 *
 * Paza: tabelele se elibereaza numai la pornirea urmatoare sau la distrugere (niciodata in semnalul lor), iar sfarsitul
 * cautarii (canalul eliberat, scanCompleted) vine dintr-un ceas separat, nu din semnalul canalului sau al cititorului de
 * sectiuni: Python-ul poate sterge obiectul chiar in scanCompleted, deci dupa el nu se mai atinge nimic.
 */

#include <lib/dvb/hdsfastscan.h>
#include <lib/dvb/db.h>
#include <lib/dvb/dvb.h>
#include <lib/dvb/sec.h>
#include <lib/dvb/frontend.h>
#include <lib/base/ebase.h>
#include <lib/base/eerror.h>
#include <lib/base/estring.h>
#include <lib/base/nconfig.h>
#include <stdio.h>
#include <string.h>
#include <algorithm>

/* ---- adunarea sectiunilor ---- */

int eHdsSectiuniFastScan::createTable(unsigned int nr, const __u8 *data, unsigned int max)
{
	size_t total = hdsfastscan::lungimeSectiune(data, 4096);
	if (!total || !max || nr >= max)
		return 0;
	if (m_cate && max != m_cate)
		m_sectiuni.clear(); /* tabela s-a schimbat intre timp: se ia de la capat */
	m_cate = max;
	m_sectiuni[nr] = std::string((const char *)data, total);
	/*emit*/ progres((int)m_sectiuni.size(), (int)max);
	return m_sectiuni.size() >= max ? 1 : 0;
}

int eHdsSectiuniFastScan::adaugaDinFisier(const std::string &sectiune)
{
	const __u8 *d = (const __u8 *)sectiune.data();
	if (sectiune.size() < 12)
		return 0;
	if (hdsfastscan::crc32(d, sectiune.size()) != 0)
	{
		eDebug("[eFastScan] sectiune din fisier cu CRC gresit (tabela %02x, nr %d), sarita", d[0], d[6]);
		return 0;
	}
	return createTable(d[6], d, (unsigned int)d[7] + 1);
}

std::vector<std::string> eHdsSectiuniFastScan::sectiuni() const
{
	std::vector<std::string> v;
	for (std::map<unsigned int, std::string>::const_iterator i = m_sectiuni.begin(); i != m_sectiuni.end(); ++i)
		v.push_back(i->second);
	return v;
}

/* ---- eFastScan ---- */

DEFINE_REF(eFastScan);

eFastScan::eFastScan(int pid, const char *providername, eDVBFrontendParametersSatellite transponderparameters, bool originalnumbering, bool fixedserviceinfo, bool createRadioBouquet, bool dropunconfigured)
	: m_pid(pid), m_operator(providername ? providername : ""), m_transponder(transponderparameters),
	  m_numerotareOriginala(originalnumbering), m_numeFixe(fixedserviceinfo), m_buchetRadio(createRadioBouquet),
	  m_faraNesetati(dropunconfigured), m_versiune(-1), m_stare(-1), m_rezultat(-1)
{
	/* numele fisierului buchetului: numele operatorului fara spatii (userbouquet.SkylinkCzechRepublic.tv) */
	m_numeFisier = replace_all(m_operator, " ", "");
	m_transponder.no_rotor_command_on_tune = false;
	m_sfarsit = eTimer::create(eApp);
	CONNECT(m_sfarsit->timeout, eFastScan::laSfarsit);
	m_paza = eTimer::create(eApp);
	CONNECT(m_paza->timeout, eFastScan::faraSemnal);
}

eFastScan::~eFastScan()
{
	if (m_sfarsit)
		m_sfarsit->stop();
	if (m_paza)
		m_paza->stop();
}

int eFastScan::getVersion()
{
	return m_versiune;
}

void eFastScan::elibereaza()
{
	m_stareConexiune = 0;
	m_demux = 0;
	m_canal = 0;
}

void eFastScan::termina(int rezultat)
{
	m_paza->stop();
	m_rezultat = rezultat;
	m_sfarsit->start(0, true);
}

void eFastScan::laSfarsit()
{
	elibereaza();
	int rezultat = m_rezultat;
	if (rezultat >= 0)
		/*emit*/ scanProgress(100);
	/*emit*/ scanCompleted(rezultat); /* ultimul lucru: obiectul poate fi sters aici */
}

void eFastScan::start(int frontendid)
{
	m_versiune = -1;
	m_stare = -1;
	m_fst = 0;
	m_fnt = 0;
	elibereaza();

	ePtr<eDVBResourceManager> res;
	eDVBResourceManager::getInstance(res);
	ePtr<iDVBFrontend> fe;
	if (!res || res->allocateRawChannel(m_canal, frontendid) || !m_canal)
	{
		eDebug("[eFastScan] tunerul %d nu se poate lua pentru cautarea rapida", frontendid);
		termina(-1);
		return;
	}
	if (m_canal->getFrontend(fe) || !fe || m_canal->getDemux(m_demux) || !m_demux)
	{
		eDebug("[eFastScan] tunerul %d nu are frontend sau demux", frontendid);
		termina(-1);
		return;
	}
	m_canal->connectStateChange(sigc::mem_fun(*this, &eFastScan::stareCanal), m_stareConexiune);

	ePtr<eDVBFrontendParameters> parm = new eDVBFrontendParameters();
	parm->setDVBS(m_transponder);
	eDebug("[eFastScan] %s: tunerul %d pe %d kHz, %d sim/s, pozitia %d, PID %d", m_operator.c_str(), frontendid,
		m_transponder.frequency, m_transponder.symbol_rate, m_transponder.orbital_position, m_pid);
	if (fe->tune(*parm))
	{
		termina(-1);
		return;
	}
	/* paza: fara semnal in 120 s (si cu motorul care se roteste de la un capat la altul) cautarea se opreste; un tuner fara
	   antena poate ramane in acordare fara sa spuna vreodata „nereusit” */
	m_paza->start(120000, true);
}

void eFastScan::faraSemnal()
{
	if (m_fst)
		return;
	eDebug("[eFastScan] %s: fara semnal in 120 s pe transponderul operatorului", m_operator.c_str());
	termina(-1);
}

void eFastScan::stareCanal(iDVBChannel *canal)
{
	int stare;
	if (!canal || canal->getState(stare) || stare == m_stare)
		return;
	m_stare = stare;
	if (stare == iDVBChannel::state_ok && !m_fst)
	{
		m_paza->stop();
		/* semnal prins: intai serviciile (FST), apoi reteaua (FNT), de pe acelasi PID */
		m_fst = new eHdsSectiuniFastScan();
		m_fnt = new eHdsSectiuniFastScan();
		CONNECT(m_fst->progres, eFastScan::progresFst);
		CONNECT(m_fnt->progres, eFastScan::progresFnt);
		CONNECT(m_fst->tableReady, eFastScan::gataFst);
		CONNECT(m_fnt->tableReady, eFastScan::gataFnt);
		eDVBTableSpec spec;
		spec.pid = m_pid;
		spec.tid = hdsfastscan::TID_FST;
		spec.timeout = 5000;
		spec.flags = eDVBTableSpec::tfAnyVersion | eDVBTableSpec::tfHaveTID | eDVBTableSpec::tfCheckCRC | eDVBTableSpec::tfHaveTimeout;
		m_fst->start(m_demux, spec);
	}
	else if (stare == iDVBChannel::state_failed && !m_fst)
	{
		eDebug("[eFastScan] %s: fara semnal pe transponderul operatorului", m_operator.c_str());
		termina(-1);
	}
}

void eFastScan::progresFst(int cate, int din)
{
	if (din > 0)
		/*emit*/ scanProgress(cate * 45 / din);
}

void eFastScan::progresFnt(int cate, int din)
{
	if (din > 0)
		/*emit*/ scanProgress(45 + cate * 45 / din);
}

void eFastScan::gataFst(int eroare)
{
	eDebug("[eFastScan] FST gata (%d)", eroare);
	if (eroare || !m_demux)
	{
		termina(-1);
		return;
	}
	eDVBTableSpec spec;
	spec.pid = m_pid;
	spec.tid = hdsfastscan::TID_FNT;
	spec.timeout = 5000;
	spec.flags = eDVBTableSpec::tfAnyVersion | eDVBTableSpec::tfHaveTID | eDVBTableSpec::tfCheckCRC | eDVBTableSpec::tfHaveTimeout;
	m_fnt->start(m_demux, spec);
}

void eFastScan::gataFnt(int eroare)
{
	eDebug("[eFastScan] FNT gata (%d)", eroare);
	if (eroare)
	{
		termina(-1);
		return;
	}
	termina(aplica(m_fnt->sectiuni(), m_fst->sectiuni()));
}

static bool citesteFisier(const char *cale, std::string &continut)
{
	continut.clear();
	if (!cale)
		return false;
	FILE *f = fopen(cale, "rb");
	if (!f)
		return false;
	char tampon[4096];
	size_t n;
	while ((n = fread(tampon, 1, sizeof(tampon), f)) > 0 && continut.size() < 4 * 1024 * 1024)
		continut.append(tampon, n);
	fclose(f);
	return true;
}

void eFastScan::startFile(const char *fnt, const char *fst)
{
	m_versiune = -1;
	m_rezultat = -1;
	m_sfarsit->stop();
	m_paza->stop();
	std::string continutFnt, continutFst;
	bool are = citesteFisier(fst, continutFst) && citesteFisier(fnt, continutFnt);
	int rezultat = -1;
	if (are)
	{
		/* aceeasi adunare ca din demux (CRC verificat, sectiunile in ordine, cele in plus ignorate) */
		ePtr<eHdsSectiuniFastScan> tFst = new eHdsSectiuniFastScan(), tFnt = new eHdsSectiuniFastScan();
		std::vector<std::string> s = hdsfastscan::imparteSectiuni(continutFst);
		for (size_t i = 0; i < s.size(); ++i)
			if (s[i].size() && (__u8)s[i][0] == hdsfastscan::TID_FST && tFst->adaugaDinFisier(s[i]))
				break;
		s = hdsfastscan::imparteSectiuni(continutFnt);
		for (size_t i = 0; i < s.size(); ++i)
			if (s[i].size() && (__u8)s[i][0] == hdsfastscan::TID_FNT && tFnt->adaugaDinFisier(s[i]))
				break;
		std::vector<std::string> sFst = tFst->sectiuni(), sFnt = tFnt->sectiuni();
		if (!sFst.empty() && !sFnt.empty())
			rezultat = aplica(sFnt, sFst);
	}
	else
		eDebug("[eFastScan] fisierele %s / %s nu se pot citi", fnt ? fnt : "-", fst ? fst : "-");
	if (rezultat >= 0)
		/*emit*/ scanProgress(100);
	/*emit*/ scanCompleted(rezultat);
}

/* tipurile de serviciu de radio (EN 300 468 tabelul 87): 0x02 radio, 0x07 FM, 0x0A radio cu codare avansata */
static bool eRadio(int tip)
{
	return tip == 0x02 || tip == 0x07 || tip == 0x0A;
}

/* buchetul operatorului (userbouquet.<nume>.tv/.radio): golit daca exista, facut si pus in bouquets.tv/.radio daca nu */
static eBouquet *buchetulOperatorului(eDVBDB *db, const std::string &fisier, int tip)
{
	std::string cerere = "FROM BOUQUET \"" + fisier + "\" ORDER BY bouquet";
	eServiceReference ref(eServiceReference::idDVB, eServiceReference::flagDirectory, cerere);
	ref.setData(0, tip);
	eBouquet *b = NULL;
	if (!db->getBouquet(ref, b) && b)
	{
		b->m_services.clear();
		return b;
	}
	eServiceReference radacina(eServiceReference::idDVB, eServiceReference::flagDirectory,
		tip == 2 ? "FROM BOUQUET \"bouquets.radio\" ORDER BY bouquet" : "FROM BOUQUET \"bouquets.tv\" ORDER BY bouquet");
	eBouquet *r = NULL;
	if (!db->getBouquet(radacina, r) && r)
	{
		if (std::find(r->m_services.begin(), r->m_services.end(), ref) == r->m_services.end())
		{
			r->m_services.push_front(ref);
			r->flushChanges();
		}
	}
	db->loadBouquet(fisier.c_str()); /* fisierul nu exista inca: intra in lista buchetelor gol */
	b = NULL;
	db->getBouquet(ref, b);
	if (b)
		b->m_services.clear();
	return b;
}

/* buchetul umplut in ordinea numerelor; cu numerotarea operatorului golurile devin semne numerotate „-” */
static void umpleBuchet(eBouquet *b, const std::string &nume, const std::map<int, eServiceReferenceDVB> &canale, bool numerotareOriginala, bool favorite)
{
	if (!b)
		return;
	if (!favorite)
		b->m_bouquet_name = nume;
	else
	{
		/* Favoritele omului raman: se scot numai canalele care intra din nou, ca sa nu apara de doua ori */
		for (std::map<int, eServiceReferenceDVB>::const_iterator c = canale.begin(); c != canale.end(); ++c)
			b->m_services.remove(c->second);
		numerotareOriginala = false;
	}
	int numar = 1;
	for (std::map<int, eServiceReferenceDVB>::const_iterator c = canale.begin(); c != canale.end(); ++c)
	{
		if (numerotareOriginala)
			for (; numar < c->first; ++numar)
			{
				eServiceReference semn(eServiceReference::idDVB, eServiceReference::isMarker | eServiceReference::isNumberedMarker);
				semn.setName("-");
				b->m_services.push_back(semn);
			}
		b->m_services.push_back(c->second);
		++numar;
	}
	b->flushChanges();
}

int eFastScan::aplica(const std::vector<std::string> &sFnt, const std::vector<std::string> &sFst)
{
	eDVBDB *db = eDVBDB::getInstance();
	if (!db)
		return -1;
	eDVBSatelliteEquipmentControl *sec = eDVBSatelliteEquipmentControl::getInstance();

	/* pozitia fiecarui transponder (tsid, onid) primit; tipul fiecarui serviciu din lista FNT */
	typedef std::pair<uint16_t, uint16_t> CheieTp;
	typedef std::pair<CheieTp, uint16_t> CheieSv;
	std::map<CheieTp, int> pozitii;
	std::map<CheieSv, int> tipFnt, tipFst;
	std::vector<hdsfastscan::Fnt> retele;
	std::vector<hdsfastscan::Fst> servicii;

	for (size_t i = 0; i < sFnt.size(); ++i)
	{
		hdsfastscan::Fnt f;
		if (hdsfastscan::citesteFnt((const uint8_t *)sFnt[i].data(), sFnt[i].size(), f))
			retele.push_back(f);
	}
	for (size_t i = 0; i < sFst.size(); ++i)
	{
		hdsfastscan::Fst f;
		if (hdsfastscan::citesteFst((const uint8_t *)sFst[i].data(), sFst[i].size(), f))
			servicii.push_back(f);
	}
	if (retele.empty() || servicii.empty())
		return -1;
	m_versiune = retele[0].versiune;

	for (size_t i = 0; i < servicii.size(); ++i)
		for (size_t j = 0; j < servicii[i].servicii.size(); ++j)
		{
			const hdsfastscan::Serviciu &sv = servicii[i].servicii[j];
			if (sv.areDescriptor)
				tipFst[CheieSv(CheieTp(sv.tsid, sv.onid), sv.sid)] = sv.tip;
		}

	std::map<int, eServiceReferenceDVB> tv, radio;
	int sarite = 0;
	for (size_t i = 0; i < retele.size(); ++i)
		for (size_t j = 0; j < retele[i].transpondere.size(); ++j)
		{
			const hdsfastscan::Transponder &tp = retele[i].transpondere[j];
			if (!tp.areLivrare)
				continue;
			if (m_faraNesetati && tp.pozitie != m_transponder.orbital_position && sec && !sec->isOrbitalPositionConfigured(tp.pozitie))
			{
				++sarite;
				continue;
			}
			CheieTp cheie(tp.tsid, tp.onid);
			pozitii[cheie] = tp.pozitie;

			eDVBFrontendParametersSatellite sat;
			memset(&sat, 0, sizeof(sat));
			sat.setMultistreamDefaults();
			sat.no_rotor_command_on_tune = false;
			sat.frequency = tp.frecventa;
			sat.symbol_rate = tp.simboluri;
			sat.polarisation = tp.polarizare;
			sat.fec = tp.fec;
			sat.inversion = eDVBFrontendParametersSatellite::Inversion_Unknown;
			sat.orbital_position = tp.pozitie;
			sat.system = tp.sistem;
			sat.modulation = tp.modulatie;
			sat.rolloff = tp.rolloff;
			sat.pilot = eDVBFrontendParametersSatellite::Pilot_Unknown;
			ePtr<eDVBFrontendParameters> parm = new eDVBFrontendParameters();
			parm->setDVBS(sat);
			eDVBChannelID chid(eDVBNamespace(tp.pozitie << 16), eTransportStreamID(tp.tsid), eOriginalNetworkID(tp.onid));
			db->addChannelToList(chid, parm);

			for (size_t k = 0; k < tp.servicii.size(); ++k)
				tipFnt[CheieSv(cheie, tp.servicii[k].sid)] = tp.servicii[k].tip;
			for (size_t k = 0; k < tp.canale.size(); ++k)
			{
				const hdsfastscan::Canal &c = tp.canale[k];
				CheieSv cs(cheie, c.sid);
				int tip = tipFst.count(cs) ? tipFst[cs] : (tipFnt.count(cs) ? tipFnt[cs] : 1);
				eServiceReferenceDVB ref(eDVBNamespace(tp.pozitie << 16), eTransportStreamID(tp.tsid), eOriginalNetworkID(tp.onid), eServiceID(c.sid), tip);
				if (m_buchetRadio && eRadio(tip))
					radio[c.numar] = ref;
				else
					tv[c.numar] = ref;
			}
		}
	if (sarite)
		eDebug("[eFastScan] %d transpondere sarite: sateliti nesetati la tuner", sarite);

	/* serviciile: noi din tabela; cele care exista primesc numele operatorului numai cu numele fixe */
	int noi = 0;
	for (size_t i = 0; i < servicii.size(); ++i)
		for (size_t j = 0; j < servicii[i].servicii.size(); ++j)
		{
			const hdsfastscan::Serviciu &sv = servicii[i].servicii[j];
			CheieTp cheie(sv.tsid, sv.onid);
			std::map<CheieTp, int>::const_iterator p = pozitii.find(cheie);
			if (p == pozitii.end())
				continue; /* transponder necunoscut sau sarit */
			CheieSv cs(cheie, sv.sid);
			int tip = sv.areDescriptor ? sv.tip : (tipFnt.count(cs) ? tipFnt[cs] : 1);
			eServiceReferenceDVB ref(eDVBNamespace(p->second << 16), eTransportStreamID(sv.tsid), eOriginalNetworkID(sv.onid), eServiceID(sv.sid), tip);
			std::string nume = convertDVBUTF8(sv.nume), furnizor = convertDVBUTF8(sv.furnizor);
			int semne = m_numeFixe ? (eDVBService::dxHoldName | eDVBService::dxNoSDT) : 0;
			ePtr<eDVBService> existent;
			if (!db->getService(ref, existent) && existent)
			{
				if (m_numeFixe && sv.areDescriptor)
				{
					existent->m_service_name = nume;
					existent->genSortName();
					existent->m_provider_name = furnizor;
				}
				existent->m_flags |= semne;
				continue;
			}
			ePtr<eDVBService> s = new eDVBService();
			s->m_service_name = nume;
			s->genSortName();
			s->m_provider_name = furnizor;
			/* PID-ul video si PCR-ul ajuta la prima pornire; PID-ul de sunet nu (tipul lui nu e in tabela) */
			if (sv.pidVideo && sv.pidVideo != 0x1fff)
				s->setCacheEntry(eDVBService::cVPID, sv.pidVideo);
			if (sv.pidPcr && sv.pidPcr != 0x1fff)
				s->setCacheEntry(eDVBService::cPCRPID, sv.pidPcr);
			s->m_flags = semne | eDVBService::dxNewFound;
			db->addService(ref, s);
			++noi;
		}

	std::string multe;
	bool multeBuchete = true;
	if (!ePythonConfigQuery::getConfigValue("config.usage.multibouquet", multe))
		multeBuchete = !(multe == "False" || multe == "false");

	if (multeBuchete)
		umpleBuchet(buchetulOperatorului(db, "userbouquet." + m_numeFisier + ".tv", 1), m_operator, tv, m_numerotareOriginala, false);
	else
	{
		eServiceReference fav(eServiceReference::idDVB, eServiceReference::flagDirectory, "FROM BOUQUET \"userbouquet.favourites.tv\" ORDER BY bouquet");
		eBouquet *b = NULL;
		if (!db->getBouquet(fav, b))
			umpleBuchet(b, m_operator, tv, m_numerotareOriginala, true);
	}
	if (!radio.empty())
	{
		if (multeBuchete)
			umpleBuchet(buchetulOperatorului(db, "userbouquet." + m_numeFisier + ".radio", 2), m_operator, radio, m_numerotareOriginala, false);
		else
		{
			eServiceReference fav(eServiceReference::idDVB, eServiceReference::flagDirectory, "FROM BOUQUET \"userbouquet.favourites.radio\" ORDER BY bouquet");
			eBouquet *b = NULL;
			if (!db->getBouquet(fav, b))
				umpleBuchet(b, m_operator, radio, m_numerotareOriginala, true);
		}
	}
	db->saveServicelist();
	eDebug("[eFastScan] %s versiunea %d: %zu canale TV, %zu radio, %d servicii noi", m_operator.c_str(), m_versiune, tv.size(), radio.size(), noi);
	return tv.empty() ? -1 : (int)(tv.size() + radio.size());
}
