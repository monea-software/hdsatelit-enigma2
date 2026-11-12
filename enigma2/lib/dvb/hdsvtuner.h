/*
 * hdsvtuner.h: partile fara enigma2 ale puntii vtuner (tunerele DVB pe USB, lib/dvb/hdsvtuner.cpp).
 *
 * Puntea: un tuner DVB pe USB (Vu+ Turbo, stickurile DVB-T2/C) face /dev/dvb/adapterN (N >= 1), dar decodorul
 * receptorului citeste numai demuxurile placii (adapter0). Driverul vtuner al placii (Vu+: dvb-proxy, /dev/misc/vtunerN;
 * HiSilicon: vtunerc) face un frontend virtual pe adapter0; enigma2 acordeaza tunerul USB adevarat si muta fluxul TS
 * din demuxul stickului in vtuner, iar placa il vede ca pe al ei.
 *
 * Dupa enigma2 OE-Alliance, lib/dvb/dvb.cpp (eDVBUsbAdapter, GPL-2.0, autorii enigma2).
 * Modificat de moneasoftware.com si hdsatelit.com, 2026.
 *
 * Totul de aici foloseste numai biblioteca standard si apelurile de sistem, cu radacina fisierelor data ca parametru:
 * se compileaza si se probeaza singur pe PC (receptor/imagine-hdsatelit/teste/proba_vtuner_punte.py).
 */
#ifndef __lib_dvb_hdsvtuner_h
#define __lib_dvb_hdsvtuner_h

#include <string>
#include <vector>
#include <cstdio>
#include <cstring>
#include <cerrno>
#include <unistd.h>
#include <limits.h>
#include <sys/stat.h>

namespace hdsvtuner
{
	/* lista cu frontend-urile USB legate, citita de Components/NimManager.py (numele in Setari tunere) si de uneltele
	   care deschid frontend-ul direct: un rand pe tuner, "<frontend virtual pe adapter0>\t<frontend USB>\t<nume>\t<sisteme>" */
	static const char *const LISTA = "/tmp/hds_tunere_usb";

	enum { PIDURI = 30 };      /* cate PID-uri trimite driverul vtuner intr-un mesaj MSG_PIDLIST */
	static const unsigned short FARA_PID = 0xffff;

	struct Legatura
	{
		int virtual_fe;        /* frontend-ul virtual de pe adapter0 (slotul tunerului) */
		std::string usb;       /* /dev/dvb/adapterN/frontend0 */
		std::string nume;      /* numele stickului */
		std::string sisteme;   /* "DVB-C,DVB-T,DVB-T2" */
	};

	inline bool existaCale(const std::string &cale)
	{
		struct stat s;
		return ::stat(cale.c_str(), &s) == 0;
	}

	inline std::string citesteLegatura(const std::string &cale)
	{
		char tinta[PATH_MAX];
		ssize_t n = ::readlink(cale.c_str(), tinta, sizeof(tinta) - 1);
		if (n < 0)
			return "";
		tinta[n] = 0;
		return tinta;
	}

	/* adaptorul N e pe USB: dispozitivul frontend-ului lui are capatul ep_00 (dvb-usb) sau subsistemul lui e usb.
	   rad = "" pe receptor, un dosar de proba pe PC */
	inline bool esteUsb(const std::string &rad, int adaptor)
	{
		char cale[160];
		snprintf(cale, sizeof(cale), "/sys/class/dvb/dvb%d.frontend0/device/ep_00", adaptor);
		if (existaCale(rad + cale))
			return true;
		snprintf(cale, sizeof(cale), "/sys/class/dvb/dvb%d.frontend0/device/subsystem", adaptor);
		return citesteLegatura(rad + cale).find("/usb") != std::string::npos;
	}

	/* frontend-ul exista: nodul din /dev sau intrarea din /sys (un frontend virtual tocmai facut de vtuner poate sa nu
	   aiba inca nodul /dev; receptorul virtual de pe PC are numai nodurile, fara /sys) */
	inline bool frontendExista(const std::string &rad, int adaptor, int fe)
	{
		char cale[128];
		snprintf(cale, sizeof(cale), "/dev/dvb/adapter%d/frontend%d", adaptor, fe);
		if (existaCale(rad + cale))
			return true;
		snprintf(cale, sizeof(cale), "/sys/class/dvb/dvb%d.frontend%d", adaptor, fe);
		return existaCale(rad + cale);
	}

	/* cate frontend-uri are adaptorul (primul indice care lipseste) */
	inline int numaraFrontenduri(const std::string &rad, int adaptor)
	{
		int n = 0;
		while (n < 64 && frontendExista(rad, adaptor, n))
			++n;
		return n;
	}

	/* numele dat de stick: fara spatii si randuri noi la coada; gol daca nu are nimic */
	inline std::string curataNume(const char *text)
	{
		std::string s = text ? text : "";
		while (!s.empty() && strchr(" \n\r\t", s[s.size() - 1]))
			s.erase(s.size() - 1);
		size_t i = 0;
		while (i < s.size() && strchr(" \n\r\t", s[i]))
			++i;
		return s.substr(i);
	}

