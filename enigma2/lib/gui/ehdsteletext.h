/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * ehdsteletext.h: widgetul care deseneaza o pagina de teletext (ecranul de pe tasta TEXT, Screens/HdsTeletext.py).
 *
 * Pagina vine din memoria paginilor (lib/dvb/hdsteletext.h, eHdsTeletext), se randeaza in 25 x 40 de celule si se
 * compune o data, cand se schimba, in doua poze ARGB: antetul (randul 0, unde merge ceasul) si corpul (randurile
 * 1-24). Compunerea se face la desen, o singura data pentru toate schimbarile de pana atunci (la deschidere veneau pe
 * rand marimea din skin, marimea ecranului, HD, peste imagine, sursa si pagina: 3-4 compuneri); in rest la desenare
 * se pun numai pozele. Cand pagina vine din nou in carusel (versiunea ei creste la fiecare pachet,
 * si cand continutul e acelasi), se asteapta sa se termine de primit si se recompune numai partea ale carei celule s-au
 * schimbat fata de cele compuse (integrarea 0.3.0: pe ARM o recompunere HD costa 300-1600 ms, iar ZDF p100 se
 * recompunea la fiecare trecere a caruselului). Literele sunt ale fontului din skin (atributul font), centrate in celula:
 * fiecare litera se scrie o singura data (eTextPara pe o ciorna, ca in esubtitle.cpp), iar acoperirea ei se pastreaza;
 * o litera mai lata decat celula se strange pe orizontala, cele duble se intind. Pagina e 4:3 (celula cat 5/6 din
 * inaltime), centrata in widget.
 *
 * Doua feluri: pe tot ecranul (fundal negru opac) si peste imagine (fundalul negru transparent, celelalte fundaluri
 * pe jumatate). Doua desene: clasic si neted (numele intern: hd). Optiunile, oprite din fabrica: conturul negru (numai
 * in jurul a ce e deschis la culoare), umbra literelor si, numai la neted, formele in relief.
 *
 * Traducerea paginii (Components/HdsTraducereTeletext.py, setTraducere): literele traduse se pun peste celulele
 * corpului dupa randare, cu fundalul si atributele celulelor (si culoarea literei data, unde e data), numai cat pagina
 * aratata are amprenta corpului pentru care a fost facuta traducerea (o pagina schimbata in carusel ramane in original
 * pana vine traducerea ei).
 */
#ifndef __lib_gui_ehdsteletext_h
#define __lib_gui_ehdsteletext_h

#include <lib/gui/ewidget.h>
#include <lib/gdi/gpixmap.h>
#include <lib/gdi/gfont.h>
#include <lib/dvb/hdsteletext.h>

#ifndef SWIG
class eHdsTeletextGlife;
#endif

class eHdsTeletextWidget: public eWidget
{
public:
	eHdsTeletextWidget(eWidget *parent);
	~eHdsTeletextWidget();

