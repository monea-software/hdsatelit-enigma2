/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsegalizator.cpp: egalizatorul in procesor (vezi hdsegalizator.h pentru drum si fire).
 *
 * Sesiunea (un post sau un fisier de proba):
 *   sursa (demux PES sau fisier TS / flux audio) -> PES -> flux elementar -> appsrc
 *   -> parser + decodor (GStreamer) -> audioconvert -> audioresample -> F32 48 kHz stereo -> appsink
 *   -> Lant (hdsegalizator_dsp.h: benzi, Noapte, nivel, volum, limitator, rampa) + Spectru
 *   -> Potrivire (tampon cu potrivirea ceasurilor) -> 16 biti -> ALSA
 *   sau, la proba din fisier, direct -> 16 biti -> fisier WAV (fara tampon, cat de repede merge).
 *
 * AAC in LATM (cum transmit posturile DVB): cand imaginea are un decodor ADTS (faad pe receptor), cadrele LOAS se
 * impacheteaza din nou ca ADTS (hdsegalizator_flux.h, LatmLaAdts) si merg pe drumul ADTS; decodorul LATM (avdec_aac_latm)
 * se foloseste numai fara decodor ADTS sau cand configuratia postului nu se poate spune in ADTS.
 *
 * Cazurile in care sunetul se intoarce pe placa (mesajul 3 catre firul enigma2, care cheama reaplicarea): GStreamer
 * sau decodorul lipsesc, placa ALSA nu se deschide sau are iesirea oprita din mixer (comutatorul „ALL”/„Master” oprit
 * sau volumul lor la minim: ar iesi liniste), nicio data de sunet in PRIMA_DATA_MS de la pornire, eroare de decodare,
 * ALSA cade de mai multe ori la rand. Sursa care a cazut se tine minte si nu se mai ia pana la schimbarea
 * postului sau a setarii. O pauza a datelor dupa ce au mers (ploaie, postul tace) nu intoarce sunetul: placa n-ar avea
 * nici ea date; iese liniste pana revin datele.
 *
 * Canalele TV (vezi hdsegalizator.h): la sursele TV firul cititor pastreaza PTS-ul fiecarui PES si
 * il da bucatii trimise in GStreamer (appsrc in format „time”); mostrele decodate isi pastreaza timpul, deci fiecare
 * bucata scrisa in tampon are PTS-ul ei (marcajele sesiunii); firul placii compara PTS-ul cadrului care iese cu PTS-ul
 * imaginii (CeasImagine) si hotaraste cu SincronImagine.
 *
 * Volumul: placa aplica volumul enigma2 pe iesiri (atunci si pe sunetul nostru) sau pe pista ei (atunci nu). In modul
 * automat, la fiecare volum sub 100 se citeste o data /proc/msp/sound0: iesirile cu Vol(100) inseamna volum pe pista,
 * deci volumul se aplica aici, pe aceeasi scara ca volume.cpp (63 de trepte de 1 dB). Mutul se aplica mereu aici.
 */

#include <lib/service/hdsegalizator.h>
#include <lib/service/hdsegalizator_dsp.h>
#include <lib/service/hdsegalizator_flux.h>
#include <lib/base/ebase.h>
#include <lib/base/eerror.h>
#include <lib/base/message.h>
#include <lib/dvb/volume.h>

#if HAVE_GSTREAMER
#include <gst/gst.h>
#endif

#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>
#include <linux/dvb/dmx.h>

/* ceasul demultiplexorului: ABI-ul driverului DVB ('o' 50), scos din antetele noi ale nucleului, pastrat de drivere */
#ifdef DMX_GET_STC
typedef struct dmx_stc CeasDemux;
#define CERERE_CEAS DMX_GET_STC
#else
struct CeasDemux
{
	unsigned int num;       /* ce ceas (0) */
	unsigned int base;      /* impartitorul pana la 90 kHz */
	unsigned long long stc;
};
#define CERERE_CEAS _IOR('o', 50, struct CeasDemux)
#endif

#include <stdlib.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <deque>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

using namespace hdsegal;

namespace
{
	const int PRIMA_DATA_MS = 3000;       /* fara niciun octet de sunet atata timp de la pornire: sunetul inapoi pe placa */
	const int FARA_DATE_MS = 2000;        /* dupa ce au mers: starea „fara date” */
	const int PERIOADA_ALSA = 480;        /* 10 ms */
	const unsigned LATENTA_ALSA_US = 100000;
	const int LATENTA_PLACA_MS = 60;      /* de la ALSA la iesire: tamponul pistei din placa si iesirea (Latency 40 ms) */
	const int TV_FARA_CEAS_MS = 4000;     /* TV: fara ceasul imaginii atata timp, sunetul se intoarce pe placa */
	const int TV_NEPOTRIVIT_MS = 8000;    /* TV: fara sincron atata timp de la pornire, la fel */
	const int POTRIVIRE_TV_MAX_MS = 300;
	const int CADERI_ALSA = 20;           /* scrieri ALSA cazute la rand dupa care sunetul se intoarce pe placa */
	const size_t MAX_APPSRC = 256 * 1024; /* octeti in coada appsrc (demux): peste atat bucatile se arunca */
	const size_t MARIME_TAMPON_DEMUX = 128 * 1024;

	uint64_t acumMs()
	{
		struct timespec t;
		clock_gettime(CLOCK_MONOTONIC, &t);
		return (uint64_t)t.tv_sec * 1000u + (uint64_t)t.tv_nsec / 1000000u;
	}

