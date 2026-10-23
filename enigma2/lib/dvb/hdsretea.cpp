/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsretea.cpp: ce spune tabela retelei (NIT) citita la scanare, pentru /api/scanare-ultima (vezi hdsretea.h).
 * Unitatile sunt cele din lib/dvb/frontend.cpp (eDVBFrontendParameters*::set): cablul si satelitul in kHz, rata in mii
 * de simboluri pe secunda, pozitia orbitala ca in enigma2.
 */

#include <lib/dvb/hdsretea.h>

#include <algorithm>

#include <dvbsi++/network_information_section.h>
#include <dvbsi++/descriptor.h>
#include <dvbsi++/network_name_descriptor.h>
#include <dvbsi++/private_data_specifier_descriptor.h>
#include <dvbsi++/cable_delivery_system_descriptor.h>
#include <dvbsi++/satellite_delivery_system_descriptor.h>
#include <dvbsi++/terrestrial_delivery_system_descriptor.h>

namespace hdsretea
{

/* cu_semn: bitul de sus al numarului e visible_service_flag (0x83, 0x88, 0x87); fara el (0x86) vizibil = -1 */
static void citesteNumere(const uint8_t *p, size_t n, unsigned masca, bool cu_semn, unsigned tag, uint32_t pds,
	int lista, unsigned tsid, unsigned onid, std::vector<Lcn> &iesire)
{
	for (size_t i = 0; i + 4 <= n; i += 4)
	{
		Lcn l;
		l.tsid = tsid;
		l.onid = onid;
		l.sid = ((unsigned)p[i] << 8) | p[i + 1];
		l.vizibil = cu_semn ? ((p[i + 2] & 0x80) ? 1 : 0) : -1;
		l.numar = (((unsigned)p[i + 2] << 8) | p[i + 3]) & masca;
		l.tag = tag;
		l.pds = pds;
		l.lista = lista;
		iesire.push_back(l);
	}
}

bool citesteLcn(unsigned tag, uint32_t pds, const uint8_t *corp, size_t lungime, unsigned tsid, unsigned onid,
	std::vector<Lcn> &iesire)
{
	if (tag == TAG_LCN || tag == TAG_LCN_HD)
	{
		if (lungime % 4)
			return false;
		/* NorDig versiunea 1: numarul are 14 biti (un singur bit rezervat) */
		unsigned masca = (tag == TAG_LCN && pds == PDS_NORDIG) ? 0x3FFF : 0x3FF;
		citesteNumere(corp, lungime, masca, true, tag, pds, -1, tsid, onid, iesire);
		return true;
	}
	if (tag == TAG_LCN_1A0)
	{
		/* sub alt PDS (sau fara niciunul), 0x86 inseamna altceva */
		if (pds != PDS_1A0 || lungime % 4)
			return false;
		/* numai forma citita pe receptor (cei 6 biti de sus ai numarului 0); altfel nu se ghiceste */
		for (size_t i = 0; i < lungime; i += 4)
			if (corp[i + 2] & 0xFC)
				return false;
		citesteNumere(corp, lungime, 0x3FF, false, tag, pds, -1, tsid, onid, iesire);
		return true;
	}
	if (tag == TAG_LCN_NORDIG_V2)
	{
		/* sub alt PDS, 0x87 inseamna altceva: brut */
		if (pds != PDS_NORDIG && pds != 0)
			return false;
		std::vector<Lcn> gasite;
		size_t i = 0;
		while (i < lungime)
		{
			if (i + 2 > lungime)
				return false;
			int lista = corp[i];
			size_t nume = corp[i + 1];
			i += 2 + nume;
			if (i + 4 > lungime)            /* country_code (3) si lungimea numerelor (1) */
				return false;
			size_t numere = corp[i + 3];
			i += 4;
			if (i + numere > lungime || numere % 4)
				return false;
			citesteNumere(corp + i, numere, 0x3FF, true, tag, pds, lista, tsid, onid, gasite);
			i += numere;
		}
		iesire.insert(iesire.end(), gasite.begin(), gasite.end());
		return true;
	}
	return false;
}

Colector::Colector(): m_octeti_bruti(0)
{
}

void Colector::goleste()
{
	m_retele.clear();
	m_sectiuni.clear();
	m_octeti_bruti = 0;
}

Retea *Colector::retea(unsigned nid)
{
	for (std::vector<Retea>::iterator r(m_retele.begin()); r != m_retele.end(); ++r)
		if (r->nid == nid)
			return &*r;
	if (m_retele.size() >= MAX_RETELE)
		return 0;
	Retea r;
	r.nid = nid;
	r.trunchiat = false;
	m_retele.push_back(r);
	return &m_retele.back();
}

static bool acelasiMux(const Mux &a, const Mux &b)
{
	return a.tsid == b.tsid && a.onid == b.onid && a.sistem == b.sistem && a.f_khz == b.f_khz && a.poz == b.poz
		&& a.pol == b.pol && a.sr == b.sr && a.mod == b.mod && a.fec == b.fec && a.s2 == b.s2;
}

static bool acelasiNumar(const Lcn &a, const Lcn &b)
{
	return a.tsid == b.tsid && a.onid == b.onid && a.sid == b.sid && a.numar == b.numar && a.vizibil == b.vizibil
		&& a.tag == b.tag && a.pds == b.pds && a.lista == b.lista;
}

static void adaugaMux(Retea &r, const Mux &m)
{
	for (std::vector<Mux>::const_iterator i(r.muxuri.begin()); i != r.muxuri.end(); ++i)
		if (acelasiMux(*i, m))
			return;
	if (r.muxuri.size() >= MAX_MUXURI)
	{
		r.trunchiat = true;
		return;
	}
	r.muxuri.push_back(m);
}

static void adaugaNumere(Retea &r, const std::vector<Lcn> &noi)
{
	for (std::vector<Lcn>::const_iterator n(noi.begin()); n != noi.end(); ++n)
	{
		bool vazut = false;
		for (std::vector<Lcn>::const_iterator i(r.lcn.begin()); i != r.lcn.end() && !vazut; ++i)
			vazut = acelasiNumar(*i, *n);
		if (vazut)
			continue;
		if (r.lcn.size() >= MAX_LCN)
		{
			r.trunchiat = true;
			return;
		}
		r.lcn.push_back(*n);
	}
}

void Colector::pastreazaBrut(Retea &r, int tsid, int onid, unsigned tag, uint32_t pds, const uint8_t *corp,
	size_t lungime)
{
	for (std::vector<Brut>::const_iterator i(r.privati.begin()); i != r.privati.end(); ++i)
		if (i->tsid == tsid && i->onid == onid && i->tag == tag && i->pds == pds && i->octeti.size() == lungime
			&& std::equal(i->octeti.begin(), i->octeti.end(), corp))
			return;
	if (m_octeti_bruti + lungime > MAX_OCTETI_BRUTI)
	{
		r.trunchiat = true;
		return;
	}
	Brut b;
	b.tsid = tsid;
	b.onid = onid;
	b.tag = tag;
	b.pds = pds;
	b.octeti.assign(corp, corp + lungime);
	r.privati.push_back(b);
	m_octeti_bruti += lungime;
}

static bool privat(unsigned tag)
{
	return tag >= 0x80 && tag != 0xFF;
}

unsigned Colector::adaugaSectiune(const NetworkInformationSection &nit)
{
	unsigned nid = nit.getNetworkId();
	/* aceeasi sectiune citita pe alt transponder al aceleiasi retele (cautarea in retea citeste NIT-ul pe fiecare):
	   nimic nou de luat din ea */
	uint64_t semn = ((uint64_t)nid << 45) | ((uint64_t)nit.getSectionNumber() << 37)
		| ((uint64_t)nit.getVersionNumber() << 32) | nit.getCrc32();
	if (!m_sectiuni.insert(semn).second)
		return nid;
	Retea *r = retea(nid);
	if (!r)
		return nid;

	uint8_t buf[2 + 256];
	uint32_t pds_retea = 0;
	const DescriptorList &bucla = *nit.getDescriptors();
	for (DescriptorConstIterator d(bucla.begin()); d != bucla.end(); ++d)
	{
		unsigned tag = (*d)->getTag();
		if (tag == TAG_PDS)
		{
			pds_retea = ((const PrivateDataSpecifierDescriptor *)*d)->getPrivateDataSpecifier();
			r->pds.insert(pds_retea);
		}
		else if (tag == TAG_NUME_RETEA)
		{
			const std::string &nume = ((const NetworkNameDescriptor *)*d)->getNetworkName();
			if (r->nume.empty())
				r->nume = nume.substr(0, MAX_NUME);
		}
		else if (privat(tag))
		{
			size_t n = (*d)->writeToBuffer(buf);
			pastreazaBrut(*r, -1, -1, tag, pds_retea, buf + 2, n - 2);
		}
	}

	const TransportStreamInfoList &muxuri = *nit.getTsInfo();
	for (TransportStreamInfoConstIterator ts(muxuri.begin()); ts != muxuri.end(); ++ts)
	{
		unsigned tsid = (*ts)->getTransportStreamId();
		unsigned onid = (*ts)->getOriginalNetworkId();
		bool are_pds = false;
		uint32_t pds = 0;
		const DescriptorList &descriptori = *(*ts)->getDescriptors();
		for (DescriptorConstIterator d(descriptori.begin()); d != descriptori.end(); ++d)
		{
			unsigned tag = (*d)->getTag();
			uint32_t pds_valabil = are_pds ? pds : pds_retea;
			Mux m;
			m.tsid = tsid;
			m.onid = onid;
			m.sr = m.mod = m.fec = m.poz = m.pol = m.s2 = -1;
			switch (tag)
			{
			case TAG_PDS:
				pds = ((const PrivateDataSpecifierDescriptor *)*d)->getPrivateDataSpecifier();
				are_pds = true;
				r->pds.insert(pds);
				break;
			case TAG_LIVRARE_CABLU:
			{
				const CableDeliverySystemDescriptor &c = *(const CableDeliverySystemDescriptor *)*d;
				m.sistem = SISTEM_CABLU;
				m.f_khz = c.getFrequency() / 10;
				m.sr = c.getSymbolRate() / 10;
				m.mod = c.getModulation();
				m.fec = c.getFecInner();
				adaugaMux(*r, m);
				break;
			}
			case TAG_LIVRARE_SATELIT:
			{
				const SatelliteDeliverySystemDescriptor &s = *(const SatelliteDeliverySystemDescriptor *)*d;
				unsigned bcd = s.getOrbitalPosition();
				int poz = ((bcd >> 12) & 0xF) * 1000 + ((bcd >> 8) & 0xF) * 100 + ((bcd >> 4) & 0xF) * 10 + (bcd & 0xF);
				if (poz && !s.getWestEastFlag())
					poz = 3600 - poz;
				m.sistem = SISTEM_SATELIT;
				m.f_khz = s.getFrequency() * 10;
				m.sr = s.getSymbolRate() / 10;
				m.mod = s.getModulation();
				m.fec = s.getFecInner();
				m.poz = poz;
				m.pol = s.getPolarization();
				m.s2 = s.getModulationSystem() ? 1 : 0;
				adaugaMux(*r, m);
				break;
			}
			case TAG_LIVRARE_TERESTRU:
			{
				const TerrestrialDeliverySystemDescriptor &t = *(const TerrestrialDeliverySystemDescriptor *)*d;
				m.sistem = SISTEM_TERESTRU;
				m.f_khz = t.getCentreFrequency() / 100;       /* in pasi de 10 Hz */
				adaugaMux(*r, m);
				break;
			}
			default:
			{
				if (!privat(tag))
					break;
				size_t n = (*d)->writeToBuffer(buf);
				std::vector<Lcn> numere;
				if (citesteLcn(tag, pds_valabil, buf + 2, n - 2, tsid, onid, numere))
					adaugaNumere(*r, numere);
				else
					pastreazaBrut(*r, (int)tsid, (int)onid, tag, pds_valabil, buf + 2, n - 2);
				break;
			}
			}
		}
	}
	return nid;
}

}
