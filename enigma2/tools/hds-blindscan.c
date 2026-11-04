/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hds-blindscan: cautarea oarba pe satelit pe tunerul de satelit, cu transponderele gasite scrise pe iesirea
 * standard, cate unul pe rand. Program separat de enigma2, pornit la cerere de ecranul de cautare oarba si de
 * interfata web; ele vorbesc numai protocolul de mai jos si nu stiu ce e in spatele lui.
 *
 * Biblioteca platformei o incarcam la rulare (dlopen) si chemam numai functii exportate de ea. Nu avem antetele ei:
 * forma structurilor de mai jos am aflat-o din ce cere si ce citeste biblioteca insasi (codul ei binar livrat pe
 * receptor), iar valorile de pornire ale tunerului sunt cele cu care driverul DVB al platformei porneste acelasi
 * tuner (tabela lui de placi). Numele si comentariile sunt ale noastre.
 *
 * CUM CAUTA: cautarea o face CIPUL demodulator (cautarea lui de purtatoare pe toata fereastra data, la orice rata
 * intre 1 si 50 MSym/s), nu programul pas cu pas. Programul:
 *   1. verifica placa: portul cerut din /proc/msp/tuner trebuie sa fie exact unul din profilurile cunoscute (canal
 *      I2C, adresa demodulatorului, tunerul si adresa lui); altfel refuza si nu atinge nimic;
 *   2. asteapta ca enigma2 sa elibereze frontend-ul tunerului (nu porneste peste o inregistrare sau un canal deschis);
 *   3. opreste citirea starii de catre driverul DVB (tuner_used = 1), porneste tunerul cu valorile platformei
 *      (aceleasi ca la pornirea receptorului), pune LNB-ul si face TOATE trecerile cerute intr-un singur proces (o singura
 *      pornire a cipului), fiecare trecere taiata in felii, ca oprirea sa fie curata (TERM/INT opreste dupa felia
 *      curenta, fara sa lase cipul la jumatate);
 *   4. la orice iesire pune tuner_used inapoi pe 0 si inchide biblioteca. Dupa cautare, enigma2 acordeaza din nou la
 *      primul canal.
 *
 * PROTOCOL (o linie pe rand; mesajele pentru om vin din enigma2, traduse):
 *   PROFIL <port> <i2c> <adr_demod> <tuner> <adr_tuner> <gpio>   ce arata placa (gpio 0x0 = placa necunoscuta)
 *   PROFIL <port> hife <tuner>                                   placa cu /dev/hife (SF8008: Si2166, AVL62X1)
 *   PORNIT <nr_treceri> <latime_totala_khz>                      cautarea a pornit
 *   TRECERE <nr> <pol> <ton22k> <if_start_khz> <if_stop_khz>     incepe o trecere (numarate de la 1)
 *   PROGRES <procent> <gasite>                                   pe toata cautarea
 *   TP <frecventa_khz> <rata_ksym> <sistem> <pol> <if_khz> <calitate>
 *                                                                un transponder gasit, frecventa reala pe satelit;
 *                                                                sistem -1 = necunoscut (il afla scanarea obisnuita)
 *   JURNAL <cuvant> <valori...>                                  amanunte pentru jurnal (timpi, stari)
 *   GATA <gasite> <durata_ms>                                    s-a terminat singura
 *   OPRIT <gasite> <durata_ms>                                   oprita din afara (TERM/INT) sau de paznicul de timp
 *   EROARE <cod> <text-scurt>                                    nu a putut porni sau a cazut
 *   SONDA <cod> <text-scurt>                                     raspunsul la --sonda
 *
 * ARGUMENTE:
 *   --trecere POL,TON,START,STOP   o trecere: polarizarea H|V|L|R, tonul 22 kHz 0|1, banda IF in kHz
 *                                  (950000..2150000); se pot da mai multe, se fac in ordinea data
 *   --tuner N                      portul tunerului de satelit (implicit 0)
 *   --lo-jos MHZ --lo-sus MHZ      oscilatoarele LNB-ului (implicit 9750 si 10600); egale = LNB cu un oscilator;
 *                                  sub 7500 MHz = banda C (frecventa reala = LO - IF)
 *   --felie KHZ                    latimea unei felii (implicit 150000, masurat pe un V20; 0 = trecerea intreaga)
 *   --timp-max S                   paznicul de timp: dupa atatea secunde se opreste curat (implicit 1200)
 *   --asteapta-frontend S          cat asteapta sa se elibereze frontend-ul (implicit 15)
 *   --lib CALE                     alta cale pentru biblioteca platformei
 *   --sonda                        NU porneste nimic: verifica placa, biblioteca si simbolurile, tuner_used si cine tine
 *                                  frontend-ul; scrie PROFIL si SONDA. Nu deschide tunerul. Pe o placa „hife”: numai
 *                                  dispozitivul, numele tunerului din /proc/bus/nim_sockets si cine tine frontend-ul.
 *   --versiune
 *
 * IESIRE: 0 = GATA/OPRIT/SONDA, 1 = eroare la pornire, 2 = argument gresit, 3 = oprit de paznicul de timp.
 */
#define _GNU_SOURCE
#include <ctype.h>
#include <dirent.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <linux/dvb/frontend.h>
#include <time.h>
#include <unistd.h>

#ifndef HDS_BLINDSCAN_VERSIUNE
#define HDS_BLINDSCAN_VERSIUNE "0.0.0"
#endif

#define IF_MIN_KHZ 950000u
#define IF_MAX_KHZ 2150000u
#define MAX_TRECERI 64
#define MAX_GASITE 1024
#define SUPRAPUNERE_KHZ 8000u      /* feliile vecine se suprapun, ca un transponder de la margine sa nu cada */
#define FELIE_MIN_KHZ 20000u

