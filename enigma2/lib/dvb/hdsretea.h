/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsretea.h: ce spune tabela retelei (NIT actual, table_id 0x40, ETSI EN 300 468 cap. 5.2.1) citita la o scanare de
 * servicii: ID-ul retelei (network_id), numele ei (network_name_descriptor 0x40), multiplexurile anuntate (TSID, ONID si
 * descriptorul de livrare: cablu 0x44, satelit 0x43, terestru 0x5A), numerele logice ale canalelor (LCN) si descriptorii
 * privati pe care imaginea nu ii stie, cu private_data_specifier-ul (0x5F) sub care stau.
 *
 * Numai citire si numai pentru /api/scanare-ultima (lib/dvb/scan.cpp il umple din NIT-urile pe care scanarea le citeste:
 * la cautarea in retea si, numai pentru informatie, la cablu pe o frecventa; vezi asteaptaNit mai jos): nimic de aici
 * nu ajunge in lista de canale. Fara enigma2, numai libdvbsi++ si std, ca probele de pe PC sa-l compileze singur.
 *
 * Numerele logice (descriptori ai operatorilor, nu din EN 300 468):
 *  - 0x83 logical_channel_descriptor (IEC 62216-1, E-book EACEM): service_id 16, visible_service_flag 1, rezervat 5,
 *    numarul 10 biti. Cu PDS 0x00000029 (NorDig, versiunea 1): rezervat 1, numarul 14 biti;
 *  - 0x88 HD simulcast logical channel (aceeasi forma ca 0x83, 10 biti): numarul canalului HD pe receptoarele HD;
 *  - 0x87 NorDig versiunea 2 (PDS 0x29 sau fara PDS): liste de canale (channel_list_id, nume, tara), fiecare cu
 *    service_id 16, visible 1, rezervat 5, numarul 10 biti;
 *  - 0x86 numai sub PDS 0x000001A0 (reteaua de cablu Digi din Romania, citita de pe receptor): perechi de cate 4
 *    octeti, service_id 16 si numarul pe 16 biti, din care se folosesc numai cei 10 de jos (cei 6 de sus sunt 0 in
 *    tabela citita: televiziunea 1..252, radioul de la 1001). Nu are semn de vizibilitate (vizibil = -1). Un descriptor
 *    cu vreunul din cei 6 biti de sus pus nu se ghiceste: ramane brut intreg. Sub alt PDS, 0x86 inseamna altceva: brut.
 * Orice alt descriptor privat (tag 0x80-0xFE) din cele doua bucle se pastreaza brut (octetii lui), pana la un plafon,
 * ca prima scanare intr-o retea noua sa arate ce trimite operatorul.
 * PDS-ul: cel din bucla multiplexului, valabil pentru descriptorii de dupa el; fara el, cel din bucla retelei.
 *
 * Paza: plafoane pe retele, multiplexuri, numere si octetii bruti, ca o tabela stricata sau uriasa (o cautare in retea
 * pe un satelit intreg citeste multe NIT-uri) sa nu umple memoria. Un descriptor LCN cu lungimea gresita se pastreaza
 * brut, nu se citeste pe jumatate.
 */

#ifndef __lib_dvb_hdsretea_h
#define __lib_dvb_hdsretea_h

#include <stdint.h>
#include <stddef.h>
#include <set>
#include <string>
#include <vector>

#ifndef SWIG
class NetworkInformationSection;

namespace hdsretea
{
	enum
	{
		/* felul livrarii, aceleasi valori ca iDVBFrontend::feSatellite / feCable / feTerrestrial */
		SISTEM_SATELIT = 0,
		SISTEM_CABLU = 1,
		SISTEM_TERESTRU = 2,
		/* descriptorii */
		TAG_NUME_RETEA = 0x40,
		TAG_LIVRARE_SATELIT = 0x43,
		TAG_LIVRARE_CABLU = 0x44,
		TAG_LIVRARE_TERESTRU = 0x5A,
		TAG_PDS = 0x5F,
		TAG_LCN = 0x83,
		TAG_LCN_NORDIG_V2 = 0x87,
		TAG_LCN_HD = 0x88,
		TAG_LCN_1A0 = 0x86,            /* numai sub PDS_1A0 */
		PDS_NORDIG = 0x00000029,
		PDS_1A0 = 0x000001A0,
		/* plafoane */
		MAX_RETELE = 64,
		MAX_MUXURI = 1024,
		MAX_LCN = 4096,
		MAX_OCTETI_BRUTI = 16384,      /* pe toata scanarea, numai octetii descriptorilor privati */
		MAX_NUME = 255,
		/* steagurile scanarii care privesc NIT-ul, aceleasi valori ca eDVBScan::scanNetworkSearch si
		   eDVBScan::hdsNitInformativ (lib/dvb/scan.cpp verifica la compilare) */
		STEAG_CAUTARE_IN_RETEA = 1,
		STEAG_NIT_INFORMATIV = 128,
	};

