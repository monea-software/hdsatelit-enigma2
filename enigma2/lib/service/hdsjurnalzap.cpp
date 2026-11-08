/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsjurnalzap.cpp: jurnalul schimbarii de canal (vezi hdsjurnalzap.h). Scris de la zero. Pe firul principal; scrierea
 * pe disc o face firul din lib/base/hdsjurnal.cpp. Datele canalului (numele, transponderul) se cauta in lista de canale
 * numai cand se scrie un esec.
 */

#include <lib/service/hdsjurnalzap.h>

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

Zap::Zap()
	: m_are_imagine(0), m_ctx(0), m_activ(false), m_esec(false), m_avert(false), m_t0(0), m_t_acordat(0), m_t_program(0), m_t_imagine(0),
	m_slot(-1), m_vpid(-1), m_vtip(-1), m_apid(-1), m_atip(-1), m_criptat(-1), m_sid(0),
	m_ceas(eTimer::create(eApp))
{
	CONNECT(m_ceas->timeout, Zap::faraImagine);
	memset(m_marcaje, 0, sizeof(m_marcaje));
	m_t_comanda = m_t_blocare = 0;
	m_sec_ms = -1;
}

void Zap::pornire(const eServiceReferenceDVB &ref, bool masurat)
{
	m_ceas->stop();
	m_activ = masurat;
	m_esec = m_avert = false;
	m_t0 = hdsjurnal::monotonMs();
	m_t_acordat = m_t_program = m_t_imagine = 0;
	memset(m_marcaje, 0, sizeof(m_marcaje));
	m_t_comanda = m_t_blocare = 0;
	m_sec_ms = -1;
	m_slot = m_vpid = m_vtip = m_apid = m_atip = m_criptat = -1;
	m_sid = 0;
	if (masurat)
		m_ref = ref;
}

static long dupa(long long t0, long long t)
{
	return t ? (long)(t - t0) : -1;
}

void Zap::marcaj(int etapa, long long t)
{
	if (m_activ && etapa >= 0 && etapa < NR_MARCAJE && !m_marcaje[etapa])
		m_marcaje[etapa] = t ? t : hdsjurnal::monotonMs();
}

void Zap::acordare(const eDVBFrontend::TimpiZap &t)
{
	/* Un transponder reutilizat pastreaza marcajele acordarii vechi. */
	if (!m_activ || t.pornire_ms < m_t0 || t.comanda_ms < m_t0)
		return;
	m_t_comanda = t.comanda_ms;
	m_t_blocare = t.lock_ms;
	if (t.sec_start_ms >= m_t0 && t.sec_gata_ms >= t.sec_start_ms)
		m_sec_ms = (long)(t.sec_gata_ms - t.sec_start_ms);
}

void Zap::textMarcaje(char *buf, size_t n) const
{
	snprintf(buf, n, " | zap_t0 %lld ms | marcaje: pmt %ld ms, decodor %ld ms, ca_pmt %ld ms, "
		"comanda_tuner %ld ms, sec %ld ms, blocare %ld ms, pachet_video -1 ms, eveniment_video %ld ms",
		m_t0, dupa(m_t0, m_marcaje[PMT_PRIMIT]), dupa(m_t0, m_marcaje[DECODOR_PREGATIT]),
		dupa(m_t0, m_marcaje[CA_PMT_TRIMIS]), dupa(m_t0, m_t_comanda), m_sec_ms,
		dupa(m_t0, m_t_blocare), dupa(m_t0, m_marcaje[EVENIMENT_VIDEO]));
}

