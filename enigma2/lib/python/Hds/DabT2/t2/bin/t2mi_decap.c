/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * t2mi_decap.c
 * Decapsulator T2-MI: din pachete T2-MI (ETSI TS 102 773) purtate intr-un PID al unui flux TS
 * scoate fluxul TS al unui PLP DVB-T2 (adaptarea de mod din ETSI EN 302 755, clauza 5.1).
 *
 * Facut de hdsatelit.com. Cod propriu, scris dupa standardele ETSI.
 *
 * Cu -A face altceva, mai simplu: fluxurile de distributie spaniole de pe 30W (Abertis/Cellnex) poarta un TS intreg
 * direct in payload-ul unui PID privat, fara T2-MI: payload-urile pachetelor acelui PID, puse cap la cap (dupa antet si
 * campul de adaptare), sunt pachetele TS de 188 de octeti ale multiplexului terestru, cu PAT, PMT si programele lui.
 * Pachetele cu bitii de criptare pusi (flux criptat pe care modulul CAM nu l-a decriptat) se numara si se arunca.
 *
 * Folosire:
 *   t2mi_decap -p PID [-l PLP] [-n] [-s] [-r] [-A] [-i fisier|-] [-o fisier|-] [-u PORT] [-a PREFIX]
 *              [-h URL [-I SEC] [-w SEC] [-R N] [-c FISIER]] [-j FISIER] [-P FISIER]
 *     -p PID   PID-ul care poarta T2-MI (0..8191); nu trebuie cu -r
 *     -A       PID-ul poarta un TS intreg in payload (fara T2-MI); -l, -n si -r nu se folosesc
 *     -l PLP   PLP-ul dorit (0..255); lipsa = primul PLP de date din L1-current
 *     -n       pune la loc pachetele nule sterse (NPD/DNP)
 *     -s       statistici pe stderr la 5 s, JSON pe o linie (ignorat cu -u)
 *     -r       intrarea e un sir de pachete T2-MI lipite, fara antete TS
 *     -i       fisier de intrare (implicit stdin)
 *     -o       fisier de iesire (implicit stdout)
 *     -u PORT  in loc de iesire, serveste HTTP pe 127.0.0.1:PORT, cel mult 8 clienti
 *     -a PREFIX  cu -u: calea acceptata (PREFIX, sau PREFIX urmat de ? . /); restul primeste 404
 *     -h URL   intrarea din HTTP (http://IPv4-sau-localhost:port/cale), cu reconectare si limita de sesiuni
 *     -I SEC   cu -u si -h: conexiunea HTTP se inchide dupa SEC secunde fara clienti (implicit 30)
 *     -w SEC   cu -h: cat se asteapta primele date (implicit 90: streamserverul poate roti antena)
 *     -R N     cu -h: cel mult N conexiuni spre sursa pe 120 s (implicit 4), oricum s-ar fi terminat
 *     -c FISIER  cu -h: un rand pe sesiune "<uptime> <epoch> t2mi_decap" (O_APPEND); la pornire randurile proprii din
 *              ultimele 120 s intra in fereastra si in pauza, ca un binar repornit sa nu ocoleasca limita
 *     -j FISIER  statistici JSON scrise atomic, cel mult o data pe secunda
 *     -P FISIER  pachetele de iesire cu PID 0 si 0x11 (PAT, SDT), cel mult 64 KB pe sesiune
 *
 * Cu -u procesul nu scrie nimic pe descriptorii 1 si 2 (il porneste un releu, cu tevi spre enigma2).
 *
 * Reguli de lucru: buffere fixe (nicio alocare dupa pornire), citiri si scrieri in blocuri mari,
 * resincronizare pe 0x47 si pe antetul T2-MI, orice camp citit din flux se verifica inainte de folosire.
 */

#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/types.h>
#ifdef __linux__
#include <sys/prctl.h>
#endif

#ifndef MSG_NOSIGNAL
#define MSG_NOSIGNAL 0
#endif

#define TS_LEN        188
#define BLOC_CITIRE   (256u * 1024u)        /* o citire */
#define BLOC_IESIRE   (256u * 1024u)        /* bufferul de iesire */
#define PRAG_SCRIERE  (64u * 1024u)         /* scriem cand se aduna atat */
#define T2MI_MAX      (6u + 8192u + 4u)     /* antet + payload_len maxim (65535 biti) + CRC */
#define PERIOADA_STAT_MS  5000

#define MAX_CLIENTI   8
#define COADA_CLIENT  (2u * 1024u * 1024u)  /* date neplecate spre un client HTTP */
#define CERERE_MAX    4096u
#define ANTET_MAX     (16u * 1024u)         /* antetul raspunsului de la sursa HTTP */
#define PSI_MAX       (64u * 1024u)
#define FEREASTRA_MS  120000
#define SOCLU_SURSA   (1024 * 1024)
#define JSON_MAX      16384u

/* ------------------------------------------------------------------ CRC pe tabele */

static uint32_t crc32_t0[256], crc32_t1[256], crc32_t2[256], crc32_t3[256];
static uint8_t crc8_t[256];

static void crc_init(void)
{
    for (uint32_t i = 0; i < 256; i++) {
        uint32_t c = i << 24;
        for (int k = 0; k < 8; k++)
            c = (c & 0x80000000u) ? (c << 1) ^ 0x04C11DB7u : (c << 1);
        crc32_t0[i] = c;

        uint8_t b = (uint8_t)i;
        for (int k = 0; k < 8; k++)
            b = (uint8_t)((b & 0x80) ? (uint8_t)(b << 1) ^ 0xD5 : (uint8_t)(b << 1));
        crc8_t[i] = b;
    }
    for (uint32_t i = 0; i < 256; i++) {
        crc32_t1[i] = (crc32_t0[i] << 8) ^ crc32_t0[crc32_t0[i] >> 24];
        crc32_t2[i] = (crc32_t1[i] << 8) ^ crc32_t0[crc32_t1[i] >> 24];
        crc32_t3[i] = (crc32_t2[i] << 8) ^ crc32_t0[crc32_t2[i] >> 24];
    }
}

/* CRC-32 MPEG-2: polinom 0x04C11DB7, pornire 0xFFFFFFFF, MSB intai, fara XOR la final.
 * Peste date + CRC-ul lor rezultatul e 0. */
static uint32_t crc32_mpeg(const uint8_t *p, size_t n)
{
    uint32_t c = 0xFFFFFFFFu;
    while (n >= 4) {
        c ^= ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) | ((uint32_t)p[2] << 8) | p[3];
        c = crc32_t3[c >> 24] ^ crc32_t2[(c >> 16) & 0xFF] ^ crc32_t1[(c >> 8) & 0xFF] ^ crc32_t0[c & 0xFF];
        p += 4;
        n -= 4;
    }
    while (n--)
        c = (c << 8) ^ crc32_t0[((c >> 24) ^ *p++) & 0xFF];
    return c;
}

/* CRC-8 din EN 302 755 anexa F: 1+x^2+x^4+x^6+x^7+x^8, pornire 0 */
static uint8_t crc8_cont(uint8_t c, const uint8_t *p, size_t n)
{
    while (n--)
        c = crc8_t[c ^ *p++];
    return c;
}

/* ------------------------------------------------------------------ stare */

typedef struct {
    uint64_t ts_in, ts_pid, ts_tei, ts_cc, ts_dublu, ts_af_rau, ts_resinc, ts_pointer_rau;
    uint64_t t2_bune, t2_rele, t2_lipsa, t2_resinc;
    uint64_t bb, bb_crc, bb_rele, bb_ne_ts, up_crc, up_sinc;
    uint64_t l1, l1_rele, l1_lipsa, comun, t2_alt_flux, ts_criptate;
    uint64_t iesite, nule, aruncate;
    uint64_t ab_resinc;   /* -A: pierderi de sincronizare in TS-ul interior */
    int mod; /* -1 necunoscut, 0 NM, 1 HEM */
} Statistici;

static Statistici st;

typedef struct {
    uint8_t part[256];     /* bucata de UP inceputa intr-un cadru anterior */
    uint16_t part_len;
    uint16_t unit;         /* lungimea unui UP transmis, in octeti */
    uint8_t hem, npd, issy;
    uint8_t are_crc;       /* NM: avem CRC-8 asteptat de la UP-ul anterior */
    uint8_t crc_a, crc_b;  /* NM: CRC-8 peste 187 octeti, respectiv peste tot UP-ul fara CRC */
    uint8_t in_l1, tip, sarcina, grup;
} Plp;

static Plp plp[256];
static uint8_t plp_vazut[256];      /* id-uri vazute in cadre BB */
static uint8_t l1_ids[256];
static int l1_n = -1;               /* -1 = inca nu am primit L1-current */

static int opt_pid = -1, opt_plp = -1, opt_nule = 0, opt_stat = 0, opt_brut = 0, opt_port = -1;
static int opt_ts_in_pid = 0;        /* -A */
static int plp_date = -1, plp_comun = -1;

static volatile sig_atomic_t opreste = 0;

/* ------------------------------------------------------------------ iesire */

static uint8_t iesire[BLOC_IESIRE];
static size_t iesire_len;
static int fd_out = 1;
static int iesire_moarta = 0;
static int tacut = 0;               /* cu -u: nimic pe descriptorii 1 si 2 */

/* clientii HTTP (-u): locuri fixe, fiecare cu o coada inel de COADA_CLIENT octeti */
typedef struct {
    int fd;
    int stare;                      /* 0 liber, 1 citim cererea, 2 flux */
    int64_t de_la;
    size_t cerere_len;
    size_t cap, len;                /* coada: primul octet la 'cap', 'len' octeti */
    char cerere[CERERE_MAX];
} Client;

static int fd_asculta = -1;
static Client clienti[MAX_CLIENTI];
static uint8_t coada_client[MAX_CLIENTI][COADA_CLIENT];
static uint64_t cl_aruncati, cl_total, oct_trimisi;
static const char *opt_prefix = NULL;

/* -P: copia pachetelor PSI de iesire */
static int psi_fd = -1;
static size_t psi_scrise;

/* pachet nul (PID 0x1FFF), completat la pornire */
static uint8_t pachet_nul[TS_LEN];

static int64_t acum_ms(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (int64_t)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}

/* mesaje pe stderr doar in afara modului releu */
static void eroare(const char *fmt, ...)
{
    char s[512];
    va_list a;
    if (tacut)
        return;
    va_start(a, fmt);
    int n = vsnprintf(s, sizeof(s), fmt, a);
    va_end(a);
    if (n > 0) {
        ssize_t w = write(2, s, (size_t)n < sizeof(s) ? (size_t)n : sizeof(s) - 1);
        (void)w;
    }
}

static void psi_trunchiaza(void)
{
    if (psi_fd < 0)
        return;
    if (ftruncate(psi_fd, 0) == 0)
        psi_scrise = 0;
}

