// hds-ocr - serviciul local de recunoastere a textului din subtitrarile DVB (imaginea HDSatelit)
//
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Monea Software pentru HD Satelit
//
// Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
// associated documentation files (the "Software"), to deal in the Software without restriction,
// including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense,
// and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so,
// subject to the following conditions: The above copyright notice and this permission notice shall be
// included in all copies or substantial portions of the Software.
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED.
//
// Proces separat de enigma2 (legat de libtesseract, Apache-2.0). Primeste pe un socket unix regiuni de
// subtitrare DVB (indici de 8 biti + paleta ARGB), scoate din paleta masca textului (umplutura fata de
// contur si fundal), imparte regiunea in randuri, mareste fiecare rand si il da lui tesseract (LSTM,
// modele tessdata_fast), apoi intoarce randurile: text UTF-8, dreptunghi, linia de baza, culorile
// umpluturii / conturului / casetei si increderea pe cuvant. Protocolul: hds_ocr_protocol.h, PROTOCOL.md.
//
// Nu blocheaza: un fir principal cu poll() (socketuri neblocante) si un fir de lucru; fiecare cerere poate fi anulata
// de o cerere mai noua (FLAG_SUPERSEDE) si are doua limite de timp:
//   - termenul clientului (timeout_ms), socotit de la primire: cat timp mai foloseste raspunsul (pagina trimisa din
//     timp are termenul pana dupa momentul afisarii);
//   - timpul de lucru al paginii, socotit de cand incepe recunoasterea (asteptarea in coada si incarcarea modelului
//     nu intra): de budget_factor ori timpul estimat dupa randuri (latimea benzii / inaltimea ei, cam jumatate din
//     numarul de litere) si viteza masurata pe masina (ms pe unitate, medie alunecatoare), intre min_budget_ms si
//     max_budget_ms. Astfel o pagina lunga pe un procesor lent are timpul ei, iar una stricata nu tine coada pe loc.
// Memoria de pagini si de randuri e comuna celor doua fire: firul principal cauta in ea o cerere chiar cand o
// primeste (pagina intreaga sau toate randurile ei deja citite) si raspunde pe loc, fara sa astepte in coada dupa
// o pagina lunga; numai ce lipseste din memorie ajunge la firul de lucru.
// Memoria glifelor: paginile unui post refolosesc aceleasi litere desenate. Dupa fiecare rand citit de tesseract,
// fiecare grupa de cerneala a randului (componente legate care se suprapun pe orizontala: litera cu punctele ei) se
// tine minte cu litera citita, cand tesseract e sigur de ea; distantele dintre litere si dintre cuvinte se tin minte
// pe model, raportate la inaltimea literelor. Un rand nou facut numai din litere vazute de cel putin doua ori, fara
// nicio grupa cu doua citiri diferite (I si l la fonturile fara serife) si cu toate distantele limpede de litera sau
// de cuvant, se compune fara tesseract (si pe firul principal, pe loc); altfel merge la tesseract. --no-glyphs o
// opreste.
// Scrisul inalt si ingust (fonturi condensate, ca la unele posturi de cablu): tesseract aduce randul la inaltimea lui
// fixa, deci literele inguste ajung foarte subtiri si se incurca intre ele ("rn" citit "m", "!" citit "I", "Al" citit
// "AI", "." citit ","), iar increderea cuvintelor scade. Inainte de recunoastere se masoara cat de ingust e scrisul
// cererii (mediana latime / inaltime a grupelor de cerneala cel putin cat 0,4 din inaltimea randului, adica literele,
// fara puncte si accente); sub --stretch-narrow randul se intinde pe orizontala pana la --stretch-target (cel mult
// --stretch-max). O cerere cu prea putine litere ca masura sa fie de crezut ia masura tinuta minte pentru model si
// inaltimea randului. Masurat pe paginile reale (Food Network pe cablu, mediana 0,47): 108 -> 137 pagini din 156 citite
// fara niciun cuvant nesigur, cuvintele gresite 86 -> 5; scrisul obisnuit (0,62-0,87) nu se intinde.
// A doua citire: un rand cu un cuvant nesigur (litere sub 70, semne sub 40) se citeste inca o data cu cealalta
// pregatire (intins -> neintins, neintins -> intins cu --reread-k), daca mai e timp, si ramane citirea cu increderea
// medie a cuvintelor mai mare. --no-stretch si --no-reread le opresc.

#include "hds_ocr_protocol.h"

#include <tesseract/baseapi.h>
#include <tesseract/ocrclass.h>
#include <tesseract/resultiterator.h>
#include <leptonica/allheaders.h>

#include <algorithm>
#include <atomic>
#include <cctype>
#include <cerrno>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <csignal>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <fcntl.h>
#include <list>
#include <map>
#include <memory>
#include <mutex>
#include <poll.h>
#include <string>
#include <sys/file.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <thread>
#include <unistd.h>
#include <unordered_map>
#include <vector>

using namespace hdsocr;

static const char *HDS_OCR_VERSION = "0.2.1";

// ------------------------------------------------------------------------------------------------
// optiuni

struct Options {
	std::string socket_path = "/tmp/hds-ocr.sock";
	std::string tessdata = "/usr/share/hds-ocr/tessdata";
	// dosare cu modele descarcate (memoria interna, stick, disc), cautate dupa --tessdata, in ordinea data
	std::vector<std::string> tessdata_extra;
	std::string implicit_model = "ron";   // pentru piste fara limba cunoscuta (o limba cunoscuta fara model = ST_NO_MODEL)
	int idle_exit_s = 600;                // iese singur dupa atatea secunde fara cereri (0 = niciodata)
	int nice_level = 10;
	int max_models = 2;                   // cate modele raman incarcate deodata (memorie)
	int cache_lines = 512;
	int cache_pages = 64;
	bool glyphs = true;                   // memoria glifelor (--no-glyphs o opreste)
	int cache_glyphs = 4096;
	int scale = 0;                        // 0 = automat (tinta target_band px), altfel factor fix 1..4
	// inaltimea tinta a benzii de text (umplutura, cu accente si codite) dupa marire, pixeli. Masurat pe
	// paginile de proba: marirea strica (LSTM isi aduce singur randul la 36 px, iar marirea biliniara
	// inmoaie marginile): x1 = 0.03% greseli, x2 = 0.09%, x3 = 0.32%. Cu 24, randurile obisnuite
	// (benzi de 17+ px) raman x1 si numai textul foarte mic se mareste x2.
	int target_band = 24;
	int psm = 7;                          // 7 = un rand, 13 = rand brut
	// scrisul ingust (vezi sus): sub stretch_narrow (mediana latime / inaltime a literelor) randul se intinde pe
	// orizontala pana la stretch_target, cel mult stretch_max. Masurat: Food Network (cablu) 0,47; Das Erste, ZDF,
	// paginile facute cu Arial, Tahoma, Verdana, DejaVu 0,62-0,87 (raman neintinse).
	bool stretch = true;
	double stretch_target = 0.68;
	double stretch_narrow = 0.59;
	double stretch_max = 1.5;
	// a doua citire a unui rand nesigur, cu cealalta pregatire (neintins -> intins de reread_k ori)
	bool reread = true;
	double reread_k = 1.25;
	int default_timeout_ms = 5000;        // termenul unei cereri fara timeout_ms
	// timpul de lucru al unei pagini (vezi sus): budget_factor x estimarea, intre min_budget_ms si max_budget_ms.
	// Pornirea: 20 ms pe unitate (masurat in /tmp pe receptor, A53: mediana 13,9, p90 23,2 ms pe unitate; un rand
	// obisnuit de subtitrare are ~17 unitati, ~34 de litere), apoi viteza masurata pe masina.
	int min_budget_ms = 1500;
	int max_budget_ms = 10000;
	double budget_factor = 3.0;
	double ms_per_unit_start = 20.0;
	bool daemon = false;
	bool verbose = false;
	// proba fara socket
	std::vector<std::string> bench_files;
	int repeat = 1;
	bool bench_no_cache = false;
	std::string dump_dir;                 // scrie randurile pregatite ca PGM (depanare)
	bool no_dict = false;                 // fara dictionarul modelului (proba)
	std::vector<std::pair<std::string, std::string>> tess_vars;   // --set NUME=VALOARE (variabile tesseract)
};
static Options g_opt;

static void logv(const char *fmt, ...)
{
	if (!g_opt.verbose)
		return;
	va_list ap;
	va_start(ap, fmt);
	fprintf(stderr, "[hds-ocr] ");
	vfprintf(stderr, fmt, ap);
	fprintf(stderr, "\n");
	va_end(ap);
}

static void loge(const char *fmt, ...)
{
	va_list ap;
	va_start(ap, fmt);
	fprintf(stderr, "[hds-ocr] ");
	vfprintf(stderr, fmt, ap);
	fprintf(stderr, "\n");
	va_end(ap);
}

