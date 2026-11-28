/* Modificat de moneasoftware.com si hdsatelit.com, 2026 */
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/ioctl.h>

#include <lib/base/init.h>
#include <lib/base/init_num.h>
#include <lib/base/ebase.h>
#include <lib/base/hdsjurnal.h>

#include <lib/base/eerror.h>
#include <lib/base/nconfig.h> // access to python config
#include <lib/dvb/db.h>
#include <lib/dvb/pmt.h>
#include <lib/dvb_ci/dvbci.h>
#include <lib/dvb_ci/dvbci_session.h>
#include <lib/dvb_ci/dvbci_camgr.h>
#include <lib/dvb_ci/dvbci_ui.h>
#include <lib/dvb_ci/dvbci_appmgr.h>
#include <lib/dvb_ci/dvbci_mmi.h>
#include <lib/dvb_ci/dvbci_ccmgr.h>
#include <lib/dvb_ci/hdscica.h>
#include <lib/dvb_ci/hdscicale.h>
#include <lib/dvb_ci/hdstsmux.h>
#include <sys/stat.h>
#include <lib/dvb/frontend.h>

#include <dvbsi++/ca_program_map_section.h>

//#define CIDEBUG 1

#ifdef CIDEBUG
	#define eDebugCI(x...) eDebug(x)
#else
	#define eDebugCI(x...)
#endif

eDVBCIInterfaces *eDVBCIInterfaces::instance = 0;

/* Setarile CI de la pornire (slot pornit/oprit, intarzierea pornirii) se citesc din /etc/enigma2/settings: sloturile se
   fac inaintea Python-ului (eAutoInitNumbers::dvb), deci ePythonConfigQuery nu are inca setarile. Acelasi lucru il face
   eSimpleConfig in enigma2 OE-Alliance (depozitul enigma2 al stratului OE-Alliance, commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4,
   eDVBCISlot::eDVBCISlot); aici numai cele doua chei de care e nevoie. */
static std::string hdsSetareCi(const char *cheie, const char *implicit)
{
	std::string rezultat = implicit;
	FILE *f = fopen("/etc/enigma2/settings", "r");
	if (!f)
		return rezultat;
	char linie[512];
	size_t lungime = strlen(cheie);
	while (fgets(linie, sizeof(linie), f))
	{
		if (strncmp(linie, cheie, lungime) == 0 && linie[lungime] == '=')
		{
			rezultat = linie + lungime + 1;
			while (!rezultat.empty() && (rezultat[rezultat.size() - 1] == '\n' || rezultat[rezultat.size() - 1] == '\r' || rezultat[rezultat.size() - 1] == ' '))
				rezultat.erase(rezultat.size() - 1);
		}
	}
	fclose(f);
	return rezultat;
}

eDVBCIInterfaces::eDVBCIInterfaces()
{
	int num_ci = 0;
	
	instance = this;
	
	eDebug("scanning for common interfaces..");

	while (1)
	{
		struct stat s;
		char filename[128];
		sprintf(filename, "/dev/ci%d", num_ci);

		if (stat(filename, &s))
			break;

		ePtr<eDVBCISlot> cislot;

		cislot = new eDVBCISlot(eApp, num_ci);
		m_slots.push_back(cislot);

		++num_ci;
	}

	for (eSmartPtrList<eDVBCISlot>::iterator it(m_slots.begin()); it != m_slots.end(); ++it)
		it->setSource(hdsTsmuxLitera(0));

	/* HD Satelit: fiecare tuner pe litera lui, ca in OE-Alliance; primele intrari ca inainte (A-D cu doua sau mai multe
	   sloturi, A-B cu unul), iar de la E numai intrarile pe care placa le are (input<N>_choices): tunerele FBC (Vu+ 4K)
	   ramase legate de un modul CI dintr-o rulare oprita nu mai trec prin modul dupa repornirea interfetei */
	int primele = num_ci > 1 ? 4 : 2;
	for (int tuner_no = 0; tuner_no < HDS_TSMUX_TUNERE; ++tuner_no)
		if (hdsTsmuxIntrareLaPornire(HDS_TSMUX_DOSAR, tuner_no, primele))
			setInputSource(tuner_no, hdsTsmuxLitera(tuner_no));

	eDebug("done, found %d common interface slots", num_ci);
}

eDVBCIInterfaces::~eDVBCIInterfaces()
{
}

eDVBCIInterfaces *eDVBCIInterfaces::getInstance()
{
	return instance;
}

eDVBCISlot *eDVBCIInterfaces::getSlot(int slotid)
{
	for(eSmartPtrList<eDVBCISlot>::iterator i(m_slots.begin()); i != m_slots.end(); ++i)
		if(i->getSlotID() == slotid)
			return i;

	eDebug("FIXME: request for unknown slot");
			
	return 0;
}

int eDVBCIInterfaces::getSlotState(int slotid)
{
	eDVBCISlot *slot;

	if( (slot = getSlot(slotid)) == 0 )
		return eDVBCISlot::stateInvalid;

	return slot->getState();
}

int eDVBCIInterfaces::reset(int slotid)
{
	eDVBCISlot *slot;

	if( (slot = getSlot(slotid)) == 0 )
		return -1;

	return slot->reset();
}

int eDVBCIInterfaces::initialize(int slotid)
{
	eDVBCISlot *slot;

	if( (slot = getSlot(slotid)) == 0 )
		return -1;

	slot->removeService();

	return sendCAPMT(slotid);
}

int eDVBCIInterfaces::sendCAPMT(int slotid)
{
	eDVBCISlot *slot;

	if( (slot = getSlot(slotid)) == 0 )
		return -1;

	PMTHandlerList::iterator it = m_pmt_handlers.begin();
	while (it != m_pmt_handlers.end())
	{
		eDVBCISlot *tmp = it->cislot;
		while (tmp && tmp != slot)
			tmp = tmp->linked_next;
		if (tmp)
		{
			tmp->setCaParameter(it->pmthandler);  // CI+: demux, program, pid-uri, tuner (OE-Alliance)
			tmp->sendCAPMT(it->pmthandler);  // send capmt
			break;
		}
		++it;
	}

	return 0;
}

int eDVBCIInterfaces::startMMI(int slotid)
{
	eDVBCISlot *slot;

	if( (slot = getSlot(slotid)) == 0 )
		return -1;
	
	return slot->startMMI();
}

int eDVBCIInterfaces::stopMMI(int slotid)
{
	eDVBCISlot *slot;

	if( (slot = getSlot(slotid)) == 0 )
		return -1;
	
	return slot->stopMMI();
}

int eDVBCIInterfaces::answerText(int slotid, int answer)
{
	eDVBCISlot *slot;

	if( (slot = getSlot(slotid)) == 0 )
		return -1;
	
	return slot->answerText(answer);
}

int eDVBCIInterfaces::answerEnq(int slotid, char *value)
{
	eDVBCISlot *slot;

	if( (slot = getSlot(slotid)) == 0 )
		return -1;
	
	return slot->answerEnq(value);
}

int eDVBCIInterfaces::cancelEnq(int slotid)
{
	eDVBCISlot *slot;

	if( (slot = getSlot(slotid)) == 0 )
		return -1;
	
	return slot->cancelEnq();
}

void eDVBCIInterfaces::ciRemoved(eDVBCISlot *slot)
{
	if (slot->use_count)
	{
		eDebug("CI Slot %d: removed... usecount %d", slot->getSlotID(), slot->use_count);
		/* canalele ramase fara modul CI: inapoi la modulul de acces (lib/dvb_ci/hdscicale.h) */
		std::vector<eDVBServicePMTHandler*> fara_ci;
		for (PMTHandlerList::iterator it(m_pmt_handlers.begin());
			it != m_pmt_handlers.end(); ++it)
		{
			if (it->cislot == slot) // remove the base slot
			{
				it->cislot = slot->linked_next;
				if (!it->cislot)
					fara_ci.push_back(it->pmthandler);
			}
			else if (it->cislot)
			{
				eDVBCISlot *prevSlot = it->cislot, *hSlot = it->cislot->linked_next;
				while (hSlot)
				{
					if (hSlot == slot) {
						prevSlot->linked_next = slot->linked_next;
						break;
					}
					prevSlot = hSlot;
					hSlot = hSlot->linked_next;
				}
			}
		}
		if (slot->linked_next)
			slot->linked_next->setSource(slot->current_source);
		else // last CI in chain
			setInputSource(slot->current_tuner, slot->current_source);
		slot->linked_next = 0;
		slot->use_count=0;
		slot->plugged=true;
		slot->user_mapped=false;
		slot->removeService(0xFFFF);
		recheckPMTHandlers();
		for (std::vector<eDVBServicePMTHandler*>::iterator h(fara_ci.begin()); h != fara_ci.end(); ++h)
			if (std::find(m_pmt_handlers.begin(), m_pmt_handlers.end(), *h) != m_pmt_handlers.end() && !isHandlerAssigned(*h))
				(*h)->ciAPlecat();
	}
}