static void psi_cauta(const uint8_t *p, size_t n)
{
    for (size_t i = 0; i + TS_LEN <= n; i += TS_LEN) {
        unsigned pid = ((unsigned)(p[i + 1] & 0x1F) << 8) | p[i + 2];
        if (pid != 0 && pid != 0x11)
            continue;
        if (psi_scrise + TS_LEN > PSI_MAX)
            return;
        if (write(psi_fd, p + i, TS_LEN) != (ssize_t)TS_LEN)
            return;
        psi_scrise += TS_LEN;
    }
}

static void client_inchide(Client *c)
{
    if (c->fd >= 0)
        close(c->fd);
    c->fd = -1;
    c->stare = 0;
    c->cerere_len = 0;
    c->cap = 0;
    c->len = 0;
}

static int clienti_flux(void)
{
    int k = 0;
    for (int i = 0; i < MAX_CLIENTI; i++)
        k += clienti[i].stare == 2;
    return k;
}

/* trimite din coada cat primeste soclul; -1 = clientul a cazut */
static int client_goleste_coada(Client *c)
{
    const uint8_t *q = coada_client[c - clienti];
    while (c->len > 0) {
        size_t seg = COADA_CLIENT - c->cap;
        if (seg > c->len)
            seg = c->len;
        ssize_t w = send(c->fd, q + c->cap, seg, MSG_NOSIGNAL);
        if (w > 0) {
            oct_trimisi += (uint64_t)w;
            c->cap = (c->cap + (size_t)w) % COADA_CLIENT;
            c->len -= (size_t)w;
            if (c->len == 0)
                c->cap = 0;
        } else if (w < 0 && errno == EINTR) {
            continue;
        } else if (w < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
            return 0;
        } else {
            return -1;
        }
    }
    return 0;
}

/* un bloc spre un client: direct daca nu asteapta nimic, restul in coada; coada plina = clientul e aruncat */
static void client_trimite(Client *c, const uint8_t *p, size_t n)
{
    if (c->len > 0 && client_goleste_coada(c) < 0) {
        client_inchide(c);
        return;
    }
    if (c->len == 0) {
        while (n > 0) {
            ssize_t w = send(c->fd, p, n, MSG_NOSIGNAL);
            if (w > 0) {
                oct_trimisi += (uint64_t)w;
                p += w;
                n -= (size_t)w;
            } else if (w < 0 && errno == EINTR) {
                continue;
            } else if (w < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
                break;
            } else {
                client_inchide(c);
                return;
            }
        }
    }
    if (n == 0)
        return;
    if (c->len + n > COADA_CLIENT) {
        cl_aruncati++;
        client_inchide(c);
        return;
    }
    uint8_t *q = coada_client[c - clienti];
    size_t coada = (c->cap + c->len) % COADA_CLIENT;
    size_t seg = COADA_CLIENT - coada;
    if (seg > n)
        seg = n;
    memcpy(q + coada, p, seg);
    if (n > seg)
        memcpy(q, p + seg, n - seg);
    c->len += n;
}

static void goleste(void)
{
    if (iesire_len == 0)
        return;
    if (psi_fd >= 0 && psi_scrise + TS_LEN <= PSI_MAX)
        psi_cauta(iesire, iesire_len);
    if (opt_port >= 0) {
        int k = 0;
        for (int i = 0; i < MAX_CLIENTI; i++) {
            if (clienti[i].stare == 2) {
                client_trimite(&clienti[i], iesire, iesire_len);
                k++;
            }
        }
        if (k == 0)
            st.aruncate += iesire_len / TS_LEN;
    } else if (!iesire_moarta) {
        const uint8_t *p = iesire;
        size_t n = iesire_len;
        while (n > 0) {
            ssize_t w = write(fd_out, p, n);
            if (w > 0) {
                p += w;
                n -= (size_t)w;
            } else if (w < 0 && errno == EINTR) {
                continue;
            } else if (w < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
                struct pollfd pf = { fd_out, POLLOUT, 0 };
                poll(&pf, 1, 1000);
            } else {
                iesire_moarta = 1; /* cititorul a plecat */
                opreste = 1;
                break;
            }
        }
    }
    iesire_len = 0;
}

static inline void emite_up(const uint8_t *p187)
{
    if (iesire_len + TS_LEN > sizeof(iesire))
        goleste();
    iesire[iesire_len] = 0x47;
    memcpy(iesire + iesire_len + 1, p187, 187);
    iesire_len += TS_LEN;
    st.iesite++;
}

static void emite_nule(unsigned k)
{
    while (k--) {
        if (iesire_len + TS_LEN > sizeof(iesire))
            goleste();
        memcpy(iesire + iesire_len, pachet_nul, TS_LEN);
        iesire_len += TS_LEN;
        st.nule++;
    }
}

/* ------------------------------------------------------------------ adaptarea de mod (BB -> TS) */

static void plp_reset(Plp *P)
{
    P->part_len = 0;
    P->are_crc = 0;
}

static void reset_toate(void)
{
    if (plp_date >= 0)
        plp_reset(&plp[plp_date]);
    if (plp_comun >= 0)
        plp_reset(&plp[plp_comun]);
}

static inline int plp_activ(int id)
{
    return id == plp_date || id == plp_comun;
}

/* Coada PLP-ului comun (EN 302 755 anexa D): cu -n, pachetele comune iau locul nulelor puse la loc in
 * PLP-ul de date; nu tinem mai mult de COADA_MAX, cele mai vechi ies direct. */
#define COADA_MAX 256u
static uint8_t coada[COADA_MAX * TS_LEN];
static unsigned coada_cap, coada_n;

static void schimba_alegerea(int date, int comun)
{
    if (date == comun)
        comun = -1;
    if (date != plp_date)
        psi_trunchiaza();          /* alt PLP = alt flux TS: PSI-ul vechi nu mai e valabil */
    if (date != plp_date && date >= 0)
        plp_reset(&plp[date]);
    if (comun != plp_comun) {
        if (comun >= 0)
            plp_reset(&plp[comun]);
        coada_cap = 0;
        coada_n = 0;
    }
    plp_date = date;
    plp_comun = comun;
}

static void emite_188(const uint8_t *p)
{
    if (iesire_len + TS_LEN > sizeof(iesire))
        goleste();
    memcpy(iesire + iesire_len, p, TS_LEN);
    iesire_len += TS_LEN;
    st.iesite++;
}

static void coada_pune(const uint8_t *p187)
{
    if (coada_n == COADA_MAX) {
        emite_188(coada + (size_t)coada_cap * TS_LEN);
        st.comun++;
        coada_cap = (coada_cap + 1) % COADA_MAX;
        coada_n--;
    }
    uint8_t *d = coada + (size_t)((coada_cap + coada_n) % COADA_MAX) * TS_LEN;
    d[0] = 0x47;
    memcpy(d + 1, p187, 187);
    coada_n++;
}

/* un UP intreg de P->unit octeti */
static void up_complet(Plp *P, const uint8_t *u)
{
    const uint8_t *sarcina;
    unsigned dnp = 0;
    int e_comun = (int)(P - plp) == plp_comun;

    if (P->hem) {
        sarcina = u;
        if (P->npd)
            dnp = u[187];
    } else {
        /* NM: [CRC-8 al UP-ului anterior][187 octeti][ISSY 0/2/3][DNP 0/1] */
        sarcina = u + 1;
        if (P->are_crc && u[0] != P->crc_a && u[0] != P->crc_b)
            st.up_crc++;
        uint8_t c = crc8_cont(0, sarcina, 187);
        P->crc_a = c;
        P->crc_b = crc8_cont(c, u + 188, (size_t)P->unit - 188);
        P->are_crc = 1;
        if (P->npd)
            dnp = u[P->unit - 1];
    }
    if (e_comun) {
        /* nulele PLP-ului comun nu intra in iesire; locul lor il tin nulele PLP-ului de date */
        if ((sarcina[0] & 0x1F) == 0x1F && sarcina[1] == 0xFF)
            return;
        if (opt_nule) {
            coada_pune(sarcina);
        } else {
            emite_up(sarcina);
            st.comun++;
        }
        return;
    }
    /* DNP spune cate nule s-au sters inaintea acestui UP */
    if (opt_nule && dnp) {
        while (dnp && coada_n) {
            emite_188(coada + (size_t)coada_cap * TS_LEN);
            st.comun++;
            coada_cap = (coada_cap + 1) % COADA_MAX;
            coada_n--;
            dnp--;
        }
        emite_nule(dnp);
    }
    emite_up(sarcina);
}

static void cadru_bb_plp(const uint8_t *pl, size_t n);

/* Fara -l: cadrele BB se tin pana vine L1-current, ca sa nu pierdem inceputul fluxului */
#define ASTEAPTA_CADRE  512u
#define ASTEAPTA_OCTETI (512u * 6733u)
static uint8_t asteapta_buf[ASTEAPTA_OCTETI];
static uint32_t asteapta_poz[ASTEAPTA_CADRE], asteapta_lung[ASTEAPTA_CADRE];
static unsigned asteapta_n;
static size_t asteapta_folosit;

static void asteapta_goleste(void)
{
    unsigned k = asteapta_n;
    asteapta_n = 0;
    for (unsigned i = 0; i < k; i++)
        cadru_bb_plp(asteapta_buf + asteapta_poz[i], asteapta_lung[i]);
    asteapta_folosit = 0;
}

static void cadru_bb(const uint8_t *pl, size_t n)
{
    st.bb++;
    if (n < 3 + 10) {
        st.bb_rele++;
        return;
    }
    plp_vazut[pl[1]] = 1;
    if (plp_date < 0) {
        if (asteapta_n < ASTEAPTA_CADRE && asteapta_folosit + n <= sizeof(asteapta_buf)) {
            memcpy(asteapta_buf + asteapta_folosit, pl, n);
            asteapta_poz[asteapta_n] = (uint32_t)asteapta_folosit;
            asteapta_lung[asteapta_n] = (uint32_t)n;
            asteapta_n++;
            asteapta_folosit += n;
            return;
        }
        /* L1-current nu vine: luam PLP-ul primului cadru tinut */
        st.l1_lipsa++;
        schimba_alegerea(asteapta_n ? asteapta_buf[asteapta_poz[0] + 1] : pl[1], -1);
        asteapta_goleste();
    }
    cadru_bb_plp(pl, n);
}

