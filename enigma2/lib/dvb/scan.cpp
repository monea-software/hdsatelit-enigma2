/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <lib/dvb/idvb.h>
#include <dvbsi++/descriptor_tag.h>
#include <dvbsi++/service_descriptor.h>
#include <dvbsi++/satellite_delivery_system_descriptor.h>
#include <dvbsi++/s2_satellite_delivery_system_descriptor.h>
#include <dvbsi++/terrestrial_delivery_system_descriptor.h>
#include <dvbsi++/extension_descriptor.h>
#include <dvbsi++/t2_delivery_system_descriptor.h>
#include <dvbsi++/cable_delivery_system_descriptor.h>
#include <dvbsi++/ca_identifier_descriptor.h>
#include <dvbsi++/registration_descriptor.h>
#include <lib/dvb/specs.h>
#include <lib/dvb/esection.h>
#include <lib/dvb/scan.h>
#include <lib/dvb/frontend.h>
#include <lib/dvb/hdsgrad.h>
#include <lib/dvb/hdsmultistream.h>
#include <lib/dvb/hdsscanreguli.h>
#include <lib/dvb/hdsterestru.h>
#include <lib/dvb/hdsurmamotor.h>
#include <lib/base/eenv.h>
#include <lib/base/eerror.h>
#include <lib/base/estring.h>
#include <lib/python/python.h>
#include <lib/base/nconfig.h>
#include <lib/dvb/db.h>
#include <algorithm>
#include <errno.h>

/* HDSatelit: steagurile NIT din lib/dvb/hdsretea.h au aceleasi valori ca ale scanarii */
static_assert((int)eDVBScan::scanNetworkSearch == (int)hdsretea::STEAG_CAUTARE_IN_RETEA, "steagul cautarii in retea");
static_assert((int)eDVBScan::hdsNitInformativ == (int)hdsretea::STEAG_NIT_INFORMATIV, "steagul NIT informativ");

#define SCAN_eDebug(x...) do { if (m_scan_debug) eDebug(x); } while(0)
#define SCAN_eDebugNoNewLine(x...) do { if (m_scan_debug) eDebugNoNewLine(x); } while(0)

DEFINE_REF(eDVBScan);

/* HDSatelit (0.8.0): rata de simboluri a unui transponder de satelit (simboluri/s), 0 la cablu, terestru sau necunoscuta;
   pentru plafonul tabelelor (lib/dvb/hdsscanreguli.h, timpTabel) */
static long hdsRataSatelit(iDVBFrontendParameters *p)
{
	int tip;
	eDVBFrontendParametersSatellite sat;
	if (!p || p->getSystem(tip) || tip != iDVBFrontend::feSatellite || p->getDVBS(sat))
		return 0;
	return (long)sat.symbol_rate;
}

/* HDSatelit (SC2, 15.11.2026): NIT-ul scanarii spune jurnalului cand vine prima sectiune, cu network_id (table_id_extension,
   octetii 3-4), version_number (octetul 5) si cate sectiuni are tabela (last_section_number + 1). Tabela se strange la fel
   ca inainte (eTable): numai ceasul din hds-scanare.log afla ceva in plus. Din randul de jurnal se vede cat asteapta
   scanarea dupa restul sectiunilor unei retele deja citite pe alt transponder (cantarirea din STADIU-SC2). */
class hdsTabelNit: public eTable<NetworkInformationSection>
{
	hdsjscan::Stare &m_jurnal;
protected:
	int createTable(unsigned int nr, const __u8 *data, unsigned int max)
	{
		hdsjscan::sectiuneNit(m_jurnal, (data[3] << 8) | data[4], (data[5] >> 1) & 0x1F, (int)max);
		return eTable<NetworkInformationSection>::createTable(nr, data, max);
	}
public:
	hdsTabelNit(bool debug, hdsjscan::Stare &jurnal): eTable<NetworkInformationSection>(debug), m_jurnal(jurnal)
	{
	}
};

eDVBScan::eDVBScan(iDVBChannel *channel, bool usePAT, bool debug)
	:m_channel(channel), m_channel_state(iDVBChannel::state_idle)
	,m_ready(0), m_ready_all(usePAT ? (readySDT|readyPAT) : readySDT)
	,m_pmt_running(false), m_abort_current_pmt(false), m_flags(0), m_num_new_services(-1)
	,m_usePAT(usePAT), m_scan_debug(debug), m_show_add_tsid_onid_check_failed_msg(true)
{
	m_hds_cautare = false;  /* pornita de start(); actualizarea din fundal de la zap (pmt.cpp) nu citeste VCT-ul */
	m_hds_psip_t0 = 0;
	m_hds_tp_cu_sdt = false;
	if (m_channel->getDemux(m_demux))
		SCAN_eDebug("scan: failed to allocate demux!");
	m_channel->connectStateChange(sigc::mem_fun(*this, &eDVBScan::stateChange), m_stateChanged_connection);
	std::string filename = eEnv::resolve("${sysconfdir}/scan_tp_valid_check.py");
	FILE *f = fopen(filename.c_str(), "r");
	if (f)
	{
		char code[16384];
		size_t rd = fread(code, 1, 16383, f);
		if (rd)
		{
			code[rd]=0;
			m_additional_tsid_onid_check_func = Py_CompileString(code, filename.c_str(), Py_file_input);
		}
		fclose(f);
	}
}

eDVBScan::~eDVBScan()
{
	if (m_additional_tsid_onid_check_func)
		Py_DECREF(m_additional_tsid_onid_check_func);
}

int eDVBScan::isValidONIDTSID(int orbital_position, eOriginalNetworkID onid, eTransportStreamID tsid)
{
	int ret;
	switch (onid.get())
	{
	case 0:
	case 0x1111:
		ret=0;
		break;
	case 0x13E:  // workaround for 11258H and 11470V on hotbird with same ONID/TSID (0x13E/0x578)
		ret = orbital_position != 130 || tsid != 0x578;
		break;
	case 1:
		ret = orbital_position == 192;
		break;
	case 0x00B1:
		ret = tsid != 0x00B0;
		break;
	case 0x00eb:
		ret = tsid != 0x4321;
		break;
	case 0x0002:
		ret = abs(orbital_position-282) < 6 && tsid != 2019;
		// 12070H and 10936V have same tsid/onid.. but even the same services are provided
		break;
	case 0x2000:
		ret = tsid != 0x1000;
		break;
	case 0x5E: // Sirius 4.8E 12322V and 12226H
		ret = abs(orbital_position-48) < 3 && tsid != 1;
		break;
	case 10100: // Eutelsat W7 36.0E 11644V and 11652V
		ret = orbital_position != 360 || tsid != 10187;
		break;
	case 42: // Tuerksat 42.0E
		ret = orbital_position != 420 || (
		    tsid != 8 && // 11830V 12729V
		    tsid != 5 && // 12679V 12685H
		    tsid != 2 && // 11096V 12015H
		    tsid != 55); // 11996V 11716V
		break;
	case 100: // Intelsat 10 68.5E 3808V 3796V 4012V, Amos 4.0W 10723V 11571H
		ret = (orbital_position != 685 && orbital_position != 3560) || tsid != 1;
		break;
	case 70: // Thor 0.8W 11862H 12341V
		ret = abs(orbital_position-3592) < 3 && tsid != 46;
		break;
	case 32: // NSS 806 (40.5W) 4059R, 3774L
		ret = orbital_position != 3195 || tsid != 21;
		break;
	default:
		ret = onid.get() < 0xFF00;
		break;
	}
	if (ret && m_additional_tsid_onid_check_func)
	{
		bool failed = true;
		ePyObject dict = PyDict_New();
		extern void PutToDict(ePyObject &, const char *, long);
		PyDict_SetItemString(dict, "__builtins__", PyEval_GetBuiltins());
		PutToDict(dict, "orbpos", orbital_position);
		PutToDict(dict, "tsid", tsid.get());
		PutToDict(dict, "onid", onid.get());
		ePyObject r = PyEval_EvalCode((PyObject*)m_additional_tsid_onid_check_func, dict, dict);
		if (r)
		{
			ePyObject o = PyDict_GetItemString(dict, "ret");
			if (o)
			{
				if (PyLong_Check(o))
				{
					ret = PyLong_AsLong(o);
					failed = false;
				}
			}
			Py_DECREF(r);
		}
		if (failed && m_show_add_tsid_onid_check_failed_msg)
		{
			eDebug("execing /etc/enigma2/scan_tp_valid_check failed!\n"
				"usable global variables in scan_tp_valid_check.py are 'orbpos', 'tsid', 'onid'\n"
				"the return value must be stored in a global var named 'ret'");
			m_show_add_tsid_onid_check_failed_msg=false;
		}
		Py_DECREF(dict);
	}
	return ret;
}

eDVBNamespace eDVBScan::buildNamespace(eOriginalNetworkID onid, eTransportStreamID tsid, unsigned long hash)
{
		// on valid ONIDs, ignore frequency ("sub network") part
	if (isValidONIDTSID((hash >> 16) & 0xFFFF, onid, tsid))
		hash &= ~0xFFFF;
	return eDVBNamespace(hash);
}

void eDVBScan::stateChange(iDVBChannel *ch)
{
	int state;
	if (ch->getState(state))
		return;
	if (m_channel_state == state)
		return;
	
	if (state == iDVBChannel::state_ok)
	{
		hdsjscan::semnalPrins(m_hds_jurnal);  /* ceasul tabelelor porneste de aici (SC2) */
		startFilter();
		m_channel_state = state;
	} else if (state == iDVBChannel::state_failed)
	{
		hdsjscan::faraSemnal(m_hds_jurnal);
		m_ch_unavailable.push_back(m_ch_current);
		nextChannel();
	}
			/* unavailable will timeout, anyway. */
}

RESULT eDVBScan::nextChannel()
{
	ePtr<iDVBFrontend> fe;

	m_SDT = 0; m_PAT = 0; m_BAT = 0; m_NIT = 0, m_PMT = 0;

	m_ready = 0;

	/* HDSatelit (0.8.0): VCT-ul transponderului de dinainte (cititorul, plafonul, sectiunile), inainte de orice iesire */
	hdsOpresteVct();
	m_hds_vct.goleste();
	m_hds_tp_cu_sdt = false;
	hdsOpresteNitAlt();
	m_hds_nit_alt_sectiuni.clear();

	/* HDSatelit (0.8.0): PMT-urile ramase de la transponderul de dinainte (pierdut in timpul tabelelor: semnalul cazut si
	   reacordarea esuata) nu se mai citesc pe cel nou. Pana acum ramaneau in lista, cu m_pmt_running pornit: pe
	   transponderul urmator se cautau PMT-urile vechi pe PID-urile lor (cate un plafon fiecare), iar cele noi de dinaintea
	   iteratorului vechi erau sarite, deci canale amestecate sau lipsa. */
	m_pmts_to_read.clear();
	m_pmt_in_progress = m_pmts_to_read.end();
	m_pmt_running = false;
	m_abort_current_pmt = false;

	m_pat_tsid = eTransportStreamID();

		/* check what we need */
	m_ready_all = readySDT;

	/* HDSatelit: la cautarea in retea si, numai pentru informatie, la cablu pe o frecventa (lib/dvb/hdsretea.h) */
	if (hdsretea::asteaptaNit(m_flags))
		m_ready_all |= readyNIT;
	
	if (m_flags & scanSearchBAT)
		m_ready_all |= readyBAT;

	if (m_usePAT)
		m_ready_all |= readyPAT;

	/* AMRZ (24.11.2026, masurat pe ZGEMMA H8.2H Plus, 13E): ce a adus NIT other (hdsSatelitDinNit) intra in coada abia acum, dupa
	   lista si NIT-ul actual. Pusa pe loc (in fata cozii) intrarea NIT other schimba ordinea intregii cautari: pe tunerele care
	   isi aleg singure sistemul varianta ei prindea prima si lista pierdea parametrii buni (12673 V DVB-S2 8PSK 30000 a ajuns
	   DVB-S QPSK 29900 in lamedb), iar actualizarile din NIT-ul actual (rolloff, FEC, frecventa) cadeau pe alte intrari (7
	   transpondere pe 13E). addChannelToScan sare acum ce s-a prins, ce n-a avut semnal cu aceiasi parametri si variantele
	   purtatorilor prinse; restul (purtatoare noi, ca 11470 V 33000 16APSK) se incearca la sfarsit. */
	if (m_ch_toScan.empty() && !m_hds_nit_alt_amanate.empty())
	{
		std::list<std::pair<eDVBChannelID, ePtr<iDVBFrontendParameters> > > amanate;
		amanate.swap(m_hds_nit_alt_amanate);
		for (std::list<std::pair<eDVBChannelID, ePtr<iDVBFrontendParameters> > >::iterator a = amanate.begin();
				a != amanate.end(); ++a)
			addChannelToScan(a->first, a->second);
		SCAN_eDebug("[eDVBScan] NIT other la sfarsit: %d intrari tinute, %d de cautat", (int)amanate.size(),
			(int)m_ch_toScan.size());
	}

	if (m_ch_toScan.empty())
	{
		SCAN_eDebug("no channels left to scan.");
		SCAN_eDebug("%zd channels scanned, %zd were unavailable.",
				m_ch_scanned.size(), m_ch_unavailable.size());
		SCAN_eDebug("%zd channels in database.", m_new_channels.size());
		hdsjscan::gata(m_hds_jurnal, m_ch_scanned.size(), m_ch_unavailable.size(), m_new_services.size());
		m_event(evtFinish);
		return -ENOENT;
	}
	
	m_ch_current = m_ch_toScan.front();
	
	m_ch_toScan.pop_front();
	
	if (m_channel->getFrontend(fe))
	{
		m_event(evtFail);
		return -ENOTSUP;
	}

	m_chid_current = eDVBChannelID();

	m_channel_state = iDVBChannel::state_idle;
	hdsjscan::transponder(m_hds_jurnal, m_ch_current, m_new_services.size());

	{
		/* HDSatelit (urma motorului): motivul acestei acordari */
		hdsurma::Motiv hds_motiv("scanare");
		if (fe->tune(*m_ch_current))
			return nextChannel();
	}

	m_event(evtUpdate);
	return 0;
}

