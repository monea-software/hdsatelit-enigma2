/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsteletext.h: paginile intregi de teletext (ETSI EN 300 706, nivelul 1 si partea de caractere a nivelului 1.5),
 * pentru vizualizatorul de pe tasta TEXT (Screens/HdsTeletext.py, lib/gui/ehdsteletext.cpp) si pagina web /teletext.
 *
 * Parserul vechi (lib/dvb/teletext.cpp) urmareste o singura pagina, pe cea a subtitrarii, si da numai textul ei. Aici
 * se culeg toate paginile serviciului care merge, cu subpaginile lor, intr-o memorie marginita (cele mai vechi pleaca
 * primele): parserul vechi da fiecare pachet si mai departe, fara sa-si schimbe drumul subtitrarilor.
 *
 * Ce se pastreaza dintr-o subpagina: octetii randurilor 0-25 asa cum au venit (cu bitul de paritate, ca sa se poata
 * citi si paginile codate Hamming, de pilda tabelul TOP 1F0), bitii de control din antet, tripletii X/26, X/28/0 si
 * legaturile FastText X/27/0. Pe magazie: M/29/0 si ultimul antet (ceasul care merge). Din 8/30: pagina de pornire
 * si numele serviciului.
 *
 * Randarea face din subpagina 25 x 40 de celule: litera (Unicode) sau mozaicul (6 sextante), culoarea literei si a
 * fundalului si atributele (dubla inaltime / latime, mozaic separat, ascuns, intermitent, cutie). Seturile de litere:
 * G0 latin cu cele 13 subseturi nationale (alese din antet, din X/28/0 sau M/29/0), al doilea set G0 prin ESC, iar din
 * X/26 literele cu semne diacritice si cele din G2 latin. Seturile chirilic, grec, arab si ebraic nu sunt inca: se arata
 * cu setul latin englezesc.
 *
 * Compunerea face din celule o poza ARGB (0xAARRGGBB, alfa 0xFF = opac): fundalurile, mozaicul ca blocuri pline,
 * literele luate de la un furnizor de glife (fontul imaginii, in lib/gui). La teletextul neted (numele intern: hd)
 * fundalurile si mozaicul legat se netezesc pe toata pagina. Conturul negru (numai in jurul a ce
 * e deschis la culoare), umbra literelor si formele in relief (numai la neted) sunt optiuni, oprite din fabrica.
 *
 * Tot ce e in namespace hdsttx e cod curat, fara antete enigma2: se compileaza si se proba pe PC (teste/
 * teletext_1_proba.cpp, teste/teletext_hd_2_proba.cpp). Clasa eHdsTeletext (pentru Python, prin SWIG) sta numai in
 * enigma2.
 */

#ifndef __lib_dvb_hdsteletext_h
#define __lib_dvb_hdsteletext_h

#include <stdint.h>
#include <stddef.h>

#ifndef SWIG
#include <map>
#include <string>
#include <vector>

namespace hdsttx
{
	enum
	{
		COLOANE = 40,
		RANDURI = 25,               /* randurile aratate: antetul (0), corpul (1-23), randul FastText (24) */
		RANDURI_PACHETE = 26,       /* randurile pastrate: 0-25 */
		TRIPLETI_X26 = 13,          /* tripleti intr-un pachet X/26 */
		LEGATURI = 6,               /* rosu, verde, galben, albastru, a cincea (index), a sasea */
		MAX_SUBPAGINI = 1500,       /* memoria implicita: cam 1,6 MB */
		PAGINA_FARA = 0             /* numar de pagina care nu exista */
	};

	/* bitii de control din antet, la pozitia lor din standard (C4 = bitul 4 ... C14 = bitul 14) */
	enum
	{
		C4_STERGE = 1 << 4, C5_STIRE = 1 << 5, C6_SUBTITRARE = 1 << 6, C7_FARA_ANTET = 1 << 7,
		C8_ACTUALIZARE = 1 << 8, C9_INTRERUPT = 1 << 9, C10_FARA_AFISARE = 1 << 10, C11_SERIAL = 1 << 11
	};

	/* atributele unei celule randate */
	enum
	{
		A_DUBLA_INALTIME = 1,
		A_DUBLA_LATIME = 2,
		A_SEPARAT = 4,              /* mozaic separat (blocuri cu rost) */
		A_ASCUNS = 8,               /* continut ascuns (se arata la cerere) */
		A_INTERMITENT = 16,
		A_CUTIE = 32,
		A_JUMATATE_JOS = 64,        /* sub o celula cu dubla inaltime: o deseneaza celula de sus */
		A_JUMATATE_DREAPTA = 128    /* langa o celula cu dubla latime: o deseneaza celula din stanga */
	};