static void cadru_bb_plp(const uint8_t *pl, size_t n)
{
    unsigned id = pl[1];
    if (!plp_activ((int)id))
        return;

    Plp *P = &plp[id];
    const uint8_t *h = pl + 3;
    uint8_t mod = crc8_cont(0, h, 9) ^ h[9];
    if (mod > 1) {
        st.bb_crc++;
        plp_reset(P);
        return;
    }
    if ((h[0] >> 6) != 3) {
        st.bb_ne_ts++;
        plp_reset(P);
        return;
    }
    unsigned issyi = (h[0] >> 3) & 1;
    unsigned npd = (h[0] >> 2) & 1;
    unsigned upl = ((unsigned)h[2] << 8) | h[3];
    unsigned dfl = ((unsigned)h[4] << 8) | h[5];
    unsigned syncd = ((unsigned)h[7] << 8) | h[8];

    if ((dfl & 7) || 13 + (size_t)(dfl / 8) > n || (syncd != 0xFFFF && ((syncd & 7) || syncd > dfl))) {
        st.bb_rele++;
        plp_reset(P);
        return;
    }
    unsigned unit, issy = 0;
    if (mod == 1) {
        unit = 187 + npd;
    } else {
        if (upl & 7) {
            st.bb_rele++;
            plp_reset(P);
            return;
        }
        unit = upl / 8;
        if (unit < 188 + npd) {
            st.bb_rele++;
            plp_reset(P);
            return;
        }
        issy = unit - 188 - npd;
        if ((issyi && issy != 2 && issy != 3) || (!issyi && issy != 0)) {
            st.bb_rele++;
            plp_reset(P);
            return;
        }
    }
    if ((int)id == plp_date)
        st.mod = mod;
    if (P->unit != unit || P->hem != mod || P->npd != npd) {
        plp_reset(P);
        P->unit = (uint16_t)unit;
        P->hem = mod;
        P->npd = (uint8_t)npd;
        P->issy = (uint8_t)issy;
    }

    const uint8_t *d = h + 10;
    size_t len = dfl / 8;

    if (syncd == 0xFFFF) {
        /* niciun UP nu incepe aici: totul continua UP-ul inceput */
        if (P->part_len == 0)
            return;
        size_t lipsa = unit - P->part_len;
        if (len < lipsa) {
            memcpy(P->part + P->part_len, d, len);
            P->part_len = (uint16_t)(P->part_len + len);
        } else if (len == lipsa) {
            memcpy(P->part + P->part_len, d, len);
            up_complet(P, P->part);
            P->part_len = 0;
        } else {
            st.up_sinc++;
            plp_reset(P);
        }
        return;
    }

    size_t cont = syncd / 8;
    if (P->part_len > 0) {
        if (P->part_len + cont == unit) {
            memcpy(P->part + P->part_len, d, cont);
            up_complet(P, P->part);
        } else {
            st.up_sinc++;
            P->are_crc = 0;
        }
        P->part_len = 0;
    } else if (cont > 0) {
        P->are_crc = 0; /* inceputul acestui UP s-a pierdut */
    }
    d += cont;
    len -= cont;
    while (len >= unit) {
        up_complet(P, d);
        d += unit;
        len -= unit;
    }
    if (len > 0) {
        memcpy(P->part, d, len);
        P->part_len = (uint16_t)len;
    }
}

/* ------------------------------------------------------------------ L1-current (lista PLP) */

static uint32_t biti(const uint8_t *p, size_t poz, unsigned n)
{
    uint32_t v = 0;
    for (unsigned i = 0; i < n; i++, poz++)
        v = (v << 1) | ((p[poz >> 3] >> (7 - (poz & 7))) & 1u);
    return v;
}

static void l1_curent(const uint8_t *pl, size_t n)
{
    /* frame_idx 8, freq_source 2 + rfu 6, L1PRE 168 biti, L1CONF_LEN 16, L1CONF ... */
    if (n < 2 + 21 + 2) {
        st.l1_rele++;
        return;
    }
    const uint8_t *pre = pl + 2;
    unsigned s2 = pre[1] & 0x0F;
    unsigned num_rf = biti(pre, 152, 3);
    size_t conf_biti = ((size_t)pl[23] << 8) | pl[24];
    size_t conf_oct = (conf_biti + 7) / 8;
    if (25 + conf_oct > n) {
        st.l1_rele++;
        return;
    }
    const uint8_t *c = pl + 25;
    if (conf_biti < 35) {
        st.l1_rele++;
        return;
    }
    unsigned num_plp = biti(c, 15, 8);
    size_t poz = 35 + (size_t)num_rf * 35 + ((s2 & 1) ? 34 : 0);
    if (poz + (size_t)num_plp * 89 > conf_biti || num_plp == 0) {
        st.l1_rele++;
        return;
    }
    st.l1++;

    for (int i = 0; i < l1_n; i++)
        plp[l1_ids[i]].in_l1 = 0;
    l1_n = 0;
    int prim_ts = -1, prim_date = -1;
    for (unsigned i = 0; i < num_plp; i++, poz += 89) {
        unsigned id = biti(c, poz, 8);
        Plp *P = &plp[id];
        if (P->in_l1)
            continue; /* id repetat: il pastram pe primul */
        P->in_l1 = 1;
        P->tip = (uint8_t)biti(c, poz + 8, 3);
        P->sarcina = (uint8_t)biti(c, poz + 11, 5);
        P->grup = (uint8_t)biti(c, poz + 28, 8);
        l1_ids[l1_n++] = (uint8_t)id;
        if (P->tip == 1 || P->tip == 2) {
            if (prim_date < 0)
                prim_date = (int)id;
            if (prim_ts < 0 && P->sarcina == 3)
                prim_ts = (int)id;
        }
    }

    int date = opt_plp;
    if (date < 0)
        date = prim_ts >= 0 ? prim_ts : prim_date;
    if (date < 0)
        date = l1_ids[0];
    int comun = -1;
    if (plp[date].in_l1) {
        for (int i = 0; i < l1_n; i++) {
            Plp *P = &plp[l1_ids[i]];
            if (P->tip == 0 && P->grup == plp[date].grup && l1_ids[i] != date) {
                comun = l1_ids[i];
                break;
            }
        }
    }
    if (date != plp_date || comun != plp_comun)
        schimba_alegerea(date, comun);
    if (asteapta_n)
        asteapta_goleste();
}

/* ------------------------------------------------------------------ pachete T2-MI */

static int t2_are_contor = 0;
static uint8_t t2_contor;

static inline int tip_cunoscut(uint8_t t)
{
    switch (t) {
    case 0x00: case 0x01: case 0x02:
    case 0x10: case 0x11: case 0x12:
    case 0x20: case 0x21:
    case 0x30: case 0x31: case 0x32: case 0x33:
        return 1;
    default:
        return 0;
    }
}

static inline size_t t2_lungime(const uint8_t *h)
{
    size_t biti_sarcina = ((size_t)h[4] << 8) | h[5];
    return 6 + (biti_sarcina + 7) / 8 + 4;
}

/* pachet T2-MI intreg, cu CRC deja verificat */
static int t2_flux = -1; /* t2mi_stream_id: il pastram pe primul vazut */

static void t2_pachet(const uint8_t *p, size_t total)
{
    int flux = p[3] & 0x07;
    if (t2_flux < 0) {
        t2_flux = flux;
    } else if (flux != t2_flux) {
        st.t2_alt_flux++;
        return;
    }
    st.t2_bune++;
    if (t2_are_contor && p[1] != (uint8_t)(t2_contor + 1)) {
        st.t2_lipsa++;
        reset_toate();
    }
    t2_contor = p[1];
    t2_are_contor = 1;

    size_t n = total - 10;
    const uint8_t *pl = p + 6;
    switch (p[0]) {
    case 0x00:
        cadru_bb(pl, n);
        break;
    case 0x10:
        l1_curent(pl, n);
        break;
    default:
        break;
    }
}

/* pachet stricat sau taiat; pierderea reala se vede din salt de packet_count la urmatorul pachet bun */
static void t2_pierdut(void)
{
    st.t2_rele++;
}

/* ------------------------------------------------------------------ intrare TS */

static uint8_t asm[T2MI_MAX];
static size_t asm_len, asm_total;
static int asm_sinc = 0;

static int cc_are = 0;
static unsigned cc_ultim;
static uint8_t ts_ultim[TS_LEN];

/* adauga octeti la pachetul T2-MI in lucru; pachetele urmeaza unul dupa altul */
static void asm_date(const uint8_t *d, size_t n)
{
    while (n > 0 && asm_sinc) {
        if (asm_len < 6) {
            size_t k = 6 - asm_len;
            if (k > n)
                k = n;
            memcpy(asm + asm_len, d, k);
            asm_len += k;
            d += k;
            n -= k;
            if (asm_len < 6)
                return;
            /* in TS nu cerem tip cunoscut: decide CRC-ul, iar pointerul de la PUSI repara lungimile gresite */
            asm_total = t2_lungime(asm);
        }
        size_t k = asm_total - asm_len;
        if (k > n)
            k = n;
        memcpy(asm + asm_len, d, k);
        asm_len += k;
        d += k;
        n -= k;
        if (asm_len == asm_total) {
            if (crc32_mpeg(asm, asm_total) == 0)
                t2_pachet(asm, asm_total);
            else
                t2_pierdut();
            asm_len = 0;
        }
    }
}

static void ts_pachet(const uint8_t *p)
{
    st.ts_in++;
    unsigned pid = ((unsigned)(p[1] & 0x1F) << 8) | p[2];
    if ((int)pid != opt_pid)
        return;
    st.ts_pid++;
    if (p[1] & 0x80) {
        st.ts_tei++;
        cc_are = 0;
        if (asm_len > 0)
            t2_pierdut();
        asm_sinc = 0;
        asm_len = 0;
        return;
    }
    unsigned afc = (p[3] >> 4) & 3;
    unsigned cc = p[3] & 0x0F;
    size_t off = 4;
    int disc = 0;
    if ((p[3] & 0xC0) || afc == 0) {
        if (p[3] & 0xC0)
            st.ts_criptate++;
        else
            st.ts_af_rau++;
        if (asm_len > 0)
            t2_pierdut();
        asm_sinc = 0;
        asm_len = 0;
        return;
    }
    if (afc & 2) {
        unsigned afl = p[4];
        if ((afc == 3 && afl > 182) || (afc == 2 && afl != 183)) {
            st.ts_af_rau++;
            if (afc == 3) {
                cc_are = 0;
                if (asm_len > 0)
                    t2_pierdut();
                asm_sinc = 0;
                asm_len = 0;
            }
            return;
        }
        if (afl > 0 && (p[5] & 0x80))
            disc = 1;
        off = 5 + afl;
    }
    if (!(afc & 1))
        return;

    if (cc_are && !disc) {
        int pierdere = 0;
        if (cc == cc_ultim) {
            /* un duplicat identic e voie (ISO 13818-1); altfel e o pierdere */
            if (memcmp(p, ts_ultim, TS_LEN) == 0) {
                st.ts_dublu++;
                return;
            }
            pierdere = 1;
        } else if (cc != ((cc_ultim + 1) & 0x0F)) {
            pierdere = 1;
        }
        if (pierdere) {
            st.ts_cc++;
            if (asm_len > 0)
                t2_pierdut();
            asm_sinc = 0;
            asm_len = 0;
        }
    }
    cc_ultim = cc;
    cc_are = 1;
    memcpy(ts_ultim, p, TS_LEN);

    const uint8_t *d = p + off;
    size_t n = TS_LEN - off;
    if (p[1] & 0x40) {
        if (n == 0) {
            st.ts_pointer_rau++;
            asm_sinc = 0;
            asm_len = 0;
            return;
        }
        unsigned ptr = d[0];
        d++;
        n--;
        if (ptr >= n) {
            st.ts_pointer_rau++;
            if (asm_len > 0)
                t2_pierdut();
            asm_sinc = 0;
            asm_len = 0;
            return;
        }
        if (asm_sinc && asm_len > 0) {
            asm_date(d, ptr);
            if (asm_len != 0) {
                /* pachetul inceput nu se termina unde arata pointerul */
                st.ts_pointer_rau++;
                t2_pierdut();
            }
        }
        asm_sinc = 1;
        asm_len = 0;
        d += ptr;
        n -= ptr;
    }
    if (asm_sinc)
        asm_date(d, n);
}

