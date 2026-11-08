/* Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 * Tap de observare al redarii existente. Nu deschide reteaua, ALSA sau un sink si nu tine serviciul in viata.
 * Streaming: numai caps, ref buffer si coada marginita, cu try_lock. Un fir separat citeste cadrele/PCM.
 * Interfata: snapshot numai cu numere si nume fixe de codec; fara caps arbitrare, URL, taguri sau date personale.
 */
#ifndef __lib_service_hdsradioonline_h
#define __lib_service_hdsradioonline_h

#include <lib/dvb/hdsspectru.h>
#include <gst/gst.h>
#include <atomic>
#include <algorithm>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstring>
#include <deque>
#include <dlfcn.h>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

class HdsRadioOnline: public std::enable_shared_from_this<HdsRadioOnline>
{
public:
	struct Date
	{
		std::string codec;
		int rata = 0, canale = 0, debit = 0;
		bool aproximativ = false, bare = false, mono = false;
		uint8_t niv[2][32];
		uint64_t nivel_ms = 0;
		Date() { memset(niv, 63, sizeof(niv)); }
	};
	static std::shared_ptr<HdsRadioOnline> creeaza()
	{
		std::shared_ptr<HdsRadioOnline> p(new HdsRadioOnline());
		std::thread([p] { p->lucreaza(); }).detach();
		return p;
	}
	void opreste() { merge = false; semnal.notify_one(); }
	std::shared_ptr<const Date> citeste()
	{
		cerere = acum();
		return std::atomic_load(&publicat);
	}
	/* Cate un pad la intrarea decodorului si la iesirea PCM: acelasi sunet, fara decodare AAC noua.
	   user_data detine numai observatorul, niciodata eServiceMP3/Poarta. */
	void leaga(GstPad *pad)
	{
		if (!pad)
			return;
		gst_pad_add_probe(pad, (GstPadProbeType)(GST_PAD_PROBE_TYPE_BUFFER | GST_PAD_PROBE_TYPE_BUFFER_LIST),
			&proba, new std::shared_ptr<HdsRadioOnline>(shared_from_this()), &sterge);
	}
private:
	struct Pachet
	{
		GstBuffer *b = NULL;
		GstCaps *caps = NULL;
		Pachet(GstBuffer *buf, GstCaps *c): b(gst_buffer_ref(buf)), caps(gst_caps_ref(c)) {}
		Pachet(Pachet &&p): b(p.b), caps(p.caps) { p.b = NULL; p.caps = NULL; }
		~Pachet() { if (b) gst_buffer_unref(b); if (caps) gst_caps_unref(caps); }
	};
	std::atomic<bool> merge{true};
	std::atomic<uint64_t> cerere{0};
	std::mutex lacat;
	std::condition_variable semnal;
	std::deque<Pachet> coada;
	GstPad *pad_comprimat = NULL, *pad_pcm = NULL; /* numai identitati; probele detin padurile */
	std::atomic<GstPad *> pad_numarat{NULL};
	std::atomic<uint64_t> octeti_primiti{0};
	uint64_t ultim_comprimat = 0, ultim_pcm_pad = 0;
	std::atomic<uint64_t> ultim_pcm{0};
	std::shared_ptr<const Date> publicat;
	Date date;
	hdsspectru::Nucleu *nucleu = NULL;
	uint64_t ultima_fft = 0, octeti = 0, durata = 0;
	uint64_t ultim_nucleu = 0, limita_analiza = 0;
	bool antet_mpeg = false;
	uint64_t inceput_octeti_ms = 0, octeti_fara_ceas = 0, ultim_pachet_ms = 0;
	uint64_t baza_octeti = 0;
	bool rafala_trecuta = false, din_nucleu = false;
	uint64_t adts_octeti = 0;
	double adts_secunde = 0;
	GstClockTime ultim_pts = GST_CLOCK_TIME_NONE;
	std::string tip_comprimat;
	std::vector<uint8_t> rest;
	/* API stabil libmpg123, incarcat numai pe firul de observare si numai pentru MPEG.
	   Valori ABI publice: SIGNED_16=0xd0, NEW_FORMAT=-11, NEED_MORE=-10. */
	void *lib = NULL, *mpg = NULL;
	bool mpg_incercat = false;
	void *(*mpg_new)(const char *, int *) = NULL;
	void (*mpg_delete)(void *) = NULL;
	int (*mpg_decode)(void *, const unsigned char *, size_t, void *, size_t, size_t *) = NULL;
	int (*mpg_format)(void *, long, int, int) = NULL;
	int (*mpg_getformat)(void *, long *, int *, int *) = NULL;
	HdsRadioOnline(): publicat(std::make_shared<Date>()) {}
	static uint64_t acum()
	{
		return std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
	}
	static void sterge(gpointer p) { delete (std::shared_ptr<HdsRadioOnline> *)p; }
	static GstPadProbeReturn proba(GstPad *pad, GstPadProbeInfo *info, gpointer user)
	{
		HdsRadioOnline &r = **(std::shared_ptr<HdsRadioOnline> *)user;
		if (!r.merge || acum() - r.cerere.load() > 3000)
			return GST_PAD_PROBE_OK;
		GstCaps *caps = gst_pad_get_current_caps(pad);
		if (!caps || gst_caps_is_empty(caps) || gst_caps_is_any(caps))
		{
			if (caps) gst_caps_unref(caps);
			return GST_PAD_PROBE_OK;
		}
		const char *n = gst_structure_get_name(gst_caps_get_structure(caps, 0));
		if (pad == r.pad_numarat.load() && !strncmp(n, "audio/", 6) && strcmp(n,"audio/x-raw"))
		{
			/* Masura debitului nu pierde octetii cand coada de analiza este plina. */
			if (GST_PAD_PROBE_INFO_TYPE(info) & GST_PAD_PROBE_TYPE_BUFFER)
			{
				GstBuffer *b = GST_PAD_PROBE_INFO_BUFFER(info);
				if (b) r.octeti_primiti += gst_buffer_get_size(b);
			}
			else if (GST_PAD_PROBE_INFO_TYPE(info) & GST_PAD_PROBE_TYPE_BUFFER_LIST)
			{
				GstBufferList *lista = GST_PAD_PROBE_INFO_BUFFER_LIST(info);
				for (guint i = 0; lista && i < gst_buffer_list_length(lista); ++i)
					r.octeti_primiti += gst_buffer_get_size(gst_buffer_list_get(lista,i));
			}
		}
		std::unique_lock<std::mutex> l(r.lacat, std::try_to_lock);
		if (!l || r.coada.size() >= 4)
		{
			gst_caps_unref(caps);
			return GST_PAD_PROBE_OK;
		}
		if (!strncmp(n, "audio/", 6))
		{
			bool raw = !strcmp(n, "audio/x-raw");
			GstPad *&ales = raw ? r.pad_pcm : r.pad_comprimat;
			uint64_t &ultima = raw ? r.ultim_pcm_pad : r.ultim_comprimat;
			uint64_t t = acum();
			/* O singura intrare comprimata si o singura iesire PCM din lant. La schimbarea
			   pistei, padul nou preia dupa expirarea celui vechi; nu numaram acelasi sunet de doua ori. */
			if (ales && ales != pad && t - ultima < 1500)
			{
				gst_caps_unref(caps);
				return GST_PAD_PROBE_OK;
			}
			ales = pad; ultima = t;
			if (!raw) r.pad_numarat = pad;
			if (raw)
			{
				GstStructure *s = gst_caps_get_structure(caps,0);
				const char *fmt = gst_structure_get_string(s,"format"), *layout = gst_structure_get_string(s,"layout");
				if ((!layout || !strcmp(layout,"interleaved")) && fmt && (!strcmp(fmt,"F32LE") || !strcmp(fmt,"S16LE"))) r.ultim_pcm = t;
			}
			if (GST_PAD_PROBE_INFO_TYPE(info) & GST_PAD_PROBE_TYPE_BUFFER)
				r.pune(GST_PAD_PROBE_INFO_BUFFER(info), caps);
			else if (GST_PAD_PROBE_INFO_TYPE(info) & GST_PAD_PROBE_TYPE_BUFFER_LIST)
			{
				GstBufferList *lista = GST_PAD_PROBE_INFO_BUFFER_LIST(info);
				for (guint i = 0; lista && i < gst_buffer_list_length(lista) && r.coada.size() < 4; ++i)
					r.pune(gst_buffer_list_get(lista, i), caps);
			}
		}
		gst_caps_unref(caps);
		r.semnal.notify_one();
		return GST_PAD_PROBE_OK;
	}
	void pune(GstBuffer *b, GstCaps *caps)
	{
		/* Nu pastram o bucata uriasa sau o coada de sunet vechi; redarea nu asteapta analiza. */
		if (b && gst_buffer_get_size(b) <= 65536 && coada.size() < 4)
			coada.emplace_back(b, caps);
	}
	void lucreaza()
	{
		nucleu = hdsspectru::creeaza();
		while (merge)
		{
			std::unique_lock<std::mutex> l(lacat);
			semnal.wait_for(l, std::chrono::milliseconds(200), [this] { return !merge || !coada.empty(); });
			if (!merge) break;
			if (coada.empty()) continue;
			Pachet p(std::move(coada.front()));
			coada.pop_front();
			l.unlock();
			if (acum() - cerere.load() > 3000) continue;
			GstMapInfo h;
			if (gst_buffer_map(p.b, &h, GST_MAP_READ))
			{
				analizeaza(p, h.data, h.size);
				gst_buffer_unmap(p.b, &h);
				std::shared_ptr<const Date> copie = std::make_shared<Date>(date);
				std::atomic_store(&publicat, copie);
			}
		}
		if (mpg) mpg_delete(mpg);
		if (lib) dlclose(lib);
		hdsspectru::distruge(nucleu);
	}
	void nivel(const uint8_t *b, size_t n, int fel)
	{
		uint64_t t = acum();
		bool config_latm = fel == hdsspectru::FEL_LATM && n > 3 && !(b[3] & 128);
		/* Configuratia LATM trebuie invatata chiar intre cadrele alese. In mod obisnuit
		   numai nivelele se citesc la 12,5 Hz; o bucata nu poate depasi bugetul firului. */
		if (t > limita_analiza || (!config_latm && t - ultim_nucleu < 80)) return;
		ultim_nucleu = t;
		int mono = 0;
		if (nucleu && hdsspectru::cadru(nucleu, fel, b, n, date.niv, &mono))
		{
			date.bare = true;
			date.mono = mono != 0;
			date.nivel_ms = acum();
			hdsspectru::Info i;
			hdsspectru::info(nucleu, &i);
			/* caps-urile dau rata nucleului AAC; cu SBR se aude dublul ei: dupa primul cadru citit raman datele nucleului */
			din_nucleu = true;
			if (i.esantionare > 0) date.rata = i.esantionare;
			if (i.canale > 0) date.canale = i.canale + i.lfe;
			if (fel == hdsspectru::FEL_ADTS || fel == hdsspectru::FEL_LATM)
				date.codec = i.ps ? "HE-AAC v2" : (i.sbr ? "HE-AAC" : "AAC");
		}
	}
	/* FFT scurta la cel mult 12,5 Hz, cu fereastra Hann. Puterea a doua linii -> o banda fs/64.
	   Din nivel dBFS in aceeasi scara 0..63 folosita de analizorul DVB. */
	template<class T> void pcm(const T *p, size_t cadre, int canale, double factor)
	{
		uint64_t t = acum();
		if (cadre < 128 || canale < 1 || canale > 8 || t - ultima_fft < 80) return;
		ultima_fft = t;
		for (int c = 0; c < (canale == 1 ? 1 : 2); ++c)
		{
			double re[128], im[128] = {};
			for (int j = 0; j < 128; ++j)
				re[j] = p[((cadre - 128) + j) * canale + c] * factor * (0.5 - 0.5 * cos(6.283185307179586 * j / 127));
			for (int j = 1, k = 0; j < 128; ++j)
			{
				int bit = 64;
				for (; k & bit; bit >>= 1) k ^= bit;
				k ^= bit;
				if (j < k) std::swap(re[j], re[k]);
			}
			for (int pas = 2; pas <= 128; pas *= 2)
				for (int a = 0; a < 128; a += pas)
					for (int j = 0; j < pas / 2; ++j)
					{
						double unghi = -6.283185307179586 * j / pas;
						int x = a + j, y = x + pas / 2;
						double r = re[y] * cos(unghi) - im[y] * sin(unghi), v = re[y] * sin(unghi) + im[y] * cos(unghi);
						re[y] = re[x] - r; im[y] = im[x] - v; re[x] += r; im[x] += v;
					}
			for (int j = 0; j < 32; ++j)
			{
				int a = j * 2, b = a + 1;
				double e = (re[a]*re[a] + im[a]*im[a] + re[b]*re[b] + im[b]*im[b]) / 1024.0;
				double db = 10 * log10(e + 1e-20);
				date.niv[c][j] = e < 1e-12 ? 63 : (uint8_t)std::max(0.0, std::min(62.0, -db / 2));
			}
		}
		date.bare = true; date.mono = canale == 1; date.nivel_ms = t;
	}
	void mpeg(const uint8_t *b, size_t n)
	{
		/* Antet MPEG-1/2/2.5, toate cele trei straturi; debitul este al fluxului comprimat. */
		static const int kb[2][3][15] = {
			{{0,32,64,96,128,160,192,224,256,288,320,352,384,416,448}, {0,32,48,56,64,80,96,112,128,160,192,224,256,320,384}, {0,32,40,48,56,64,80,96,112,128,160,192,224,256,320}},
			{{0,32,48,56,64,80,96,112,128,144,160,176,192,224,256}, {0,8,16,24,32,40,48,56,64,80,96,112,128,144,160}, {0,8,16,24,32,40,48,56,64,80,96,112,128,144,160}}};
		for (size_t i = 0; i + 4 <= n && i < 16384; ++i)
		{
			if (b[i] != 255 || (b[i+1] & 224) != 224) continue;
			int v = (b[i+1] >> 3) & 3, layer = (b[i+1] >> 1) & 3, r = (b[i+2] >> 2) & 3, k = b[i+2] >> 4;
			if (v == 1 || !layer || r == 3 || !k || k == 15) continue;
			static const int rates[] = {44100,48000,32000};
			int esantion = rates[r] / (v == 3 ? 1 : (v == 2 ? 2 : 4)), debit_cadru = kb[v == 3 ? 0 : 1][3-layer][k];
			/* Antet adevarat: bucata e chiar cadrul lui sau urmatorul cadru incepe la fel; altfel e un 0xFFE din mijlocul datelor. */
			int umplut = (b[i+2] >> 1) & 1;
			size_t lung = layer == 3 ? (size_t)(12000 * debit_cadru / esantion + umplut) * 4 :
				(size_t)((v == 3 || layer == 2 ? 144000 : 72000) * debit_cadru / esantion + umplut);
			bool bun = i == 0 && lung == n;
			if (!bun && i + lung + 4 <= n)
				bun = b[i+lung] == 255 && (b[i+lung+1] & 254) == (b[i+1] & 254) && ((b[i+lung+2] >> 2) & 3) == r;
			if (!bun) continue;
			date.rata = esantion;
			date.canale = (b[i+3] >> 6) == 3 ? 1 : 2;
			date.debit = debit_cadru;
			antet_mpeg = true;
			date.aproximativ = false;
			date.codec = layer == 1 ? "MP3" : (layer == 2 ? "MP2" : "MP1");
			break;
		}
		/* La EQ pornit folosim PCM-ul decodorului deja activ, fara a dubla decodarea MPEG. */
		if (acum() - ultim_pcm.load() < 1500) return;
		if (!mpg_incercat)
		{
			mpg_incercat = true;
			lib = dlopen("libmpg123.so.0", RTLD_NOW | RTLD_LOCAL);
			if (lib)
			{
				int (*init)() = (int(*)())dlsym(lib, "mpg123_init");
				mpg_new = (void *(*)(const char *,int *))dlsym(lib, "mpg123_new");
				mpg_delete = (void(*)(void *))dlsym(lib, "mpg123_delete");
				mpg_decode = (int(*)(void *,const unsigned char *,size_t,void *,size_t,size_t *))dlsym(lib, "mpg123_decode");
				mpg_format = (int(*)(void *,long,int,int))dlsym(lib, "mpg123_format");
				mpg_getformat = (int(*)(void *,long *,int *,int *))dlsym(lib, "mpg123_getformat");
				int (*none)(void *) = (int(*)(void *))dlsym(lib,"mpg123_format_none");
				int (*feed)(void *) = (int(*)(void *))dlsym(lib,"mpg123_open_feed");
				if (init && mpg_new && mpg_delete && mpg_decode && mpg_format && mpg_getformat && none && feed && !init())
				{
					int err = 0; mpg = mpg_new(NULL, &err);
					if (mpg)
					{
						none(mpg);
						const long rates[] = {8000,11025,12000,16000,22050,24000,32000,44100,48000};
						for (unsigned i = 0; i < sizeof(rates)/sizeof(rates[0]); ++i) mpg_format(mpg,rates[i],3,0xd0);
						if (feed(mpg)) { mpg_delete(mpg); mpg = NULL; }
					}
				}
			}
		}
		if (!mpg) return;
		int16_t iesire[8192];
		/* Cel mult 16 citiri / 256 KiB PCM pe bucata, buget de 8 ms; excesul se arunca, nu franeaza redarea. */
		uint64_t sf = acum() + 8;
		bool terminat = false;
		for (int j = 0; j < 16 && merge && acum() <= sf; ++j)
		{
			size_t scris = 0;
			int r = mpg_decode(mpg, j ? NULL : b, j ? 0 : n, iesire, sizeof(iesire), &scris);
			long rata = 0; int canale = 0, enc = 0;
			if (!mpg_getformat(mpg, &rata, &canale, &enc) && enc == 0xd0 && canale > 0 && scris)
				pcm(iesire, scris / (2 * canale), canale, 1.0 / 32768);
			if (r == -10 || (r != 0 && r != -11)) { terminat = true; break; }
		}
		/* Nu lasam date vechi sa creasca in tamponul intern al bibliotecii cand procesorul este ocupat. */
		if (!terminat)
		{
			mpg_delete(mpg); mpg = NULL;
			dlclose(lib); lib = NULL; mpg_incercat = false;
		}
	}
	void analizeaza(const Pachet &p, const uint8_t *b, size_t n)
	{
		limita_analiza = acum() + 8;
		GstStructure *s = gst_caps_get_structure(p.caps, 0);
		const char *tip = gst_structure_get_name(s), *fmt = gst_structure_get_string(s, "format");
		int rata = 0, canale = 0;
		gst_structure_get_int(s, "rate", &rata); gst_structure_get_int(s, "channels", &canale);
		if (!strcmp(tip, "audio/x-raw"))
		{
			if (tip_comprimat.empty()) { date.codec = "PCM"; date.rata = rata; date.canale = canale; }
			const char *layout = gst_structure_get_string(s,"layout");
			if (canale > 0 && canale <= 8 && fmt && (!layout || !strcmp(layout,"interleaved")))
			{
				if (!strcmp(fmt,"F32LE") && n % (4 * canale) == 0) pcm((const float *)b, n/(4*canale), canale, 1.0);
				else if (!strcmp(fmt,"S16LE") && n % (2 * canale) == 0) pcm((const int16_t *)b, n/(2*canale), canale, 1.0/32768);
				/* FLAC de 24 de biti da S24_32LE sau S32LE */
				else if (!strcmp(fmt,"S32LE") && n % (4 * canale) == 0) pcm((const int32_t *)b, n/(4*canale), canale, 1.0/2147483648.0);
				else if (!strcmp(fmt,"S24_32LE") && n % (4 * canale) == 0) pcm((const int32_t *)b, n/(4*canale), canale, 1.0/8388608);
			}
			return;
		}
		if (tip_comprimat != tip)
		{
			tip_comprimat = tip; date = Date(); rest.clear(); octeti = durata = 0; ultim_pts = GST_CLOCK_TIME_NONE;
			inceput_octeti_ms = 0; octeti_fara_ceas = 0; antet_mpeg = false; rafala_trecuta = false; din_nucleu = false;
			adts_octeti = 0; adts_secunde = 0;
			hdsspectru::reseteaza(nucleu);
		}
		uint64_t t = acum();
		if (ultim_pachet_ms && t - ultim_pachet_ms > 1500)
		{
			rest.clear(); octeti = durata = 0; ultim_pts = GST_CLOCK_TIME_NONE;
			inceput_octeti_ms = 0; octeti_fara_ceas = 0; rafala_trecuta = false;
			adts_octeti = 0; adts_secunde = 0;
			if (mpg) { mpg_delete(mpg); mpg = NULL; dlclose(lib); lib = NULL; mpg_incercat = false; }
		}
		ultim_pachet_ms = t;
		if (rata > 0 && !din_nucleu) date.rata = rata;
		if (canale > 0 && !din_nucleu) date.canale = canale;
		int versiune = 0; gst_structure_get_int(s,"mpegversion",&versiune);
		const char *format = gst_structure_get_string(s,"stream-format");
		int fel = 0;
		if (!strcmp(tip,"audio/mpeg"))
		{
			if (versiune == 1) mpeg(b,n);
			else if (versiune == 2 || versiune == 4)
			{
				if (!din_nucleu) date.codec = "AAC";
				fel = format && (!strcmp(format,"loas") || !strcmp(format,"latm")) ? hdsspectru::FEL_LATM : hdsspectru::FEL_ADTS;
			}
			else date.codec = "MPEG";
		}
		else if (!strcmp(tip,"audio/x-ac3")) { date.codec = "AC3"; fel = hdsspectru::FEL_AC3; }
		else if (!strcmp(tip,"audio/x-eac3")) { date.codec = "AC3+"; fel = hdsspectru::FEL_EAC3; }
		else if (!strcmp(tip,"audio/x-dts")) { date.codec = "DTS"; fel = hdsspectru::FEL_DTS; }
		else if (!strcmp(tip,"audio/x-flac")) date.codec = "FLAC";
		else if (!strcmp(tip,"audio/x-vorbis")) date.codec = "Vorbis";
		else if (!strcmp(tip,"audio/x-opus")) date.codec = "Opus";
		GstClockTime d = GST_BUFFER_DURATION(p.b), pts = GST_BUFFER_PTS(p.b);
		if (!GST_CLOCK_TIME_IS_VALID(d) && GST_CLOCK_TIME_IS_VALID(pts) && GST_CLOCK_TIME_IS_VALID(ultim_pts) && pts > ultim_pts) d = pts - ultim_pts;
		ultim_pts = pts;
		if (GST_CLOCK_TIME_IS_VALID(d) && d > 0 && d <= GST_SECOND * 10)
		{
			octeti += n; durata += d;
			if (durata >= GST_SECOND / 2)
			{
				if (!(versiune == 1 && antet_mpeg))
				{
					date.debit = (int)(octeti * 8.0 * GST_SECOND / durata / 1000); date.aproximativ = true;
				}
				if (durata >= GST_SECOND * 10) { durata /= 2; octeti /= 2; }
			}
		}
		else
		{
			/* Unele sinkuri hardware nu dau PTS/durata: media octetilor comprimati primiti,
			   pe ceas monoton, numai dupa o fereastra reala de cel putin doua secunde. */
			uint64_t primiti = octeti_primiti.load();
			if (!inceput_octeti_ms) { inceput_octeti_ms = t; baza_octeti = primiti >= n ? primiti - n : 0; }
			octeti_fara_ceas = primiti - baza_octeti;
			uint64_t ms = t - inceput_octeti_ms;
			/* La conectare serverul trimite pe nerasuflate cateva secunde de sunet: nu intra in masura. */
			if (!rafala_trecuta && ms >= 3000) { rafala_trecuta = true; inceput_octeti_ms = t; baza_octeti = primiti; octeti_fara_ceas = 0; ms = 0; }
			if (rafala_trecuta && ms >= 2000)
			{
				if (!(versiune == 1 && antet_mpeg))
				{
					date.debit = (int)(octeti_fara_ceas * 8.0 / ms); date.aproximativ = true;
				}
				if (ms >= 10000) { inceput_octeti_ms = t - ms/2; baza_octeti = primiti - octeti_fara_ceas/2; }
			}
		}
		if (fel == hdsspectru::FEL_ADTS && format && !strcmp(format,"raw"))
		{
			/* AAC LC brut in MP4/HLS: ASC descrie nucleul; cititorul ADTS existent poate citi si SBR/PS. */
			const GValue *v = gst_structure_get_value(s,"codec_data");
			GstBuffer *cfg = v && GST_VALUE_HOLDS_BUFFER(v) ? gst_value_get_buffer(v) : NULL;
			GstMapInfo h;
			if (cfg && n <= 8184 && gst_buffer_map(cfg,&h,GST_MAP_READ))
			{
				size_t poz = 0; bool rau = false;
				auto biti = [&](int nr) -> int {
					if (poz + nr > h.size * 8) { rau = true; return 0; }
					int v = 0; while (nr--) { v = (v<<1)|((h.data[poz/8]>>(7-poz%8))&1); ++poz; } return v;
				};
				int objet = biti(5); if (objet == 31) objet = 32 + biti(6);
				int sr = biti(4); if (sr == 15) { biti(24); rau = true; }
				int ch = biti(4);
				if (objet == 5 || objet == 29)
				{
					int ext_sr = biti(4); if (ext_sr == 15) biti(24);
					objet = biti(5); if (objet == 31) objet = 32 + biti(6);
				}
				if (!rau && objet >= 1 && objet <= 4 && sr < 13 && ch > 0 && ch <= 7)
				{
					std::vector<uint8_t> adts(n+7); size_t len=n+7;
					adts[0]=255; adts[1]=241; adts[2]=((objet-1)<<6)|(sr<<2)|(ch>>2);
					adts[3]=((ch&3)<<6)|(len>>11); adts[4]=(len>>3)&255; adts[5]=((len&7)<<5)|31; adts[6]=252;
					memcpy(adts.data()+7,b,n); nivel(adts.data(),adts.size(),fel);
				}
				gst_buffer_unmap(cfg,&h);
			}
		}
		else if (fel == hdsspectru::FEL_ADTS || fel == hdsspectru::FEL_LATM)
		{
			if (rest.size()+n > 65536) rest.clear();
			rest.insert(rest.end(),b,b+n);
			size_t i=0;
			size_t antet = fel == hdsspectru::FEL_ADTS ? 7 : 3;
			while (i+antet <= rest.size())
			{
				size_t lung=hdsspectru::lungimeAac(fel,rest.data()+i,rest.size()-i);
				if (!lung) { ++i; continue; }
				if (i+lung > rest.size()) break;
				if (fel == hdsspectru::FEL_ADTS)
				{
					/* Debitul din cadre: durata lor nu depinde de cat de repede trimite serverul. */
					static const int rate_adts[13] = {96000,88200,64000,48000,44100,32000,24000,22050,16000,12000,11025,8000,7350};
					adts_octeti += lung;
					adts_secunde += 1024.0 * ((rest[i+6] & 3) + 1) / rate_adts[(rest[i+2] >> 2) & 15];
					if (adts_secunde >= 1.0)
					{
						date.debit = (int)(adts_octeti * 8 / adts_secunde / 1000);
						date.aproximativ = true;
						if (adts_secunde >= 30.0) { adts_octeti /= 2; adts_secunde /= 2; }
					}
				}
				nivel(rest.data()+i,lung,fel); i+=lung;
			}
			rest.erase(rest.begin(),rest.begin()+i);
		}
		else if (fel) nivel(b,n,fel);
	}
};
#endif