	uint64_t procesorFirNs()
	{
		struct timespec t;
		clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t);
		return (uint64_t)t.tv_sec * 1000000000ull + (uint64_t)t.tv_nsec;
	}

	void numeFir(const char *nume)
	{
		pthread_setname_np(pthread_self(), nume);
	}

	/* ---------------------------------------------------------------- libasound, incarcata la nevoie */
	struct Alsa
	{
		/* valorile din alsa/pcm.h si alsa/mixer.h (ABI stabil): SND_PCM_STREAM_PLAYBACK, SND_PCM_FORMAT_S16_LE,
		   SND_PCM_ACCESS_RW_INTERLEAVED, SND_PCM_NONBLOCK, SND_PCM_STATE_DRAINING, SND_MIXER_SCHN_FRONT_LEFT */
		enum { REDARE = 0, S16_LE = 2, RW_INTRETESUT = 3, NEBLOCANT = 1, STARE_GOLIRE = 5, CANAL_STANGA = 0 };
		typedef int (*f_open)(void **, const char *, int, int);
		typedef int (*f_set_params)(void *, int, int, unsigned, unsigned, int, unsigned);
		typedef long (*f_writei)(void *, const void *, unsigned long);
		typedef int (*f_recover)(void *, int, int);
		typedef int (*f_close)(void *);
		typedef int (*f_drop)(void *);
		typedef int (*f_drain)(void *);
		typedef int (*f_nonblock)(void *, int);
		typedef int (*f_state)(void *);
		typedef const char *(*f_strerror)(int);
		typedef int (*f_delay)(void *, long *);
		/* mixerul (numai citire): o iesire oprita din mixer ar da liniste cu starea „merge” */
		typedef int (*f_mixer_open)(void **, int);
		typedef int (*f_mixer_attach)(void *, const char *);
		typedef int (*f_mixer_register)(void *, void *, void **);
		typedef int (*f_mixer_load)(void *);
		typedef int (*f_mixer_close)(void *);
		typedef void *(*f_elem)(void *);
		typedef const char *(*f_elem_nume)(void *);
		typedef int (*f_elem_are)(void *);
		typedef int (*f_elem_comutator)(void *, int, int *);
		typedef int (*f_elem_domeniu)(void *, long *, long *);
		typedef int (*f_elem_volum)(void *, int, long *);

		void *lib;
		std::once_flag o_data;
		f_open open;
		f_set_params set_params;
		f_writei writei;
		f_recover recover;
		f_close close;
		f_drop drop;
		f_drain drain;
		f_nonblock nonblock;
		f_state state;
		f_strerror strerror;
		f_delay delay;
		f_mixer_open m_open;
		f_mixer_attach m_attach;
		f_mixer_register m_register;
		f_mixer_load m_load;
		f_mixer_close m_close;
		f_elem m_primul;
		f_elem m_urmatorul;
		f_elem_nume m_nume;
		f_elem_are m_are_comutator, m_are_volum;
		f_elem_comutator m_comutator;
		f_elem_domeniu m_domeniu;
		f_elem_volum m_volum;

		Alsa(): lib(0), open(0), set_params(0), writei(0), recover(0), close(0), drop(0), drain(0), nonblock(0),
			state(0), strerror(0), delay(0), m_open(0), m_attach(0), m_register(0), m_load(0), m_close(0), m_primul(0),
			m_urmatorul(0), m_nume(0), m_are_comutator(0), m_are_volum(0), m_comutator(0), m_domeniu(0), m_volum(0) {}

		/* o singura data, de pe orice fir (firul enigma2 si firul de control o pot cere deodata) */
		bool incarca()
		{
			std::call_once(o_data, [this] { incarcaAcum(); });
			return lib != 0;
		}

		/* iesirea placii `placa` oprita din mixer: 1 da (comutatorul „Master” oprit, „ALL” pornit, sau volumul lor la
		   minim), 0 nu, -1 nu se stie (mixerul nu se poate citi). Numai citire.
		   „ALL Playback Switch” e al placii HiSilicon (HISIAIAO) si e MUTUL tuturor iesirilor: driverul (hi_aiao.ko,
		   snd_soc_put_hisi_switch) da valoarea direct functiei de mut, deci pornit = mut, oprit = sunet (pe receptor e oprit
		   si sunetul se aude). Un „Master” obisnuit e invers: pornit = sunet. */
		int iesireOprita(const std::string &placa)
		{
			if (!incarca() || !m_open)
				return -1;
			/* mixerul placii: „hw:N” din numele placii ALSA („hw:N,M”, „plughw:N,M”), altfel cel implicit */
			std::string ctl = "default";
			size_t p = placa.find("hw:");
			if (p != std::string::npos)
			{
				size_t v = placa.find(',', p);
				ctl = "hw:" + placa.substr(p + 3, v == std::string::npos ? std::string::npos : v - p - 3);
			}
			void *mixer = 0;
			if (m_open(&mixer, 0) < 0 || !mixer)
				return -1;
			int rez = -1;
			if (m_attach(mixer, ctl.c_str()) >= 0 && m_register(mixer, 0, 0) >= 0 && m_load(mixer) >= 0)
			{
				rez = 0;
				for (void *e = m_primul(mixer); e; e = m_urmatorul(e))
				{
					const char *n = m_nume(e);
					if (!n || (strcmp(n, "ALL") && strcmp(n, "Master")))
						continue;
					int pornit = 1;
					const bool e_mut = strcmp(n, "ALL") == 0;
					if (m_are_comutator(e) && m_comutator(e, CANAL_STANGA, &pornit) >= 0 && (e_mut ? pornit : !pornit))
					{
						eDebug("[HdsEgalizator] mixerul %s: %s", ctl.c_str(), e_mut ? "comutatorul ALL pornit (mut)" :
							"comutatorul Master oprit");
						rez = 1;
					}
					long mic = 0, mare = 0, vol = 0;
					if (m_are_volum(e) && m_domeniu(e, &mic, &mare) >= 0 && mare > mic &&
						m_volum(e, CANAL_STANGA, &vol) >= 0 && vol <= mic)
					{
						eDebug("[HdsEgalizator] mixerul %s: volumul %s la minim", ctl.c_str(), n);
						rez = 1;
					}
				}
			}
			m_close(mixer);
			return rez;
		}

	private:
		void incarcaAcum()
		{
			void *l = dlopen("libasound.so.2", RTLD_NOW | RTLD_LOCAL);
			if (!l)
			{
				eDebug("[HdsEgalizator] libasound.so.2 lipseste: %s", dlerror());
				return;
			}
			open = (f_open)dlsym(l, "snd_pcm_open");
			set_params = (f_set_params)dlsym(l, "snd_pcm_set_params");
			writei = (f_writei)dlsym(l, "snd_pcm_writei");
			recover = (f_recover)dlsym(l, "snd_pcm_recover");
			close = (f_close)dlsym(l, "snd_pcm_close");
			drop = (f_drop)dlsym(l, "snd_pcm_drop");
			drain = (f_drain)dlsym(l, "snd_pcm_drain");
			nonblock = (f_nonblock)dlsym(l, "snd_pcm_nonblock");
			state = (f_state)dlsym(l, "snd_pcm_state");
			strerror = (f_strerror)dlsym(l, "snd_strerror");
			delay = (f_delay)dlsym(l, "snd_pcm_delay");     /* numai pentru sincronul TV; fara ea se ia latenta pusa la deschidere */
			if (!open || !set_params || !writei || !recover || !close || !drop || !drain || !nonblock || !state || !strerror)
			{
				eDebug("[HdsEgalizator] libasound.so.2 fara functiile de redare");
				dlclose(l);
				return;
			}
			m_open = (f_mixer_open)dlsym(l, "snd_mixer_open");
			m_attach = (f_mixer_attach)dlsym(l, "snd_mixer_attach");
			m_register = (f_mixer_register)dlsym(l, "snd_mixer_selem_register");
			m_load = (f_mixer_load)dlsym(l, "snd_mixer_load");
			m_close = (f_mixer_close)dlsym(l, "snd_mixer_close");
			m_primul = (f_elem)dlsym(l, "snd_mixer_first_elem");
			m_urmatorul = (f_elem)dlsym(l, "snd_mixer_elem_next");
			m_nume = (f_elem_nume)dlsym(l, "snd_mixer_selem_get_name");
			m_are_comutator = (f_elem_are)dlsym(l, "snd_mixer_selem_has_playback_switch");
			m_are_volum = (f_elem_are)dlsym(l, "snd_mixer_selem_has_playback_volume");
			m_comutator = (f_elem_comutator)dlsym(l, "snd_mixer_selem_get_playback_switch");
			m_domeniu = (f_elem_domeniu)dlsym(l, "snd_mixer_selem_get_playback_volume_range");
			m_volum = (f_elem_volum)dlsym(l, "snd_mixer_selem_get_playback_volume");
			if (!m_open || !m_attach || !m_register || !m_load || !m_close || !m_primul || !m_urmatorul || !m_nume ||
				!m_are_comutator || !m_are_volum || !m_comutator || !m_domeniu || !m_volum)
			{
				/* fara functiile mixerului se merge mai departe: lipseste numai verificarea iesirii oprite */
				eDebug("[HdsEgalizator] libasound.so.2 fara functiile mixerului");
				m_open = 0;
			}
			lib = l;
		}
	};

	Alsa alsa;

	/* coborarea si linistea din tamponul placii se aud pana la capat, dar cel mult ~200 ms: o placa blocata nu tine firul
	   de iesire (si prin el firul de control, care il asteapta) */
	void golesteCuLimita(void *pcm)
	{
		alsa.nonblock(pcm, 1);
		if (alsa.drain(pcm) == -EAGAIN)
			for (int i = 0; i < 20 && alsa.state(pcm) == Alsa::STARE_GOLIRE; i++)
				usleep(10000);
		if (alsa.state(pcm) == Alsa::STARE_GOLIRE)
			alsa.drop(pcm);
	}

	/* ---------------------------------------------------------------- PES -> flux elementar audio */
	class PesLaEs
	{
	public:
		/* bucati de PES taiate oricum -> octetii sunetului (stream id 0xC0-0xDF) adaugati in `es`; cu `pts`, pentru
		   fiecare PES cu PTS: (locul in `es` unde incepe sunetul lui, PTS-ul pe 33 de biti) */
		void adauga(const uint8_t *d, size_t n, std::vector<uint8_t> &es,
			std::vector<std::pair<size_t, uint64_t> > *pts = 0)
		{
			m_buf.insert(m_buf.end(), d, d + n);
			size_t i = 0, pastreaza = m_buf.size();
			const size_t marime = m_buf.size();
			while (true)
			{
				size_t p = cauta(i);
				if (p == NIMIC)
				{
					pastreaza = marime > 3 ? marime - 3 : 0;
					if (pastreaza < i)
						pastreaza = i;
					break;
				}
				if (p + 9 > marime)
				{
					pastreaza = p;
					break;
				}
				if ((m_buf[p + 6] & 0xC0) != 0x80)
				{
					i = p + 1;
					continue;
				}
				size_t lungime = ((size_t)m_buf[p + 4] << 8) | m_buf[p + 5];
				size_t inceput = p + 9 + m_buf[p + 8];
				size_t sfarsit;
				if (lungime == 0)
				{
					size_t q = cauta(inceput);
					if (q == NIMIC)
					{
						pastreaza = p;
						break;
					}
					sfarsit = q;
				}
				else
				{
					sfarsit = p + 6 + lungime;
					if (sfarsit > marime)
					{
						pastreaza = p;
						break;
					}
				}
				if (inceput < sfarsit)
				{
					if (pts && (m_buf[p + 7] & 0x80) && m_buf[p + 8] >= 5)
					{
						const uint8_t *h = &m_buf[p + 9];
						uint64_t v = ((uint64_t)(h[0] & 0x0E) << 29) | ((uint64_t)h[1] << 22) |
							((uint64_t)(h[2] & 0xFE) << 14) | ((uint64_t)h[3] << 7) | (uint64_t)(h[4] >> 1);
						pts->push_back(std::make_pair(es.size(), v));
					}
					es.insert(es.end(), m_buf.begin() + inceput, m_buf.begin() + sfarsit);
				}
				i = sfarsit;
			}
			m_buf.erase(m_buf.begin(), m_buf.begin() + pastreaza);
			if (m_buf.size() > 512 * 1024)
				m_buf.clear();
		}

		void goleste() { m_buf.clear(); }

	private:
		static const size_t NIMIC = (size_t)-1;

		size_t cauta(size_t de_la) const
		{
			for (size_t k = de_la; k + 3 < m_buf.size(); k++)
				if (m_buf[k] == 0 && m_buf[k + 1] == 0 && m_buf[k + 2] == 1 && (m_buf[k + 3] & 0xE0) == 0xC0)
					return k;
			return NIMIC;
		}

		std::vector<uint8_t> m_buf;
	};

	/* ---------------------------------------------------------------- LOAS -> cadre intregi (AAC in LATM) */
	class LoasCadre
	{
	public:
		/* fluxul LOAS (sincronizarea 0x2B7 pe 11 biti, lungimea pe 13 biti) -> cadre intregi, cate unul pe bucata:
		   decodorul LATM vrea cadrele despartite (aacparse nu le desparte bine). Un inceput fals se sare cand dupa
		   cadru nu urmeaza alta sincronizare. */
		void adauga(const uint8_t *d, size_t n, std::vector<std::vector<uint8_t> > &cadre)
		{
			m_buf.insert(m_buf.end(), d, d + n);
			size_t i = 0;
			while (i + 3 <= m_buf.size())
			{
				if (m_buf[i] != 0x56 || (m_buf[i + 1] & 0xE0) != 0xE0)
				{
					i++;
					continue;
				}
				size_t l = 3 + (((size_t)(m_buf[i + 1] & 0x1f) << 8) | m_buf[i + 2]);
				if (i + l > m_buf.size())
					break;
				if (i + l + 2 <= m_buf.size() && (m_buf[i + l] != 0x56 || (m_buf[i + l + 1] & 0xE0) != 0xE0))
				{
					i++;
					continue;
				}
				cadre.push_back(std::vector<uint8_t>(m_buf.begin() + i, m_buf.begin() + i + l));
				i += l;
			}
			m_buf.erase(m_buf.begin(), m_buf.begin() + i);
			if (m_buf.size() > 64 * 1024)
				m_buf.clear();
		}

	private:
		std::vector<uint8_t> m_buf;
	};

	/* ---------------------------------------------------------------- pachete TS -> PES (numai fisiere de proba) */
	class TsLaPes
	{
	public:
		explicit TsLaPes(int pid): m_pid(pid) {}

		/* pachete intregi de 188 de octeti; cu pid -1 se alege primul PID care incepe un PES audio */
		void adauga(const uint8_t *d, size_t n, std::vector<uint8_t> &pes)
		{
			for (size_t o = 0; o + 188 <= n; o += 188)
			{
				const uint8_t *p = d + o;
				if (p[0] != 0x47)
					continue;
				int pid = ((p[1] & 0x1f) << 8) | p[2];
				bool inceput = p[1] & 0x40;
				int afc = (p[3] >> 4) & 3;
				if (!(afc & 1))
					continue;
				size_t poz = 4;
				if (afc & 2)
					poz += 1 + p[4];
				if (poz >= 188)
					continue;
				if (m_pid < 0)
				{
					if (inceput && poz + 4 <= 188 && p[poz] == 0 && p[poz + 1] == 0 && p[poz + 2] == 1 &&
						(p[poz + 3] & 0xE0) == 0xC0)
						m_pid = pid;
					else
						continue;
				}
				if (pid == m_pid)
					pes.insert(pes.end(), p + poz, p + 188);
			}
		}

		int pid() const { return m_pid; }

	private:
		int m_pid;
	};

	/* ---------------------------------------------------------------- felul fluxului dupa primele cadre */
	inline int felDinEs(const uint8_t *d, size_t n)
	{
		for (size_t i = 0; i + 4 < n; i++)
		{
			if (d[i] == 0x56 && (d[i + 1] & 0xE0) == 0xE0)
			{
				size_t lung = ((size_t)(d[i + 1] & 0x1f) << 8) | d[i + 2];
				size_t urm = i + 3 + lung;
				if (urm + 1 < n && d[urm] == 0x56 && (d[urm + 1] & 0xE0) == 0xE0)
					return eHdsEgalizator::felAacLatm;
			}
			if (d[i] == 0xFF && (d[i + 1] & 0xF0) == 0xF0 && ((d[i + 1] >> 1) & 3) == 0)
			{
				size_t lung = ((size_t)(d[i + 3] & 3) << 11) | ((size_t)d[i + 4] << 3) | (i + 5 < n ? d[i + 5] >> 5 : 0);
				size_t urm = i + lung;
				if (lung > 7 && urm + 1 < n && d[urm] == 0xFF && (d[urm + 1] & 0xF6) == 0xF0)
					return eHdsEgalizator::felAacAdts;
			}
			if (d[i] == 0xFF && (d[i + 1] & 0xE0) == 0xE0 && ((d[i + 1] >> 1) & 3) != 0 && ((d[i + 1] >> 3) & 3) != 1)
			{
				int idx = d[i + 2] >> 4;
				if (idx != 0 && idx != 15 && ((d[i + 2] >> 2) & 3) != 3)
					return eHdsEgalizator::felMpeg;
			}
		}
		return -1;
	}

	/* numele codecului dupa primul antet MPEG audio: MP1 / MP2 / MP3 */
	inline const char *numeMpeg(const uint8_t *d, size_t n)
	{
		for (size_t i = 0; i + 3 < n; i++)
			if (d[i] == 0xFF && (d[i + 1] & 0xE0) == 0xE0 && ((d[i + 1] >> 1) & 3) != 0)
			{
				int strat = (d[i + 1] >> 1) & 3;
				return strat == 3 ? "MP1" : (strat == 2 ? "MP2" : "MP3");
			}
		return "MPEG";
	}

	/* ---------------------------------------------------------------- fisier WAV, 16 biti, stereo, 48 kHz */
	class Wav
	{
	public:
		Wav(): m_f(0), m_octeti(0) {}
		~Wav() { inchide(); }

		bool deschide(const std::string &cale)
		{
			m_f = fopen(cale.c_str(), "wb");
			if (!m_f)
				return false;
			m_octeti = 0;
			antet();
			return true;
		}

		void scrie(const int16_t *d, int esantioane)
		{
			if (m_f && fwrite(d, 2, esantioane, m_f) == (size_t)esantioane)
				m_octeti += (uint32_t)esantioane * 2;
		}

		void inchide()
		{
			if (!m_f)
				return;
			fseek(m_f, 0, SEEK_SET);
			antet();
			fclose(m_f);
			m_f = 0;
		}

		bool deschis() const { return m_f != 0; }

	private:
		void pune32(uint8_t *p, uint32_t v) { p[0] = v; p[1] = v >> 8; p[2] = v >> 16; p[3] = v >> 24; }
		void pune16(uint8_t *p, uint16_t v) { p[0] = v; p[1] = v >> 8; }

		void antet()
		{
			uint8_t h[44];
			memcpy(h, "RIFF", 4);
			pune32(h + 4, 36 + m_octeti);
			memcpy(h + 8, "WAVEfmt ", 8);
			pune32(h + 16, 16);
			pune16(h + 20, 1);
			pune16(h + 22, CANALE);
			pune32(h + 24, RATA);
			pune32(h + 28, RATA * CANALE * 2);
			pune16(h + 32, CANALE * 2);
			pune16(h + 34, 16);
			memcpy(h + 36, "data", 4);
			pune32(h + 40, m_octeti);
			if (fwrite(h, 1, 44, m_f) != 44)
				eDebug("[HdsEgalizator] antetul WAV nu s-a scris");
		}

		FILE *m_f;
		uint32_t m_octeti;
	};

	struct Sursa
	{
		int demux, pid, fel;
		bool tv;              /* canal cu imagine: sunetul se tine dupa ceasul imaginii */
		std::string fisier, wav;
		Sursa(): demux(-1), pid(-1), fel(-1), tv(false) {}
		bool aceeasi(const Sursa &a) const
		{
			return demux == a.demux && pid == a.pid && fel == a.fel && tv == a.tv && fisier == a.fisier;
		}
		bool valida() const { return pid >= 0 || !fisier.empty(); }
	};

	/* cele 4 stari care se vad in stare() */
	enum Stare { STARE_OPRIT, STARE_PORNESTE, STARE_MERGE, STARE_FARA_DATE, STARE_EROARE, STARE_PROBA_GATA };
	const char *NUME_STARE[] = { "oprit", "porneste", "merge", "fara-date", "eroare", "proba-gata" };

	/* mesajele catre firul enigma2 (acelasi numar ca semnalul schimbare) */
	enum { MESAJ_MERGE = 1, MESAJ_OPRIT = 2, MESAJ_INAPOI_PE_PLACA = 3, MESAJ_FARA_DATE = 4, MESAJ_PROBA_GATA = 5 };
}