/* ------------------------------------------------------------------ -A: TS intreg in payload-ul unui PID */

/* payload-urile puse cap la cap; dupa fiecare apel raman cel mult 188 de octeti (un pachet inceput sau o cautare), plus
 * cel mult 184 noi */
#define AB_MAX (4u * TS_LEN)
static uint8_t ab[AB_MAX];
static size_t ab_len;
static int ab_sinc = 0;

static void ab_pierdut(void)
{
    if (ab_sinc)
        st.ab_resinc++;
    ab_len = 0;
    ab_sinc = 0;
}

static void ab_date(const uint8_t *d, size_t n)
{
    if (ab_len + n > AB_MAX) {     /* nu se poate (vezi AB_MAX); daca totusi, o luam de la capat */
        ab_pierdut();
        if (n > AB_MAX)
            return;
    }
    memcpy(ab + ab_len, d, n);
    ab_len += n;
    size_t i = 0;
    for (;;) {
        if (ab_sinc) {
            if (ab_len - i < TS_LEN)
                break;
            if (ab[i] == 0x47) {
                emite_188(ab + i);
                i += TS_LEN;
                continue;
            }
            ab_sinc = 0;
            st.ab_resinc++;
        }
        /* cautare: 0x47 urmat de 0x47 dupa 188 de octeti */
        const uint8_t *q = memchr(ab + i, 0x47, ab_len - i);
        if (!q) {
            i = ab_len;
            break;
        }
        i = (size_t)(q - ab);
        if (ab_len - i < TS_LEN + 1)
            break;                 /* asteptam inca un payload */
        if (ab[i + TS_LEN] == 0x47) {
            ab_sinc = 1;
            continue;
        }
        i++;
    }
    if (i > 0) {
        memmove(ab, ab + i, ab_len - i);
        ab_len -= i;
    }
}

static void ts_pachet_in_pid(const uint8_t *p)
{
    st.ts_in++;
    unsigned pid = ((unsigned)(p[1] & 0x1F) << 8) | p[2];
    if ((int)pid != opt_pid)
        return;
    st.ts_pid++;
    if (p[1] & 0x80) {
        st.ts_tei++;
        cc_are = 0;
        ab_pierdut();
        return;
    }
    unsigned afc = (p[3] >> 4) & 3;
    unsigned cc = p[3] & 0x0F;
    size_t off = 4;
    int disc = 0;
    if (p[3] & 0xC0) {
        st.ts_criptate++;
        cc_are = 0;
        ab_pierdut();
        return;
    }
    if (afc == 0) {
        st.ts_af_rau++;
        ab_pierdut();
        return;
    }
    if (afc & 2) {
        unsigned afl = p[4];
        if ((afc == 3 && afl > 182) || (afc == 2 && afl != 183)) {
            st.ts_af_rau++;
            if (afc == 3) {
                cc_are = 0;
                ab_pierdut();
            }
            return;
        }
        if (afl > 0 && (p[5] & 0x80))
            disc = 1;
        off = 5 + afl;
    }
    if (!(afc & 1))
        return;
    if (cc_are && !disc) {
        if (cc == cc_ultim) {
            if (memcmp(p, ts_ultim, TS_LEN) == 0) {
                st.ts_dublu++;
                return;
            }
            st.ts_cc++;
            ab_pierdut();
        } else if (cc != ((cc_ultim + 1) & 0x0F)) {
            st.ts_cc++;
            ab_pierdut();
        }
    }
    cc_ultim = cc;
    cc_are = 1;
    memcpy(ts_ultim, p, TS_LEN);
    ab_date(p + off, TS_LEN - off);
}

static uint8_t intrare[BLOC_CITIRE + T2MI_MAX + 3 * TS_LEN];
static size_t intrare_len;
static int ts_sinc = 0;

static void proceseaza_ts(int la_sfarsit)
{
    const uint8_t *b = intrare;
    size_t len = intrare_len, i = 0;
    while (len - i >= TS_LEN) {
        if (ts_sinc) {
            if (b[i] == 0x47) {
                if (opt_ts_in_pid)
                    ts_pachet_in_pid(b + i);
                else
                    ts_pachet(b + i);
                i += TS_LEN;
                continue;
            }
            ts_sinc = 0;
            st.ts_resinc++;
        }
        /* cautam 0x47 repetat la 188 octeti */
        if (b[i] != 0x47) {
            const uint8_t *q = memchr(b + i + 1, 0x47, len - i - 1);
            i = q ? (size_t)(q - b) : len;
            continue;
        }
        if (len - i >= 3 * TS_LEN) {
            if (b[i + TS_LEN] == 0x47 && b[i + 2 * TS_LEN] == 0x47) {
                ts_sinc = 1;
                continue;
            }
            i++;
            continue;
        }
        if (la_sfarsit) {
            if (len - i >= 2 * TS_LEN ? b[i + TS_LEN] == 0x47 : 1) {
                ts_sinc = 1;
                continue;
            }
            i++;
            continue;
        }
        break; /* asteptam date */
    }
    if (i > 0) {
        memmove(intrare, intrare + i, len - i);
        intrare_len = len - i;
    }
}

/* ------------------------------------------------------------------ intrare T2-MI lipit (fara TS) */

static int brut_sinc = 0;

static void proceseaza_brut(int la_sfarsit)
{
    const uint8_t *b = intrare;
    size_t len = intrare_len, i = 0;
    while (len - i >= 6) {
        const uint8_t *p = b + i;
        /* cand cautam: tip cunoscut, bitii rfu din antet 0, lungime nenula, apoi CRC-32.
         * Cand suntem sincronizati decide doar CRC-ul, ca un pachet de tip rezervat sa nu lase
         * o gaura in packet_count. */
        if (!brut_sinc && (!tip_cunoscut(p[0]) || (p[2] & 0x0F) || (p[3] & 0xF8) || (p[4] | p[5]) == 0)) {
            if (brut_sinc) {
                brut_sinc = 0;
                st.t2_resinc++;
                t2_pierdut();
            }
            i++;
            continue;
        }
        size_t total = t2_lungime(p);
        if (len - i < total) {
            if (!la_sfarsit)
                break;
            i++;
            continue;
        }
        if (crc32_mpeg(p, total) == 0) {
            brut_sinc = 1;
            t2_pachet(p, total);
            i += total;
        } else {
            if (brut_sinc) {
                brut_sinc = 0;
                st.t2_resinc++;
                t2_pierdut();
            }
            i++;
        }
    }
    if (i > 0) {
        memmove(intrare, intrare + i, len - i);
        intrare_len = len - i;
    }
    if (la_sfarsit)
        intrare_len = 0;
}

/* ------------------------------------------------------------------ resetare intre sesiuni */

/* starea decapsulatorului ca la pornire; contoarele raman */
static void decap_reset(void)
{
    intrare_len = 0;
    ts_sinc = 0;
    brut_sinc = 0;
    asm_len = 0;
    asm_total = 0;
    asm_sinc = 0;
    cc_are = 0;
    ab_len = 0;
    ab_sinc = 0;
    t2_flux = -1;
    t2_are_contor = 0;
    memset(plp, 0, sizeof(plp));
    memset(plp_vazut, 0, sizeof(plp_vazut));
    l1_n = -1;
    plp_date = opt_plp;
    plp_comun = -1;
    coada_cap = 0;
    coada_n = 0;
    asteapta_n = 0;
    asteapta_folosit = 0;
    st.mod = -1;
}

static void proceseaza(int la_sfarsit)
{
    if (opt_brut)
        proceseaza_brut(la_sfarsit);
    else
        proceseaza_ts(la_sfarsit);
}

/* ------------------------------------------------------------------ intrare HTTP (-h) */

enum { H_ASTEAPTA_CLIENT, H_CONECTARE, H_ASTEPT_DATE, H_DATE, H_PAUZA, H_LIMITA };
static const char *const h_nume[] = { "asteapta_client", "conectare", "astept_date", "date", "pauza", "limita" };

static const char *opt_url = NULL, *opt_j = NULL, *opt_c = NULL, *opt_psi = NULL;
static long opt_inactiv = 30, opt_termen = 90, opt_sesiuni = 4;

static int h_stare = H_ASTEAPTA_CLIENT;
static int h_fd = -1;
static struct sockaddr_in h_adresa;
static char h_gazda[64];
static char h_cale[1024];
static int h_antet_gata;
static int h_pauza_idx;
static int64_t h_de_la, h_prima_data, h_ultima_data, h_pauza_pana;
static int64_t h_ultim_client = -1;         /* ultimul moment cu un client in flux (-u) */
static uint64_t oct_intrare, h_sesiuni, h_conectari, h_ocupat;
static uint64_t h_iesite_la_inceput;        /* st.iesite la inceputul datelor: sesiunea a dat pachete TS? */
static int64_t h_fereastra[64];             /* momentele conexiunilor din ultimele 120 s, in ordine */
static uint8_t h_fereastra_ses[64];         /* 1 = conexiunea a fost sesiune (antet 200 fara 400 in corp) */
static int h_fereastra_n;

/* Pauza dupa o conexiune terminata, cu indice crescut la fiecare esec si pus la 0 doar dupa date bune.
 * Dupa o sesiune (8001 a pornit serviciul: memorie in driver) pauzele sunt mai lungi decat dupa o conexiune
 * fara sesiune (400, tuner ocupat, inchidere inainte de antet), ca zap-ul cu un 400 scurt sa nu astepte.
 * Pe un transponder fara semnal (200 si inchidere dupa ~3 s): sesiuni la 0, 8, 21, 44 s, apoi una la 60 s. */
#define PAUZE_N 6
static const int64_t pauze_sesiune[PAUZE_N] = { 5000, 10000, 20000, 40000, 60000, 60000 };
static const int64_t pauze_fara[PAUZE_N] = { 2000, 4000, 8000, 16000, 32000, 60000 };
static char eroare_ultima[96];