#ifndef PROC_TUNER
#define PROC_TUNER "/proc/msp/tuner"
#endif
#ifndef TUNER_USED
#define TUNER_USED "/proc/stb/parameters/tuner_used"
#endif
#ifndef ZAVOR_PROCES
#define ZAVOR_PROCES "/tmp/hds-blindscan.lock"
#endif
/* Calea /dev/hife (SF8008) e scrisa dupa interfata driverului citita din binare; pornita pentru toti (o functie din
 * imagine nu se ascunde in spatele unui semn: oamenii o probeaza si vedem daca merge). */

/* ---------------------------------------------------------------- structurile cerute de biblioteca */
/* Parametrul cautarii (7 cuvinte). Biblioteca citeste polarizarea, tonul, banda IF si raportul. */
typedef struct {
	uint32_t mod;          /* +0  1 = banda data de noi */
	uint32_t polarizare;   /* +4  0 H, 1 V, 2 L, 3 R */
	uint32_t ton22k;       /* +8  0 oprit, 1 pornit */
	uint32_t if_start_khz; /* +12 */
	uint32_t if_stop_khz;  /* +16 */
	void    *comutator;    /* +20 functie optionala de comutare; NULL = nu e */
	void   (*raport)(uint32_t tuner, uint32_t eveniment, void *notificare); /* +24 */
} ParamCautare;

/* Ce primeste raportul la evenimentul 2: un transponder (16 o). */
typedef struct {
	uint32_t frecventa_khz; /* frecventa reala pe satelit (biblioteca socoteste LO-ul din configurarea LNB) */
	uint32_t rata_baud;
	uint32_t polarizare;
	uint8_t  calitate;
	uint8_t  rezervat[3];
} TpGasit;

/* Atributele tunerului (32 o), aceleasi ca la pornirea receptorului. */
typedef struct {
	uint32_t semnal;      /* 2 = satelit */
	uint32_t tip_tuner;
	uint32_t adr_tuner;
	uint32_t tip_demod;
	uint32_t adr_demod;
	uint32_t iesire_ts;
	uint8_t  canal_i2c;
	uint8_t  rezervat[3];
	uint32_t gpio_reset;
} AtributTuner;

/* Atributele de satelit (40 o), aceleasi ca la pornirea receptorului. */
typedef struct {
	uint32_t ceas_demod_khz;
	uint16_t filtru_max_mhz;
	uint16_t ceas_i2c_khz;
	uint32_t c8, c12, c16, c20, c24, c28;
	uint32_t c32;
	uint16_t c36, c38;
} AtributSat;

/* Configurarea LNB-ului (32 o). */
typedef struct {
	uint32_t tip;        /* 0 un oscilator, 1 doua (universal) */
	uint32_t lo_jos_mhz;
	uint32_t lo_sus_mhz;
	uint32_t lo_trei_mhz;
	uint32_t banda;      /* 0 C, 1 Ku */
	uint8_t  scr;
	uint8_t  rezervat[3];
	uint32_t scr_if_mhz;
	uint32_t pozitie;
} ConfigLnb;

#if defined(__arm__)
typedef char verifica_param[sizeof(ParamCautare) == 28 ? 1 : -1];
#endif
typedef char verifica_tp[sizeof(TpGasit) == 16 ? 1 : -1];
typedef char verifica_atr[sizeof(AtributTuner) == 32 ? 1 : -1];
typedef char verifica_sat[sizeof(AtributSat) == 40 ? 1 : -1];
typedef char verifica_lnb[sizeof(ConfigLnb) == 32 ? 1 : -1];

/* Profilurile cunoscute: ce arata /proc/msp/tuner pentru port -> valorile de pornire din tabela platformei.
 * Numai combinatii unice in tabela; orice alta placa e refuzata. */
typedef struct {
	uint32_t port, i2c, adr_demod, adr_tuner;
	const char *nume_tuner;
	uint32_t tip_tuner, tip_demod, iesire_ts, gpio_reset;
} Profil;

static const Profil PROFILURI[] = {
	{ 0, 2, 0xc8, 0xc4, "AV2018", 0x1d, 0x11c, 3, 0x22 },  /* tunerul de satelit al placii u57/u571 */
	{ 1, 1, 0xc8, 0xc4, "AV2018", 0x1d, 0x11c, 3, 0x1d },  /* al doilea tuner de satelit, varianta cu doua */
};

/* Semnaturile functiilor folosite (rezolvate cu dlsym). */
typedef int (*fn_v)(void);
typedef int (*fn_u)(uint32_t);
typedef int (*fn_up)(uint32_t, const void *);
typedef int (*fn_uu)(uint32_t, uint32_t);
typedef void (*fn_proc)(uint32_t, const ParamCautare *);

static struct {
	void *lib;
	fn_v init, deinit;
	fn_u open, close;
	fn_up setattr, setsatattr, setlnbconfig;
	fn_uu setlnbpower;
	fn_proc cautare;
} B;

static volatile sig_atomic_t cerere_oprire = 0;
static volatile sig_atomic_t lucru_terminat = 0;

/* ---------------------------------------------------------------- iesirea */
static pthread_mutex_t m_iesire = PTHREAD_MUTEX_INITIALIZER;

static void linie(const char *fmt, ...) {
	va_list ap;
	pthread_mutex_lock(&m_iesire);
	va_start(ap, fmt);
	vprintf(fmt, ap);
	va_end(ap);
	putchar('\n');
	if (fflush(stdout) || ferror(stdout)) cerere_oprire = 1;   /* cititorul a plecat: oprim curat */
	pthread_mutex_unlock(&m_iesire);
}

static uint64_t ms_acum(void) {
	struct timespec t;
	clock_gettime(CLOCK_MONOTONIC, &t);
	return (uint64_t)t.tv_sec * 1000u + (uint64_t)t.tv_nsec / 1000000u;
}