/* ======================================================================== motorul (firele) */

class eHdsEgalizatorMotor
{
public:
	struct Sesiune
	{
		Sursa sursa, cerut;
		eHdsEgalizatorMotor *motor;
#if HAVE_GSTREAMER
		GstElement *pipe, *appsrc, *appsink, *decodor;
#endif
		std::thread cititor, iesire;
		std::atomic<bool> gata;
		int fd;
		void *pcm;
		Lant lant;
		Spectru spectru;
		Potrivire potrivire;
		Conversie16 conv;
		Wav wav;
		std::vector<float> tmp;
		std::vector<int16_t> tmp16;
		PesLaEs pes;
		LoasCadre loas;
		LatmLaAdts latm;
		bool reimpacheteaza;            /* LATM: cadrele merg ca ADTS spre decodorul ADTS */
		std::atomic<bool> latm_rau;     /* configuratia LATM a devenit una care nu se poate spune in ADTS */
		std::atomic<int> debit_antet;   /* kbit/s din antetul cadrelor MPEG (0: nu se stie) */
		uint64_t ultim_debit_ms;        /* firul cititor: ultima citire a antetului */
		std::vector<uint8_t> inceput;   /* octetii cititi inainte de pornirea decodorului */
		std::atomic<uint64_t> ns_cit, ns_dec, ns_ies;
		uint64_t ultim_ns_dec;
		std::atomic<uint64_t> octeti_es, cadre;
		std::atomic<uint64_t> ultima_data_ms;
		std::atomic<int> caderi_alsa;
		std::atomic<bool> eos;
		std::atomic<bool> rampaJos;
		std::atomic<double> pregain_db, abatere_ppm;
		std::atomic<int> benzi_active;
		std::atomic<unsigned> limitari;
		unsigned versiune;
		uint64_t pornit_ms;
		std::string decodor_nume, codec;
		bool info_decodor;
		int esantionare, canale;
		/* TV: PTS-ul bucatilor scrise in tampon (numarul cadrului, PTS) si starea sincronului */
		std::mutex lacat_pts;
		std::deque<std::pair<uint64_t, uint64_t> > marcaje;
		uint64_t pts_baza;           /* firul cititor: primul PTS al sesiunii (timpul 0 in GStreamer) */
		std::atomic<bool> pts_baza_ok;
		std::atomic<int> tv_stare;   /* TV_ASTEAPTA, TV_POTRIVIT, TV_FARA_CEAS, TV_NEPOTRIVIT */
		std::atomic<double> eroare_tv_ms;
		std::atomic<unsigned> taceri_tv, aruncari_tv;
		uint64_t ultim_ceas_bun;     /* firul placii */
		int tacere_ramasa;           /* firul placii: cadrele de tacere hotarate de sincron, inca nescrise */

		void marcheaza(uint64_t cadru, uint64_t pts)
		{
			std::lock_guard<std::mutex> l(lacat_pts);
			marcaje.push_back(std::make_pair(cadru, pts & MASCA_PTS));
			while (marcaje.size() > 512)
				marcaje.pop_front();
		}

		/* PTS-ul cadrului `cadru` (din marcajul de dinaintea lui, 48 kHz = 15/8 pasi de 90 kHz pe cadru) */
		bool ptsLa(uint64_t cadru, uint64_t &pts)
		{
			std::lock_guard<std::mutex> l(lacat_pts);
			while (marcaje.size() > 1 && marcaje[1].first <= cadru && cadru - marcaje[1].first > (uint64_t)RATA)
				marcaje.pop_front();
			if (marcaje.empty())
				return false;
			const std::pair<uint64_t, uint64_t> *m = &marcaje.front();
			for (size_t i = marcaje.size(); i-- > 0;)
				if (marcaje[i].first <= cadru)
				{
					m = &marcaje[i];
					break;
				}
			int64_t dif = (int64_t)(cadru - m->first);
			pts = (uint64_t)((int64_t)m->second + dif * 15 / 8) & MASCA_PTS;
			return true;
		}

		Sesiune(): motor(0),
#if HAVE_GSTREAMER
			pipe(0), appsrc(0), appsink(0), decodor(0),
#endif
			gata(false), fd(-1), pcm(0), reimpacheteaza(false), latm_rau(false), debit_antet(0), ultim_debit_ms(0),
			ns_cit(0), ns_dec(0), ns_ies(0), ultim_ns_dec(0), octeti_es(0), cadre(0),
			ultima_data_ms(0), caderi_alsa(0), eos(false), rampaJos(false), pregain_db(0.0), abatere_ppm(0.0),
			benzi_active(0), limitari(0), versiune(0), pornit_ms(0), info_decodor(false),
			esantionare(0), canale(0), pts_baza(0), pts_baza_ok(false), tv_stare(0), eroare_tv_ms(0.0), taceri_tv(0),
			aruncari_tv(0), ultim_ceas_bun(0), tacere_ramasa(0)
		{
		}
	};
	enum { TV_ASTEAPTA = 0, TV_POTRIVIT = 1, TV_FARA_CEAS = 2, TV_NEPOTRIVIT = 3 };

	eHdsEgalizatorMotor():
		pompa(0), m_cerereSpectru(0), m_stare(STARE_OPRIT), m_versiune(1), m_volum_mod(0), m_placa("default"), m_sesiune(0),
		m_ultim_volum(-1), m_ultim_mut(false), m_volum_aici(true), m_procent(0.0), m_procent_cit(0.0),
		m_procent_dec(0.0), m_procent_ies(0.0), m_debit(0), m_debit_aprox(true), m_ultim_octeti(0), m_ultim_cadre(0),
		m_ultim_masura(0), m_suma_octeti(0.0), m_suma_cadre(0.0), m_volumctl(0), m_tv(true), m_potrivire_tv_ms(0)
	{
		for (int i = 0; i < 3; i++)
			m_ultime_fir[i] = 0;
		std::thread t(&eHdsEgalizatorMotor::firControl, this);
		t.detach();
	}

	eFixedMessagePump<int> *pompa;
	std::atomic<uint64_t> m_cerereSpectru;    /* ultima citire a starii (ms), pentru spectrul la cerere */

	/* ---- firul enigma2 ---- */

	void porneste(const Sursa &s)
	{
		std::lock_guard<std::mutex> l(m_lacatComenzi);
		m_comenzi.push_back(Comanda(Comanda::PORNESTE, s));
		m_cv.notify_one();
	}

	void opreste()
	{
		std::lock_guard<std::mutex> l(m_lacatComenzi);
		m_comenzi.push_back(Comanda(Comanda::OPRESTE, Sursa()));
		m_cv.notify_one();
	}

	/* canalele TV: daca driverul da ceasul demultiplexorului (STC), sunetul din procesor s-ar putea tine dupa imagine;
	   firul de control il citeste de doua ori (numai citire) si pune raspunsul in stare() si in jurnal */
	void probeazaCeasul(int demux)
	{
		Sursa s;
		s.demux = demux;
		std::lock_guard<std::mutex> l(m_lacatComenzi);
		m_comenzi.push_back(Comanda(Comanda::CEAS, s));
		m_cv.notify_one();
	}

	void setBanda(int i, double db)
	{
		std::lock_guard<std::mutex> l(m_lacat);
		m_setari.benzi[i] = limiteaza(db, -CASTIG_MAXIM_DB, CASTIG_MAXIM_DB);
		m_versiune++;
	}

	void setNoapte(bool n)
	{
		std::lock_guard<std::mutex> l(m_lacat);
		m_setari.noapte = n;
		m_versiune++;
	}

	void setNivel(double db)
	{
		std::lock_guard<std::mutex> l(m_lacat);
		m_setari.nivel_db = limiteaza(db, -12.0, 12.0);
		m_versiune++;
	}

	void setVolumMod(int mod)
	{
		std::lock_guard<std::mutex> l(m_lacat);
		m_volum_mod = mod;
		m_ultim_volum = -1;        /* se hotaraste din nou */
	}

	void setPlaca(const std::string &p)
	{
		std::lock_guard<std::mutex> l(m_lacat);
		m_placa = p.empty() ? "default" : p;
	}

	void setVolumControl(eDVBVolumecontrol *v) { m_volumctl = v; }

	void setTv(bool da) { m_tv = da; }
	bool tv() const { return m_tv.load(); }
	void setPotrivireTv(int ms)
	{
		m_potrivire_tv_ms = ms < -POTRIVIRE_TV_MAX_MS ? -POTRIVIRE_TV_MAX_MS : (ms > POTRIVIRE_TV_MAX_MS ? POTRIVIRE_TV_MAX_MS : ms);
	}

	/* PTS-ul imaginii (firul enigma2, de la servicedvb); reseteaza = alt serviciu */
	void ceasImagine(long long pts)
	{
		std::lock_guard<std::mutex> l(m_lacat_ceas);
		m_ceas_imagine.citire(pts, (int64_t)acumMs());
	}

	void reseteazaCeasImagine()
	{
		std::lock_guard<std::mutex> l(m_lacat_ceas);
		m_ceas_imagine.reseteaza();
	}

	bool imagineLa(uint64_t t_ms, uint64_t &pts, int &unitate)
	{
		std::lock_guard<std::mutex> l(m_lacat_ceas);
		unitate = m_ceas_imagine.unitate();
		return m_ceas_imagine.la((int64_t)t_ms, pts);
	}

	/* sursa care merge (sau care porneste) acum, pentru idempotenta alegerii pistei */
	bool mergeCu(const Sursa &s)
	{
		std::lock_guard<std::mutex> l(m_lacat);
		return m_sursa_dorita.valida() && m_sursa_dorita.aceeasi(s);
	}

	bool activ()
	{
		std::lock_guard<std::mutex> l(m_lacat);
		return m_sursa_dorita.valida();
	}

	bool proba()
	{
		std::lock_guard<std::mutex> l(m_lacat);
		return !m_sursa_dorita.fisier.empty();
	}

	void noteazaDorita(const Sursa &s)
	{
		std::lock_guard<std::mutex> l(m_lacat);
		m_sursa_dorita = s;
	}