bool hdsNumaiCi()
{
	eDVBCIInterfaces *ci = eDVBCIInterfaces::getInstance();
	if (!ci || !ci->getNumOfSlots())
		return false;
	std::string valoare;
	return !ePythonConfigQuery::getConfigValue(HDS_CI_NUMAI_CI_CHEIE, valoare) && hdsNumaiCiPornit(valoare);
}

static bool canDescrambleMultipleServices(int slotid)
{
	char configStr[255];
	snprintf(configStr, 255, "config.ci.%d.canDescrambleMultipleServices", slotid);
	std::string str;
	ePythonConfigQuery::getConfigValue(configStr, str);
	if ( str == "auto" )
	{
		std::string appname = eDVBCI_UI::getInstance()->getAppName(slotid);
		if (appname.find("AlphaCrypt") != std::string::npos)
			return true;
	}
	else if (str == "yes")
		return true;
	return false;
}

/* HD Satelit: un canal criptat care n-a primit niciun modul CI, cand cel putin un modul si-a spus CAID-urile: un rand in
   hds-ci.log cu CAID-urile canalului si ale fiecarui modul (negru cu modulul recunoscut: CAID-uri care nu se potrivesc,
   modul ocupat cu alt canal sau alocare de mana pe alte canale), o singura data pentru aceleasi CAID-uri si aceeasi stare a
   modulelor; fara canalul insusi (jurnalul pleaca in pachetele testerilor, fara listele de canale ale omului) */
template <class Lista>
static std::string hdsCaiduriText(const Lista &lista)
{
	std::string text;
	char buf[8];
	int n = 0;
	for (typename Lista::const_iterator i = lista.begin(); i != lista.end(); ++i)
	{
		if (n++ == 16)
		{
			text += " ...";
			break;
		}
		snprintf(buf, sizeof(buf), "%s%04x", text.empty() ? "" : " ", *i);
		text += buf;
	}
	return text.empty() ? std::string("-") : text;
}

static void hdsJurnalFaraModul(const CAID_LIST &caids, eSmartPtrList<eDVBCISlot> &sloturi)
{
	static std::string ultimul;
	std::string module;
	for (eSmartPtrList<eDVBCISlot>::iterator s(sloturi.begin()); s != sloturi.end(); ++s)
	{
		eDVBCICAManagerSession *ca = s->getCAManager();
		if (!ca)
			continue;
		char buf[48];
		snprintf(buf, sizeof(buf), "%sCI%d (%d canale): ", module.empty() ? "" : "; ", s->getSlotID(), s->getUseCount());
		module += buf;
		module += hdsCaiduriText(ca->getCAIDs());
	}
	if (module.empty())
		return;
	std::string mesaj = hdsCaiduriText(caids) + " | " + module;
	if (mesaj == ultimul)
		return;
	ultimul = mesaj;
	hdsjurnal::scrief("ci", hdsjurnal::INFO, "slot", "CI: canal criptat fara modul CI, CAID-uri canal: %s; module: %s",
		hdsCaiduriText(caids).c_str(), module.c_str());
}

void eDVBCIInterfaces::recheckPMTHandlers()
{
	eDebugCI("recheckPMTHAndlers()");
	for (PMTHandlerList::iterator it(m_pmt_handlers.begin());
		it != m_pmt_handlers.end(); ++it)
	{
		CAID_LIST caids;
		ePtr<eDVBService> service;
		eServiceReferenceDVB ref;
		eDVBCISlot *tmp = it->cislot;
		eDVBServicePMTHandler *pmthandler = it->pmthandler;
		eDVBServicePMTHandler::program p;
		bool plugged_cis_exist = false;

		pmthandler->getServiceReference(ref);
		pmthandler->getService(service);

		eDebugCI("recheck %p %s", pmthandler, ref.toString().c_str());
		for (eSmartPtrList<eDVBCISlot>::iterator ci_it(m_slots.begin()); ci_it != m_slots.end(); ++ci_it)
			if (ci_it->plugged && ci_it->getCAManager())
			{
				eDebug("Slot %d plugged", ci_it->getSlotID());
				ci_it->plugged = false;
				plugged_cis_exist = true;
			}

		// check if this pmt handler has already assigned CI(s) .. and this CI(s) are already running
		if (!plugged_cis_exist)
		{
			while(tmp)
			{
				if (!tmp->running_services.empty())
					break;
				tmp=tmp->linked_next;
			}
			if (tmp) // we dont like to change tsmux for running services
			{
				eDebugCI("already assigned and running CI!\n");
				continue;
			}
		}

		if (!pmthandler->getProgramInfo(p))
		{
			int cnt=0;
			std::set<eDVBServicePMTHandler::program::capid_pair> set(p.caids.begin(), p.caids.end());
			for (std::set<eDVBServicePMTHandler::program::capid_pair>::reverse_iterator x(set.rbegin()); x != set.rend(); ++x, ++cnt)
				caids.push_front(x->caid);
			if (service && cnt)
				service->m_ca = caids;
		}

		if (service)
			caids = service->m_ca;

		if (caids.empty())
			continue; // unscrambled service

		for (eSmartPtrList<eDVBCISlot>::iterator ci_it(m_slots.begin()); ci_it != m_slots.end(); ++ci_it)
		{
			eDebugCI("check Slot %d", ci_it->getSlotID());
			bool useThis=false;
			bool user_mapped=true;
			eDVBCICAManagerSession *ca_manager = ci_it->getCAManager();

			if (ca_manager)
			{
				int mask=0;
				if (!ci_it->possible_services.empty())
				{
					mask |= 1;
					serviceSet::iterator it = ci_it->possible_services.find(ref);
					if (it != ci_it->possible_services.end())
					{
						eDebug("'%s' is in service list of slot %d... so use it", ref.toString().c_str(), ci_it->getSlotID());
						useThis = true;
					}
					else // check parent
					{
						eServiceReferenceDVB parent_ref = ref.getParentServiceReference();
						if (parent_ref)
						{
							it = ci_it->possible_services.find(ref);
							if (it != ci_it->possible_services.end())
							{
								eDebug("parent '%s' of '%s' is in service list of slot %d... so use it",
									parent_ref.toString().c_str(), ref.toString().c_str(), ci_it->getSlotID());
								useThis = true;
							}
						}
					}
				}
				if (!useThis && !ci_it->possible_providers.empty())
				{
					eDVBNamespace ns = ref.getDVBNamespace();
					mask |= 2;
					if (!service) // subservice?
					{
						eServiceReferenceDVB parent_ref = ref.getParentServiceReference();
						eDVBDB::getInstance()->getService(parent_ref, service);
					}
					if (service)
					{
						providerSet::iterator it = ci_it->possible_providers.find(providerPair(service->m_provider_name, ns.get()));
						if (it != ci_it->possible_providers.end())
						{
							eDebug("'%s/%08x' is in provider list of slot %d... so use it", service->m_provider_name.c_str(), ns.get(), ci_it->getSlotID());
							useThis = true;
						}
					}
				}
				if (!useThis && !ci_it->possible_caids.empty())
				{
					mask |= 4;
					for (CAID_LIST::iterator ca(caids.begin()); ca != caids.end(); ++ca)
					{
						caidSet::iterator it = ci_it->possible_caids.find(*ca);
						if (it != ci_it->possible_caids.end())
						{
							eDebug("caid '%04x' is in caid list of slot %d... so use it", *ca, ci_it->getSlotID());
							useThis = true;
							break;
						}
					}
				}
				if (!useThis && !mask)
				{
					const std::vector<uint16_t> &ci_caids = ca_manager->getCAIDs();
					for (CAID_LIST::iterator ca(caids.begin()); ca != caids.end(); ++ca)
					{
						std::vector<uint16_t>::const_iterator z =
							std::lower_bound(ci_caids.begin(), ci_caids.end(), *ca);
						if ( z != ci_caids.end() && *z == *ca )
						{
							eDebug("The CI in Slot %d has said it can handle caid %04x... so use it", ci_it->getSlotID(), *z);
							useThis = true;
							user_mapped = false;
							break;
						}
					}
				}
			}

			if (useThis)
			{
				// check if this CI is already assigned to this pmthandler
				eDVBCISlot *tmp = it->cislot;
				while(tmp)
				{
					if (tmp == ci_it)
						break;
					tmp=tmp->linked_next;
				}
				if (tmp) // ignore already assigned cislots...
				{
					eDebugCI("already assigned!");
					continue;
				}
				eDebugCI("current slot %d usecount %d", ci_it->getSlotID(), ci_it->use_count);
				if (ci_it->use_count)  // check if this CI can descramble more than one service
				{
					bool found = false;
					useThis = false;
					PMTHandlerList::iterator tmp = m_pmt_handlers.begin();
					while (!found && tmp != m_pmt_handlers.end())
					{
						eDebugCI(".");
						eDVBCISlot *tmp_cislot = tmp->cislot;
						while (!found && tmp_cislot)
						{
							eDebugCI("..");
							eServiceReferenceDVB ref2;
							tmp->pmthandler->getServiceReference(ref2);
							if ( tmp_cislot == ci_it && it->pmthandler != tmp->pmthandler )
							{
								eDebugCI("check pmthandler %s for same service/tp", ref2.toString().c_str());
								eDVBChannelID s1, s2;
								if (ref != ref2)
								{
									eDebugCI("different services!");
									ref.getChannelID(s1);
									ref2.getChannelID(s2);
								}
								if (ref == ref2 || (s1 == s2 && canDescrambleMultipleServices(tmp_cislot->getSlotID())))
								{
									found = true;
									eDebugCI("found!");
									eDVBCISlot *tmpci = it->cislot = tmp->cislot;
									while(tmpci)
									{
										++tmpci->use_count;
										eDebug("(2)CISlot %d, usecount now %d", tmpci->getSlotID(), tmpci->use_count);
										tmpci=tmpci->linked_next;
									}
									/* legat de modulul care are deja serviciul (fara gotPMT): si el iese de la modulul
									   de acces cand canalul merge numai prin CI (lib/dvb_ci/hdscicale.h) */
									it->pmthandler->ciALuatCanalul();
								}
							}
							tmp_cislot=tmp_cislot->linked_next;
						}
						eDebugCI("...");
						++tmp;
					}
				}

				if (useThis)
				{
					if (ci_it->user_mapped)  // we dont like to link user mapped CIs
					{
						eDebugCI("user mapped CI already in use... dont link!");
						continue;
					}

					++ci_it->use_count;
					eDebug("(1)CISlot %d, usecount now %d", ci_it->getSlotID(), ci_it->use_count);

					/* HD Satelit: sursele ca text, ca in OE-Alliance: CI<slot> si litera tunerului ('A' + numarul lui), si
					   pentru tunerele de dupa D (FBC: 8 demodulatoare pe un loc; inainte ramanea A, deci modulul primea
					   fluxul altui tuner si canalul ramanea negru) */
					std::string ci_source = hdsTsmuxCi(ci_it->getSlotID());

					if (!it->cislot)
					{
						int tunernum = -1;
						eUsePtr<iDVBChannel> channel;
						if (!pmthandler->getChannel(channel) && channel)
						{
							ePtr<iDVBFrontend> frontend;
							if (!channel->getFrontend(frontend) && frontend)
							{
								eDVBFrontend *fe = (eDVBFrontend*) &(*frontend);
								tunernum = fe->getSlotID();
							}
						}
						std::string tuner_source = hdsTsmuxLitera(tunernum);
						ci_it->current_tuner = tunernum;
						if (tuner_source.empty())
						{
							/* fara tuner (sau peste Z): nicio intrare tsmux de schimbat, ca in OE-Alliance */
							hdsjurnal::scrief("ci", hdsjurnal::INFO, "slot", "CI%d: canalul n-are tuner cu litera (%d), rutarea /proc/stb/tsmux ramane neatinsa",
								ci_it->getSlotID(), tunernum);
						}
						else
						{
							setInputSource(tunernum, ci_source);
							ci_it->setSource(tuner_source);
							/* HD Satelit: rutarea citita inapoi din /proc, ca jurnalul CI sa arate ce a primit driverul */
							char fin[32], fci[32];
							snprintf(fin, sizeof(fin), "input%d", tunernum);
							snprintf(fci, sizeof(fci), "ci%d_input", ci_it->getSlotID());
							hdsjurnal::scrief("ci", hdsjurnal::INFO, "slot", "CI%d rutare: %s=%s (cerut %s), %s=%s (cerut %s)",
								ci_it->getSlotID(), fin, hdsTsmuxCiteste(HDS_TSMUX_DOSAR, fin).c_str(), ci_source.c_str(),
								fci, hdsTsmuxCiteste(HDS_TSMUX_DOSAR, fci).c_str(), tuner_source.c_str());
						}
					}
					else
					{
						ci_it->current_tuner = it->cislot->current_tuner;
						ci_it->linked_next = it->cislot;
						ci_it->setSource(ci_it->linked_next->current_source);
						ci_it->linked_next->setSource(ci_source);
					}
					it->cislot = ci_it;
					eDebugCI("assigned!");
					gotPMT(pmthandler);
				}

				if (it->cislot && user_mapped) // CI assigned to this pmthandler in this run.. and user mapped? then we break here.. we dont like to link other CIs to user mapped CIs
				{
					eDebugCI("user mapped CI assigned... dont link CIs!");
					break;
				}
			}
		}
		if (!it->cislot)
			hdsJurnalFaraModul(caids, m_slots);
	}
}