void Zap::textCanal(char *buf, size_t n)
{
	size_t f = 0;
	buf[0] = 0;
	std::string ref = m_ref.toString();
	std::string nume;
	char tp[160] = "?";
	ePtr<eDVBResourceManager> res;
	ePtr<iDVBChannelList> db;
	if (!eDVBResourceManager::getInstance(res) && !res->getChannelList(db) && db)
	{
		ePtr<eDVBService> s;
		if (!db->getService(m_ref, s) && s)
			nume = s->m_service_name;
		eDVBChannelID chid;
		m_ref.getChannelID(chid);
		ePtr<iDVBFrontendParameters> fp;
		int tip = -1;
		if (!db->getChannelFrontendData(chid, fp) && fp && !fp->getSystem(tip))
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
	for (size_t i = 0; i < nume.size(); ++i)
		if (nume[i] == '"')
			nume[i] = '\'';
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
	char marcaje[320];
	textMarcaje(marcaje, sizeof(marcaje));
	textCanal(canal, sizeof(canal));
	long long acum = hdsjurnal::monotonMs();
	hdsjurnal::scrief(COMPONENTA, nivel, "zap", "%c %s dupa %ld ms (acordare %ld ms, program %ld ms)%s | %s", litera(m_slot),
		motiv, (long)(acum - m_t0), dupa(m_t0, m_t_acordat), dupa(m_t0, m_t_program), marcaje, canal);
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
	m_ceas->stop();
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
	if (vpid > 0 && vpid < 0x2000 && !m_avert && !m_ceas->isActive())
	{
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
		/* "fara" numai dupa PMT: memoria listei de canale nu tine sunetul la multe canale, deci nu spune nimic despre canal */
		snprintf(buf, n, "%s", m_marcaje[PMT_PRIMIT] ? "fara" : "nestiut (PMT nesosit)");
}

void Zap::programGata()
{
	if (!m_activ || !m_t_program || (m_vpid > 0 && m_vpid < 0x2000))
		return;
	/* Radio: randul final asteapta si CA PMT. */
	m_activ = false;
	char sunet[48];
	textSunet(sunet, sizeof(sunet));
	char marcaje[320];
	textMarcaje(marcaje, sizeof(marcaje));
	hdsjurnal::scrief(COMPONENTA, hdsjurnal::INFO, "zap", "%c reusit fara imagine (radio): acordare %ld ms, program %ld ms"
		" | sunet %s | criptat %s%s", litera(m_slot), dupa(m_t0, m_t_acordat), dupa(m_t0, m_t_program), sunet,
		m_criptat ? "da" : "nu", marcaje);
}

void Zap::imagine(int latime, int inaltime)
{
	if (!m_activ || m_t_imagine || !m_t_program)
		return;
	m_t_imagine = hdsjurnal::monotonMs();
	m_marcaje[EVENIMENT_VIDEO] = m_t_imagine;
	m_ceas->stop();
	m_activ = false;
	char sunet[48];
	textSunet(sunet, sizeof(sunet));
	char marime[32] = "";  /* numai cand primul eveniment e chiar marimea imaginii */
	if (latime > 0 && inaltime > 0)
		snprintf(marime, sizeof(marime), " %dx%d", latime, inaltime);
	char marcaje[320];
	textMarcaje(marcaje, sizeof(marcaje));
	hdsjurnal::scrief(COMPONENTA, hdsjurnal::INFO, "zap", "%c %s: acordare %ld ms, program %ld ms, imagine %ld ms | video %s"
		"%s | sunet %s | criptat %s%s", litera(m_slot), m_avert ? "imagine tarzie" : "reusit", dupa(m_t0, m_t_acordat),
		dupa(m_t0, m_t_program), dupa(m_t0, m_t_imagine), codecVideo(m_vtip), marime, sunet,
		m_criptat ? "da" : "nu", marcaje);
}

void Zap::faraImagine()
{
	if (!m_activ || m_t_imagine || m_avert || m_esec)
		return;
	if (m_are_imagine && m_are_imagine(m_ctx))
	{
		/* imaginea merge, numai evenimentul a lipsit: reusit, fara canal, fara timpul primei imagini */
		m_activ = false;
		char sunet[48];
		textSunet(sunet, sizeof(sunet));
		char marcaje[320];
		textMarcaje(marcaje, sizeof(marcaje));
		hdsjurnal::scrief(COMPONENTA, hdsjurnal::INFO, "zap", "%c reusit: acordare %ld ms, program %ld ms, imagine fara "
			"eveniment de la decodor (merge la %d ms) | video %s | sunet %s | criptat %s%s", litera(m_slot),
			dupa(m_t0, m_t_acordat), dupa(m_t0, m_t_program), (int)FARA_IMAGINE_MS, codecVideo(m_vtip), sunet,
			m_criptat ? "da" : "nu", marcaje);
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
	if (m_activ && !m_t_imagine && !m_avert && !m_esec && m_vpid > 0 && m_vpid < 0x2000 &&
		hdsjurnal::monotonMs() - m_t0 >= PRAG_OPRIRE_MS)
		scrieEsec(hdsjurnal::AVERT, "oprit fara imagine");
	m_activ = false;
}

}