static int numar(const char *s, long *v) {
	if (!s || !*s) return -1;
	char *cap = NULL;
	errno = 0;
	long x = strtol(s, &cap, 0);
	if (errno || cap == s || *cap) return -1;
	*v = x;
	return 0;
}

/* ---------------------------------------------------------------- placa */
typedef struct {
	long port, i2c, adr_demod, adr_tuner;
	char nume_tuner[48];
	int gasit;
} RandProc;

/* Randul portului din /proc/msp/tuner: "N: stare i2c semnal frecventa rata qam <demod...> 0xDD <tuner...> 0xTT".
 * Numele demodului si al tunerului pot avea spatii; tunerul e intre cele doua adrese hexa. */
static int citeste_proc_tuner(long port, RandProc *r) {
	memset(r, 0, sizeof *r);
	FILE *f = fopen(PROC_TUNER, "r");
	if (!f) return -1;
	char buf[512];
	while (fgets(buf, sizeof buf, f)) {
		char *tok[32];
		int n = 0;
		for (char *p = strtok(buf, " \t\r\n"); p && n < 32; p = strtok(NULL, " \t\r\n")) tok[n++] = p;
		if (n < 10) continue;
		size_t l = strlen(tok[0]);
		if (l < 2 || tok[0][l - 1] != ':') continue;
		tok[0][l - 1] = '\0';
		long p0;
		if (numar(tok[0], &p0) || p0 != port) continue;
		int h1 = -1, h2 = -1;
		for (int i = 7; i < n; i++) {
			if (!strncmp(tok[i], "0x", 2) || !strncmp(tok[i], "0X", 2)) { if (h1 < 0) h1 = i; else h2 = i; }
		}
		if (h1 < 0 || h2 < 0 || h2 <= h1 + 1) continue;
		if (numar(tok[2], &r->i2c) || numar(tok[h1], &r->adr_demod) || numar(tok[h2], &r->adr_tuner)) continue;
		r->nume_tuner[0] = '\0';
		for (int i = h1 + 1; i < h2; i++) {
			if (r->nume_tuner[0]) strncat(r->nume_tuner, "_", sizeof r->nume_tuner - strlen(r->nume_tuner) - 1);
			strncat(r->nume_tuner, tok[i], sizeof r->nume_tuner - strlen(r->nume_tuner) - 1);
		}
		r->port = port;
		r->gasit = 1;
		break;
	}
	fclose(f);
	return r->gasit ? 0 : -1;
}

static const Profil *profil_placa(long port, RandProc *r) {
	if (citeste_proc_tuner(port, r)) return NULL;
	for (size_t i = 0; i < sizeof PROFILURI / sizeof PROFILURI[0]; i++) {
		const Profil *p = &PROFILURI[i];
		if ((long)p->port == port && (long)p->i2c == r->i2c && (long)p->adr_demod == r->adr_demod &&
		    (long)p->adr_tuner == r->adr_tuner && !strcmp(p->nume_tuner, r->nume_tuner))
			return p;
	}
	return NULL;
}

/* Cine tine deschis /dev/dvb/adapter0/frontend<port>: pid-ul primului gasit, 0 = nimeni. */
static int cine_tine_frontend(long port) {
	char tinta_cautata[64];
	snprintf(tinta_cautata, sizeof tinta_cautata, "/dev/dvb/adapter0/frontend%ld", port);
	DIR *proc = opendir("/proc");
	if (!proc) return 0;
	struct dirent *d;
	int gasit = 0;
	char cale[300], leg[400], tinta[256];
	while (!gasit && (d = readdir(proc))) {
		const char *c = d->d_name;
		if (!*c) continue;
		int cifre = 1;
		for (; *c; c++) if (!isdigit((unsigned char)*c)) { cifre = 0; break; }
		if (!cifre || atoi(d->d_name) == (int)getpid()) continue;
		snprintf(cale, sizeof cale, "/proc/%.64s/fd", d->d_name);
		DIR *fd = opendir(cale);
		if (!fd) continue;
		struct dirent *e;
		while ((e = readdir(fd))) {
			snprintf(leg, sizeof leg, "%.300s/%.64s", cale, e->d_name);
			ssize_t n = readlink(leg, tinta, sizeof tinta - 1);
			if (n <= 0) continue;
			tinta[n] = '\0';
			if (!strcmp(tinta, tinta_cautata)) { gasit = atoi(d->d_name); break; }
		}
		closedir(fd);
	}
	closedir(proc);
	return gasit;
}

static int citeste_tuner_used(void) {
	FILE *f = fopen(TUNER_USED, "r");
	if (!f) return -1;
	int v = -1;
	if (fscanf(f, "%d", &v) != 1) v = -1;
	fclose(f);
	return v;
}

static int scrie_tuner_used(int v) {
	int fd = open(TUNER_USED, O_WRONLY);
	if (fd < 0) return -1;
	char b[2] = { (char)('0' + (v ? 1 : 0)), '\n' };
	ssize_t n = write(fd, b, 2);
	close(fd);
	return n == 2 ? 0 : -1;
}

/* ---------------------------------------------------------------- biblioteca */
/* libhi_msp nu are scrise bibliotecile de care depinde: simbolurile din libm, libhi_common si libjpeg trebuie sa fie
 * deja incarcate global (in showiframe sunt, fiind legat de ele). Le incarcam noi intai; ce lipseste se vede la
 * libhi_msp, in randul JURNAL dlopen. */
static const char *DEPENDINTE[] = { "libm.so.6", "libhi_common.so", "libjpeg.so.62" };