	bool esuata(const Sursa &s)
	{
		std::lock_guard<std::mutex> l(m_lacat);
		return m_esuata.valida() && m_esuata.aceeasi(s);
	}

	void uitaEsuata()
	{
		std::lock_guard<std::mutex> l(m_lacat);
		m_esuata = Sursa();
	}

	PyObject *stare(const std::string &post);

	/* ---- firul de control ---- */
private:
	struct Comanda
	{
		enum Fel { PORNESTE, OPRESTE, CEAS } fel;
		Sursa sursa;
		Comanda(Fel f, const Sursa &s): fel(f), sursa(s) {}
	};

	void trimite(int cod)
	{
		if (pompa)
			pompa->send(cod);
	}

	void seteazaStarea(Stare s, const std::string &motiv)
	{
		std::lock_guard<std::mutex> l(m_lacat);
		m_stare = s;
		m_motiv = motiv;
	}

	void firControl()
	{
		numeFir("hds-egal");
		while (true)
		{
			std::deque<Comanda> de_facut;
			{
				std::unique_lock<std::mutex> l(m_lacatComenzi);
				m_cv.wait_for(l, std::chrono::milliseconds(200), [this] { return !m_comenzi.empty(); });
				de_facut.swap(m_comenzi);
			}
			/* din mai multe comenzi la rand conteaza numai ultima pornire sau oprire (o schimbare rapida de posturi);
			   proba ceasului nu tine de sesiune */
			const Comanda *ultima = 0;
			for (size_t i = 0; i < de_facut.size(); i++)
			{
				if (de_facut[i].fel == Comanda::CEAS)
					citesteCeasul(de_facut[i].sursa.demux);
				else
					ultima = &de_facut[i];
			}
			if (ultima)
			{
				const Comanda &c = *ultima;
				if (c.fel == Comanda::PORNESTE)
				{
					inchideSesiunea();
					deschideSesiunea(c.sursa);
				}
				else
				{
					bool era = m_sesiune != 0;
					inchideSesiunea();
					seteazaStarea(STARE_OPRIT, "");
					if (era)
						trimite(MESAJ_OPRIT);
				}
			}
			verifica();
		}
	}

	/* `s` e o copie: de cele mai multe ori vine din sesiunea pe care inchideSesiunea() o sterge */
	void esec(Sursa s, const std::string &motiv)
	{
		eDebug("[HdsEgalizator] sunetul se intoarce pe placa: %s", motiv.c_str());
		inchideSesiunea();
		{
			std::lock_guard<std::mutex> l(m_lacat);
			m_stare = STARE_EROARE;
			m_motiv = motiv;
			if (s.fisier.empty())
				m_esuata = s;
			/* alt post, pornit intre timp, ramane dorit */
			if (m_sursa_dorita.aceeasi(s))
				m_sursa_dorita = Sursa();
		}
		trimite(s.fisier.empty() ? MESAJ_INAPOI_PE_PLACA : MESAJ_OPRIT);
	}

	void citesteCeasul(int demux);
	void notaDebit(Sesiune *s, const std::vector<uint8_t> &es);
	void deschideSesiunea(const Sursa &cerut);
	void inchideSesiunea();
	void verifica();
	void volum();
	void procesor();
	void firCititor(Sesiune *s);
	void firIesire(Sesiune *s);
	void prelucreaza(Sesiune *s, const float *date, int cadre, long long pts90);
	int sincronTv(Sesiune *s);
	void impingeTv(Sesiune *s, const std::vector<uint8_t> &es, const std::vector<std::pair<size_t, uint64_t> > &pts);
	void impingeCuPts(Sesiune *s, const uint8_t *d, size_t n, bool are_pts, uint64_t pts);
#if HAVE_GSTREAMER
	static GstFlowReturn laMostra(GstElement *sink, gpointer user);
	void infoDecodor(Sesiune *s);
#endif
	void impinge(Sesiune *s, const std::vector<uint8_t> &es, bool asteapta);
	void impingeBucata(Sesiune *s, const std::vector<uint8_t> &b);

	std::mutex m_lacatComenzi;
	std::condition_variable m_cv;
	std::deque<Comanda> m_comenzi;

	/* m_lacat: setarile, starea, sursele (firul enigma2 <-> firul de control <-> firul de decodare) */
	std::mutex m_lacat;
	Setari m_setari;
	Stare m_stare;
	std::string m_motiv;
	unsigned m_versiune;
	int m_volum_mod;
	std::string m_placa;
	Sursa m_sursa_dorita, m_esuata;
	std::string m_ceas_tv;                /* proba ceasului STC: „da”, „nu”, „fara-demux” sau gol */

	/* numai pe firul de control */
	Sesiune *m_sesiune;
	int m_ultim_volum;
	bool m_ultim_mut;
	bool m_volum_aici;
	double m_procent, m_procent_cit, m_procent_dec, m_procent_ies;
	int m_debit;
	bool m_debit_aprox;                   /* debitul din octeti (AAC), nu din antet */
	uint64_t m_ultim_octeti, m_ultim_cadre, m_ultim_masura;
	double m_suma_octeti, m_suma_cadre;   /* ferestre de ~10 s pentru debit */
	uint64_t m_ultime_fir[3];
	eDVBVolumecontrol *m_volumctl;
	/* canalele TV */
	std::atomic<bool> m_tv;
	std::atomic<int> m_potrivire_tv_ms;
	std::mutex m_lacat_ceas;
	CeasImagine m_ceas_imagine;
};

/* ------------------------------------------------------------------------ decodoarele din GStreamer */

namespace
{
	struct Decodoare
	{
		bool gst;
		std::string mpeg, adts, latm;
		std::once_flag o_data;
		Decodoare(): gst(false) {}
	};
	Decodoare decodoare_;

#if HAVE_GSTREAMER
	inline bool exista(const char *nume)
	{
		GstElementFactory *f = gst_element_factory_find(nume);
		if (!f)
			return false;
		gst_object_unref(f);
		return true;
	}

	inline std::string primul(const char *const *nume)
	{
		for (; *nume; nume++)
			if (exista(*nume))
				return *nume;
		return "";
	}
#endif

	void cautaDecodoare()
	{
#if HAVE_GSTREAMER
		GError *err = 0;
		if (!gst_is_initialized() && !gst_init_check(0, 0, &err))
		{
			eDebug("[HdsEgalizator] GStreamer nu porneste: %s", err ? err->message : "?");
			if (err)
				g_error_free(err);
			return;
		}
		decodoare_.gst = true;
		static const char *const mpeg[] = { "mpg123audiodec", "avdec_mp2float", 0 };
		static const char *const adts[] = { "faad", "fdkaacdec", "avdec_aac", 0 };
		static const char *const latm[] = { "avdec_aac_latm", "fdkaacdec", 0 };
		if (exista("mpegaudioparse"))
			decodoare_.mpeg = primul(mpeg);
		if (exista("aacparse"))
		{
			decodoare_.adts = primul(adts);
			decodoare_.latm = primul(latm);
		}
		eDebug("[HdsEgalizator] decodoare: MPEG %s, AAC ADTS %s, AAC LATM %s",
			decodoare_.mpeg.empty() ? "-" : decodoare_.mpeg.c_str(),
			decodoare_.adts.empty() ? "-" : decodoare_.adts.c_str(),
			!decodoare_.adts.empty() ? "prin ADTS" : (decodoare_.latm.empty() ? "-" : decodoare_.latm.c_str()));
#endif
	}

	/* o singura cautare, de pe orice fir (firul enigma2 si firul de control o pot cere deodata) */
	const Decodoare &decodoare()
	{
		std::call_once(decodoare_.o_data, cautaDecodoare);
		return decodoare_;
	}

	/* LATM: cu un decodor ADTS in imagine, cadrele se impacheteaza ca ADTS (drumul decodorului de pe receptor) */
	const std::string &decodorPentru(int fel)
	{
		const Decodoare &d = decodoare();
		if (fel == eHdsEgalizator::felAacAdts)
			return d.adts;
		if (fel == eHdsEgalizator::felAacLatm)
			return d.adts.empty() ? d.latm : d.adts;
		return d.mpeg;
	}
}

/* ------------------------------------------------------------------------ ceasul demultiplexorului (canalele TV) */

void eHdsEgalizatorMotor::citesteCeasul(int demux)
{
	char cale[64];
	snprintf(cale, sizeof(cale), "/dev/dvb/adapter0/demux%d", demux);
	std::string rez;
	int fd = ::open(cale, O_RDWR | O_CLOEXEC);
	if (fd < 0)
		rez = "fara-demux";
	else
	{
		/* doua citiri la 100 ms: ceasul trebuie sa fi mers ~9000 de pasi de 90 kHz */
		CeasDemux a, b;
		memset(&a, 0, sizeof(a));
		a.num = 0;
		a.base = 1;
		b = a;
		bool bun = ::ioctl(fd, CERERE_CEAS, &a) >= 0;
		if (bun)
		{
			usleep(100000);
			bun = ::ioctl(fd, CERERE_CEAS, &b) >= 0;
		}
		::close(fd);
		long long pasi = 0;
		if (bun)
		{
			unsigned long long va = a.base ? a.stc / a.base : a.stc, vb = b.base ? b.stc / b.base : b.stc;
			pasi = (long long)(vb - va);
		}
		rez = bun && pasi > 4500 && pasi < 18000 ? "da" : "nu";
		eDebug("[HdsEgalizator] ceasul demultiplexorului (STC) pe demux%d: %s (%s, %lld pasi de 90 kHz in 100 ms)",
			demux, rez.c_str(), bun ? "citit" : "DMX_GET_STC refuzat", pasi);
	}
	std::lock_guard<std::mutex> l(m_lacat);
	m_ceas_tv = rez;
}

/* ------------------------------------------------------------------------ sesiunea */