	/* familia fontului (din skin); marimea se socoteste din celula */
	void setFont(gFont *font);
	/* 0 = pe tot ecranul, 1 = peste imagine */
	void setPeste(int peste);
	int getPeste() { return m_peste; }
	/* teletextul neted (mozaicul netezit; numele intern a ramas hd): 1 = pornit */
	void setHd(int hd);
	int getHd() { return m_hd; }
	/* conturul negru in jurul literelor (si, peste imagine, al formelor) deschise la culoare: 1 = pornit */
	void setContur(int contur);
	int getContur() { return m_contur; }
	/* umbra literelor: 1 = pornita */
	void setUmbra(int umbra);
	int getUmbra() { return m_umbra; }
	/* formele in relief (numai la neted): 1 = pornite */
	void setRelief(int relief);
	int getRelief() { return m_relief; }
	/* de unde vin paginile: -1 = canalul care merge, 0 = copia incarcata pentru televizor (eHdsTeletext::copie(0)) */
	void setSursa(int sursa);
	/* cat a durat ultima compunere (antet si corp), milisecunde */
	int ultimaCompunereMs() { return m_ms; }
	void setArataAscuns(int arata);
	int getArataAscuns() { return m_arata_ascuns; }
	/* coloanele 0-7 ale antetului (numarul paginii sau cifrele tastate), cel mult 8 litere */
	void setStare(const char *stare);
	/* pagina 100..899 si subcodul (-1 = cea primita cel mai recent); 1 = pagina e in memorie */
	int setPagina(int pagina, int subcod);
	/* chemata des de ecran: reface ce s-a schimbat (pagina, antetul cu ceasul, memoria golita la zap);
	   1 = pagina ceruta e in memorie */
	int actualizeaza();
	/* faza intermitentelor: 1 = literele intermitente stinse; reface numai daca pagina le are */
	void setFaza(int stinse);
	int areIntermitente() { return m_are_intermitente; }
	/* subcodul subpaginii aratate acum (-1 = niciuna) */
	int subcodAratat() { return m_subcod_aratat; }
	/* locul paginii in widget (pentru mesajele ecranului): x, y, latimea, inaltimea */
	int paginaX() { return m_x0; }
	int paginaY() { return m_y0; }
	int paginaLatime() { return hdsttx::COLOANE * m_l; }
	int paginaInaltime() { return hdsttx::RANDURI * m_i; }
	/* traducerea paginii: literele si culorile celulelor randurilor 1-24, cate 960 de semne (UTF-8). La litere U+0001
	   = celula ramane cum e, altfel litera pusa in celula (mozaicul ei sters, fundalul si atributele raman); la culori
	   '0'-'7' = culoarea literei, orice alt semn = culoarea celulei. Se pune numai peste pagina `pagina` cat corpul ei
	   are amprenta `amprenta` (amprentaCorp). 1 = primita, 0 = marimi gresite (nimic schimbat). */
	int setTraducere(int pagina, int amprenta, const char *litere, const char *culori);
	/* fara traducere: pagina in original */
	void stergeTraducere();
	/* amprenta corpului (randurile 1-24) randat ultima oara, fara traducere: crc32 (ca zlib.crc32) al celor 960 de
	   celule scrise ca in eHdsTeletext::pagina (8 octeti fiecare), & 0x7FFFFFFF; -1 inainte de prima randare */
	int amprentaCorp() { return m_amprenta; }
	/* 1 = la ultima randare traducerea s-a pus peste pagina */
	int traducereAratata() { return m_trad_aratata; }

protected:
	int event(int event, void *data, void *data2);

#ifndef SWIG
private:
	void aseaza();
	/* cere compunerea pozelor (intotdeauna: aspectul s-a schimbat sau alta pagina) */
	void reface(bool antet, bool corp);
	/* randeaza celulele si cere compunerea numai a partii ale carei celule difera de cele compuse; cu_corp fals =
	   numai antetul */
	void refaSchimbat(bool cu_corp);
	/* cererile se strang pana la desen (evtPaint): acolo compuneCerute randeaza celulele si compune o singura data */
	void cere(bool antet, bool corp);
	void compuneCerute();
	void randeazaCelule();
	void compunePoze(bool antet, bool corp);
	void culoareaFundalului();
	/* dupa randeazaCelule: traducerea peste celulele corpului, daca e a paginii aratate */
	void puneTraducerea();

	eHdsTeletextGlife *m_glife;
	std::string m_familie;
	int m_peste, m_arata_ascuns, m_stinse, m_are_intermitente, m_hd, m_sursa, m_ms;
	int m_contur, m_umbra, m_relief;
	eHdsTeletext *sursa();
	std::string m_stare;
	int m_pagina, m_subcod, m_subcod_aratat, m_gasita;
	uint32_t m_v_pagina, m_v_antet, m_v_colector;
	uint32_t m_v_vazut;         /* versiunea paginii la trecerea de dinainte a ceasului (pagina inca se primeste?) */
	int m_amanari;              /* de cate treceri se asteapta sa se termine de primit pagina */
	int m_cere_antet, m_cere_corp;  /* compuneri cerute, facute la desen */
	int m_l, m_i, m_x0, m_y0;
	hdsttx::Celula m_celule[hdsttx::RANDURI][hdsttx::COLOANE];
	hdsttx::Celula m_compus[hdsttx::RANDURI][hdsttx::COLOANE];     /* celulele din pozele de acum */
	ePtr<gPixmap> m_poza_antet, m_poza_corp, m_poza_corp_stinsa;
	std::vector<uint32_t> m_trad_litere;    /* 960 de litere (randurile 1-24) sau gol = fara traducere */
	std::string m_trad_culori;              /* 960 de semne sau gol */
	int m_trad_pagina, m_trad_amprenta, m_amprenta, m_trad_aratata;
#endif
};

#endif