	struct Celula
	{
		uint32_t cod;               /* litera, ca punct Unicode (0x20 = spatiu) */
		uint8_t mozaic;             /* 0 = litera; altfel 0x40 | sextantele (bitul 0 sus-stanga ... bitul 5 jos-dreapta) */
		uint8_t fata;               /* culoarea literei sau a mozaicului, 0..7 (negru, rosu, verde, galben, albastru,
		                               magenta, cyan, alb) */
		uint8_t fundal;             /* culoarea fundalului, 0..7 */
		uint8_t atribute;           /* A_* */
	};

	/* decodari; octetii se dau asa cum vin in PES (primul bit transmis in bitul 7) */
	uint8_t intoarce(uint8_t b);                    /* bitii in ordinea transmisiei: primul in bitul 0 */
	int hamming84(uint8_t intors);                  /* 0..15, -1 = doua erori */
	int hamming2418(const uint8_t *intorsi);        /* trei octeti -> 18 biti, -1 = doua erori */
	int paritate(uint8_t intors);                   /* 7 biti, -1 = paritate gresita */

	/* numerele paginilor: intern magazia (1..8) * 0x100 + numarul hexa din antet (0x00..0xFF); afisabile sunt
	   cele cu ambele cifre zecimale. Pentru om: 100..899. */
	int paginaDinZecimal(int numar);                /* 100..899 -> 0x100..0x899, altfel PAGINA_FARA */
	int zecimalDinPagina(int pagina);               /* 0x100..0x899 cu cifre zecimale -> 100..899, altfel 0 */

	struct Subpagina
	{
		uint16_t subcod;            /* S4 S3 S2 S1 din antet (13 biti) */
		uint16_t control;           /* C4..C14 */
		uint8_t text[RANDURI_PACHETE][COLOANE];     /* octetii intorsi, cu paritatea in bitul 7 */
		uint32_t randuri;           /* randurile primite (bitul 0 = antetul) */
		std::vector<uint32_t> x26;  /* tripletii X/26, la codul de desemnare * 13 + i; 0xFFFFFFFF = lipsa */
		uint32_t x28[2];
		bool are_x28;
		int legaturi[LEGATURI];     /* paginile FastText (intern), PAGINA_FARA = fara */
		bool are_legaturi;
		uint32_t ordine;            /* cand s-a primit ultima oara (pentru memoria marginita) */
		uint32_t versiune;          /* creste la fiecare schimbare */
		Subpagina();
		void stergeCorpul();
	};

	class Colector
	{
	public:
		explicit Colector(size_t max_subpagini = MAX_SUBPAGINI);
		void reseteaza();
		void setMaxSubpagini(size_t n);

		/* un pachet: 2 octeti de adresa si 40 de date, asa cum vin in unitatea de date EBU (dupa line_offset si
		   framing_code); fals = pachet aruncat (adresa sau antet stricat) */
		bool adaugaPachet(const uint8_t *adresa_si_date);

		/* subpagina cu subcodul cerut; subcod < 0 = cea primita cel mai recent; NULL = lipsa */
		const Subpagina *gaseste(int pagina, int subcod) const;
		std::vector<int> subcoduri(int pagina) const;   /* in ordine crescatoare */
		std::vector<int> pagini() const;                /* paginile din memorie (intern), in ordine */
		uint32_t versiunePagina(int pagina) const;      /* suma versiunilor subpaginilor, 0 = lipsa */

		/* ultimul antet al magaziei (coloanele 8..39, intorse) si controlul lui; NULL = niciunul */
		const uint8_t *antetRulant(int magazie, uint16_t *control) const;
		uint32_t versiuneAntet(int magazie) const;
		bool m29(int magazie, uint32_t t[2]) const;

		int paginaInitiala() const;                     /* din 8/30, intern; PAGINA_FARA = nespusa */
		std::string numeServiciu() const;               /* din 8/30 (20 de litere, fara spatiile de la capete) */
		size_t numarSubpagini() const { return m_numar; }
		size_t numarPagini() const { return m_pagini.size(); }
		size_t octeti() const;
		uint32_t versiune() const { return m_versiune; }
		uint32_t pacheteBune() const { return m_bune; }
		uint32_t pacheteRele() const { return m_rele; }