RESULT eDVBScan::startFilter()
{
	bool startSDT=true;
	ASSERT(m_demux);

			/* only start required filters filter */

	if (m_ready_all & readyPAT)
		startSDT = m_ready & readyPAT;

	// m_ch_current is not set, when eDVBScan is just used for a SDT update
	if (!m_ch_current)
	{
		unsigned int channelFlags;
		m_channel->getCurrentFrontendParameters(m_ch_current);
		m_ch_current->getFlags(channelFlags);
		if (channelFlags & iDVBFrontendParameters::flagOnlyFree)
			m_flags |= scanOnlyFree;
	}

	m_SDT = 0;
	if (startSDT && (m_ready_all & readySDT))
	{
		m_SDT = new eTable<ServiceDescriptionSection>(m_scan_debug);
		int tsid=-1;
		if (m_ready & readyPAT && m_ready & validPAT)
		{
			std::vector<ProgramAssociationSection*>::const_iterator i =
				m_PAT->getSections().begin();
			ASSERT(i != m_PAT->getSections().end());
			tsid = (*i)->getTableIdExtension(); // in PAT this is the transport stream id
			m_pat_tsid = eTransportStreamID(tsid);
			for (; i != m_PAT->getSections().end(); ++i)
			{
				const ProgramAssociationSection &pat = **i;
				ProgramAssociationConstIterator program = pat.getPrograms()->begin();
				for (; program != pat.getPrograms()->end(); ++program)
					m_pmts_to_read.insert(std::pair<unsigned short, service>((*program)->getProgramNumber(), service((*program)->getProgramMapPid())));
			}
			m_PMT = new eTable<ProgramMapSection>(m_scan_debug);
			CONNECT(m_PMT->tableReady, eDVBScan::PMTready);
			PMTready(-2);
			// KabelBW HACK ... on 618Mhz and 626Mhz the transport stream id in PAT and SDT is different

			{
				int type;
				m_ch_current->getSystem(type);
				if (type == iDVBFrontend::feCable)
				{
					eDVBFrontendParametersCable parm;
					m_ch_current->getDVBC(parm);
					if ((tsid == 0x00d7 && abs((int)parm.frequency-618000) < 2000) ||
						(tsid == 0x00d8 && abs((int)parm.frequency-626000) < 2000))
						tsid = -1;
				}
			}
		}
		if (tsid == -1)
		{
			if (m_SDT->start(m_demux, eDVBSDTSpec()))
				return -1;
		}
		else if (m_SDT->start(m_demux, eDVBSDTSpec(tsid, true)))
			return -1;
		CONNECT(m_SDT->tableReady, eDVBScan::SDTready);
	}

	if (!(m_ready & readyPAT))
	{
		m_PAT = 0;
		if (m_ready_all & readyPAT)
		{
			m_PAT = new eTable<ProgramAssociationSection>(m_scan_debug);
			/* plafonul PAT-ului creste la ratele mici (lib/dvb/hdsscanreguli.h, timpTabel) */
			if (m_PAT->start(m_demux, eDVBPATSpec(hdsscanreguli::timpTabel(4000, hdsRataSatelit(m_ch_current)))))
				return -1;
			CONNECT(m_PAT->tableReady, eDVBScan::PATready);
		}

		m_NIT = 0;
		if (m_ready_all & readyNIT)
		{
			m_NIT = new hdsTabelNit(m_scan_debug, m_hds_jurnal);
			if (m_NIT->start(m_demux, eDVBNITSpec()))
				return -1;
			CONNECT(m_NIT->tableReady, eDVBScan::NITready);
		}

		m_BAT = 0;
		if (m_ready_all & readyBAT)
		{
			m_BAT = new eTable<BouquetAssociationSection>(m_scan_debug);
			if (m_BAT->start(m_demux, eDVBBATSpec()))
				return -1;
			CONNECT(m_BAT->tableReady, eDVBScan::BATready);
		}

		/* HDSatelit (0.8.0): VCT-ul ATSC, odata cu PAT-ul; nu intra in m_ready_all pana nu vine o sectiune PSIP buna */
		hdsPornestePsip();
		/* HDSatelit (0.8.0): NIT-ul altor retele, la cautarea in retea pe satelit; nu intra in m_ready_all */
		hdsPornesteNitAlt();
	}
	return 0;
}

/* HDSatelit (0.8.0): VCT-ul ATSC cu numele canalelor americane (lib/dvb/hdsvct.h). Cititorul brut pe PID-ul PSIP (0x1FFB,
   tabelele 0xC0-0xCF) porneste odata cu PAT-ul, numai la cautarea pornita cu start(), pe satelit, cablu si terestru. Un
   transponder fara PSIP (Europa) nu asteapta nimic in plus: readyVCT intra in m_ready_all numai la prima sectiune MGT sau
   VCT buna, iar de acolo VCT-ul are hdsvct::RAGAZ_MS (mai mult la ratele mici) sa vina intreg. Un cititor care nu
   porneste (filtre epuizate) lasa cautarea ca inainte, fara nume din VCT. */
void eDVBScan::hdsPornestePsip()
{
	if (!m_hds_cautare || m_hds_psip || !m_demux)
		return;
	ePtr<iDVBSectionReader> cititor;
	if (m_demux->createSectionReader(eApp, cititor) || !cititor)
		return;
	eDVBSectionFilterMask masca;
	memset(&masca, 0, sizeof(masca));
	masca.pid = hdsvct::PID_PSIP;
	masca.flags = eDVBSectionFilterMask::rfCRC;
	masca.data[0] = 0xC0;
	masca.mask[0] = 0xF0;
	cititor->connectRead(sigc::mem_fun(*this, &eDVBScan::hdsSectiunePsip), m_hds_psip_conn);
	if (cititor->start(masca))
	{
		m_hds_psip_conn = 0;
		return;
	}
	m_hds_psip = cititor;
	m_hds_psip_t0 = hdsjurnal::monotonMs();
}

/* cititorul si plafonul VCT oprite (sectiunile stranse raman, pentru nume, pana la transponderul urmator) */
void eDVBScan::hdsOpresteVct()
{
	if (m_hds_psip)
		m_hds_psip->stop();
	m_hds_psip = 0;
	m_hds_psip_conn = 0;
	if (m_hds_vct_plafon)
		m_hds_vct_plafon->stop();
}

void eDVBScan::hdsSectiunePsip(const __u8 *data)
{
	/* tamponul cititorului are hdsvct::MAX_SECTIUNE octeti; lungimea si CRC-ul le verifica hdsvct */
	int r = m_hds_vct.adauga(data, hdsvct::MAX_SECTIUNE, (long)(hdsjurnal::monotonMs() - m_hds_psip_t0));
	if (r & hdsvct::Colector::COMPLET)
	{
		SCAN_eDebug("[eDVBScan] VCT %02x intreg: TSID %04x, %d canale", m_hds_vct.tabel(), m_hds_vct.tsid(),
			(int)m_hds_vct.canale().size());
		/* intai cititorul oprit, apoi transponderul poate trece mai departe; dupa channelDone nimic */
		hdsOpresteVct();
		hdsjscan::tabel(m_hds_jurnal, hdsjscan::TABEL_VCT, 0);
		m_ready_all |= readyVCT;
		m_ready |= readyVCT | validVCT;
		channelDone();
		return;
	}
	if (r & hdsvct::Colector::ARMAT)
	{
		m_ready_all |= readyVCT;
		if (!m_hds_vct_plafon)
		{
			m_hds_vct_plafon = eTimer::create(eApp);
			CONNECT(m_hds_vct_plafon->timeout, eDVBScan::hdsVctPlafon);
		}
		m_hds_vct_plafon->start(hdsscanreguli::timpTabel(hdsvct::RAGAZ_MS, hdsRataSatelit(m_ch_current)), true);
	}
}

/* VCT-ul n-a venit intreg in plafon: transponderul se termina fara el */
void eDVBScan::hdsVctPlafon()
{
	SCAN_eDebug("[eDVBScan] VCT neintreg in %d ms", hdsscanreguli::timpTabel(hdsvct::RAGAZ_MS, hdsRataSatelit(m_ch_current)));
	hdsOpresteVct();
	hdsjscan::tabel(m_hds_jurnal, hdsjscan::TABEL_VCT, -1);
	m_ready |= readyVCT;
	channelDone();
}

/* canalul din VCT-ul intreg al serviciului sid din acest flux (hdsvct::canalPentru), NULL daca nu e */
const hdsvct::Canal *eDVBScan::hdsCanalVct(int sid)
{
	if (!m_hds_vct.complet())
		return 0;
	return hdsvct::canalPentru(m_hds_vct.canale(), sid, m_hds_vct.tsid(), m_pat_tsid.get());
}

/* La sfarsitul transponderului, serviciile lui fara nume din SDT (gasite numai in PAT/PMT, cu numele facut din frecventa,
   sau cu numele din SDT gol) iau numele din VCT (hdsvct::vctCastiga); un nume adevarat din SDT ramane. Numarul canalului
   (major.minor) ramane numai in jurnal: lista de canale n-are camp pentru el, iar in nume ar schimba ordinea alfabetica si
   numele stiut de om. */
void eDVBScan::hdsNumeleDinVct()
{
	if (!m_hds_vct.complet() || !m_chid_current)
		return;
	for (std::map<eServiceReferenceDVB, ePtr<eDVBService> >::iterator s = m_new_services.begin(); s != m_new_services.end(); ++s)
	{
		eDVBChannelID chid;
		s->first.getChannelID(chid);
		if (!(chid == m_chid_current))
			continue;
		int sid = s->first.getServiceID().get();
		const hdsvct::Canal *c = hdsCanalVct(sid);
		if (!c)
			continue;
		std::string nume = hdsvct::numeCanal(*c);
		SCAN_eDebug("[eDVBScan] VCT: SID %04x canalul %d.%d '%s'%s", sid, c->major, c->minor, nume.c_str(),
			c->ascuns ? " (ascuns)" : "");
		if (nume.empty() || !hdsvct::vctCastiga(m_sdt_services.count(s->first) > 0, s->second->m_service_name))
			continue;
		s->second->m_service_name = nume;
		s->second->genSortName();
		m_hds_nume_vct[s->first] = !m_hds_tp_cu_sdt;
	}
}

void eDVBScan::SDTready(int err)
{
	SCAN_eDebug("got sdt %d", err);
	if (err && m_SDT)
	{
		eDVBTableSpec previous;
		if (!m_SDT->getSpec(previous)
			&& (previous.flags & eDVBTableSpec::tfHaveTIDExt))
		{
			// PAT si SDT pot avea TSID diferit. Reluam doar SDT actual.
			// Fara filtrul TSID, o a doua eroare nu mai reia citirea.
			eDVBTableSpec fallback = eDVBSDTSpec();
			fallback.timeout = hdsscanreguli::timpTabel(10000, hdsRataSatelit(m_ch_current));
			SCAN_eDebug("SDT pentru TSID %04x lipseste, reluam fara TSID",
				previous.tidext);
			m_SDT = new eTable<ServiceDescriptionSection>(m_scan_debug);
			CONNECT(m_SDT->tableReady, eDVBScan::SDTready);
			if (!m_SDT->start(m_demux, fallback))
				return;
			SCAN_eDebug("reluarea SDT actual nu a putut porni");
		}
	}
	hdsjscan::tabel(m_hds_jurnal, hdsjscan::TABEL_SDT, err);
	m_ready |= readySDT;
	if (!err)
		m_ready |= validSDT;
	channelDone();
}

void eDVBScan::NITready(int err)
{
	SCAN_eDebug("got nit, err %d", err);
	hdsjscan::tabel(m_hds_jurnal, hdsjscan::TABEL_NIT, err);
	m_ready |= readyNIT;
	if (!err)
		m_ready |= validNIT;
	channelDone();
}

void eDVBScan::BATready(int err)
{
	SCAN_eDebug("got bat");
	hdsjscan::tabel(m_hds_jurnal, hdsjscan::TABEL_BAT, err);
	m_ready |= readyBAT;
	if (!err)
		m_ready |= validBAT;
	channelDone();
}

void eDVBScan::PATready(int err)
{
	SCAN_eDebug("got pat");
	hdsjscan::tabel(m_hds_jurnal, hdsjscan::TABEL_PAT, err);
	m_ready |= readyPAT;
	if (!err)
		m_ready |= validPAT;
	startFilter(); // for starting the SDT filter
}