static void seteaza_eroare(const char *a, const char *b)
{
    size_t k = 0;
    for (int j = 0; j < 2; j++) {
        const char *s = j ? b : a;
        if (!s)
            continue;
        for (; *s && k + 1 < sizeof(eroare_ultima); s++) {
            unsigned char ch = (unsigned char)*s;
            eroare_ultima[k++] = (ch < 0x20 || ch > 0x7E || ch == '"' || ch == '\\') ? '_' : (char)ch;
        }
    }
    eroare_ultima[k] = 0;
}

static int url_citeste(const char *u)
{
    if (strncmp(u, "http://", 7) != 0)
        return -1;
    const char *g = u + 7;
    const char *sl = strchr(g, '/');
    size_t glen = sl ? (size_t)(sl - g) : strlen(g);
    if (glen == 0 || glen >= sizeof(h_gazda))
        return -1;
    memcpy(h_gazda, g, glen);
    h_gazda[glen] = 0;
    long port = 80;
    char *dp = strchr(h_gazda, ':');
    if (dp) {
        *dp = 0;
        char *e;
        errno = 0;
        port = strtol(dp + 1, &e, 10);
        if (errno || e == dp + 1 || *e || port < 1 || port > 65535)
            return -1;
    }
    const char *cale = sl ? sl : "/";
    if (strlen(cale) >= sizeof(h_cale))
        return -1;
    for (const char *s = cale; *s; s++)
        if ((unsigned char)*s <= 0x20 || (unsigned char)*s >= 0x7F)
            return -1;
    strcpy(h_cale, cale);
    memset(&h_adresa, 0, sizeof(h_adresa));
    h_adresa.sin_family = AF_INET;
    h_adresa.sin_port = htons((uint16_t)port);
    if (strcmp(h_gazda, "localhost") == 0)
        h_adresa.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    else if (inet_pton(AF_INET, h_gazda, &h_adresa.sin_addr) != 1)
        return -1;
    return 0;
}

/* un rand in fisierul -c, in formatul din comun/sesiuni8001.py */
static void noteaza_sesiune(void)
{
    if (!opt_c)
        return;
    int fd = open(opt_c, O_WRONLY | O_APPEND | O_CREAT, 0644);
    if (fd < 0)
        return;
    struct stat sb;
    if (fstat(fd, &sb) == 0 && sb.st_size > (off_t)(256 * 1024)) {
        close(fd);
        return;
    }
    long up = 0;
    int fu = open("/proc/uptime", O_RDONLY);
    if (fu >= 0) {
        char b[64];
        ssize_t r = read(fu, b, sizeof(b) - 1);
        close(fu);
        if (r > 0) {
            b[r] = 0;
            up = strtol(b, NULL, 10);
        }
    }
    char l[96];
    int n = snprintf(l, sizeof(l), "%ld %lld t2mi_decap\n", up, (long long)time(NULL));
    if (n > 0) {
        ssize_t w = write(fd, l, (size_t)n);
        (void)w;
    }
    close(fd);
}

#define FEREASTRA_LOC ((int)(sizeof(h_fereastra) / sizeof(h_fereastra[0])))

static void fereastra_curata(int64_t t)
{
    int k = 0;
    for (int i = 0; i < h_fereastra_n; i++) {
        if (t - h_fereastra[i] < FEREASTRA_MS) {
            h_fereastra[k] = h_fereastra[i];
            h_fereastra_ses[k] = h_fereastra_ses[i];
            k++;
        }
    }
    h_fereastra_n = k;
}

/* un moment nou la coada ferestrei; plina = cel mai vechi pleaca */
static void fereastra_pune(int64_t t, int sesiune)
{
    if (h_fereastra_n == FEREASTRA_LOC) {
        memmove(h_fereastra, h_fereastra + 1, sizeof(h_fereastra[0]) * (size_t)(FEREASTRA_LOC - 1));
        memmove(h_fereastra_ses, h_fereastra_ses + 1, (size_t)(FEREASTRA_LOC - 1));
        h_fereastra_n--;
    }
    h_fereastra[h_fereastra_n] = t;
    h_fereastra_ses[h_fereastra_n] = (uint8_t)sesiune;
    h_fereastra_n++;
}

static int fereastra_sesiuni(void)
{
    int k = 0;
    for (int i = 0; i < h_fereastra_n; i++)
        k += h_fereastra_ses[i];
    return k;
}

/* o sesiune pe sursa: raspuns 200 fara alt raspuns HTTP in corp. Conexiunea curenta e ultima din fereastra. */
static void h_sesiune_noua(int64_t t)
{
    h_sesiuni++;
    fereastra_curata(t);
    if (h_fereastra_n > 0)
        h_fereastra_ses[h_fereastra_n - 1] = 1;
    noteaza_sesiune();
    psi_trunchiaza();
}

/* /proc/uptime in milisecunde, fara virgula mobila; -1 daca nu se poate citi */
static int64_t uptime_ms(void)
{
    int fu = open("/proc/uptime", O_RDONLY);
    if (fu < 0)
        return -1;
    char b[64];
    ssize_t r = read(fu, b, sizeof(b) - 1);
    close(fu);
    if (r <= 0)
        return -1;
    b[r] = 0;
    int64_t s = 0, frac = 0, scala = 100;
    int i = 0, cifre = 0;
    for (; b[i] >= '0' && b[i] <= '9'; i++, cifre++)
        s = s * 10 + (b[i] - '0');
    if (cifre == 0)
        return -1;
    if (b[i] == '.') {
        for (i++; b[i] >= '0' && b[i] <= '9' && scala > 0; i++, scala /= 10)
            frac += (b[i] - '0') * scala;
    }
    return s * 1000 + frac;
}

/* La pornire cu -c: randurile "<uptime> <epoch> t2mi_decap" din ultimele 120 s (dupa uptime, care nu sare cand se
 * potriveste ceasul) intra in fereastra, iar pauza continua de unde a lasat-o binarul de dinainte. Se citeste doar
 * coada fisierului, intr-un buffer fix. Randurile altor procese (releul DAB scrie "releu") nu se iau: limita e pe proces. */
static char contor_buf[8193];

static void h_citeste_contor(int64_t t)
{
    if (!opt_c)
        return;
    int64_t up = uptime_ms();
    if (up < 0)
        return;
    int fd = open(opt_c, O_RDONLY);
    if (fd < 0)
        return;
    struct stat sb;
    ssize_t r = -1;
    off_t de_la = 0;
    if (fstat(fd, &sb) == 0) {
        if (sb.st_size > (off_t)(sizeof(contor_buf) - 1))
            de_la = sb.st_size - (off_t)(sizeof(contor_buf) - 1);
        if (lseek(fd, de_la, SEEK_SET) == de_la)
            r = read(fd, contor_buf, sizeof(contor_buf) - 1);
    }
    close(fd);
    if (r <= 0)
        return;
    contor_buf[r] = 0;
    char *p = contor_buf;
    if (de_la > 0) {                    /* primul rand poate fi taiat */
        p = strchr(p, '\n');
        if (!p)
            return;
        p++;
    }
    static const char nume[] = "t2mi_decap";
    int gasite = 0;
    int64_t ultimul = 0;
    while (*p) {
        char *sf = strchr(p, '\n');
        if (!sf)
            break;                      /* rand neterminat: se scrie chiar acum */
        *sf = 0;
        int64_t up_rand = 0;
        int cifre = 0;
        char *q = p;
        for (; *q >= '0' && *q <= '9' && cifre < 12; q++, cifre++)
            up_rand = up_rand * 10 + (*q - '0');
        if (cifre > 0 && *q == ' ') {
            q++;
            while (*q >= '0' && *q <= '9')
                q++;
            if (*q == ' ' && strcmp(q + 1, nume) == 0) {
                /* uptime-ul din rand e trunchiat la secunda: momentul real e cel mult 999 ms mai tarziu */
                int64_t moment_up = up_rand * 1000 + 999;
                if (moment_up <= up + 2000) {           /* altfel e din alta pornire a masinii */
                    int64_t varsta = up - moment_up;
                    if (varsta < 0)
                        varsta = 0;
                    if (varsta < FEREASTRA_MS) {
                        fereastra_pune(t - varsta, 1);
                        gasite++;
                        ultimul = t - varsta;
                    }
                }
            }
        }
        p = sf + 1;
    }
    if (gasite > 0) {
        h_pauza_idx = gasite < PAUZE_N ? gasite : PAUZE_N - 1;
        h_pauza_pana = ultimul + pauze_sesiune[(gasite - 1) < PAUZE_N - 1 ? gasite - 1 : PAUZE_N - 1];
    }
}

/* pauza de dupa o conexiune terminata; indicele urca pana la plafon */
static void h_pauza_dupa(int64_t t, int sesiune, int bune)
{
    if (bune)
        h_pauza_idx = 0;
    h_pauza_pana = t + (sesiune && !bune ? pauze_sesiune : pauze_fara)[h_pauza_idx];
    if (h_pauza_idx < PAUZE_N - 1)
        h_pauza_idx++;
}

static void h_inchide_fd(void)
{
    if (h_fd >= 0)
        close(h_fd);
    h_fd = -1;
}

/* sfarsitul unei conectari (EOF, eroare, tuner ocupat, termen): golire, resetare, pauza crescatoare */
/* inchiderea conexiunii curente: golire, resetare; -> 1 daca a fost sesiune, *bune = au iesit pachete TS */
static int h_incheie(int64_t t, int ocupat, int *bune)
{
    int sesiune = 0;
    *bune = 0;
    if (h_stare == H_DATE) {
        proceseaza(1);
        goleste();
        sesiune = 1;
        *bune = st.iesite > h_iesite_la_inceput;
        decap_reset();
    } else if (h_stare == H_ASTEPT_DATE && h_antet_gata && !ocupat) {
        h_sesiune_noua(t);          /* 200 fara 400 in corp, chiar daca nu au venit date */
        sesiune = 1;
    }
    h_inchide_fd();
    intrare_len = 0;
    return sesiune;
}

/* sfarsitul unei conectari (EOF, eroare, tuner ocupat, termen): pauza crescatoare, pusa la minim doar dupa date bune */
static void h_termina(int64_t t, const char *motiv, const char *detaliu, int ocupat)
{
    int bune;
    int sesiune = h_incheie(t, ocupat, &bune);
    if (ocupat)
        h_ocupat++;
    seteaza_eroare(motiv, detaliu);
    h_pauza_dupa(t, sesiune, bune);
    h_stare = H_PAUZA;
}

/* fara clienti de -I secunde: conexiunea se inchide curat. Dupa date bune clientul care revine se conecteaza
 * imediat (zap inapoi); fara date bune pauza merge mai departe, ca plecarile si revenirile sa nu o ocoleasca. */
static void h_inchide_liniste(int64_t t)
{
    int bune;
    int sesiune = h_incheie(t, 0, &bune);
    if (bune) {
        h_pauza_idx = 0;
        h_pauza_pana = t;
    } else {
        h_pauza_dupa(t, sesiune, 0);
    }
    h_stare = H_ASTEAPTA_CLIENT;
}