void eDVBCIInterfaces::addPMTHandler(eDVBServicePMTHandler *pmthandler)
{
	// check if this pmthandler is already registered
	PMTHandlerList::iterator it = m_pmt_handlers.begin();
	while (it != m_pmt_handlers.end())
	{
		if ( *it++ == pmthandler )
			return;
	}

	eServiceReferenceDVB ref;
	pmthandler->getServiceReference(ref);
	eDebug("[eDVBCIInterfaces] addPMTHandler %s", ref.toString().c_str());

	m_pmt_handlers.push_back(CIPmtHandler(pmthandler));
	recheckPMTHandlers();
}

void eDVBCIInterfaces::removePMTHandler(eDVBServicePMTHandler *pmthandler)
{
	PMTHandlerList::iterator it=std::find(m_pmt_handlers.begin(),m_pmt_handlers.end(),pmthandler);
	if (it != m_pmt_handlers.end())
	{
		eDVBCISlot *slot = it->cislot;
		eDVBCISlot *base_slot = slot;
		eDVBServicePMTHandler *pmthandler = it->pmthandler;
		m_pmt_handlers.erase(it);

		eServiceReferenceDVB service_to_remove;
		pmthandler->getServiceReference(service_to_remove);

		bool sameServiceExist=false;
		for (PMTHandlerList::iterator i=m_pmt_handlers.begin(); i != m_pmt_handlers.end(); ++i)
		{
			if (i->cislot)
			{
				eServiceReferenceDVB ref;
				i->pmthandler->getServiceReference(ref);
				if ( ref == service_to_remove )
				{
					sameServiceExist=true;
					break;
				}
			}
		}

		while(slot)
		{
			eDVBCISlot *next = slot->linked_next;
			if (!sameServiceExist)
			{
				eDebug("[eDVBCIInterfaces] remove last pmt handler for service %s send empty capmt",
					service_to_remove.toString().c_str());
				std::vector<uint16_t> caids;
				caids.push_back(0xFFFF);
				slot->sendCAPMT(pmthandler, caids);  // send a capmt without caids to remove a running service
				slot->removeService(service_to_remove.getServiceID().get());
			}

			if (!--slot->use_count)
			{
				if (slot->linked_next)
					slot->linked_next->setSource(slot->current_source);
				else
					setInputSource(slot->current_tuner, slot->current_source);

				if (base_slot != slot)
				{
					eDVBCISlot *tmp = it->cislot;
					while(tmp->linked_next != slot)
						tmp = tmp->linked_next;
					ASSERT(tmp);
					if (slot->linked_next)
						tmp->linked_next = slot->linked_next;
					else
						tmp->linked_next = 0;
				}
				else // removed old base slot.. update ptr
					base_slot = slot->linked_next;
				slot->linked_next = 0;
				slot->user_mapped = false;
			}
			eDebug("(3) slot %d usecount is now %d", slot->getSlotID(), slot->use_count);
			slot = next;
		}
		// check if another service is waiting for the CI
		recheckPMTHandlers();
	}
}

bool eDVBCIInterfaces::isHandlerAssigned(eDVBServicePMTHandler *pmthandler)
{
	for (PMTHandlerList::iterator it = m_pmt_handlers.begin(); it != m_pmt_handlers.end(); ++it)
		if (it->pmthandler == pmthandler)
			return it->cislot != NULL;
	return false;
}

void eDVBCIInterfaces::gotPMT(eDVBServicePMTHandler *pmthandler)
{
	eDebug("[eDVBCIInterfaces] gotPMT");
	PMTHandlerList::iterator it=std::find(m_pmt_handlers.begin(), m_pmt_handlers.end(), pmthandler);
	if (it != m_pmt_handlers.end() && it->cislot)
	{
		eDVBCISlot *tmp = it->cislot;
		bool trimis = false;
		while(tmp)
		{
			eDebugCI("check slot %d %d %d", tmp->getSlotID(), tmp->running_services.empty(), canDescrambleMultipleServices(tmp->getSlotID()));
			if (tmp->running_services.empty() || canDescrambleMultipleServices(tmp->getSlotID()))
			{
				tmp->setCaParameter(pmthandler);  // CI+: demux, program, pid-uri, tuner (OE-Alliance)
				tmp->sendCAPMT(pmthandler);
				trimis = true;
			}
			tmp = tmp->linked_next;
		}
		/* un canal pe o singura cale: cu optiunea pornita, serviciul dat modulului CI iese de la modulul de acces
		   (si cand modulul l-a luat dupa zap, de pilda la pornirea lui) */
		if (trimis)
			pmthandler->ciALuatCanalul();
	}
}