void eHdsEgalizatorMotor::deschideSesiunea(const Sursa &cerut)
{
	Sursa sursa = cerut;
	seteazaStarea(STARE_PORNESTE, "");
#if HAVE_GSTREAMER
	const Decodoare &dec = decodoare();
	if (!dec.gst)
	{
		esec(cerut, "fara-gstreamer");
		return;
	}
	Sesiune *s = new Sesiune();
	s->motor = this;
	s->sursa = sursa;
	s->cerut = cerut;
	s->pornit_ms = acumMs();
	s->tmp.reserve(8192);
	if (!sursa.fisier.empty())
		s->potrivire.faraPotrivire();
	else if (sursa.tv)
		s->potrivire.raportExtern(1.0);     /* TV: raportul il da sincronul cu imaginea */
	{
		/* de aici, esec() inchide tot ce s-a deschis in sesiune */
		std::lock_guard<std::mutex> l(m_lacat);
		m_sesiune = s;
	}
	std::vector<uint8_t> inceput;
	if (!sursa.fisier.empty())
	{
		/* proba: felul fluxului din primii 256 KB ai fisierului (firul cititor il citeste apoi de la capat) */
		FILE *f = fopen(sursa.fisier.c_str(), "rb");
		if (!f)
		{
			esec(cerut, "fisier-lipsa");
			return;
		}
		std::vector<uint8_t> brut(256 * 1024);
		size_t n = fread(brut.data(), 1, brut.size(), f);
		fclose(f);
		brut.resize(n);
		if (n >= 376 && brut[0] == 0x47 && brut[188] == 0x47)
		{
			TsLaPes ts(sursa.pid);
			std::vector<uint8_t> pes;
			ts.adauga(brut.data(), n - n % 188, pes);
			PesLaEs p;
			p.adauga(pes.data(), pes.size(), inceput);
			sursa.pid = ts.pid();
		}
		else
			inceput = brut;
		sursa.fel = felDinEs(inceput.data(), inceput.size());
		if (sursa.fel < 0)
		{
			esec(cerut, "format-necunoscut");
			return;
		}
	}
	else
	{
		char cale[64];
		snprintf(cale, sizeof(cale), "/dev/dvb/adapter0/demux%d", sursa.demux);
		s->fd = ::open(cale, O_RDWR | O_CLOEXEC);
		bool bun = s->fd >= 0;
		if (bun)
		{
			struct dmx_pes_filter_params f;
			memset(&f, 0, sizeof(f));
			f.pid = sursa.pid;
			f.input = DMX_IN_FRONTEND;
			f.output = DMX_OUT_TAP;
			f.pes_type = DMX_PES_OTHER;
			f.flags = DMX_IMMEDIATE_START;
			if (::ioctl(s->fd, DMX_SET_BUFFER_SIZE, MARIME_TAMPON_DEMUX) < 0)
				eDebug("[HdsEgalizator] DMX_SET_BUFFER_SIZE: %m");
			bun = ::ioctl(s->fd, DMX_SET_PES_FILTER, &f) >= 0;
			if (!bun)
				eDebug("[HdsEgalizator] filtrul PES pe %s, PID %d: %m", cale, sursa.pid);
		}
		else
			eDebug("[HdsEgalizator] %s: %m", cale);
		if (!bun)
		{
			esec(cerut, "demux-refuzat");
			return;
		}
		if (sursa.fel != eHdsEgalizator::felMpeg)
		{
			/* AAC: PMT spune numai „AAC” (ADTS si LATM apar sub ambele feluri), deci felul se afla din primele cadre;
			   octetii cititi aici intra primii in decodor */
			uint64_t pana = acumMs() + 800;
			std::vector<uint8_t> buf(16 * 1024);
			int fel = -1;
			while (fel < 0 && acumMs() < pana)
			{
				struct pollfd pfd;
				pfd.fd = s->fd;
				pfd.events = POLLIN;
				pfd.revents = 0;
				if (poll(&pfd, 1, 50) > 0 && (pfd.revents & POLLIN))
				{
					ssize_t n = ::read(s->fd, buf.data(), buf.size());
					if (n > 0)
						s->pes.adauga(buf.data(), (size_t)n, s->inceput);
				}
				fel = felDinEs(s->inceput.data(), s->inceput.size());
			}
			if (fel == eHdsEgalizator::felAacAdts || fel == eHdsEgalizator::felAacLatm)
				sursa.fel = fel;
			if (!s->inceput.empty())
			{
				s->octeti_es += s->inceput.size();
				s->ultima_data_ms = acumMs();
			}
		}
	}
	const std::string &decodor = decodorPentru(sursa.fel);
	if (decodor.empty())
	{
		esec(cerut, sursa.fel == eHdsEgalizator::felMpeg ? "fara-decodor-mpeg" : "fara-decodor-aac");
		return;
	}
	if (sursa.fel == eHdsEgalizator::felAacLatm && !decodoare().adts.empty())
	{
		/* configuratia din primele cadre: una care nu se poate spune in ADTS (mai multe programe, cadre de 960...)
		   intoarce sunetul pe placa; fara configuratie inca (vine din cand in cand) se merge pe ADTS */
		const std::vector<uint8_t> &primii = sursa.fisier.empty() ? s->inceput : inceput;
		LoasCadre loas;
		LatmLaAdts proba;
		std::vector<std::vector<uint8_t> > cadre;
		std::vector<uint8_t> adts;
		loas.adauga(primii.data(), primii.size(), cadre);
		for (size_t i = 0; i < cadre.size() && !proba.cadreFacute() && !proba.nesuportat(); i++)
			proba.cadru(cadre[i].data(), cadre[i].size(), adts);
		if (!proba.cadreFacute() && proba.nesuportat())
		{
			esec(cerut, "latm-nesuportat");
			return;
		}
		s->reimpacheteaza = true;
		if (proba.cadreFacute())
			eDebug("[HdsEgalizator] LATM prin ADTS: profilul %d, esantionarea %d, canalele %d%s%s", proba.config().profil,
				proba.config().idx_esantionare, proba.config().canale, proba.config().sbr ? ", SBR" : "",
				proba.config().ps ? ", PS" : "");
	}
	{
		/* stare() le citeste de pe firul enigma2 */
		std::lock_guard<std::mutex> l(m_lacat);
		s->sursa = sursa;
		s->decodor_nume = decodor;
		if (sursa.fel == eHdsEgalizator::felMpeg)
			s->codec = inceput.empty() ? "MPEG" : numeMpeg(inceput.data(), inceput.size());
		else
			s->codec = sursa.fel == eHdsEgalizator::felAacLatm ? "AAC (LATM)" : "AAC";
	}

	/* iesirea: ALSA pentru posturi si pentru proba in timp real (iesirea „alsa”), altfel fisierul WAV al probei */
	std::string placa;
	{
		std::lock_guard<std::mutex> l(m_lacat);
		placa = m_placa;
	}
	if (sursa.fisier.empty() || sursa.wav.compare(0, 4, "alsa") == 0)
	{
		if (!alsa.incarca())
		{
			esec(cerut, "fara-alsa");
			return;
		}
		if (alsa.iesireOprita(placa) == 1)
		{
			esec(cerut, "placa-oprita");
			return;
		}
		/* deschiderea nu asteapta o placa ocupata (firul de control n-ar mai ajunge la intoarcerea pe placa); scrierile
		   apoi asteapta placa */
		void *pcm = 0;
		int r = alsa.open(&pcm, placa.c_str(), Alsa::REDARE, Alsa::NEBLOCANT);
		if (r >= 0)
		{
			{
				std::lock_guard<std::mutex> l(m_lacat);
				s->pcm = pcm;
			}
			r = alsa.nonblock(pcm, 0);
			if (r >= 0)
				r = alsa.set_params(pcm, Alsa::S16_LE, Alsa::RW_INTRETESUT, CANALE, RATA, 1, LATENTA_ALSA_US);
		}
		if (r < 0)
		{
			eDebug("[HdsEgalizator] placa ALSA %s: %s", placa.c_str(), alsa.strerror(r));
			esec(cerut, "alsa-refuzat");
			return;
		}
	}
	else if (!s->wav.deschide(sursa.wav))
	{
		esec(cerut, "wav-refuzat");
		return;
	}

	/* LATM spre decodorul LATM: cadrele LOAS le desparte firul cititor (LoasCadre), deci fara parser; LATM prin ADTS
	   merge pe drumul ADTS */
	const int drum = s->reimpacheteaza ? (int)eHdsEgalizator::felAacAdts : sursa.fel;
	const char *caps = drum == eHdsEgalizator::felMpeg ? "audio/mpeg,mpegversion=(int)1" :
		(drum == eHdsEgalizator::felAacLatm ?
		"audio/mpeg,mpegversion=(int)4,stream-format=(string)loas,framed=(boolean)true" :
		"audio/mpeg,mpegversion=(int)4,stream-format=(string)adts");
	const char *parser = drum == eHdsEgalizator::felMpeg ? "mpegaudioparse ! " :
		(drum == eHdsEgalizator::felAacLatm ? "" : "aacparse ! ");
	char text[1024];
	snprintf(text, sizeof(text),
		"appsrc name=sursa caps=\"%s\" format=%s is-live=%s block=%s max-bytes=%u ! %s%s name=decodor ! "
		"audioconvert ! audioresample ! audio/x-raw,format=F32LE,rate=%d,channels=%d,layout=interleaved ! "
		"appsink name=iesire emit-signals=true sync=false max-buffers=16 drop=false",
		/* cu parser, octetii intra ca flux (bytes); cadrele LATM despartite merg direct in decodor, care cere timp; la TV
		   fiecare PES intra cu PTS-ul lui (time), ca mostrele decodate sa-l pastreze */
		caps, (drum == eHdsEgalizator::felAacLatm || sursa.tv) ? "time" : "bytes",
		sursa.fisier.empty() ? "true" : "false", sursa.fisier.empty() ? "false" : "true",
		(unsigned)(sursa.fisier.empty() ? MAX_APPSRC * 2 : 65536), parser, decodor.c_str(), RATA, CANALE);
	GError *err = 0;
	GstElement *pipe = gst_parse_launch(text, &err);
	if (!pipe || err)
	{
		eDebug("[HdsEgalizator] drumul GStreamer nu se face: %s", err ? err->message : "?");
		if (err)
			g_error_free(err);
		if (pipe)
			gst_object_unref(pipe);
		esec(cerut, "eroare-gstreamer");
		return;
	}
	s->pipe = pipe;
	s->appsrc = gst_bin_get_by_name(GST_BIN(s->pipe), "sursa");
	s->appsink = gst_bin_get_by_name(GST_BIN(s->pipe), "iesire");
	s->decodor = gst_bin_get_by_name(GST_BIN(s->pipe), "decodor");
	if (!s->appsrc || !s->appsink || !s->decodor)
	{
		esec(cerut, "eroare-gstreamer");
		return;
	}
	g_signal_connect(s->appsink, "new-sample", G_CALLBACK(&eHdsEgalizatorMotor::laMostra), s);

	/* lantul porneste direct cu setarile de acum si urca in RAMPA_MS */
	{
		std::lock_guard<std::mutex> l(m_lacat);
		s->lant.seteaza(m_setari);
		s->versiune = m_versiune;
	}
	s->lant.aseazaBenzile();
	s->lant.rampa(true);

	if (gst_element_set_state(s->pipe, GST_STATE_PLAYING) == GST_STATE_CHANGE_FAILURE)
	{
		esec(cerut, "eroare-gstreamer");
		return;
	}
	s->cititor = std::thread(&eHdsEgalizatorMotor::firCititor, this, s);
	if (s->pcm)
		s->iesire = std::thread(&eHdsEgalizatorMotor::firIesire, this, s);
	m_ultim_volum = -1;
	m_ultim_octeti = 0;
	m_ultim_cadre = 0;
	m_suma_octeti = m_suma_cadre = 0.0;
	m_ultim_masura = acumMs();
	{
		std::lock_guard<std::mutex> l(m_lacat);
		m_debit = 0;
		m_debit_aprox = true;
	}
	for (int i = 0; i < 3; i++)
		m_ultime_fir[i] = 0;
	eDebug("[HdsEgalizator] pornit: %s%s, PID %d, %s, %s%s, iesirea %s", sursa.fisier.empty() ? "demux" : sursa.fisier.c_str(),
		sursa.tv ? " (TV, dupa ceasul imaginii)" : "", sursa.pid, s->codec.c_str(), decodor.c_str(),
		s->reimpacheteaza ? " (prin ADTS)" : "", sursa.fisier.empty() ? placa.c_str() : sursa.wav.c_str());
#else
	esec(cerut, "fara-gstreamer");
#endif
}

void eHdsEgalizatorMotor::inchideSesiunea()
{
	Sesiune *s = m_sesiune;
	if (!s)
		return;
	{
		/* stare() (firul enigma2) citeste sesiunea sub lacat: de aici nu o mai vede */
		std::lock_guard<std::mutex> l(m_lacat);
		m_sesiune = 0;
	}
	/* iesirea coboara in 20 ms, scrie doua perioade de liniste, le lasa sa se auda si se opreste singura */
	if (s->iesire.joinable())
	{
		s->rampaJos = true;
		s->iesire.join();
	}
	s->gata = true;
#if HAVE_GSTREAMER
	/* starea NULL deblocheaza si o impingere care asteapta loc in coada (proba din fisier) */
	if (s->appsrc)
	{
		GstFlowReturn r;
		g_signal_emit_by_name(s->appsrc, "end-of-stream", &r);
	}
	if (s->pipe)
		gst_element_set_state(s->pipe, GST_STATE_NULL);
#endif
	if (s->cititor.joinable())
		s->cititor.join();
	if (s->fd >= 0)
	{
		::ioctl(s->fd, DMX_STOP);
		::close(s->fd);
	}
	if (s->pcm)
		alsa.close(s->pcm);
	s->wav.inchide();
#if HAVE_GSTREAMER
	if (s->decodor)
		gst_object_unref(s->decodor);
	if (s->appsink)
		gst_object_unref(s->appsink);
	if (s->appsrc)
		gst_object_unref(s->appsrc);
	if (s->pipe)
		gst_object_unref(s->pipe);
#endif
	eDebug("[HdsEgalizator] oprit dupa %llu ms: %llu octeti de sunet, %llu cadre, %u goluri",
		(unsigned long long)(acumMs() - s->pornit_ms), (unsigned long long)s->octeti_es.load(),
		(unsigned long long)s->cadre.load(), s->potrivire.goluri());
	if (s->sursa.tv)
		eDebug("[HdsEgalizator] TV: sincronul %s, ultima abatere %.0f ms, %u perioade de tacere, %u aruncari",
			s->tv_stare.load() == TV_POTRIVIT ? "potrivit" : (s->tv_stare.load() == TV_FARA_CEAS ? "fara ceasul imaginii" :
			(s->tv_stare.load() == TV_NEPOTRIVIT ? "nepotrivit" : "inca nepotrivit")), s->eroare_tv_ms.load(),
			s->taceri_tv.load(), s->aruncari_tv.load());
	delete s;
}