void eDVBScan::PMTready(int err)
{
	SCAN_eDebug("got pmt %d", err);
	if (!err)
	{
		bool scrambled = false;
		bool have_audio = false;
		bool have_video = false;
		unsigned short pcrpid = 0xFFFF;
		std::vector<ProgramMapSection*>::const_iterator i;

		for (i = m_PMT->getSections().begin(); i != m_PMT->getSections().end(); ++i)
		{
			const ProgramMapSection &pmt = **i;
			if (pcrpid == 0xFFFF)
				pcrpid = pmt.getPcrPid();
			else
				SCAN_eDebug("already have a pcrpid %04x %04x", pcrpid, pmt.getPcrPid());
			ElementaryStreamInfoConstIterator es;
			for (es = pmt.getEsInfo()->begin(); es != pmt.getEsInfo()->end(); ++es)
			{
				int isaudio = 0, isvideo = 0, is_scrambled = 0, forced_audio = 0, forced_video = 0;
				switch ((*es)->getType())
				{
				case 0x1b: // AVC Video Stream (MPEG4 H264)
				case 0x24: // H.265 HEVC
				case 0x27: // H.265 HEVC temporal video sub-bitstream
				case 0x10: // MPEG 4 Part 2
				case 0x01: // MPEG 1 video
				case 0x02: // MPEG 2 video
				case 0x42: // AVS / AVS+ (decodorul placii)
				case 0x33: // H.266 VVC (fara decodor)
				case 0xD2: // AVS2 (fara decodor)
				case 0xD4: // AVS3 (fara decodor); canalul ramane TV, cu mesajul cu numele formatului, nu radio
					isvideo = 1;
					forced_video = 1;
					//break; fall through !!!
				case 0x03: // MPEG 1 audio
				case 0x04: // MPEG 2 audio
				case 0x0f: // MPEG 2 AAC
				case 0x11: // MPEG 4 AAC
					if (!isvideo) 
					{
						forced_audio = 1;
						isaudio = 1;
					}
				case 0x81: // AC3 (ATSC/SCTE, America de Nord): audio si fara descriptorul AC3, ca in OE-Alliance (TC308)
				case 0x87: // E-AC3 (ATSC)
					if (!isvideo && !forced_audio)
						isaudio = 1;
					//break; fall through !!!
				case 0x06: // PES Private
				case 0xEA: // TS_PSI_ST_SMPTE_VC1
				{
					/* HDSatelit (0.7.5, TC308): descriptorii ATSC AC-3 (0x81) si E-AC-3 (0xCC) pe fluxuri 0x06/0x81/0x87, numai
					   fara private_data_specifier (0x5F) pe pista, ca in lib/dvb/pmt.cpp: canalul cu un asemenea sunet nu iese "date" */
					int hds_tip = (*es)->getType();
					bool hds_atsc = (hds_tip == 0x06 || hds_tip == 0x81 || hds_tip == 0x87);
					for (DescriptorConstIterator desc = (*es)->getDescriptors()->begin();
							hds_atsc && desc != (*es)->getDescriptors()->end(); ++desc)
					{
						if ((*desc)->getTag() == 0x5F) // private_data_specifier
							hds_atsc = false;
					}
					for (DescriptorConstIterator desc = (*es)->getDescriptors()->begin();
							desc != (*es)->getDescriptors()->end(); ++desc)
					{
						uint8_t tag = (*desc)->getTag();
						if (hds_atsc && !forced_video && !forced_audio && !isvideo && (tag == 0x81 || tag == 0xCC))
							isaudio = 1;
						/* PES private can contain AC-3, DTS or lots of other stuff.
						   check descriptors to get the exakt type. */
						if (!forced_video && !forced_audio)
						{
							switch (tag)
							{
							case 0x1C: // TS_PSI_DT_MPEG4_Audio
							case 0x2B: // TS_PSI_DT_MPEG2_AAC
							case AAC_DESCRIPTOR:
							case AC3_DESCRIPTOR:
							case ENHANCED_AC3_DESCRIPTOR: // 0x7a, E-AC-3 (Dolby Digital Plus)
							case DTS_DESCRIPTOR:
							case AUDIO_STREAM_DESCRIPTOR:
								isaudio = 1;
								break;
							case 0x28: // TS_PSI_DT_AVC
							case 0x1B: // TS_PSI_DT_MPEG4_Video
							case VIDEO_STREAM_DESCRIPTOR:
								isvideo = 1;
								break;
							case REGISTRATION_DESCRIPTOR: /* some services don't have a separate AC3 descriptor */
							{
								RegistrationDescriptor *d = (RegistrationDescriptor*)(*desc);
								switch (d->getFormatIdentifier())
								{
								case 0x44545331 ... 0x44545333: // DTS1/DTS2/DTS3
								case 0x41432d33: // == 'AC-3'
								case 0x42535344: // == 'BSSD' (LPCM)
									isaudio = 1;
									break;
								case 0x56432d31: // == 'VC-1'
								case 0x41563031: // == 'AV01' (AV1 fara decodor: canalul ramane TV, cu mesajul)
									isvideo = 1;
									break;
								default:
									break;
								}
							}
							default:
								break;
							}
						}
						if (tag == CA_DESCRIPTOR)
							is_scrambled = 1;
					}
				}
				//break; fall through !!!
				default:
					break;
				}
				if (isvideo)
					have_video = true;
				else if (isaudio)
					have_audio = true;
				else
					continue;
				if (is_scrambled)
					scrambled = true;
			}
			for (DescriptorConstIterator desc = pmt.getDescriptors()->begin();
				desc != pmt.getDescriptors()->end(); ++desc)
			{
				if ((*desc)->getTag() == CA_DESCRIPTOR)
					scrambled = true;
			}
		}
		m_pmt_in_progress->second.scrambled = scrambled;
		if ( have_video )
			m_pmt_in_progress->second.serviceType = 1;
		else if ( have_audio )
			m_pmt_in_progress->second.serviceType = 2;
		else
			m_pmt_in_progress->second.serviceType = 100;
	}
	if (err == -1) // timeout or removed by sdt
	{
		hdsjscan::pmtLipsa(m_hds_jurnal);  /* PMT-ul care n-a venit in plafonul lui (4 s, mai mult la ratele mici) sau scos de SDT */
		m_pmts_to_read.erase(m_pmt_in_progress++);
	}
	else if (m_pmt_running)
		++m_pmt_in_progress;
	else
	{
		m_pmt_in_progress = m_pmts_to_read.begin();
		m_pmt_running = true;
	}

	if (m_pmt_in_progress != m_pmts_to_read.end())
		m_PMT->start(m_demux, eDVBPMTSpec(m_pmt_in_progress->second.pmtPid, m_pmt_in_progress->first,
			hdsscanreguli::timpTabel(4000, hdsRataSatelit(m_ch_current))));
	else
	{
		m_PMT = 0;
		m_pmt_running = false;
		hdsjscan::tabel(m_hds_jurnal, hdsjscan::TABEL_PMT, 0);
		channelDone();
	}
}


void eDVBScan::addKnownGoodChannel(const eDVBChannelID &chid, iDVBFrontendParameters *feparm)
{
		/* add it to the list of known channels. */
	if (chid)
		m_new_channels.insert(std::pair<eDVBChannelID,ePtr<iDVBFrontendParameters> >(chid, feparm));
}

/* mai jos, langa hdsCelalaltSistem */
static bool hdsAltaVarianta(iDVBFrontendParameters *prins, iDVBFrontendParameters *alt);

void eDVBScan::addChannelToScan(const eDVBChannelID &chid, iDVBFrontendParameters *feparm)
{
		/* check if we don't already have that channel ... */

	int type;
	feparm->getSystem(type);

	switch(type)
	{
	case iDVBFrontend::feSatellite:
	{
		eDVBFrontendParametersSatellite parm;
		feparm->getDVBS(parm);
		SCAN_eDebug("try to add %d %d %d %d %d %d",
			parm.orbital_position, parm.frequency, parm.symbol_rate, parm.polarisation, parm.fec, parm.modulation);
		break;
	}
	case iDVBFrontend::feCable:
	{
		eDVBFrontendParametersCable parm;
		feparm->getDVBC(parm);
		SCAN_eDebug("try to add %d %d %d %d",
			parm.frequency, parm.symbol_rate, parm.modulation, parm.fec_inner);
		break;
	}
	case iDVBFrontend::feTerrestrial:
	{
		eDVBFrontendParametersTerrestrial parm;
		feparm->getDVBT(parm);
		SCAN_eDebug("try to add %d %d %d %d %d %d %d %d, %s, PLP %d",
			parm.frequency, parm.modulation, parm.transmission_mode, parm.hierarchy,
			parm.guard_interval, parm.code_rate_LP, parm.code_rate_HP, parm.bandwidth,
			hdster::sistemNormalizat(parm.system) == hdster::SISTEM_T2 ? "DVB-T2" : "DVB-T", parm.plp_id);
		break;
	}
	}

	int found_count=0;
		/* ... in the list of channels to scan */
	for (std::list<ePtr<iDVBFrontendParameters> >::iterator i(m_ch_toScan.begin()); i != m_ch_toScan.end();)
	{
		if (sameChannel(*i, feparm))
		{
			if (!found_count)
			{
				*i = feparm;  // update
				hdsNoteFromNIT(chid, feparm);
				SCAN_eDebug("update");
			}
			else
			{
				SCAN_eDebug("remove dupe");
				m_ch_toScan.erase(i++);
				continue;
			}
			++found_count;
		}
		++i;
	}

	if (found_count > 0)
	{
		SCAN_eDebug("already in todo list");
		return;
	}

		/* ... in the list of successfully scanned channels */
	for (std::list<ePtr<iDVBFrontendParameters> >::const_iterator i(m_ch_scanned.begin()); i != m_ch_scanned.end(); ++i)
		if (sameChannel(*i, feparm))
		{
			SCAN_eDebug("successfully scanned");
			return;
		}
		else if (hdsAltaVarianta(*i, feparm))
		{
			/* NIT-ul anunta alta varianta (rata, sistem, FEC) a unei purtatori deja prinse: nu se adauga (hdsAltaVarianta) */
			SCAN_eDebug("other variant of a scanned carrier");
			return;
		}

		/* ... in the list of unavailable channels */
	for (std::list<ePtr<iDVBFrontendParameters> >::const_iterator i(m_ch_unavailable.begin()); i != m_ch_unavailable.end(); ++i)
		if (sameChannel(*i, feparm, true))
		{
			SCAN_eDebug("scanned but not available");
			return;
		}

		/* ... on the current channel */
	if (sameChannel(m_ch_current, feparm))
	{
		SCAN_eDebug("is current");
		return;
	}

	SCAN_eDebug("really add");
		/* otherwise, add it to the todo list. */
	hdsNoteFromNIT(chid, feparm);
	m_ch_toScan.push_front(feparm); // better.. then the rotor not turning wild from east to west :)
}

/* HDSatelit: the tsid/onid the NIT announced for a transponder it added to the todo list, for /api/scanare-ultima
   (a transponder without signal has no channel id of its own). Only read by getScannedTransponders. */
void eDVBScan::hdsNoteFromNIT(const eDVBChannelID &chid, iDVBFrontendParameters *feparm)
{
	if (!feparm)
		return;
	if (m_nit_chid.find(feparm) == m_nit_chid.end())
		m_nit_chid_refs.push_back(ePtr<iDVBFrontendParameters>(feparm));
	m_nit_chid[feparm] = chid;
}

/* HDSatelit: the NIT of the current transponder for /api/scanare-ultima (hdsretea.h); only where the scan reads the
   NIT anyway. Nothing of it changes what is scanned or what goes to the channel list. */
void eDVBScan::hdsNoteNIT()
{
	if (!m_NIT || !m_ch_current)
		return;
	std::vector<NetworkInformationSection*>::const_iterator i;
	for (i = m_NIT->getSections().begin(); i != m_NIT->getSections().end(); ++i)
		m_network_on_tp[(iDVBFrontendParameters*)m_ch_current] = m_networks.adaugaSectiune(**i);
}

int eDVBScan::sameChannel(iDVBFrontendParameters *ch1, iDVBFrontendParameters *ch2, bool exact) const
{
	int diff;
	if (ch1->calculateDifference(ch2, diff, exact))
		return 0;
	/* HDSatelit (0.8.0): pe satelit frecventele trebuie sa fie in fereastra ratei mai mici (lib/dvb/hdsscanreguli.h,
	   fereastraUnireKhz): doua purtatoare inguste la 1 MHz una de alta nu mai sunt unite; de la 6 MS/s fereastra e 4 MHz,
	   ca inainte. NIT9: frecventa si rata se judeca separat (aceeasiIntrare), nu prin suma lor sub 4000: 29900 fata de
	   30000 kS/s pe aceeasi frecventa e aceeasi intrare */
	int a, b;
	eDVBFrontendParametersSatellite p, q;
	if (!ch1->getSystem(a) && !ch2->getSystem(b) && a == iDVBFrontend::feSatellite && b == iDVBFrontend::feSatellite &&
		!ch1->getDVBS(p) && !ch2->getDVBS(q))
		return hdsscanreguli::aceeasiIntrare(diff, (long)p.frequency, (long)q.frequency, (long)p.symbol_rate,
			(long)q.symbol_rate) ? 1 : 0;
	if (diff >= 4000) // more than 4mhz difference?
		return 0;
	return 1;
}

/* Un multiplex terestru prins pe o frecventa: aceeasi frecventa cu celalalt sistem nu se mai incearca (cautarea fara
   sistem stiut le pune pe amandoua, DVB-T2 si DVB-T), afara de un PLP ales diferit, care e alt multiplex. */
static bool hdsCelalaltSistem(iDVBFrontendParameters *prins, iDVBFrontendParameters *alt)
{
	int a, b;
	if (!prins || !alt || prins->getSystem(a) || alt->getSystem(b))
		return false;
	if (a != iDVBFrontend::feTerrestrial || b != iDVBFrontend::feTerrestrial)
		return false;
	eDVBFrontendParametersTerrestrial p, q;
	if (prins->getDVBT(p) || alt->getDVBT(q))
		return false;
	return hdster::sistemNormalizat(p.system) != hdster::sistemNormalizat(q.system)
		&& hdster::aceeasiFrecventa(p.frequency, q.frequency) && hdster::acelasiPlp(p.plp_id, q.plp_id);
}

/* HDSatelit (SCV, 15.11.2026): aceeasi purtatoare de satelit cu alti parametri. Listele vechi (satellites.xml, lamedb) si
   NIT-urile altor retele pastreaza pe aceeasi frecventa si polarizare rata, sistemul sau FEC-ul de dinainte (Hotbird 13E:
   11938 H 27500 langa 11938 H 30000, 12207 H 29900 langa 12207 H 27500). sameChannel nu le uneste (diferenta lui aduna kHz
   si simboli/s, deci 2500000 la 27500 fata de 30000), iar varianta veche se incerca si se dadea fara semnal dupa 3 s
   (pe receptorul de probe, Hotbird: 7 din cele 43 fara semnal erau asa, 5 dupa ce varianta buna fusese deja prinsa).
   Pe aceeasi pozitie, polarizare, flux (ISI, cod Gold) si PLP T2-MI, la cel mult HDS_VARIANTA_KHZ de o purtatoare PRINSA
   cu rata de macar HDS_VARIANTA_SR_MIN nu poate fi alta purtatoare: banda celei prinse (peste 13 MHz) o acopera.
   Se sare numai fata de una prinsa (m_ch_scanned), niciodata fata de una fara semnal: o varianta veche moarta nu opreste
   varianta noua. Fluxurile multistream si PLP-urile T2-MI diferite raman (alt flux pe aceeasi purtatoare = alte canale). */
enum { HDS_VARIANTA_KHZ = 4000, HDS_VARIANTA_SR_MIN = 10000000 };

static bool hdsAltaVarianta(iDVBFrontendParameters *prins, iDVBFrontendParameters *alt)
{
	int a, b;
	if (!prins || !alt || prins == alt || prins->getSystem(a) || alt->getSystem(b))
		return false;
	if (a != iDVBFrontend::feSatellite || b != iDVBFrontend::feSatellite)
		return false;
	eDVBFrontendParametersSatellite p, q;
	if (prins->getDVBS(p) || alt->getDVBS(q))
		return false;
	return p.orbital_position == q.orbital_position && p.polarisation == q.polarisation
		&& p.symbol_rate >= HDS_VARIANTA_SR_MIN
		&& abs((int)p.frequency - (int)q.frequency) <= HDS_VARIANTA_KHZ
		&& hdsms::acelasiFlux(hdsms::cheie(p.is_id, p.pls_mode, p.pls_code), hdsms::cheie(q.is_id, q.pls_mode, q.pls_code))
		&& p.t2mi_plp_id == q.t2mi_plp_id;
}

/* HDSatelit (0.8.0): ce stie scanarea si lista de canale despre un transponder de satelit (lib/dvb/hdsscanreguli.h) */
static hdsscanreguli::Vazut hdsVazut(iDVBFrontendParameters *p)
{
	int tip;
	eDVBFrontendParametersSatellite sat;
	if (!p || p->getSystem(tip) || tip != iDVBFrontend::feSatellite || p->getDVBS(sat))
		return hdsscanreguli::nevazut();
	return hdsscanreguli::vazut((long)sat.frequency, sat.polarisation, (long)sat.symbol_rate);
}