static void h_trimite_cerere(int64_t t)
{
    char c[1400];
    int n = snprintf(c, sizeof(c), "GET %s HTTP/1.0\r\nHost: %s\r\nUser-Agent: hdsatelit\r\n\r\n", h_cale, h_gazda);
    h_conectari++;
    if (n <= 0 || (size_t)n >= sizeof(c) || send(h_fd, c, (size_t)n, MSG_NOSIGNAL) != (ssize_t)n) {
        h_stare = H_CONECTARE;
        h_termina(t, "cererea HTTP nu a plecat", NULL, 0);
        return;
    }
    h_stare = H_ASTEPT_DATE;
    h_antet_gata = 0;
    h_de_la = t;
    intrare_len = 0;
}

static void h_conecteaza(int64_t t)
{
    fereastra_curata(t);
    if (h_fereastra_n >= opt_sesiuni) {
        h_stare = H_LIMITA;
        return;
    }
    fereastra_pune(t, 0);           /* orice conexiune intra in limita, si cele care nu ajung sesiune */
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) {
        h_termina(t, "socket: ", strerror(errno), 0);
        return;
    }
    fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK);
    int buf = SOCLU_SURSA;
    setsockopt(fd, SOL_SOCKET, SO_RCVBUF, &buf, sizeof(buf));
    h_fd = fd;
    h_de_la = t;
    if (connect(fd, (struct sockaddr *)&h_adresa, sizeof(h_adresa)) == 0) {
        h_trimite_cerere(t);
    } else if (errno == EINPROGRESS || errno == EINTR) {
        h_stare = H_CONECTARE;
    } else {
        h_stare = H_CONECTARE;
        h_termina(t, "conectare: ", strerror(errno), 0);
    }
}

static void h_conectat(int64_t t)
{
    int err = 0;
    socklen_t l = sizeof(err);
    if (getsockopt(h_fd, SOL_SOCKET, SO_ERROR, &err, &l) < 0)
        err = errno;
    if (err) {
        h_termina(t, "conectare: ", strerror(err), 0);
        return;
    }
    h_trimite_cerere(t);
}

static int contine(const uint8_t *p, size_t n, const char *ac)
{
    size_t m = strlen(ac);
    for (size_t i = 0; i + m <= n; i++)
        if (memcmp(p + i, ac, m) == 0)
            return 1;
    return 0;
}

static void h_date_incep(int64_t t)
{
    h_stare = H_DATE;
    h_prima_data = t;
    h_ultima_data = t;
    h_iesite_la_inceput = st.iesite;
    h_sesiune_noua(t);
    seteaza_eroare("", NULL);
    proceseaza(0);
}

/* primii octeti din corp: alt raspuns HTTP fara " 200" = tuner ocupat. -> 1 date, 0 nehotarat, -1 terminat */
static int h_decide(int64_t t, int eof)
{
    size_t n = intrare_len;
    size_t k = n < 7 ? n : 7;
    if (n > 0 && memcmp(intrare, "HTTP/1.", k) != 0) {
        h_date_incep(t);
        return 1;
    }
    if (n < 7 || (n < 12 && !eof)) {
        if (eof) {
            h_termina(t, "sursa a inchis fluxul fara date", NULL, 0);
            return -1;
        }
        return 0;
    }
    if (!contine(intrare, n < 16 ? n : 16, " 200")) {
        char d[48];
        size_t m = n < sizeof(d) - 1 ? n : sizeof(d) - 1;
        memcpy(d, intrare, m);
        d[m] = 0;
        for (size_t i = 0; i < m; i++)
            if (d[i] == '\r' || d[i] == '\n')
                d[i] = 0;
        h_termina(t, "tuner ocupat: ", d, 1);
        return -1;
    }
    h_date_incep(t);
    return 1;
}

static void h_citeste(int64_t t)
{
    size_t loc = sizeof(intrare) - intrare_len;
    if (loc > BLOC_CITIRE)
        loc = BLOC_CITIRE;
    ssize_t n = recv(h_fd, intrare + intrare_len, loc, 0);
    if (n < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR)
            return;
        if (h_stare == H_ASTEPT_DATE && h_antet_gata)
            h_decide(t, 1);
        if (h_fd >= 0)
            h_termina(t, "citire: ", strerror(errno), 0);
        return;
    }
    if (n == 0) {
        if (h_stare == H_ASTEPT_DATE && h_antet_gata) {
            if (h_decide(t, 1) != 1)
                return;
        }
        h_termina(t, h_stare == H_DATE ? "sursa a inchis fluxul" : "sursa a inchis inainte de antet", NULL, 0);
        return;
    }
    oct_intrare += (uint64_t)n;
    h_ultima_data = t;
    intrare_len += (size_t)n;
    if (h_stare == H_DATE) {
        proceseaza(0);
        return;
    }
    if (!h_antet_gata) {
        size_t sf = 0;
        int gasit = 0;
        for (size_t i = 0; i + 4 <= intrare_len && i < ANTET_MAX; i++) {
            if (intrare[i] == '\r' && intrare[i + 1] == '\n' && intrare[i + 2] == '\r' && intrare[i + 3] == '\n') {
                sf = i;
                gasit = 1;
                break;
            }
        }
        if (!gasit) {
            if (intrare_len > ANTET_MAX)
                h_termina(t, "antet HTTP prea lung", NULL, 0);
            return;
        }
        size_t linie = 0;
        while (linie < sf && intrare[linie] != '\r' && intrare[linie] != '\n')
            linie++;
        if (!contine(intrare, linie, " 200")) {
            char d[48];
            size_t m = linie < sizeof(d) - 1 ? linie : sizeof(d) - 1;
            memcpy(d, intrare, m);
            d[m] = 0;
            h_termina(t, "raspuns HTTP: ", d, 0);
            return;
        }
        memmove(intrare, intrare + sf + 4, intrare_len - sf - 4);
        intrare_len -= sf + 4;
        h_antet_gata = 1;
        if (intrare_len == 0)
            return;
    }
    h_decide(t, 0);
}

/* pornirile, pauzele si termenele sursei HTTP; chemat la fiecare trecere prin bucla */
static void h_tic(int64_t t)
{
    int vrea = 1;
    if (opt_port >= 0) {
        if (clienti_flux() > 0)
            h_ultim_client = t;
        vrea = h_ultim_client >= 0 && t - h_ultim_client < (int64_t)opt_inactiv * 1000;
    }
    switch (h_stare) {
    case H_ASTEAPTA_CLIENT:
    case H_PAUZA:
        if (!vrea) {
            h_stare = H_ASTEAPTA_CLIENT;
        } else if (t >= h_pauza_pana) {
            h_conecteaza(t);
        } else {
            h_stare = H_PAUZA;
        }
        break;
    case H_LIMITA:
        if (!vrea) {
            h_stare = H_ASTEAPTA_CLIENT;
        } else {
            fereastra_curata(t);
            if (h_fereastra_n < opt_sesiuni)
                h_conecteaza(t);
        }
        break;
    case H_CONECTARE:
        if (!vrea)
            h_inchide_liniste(t);
        else if (t - h_de_la > 10000)
            h_termina(t, "conectare fara raspuns", NULL, 0);
        break;
    case H_ASTEPT_DATE:
        if (!vrea)
            h_inchide_liniste(t);
        else if (t - h_de_la > (int64_t)opt_termen * 1000)
            h_termina(t, "fara date in termen", NULL, 0);
        break;
    case H_DATE:
        if (!vrea)
            h_inchide_liniste(t);
        else if (t - h_ultima_data > (int64_t)opt_termen * 1000)
            h_termina(t, "fluxul s-a oprit", NULL, 0);
        break;
    default:
        break;
    }
}

/* ------------------------------------------------------------------ statistici */

