/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsegalizator.h: egalizatorul in procesor pentru posturile de radio (Meniu > Audio > Egalizator,
 * lib/python/Components/HdsEgalizator.py, pagina web /egalizator).
 *
 * Placa de sunet a receptorului nu are egalizator, deci cat egalizatorul e pornit, sunetul unui post de radio nu mai
 * trece prin decodorul placii: fluxul audio al postului se citeste din demultiplexor (filtru PES, ca cititorul de RDS),
 * se decodeaza in procesor cu GStreamer (MPEG audio cu mpg123; AAC cu decodorul care exista in imagine, LATM prin ADTS:
 * hdsegalizator_flux.h), trece prin prelucrarea din hdsegalizator_dsp.h (10 benzi, Noapte, nivel, limitator) si iese
 * pe placa ALSA a receptorului (biblioteca libasound se incarca la pornire, cu dlopen).
 * Canalele TV: imaginea o arata placa dupa ceasul ei, deci sunetul din procesor se tine dupa PTS-ul
 * imaginii, citit de servicedvb la 100 ms (VIDEO_GET_PTS, ceasImagine): PTS-ul fiecarui PES audio merge prin GStreamer
 * pana la cadrele din tampon, iar firul placii aseaza sunetul cu tacere, aruncare sau raportul tamponului
 * (hdsegalizator_dsp.h: CeasImagine, SincronImagine). Numai sunetul MPEG (MP2); setarea „tv” il opreste, „potrivire” il
 * muta fata de imagine. Fara ceasul imaginii in TV_FARA_CEAS_MS sau fara sincron in TV_NEPOTRIVIT_MS sunetul se
 * intoarce pe placa (stare(): „tv-fara-ceas”, „tv-nepotrivit”). Cu setarea „tv” oprita, la canalele TV motorul citeste
 * o data ceasul demultiplexorului (numai citire) si spune in stare() („ceas_tv”) daca driverul il da.
 *
 * Legatura cu redarea (lib/service/servicedvb.cpp): la fiecare alegere a pistei de sunet a serviciului principal,
 * preiaSunetul() spune daca sunetul trece pe aici; atunci decodorul placii primeste PID-ul -1 (fara sunet), iar RDS,
 * lista de piste si memoria PID-ului raman pe PID-ul adevarat. Oprirea serviciului cheama serviciuOprit(). O schimbare
 * a setarii „pornit” sau o cadere a drumului din procesor cheama functia de reaplicare data de serviciu (alegerea din
 * nou a pistei de acum), deci sunetul trece inapoi pe placa fara sa ramana liniste.
 *
 * Firul enigma2 nu asteapta niciodata: preiaSunetul() si setarile doar noteaza; pornirea si oprirea drumului (GStreamer,
 * ALSA, demultiplexorul) le face firul „hds-egal”. Firele: „hds-egal” (comenzi, stare, volum), „hds-egal-cit”
 * (demultiplexorul sau fisierul), firul GStreamer (decodarea si prelucrarea), „hds-egal-ies” (placa de sunet). Fiecare
 * isi masoara timpul de procesor (CLOCK_THREAD_CPUTIME_ID); stare() da suma, in procente dintr-un nucleu.
 *
 * Proba fara receptor (emulator, PC): pornesteDinFisier() trece un fisier TS sau un flux audio pe acelasi drum, cu
 * iesirea intr-un fisier WAV.
 */

#ifndef __lib_service_hdsegalizator_h
#define __lib_service_hdsegalizator_h

#include <lib/python/connections.h>
#ifndef SWIG
#include <sigc++/sigc++.h>
#include <string>
#endif

#ifndef SWIG
class eHdsEgalizatorMotor;
#endif

class eHdsEgalizator
#ifndef SWIG
	: public sigc::trackable