static hdsscanreguli::Vazut hdsVazutInLista(iDVBChannelList *db, const eDVBChannelID &chid)
{
	ePtr<iDVBFrontendParameters> p;
	if (!db || db->getChannelFrontendData(chid, p) || !p)
		return hdsscanreguli::nevazut();
	return hdsVazut(p);
}

/* HDSatelit (0.8.0): continutul SDT-ului de acum (fiecare serviciu cu SID-ul, tipul si numele, in ordinea SID), ca doua
   prinderi cu acelasi TSID si ONID sa se poata deosebi: acelasi continut e acelasi flux */
std::string eDVBScan::hdsContinutSdt()
{
	std::map<unsigned short, std::string> servicii;
	if (!m_SDT)
		return std::string();
	std::vector<ServiceDescriptionSection*>::const_iterator i;
	for (i = m_SDT->getSections().begin(); i != m_SDT->getSections().end(); ++i)
	{
		const ServiceDescriptionList &lista = *(*i)->getDescriptions();
		for (ServiceDescriptionConstIterator s(lista.begin()); s != lista.end(); ++s)
		{
			std::string text;
			for (DescriptorConstIterator d = (*s)->getDescriptors()->begin(); d != (*s)->getDescriptors()->end(); ++d)
				if ((*d)->getTag() == SERVICE_DESCRIPTOR)
				{
					ServiceDescriptor &sd = (ServiceDescriptor&)**d;
					char tip[8];
					snprintf(tip, sizeof(tip), "%d:", sd.getServiceType());
					text = tip + sd.getServiceProviderName() + "/" + sd.getServiceName();
				}
			servicii[(*s)->getServiceId()] = text;
		}
	}
	std::string continut;
	for (std::map<unsigned short, std::string>::const_iterator s = servicii.begin(); s != servicii.end(); ++s)
	{
		char sid[8];
		snprintf(sid, sizeof(sid), "%04x=", s->first);
		continut += sid + s->second + "\n";
	}
	return continut;
}

/* HDSatelit (0.8.0): acelasi TSID si ONID pe mai multe transpondere ale aceluiasi satelit (de pilda 55.6W in banda C:
   3925 V, 4015 V, 4050 V). Cu ONID-ul valid namespace-ul nu are frecventa, deci al doilea transponder il suprascria pe
   primul in lista (canalele unuia disparute sau pornite pe celalalt). Acum transponderul prins primul ramane pe namespace-ul
   de pana acum, iar al doilea primeste namespace-ul cu frecventa (ca transponderele cu ONID invalid), numai la coliziune
   adevarata (hdsscanreguli::namespaceCuFrecventa). Fara coliziune totul ramane exact ca inainte (Europa: aceleasi
   referinte). La sfarsit hdsColiziuniLaSfarsit da namespace-ul de pana acum transponderului pe care lista il avea deja. */
eDVBNamespace eDVBScan::hdsNamespaceLaColiziune(eDVBNamespace ns, eOriginalNetworkID onid, eTransportStreamID tsid,
	unsigned long hash)
{
	/* numai namespace-ul fara frecventa (ONID valid) poate avea coliziuni; cel cu frecventa e deja unic */
	if (!(hash & 0xFFFF) || (unsigned int)ns.get() != (unsigned int)(hash & ~0xFFFFUL))
		return ns;
	hdsscanreguli::Vazut acum = hdsVazut(m_ch_current);
	if (!acum.exista)
		return ns;
	eDVBNamespace ns_frecventa((int)(unsigned int)hash);
	eDVBChannelID orb(ns, tsid, onid), cu_frecventa(ns_frecventa, tsid, onid);
	std::map<eDVBChannelID, ePtr<iDVBFrontendParameters> >::const_iterator in_cautare = m_new_channels.find(orb);
	hdsscanreguli::Vazut vazut_cautare = in_cautare != m_new_channels.end() ? hdsVazut(in_cautare->second) :
		hdsscanreguli::nevazut();
	std::map<eDVBChannelID, std::string>::const_iterator continut = m_hds_continut.find(orb);
	bool acelasi_continut = continut != m_hds_continut.end() && continut->second == hdsContinutSdt();
	eDVBDB *db = eDVBDB::getInstance();
	hdsscanreguli::Vazut lista_orb = hdsVazutInLista(db, orb);
	bool lista_frecventa = hdsVazutInLista(db, cu_frecventa).exista;
	if (!hdsscanreguli::namespaceCuFrecventa(acum, vazut_cautare, acelasi_continut, lista_orb, lista_frecventa))
		return ns;
	eDebug("[eDVBScan] TSID %04x ONID %04x e deja pe alt transponder: %ld %d primeste namespace-ul %08x",
		tsid.get(), onid.get(), acum.frecventa, acum.polarizare, (unsigned int)ns_frecventa.get());
	if (vazut_cautare.exista)
	{
		std::list<eDVBChannelID> &grup = m_hds_coliziuni[orb];
		if (std::find(grup.begin(), grup.end(), cu_frecventa) == grup.end())
			grup.push_back(cu_frecventa);
	}
	return ns_frecventa;
}

/* muta transponderul si serviciile lui gasite in aceasta cautare de pe un (namespace, TSID, ONID) pe altul */
void eDVBScan::hdsMutaCanal(const eDVBChannelID &din, const eDVBChannelID &spre)
{
	std::map<eDVBChannelID, ePtr<iDVBFrontendParameters> >::iterator c = m_new_channels.find(din);
	if (c != m_new_channels.end())
	{
		ePtr<iDVBFrontendParameters> p = c->second;
		m_new_channels.erase(c);
		m_new_channels[spre] = p;
	}
	std::map<eDVBChannelID, ePyObjectWrapper>::iterator t = m_tuner_data.find(din);
	if (t != m_tuner_data.end())
	{
		ePyObjectWrapper w = t->second;
		m_tuner_data.erase(t);
		m_tuner_data.insert(std::pair<eDVBChannelID, ePyObjectWrapper>(spre, w));
	}
	std::list<std::pair<eServiceReferenceDVB, ePtr<eDVBService> > > mutate;
	for (std::map<eServiceReferenceDVB, ePtr<eDVBService> >::iterator s = m_new_services.begin(); s != m_new_services.end();)
	{
		eDVBChannelID chid;
		s->first.getChannelID(chid);
		if (chid == din)
		{
			mutate.push_back(*s);
			m_new_services.erase(s++);
		}
		else
			++s;
	}
	for (std::list<std::pair<eServiceReferenceDVB, ePtr<eDVBService> > >::iterator m = mutate.begin(); m != mutate.end(); ++m)
	{
		eServiceReferenceDVB ref = m->first;
		bool din_sdt = m_sdt_services.erase(ref) > 0;
		std::map<eServiceReferenceDVB, bool>::iterator vct = m_hds_nume_vct.find(ref);
		bool din_vct = vct != m_hds_nume_vct.end(), vct_fara_sdt = din_vct && vct->second;
		if (din_vct)
			m_hds_nume_vct.erase(vct);
		ref.set(spre);
		m_new_services[ref] = m->second;
		if (din_sdt)
			m_sdt_services.insert(ref);
		if (din_vct)
			m_hds_nume_vct[ref] = vct_fara_sdt;
	}
	m_last_service = m_new_services.end();
}

/* HDSatelit (0.8.0): la sfarsitul cautarii, in fiecare grup de coliziune, namespace-ul de pana acum (ns_orb) il pastreaza
   transponderul pe care lista il avea deja sub el (hdsscanreguli::pastratorNamespace), oricare ar fi fost ordinea
   cautarii: bucheturile si temporizatoarele omului arata tot ce aratau. Fara intrare in lista: ramane cel prins primul. */
void eDVBScan::hdsColiziuniLaSfarsit(iDVBChannelList *db)
{
	for (std::map<eDVBChannelID, std::list<eDVBChannelID> >::iterator g = m_hds_coliziuni.begin(); g != m_hds_coliziuni.end(); ++g)
	{
		const eDVBChannelID &orb = g->first;
		std::map<eDVBChannelID, ePtr<iDVBFrontendParameters> >::iterator primul = m_new_channels.find(orb);
		if (primul == m_new_channels.end())
			continue;
		std::vector<hdsscanreguli::Vazut> grup;
		std::vector<eDVBChannelID> chiduri;
		grup.push_back(hdsVazut(primul->second));
		chiduri.push_back(orb);
		for (std::list<eDVBChannelID>::iterator m = g->second.begin(); m != g->second.end(); ++m)
		{
			std::map<eDVBChannelID, ePtr<iDVBFrontendParameters> >::iterator c = m_new_channels.find(*m);
			grup.push_back(c != m_new_channels.end() ? hdsVazut(c->second) : hdsscanreguli::nevazut());
			chiduri.push_back(*m);
		}
		int i = hdsscanreguli::pastratorNamespace(&grup[0], (int)grup.size(), hdsVazutInLista(db, orb));
		if (i <= 0)
			continue;
		/* primul trece pe namespace-ul cu frecventa lui, iar cel din lista inapoi pe ns_orb */
		unsigned long hash = 0;
		primul->second->getHash(hash);
		eDVBChannelID primul_nou(eDVBNamespace((int)(unsigned int)hash), orb.transport_stream_id, orb.original_network_id);
		eDVBChannelID temporar(eDVBNamespace((int)0xFFFFFFFEu), orb.transport_stream_id, orb.original_network_id);
		eDebug("[eDVBScan] TSID %04x ONID %04x: namespace-ul %08x ramane transponderului din lista (%ld %d)",
			orb.transport_stream_id.get(), orb.original_network_id.get(), (unsigned int)orb.dvbnamespace.get(),
			grup[i].frecventa, grup[i].polarizare);
		hdsMutaCanal(orb, temporar);
		hdsMutaCanal(chiduri[i], orb);
		hdsMutaCanal(temporar, primul_nou);
	}
	m_hds_coliziuni.clear();
}

/* HDSatelit (0.8.0): o intrare de satelit fara flux (fara descriptorul 0x79) pe purtatoarea multistream a unei intrari stiute
   cu flux (aceeasi pozitie si polarizare, sub 4 MHz): e aceeasi purtatoare, numai ca fara flux ales */
static bool hdsFaraFluxPeMultistream(iDVBFrontendParameters *stiut, iDVBFrontendParameters *nou)
{
	int a, b;
	if (!stiut || !nou || stiut->getSystem(a) || nou->getSystem(b) || a != iDVBFrontend::feSatellite ||
			b != iDVBFrontend::feSatellite)
		return false;
	eDVBFrontendParametersSatellite p, q;
	if (stiut->getDVBS(p) || nou->getDVBS(q))
		return false;
	return p.needsStreamSelection() && !q.needsStreamSelection() && p.orbital_position == q.orbital_position &&
		p.polarisation == q.polarisation && abs((int)p.frequency - (int)q.frequency) < 4000;
}

/* HDSatelit (0.8.0): NIT-ul altor retele numai adauga transpondere noi. O intrare deja de cautat ramane cum e (din lista
   omului sau din NIT-ul actual: campuri pe care un NIT nu le poarta, de pilda PLP-ul T2-MI, nu se pierd; addChannelToScan
   ar fi suprascris-o), iar o intrare fara flux pe o purtatoare multistream stiuta cu flux (de cautat, cautata sau acordata
   acum) nu se mai pune. Restul (cautat, fara semnal, acordat acum) il hotaraste addChannelToScan, ca la NIT-ul actual. */
bool eDVBScan::hdsStiutPentruNitAlt(iDVBFrontendParameters *feparm)
{
	for (std::list<ePtr<iDVBFrontendParameters> >::const_iterator t(m_ch_toScan.begin()); t != m_ch_toScan.end(); ++t)
		if (sameChannel(*t, feparm) || hdsFaraFluxPeMultistream(*t, feparm))
			return true;
	for (std::list<ePtr<iDVBFrontendParameters> >::const_iterator c(m_ch_scanned.begin()); c != m_ch_scanned.end(); ++c)
		if (hdsFaraFluxPeMultistream(*c, feparm))
			return true;
	return hdsFaraFluxPeMultistream(m_ch_current, feparm);
}

/* HDSatelit (0.8.0): descriptorul S2 (0x79) al unei intrari din NIT: fluxul (ISI) si indexul secventei Gold ale
   transponderului din descriptorul de satelit (0x43) al aceleiasi intrari; la NIT-ul actual si la cel al altor retele */
static void hdsS2DinNit(const TransportStreamInfo &tsinfo, bool &s2_gasit, int &s2_isi, int &s2_gold)
{
	for (DescriptorConstIterator desc = tsinfo.getDescriptors()->begin();
			desc != tsinfo.getDescriptors()->end(); ++desc)
	{
		if ((*desc)->getTag() != S2_SATELLITE_DELIVERY_SYSTEM_DESCRIPTOR)
			continue;
		S2SatelliteDeliverySystemDescriptor &d = (S2SatelliteDeliverySystemDescriptor&)**desc;
		s2_gasit = true;
		if (d.getMultipleInputStreamFlag())
			s2_isi = d.getInputStreamIdentifier();
		if (d.getScramblingSequenceSelector())
			s2_gold = d.getScramblingSequenceIndex() & hdsms::PLS_MASCA;
	}
}

/* HDSatelit (0.8.0): transponderul anuntat de descriptorul de satelit (0x43) al unei intrari din NIT intra in cautare numai
   daca e pe satelitul acordat (hdsscanreguli::pozitieDinNit: sub 0,5 grade; la NIT-ul actual si cu steagul est/vest gresit,
   la NIT-ul altor retele, alta_retea, nu); altfel se arunca. Acelasi drum pentru NIT-ul actual (0x40) si cel al altor
   retele (0x41). */