int eDVBCIInterfaces::getMMIState(int slotid)
{
	eDVBCISlot *slot;

	if( (slot = getSlot(slotid)) == 0 )
		return -1;

	return slot->getMMIState();
}

/* HD Satelit: ca in enigma2 OE-Alliance de azi (lib/dvb_ci/hdstsmux.h): „CI<slot>” sau litera tunerului in
   /proc/stb/tsmux/input<tuner>, oricate sloturi ar fi (ramura veche DM7025 scria „CI” pe placile cu un slot) */
/* si oricare ar fi tunerul (A..Z, si tunerele FBC de dupa D) */
int eDVBCIInterfaces::setInputSource(int tuner_no, const std::string &source)
{
	const char *sursa = source.c_str();
	if (tuner_no < 0 || source.empty())
	{
		eDebug("setInputSource(%d, %s) failed!!!", tuner_no, sursa);
		return 0;
	}
	char fisier[32];
	snprintf(fisier, sizeof(fisier), "input%d", tuner_no);
	int eroare = 0;
	if (!hdsTsmuxScrie(HDS_TSMUX_DOSAR, fisier, sursa, &eroare))
		eDebug("[CI] %s/%s: sursa %s refuzata: %s", HDS_TSMUX_DOSAR, fisier, sursa, strerror(eroare));
	eDebug("eDVBCIInterfaces->setInputSource(%d) = %s", tuner_no, sursa);
	return 0;
}

PyObject *eDVBCIInterfaces::getDescrambleRules(int slotid)
{
	eDVBCISlot *slot = getSlot(slotid);
	if (!slot)
	{
		char tmp[255];
		snprintf(tmp, 255, "eDVBCIInterfaces::getDescrambleRules try to get rules for CI Slot %d... but just %zd slots are available", slotid, m_slots.size());
		PyErr_SetString(PyExc_Exception, tmp);
		return 0;
	}
	ePyObject tuple = PyTuple_New(3);
	int caids = slot->possible_caids.size();
	int services = slot->possible_services.size();
	int providers = slot->possible_providers.size();
	ePyObject caid_list = PyList_New(caids);
	ePyObject service_list = PyList_New(services);
	ePyObject provider_list = PyList_New(providers);
	caidSet::iterator caid_it(slot->possible_caids.begin());
	while(caids)
	{
		--caids;
		PyList_SET_ITEM(caid_list, caids, PyLong_FromLong(*caid_it));
		++caid_it;
	}
	serviceSet::iterator ref_it(slot->possible_services.begin());
	while(services)
	{
		--services;
		PyList_SET_ITEM(service_list, services, PyUnicode_FromString(ref_it->toString().c_str()));
		++ref_it;
	}
	providerSet::iterator provider_it(slot->possible_providers.begin());
	while(providers)
	{
		ePyObject tuple = PyTuple_New(2);
		PyTuple_SET_ITEM(tuple, 0, PyUnicode_FromString(provider_it->first.c_str()));
		PyTuple_SET_ITEM(tuple, 1, PyLong_FromUnsignedLong(provider_it->second));
		--providers;
		PyList_SET_ITEM(provider_list, providers, tuple);
		++provider_it;
	}
	PyTuple_SET_ITEM(tuple, 0, service_list);
	PyTuple_SET_ITEM(tuple, 1, provider_list);
	PyTuple_SET_ITEM(tuple, 2, caid_list);
	return tuple;
}

const char *PyObject_TypeStr(PyObject *o)
{
	return Py_TYPE(o) && Py_TYPE(o)->tp_name ? Py_TYPE(o)->tp_name : "unknown object type";
}

RESULT eDVBCIInterfaces::setDescrambleRules(int slotid, SWIG_PYOBJECT(ePyObject) obj )
{
	eDVBCISlot *slot = getSlot(slotid);
	if (!slot)
	{
		char tmp[255];
		snprintf(tmp, 255, "eDVBCIInterfaces::setDescrambleRules try to set rules for CI Slot %d... but just %zd slots are available", slotid, m_slots.size());
		PyErr_SetString(PyExc_Exception, tmp);
		return -1;
	}
	if (!PyTuple_Check(obj))
	{
		char tmp[255];
		snprintf(tmp, 255, "2nd argument of setDescrambleRules is not a tuple.. it is a '%s'!!", PyObject_TypeStr(obj));
		PyErr_SetString(PyExc_Exception, tmp);
		return -1;
	}
	if (PyTuple_Size(obj) != 3)
	{
		const char *errstr = "eDVBCIInterfaces::setDescrambleRules not enough entrys in argument tuple!!\n"
			"first argument should be a pythonlist with possible services\n"
			"second argument should be a pythonlist with possible providers/dvbnamespace tuples\n"
			"third argument should be a pythonlist with possible caids";
		PyErr_SetString(PyExc_Exception, errstr);
		return -1;
	}
	ePyObject service_list = PyTuple_GET_ITEM(obj, 0);
	ePyObject provider_list = PyTuple_GET_ITEM(obj, 1);
	ePyObject caid_list = PyTuple_GET_ITEM(obj, 2);
	if (!PyList_Check(service_list) || !PyList_Check(provider_list) || !PyList_Check(caid_list))
	{
		char errstr[512];
		snprintf(errstr, 512, "eDVBCIInterfaces::setDescrambleRules incorrect data types in argument tuple!!\n"
			"first argument(%s) should be a pythonlist with possible services (reference strings)\n"
			"second argument(%s) should be a pythonlist with possible providers (providername strings)\n"
			"third argument(%s) should be a pythonlist with possible caids (ints)",
			PyObject_TypeStr(service_list), PyObject_TypeStr(provider_list), PyObject_TypeStr(caid_list));
		PyErr_SetString(PyExc_Exception, errstr);
		return -1;
	}
	slot->possible_caids.clear();
	slot->possible_services.clear();
	slot->possible_providers.clear();
	int size = PyList_Size(service_list);
	while(size)
	{
		--size;
		ePyObject refstr = PyList_GET_ITEM(service_list, size);
		if (!PyUnicode_Check(refstr))
		{
			char buf[255];
			snprintf(buf, 255, "eDVBCIInterfaces::setDescrambleRules entry in service list is not a string.. it is '%s'!!", PyObject_TypeStr(refstr));
			PyErr_SetString(PyExc_Exception, buf);
			return -1;
		}
		const char *tmpstr = PyUnicode_AsUTF8(refstr);
		if (!tmpstr)  // a str with surrogates: the Python error is already set, do not use a NULL string
		{
			eDebug("eDVBCIInterfaces::setDescrambleRules entry in service list is not usable as UTF-8!!");
			return -1;
		}
		eServiceReference ref(tmpstr);
		if (ref.valid())
			slot->possible_services.insert(ref);
		else
			eDebug("eDVBCIInterfaces::setDescrambleRules '%s' is not a valid service reference... ignore!!", tmpstr);
	};
	size = PyList_Size(provider_list);
	while(size)
	{
		--size;
		ePyObject tuple = PyList_GET_ITEM(provider_list, size);
		if (!PyTuple_Check(tuple))
		{
			char buf[255];
			snprintf(buf, 255, "eDVBCIInterfaces::setDescrambleRules entry in provider list is not a tuple it is '%s'!!", PyObject_TypeStr(tuple));
			PyErr_SetString(PyExc_Exception, buf);
			return -1;
		}
		if (PyTuple_Size(tuple) != 2)
		{
			char buf[255];
			snprintf(buf, 255, "eDVBCIInterfaces::setDescrambleRules provider tuple has %zd instead of 2 entries!!", PyTuple_Size(tuple));
			PyErr_SetString(PyExc_Exception, buf);
			return -1;
		}
		if (!PyUnicode_Check(PyTuple_GET_ITEM(tuple, 0)))
		{
			char buf[255];
			snprintf(buf, 255, "eDVBCIInterfaces::setDescrambleRules 1st entry in provider tuple is not a string it is '%s'", PyObject_TypeStr(PyTuple_GET_ITEM(tuple, 0)));
			PyErr_SetString(PyExc_Exception, buf);
			return -1;
		}
		if (!PyLong_Check(PyTuple_GET_ITEM(tuple, 1)))
		{
			char buf[255];
			snprintf(buf, 255, "eDVBCIInterfaces::setDescrambleRules 2nd entry in provider tuple is not a long it is '%s'", PyObject_TypeStr(PyTuple_GET_ITEM(tuple, 1)));
			PyErr_SetString(PyExc_Exception, buf);
			return -1;
		}
		const char *tmpstr = PyUnicode_AsUTF8(PyTuple_GET_ITEM(tuple, 0));
		if (!tmpstr)  // a str with surrogates: the Python error is already set, strlen(NULL) stopped enigma2
		{
			eDebug("eDVBCIInterfaces::setDescrambleRules provider name is not usable as UTF-8!!");
			return -1;
		}
		uint32_t orbpos = PyLong_AsUnsignedLong(PyTuple_GET_ITEM(tuple, 1));
		if (strlen(tmpstr))
			slot->possible_providers.insert(std::pair<std::string, uint32_t>(tmpstr, orbpos));
		else
			eDebug("eDVBCIInterfaces::setDescrambleRules ignore invalid entry in provider tuple (string is empty)!!");
	};
	size = PyList_Size(caid_list);
	while(size)
	{
		--size;
		ePyObject caid = PyList_GET_ITEM(caid_list, size);
		if (!PyLong_Check(caid))
		{
			char buf[255];
			snprintf(buf, 255, "eDVBCIInterfaces::setDescrambleRules entry in caid list is not a long it is '%s'!!", PyObject_TypeStr(caid));
			PyErr_SetString(PyExc_Exception, buf);
			return -1;
		}
		int tmpcaid = PyLong_AsLong(caid);
		if (tmpcaid > 0 && tmpcaid < 0x10000)
			slot->possible_caids.insert(tmpcaid);
		else
			eDebug("eDVBCIInterfaces::setDescrambleRules %d is not a valid caid... ignore!!", tmpcaid);
	};
	return 0;
}

