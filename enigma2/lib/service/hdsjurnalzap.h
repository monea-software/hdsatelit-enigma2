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
 *         tarziu da randul „imagine tarzie”. Nu se citeste /proc/stb/video/zapmode (pe HiSilicon poate da Oops).
 *         La coada, ca la esec, numai numele si referinta canalului ("| canal: nume=... ref=..."; din 0.7.7,
 *         asistenta 888733: fara ele nu se putea spune daca un canal care o data a iesit "oprit fara imagine" a mers
 *         alta data); transponderul si PID-urile raman ale randurilor cu esec (transponderul si in hds-tuner.log, dupa
 *         ora). Canalul randurilor reusite e pentru asistenta: hds-zap.log nu intra in rapoartele prin coduri QR
 *         (HdsQrRapoarte), iar in pachetele testerilor coada lor se taie (HdsBetaTester.faraCanaleReusite; nota lor
 *         spune „fără listele tale de canale”, iar canalul care nu merge era deja acceptat).
 *         sunet: codecul; "fara" numai dintr-un program PMT aplicat (pmtPid valid), nu din marcajul de primire.
 *         Fara pista in cache: "nestiut"; dupa randul video/radio datele audio tarzii completeaza acelasi zap_t0,
 *         fara un temporizator nou. Oprirea, refuzul si urmatorul zap anuleaza asteptarea.
 *   AVERT/EROARE la esec, CU canalul (ca sa se afle exact canalul care nu merge): numele, referinta, pozitia,
 *         transponderul, sistemul, SID-ul, PID-urile si codecurile; motivul: fara resurse (tuner ocupat), fara PAT,
 *         serviciul lipsa din PAT, fara PMT, acordare esuata, configurare gresita, fara imagine dupa
 *         FARA_IMAGINE_MS de la cerere (la un canal criptat: fara acces sau raspuns lent al modulului; cu
 *         evenimentul video venit, dar fara cadre noi: „eveniment video fara cadre noi”), oprit de om
 *         fara imagine dupa mai mult de PRAG_OPRIRE_MS.
 * Exemplu: "2026-10-29T08:14:04Z [INFO] [zap] A reusit: acordare 118 ms, program 302 ms, imagine 846 ms | video H264
 *   1920x1080 | sunet AAC | criptat nu | zap_t0 ... | marcaje: ... | canal: nume="TVR 1" ref=1:0:19:..."
 *
 * PLACILE FARA EVENIMENT VIDEO (15.11.2026, Vu+ Solo SE, driverul Vu+ vechi): decodorul nu trimite niciodata evenimentul
 * video, deci fara masura de mai jos fiecare zap scria "imagine fara eveniment de la decodor (merge la 6000 ms)" (timpul
 * pana la imagine lipsea) si, la zap-ul facut intre 3 si 6 s, "oprit fara imagine" fals. Dupa INVATAT_DUPA zap-uri la
 * rand cu imagine (PTS miscat) si fara eveniment, placa e tinuta minte ca fara eveniment (pana la repornirea enigma2):
 * atunci PTS-ul se citeste de la program() (decodorul pornit), la PAS_PTS_MS,
 * si imaginea e prima din doua citiri la rand cu PTS-ul miscat (o citire singura poate fi PTS-ul canalului dinainte
 * inlocuit de cel nou). Randul: "imagine N ms (din PTS, fara eveniment video)". Primele zap-uri dupa pornire raman ca
 * inainte (randul de la 6 s e corect, numai fara timp).
 * Un eveniment video sterge numai socoteala de dinaintea invatarii (zap-urile la rand); o placa invatata ramane invatata
 * (0.7.7, asistenta 888733, Vu+ Duo 4K SE): driverul Vu+ 4K trimite evenimentul NUMAI cand se schimba marimea imaginii,
 * deci dupa un canal SD urmat de unul HD semnul se stergea, PTS-ul se citea iar abia la 6 s, iar zap-ul parasit la 3,8-6,3 s
 * pe un canal de aceeasi marime iesea "oprit fara imagine", chiar daca imaginea mergea. Citirile de la program() nu strica
 * nimic pe o placa cu eveniment: evenimentul venit intre ele da timpul imaginii, ca inainte.
 *
 * RELEUL T2-MI LOCAL (15.11.2026): canalul pus prin releul imaginii (hdsreleut2.h, 127.0.0.1:8889/t2/) vine ca flux, fara
 * tunerul si fara acordarea acestui canal (tunerul il tine releul). Randul nu mai arata tunerul "?" si "acordare -1 ms",
 * ci "releu T2-MI" in locul literei tunerului, fara campul acordare: "releu T2-MI reusit: program 210 ms, imagine 900 ms
 * | ...". Randurile tunerelor raman neschimbate.
 *
 * Scris de la zero pentru imaginea HD Satelit.
 */