void eDVBScan::hdsSatelitDinNit(SatelliteDeliverySystemDescriptor &d, eOriginalNetworkID onid, eTransportStreamID tsid,
	bool s2_gasit, int s2_isi, int s2_gold, bool alta_retea)
{
	if (d.getFrequency() < 10000)
		return;

	ePtr<eDVBFrontendParameters> feparm = new eDVBFrontendParameters;
	eDVBFrontendParametersSatellite sat;
	sat.set(d);

	eDVBFrontendParametersSatellite p;
	m_ch_current->getDVBS(p);

	int hds_poz = hdsscanreguli::pozitieDinNit(p.orbital_position, sat.orbital_position, alta_retea);
	if (hds_poz == hdsscanreguli::POZITIE_EST_VEST)
		SCAN_eDebug("found transponder with incorrect west/east flag ... correct this");
	if (hds_poz != hdsscanreguli::POZITIE_ALT_SATELIT)
		sat.orbital_position = p.orbital_position;

	if (s2_gasit)
	{
		sat.is_id = s2_isi;
		sat.pls_mode = eDVBFrontendParametersSatellite::PLS_Gold;
		sat.pls_code = s2_gold;
		if (sat.needsStreamSelection())
			sat.system = eDVBFrontendParametersSatellite::System_DVB_S2;
	}
	else if (p.needsStreamSelection() && sat.orbital_position == p.orbital_position
		&& sat.polarisation == p.polarisation
		&& abs((int)sat.frequency - (int)p.frequency) < 4000)
	{
		// acelasi purtator multistream, fara 0x79: se tine fluxul acordat, altfel transponderul ar intra
		// in lamedb peste cel acordat, fara flux, si canalele lui n-ar mai porni
		sat.is_id = p.is_id;
		sat.pls_mode = p.pls_mode;
		sat.pls_code = p.pls_code;
		sat.system = p.system;
	}

	feparm->setDVBS(sat);

	if (!alta_retea && p.orbital_position == sat.orbital_position)
	{
		/* NIT9: descriptorul propriu al transponderului din NIT-ul actual (reteaua lui), pentru intrarile prinse care au
		   venit numai din NIT other (hdsParametriNitAlt) */
		m_hds_nit_propriu[std::make_pair(((unsigned int)onid.get() << 16) | (unsigned int)tsid.get(),
			sat.orbital_position)] = sat;
	}
	if ( p.orbital_position != sat.orbital_position)
		SCAN_eDebug("dropping this transponder, it's on another satellite.");
	else if (alta_retea && hdsStiutPentruNitAlt(feparm))
		SCAN_eDebug("already known, kept as it is (other network)");
	else
	{
		unsigned long hash=0;
		feparm->getHash(hash);
		eDVBChannelID chid(buildNamespace(onid, tsid, hash), tsid, onid);
		if (alta_retea)
		{
			m_hds_nit_alt_amanate.push_back(std::make_pair(chid, ePtr<iDVBFrontendParameters>(feparm)));  /* nextChannel, la sfarsit */
			m_hds_din_nit_alt.push_back(ePtr<iDVBFrontendParameters>(feparm));
		}
		else
			addChannelToScan(chid, feparm);
	}
}

/* HDSatelit (0.8.0): NIT-ul altor retele (0x41, acelasi PID cu NIT-ul actual), numai la cautarea in retea pe satelit pornita
   cu start(). Se culege ce vine cat transponderul isi citeste celelalte tabele: nu intra in m_ready_all, deci nu lungeste
   cautarea. La sfarsitul transponderului (hdsNitAltaRetea) fiecare intrare trece prin hdsSatelitDinNit, cu regula
   pozitiei fara indreptarea est/vest: transponderele altui satelit se arunca. Ce n-a venit pe un transponder vine pe altul
   al aceleiasi retele (NIT-ul altor retele se repeta pe fiecare). */
enum { HDS_NIT_ALT_MAX_SECTIUNI = 256, HDS_NIT_ALT_MAX_OCTETI = 1024 };

void eDVBScan::hdsPornesteNitAlt()
{
	int tip;
	if (!m_hds_cautare || m_hds_nit_alt || !m_demux || !m_ch_current || !hdsretea::adaugaFrecventeleDinNit(m_flags) ||
			m_ch_current->getSystem(tip) || tip != iDVBFrontend::feSatellite)
		return;
	ePtr<iDVBSectionReader> cititor;
	if (m_demux->createSectionReader(eApp, cititor) || !cititor)
		return;
	eDVBSectionFilterMask masca;
	memset(&masca, 0, sizeof(masca));
	masca.pid = NetworkInformationSection::PID;
	masca.flags = eDVBSectionFilterMask::rfCRC;
	masca.data[0] = 0x41;    /* network_information_section - other_network */
	masca.mask[0] = 0xFF;
	cititor->connectRead(sigc::mem_fun(*this, &eDVBScan::hdsSectiuneNitAlt), m_hds_nit_alt_conn);
	if (cititor->start(masca))
	{
		m_hds_nit_alt_conn = 0;
		return;
	}
	m_hds_nit_alt = cititor;
}

void eDVBScan::hdsOpresteNitAlt()
{
	if (m_hds_nit_alt)
		m_hds_nit_alt->stop();
	m_hds_nit_alt = 0;
	m_hds_nit_alt_conn = 0;
}

/* o sectiune NIT other: numai tinuta minte (ultima venita pe fiecare retea si numar de sectiune), cu plafon; nimic
   altceva nu se schimba aici */
void eDVBScan::hdsSectiuneNitAlt(const __u8 *data)
{
	size_t n = hdsvct::lungimeBuna(data, hdsvct::MAX_SECTIUNE);
	if (!n || n > (size_t)HDS_NIT_ALT_MAX_OCTETI || data[0] != 0x41 || !(data[5] & 0x01))
		return;
	unsigned int cheie = ((unsigned int)((data[3] << 8) | data[4]) << 8) | data[6];
	if (m_hds_nit_alt_sectiuni.size() >= (size_t)HDS_NIT_ALT_MAX_SECTIUNI && !m_hds_nit_alt_sectiuni.count(cheie))
		return;
	m_hds_nit_alt_sectiuni[cheie].assign(data, data + n);
}

/* la sfarsitul transponderului: transponderele anuntate de NIT-ul altor retele pe satelitul acordat intra in cautare, ca
   cele din NIT-ul actual; numai cand frecventele din NIT intra in cautare si nu cat lista se mai poate inlocui cu primul
   NIT (clearToScanOnFirstNIT) */
void eDVBScan::hdsNitAltaRetea()
{
	hdsOpresteNitAlt();
	int tip;
	if (!m_hds_nit_alt_sectiuni.empty() && hdsretea::adaugaFrecventeleDinNit(m_flags) &&
		!(m_flags & clearToScanOnFirstNIT) && m_ch_current && !m_ch_current->getSystem(tip) &&
		tip == iDVBFrontend::feSatellite)
	{
		size_t inainte = m_ch_toScan.size();
		for (std::map<unsigned int, std::vector<__u8> >::const_iterator s = m_hds_nit_alt_sectiuni.begin();
				s != m_hds_nit_alt_sectiuni.end(); ++s)
		{
			NetworkInformationSection nit(&s->second[0]);
			const TransportStreamInfoList &lista = *nit.getTsInfo();
			for (TransportStreamInfoConstIterator ts(lista.begin()); ts != lista.end(); ++ts)
			{
				bool s2_gasit = false;
				int s2_isi = hdsms::ISI_FARA_FILTRU, s2_gold = 0;
				hdsS2DinNit(**ts, s2_gasit, s2_isi, s2_gold);
				for (DescriptorConstIterator desc = (*ts)->getDescriptors()->begin();
						desc != (*ts)->getDescriptors()->end(); ++desc)
				{
					if ((*desc)->getTag() == SATELLITE_DELIVERY_SYSTEM_DESCRIPTOR)
						hdsSatelitDinNit((SatelliteDeliverySystemDescriptor&)**desc, (*ts)->getOriginalNetworkId(),
							(*ts)->getTransportStreamId(), s2_gasit, s2_isi, s2_gold, true);
				}
			}
		}
		SCAN_eDebug("[eDVBScan] NIT other: %d sectiuni, transpondere de cautat %d -> %d, tinute pentru sfarsit %d",
			(int)m_hds_nit_alt_sectiuni.size(), (int)inainte, (int)m_ch_toScan.size(), (int)m_hds_nit_alt_amanate.size());
	}
	m_hds_nit_alt_sectiuni.clear();
}