static size_t formateaza_stat(char *s, size_t cap, int64_t de_la_ms)
{
    size_t k = 0;
    int r;
    const char *mod = st.mod < 0 ? "?" : (st.mod ? "HEM" : "NM");
    char hs[32];
    if (opt_url)
        snprintf(hs, sizeof(hs), "\"%s\"", h_nume[h_stare]);
    else
        strcpy(hs, "null");
    r = snprintf(s + k, cap - k,
                 "{\"t_ms\":%lld,\"ts\":%llu,\"ts_pid\":%llu,\"cc\":%llu,\"tei\":%llu,\"dublu\":%llu,"
                 "\"af_rau\":%llu,\"pointer_rau\":%llu,\"resinc_ts\":%llu,"
                 "\"t2mi_bune\":%llu,\"t2mi_rele\":%llu,\"t2mi_lipsa\":%llu,\"resinc_t2mi\":%llu,"
                 "\"bb\":%llu,\"bb_crc\":%llu,\"bb_rele\":%llu,\"bb_ne_ts\":%llu,\"up_crc\":%llu,\"up_sinc\":%llu,"
                 "\"l1\":%llu,\"l1_rele\":%llu,\"l1_lipsa\":%llu,\"alt_flux\":%llu,\"criptate\":%llu,"
                 "\"mod\":\"%s\",\"plp_date\":%d,\"plp_comun\":%d,\"comun_iesite\":%llu,"
                 "\"iesite\":%llu,\"nule\":%llu,\"aruncate\":%llu,\"ts_in_pid\":%s,\"resinc_interior\":%llu,"
                 "\"client\":%s,",
                 (long long)(acum_ms() - de_la_ms), (unsigned long long)st.ts_in, (unsigned long long)st.ts_pid,
                 (unsigned long long)st.ts_cc, (unsigned long long)st.ts_tei, (unsigned long long)st.ts_dublu,
                 (unsigned long long)st.ts_af_rau, (unsigned long long)st.ts_pointer_rau,
                 (unsigned long long)st.ts_resinc, (unsigned long long)st.t2_bune, (unsigned long long)st.t2_rele,
                 (unsigned long long)st.t2_lipsa, (unsigned long long)st.t2_resinc, (unsigned long long)st.bb,
                 (unsigned long long)st.bb_crc, (unsigned long long)st.bb_rele, (unsigned long long)st.bb_ne_ts,
                 (unsigned long long)st.up_crc, (unsigned long long)st.up_sinc, (unsigned long long)st.l1,
                 (unsigned long long)st.l1_rele, (unsigned long long)st.l1_lipsa, (unsigned long long)st.t2_alt_flux,
                 (unsigned long long)st.ts_criptate, mod, plp_date, plp_comun, (unsigned long long)st.comun,
                 (unsigned long long)st.iesite,
                 (unsigned long long)st.nule, (unsigned long long)st.aruncate,
                 opt_ts_in_pid ? "true" : "false", (unsigned long long)st.ab_resinc,
                 opt_port < 0 ? "null" : (clienti_flux() > 0 ? "true" : "false"));
    if (r < 0 || (size_t)r >= cap - k)
        return 0;
    k += (size_t)r;
    int64_t acum = acum_ms();
    fereastra_curata(acum);
    /* cat mai asteapta sursa pana la urmatoarea conexiune (pauza sau limita), ca releul si pluginul sa stie */
    int64_t ramas = 0;
    if (opt_url && (h_stare == H_PAUZA || h_stare == H_LIMITA || h_stare == H_ASTEAPTA_CLIENT)) {
        if (h_pauza_pana > acum)
            ramas = h_pauza_pana - acum;
        if (h_fereastra_n >= opt_sesiuni && h_fereastra_n > 0) {
            int64_t liber = h_fereastra[h_fereastra_n - opt_sesiuni] + FEREASTRA_MS - acum;
            if (liber > ramas)
                ramas = liber;
        }
    }
    r = snprintf(s + k, cap - k,
                 "\"pid\":%ld,\"octeti_intrare\":%llu,\"http_stare\":%s,\"sesiuni_8001\":%llu,\"sesiuni_fereastra\":%d,"
                 "\"conexiuni_fereastra\":%d,\"pauza_idx\":%d,\"pauza_ramasa_ms\":%lld,\"antet_200\":%s,"
                 "\"conectari\":%llu,\"ocupat_400\":%llu,\"eroare_ultima\":\"%s\",\"clienti\":%d,"
                 "\"clienti_aruncati\":%llu,\"clienti_total\":%llu,\"octeti_trimisi\":%llu,\"psi_octeti\":%lu,\"plp\":[",
                 (long)getpid(), (unsigned long long)oct_intrare, hs, (unsigned long long)h_sesiuni, fereastra_sesiuni(),
                 h_fereastra_n, h_pauza_idx, (long long)ramas,
                 (opt_url && h_stare == H_ASTEPT_DATE && h_antet_gata) ? "true" : "false",
                 (unsigned long long)h_conectari, (unsigned long long)h_ocupat, eroare_ultima, clienti_flux(),
                 (unsigned long long)cl_aruncati, (unsigned long long)cl_total, (unsigned long long)oct_trimisi,
                 (unsigned long)psi_scrise);
    if (r < 0 || (size_t)r >= cap - k)
        return 0;
    k += (size_t)r;
    /* loc pastrat pentru inchiderea obiectului, ca JSON-ul sa ramana valid oricat de lungi sunt listele */
    size_t cap_liste = cap - 32;
    for (int i = 0; i < (l1_n < 0 ? 0 : l1_n) && k + 64 < cap_liste; i++) {
        const Plp *P = &plp[l1_ids[i]];
        r = snprintf(s + k, cap - k, "%s{\"id\":%u,\"tip\":%u,\"sarcina\":%u,\"grup\":%u}", i ? "," : "",
                     l1_ids[i], P->tip, P->sarcina, P->grup);
        if (r < 0)
            return 0;
        k += (size_t)r;
    }
    memcpy(s + k, "],\"plp_bb\":[", 12);
    k += 12;
    int primul = 1;
    for (int i = 0; i < 256 && k + 8 < cap_liste; i++) {
        if (!plp_vazut[i])
            continue;
        r = snprintf(s + k, cap - k, "%s%d", primul ? "" : ",", i);
        if (r < 0)
            return 0;
        k += (size_t)r;
        primul = 0;
    }
    s[k++] = ']';
    s[k++] = '}';
    s[k++] = '\n';
    return k;
}

static void scrie_stat(int64_t de_la_ms)
{
    char s[JSON_MAX];
    size_t k = formateaza_stat(s, sizeof(s), de_la_ms);
    if (k == 0 || tacut)
        return;
    ssize_t w = write(2, s, k);
    (void)w;
}

static char j_tmp[4200];

static void scrie_json(int64_t de_la_ms)
{
    char s[JSON_MAX];
    if (!opt_j)
        return;
    size_t k = formateaza_stat(s, sizeof(s), de_la_ms);
    if (k == 0)
        return;
    int fd = open(j_tmp, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0)
        return;
    ssize_t w = write(fd, s, k);
    close(fd);
    if (w == (ssize_t)k)
        rename(j_tmp, opt_j);
}

/* ------------------------------------------------------------------ server HTTP (-u) */

static int http_porneste(int port)
{
    int fd = socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0)
        return -1;
    int da = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &da, sizeof(da));
    struct sockaddr_in a;
    memset(&a, 0, sizeof(a));
    a.sin_family = AF_INET;
    a.sin_port = htons((uint16_t)port);
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (bind(fd, (struct sockaddr *)&a, sizeof(a)) < 0 || listen(fd, 8) < 0) {
        close(fd);
        return -1;
    }
    fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK);
    return fd;
}

static void raspuns_scurt(Client *c, const char *stare)
{
    char r[256];
    int n = snprintf(r, sizeof(r), "HTTP/1.0 %s\r\nContent-Type: text/plain\r\nContent-Length: %u\r\n"
                     "Connection: close\r\n\r\n%s\n", stare, (unsigned)strlen(stare) + 1, stare);
    if (n > 0 && (size_t)n < sizeof(r)) {
        ssize_t w = send(c->fd, r, (size_t)n, MSG_NOSIGNAL);
        (void)w;
    }
    client_inchide(c);
}

static void http_accepta(int64_t t)
{
    for (int k = 0; k < 16; k++) {
        int fd = accept(fd_asculta, NULL, NULL);
        if (fd < 0)
            return;
        Client *c = NULL;
        for (int i = 0; i < MAX_CLIENTI; i++) {
            if (clienti[i].stare == 0) {
                c = &clienti[i];
                break;
            }
        }
        if (!c) {
            static const char plin[] = "HTTP/1.0 503 Service Unavailable\r\nConnection: close\r\n\r\n";
            ssize_t w = send(fd, plin, sizeof(plin) - 1, MSG_NOSIGNAL);
            (void)w;
            close(fd);
            continue;
        }
        fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK);
        c->fd = fd;
        c->stare = 1;
        c->de_la = t;
        c->cerere_len = 0;
        c->cap = 0;
        c->len = 0;
    }
}

/* PREFIX exact, sau urmat de '?', '.', '/' (dar nu /servicii: acela e al releului) */
static int cale_buna(const char *cale, size_t n)
{
    if (!opt_prefix)
        return 1;
    size_t m = strlen(opt_prefix);
    if (n < m || memcmp(cale, opt_prefix, m) != 0)
        return 0;
    if (n == m || cale[m] == '?' || cale[m] == '.')
        return 1;
    if (cale[m] != '/')
        return 0;
    const char *rest = cale + m + 1;
    size_t rn = n - m - 1;
    if (rn >= 8 && memcmp(rest, "servicii", 8) == 0 && (rn == 8 || rest[8] == '?' || rest[8] == '/' || rest[8] == '.'))
        return 0;
    return 1;
}

static void client_citeste(Client *c)
{
    if (c->stare == 1) {
        ssize_t r = recv(c->fd, c->cerere + c->cerere_len, CERERE_MAX - 1 - c->cerere_len, 0);
        if (r == 0 || (r < 0 && errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR)) {
            client_inchide(c);
            return;
        }
        if (r < 0)
            return;
        c->cerere_len += (size_t)r;
        c->cerere[c->cerere_len] = 0;
        if (!strstr(c->cerere, "\r\n\r\n") && !strstr(c->cerere, "\n\n")) {
            if (c->cerere_len >= CERERE_MAX - 1)
                raspuns_scurt(c, "400 Bad Request");
            return;
        }
        if (strncmp(c->cerere, "GET ", 4) != 0) {
            raspuns_scurt(c, "405 Method Not Allowed");
            return;
        }
        const char *cale = c->cerere + 4;
        size_t n = strcspn(cale, " \r\n");
        if (!cale_buna(cale, n)) {
            raspuns_scurt(c, "404 Not Found");
            return;
        }
        static const char raspuns[] = "HTTP/1.0 200 OK\r\nContent-Type: video/MP2T\r\n"
                                      "Cache-Control: no-cache\r\nConnection: close\r\n\r\n";
        if (send(c->fd, raspuns, sizeof(raspuns) - 1, MSG_NOSIGNAL) != (ssize_t)(sizeof(raspuns) - 1)) {
            client_inchide(c);
            return;
        }
        c->stare = 2;
        c->cap = 0;
        c->len = 0;
        cl_total++;
    } else if (c->stare == 2) {
        /* clientul nu trimite nimic; citim doar ca sa aflam cand pleaca */
        char gunoi[512];
        ssize_t r = recv(c->fd, gunoi, sizeof(gunoi), 0);
        if (r == 0 || (r < 0 && errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR))
            client_inchide(c);
    }
}

/* ------------------------------------------------------------------ main */

static void la_semnal(int s)
{
    (void)s;
    opreste = 1;
}

static void folosire(void)
{
    static const char t[] =
        "folosire: t2mi_decap -p PID [-l PLP] [-n] [-s] [-r] [-A] [-i fisier|-] [-o fisier|-] [-u PORT] [-a PREFIX]\n"
        "                     [-h URL [-I SEC] [-w SEC] [-R N] [-c FISIER]] [-j FISIER] [-P FISIER]\n"
        "  -p PID     PID-ul cu T2-MI (0..8191), nu trebuie cu -r\n"
        "  -A         PID-ul poarta un TS intreg in payload, fara T2-MI (fara -l, -n, -r)\n"
        "  -l PLP     PLP-ul dorit (0..255), implicit primul PLP de date din L1-current\n"
        "  -n         pune la loc pachetele nule sterse (NPD)\n"
        "  -s         statistici JSON pe stderr la 5 s (nu cu -u)\n"
        "  -r         intrare fara antete TS: pachete T2-MI lipite\n"
        "  -i         intrare (implicit stdin)\n"
        "  -o         iesire (implicit stdout)\n"
        "  -u PORT    serveste HTTP pe 127.0.0.1:PORT, cel mult 8 clienti; nimic pe stdout/stderr\n"
        "  -a PREFIX  cu -u: calea acceptata; altfel 404\n"
        "  -h URL     intrare din http://IPv4-sau-localhost:port/cale, cu reconectare\n"
        "  -I SEC     cu -u si -h: inchide sursa dupa SEC s fara clienti (implicit 30)\n"
        "  -w SEC     cu -h: termenul primelor date (implicit 90)\n"
        "  -R N       cu -h: cel mult N conexiuni spre sursa pe 120 s (implicit 4)\n"
        "  -c FISIER  cu -h: contorul de sesiuni (un rand pe sesiune; citit la pornire pentru limita)\n"
        "  -j FISIER  statistici JSON, scrise atomic o data pe secunda\n"
        "  -P FISIER  pachetele PAT/SDT de iesire, cel mult 64 KB\n"
        "  -t         proba interna a CRC-urilor\n";
    if (tacut)
        return;
    ssize_t w = write(2, t, sizeof(t) - 1);
    (void)w;
}

static int numar(const char *s, long min, long max, long *v)
{
    char *e;
    errno = 0;
    long x = strtol(s, &e, 0);
    if (errno || e == s || *e || x < min || x > max)
        return -1;
    *v = x;
    return 0;
}

