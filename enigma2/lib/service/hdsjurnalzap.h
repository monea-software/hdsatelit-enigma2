/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsjurnalzap.h: jurnalul schimbarii de canal (/home/root/logs/hds-zap.log, forma din lib/base/hdsjurnal.h), numai
 * pentru canalul viu din fereastra principala (nu inregistrari, nu fisiere, nu a doua fereastra). Un membru al
 * eDVBServicePlay, chemat cu cate un rand din servicedvb.cpp: start, evenimentele PMT, updateDecoder, primul eveniment
 * al decodorului video, stop.
 *
 * CE SE SCRIE:
 *   INFO  zap reusit: tunerul, timpii pasilor de la cerere (acordare = canalul primit, program = PID-uri date
 *         decodorului, inclusiv din cache; imagine = primul eveniment video; pe V20 vine la ~0,5-1 s dupa primul cadru
 *         aratat, iar dupa o repornire cu aceeasi marime a imaginii nu vine deloc: atunci la FARA_IMAGINE_MS se
 *         intreaba PTS-ul decodorului), codecurile, marimea imaginii, criptat
 *         da/nu. FARA canal: nici numele, nici referinta, nici transponderul (acelea sunt in hds-tuner.log, dupa ora).
 *         sunet: codecul; "fara" numai dupa ce a sosit PMT-ul si n-are sunet; "nestiut" cand randul se scrie inaintea PMT-ului.
 *   AVERT/EROARE la esec, CU canalul (ca sa se afle exact canalul care nu merge): numele, referinta, pozitia,
 *         transponderul, sistemul, SID-ul, PID-urile si codecurile; motivul: fara resurse (tuner ocupat), fara PAT,
 *         serviciul lipsa din PAT, fara PMT, acordare esuata, configurare gresita, fara imagine dupa
 *         FARA_IMAGINE_MS de la cerere (la un canal criptat: fara acces sau raspuns lent al modulului), oprit de om
 *         fara imagine dupa mai mult de PRAG_OPRIRE_MS.
 * Exemplu: "2026-10-29T08:14:04Z [INFO] [zap] A reusit: acordare 118 ms, program 302 ms, imagine 846 ms | video H264
 *   1920x1080 | sunet AAC | criptat nu"
 *
 * Scris de la zero pentru imaginea HD Satelit.
 */
#ifndef __lib_service_hdsjurnalzap_h
#define __lib_service_hdsjurnalzap_h

#include <lib/base/ebase.h>
#include <lib/dvb/idvb.h>
#include <lib/dvb/pmt.h>
#include <sigc++/sigc++.h>

namespace hdsjzap
{

enum { FARA_IMAGINE_MS = 6000, PRAG_OPRIRE_MS = 3000 };

class Zap: public sigc::trackable
{
public:
	Zap();
	/* start(): masurat = canalul viu din fereastra principala */
	void pornire(const eServiceReferenceDVB &ref, bool masurat);
	/* serviceEvent: evenimentul PMT handler-ului; slot = tunerul la eventTuned, altfel -1 */
	void eveniment(int ev, int slot);
	/* updateDecoder: programul citit si PID-ul video dat decodorului (vpid <= 0 = fara imagine, radio) */
	void program(const eDVBServicePMTHandler::program &p, int vpid, int vtip);
	/* Finalizare radio dupa incercarea CA PMT. */
	void programGata();
	enum { PMT_PRIMIT, DECODOR_PREGATIT, CA_PMT_TRIMIS, EVENIMENT_VIDEO, NR_MARCAJE };
	/* Timpi absoluti monotoni; zero cere o singura citire de ceas. */
	void marcaj(int etapa, long long t = 0);
	void acordare(const eDVBFrontend::TimpiZap &t);
	/* video_event: primul eveniment; nu confirma primul cadru HDMI. */
	void imagine(int latime, int inaltime);
	/* stop() */
	void oprire();
	/* la FARA_IMAGINE_MS fara niciun eveniment al decodorului (aceeasi marime a imaginii ca inainte: decodorul nu trimite
	   nimic): "arata decodorul ceva?" (PTS-ul imaginii), intrebare data de eDVBServicePlay; fara ea randul e AVERT */
	typedef bool (*AreImagine)(void *);
	void verificare(AreImagine f, void *ctx) { m_are_imagine = f; m_ctx = ctx; }
private:
	AreImagine m_are_imagine;
	void *m_ctx;
	bool m_activ, m_esec, m_avert;
	long long m_t0, m_t_acordat, m_t_program, m_t_imagine;
	long long m_marcaje[NR_MARCAJE], m_t_comanda, m_t_blocare;
	long m_sec_ms;
	int m_slot, m_vpid, m_vtip, m_apid, m_atip, m_criptat, m_sid;
	eServiceReferenceDVB m_ref;
	ePtr<eTimer> m_ceas;
	void faraImagine();
	void scrieEsec(const char *nivel, const char *motiv);
	void textCanal(char *buf, size_t n);
	void textMarcaje(char *buf, size_t n) const;
	void textSunet(char *buf, size_t n) const;
};

}

#endif