void eDVBScan::channelDone()
{
	if (m_ready & validSDT && (!(m_flags & scanOnlyFree) || !m_pmt_running))
	{
		unsigned long hash = 0;

		m_ch_current->getHash(hash);
		
		eDVBNamespace dvbnamespace = buildNamespace(
			(**m_SDT->getSections().begin()).getOriginalNetworkId(),
			(**m_SDT->getSections().begin()).getTransportStreamId(),
			hash);
		dvbnamespace = hdsNamespaceLaColiziune(dvbnamespace,
			(**m_SDT->getSections().begin()).getOriginalNetworkId(),
			(**m_SDT->getSections().begin()).getTransportStreamId(), hash);
		/* ca m_new_channels: ramane continutul transponderului prins primul sub acest chid */
		m_hds_continut.insert(std::make_pair(eDVBChannelID(dvbnamespace,
			(**m_SDT->getSections().begin()).getTransportStreamId(),
			(**m_SDT->getSections().begin()).getOriginalNetworkId()), hdsContinutSdt()));
		
		SCAN_eDebug("SDT: ");
		m_hds_tp_cu_sdt = true;  /* numele din VCT de pe acest transponder nu inlocuiesc nume bune in lista */
		std::vector<ServiceDescriptionSection*>::const_iterator i;
		for (i = m_SDT->getSections().begin(); i != m_SDT->getSections().end(); ++i)
			processSDT(dvbnamespace, **i);
		m_ready &= ~validSDT;
	}
	
	if (m_ready & validNIT)
	{
		int system;
		std::list<ePtr<iDVBFrontendParameters> > m_ch_toScan_backup;
		m_ch_current->getSystem(system);
		SCAN_eDebug("dumping NIT");
		hdsNoteNIT();
		/* HDSatelit: la NIT-ul numai pentru informatie reteaua ramane in colector, dar frecventele anuntate nu intra
		   in scanare: se scaneaza tot numai ce s-a ales */
		bool hds_adauga = hdsretea::adaugaFrecventeleDinNit(m_flags);
		if (hds_adauga && (m_flags & clearToScanOnFirstNIT))
		{
			m_ch_toScan_backup = m_ch_toScan;
			m_ch_toScan.clear();
		}
		std::vector<NetworkInformationSection*>::const_iterator i;
		for (i = m_NIT->getSections().begin(); hds_adauga && i != m_NIT->getSections().end(); ++i)
		{
			const TransportStreamInfoList &tsinfovec = *(*i)->getTsInfo();
			
			for (TransportStreamInfoConstIterator tsinfo(tsinfovec.begin()); 
				tsinfo != tsinfovec.end(); ++tsinfo)
			{
				SCAN_eDebug("TSID: %04x ONID: %04x", (*tsinfo)->getTransportStreamId(),
					(*tsinfo)->getOriginalNetworkId());
				
				eOriginalNetworkID onid = (*tsinfo)->getOriginalNetworkId();
				eTransportStreamID tsid = (*tsinfo)->getTransportStreamId();

				// descriptorul S2 (0x79) poarta fluxul (ISI) si indexul secventei Gold ale transponderului din 0x43
				bool s2_gasit = false;
				int s2_isi = hdsms::ISI_FARA_FILTRU, s2_gold = 0;
				hdsS2DinNit(**tsinfo, s2_gasit, s2_isi, s2_gold);

				for (DescriptorConstIterator desc = (*tsinfo)->getDescriptors()->begin();
						desc != (*tsinfo)->getDescriptors()->end(); ++desc)
				{
					switch ((*desc)->getTag())
					{
					case CABLE_DELIVERY_SYSTEM_DESCRIPTOR:
					{
						if (system != iDVBFrontend::feCable)
							break; // when current locked transponder is no cable transponder ignore this descriptor
						CableDeliverySystemDescriptor &d = (CableDeliverySystemDescriptor&)**desc;
						ePtr<eDVBFrontendParameters> feparm = new eDVBFrontendParameters;
						eDVBFrontendParametersCable cable;
						cable.set(d);
						feparm->setDVBC(cable);

						unsigned long hash=0;
						feparm->getHash(hash);
						eDVBNamespace ns = buildNamespace(onid, tsid, hash);

						addChannelToScan(
							eDVBChannelID(ns, tsid, onid),
							feparm);
						break;
					}
					case TERRESTRIAL_DELIVERY_SYSTEM_DESCRIPTOR:
					{
						if (system != iDVBFrontend::feTerrestrial)
							break; // when current locked transponder is no terrestrial transponder ignore this descriptor
						TerrestrialDeliverySystemDescriptor &d = (TerrestrialDeliverySystemDescriptor&)**desc;
						ePtr<eDVBFrontendParameters> feparm = new eDVBFrontendParameters;
						eDVBFrontendParametersTerrestrial terr;
						terr.set(d);
						feparm->setDVBT(terr);

						unsigned long hash=0;
						feparm->getHash(hash);
						eDVBNamespace ns = buildNamespace(onid, tsid, hash);

						addChannelToScan(
							eDVBChannelID(ns, tsid, onid),
							feparm);
						break;
					}
					case EXTENSION_DESCRIPTOR:
					{
						// retelele DVB-T2 isi anunta multiplexurile in descriptorul T2 (extensia 0x04): PLP-ul si, in
						// forma lunga, frecventele fiecarei celule (in unitati de 10 Hz); forma scurta n-are frecvente
						if (system != iDVBFrontend::feTerrestrial)
							break;
						if (((ExtensionDescriptor&)**desc).getExtensionTag() != hdster::T2_DESCRIPTOR)
							break;
						T2DeliverySystemDescriptor &d = (T2DeliverySystemDescriptor&)**desc;
						const T2CellList *celule = d.getCells();
						for (T2CellConstIterator c = celule->begin(); c != celule->end(); ++c)
						{
							const T2FrequencyList *frecvente = (*c)->getCentreFrequencies();
							for (T2FrequencyConstIterator f = frecvente->begin(); f != frecvente->end(); ++f)
							{
								ePtr<eDVBFrontendParameters> feparm = new eDVBFrontendParameters;
								eDVBFrontendParametersTerrestrial terr;
								terr.frequency = (*f) * 10;
								terr.bandwidth = hdster::latimeDinDescriptorT2(d.getBandwidth());
								terr.code_rate_HP = terr.code_rate_LP = eDVBFrontendParametersTerrestrial::FEC_Auto;
								terr.modulation = eDVBFrontendParametersTerrestrial::Modulation_Auto;
								terr.transmission_mode = hdster::modDinDescriptorT2(d.getTransmissionMode());
								terr.guard_interval = hdster::gardaDinDescriptorT2(d.getGuardInterval());
								terr.hierarchy = eDVBFrontendParametersTerrestrial::Hierarchy_Auto;
								terr.inversion = eDVBFrontendParametersTerrestrial::Inversion_Unknown;
								terr.system = eDVBFrontendParametersTerrestrial::System_DVB_T2;
								terr.plp_id = d.getPlpId();
								feparm->setDVBT(terr);

								unsigned long hash=0;
								feparm->getHash(hash);
								eDVBNamespace ns = buildNamespace(onid, tsid, hash);

								addChannelToScan(
									eDVBChannelID(ns, tsid, onid),
									feparm);
							}
						}
						break;
					}
					case SATELLITE_DELIVERY_SYSTEM_DESCRIPTOR:
					{
						if (system != iDVBFrontend::feSatellite)
							break; // when current locked transponder is no satellite transponder ignore this descriptor

						hdsSatelitDinNit((SatelliteDeliverySystemDescriptor&)**desc, onid, tsid, s2_gasit, s2_isi, s2_gold, false);
						break;
					}
					default:
						SCAN_eDebug("descr<%x>", (*desc)->getTag());
						break;
					}
				}
			}
			
		}

			/* a pitfall is to have the clearToScanOnFirstNIT-flag set, and having channels which have
			   no or invalid NIT. this code will not erase the toScan list unless at least one valid entry
			   has been found.

			   This is not a perfect solution, as the channel could contain a partial NIT. Life's bad.
			*/
		if (hds_adauga && (m_flags & clearToScanOnFirstNIT))
		{
			if (m_ch_toScan.empty())
			{
				eWarning("clearToScanOnFirstNIT was set, but NIT is invalid. Refusing to stop scan.");
				m_ch_toScan = m_ch_toScan_backup;
			} else
	 			m_flags &= ~clearToScanOnFirstNIT;
 		}
		m_ready &= ~validNIT;
	}

	if (m_pmt_running || (m_ready & m_ready_all) != m_ready_all)
	{
		if (m_abort_current_pmt)
		{
			m_abort_current_pmt = false;
			PMTready(-1);
		}
		return;
	}

	SCAN_eDebug("channel done!");

	/* HDSatelit (0.8.0): transponderele anuntate de NIT-ul altor retele, culese pe acest transponder */
	hdsNitAltaRetea();
	
		/* if we had services on this channel, we declare
		   this channels as "known good". add it.
		   
		   (TODO: not yet implemented)
		   a NIT entry could have possible overridden
		   our frontend data with more exact data.
		   
		   (TODO: not yet implemented)
		   the tuning process could have lead to more
		   exact data than the user entered.
		   
		   The channel id was probably corrected
		   by the data written in the SDT. this is
		   important, as "initial transponder lists"
		   usually don't have valid CHIDs (and that's
		   good).
		   
		   These are the reasons for adding the transponder
		   here, and not before.
		*/

	int type;
	if (m_ch_current->getSystem(type))
		type = -1;

	for (m_pmt_in_progress = m_pmts_to_read.begin(); m_pmt_in_progress != m_pmts_to_read.end();)
	{
		eServiceReferenceDVB ref;
		ePtr<eDVBService> service = new eDVBService;

		if (!m_chid_current)
		{
			unsigned long hash = 0;

			m_ch_current->getHash(hash);

			m_chid_current = eDVBChannelID(
				buildNamespace(eOriginalNetworkID(0), m_pat_tsid, hash),
				m_pat_tsid, eOriginalNetworkID(0));
		}

		if (m_pmt_in_progress->second.serviceType == 1)
			SCAN_eDebug("SID %04x is VIDEO", m_pmt_in_progress->first);
		else if (m_pmt_in_progress->second.serviceType == 2)
			SCAN_eDebug("SID %04x is AUDIO", m_pmt_in_progress->first);
		else
			SCAN_eDebug("SID %04x is DATA", m_pmt_in_progress->first);

		ref.set(m_chid_current);
		ref.setServiceID(m_pmt_in_progress->first);
		ref.setServiceType(m_pmt_in_progress->second.serviceType);

		if (type != -1)
		{
			char sname[255];
			std::string pname;
			memset(sname, 0, sizeof(sname));
			switch(type)
			{
				case iDVBFrontend::feSatellite:
				{
					eDVBFrontendParametersSatellite parm;
					m_ch_current->getDVBS(parm);
					snprintf(sname, 255, "%d%c SID 0x%02x",
							parm.frequency/1000,
							parm.polarisation ? 'V' : 'H',
							m_pmt_in_progress->first);
					/* furnizorul e deja UTF-8 (gradul C2 B0): nu mai trece prin convertDVBUTF8 (lib/dvb/hdsgrad.h) */
					pname = hdsgrad::furnizorScanare(parm.system, parm.modulation, parm.frequency,
						parm.polarisation, parm.orbital_position);
					break;
				}
				case iDVBFrontend::feTerrestrial:
				{
					eDVBFrontendParametersTerrestrial parm;
					m_ch_current->getDVBT(parm);
					snprintf(sname, 255, "%d SID 0x%02x",
						parm.frequency/1000,
						m_pmt_in_progress->first);
					break;
				}
				case iDVBFrontend::feCable:
				{
					eDVBFrontendParametersCable parm;
					m_ch_current->getDVBC(parm);
					snprintf(sname, 255, "%d SID 0x%02x",
						parm.frequency/1000,
						m_pmt_in_progress->first);
					break;
				}
			}
			SCAN_eDebug("name '%s', provider_name '%s'", sname, pname.c_str());
			service->m_service_name = convertDVBUTF8(sname);
			service->genSortName();
			service->m_provider_name = pname;
		}

		/* HDSatelit (0.8.0): numele din VCT-ul ATSC in locul celui facut din frecventa (UTF-8 gata facut, fara convertDVBUTF8),
		   deja la gasire, ca ecranul cautarii sa-l arate */
		const hdsvct::Canal *hds_canal = hdsCanalVct(m_pmt_in_progress->first);
		bool hds_vct = hds_canal && !hdsvct::numeCanal(*hds_canal).empty();
		if (hds_vct)
		{
			service->m_service_name = hdsvct::numeCanal(*hds_canal);
			service->genSortName();
		}

		if (!(m_flags & scanOnlyFree) || !m_pmt_in_progress->second.scrambled) {
			SCAN_eDebug("add not scrambled!");
			/* HDSatelit: a service without SDT is scrambled when its PMT has CA descriptors */
			if (m_pmt_in_progress->second.scrambled)
				service->m_flags |= eDVBService::dxIsScrambledPMT;
			std::pair<std::map<eServiceReferenceDVB, ePtr<eDVBService> >::iterator, bool> i =
				m_new_services.insert(std::pair<eServiceReferenceDVB, ePtr<eDVBService> >(ref, service));
			if (i.second)
			{
				if (hds_vct)
					m_hds_nume_vct[ref] = !m_hds_tp_cu_sdt;
				m_last_service = i.first;
				m_event(evtNewService);
			}
		}
		else
			SCAN_eDebug("dont add... is scrambled!");
		m_pmts_to_read.erase(m_pmt_in_progress++);
	}

	/* HDSatelit (0.8.0): serviciile din SDT cu numele gol iau si ele numele din VCT; numarul canalului in jurnal */
	hdsNumeleDinVct();

	if (!m_chid_current)
		eWarning("SCAN: the current channel's ID was not corrected - not adding channel.");
	else
	{
		addKnownGoodChannel(m_chid_current, m_ch_current);
		if (m_chid_current)
		{
			switch(type)
			{
				case iDVBFrontend::feSatellite:
				case iDVBFrontend::feTerrestrial:
				case iDVBFrontend::feCable:
				{
					ePtr<iDVBFrontend> fe;
					if (!m_channel->getFrontend(fe))
					{
						ePyObject tp_dict = PyDict_New();
						fe->getTransponderData(tp_dict, false);
//						eDebug("add tuner data for tsid %04x, onid %04x, ns %08x",
//							m_chid_current.transport_stream_id.get(), m_chid_current.original_network_id.get(),
//							m_chid_current.dvbnamespace.get());
						m_tuner_data.insert(std::pair<eDVBChannelID, ePyObjectWrapper>(m_chid_current, tp_dict));
						Py_DECREF(tp_dict);
					}
				}
				default:
					break;
			}
		}
	}

	{
		/* SNR-ul si nivelul in randul transponderului, numai la scanarea cu jurnal, o data pe transponder si dupa tabele: atunci
		   scanarea nu asteapta nimic de la tuner. Cat dureaza citirea se scrie in rand; o citire lenta le opreste pe urmatoarele */
		int hds_snr = -1, hds_nivel = -1;
		long hds_citire_ms = -1;
		ePtr<iDVBFrontend> hds_fe;
		if (hdsjscan::citesteSemnal(m_hds_jurnal) && m_channel && !m_channel->getFrontend(hds_fe))
		{
			long long hds_inceput = hdsjurnal::monotonMs();
			hds_snr = hds_fe->readFrontendData(iDVBFrontend::signalQualitydB);
			hds_nivel = hds_fe->readFrontendData(iDVBFrontend::signalPower);
			hds_citire_ms = (long)(hdsjurnal::monotonMs() - hds_inceput);
		}
		hdsjscan::prins(m_hds_jurnal, m_new_services.size(), hds_snr, hds_nivel, hds_citire_ms);
	}
	m_ch_scanned.push_back(m_ch_current);

	for (std::list<ePtr<iDVBFrontendParameters> >::iterator i(m_ch_toScan.begin()); i != m_ch_toScan.end();)
	{
		if (hdsAltaVarianta(m_ch_current, *i))
		{
			/* alta varianta a purtatorii abia prinse: nu se mai incearca (hdsAltaVarianta) */
			hdsjscan::variantaSarita(m_hds_jurnal, *i, m_ch_current);
			m_ch_toScan.erase(i++);
			continue;
		}
		if (sameChannel(*i, m_ch_current) || hdsCelalaltSistem(m_ch_current, *i))
		{
			SCAN_eDebug("remove dupe 2");
			m_ch_toScan.erase(i++);
			continue;
		}
		++i;
	}
	
	nextChannel();
}

void eDVBScan::start(const eSmartPtrList<iDVBFrontendParameters> &known_transponders, int flags)
{
	m_flags = flags;
	m_ch_toScan.clear();
	m_ch_scanned.clear();
	m_ch_unavailable.clear();
	m_new_channels.clear();
	m_tuner_data.clear();
	m_new_services.clear();
	m_sdt_services.clear();
	m_hds_nume_vct.clear();
	m_hds_cautare = true;   /* cautarea ceruta citeste si VCT-ul ATSC (hdsPornestePsip) */
	m_hds_coliziuni.clear();
	m_hds_continut.clear();
	m_hds_nit_alt_amanate.clear();
	m_hds_din_nit_alt.clear();
	m_hds_nit_propriu.clear();
	m_networks.goleste();
	m_network_on_tp.clear();
	m_nit_chid.clear();
	m_nit_chid_refs.clear();
	m_last_service = m_new_services.end();
	m_num_new_services = -1;

	for (eSmartPtrList<iDVBFrontendParameters>::const_iterator i(known_transponders.begin()); i != known_transponders.end(); ++i)
	{
		bool exist=false;
		for (std::list<ePtr<iDVBFrontendParameters> >::const_iterator ii(m_ch_toScan.begin()); ii != m_ch_toScan.end(); ++ii)
		{
			if (sameChannel(*i, *ii, true))
			{
				exist=true;
				break;
			}
		}
		if (!exist)
			m_ch_toScan.push_back(*i);
	}

	hdsjscan::pornita(m_hds_jurnal, m_ch_toScan.size(), flags);
	nextChannel();
}

/* HDSatelit (0.7.5, sosozah, forum 588 #2055): buchetul "Last Scanned" cu canalele gasite de ultima scanare, rescris la
   fiecare scanare, TV si radio separat, la coada listei de buchete; ca in enigma2 OE-Alliance (din sursele GPL enigma2
   (OE-Alliance), commitul 03eeb0ea5, lib/dvb/scan.cpp, eDVBScan::insertInto). Fisierele: userbouquet.LastScanned.tv si
   .radio, aceleasi nume ca acolo (Components/HdsEditorCanale.py si HdsFavorite.py le stiu deja ca buchete automate).
   Setarea config.usage.hds_ultima_scanare (Components/UsageConfig.py, data/setup.xml; in web /setari?id=usage),
   pornita din fabrica: oprita, buchetul nu se mai scrie si iese din lista buchetelor (fisierul ramane, nefolosit).
   O cheie lipsa sau necitita lasa buchetul pornit, ca din fabrica. */
static void hdsBuchetUltimaScanare(iDVBChannelList *db,
	const std::map<eServiceReferenceDVB, ePtr<eDVBService> > &gasite)
{
	std::string valoare;
	bool pornit = ePythonConfigQuery::getConfigValue("config.usage.hds_ultima_scanare", valoare) != 0
		|| valoare != "False";
	for (int tip = 1; tip <= 2; ++tip)   /* tipul buchetului: 1 TV (bouquets.tv), 2 radio (bouquets.radio) */
	{
		bool radio = tip == 2;
		std::string ext = radio ? "radio" : "tv";
		std::string nume = "userbouquet.LastScanned." + ext;
		eServiceReference ref(eServiceReference::idDVB, eServiceReference::flagDirectory,
			"FROM BOUQUET \"" + nume + "\" ORDER BY bouquet");
		ref.setData(0, tip);
		eServiceReference radacina(eServiceReference::idDVB, eServiceReference::flagDirectory,
			"FROM BOUQUET \"bouquets." + ext + "\" ORDER BY bouquet");
		radacina.setData(0, tip);
		eBouquet *lista = NULL;
		if (db->getBouquet(radacina, lista) || !lista)
		{
			eDebug("[eDVBScan] Last Scanned: lista buchetelor %s lipseste", ext.c_str());
			continue;
		}
		std::list<eServiceReference>::iterator loc = std::find(lista->m_services.begin(), lista->m_services.end(), ref);
		if (!pornit)
		{
			if (loc != lista->m_services.end())
			{
				lista->m_services.erase(loc);
				lista->flushChanges();
			}
			continue;
		}
		if (loc == lista->m_services.end())
		{
			lista->m_services.push_back(ref);
			lista->flushChanges();
		}
		eBouquet *buchet = NULL;
		if (db->getBouquet(ref, buchet) || !buchet)
		{
			/* incarcarea il trece si in baza de date, chiar daca fisierul nu exista inca */
			eDVBDB *baza = eDVBDB::getInstance();
			if (baza)
				baza->loadBouquet(nume.c_str());
			buchet = NULL;
			db->getBouquet(ref, buchet);
		}
		if (!buchet)
		{
			eDebug("[eDVBScan] Last Scanned: %s nu se poate face", nume.c_str());
			continue;
		}
		buchet->m_bouquet_name = "Last Scanned";
		buchet->m_services.clear();
		for (std::map<eServiceReferenceDVB, ePtr<eDVBService> >::const_iterator s(gasite.begin()); s != gasite.end(); ++s)
		{
			int t = s->first.getServiceType();
			/* radio: 2 si 0x0A (radio AVC / HE-AAC), ca dRadio si dRadioAvc in OE-Alliance */
			bool post_radio = t == 2 || t == 10;
			if (post_radio == radio)
				buchet->m_services.push_back(s->first);
		}
		buchet->flushChanges();
	}
}