int main(int argc, char **argv)
{
    const char *f_in = "-", *f_out = "-";
    int c;
    long v;
    crc_init();
    memset(pachet_nul, 0xFF, sizeof(pachet_nul));
    pachet_nul[0] = 0x47;
    pachet_nul[1] = 0x1F;
    pachet_nul[2] = 0xFF;
    pachet_nul[3] = 0x10;
    st.mod = -1;
    for (int i = 0; i < MAX_CLIENTI; i++)
        clienti[i].fd = -1;

    /* -u se afla inainte de orice mesaj: in modul releu nu se scrie nimic pe stderr */
    for (int i = 1; i < argc; i++)
        if (strncmp(argv[i], "-u", 2) == 0)
            tacut = 1;

    while ((c = getopt(argc, argv, "p:l:nsrAi:o:u:th:I:w:R:c:j:P:a:")) != -1) {
        switch (c) {
        case 'p':
            if (numar(optarg, 0, 8191, &v)) { folosire(); return 2; }
            opt_pid = (int)v;
            break;
        case 'l':
            if (numar(optarg, 0, 255, &v)) { folosire(); return 2; }
            opt_plp = (int)v;
            break;
        case 'n': opt_nule = 1; break;
        case 's': opt_stat = 1; break;
        case 'r': opt_brut = 1; break;
        case 'A': opt_ts_in_pid = 1; break;
        case 'i': f_in = optarg; break;
        case 'o': f_out = optarg; break;
        case 'u':
            if (numar(optarg, 1, 65535, &v)) { folosire(); return 2; }
            opt_port = (int)v;
            break;
        case 'h': opt_url = optarg; break;
        case 'I':
            if (numar(optarg, 0, 86400, &v)) { folosire(); return 2; }
            opt_inactiv = v;
            break;
        case 'w':
            if (numar(optarg, 1, 86400, &v)) { folosire(); return 2; }
            opt_termen = v;
            break;
        case 'R':
            if (numar(optarg, 1, 64, &v)) { folosire(); return 2; }
            opt_sesiuni = v;
            break;
        case 'c': opt_c = optarg; break;
        case 'j': opt_j = optarg; break;
        case 'P': opt_psi = optarg; break;
        case 'a':
            if (optarg[0] != '/' || strlen(optarg) > 512) { folosire(); return 2; }
            opt_prefix = optarg;
            break;
        case 't': {
            static const uint8_t m[] = "123456789";
            int ok = crc32_mpeg(m, 9) == 0x0376E6E7u && crc8_cont(0, m, 9) == 0xBC;
            eroare("crc32=%08x crc8=%02x %s\n", crc32_mpeg(m, 9), crc8_cont(0, m, 9), ok ? "bun" : "GRESIT");
            return ok ? 0 : 1;
        }
        default:
            folosire();
            return 2;
        }
    }
    tacut = opt_port >= 0;
    if (optind != argc || (opt_pid < 0 && !opt_brut) || (opt_url && strcmp(f_in, "-") != 0)
        || (opt_ts_in_pid && (opt_pid < 0 || opt_brut || opt_nule || opt_plp >= 0))) {
        folosire();
        return 2;
    }
    if (opt_url && url_citeste(opt_url) < 0) {
        eroare("t2mi_decap: URL gresit (se accepta http://IPv4-sau-localhost:port/cale): %s\n", opt_url);
        return 2;
    }
    if (opt_j) {
        int n = snprintf(j_tmp, sizeof(j_tmp), "%s.tmp", opt_j);
        if (n <= 0 || (size_t)n >= sizeof(j_tmp)) { folosire(); return 2; }
    }
    if (tacut)
        opt_stat = 0;
    plp_date = opt_plp; /* cu -l lucram de la primul cadru; fara -l asteptam L1-current */

    signal(SIGPIPE, SIG_IGN);
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_handler = la_semnal;
    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGTERM, &sa, NULL);

    /* pornit de un releu: moare odata cu el */
    int paza_parinte = opt_port >= 0 || opt_url != NULL;
    pid_t parinte = getppid();
    if (paza_parinte) {
#ifdef __linux__
        prctl(PR_SET_PDEATHSIG, SIGTERM);
#endif
        if (getppid() != parinte || parinte == 1)
            return 1;
    }

    int fd_in = -1;
    if (!opt_url) {
        fd_in = 0;
        if (strcmp(f_in, "-") != 0) {
            fd_in = open(f_in, O_RDONLY);
            if (fd_in < 0) {
                eroare("t2mi_decap: nu pot deschide %s: %s\n", f_in, strerror(errno));
                return 1;
            }
        }
    }
    if (opt_psi) {
        psi_fd = open(opt_psi, O_WRONLY | O_CREAT | O_TRUNC | O_APPEND, 0644);
        if (psi_fd < 0) {
            eroare("t2mi_decap: nu pot scrie %s: %s\n", opt_psi, strerror(errno));
            return 1;
        }
    }
    if (opt_port >= 0) {
        fd_asculta = http_porneste(opt_port);
        if (fd_asculta < 0)
            return 1;
    } else if (strcmp(f_out, "-") != 0) {
        fd_out = open(f_out, O_WRONLY | O_CREAT | O_TRUNC, 0644);
        if (fd_out < 0) {
            eroare("t2mi_decap: nu pot scrie %s: %s\n", f_out, strerror(errno));
            return 1;
        }
    }

    int64_t start = acum_ms(), ultima_stat = start, ultima_scriere = start, ultim_json = start, ultim_parinte = start;
    int sfarsit = 0;
    if (opt_url)
        h_citeste_contor(start);
    scrie_json(start); /* fisierul -j exista = portul asculta */

    while (!opreste && !sfarsit) {
        struct pollfd pf[2 + MAX_CLIENTI];
        int ip_cl[MAX_CLIENTI];
        int np = 0, ip_in = -1, ip_asc = -1;
        int sursa_fd = opt_url ? h_fd : fd_in;
        if (sursa_fd >= 0) {
            ip_in = np;
            pf[np].fd = sursa_fd;
            pf[np].events = (short)(opt_url && h_stare == H_CONECTARE ? POLLOUT : POLLIN);
            pf[np].revents = 0;
            np++;
        }
        if (fd_asculta >= 0) {
            ip_asc = np;
            pf[np].fd = fd_asculta; pf[np].events = POLLIN; pf[np].revents = 0; np++;
        }
        for (int i = 0; i < MAX_CLIENTI; i++) {
            ip_cl[i] = -1;
            if (clienti[i].stare == 0)
                continue;
            ip_cl[i] = np;
            pf[np].fd = clienti[i].fd;
            pf[np].events = (short)(POLLIN | (clienti[i].len ? POLLOUT : 0));
            pf[np].revents = 0;
            np++;
        }
        int r = poll(pf, (nfds_t)np, 200);
        if (r < 0 && errno != EINTR)
            break;
        int64_t t = acum_ms();

        if (r > 0 && ip_asc >= 0 && (pf[ip_asc].revents & POLLIN))
            http_accepta(t);
        for (int i = 0; r > 0 && i < MAX_CLIENTI; i++) {
            Client *cl = &clienti[i];
            if (ip_cl[i] < 0 || cl->stare == 0 || pf[ip_cl[i]].fd != cl->fd)
                continue;
            short ev = pf[ip_cl[i]].revents;
            if (ev & (POLLIN | POLLHUP | POLLERR))
                client_citeste(cl);
            if (cl->stare == 2 && (ev & POLLOUT) && cl->len && client_goleste_coada(cl) < 0)
                client_inchide(cl);
        }
        for (int i = 0; i < MAX_CLIENTI; i++)
            if (clienti[i].stare == 1 && t - clienti[i].de_la > 10000)
                client_inchide(&clienti[i]);

        if (r > 0 && ip_in >= 0 && pf[ip_in].revents) {
            short ev = pf[ip_in].revents;
            if (opt_url) {
                if (h_stare == H_CONECTARE)
                    h_conectat(t);
                else if (ev & (POLLIN | POLLHUP | POLLERR))
                    h_citeste(t);
            } else if (ev & (POLLIN | POLLHUP | POLLERR)) {
                ssize_t n = read(fd_in, intrare + intrare_len, BLOC_CITIRE);
                if (n < 0) {
                    if (errno != EINTR && errno != EAGAIN)
                        sfarsit = 1;
                } else if (n == 0) {
                    sfarsit = 1;
                } else {
                    oct_intrare += (uint64_t)n;
                    intrare_len += (size_t)n;
                    proceseaza(0);
                }
            }
        }
        if (sfarsit)
            proceseaza(1);
        if (opt_url)
            h_tic(t);

        if (iesire_len >= PRAG_SCRIERE || (iesire_len > 0 && t - ultima_scriere >= 300) || sfarsit) {
            goleste();
            ultima_scriere = t;
        }
        if (opt_stat && t - ultima_stat >= PERIOADA_STAT_MS) {
            scrie_stat(start);
            ultima_stat = t;
        }
        if (opt_j && t - ultim_json >= 1000) {
            scrie_json(start);
            ultim_json = t;
        }
        if (paza_parinte && t - ultim_parinte >= 1000) {
            if (getppid() != parinte)
                opreste = 1;
            ultim_parinte = t;
        }
    }
    goleste();
    /* oprit (SIGTERM) dupa antetul 200, inainte de date: sesiunea a costat in driver, deci are rand in -c */
    if (opt_url && h_stare == H_ASTEPT_DATE && h_antet_gata)
        h_sesiune_noua(acum_ms());
    /* la sfarsitul intrarii, ce mai asteapta spre clienti pleaca (cel mult 5 s) */
    int64_t pana_la = acum_ms() + 5000;
    while (!opreste && fd_asculta >= 0 && acum_ms() < pana_la) {
        struct pollfd pf[MAX_CLIENTI];
        Client *cl[MAX_CLIENTI];
        int np = 0;
        for (int i = 0; i < MAX_CLIENTI; i++) {
            if (clienti[i].stare == 2 && clienti[i].len > 0) {
                cl[np] = &clienti[i];
                pf[np].fd = clienti[i].fd;
                pf[np].events = POLLOUT;
                pf[np].revents = 0;
                np++;
            }
        }
        if (np == 0)
            break;
        if (poll(pf, (nfds_t)np, 200) > 0) {
            for (int i = 0; i < np; i++)
                if (pf[i].revents && client_goleste_coada(cl[i]) < 0)
                    client_inchide(cl[i]);
        }
    }
    if (opt_stat)
        scrie_stat(start);
    scrie_json(start);
    for (int i = 0; i < MAX_CLIENTI; i++)
        client_inchide(&clienti[i]);
    h_inchide_fd();
    if (fd_asculta >= 0)
        close(fd_asculta);
    if (psi_fd >= 0)
        close(psi_fd);
    if (fd_out > 2)
        close(fd_out);
    return 0;
}
