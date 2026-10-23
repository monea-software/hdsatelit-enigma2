/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsait.h: tabela aplicatiilor (AIT, table_id 0x74, ETSI TS 102 809 cap. 5.3) citita pentru HbbTV (ETSI TS 102 796):
 * aplicatiile cu organizatia, id-ul, codul de control, numele, transporturile (HTTP si caruselul de obiecte), calea de
 * pornire, profilul cu versiunea, vizibilitatea si prioritatea.
 *
 * Scris de la zero, fara clasele AIT din libdvbsi++ (acolo vizibilitatea se citeste cu masca 0x02 in loc de 0x03, iar
 * transportul HTTP stricat poate duce citirea in afara tamponului). Numai functii pure, fara enigma2: lib/dvb/pmt.cpp
 * le foloseste pentru canalul redat, iar probele de pe PC le compileaza singure (aceleasi reguli ca
 * Components/HdsAnalizaFlux.citeste_ait, care citeste aceleasi sectiuni in Python).
 *
 * Paza: fiecare lungime se verifica fata de capatul buclei ei. O bucla care trece de capat (descriptorii comuni, bucla
 * aplicatiilor, descriptorii unei aplicatii, un descriptor) strica sectiunea intreaga: nicio aplicatie din ea. Un camp
 * gresit inauntrul unui descriptor strica numai descriptorul acela (sau, la nume si la adrese, restul lui).
 */

#ifndef __lib_dvb_hdsait_h
#define __lib_dvb_hdsait_h

#include <stdint.h>
#include <stddef.h>
#include <string>
#include <utility>
#include <vector>

#ifndef SWIG
namespace hdsait
{
	enum
	{
		TID = 0x74,
		TIP_HBBTV = 0x0010,
		/* application_control_code (TS 102 809, tabelul 4; HbbTV: TS 102 796 cap. 7.2.3.1) */
		COD_AUTOSTART = 0x01,
		COD_PRESENT = 0x02,
		COD_DESTROY = 0x03,
		COD_KILL = 0x04,
		COD_DISABLED = 0x07,
		/* protocol_id din transport_protocol_descriptor (TS 102 809 tabelul 18) */
		PROTOCOL_CARUSEL = 0x0001,
		PROTOCOL_IP = 0x0002,
		PROTOCOL_HTTP = 0x0003,
		/* marginile unei sectiuni citite (o sectiune AIT are cel mult 1024 de octeti) */
		MAX_SECTIUNE = 4096,
		MAX_APLICATII = 64,
		MAX_TRANSPORTURI = 8,
		MAX_ADRESE = 4,
		MAX_EXTENSII = 8,
		MAX_PROFILE = 8,
		MAX_ETICHETE = 16,
		MAX_LIMITE = 8,
		MAX_VARSTE = 8,
	};

	enum
	{
		BUN = 0,
		E_SCURTA = -1,      /* mai putin de 16 octeti sau lungimea din antet trece de date */
		E_ANTET = -2,       /* alt table_id, fara section_syntax_indicator sau current_next_indicator = 0 */
		E_CRC = -3,
		E_STRUCTURA = -4,   /* o bucla sau un descriptor trece de capatul lui */
	};

	struct Profil
	{
		unsigned profil, major, minor, micro;
	};

	struct Transport
	{
		unsigned protocol;                  /* PROTOCOL_CARUSEL, PROTOCOL_HTTP, altul pastrat fara selector */
		unsigned eticheta;                  /* transport_protocol_label */
		int la_distanta;                    /* carusel: 1 = pe alt serviciu (onid, tsid, sid de mai jos) */
		unsigned onid, tsid, sid;
		int tag;                            /* carusel: component_tag; -1 la celelalte */
		std::vector<std::string> adrese;    /* HTTP: URL_base, in ordinea din descriptor */
		std::vector<std::string> extensii;  /* HTTP: URL_extension ale primei adrese */
	};

	struct Aplicatie
	{
		uint32_t org;
		unsigned id;
		unsigned cod;                       /* application_control_code */
		int prioritate;                     /* din application_descriptor; -1 fara el */
		int vizibilitate;                   /* 0..3; -1 fara application_descriptor */
		int legat;                          /* service_bound_flag; -1 fara application_descriptor */
		std::vector<Profil> profile;
		std::vector<unsigned> etichete;     /* transport_protocol_label, in ordinea de preferinta */
		std::string nume, limba;            /* primul nume: octetii DVB (cu prefixul de codare), limba ISO 639 */
		std::vector<Transport> transporturi;/* dupa etichete; fara etichete, ale aplicatiei sau, fara ele, cele comune */
		std::string cale;                   /* simple_application_location_descriptor (0x15) */
		int utilizare;                      /* application_usage_descriptor (0x16); -1 fara el */
		std::vector<std::string> limite;    /* simple_application_boundary_descriptor (0x17) */
		std::vector<std::pair<std::string, unsigned> > varste;  /* parental_rating_descriptor (0x55): tara, nota */
	};

	struct Sectiune
	{
		unsigned tip;                       /* application_type */
		int test;                           /* test_application_flag */
		unsigned versiune, numar, ultima;
		std::vector<Aplicatie> aplicatii;
	};

	/* CRC-32/MPEG-2 (polinomul 0x04C11DB7, pornit din 0xFFFFFFFF); peste o sectiune intreaga, cu CRC-ul ei, da 0 */
	uint32_t crc32(const uint8_t *date, size_t n);
	/* 3 + section_length, sau 0 cand n < 3 */
	size_t lungime(const uint8_t *date, size_t n);
	/* o sectiune AIT (cel putin `lungime` octeti in date) -> BUN si s completat, sau o eroare (s gol) */
	int citeste(const uint8_t *date, size_t n, Sectiune &s);
}

/* O sectiune pentru eTable (lib/dvb/esection.h): constructorul primeste tamponul lui eDVBSectionReader (MAX_SECTIUNE
   octeti) si citeste sectiunea pe loc. */
class eHdsAitSection
{
	hdsait::Sectiune m_sectiune;
	int m_eroare;
public:
	eHdsAitSection(const uint8_t *date);
	int eroare() const { return m_eroare; }
	const hdsait::Sectiune &sectiune() const { return m_sectiune; }
};
#endif

#endif
