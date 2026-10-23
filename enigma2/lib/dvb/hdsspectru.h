/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsspectru.h: nivelul sunetului pe benzi de frecventa, din cadrele comprimate ale unui post (AAC, HE-AAC, AC-3,
 * E-AC-3, DTS, PCM SMPTE 302M), pentru barele ecranului radio (lib/python/Components/HdsRadioAnaliza.py).
 *
 * Nu se decodeaza sunetul: se citesc numai datele din care iese nivelul fiecarei benzi (liniile spectrale AAC si
 * anvelopa SBR, liniile AC-3 / E-AC-3, factorii de scala DTS, esantioanele PCM) si se aduna pe 32 de benzi egale de
 * fs/64 (750 Hz la 48 kHz), ca subbenzile MPEG Layer II. Rezultatul e pe scara factorilor de scala MPEG (indicele
 * 0..62, 2 dB pe treapta, 63 = nimic in banda), deci desenul si pagina web il folosesc la fel pe orice format.
 *
 * Sunetul auzit nu se atinge: cadrele vin dintr-un filtru separat al demultiplexorului, citit de firul analizorului.
 * Merge si cand iesirea e pe trecere spre bara de sunet (AC-3 / DTS neschimbat), fiindca fluxul e acelasi.
 *
 * Tot de aici, pentru textul radio al posturilor AAC (lib/dvb/radiotext.cpp): octetii elementelor DSE ai unui cadru
 * AAC, citit element cu element (fara nivele), ca sa se ajunga la elementele de dupa sunet.
 *
 * Paza: fiecare citire de biti e marginita de lungimea cadrului (cadrul se copiaza intr-un tampon cu zerouri dupa el),
 * toate tablourile au marimi fixe, iar orice valoare din afara standardului opreste numai cadrul acela.
 */

#ifndef __lib_dvb_hdsspectru_h
#define __lib_dvb_hdsspectru_h

#include <stdint.h>
#include <stddef.h>

#ifndef SWIG
namespace hdsspectru
{
	enum
	{
		FEL_ADTS = 1,       /* AAC in ADTS */
		FEL_LATM = 2,       /* AAC in LATM / LOAS (cadrul LOAS intreg, cu antetul de 3 octeti) */
		FEL_AC3 = 3,
		FEL_EAC3 = 4,
		FEL_DTS = 5,        /* nucleul DTS (fara extensiile DTS-HD) */
		FEL_S302M = 6,      /* PCM SMPTE 302M: antetul AES3 de 4 octeti si esantioanele unui pachet PES */
	};
	enum { BENZI = 32, GOL = 63 };

	struct Info
	{
		int esantionare;    /* a sunetului auzit (cu SBR: dublul nucleului AAC) */
		int canale;         /* cate canale are fluxul (fara LFE) */
		int lfe;            /* 1 cu canal LFE */
		int profil;         /* AAC: tipul obiectului (2 = LC); AC-3 / E-AC-3: bsid; DTS: 0 */
		int sbr;            /* AAC: 1 cand fluxul are date SBR (HE-AAC) */
		int ps;             /* AAC: 1 cu stereo parametric (HE-AAC v2) */
		int biti;           /* PCM: bitii pe esantion */
	};

	class Nucleu;
	Nucleu *creeaza();
	void distruge(Nucleu *n);
	void reseteaza(Nucleu *n);
	/* un cadru intreg -> 1 si nivelul pe benzi in niv[2][BENZI] (niv[1] = niv[0] la mono), 0 fara rezultat (cadru care
	   nu se poate citi pana la capat); *mono = 1 cand fluxul are un singur canal */
	int cadru(Nucleu *n, int fel, const uint8_t *date, size_t lungime, uint8_t niv[2][BENZI], int *mono);
	void info(const Nucleu *n, Info *i);
	/* cadre citite bine / cadre refuzate de la pornire */
	void contoare(const Nucleu *n, unsigned *bune, unsigned *rele);

	/* Textul radio al posturilor AAC: octetii elementelor DSE (data_stream_element) ai unui cadru AAC intreg (FEL_ADTS
	   sau FEL_LATM), legati in ordinea lor; lib/dvb/radiotext.cpp ii da decodorului UECP. Cadrul se citeste element cu
	   element, fara nivelele benzilor. Un cititor pe flux (configuratia LATM ramane de la un cadru la altul).
	   dse() -> octetii scrisi in iesire (cel mult max), 0 fara DSE, -1 cadru care nu se poate citi. */
	class CititorDse;
	CititorDse *creeazaDse();
	void distrugeDse(CititorDse *c);
	int dse(CititorDse *c, int fel, const uint8_t *date, size_t lungime, uint8_t *iesire, size_t max);
	/* lungimea cadrului AAC de felul `fel` de la inceputul datelor (ADTS: din antet; LATM: 3 + lungimea LOAS), 0 cand
	   datele nu incep cu un astfel de cadru sau nu ajung pentru antet */
	size_t lungimeAac(int fel, const uint8_t *date, size_t n);
	enum { DSE_CADRU_MAX = 8194 };       /* cel mai lung cadru AAC: 3 + 8191 (LATM), 8191 (ADTS) */
}
#endif

#ifndef HDS_SPECTRU_FARA_PYTHON
/* Pentru Python (SWIG): un obiect pe flux, folosit de un singur fir (al analizorului). */
class eHdsSpectru
{
public:
	eHdsSpectru();
	~eHdsSpectru();
	void reset();
	/* fel: 1 ADTS, 2 LATM, 3 AC-3, 4 E-AC-3, 5 DTS, 6 PCM 302M; date: bytes cu un cadru intreg.
	   -> (f0, f1) cu cate 32 de indici (f1 None la mono), sau None. Calculul se face fara GIL. */
	PyObject *cadru(int fel, PyObject *date);
	/* -> dictionar: esantionare, canale, lfe, profil, sbr, ps, biti, bune, rele */
	PyObject *info();
#ifndef SWIG
private:
	hdsspectru::Nucleu *m_nucleu;
	eHdsSpectru(const eHdsSpectru &);
	eHdsSpectru &operator=(const eHdsSpectru &);
#endif
};
#endif

#endif
