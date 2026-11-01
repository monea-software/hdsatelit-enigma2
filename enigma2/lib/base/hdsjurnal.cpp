/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hdsjurnal.cpp: jurnalele componentelor (vezi hdsjurnal.h). Scris de la zero.
 *
 * In teava, un rand e "componenta" + DESPARTITOR + randul + capat de linie (sub PIPE_BUF: intra intreg sau deloc).
 * Firul jurnalelor citeste teava, desparte randurile, le scrie in fisierul componentei (tinut deschis, cel mult
 * FISIERE_DESCHISE), face fdatasync o data pe fiecare citire si roteste fisierul la ROTIRE_OCTETI. Nimic de aici nu tine
 * un lacat pe care sa-l astepte firul care cheama. Nu depinde de enigma2: probele de pe PC compileaza fisierul singur.
 */

#include <lib/base/hdsjurnal.h>

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

namespace hdsjurnal
{

const char INFO[] = "INFO";
const char AVERT[] = "AVERT";
const char EROARE[] = "EROARE";

static const char *const DOSAR_IMPLICIT = "/home/root/logs";
static const char DESPARTITOR = 0x1f;
enum { FISIERE_DESCHISE = 32, LUNGIME_COMPONENTA = 32, LUNGIME_MODUL = 24 };

/* ------------------------------------------------------------------ marunte */

static double secunde(clockid_t ceas)
{
	struct timespec t;
	if (clock_gettime(ceas, &t))
		return 0.0;
	return (double)t.tv_sec + (double)t.tv_nsec / 1e9;
}

long long monotonMs()
{
	struct timespec t;
	if (clock_gettime(CLOCK_MONOTONIC, &t))
		return 0;
	return (long long)t.tv_sec * 1000LL + t.tv_nsec / 1000000L;
}

static int cifra(char c) { return c >= '0' && c <= '9'; }
static int hexa(char c) { return cifra(c) || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'); }
static int litera(char c) { return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || cifra(c) || c == '_'; }
static char mica(char c) { return (c >= 'A' && c <= 'Z') ? (char)(c - 'A' + 'a') : c; }

int numeBun(const char *c)
{
	if (!c || !*c)
		return 0;
	size_t i = 0;
	for (; c[i]; ++i)
	{
		if (i >= LUNGIME_COMPONENTA)
			return 0;
		if (!((c[i] >= 'a' && c[i] <= 'z') || cifra(c[i]) || c[i] == '-'))
			return 0;
	}
	return 1;
}

/* ------------------------------------------------------------------ curatarea */

/* IPv4 la s: 4 grupuri de 1..3 cifre despartite de '.', fara cifra sau '.' inainte si dupa; lungimea sau 0 */
static size_t ipv4(const char *s, const char *inceput, size_t poz[4])
{
	if (s > inceput && (cifra(s[-1]) || s[-1] == '.'))
		return 0;
	size_t i = 0;
	for (int g = 0; g < 4; ++g)
	{
		size_t n = 0;
		poz[g] = i;
		while (cifra(s[i]) && n < 4)
		{
			++i;
			++n;
		}
		if (n == 0 || n > 3)
			return 0;
		if (g < 3)
		{
			if (s[i] != '.')
				return 0;
			++i;
		}
	}
	if (cifra(s[i]) || (s[i] == '.' && cifra(s[i + 1])))
		return 0;
	return i;
}

/* MAC la s: 6 grupuri de 2 semne hexa despartite de ':' sau '-' (acelasi), fara semn hexa inainte si dupa */
static size_t mac(const char *s, const char *inceput)
{
	if (s > inceput && (hexa(s[-1]) || s[-1] == ':'))
		return 0;
	char desp = 0;
	size_t i = 0;
	for (int g = 0; g < 6; ++g)
	{
		if (!hexa(s[i]) || !hexa(s[i + 1]))
			return 0;
		i += 2;
		if (g < 5)
		{
			if (s[i] != ':' && s[i] != '-')
				return 0;
			if (desp && s[i] != desp)
				return 0;
			desp = s[i];
			++i;
		}
	}
	if (hexa(s[i]) || s[i] == ':')
		return 0;
	return i;
}

static const char *const CHEI[] = {
	"password", "passwd", "parola", "cheie", "jeton", "token", "secret", "essid", "ssid", "pass", "psk", "key", 0
};

/* cheie secreta la s ("token=", "parola: ", ghilimele "key": ghilimele): lungimea pana la valoare, 0 daca nu e */
static size_t cheie(const char *s, const char *inceput)
{
	if (s > inceput && litera(s[-1]))
		return 0;
	for (int k = 0; CHEI[k]; ++k)
	{
		size_t n = strlen(CHEI[k]), i = 0;
		while (i < n && mica(s[i]) == CHEI[k][i])
			++i;
		if (i < n || litera(s[i]))
			continue;
		if (s[i] == '"' || s[i] == '\'')
			++i;
		while (s[i] == ' ')
			++i;
		if (s[i] != '=' && s[i] != ':')
			continue;
		++i;
		while (s[i] == ' ')
			++i;
		if (s[i] == '"' || s[i] == '\'')
			++i;
		return i;
	}
	return 0;
}

static int capatValoare(char c)
{
	return !c || c == ' ' || c == '&' || c == ',' || c == ';' || c == '"' || c == '\'' || c == ')' || c == '}' ||
		c == ']';
}

size_t curata(char *m)
{
	if (!m)
		return 0;
	for (char *p = m; *p; ++p)
		if ((unsigned char)*p < 0x20 || *p == 0x7f)
			*p = ' ';
	/* scrierea (w) nu trece niciodata de citire (r): fiecare inlocuire e cel mult cat textul inlocuit */
	size_t r = 0, w = 0;
	while (m[r])
	{
		size_t poz[4];
		size_t n = ipv4(m + r, m, poz);
		if (n)
		{
			memmove(m + w, m + r, poz[2]);
			w += poz[2];
			m[w++] = 'x';
			m[w++] = '.';
			m[w++] = 'x';
			r += n;
			continue;
		}
		n = mac(m + r, m);
		if (n)
		{
			char desp = m[r + 2];
			memmove(m + w, m + r, 9);
			w += 9;
			for (int g = 0; g < 3; ++g)
			{
				m[w++] = 'x';
				m[w++] = 'x';
				if (g < 2)
					m[w++] = desp;
			}
			r += n;
			continue;
		}
		n = cheie(m + r, m);
		if (n)
		{
			memmove(m + w, m + r, n);
			w += n;
			r += n;
			size_t v = 0;
			while (!capatValoare(m[r + v]))
				++v;
			for (size_t i = 0; i < v && i < 3; ++i)
				m[w++] = '*';
			r += v;
			continue;
		}
		m[w++] = m[r++];
	}
	m[w] = 0;
	return w;
}

/* ------------------------------------------------------------------ randul */

size_t formeaza(char *buf, size_t n, const struct timespec &utc, const char *nivel, const char *modul, const char *mesaj)
{
	struct tm t;
	time_t sec = utc.tv_sec;
	if (!n || !gmtime_r(&sec, &t))
		return 0;
	int r = snprintf(buf, n, "%04d-%02d-%02dT%02d:%02d:%02dZ [%s] [%s] %s", t.tm_year + 1900, t.tm_mon + 1, t.tm_mday,
		t.tm_hour, t.tm_min, t.tm_sec, nivel, modul, mesaj ? mesaj : "");
	if (r < 0)
		return 0;
	if ((size_t)r >= n)
		r = (int)n - 1;
	return (size_t)r;
}

static const char *nivelBun(const char *nivel)
{
	if (nivel && !strcmp(nivel, AVERT))
		return AVERT;
	if (nivel && !strcmp(nivel, EROARE))
		return EROARE;
	return INFO;
}

static void modulBun(char *dst, const char *modul)
{
	size_t i = 0;
	if (modul)
		for (; modul[i] && i < LUNGIME_MODUL; ++i)
			dst[i] = ((unsigned char)modul[i] <= ' ' || modul[i] == ']' || modul[i] == '[') ? '-' : modul[i];
	if (!i)
		dst[i++] = '-';
	dst[i] = 0;
}

/* ------------------------------------------------------------------ firul jurnalelor */

struct Fisier
{
	char componenta[LUNGIME_COMPONENTA + 1];
	int fd;
	size_t marime;
	ino_t ino;
	int atins;
};

static pthread_once_t s_o_data = PTHREAD_ONCE_INIT;
static int s_teava[2] = { -1, -1 };
static std::atomic<unsigned long> s_pierdute(0);
static std::atomic<unsigned long> s_trimise(0);
static std::atomic<unsigned long> s_mutati(0);
static Fisier s_fisiere[FISIERE_DESCHISE];  /* numai firul jurnalelor */
static int s_numar = 0;

const char *dosar()
{
	const char *d = getenv("HDS_JURNAL_DIR");
	return (d && *d) ? d : DOSAR_IMPLICIT;
}

static void cale(char *buf, size_t n, const char *componenta, int vechi)
{
	if (vechi)
		snprintf(buf, n, "%s/hds-%s.log.%d", dosar(), componenta, vechi);
	else
		snprintf(buf, n, "%s/hds-%s.log", dosar(), componenta);
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

static void roteste(const char *componenta)
{
	char a[512], b[512];
	for (int v = FISIERE_VECHI; v > 1; --v)
	{
		cale(a, sizeof(a), componenta, v - 1);
		cale(b, sizeof(b), componenta, v);
		::rename(a, b);
	}
	cale(a, sizeof(a), componenta, 0);
	cale(b, sizeof(b), componenta, 1);
	::rename(a, b);
}

static void randPornit(Fisier &f)
{
	char comm[32] = "?";
	int fd = ::open("/proc/self/comm", O_RDONLY | O_CLOEXEC);
	if (fd >= 0)
	{
		ssize_t r = ::read(fd, comm, sizeof(comm) - 1);
		::close(fd);
		comm[r > 0 ? r : 0] = 0;
		char *nl = strchr(comm, '\n');
		if (nl)
			*nl = 0;
	}
	char mesaj[128], rand[LUNGIME_RAND];
	snprintf(mesaj, sizeof(mesaj), "pornit: proces=%s pid=%d up=%.1fs", comm, (int)getpid(), secunde(CLOCK_MONOTONIC));
	curata(mesaj);
	struct timespec real;
	clock_gettime(CLOCK_REALTIME, &real);
	size_t n = formeaza(rand, sizeof(rand) - 1, real, INFO, "jurnal", mesaj);
	rand[n++] = '\n';
	scrieTot(f.fd, rand, n);
	f.marime += n;
}

static int deschide(Fisier &f, int primaOara)
{
	char c[512];
	cale(c, sizeof(c), f.componenta, 0);
	if (mkdir(dosar(), 0755) && errno != EEXIST)
		return -1;
	f.fd = ::open(c, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0644);
	if (f.fd < 0)
		return -1;
	fchmod(f.fd, 0644);  /* open trece prin libopen.so (LD_PRELOAD), care nu da mai departe drepturile */
	struct stat st;
	if (fstat(f.fd, &st))
	{
		st.st_size = 0;
		st.st_ino = 0;
	}
	f.marime = (size_t)st.st_size;
	f.ino = st.st_ino;
	if (f.marime >= ROTIRE_OCTETI)
	{
		::close(f.fd);
		roteste(f.componenta);
		f.fd = ::open(c, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0644);
		if (f.fd < 0)
			return -1;
		fchmod(f.fd, 0644);
		f.marime = 0;
		f.ino = fstat(f.fd, &st) ? 0 : st.st_ino;
	}
	if (primaOara)
		randPornit(f);
	return f.fd;
}

static Fisier *fisier(const char *componenta)
{
	for (int i = 0; i < s_numar; ++i)
		if (!strcmp(s_fisiere[i].componenta, componenta))
			return &s_fisiere[i];
	Fisier *f;
	if (s_numar < FISIERE_DESCHISE)
		f = &s_fisiere[s_numar++];
	else
	{
		f = &s_fisiere[FISIERE_DESCHISE - 1];  /* prea multe componente: ultimul loc se refoloseste */
		if (f->fd >= 0)
			::close(f->fd);
	}
	strncpy(f->componenta, componenta, LUNGIME_COMPONENTA);
	f->componenta[LUNGIME_COMPONENTA] = 0;
	f->fd = -1;
	f->marime = 0;
	f->ino = 0;
	f->atins = 0;
	deschide(*f, 1);
	return f;
}

/* la prima atingere dintr-o citire: fisierul sters sau rotit de altcineva se deschide din nou */
static void verifica(Fisier &f)
{
	char c[512];
	cale(c, sizeof(c), f.componenta, 0);
	struct stat st;
	if (f.fd >= 0 && !::stat(c, &st) && st.st_ino == f.ino)
		return;
	if (f.fd >= 0)
		::close(f.fd);
	f.fd = -1;
	deschide(f, 0);
}

static void unRand(char *rec, size_t n)
{
	char *d = (char *)memchr(rec, DESPARTITOR, n);
	if (!d)
		return;
	*d = 0;
	if (!numeBun(rec))
		return;
	Fisier *f = fisier(rec);
	if (!f)
		return;
	if (!f->atins)
	{
		verifica(*f);
		f->atins = 1;
	}
	if (f->fd < 0)
		return;
	char *rand = d + 1;
	size_t lung = n - (size_t)(rand - rec);
	scrieTot(f->fd, rand, lung);
	f->marime += lung;
	if (f->marime >= ROTIRE_OCTETI)
	{
		fdatasync(f->fd);
		::close(f->fd);
		f->fd = -1;
		roteste(f->componenta);
		deschide(*f, 0);
	}
}

static void *firJurnal(void *)
{
	static char buf[16384];
	size_t rest = 0;
	for (;;)
	{
		ssize_t r = ::read(s_teava[0], buf + rest, sizeof(buf) - rest);
		if (r < 0)
		{
			if (errno == EINTR)
				continue;
			break;
		}
		if (r == 0)
			break;
		size_t total = rest + (size_t)r, inceput = 0;
		for (size_t i = 0; i < total; ++i)
			if (buf[i] == '\n')
			{
				unRand(buf + inceput, i + 1 - inceput);
				inceput = i + 1;
			}
		rest = total - inceput;
		if (rest == sizeof(buf))
			rest = 0;  /* nu se poate (randurile sunt sub PIPE_BUF), dar nu ramane blocat */
		else if (rest && inceput)
			memmove(buf, buf + inceput, rest);
		for (int i = 0; i < s_numar; ++i)
			if (s_fisiere[i].atins)
			{
				if (s_fisiere[i].fd >= 0)
					fdatasync(s_fisiere[i].fd);
				s_fisiere[i].atins = 0;
			}
		s_mutati.fetch_add((unsigned long)r);
	}
	return 0;
}

static void porneste()
{
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
	fcntl(t[1], F_SETPIPE_SZ, 128 * 1024);
#endif
	s_teava[0] = t[0];
	pthread_attr_t atr;
	pthread_t fir;
	pthread_attr_init(&atr);
	pthread_attr_setdetachstate(&atr, PTHREAD_CREATE_DETACHED);
	pthread_attr_setstacksize(&atr, 64 * 1024);
	if (pthread_create(&fir, &atr, firJurnal, 0))
	{
		::close(t[0]);
		::close(t[1]);
		s_teava[0] = -1;
	}
	else
		s_teava[1] = t[1];
	pthread_attr_destroy(&atr);
}

static int inTeava(const char *rec, size_t n)
{
	ssize_t r;
	do
		r = ::write(s_teava[1], rec, n);
	while (r < 0 && errno == EINTR);
	if (r == (ssize_t)n)
	{
		s_trimise.fetch_add((unsigned long)n);
		return 1;
	}
	return 0;
}

static size_t inregistrare(char *rec, size_t n, const char *componenta, const char *nivel, const char *modul,
	const char *mesaj)
{
	size_t lc = strlen(componenta);
	if (lc + 3 >= n)
		return 0;
	memcpy(rec, componenta, lc);
	rec[lc] = DESPARTITOR;
	struct timespec real;
	clock_gettime(CLOCK_REALTIME, &real);
	size_t lr = formeaza(rec + lc + 1, n - lc - 2, real, nivel, modul, mesaj);
	rec[lc + 1 + lr] = '\n';
	return lc + 2 + lr;
}

void scrie(const char *componenta, const char *nivel, const char *modul, const char *mesaj)
{
	pthread_once(&s_o_data, porneste);
	if (s_teava[1] < 0)
		return;
	const char *comp = numeBun(componenta) ? componenta : "diverse";
	char m[LUNGIME_MESAJ + 1], md[LUNGIME_MODUL + 1], rec[LUNGIME_RAND + LUNGIME_COMPONENTA + 4];
	size_t i = 0;
	if (mesaj)
		for (; mesaj[i] && i < LUNGIME_MESAJ; ++i)
			m[i] = mesaj[i];
	m[i] = 0;
	curata(m);
	modulBun(md, modul);
	unsigned long pierdute = s_pierdute.exchange(0);
	if (pierdute)
	{
		char p[96];
		snprintf(p, sizeof(p), "%lu randuri pierdute (teava plina)", pierdute);
		size_t n = inregistrare(rec, sizeof(rec), comp, AVERT, "jurnal", p);
		if (!n || !inTeava(rec, n))
		{
			s_pierdute.fetch_add(pierdute + 1);
			return;
		}
	}
	size_t n = inregistrare(rec, sizeof(rec), comp, nivelBun(nivel), md, m);
	if (!n || !inTeava(rec, n))
		s_pierdute.fetch_add(1);
}

void scrief(const char *componenta, const char *nivel, const char *modul, const char *fmt, ...)
{
	char m[LUNGIME_MESAJ + 1];
	va_list ap;
	va_start(ap, fmt);
	int r = vsnprintf(m, sizeof(m), fmt, ap);
	va_end(ap);
	if (r < 0)
		return;
	scrie(componenta, nivel, modul, m);
}

int asteaptaScrierea(int ms)
{
	for (int i = 0; i <= ms; i += 5)
	{
		if (s_mutati.load() >= s_trimise.load())
			return 0;
		usleep(5000);
	}
	return s_mutati.load() >= s_trimise.load() ? 0 : -1;
}

/* ------------------------------------------------------------------ frana */

Frana::Frana(int pauza_ms)
	: m_pauza_ms(pauza_ms), m_ultim(-1.0), m_sarite(0)
{
}

bool Frana::lasa(unsigned long &sarite)
{
	double acum = secunde(CLOCK_MONOTONIC);
	if (m_ultim >= 0.0 && (acum - m_ultim) * 1000.0 < m_pauza_ms)
	{
		++m_sarite;
		return false;
	}
	sarite = m_sarite;
	m_sarite = 0;
	m_ultim = acum;
	return true;
}

}

void hdsJurnalScrie(const char *componenta, const char *nivel, const char *modul, const char *mesaj)
{
	hdsjurnal::scrie(componenta, nivel, modul, mesaj);
}