/* ------------------------------------------------------------------------ firele */

void eHdsEgalizatorMotor::impinge(Sesiune *s, const std::vector<uint8_t> &es, bool asteapta)
{
#if HAVE_GSTREAMER
	if (es.empty() || !s->appsrc)
		return;
	if (!asteapta)
	{
		guint64 nivel = 0;
		g_object_get(s->appsrc, "current-level-bytes", &nivel, NULL);
		if (nivel > MAX_APPSRC)
			return;               /* decodorul a ramas in urma: bucata se pierde, nu memoria */
	}
	if (s->sursa.fel == eHdsEgalizator::felAacLatm)
	{
		std::vector<std::vector<uint8_t> > cadre;
		s->loas.adauga(es.data(), es.size(), cadre);
		if (s->reimpacheteaza)
		{
			std::vector<uint8_t> adts;
			for (size_t i = 0; i < cadre.size(); i++)
				s->latm.cadru(cadre[i].data(), cadre[i].size(), adts);
			if (s->latm.nesuportat())
				s->latm_rau = true;
			if (!adts.empty())
				impingeBucata(s, adts);
		}
		else
			for (size_t i = 0; i < cadre.size(); i++)
				impingeBucata(s, cadre[i]);
	}
	else
		impingeBucata(s, es);
#else
	(void)s;
	(void)es;
	(void)asteapta;
#endif
}

void eHdsEgalizatorMotor::impingeBucata(Sesiune *s, const std::vector<uint8_t> &b)
{
#if HAVE_GSTREAMER
	GstBuffer *g = gst_buffer_new_allocate(NULL, b.size(), NULL);
	gst_buffer_fill(g, 0, b.data(), b.size());
	GstFlowReturn r;
	g_signal_emit_by_name(s->appsrc, "push-buffer", g, &r);
	gst_buffer_unref(g);
#else
	(void)s;
	(void)b;
#endif
}

/* TV: fiecare PES cu PTS-ul lui; octetii de dinaintea primului PTS al sesiunii nu intra (fara timp) */
void eHdsEgalizatorMotor::impingeTv(Sesiune *s, const std::vector<uint8_t> &es,
	const std::vector<std::pair<size_t, uint64_t> > &pts)
{
#if HAVE_GSTREAMER
	if (es.empty() || !s->appsrc)
		return;
	guint64 nivel = 0;
	g_object_get(s->appsrc, "current-level-bytes", &nivel, NULL);
	if (nivel > MAX_APPSRC)
		return;
	size_t de_la = 0;
	bool are = false;
	uint64_t p = 0;
	for (size_t i = 0; i <= pts.size(); i++)
	{
		size_t pana = i < pts.size() ? pts[i].first : es.size();
		if (pana > de_la && (are || s->pts_baza_ok))
			impingeCuPts(s, es.data() + de_la, pana - de_la, are, p);
		if (i < pts.size())
		{
			de_la = pts[i].first;
			are = true;
			p = pts[i].second;
		}
	}
#else
	(void)s;
	(void)es;
	(void)pts;
#endif
}

void eHdsEgalizatorMotor::impingeCuPts(Sesiune *s, const uint8_t *d, size_t n, bool are_pts, uint64_t pts)
{
#if HAVE_GSTREAMER
	if (are_pts && !s->pts_baza_ok)
	{
		s->pts_baza = pts;
		s->pts_baza_ok = true;
	}
	GstBuffer *g = gst_buffer_new_allocate(NULL, n, NULL);
	gst_buffer_fill(g, 0, d, n);
	if (are_pts)
	{
		int64_t dif = diferentaPts(pts, s->pts_baza);
		if (dif >= 0)
			GST_BUFFER_PTS(g) = (GstClockTime)dif * 100000u / 9u;    /* 90 kHz -> ns */
	}
	GstFlowReturn r;
	g_signal_emit_by_name(s->appsrc, "push-buffer", g, &r);
	gst_buffer_unref(g);
#else
	(void)s;
	(void)d;
	(void)n;
	(void)are_pts;
	(void)pts;
#endif
}

/* debitul din antetul cadrelor MPEG (firul cititor, cel mult o data la 2 s dupa ce s-a gasit) */
void eHdsEgalizatorMotor::notaDebit(Sesiune *s, const std::vector<uint8_t> &es)
{
	if (s->sursa.fel != eHdsEgalizator::felMpeg || es.empty())
		return;
	uint64_t acum = acumMs();
	if (s->debit_antet.load() && acum - s->ultim_debit_ms < 2000)
		return;
	int k = debitMpeg(es.data(), es.size());
	if (k > 0)
	{
		s->debit_antet = k;
		s->ultim_debit_ms = acum;
	}
}

void eHdsEgalizatorMotor::firCititor(Sesiune *s)
{
	numeFir("hds-egal-cit");
	std::vector<uint8_t> buf(32 * 1024), es, pes;
	PesLaEs &p = s->pes;
	uint64_t ns0 = procesorFirNs();
	if (!s->sursa.fisier.empty())
	{
		FILE *f = fopen(s->sursa.fisier.c_str(), "rb");
		bool ts = false;
		TsLaPes t(s->sursa.pid);
		if (f)
		{
			size_t n = fread(buf.data(), 1, 376, f);
			ts = n == 376 && buf[0] == 0x47 && buf[188] == 0x47;
			fseek(f, 0, SEEK_SET);
		}
		while (f && !s->gata)
		{
			size_t n = fread(buf.data(), 1, ts ? 188 * 170 : buf.size(), f);
			if (n == 0)
				break;
			es.clear();
			if (ts)
			{
				pes.clear();
				t.adauga(buf.data(), n - n % 188, pes);
				p.adauga(pes.data(), pes.size(), es);
			}
			else
				es.assign(buf.begin(), buf.begin() + n);
			s->octeti_es += es.size();
			if (!es.empty())
				s->ultima_data_ms = acumMs();
			notaDebit(s, es);
			impinge(s, es, true);
			uint64_t ns1 = procesorFirNs();
			s->ns_cit += ns1 - ns0;
			ns0 = ns1;
		}
		if (f)
			fclose(f);
#if HAVE_GSTREAMER
		if (!s->gata && s->appsrc)
		{
			GstFlowReturn r;
			g_signal_emit_by_name(s->appsrc, "end-of-stream", &r);
		}
#endif
		return;
	}
	if (!s->inceput.empty())
	{
		impinge(s, s->inceput, false);
		s->inceput.clear();
	}
	std::vector<std::pair<size_t, uint64_t> > pts;
	while (!s->gata)
	{
		struct pollfd pfd;
		pfd.fd = s->fd;
		pfd.events = POLLIN;
		pfd.revents = 0;
		int r = poll(&pfd, 1, 100);
		if (r > 0 && (pfd.revents & POLLIN))
		{
			ssize_t n = ::read(s->fd, buf.data(), buf.size());
			if (n > 0)
			{
				es.clear();
				pts.clear();
				p.adauga(buf.data(), (size_t)n, es, s->sursa.tv ? &pts : 0);
				if (!es.empty())
				{
					s->octeti_es += es.size();
					s->ultima_data_ms = acumMs();
					notaDebit(s, es);
					if (s->sursa.tv)
						impingeTv(s, es, pts);
					else
						impinge(s, es, false);
				}
			}
			else if (n < 0 && errno != EAGAIN && errno != EINTR && errno != EOVERFLOW)
				usleep(20000);
		}
		else if (r > 0)
			usleep(20000);        /* POLLERR (tampon plin la demux): o pauza scurta, fara bucla pe procesor */
		uint64_t ns1 = procesorFirNs();
		s->ns_cit += ns1 - ns0;
		ns0 = ns1;
	}
}

void eHdsEgalizatorMotor::firIesire(Sesiune *s)
{
	numeFir("hds-egal-ies");
	std::vector<float> f(PERIOADA_ALSA * CANALE);
	std::vector<int16_t> b(PERIOADA_ALSA * CANALE);
	uint64_t ns0 = procesorFirNs();
	int la_rand = 0, dupa = 0;
	double g = 1.0;
	const double pas_jos = 1.0 / (0.020 * RATA);
	while (!s->gata)
	{
		/* TV: fara ceas sau fara PTS perioada e tacere; cu sunetul devreme, tacerea hotarata de sincron (exact), apoi sunetul */
		int tacere = (s->sursa.tv && !s->rampaJos) ? sincronTv(s) : 0;
		if (tacere > 0)
			std::fill(f.begin(), f.begin() + (size_t)tacere * CANALE, 0.0f);
		if (tacere < PERIOADA_ALSA)
			s->potrivire.citeste(f.data() + (size_t)tacere * CANALE, PERIOADA_ALSA - tacere);
		if (s->rampaJos)
		{
			for (int i = 0; i < PERIOADA_ALSA; i++)
			{
				g -= pas_jos;
				if (g < 0.0)
					g = 0.0;
				f[2 * i] *= (float)g;
				f[2 * i + 1] *= (float)g;
			}
			if (g <= 0.0 && ++dupa > 2)
				break;
		}
		s->conv.converteste(f.data(), b.data(), PERIOADA_ALSA * CANALE);
		s->abatere_ppm = (s->potrivire.raport() - 1.0) * 1e6;
		long w = alsa.writei(s->pcm, b.data(), PERIOADA_ALSA);
		/* timpul firului cu tot cu scrierea in placa (asteptarea in writei nu consuma procesor) */
		uint64_t ns1 = procesorFirNs();
		s->ns_ies += ns1 - ns0;
		ns0 = ns1;
		if (w < 0)
		{
			int r = alsa.recover(s->pcm, (int)w, 1);
			if (r < 0)
			{
				if (++la_rand >= CADERI_ALSA)
				{
					s->caderi_alsa = la_rand;
					alsa.drop(s->pcm);
					return;
				}
				usleep(10000);
			}
		}
		else
			la_rand = 0;
	}
	if (s->rampaJos)
		golesteCuLimita(s->pcm);
	else
		alsa.drop(s->pcm);
}

/* TV, firul placii: -> cate cadre de tacere incep perioada (PERIOADA_ALSA = toata perioada: fara ceas, fara PTS, sau
   sunetul e mai devreme decat o perioada); restul perioadei se citeste din tampon, dupa o eventuala aruncare, cu
   raportul sincronului */
int eHdsEgalizatorMotor::sincronTv(Sesiune *s)
{
	uint64_t acum = acumMs();
	uint64_t pts_v = 0, pts_a = 0;
	int unitate = 0;
	bool ok_v = imagineLa(acum, pts_v, unitate);
	if (ok_v)
		s->ultim_ceas_bun = acum;
	else
	{
		uint64_t de_la = s->ultim_ceas_bun ? s->ultim_ceas_bun : s->pornit_ms;
		if (acum - de_la > (uint64_t)TV_FARA_CEAS_MS && s->tv_stare.load() != TV_FARA_CEAS)
			s->tv_stare = TV_FARA_CEAS;
		return PERIOADA_ALSA;
	}
	if (s->potrivire.asteapta())
		return 0;                         /* tamponul se umple: citirea da tacere fara sa ia nimic */
	if (s->tacere_ramasa > 0)
	{
		/* tacerea hotarata se scrie toata, fara alta decizie: imaginea merge cat ea, deci sunetul ajunge exact la timp */
		int t = s->tacere_ramasa < PERIOADA_ALSA ? s->tacere_ramasa : PERIOADA_ALSA;
		s->tacere_ramasa -= t;
		return t;
	}
	if (!s->ptsLa(s->potrivire.citite(), pts_a))
		return PERIOADA_ALSA;
	double intarziere = LATENTA_ALSA_US / 1e6;
	long fr = 0;
	if (alsa.delay && s->pcm && alsa.delay(s->pcm, &fr) == 0 && fr >= 0)
		intarziere = (double)fr / RATA;
	intarziere += LATENTA_PLACA_MS / 1000.0;
	SincronImagine d = SincronImagine::decide(pts_a, intarziere, pts_v, m_potrivire_tv_ms.load() / 1000.0);
	s->eroare_tv_ms = d.eroare_s * 1000.0;
	if (d.fapta == SincronImagine::MERGE)
	{
		s->potrivire.raportExtern(d.raport);
		if (s->tv_stare.load() != TV_POTRIVIT)
		{
			s->tv_stare = TV_POTRIVIT;
			eDebug("[HdsEgalizator] TV: sunetul potrivit cu imaginea (abatere %.0f ms, ceasul imaginii in %s)",
				d.eroare_s * 1000.0, unitate == 1 ? "ms" : "90 kHz");
		}
		return 0;
	}
	if (s->tv_stare.load() == TV_ASTEAPTA && acum - s->pornit_ms > (uint64_t)TV_NEPOTRIVIT_MS)
		s->tv_stare = TV_NEPOTRIVIT;
	if (d.fapta == SincronImagine::ARUNCA)
	{
		s->potrivire.arunca(d.cadre);
		s->aruncari_tv++;
		return 0;
	}
	s->taceri_tv++;
	s->tacere_ramasa = d.cadre;
	int t = s->tacere_ramasa < PERIOADA_ALSA ? s->tacere_ramasa : PERIOADA_ALSA;
	s->tacere_ramasa -= t;
	return t;
}