static int64_t now_us()
{
	return std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

// ------------------------------------------------------------------------------------------------
// limba pistei DVB (ISO 639-2 B sau T, uneori 639-1) -> modelul tessdata

struct LangMap { const char *code; const char *model; };
static const LangMap LANG_MAP[] = {
	{"rum", "ron"}, {"ron", "ron"}, {"mol", "ron"}, {"ro", "ron"},
	{"eng", "eng"}, {"en", "eng"},
	{"ger", "deu"}, {"deu", "deu"}, {"de", "deu"},
	{"fre", "fra"}, {"fra", "fra"}, {"fr", "fra"},
	{"ita", "ita"}, {"it", "ita"},
	{"spa", "spa"}, {"esl", "spa"}, {"es", "spa"},
	{"hun", "hun"}, {"hu", "hun"},
	{"pol", "pol"}, {"pl", "pol"},
	{"cze", "ces"}, {"ces", "ces"}, {"cs", "ces"},
	{"dut", "nld"}, {"nld", "nld"}, {"nla", "nld"}, {"nl", "nld"},
	{"por", "por"}, {"pt", "por"},
	{"rus", "rus"}, {"ru", "rus"},
	{"tur", "tur"}, {"tr", "tur"},
	// limbi ale caror modele se descarca la cerere (Components/HdsOcrModele.py): se folosesc cand modelul e intr-unul
	// din dosare
	{"slo", "slk"}, {"slk", "slk"}, {"sk", "slk"},
	{"hrv", "hrv"}, {"scr", "hrv"}, {"hr", "hrv"},
	// sarba: modelul chirilic sau cel cu litere latine, primul care exista; „srpl" e codul clientului pentru
	// modelul cu litere latine (campul limbii din protocol are 4 octeti, „srp_latn" nu incape)
	{"srp", "srp"}, {"srp", "srp_latn"}, {"scc", "srp"}, {"scc", "srp_latn"}, {"sr", "srp"}, {"sr", "srp_latn"},
	{"srpl", "srp_latn"},
	{"slv", "slv"}, {"sl", "slv"},
	{"bul", "bul"}, {"bg", "bul"},
	{"gre", "ell"}, {"ell", "ell"}, {"el", "ell"},
	{"ukr", "ukr"}, {"uk", "ukr"},
	{"swe", "swe"}, {"sv", "swe"},
	{"dan", "dan"}, {"da", "dan"},
	{"nor", "nor"}, {"nob", "nor"}, {"nno", "nor"}, {"no", "nor"},
	{"fin", "fin"}, {"fi", "fin"},
	{"cat", "cat"}, {"ca", "cat"},
	{"alb", "sqi"}, {"sqi", "sqi"}, {"sq", "sqi"},
	{"lit", "lit"}, {"lt", "lit"},
	{"lav", "lav"}, {"lv", "lav"},
	{"est", "est"}, {"et", "est"},
	{"mac", "mkd"}, {"mkd", "mkd"}, {"mk", "mkd"},
	{"bel", "bel"}, {"be", "bel"},
	{"bos", "bos"}, {"bs", "bos"},
	{"bre", "bre"}, {"br", "bre"},
	{"cos", "cos"}, {"co", "cos"},
	{"wel", "cym"}, {"cym", "cym"}, {"cy", "cym"},
	{"baq", "eus"}, {"eus", "eus"}, {"eu", "eus"},
	{"fao", "fao"}, {"fo", "fao"},
	{"fry", "fry"}, {"fy", "fry"},
	{"gla", "gla"}, {"gd", "gla"},
	{"gle", "gle"}, {"ga", "gle"},
	{"glg", "glg"}, {"gl", "glg"},
	{"ice", "isl"}, {"isl", "isl"}, {"is", "isl"},
	{"ltz", "ltz"}, {"lb", "ltz"},
	{"mlt", "mlt"}, {"mt", "mlt"},
	{"oci", "oci"}, {"oc", "oci"},
	{"ara", "ara"}, {"ar", "ara"},
	{"heb", "heb"}, {"he", "heb"}, {"iw", "heb"},
	{"per", "fas"}, {"fas", "fas"}, {"fa", "fas"},
	{"kur", "kmr"}, {"kmr", "kmr"}, {"ku", "kmr"},
	{nullptr, nullptr},
};

static bool file_exists(const std::string &p)
{
	struct stat st;
	return stat(p.c_str(), &st) == 0 && S_ISREG(st.st_mode);
}

// dosarul in care e modelul (--tessdata, apoi fiecare --tessdata-extra), sau "" daca lipseste din toate. Se
// verifica la fiecare cerere (un stat pe dosar): un model descarcat intre timp se foloseste fara repornire, iar un stick
// scos da ST_NO_MODEL.
static std::string model_dir(const std::string &model)
{
	if (model.empty())
		return "";
	if (file_exists(g_opt.tessdata + "/" + model + ".traineddata"))
		return g_opt.tessdata;
	for (const std::string &dir : g_opt.tessdata_extra)
		if (file_exists(dir + "/" + model + ".traineddata"))
			return dir;
	return "";
}

static bool model_exists(const std::string &model)
{
	return !model_dir(model).empty();
}

// intoarce modelul de folosit sau "" (ST_NO_MODEL). O limba cunoscuta (in LANG_MAP) al carei model lipseste din dosare
// NU trece pe modelul implicit: romana ar citi greaca sau chirilica drept litere fara sens, cu incredere mica. Numai o
// pista fara limba sau cu un cod necunoscut („und", „qaa", gol) ia modelul implicit (--implicit, romana). Un cod cu
// mai multe randuri in LANG_MAP (sarba) ia primul model care exista.
static std::string resolve_model(const char lang4[4])
{
	char code[5] = {0};
	for (int i = 0; i < 4 && lang4[i]; ++i)
	{
		char c = lang4[i];
		if (c >= 'A' && c <= 'Z')
			c = (char)(c - 'A' + 'a');
		if (c < 'a' || c > 'z')
			break;
		code[i] = c;
	}
	bool known = false;
	for (const LangMap *m = LANG_MAP; m->code; ++m)
		if (!strcmp(m->code, code))
		{
			if (model_exists(m->model))
				return m->model;
			known = true;
		}
	if (known)
		return "";
	if (model_exists(g_opt.implicit_model))
		return g_opt.implicit_model;
	return "";
}

// ------------------------------------------------------------------------------------------------
// memorie LRU (amprenta 64 de biti -> valoare)

static uint64_t fnv1a(uint64_t h, const void *data, size_t n)
{
	const uint8_t *p = (const uint8_t *)data;
	for (size_t i = 0; i < n; ++i)
	{
		h ^= p[i];
		h *= 1099511628211ULL;
	}
	return h;
}
static const uint64_t FNV_START = 14695981039346656037ULL;

template <class V> class Lru
{
public:
	explicit Lru(size_t cap) : m_cap(cap) {}
	bool get(uint64_t k, V &out)
	{
		auto it = m_map.find(k);
		if (it == m_map.end())
			return false;
		m_list.splice(m_list.begin(), m_list, it->second);
		out = it->second->second;
		return true;
	}
	void put(uint64_t k, const V &v)
	{
		if (m_cap == 0)
			return;
		auto it = m_map.find(k);
		if (it != m_map.end())
		{
			it->second->second = v;
			m_list.splice(m_list.begin(), m_list, it->second);
			return;
		}
		m_list.emplace_front(k, v);
		m_map[k] = m_list.begin();
		while (m_map.size() > m_cap)
		{
			m_map.erase(m_list.back().first);
			m_list.pop_back();
		}
	}
	size_t size() const { return m_map.size(); }
private:
	size_t m_cap;
	std::list<std::pair<uint64_t, V>> m_list;
	std::unordered_map<uint64_t, typename std::list<std::pair<uint64_t, V>>::iterator> m_map;
};

// ------------------------------------------------------------------------------------------------
// motoarele tesseract, cate unul pe model, folosite numai din firul de lucru

class Engines
{
public:
	tesseract::TessBaseAPI *get(const std::string &model)
	{
		for (auto it = m_list.begin(); it != m_list.end(); ++it)
			if (it->first == model)
			{
				m_list.splice(m_list.begin(), m_list, it);
				return m_list.front().second.get();
			}
		int64_t t0 = now_us();
		std::unique_ptr<tesseract::TessBaseAPI> api(new tesseract::TessBaseAPI());
		std::vector<std::string> vars, vals;
		vars.push_back("debug_file"); vals.push_back("/dev/null");
		if (g_opt.no_dict)
		{
			vars.push_back("load_system_dawg"); vals.push_back("0");
			vars.push_back("load_freq_dawg"); vals.push_back("0");
		}
		for (auto &kv : g_opt.tess_vars)
		{
			vars.push_back(kv.first);
			vals.push_back(kv.second);
		}
		const std::string dir = model_dir(model);
		if (dir.empty() || api->Init(dir.c_str(), model.c_str(), tesseract::OEM_LSTM_ONLY, nullptr, 0, &vars, &vals, false) != 0)
		{
			loge("nu pot incarca modelul %s din %s", model.c_str(), dir.empty() ? "niciun dosar" : dir.c_str());
			return nullptr;
		}
		api->SetVariable("tessedit_do_invert", "0");      // noi dam mereu text inchis pe alb
		logv("model %s incarcat in %.0f ms", model.c_str(), (now_us() - t0) / 1000.0);
		m_list.emplace_front(model, std::move(api));
		while ((int)m_list.size() > std::max(1, g_opt.max_models))
		{
			logv("model %s descarcat (maxim %d incarcate)", m_list.back().first.c_str(), g_opt.max_models);
			m_list.back().second->End();
			m_list.pop_back();
		}
		return m_list.front().second.get();
	}
	std::vector<std::string> loaded() const
	{
		std::vector<std::string> v;
		for (auto &e : m_list)
			v.push_back(e.first);
		return v;
	}
private:
	std::list<std::pair<std::string, std::unique_ptr<tesseract::TessBaseAPI>>> m_list;
};

// ------------------------------------------------------------------------------------------------
// analiza paletei: ce e fundal, ce e contur, ce e umplutura

struct Entry {
	int a = 0, r = 0, g = 0, b = 0;
	double luma = 0;      // luminanta culorii (0..255)
	double lb = 0;        // luminanta compusa peste negru (luma * opacitate)
	double lw = 0;        // luminanta compusa peste alb
	long cnt = 0;         // pixeli
	long touch = 0;       // pixeli care ating fundalul (vecin transparent / caseta / marginea regiunii)
	long border = 0;      // pixeli pe marginea partii netransparente a regiunii
	long solid = 0;       // pixeli cu toti cei 4 vecini de aceeasi culoare (o caseta e „plina", un contur nu)
	bool bg = false;      // transparent sau caseta
	double outer() const { return cnt ? (double)touch / cnt : 0; }
};

struct Analysis {
	int n = 0;                       // intrari in paleta (+1 pentru "in afara paletei", tratat transparent)
	std::vector<Entry> e;
	int box = -1, fill = -1, outline = -1;
	bool inverted = false;
	bool has_outline = false;
	double ref = 0;                  // luminanta fundalului de referinta (contur / caseta / 0)
	std::vector<uint8_t> lut;        // index -> gri (0 = cerneala textului, 255 = fundal), pentru toata regiunea
};

static const int ALPHA_TRANSPARENT = 48;

static double luma_of(int r, int g, int b) { return 0.299 * r + 0.587 * g + 0.114 * b; }

// masca: normal (text deschis, contur/fundal inchis): cerneala = cat de aproape e de umplutura in luminanta
// compusa peste negru; inversat (text inchis pe caseta/contur deschis): luminanta compusa peste alb.
static void build_lut(const Analysis &an, double hi_fill, std::vector<uint8_t> &lut)
{
	lut.assign(256, 255);
	for (int i = 0; i < an.n; ++i)
	{
		const Entry &e = an.e[i];
		if (e.bg || i == an.outline || e.a < ALPHA_TRANSPARENT)
		{
			lut[i] = 255;
			continue;
		}
		double v;
		if (!an.inverted)
		{
			double span = hi_fill - an.ref;
			if (span < 1)
				span = 1;
			v = 255.0 * (hi_fill - e.lb) / span;
		}
		else
		{
			double span = an.ref - hi_fill;
			if (span < 1)
				span = 1;
			v = 255.0 * (e.lw - hi_fill) / span;
		}
		lut[i] = (uint8_t)std::lround(std::min(255.0, std::max(0.0, v)));
	}
}

static void analyze(const Request &rq, Analysis &an)
{
	const int W = rq.width, H = rq.height;
	an.n = (int)rq.palette.size();
	an.e.assign(257, Entry());
	for (int i = 0; i < an.n; ++i)
	{
		uint32_t c = rq.palette[i];
		Entry &e = an.e[i];
		e.a = (c >> 24) & 255; e.r = (c >> 16) & 255; e.g = (c >> 8) & 255; e.b = c & 255;
		e.luma = luma_of(e.r, e.g, e.b);
		e.lb = e.luma * e.a / 255.0;
		e.lw = e.lb + 255.0 * (1.0 - e.a / 255.0);
		e.bg = e.a < ALPHA_TRANSPARENT;
	}
	an.e[256].bg = true;   // index in afara paletei
	const uint8_t *px = rq.pixels.data();
	auto idx = [&](int x, int y) -> int { int v = px[(size_t)y * W + x]; return v < an.n ? v : 256; };
	// marginea se ia pe dreptunghiul partii netransparente, nu pe al regiunii: o caseta cu cativa pixeli
	// transparenti in jur (regiunea mai mare decat caseta) e tot caseta. Probat in cloud 25.09: text negru pe
	// caseta gri deschis cu 3 px transparenti pe margine iesea „Ir uiV alee [49 ...", caseta luata drept text.
	int bx0 = W, by0 = H, bx1 = -1, by1 = -1;
	for (int y = 0; y < H; ++y)
		for (int x = 0; x < W; ++x)
		{
			int i = idx(x, y);
			an.e[i].cnt++;
			if (!an.e[i].bg)
			{
				bx0 = std::min(bx0, x); bx1 = std::max(bx1, x);
				by0 = std::min(by0, y); by1 = std::max(by1, y);
			}
		}
	long border_total = 0, holes = 0, total = bx1 >= 0 ? (long)(bx1 - bx0 + 1) * (by1 - by0 + 1) : (long)W * H;
	if (bx1 >= 0)
		for (int y = by0; y <= by1; ++y)
			for (int x = bx0; x <= bx1; ++x)
			{
				int i = idx(x, y);
				if (x == bx0 || y == by0 || x == bx1 || y == by1)
				{
					an.e[i].border++;
					border_total++;
				}
				else if (an.e[i].bg)
					holes++;   // transparent in interiorul partii netransparente (intre litere, in „o")
				else if (idx(x - 1, y) == i && idx(x + 1, y) == i && idx(x, y - 1) == i && idx(x, y + 1) == i)
					an.e[i].solid++;
			}
	// caseta: o culoare opaca ce acopera mare parte din regiune si cea mai mare parte din margine, „plina"
	// (jumatate din pixeli cu toti vecinii la fel), fara gauri transparente si cu text pe ea (alta culoare).
	// Conturul literelor nu trece: la un cuvant scurt cu regiunea stransa pe text („IN") umple si el marginea,
	// dar e plin numai ~0,37; la HD (contur de 5 px) e plin ~0,66, dar are 0,3-0,5 gauri. Masurat pe paginile
	// de proba: casetele au plin 0,82-0,89 si gauri 0,00 (cloud/rezultate/casete-masuratori.txt).
	int best = -1;
	long nonbg = 0;
	for (int i = 0; i < an.n; ++i)
		if (!an.e[i].bg)
		{
			nonbg += an.e[i].cnt;
			if (best < 0 || an.e[i].cnt > an.e[best].cnt)
				best = i;
		}
	if (best >= 0 && an.e[best].cnt >= total * 0.35 && an.e[best].border >= border_total * 0.5 &&
		an.e[best].solid >= an.e[best].cnt * 0.5 && holes <= total * 0.15 &&
		nonbg - an.e[best].cnt >= std::max(1L, nonbg / 50))
	{
		an.box = best;
		an.e[best].bg = true;
	}
	// atingerea fundalului (4 vecini)
	for (int y = 0; y < H; ++y)
		for (int x = 0; x < W; ++x)
		{
			int i = idx(x, y);
			if (an.e[i].bg)
				continue;
			bool t = x == 0 || y == 0 || x == W - 1 || y == H - 1 ||
				an.e[idx(x - 1, y)].bg || an.e[idx(x + 1, y)].bg || an.e[idx(x, y - 1)].bg || an.e[idx(x, y + 1)].bg;
			if (t)
				an.e[i].touch++;
		}
	long ink = 0;
	for (int i = 0; i < an.n; ++i)
		if (!an.e[i].bg)
			ink += an.e[i].cnt;
	// intrarile insemnate: opace, cel putin 2% din pixelii ne-fundal
	std::vector<int> sig;
	for (int i = 0; i < an.n; ++i)
		if (!an.e[i].bg && an.e[i].a >= 128 && an.e[i].cnt >= std::max(1L, ink / 50))
			sig.push_back(i);
	if (sig.empty())
		for (int i = 0; i < an.n; ++i)
			if (!an.e[i].bg && an.e[i].cnt > 0)
				sig.push_back(i);
	if (sig.empty())
	{
		an.lut.assign(256, 255);
		return;
	}
	int B = sig[0], D = sig[0];
	for (int i : sig)
	{
		if (an.e[i].lb > an.e[B].lb) B = i;
		if (an.e[i].lb < an.e[D].lb) D = i;
	}
	if (an.box >= 0)
	{
		const Entry &bx = an.e[an.box];
		// textul = intrarea cea mai folosita si mai departe de caseta ca luminanta
		int t = -1;
		double bestv = -1;
		for (int i : sig)
		{
			double v = an.e[i].cnt * std::fabs(an.e[i].lb - bx.lb);
			if (v > bestv) { bestv = v; t = i; }
		}
		an.fill = t;
		an.inverted = an.e[t].lb < bx.lb;
		an.ref = an.inverted ? bx.lw : bx.lb;
		// contur in interiorul casetei: o intrare opusa textului, care atinge caseta
		int o = an.inverted ? B : D;
		if (o != t && std::fabs(an.e[o].lb - an.e[t].lb) >= 50 && an.e[o].outer() > an.e[t].outer() + 0.15)
		{
			an.outline = o;
			an.has_outline = true;
			an.ref = an.inverted ? an.e[o].lw : an.e[o].lb;
		}
	}
	else if (an.e[B].lb - an.e[D].lb >= 50)
	{
		// doua tonuri: de obicei umplutura deschisa cu contur inchis; inversat daca cel inchis e in interior
		bool inv = an.e[B].outer() > an.e[D].outer() + 0.15 && an.e[D].outer() < 0.12;
		an.inverted = inv;
		an.fill = inv ? D : B;
		an.outline = inv ? B : D;
		an.has_outline = an.e[an.outline].outer() > 0.15;
		an.ref = inv ? an.e[an.outline].lw : an.e[an.outline].lb;
		if (!an.has_outline)
		{
			// tonul inchis nu inconjoara textul (de ex. doua culori de text): nu e contur
			an.outline = -1;
			an.ref = inv ? 255 : 0;
		}
	}
	else
	{
		an.fill = B;
		an.inverted = false;
		an.ref = 0;
	}
	build_lut(an, an.inverted ? an.e[an.fill].lw : an.e[an.fill].lb, an.lut);
}

// ------------------------------------------------------------------------------------------------
// randurile

struct Band { int y0, y1, x0, x1; };   // [y0, y1) si [x0, x1) in coordonatele regiunii

static std::vector<Band> find_bands(const Request &rq, const Analysis &an)
{
	const int W = rq.width, H = rq.height;
	std::vector<int> rows(H, 0);
	for (int y = 0; y < H; ++y)
	{
		const uint8_t *p = rq.pixels.data() + (size_t)y * W;
		int c = 0;
		for (int x = 0; x < W; ++x)
			if (an.lut[p[x]] < 160)
				c++;
		rows[y] = c;
	}
	std::vector<Band> b;
	for (int y = 0; y < H;)
	{
		if (!rows[y]) { y++; continue; }
		int y0 = y;
		while (y < H && rows[y]) y++;
		b.push_back({y0, y, 0, 0});
	}
	if (b.empty())
		return b;
	// benzile mici (semne diacritice, punctul lui i, virgula de sub s/t) se lipesc de randul cel mai apropiat
	for (bool changed = true; changed && b.size() > 1;)
	{
		changed = false;
		int hmax = 0;
		for (auto &x : b) hmax = std::max(hmax, x.y1 - x.y0);
		for (size_t i = 0; i < b.size(); ++i)
		{
			int h = b[i].y1 - b[i].y0;
			if (h >= hmax * 0.45)
				continue;
			int gu = i > 0 ? b[i].y0 - b[i - 1].y1 : 1 << 30;
			int gd = i + 1 < b.size() ? b[i + 1].y0 - b[i].y1 : 1 << 30;
			int g = std::min(gu, gd);
			if (g > hmax * 0.6)
				continue;
			size_t j = gu <= gd ? i - 1 : i + 1;
			size_t a = std::min(i, j), c = std::max(i, j);
			b[a].y0 = std::min(b[a].y0, b[c].y0);
			b[a].y1 = std::max(b[a].y1, b[c].y1);
			b.erase(b.begin() + c);
			changed = true;
			break;
		}
	}
	// zgomot: benzi de 1-2 pixeli ramase singure
	std::vector<Band> out;
	for (auto &x : b)
	{
		if (x.y1 - x.y0 < 3)
			continue;
		int x0 = W, x1 = 0;
		for (int y = x.y0; y < x.y1; ++y)
		{
			const uint8_t *p = rq.pixels.data() + (size_t)y * W;
			for (int xx = 0; xx < W; ++xx)
				if (an.lut[p[xx]] < 160)
				{
					x0 = std::min(x0, xx);
					x1 = std::max(x1, xx + 1);
				}
		}
		if (x1 > x0)
		{
			x.x0 = x0;
			x.x1 = x1;
			out.push_back(x);
		}
	}
	return out;
}

// marire biliniara a unei imagini gri (1 octet/pixel)
static void upscale(const std::vector<uint8_t> &src, int w, int h, int s, std::vector<uint8_t> &dst)
{
	int W = w * s, H = h * s;
	dst.resize((size_t)W * H);
	for (int Y = 0; Y < H; ++Y)
	{
		double fy = (Y + 0.5) / s - 0.5;
		int y0 = (int)std::floor(fy);
		double ty = fy - y0;
		int ya = std::min(h - 1, std::max(0, y0)), yb = std::min(h - 1, std::max(0, y0 + 1));
		for (int X = 0; X < W; ++X)
		{
			double fx = (X + 0.5) / s - 0.5;
			int x0 = (int)std::floor(fx);
			double tx = fx - x0;
			int xa = std::min(w - 1, std::max(0, x0)), xb = std::min(w - 1, std::max(0, x0 + 1));
			double v = (1 - ty) * ((1 - tx) * src[(size_t)ya * w + xa] + tx * src[(size_t)ya * w + xb]) +
				ty * ((1 - tx) * src[(size_t)yb * w + xa] + tx * src[(size_t)yb * w + xb]);
			dst[(size_t)Y * W + X] = (uint8_t)std::lround(v);
		}
	}
}

// romana: s si t cu sedila -> cu virgula (forma corecta); tesseract le scoate uneori pe cele cu sedila
static std::string ro_comma(const std::string &s)
{
	std::string o;
	o.reserve(s.size());
	for (size_t i = 0; i < s.size(); ++i)
	{
		unsigned char c = (unsigned char)s[i];
		if ((c == 0xC5) && i + 1 < s.size())
		{
			unsigned char d = (unsigned char)s[i + 1];
			// U+015E S, U+015F s, U+0162 T, U+0163 t (sedila) -> U+0218, U+0219, U+021A, U+021B (virgula)
			const char *rep = nullptr;
			if (d == 0x9E) rep = "\xC8\x98";
			else if (d == 0x9F) rep = "\xC8\x99";
			else if (d == 0xA2) rep = "\xC8\x9A";
			else if (d == 0xA3) rep = "\xC8\x9B";
			if (rep)
			{
				o += rep;
				i++;
				continue;
			}
		}
		o += (char)c;
	}
	return o;
}

// bara verticala nu apare in subtitrari; la fonturile fara serife "I" mare e desenat ca o bara si
// tesseract scrie uneori "|" (aceeasi corectura o fac si programele de subtitrari)
static std::string fix_bar(const std::string &s)
{
	std::string o = s;
	for (char &c : o)
		if (c == '|')
			c = 'I';
	return o;
}

static std::string trim(const std::string &s)
{
	size_t a = 0, b = s.size();
	while (a < b && (s[a] == ' ' || s[a] == '\n' || s[a] == '\r' || s[a] == '\t')) a++;
	while (b > a && (s[b - 1] == ' ' || s[b - 1] == '\n' || s[b - 1] == '\r' || s[b - 1] == '\t')) b--;
	return s.substr(a, b - a);
}

// rezultatul unui rand, in coordonate relative la coltul decupajului, pixeli de regiune (pentru memorie)
struct LineOcr {
	bool ok = false;
	std::string text;
	int conf = 0;
	bool low = false;
	int baseline = -1;         // relativ la y-ul decupajului
	int x_height = 0, ascender = 0, descender = 0;
	std::vector<Word> words;   // x, y relative la decupaj
};

struct Job {
	Request rq;
	int conn = -1;             // conexiunea (id intern); -1 = proba fara socket
	int64_t t_recv = 0;
	int64_t deadline = 0;
	std::atomic<bool> cancelled{false};
};

static bool cancel_cb(void *self, int)
{
	Job *j = (Job *)self;
	return j && j->cancelled.load();
}

struct Stats {
	std::atomic<long> requests{0}, lines{0}, line_hits{0}, page_hits{0}, timeouts{0}, cancelled{0};
	std::atomic<long> glyph_lines{0};       // randuri compuse din memoria glifelor, fara tesseract
	// de ce un rand nu s-a putut compune (proba): distantele neinvatate, o grupa necunoscuta, cu doua citiri, vazuta
	// o singura data, o distanta nelamurita
	std::atomic<long> gm_spacing{0}, gm_unknown{0}, gm_ambiguous{0}, gm_seen{0}, gm_gap{0};
	std::atomic<long> budget_timeouts{0};   // randuri oprite de timpul de lucru al paginii
	std::atomic<long> expired{0};           // randuri oprite de termenul clientului (pagina fara folos)
	std::atomic<long> immediate{0};         // cereri raspunse pe loc din memorie, la primire
	std::atomic<long> stretched{0};         // randuri citite intinse (scris ingust)
	std::atomic<long> rereads{0};           // randuri nesigure citite a doua oara
	std::atomic<long> rereads_better{0};    // ... la care a doua citire a ramas
};
static Stats g_stats;

// unitatile unei benzi: latimea / inaltimea (cam jumatate din numarul de litere, oricare ar fi marimea literelor)
static double band_units(int x0, int x1, int y0, int y1)
{
	return std::max(1.0, (double)(x1 - x0) / std::max(1, y1 - y0));
}

// viteza de recunoastere pe masina asta: ms pe unitate, medie alunecatoare peste randurile recunoscute (nu cele din
// memorie). Scrisa de firul de lucru, citita si de firul principal (PONG).
class Speed
{
public:
	void add(double ms, double units)
	{
		if (units <= 0 || ms < 0)
			return;
		std::lock_guard<std::mutex> lk(m_mx);
		double v = ms / units;
		m_ms_per_unit = m_samples ? 0.8 * m_ms_per_unit + 0.2 * v : v;
		m_samples++;
	}
	double ms_per_unit()
	{
		std::lock_guard<std::mutex> lk(m_mx);
		return m_samples ? m_ms_per_unit : g_opt.ms_per_unit_start;
	}
	long samples()
	{
		std::lock_guard<std::mutex> lk(m_mx);
		return m_samples;
	}
	// timpul de lucru al unei pagini cu atatea unitati, ms
	int budget_ms(double units)
	{
		double est = units * ms_per_unit();
		double b = g_opt.budget_factor * est + 300.0;
		return (int)std::max((double)g_opt.min_budget_ms, std::min((double)g_opt.max_budget_ms, b));
	}
private:
	std::mutex m_mx;
	double m_ms_per_unit = 0;
	long m_samples = 0;
};
static Speed g_speed;

// ------------------------------------------------------------------------------------------------
// memoria glifelor (vezi inceputul fisierului)

// o litera citita de tesseract: textul, increderea, al catelea cuvant si marginile cuvantului in decupaj (pixeli de
// regiune). Marginile literelor date de LSTM sunt aproximative; ale cuvintelor sunt sigure, deci literele unui cuvant
// se leaga de grupele lui dupa ordine, cand sunt tot atatea.
struct Sym {
	std::string text;
	int conf = 0;
	int word = 0;
	int wx0 = 0, wx1 = 0;
};

// o grupa de cerneala a unui rand: [x0, x1) x [y0, y1) in decupaj si cheia formei ei
struct Grupa {
	int x0 = 0, x1 = 0, y0 = 0, y1 = 0;
	uint64_t key = 0;
};

struct GlyphVal {
	std::string text;
	int conf = 0;          // cea mai mica incredere cu care a fost citita
	int seen = 0;
	bool ambiguous = false;  // aceeasi forma citita o data ca o litera si alta data ca alta
};

// distantele dintre grupe, raportate la inaltimea literei x (mediana grupelor citite ca litere mici fara codite si
// accente); pe model si pe inaltimea literei x (un post are de obicei un singur font, in una sau doua marimi)
struct Spacing {
	double max_intra = -1;  // cea mai mare distanta vazuta intre literele aceluiasi cuvant
	double min_inter = 1e9; // cea mai mica distanta vazuta intre cuvinte
	int lines = 0;
};

// literele mici fara codite, accente si puncte (latine, chirilice, grecesti): inaltimea lor = inaltimea literei x
static bool litera_x(const std::string &t)
{
	static const char *const L[] = {"a", "c", "e", "m", "n", "o", "r", "s", "u", "v", "w", "x", "z",
		"а", "в", "г", "е", "к", "м", "н", "о", "п", "с", "т", "х", "ч", "ш", "ь", "ы", "ъ", "э", "ю", "я",
		"α", "κ", "ι", "ν", "ο", "π", "σ", "τ", "υ", "ω"};
	for (const char *l : L)
		if (t == l)
			return true;
	return false;
}

// inaltimea literei x a unui rand: mediana grupelor citite ca litere x (0 = niciuna)
static int x_height_of(const std::vector<int> &inaltimi)
{
	if (inaltimi.empty())
		return 0;
	std::vector<int> v = inaltimi;
	std::nth_element(v.begin(), v.begin() + v.size() / 2, v.end());
	return v[v.size() / 2];
}

static const int GLYPH_MIN_CONF = 90;   // increderea minima a unei litere tinute minte
static const int GLYPH_MIN_SEEN = 2;    // de cate ori trebuie vazuta la fel inainte sa fie folosita
static const int GLYPH_MAX_GROUPS = 300;

// Grupele de cerneala ale randurilor [r0, r1) din decupaj (255 = fundal, sub 128 = cerneala): componente legate (8
// vecini), fara punctele singure, unite cand se suprapun pe orizontala; cheia fiecareia = modelul, marimea, pozitia
// fata de linia de baza (mediana marginilor de jos) si forma pixel cu pixel. base = linia de baza, medh = inaltimea
// mediana. false cand randul nu se poate imparti (gol, prea multe grupe).
static bool glyph_groups(const std::vector<uint8_t> &crop, int cw, int r0, int r1, const std::string &model,
	std::vector<Grupa> &out, int &base, int &medh)
{
	out.clear();
	const int h = r1 - r0;
	if (cw <= 0 || h <= 0 || (size_t)cw * h > 4000000)
		return false;
	std::vector<int> lab((size_t)cw * h, 0);
	struct Comp { int x0, x1, y0, y1, px; };
	std::vector<Comp> comps(1, Comp{0, 0, 0, 0, 0});
	std::vector<int> st;
	auto ink = [&](int x, int y) { return crop[(size_t)(y + r0) * cw + x] < 128; };
	for (int y = 0; y < h; ++y)
		for (int x = 0; x < cw; ++x)
		{
			if (!ink(x, y) || lab[(size_t)y * cw + x])
				continue;
			const int k = (int)comps.size();
			Comp c{x, x + 1, y, y + 1, 0};
			lab[(size_t)y * cw + x] = k;
			st.assign(1, y * cw + x);
			while (!st.empty())
			{
				const int p = st.back();
				st.pop_back();
				const int py = p / cw, px = p % cw;
				c.px++;
				c.x0 = std::min(c.x0, px); c.x1 = std::max(c.x1, px + 1);
				c.y0 = std::min(c.y0, py); c.y1 = std::max(c.y1, py + 1);
				for (int dy = -1; dy <= 1; ++dy)
					for (int dx = -1; dx <= 1; ++dx)
					{
						const int qy = py + dy, qx = px + dx;
						if (qy < 0 || qy >= h || qx < 0 || qx >= cw || !ink(qx, qy) || lab[(size_t)qy * cw + qx])
							continue;
						lab[(size_t)qy * cw + qx] = k;
						st.push_back(qy * cw + qx);
					}
			}
			comps.push_back(c);
		}
	std::vector<int> ord;
	for (int k = 1; k < (int)comps.size(); ++k)
		if (comps[k].px > 1)
			ord.push_back(k);
	if (ord.empty())
		return false;
	std::sort(ord.begin(), ord.end(), [&](int a, int b) { return comps[a].x0 < comps[b].x0; });
	std::vector<int> gid(comps.size(), -1);
	for (int k : ord)
	{
		const Comp &c = comps[k];
		if (out.empty() || c.x0 >= out.back().x1)
		{
			if ((int)out.size() >= GLYPH_MAX_GROUPS)
				return false;
			Grupa g;
			g.x0 = c.x0; g.x1 = c.x1; g.y0 = c.y0; g.y1 = c.y1;
			out.push_back(g);
		}
		else
		{
			Grupa &g = out.back();
			g.x1 = std::max(g.x1, c.x1); g.y0 = std::min(g.y0, c.y0); g.y1 = std::max(g.y1, c.y1);
		}
		gid[k] = (int)out.size() - 1;
	}
	std::vector<int> jos, inalt;
	for (const Grupa &g : out)
	{
		jos.push_back(g.y1);
		inalt.push_back(g.y1 - g.y0);
	}
	std::nth_element(jos.begin(), jos.begin() + jos.size() / 2, jos.end());
	std::nth_element(inalt.begin(), inalt.begin() + inalt.size() / 2, inalt.end());
	base = jos[jos.size() / 2];
	medh = std::max(1, inalt[inalt.size() / 2]);
	std::vector<uint8_t> bits;
	for (int i = 0; i < (int)out.size(); ++i)
	{
		Grupa &g = out[i];
		int32_t dim[4] = {g.x1 - g.x0, g.y1 - g.y0, g.y0 - base, g.y1 - base};
		uint64_t key = FNV_START;
		key = fnv1a(key, model.data(), model.size());
		key = fnv1a(key, dim, sizeof(dim));
		bits.assign(((size_t)dim[0] * dim[1] + 7) / 8, 0);
		size_t b = 0;
		for (int y = g.y0; y < g.y1; ++y)
			for (int x = g.x0; x < g.x1; ++x, ++b)
			{
				const int l = lab[(size_t)y * cw + x];
				if (l > 0 && gid[l] == i)
					bits[b >> 3] |= (uint8_t)(1u << (b & 7));
			}
		g.key = fnv1a(key, bits.data(), bits.size());
		g.y0 += r0;
		g.y1 += r0;
	}
	base += r0;
	return true;
}

// memoria randurilor, a paginilor si a glifelor, comuna firului principal (raspunsul pe loc) si firului de lucru
struct Memory
{
	Memory() : lines(g_opt.cache_lines), pages(g_opt.cache_pages), glyphs(g_opt.cache_glyphs) {}
	std::mutex mx;
	Lru<LineOcr> lines;
	Lru<std::vector<Line>> pages;
	Lru<GlyphVal> glyphs;
	std::map<std::string, Spacing> spacing;   // pe model si inaltimea literei x („deu:14”)
	static std::string spacing_key(const std::string &model, int xh) { return model + ":" + std::to_string(xh); }
	// ingustimea scrisului (mediana latime / inaltime a literelor), pe model si inaltimea randului; medie alunecatoare
	std::map<std::string, double> aspect;
	bool get_aspect(const std::string &k, double &v)
	{
		std::lock_guard<std::mutex> l(mx);
		auto it = aspect.find(k);
		if (it == aspect.end())
			return false;
		v = it->second;
		return true;
	}
	void put_aspect(const std::string &k, double v)
	{
		std::lock_guard<std::mutex> l(mx);
		auto it = aspect.find(k);
		if (it == aspect.end())
		{
			if (aspect.size() >= 64)
				aspect.clear();
			aspect[k] = v;
		}
		else
			it->second = 0.7 * it->second + 0.3 * v;
	}
	bool get_line(uint64_t k, LineOcr &v) { std::lock_guard<std::mutex> l(mx); return lines.get(k, v); }
	void put_line(uint64_t k, const LineOcr &v) { std::lock_guard<std::mutex> l(mx); lines.put(k, v); }
	bool get_page(uint64_t k, std::vector<Line> &v) { std::lock_guard<std::mutex> l(mx); return pages.get(k, v); }
	void put_page(uint64_t k, const std::vector<Line> &v) { std::lock_guard<std::mutex> l(mx); pages.put(k, v); }
	size_t size() { std::lock_guard<std::mutex> l(mx); return lines.size(); }
	size_t glyph_count() { std::lock_guard<std::mutex> l(mx); return glyphs.size(); }

	// Dupa un rand citit de tesseract: in fiecare cuvant cu tot atatea grupe cate litere, grupele se leaga de litere
	// dupa ordine; fiecare grupa citita sigur se tine minte; distantele dintre grupele vecine ale aceluiasi cuvant si
	// dintre cuvinte, la fel.
	void learn(const std::string &model, const std::vector<uint8_t> &crop, int cw, int r0, int r1,
		const std::vector<Sym> &syms, int line_conf)
	{
		if (syms.empty() || line_conf < 80)
			return;
		std::vector<Grupa> gr;
		int base = 0, medh = 1;
		if (!glyph_groups(crop, cw, r0, r1, model, gr, base, medh))
			return;
		// grupa i -> litera (indicele in syms), -1 = nelegata
		std::vector<int> la(gr.size(), -1);
		const int cuvinte = syms.back().word + 1;
		for (int w = 0; w < cuvinte; ++w)
		{
			std::vector<int> s_w, g_w;
			for (size_t k = 0; k < syms.size(); ++k)
				if (syms[k].word == w)
					s_w.push_back((int)k);
			if (s_w.empty())
				continue;
			const int wx0 = syms[s_w[0]].wx0, wx1 = syms[s_w[0]].wx1;
			for (size_t i = 0; i < gr.size(); ++i)
			{
				const int c2 = gr[i].x0 + gr[i].x1;   // de doua ori mijlocul
				if (2 * wx0 <= c2 && c2 < 2 * wx1)
					g_w.push_back((int)i);
			}
			if (g_w.size() != s_w.size())
				continue;
			for (size_t j = 0; j < g_w.size(); ++j)
				if (la[g_w[j]] == -1)
					la[g_w[j]] = s_w[j];
				else
					la[g_w[j]] = -2;                  // in doua cuvinte: nesigura
		}
		for (int &x : la)
			if (x == -2)
				x = -1;
		std::lock_guard<std::mutex> l(mx);
		for (size_t i = 0; i < gr.size(); ++i)
		{
			if (la[i] < 0)
				continue;
			const Sym &s = syms[la[i]];
			if (s.conf < GLYPH_MIN_CONF || s.text.empty() || s.text == " ")
				continue;
			GlyphVal v;
			if (glyphs.get(gr[i].key, v))
			{
				if (v.text != s.text)
					v.ambiguous = true;
				v.seen++;
				v.conf = std::min(v.conf, s.conf);
			}
			else
			{
				v.text = s.text;
				v.conf = s.conf;
				v.seen = 1;
			}
			glyphs.put(gr[i].key, v);
		}
		std::vector<int> hx;
		for (size_t i = 0; i < gr.size(); ++i)
			if (la[i] >= 0 && litera_x(syms[la[i]].text))
				hx.push_back(gr[i].y1 - gr[i].y0);
		const int xh = x_height_of(hx);
		if (xh <= 0)
			return;
		Spacing &sp = spacing[spacing_key(model, xh)];
		bool are = false;
		for (size_t i = 0; i + 1 < gr.size(); ++i)
		{
			if (la[i] < 0 || la[i + 1] < 0 || la[i] == la[i + 1])
				continue;
			const double r = (double)(gr[i + 1].x0 - gr[i].x1) / xh;
			if (syms[la[i]].word == syms[la[i + 1]].word)
				sp.max_intra = std::max(sp.max_intra, r);
			else
				sp.min_inter = std::min(sp.min_inter, r);
			are = true;
		}
		if (are)
			sp.lines++;
	}

	// Randul compus din glife, fara tesseract; false cand o grupa nu e stiuta sigur sau o distanta nu e limpede.
	bool compose(const std::string &model, const std::vector<uint8_t> &crop, int cw, int r0, int r1, bool ro_fix,
		bool want_words, LineOcr &lo)
	{
		std::vector<Grupa> gr;
		int base = 0, medh = 1;
		if (!glyph_groups(crop, cw, r0, r1, model, gr, base, medh))
			return false;
		std::vector<GlyphVal> val(gr.size());
		std::vector<bool> spatiu(gr.size(), false);   // spatiu inaintea grupei i
		int xh = 0;
		{
			std::lock_guard<std::mutex> l(mx);
			std::vector<int> hx;
			for (size_t i = 0; i < gr.size(); ++i)
			{
				GlyphVal v;
				if (glyphs.get(gr[i].key, v) && !v.ambiguous && litera_x(v.text))
					hx.push_back(gr[i].y1 - gr[i].y0);
			}
			xh = x_height_of(hx);
			auto it = xh > 0 ? spacing.find(spacing_key(model, xh)) : spacing.end();
			if (it == spacing.end() || it->second.lines < 2 || it->second.max_intra < 0 ||
				it->second.max_intra >= it->second.min_inter)
			{
				g_stats.gm_spacing++;
				if (getenv("HDS_OCR_DEPANARE"))
					logv("glife: distante lipsa pentru %s xh=%d (%zu grupe, %zu litere x)", model.c_str(), xh, gr.size(),
						hx.size());
				return false;
			}
			const Spacing sp = it->second;
			for (size_t i = 0; i < gr.size(); ++i)
			{
				if (!glyphs.get(gr[i].key, val[i]))
				{
					g_stats.gm_unknown++;
					return false;
				}
				if (val[i].ambiguous || val[i].conf < GLYPH_MIN_CONF)
				{
					g_stats.gm_ambiguous++;
					return false;
				}
				if (val[i].seen < GLYPH_MIN_SEEN)
				{
					g_stats.gm_seen++;
					return false;
				}
				if (i == 0)
					continue;
				const double r = (double)(gr[i].x0 - gr[i - 1].x1) / xh;
				if (r >= sp.min_inter)
					spatiu[i] = true;
				else if (r > sp.max_intra)
				{
					g_stats.gm_gap++;
					return false;
				}
			}
		}
		std::string text;
		int conf = 100, top = base, jos = base;
		std::vector<Word> words;
		Word w;
		std::string wt;
		int wx0 = 0, wx1 = 0, wy0 = 0, wy1 = 0, wc = 100;
		auto inchide = [&]() {
			if (wt.empty())
				return;
			w.x = (int16_t)wx0; w.y = (int16_t)wy0;
			w.w = (uint16_t)std::max(1, wx1 - wx0); w.h = (uint16_t)std::max(1, wy1 - wy0);
			w.confidence = (uint8_t)wc;
			w.text = ro_fix ? ro_comma(fix_bar(wt)) : fix_bar(wt);
			words.push_back(w);
			wt.clear();
		};
		for (size_t i = 0; i < gr.size(); ++i)
		{
			if (spatiu[i])
			{
				text += ' ';
				inchide();
			}
			if (wt.empty())
			{
				wx0 = gr[i].x0; wx1 = gr[i].x1; wy0 = gr[i].y0; wy1 = gr[i].y1; wc = 100;
			}
			wx1 = std::max(wx1, gr[i].x1); wy0 = std::min(wy0, gr[i].y0); wy1 = std::max(wy1, gr[i].y1);
			wc = std::min(wc, val[i].conf);
			wt += val[i].text;
			text += val[i].text;
			conf = std::min(conf, val[i].conf);
			top = std::min(top, gr[i].y0);
			jos = std::max(jos, gr[i].y1);
		}
		inchide();
		text = fix_bar(trim(text));
		if (ro_fix)
			text = ro_comma(text);
		if (text.empty())
			return false;
		lo = LineOcr();
		lo.ok = true;
		lo.text = text;
		lo.conf = conf;
		lo.low = false;
		lo.baseline = base;
		lo.x_height = xh;
		lo.ascender = base - top;
		lo.descender = jos - base;
		if (want_words)
			lo.words = words;
		return true;
	}
};

// ------------------------------------------------------------------------------------------------
// scrisul ingust si a doua citire

static const int ASPECT_MIN_GRUPE = 8;   // atatea litere pe cerere ca masura ei sa fie de crezut
static const int RECITIRE_PRAG = 70;     // ca in client: un cuvant cu litere sub atat face randul nesigur
static const int RECITIRE_PRAG_SEMNE = 40;

// cat de ingust e scrisul cererii: mediana latime / inaltime a grupelor de cerneala (8 vecini) inalte cel putin cat 0,4
// din banda lor (literele; punctele, virgulele si accentele raman deoparte); 0 = nicio litera. *n = cate grupe.
static double region_aspect(const Request &rq, const Analysis &an, const std::vector<Band> &bands, int *n)
{
	std::vector<double> rap;
	std::vector<uint8_t> vazut;
	std::vector<int> st;
	for (const Band &bd : bands)
	{
		const int w = bd.x1 - bd.x0, h = bd.y1 - bd.y0;
		if (w <= 0 || h <= 0)
			continue;
		vazut.assign((size_t)w * h, 0);
		auto cerneala = [&](int x, int y) {
			return an.lut[rq.pixels[(size_t)(bd.y0 + y) * rq.width + bd.x0 + x]] < 128;
		};
		for (int y = 0; y < h; ++y)
			for (int x = 0; x < w; ++x)
			{
				if (vazut[(size_t)y * w + x] || !cerneala(x, y))
					continue;
				int x0 = x, x1 = x, y0 = y, y1 = y;
				vazut[(size_t)y * w + x] = 1;
				st.assign(1, y * w + x);
				while (!st.empty())
				{
					const int k = st.back();
					st.pop_back();
					const int cx = k % w, cy = k / w;
					x0 = std::min(x0, cx); x1 = std::max(x1, cx); y0 = std::min(y0, cy); y1 = std::max(y1, cy);
					for (int dy = -1; dy <= 1; ++dy)
						for (int dx = -1; dx <= 1; ++dx)
						{
							const int nx = cx + dx, ny = cy + dy;
							if (nx < 0 || ny < 0 || nx >= w || ny >= h || vazut[(size_t)ny * w + nx] || !cerneala(nx, ny))
								continue;
							vazut[(size_t)ny * w + nx] = 1;
							st.push_back(ny * w + nx);
						}
				}
				const int gw = x1 - x0 + 1, gh = y1 - y0 + 1;
				if (gh >= 0.4 * h && gw >= 2)
					rap.push_back((double)gw / gh);
			}
	}
	*n = (int)rap.size();
	if (rap.empty())
		return 0;
	std::nth_element(rap.begin(), rap.begin() + rap.size() / 2, rap.end());
	return rap[rap.size() / 2];
}

// un cuvant cu litere sau cifre (ca _areLitere din client): ASCII alfanumeric sau o litera din afara ASCII (UTF-8 cu
// primul octet C3..DF, E0, E1 sau de la E3 incolo; C2 si E2 sunt semne: ghilimele, linia lunga, punctele de suspensie)
static bool are_litere(const std::string &t)
{
	for (size_t i = 0; i < t.size(); ++i)
	{
		const unsigned char c = (unsigned char)t[i];
		if (c < 0x80 ? isalnum(c) != 0 : ((c >= 0xC3 && c <= 0xDF) || c == 0xE0 || c == 0xE1 || c >= 0xE3))
			return true;
	}
	return false;
}

// randul are un cuvant nesigur (aceleasi praguri ca decizia clientului de dinainte)
static bool rand_nesigur(const LineOcr &lo)
{
	for (const Word &w : lo.words)
		if (w.confidence < (are_litere(w.text) ? RECITIRE_PRAG : RECITIRE_PRAG_SEMNE))
			return true;
	return false;
}

// increderea medie a cuvintelor cu litere (0 fara niciunul)
static double medie_litere(const LineOcr &lo)
{
	double s = 0;
	int n = 0;
	for (const Word &w : lo.words)
		if (are_litere(w.text))
		{
			s += w.confidence;
			n++;
		}
	return n ? s / n : 0;
}

class Recognizer
{
public:
	explicit Recognizer(Memory &mem) : m_mem(mem) {}

	// cached_only: numai din memorie (firul principal, la primire). Cand un rand nu e in memorie, *missing = true si
	// rezultatul nu se foloseste (cererea merge la firul de lucru); nimic nu se numara de doua ori.
	Result run(Job &job, bool cached_only = false, bool *missing = nullptr)
	{
		Result res;
		const Request &rq = job.rq;
		res.request_id = rq.request_id;
		res.generation = rq.generation;
		std::string model = resolve_model(rq.lang);
		if (model.empty())
		{
			res.status = ST_NO_MODEL;
			return finish(job, res);
		}
		memcpy(res.model, model.data(), std::min(model.size(), sizeof(res.model)));
		const bool use_cache = !(rq.flags & FLAG_NO_CACHE) && !g_opt.bench_no_cache;
		const bool cedilla = (rq.flags & FLAG_KEEP_CEDILLA) != 0;
		// pagina intreaga deja vazuta (DVB retrimite aceeasi pagina des)
		uint64_t pk = FNV_START;
		pk = fnv1a(pk, model.data(), model.size());
		uint32_t fl = rq.flags & (FLAG_KEEP_CEDILLA | FLAG_NO_WORDS);
		pk = fnv1a(pk, &fl, sizeof(fl));
		pk = fnv1a(pk, &rq.width, sizeof(rq.width));
		pk = fnv1a(pk, &rq.height, sizeof(rq.height));
		pk = fnv1a(pk, rq.palette.data(), rq.palette.size() * 4);
		pk = fnv1a(pk, rq.pixels.data(), rq.pixels.size());
		std::vector<Line> cached;
		if (use_cache && m_mem.get_page(pk, cached))
		{
			g_stats.page_hits++;
			for (Line l : cached)
			{
				l.x += rq.x; l.y += rq.y; l.baseline += rq.y;
				for (auto &w : l.words) { w.x += rq.x; w.y += rq.y; }
				l.flags |= LF_CACHED;
				res.lines.push_back(l);
			}
			res.cache_hits = (uint16_t)res.lines.size();
			return finish(job, res);
		}
		Analysis an;
		analyze(rq, an);
		std::vector<Band> bands = find_bands(rq, an);
		double units = 0;
		for (const Band &b : bands)
			units += band_units(b.x0, b.x1, b.y0, b.y1);
		const double k = stretch_for(model, rq, an, bands, !cached_only);
		int64_t run_deadline = 0;   // pus la primul rand de recunoscut, dupa incarcarea modelului
		tesseract::TessBaseAPI *api = nullptr;
		bool complete = true;
		long hits = 0;
		std::vector<Line> rel;   // relative la regiune, pentru memoria de pagini
		for (size_t bi = 0; bi < bands.size(); ++bi)
		{
			const Band &bd = bands[bi];
			Line L;
			// culorile randului: umplutura = intrarea "cerneala" cea mai folosita in banda
			std::vector<long> cnt(257, 0);
			for (int y = bd.y0; y < bd.y1; ++y)
			{
				const uint8_t *p = rq.pixels.data() + (size_t)y * rq.width;
				for (int x = bd.x0; x < bd.x1; ++x)
					cnt[p[x] < an.n ? p[x] : 256]++;
			}
			// (culoarea cea mai folosita si mai "plina" din cerneala randului; un rand verde intr-o regiune
			// cu text alb isi primeste propria masca, altfel ar iesi gri)
			int fillk = an.fill;
			double bestc = -1;
			for (int i = 0; i < an.n; ++i)
				if (!an.e[i].bg && i != an.outline && an.lut[i] < 160 && cnt[i] > 0)
				{
					double v = (double)cnt[i] * (255 - an.lut[i]);
					if (v > bestc)
					{
						bestc = v;
						fillk = i;
					}
				}
			std::vector<uint8_t> lut = an.lut;
			if (fillk >= 0 && fillk != an.fill)
			{
				double hi = an.inverted ? an.e[fillk].lw : an.e[fillk].lb;
				if (std::fabs(hi - an.ref) >= 30)
					build_lut(an, hi, lut);
			}
			auto argb = [&](int i) -> uint32_t {
				if (i < 0 || i >= an.n) return 0;
				return rq.palette[i];
			};
			L.fill = argb(fillk);
			L.outline = an.has_outline ? argb(an.outline) : 0;
			L.box = an.box >= 0 ? argb(an.box) : 0;
			if (an.inverted)
				L.flags |= LF_INVERTED;
			// grosimea conturului: pixeli de contur / pixeli de margine ai umpluturii
			if (an.has_outline)
			{
				long olc = 0, edge = 0;
				int y0 = std::max(0, bd.y0 - 8), y1 = std::min((int)rq.height, bd.y1 + 8);
				int x0 = std::max(0, bd.x0 - 8), x1 = std::min((int)rq.width, bd.x1 + 8);
				for (int y = y0; y < y1; ++y)
					for (int x = x0; x < x1; ++x)
					{
						int v = rq.pixels[(size_t)y * rq.width + x];
						if (v < an.n && !an.e[v].bg && lut[v] == 255)
							olc++;   // conturul si treptele lui semitransparente
						else if (v < an.n && lut[v] < 128 && x > 0 && y > 0 && x < rq.width - 1 && y < rq.height - 1)
						{
							const uint8_t *p = rq.pixels.data() + (size_t)y * rq.width + x;
							auto ink = [&](int q) { return q < an.n && lut[q] < 128; };
							if (!ink(p[-1]) || !ink(p[1]) || !ink(p[-(int)rq.width]) || !ink(p[rq.width]))
								edge++;
						}
					}
				if (edge > 0)
					L.outline_px = (uint8_t)std::min(255L, std::lround((double)olc / edge));
			}
			// decupajul: banda + margine (conturul intra in dreptunghiul intors)
			int pad = 6 + L.outline_px;
			int cx0 = bd.x0 - pad, cy0 = bd.y0 - pad, cx1 = bd.x1 + pad, cy1 = bd.y1 + pad;
			int cw = cx1 - cx0, ch = cy1 - cy0;
			std::vector<uint8_t> crop((size_t)cw * ch, 255);
			// numai randurile benzii: cerneala randurilor vecine (codite, accente) ramane alba
			for (int y = bd.y0; y < bd.y1; ++y)
				for (int x = std::max(0, cx0); x < std::min((int)rq.width, cx1); ++x)
					crop[(size_t)(y - cy0) * cw + (x - cx0)] = lut[rq.pixels[(size_t)y * rq.width + x]];
			// dreptunghiul intors: umplutura + contur, in regiune
			{
				int ox = L.outline_px;
				int rx0 = std::max(0, bd.x0 - ox), ry0 = std::max(0, bd.y0 - ox);
				int rx1 = std::min((int)rq.width, bd.x1 + ox), ry1 = std::min((int)rq.height, bd.y1 + ox);
				L.x = (int16_t)rx0; L.y = (int16_t)ry0; L.w = (uint16_t)(rx1 - rx0); L.h = (uint16_t)(ry1 - ry0);
			}
			int bh = bd.y1 - bd.y0;
			int s = g_opt.scale > 0 ? g_opt.scale : (int)std::lround((double)g_opt.target_band / std::max(1, bh));
			s = std::max(1, std::min(4, s));
			uint64_t lk = FNV_START;
			lk = fnv1a(lk, model.data(), model.size());
			lk = fnv1a(lk, &fl, sizeof(fl));
			lk = fnv1a(lk, &s, sizeof(s));
			const int k100 = (int)std::lround(k * 100);   // acelasi rand intins altfel (alt scris tinut minte) e alt rand
			lk = fnv1a(lk, &k100, sizeof(k100));
			lk = fnv1a(lk, &cw, sizeof(cw));
			lk = fnv1a(lk, &ch, sizeof(ch));
			lk = fnv1a(lk, crop.data(), crop.size());
			LineOcr lo;
			bool hit = use_cache && m_mem.get_line(lk, lo);
			const bool ro_fix = model == "ron" && !cedilla;
			if (hit)
			{
				hits++;
				res.cache_hits++;
				L.flags |= LF_CACHED;
			}
			else if (use_cache && g_opt.glyphs && m_mem.compose(model, crop, cw, bd.y0 - cy0, bd.y1 - cy0, ro_fix,
				!(rq.flags & FLAG_NO_WORDS), lo))
			{
				// un rand nou, facut numai din litere deja citite: fara tesseract (si pe firul principal)
				g_stats.glyph_lines++;
				m_mem.put_line(lk, lo);
			}
			else if (cached_only)
			{
				if (missing)
					*missing = true;
				return res;
			}
			else
			{
				if (job.cancelled.load() || job.deadline <= now_us())
				{
					// pagina fara folos (termenul clientului a trecut) sau anulata: nimic de recunoscut
					L.flags |= LF_TIMEOUT;
					complete = false;
					if (!job.cancelled.load())
						g_stats.expired++;
				}
				else
				{
					if (!api)
						api = m_engines.get(model);
					if (!api)
					{
						res.status = ST_ERROR;
						return finish(job, res);
					}
					int64_t t0 = now_us();
					if (!run_deadline)
						run_deadline = t0 + (int64_t)g_speed.budget_ms(units) * 1000;
					const bool by_budget = run_deadline < job.deadline;
					int64_t left_ms = ((by_budget ? run_deadline : job.deadline) - t0) / 1000;
					if (left_ms <= 0)
					{
						L.flags |= LF_TIMEOUT;
						complete = false;
						(by_budget ? g_stats.budget_timeouts : g_stats.expired)++;
					}
					else
					{
						std::vector<Sym> syms;
						const bool cu_glife = use_cache && g_opt.glyphs;
						lo = recognize_line(api, job, crop, cw, ch, s, bh, k, (int)left_ms, ro_fix,
							!(rq.flags & FLAG_NO_WORDS), bi, cu_glife ? &syms : nullptr);
						const int64_t t_prima = now_us();
						if (lo.ok && k > 1.001)
							g_stats.stretched++;
						// randul nesigur: inca o citire cu cealalta pregatire, daca mai e timp pentru ea (cat a durat
						// prima, dupa latimea imaginii); ramane citirea cu increderea medie mai mare
						if (lo.ok && g_opt.reread && rand_nesigur(lo) && !job.cancelled.load())
						{
							const double k2 = k > 1.001 ? 1.0 : g_opt.reread_k;
							const int64_t ramas_ms = ((by_budget ? run_deadline : job.deadline) - t_prima) / 1000;
							const double cat = (t_prima - t0) / 1000.0 * k2 / k;
							if (ramas_ms > cat * 1.2 + 5)
							{
								std::vector<Sym> syms2;
								LineOcr lo2 = recognize_line(api, job, crop, cw, ch, s, bh, k2, (int)ramas_ms, ro_fix,
									!(rq.flags & FLAG_NO_WORDS), bi, cu_glife ? &syms2 : nullptr);
								g_stats.rereads++;
								if (lo2.ok && medie_litere(lo2) > medie_litere(lo))
								{
									lo = lo2;
									syms.swap(syms2);
									g_stats.rereads_better++;
								}
							}
						}
						if (lo.ok && !syms.empty())
							m_mem.learn(model, crop, cw, bd.y0 - cy0, bd.y1 - cy0, syms, lo.low ? 0 : lo.conf);
						g_stats.lines++;
						if (!lo.ok)
						{
							L.flags |= LF_TIMEOUT;
							complete = false;
							if (!job.cancelled.load())
								(by_budget ? g_stats.budget_timeouts : g_stats.expired)++;
						}
						else
						{
							// viteza: numai prima citire (a doua e rara si ar umfla ms pe unitate)
							g_speed.add((t_prima - t0) / 1000.0, band_units(bd.x0, bd.x1, bd.y0, bd.y1));
							if (use_cache)
								m_mem.put_line(lk, lo);
						}
					}
				}
			}
			if (lo.ok)
			{
				L.text = lo.text;
				L.confidence = (uint8_t)std::max(0, std::min(100, lo.conf));
				if (lo.low)
					L.flags |= LF_LOW_CONF;
				L.baseline = (int16_t)(lo.baseline >= 0 ? cy0 + lo.baseline : L.y + L.h);
				L.x_height = (uint16_t)lo.x_height;
				L.ascender = (uint16_t)lo.ascender;
				L.descender = (uint16_t)lo.descender;
				for (Word w : lo.words)
				{
					w.x = (int16_t)(w.x + cx0);
					w.y = (int16_t)(w.y + cy0);
					L.words.push_back(w);
				}
			}
			else
				L.baseline = (int16_t)(L.y + L.h);
			if (L.text.empty() && lo.ok)
				continue;   // banda fara text recunoscut (zgomot)
			rel.push_back(L);
		}
		g_stats.line_hits += hits;
		if (complete && use_cache)
			m_mem.put_page(pk, rel);
		for (Line l : rel)
		{
			l.x += rq.x; l.y += rq.y; l.baseline += rq.y;
			for (auto &w : l.words) { w.x += rq.x; w.y += rq.y; }
			res.lines.push_back(l);
		}
		if (!complete)
			res.status = job.cancelled.load() ? ST_CANCELLED : ST_TIMEOUT;
		return finish(job, res);
	}

	std::vector<std::string> loaded() const { return m_engines.loaded(); }
	size_t cache_size() const { return m_mem.size(); }

private:
	Result &finish(Job &job, Result &res)
	{
		if (res.status == ST_TIMEOUT) g_stats.timeouts++;
		if (res.status == ST_CANCELLED) g_stats.cancelled++;
		res.elapsed_us = (uint32_t)std::min<int64_t>(0xFFFFFFFF, now_us() - job.t_recv);
		return res;
	}

	// intinderea orizontala a randurilor cererii (1 = deloc): dupa ingustimea scrisului masurata pe cerere, sau, cand
	// cererea are prea putine litere, dupa cea tinuta minte pentru model si inaltimea randurilor; tine_minte = masura
	// cererii intra in memorie (numai firul de lucru, ca o cerere sa nu se numere de doua ori)
	double stretch_for(const std::string &model, const Request &rq, const Analysis &an, const std::vector<Band> &bands,
		bool tine_minte)
	{
		if (!g_opt.stretch || bands.empty())
			return 1.0;
		int n = 0;
		const double asp = region_aspect(rq, an, bands, &n);
		std::vector<int> inaltimi;
		for (const Band &b : bands)
			inaltimi.push_back(b.y1 - b.y0);
		std::nth_element(inaltimi.begin(), inaltimi.begin() + inaltimi.size() / 2, inaltimi.end());
		const std::string cheie = model + ":" + std::to_string(inaltimi[inaltimi.size() / 2] / 8);
		double folosit = 0;
		if (n >= ASPECT_MIN_GRUPE)
		{
			folosit = asp;
			if (tine_minte)
				m_mem.put_aspect(cheie, asp);
		}
		else if (!m_mem.get_aspect(cheie, folosit) && n >= 3)
			folosit = asp;
		if (folosit <= 0 || folosit >= g_opt.stretch_narrow)
			return 1.0;
		double k = std::min(g_opt.stretch_max, std::max(1.0, g_opt.stretch_target / folosit));
		// pasi de 0,05: acelasi scris da aceeasi intindere (si acelasi rand in memoria randurilor)
		k = std::round(k * 20) / 20;
		logv("scris ingust: %.3f (%d litere, %s), intindere %.2f", folosit, n, n >= ASPECT_MIN_GRUPE ? "cererea" : "memoria",
			k);
		return k;
	}

	// k: intinderea orizontala (1 = deloc); cuvintele si literele se intorc in coordonatele decupajului neintins
	LineOcr recognize_line(tesseract::TessBaseAPI *api, Job &job, const std::vector<uint8_t> &crop, int cw, int ch,
		int s, int bh, double k, int left_ms, bool ro_fix, bool want_words, size_t line_no,
		std::vector<Sym> *syms = nullptr)
	{
		LineOcr lo;
		std::vector<uint8_t> img;
		const std::vector<uint8_t> *use = &crop;
		if (s > 1)
		{
			upscale(crop, cw, ch, s, img);
			use = &img;
		}
		int W = cw * s, H = ch * s;
		std::vector<uint8_t> intins;
		if (k > 1.001)
		{
			// intinderea pe orizontala, liniara (randurile raman cum sunt)
			const int W2 = (int)std::lround(W * k);
			intins.resize((size_t)W2 * H);
			for (int X = 0; X < W2; ++X)
			{
				const double fx = (X + 0.5) / k - 0.5;
				const int x0 = (int)std::floor(fx);
				const double tx = fx - x0;
				const int xa = std::min(W - 1, std::max(0, x0)), xb = std::min(W - 1, std::max(0, x0 + 1));
				for (int Y = 0; Y < H; ++Y)
				{
					const uint8_t *r = use->data() + (size_t)Y * W;
					intins[(size_t)Y * W2 + X] = (uint8_t)std::lround((1 - tx) * r[xa] + tx * r[xb]);
				}
			}
			use = &intins;
			W = W2;
		}
		// marirea pe orizontala: a lui s, plus intinderea
		const double sx = s * (k > 1.001 ? k : 1.0);
		if (!g_opt.dump_dir.empty())
		{
			char name[512];
			snprintf(name, sizeof(name), "%s/r%u-l%zu.pgm", g_opt.dump_dir.c_str(), job.rq.request_id, line_no);
			FILE *f = fopen(name, "wb");
			if (f)
			{
				fprintf(f, "P5\n%d %d\n255\n", W, H);
				fwrite(use->data(), 1, use->size(), f);
				fclose(f);
			}
		}
		api->SetPageSegMode((tesseract::PageSegMode)g_opt.psm);
		api->SetImage(use->data(), W, H, 1, W);
		int dpi = (int)std::lround(std::min(1200.0, std::max(70.0, 7.2 * bh * s)));
		api->SetSourceResolution(dpi);
		tesseract::ETEXT_DESC mon;
		mon.cancel = cancel_cb;
		mon.cancel_this = &job;
		mon.set_deadline_msecs(std::max(1, left_ms));
		int rc = api->Recognize(&mon);
		if (rc != 0 || job.cancelled.load() || mon.deadline_exceeded())
		{
			api->Clear();
			return lo;
		}
		char *t = api->GetUTF8Text();
		std::string text = t ? trim(t) : std::string();
		delete[] t;
		text = fix_bar(text);
		if (ro_fix)
			text = ro_comma(text);
		lo.text = text;
		lo.ok = true;
		std::unique_ptr<tesseract::ResultIterator> it(api->GetIterator());
		double csum = 0;
		int cn = 0;
		bool first_line = true;
		// fara niciun cuvant (tesseract nu a gasit text in banda) randul iteratorului e nul si RowAttributes
		// cade (SIGSEGV). Probat in cloud 25.09 cu o regiune de doua culori „III" (DejaVu 40 px, fara margine).
		if (it && !it->Empty(tesseract::RIL_WORD))
		{
			do
			{
				if (first_line)
				{
					int x1, y1, x2, y2;
					if (it->Baseline(tesseract::RIL_TEXTLINE, &x1, &y1, &x2, &y2))
						lo.baseline = (int)std::lround((y1 + y2) / 2.0 / s);
					float rh = 0, de = 0, as = 0;
					it->RowAttributes(&rh, &de, &as);
					double xh = (double)rh - as + de;   // row_height = x_height + ascenders - descenders
					lo.x_height = (int)std::lround(std::max(0.0, xh / s));
					lo.ascender = (int)std::lround(std::max(0.0, (xh + as) / s));
					lo.descender = (int)std::lround(std::max(0.0, -(double)de / s));
					first_line = false;
				}
				char *wt = it->GetUTF8Text(tesseract::RIL_WORD);
				if (!wt)
					continue;
				std::string ws = trim(wt);
				delete[] wt;
				if (ws.empty())
					continue;
				float c = it->Confidence(tesseract::RIL_WORD);
				csum += c;
				cn++;
				if (c < 50)
					lo.low = true;
				if (want_words)
				{
					int l, tp, r, b;
					Word w;
					if (it->BoundingBox(tesseract::RIL_WORD, &l, &tp, &r, &b))
					{
						w.x = (int16_t)(l / sx);
						w.y = (int16_t)(tp / s);
						w.w = (uint16_t)std::max(1, (int)std::ceil((r - l) / sx));
						w.h = (uint16_t)std::max(1, (b - tp + s - 1) / s);
					}
					w.confidence = (uint8_t)std::max(0, std::min(100, (int)std::lround(c)));
					w.text = ro_fix ? ro_comma(fix_bar(ws)) : fix_bar(ws);
					lo.words.push_back(w);
				}
			} while (it->Next(tesseract::RIL_WORD));
		}
		lo.conf = cn ? (int)std::lround(csum / cn) : 0;
		// literele, pentru memoria glifelor: marginile (in decupaj), textul, increderea si al catelea cuvant
		if (syms && cn)
		{
			std::unique_ptr<tesseract::ResultIterator> si(api->GetIterator());
			int cuv = -1, wx0 = 0, wx1 = 0;
			if (si && !si->Empty(tesseract::RIL_SYMBOL))
			{
				do
				{
					int l, tp, r, b;
					if (si->IsAtBeginningOf(tesseract::RIL_WORD))
					{
						cuv++;
						wx0 = wx1 = 0;
						if (si->BoundingBox(tesseract::RIL_WORD, &l, &tp, &r, &b))
						{
							wx0 = (int)(l / sx);
							wx1 = (int)std::ceil(r / sx);
						}
					}
					char *st = si->GetUTF8Text(tesseract::RIL_SYMBOL);
					if (st && wx1 > wx0)
					{
						Sym y;
						y.text = st;
						y.conf = (int)std::lround(si->Confidence(tesseract::RIL_SYMBOL));
						y.word = cuv;
						y.wx0 = wx0;
						y.wx1 = wx1;
						syms->push_back(y);
					}
					delete[] st;
				} while (si->Next(tesseract::RIL_SYMBOL));
			}
		}
		api->Clear();
		return lo;
	}

	Engines m_engines;
	Memory &m_mem;
};

// ------------------------------------------------------------------------------------------------
// JSON (numai pentru PONG si pentru proba fara socket)

static std::string jstr(const std::string &s)
{
	std::string o = "\"";
	for (unsigned char c : s)
	{
		if (c == '"' || c == '\\') { o += '\\'; o += (char)c; }
		else if (c < 0x20) { char b[8]; snprintf(b, sizeof(b), "\\u%04x", c); o += b; }
		else o += (char)c;
	}
	return o + "\"";
}

static std::string result_json(const Result &r)
{
	char b[256];
	std::string o;
	snprintf(b, sizeof(b), "{\"request_id\":%u,\"status\":%u,\"elapsed_us\":%u,\"model\":", r.request_id, r.status, r.elapsed_us);
	o += b;
	o += jstr(std::string(r.model, strnlen(r.model, sizeof(r.model))));
	snprintf(b, sizeof(b), ",\"cache_hits\":%u,\"lines\":[", r.cache_hits);
	o += b;
	for (size_t i = 0; i < r.lines.size(); ++i)
	{
		const Line &l = r.lines[i];
		snprintf(b, sizeof(b), "%s{\"rect\":[%d,%d,%u,%u],\"baseline\":%d,\"x_height\":%u,\"ascender\":%u,\"descender\":%u,"
			"\"fill\":\"%08X\",\"outline\":\"%08X\",\"box\":\"%08X\",\"outline_px\":%u,\"conf\":%u,\"flags\":%u,\"text\":",
			i ? "," : "", l.x, l.y, l.w, l.h, l.baseline, l.x_height, l.ascender, l.descender, l.fill, l.outline, l.box,
			l.outline_px, l.confidence, l.flags);
		o += b;
		o += jstr(l.text);
		o += ",\"words\":[";
		for (size_t k = 0; k < l.words.size(); ++k)
		{
			const Word &w = l.words[k];
			snprintf(b, sizeof(b), "%s{\"rect\":[%d,%d,%u,%u],\"conf\":%u,\"text\":", k ? "," : "", w.x, w.y, w.w, w.h, w.confidence);
			o += b;
			o += jstr(w.text);
			o += "}";
		}
		o += "]}";
	}
	return o + "]}";
}

// ------------------------------------------------------------------------------------------------
// proba fara socket: fisiere cu cereri RECOGNIZE intregi (antet + corp), rezultat JSON pe stdout

static bool read_file(const std::string &path, std::vector<uint8_t> &out)
{
	FILE *f = fopen(path.c_str(), "rb");
	if (!f)
		return false;
	out.clear();
	uint8_t buf[65536];
	size_t n;
	while ((n = fread(buf, 1, sizeof(buf), f)) > 0)
		out.insert(out.end(), buf, buf + n);
	fclose(f);
	return true;
}

static int run_bench()
{
	Memory mem;
	Recognizer rec(mem);
	int bad = 0;
	for (int rep = 0; rep < g_opt.repeat; ++rep)
		for (const std::string &path : g_opt.bench_files)
		{
			std::vector<uint8_t> data;
			uint16_t type;
			uint32_t len;
			if (!read_file(path, data) || data.size() < HEADER_SIZE || !parse_header(data.data(), type, len) ||
				type != MSG_RECOGNIZE || data.size() != HEADER_SIZE + len)
			{
				loge("fisier gresit: %s", path.c_str());
				bad++;
				continue;
			}
			std::unique_ptr<Job> job(new Job());
			if (!decode_request(data.data() + HEADER_SIZE, len, job->rq))
			{
				loge("cerere gresita: %s", path.c_str());
				bad++;
				continue;
			}
			job->t_recv = now_us();
			int to = job->rq.timeout_ms ? job->rq.timeout_ms : g_opt.default_timeout_ms;
			job->deadline = job->t_recv + (int64_t)to * 1000;
			g_stats.requests++;
			Result r = rec.run(*job);
			printf("{\"file\":%s,\"rep\":%d,\"result\":%s}\n", jstr(path).c_str(), rep, result_json(r).c_str());
			fflush(stdout);
		}
	logv("viteza masurata: %.2f ms pe unitate (%ld randuri); opriri: %ld de timpul de lucru, %ld de termen",
		g_speed.ms_per_unit(), g_speed.samples(), g_stats.budget_timeouts.load(), g_stats.expired.load());
	logv("randuri: %ld cu tesseract, %ld din memoria randurilor, %ld compuse din glife (%zu glife tinute minte)",
		g_stats.lines.load(), g_stats.line_hits.load(), g_stats.glyph_lines.load(), mem.glyph_count());
	logv("randuri necompuse: %ld distantele neinvatate, %ld o grupa necunoscuta, %ld o grupa nesigura, %ld o grupa "
		"vazuta o data, %ld o distanta nelamurita", g_stats.gm_spacing.load(), g_stats.gm_unknown.load(),
		g_stats.gm_ambiguous.load(), g_stats.gm_seen.load(), g_stats.gm_gap.load());
	{
		std::lock_guard<std::mutex> l(mem.mx);
		for (auto &kv : mem.spacing)
			logv("distante %s: litere pana la %.3f, cuvinte de la %.3f (%d randuri)", kv.first.c_str(),
				kv.second.max_intra, kv.second.min_inter, kv.second.lines);
	}
	return bad ? 1 : 0;
}

// ------------------------------------------------------------------------------------------------
// serviciul

static volatile sig_atomic_t g_stop = 0;
static void on_signal(int) { g_stop = 1; }

struct Conn {
	int fd = -1;
	int id = 0;
	std::vector<uint8_t> in;
	std::vector<uint8_t> out;
	size_t out_off = 0;
	bool dead = false;
};

class Server
{
public:
	int run()
	{
		if (!listen_socket())
			return 1;
		if (pipe(m_wake) != 0)
			return 1;
		fcntl(m_wake[0], F_SETFL, O_NONBLOCK);
		fcntl(m_wake[1], F_SETFL, O_NONBLOCK);
		std::thread worker([this] { work(); });
		m_last_req = now_us();
		std::string dirs = g_opt.tessdata;
		for (const std::string &dir : g_opt.tessdata_extra)
			dirs += " " + dir;
		loge("pornit (versiunea %s, tesseract %s), socket %s, modele %s", HDS_OCR_VERSION,
			tesseract::TessBaseAPI::Version(), g_opt.socket_path.c_str(), dirs.c_str());
		while (!g_stop)
		{
			std::vector<pollfd> pf;
			pf.push_back({m_listen, POLLIN, 0});
			pf.push_back({m_wake[0], POLLIN, 0});
			for (auto &c : m_conns)
				pf.push_back({c.fd, (short)(POLLIN | (c.out.size() > c.out_off ? POLLOUT : 0)), 0});
			int r = poll(pf.data(), pf.size(), 1000);
			if (r < 0 && errno != EINTR)
				break;
			if (r > 0)
			{
				if (pf[0].revents & POLLIN)
					accept_all();
				if (pf[1].revents & POLLIN)
				{
					char b[64];
					while (read(m_wake[0], b, sizeof(b)) > 0) {}
				}
				for (size_t i = 2; i < pf.size(); ++i)
				{
					Conn *c = find_fd(pf[i].fd);
					if (!c)
						continue;
					if (pf[i].revents & (POLLIN | POLLHUP | POLLERR))
						read_conn(*c);
					if (!c->dead && (pf[i].revents & POLLOUT))
						write_conn(*c);
				}
			}
			deliver();
			reap();
			if (g_opt.idle_exit_s > 0 && idle() && now_us() - m_last_req > (int64_t)g_opt.idle_exit_s * 1000000)
			{
				loge("nicio cerere de %d s, ies", g_opt.idle_exit_s);
				break;
			}
		}
		{
			std::lock_guard<std::mutex> lk(m_mx);
			m_quit = true;
			if (m_running)
				m_running->cancelled = true;
		}
		m_cv.notify_all();
		worker.join();
		for (auto &c : m_conns)
			close(c.fd);
		close(m_listen);
		unlink(g_opt.socket_path.c_str());
		return 0;
	}

private:
	bool listen_socket()
	{
		std::string lock = g_opt.socket_path + ".lock";
		m_lockfd = open(lock.c_str(), O_RDWR | O_CREAT | O_CLOEXEC, 0600);
		if (m_lockfd < 0 || flock(m_lockfd, LOCK_EX | LOCK_NB) != 0)
		{
			loge("ruleaza deja (zavorul %s e luat)", lock.c_str());
			exit(0);
		}
		sockaddr_un a;
		memset(&a, 0, sizeof(a));
		a.sun_family = AF_UNIX;
		if (g_opt.socket_path.size() >= sizeof(a.sun_path))
		{
			loge("calea socketului e prea lunga");
			return false;
		}
		strcpy(a.sun_path, g_opt.socket_path.c_str());
		unlink(a.sun_path);   // socket ramas de la un proces cazut (zavorul e al nostru)
		m_listen = socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
		mode_t old = umask(077);
		int rb = bind(m_listen, (sockaddr *)&a, sizeof(a));
		umask(old);
		if (m_listen < 0 || rb != 0 || listen(m_listen, 8) != 0)
		{
			loge("nu pot asculta pe %s: %s", a.sun_path, strerror(errno));
			return false;
		}
		return true;
	}

	void accept_all()
	{
		for (;;)
		{
			int fd = accept4(m_listen, nullptr, nullptr, SOCK_NONBLOCK | SOCK_CLOEXEC);
			if (fd < 0)
				break;
			if (m_conns.size() >= 16)
			{
				close(fd);
				continue;
			}
			Conn c;
			c.fd = fd;
			c.id = ++m_next_id;
			m_conns.push_back(std::move(c));
			logv("conexiune %d", m_next_id);
		}
	}

	Conn *find_fd(int fd)
	{
		for (auto &c : m_conns)
			if (c.fd == fd)
				return &c;
		return nullptr;
	}
	Conn *find_id(int id)
	{
		for (auto &c : m_conns)
			if (c.id == id && !c.dead)
				return &c;
		return nullptr;
	}

	void read_conn(Conn &c)
	{
		uint8_t buf[65536];
		for (;;)
		{
			ssize_t n = recv(c.fd, buf, sizeof(buf), 0);
			if (n > 0)
			{
				c.in.insert(c.in.end(), buf, buf + n);
				if (c.in.size() > HEADER_SIZE + MAX_PAYLOAD)
				{
					c.dead = true;
					return;
				}
				continue;
			}
			if (n == 0 || (errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR))
				c.dead = true;
			break;
		}
		// mesaje intregi
		size_t off = 0;
		while (c.in.size() - off >= HEADER_SIZE)
		{
			uint16_t type;
			uint32_t len;
			if (!parse_header(c.in.data() + off, type, len))
			{
				c.dead = true;
				break;
			}
			if (c.in.size() - off < HEADER_SIZE + len)
				break;
			handle(c, type, c.in.data() + off + HEADER_SIZE, len);
			off += HEADER_SIZE + len;
		}
		if (off)
			c.in.erase(c.in.begin(), c.in.begin() + off);
	}

	void send_result(Conn &c, const Result &r)
	{
		std::vector<uint8_t> o = encode_result(r);
		c.out.insert(c.out.end(), o.begin(), o.end());
		write_conn(c);
	}

	void handle(Conn &c, uint16_t type, const uint8_t *p, uint32_t len)
	{
		if (type == MSG_PING)
		{
			std::string j = pong();
			std::vector<uint8_t> o;
			put_header(o, MSG_PONG, (uint32_t)j.size());
			o.insert(o.end(), j.begin(), j.end());
			c.out.insert(c.out.end(), o.begin(), o.end());
			write_conn(c);
			return;
		}
		if (type != MSG_RECOGNIZE)
		{
			c.dead = true;
			return;
		}
		m_last_req = now_us();
		std::unique_ptr<Job> job(new Job());
		job->conn = c.id;
		job->t_recv = now_us();
		if (!decode_request(p, len, job->rq))
		{
			Result r;
			r.request_id = len >= 8 ? get32(p) : 0;
			r.generation = len >= 8 ? get32(p + 4) : 0;
			r.status = ST_BAD_REQUEST;
			send_result(c, r);
			return;
		}
		int to = job->rq.timeout_ms ? job->rq.timeout_ms : g_opt.default_timeout_ms;
		to = std::min(to, 10000);
		job->deadline = job->t_recv + (int64_t)to * 1000;
		g_stats.requests++;
		// pagina (sau fiecare rand al ei) deja citita: raspunsul pe loc, fara coada
		if (!(job->rq.flags & FLAG_NO_CACHE))
		{
			bool missing = false;
			Result r = m_fast.run(*job, true, &missing);
			if (!missing)
			{
				g_stats.immediate++;
				send_result(c, r);
				return;
			}
		}
		std::vector<std::unique_ptr<Job>> dropped;
		{
			std::lock_guard<std::mutex> lk(m_mx);
			if (job->rq.flags & FLAG_SUPERSEDE)
			{
				for (auto it = m_queue.begin(); it != m_queue.end();)
					if ((*it)->conn == c.id && (*it)->rq.generation < job->rq.generation)
					{
						dropped.push_back(std::move(*it));
						it = m_queue.erase(it);
					}
					else
						++it;
				if (m_running && m_running->conn == c.id && m_running->rq.generation < job->rq.generation)
					m_running->cancelled = true;
			}
			if (m_queue.size() >= 8)
			{
				Result r;
				r.request_id = job->rq.request_id;
				r.generation = job->rq.generation;
				r.status = ST_BUSY;
				send_result(c, r);
			}
			else
				m_queue.push_back(std::move(job));
		}
		m_cv.notify_one();
		for (auto &d : dropped)
		{
			Result r;
			r.request_id = d->rq.request_id;
			r.generation = d->rq.generation;
			r.status = ST_CANCELLED;
			r.elapsed_us = (uint32_t)(now_us() - d->t_recv);
			g_stats.cancelled++;
			send_result(c, r);
		}
	}

	void write_conn(Conn &c)
	{
		while (c.out_off < c.out.size())
		{
			ssize_t n = send(c.fd, c.out.data() + c.out_off, c.out.size() - c.out_off, MSG_NOSIGNAL);
			if (n > 0)
			{
				c.out_off += n;
				continue;
			}
			if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR))
				break;
			c.dead = true;
			break;
		}
		if (c.out_off == c.out.size())
		{
			c.out.clear();
			c.out_off = 0;
		}
		else if (c.out.size() - c.out_off > 4u * 1024 * 1024)
			c.dead = true;   // clientul nu citeste
	}

	// rezultatele gata din firul de lucru
	void deliver()
	{
		std::deque<std::pair<int, Result>> done;
		{
			std::lock_guard<std::mutex> lk(m_mx);
			done.swap(m_done);
		}
		for (auto &d : done)
		{
			Conn *c = find_id(d.first);
			if (c)
				send_result(*c, d.second);
		}
	}

	void reap()
	{
		for (auto it = m_conns.begin(); it != m_conns.end();)
			if (it->dead)
			{
				int id = it->id;
				close(it->fd);
				it = m_conns.erase(it);
				std::lock_guard<std::mutex> lk(m_mx);
				for (auto q = m_queue.begin(); q != m_queue.end();)
					if ((*q)->conn == id)
						q = m_queue.erase(q);
					else
						++q;
				if (m_running && m_running->conn == id)
					m_running->cancelled = true;
				logv("conexiunea %d inchisa", id);
			}
			else
				++it;
	}

	bool idle()
	{
		std::lock_guard<std::mutex> lk(m_mx);
		return m_queue.empty() && !m_running && m_done.empty();
	}

	void work()
	{
		Recognizer rec(m_mem);
		for (;;)
		{
			std::unique_ptr<Job> job;
			{
				std::unique_lock<std::mutex> lk(m_mx);
				m_cv.wait(lk, [this] { return m_quit || !m_queue.empty(); });
				if (m_quit)
					break;
				job = std::move(m_queue.front());
				m_queue.pop_front();
				m_running = job.get();
			}
			Result r;
			if (job->cancelled.load())
			{
				r.request_id = job->rq.request_id;
				r.generation = job->rq.generation;
				r.status = ST_CANCELLED;
			}
			else
				r = rec.run(*job);
			{
				std::lock_guard<std::mutex> lk(m_mx);
				m_running = nullptr;
				m_done.emplace_back(job->conn, r);
				m_loaded = rec.loaded();
			}
			logv("cererea %u: stare %u, %zu randuri, %.1f ms", r.request_id, r.status, r.lines.size(), r.elapsed_us / 1000.0);
			if (write(m_wake[1], "x", 1) < 0) {}
		}
	}

	std::string pong()
	{
		char b[1024];
		std::string models;
		{
			// copia listei de modele facuta de firul de lucru dupa fiecare cerere
			std::lock_guard<std::mutex> lk(m_mx);
			for (auto &m : m_loaded)
				models += (models.empty() ? "" : ",") + jstr(m);
		}
		snprintf(b, sizeof(b), "{\"version\":\"%s\",\"tesseract\":\"%s\",\"requests\":%ld,\"lines_recognized\":%ld,"
			"\"line_cache_hits\":%ld,\"page_cache_hits\":%ld,\"timeouts\":%ld,\"cancelled\":%ld,\"budget_timeouts\":%ld,"
			"\"expired\":%ld,\"immediate\":%ld,\"ms_per_unit\":%.2f,\"speed_samples\":%ld,\"glyph_lines\":%ld,"
			"\"glyphs\":%zu,\"connections\":%zu,\"stretched_lines\":%ld,\"rereads\":%ld,\"rereads_better\":%ld,"
			"\"models\":[",
			HDS_OCR_VERSION, tesseract::TessBaseAPI::Version(), g_stats.requests.load(), g_stats.lines.load(),
			g_stats.line_hits.load(), g_stats.page_hits.load(), g_stats.timeouts.load(), g_stats.cancelled.load(),
			g_stats.budget_timeouts.load(), g_stats.expired.load(), g_stats.immediate.load(), g_speed.ms_per_unit(),
			g_speed.samples(), g_stats.glyph_lines.load(), m_mem.glyph_count(), m_conns.size(), g_stats.stretched.load(),
			g_stats.rereads.load(), g_stats.rereads_better.load());
		return std::string(b) + models + "]}";
	}

	Memory m_mem;
	Recognizer m_fast{m_mem};        // numai memoria (firul principal); tesseract ramane in firul de lucru
	int m_listen = -1, m_lockfd = -1;
	int m_wake[2] = {-1, -1};
	int m_next_id = 0;
	int64_t m_last_req = 0;
	std::list<Conn> m_conns;
	std::mutex m_mx;
	std::condition_variable m_cv;
	std::deque<std::unique_ptr<Job>> m_queue;
	std::deque<std::pair<int, Result>> m_done;
	Job *m_running = nullptr;
	std::vector<std::string> m_loaded;
	bool m_quit = false;
};