static int incarca_biblioteca(const char *cale) {
	for (size_t i = 0; i < sizeof DEPENDINTE / sizeof DEPENDINTE[0]; i++)
		dlopen(DEPENDINTE[i], RTLD_NOW | RTLD_GLOBAL);   /* raman incarcate pana la iesire */
	const char *cai[] = { cale, "libhi_msp.so", "libhi_msp.so.0.0", "/usr/lib/libhi_msp.so" };
	const char *ultima_eroare = NULL;
	for (int i = 0; i < 4 && !B.lib; i++) {
		if (!cai[i]) continue;
		B.lib = dlopen(cai[i], RTLD_NOW | RTLD_GLOBAL);
		if (!B.lib) ultima_eroare = dlerror();
	}
	if (!B.lib) {
		if (ultima_eroare) linie("JURNAL dlopen %s", ultima_eroare);
		return 1;
	}
	B.init         = (fn_v)dlsym(B.lib, "HI_UNF_TUNER_Init");
	B.deinit       = (fn_v)dlsym(B.lib, "HI_UNF_TUNER_DeInit");
	B.open         = (fn_u)dlsym(B.lib, "HI_UNF_TUNER_Open");
	B.close        = (fn_u)dlsym(B.lib, "HI_UNF_TUNER_Close");
	B.setattr      = (fn_up)dlsym(B.lib, "HI_UNF_TUNER_SetAttr");
	B.setsatattr   = (fn_up)dlsym(B.lib, "HI_UNF_TUNER_SetSatAttr");
	B.setlnbconfig = (fn_up)dlsym(B.lib, "HI_UNF_TUNER_SetLNBConfig");
	B.setlnbpower  = (fn_uu)dlsym(B.lib, "HI_UNF_TUNER_SetLNBPower");
	B.cautare      = (fn_proc)dlsym(B.lib, "TUNER_BlindScanProcess");
	if (!B.init || !B.deinit || !B.open || !B.close || !B.setattr || !B.setsatattr || !B.setlnbconfig ||
	    !B.setlnbpower || !B.cautare)
		return 2;
	return 0;
}

/* ---------------------------------------------------------------- trecerile si rezultatele */
typedef struct {
	uint32_t polarizare, ton22k, if_start, if_stop;
	char eticheta;
} Trecere;

static Trecere treceri[MAX_TRECERI];
static int nr_treceri = 0;
static uint32_t lo_jos_mhz = 9750, lo_sus_mhz = 10600;
static uint32_t felie_khz = 150000;
static long port_tuner = 0;
static const Profil *placa_aleasa = NULL;

static struct {
	uint32_t frecventa_khz, rata_ksym, polarizare;
} gasite[MAX_GASITE];
static int nr_gasite = 0;
static int cod_lucru = 0;          /* 0 bine, altceva = eroare de pornire (deja scrisa) */
static int oprit_de_paznic = 0;

/* progresul pe toata cautarea */
static uint64_t khz_total = 0, khz_facuti = 0;
static uint32_t khz_felie = 0;
static int ultimul_procent = -1;
static uint32_t stare_felie = 0;
static int trecere_curenta = 0;

static int e_dublura(uint32_t f, uint32_t rata_ksym, uint32_t pol) {
	for (int i = 0; i < nr_gasite; i++) {
		if (gasite[i].polarizare != pol) continue;
		uint32_t r = gasite[i].rata_ksym < rata_ksym ? gasite[i].rata_ksym : rata_ksym;
		uint32_t tol = r / 4 > 1000 ? r / 4 : 1000;   /* kHz: un sfert din rata, cel putin 1 MHz */
		uint32_t d = gasite[i].frecventa_khz > f ? gasite[i].frecventa_khz - f : f - gasite[i].frecventa_khz;
		if (d <= tol) return 1;
	}
	return 0;
}

static uint32_t lo_trecere_mhz(const Trecere *t) {
	if (lo_jos_mhz == lo_sus_mhz) return lo_jos_mhz;
	return t->ton22k ? lo_sus_mhz : lo_jos_mhz;
}

static uint32_t pas_felie(const Trecere *t) {
	uint32_t latime = t->if_stop - t->if_start;
	if (!felie_khz || felie_khz >= latime) return latime;
	return felie_khz < FELIE_MIN_KHZ ? FELIE_MIN_KHZ : felie_khz;
}

static void scrie_progres(uint32_t procent_felie) {
	if (!khz_total) return;
	uint64_t facut = khz_facuti + (uint64_t)khz_felie * (procent_felie > 100 ? 100 : procent_felie) / 100u;
	int p = (int)(facut * 100u / khz_total);
	if (p > 100) p = 100;
	if (p != ultimul_procent) {
		ultimul_procent = p;
		linie("PROGRES %d %d", p, nr_gasite);
	}
}

/* Raportul chemat de biblioteca din firul de lucru. notificare = pointer la pointerul datelor evenimentului:
 * 0 = starea (u32: 1 in curs, 2 gata, 3 oprita, 4 cadere), 1 = progresul feliei (u16, procent), 2 = transponder. */
static void raport(uint32_t tuner, uint32_t eveniment, void *notificare) {
	(void)tuner;
	void *date = notificare ? *(void **)notificare : NULL;
	if (!date) return;
	if (eveniment == 0) {
		stare_felie = *(const uint32_t *)date;
	} else if (eveniment == 1) {
		scrie_progres(*(const uint16_t *)date);
	} else if (eveniment == 2) {
		const TpGasit *t = (const TpGasit *)date;
		const uint8_t *o = (const uint8_t *)date;
		/* cei 16 octeti asa cum vin: daca sistemul (S/S2) sau modulatia stau in octetii de dupa calitate */
		linie("JURNAL tp-brut %02x%02x%02x%02x %02x%02x%02x%02x %02x%02x%02x%02x %02x%02x%02x%02x",
		      o[0], o[1], o[2], o[3], o[4], o[5], o[6], o[7], o[8], o[9], o[10], o[11], o[12], o[13], o[14], o[15]);
		uint32_t f = t->frecventa_khz, rata = t->rata_baud / 1000u, pol = t->polarizare;
		if (f < 1000000u || f > 30000000u || rata < 500u || rata > 70000u || pol > 3) {
			linie("JURNAL tp-respins %u %u %u", f, t->rata_baud, pol);
			return;
		}
		if (e_dublura(f, rata, pol) || nr_gasite >= MAX_GASITE) return;
		gasite[nr_gasite].frecventa_khz = f;
		gasite[nr_gasite].rata_ksym = rata;
		gasite[nr_gasite].polarizare = pol;
		nr_gasite++;
		uint32_t lo = lo_trecere_mhz(&treceri[trecere_curenta]) * 1000u;
		uint32_t fi = lo < 7500000u ? (lo > f ? lo - f : 0) : (f > lo ? f - lo : 0);
		linie("TP %u %u -1 %c %u %u", f, rata, "HVLR"[pol], fi, (unsigned)t->calitate);
	}
}