/* NIT9 (24.11.2026, ZGEMMA H8.2H Plus, 13E): un transponder prins care a venit numai din NIT-ul altei retele nu-si scrie in
   lista parametrii din NIT other (pe 12673 V: DVB-S QPSK 29900 in locul lui DVB-S2 8PSK 30000, pe tunerele care isi aleg
   singure sistemul prinde cu oricare). Ia descriptorul propriu din NIT-ul actual citit pe el, altfel pastreaza ce avea
   lista (lib/dvb/hdsscanreguli.h, parametriPentruNitAlt); un transponder nou ramane cu parametrii NIT other. Inainte de
   scanRemoveServices, cat lista mai are transponderul. */
void eDVBScan::hdsParametriNitAlt(iDVBChannelList *db)
{
	for (std::map<eDVBChannelID, ePtr<iDVBFrontendParameters> >::iterator ch(m_new_channels.begin());
			ch != m_new_channels.end(); ++ch)
	{
		bool din_nit_alt = false;
		for (std::list<ePtr<iDVBFrontendParameters> >::const_iterator n(m_hds_din_nit_alt.begin());
				n != m_hds_din_nit_alt.end(); ++n)
			if ((iDVBFrontendParameters*)*n == (iDVBFrontendParameters*)ch->second)
				din_nit_alt = true;
		int tip;
		eDVBFrontendParametersSatellite acum;
		if (!din_nit_alt || ch->second->getSystem(tip) || tip != iDVBFrontend::feSatellite || ch->second->getDVBS(acum))
			continue;
		std::map<std::pair<unsigned int, int>, eDVBFrontendParametersSatellite>::const_iterator propriu =
			m_hds_nit_propriu.find(std::make_pair(((unsigned int)ch->first.original_network_id.get() << 16) |
				(unsigned int)ch->first.transport_stream_id.get(), acum.orbital_position));
		bool potrivit = propriu != m_hds_nit_propriu.end() && propriu->second.polarisation == acum.polarisation &&
			hdsscanreguli::abatere((long)propriu->second.frequency, (long)acum.frequency) <
				hdsscanreguli::fereastraUnireKhz((long)propriu->second.symbol_rate, (long)acum.symbol_rate);
		ePtr<iDVBFrontendParameters> din_lista;
		eDVBFrontendParametersSatellite lista;
		int tip_lista;
		bool in_lista = db && !db->getChannelFrontendData(ch->first, din_lista) && din_lista &&
			!din_lista->getSystem(tip_lista) && tip_lista == iDVBFrontend::feSatellite && !din_lista->getDVBS(lista) &&
			lista.orbital_position == acum.orbital_position && lista.polarisation == acum.polarisation &&
			hdsscanreguli::abatere((long)lista.frequency, (long)acum.frequency) <
				hdsscanreguli::fereastraUnireKhz((long)lista.symbol_rate, (long)acum.symbol_rate);
		int alegere = hdsscanreguli::parametriPentruNitAlt(propriu != m_hds_nit_propriu.end(), potrivit, in_lista);
		if (alegere == hdsscanreguli::PARAMETRI_DIN_NIT_ALT)
			continue;
		eDVBFrontendParametersSatellite nou = alegere == hdsscanreguli::PARAMETRI_DIN_NIT_PROPRIU ? propriu->second : lista;
		/* fluxul si PLP-ul T2-MI cu care s-a prins raman (NIT-ul nu poarta PLP-ul, iar fluxul acordat e cel bun) */
		nou.orbital_position = acum.orbital_position;
		nou.is_id = acum.is_id;
		nou.pls_mode = acum.pls_mode;
		nou.pls_code = acum.pls_code;
		nou.t2mi_plp_id = acum.t2mi_plp_id;
		nou.t2mi_pid = acum.t2mi_pid;
		eDebug("[eDVBScan] NIT other: %d %c %d prins, in lista cu %s: %d %d (in loc de %d %d din NIT other)",
			acum.frequency / 1000, acum.polarisation ? 'V' : 'H', acum.symbol_rate / 1000,
			alegere == hdsscanreguli::PARAMETRI_DIN_NIT_PROPRIU ? "descriptorul propriu din NIT-ul actual" : "parametrii din lista",
			nou.frequency, nou.symbol_rate, acum.frequency, acum.symbol_rate);
		/* acelasi obiect (ca ramura terestra din insertInto): legatura cu m_ch_scanned ramane pentru /api/scanare-ultima
		   (getScannedTransponders, dupa adresa), iar scanRemoveServices sterge cu parametrii buni */
		((eDVBFrontendParameters*)&*ch->second)->setDVBS(nou);
	}
}

void eDVBScan::insertInto(iDVBChannelList *db, bool dontRemoveOldFlags)
{
	/* HDSatelit: how many of the found services were not in the channel list before this scan
	   (summary on the scan screen). Counted before scanRemoveServices clears the scanned positions,
	   otherwise every service would look new. */
	hdsColiziuniLaSfarsit(db);
	hdsParametriNitAlt(db);
	m_num_new_services = 0;
	for (std::map<eServiceReferenceDVB, ePtr<eDVBService> >::const_iterator
		service(m_new_services.begin()); service != m_new_services.end(); ++service)
	{
		ePtr<eDVBService> dvb_service;
		if (db->getService(service->first, dvb_service))
			++m_num_new_services;
	}

	if (m_flags & scanRemoveServices)
	{
		bool clearTerrestrial=false;
		bool clearCable=false;
		std::set<unsigned int> scanned_sat_positions;
		
		std::list<ePtr<iDVBFrontendParameters> >::iterator it(m_ch_scanned.begin());
		for (;it != m_ch_scanned.end(); ++it)
		{
			if (m_flags & scanDontRemoveUnscanned)
				db->removeServices(&(*(*it)));
			else
			{
				int system;
				(*it)->getSystem(system);
				switch(system)
				{
					case iDVBFrontend::feSatellite:
					{
						eDVBFrontendParametersSatellite sat_parm;
						(*it)->getDVBS(sat_parm);
						scanned_sat_positions.insert(sat_parm.orbital_position);
						break;
					}
					case iDVBFrontend::feTerrestrial:
					{
						clearTerrestrial=true;
						break;
					}
					case iDVBFrontend::feCable:
					{
						clearCable=true;
						break;
					}
				}
			}
		}

		for (it=m_ch_unavailable.begin();it != m_ch_unavailable.end(); ++it)
		{
			if (m_flags & scanDontRemoveUnscanned)
				db->removeServices(&(*(*it)));
			else
			{
				int system;
				(*it)->getSystem(system);
				switch(system)
				{
					case iDVBFrontend::feSatellite:
					{
						eDVBFrontendParametersSatellite sat_parm;
						(*it)->getDVBS(sat_parm);
						scanned_sat_positions.insert(sat_parm.orbital_position);
						break;
					}
					case iDVBFrontend::feTerrestrial:
					{
						clearTerrestrial=true;
						break;
					}
					case iDVBFrontend::feCable:
					{
						clearCable=true;
						break;
					}
				}
			}
		}

		if (clearTerrestrial)
		{
			eDVBChannelID chid;
			chid.dvbnamespace=0xEEEE0000;
			db->removeServices(chid);
		}
		if (clearCable)
		{
			eDVBChannelID chid;
			chid.dvbnamespace=0xFFFF0000;
			db->removeServices(chid);
		}
		for (std::set<unsigned int>::iterator x(scanned_sat_positions.begin()); x != scanned_sat_positions.end(); ++x)
		{
			eDVBChannelID chid;
			if (m_flags & scanDontRemoveFeeds)
				chid.dvbnamespace = eDVBNamespace((*x)<<16);
//			eDebug("remove %d %08x", *x, chid.dvbnamespace.get());
			db->removeServices(chid, *x);
		}
	}

	for (std::map<eDVBChannelID, ePtr<iDVBFrontendParameters> >::const_iterator 
			ch(m_new_channels.begin()); ch != m_new_channels.end(); ++ch)
	{
		int system;
		ch->second->getSystem(system);
		std::map<eDVBChannelID, ePyObjectWrapper>::iterator it = m_tuner_data.find(ch->first);

		switch(system)
		{
			case iDVBFrontend::feTerrestrial:
			{
				// frecventa (numai cand e posibila: hdster::frecventaSalvata), sistemul (DVB-T / DVB-T2) si PLP-ul spuse de
				// tuner dupa prindere (getTransponderData)
				if (it == m_tuner_data.end())
					break;
				eDVBFrontendParameters *p = (eDVBFrontendParameters*)&(*ch->second);
				eDVBFrontendParametersTerrestrial parm;
				p->getDVBT(parm);
				PyObject *val = PyDict_GetItemString(it->second, "frequency");
				if (val && PyLong_Check(val))
					parm.frequency = hdster::frecventaSalvata(parm.frequency, PyLong_AsLong(val));
				val = PyDict_GetItemString(it->second, "system");
				if (val && PyLong_Check(val))
					parm.system = hdster::sistemNormalizat(PyLong_AsLong(val));
				val = PyDict_GetItemString(it->second, "plp_id");
				if (val && PyLong_Check(val))
				{
					int plp = hdster::plpNormalizat(parm.system, PyLong_AsLong(val));
					// un PLP ales la acordare ramane cand driverul nu-l spune
					if (plp >= 0 || parm.plp_id < 0)
						parm.plp_id = plp;
				}
				parm.plp_id = hdster::plpNormalizat(parm.system, parm.plp_id);
				p->setDVBT(parm);
				break;
			}
			case iDVBFrontend::feSatellite: // no update of any transponder parameter yet
			case iDVBFrontend::feCable:
				break;
		}

		if (m_flags & scanOnlyFree)
		{
			eDVBFrontendParameters *ptr = (eDVBFrontendParameters*)&(*ch->second);
			ptr->setFlags(iDVBFrontendParameters::flagOnlyFree);
		}

		db->addChannelToList(ch->first, ch->second);
	}

	for (std::map<eServiceReferenceDVB, ePtr<eDVBService> >::const_iterator
		service(m_new_services.begin()); service != m_new_services.end(); ++service)
	{
		ePtr<eDVBService> dvb_service;
		if (!db->getService(service->first, dvb_service))
		{
			if (dvb_service->m_flags & eDVBService::dxNoSDT)
				continue;
			/* HDSatelit (0.8.0): un nume gol din SDT (o recautare cu semnal slab, un descriptor cu numele gol) sau numele
			   facut din frecventa al unui serviciu gasit numai in PAT nu sterge numele bun din lista; un nume adevarat din
			   SDT il inlocuieste ca inainte. La fel furnizorul gol. */
			bool hds_din_sdt = m_sdt_services.count(service->first) > 0;
			/* HDSatelit (0.8.0): numele din VCT-ul ATSC inlocuieste numai un nume gol sau facut din frecventa, iar pe un
			   transponder fara SDT orice nume (hdsvct::vctInlocuiesteInLista); un nume bun din lista ramane */
			std::map<eServiceReferenceDVB, bool>::const_iterator hds_vct = m_hds_nume_vct.find(service->first);
			bool hds_nume_bun = hds_vct != m_hds_nume_vct.end() ?
				hdsvct::vctInlocuiesteInLista(dvb_service->m_service_name, hds_vct->second) : hds_din_sdt;
			if (!(dvb_service->m_flags & eDVBService::dxHoldName) && (dvb_service->m_service_name.empty() ||
				(hds_nume_bun && !service->second->m_service_name.empty())))
			{
				dvb_service->m_service_name = service->second->m_service_name;
				dvb_service->m_service_name_sort = service->second->m_service_name_sort;
			}
			if (dvb_service->m_provider_name.empty() || (hds_din_sdt && !service->second->m_provider_name.empty()))
				dvb_service->m_provider_name = service->second->m_provider_name;
			if (service->second->m_ca.size())
				dvb_service->m_ca = service->second->m_ca;
			/* HDSatelit: a known service takes the scrambled flag of this scan too (its SDT is the newest word) */
			dvb_service->m_flags = (dvb_service->m_flags & ~eDVBService::dxIsScrambledPMT) |
				(service->second->m_flags & eDVBService::dxIsScrambledPMT);
			if (!dontRemoveOldFlags) // do not remove new found flags when not wished
				dvb_service->m_flags &= ~eDVBService::dxNewFound;
		}
		else
		{
			db->addService(service->first, service->second);
			if (!(m_flags & scanRemoveServices))
				service->second->m_flags |= eDVBService::dxNewFound;
		}
	}

	/* HDSatelit (0.7.5): "Last Scanned" numai dupa o scanare ceruta, nu la actualizarea listei din fundal (pmt.cpp,
	   dontRemoveOldFlags = true), ca in OE-Alliance (!backgroundscanresult) */
	if (!dontRemoveOldFlags)
		hdsBuchetUltimaScanare(db, m_new_services);
}