// ------------------------------------------------------------------------------------------------

static void usage()
{
	printf("hds-ocr %s - recunoasterea textului din subtitrarile DVB (serviciu local)\n"
		"  --socket CALE        socketul unix (implicit /tmp/hds-ocr.sock)\n"
		"  --tessdata DOSAR     modelele .traineddata (implicit /usr/share/hds-ocr/tessdata)\n"
		"  --tessdata-extra DOSAR  alt dosar cu modele, cautat dupa --tessdata (se poate repeta)\n"
		"  --implicit MODEL     modelul pentru piste fara limba cunoscuta (implicit ron)\n"
		"  --idle-exit SEC      iese dupa SEC secunde fara cereri (implicit 600, 0 = niciodata)\n"
		"  --nice N             prioritatea procesului (implicit 10)\n"
		"  --max-models N       modele incarcate deodata (implicit 2)\n"
		"  --cache N            randuri tinute minte (implicit 512)\n"
		"  --no-glyphs          fara memoria glifelor (randurile noi trec toate prin tesseract)\n"
		"  --scale N            marirea randului 1..4 (implicit 0 = automat, tinta --target-band px)\n"
		"  --target-band PX     inaltimea tinta a randului dupa marire (implicit 24)\n"
		"  --psm N              modul de pagina tesseract pentru un rand (7 sau 13; implicit 7)\n"
		"  --no-stretch         fara intinderea scrisului ingust\n"
		"  --stretch-narrow R   scrisul cu latime / inaltime a literelor sub R se intinde (implicit 0.59)\n"
		"  --stretch-target R   pana la acest raport (implicit 0.68)\n"
		"  --stretch-max K      intinderea cea mai mare (implicit 1.5)\n"
		"  --no-reread          fara a doua citire a randurilor nesigure\n"
		"  --reread-k K         intinderea la a doua citire a unui rand neintins (implicit 1.25)\n"
		"  --timeout MS         termenul unei cereri fara timeout_ms (implicit 5000)\n"
		"  --min-budget MS      timpul de lucru minim al unei pagini (implicit 1500)\n"
		"  --max-budget MS      timpul de lucru maxim al unei pagini (implicit 10000)\n"
		"  --budget-factor F    timpul de lucru = F x timpul estimat (implicit 3)\n"
		"  --ms-per-unit MS     viteza de pornire, ms pe unitate de rand (implicit 20)\n"
		"  --daemon             trece in fundal (pentru pornirea din enigma2)\n"
		"  -v                   jurnal pe stderr\n"
		"  --bench FISIER...    proba fara socket: cereri RECOGNIZE din fisiere, rezultat JSON pe stdout\n"
		"  --repeat N           de cate ori (--bench)\n"
		"  --no-cache           fara memorie de randuri (--bench)\n"
		"  --no-dict            fara dictionarul modelului (proba)\n"
		"  --set NUME=VALOARE   variabila tesseract la incarcarea modelului (proba; se poate repeta)\n"
		"  --dump DOSAR         scrie randurile pregatite ca PGM (depanare)\n",
		HDS_OCR_VERSION);
}