PyObject *eDVBCIInterfaces::readCICaIds(int slotid)
{
	eDVBCISlot *slot = getSlot(slotid);
	if (!slot)
	{
		char tmp[255];
		snprintf(tmp, 255, "eDVBCIInterfaces::readCICaIds try to get CAIds for CI Slot %d... but just %zd slots are available", slotid, m_slots.size());
		PyErr_SetString(PyExc_Exception, tmp);
	}
	else
	{
		int idx=0;
		eDVBCICAManagerSession *ca_manager = slot->getCAManager();
		const std::vector<uint16_t> *ci_caids = ca_manager ? &ca_manager->getCAIDs() : 0;
		ePyObject list = PyList_New(ci_caids ? ci_caids->size() : 0);
		if (ci_caids)
		{
			for (std::vector<uint16_t>::const_iterator it = ci_caids->begin(); it != ci_caids->end(); ++it)
				PyList_SET_ITEM(list, idx++, PyLong_FromLong(*it));
		}
		return list;
	}
	return 0;
}

int eDVBCIInterfaces::setCIClockRate(int slotid, int rate)
{
	eDVBCISlot *slot = getSlot(slotid);
	if (slot)
		return slot->setClockRate(rate);
	return -1;
}

int eDVBCIInterfaces::setCIEnabled(int slotid, bool enabled)
{
	eDVBCISlot *slot = getSlot(slotid);
	if (slot)
		return slot->setEnabled(enabled);
	return -1;
}

/* CI+: rutarea fluxului prin modul in timpul autentificarii (din sursele GPL enigma2 (OE-Alliance), commitul
   29d951a6ec2e019680741efdad5ca7e7902b20e4, eDVBCIInterfaces::setCIPlusRouting/revertCIPlusRouting). Multe module
   CI+ 1.3 cer un transponder trecut prin ele ca sa termine autentificarea (orice canal). Sursele vechi se citesc
   asa cum sunt din /proc si se scriu inapoi la fel cand modulul a primit cheile (sau cand e scos). */
static bool hdsCitesteSursa(const char *cale, std::string &sursa)
{
	char buf[32] = {0};
	FILE *f = fopen(cale, "r");
	if (!f)
		return false;
	bool bun = fscanf(f, "%31s", buf) == 1;
	fclose(f);
	if (bun)
		sursa = buf;
	return bun && !sursa.empty();
}

static void hdsScrieSursa(const char *cale, const std::string &sursa)
{
	FILE *f = fopen(cale, "w");
	if (!f)
	{
		eDebug("[CI] nu pot scrie %s", cale);
		return;
	}
	fputs(sursa.c_str(), f);
	fclose(f);
}

void eDVBCIInterfaces::setCIPlusRouting(int slotid)
{
	eDebug("[CI] setCIRouting slotid=%d", slotid);
	eDVBCISlot *slot = getSlot(slotid);
	if (!slot || slotid < 0)
		return;
	if (m_pmt_handlers.empty())
	{
		eDebug("[CI] setCIRouting: niciun canal pornit, rutarea ramane cum e");
		return;
	}
	/* cererile repetate de Content Control nu au voie sa suprascrie sursele salvate */
	if (slot->ciplusRoutingDone() || slot->getCIPlusRoutingTunerNum() >= 0)
		return;
	/* modulul are deja canale (rutarea lor, ca „CamMgrRouting active” in OE-Alliance): primeste deja un transponder,
	   iar mutarea altui tuner prin el ar lasa canalul decriptat fara imagine */
	if (slot->use_count > 0)
	{
		eDebug("[CI] setCIRouting: slotul %d are deja canale, rutarea ramane", slotid);
		return;
	}
	for (PMTHandlerList::iterator it = m_pmt_handlers.begin(); it != m_pmt_handlers.end(); ++it)
	{
		if (it->cislot)  // canalul are deja un modul alocat: rutarea lui ramane neatinsa
			continue;
		int tunernum = -1;
		eUsePtr<iDVBChannel> channel;
		if (!it->pmthandler->getChannel(channel) && channel)
		{
			ePtr<iDVBFrontend> frontend;
			if (!channel->getFrontend(frontend) && frontend)
				tunernum = ((eDVBFrontend *)&(*frontend))->getSlotID();
		}
		std::string litera = hdsTsmuxLitera(tunernum);  // A..Z, si tunerele FBC de dupa D
		if (litera.empty())
			continue;
		char cale[64];
		std::string sursa, sursa_ci;
		snprintf(cale, sizeof(cale), "/proc/stb/tsmux/input%d", tunernum);
		if (!hdsCitesteSursa(cale, sursa))
			continue;
		snprintf(cale, sizeof(cale), "/proc/stb/tsmux/ci%d_input", slotid);
		if (!hdsCitesteSursa(cale, sursa_ci))
			continue;
		/* CI<n> al altui modul fara canale (autentificarea lui in curs): sursa tunerului e litera lui (hdstsmux.h) */
		{
			int n = hdsTsmuxSlotDinSursa(sursa);
			eDVBCISlot *alt = n >= 0 ? getSlot(n) : 0;
			std::string a_tunerului = hdsTsmuxSursaTunerului(sursa, alt && alt->use_count > 0, litera);
			if (a_tunerului != sursa)
			{
				hdsjurnal::scrief("ci", hdsjurnal::INFO, "slot", "CI%d autentificare CI+: input%d era %s (autentificarea altui modul), tinut minte %s",
					slotid, tunernum, sursa.c_str(), a_tunerului.c_str());
				sursa = a_tunerului;
			}
		}
		setInputSource(tunernum, hdsTsmuxCi(slotid));
		slot->setSource(litera);
		slot->setCIPlusRoutingParameter(tunernum, sursa, sursa_ci);
		hdsjurnal::scrief("ci", hdsjurnal::INFO, "slot", "CI%d autentificare CI+: tunerul %d trecut prin modul", slotid, tunernum);
		break;
	}
}