void eHdsEgalizatorMotor::prelucreaza(Sesiune *s, const float *date, int cadre, long long pts90)
{
	unsigned v;
	{
		std::lock_guard<std::mutex> l(m_lacat);
		v = m_versiune;
		if (v != s->versiune)
		{
			s->lant.seteaza(m_setari);
			s->versiune = v;
		}
	}
	s->tmp.assign(date, date + (size_t)cadre * CANALE);
	s->lant.prelucreaza(s->tmp.data(), cadre);
	/* spectrul se calculeaza numai cat cineva il citeste (ecranul sau pagina web deschise) */
	if (acumMs() - m_cerereSpectru.load() < 3000)
		s->spectru.adauga(s->tmp.data(), cadre);
	s->cadre += cadre;
	s->pregain_db = s->lant.pregainDb();
	s->benzi_active = s->lant.benziActive();
	s->limitari = s->lant.limitari();
	if (s->pcm)
	{
		/* proba din fisier spre placa: fisierul nu are ceas, deci decodarea asteapta placa (tamponul putin peste tinta,
		   ca iesirea sa porneasca; potrivirea ceasurilor e oprita, raportul ramane 1) */
		if (!s->sursa.fisier.empty())
			while (!s->gata && !s->rampaJos && s->potrivire.umplere() > s->potrivire.tinta() + RATA / 50)
				usleep(5000);
		if (s->sursa.tv && pts90 >= 0)
			s->marcheaza(s->potrivire.scrise(), (uint64_t)pts90);
		s->potrivire.scrie(s->tmp.data(), cadre);
	}
	else if (s->wav.deschis())
	{
		s->tmp16.resize((size_t)cadre * CANALE);
		s->conv.converteste(s->tmp.data(), s->tmp16.data(), cadre * CANALE);
		s->wav.scrie(s->tmp16.data(), cadre * CANALE);
	}
}

#if HAVE_GSTREAMER
GstFlowReturn eHdsEgalizatorMotor::laMostra(GstElement *sink, gpointer user)
{
	Sesiune *s = (Sesiune *)user;
	GstSample *m = 0;
	g_signal_emit_by_name(sink, "pull-sample", &m);
	if (!m)
		return GST_FLOW_EOS;
	uint64_t ns0 = procesorFirNs();
	GstBuffer *b = gst_sample_get_buffer(m);
	GstMapInfo h;
	if (b && gst_buffer_map(b, &h, GST_MAP_READ))
	{
		int cadre = (int)(h.size / (sizeof(float) * CANALE));
		long long pts90 = -1;
		if (s->sursa.tv && s->pts_baza_ok && GST_BUFFER_PTS_IS_VALID(b))
			pts90 = (long long)((s->pts_baza + (uint64_t)GST_BUFFER_PTS(b) * 9u / 100000u) & MASCA_PTS);
		if (cadre > 0 && !s->gata)
			s->motor->prelucreaza(s, (const float *)h.data, cadre, pts90);
		gst_buffer_unmap(b, &h);
	}
	gst_sample_unref(m);
	/* timpul firului de decodare: de la mostra de dinainte (decodarea ei) pana la sfarsitul prelucrarii acesteia */
	uint64_t ns1 = procesorFirNs();
	if (s->ultim_ns_dec && ns1 > s->ultim_ns_dec)
		s->ns_dec += ns1 - s->ultim_ns_dec;
	else
		s->ns_dec += ns1 - ns0;
	s->ultim_ns_dec = ns1;
	return GST_FLOW_OK;
}

void eHdsEgalizatorMotor::infoDecodor(Sesiune *s)
{
	if (s->info_decodor || !s->decodor || s->cadre.load() == 0)
		return;
	GstPad *pad = gst_element_get_static_pad(s->decodor, "src");
	if (!pad)
		return;
	GstCaps *c = gst_pad_get_current_caps(pad);
	if (c)
	{
		const GstStructure *st = gst_caps_get_structure(c, 0);
		int rata = 0, canale = 0;
		if (st && gst_structure_get_int(st, "rate", &rata) && gst_structure_get_int(st, "channels", &canale))
		{
			std::lock_guard<std::mutex> l(m_lacat);
			s->esantionare = rata;
			s->canale = canale;
			s->info_decodor = true;
		}
		gst_caps_unref(c);
	}
	gst_object_unref(pad);
}
#endif

/* ------------------------------------------------------------------------ verificarile firului de control */

void eHdsEgalizatorMotor::verifica()
{
	Sesiune *s = m_sesiune;
	if (!s)
		return;
	uint64_t acum = acumMs();
#if HAVE_GSTREAMER
	GstBus *bus = gst_element_get_bus(s->pipe);
	GstMessage *m;
	while (bus && (m = gst_bus_pop_filtered(bus, (GstMessageType)(GST_MESSAGE_ERROR | GST_MESSAGE_EOS))))
	{
		if (GST_MESSAGE_TYPE(m) == GST_MESSAGE_ERROR)
		{
			GError *err = 0;
			gchar *dbg = 0;
			gst_message_parse_error(m, &err, &dbg);
			eDebug("[HdsEgalizator] eroare GStreamer: %s (%s)", err ? err->message : "?", dbg ? dbg : "");
			if (err)
				g_error_free(err);
			g_free(dbg);
			gst_message_unref(m);
			gst_object_unref(bus);
			esec(s->cerut, "eroare-decodare");
			return;
		}
		gst_message_unref(m);
		s->eos = true;
	}
	if (bus)
		gst_object_unref(bus);
	infoDecodor(s);
#endif
	if (s->eos && !s->sursa.fisier.empty())
	{
		inchideSesiunea();
		{
			std::lock_guard<std::mutex> l(m_lacat);
			m_stare = STARE_PROBA_GATA;
			m_motiv = "";
			m_sursa_dorita = Sursa();
		}
		trimite(MESAJ_PROBA_GATA);
		return;
	}
	if (s->caderi_alsa.load() >= CADERI_ALSA)
	{
		esec(s->cerut, "alsa-cazut");
		return;
	}
	if (s->latm_rau.load())
	{
		esec(s->cerut, "latm-nesuportat");
		return;
	}
	if (s->sursa.tv && s->tv_stare.load() == TV_FARA_CEAS)
	{
		esec(s->cerut, "tv-fara-ceas");
		return;
	}
	if (s->sursa.tv && s->tv_stare.load() == TV_NEPOTRIVIT)
	{
		esec(s->cerut, "tv-nepotrivit");
		return;
	}
	uint64_t ultima = s->ultima_data_ms.load();
	Stare st;
	{
		std::lock_guard<std::mutex> l(m_lacat);
		st = m_stare;
	}
	if (ultima == 0)
	{
		if (acum - s->pornit_ms > (uint64_t)PRIMA_DATA_MS)
		{
			esec(s->cerut, "fara-date-la-pornire");
			return;
		}
	}
	else if (acum - ultima > (uint64_t)FARA_DATE_MS)
	{
		if (st != STARE_FARA_DATE)
		{
			seteazaStarea(STARE_FARA_DATE, "");
			trimite(MESAJ_FARA_DATE);
		}
	}
	else if (st != STARE_MERGE && s->cadre.load() > 0)
	{
		seteazaStarea(STARE_MERGE, "");
		trimite(MESAJ_MERGE);
	}
	volum();
	procesor();
}

void eHdsEgalizatorMotor::volum()
{
	if (!m_volumctl || !m_sesiune || !m_sesiune->sursa.fisier.empty())
		return;
	int v = m_volumctl->getVolume();
	bool mut = m_volumctl->isMuted();
	if (v == m_ultim_volum && mut == m_ultim_mut)
		return;
	int mod;
	{
		std::lock_guard<std::mutex> l(m_lacat);
		mod = m_volum_mod;
	}
	bool aici = mod == 1;
	if (mod == 0)
	{
		aici = m_volum_aici;
		if (v < 100)
		{
			/* iesirile placii cu Vol(100) cand volumul enigma2 e sub 100: volumul e pe pista placii, deci se pune aici */
			FILE *f = fopen("/proc/msp/sound0", "r");
			if (!f)
				aici = true;
			else
			{
				char rand[512];
				int iesiri = 0, pline = 0;
				while (fgets(rand, sizeof(rand), f))
				{
					if (strncmp(rand, "DAC0:", 5) && strncmp(rand, "SPDIF0:", 7) && strncmp(rand, "HDMI0:", 6))
						continue;
					const char *p = strstr(rand, " Vol(");
					if (!p)
						continue;
					iesiri++;
					if (atoi(p + 5) >= 100)
						pline++;
				}
				fclose(f);
				if (iesiri)
					aici = pline == iesiri;
			}
		}
		m_volum_aici = aici;
	}
	double factor = 1.0;
	if (aici)
		factor = v <= 0 ? 0.0 : dbLaLiniar(-(double)(63 - v * 63 / 100));
	{
		std::lock_guard<std::mutex> l(m_lacat);
		m_setari.volum = factor;
		m_setari.mut = mut;
		m_versiune++;
	}
	m_ultim_volum = v;
	m_ultim_mut = mut;
}

void eHdsEgalizatorMotor::procesor()
{
	Sesiune *s = m_sesiune;
	uint64_t acum = acumMs();
	uint64_t dt = acum - m_ultim_masura;
	if (dt < 1000)
		return;
	uint64_t fire[3] = { s->ns_cit.load(), s->ns_dec.load(), s->ns_ies.load() };
	double p[3];
	for (int i = 0; i < 3; i++)
	{
		p[i] = m_ultime_fir[i] ? (double)(fire[i] - m_ultime_fir[i]) / (dt * 1e6) * 100.0 : 0.0;
		m_ultime_fir[i] = fire[i];
	}
	/* debitul: din antet la MPEG; altfel octetii fata de sunetul decodat, pe ~10 s (nu depinde de viteza cu care vin
	   datele, deci merge si la proba din fisier) */
	uint64_t octeti = s->octeti_es.load(), cadre = s->cadre.load();
	double k = exp(-(double)dt / 10000.0);
	m_suma_octeti = m_suma_octeti * k + (double)(octeti - m_ultim_octeti);
	m_suma_cadre = m_suma_cadre * k + (double)(cadre - m_ultim_cadre);
	m_ultim_octeti = octeti;
	m_ultim_cadre = cadre;
	m_ultim_masura = acum;
	int antet = s->debit_antet.load();
	int debit = antet > 0 ? antet :
		(m_suma_cadre > RATA / 2 ? (int)(m_suma_octeti * 8.0 * RATA / m_suma_cadre / 1000.0 + 0.5) : 0);
	std::lock_guard<std::mutex> l(m_lacat);
	/* medie pe ~4 s, ca cifra de pe ecran sa nu sara */
	m_procent_cit += (p[0] - m_procent_cit) * 0.3;
	m_procent_dec += (p[1] - m_procent_dec) * 0.3;
	m_procent_ies += (p[2] - m_procent_ies) * 0.3;
	m_procent = m_procent_cit + m_procent_dec + m_procent_ies;
	m_debit = debit;
	m_debit_aprox = antet <= 0;
}