/* Firul de lucru: toata partea de placa. Semnalele sunt blocate aici (ioctl-urile bibliotecii nu sunt intrerupte);
 * firul principal le primeste si cere oprirea, care se face intre felii. */
static void *lucru(void *arg) {
	(void)arg;
	int cod;
	AtributTuner a;
	AtributSat s;
	ConfigLnb l;
	uint64_t t0;
	/* driverul DVB nu mai citeste demodulatorul inainte ca noi sa-l resetam (fara trafic I2C in paralel) */
	if (scrie_tuner_used(1)) { linie("EROARE 1 tuner-used"); cod_lucru = 1; goto gata; }
	if ((cod = B.init()) != 0) { linie("EROARE %d init", cod); cod_lucru = 1; goto liber; }
	if ((cod = B.open((uint32_t)port_tuner)) != 0) { linie("EROARE %d deschidere", cod); cod_lucru = 1; goto deinit; }

	memset(&a, 0, sizeof a);
	a.semnal = 2;
	a.tip_tuner = placa_aleasa->tip_tuner;
	a.adr_tuner = placa_aleasa->adr_tuner;
	a.tip_demod = placa_aleasa->tip_demod;
	a.adr_demod = placa_aleasa->adr_demod;
	a.iesire_ts = placa_aleasa->iesire_ts;
	a.canal_i2c = (uint8_t)placa_aleasa->i2c;
	a.gpio_reset = placa_aleasa->gpio_reset;
	t0 = ms_acum();
	if ((cod = B.setattr((uint32_t)port_tuner, &a)) != 0) { linie("EROARE %d atribute", cod); cod_lucru = 1; goto inchide; }

	memset(&s, 0, sizeof s);
	s.ceas_demod_khz = 24000;
	s.filtru_max_mhz = 40;
	s.ceas_i2c_khz = 400;
	s.c32 = 1;
	if ((cod = B.setsatattr((uint32_t)port_tuner, &s)) != 0) { linie("EROARE %d atribute-satelit", cod); cod_lucru = 1; goto inchide; }

	memset(&l, 0, sizeof l);
	l.tip = lo_jos_mhz == lo_sus_mhz ? 0 : 1;
	l.lo_jos_mhz = lo_jos_mhz;
	l.lo_sus_mhz = lo_sus_mhz;
	l.banda = lo_jos_mhz < 7500 ? 0 : 1;
	if ((cod = B.setlnbconfig((uint32_t)port_tuner, &l)) != 0) { linie("EROARE %d lnb", cod); cod_lucru = 1; goto inchide; }
	if ((cod = B.setlnbpower((uint32_t)port_tuner, 1)) != 0) { linie("EROARE %d alimentare-lnb", cod); cod_lucru = 1; goto inchide; }
	linie("JURNAL pornire-tuner-ms %llu", (unsigned long long)(ms_acum() - t0));

	linie("PORNIT %d %llu", nr_treceri, (unsigned long long)khz_total);
	for (int i = 0; i < nr_treceri && !cerere_oprire; i++) {
		Trecere *t = &treceri[i];
		trecere_curenta = i;
		linie("TRECERE %d %c %u %u %u", i + 1, t->eticheta, t->ton22k, t->if_start, t->if_stop);
		uint64_t tt = ms_acum();
		uint32_t pas = pas_felie(t);
		for (uint32_t a0 = t->if_start; a0 < t->if_stop && !cerere_oprire; a0 += pas) {
			uint32_t a1 = a0 + pas + SUPRAPUNERE_KHZ;
			if (a1 > t->if_stop || t->if_stop - a1 < FELIE_MIN_KHZ) a1 = t->if_stop;
			ParamCautare p;
			memset(&p, 0, sizeof p);
			p.mod = 1;
			p.polarizare = t->polarizare;
			p.ton22k = t->ton22k;
			p.if_start_khz = a0;
			p.if_stop_khz = a1;
			p.raport = raport;
			khz_felie = a1 - a0 > pas ? pas : a1 - a0;
			stare_felie = 0;
			uint64_t tf = ms_acum();
			B.cautare((uint32_t)port_tuner, &p);
			linie("JURNAL felie %u %u stare %u ms %llu", a0, a1, stare_felie, (unsigned long long)(ms_acum() - tf));
			khz_facuti += khz_felie;
			khz_felie = 0;
			scrie_progres(0);
			if (a1 >= t->if_stop) break;
		}
		linie("JURNAL trecere %d ms %llu gasite %d", i + 1, (unsigned long long)(ms_acum() - tt), nr_gasite);
	}
	if (!cerere_oprire) { khz_facuti = khz_total; scrie_progres(0); }

inchide:
	B.close((uint32_t)port_tuner);
deinit:
	B.deinit();
liber:
	scrie_tuner_used(0);
gata:
	lucru_terminat = 1;
	return NULL;
}