	/* NIT-ul se asteapta pe fiecare transponder acordat la cautarea in retea si la NIT-ul numai pentru informatie
	   (cablu pe o frecventa). Asteptarea are plafonul tabelei (NetworkInformationSection::TIMEOUT, 12 s): fara NIT,
	   transponderul se termina dupa plafon cu serviciile lui, ca orice transponder acordat. */
	inline bool asteaptaNit(int steaguri)
	{
		return (steaguri & (STEAG_CAUTARE_IN_RETEA | STEAG_NIT_INFORMATIV)) != 0;
	}

	/* Frecventele anuntate in NIT intra in scanare numai la cautarea in retea; la NIT-ul numai pentru informatie
	   reteaua merge doar in Colector si se scaneaza tot numai frecventa aleasa. Cu amandoua steagurile: cautare. */
	inline bool adaugaFrecventeleDinNit(int steaguri)
	{
		return (steaguri & STEAG_CAUTARE_IN_RETEA) != 0;
	}

	struct Mux
	{
		unsigned tsid, onid;
		int sistem;                  /* SISTEM_* */
		unsigned f_khz;
		int sr;                      /* mii de simboluri pe secunda; -1 la terestru */
		int mod;                     /* cablu: codul din descriptor (1 = QAM16 ... 5 = QAM256, 0 nedefinit);
		                                satelit: 0 auto, 1 QPSK, 2 8PSK, 3 16QAM; -1 la terestru */
		int fec;                     /* FEC_inner din descriptor (cablu si satelit), -1 la terestru */
		int poz;                     /* satelit: pozitia orbitala ca in enigma2 (192 = 19,2 E, 3550 = 5 V); -1 altfel */
		int pol;                     /* satelit: 0 H, 1 V, 2 L, 3 R; -1 altfel */
		int s2;                      /* satelit: 1 DVB-S2, 0 DVB-S; -1 altfel */
	};

	struct Lcn
	{
		unsigned tsid, onid, sid;
		unsigned numar;
		int vizibil;                 /* 1 vizibil, 0 ascuns, -1 descriptorul nu are semnul (0x86) */
		unsigned tag;                /* TAG_LCN, TAG_LCN_HD, TAG_LCN_NORDIG_V2, TAG_LCN_1A0 */
		uint32_t pds;                /* PDS-ul sub care sta descriptorul, 0 = niciunul */
		int lista;                   /* 0x87: channel_list_id; -1 la celelalte */
	};

	struct Brut
	{
		int tsid, onid;              /* -1, -1 = bucla retelei */
		unsigned tag;
		uint32_t pds;
		std::vector<uint8_t> octeti; /* corpul descriptorului, fara tag si lungime */
	};

	struct Retea
	{
		unsigned nid;
		std::string nume;            /* octetii din network_name_descriptor, neconvertiti (prima valoare nevida) */
		std::set<uint32_t> pds;      /* toate PDS-urile vazute in tabela */
		std::vector<Mux> muxuri;
		std::vector<Lcn> lcn;
		std::vector<Brut> privati;
		bool trunchiat;              /* s-au lasat descriptori bruti sau numere peste plafon */
	};

	/* Numerele dintr-un descriptor LCN (0x83, 0x88, 0x87, 0x86 sub PDS_1A0), corpul fara tag si lungime. Intoarce
	   false cand forma nu se potriveste (lungimea gresita, alt tag, alt PDS la 0x87 si 0x86, bitii de sus pusi la
	   0x86): atunci descriptorul se pastreaza brut si nu se ia niciun numar din el. */
	bool citesteLcn(unsigned tag, uint32_t pds, const uint8_t *corp, size_t lungime, unsigned tsid, unsigned onid,
		std::vector<Lcn> &iesire);

	class Colector
	{
	public:
		Colector();
		void goleste();
		/* o sectiune NIT actual; intoarce network_id-ul ei */
		unsigned adaugaSectiune(const NetworkInformationSection &nit);
		const std::vector<Retea> &retele() const { return m_retele; }
	private:
		Retea *retea(unsigned nid);
		void pastreazaBrut(Retea &r, int tsid, int onid, unsigned tag, uint32_t pds, const uint8_t *corp, size_t lungime);
		std::vector<Retea> m_retele;
		std::set<uint64_t> m_sectiuni;  /* sectiunile luate deja (nid, numar, versiune, CRC) */
		size_t m_octeti_bruti;
	};
}
#endif

#endif