		/* TOP: tipul paginii 100..899 din tabelul de baza (pagina 1F0), -1 fara tabel; 0 = nu se transmite */
		int topTip(int pagina) const;

		/* copia intreaga (subpaginile, M/29, antetele magaziilor, pagina de pornire, numele) ca sir de octeti, fara
		   compresie (o face Python); pid = al serviciului, pus in copie */
		std::string exporta(int pid) const;
		/* din copie; -1 = format gresit (memoria ramane goala), altfel PID-ul din copie */
		int incarca(const uint8_t *date, size_t n);

	private:
		typedef std::map<int, Subpagina> Subpagini;     /* dupa subcod */
		std::map<int, Subpagini> m_pagini;              /* dupa pagina (intern) */
		size_t m_max;
		size_t m_numar;
		uint32_t m_ceas;
		uint32_t m_versiune;
		uint32_t m_bune, m_rele;
		int m_curenta[9];                               /* pagina primita acum, pe magazie (1..8) */
		int m_subcod_curent[9];
		uint8_t m_antet[9][32];
		uint16_t m_antet_control[9];
		bool m_are_antet[9];
		uint32_t m_antet_versiune[9];
		uint32_t m_m29[9][2];
		bool m_are_m29[9];
		int m_initiala;
		uint8_t m_nume[20];
		bool m_are_nume;

		Subpagina *curenta(int magazie);
		void inchide(int magazie);
		void faLoc();
	};

	/* randarea unei subpagini (sau numai a antetului, cand sp e NULL) in celule.
	   stare: cel mult 8 litere ASCII pentru coloanele 0-7 ale antetului (numarul paginii, cifrele tastate);
	   antet: ultimul antet al magaziei (din antetRulant): ceasul (coloanele 32-39) vine de acolo, iar fara pagina tot
	   antetul. */
	void randeaza(const Colector &col, const Subpagina *sp, int pagina, const char *stare, const uint8_t *antet,
		uint16_t antet_control, Celula iesire[RANDURI][COLOANE]);

	/* legaturile FastText ale subpaginii, ca numere zecimale (0 = fara) */
	void legaturiZecimale(const Subpagina &sp, int iesire[LEGATURI]);

	/* compunerea in pixeli */
	class Glife
	{
	public:
		virtual ~Glife() {}
		/* acoperirea literei `cod` intr-un dreptunghi latime x inaltime (o celula, sau dublu pe o directie), randuri
		   de cate `latime` octeti, 0..255; NULL = nimic de desenat */
		virtual const uint8_t *acoperire(uint32_t cod, int latime, int inaltime) = 0;
	};

	struct Aspect
	{
		int l, i;                   /* latimea si inaltimea unei celule, in pixeli */
		bool peste;                 /* peste imagine: fundalul negru transparent, celelalte pe jumatate */
		bool hd;                    /* teletextul neted (numele intern a ramas hd): fundalurile si mozaicul legat netezite
		                               pe toata grila de sextante (laturi drepte, scarile ca linii oblice, colturile reale
		                               rotunjite; vezi hdsteletext.cpp, stratul HD), blocurile separate rotunjite */
		bool cu_contur;             /* conturul negru, numai in jurul a ce e deschis la culoare (luminanta de cel putin
		                               PRAG_DESCHIS): pe tot ecranul literele, peste imagine si formele; oprit din fabrica */
		bool cu_umbra;              /* umbra moale a literelor (jos-dreapta); oprita din fabrica */
		bool relief;                /* numai la neted: formele (mozaicul, casetele colorate; nu literele) cu o fata
		                               laterala spre dreapta-jos, ca niste forme in relief; oprit din fabrica */
		int contur;                 /* grosimea conturului peste imagine, pixeli (0 = fara); pe tot ecranul 1 */
		uint8_t alfa_fundal;        /* opacitatea fundalurilor colorate peste imagine */
		bool stinge_intermitente;   /* faza in care literele intermitente nu se vad */
		bool arata_ascuns;
		Aspect();
	};

	/* luminanta relativa (Rec. 709, x 256: 54 r + 183 g + 19 b) de la care o culoare e "deschisa" si primeste contur:
	   alb, galben, cyan, verde da; magenta, rosu, albastru, negru nu */
	enum { PRAG_DESCHIS = 128 };
	inline int luminanta(uint32_t rgb)
	{
		return (int)((54u * ((rgb >> 16) & 0xFF) + 183u * ((rgb >> 8) & 0xFF) + 19u * (rgb & 0xFF) + 128u) >> 8);
	}