/* ---------------------------------------------------------------- calea „hife” (SF8008, NEPROBATA pe aparat)
 * Pe placile Octagon SF8008 driverul platformei (hi-dvb.ko) are propriile drivere de demodulator (Si2166, AVL62X1) si
 * cautarea oarba facuta de un fir in nucleu, pornita prin dispozitivul /dev/hife. Interfata, aflata din binarele
 * livrate (hi_fe_ioctl in hi-dvb.ko, unealta producatorului care il foloseste):
 *   0x40046f67  alege frontend-ul (int)
 *   0xc0146f65  porneste cautarea pe banda IF data (MHz) si ratele date (Sym/s); toti parametrii 0 = anuleaza
 *   0x6f66      fara tampon: numarul gasit cand e gata, -1 cat lucreaza; cu tampon: lista (frecventa IF in MHz,
 *               rata in kSym/s, apoi FEC, inversia, sistemul, modulatia, rolloff-ul si pilotul)
 * Tensiunea si tonul LNB-ului nu trec prin /dev/hife: le punem noi pe frontend-ul DVB al aceluiasi tuner. */
#define HIFE "/dev/hife"
#define HIFE_ALEGE    0x40046f67u
#define HIFE_PORNESTE 0xc0146f65u
#define HIFE_CITESTE  0x6f66u
#define HIFE_RATA_MIN 1000000u
#define HIFE_RATA_MAX 45000000u
#define HIFE_FELIE_MS_MAX 180000u

typedef struct {
	uint32_t frecventa_start_mhz, frecventa_stop_mhz, rata_min, rata_max, numar;
} HifeParam;

typedef struct {
	uint32_t frecventa_mhz, rata_ksym, fec, inversiune, sistem, modulatie, rolloff, pilot;
} HifeTp;

typedef char verifica_hife_param[sizeof(HifeParam) == 20 ? 1 : -1];
typedef char verifica_hife_tp[sizeof(HifeTp) == 32 ? 1 : -1];

static int mod_hife = 0;
static char nume_nim[48];

/* /proc/bus/nim_sockets: numele tunerului de pe socketul cerut (de pilda „Si2166D”), 0 daca e gasit */
static int citeste_nim(long port, char *nume, size_t n) {
	FILE *f = fopen("/proc/bus/nim_sockets", "r");
	if (!f) return -1;
	char buf[256];
	long cur = -1;
	int gasit = -1;
	while (fgets(buf, sizeof buf, f)) {
		long x;
		if (sscanf(buf, "NIM Socket %ld:", &x) == 1) { cur = x; continue; }
		const char *p = strstr(buf, "Name:");
		if (cur == port && p) {
			p += 5;
			while (*p == ' ' || *p == '\t') p++;
			snprintf(nume, n, "%s", p);
			nume[strcspn(nume, "\r\n")] = '\0';
			gasit = 0;
			break;
		}
	}
	fclose(f);
	return gasit;
}

/* placa cu /dev/hife si un demodulator cu cautare oarba in driver */
static int placa_hife(long port) {
	if (access(HIFE, R_OK | W_OK)) return 0;
	if (citeste_nim(port, nume_nim, sizeof nume_nim)) return 0;
	return strstr(nume_nim, "Si2166") != NULL || strstr(nume_nim, "AVL62X1") != NULL;
}

static uint32_t sistem_din_linux(uint32_t s) {
	/* fe_delivery_system din Linux: SYS_DVBS 5, SYS_DVBS2 6 (sistemul nostru: 0 DVB-S, 1 DVB-S2) */
	return s == 5 ? 0u : s == 6 ? 1u : (uint32_t)-1;
}

static void tp_hife(const HifeTp *t, const Trecere *tr) {
	uint32_t lo = lo_trecere_mhz(tr);
	uint32_t f_mhz = lo < 7500 ? lo - t->frecventa_mhz : lo + t->frecventa_mhz;
	uint32_t f = f_mhz * 1000u, rata = t->rata_ksym, pol = tr->polarizare;
	linie("JURNAL tp-hife %u %u %u %u %u %u %u %u", t->frecventa_mhz, t->rata_ksym, t->fec, t->inversiune, t->sistem,
	      t->modulatie, t->rolloff, t->pilot);
	if (f < 1000000u || f > 30000000u || rata < 500u || rata > 70000u) return;
	if (e_dublura(f, rata, pol) || nr_gasite >= MAX_GASITE) return;
	gasite[nr_gasite].frecventa_khz = f;
	gasite[nr_gasite].rata_ksym = rata;
	gasite[nr_gasite].polarizare = pol;
	nr_gasite++;
	int sis = (int)sistem_din_linux(t->sistem);
	linie("TP %u %u %d %c %u 0", f, rata, sis, "HVLR"[pol], t->frecventa_mhz * 1000u);
}