RESULT eDVBScan::processSDT(eDVBNamespace dvbnamespace, const ServiceDescriptionSection &sdt)
{
	const ServiceDescriptionList &services = *sdt.getDescriptions();
	SCAN_eDebug("ONID: %04x", sdt.getOriginalNetworkId());
	eDVBChannelID chid(dvbnamespace, sdt.getTransportStreamId(), sdt.getOriginalNetworkId());
	
	/* save correct CHID for this channel */
	m_chid_current = chid;

	for (ServiceDescriptionConstIterator s(services.begin()); s != services.end(); ++s)
	{
		unsigned short service_id = (*s)->getServiceId();
		SCAN_eDebugNoNewLine("SID %04x: ", service_id);
		bool add = true;

		if (m_flags & scanOnlyFree)
		{
			std::map<unsigned short, service>::iterator it =
				m_pmts_to_read.find(service_id);
			if (it != m_pmts_to_read.end())
			{
				if (it->second.scrambled)
				{
					SCAN_eDebug("is scrambled!");
					add = false;
				}
				else
					SCAN_eDebug("is free");
			}
			else {
				SCAN_eDebug("not found in PAT.. so we assume it is scrambled!!");
				add = false;
			}
		}

		if (add)
		{
			eServiceReferenceDVB ref;
			ePtr<eDVBService> service = new eDVBService;

			ref.set(chid);
			ref.setServiceID(service_id);

			for (DescriptorConstIterator desc = (*s)->getDescriptors()->begin();
					desc != (*s)->getDescriptors()->end(); ++desc)
			{
				switch ((*desc)->getTag())
				{
				case SERVICE_DESCRIPTOR:
				{
					ServiceDescriptor &d = (ServiceDescriptor&)**desc;
					ref.setServiceType(d.getServiceType());
					service->m_service_name = convertDVBUTF8(d.getServiceName());
					service->genSortName();

					service->m_provider_name = convertDVBUTF8(d.getServiceProviderName());
					SCAN_eDebug("name '%s', provider_name '%s'", service->m_service_name.c_str(), service->m_provider_name.c_str());
					break;
				}
				case CA_IDENTIFIER_DESCRIPTOR:
				{
					CaIdentifierDescriptor &d = (CaIdentifierDescriptor&)**desc;
					const CaSystemIdList &caids = *d.getCaSystemIds();
					SCAN_eDebugNoNewLine("CA ");
					for (CaSystemIdList::const_iterator i(caids.begin()); i != caids.end(); ++i)
					{
						SCAN_eDebugNoNewLine("%04x ", *i);
						service->m_ca.push_front(*i);
					}
					SCAN_eDebug("%s", "");
					break;
				}
				default:
					SCAN_eDebug("descr<%x>", (*desc)->getTag());
					break;
				}
			}

			/* HDSatelit: scrambled or free, as the SDT says (free_CA_mode): kept in the flags, for the mark in the channel
			   list (lib/service/listboxservice.cpp, serviceMarks) */
			if ((*s)->getFreeCaMode())
				service->m_flags |= eDVBService::dxIsScrambledPMT;

			std::pair<std::map<eServiceReferenceDVB, ePtr<eDVBService> >::iterator, bool> i =
				m_new_services.insert(std::pair<eServiceReferenceDVB, ePtr<eDVBService> >(ref, service));
			m_sdt_services.insert(ref);

			if (i.second)
			{
				m_last_service = i.first;
				m_event(evtNewService);
			}
		}
		if (m_pmt_running && m_pmt_in_progress->first == service_id)
			m_abort_current_pmt = true;
		else
			m_pmts_to_read.erase(service_id);
	}

	return 0;
}

RESULT eDVBScan::connectEvent(const sigc::slot<void(int)> &event, ePtr<eConnection> &connection)
{
	connection = new eConnection(this, m_event.connect(event));
	return 0;
}

void eDVBScan::getStats(int &transponders_done, int &transponders_total, int &services)
{
	transponders_done = m_ch_scanned.size() + m_ch_unavailable.size();
	transponders_total = m_ch_toScan.size() + transponders_done;
	services = m_new_services.size();
}

int eDVBScan::getLastServiceType()
{
	if (m_last_service == m_new_services.end())
		return -1;
	return m_last_service->first.getServiceType();
}

void eDVBScan::getLastServiceName(std::string &last_service_name)
{
	if (m_last_service == m_new_services.end())
		last_service_name = "";
	else
		last_service_name = m_last_service->second->m_service_name;
}

/* HDSatelit: the result of this scan for the web interface (Components/HdsScanareUltima.py). Only reads the lists of
   the scan; the channel list is written only by insertInto, as before. Names go through "replace", so a broken byte
   in a name does not lose the whole list. */
PyObject *eDVBScan::getFoundServices()
{
	ePyObject list = PyList_New(0);
	for (std::map<eServiceReferenceDVB, ePtr<eDVBService> >::const_iterator
		i(m_new_services.begin()); i != m_new_services.end(); ++i)
	{
		const eServiceReferenceDVB &ref = i->first;
		const std::string &name = i->second->m_service_name;
		const std::string &provider = i->second->m_provider_name;
		ePyObject caids = PyList_New(0);
		for (CAID_LIST::const_iterator c(i->second->m_ca.begin()); c != i->second->m_ca.end(); ++c)
		{
			ePyObject caid = PyLong_FromLong(*c);
			PyList_Append(caids, caid);
			Py_DECREF(caid);
		}
		ePyObject tuple = PyTuple_New(9);
		PyTuple_SET_ITEM(tuple, 0, PyLong_FromLong(ref.getServiceID().get()));
		PyTuple_SET_ITEM(tuple, 1, PyLong_FromUnsignedLong((unsigned int)ref.getDVBNamespace().get()));
		PyTuple_SET_ITEM(tuple, 2, PyLong_FromLong(ref.getTransportStreamID().get()));
		PyTuple_SET_ITEM(tuple, 3, PyLong_FromLong(ref.getOriginalNetworkID().get()));
		PyTuple_SET_ITEM(tuple, 4, PyLong_FromLong(ref.getServiceType()));
		PyTuple_SET_ITEM(tuple, 5, PyUnicode_DecodeUTF8(name.data(), name.size(), "replace"));
		PyTuple_SET_ITEM(tuple, 6, PyUnicode_DecodeUTF8(provider.data(), provider.size(), "replace"));
		PyTuple_SET_ITEM(tuple, 7, caids);
		PyTuple_SET_ITEM(tuple, 8, PyBool_FromLong(m_sdt_services.count(ref) ? 1 : 0));
		PyList_Append(list, tuple);
		Py_DECREF(tuple);
	}
	return list;
}

PyObject *eDVBScan::getScannedTransponders()
{
	/* the channel id of every transponder that sent tables: addKnownGoodChannel keeps the same object as m_ch_scanned */
	std::map<iDVBFrontendParameters*, eDVBChannelID> chids;
	for (std::map<eDVBChannelID, ePtr<iDVBFrontendParameters> >::const_iterator
		ch(m_new_channels.begin()); ch != m_new_channels.end(); ++ch)
		chids[(iDVBFrontendParameters*)ch->second] = ch->first;

	ePyObject list = PyList_New(0);
	for (int tuned = 1; tuned >= 0; --tuned)
	{
		const std::list<ePtr<iDVBFrontendParameters> > &tps = tuned ? m_ch_scanned : m_ch_unavailable;
		for (std::list<ePtr<iDVBFrontendParameters> >::const_iterator i(tps.begin()); i != tps.end(); ++i)
		{
			iDVBFrontendParameters *tp = (iDVBFrontendParameters*)*i;
			if (!tp)
				continue;
			int system = -1, orbital_position = -1, polarisation = -1, modulation = -1;
			unsigned int frequency = 0, symbol_rate = 0;
			if (tp->getSystem(system))
				system = -1;
			switch (system)
			{
			case iDVBFrontend::feSatellite:
			{
				eDVBFrontendParametersSatellite p;
				tp->getDVBS(p);
				orbital_position = p.orbital_position;
				frequency = p.frequency;
				polarisation = p.polarisation;
				symbol_rate = p.symbol_rate;
				break;
			}
			case iDVBFrontend::feCable:
			{
				eDVBFrontendParametersCable p;
				tp->getDVBC(p);
				frequency = p.frequency;
				symbol_rate = p.symbol_rate;
				modulation = p.modulation;
				break;
			}
			case iDVBFrontend::feTerrestrial:
			{
				eDVBFrontendParametersTerrestrial p;
				tp->getDVBT(p);
				frequency = p.frequency;
				break;
			}
			default:
				break;
			}
			std::map<iDVBFrontendParameters*, eDVBChannelID>::const_iterator id = chids.find(tp);
			bool has_id = tuned && id != chids.end();
			std::map<iDVBFrontendParameters*, eDVBChannelID>::const_iterator nit = m_nit_chid.find(tp);
			std::map<iDVBFrontendParameters*, unsigned int>::const_iterator net = m_network_on_tp.find(tp);
			ePyObject tuple = PyTuple_New(14);
			PyTuple_SET_ITEM(tuple, 0, PyLong_FromLong(system));
			PyTuple_SET_ITEM(tuple, 1, PyLong_FromLong(orbital_position));
			PyTuple_SET_ITEM(tuple, 2, PyLong_FromUnsignedLong(frequency));
			PyTuple_SET_ITEM(tuple, 3, PyLong_FromLong(polarisation));
			PyTuple_SET_ITEM(tuple, 4, PyLong_FromUnsignedLong(symbol_rate));
			PyTuple_SET_ITEM(tuple, 5, PyBool_FromLong(tuned));
			PyTuple_SET_ITEM(tuple, 6, PyBool_FromLong(has_id ? 1 : 0));
			PyTuple_SET_ITEM(tuple, 7, PyLong_FromUnsignedLong(has_id ? (unsigned int)id->second.dvbnamespace.get() : 0));
			PyTuple_SET_ITEM(tuple, 8, PyLong_FromLong(has_id ? id->second.transport_stream_id.get() : 0));
			PyTuple_SET_ITEM(tuple, 9, PyLong_FromLong(has_id ? id->second.original_network_id.get() : 0));
			PyTuple_SET_ITEM(tuple, 10, PyLong_FromLong(nit != m_nit_chid.end() ? nit->second.transport_stream_id.get() : -1));
			PyTuple_SET_ITEM(tuple, 11, PyLong_FromLong(nit != m_nit_chid.end() ? nit->second.original_network_id.get() : -1));
			PyTuple_SET_ITEM(tuple, 12, PyLong_FromLong(net != m_network_on_tp.end() ? (long)net->second : -1));
			PyTuple_SET_ITEM(tuple, 13, PyLong_FromLong(modulation));
			PyList_Append(list, tuple);
			Py_DECREF(tuple);
		}
	}
	return list;
}

static PyObject *hdsIntList(const std::set<uint32_t> &values)
{
	ePyObject list = PyList_New(0);
	for (std::set<uint32_t>::const_iterator v(values.begin()); v != values.end(); ++v)
	{
		ePyObject o = PyLong_FromUnsignedLong(*v);
		PyList_Append(list, o);
		Py_DECREF(o);
	}
	return list;
}

/* HDSatelit: every network whose NIT this scan read (lib/dvb/hdsretea.h), for /api/scanare-ultima. The name goes
   through the DVB text conversion and "replace", like the service names. Read only. */
PyObject *eDVBScan::getNetworks()
{
	ePyObject list = PyList_New(0);
	const std::vector<hdsretea::Retea> &networks = m_networks.retele();
	for (std::vector<hdsretea::Retea>::const_iterator n(networks.begin()); n != networks.end(); ++n)
	{
		std::string name = convertDVBUTF8(n->nume);
		ePyObject muxes = PyList_New(0);
		for (std::vector<hdsretea::Mux>::const_iterator m(n->muxuri.begin()); m != n->muxuri.end(); ++m)
		{
			ePyObject t = PyTuple_New(10);
			PyTuple_SET_ITEM(t, 0, PyLong_FromLong(m->tsid));
			PyTuple_SET_ITEM(t, 1, PyLong_FromLong(m->onid));
			PyTuple_SET_ITEM(t, 2, PyLong_FromLong(m->sistem));
			PyTuple_SET_ITEM(t, 3, PyLong_FromUnsignedLong(m->f_khz));
			PyTuple_SET_ITEM(t, 4, PyLong_FromLong(m->sr));
			PyTuple_SET_ITEM(t, 5, PyLong_FromLong(m->mod));
			PyTuple_SET_ITEM(t, 6, PyLong_FromLong(m->fec));
			PyTuple_SET_ITEM(t, 7, PyLong_FromLong(m->poz));
			PyTuple_SET_ITEM(t, 8, PyLong_FromLong(m->pol));
			PyTuple_SET_ITEM(t, 9, PyLong_FromLong(m->s2));
			PyList_Append(muxes, t);
			Py_DECREF(t);
		}
		ePyObject numbers = PyList_New(0);
		for (std::vector<hdsretea::Lcn>::const_iterator l(n->lcn.begin()); l != n->lcn.end(); ++l)
		{
			ePyObject t = PyTuple_New(8);
			PyTuple_SET_ITEM(t, 0, PyLong_FromLong(l->tsid));
			PyTuple_SET_ITEM(t, 1, PyLong_FromLong(l->onid));
			PyTuple_SET_ITEM(t, 2, PyLong_FromLong(l->sid));
			PyTuple_SET_ITEM(t, 3, PyLong_FromLong(l->numar));
			PyTuple_SET_ITEM(t, 4, PyLong_FromLong(l->vizibil));    /* 1, 0, -1 = no visibility flag (0x86) */
			PyTuple_SET_ITEM(t, 5, PyLong_FromLong(l->tag));
			PyTuple_SET_ITEM(t, 6, PyLong_FromUnsignedLong(l->pds));
			PyTuple_SET_ITEM(t, 7, PyLong_FromLong(l->lista));
			PyList_Append(numbers, t);
			Py_DECREF(t);
		}
		ePyObject raw = PyList_New(0);
		for (std::vector<hdsretea::Brut>::const_iterator b(n->privati.begin()); b != n->privati.end(); ++b)
		{
			ePyObject t = PyTuple_New(5);
			PyTuple_SET_ITEM(t, 0, PyLong_FromLong(b->tsid));
			PyTuple_SET_ITEM(t, 1, PyLong_FromLong(b->onid));
			PyTuple_SET_ITEM(t, 2, PyLong_FromLong(b->tag));
			PyTuple_SET_ITEM(t, 3, PyLong_FromUnsignedLong(b->pds));
			PyTuple_SET_ITEM(t, 4, PyBytes_FromStringAndSize(b->octeti.empty() ? "" : (const char *)&b->octeti[0],
				b->octeti.size()));
			PyList_Append(raw, t);
			Py_DECREF(t);
		}
		ePyObject tuple = PyTuple_New(7);
		PyTuple_SET_ITEM(tuple, 0, PyLong_FromLong(n->nid));
		PyTuple_SET_ITEM(tuple, 1, PyUnicode_DecodeUTF8(name.data(), name.size(), "replace"));
		PyTuple_SET_ITEM(tuple, 2, hdsIntList(n->pds));
		PyTuple_SET_ITEM(tuple, 3, muxes);
		PyTuple_SET_ITEM(tuple, 4, numbers);
		PyTuple_SET_ITEM(tuple, 5, raw);
		PyTuple_SET_ITEM(tuple, 6, PyBool_FromLong(n->trunchiat ? 1 : 0));
		PyList_Append(list, tuple);
		Py_DECREF(tuple);
	}
	return list;
}

RESULT eDVBScan::getFrontend(ePtr<iDVBFrontend> &fe)
{
	if (m_channel)
		return m_channel->getFrontend(fe);
	fe = 0;
	return -1;
}

RESULT eDVBScan::getCurrentTransponder(ePtr<iDVBFrontendParameters> &tp)
{
	if (m_ch_current)
	{
		tp = m_ch_current;
		return 0;
	}
	tp = 0;
	return -1;
}