int main(int argc, char **argv)
{
	// OpenMP (libtesseract din Ubuntu e construita cu el) citeste OMP_THREAD_LIMIT cand se incarca biblioteca,
	// INAINTE de main, deci un setenv facut aici nu mai conteaza. Daca lipseste din mediu, il punem si
	// pornim programul inca o data (execv). Probat in cloud 25.09: fara asta, prima cerere lua 3,5 s (fire
	// OpenMP care se bat pe 4 nuclee, user 10 s) si iesea TIMEOUT. Pe receptor tesseract e fara OpenMP.
	if (!getenv("OMP_THREAD_LIMIT"))
	{
		setenv("OMP_THREAD_LIMIT", "1", 1);
		execv("/proc/self/exe", argv);
		// execv nu a mers (fara /proc): se merge mai departe, cu OpenMP cat vrea el
	}
	for (int i = 1; i < argc; ++i)
	{
		std::string a = argv[i];
		auto next = [&](const char *name) -> std::string {
			if (i + 1 >= argc)
			{
				loge("lipseste valoarea pentru %s", name);
				exit(2);
			}
			return argv[++i];
		};
		if (a == "--socket") g_opt.socket_path = next("--socket");
		else if (a == "--tessdata") g_opt.tessdata = next("--tessdata");
		else if (a == "--tessdata-extra") g_opt.tessdata_extra.push_back(next("--tessdata-extra"));
		else if (a == "--implicit") g_opt.implicit_model = next("--implicit");
		else if (a == "--idle-exit") g_opt.idle_exit_s = atoi(next("--idle-exit").c_str());
		else if (a == "--nice") g_opt.nice_level = atoi(next("--nice").c_str());
		else if (a == "--max-models") g_opt.max_models = atoi(next("--max-models").c_str());
		else if (a == "--cache") g_opt.cache_lines = atoi(next("--cache").c_str());
		else if (a == "--no-glyphs") g_opt.glyphs = false;
		else if (a == "--scale") g_opt.scale = atoi(next("--scale").c_str());
		else if (a == "--target-band") g_opt.target_band = atoi(next("--target-band").c_str());
		else if (a == "--psm") g_opt.psm = atoi(next("--psm").c_str());
		else if (a == "--no-stretch") g_opt.stretch = false;
		else if (a == "--stretch-narrow") g_opt.stretch_narrow = atof(next("--stretch-narrow").c_str());
		else if (a == "--stretch-target") g_opt.stretch_target = atof(next("--stretch-target").c_str());
		else if (a == "--stretch-max") g_opt.stretch_max = std::max(1.0, std::min(3.0, atof(next("--stretch-max").c_str())));
		else if (a == "--no-reread") g_opt.reread = false;
		else if (a == "--reread-k") g_opt.reread_k = std::max(1.0, std::min(3.0, atof(next("--reread-k").c_str())));
		else if (a == "--timeout") g_opt.default_timeout_ms = atoi(next("--timeout").c_str());
		else if (a == "--min-budget") g_opt.min_budget_ms = std::max(50, atoi(next("--min-budget").c_str()));
		else if (a == "--max-budget") g_opt.max_budget_ms = std::max(50, atoi(next("--max-budget").c_str()));
		else if (a == "--budget-factor") g_opt.budget_factor = std::max(1.0, atof(next("--budget-factor").c_str()));
		else if (a == "--ms-per-unit") g_opt.ms_per_unit_start = std::max(0.1, atof(next("--ms-per-unit").c_str()));
		else if (a == "--daemon") g_opt.daemon = true;
		else if (a == "-v") g_opt.verbose = true;
		else if (a == "--repeat") g_opt.repeat = atoi(next("--repeat").c_str());
		else if (a == "--no-cache") g_opt.bench_no_cache = true;
		else if (a == "--no-dict") g_opt.no_dict = true;
		else if (a == "--set")
		{
			std::string kv = next("--set");
			size_t eq = kv.find('=');
			if (eq == std::string::npos || eq == 0)
			{
				loge("--set cere NUME=VALOARE");
				return 2;
			}
			g_opt.tess_vars.emplace_back(kv.substr(0, eq), kv.substr(eq + 1));
		}
		else if (a == "--dump") g_opt.dump_dir = next("--dump");
		else if (a == "--bench")
		{
			while (i + 1 < argc && argv[i + 1][0] != '-')
				g_opt.bench_files.push_back(argv[++i]);
		}
		else if (a == "--version") { printf("hds-ocr %s (tesseract %s)\n", HDS_OCR_VERSION, tesseract::TessBaseAPI::Version()); return 0; }
		else if (a == "-h" || a == "--help") { usage(); return 0; }
		else { loge("optiune necunoscuta: %s", a.c_str()); usage(); return 2; }
	}
	if (g_opt.psm != 7 && g_opt.psm != 13)
		g_opt.psm = 7;
	if (g_opt.max_budget_ms < g_opt.min_budget_ms)
		g_opt.max_budget_ms = g_opt.min_budget_ms;
	// leptonica scrie pe stderr mesaje fara folos aici (de ex. fontul de depanare din TIFF, care lipseste
	// intentionat din leptonica de pe receptor); se vad numai cu LEPT_MSG_SEVERITY=1..5 in mediu
	setMsgSeverity(getenv("LEPT_MSG_SEVERITY") ? L_SEVERITY_EXTERNAL : L_SEVERITY_NONE);
	// un singur fir de calcul in tesseract: OMP_THREAD_LIMIT e pus la inceputul lui main (cu execv)
	if (g_opt.nice_level)
		setpriority(PRIO_PROCESS, 0, g_opt.nice_level);
	if (!g_opt.bench_files.empty())
		return run_bench();
	if (g_opt.daemon)
	{
		pid_t p = fork();
		if (p < 0)
			return 1;
		if (p > 0)
			return 0;
		setsid();
		int fd = open("/dev/null", O_RDWR);
		if (fd >= 0)
		{
			dup2(fd, 0);
			dup2(fd, 1);
			if (!g_opt.verbose)
				dup2(fd, 2);
			if (fd > 2)
				close(fd);
		}
	}
	signal(SIGPIPE, SIG_IGN);
	struct sigaction sa;
	memset(&sa, 0, sizeof(sa));
	sa.sa_handler = on_signal;
	sigaction(SIGTERM, &sa, nullptr);
	sigaction(SIGINT, &sa, nullptr);
	Server srv;
	return srv.run();
}