	/* tipul spus driverului vtuner (VTUNER_SET_TYPE), dupa fe_type din FE_GET_INFO (0 QPSK, 1 QAM, 2 OFDM, 3 ATSC);
	   NULL = tip pe care puntea nu-l suporta */
	inline const char *tipVtuner(int fe_type, bool poate2g)
	{
		switch (fe_type)
		{
		case 0: return "DVB-S2";
		case 1: return "DVB-C";
		case 2: return poate2g ? "DVB-T2" : "DVB-T";
		case 3: return "ATSC";
		default: return 0;
		}
	}

	/* sistemele de livrare (DTV_ENUM_DELSYS, numerele din linux/dvb/frontend.h) ca text pentru lista; fara dubluri */
	inline std::string textSisteme(const unsigned char *delsys, int n, const char *tip)
	{
		std::vector<std::string> nume;
		for (int i = 0; i < n; ++i)
		{
			const char *t = 0;
			switch (delsys[i])
			{
			case 1: case 2: t = "DVB-C"; break;            /* SYS_DVBC_ANNEX_A, SYS_DVBC_ANNEX_B */
			case 18: t = "DVB-C"; break;                   /* SYS_DVBC_ANNEX_C */
			case 3: t = "DVB-T"; break;                    /* SYS_DVBT */
			case 16: t = "DVB-T2"; break;                  /* SYS_DVBT2 */
			case 5: t = "DVB-S"; break;                    /* SYS_DVBS */
			case 6: t = "DVB-S2"; break;                   /* SYS_DVBS2 */
			case 11: t = "ATSC"; break;                    /* SYS_ATSC */
			default: break;
			}
			if (!t)
				continue;
			bool are = false;
			for (size_t k = 0; k < nume.size(); ++k)
				are = are || nume[k] == t;
			if (!are)
				nume.push_back(t);
		}
		if (nume.empty() && tip)
			nume.push_back(tip);
		std::string rez;
		for (size_t k = 0; k < nume.size(); ++k)
			rez += (k ? "," : "") + nume[k];
		return rez;
	}

	inline bool inLista(const unsigned short *lista, unsigned short pid)
	{
		for (int i = 0; i < PIDURI; ++i)
			if (lista[i] == pid)
				return true;
		return false;
	}

	/* ce se scoate si ce se pune pe demuxul stickului cand vtuner trimite lista noua de PID-uri */
	inline void schimbariPid(const unsigned short *vechi, const unsigned short *noi,
		std::vector<unsigned short> &scoase, std::vector<unsigned short> &puse)
	{
		scoase.clear();
		puse.clear();
		for (int i = 0; i < PIDURI; ++i)
			if (vechi[i] != FARA_PID && !inLista(noi, vechi[i]))
			{
				bool dublu = false;
				for (size_t k = 0; k < scoase.size(); ++k)
					dublu = dublu || scoase[k] == vechi[i];
				if (!dublu)
					scoase.push_back(vechi[i]);
			}
		for (int i = 0; i < PIDURI; ++i)
			if (noi[i] != FARA_PID && !inLista(vechi, noi[i]))
			{
				bool dublu = false;
				for (size_t k = 0; k < puse.size(); ++k)
					dublu = dublu || puse[k] == noi[i];
				if (!dublu)
					puse.push_back(noi[i]);
			}
	}

	/* fara tabulatori si randuri noi in campuri (lista e pe randuri, despartita cu tab) */
	inline std::string campCurat(const std::string &s)
	{
		std::string r = s;
		for (size_t i = 0; i < r.size(); ++i)
			if (r[i] == '\t' || r[i] == '\n' || r[i] == '\r')
				r[i] = ' ';
		return r;
	}

	/* scrie lista (prin fisier nou + rename, ca cititorul sa nu vada niciodata o lista pe jumatate); fara legaturi
	   sterge lista ramasa de la pornirea de dinainte. 0 = bine */
	inline int scrieLista(const std::string &cale, const std::vector<Legatura> &legaturi)
	{
		if (legaturi.empty())
		{
			if (::unlink(cale.c_str()) < 0 && errno != ENOENT)
				return -1;
			return 0;
		}
		std::string nou = cale + ".nou";
		FILE *f = fopen(nou.c_str(), "w");
		if (!f)
			return -1;
		for (size_t i = 0; i < legaturi.size(); ++i)
			fprintf(f, "%d\t%s\t%s\t%s\n", legaturi[i].virtual_fe, campCurat(legaturi[i].usb).c_str(),
				campCurat(legaturi[i].nume).c_str(), campCurat(legaturi[i].sisteme).c_str());
		bool bine = !ferror(f);
		bine = fclose(f) == 0 && bine;
		if (!bine || ::rename(nou.c_str(), cale.c_str()) < 0)
		{
			::unlink(nou.c_str());
			return -1;
		}
		return 0;
	}
}

#endif