#endif
{
	static eHdsEgalizator *instance;
#ifdef SWIG
	eHdsEgalizator();
	~eHdsEgalizator();
#endif
public:
#ifndef SWIG
	eHdsEgalizator();
	~eHdsEgalizator();
#endif
	static eHdsEgalizator *getInstance();
	/* motorul, numai daca exista deja (fara sa-l porneasca): pentru oprirea serviciilor */
	static eHdsEgalizator *existent() { return instance; }

	/* felul fluxului audio (acelasi numar ca eDVBAudio: 0 MPEG, 3 AAC in ADTS, 4 AAC in LATM) */
	enum { felMpeg = 0, felAacAdts = 3, felAacLatm = 4, felDinFisier = -1 };

	/* setarile (firul enigma2): egalizatorul pornit de om, castigul benzii i (0..9) in dB, modul Noapte, potrivirea
	   tariei in dB, volumul aplicat aici (0 = singur, dupa placa; 1 = da; 2 = nu), placa ALSA (implicit „default”) */
	void setPornit(int pornit);
	void setBanda(int banda, double db);
	void setNoapte(int noapte);
	void setNivel(double db);
	void setVolumAici(int mod);
	void setPlacaAlsa(const char *nume);
	/* canalele TV: egalizatorul si la ele (1, implicit) sau numai la radio (0); sunetul mai tarziu (+) sau mai devreme
	   (-) fata de imagine, in ms (-300..300) */
	void setTv(int da);
	void setPotrivireTv(int ms);

	/* serviciul care merge alege din nou pista de sunet (dupa o schimbare a setarii „pornit”) */
	void reaplica();

	/* -> dictionar: pornit, stare, motiv, post, placa, ceas_tv, volum_aici, tv, potrivire_tv_ms si, cat merge o sesiune:
	   codec, decodor, latm_prin_adts, esantionare, canale, debit, debit_aprox, procesor, procesor_fire, tampon_ms, goluri,
	   aruncate, abatere_ppm, spectru, castig_inainte_db, benzi_active, limitari, iesire, fisier, secunde, cadre, la TV
	   si sesiune_tv, sincron_tv_ms, ceas_imagine (1 ms, 90 kHz, 0 inca nu), taceri_tv, aruncari_tv */
	PyObject *stare();
	/* -> dictionar: gstreamer (0/1), mpeg, aac_adts, aac_latm (numele decodorului sau None), latm_prin_adts (0/1: LATM
	   merge prin decodorul ADTS), alsa (0/1) */
	PyObject *decodoare();

	/* proba: fisierul (TS cu `pid`, sau fluxul audio insusi; pid -1 = primul PID cu sunet) pe acelasi drum; iesirea e
	   fisierul WAV `iesire` (cat de repede merge) sau, cu iesire = „alsa”, placa de sunet, in timp real;
	   -> 0 pornit, altfel motivul se vede in stare() */
	int pornesteDinFisier(const char *cale, int pid, const char *iesire);
	void opresteFisier();

	/* starea s-a schimbat (pe firul enigma2): 1 merge, 2 oprit, 3 eroare (sunetul s-a intors pe placa), 4 fara date,
	   5 proba din fisier gata */
	PSignal1<void, int> schimbare;

#ifndef SWIG
	/* din servicedvb.cpp (firul enigma2), la fiecare alegere a pistei de sunet a serviciului principal: demux = numarul
	   demultiplexorului de date (-1 la inregistrari, timeshift, fisiere), radio = serviciul nu are imagine.
	   -> true cand sunetul trece prin procesor (decodorul placii nu-l mai porneste). */
	bool preiaSunetul(const void *proprietar, int demux, int pid, int fel, bool radio, const sigc::slot<void()> &reaplica);
	/* serviciul principal se opreste */
	void serviciuOprit(const void *proprietar);
	/* serviciul principal e pus pe pauza sau porneste din nou (pause() / unpause()): sunetul din procesor se opreste
	   odata cu decodorul placii, iar la pornire pista se alege din nou */
	void pauza(const void *proprietar, bool pauza);
	/* pe firul enigma2, din pompa de mesaje */
	void mesaj(const int &cod);
	/* din servicedvb.cpp (firul enigma2), la ~100 ms cat sunetul unui canal TV trece prin procesor: PTS-ul imaginii
	   cum il da decodorul (getPTS) */
	void ceasImagine(long long pts);
private:
	eHdsEgalizatorMotor *m_motor;
	sigc::slot<void()> m_reaplica;
	const void *m_proprietar;
	eHdsEgalizator(const eHdsEgalizator &);
	eHdsEgalizator &operator=(const eHdsEgalizator &);
#endif
};

#endif
