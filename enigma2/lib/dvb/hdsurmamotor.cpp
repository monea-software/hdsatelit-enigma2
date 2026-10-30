/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsurmamotor.cpp: urma comenzilor de motor (vezi hdsurmamotor.h). Scris de la zero.
 *
 * Firul principal formeaza randul intr-un tampon de pe stiva si il scrie intr-o teava deschisa O_NONBLOCK (un rand e mai
 * scurt decat PIPE_BUF, deci intra intreg sau deloc); cand teava e plina, randul se numara ca pierdut. Firul urmei
 * (pornit la primul rand, desprins) citeste teava, scrie in fisier, face fdatasync si roteste fisierul la ROTIRE_OCTETI,
 * numai la capat de rand. Nimic de aici nu tine un lacat pe care sa-l astepte firul principal.
 *
 * Fara Python.h lantul de apeluri Python ramane gol; HDS_URMA_FARA_ENIGMA (probele de pe PC) scoate numai consola enigma2.
 */

#include <lib/dvb/hdsurmamotor.h>

#include <atomic>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#ifndef HDS_URMA_FARA_ENIGMA
#include <lib/base/eerror.h>
#endif

namespace hdsurma
{

static const char *const DOSAR_IMPLICIT = "/home/root/logs";
static const char *const NUME_FISIER = "hds-motor.log";
static const char *const SUFIX_VECHI = ".1";
enum { LUNGIME_RAND = 2048 };          /* sub PIPE_BUF (4096): scrierea in teava e atomica */
/* "goto_omis": cel mult un rand la 30 s pe tuner la reacordarea dupa pierderea semnalului (un semnal care se prinde si
   se pierde des, de pilda pe ploaie, n-are voie sa impinga din fisier comenzile de motor cautate) si cel mult unul la
   10 minute la celelalte acordari; cele sarite se numara in "omise" la randul urmator */
enum { OMIS_REACORDARE_S = 30, OMIS_PAUZA_S = 600 };
enum { SLOTURI = 8 };

/* ------------------------------------------------------------------ marunte */

static void copiaza(char *dst, size_t n, const char *src)
{
	if (!n)
		return;
	size_t i = 0;
	if (src)
		for (; src[i] && i + 1 < n; ++i)
			dst[i] = src[i];
	dst[i] = 0;
}

static double secunde(clockid_t ceas)
{
	struct timespec t;
	if (clock_gettime(ceas, &t))
		return 0.0;
	return (double)t.tv_sec + (double)t.tv_nsec / 1e9;
}

static void adauga(char *buf, size_t n, size_t &folosit, const char *fmt, ...) __attribute__((format(printf, 4, 5)));
static void adauga(char *buf, size_t n, size_t &folosit, const char *fmt, ...)
{
	if (folosit + 1 >= n)
		return;
	va_list ap;
	va_start(ap, fmt);
	int r = vsnprintf(buf + folosit, n - folosit, fmt, ap);
	va_end(ap);
	if (r < 0)
		return;
	folosit += (size_t)r;
	if (folosit >= n)
		folosit = n - 1;
}

void Acordare::goleste()
{
	motiv[0] = canal[0] = cerere[0] = python[0] = tp[0] = 0;
	orbital = -1;
	rotor_de_la = -1;
	rotor_cmd = -1;
	rotor_cmd_vechi = -1;
	mono_s = 0.0;
	rotire_tensiune = 0;
	rotire_tinta = 0;
	rotire_plan_ms = 0;
	rotire_grade_zecimi = 0;
	rotire_plecare = 0;
	rotire_proba = 0;
}

Eveniment::Eveniment()
	: tip(""), slot(-1), octeti(0), lungime(0), rezultat(0), ret_driver(0), cale(0), acordare(0), crezuta(-1), crezuta_cmd(-1),
	spre(-1), spre_cmd(-1), omise(0), faza(""), incercare(0), fara_semnal_ms(-1), dupa_ms(-1), mers_ms(-1),
	urmatoarea_s(-1), cod(0), tensiune(0), plan_ms(-1), tinut_ms(-1)
{
}

/* ------------------------------------------------------------------ cine a cerut */

static thread_local const char *t_motiv = 0;
static thread_local const char *t_canal = 0;

Motiv::Motiv(const char *motiv, const char *canal)
	: m_motiv_vechi(t_motiv), m_canal_vechi(t_canal)
{
	if (motiv)
		t_motiv = motiv;
	if (canal)
		t_canal = canal;
}

Motiv::~Motiv()
{
	t_motiv = m_motiv_vechi;
	t_canal = m_canal_vechi;
}

/* numai de pe firul principal (SWIG); citita tot de acolo */
static char s_cerere[96];
static double s_cerere_pana = 0.0;

void anuntaCerere(const char *text, int ttl_ms)
{
	copiaza(s_cerere, sizeof(s_cerere), text);
	if (ttl_ms < 0)
		ttl_ms = 0;
	if (ttl_ms > 600000)
		ttl_ms = 600000;
	s_cerere_pana = secunde(CLOCK_MONOTONIC) + ttl_ms / 1000.0;
}

#if defined(Py_PYTHON_H)
/* lantul de apeluri Python al firului curent: "fisier:linie functie < ..." (fisierul fara dosar si fara .py). Numai cu
   interpretorul tinut de firul curent si fara o eroare Python in asteptare (nu o atingem pe a altcuiva). */
static void lantPython(char *buf, size_t n)
{
	if (!n)
		return;
	buf[0] = 0;
	if (!Py_IsInitialized() || !PyGILState_Check() || PyErr_Occurred())
		return;
	PyFrameObject *cadru = PyThreadState_GetFrame(PyThreadState_Get());
	size_t folosit = 0;
	for (int nivel = 0; cadru && nivel < 5; ++nivel)
	{
		PyCodeObject *cod = PyFrame_GetCode(cadru);
		int linie = PyFrame_GetLineNumber(cadru);
		const char *fisier = cod ? PyUnicode_AsUTF8(cod->co_filename) : 0;
		const char *functie = cod ? PyUnicode_AsUTF8(cod->co_name) : 0;
		if (PyErr_Occurred())
			PyErr_Clear();
		const char *scurt = fisier ? strrchr(fisier, '/') : 0;
		scurt = scurt ? scurt + 1 : (fisier ? fisier : "?");
		size_t lungime = strlen(scurt);
		if (lungime > 3 && !strcmp(scurt + lungime - 3, ".py"))
			lungime -= 3;
		adauga(buf, n, folosit, "%s%.*s:%d %s", nivel ? " < " : "", (int)lungime, scurt, linie, functie ? functie : "?");
		Py_XDECREF(cod);
		PyFrameObject *inapoi = PyFrame_GetBack(cadru);
		Py_DECREF(cadru);
		cadru = inapoi;
	}
	Py_XDECREF(cadru);
}
#else
static void lantPython(char *buf, size_t n)
{
	if (n)
		buf[0] = 0;
}
#endif

void completeazaCine(Acordare &a, const char *motiv_implicit)
{
	copiaza(a.motiv, sizeof(a.motiv), t_motiv ? t_motiv : motiv_implicit);
	if (t_canal)
		copiaza(a.canal, sizeof(a.canal), t_canal);
	double acum = secunde(CLOCK_MONOTONIC);
	copiaza(a.cerere, sizeof(a.cerere), (s_cerere[0] && acum <= s_cerere_pana) ? s_cerere : "");
	lantPython(a.python, sizeof(a.python));
	a.mono_s = acum;
}

void textTp(char *buf, size_t n, unsigned int frecventa_khz, int polarizare, unsigned int sr)
{
	static const char *const POL[] = { "H", "V", "L", "R" };
	const char *pol = (polarizare >= 0 && polarizare < 4) ? POL[polarizare] : "?";
	size_t folosit = 0;
	if (n)
		buf[0] = 0;
	adauga(buf, n, folosit, "%u %s %u", frecventa_khz / 1000, pol, sr / 1000);
}

/* ------------------------------------------------------------------ comenzile */

int esteMotor(const unsigned char *d, int len)
{
	if (!d || len < 3)
		return 0;
	return (d[0] & 0xFC) == 0xE0 && d[1] >= 0x30 && d[1] <= 0x32 && d[2] >= 0x60 && d[2] <= 0x6F;
}

const char *numeComanda(const unsigned char *d, int len)
{
	if (!esteMotor(d, len))
		return "nu_e_motor";
	switch (d[2])
	{
	case 0x60: return "oprire";
	case 0x63: return "limite_oprite";
	case 0x66: return "limita_est";
	case 0x67: return "limita_vest";
	case 0x68: return "mers_est";
	case 0x69: return "mers_vest";
	case 0x6A: return (len >= 4 && d[3] == 0) ? "limite_pornite" : "memoreaza_pozitia";
	case 0x6B: return "mergi_la_pozitia";
	case 0x6E: return "mergi_la_unghi";
	case 0x6F: return "recalculeaza_pozitiile";
	default: return "alta_comanda";
	}
}

int unghiZecimi(const unsigned char *d, int len, int *ok)
{
	/* zecimile se trimit codate pe 4 biti (ca tabelul gotoXTable din sec.cpp) */
	static const unsigned char ZECIMI[10] = { 0x0, 0x2, 0x3, 0x5, 0x6, 0x8, 0xA, 0xB, 0xD, 0xE };
	if (ok)
		*ok = 0;
	if (!esteMotor(d, len) || d[2] != 0x6E || len < 5)
		return 0;
	unsigned int v = ((unsigned int)d[3] << 8) | d[4];
	unsigned int sens = v >> 12;
	if (sens != 0xE && sens != 0xD)
		return 0;
	int zecime = 0;
	for (int i = 0; i < 10; ++i)
		if (ZECIMI[i] == (v & 0xF))
			zecime = i;
	int valoare = (int)((v >> 4) & 0xFF) * 10 + zecime;
	if (ok)
		*ok = 1;
	return sens == 0xE ? valoare : -valoare;
}

/* ------------------------------------------------------------------ randul */

class Json
{
public:
	Json(char *buf, size_t n) : m_buf(buf), m_n(n), m_folosit(0), m_ok(n > 2), m_primul(true)
	{
		brut("{");
	}
	void text(const char *cheie, const char *valoare)
	{
		if (!valoare)
			return;
		cheia(cheie);
		brut("\"");
		for (const unsigned char *p = (const unsigned char *)valoare; *p && m_ok; ++p)
		{
			char mic[8];
			if (*p == '"' || *p == '\\')
			{
				mic[0] = '\\';
				mic[1] = (char)*p;
				mic[2] = 0;
			}
			else if (*p < 0x20)
				snprintf(mic, sizeof(mic), "\\u%04x", *p);
			else
			{
				mic[0] = (char)*p;
				mic[1] = 0;
			}
			brut(mic);
		}
		brut("\"");
	}
	void numar(const char *cheie, long valoare)
	{
		char mic[24];
		snprintf(mic, sizeof(mic), "%ld", valoare);
		cheia(cheie);
		brut(mic);
	}
	void zecimal(const char *cheie, double valoare, int zecimale)
	{
		char mic[40];
		snprintf(mic, sizeof(mic), "%.*f", zecimale, valoare);
		cheia(cheie);
		brut(mic);
	}
	size_t gata()
	{
		brut("}");
		return m_ok ? m_folosit : 0;
	}
private:
	void cheia(const char *cheie)
	{
		if (!m_primul)
			brut(",");
		m_primul = false;
		brut("\"");
		brut(cheie);
		brut("\":");
	}
	void brut(const char *s)
	{
		size_t l = strlen(s);
		if (!m_ok || m_folosit + l + 1 > m_n)
		{
			m_ok = false;
			return;
		}
		memcpy(m_buf + m_folosit, s, l);
		m_folosit += l;
		m_buf[m_folosit] = 0;
	}
	char *m_buf;
	size_t m_n, m_folosit;
	bool m_ok, m_primul;
};

size_t formeaza(char *buf, size_t n, const Eveniment &e, const struct timespec &real, const struct timespec &mono,
	const char *pornire, unsigned long pierdute)
{
	char ora[40];
	struct tm local;
	time_t s = real.tv_sec;
	if (localtime_r(&s, &local) && strftime(ora, sizeof(ora), "%Y-%m-%d %H:%M:%S", &local))
	{
		size_t l = strlen(ora);
		snprintf(ora + l, sizeof(ora) - l, ".%03ld", (long)(real.tv_nsec / 1000000));
	}
	else
		copiaza(ora, sizeof(ora), "?");

	Json j(buf, n);
	j.text("ora", ora);
	j.zecimal("mono", (double)mono.tv_sec + (double)mono.tv_nsec / 1e9, 3);
	if (pornire && *pornire)
		j.text("pornire", pornire);
	j.text("eveniment", e.tip);
	j.numar("tuner", e.slot);
	if (e.octeti && e.lungime > 0)
	{
		char hex[3 * 8 + 1];
		size_t folosit = 0;
		hex[0] = 0;
		for (int i = 0; i < e.lungime && i < 8; ++i)
			adauga(hex, sizeof(hex), folosit, "%s%02X", i ? " " : "", e.octeti[i]);
		j.text("hex", hex);
		j.text("comanda", numeComanda(e.octeti, e.lungime));
		if (esteMotor(e.octeti, e.lungime))
		{
			unsigned char c = e.octeti[2];
			int ok = 0;
			int zecimi = unghiZecimi(e.octeti, e.lungime, &ok);
			if (ok)
				j.zecimal("unghi", zecimi / 10.0, 1);
			if ((c == 0x6A || c == 0x6B) && e.lungime >= 4)
				j.numar("pozitia", e.octeti[3]);
			if ((c == 0x68 || c == 0x69) && e.lungime >= 4)
			{
				unsigned char p = e.octeti[3];
				if (!p)
					j.numar("fara_oprire", 1);
				else if (p < 0x80)
					j.numar("secunde", p);
				else
					j.numar("pasi", 0x100 - p);
			}
		}
		j.numar("rezultat", e.rezultat);
		if (e.ret_driver > 0)
			j.numar("ret", e.ret_driver);
	}
	if (e.cale)
		j.text("cale", e.cale);
	if (e.acordare)
	{
		const Acordare &a = *e.acordare;
		j.text("motiv", a.motiv);
		if (a.cerere[0])
			j.text("cerere", a.cerere);
		if (a.python[0])
			j.text("python", a.python);
		if (a.canal[0])
			j.text("canal", a.canal);
		if (a.tp[0])
			j.text("tp", a.tp);
		if (a.orbital >= 0)
			j.numar("sat", a.orbital);
		if (a.rotor_cmd >= 0)
			j.numar("cmd_calculata", a.rotor_cmd);
		/* tensiunea de rotire, numai in randul comenzii de motor din acordare (6E, 6B) */
		if (a.rotire_tensiune > 0 && e.octeti && esteMotor(e.octeti, e.lungime) && (e.octeti[2] == 0x6E || e.octeti[2] == 0x6B)
			&& e.cale && !strcmp(e.cale, "acordare"))
		{
			j.numar("tensiune_rotire", a.rotire_tensiune);
			j.numar("tensiune_tinta", a.rotire_tinta);
			j.numar("rotire_plan_ms", a.rotire_plan_ms);
			j.zecimal("rotire_grade", a.rotire_grade_zecimi / 10.0, 1);
			j.text("plecare", a.rotire_plecare == 0 ? "stiuta" : (a.rotire_plecare == 1 ? "zona" : "necunoscuta"));
			/* proba de semnal dinaintea comenzii (lib/dvb/hdsrotire.h): facuta (deci fara semnal, altfel comanda nu
			   pleca), sarita pentru un geaman pe alt satelit sau fara lista transponderelor */
			if (a.rotire_proba >= 1 && a.rotire_proba <= 3)
				j.text("proba", a.rotire_proba == 1 ? "fara_semnal" : (a.rotire_proba == 2 ? "geaman" : "fara_lista"));
		}
	}
	j.numar("crezuta", e.crezuta);
	if (e.crezuta_cmd >= 0)
		j.numar("crezuta_cmd", e.crezuta_cmd);
	if (!strcmp(e.tip, "pozitie_crezuta"))
	{
		j.numar("spre", e.spre);
		if (e.spre_cmd >= 0)
			j.numar("spre_cmd", e.spre_cmd);
	}
	if (!strcmp(e.tip, "readucere"))
	{
		j.text("faza", e.faza);
		j.numar("incercare", e.incercare);
		if (e.fara_semnal_ms >= 0)
			j.numar("fara_semnal_ms", e.fara_semnal_ms);
		if (e.dupa_ms >= 0)
			j.numar("dupa_ms", e.dupa_ms);
		if (e.mers_ms >= 0)
			j.numar("mers_ms", e.mers_ms);
		if (e.urmatoarea_s >= 0)
			j.numar("urmatoarea_s", e.urmatoarea_s);
		if (e.cod)
			j.numar("cod", e.cod);
	}
	if (!strcmp(e.tip, "tensiune_rotire"))
	{
		j.text("faza", e.faza);
		j.numar("tensiune", e.tensiune);
		j.numar("plan_ms", e.plan_ms);
		j.numar("tinut_ms", e.tinut_ms);
	}
	if (!strcmp(e.tip, "proba_semnal"))
	{
		j.text("faza", e.faza);
		j.numar("fereastra_ms", e.plan_ms);
		j.numar("durata_ms", e.tinut_ms);
	}
	if (e.omise)
		j.numar("omise", (long)e.omise);
	if (pierdute)
		j.numar("pierdute", (long)pierdute);
	return j.gata();
}

/* ------------------------------------------------------------------ scrierea */

static pthread_once_t s_o_data = PTHREAD_ONCE_INIT;
static int s_teava[2] = { -1, -1 };
static std::atomic<unsigned long> s_pierdute(0);
static std::atomic<unsigned long> s_trimise(0);   /* octeti pusi in teava */
static std::atomic<unsigned long> s_mutati(0);    /* octeti mutati de fir din teava (in fisier sau aruncati) */
static char s_pornire[12];

const char *dosar()
{
	const char *d = getenv("HDS_URMA_MOTOR_DIR");
	return (d && *d) ? d : DOSAR_IMPLICIT;
}

static void cai(char *fisier, size_t n1, char *vechi, size_t n2)
{
	size_t f = 0, v = 0;
	if (n1)
		fisier[0] = 0;
	if (n2)
		vechi[0] = 0;
	adauga(fisier, n1, f, "%s/%s", dosar(), NUME_FISIER);
	adauga(vechi, n2, v, "%s/%s%s", dosar(), NUME_FISIER, SUFIX_VECHI);
}

static int deschide(size_t &marime)
{
	char fisier[512], vechi[520];
	cai(fisier, sizeof(fisier), vechi, sizeof(vechi));
	if (mkdir(dosar(), 0755) && errno != EEXIST)
		return -1;
	int fd = ::open(fisier, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0644);
	if (fd < 0)
		return -1;
	struct stat st;
	marime = fstat(fd, &st) ? 0 : (size_t)st.st_size;
	if (marime >= ROTIRE_OCTETI)
	{
		::close(fd);
		::rename(fisier, vechi);
		fd = ::open(fisier, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0644);
		marime = 0;
	}
	return fd;
}

static void scrieTot(int fd, const char *p, size_t n)
{
	while (n)
	{
		ssize_t r = ::write(fd, p, n);
		if (r < 0)
		{
			if (errno == EINTR)
				continue;
			return;
		}
		p += r;
		n -= (size_t)r;
	}
}

static void *firUrma(void *)
{
	char buf[8192];
	int fd = -1;
	size_t marime = 0;
	for (;;)
	{
		ssize_t r = ::read(s_teava[0], buf, sizeof(buf));
		if (r < 0)
		{
			if (errno == EINTR)
				continue;
			break;
		}
		if (r == 0)
			break;
		if (fd < 0)
			fd = deschide(marime);
		if (fd >= 0)
		{
			scrieTot(fd, buf, (size_t)r);
			marime += (size_t)r;
			fdatasync(fd);
			if (marime >= ROTIRE_OCTETI && buf[r - 1] == '\n')
			{
				char fisier[512], vechi[520];
				cai(fisier, sizeof(fisier), vechi, sizeof(vechi));
				::close(fd);
				fd = -1;
				::rename(fisier, vechi);
				marime = 0;
			}
		}
		s_mutati.fetch_add((unsigned long)r);
	}
	if (fd >= 0)
		::close(fd);
	return 0;
}

static void citestePornirea()
{
	int fd = ::open("/proc/sys/kernel/random/boot_id", O_RDONLY | O_CLOEXEC);
	s_pornire[0] = 0;
	if (fd < 0)
		return;
	char tmp[40];
	ssize_t r = ::read(fd, tmp, sizeof(tmp) - 1);
	::close(fd);
	if (r <= 0)
		return;
	tmp[r] = 0;
	size_t i = 0;
	for (; i < 8 && i + 1 < sizeof(s_pornire) && tmp[i] && tmp[i] != '\n'; ++i)
		s_pornire[i] = tmp[i];
	s_pornire[i] = 0;
}

static void pornesteUrma()
{
	citestePornirea();
	int t[2];
	if (pipe2(t, O_CLOEXEC))
		return;
	int fl = fcntl(t[1], F_GETFL);
	if (fl < 0 || fcntl(t[1], F_SETFL, fl | O_NONBLOCK) < 0)
	{
		::close(t[0]);
		::close(t[1]);
		return;
	}
#ifdef F_SETPIPE_SZ
	fcntl(t[1], F_SETPIPE_SZ, 64 * 1024);
#endif
	s_teava[0] = t[0];
	pthread_attr_t atr;
	pthread_t fir;
	pthread_attr_init(&atr);
	pthread_attr_setdetachstate(&atr, PTHREAD_CREATE_DETACHED);
	pthread_attr_setstacksize(&atr, 64 * 1024);
	if (pthread_create(&fir, &atr, firUrma, 0))
	{
		::close(t[0]);
		::close(t[1]);
		s_teava[0] = -1;
	}
	else
		s_teava[1] = t[1];
	pthread_attr_destroy(&atr);
}

void noteaza(const Eveniment &e)
{
	pthread_once(&s_o_data, pornesteUrma);
	struct timespec real, mono;
	clock_gettime(CLOCK_REALTIME, &real);
	clock_gettime(CLOCK_MONOTONIC, &mono);
	unsigned long pierdute = s_pierdute.exchange(0);
	char rand[LUNGIME_RAND];
	size_t l = formeaza(rand, sizeof(rand) - 1, e, real, mono, s_pornire, pierdute);
	if (!l)
	{
		/* nu incape (n-ar trebui): randul fara lantul Python si fara cereri */
		Eveniment scurt = e;
		scurt.acordare = 0;
		l = formeaza(rand, sizeof(rand) - 1, scurt, real, mono, s_pornire, pierdute);
	}
	if (!l)
	{
		s_pierdute.fetch_add(pierdute + 1);
		return;
	}
#ifndef HDS_URMA_FARA_ENIGMA
	eDebug("[HdsUrmaMotor] %s", rand);
#endif
	rand[l++] = '\n';
	ssize_t r = s_teava[1] >= 0 ? ::write(s_teava[1], rand, l) : -1;
	if (r == (ssize_t)l)
		s_trimise.fetch_add((unsigned long)l);
	else
		s_pierdute.fetch_add(pierdute + 1);
}

int asteaptaScrierea(int ms)
{
	for (int i = 0; i <= ms; i += 5)
	{
		if (s_mutati.load() >= s_trimise.load())
			return 1;
		usleep(5000);
	}
	return s_mutati.load() >= s_trimise.load();
}

/* ------------------------------------------------------------------ evenimentele */

void comandaTrimisa(int slot, const unsigned char *d, int len, int rezultat, const char *cale, const Acordare &a,
	long crezuta, long crezuta_cmd, int ret_driver)
{
	Eveniment e;
	e.tip = "comanda";
	e.slot = slot;
	e.octeti = d;
	e.lungime = len;
	e.rezultat = rezultat;
	e.cale = cale;
	e.acordare = &a;
	e.crezuta = crezuta;
	e.crezuta_cmd = crezuta_cmd;
	e.ret_driver = ret_driver;
	noteaza(e);
}

static double s_omis_ultim[SLOTURI];
static unsigned long s_omis_sarite[SLOTURI];
static int s_pauza_reacordare = OMIS_REACORDARE_S;
static int s_pauza_altele = OMIS_PAUZA_S;

void pauzeOmis(int reacordare_s, int altele_s)
{
	s_pauza_reacordare = reacordare_s < 0 ? 0 : reacordare_s;
	s_pauza_altele = altele_s < 0 ? 0 : altele_s;
}

void gotoOmis(int slot, const Acordare &a, long ultima_cmd)
{
	bool reacordare = !strncmp(a.motiv, "reacordare", 10);
	unsigned long omise = 0;
	if (slot >= 0 && slot < SLOTURI)
	{
		double acum = secunde(CLOCK_MONOTONIC);
		double pauza = reacordare ? s_pauza_reacordare : s_pauza_altele;
		if (s_omis_ultim[slot] > 0.0 && acum - s_omis_ultim[slot] < pauza)
		{
			++s_omis_sarite[slot];
			return;
		}
		s_omis_ultim[slot] = acum;
		omise = s_omis_sarite[slot];
		s_omis_sarite[slot] = 0;
	}
	Eveniment e;
	e.tip = "goto_omis";
	e.slot = slot;
	e.cale = "acordare";
	e.acordare = &a;
	e.crezuta = a.rotor_de_la;
	e.crezuta_cmd = ultima_cmd;
	e.omise = omise;
	noteaza(e);
}

void pozitieCrezuta(int slot, long de_la, long de_la_cmd, int spre, int spre_cmd)
{
	Acordare a;
	a.goleste();
	completeazaCine(a, "pozitia pusa din Python");
	Eveniment e;
	e.tip = "pozitie_crezuta";
	e.slot = slot;
	e.acordare = &a;
	e.crezuta = de_la;
	e.crezuta_cmd = de_la_cmd;
	e.spre = spre;
	e.spre_cmd = spre_cmd;
	noteaza(e);
}

void readucere(int slot, const char *faza, int incercare, int orbital, long crezuta, long fara_semnal_ms,
	long dupa_ms, long mers_ms, long urmatoarea_s, long cod)
{
	Acordare a;
	a.goleste();
	completeazaCine(a, "readucere dupa pierderea semnalului");
	a.orbital = orbital;
	Eveniment e;
	e.tip = "readucere";
	e.slot = slot;
	e.acordare = &a;
	e.crezuta = crezuta;
	e.faza = faza ? faza : "";
	e.incercare = incercare;
	e.fara_semnal_ms = fara_semnal_ms;
	e.dupa_ms = dupa_ms;
	e.mers_ms = mers_ms;
	e.urmatoarea_s = urmatoarea_s;
	e.cod = cod;
	noteaza(e);
}

void tensiuneRotire(int slot, const char *faza, long plan_ms, long tinut_ms, int orbital, long crezuta,
	const Acordare *acordare)
{
	Acordare a;
	if (acordare)
		a = *acordare;
	else
	{
		a.goleste();
		completeazaCine(a, "mersul motorului oprit");
	}
	if (orbital >= 0)
		a.orbital = orbital;
	Eveniment e;
	e.tip = "tensiune_rotire";
	e.slot = slot;
	e.acordare = &a;
	e.crezuta = crezuta;
	e.faza = faza ? faza : "";
	e.tensiune = 18;
	e.plan_ms = plan_ms;
	e.tinut_ms = tinut_ms;
	noteaza(e);
}

void probaSemnal(int slot, const char *faza, long fereastra_ms, long durata_ms, int orbital, long crezuta,
	const Acordare *acordare)
{
	Acordare a;
	if (acordare)
		a = *acordare;
	else
	{
		a.goleste();
		completeazaCine(a, "acordare");
	}
	if (orbital >= 0)
		a.orbital = orbital;
	Eveniment e;
	e.tip = "proba_semnal";
	e.slot = slot;
	e.acordare = &a;
	e.crezuta = crezuta;
	e.faza = faza ? faza : "";
	e.plan_ms = fereastra_ms;
	e.tinut_ms = durata_ms;
	noteaza(e);
}

}