static void *lucru_hife(void *arg) {
	(void)arg;
	char cale[64];
	int hf = -1, fe;
	snprintf(cale, sizeof cale, "/dev/dvb/adapter0/frontend%ld", port_tuner);
	fe = open(cale, O_RDWR | O_NONBLOCK);
	if (fe < 0) { linie("EROARE 1 frontend-deschidere"); cod_lucru = 1; goto gata; }
	hf = open(HIFE, O_RDWR | O_NONBLOCK);
	if (hf < 0) { linie("EROARE 1 hife-deschidere"); cod_lucru = 1; goto gata; }
	int feid = (int)port_tuner;
	if (ioctl(hf, HIFE_ALEGE, &feid) < 0) { linie("EROARE %d hife-alege", errno); cod_lucru = 1; goto gata; }

	/* Si2166: firul din nucleu (si2166_blindscan_thread) inmulteste limitele cu 1000, deci cere kSym/s. Cu Sym/s, dupa depasire si
	 * impachetarea pe 16 biti, intervalul cautat iese 16960-18711 kSym/s si scapa transpondere care se prind la acordare directa */
	uint32_t impartitor = strstr(nume_nim, "Si2166") ? 1000u : 1u;
	linie("JURNAL hife-rate %u %u", HIFE_RATA_MIN / impartitor, HIFE_RATA_MAX / impartitor);
	linie("PORNIT %d %llu", nr_treceri, (unsigned long long)khz_total);
	for (int i = 0; i < nr_treceri && !cerere_oprire; i++) {
		Trecere *t = &treceri[i];
		trecere_curenta = i;
		/* LNB-ul: 18 V la H si R, 13 V la V si L; tonul dupa banda */
		ioctl(fe, FE_SET_TONE, t->ton22k ? SEC_TONE_ON : SEC_TONE_OFF);
		ioctl(fe, FE_SET_VOLTAGE, (t->polarizare == 0 || t->polarizare == 3) ? SEC_VOLTAGE_18 : SEC_VOLTAGE_13);
		struct timespec lnb = { 0, 150 * 1000 * 1000 };
		nanosleep(&lnb, NULL);
		linie("TRECERE %d %c %u %u %u", i + 1, t->eticheta, t->ton22k, t->if_start, t->if_stop);
		uint64_t tt = ms_acum();
		uint32_t pas = pas_felie(t);
		for (uint32_t a0 = t->if_start; a0 < t->if_stop && !cerere_oprire; a0 += pas) {
			uint32_t a1 = a0 + pas + SUPRAPUNERE_KHZ;
			if (a1 > t->if_stop || t->if_stop - a1 < FELIE_MIN_KHZ) a1 = t->if_stop;
			HifeParam p = { a0 / 1000u, (a1 + 999u) / 1000u, HIFE_RATA_MIN / impartitor, HIFE_RATA_MAX / impartitor, 0 };
			khz_felie = a1 - a0 > pas ? pas : a1 - a0;
			uint64_t tf = ms_acum();
			int n = -1;
			if (ioctl(hf, HIFE_PORNESTE, &p) < 0) {
				linie("JURNAL hife-pornire %d", errno);
			} else {
				while (!cerere_oprire && ms_acum() - tf < HIFE_FELIE_MS_MAX) {
					n = ioctl(hf, HIFE_CITESTE, 0);
					if (n >= 0) break;
					struct timespec astept = { 0, 50 * 1000 * 1000 };
					nanosleep(&astept, NULL);
					scrie_progres((uint32_t)((ms_acum() - tf) * 100u / 30000u));   /* ~30 s pe felie, estimat */
				}
				if (n < 0) {
					HifeParam z = { 0, 0, 0, 0, 0 };
					ioctl(hf, HIFE_PORNESTE, &z);   /* anuleaza cautarea din nucleu */
				}
			}
			if (n > 0) {
				HifeTp *lista = calloc((size_t)n, sizeof(HifeTp));
				if (lista && ioctl(hf, HIFE_CITESTE, lista) >= 0)
					for (int k = 0; k < n; k++) tp_hife(&lista[k], t);
				free(lista);
			}
			linie("JURNAL felie %u %u stare %d ms %llu", a0, a1, n, (unsigned long long)(ms_acum() - tf));
			khz_facuti += khz_felie;
			khz_felie = 0;
			scrie_progres(0);
			if (a1 >= t->if_stop) break;
		}
		linie("JURNAL trecere %d ms %llu gasite %d", i + 1, (unsigned long long)(ms_acum() - tt), nr_gasite);
	}
	if (!cerere_oprire) { khz_facuti = khz_total; scrie_progres(0); }
gata:
	if (hf >= 0) close(hf);
	if (fe >= 0) close(fe);
	lucru_terminat = 1;
	return NULL;
}

/* ---------------------------------------------------------------- argumente */
static int citeste_trecere(const char *s) {
	if (nr_treceri >= MAX_TRECERI || !s) return -1;
	char pol = 0, rest = 0;
	unsigned ton = 0, a = 0, b = 0;
	if (sscanf(s, "%c,%u,%u,%u%c", &pol, &ton, &a, &b, &rest) != 4) return -1;
	const char *p = pol ? strchr("HVLR", toupper((unsigned char)pol)) : NULL;
	if (!p || ton > 1 || a < IF_MIN_KHZ || b > IF_MAX_KHZ || a >= b) return -1;
	Trecere *t = &treceri[nr_treceri++];
	t->polarizare = (uint32_t)(p - "HVLR");
	t->eticheta = *p;
	t->ton22k = ton;
	t->if_start = a;
	t->if_stop = b;
	return 0;
}

static int zavor_proces(void) {
	int fd = open(ZAVOR_PROCES, O_RDWR | O_CREAT | O_CLOEXEC, 0644);
	if (fd < 0) return -1;
	if (flock(fd, LOCK_EX | LOCK_NB)) { close(fd); return -1; }
	return fd;   /* ramane deschis pana la iesire */
}