#ifndef __lib_service_hdsjurnalzap_h
#define __lib_service_hdsjurnalzap_h

#include <lib/base/ebase.h>
#include <lib/dvb/idvb.h>
#include <lib/dvb/pmt.h>
#include <sigc++/sigc++.h>
#include <string>

namespace hdsjzap
{

enum { FARA_IMAGINE_MS = 6000, PRAG_OPRIRE_MS = 3000, PAS_PTS_MS = 350, MAX_CITIRI_RATATE = 6, INVATAT_DUPA = 2 };

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
	/* pmtPid valid: program citit din PMT, nu doar marcajul primit inainte de updateDecoder.
	   Dupa randul video/radio provizoriu asteptam numai datele audio, fara un ceas nou. */
	bool m_program_pmt, m_sunet_asteptat;
	long long m_t0, m_t_acordat, m_t_program, m_t_imagine;
	/* evenimentul video (timpul, marimea) si citirile PTS-ului de dupa el sau de la FARA_IMAGINE_MS */
	long long m_t_eveniment, m_pts, m_t_cadre, m_termen_pts;
	int m_latime, m_inaltime, m_citiri, m_bune;
	bool m_pts_bun;
	ePtr<eTimer> m_ceas_pts;
	void citestePts();
	void pornesteCitiri(long long termen);
	/* cum s-a aflat imaginea: evenimentul video (cu cadre), PTS-ul la FARA_IMAGINE_MS fara eveniment, PTS-ul citit de la
	   program() pe o placa fara eveniment video */
	enum { CU_EVENIMENT, FARA_EVENIMENT, DIN_PTS };
	void scrieImagine(long long t, int cum);
	/* placa fara eveniment video: m_din_pts = citirile pornite de la program(); m_t_miscare = prima citire cu PTS miscat,
	   inca neconfirmata de a doua; s_fara_eveniment = zap-uri la rand cu imagine si fara eveniment (pe tot procesul,
	   eDVBServicePlay si deci Zap se fac din nou la fiecare canal) */
	bool m_din_pts;
	long long m_t_miscare;
	static int s_fara_eveniment;
	long long m_marcaje[NR_MARCAJE], m_t_comanda, m_t_blocare;
	/* cand a ajuns cererea la tuner (eDVBFrontend::tune, TimpiZap.pornire_ms): desparte o intarziere dinaintea acordarii
	   (alocarea canalului, bucla principala ocupata dupa iesirea dintr-un film) de una din secventa SEC */
	long long m_t_acordare_ceruta;
	long m_sec_ms;
	int m_slot, m_vpid, m_vtip, m_apid, m_atip, m_criptat, m_sid;
	/* canalul vine prin releul T2-MI local (hdsEsteReleuT2 pe calea referintei, la pornire) */
	bool m_releu;
	/* inceputul randului: litera tunerului sau "releu T2-MI"; campul "acordare N ms, " (gol la releu) */
	void textCine(char *buf, size_t n) const;
	void textAcordare(char *buf, size_t n) const;
	eServiceReferenceDVB m_ref;
	ePtr<eTimer> m_ceas;
	void faraImagine();
	void scrieEsec(const char *nivel, const char *motiv);
	void textCanal(char *buf, size_t n);
	/* numele canalului din lista de canale ("" cand nu e), cu ghilimelele schimbate in apostrof */
	std::string numeCanal();
	/* coada randurilor reusite: " | canal: nume=\"...\" ref=..." (numai numele si referinta) */
	void textCanalScurt(char *buf, size_t n);
	void textMarcaje(char *buf, size_t n) const;
	void textSunet(char *buf, size_t n) const;
};

}

#endif
