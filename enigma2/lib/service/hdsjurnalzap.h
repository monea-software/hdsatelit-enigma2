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
 *         da/nu. „imagine” se scrie NUMAI cu cadre noi (11.11.2026): pe un canal nedescifrat (Digi 4K) evenimentul
 *         vine fara nicio imagine, deci dupa eveniment PTS-ul video se citeste de doua ori, la PAS_PTS_MS si la
 *         2 x PAS_PTS_MS (nicio cerere la decodor chiar in evenimentul lui), si numai un PTS care s-a schimbat
 *         inseamna imagine; altfel citirile continua pana la FARA_IMAGINE_MS de la cerere, iar atunci randul e
 *         AVERT „fara imagine” cu motivul (eveniment video fara cadre noi). Timpul „imagine” ramane al evenimentului
 *         cand cadrele merg de la prima pereche de citiri, altfel e al citirii care a vazut PTS-ul miscandu-se;
 *         marcajul „cadre” spune cand s-a vazut. Dupa avertisment citirile mai merg FARA_IMAGINE_MS: cheia venita
 *         tarziu da randul „imagine tarzie”. Nu se citeste /proc/stb/video/zapmode (pe HiSilicon poate da Oops). FARA canal: nici numele, nici referinta, nici transponderul (acelea sunt in hds-tuner.log, dupa ora).
 *         sunet: codecul; "fara" numai dupa ce a sosit PMT-ul si n-are sunet; "nestiut" cand randul se scrie inaintea PMT-ului.
 *   AVERT/EROARE la esec, CU canalul (ca sa se afle exact canalul care nu merge): numele, referinta, pozitia,
 *         transponderul, sistemul, SID-ul, PID-urile si codecurile; motivul: fara resurse (tuner ocupat), fara PAT,
 *         serviciul lipsa din PAT, fara PMT, acordare esuata, configurare gresita, fara imagine dupa
 *         FARA_IMAGINE_MS de la cerere (la un canal criptat: fara acces sau raspuns lent al modulului; cu
 *         evenimentul video venit, dar fara cadre noi: „eveniment video fara cadre noi”), oprit de om
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

enum { FARA_IMAGINE_MS = 6000, PRAG_OPRIRE_MS = 3000, PAS_PTS_MS = 350, MAX_CITIRI_RATATE = 6 };

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
	/* video_event: primul eveniment; nu confirma primul cadru HDMI. Cu citirea PTS-ului data, randul asteapta cadrele noi. */
	void imagine(int latime, int inaltime);
	/* stop() */
	void oprire();
	/* PTS-ul video al decodorului (true = citit), dat de eDVBServicePlay: dupa evenimentul video si la FARA_IMAGINE_MS
	   fara eveniment (aceeasi marime a imaginii ca inainte: decodorul nu trimite nimic) doua citiri cu PTS diferit
	   inseamna cadre noi. Fara ea: randul la eveniment (ca inainte) si AVERT la FARA_IMAGINE_MS. */
	typedef bool (*CitestePts)(void *, long long &pts);
	void verificare(CitestePts f, void *ctx) { m_citeste_pts = f; m_ctx = ctx; }
private:
	CitestePts m_citeste_pts;
	void *m_ctx;
	bool m_activ, m_esec, m_avert;
	long long m_t0, m_t_acordat, m_t_program, m_t_imagine;
	/* evenimentul video (timpul, marimea) si citirile PTS-ului de dupa el sau de la FARA_IMAGINE_MS */
	long long m_t_eveniment, m_pts, m_t_cadre, m_termen_pts;
	int m_latime, m_inaltime, m_citiri, m_bune;
	bool m_pts_bun;
	ePtr<eTimer> m_ceas_pts;
	void citestePts();
	void pornesteCitiri(long long termen);
	void scrieImagine(long long t, bool fara_eveniment);
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