int main(int argc, char **argv) {
	int sonda = 0;
	long timp_max = 1200, asteapta_fe = 15;
	const char *cale_lib = NULL;

	for (int i = 1; i < argc; i++) {
		const char *a = argv[i];
		const char *v = (i + 1 < argc) ? argv[i + 1] : NULL;
		long x;
		if (!strcmp(a, "--versiune")) { linie("hds-blindscan %s", HDS_BLINDSCAN_VERSIUNE); return 0; }
		else if (!strcmp(a, "--sonda")) sonda = 1;
		else if (!strcmp(a, "--trecere")) { if (citeste_trecere(v)) { linie("EROARE 2 trecere-gresita"); return 2; } i++; }
		else if (!strcmp(a, "--tuner") && !numar(v, &x) && x >= 0 && x <= 7) { port_tuner = x; i++; }
		else if (!strcmp(a, "--lo-jos") && !numar(v, &x) && x > 0 && x < 30000) { lo_jos_mhz = (uint32_t)x; i++; }
		else if (!strcmp(a, "--lo-sus") && !numar(v, &x) && x > 0 && x < 30000) { lo_sus_mhz = (uint32_t)x; i++; }
		else if (!strcmp(a, "--felie") && !numar(v, &x) && x >= 0 && x <= 1200000) { felie_khz = (uint32_t)x; i++; }
		else if (!strcmp(a, "--timp-max") && !numar(v, &x) && x > 0 && x < 86400) { timp_max = x; i++; }
		else if (!strcmp(a, "--asteapta-frontend") && !numar(v, &x) && x >= 0 && x < 600) { asteapta_fe = x; i++; }
		else if (!strcmp(a, "--lib") && v) { cale_lib = v; i++; }
		else { linie("EROARE 2 argument-gresit"); return 2; }
	}
	if ((lo_jos_mhz < 7500) != (lo_sus_mhz < 7500)) { linie("EROARE 2 lo-amestecat"); return 2; }

	RandProc r;
	placa_aleasa = profil_placa(port_tuner, &r);
	if (r.gasit)
		linie("PROFIL %ld %ld 0x%lx %s 0x%lx 0x%x", r.port, r.i2c, r.adr_demod, r.nume_tuner, r.adr_tuner,
		      placa_aleasa ? placa_aleasa->gpio_reset : 0u);
	if (!placa_aleasa && placa_hife(port_tuner)) {
		mod_hife = 1;
		linie("PROFIL %ld hife %s", port_tuner, nume_nim);
	}

	if (sonda && mod_hife) {
		/* numai citiri: dispozitivul, numele tunerului, cine tine frontend-ul */
		linie("JURNAL frontend-tinut %d", cine_tine_frontend(port_tuner));
		linie("SONDA 0 hife");
		return 0;
	}
	if (sonda) {
		int lib = incarca_biblioteca(cale_lib);
		int tu = citeste_tuner_used();
		int fe = cine_tine_frontend(port_tuner);
		linie("JURNAL tuner-used %d frontend-tinut %d", tu, fe);
		if (!r.gasit)       linie("SONDA 1 proc-tuner-lipsa");
		else if (!placa_aleasa)   linie("SONDA 1 placa-necunoscuta");
		else if (lib == 1)  linie("SONDA 1 biblioteca-lipsa");
		else if (lib == 2)  linie("SONDA 1 simboluri-lipsa");
		else if (tu < 0)    linie("SONDA 1 tuner-used-lipsa");
		else                linie("SONDA 0 gata");
		if (B.lib) dlclose(B.lib);
		return 0;
	}

	if (!nr_treceri) { linie("EROARE 2 fara-treceri"); return 2; }
	if (!mod_hife) {
		if (!r.gasit) { linie("EROARE 1 proc-tuner-lipsa"); return 1; }
		if (!placa_aleasa) { linie("EROARE 1 placa-necunoscuta"); return 1; }
		int lib = incarca_biblioteca(cale_lib);
		if (lib == 1) { linie("EROARE 1 biblioteca-lipsa"); return 1; }
		if (lib == 2) { linie("EROARE 1 simboluri-lipsa"); return 1; }
		if (citeste_tuner_used() < 0) { linie("EROARE 1 tuner-used-lipsa"); return 1; }
	}
	if (zavor_proces() < 0) { linie("EROARE 1 alt-proces"); return 1; }

	/* enigma2 elibereaza frontend-ul la cateva secunde dupa oprirea canalului; peste o inregistrare nu pornim */
	int fe = cine_tine_frontend(port_tuner);
	if (fe) linie("JURNAL asteapta-frontend %d", fe);
	for (long n = 0; fe && n < asteapta_fe * 2; n++) {
		struct timespec ts = { 0, 500 * 1000 * 1000 };
		nanosleep(&ts, NULL);
		fe = cine_tine_frontend(port_tuner);
	}
	if (fe) { linie("EROARE 1 frontend-ocupat"); return 1; }

	for (int i = 0; i < nr_treceri; i++) khz_total += treceri[i].if_stop - treceri[i].if_start;

	sigset_t semnale;
	sigemptyset(&semnale);
	sigaddset(&semnale, SIGTERM);
	sigaddset(&semnale, SIGINT);
	sigaddset(&semnale, SIGHUP);
	sigaddset(&semnale, SIGPIPE);
	pthread_sigmask(SIG_BLOCK, &semnale, NULL);   /* mostenit de firul de lucru */

	uint64_t t0 = ms_acum();
	pthread_t fir;
	if (pthread_create(&fir, NULL, mod_hife ? lucru_hife : lucru, NULL)) { linie("EROARE 1 fir"); return 1; }

	while (!lucru_terminat) {
		struct timespec astept = { 0, 250 * 1000 * 1000 };
		int s = sigtimedwait(&semnale, NULL, &astept);
		if (s == SIGTERM || s == SIGINT || s == SIGHUP || s == SIGPIPE) cerere_oprire = 1;
		uint64_t trecut = ms_acum() - t0;
		if (!cerere_oprire && trecut > (uint64_t)timp_max * 1000u) { cerere_oprire = 1; oprit_de_paznic = 1; }
		if (trecut > ((uint64_t)timp_max + 300u) * 1000u) {
			/* biblioteca nu s-a intors nici dupa marja: tuner_used inapoi si iesim (ioctl-ul in curs se termina
			 * in nucleu inainte ca procesul sa dispara) */
			scrie_tuner_used(0);
			linie("EROARE 4 blocat");
			_exit(4);
		}
	}
	pthread_join(fir, NULL);
	if (cod_lucru) return 1;
	unsigned long long durata = (unsigned long long)(ms_acum() - t0);
	if (B.lib) dlclose(B.lib);
	if (cerere_oprire) {
		if (oprit_de_paznic) linie("JURNAL timp-depasit %ld", timp_max);
		linie("OPRIT %d %llu", nr_gasite, durata);
		return oprit_de_paznic ? 3 : 0;
	}
	linie("GATA %d %llu", nr_gasite, durata);
	return 0;
}
