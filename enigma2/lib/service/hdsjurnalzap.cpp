/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsjurnalzap.cpp: jurnalul schimbarii de canal (vezi hdsjurnalzap.h). Scris de la zero. Pe firul principal; scrierea
 * pe disc o face firul din lib/base/hdsjurnal.cpp. Datele canalului (numele, transponderul) se cauta in lista de canale
 * numai cand se scrie un esec.
 */

#include <lib/service/hdsjurnalzap.h>
#include <lib/service/hdsreleut2.h>

#include <lib/base/hdsjurnal.h>
#include <lib/dvb/db.h>
#include <lib/dvb/dvb.h>
#include <lib/dvb/hdsjurnaltuner.h>
#include <libsig_comp.h>

#include <stdio.h>
#include <string.h>

namespace hdsjzap
{

static const char *const COMPONENTA = "zap";

static const char *codecVideo(int t)
{
	switch (t)
	{
	case 0: return "MPEG2";
	case 1: return "H264";
	case 3: return "VC1";
	case 4: return "MPEG4";
	case 5: return "VC1-SM";
	case 6: return "MPEG1";
	case 7: return "H265";
	case 16: return "AVS";
	default: return "?";
	}
}

static const char *codecSunet(int t)
{
	static const char *const T[] = { "MPEG", "AC3", "DTS", "AAC", "HE-AAC", "LPCM", "DTS-HD", "E-AC3" };
	return (t >= 0 && t < 8) ? T[t] : "?";
}

static char litera(int slot)
{
	return (slot >= 0 && slot < 26) ? (char)('A' + slot) : '?';
}

int Zap::s_fara_eveniment = 0;

Zap::Zap()
	: m_citeste_pts(0), m_ctx(0), m_activ(false), m_esec(false), m_avert(false), m_program_pmt(false), m_sunet_asteptat(false),
	m_t0(0), m_t_acordat(0), m_t_program(0), m_t_imagine(0),
	m_t_eveniment(0), m_pts(0), m_t_cadre(0), m_termen_pts(0), m_latime(-1), m_inaltime(-1), m_citiri(0), m_bune(0), m_pts_bun(false),
	m_ceas_pts(eTimer::create(eApp)),
	m_din_pts(false), m_t_miscare(0),
	m_slot(-1), m_vpid(-1), m_vtip(-1), m_apid(-1), m_atip(-1), m_criptat(-1), m_sid(0), m_releu(false),
	m_ceas(eTimer::create(eApp))
{
	CONNECT(m_ceas->timeout, Zap::faraImagine);
	CONNECT(m_ceas_pts->timeout, Zap::citestePts);
	memset(m_marcaje, 0, sizeof(m_marcaje));
	m_t_comanda = m_t_blocare = m_t_acordare_ceruta = 0;
	m_sec_ms = -1;
}

void Zap::pornire(const eServiceReferenceDVB &ref, bool masurat)
{
	m_ceas->stop();
	m_ceas_pts->stop();
	m_activ = masurat;
	m_esec = m_avert = false;
	m_program_pmt = m_sunet_asteptat = false;
	m_t0 = hdsjurnal::monotonMs();
	m_t_acordat = m_t_program = m_t_imagine = 0;
	m_t_eveniment = m_pts = m_t_cadre = m_termen_pts = 0;
	m_latime = m_inaltime = -1;
	m_citiri = m_bune = 0;
	m_pts_bun = false;
	m_din_pts = false;
	m_t_miscare = 0;
	memset(m_marcaje, 0, sizeof(m_marcaje));
	m_t_comanda = m_t_blocare = m_t_acordare_ceruta = 0;
	m_sec_ms = -1;
	m_slot = m_vpid = m_vtip = m_apid = m_atip = m_criptat = -1;
	m_sid = 0;
	/* releul T2-MI local: canal fara tunerul si fara acordarea lui (randul spune "releu T2-MI") */
	m_releu = masurat && hdsEsteReleuT2(ref.path);
	if (masurat)
		m_ref = ref;
}

static long dupa(long long t0, long long t)
{
	return t ? (long)(t - t0) : -1;
}

void Zap::textCine(char *buf, size_t n) const
{
	if (m_releu)
		snprintf(buf, n, "releu T2-MI");
	else
		snprintf(buf, n, "%c", litera(m_slot));
}

void Zap::textAcordare(char *buf, size_t n) const
{
	/* la releu tunerul e al releului: nici eventTuned, nici timpii frontend-ului nu tin de acest canal */
	if (m_releu)
		buf[0] = 0;
	else
		snprintf(buf, n, "acordare %ld ms, ", dupa(m_t0, m_t_acordat));
}

void Zap::marcaj(int etapa, long long t)
{
	if (m_activ && (!t || t >= m_t0) && etapa >= 0 && etapa < NR_MARCAJE && !m_marcaje[etapa])
		m_marcaje[etapa] = t ? t : hdsjurnal::monotonMs();
}

void Zap::acordare(const eDVBFrontend::TimpiZap &t)
{
	/* Un transponder reutilizat pastreaza marcajele acordarii vechi. */
	if (!m_activ || t.pornire_ms < m_t0 || t.comanda_ms < m_t0)
		return;
	m_t_comanda = t.comanda_ms;
	m_t_acordare_ceruta = t.pornire_ms;
	m_t_blocare = t.lock_ms;
	if (t.sec_start_ms >= m_t0 && t.sec_gata_ms >= t.sec_start_ms)
		m_sec_ms = (long)(t.sec_gata_ms - t.sec_start_ms);
}

void Zap::textMarcaje(char *buf, size_t n) const
{
	snprintf(buf, n, " | zap_t0 %lld ms | marcaje: pmt %ld ms, decodor %ld ms, ca_pmt %ld ms, "
		"comanda_tuner %ld ms, sec %ld ms, blocare %ld ms, pachet_video -1 ms, eveniment_video %ld ms, cadre %ld ms, "
		"acordare_ceruta %ld ms",
		m_t0, dupa(m_t0, m_marcaje[PMT_PRIMIT]), dupa(m_t0, m_marcaje[DECODOR_PREGATIT]),
		dupa(m_t0, m_marcaje[CA_PMT_TRIMIS]), dupa(m_t0, m_t_comanda), m_sec_ms,
		dupa(m_t0, m_t_blocare), dupa(m_t0, m_marcaje[EVENIMENT_VIDEO]), dupa(m_t0, m_t_cadre),
		dupa(m_t0, m_t_acordare_ceruta));
}

std::string Zap::numeCanal()
{
	std::string nume;
	ePtr<eDVBResourceManager> res;
	ePtr<iDVBChannelList> db;
	if (!eDVBResourceManager::getInstance(res) && !res->getChannelList(db) && db)
	{
		ePtr<eDVBService> s;
		if (!db->getService(m_ref, s) && s)
			nume = s->m_service_name;
	}
	for (size_t i = 0; i < nume.size(); ++i)
		if (nume[i] == '"')
			nume[i] = '\'';
	return nume;
}

void Zap::textCanalScurt(char *buf, size_t n)
{
	/* randurile reusite: numai numele si referinta (o cautare in lista de canale, ca la esec) */
	snprintf(buf, n, " | canal: nume=\"%s\" ref=%s", numeCanal().c_str(), m_ref.toString().c_str());
}

void Zap::textCanal(char *buf, size_t n)
{
	size_t f = 0;
	buf[0] = 0;
	std::string ref = m_ref.toString();
	std::string nume = numeCanal();
	char tp[160] = "?";
	ePtr<eDVBResourceManager> res;
	ePtr<iDVBChannelList> db;
	if (!eDVBResourceManager::getInstance(res) && !res->getChannelList(db) && db)
	{
		eDVBChannelID chid;
		m_ref.getChannelID(chid);
		ePtr<iDVBFrontendParameters> fp;
		int tip = -1;
		/* la releul T2-MI tp= vine din cale (hdsReleuT2Tp, mai jos), nu din lista de canale */
		if (!m_releu && !db->getChannelFrontendData(chid, fp) && fp && !fp->getSystem(tip))
		{
			if (tip == iDVBFrontend::feSatellite)
			{
				eDVBFrontendParametersSatellite p;
				if (!fp->getDVBS(p))
					hdsjtuner::textSat(tp, sizeof(tp), p);
			}
			else if (tip == iDVBFrontend::feCable)
			{
				eDVBFrontendParametersCable p;
				if (!fp->getDVBC(p))
					hdsjtuner::textCablu(tp, sizeof(tp), p);
			}
			else if (tip == iDVBFrontend::feTerrestrial)
			{
				eDVBFrontendParametersTerrestrial p;
				if (!fp->getDVBT(p))
					hdsjtuner::textTerestru(tp, sizeof(tp), p);
			}
		}
	}
	/* MI7 (15.11.2026): fluxul releului nu are transponder in lista; randul arata feed-ul si PLP-ul din cale, nu "tp=?" */
	if (m_releu)
	{
		std::string t2 = hdsReleuT2Tp(m_ref.path);
		if (!t2.empty())
			snprintf(tp, sizeof(tp), "%s", t2.c_str());
	}
	int sid = m_sid ? m_sid : m_ref.getServiceID().get();
	int r = snprintf(buf, n, "canal: nume=\"%s\" ref=%s tp=%s sid=0x%x", nume.c_str(), ref.c_str(), tp, sid);
	f = r > 0 ? (size_t)r : 0;
	if (f < n && m_vpid > 0)
		f += snprintf(buf + f, n - f, " vpid=0x%x %s", m_vpid, codecVideo(m_vtip));
	if (f < n && m_apid > 0)
		f += snprintf(buf + f, n - f, " apid=0x%x %s", m_apid, codecSunet(m_atip));
	if (f < n && m_criptat >= 0)
		snprintf(buf + f, n - f, " criptat=%s", m_criptat ? "da" : "nu");
}

void Zap::scrieEsec(const char *nivel, const char *motiv)
{
	char canal[600];
	char marcaje[340];
	textMarcaje(marcaje, sizeof(marcaje));
	textCanal(canal, sizeof(canal));
	char cine[16], acordare[40];
	textCine(cine, sizeof(cine));
	textAcordare(acordare, sizeof(acordare));
	long long acum = hdsjurnal::monotonMs();
	hdsjurnal::scrief(COMPONENTA, nivel, "zap", "%s %s dupa %ld ms (%sprogram %ld ms)%s | %s", cine,
		motiv, (long)(acum - m_t0), acordare, dupa(m_t0, m_t_program), marcaje, canal);
}

void Zap::eveniment(int ev, int slot)
{
	if (!m_activ)
		return;
	const char *motiv = 0;
	switch (ev)
	{
	case eDVBServicePMTHandler::eventTuned:
		if (!m_t_acordat)
		{
			m_t_acordat = hdsjurnal::monotonMs();
			m_slot = slot;
		}
		return;
	case eDVBServicePMTHandler::eventNoResources: motiv = "fara resurse (tuner sau demux ocupat)"; break;
	case eDVBServicePMTHandler::eventNoPAT: motiv = "fara PAT"; break;
	case eDVBServicePMTHandler::eventNoPATEntry: motiv = "serviciul lipseste din PAT"; break;
	case eDVBServicePMTHandler::eventNoPMT: motiv = "fara PMT"; break;
	case eDVBServicePMTHandler::eventTuneFailed: motiv = "acordare esuata (fara semnal)"; break;
	case eDVBServicePMTHandler::eventMisconfiguration: motiv = "configurare gresita a tunerului"; break;
	default:
		return;
	}
	if (m_esec)
		return;
	m_esec = true;
	m_sunet_asteptat = false;
	m_activ = false;
	m_ceas->stop();
	m_ceas_pts->stop();
	scrieEsec(hdsjurnal::EROARE, motiv);
}

void Zap::program(const eDVBServicePMTHandler::program &p, int vpid, int vtip)
{
	if (!m_activ)
		return;
	/* Primul program vine de obicei din memoria listei de canale, la cateva ms dupa acordare, adesea fara sunet. PMT-ul adevarat cheama din
	   nou: timpul ramane al primului, datele randului final sunt ale ultimului. */
	if (!m_t_program)
		m_t_program = hdsjurnal::monotonMs();
	m_criptat = p.caids.empty() ? 0 : 1;
	if (!p.audioStreams.empty())
	{
		size_t i = (p.defaultAudioStream >= 0 && (size_t)p.defaultAudioStream < p.audioStreams.size()) ?
			(size_t)p.defaultAudioStream : 0;
		m_apid = p.audioStreams[i].pid;
		m_atip = p.audioStreams[i].type;
	}
	else
		m_apid = m_atip = -1;
	m_vpid = vpid;
	m_vtip = vtip;
	/* getProgramInfo da pmtPid=-1 pentru cache; marcajul PMT singur nu confirma aceasta lista audio. */
	m_program_pmt = p.pmtPid > 0 && p.pmtPid < 0x1fff;
	if (m_sunet_asteptat && (m_t_imagine || vpid <= 0 || vpid >= 0x2000))
	{
		if (!m_program_pmt && m_apid <= 0)
			return;
		m_sunet_asteptat = false;
		m_activ = false;
		char sunet[48];
		textSunet(sunet, sizeof(sunet));
		/* Aceeasi cerere, fara repetarea numelui sau a referintei canalului. */
		hdsjurnal::scrief(COMPONENTA, hdsjurnal::INFO, "zap", "sunet actualizat dupa %ld ms | sunet %s | zap_t0 %lld ms",
			(long)(hdsjurnal::monotonMs() - m_t0), sunet, m_t0);
		return;
	}
	/* Un program fara video din cache putea parea radio; programul TV real isi pastreaza masurarea imaginii. */
	m_sunet_asteptat = false;
	if (vpid > 0 && vpid < 0x2000 && !m_avert && !m_t_eveniment && !m_ceas->isActive() && !m_ceas_pts->isActive())
	{
		if (m_citeste_pts && s_fara_eveniment >= INVATAT_DUPA)
		{
			/* placa fara eveniment video (Vu+ Solo SE): PTS-ul se citeste de acum, decodorul are PID-ul; termenul
			   avertismentului ramane FARA_IMAGINE_MS de la cerere */
			m_din_pts = true;
			m_t_miscare = 0;
			pornesteCitiri(m_t0 + FARA_IMAGINE_MS);
			m_ceas_pts->start(PAS_PTS_MS, true);
			return;
		}
		long trecut = (long)(hdsjurnal::monotonMs() - m_t0);
		long rest = FARA_IMAGINE_MS - trecut;
		m_ceas->start(rest < 1000 ? 1000 : rest, true);
	}
}

void Zap::textSunet(char *buf, size_t n) const
{
	if (m_apid > 0)
		snprintf(buf, n, "%s", codecSunet(m_atip));
	else
		/* Lista goala din cache nu dovedeste lipsa pistei. */
		snprintf(buf, n, "%s", m_program_pmt ? "fara" : "nestiut (PMT nesosit)");
}

void Zap::programGata()
{
	if (!m_activ || m_sunet_asteptat || !m_t_program || (m_vpid > 0 && m_vpid < 0x2000))
		return;
	/* Radio: randul final asteapta si CA PMT. */
	m_ceas->stop();
	m_ceas_pts->stop();
	m_sunet_asteptat = m_apid <= 0 && !m_program_pmt;
	m_activ = m_sunet_asteptat;
	char sunet[48];
	textSunet(sunet, sizeof(sunet));
	char marcaje[340];
	textMarcaje(marcaje, sizeof(marcaje));
	char cine[16], acordare[40];
	textCine(cine, sizeof(cine));
	textAcordare(acordare, sizeof(acordare));
	char canal[400];
	textCanalScurt(canal, sizeof(canal));
	hdsjurnal::scrief(COMPONENTA, hdsjurnal::INFO, "zap", "%s reusit fara imagine (radio): %sprogram %ld ms"
		" | sunet %s | criptat %s%s%s", cine, acordare, dupa(m_t0, m_t_program), sunet,
		m_criptat ? "da" : "nu", marcaje, canal);
}

void Zap::imagine(int latime, int inaltime)
{
	/* placa trimite evenimente video: zap-urile la rand fara eveniment se numara de la capat (si dupa randul final).
	   O placa deja invatata ramane invatata (0.7.7, asistenta 888733): driverul Vu+ 4K trimite evenimentul numai cand se
	   schimba marimea imaginii, deci un eveniment nu spune ca il trimite la fiecare zap */
	if (s_fara_eveniment < INVATAT_DUPA)
		s_fara_eveniment = 0;
	if (!m_activ || m_sunet_asteptat || m_t_eveniment || m_t_imagine || !m_t_program)
		return;
	m_t_eveniment = hdsjurnal::monotonMs();
	m_marcaje[EVENIMENT_VIDEO] = m_t_eveniment;
	m_latime = latime;
	m_inaltime = inaltime;
	if (!m_citeste_pts)
	{
		scrieImagine(m_t_eveniment, false);
		return;
	}
	/* evenimentul nu spune ca se vad cadre (canal nedescifrat: vine si fara imagine); in el nu se intreaba decodorul,
	   PTS-ul se citeste din ceas. Dupa avertisment (imagine tarzie) citirile merg FARA_IMAGINE_MS de la eveniment. */
	m_ceas->stop();
	pornesteCitiri(m_avert ? m_t_eveniment + FARA_IMAGINE_MS : m_t0 + FARA_IMAGINE_MS);
	m_ceas_pts->start(PAS_PTS_MS, true);
}

void Zap::pornesteCitiri(long long termen)
{
	m_citiri = m_bune = 0;
	m_pts_bun = false;
	m_termen_pts = termen;
}

void Zap::citestePts()
{
	if (!m_activ || m_sunet_asteptat || m_esec || m_t_imagine || !m_citeste_pts)
		return;
	long long pts = 0;
	bool bun = m_citeste_pts(m_ctx, pts) && pts > 0;
	long long acum = hdsjurnal::monotonMs();
	if (bun && m_pts_bun && pts != m_pts)
	{
		if (m_din_pts && !m_t_eveniment)
		{
			/* placa fara eveniment: prima miscare poate fi PTS-ul canalului dinainte inlocuit de cel nou, deci imaginea
			   e a primei din doua citiri la rand cu PTS-ul miscat */
			if (!m_t_miscare)
			{
				m_t_miscare = acum;
				m_pts = pts;
				++m_bune;
				++m_citiri;
				m_ceas_pts->start(PAS_PTS_MS, true);
				return;
			}
			m_t_cadre = acum;
			scrieImagine(m_t_miscare, DIN_PTS);
			return;
		}
		/* cadre noi: timpul imaginii e al evenimentului cand merg de la prima pereche de citiri */
		m_t_cadre = acum;
		scrieImagine(m_t_eveniment && m_citiri == 1 ? m_t_eveniment : acum, m_t_eveniment ? CU_EVENIMENT : FARA_EVENIMENT);
		return;
	}
	if (bun && m_pts_bun)
		m_t_miscare = 0;  /* PTS-ul pe loc: miscarea de dinainte nu se mai numara */
	if (bun)
	{
		m_pts = pts;
		m_pts_bun = true;
		++m_bune;
	}
	++m_citiri;
	/* pana la termen, si macar doua citiri bune (o citire cazuta nu face din una singura un verdict) */
	if (acum < m_termen_pts || (m_bune < 2 && m_citiri < MAX_CITIRI_RATATE))
	{
		m_ceas_pts->start(PAS_PTS_MS, true);
		return;
	}
	if (m_avert)
		return;  /* nici dupa avertisment n-au venit cadre: avertismentul ramane randul final */
	m_avert = true;
	const char *cr = m_criptat == 1 ? "fara acces sau raspuns lent al modulului" : "";
	char motiv[200];
	if (m_t_eveniment)
		snprintf(motiv, sizeof(motiv), "fara imagine: eveniment video la %ld ms, dar decodorul nu arata cadre noi "
			"(PTS-ul video sta pe loc)%s%s", dupa(m_t0, m_t_eveniment), *cr ? "; criptat: " : "", cr);
	else
		snprintf(motiv, sizeof(motiv), "fara imagine%s%s%s", *cr ? " (criptat: " : "", cr, *cr ? ")" : "");
	scrieEsec(hdsjurnal::AVERT, motiv);
	/* cheia poate veni mai tarziu: citirile mai merg FARA_IMAGINE_MS, iar cadrele de atunci dau „imagine tarzie” */
	m_termen_pts = acum + FARA_IMAGINE_MS;
	m_ceas_pts->start(PAS_PTS_MS, true);
}

void Zap::scrieImagine(long long t, int cum)
{
	m_t_imagine = t ? t : hdsjurnal::monotonMs();
	m_ceas->stop();
	m_ceas_pts->stop();
	m_sunet_asteptat = m_apid <= 0 && !m_program_pmt;
	m_activ = m_sunet_asteptat;
	/* imagine fara eveniment video: inca un zap la rand care spune ca placa nu trimite evenimentul */
	if (cum != CU_EVENIMENT && s_fara_eveniment < INVATAT_DUPA)
		++s_fara_eveniment;
	char sunet[48];
	textSunet(sunet, sizeof(sunet));
	char marcaje[340];
	textMarcaje(marcaje, sizeof(marcaje));
	char cine[16], acordare[40];
	textCine(cine, sizeof(cine));
	textAcordare(acordare, sizeof(acordare));
	char canal[400];
	textCanalScurt(canal, sizeof(canal));
	if (cum == FARA_EVENIMENT)
	{
		/* imaginea merge, numai evenimentul a lipsit: reusit, fara timpul primei imagini */
		hdsjurnal::scrief(COMPONENTA, hdsjurnal::INFO, "zap", "%s reusit: %sprogram %ld ms, imagine fara "
			"eveniment de la decodor (merge la %d ms) | video %s | sunet %s | criptat %s%s%s", cine,
			acordare, dupa(m_t0, m_t_program), (int)FARA_IMAGINE_MS, codecVideo(m_vtip), sunet,
			m_criptat ? "da" : "nu", marcaje, canal);
		return;
	}
	char marime[32] = "";  /* numai cand primul eveniment e chiar marimea imaginii */
	if (m_latime > 0 && m_inaltime > 0)
		snprintf(marime, sizeof(marime), " %dx%d", m_latime, m_inaltime);
	hdsjurnal::scrief(COMPONENTA, hdsjurnal::INFO, "zap", "%s %s: %sprogram %ld ms, imagine %ld ms%s | video %s"
		"%s | sunet %s | criptat %s%s%s", cine, m_avert ? "imagine tarzie" : "reusit", acordare,
		dupa(m_t0, m_t_program), dupa(m_t0, m_t_imagine), cum == DIN_PTS ? " (din PTS, fara eveniment video)" : "",
		codecVideo(m_vtip), marime, sunet, m_criptat ? "da" : "nu", marcaje, canal);
}

void Zap::faraImagine()
{
	if (!m_activ || m_sunet_asteptat || m_t_imagine || m_t_eveniment || m_avert || m_esec)
		return;
	if (m_din_pts || m_ceas_pts->isActive())
		return;  /* citirile de la program() au termenul lor si scriu singure avertismentul */
	if (m_citeste_pts)
	{
		/* fara eveniment de la decodor: doua citiri ale PTS-ului spun daca imaginea merge */
		pornesteCitiri(0);
		citestePts();
		return;
	}
	m_avert = true;
	char motiv[96];
	snprintf(motiv, sizeof(motiv), "fara imagine%s", m_criptat == 1 ? " (criptat: fara acces sau raspuns lent al "
		"modulului)" : "");
	scrieEsec(hdsjurnal::AVERT, motiv);
}

void Zap::oprire()
{
	m_ceas->stop();
	m_ceas_pts->stop();
	/* oprit intre eveniment si a doua citire (zap repede), sau inainte de a doua miscare pe o placa fara eveniment: o
	   ultima citire, decodorul e inca pornit */
	if (m_activ && (m_t_eveniment || m_din_pts) && !m_t_imagine && !m_esec && m_pts_bun && m_citeste_pts)
	{
		long long pts = 0;
		if (m_citeste_pts(m_ctx, pts) && pts > 0 && pts != m_pts)
		{
			long long acum = hdsjurnal::monotonMs();
			m_t_cadre = acum;
			if (m_t_eveniment)
				scrieImagine(m_citiri == 1 ? m_t_eveniment : acum, CU_EVENIMENT);
			else
				scrieImagine(m_t_miscare ? m_t_miscare : acum, DIN_PTS);
			m_sunet_asteptat = false;
			m_activ = false;
			return;
		}
	}
	if (m_activ && !m_t_imagine && !m_avert && !m_esec && m_vpid > 0 && m_vpid < 0x2000 &&
		hdsjurnal::monotonMs() - m_t0 >= PRAG_OPRIRE_MS)
		scrieEsec(hdsjurnal::AVERT, m_t_eveniment ? "oprit fara imagine (eveniment video fara cadre noi)" :
			"oprit fara imagine");
	m_activ = false;
	m_sunet_asteptat = false;
}

}