	/* culoarea teletext 0..7 ca 0xRRGGBB */
	uint32_t culoare(int index);

	/* randurile [rand0, rand1) ale paginii, in poza de 40*l x (rand1-rand0)*i pixeli, cu `pas` uint32 pe rand;
	   intoarce 1 daca pe randuri sunt celule intermitente */
	int compune(const Celula pagina[RANDURI][COLOANE], int rand0, int rand1, const Aspect &a, Glife &glife,
		uint32_t *pixeli, int pas);

	/* faza stinsa a corpului (randurile 1-24, a.stinge_intermitente) din faza aprinsa deja compusa (`aprinsa`, aceeasi
	   marime si acelasi `pas`): se copiaza, apoi se recompun numai benzile de randuri cu celule intermitente (cu un rand
	   de margine, pentru umbra si contur); iese la fel ca o compunere intreaga. false = nu s-a scris nimic, trebuie
	   compusa intreaga (mozaic intermitent: in HD schimba formele netezite si dincolo de randul lui) */
	bool compuneStinsa(const Celula pagina[RANDURI][COLOANE], const Aspect &a, Glife &glife, const uint32_t *aprinsa,
		uint32_t *stinsa, int pas);
}
#endif

#ifndef HDS_TELETEXT_FARA_PYTHON
/* Pentru Python (SWIG) si pentru parser: paginile serviciului care merge, o singura memorie pentru tot procesul.
   Parserul serviciului primar (lib/dvb/teletext.cpp) o porneste si ii da pachetele; ecranul, widgetul si pagina web
   citesc din ea. Totul pe firul principal. Numerele paginilor, pentru Python: 100..899. */
class eHdsTeletext
{
#ifdef SWIG
	eHdsTeletext();
	~eHdsTeletext();
#endif
public:
	static eHdsTeletext *getInstance();
	/* o copie incarcata din fisier, fara tuner: locul 0 pentru televizor, 1 pentru pagina web */
	static eHdsTeletext *copie(int loc);
	/* copia paginilor de acum (bytes, necomprimat; Components/HdsTeletextCopie.py o comprima) */
	PyObject *exporta();
	/* incarca o copie (bytes necomprimat) in locul ei: PID-ul din copie, -1 = copie stricata */
	int incarca(PyObject *date);
	/* (pid, pagini, subpagini, octeti, versiune, pachete bune, pachete rele); pid -1 = niciun serviciu cu teletext */
	PyObject *stare();
	/* paginile afisabile din memorie, 100..899, crescator */
	PyObject *pagini();
	/* subcodurile paginii, crescator */
	PyObject *subpagini(int pagina);
	/* contorul paginii (0 = nu e in memorie): se schimba la fiecare pachet primit pentru ea */
	int versiune(int pagina);
	/* pagina randata: None daca lipseste, altfel (pagina, subcod, versiune, celule); subcod -1 = cea primita cel mai
	   recent; celule = 1000 x 8 octeti: cod (uint32, little endian), mozaic, culoarea, fundalul, atributele. Cu
	   pagina lipsa: aratAntet = 1 da totusi (pagina, -1, 0, celule) cu antetul magaziei si randurile goale. */
	PyObject *pagina(int pagina, int subcod, const char *stare, int aratAntet);
	/* legaturile FastText ale subpaginii: lista de 6 numere (0 = fara), sau None */
	PyObject *legaturi(int pagina, int subcod);
	/* tabelul TOP: bytes de 800 (tipul paginilor 100..899) sau None */
	PyObject *top();
	int paginaInitiala();
	std::string numeServiciu();
	int pid() { return m_pid; }
#ifndef SWIG
	eHdsTeletext();
	hdsttx::Colector &colector() { return m_colector; }
	/* parserul serviciului primar: start(pid), pachetele, distrugerea */
	void porneste(const void *proprietar, int pid);
	void opreste(const void *proprietar);
	void adauga(const void *proprietar, const uint8_t *adresa_si_date);
private:
	hdsttx::Colector m_colector;
	const void *m_proprietar;
	int m_pid;
	eHdsTeletext(const eHdsTeletext &);
	eHdsTeletext &operator=(const eHdsTeletext &);
#endif
};
#endif

#endif