void eDVBCIInterfaces::revertCIPlusRouting(int slotid)
{
	eDVBCISlot *slot = getSlot(slotid);
	if (!slot)
		return;
	/* chemat de managerul CI+ cand modulul a dat cheile (check_new_key): autentificarea a reusit */
	if (slot->getCCManager())
		slot->m_ciplus_keys = true;
	if (slot->ciplusRoutingDone())
		return;
	/* intre timp modulul a primit canale (zap pe un canal decriptat): rutarea lor e cea buna, sursele vechi nu se mai
	   scriu peste ea */
	if (slot->use_count > 0)
	{
		slot->setCIPlusRoutingDone();
		return;
	}
	int tunernum = slot->getCIPlusRoutingTunerNum();
	if (tunernum >= 0 && !slot->getCIPlusRoutingInput().empty() && !slot->getCIPlusRoutingCIInput().empty())
	{
		char cale[64];
		snprintf(cale, sizeof(cale), "/proc/stb/tsmux/ci%d_input", slotid);
		hdsScrieSursa(cale, slot->getCIPlusRoutingCIInput());
		/* doua module CI+ pe acelasi tuner (hdstsmux.h): CI<n> tinut minte al unui modul fara canale nu e sursa tunerului;
		   daca celalalt modul se autentifica inca, fluxul trece prin el pana termina si el */
		std::string inapoi = slot->getCIPlusRoutingInput();
		int n = hdsTsmuxSlotDinSursa(inapoi);
		eDVBCISlot *alt = n >= 0 ? getSlot(n) : 0;
		int in_autentificare = -1, cu_canale = -1;
		for (eSmartPtrList<eDVBCISlot>::iterator it(m_slots.begin()); it != m_slots.end(); ++it)
		{
			if ((eDVBCISlot *)it == slot)
				continue;
			if (cu_canale < 0 && it->use_count > 0 && it->current_tuner == tunernum)
				cu_canale = it->getSlotID();
			else if (in_autentificare < 0 && !it->use_count && !it->ciplusRoutingDone() && it->getCIPlusRoutingTunerNum() == tunernum)
				in_autentificare = it->getSlotID();
		}
		snprintf(cale, sizeof(cale), "/proc/stb/tsmux/input%d", tunernum);
		std::string acum;
		bool acum_cu_canale = false;
		if (cu_canale >= 0 && hdsCitesteSursa(cale, acum))
		{
			int na = hdsTsmuxSlotDinSursa(acum);
			eDVBCISlot *sa = na >= 0 ? getSlot(na) : 0;
			acum_cu_canale = sa && sa->use_count > 0;
		}
		inapoi = hdsTsmuxSursaInapoi(inapoi, alt && alt->use_count > 0, hdsTsmuxLitera(tunernum), in_autentificare, cu_canale,
			acum_cu_canale);
		if (inapoi.empty())
			hdsjurnal::scrief("ci", hdsjurnal::INFO, "slot", "CI%d autentificare CI+ gata: tunerul %d ramane pe modulul care a primit intre timp canale", slotid, tunernum);
		else
		{
			hdsScrieSursa(cale, inapoi);
			hdsjurnal::scrief("ci", hdsjurnal::INFO, "slot", "CI%d autentificare CI+ gata: tunerul %d inapoi pe sursa lui (%s)", slotid, tunernum, inapoi.c_str());
		}
	}
	slot->setCIPlusRoutingDone();
}

int eDVBCIInterfaces::getCIPlusState(int slotid)
{
	eDVBCISlot *slot = getSlot(slotid);
	if (!slot || !slot->getCCManager())
		return 0;
	/* 3 = cheia CI+ a modulului refuzata de driver pe toate dispozitivele caN potrivite (imaginea s-ar opri) */
	if (slot->m_ciplus_cheie_refuzata)
		return 3;
	return slot->m_ciplus_keys ? 2 : 1;
}

std::string eDVBCIInterfaces::getLanguage()
{
	/* limba meniului, pentru resursa Host Language & Country a modulelor CI+ */
	return hdsSetareCi("config.osd.language", "en_GB");
}

int eDVBCISlot::send(const unsigned char *data, size_t len)
{
	int res=0;
	//int i;
	//eDebugNoNewLine("< ");
	//for(i=0;i<len;i++)
	//	eDebugNoNewLine("%02x ",data[i]);
	//eDebug("");

	if (fd < 0)  // slotul oprit: nimic nu pleaca spre modul
		return -1;

	if (sendqueue.empty())
		res = ::write(fd, data, len);

	if (res < 0 || (unsigned int)res != len)
	{
		unsigned char *d = new unsigned char[len];
		memcpy(d, data, len);
		sendqueue.push( queueData(d, len) );
		notifier->setRequested(eSocketNotifier::Read | eSocketNotifier::Priority | eSocketNotifier::Write);
	}

	return res;
}

void eDVBCISlot::data(int what)
{
	eDebugCI("CISlot %d what %d\n", getSlotID(), what);
	if (state == stateDisabled)
		return;
	if(what == eSocketNotifier::Priority) {
		if(state != stateRemoved) {
			state = stateRemoved;
			hdsjurnal::scrief("ci", hdsjurnal::INFO, "slot", "CI%d modul scos", getSlotID());
			/* CI+: modulul scos in timpul autentificarii nu lasa tunerul legat de un slot gol (fara imagine) */
			eDVBCIInterfaces::getInstance()->revertCIPlusRouting(getSlotID());
			m_ciplus_keys = false;
			while(sendqueue.size())
			{
				delete [] sendqueue.top().data;
				sendqueue.pop();
			}
			eDVBCISession::deleteSessions(this);
			eDVBCIInterfaces::getInstance()->ciRemoved(this);
			if (notifier)  // slotul oprit cand /dev/ciN nu s-a putut deschide: fara notificator
				notifier->setRequested(eSocketNotifier::Read);
			eDVBCI_UI::getInstance()->setState(getSlotID(),0);
		}
		return;
	}

	if (state == stateInvalid)
		reset();

	if(state != stateInserted) {
		eDebug("ci inserted in slot %d", getSlotID());
		hdsjurnal::scrief("ci", hdsjurnal::INFO, "slot", "CI%d modul introdus", getSlotID());
		state = stateInserted;
		/* CI+: optiunile citite iar (schimbarea lor nu cere repornire), rutarea de autentificare de la zero */
		readCIPlusSettings();
		m_ciPlusRoutingDone = false;
		m_ciplus_keys = false;
		m_ciplus_routing_tunernum = -1;
		m_ciplus_routing_input.clear();
		m_ciplus_routing_ci_input.clear();
		eDVBCI_UI::getInstance()->setState(getSlotID(),1);
		notifier->setRequested(eSocketNotifier::Read|eSocketNotifier::Priority);
		/* enable PRI to detect removal or errors */
	}

	if (what & eSocketNotifier::Read) {
		__u8 data[4096];
		int r;
		r = ::read(fd, data, 4096);
		if(r > 0) {
//			int i;
//			eDebugNoNewLine("> ");
//			for(i=0;i<r;i++)
//				eDebugNoNewLine("%02x ",data[i]);
//			eDebug("");
			eDVBCISession::receiveData(this, data, r);
			eDVBCISession::pollAll();
			return;
		}
	}
	else if (what & eSocketNotifier::Write) {
		if (!sendqueue.empty()) {
			const queueData &qe = sendqueue.top();
			int res = ::write(fd, qe.data, qe.len);
			if (res >= 0 && (unsigned int)res == qe.len)
			{
				delete [] qe.data;
				sendqueue.pop();
			}
		}
		else
			notifier->setRequested(eSocketNotifier::Read|eSocketNotifier::Priority);
	}
}

DEFINE_REF(eDVBCISlot);

eDVBCISlot::eDVBCISlot(eMainloop *context, int nr)
	:startup_timeout(eTimer::create(context))
{
	application_manager = 0;
	mmi_session = 0;
	ca_manager = 0;
	cc_manager = 0;
	m_ca_demux_id = -1;
	m_program_number = 0;
	m_video_pid = 0;
	m_audio_pid = 0;
	m_audio_number = 0;
	memset(m_audio_pids, 0, sizeof(m_audio_pids));
	m_tunernum = -1;
	m_ciPlusRoutingDone = false;
	m_ciplus_keys = false;
	m_ca_decode_demux_id = -1;
	m_ca_ales = -1;
	m_ciplus_cheie_refuzata = false;
	m_ciplus_routing_tunernum = -1;
	use_count = 0;
	linked_next = 0;
	user_mapped = false;
	plugged = false;
	fd = -1;
	m_context = context;
	state = stateDisabled;

	slotid = nr;
	readCIPlusSettings();

	/* din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4: slotul oprit nu se
	   deschide deloc (starea 3 in Python, „modul oprit”); cel pornit se deschide dupa intarzierea pornirii
	   (config.cimisc.bootDelay, implicit 5 s), ca modulele care pornesc greu sa nu fie resetate inainte sa fie gata */
	char cheie[64];
	snprintf(cheie, sizeof(cheie), "config.ci.%d.enabled", nr);
	bool pornit = hdsSetareCi(cheie, "true") != "false";
	if (pornit)
	{
		int intarziere = atoi(hdsSetareCi("config.cimisc.bootDelay", "5").c_str());
		if (intarziere < 0 || intarziere > 15)
			intarziere = 5;
		hdsjurnal::scrief("ci", hdsjurnal::INFO, "slot", "CI%d pornit, deschis dupa %d s", nr, intarziere);
		eDVBCI_UI::getInstance()->setState(nr, 0);  // slotul se vede in meniu si cat asteapta
		if (intarziere)
		{
			CONNECT(startup_timeout->timeout, eDVBCISlot::openDevice);
			startup_timeout->start(1000 * intarziere, true);
		}
		else
			openDevice();
	}
	else
	{
		hdsjurnal::scrief("ci", hdsjurnal::INFO, "slot", "CI%d oprit din setari", nr);
		eDVBCI_UI::getInstance()->setState(nr, 3);
	}
}