namespace
{
	void puneText(PyObject *d, const char *k, const std::string &v)
	{
		PyObject *o = PyUnicode_FromString(v.c_str());
		PyDict_SetItemString(d, k, o);
		Py_DECREF(o);
	}

	void puneInt(PyObject *d, const char *k, long v)
	{
		PyObject *o = PyLong_FromLong(v);
		PyDict_SetItemString(d, k, o);
		Py_DECREF(o);
	}

	void puneReal(PyObject *d, const char *k, double v)
	{
		PyObject *o = PyFloat_FromDouble(v);
		PyDict_SetItemString(d, k, o);
		Py_DECREF(o);
	}
}

PyObject *eHdsEgalizatorMotor::stare(const std::string &post)
{
	m_cerereSpectru = acumMs();
	PyObject *d = PyDict_New();
	std::lock_guard<std::mutex> l(m_lacat);
	Sesiune *s = m_sesiune;
	puneText(d, "stare", NUME_STARE[m_stare]);
	puneText(d, "motiv", m_motiv);
	/* o proba din fisier nu tine de postul de acum */
	puneText(d, "post", (s && !s->sursa.fisier.empty()) ? std::string("proba") : post);
	puneInt(d, "volum_aici", m_volum_aici ? 1 : 0);
	puneText(d, "placa", m_placa);
	puneText(d, "ceas_tv", m_ceas_tv);
	puneInt(d, "tv", m_tv.load() ? 1 : 0);
	puneInt(d, "potrivire_tv_ms", m_potrivire_tv_ms.load());
	if (s && s->sursa.tv)
	{
		uint64_t p = 0;
		int unitate = 0;
		imagineLa(acumMs(), p, unitate);
		puneInt(d, "sesiune_tv", 1);
		puneReal(d, "sincron_tv_ms", s->eroare_tv_ms.load());
		puneInt(d, "ceas_imagine", unitate);
		puneInt(d, "taceri_tv", (long)s->taceri_tv.load());
		puneInt(d, "aruncari_tv", (long)s->aruncari_tv.load());
	}
	if (s)
	{
		puneText(d, "codec", s->codec);
		puneText(d, "decodor", s->decodor_nume);
		puneInt(d, "pid", s->sursa.pid);
		puneInt(d, "demux", s->sursa.demux);
		puneInt(d, "esantionare", s->esantionare);
		puneInt(d, "canale", s->canale);
		puneInt(d, "debit", m_debit);
		puneInt(d, "debit_aprox", m_debit_aprox ? 1 : 0);
		puneInt(d, "latm_prin_adts", s->reimpacheteaza ? 1 : 0);
		puneReal(d, "procesor", m_procent);
		PyObject *f = PyDict_New();
		puneReal(f, "citire", m_procent_cit);
		puneReal(f, "decodare", m_procent_dec);
		puneReal(f, "iesire", m_procent_ies);
		PyDict_SetItemString(d, "procesor_fire", f);
		Py_DECREF(f);
		puneReal(d, "tampon_ms", s->pcm ? s->potrivire.umplere() * 1000.0 / RATA : 0.0);
		puneInt(d, "goluri", s->potrivire.goluri());
		puneInt(d, "aruncate", s->potrivire.aruncate());
		puneReal(d, "abatere_ppm", s->abatere_ppm.load());
		puneReal(d, "castig_inainte_db", s->pregain_db.load());
		puneInt(d, "benzi_active", s->benzi_active.load());
		puneInt(d, "limitari", (long)s->limitari.load());
		puneText(d, "iesire", s->pcm ? "alsa:" + m_placa : "wav:" + s->sursa.wav);
		puneText(d, "fisier", s->sursa.fisier);
		puneReal(d, "secunde", (acumMs() - s->pornit_ms) / 1000.0);
		puneInt(d, "cadre", (long)s->cadre.load());
		double niv[BENZI];
		s->spectru.citeste(niv, 0);
		PyObject *sp = PyList_New(BENZI);
		for (int i = 0; i < BENZI; i++)
			PyList_SET_ITEM(sp, i, PyFloat_FromDouble(niv[i]));
		PyDict_SetItemString(d, "spectru", sp);
		Py_DECREF(sp);
	}
	return d;
}

/* ======================================================================== fata catre Python si servicedvb */

eHdsEgalizator *eHdsEgalizator::instance = 0;

namespace
{
	/* setarile de pe firul enigma2 si ce s-a hotarat pentru postul de acum */
	struct FataStare
	{
		bool pornit;
		bool pauza;            /* serviciul principal e pe pauza (fara timeshift, decodorul placii oprit pe loc) */
		const void *ceas_probat; /* serviciul pentru care proba ceasului STC e facuta */
		std::string post;      /* da, oprit, pauza, tv, inregistrare, format, fara-gstreamer, fara-decodor-mpeg/aac, ... */
		FataStare(): pornit(false), pauza(false), ceas_probat(0), post("nimic") {}
	};
	FataStare fata;
}

eHdsEgalizator::eHdsEgalizator(): m_motor(new eHdsEgalizatorMotor()), m_proprietar(0)
{
	instance = this;
	m_motor->pompa = new eFixedMessagePump<int>(eApp, 1);
	CONNECT(m_motor->pompa->recv_msg, eHdsEgalizator::mesaj);
	m_motor->setVolumControl(eDVBVolumecontrol::getInstance());
}

eHdsEgalizator::~eHdsEgalizator()
{
	instance = 0;
}

eHdsEgalizator *eHdsEgalizator::getInstance()
{
	if (!instance)
		new eHdsEgalizator();
	return instance;
}

void eHdsEgalizator::setPornit(int pornit)
{
	bool p = pornit != 0;
	if (p == fata.pornit)
		return;
	fata.pornit = p;
	m_motor->uitaEsuata();
	reaplica();
}

void eHdsEgalizator::setBanda(int banda, double db)
{
	if (banda >= 0 && banda < BENZI)
		m_motor->setBanda(banda, db);
}

void eHdsEgalizator::setNoapte(int noapte)
{
	m_motor->setNoapte(noapte != 0);
}

void eHdsEgalizator::setNivel(double db)
{
	m_motor->setNivel(db);
}

void eHdsEgalizator::setVolumAici(int mod)
{
	m_motor->setVolumMod(mod < 0 || mod > 2 ? 0 : mod);
}

void eHdsEgalizator::setPlacaAlsa(const char *nume)
{
	m_motor->setPlaca(nume ? nume : "");
}

void eHdsEgalizator::setTv(int da)
{
	bool d = da != 0;
	if (d == m_motor->tv())
		return;
	m_motor->setTv(d);
	m_motor->uitaEsuata();
	reaplica();
}

void eHdsEgalizator::setPotrivireTv(int ms)
{
	m_motor->setPotrivireTv(ms);
}

void eHdsEgalizator::ceasImagine(long long pts)
{
	m_motor->ceasImagine(pts);
}

void eHdsEgalizator::reaplica()
{
	if (!m_reaplica.empty())
		m_reaplica();
	else if (!fata.pornit && m_motor->activ() && !m_motor->proba())
		m_motor->opreste();
}

PyObject *eHdsEgalizator::stare()
{
	PyObject *d = m_motor->stare(fata.post);
	puneInt(d, "pornit", fata.pornit ? 1 : 0);
	return d;
}

PyObject *eHdsEgalizator::decodoare()
{
	const Decodoare &dec = ::decodoare();
	PyObject *d = PyDict_New();
	puneInt(d, "gstreamer", dec.gst ? 1 : 0);
	const std::string *n[3] = { &dec.mpeg, &dec.adts, &dec.latm };
	const char *k[3] = { "mpeg", "aac_adts", "aac_latm" };
	for (int i = 0; i < 3; i++)
	{
		if (n[i]->empty())
			PyDict_SetItemString(d, k[i], Py_None);
		else
			puneText(d, k[i], *n[i]);
	}
	puneInt(d, "alsa", alsa.incarca() ? 1 : 0);
	puneInt(d, "latm_prin_adts", dec.adts.empty() ? 0 : 1);
	return d;
}

int eHdsEgalizator::pornesteDinFisier(const char *cale, int pid, const char *iesire)
{
	if (!cale || !*cale || !iesire || !*iesire)
		return -1;
	Sursa s;
	s.fisier = cale;
	s.wav = iesire;
	s.pid = pid;
	m_motor->noteazaDorita(s);
	m_motor->porneste(s);
	return 0;
}

void eHdsEgalizator::opresteFisier()
{
	if (m_motor->proba())
	{
		m_motor->noteazaDorita(Sursa());
		m_motor->opreste();
	}
}

bool eHdsEgalizator::preiaSunetul(const void *proprietar, int demux, int pid, int fel, bool radio,
	const sigc::slot<void()> &reaplica)
{
	m_proprietar = proprietar;
	m_reaplica = reaplica;
	std::string motiv;
	if (!fata.pornit)
		motiv = "oprit";
	else if (fata.pauza)
		motiv = "pauza";
	else if (pid < 0)
		motiv = "fara-sunet";
	else if (demux < 0)
		motiv = "inregistrare";
	else if (!radio && !m_motor->tv())
		motiv = "tv";
	else if (!radio && fel != felMpeg)
		motiv = "format";          /* la TV numai MPEG: la AAC (LATM) PTS-ul nu se tine pe cadre */
	else if (fel != felMpeg && fel != felAacAdts && fel != felAacLatm)
		motiv = "format";
	else if (!::decodoare().gst)
		motiv = "fara-gstreamer";
	else if (decodorPentru(fel).empty())
		motiv = fel == felMpeg ? "fara-decodor-mpeg" : "fara-decodor-aac";
	else if (!alsa.incarca())
		motiv = "fara-alsa";
	Sursa s;
	s.demux = demux;
	s.pid = pid;
	s.fel = fel;
	s.tv = !radio;
	if (motiv.empty() && m_motor->esuata(s))
		motiv = "esuat";
	if (motiv == "tv" && demux >= 0 && fata.ceas_probat != proprietar)
	{
		fata.ceas_probat = proprietar;
		m_motor->probeazaCeasul(demux);
	}
	if (!motiv.empty())
	{
		fata.post = motiv;
		if (m_motor->activ() && !m_motor->proba())
		{
			m_motor->noteazaDorita(Sursa());
			m_motor->opreste();
		}
		return false;
	}
	fata.post = "da";
	if (m_motor->mergeCu(s))
		return true;
	if (s.tv)
		m_motor->reseteazaCeasImagine();    /* alt canal: ceasul imaginii se invata din nou */
	m_motor->noteazaDorita(s);
	m_motor->porneste(s);
	return true;
}

void eHdsEgalizator::serviciuOprit(const void *proprietar)
{
	if (proprietar != m_proprietar)
		return;
	m_proprietar = 0;
	m_reaplica = sigc::slot<void()>();
	m_motor->uitaEsuata();
	fata.post = "nimic";
	fata.pauza = false;
	fata.ceas_probat = 0;
	if (m_motor->activ() && !m_motor->proba())
	{
		m_motor->noteazaDorita(Sursa());
		m_motor->opreste();
	}
}

void eHdsEgalizator::pauza(const void *proprietar, bool pauza)
{
	if (proprietar != m_proprietar || pauza == fata.pauza)
		return;
	fata.pauza = pauza;
	if (pauza)
	{
		/* sunetul din procesor se opreste odata cu decodorul placii; la pornire, pista se alege din nou */
		fata.post = "pauza";
		if (m_motor->activ() && !m_motor->proba())
		{
			m_motor->noteazaDorita(Sursa());
			m_motor->opreste();
		}
	}
	else if (!m_reaplica.empty())
		m_reaplica();
}

void eHdsEgalizator::mesaj(const int &cod)
{
	if (cod == MESAJ_INAPOI_PE_PLACA)
	{
		fata.post = "esuat";
		if (!m_reaplica.empty())
			m_reaplica();
	}
	/*emit*/ schimbare(cod);
}