void eDVBCISlot::openDevice()
{
	char filename[128];

	plugged = true;

	sprintf(filename, "/dev/ci%d", slotid);

//	possible_caids.insert(0x1702);
//	possible_providers.insert(providerPair("PREMIERE", 0xC00000));
//	possible_services.insert(eServiceReference("1:0:1:2A:4:85:C00000:0:0:0:"));

	fd = ::open(filename, O_RDWR | O_NONBLOCK | O_CLOEXEC);

	eDebugCI("CI Slot %d has fd %d", getSlotID(), fd);
	state = stateInvalid;

	if (fd >= 0)
	{
		notifier = eSocketNotifier::create(m_context, fd, eSocketNotifier::Read | eSocketNotifier::Priority | eSocketNotifier::Write);
		CONNECT(notifier->activated, eDVBCISlot::data);
	} else
	{
		perror(filename);
	}
}

void eDVBCISlot::closeDevice()
{
	/* ca in OE-Alliance: dispozitivul se inchide, apoi drumul „modul scos” (sesiunile sterse, canalele luate inapoi) */
	if (notifier)
		notifier->stop();
	if (fd >= 0)
		::close(fd);
	fd = -1;
	data(eSocketNotifier::Priority);
	state = stateDisabled;
}

int eDVBCISlot::setEnabled(bool enabled)
{
	eDebug("[CI%d] Enabled: %d, state %d", slotid, enabled, state);
	startup_timeout->stop();
	if (enabled && state != stateDisabled)
		return 0;
	if (!enabled && state == stateDisabled)
	{
		eDVBCI_UI::getInstance()->setState(slotid, 3);
		return 0;
	}
	if (enabled)
	{
		hdsjurnal::scrief("ci", hdsjurnal::INFO, "slot", "CI%d pornit din meniu", slotid);
		eDVBCI_UI::getInstance()->setState(slotid, 0);
		openDevice();
	}
	else
	{
		hdsjurnal::scrief("ci", hdsjurnal::INFO, "slot", "CI%d oprit din meniu", slotid);
		closeDevice();
		eDVBCI_UI::getInstance()->setState(slotid, 3);
	}
	return 0;
}

eDVBCISlot::~eDVBCISlot()
{
	eDVBCISession::deleteSessions(this);
	if (fd >= 0)
		::close(fd);
}

void eDVBCISlot::setAppManager( eDVBCIApplicationManagerSession *session )
{
	application_manager=session;
}

void eDVBCISlot::setMMIManager( eDVBCIMMISession *session )
{
	mmi_session = session;
}

void eDVBCISlot::setCAManager( eDVBCICAManagerSession *session )
{
	ca_manager = session;
}

void eDVBCISlot::setCCManager( eDVBCICcSession *session )
{
	cc_manager = session;
}

/* CI+: profilurile operatorului si optiunile de decriptare (config.ci.N.disable_operator_profile,
   config.ci.N.alternative_ca_handling 0-3), citite din /etc/enigma2/settings la pornire si la fiecare modul introdus,
   ca in OE-Alliance (eSimpleConfig in constructorul slotului) */
void eDVBCISlot::readCIPlusSettings()
{
	char cheie[80];
	snprintf(cheie, sizeof(cheie), "config.ci.%d.disable_operator_profile", slotid);
	m_operator_profiles_disabled = hdsSetareCi(cheie, "false") == "true";
	snprintf(cheie, sizeof(cheie), "config.ci.%d.alternative_ca_handling", slotid);
	/* „auto” (implicit din 0.7.5) sau lipsa = dispozitivul il alege receptorul (lib/dvb_ci/hdscica.h); 0-3 alese de mana
	   lucreaza exact ca in OE-Alliance */
	m_alt_ca_handling = hdsCaOptiune(hdsSetareCi(cheie, "auto").c_str());
	/* felul dispozitivului care a primit cheia ultima data */
	m_ca_ales = -1;
	m_ciplus_cheie_refuzata = false;
	char cale[80];
	snprintf(cale, sizeof(cale), HDS_CA_FISIER, slotid);
	FILE *f = fopen(cale, "r");
	if (f)
	{
		char text[8] = "";
		if (fgets(text, sizeof(text), f))
			m_ca_ales = hdsCaFel(text);
		fclose(f);
	}
}

/* HD Satelit: felul dispozitivului caN care a primit cheia CI+; scris pe disc numai cand se schimba, ca la urmatoarea
   pornire sa fie incercat intai */
void eDVBCISlot::setCaAles(int fel)
{
	if (fel < 0 || fel >= HDS_CA_FELURI || fel == m_ca_ales)
		return;
	m_ca_ales = fel;
	mkdir("/etc/enigma2/hdsatelit", 0755);
	char cale[80];
	snprintf(cale, sizeof(cale), HDS_CA_FISIER, slotid);
	FILE *f = fopen(cale, "w");
	if (f)
	{
		fprintf(f, "%d\n", fel);
		fclose(f);
	}
	hdsjurnal::scrief("ci", hdsjurnal::INFO, "slot", "CI%d CI+: dispozitivul de descifrare tinut minte: felul %d (%s)", slotid, fel,
		fel == HDS_CA_DATE ? "ca<demux>" : fel == HDS_CA_DATE_PLUS1 ? "ca<demux+1>" : "ca<demuxul decodorului>");
}

/* HD Satelit: cheia CI+ refuzata pe toate dispozitivele (sau primita din nou): starea CI+ a slotului se schimba, iar
   ecranul (Screens/Ci.py, CiMessageHandler) si pagina web o afla prin ciStateChanged */
void eDVBCISlot::setCheieCiplusRefuzata(bool refuzata)
{
	if (refuzata == m_ciplus_cheie_refuzata)
		return;
	m_ciplus_cheie_refuzata = refuzata;
	eDVBCI_UI::getInstance()->anuntaStareCiplus(slotid);
}

void eDVBCISlot::setCIPlusRoutingParameter(int tunernum, const std::string &input, const std::string &ci_input)
{
	m_ciplus_routing_tunernum = tunernum;
	m_ciplus_routing_input = input;
	m_ciplus_routing_ci_input = ci_input;
}

/* parametrii descifrarii CI+ pentru canalul trimis modulului (din sursele GPL enigma2 (OE-Alliance), commitul
   29d951a6ec2e019680741efdad5ca7e7902b20e4, eDVBCISlot::setCaParameter) */
int eDVBCISlot::setCaParameter(eDVBServicePMTHandler *pmthandler)
{
	ePtr<iDVBDemux> demux;
	eDVBServicePMTHandler::program program;
	eServiceReferenceDVB ref;
	uint8_t dmx_id;
	eUsePtr<iDVBChannel> channel;
	ePtr<iDVBFrontend> frontend;

	m_ca_demux_id = -1;
	if (!pmthandler->getDataDemux(demux) && demux && !demux->getCADemuxID(dmx_id))
		m_ca_demux_id = dmx_id;
	/* demuxul decodorului, numai cand e deja aflat (fara sa ceara alt demux): al treilea dispozitiv de incercat */
	m_ca_decode_demux_id = pmthandler->getDecodeDemuxNum();

	pmthandler->getServiceReference(ref);
	m_program_number = ref.getServiceID().get();

	m_audio_number = 0;
	m_video_pid = 0;
	m_audio_pid = 0;
	if (!pmthandler->getProgramInfo(program))
	{
		m_audio_number = program.audioStreams.size();
		if (m_audio_number > 16)
			m_audio_number = 16;
		for (int i = 0; i < m_audio_number; i++)
			m_audio_pids[i] = program.audioStreams[i].pid;
		m_video_pid = program.videoStreams.empty() ? 0 : program.videoStreams[0].pid;
		m_audio_pid = (program.audioStreams.empty() || program.defaultAudioStream < 0 || static_cast<size_t>(program.defaultAudioStream) >= program.audioStreams.size()) ? 0 : program.audioStreams[program.defaultAudioStream].pid;
	}

	m_tunernum = -1;
	if (!pmthandler->getChannel(channel) && channel && !channel->getFrontend(frontend) && frontend)
	{
		m_tunernum = ((eDVBFrontend *)&(*frontend))->getSlotID();
#ifndef DESCRAMBLER_VU
		/* calea Vu+ (al doilea tuner FBC, sloturile 8-15) exista numai pe Vu+; in rest tunerul nu conteaza */
		if (m_tunernum > 7)
			m_tunernum = -1;
#endif
	}
	eDebug("[CI%d] setCaParameter demux %d (decodor %d) tuner %d program %04x", slotid, m_ca_demux_id, m_ca_decode_demux_id, m_tunernum, m_program_number);
	return 0;
}

int eDVBCISlot::getSlotID()
{
	return slotid;
}

int eDVBCISlot::reset()
{
	eDebug("CI Slot %d: reset requested", getSlotID());
	hdsjurnal::scrief("ci", hdsjurnal::INFO, "slot", "CI%d resetare ceruta", getSlotID());

	if (fd < 0)  // slotul oprit sau inca neinceput (intarzierea pornirii)
		return -1;

	/* HD Satelit (CI+ pe AX HD51, forumul 479): dupa resetare modulul isi deschide sesiuni noi (transportul se reia de la
	   zero); cele vechi se sterg aici, ca la scoaterea modulului. Altfel managerul CI+ vechi tinea deschis dispozitivul caN
	   („can not open /dev/dvb/adapter0/ca0” la cel nou, darog69, 13.11.2026 21:11), iar optiunile CI+ schimbate din meniu
	   (Screens/Ci.py reseteaza modulul dupa ele) nu ajungeau la nucleu: se citeau numai la introducerea modulului. */
	eDVBCISession::deleteSessions(this);
	m_ciplus_keys = false;
	readCIPlusSettings();

	if (state == stateInvalid)
	{
		unsigned char buf[256];
		eDebug("ci flush");
		while(::read(fd, buf, 256)>0);
		state = stateResetted;
	}

	while(sendqueue.size())
	{
		delete [] sendqueue.top().data;
		sendqueue.pop();
	}

	ioctl(fd, 0);

	return 0;
}

int eDVBCISlot::startMMI()
{
	eDebug("CI Slot %d: startMMI()", getSlotID());
	
	if(application_manager)
		application_manager->startMMI();
	
	return 0;
}

int eDVBCISlot::stopMMI()
{
	eDebug("CI Slot %d: stopMMI()", getSlotID());

	if(mmi_session)
		mmi_session->stopMMI();
	
	return 0;
}

int eDVBCISlot::answerText(int answer)
{
	eDebug("CI Slot %d: answerText(%d)", getSlotID(), answer);

	if(mmi_session)
		mmi_session->answerText(answer);

	return 0;
}

int eDVBCISlot::getMMIState()
{
	if(mmi_session)
		return 1;

	return 0;
}

int eDVBCISlot::answerEnq(char *value)
{
	eDebug("CI Slot %d: answerENQ(%s)", getSlotID(), value);

	if(mmi_session)
		mmi_session->answerEnq(value);

	return 0;
}

int eDVBCISlot::cancelEnq()
{
	eDebug("CI Slot %d: cancelENQ", getSlotID());

	if(mmi_session)
		mmi_session->cancelEnq();

	return 0;
}

int eDVBCISlot::sendCAPMT(eDVBServicePMTHandler *pmthandler, const std::vector<uint16_t> &ids)
{
	if (!ca_manager)
	{
		eDebug("no ca_manager (no CI plugged?)");
		return -1;
	}
	const std::vector<uint16_t> &caids = ids.empty() ? ca_manager->getCAIDs() : ids;
	ePtr<eTable<ProgramMapSection> > ptr;
	if (pmthandler->getPMT(ptr))
		return -1;
	else
	{
		eDVBTableSpec table_spec;
		ptr->getSpec(table_spec);
		int pmt_version = table_spec.version & 0x1F; // just 5 bits

		eServiceReferenceDVB ref;
		pmthandler->getServiceReference(ref);
		uint16_t program_number = ref.getServiceID().get();
		std::map<uint16_t, uint8_t>::iterator it =
			running_services.find(program_number);
		bool sendEmpty = caids.size() == 1 && caids[0] == 0xFFFF;

		if ( it != running_services.end() &&
			(pmt_version == it->second) &&
			!sendEmpty )
		{
			eDebug("[eDVBCISlot] dont send self capmt version twice");
			return -1;
		}

		std::vector<ProgramMapSection*>::const_iterator i=ptr->getSections().begin();
		if ( i == ptr->getSections().end() )
			return -1;
		else
		{
			unsigned char raw_data[2048];

//			eDebug("send %s capmt for service %04x to slot %d",
//				it != running_services.end() ? "UPDATE" : running_services.empty() ? "ONLY" : "ADD",
//				program_number, slotid);

			CaProgramMapSection capmt(*i++,
				it != running_services.end() ? 0x05 /*update*/ : running_services.empty() ? 0x03 /*only*/ : 0x04 /*add*/, 0x01, caids );
			while( i != ptr->getSections().end() )
			{
		//			eDebug("append");
				capmt.append(*i++);
			}
			capmt.writeToBuffer(raw_data);

// begin calc capmt length
			int wp=0;
			int hlen;
			if ( raw_data[3] & 0x80 )
			{
				int i=0;
				int lenbytes = raw_data[3] & ~0x80;
				while(i < lenbytes)
					wp = (wp << 8) | raw_data[4 + i++];
				wp+=4;
				wp+=lenbytes;
				hlen = 4 + lenbytes;
			}
			else
			{
				wp = raw_data[3];
				wp+=4;
				hlen = 4;
			}
// end calc capmt length

			if (sendEmpty)
			{
//				eDebugNoNewLine("SEND EMPTY CAPMT.. old version is %02x", raw_data[hlen+3]);
				if (sendEmpty && running_services.size() == 1)  // check if this is the capmt for the last running service
					raw_data[hlen] = 0x03; // send only instead of update... because of strange effects with alphacrypt
				raw_data[hlen+3] &= ~0x3E;
				raw_data[hlen+3] |= ((pmt_version+1) & 0x1F) << 1;
//				eDebug(" new version is %02x", raw_data[hlen+3]);
			}

//			eDebug("ca_manager %p dump capmt:", ca_manager);
//			for(int i=0;i<wp;i++)
//				eDebugNoNewLine("%02x ", raw_data[i]);
//			eDebug("");

			//dont need tag and lenfield
			ca_manager->sendCAPMT(raw_data + hlen, wp - hlen);
			running_services[program_number] = pmt_version;

			/* CI+ (din sursele GPL enigma2 (OE-Alliance), commitul 29d951a6ec2e019680741efdad5ca7e7902b20e4): pid-urile
			   programului merg la descifrarea CI+ (numai cand modulul a deschis Content Control) */
			if (cc_manager)
			{
				std::vector<uint16_t> pids;
				int prg_info_len = ((raw_data[hlen + 4] << 8) | raw_data[hlen + 5]) & 0xfff;
				int es_info_len = 0;
				for (int jj = hlen + prg_info_len + 6; jj + 4 < wp; jj += es_info_len + 5)
				{
					uint16_t es_pid = ((raw_data[jj + 1] << 8) | raw_data[jj + 2]) & 0x1fff;
					pids.push_back(es_pid);
					es_info_len = ((raw_data[jj + 3] << 8) | raw_data[jj + 4]) & 0xfff;
				}
				if (!sendEmpty)
					cc_manager->addProgram(program_number, pids);
				else
					cc_manager->removeProgram(program_number, pids);
			}
		}
	}
	return 0;
}

void eDVBCISlot::removeService(uint16_t program_number)
{
	if (program_number == 0xFFFF)
		running_services.clear();  // remove all
	else
		running_services.erase(program_number);  // remove single service
}

/* HD Satelit: ca in enigma2 OE-Alliance de azi (lib/dvb_ci/hdstsmux.h): sursa modulului in /proc/stb/tsmux/ci<slot>_input,
   oricate sloturi ar fi (ramura veche DM7025 o scria in /proc/stb/tsmux/input2, intrarea demuxului 2) */
int eDVBCISlot::setSource(const std::string &source)
{
	current_source = source;
	const char *sursa = source.c_str();
	if (source.empty())
	{
		eDebug("CI Slot %d: setSource failed!!!", getSlotID());
		return 0;
	}
	char fisier[32];
	snprintf(fisier, sizeof(fisier), "ci%d_input", slotid);
	int eroare = 0;
	if (!hdsTsmuxScrie(HDS_TSMUX_DOSAR, fisier, sursa, &eroare))
		eDebug("[CI] %s/%s: sursa %s refuzata: %s", HDS_TSMUX_DOSAR, fisier, sursa, strerror(eroare));
	eDebug("CI Slot %d setSource = %s", getSlotID(), sursa);
	return 0;
}

int eDVBCISlot::setClockRate(int rate)
{
	char buf[64];
	snprintf(buf, 64, "/proc/stb/tsmux/ci%d_tsclk", slotid);
	FILE *ci = fopen(buf, "wb");
	if (ci)
	{
		/* 2 = extra_high, numai unde driverul il ofera in ci%d_tsclk_choices (ca in OE-Alliance) */
		if (rate == 2)
			fprintf(ci, "extra_high");
		else if (rate)
			fprintf(ci, "high");
		else
			fprintf(ci, "normal");
		fclose(ci);
		return 0;
	}
	return -1;
}

eAutoInitP0<eDVBCIInterfaces> init_eDVBCIInterfaces(eAutoInitNumbers::dvb, "CI Slots");
