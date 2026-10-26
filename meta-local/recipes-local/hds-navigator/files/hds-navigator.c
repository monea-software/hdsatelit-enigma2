/*
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 * SPDX-License-Identifier: GPL-2.0-only
 *
 * hds-navigator: lansator WPE WebKit 2.x (API WPEPlatform) pentru receptoare fara DRM si fara Wayland.
 *
 * O platforma WPE proprie ("hds-fbdev") primeste cadrele paginii in memorie partajata (WPEBufferSHM),
 * le copiaza pe /dev/fb0 (numai dreptunghiurile schimbate) sau intr-o panza din memorie scrisa ca PPM
 * (pentru probe fara ecran). Telecomanda se citeste direct din evdev (dupa ce enigma2 a pus eRCInput.lock()),
 * iar comenzile vin pe intrarea standard, cate una pe rand. Pe iesirea standard lansatorul scrie numai
 * randuri de stare scurte ("HDS-NAV ..."); adresele si textele din pagina merg numai in base64, numai spre
 * enigma2, la cererea lui, si nu se scriu in niciun jurnal.
 *
 * Predarea ecranului: cu --ascuns lansatorul deseneaza numai in memorie pana la comanda „arata” (enigma2 o trimite
 * dupa fbClass.lock()); „ascunde” opreste scrierea pe framebuffer si elibereaza telecomanda (EVIOCGRAB) inainte ca
 * enigma2 sa o ia inapoi. Ferestrele pe care pagina le cere (autentificare, alert/confirm/prompt, <select>, tastatura
 * pentru un camp) le deseneaza enigma2: lansatorul le cere cu un rand „HDS-NAV CERERE ...” si primeste raspunsul pe
 * intrarea standard.
 *
 * Randarea: implicit procesul web compune cu GLES pe ecranul EGL disponibil si citeste cadrul inapoi in memoria
 * partajata; --pictura-cpu lasa numai compunerea pe GLES; --cpu desenul si compunerea pe procesor (Skia).
 * Rezerva automata: la pornire un proces copil incearca ecranul EGL (dlopen, fara legare de libEGL); daca nu exista
 * sau nu porneste, desenul trece pe procesor. Daca procesul web cade cu GL sau nu da niciun cadru in 15 s dupa
 * incarcare, lansatorul se reporneste o singura data cu --cpu. Fiecare trecere pe procesor lasa un rand
 * „HDS-NAV REZERVA ...”.
 *
 * Modul HbbTV (--hbbtv, aplicatia HbbTV a canalului, pornita de enigma2 la tasta ROSIE): fundalul paginii e transparent
 * (zonele fara continut au alfa 0 pe fb0, deci canalul de dedesubt se vede), User-Agent-ul primeste partea HbbTV
 * (--agent-adaugat), navigarea spatiala e oprita (aplicatia isi muta singura focalizarea), constantele VK_* sunt puse
 * in pagina, iar tastele vin numai pe intrarea standard (fara --intrare, deci fara EVIOCGRAB: telecomanda ramane a
 * enigma2, care trimite numai tastele aplicatiei): sagetile, OK, culorile (keyCode 403-406 din WebKit), cifrele si
 * BACK (VK_BACK 461, eveniment facut in pagina, fiindca WebKit da 166 pentru tasta Back). La iesire lansatorul goleste
 * (alfa 0) ce a desenat pe fb0. Ferestrele cerute de pagina le refuza enigma2.
 *
 * Stratul HbbTV (etapa H3, numai cu --hbbtv): obiectele OIPF/HbbTV 1.5 (oipfApplicationManager, Application, Keyset,
 * oipfConfiguration, oipfCapabilities, oipfParentalControlManager, video/broadcast, oipfObjectFactory) sunt in
 * hds-hbbtv.js (--hbbtv-js, implicit /usr/share/hds-navigator/hds-hbbtv.js), pus in cadrul de sus la inceputul
 * fiecarui document, dupa starea data de enigma2 (window.__hdsHbbtvStare). Starea vine la pornire cu
 * --hbbtv-parte CHEIE=BASE64 (partile mici) si apoi pe intrarea standard: "hbbtv-parte CHEIE BASE64" (tinuta minte
 * pentru documentele urmatoare si trimisa paginii de acum) si "hbbtv-ev BASE64" (un eveniment pentru pagina). JSON-ul
 * ajunge in pagina numai ca sir scapat, citit cu JSON.parse. Pagina vorbeste cu enigma2 prin mesajele WebKit
 * "hdshbbtv": lansatorul lasa sa treaca numai comenzile cunoscute, cu semne dintr-o lista scurta (numere, ccid,
 * base64), cel mult 40 pe secunda, ca randuri "HDS-NAV HBBTV ...". Fara fisierul scriptului: "HDS-NAV HBBTV strat 0
 * lipsa" si aplicatia merge ca in H2 (fara obiecte). Cu --hbbtv, "ascunde" (Application.hide) goleste intai ce s-a
 * desenat, ca imaginea canalului sa se vada cat aplicatia e ascunsa.
 *
 * Etapele H4 si H6 (0.6.0): in modul HbbTV culorile semitransparente se depremultiplica la copierea pe ecran (stratul
 * grafic al u57 amesteca nepremultiplicat, vezi depremul_rand); fereastra video (pozitia si marimea video/broadcast,
 * comanda paginii "fereastra x y l i") o muta enigma2, care are drept de scriere in /proc/stb/vmpeg/0. Comanda
 * "vizibil 0|1" ascunde pagina fata de WebKit (aplicatia pornita automat si inca nevazuta nu deseneaza). Captura cu o
 * cale ".pam" pastreaza si alfa.
 *
 * --utilizator NUME: dupa deschiderea framebufferului si a intrarilor (care cer root), lansatorul coboara pe acel
 * utilizator (initgroups, setgid, setuid; se opreste daca nu reuseste) inainte de proba EGL si de WebKit, deci si
 * procesele WebKit ruleaza fara root (paginile HbbTV sunt JavaScript strain, pornit la o simpla apasare de ROSU).
 *
 * Stratul lansatorului (numai in afara modului HbbTV): peste cadrul paginii, direct pe ecran, lansatorul deseneaza
 * chenarul elementului cu focalizare (--chenar), care pulseaza o data pe secunda. Nu e CSS pus in pagina, deci situl
 * nu-l poate ascunde sau strica; dreptunghiul elementului il trimite scriptul injectat SCRIPT_CHENAR. Tot in strat,
 * jos pe mijloc, textele de ajutor (traduse de enigma2, date cu --text CHEIE=base64, desenate cu FreeType): „OK sau
 * TEXT: scrie” cat un camp de text are focalizarea, „Niciun câmp de scris pe ecran” dupa TEXT fara camp.
 *
 * Stilul chenarului (lotul chenar-027, ales de om in Setari navigator web): --chenar-culoare (galben, alb, verde,
 * albastru, portocaliu, rosu, auto = contrast automat: galben pe pagina inchisa, albastru inchis pe cea deschisa, dupa
 * luminozitatea paginii de sub chenar), --chenar-forma (dreptunghi, rotunjit, subliniere, fundal = culoarea
 * semitransparenta peste element), --chenar-grosime (subtire, normal, gros) si --chenar-puls (oprit, lent, normal,
 * rapid). Fara ele (valorile din fabrica) chenarul e exact cel din 0.4.0: galben, dreptunghi, banda de 2,5 puncte CSS,
 * un puls pe secunda. Cat ruleaza, comanda "chenar <0|1> <culoare> <forma> <grosime> <puls>" il schimba pe loc
 * (raspunsul "HDS-NAV CHENAR ..." sau "HDS-NAV EROARE chenar"); repornirea pe procesor pastreaza stilul de acum.
 *
 * Meniurile care se deschid numai sub mouse (regulile CSS cu :hover, de pilda "other files" dintr-o interfata web cu
 * meniu pe randuri): SCRIPT_MENIURI copiaza fiecare regula :hover a paginii intr-o foaie proprie, cu :focus-within in loc
 * de :hover, deci meniul se deschide si cand legatura lui primeste focalizarea de la sageti (si ramane deschis cat
 * focalizarea e intr-un rand al lui). Numai in afara modului HbbTV; foile din alta origine nu se pot citi si raman cum
 * sunt. Listele derulante (<select>) au fereastra lor de alegere in enigma2 ("CERERE alegere").
 *
 * Scrisul: OK pe un camp de text sau tasta TEXT cer tastatura enigma2 („CERERE tastatura ...”); TEXT fara camp cu
 * focalizare da focalizarea primului camp de text care se vede pe ecran.
 *
 * Indicatorul (mouse din sageti): ALBASTRU il porneste si il opreste (MENU si INFO raman meniul navigatorului).
 * Pornit, sagetile misca o sageata desenata in strat (cu accelerare cat sunt tinute), OK face clic (evenimente de
 * indicator WPE: miscare, apasare, eliberare), iar la marginea ecranului pagina se deruleaza (evenimente de derulare
 * in pozitia sagetii, deci si casetele derulabile din pagina). Oprit, sagetile revin la navigarea spatiala.
 *
 * Raspunsul la taste (in afara modului HbbTV): derularea fara animatie (setarea WebKit „smooth scrolling” e pornita
 * implicit, iar multe situri cer scroll-behavior: smooth; o foaie de stil a utilizatorului o anuleaza), deci
 * navigarea spatiala si CH+/CH- muta pagina in cadrul urmator. Pentru masurare, dupa fiecare tasta trimisa paginii:
 * „TIMP tasta-cadru MS” (primul cadru dupa ea), „TIMP tasta-chenar MS” (chenarul a ajuns pe noul element) si
 * „TIMP tasta-gata MS CADRE” (ultimul cadru inainte de 300 ms de liniste).
 *
 * Din 0.7.0, numai in modul HbbTV:
 * - Traducerea textelor paginii prin receptor: comanda paginii "tradu ID BASE64" (ID din cifre si litere mici, cel mult
 *   16; BASE64 = JSON-ul facut de pagina) trece spre enigma2 ca orice comanda, cu un debit al ei
 *   (HBBTV_TRADU_PE_SECUNDA), ca traducerile sa nu ia locul comenzilor aplicatiei; raspunsul vine ca eveniment
 *   ("hbbtv-ev", care primeste acum si raspunsuri mari, HBBTV_EV_MAXIM). Merge si in paginile https, unde scriptul
 *   paginii nu poate chema interfata web a receptorului (continut amestecat). Scriptul paginii afla ce stie lansatorul
 *   din window.__hdsHbbtvStare.lansator (versiunea, comenzile noi, schema dvb).
 * - Schema dvb:// (ETSI TS 102 851, ETSI TS 102 796 cap. 9.2): dvb://<onid>.[<tsid>].<sid>.<component_tag>[$<id>]/<cale>
 *   se citeste din arborele caruselului scris de enigma2 in <--dvb-dosar>/<onid>.<tsid>.<sid>.<tag> (hex mic, implicit
 *   /tmp/hds-carusel), acelasi dosar pe care il da si serverul local al receptorului: pagina din carusel poate fi
 *   deschisa direct cu adresa dvb://, iar adresele dvb:// ramase intr-o pagina data de serverul local merg si ele. Calea
 *   se verifica bucata cu bucata (fara "." sau "..", fara "/" sau "\" codate, fara caractere de control, fara legaturi
 *   simbolice: fiecare bucata se deschide cu O_NOFOLLOW din dosarul de dinainte), numai fisiere obisnuite de cel mult
 *   DVB_FISIER_MAXIM; un dosar da numele din el despartite prin virgula (TS 102 796 V1.2.1 Tabelul 10); lipsa = 404.
 *   Un fisier care inca nu a venit se asteapta cel mult DVB_ASTEPTARE_MS, numai cat manifestul (<dosar>.json) nu spune
 *   "complet". Tipul: content_type din manifest, altfel dupa extensie (o pagina .html care se declara XHTML primeste
 *   tipul paginilor HbbTV). Raspunsurile au Access-Control-Allow-Origin: * (fisierele caruselului nu se opresc pentru
 *   CORS, TS 102 796 V1.4.1 cap. 9.2) si Cache-Control: no-store. Schema nu e "sigura" (o pagina din carusel poate cere
 *   resurse http://, ca la televizoare).
 * - Erorile JavaScript ale paginii (exceptiile neprinse, promisiunile respinse fara tratare, console.error, scripturile
 *   si foile de stil care nu s-au incarcat) merg pe iesirea de erori, cate un rand "hds-navigator: pagina: ...", fara
 *   adrese (numai numele fisierului), cel mult ERORI_JS_PE_DOCUMENT pe document, ERORI_JS_PE_SECUNDA pe secunda si
 *   ERORI_JS_MAXIM de la pornire: enigma2 le pune in jurnalul erorilor navigatorului.
 * - Cache-ul paginilor: modelul DOCUMENT_BROWSER (cel mult 20 MB pe disc cand dosarul cache-ului are sub 4 GB liberi,
 *   16 MB in memorie), in locul celui de navigator obisnuit (100 MB pe disc pe /tmp, care e memorie).
 * - Partile starii venite una dupa alta (la "HBBTV strat 1" enigma2 trimite sase) refac scriptul paginilor o singura
 *   data, cand nu mai e nimic de citit (si oricum inaintea oricarei navigari); o parte neschimbata nu il reface.
 * - Pagina care nu se deschide: "EROARE-INCARCARE dns" cand numele gazdei nu exista (G_RESOLVER_ERROR_NOT_FOUND),
 *   "retea" si pentru erorile de legatura (fara DNS, legatura refuzata, termen depasit, retea de neatins).
 *
 * Din 0.7.0-r2, numai in modul HbbTV: comanda paginii "av" (filmele aplicatiilor, obiectul A/V din hds-hbbtv.js: porneste,
 * viteza, cauta, opreste, fereastra, ecran-intreg, pista) trece spre enigma2 ca celelalte comenzi (aceleasi semne,
 * acelasi debit); playerul e al receptorului. Scriptul paginii afla ca lansatorul o lasa din
 * window.__hdsHbbtvStare.lansator.av.
 */

#include <wpe/webkit.h>
#include <wpe/wpe-platform.h>
#include <libsoup/soup.h>

#include <ft2build.h>
#include FT_FREETYPE_H

#include <dirent.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <glib-unix.h>
#include <grp.h>
#include <linux/fb.h>
#include <linux/input.h>
#include <pwd.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

/* Versiunea lansatorului, spusa scriptului paginilor HbbTV (window.__hdsHbbtvStare.lansator); reteta o da din PV. */
#ifndef HDS_NAV_VERSIUNE
#define HDS_NAV_VERSIUNE "0.7.0"
#endif

/* ---------------------------------------------------------------- optiuni */

static struct {
    char *url;
    char *fb;
    char *captura;
    char **intrari;
    char *date;
    int latime;
    int inaltime;
    double scara;
    double marire;
    gboolean cpu;
    gboolean pictura_cpu;
    gboolean efemer;
    int port_certificat;
    int memorie_mb;
    int captura_dupa_ms;
    int iesire_dupa_s;
    gboolean ascuns;
    char *numai_gazda;
    char *gazda_certificat;
    int font_minim;
    gboolean marire_auto;
    int oom;
    char *limba;
    char *cache;
    gboolean hbbtv;
    char *agent_adaugat;
    char *utilizator;
    gboolean chenar;
    char *chenar_culoare;
    char *chenar_forma;
    char *chenar_grosime;
    char *chenar_puls;
    char **texte;
    char *font;
    char *hbbtv_js;
    char **hbbtv_parti;
    gboolean marire_copiere;
    char *dvb_dosar;
} opt = {
    .latime = 1280,
    .inaltime = 720,
    .scara = 1.0,
    .marire = 1.0,
    .captura_dupa_ms = 1500,
    .oom = -10000,
};

static GOptionEntry intrari_optiuni[] = {
    { "fb", 0, 0, G_OPTION_ARG_FILENAME, &opt.fb, "Dispozitivul framebuffer (de exemplu /dev/fb0); fara el, panza din memorie", "CALE" },
    { "captura", 0, 0, G_OPTION_ARG_FILENAME, &opt.captura, "Scrie ecranul ca PPM dupa prima pagina", "CALE" },
    { "captura-dupa-ms", 0, 0, G_OPTION_ARG_INT, &opt.captura_dupa_ms, "Intarzierea capturii dupa incarcare", "MS" },
    { "intrare", 0, 0, G_OPTION_ARG_FILENAME_ARRAY, &opt.intrari, "Dispozitiv evdev al telecomenzii (se poate repeta)", "CALE" },
    { "latime", 0, 0, G_OPTION_ARG_INT, &opt.latime, "Latimea paginii in puncte CSS", "N" },
    { "inaltime", 0, 0, G_OPTION_ARG_INT, &opt.inaltime, "Inaltimea paginii in puncte CSS", "N" },
    { "scara", 0, 0, G_OPTION_ARG_DOUBLE, &opt.scara, "Puncte de ecran pe punct CSS (1.5 pentru 1280 -> 1920)", "F" },
    { "marire", 0, 0, G_OPTION_ARG_DOUBLE, &opt.marire, "Marirea paginii (zoom-level)", "F" },
    { "cpu", 0, 0, G_OPTION_ARG_NONE, &opt.cpu, "Fara accelerare: pagina desenata si compusa cu procesorul", NULL },
    { "pictura-cpu", 0, 0, G_OPTION_ARG_NONE, &opt.pictura_cpu, "Pagina desenata cu procesorul (Skia), compunerea pe GLES", NULL },
    { "efemer", 0, 0, G_OPTION_ARG_NONE, &opt.efemer, "Nimic pe disc (cookie-uri, cache)", NULL },
    { "date", 0, 0, G_OPTION_ARG_FILENAME, &opt.date, "Dosarul profilului (fara --efemer)", "CALE" },
    { "certificat-local", 0, 0, G_OPTION_ARG_INT, &opt.port_certificat, "Primeste certificatul propriu numai pentru 127.0.0.1:PORT", "PORT" },
    { "memorie-mb", 0, 0, G_OPTION_ARG_INT, &opt.memorie_mb, "Limita de memorie a procesului web", "MB" },
    { "iesire-dupa-s", 0, 0, G_OPTION_ARG_INT, &opt.iesire_dupa_s, "Iese singur dupa atatea secunde (probe)", "S" },
    { "ascuns", 0, 0, G_OPTION_ARG_NONE, &opt.ascuns, "Nu scrie pe framebuffer si nu apuca telecomanda pana la comanda arata", NULL },
    { "numai-gazda", 0, 0, G_OPTION_ARG_STRING, &opt.numai_gazda, "Navigarea permisa numai spre aceasta gazda si acest port", "GAZDA:PORT" },
    { "gazda-certificat", 0, 0, G_OPTION_ARG_STRING, &opt.gazda_certificat, "Gazda pentru --certificat-local (implicit 127.0.0.1)", "GAZDA" },
    { "font-minim", 0, 0, G_OPTION_ARG_INT, &opt.font_minim, "Marimea minima a literelor, in puncte CSS", "N" },
    { "marire-auto", 0, 0, G_OPTION_ARG_NONE, &opt.marire_auto, "Pagina mai lata decat ecranul se micsoreaza pana incape", NULL },
    { "oom", 0, 0, G_OPTION_ARG_INT, &opt.oom, "Valoarea scrisa in /proc/self/oom_score_adj la pornire", "N" },
    { "limba", 0, 0, G_OPTION_ARG_STRING, &opt.limba, "Limba preferata a paginilor (de exemplu ro)", "COD" },
    { "cache", 0, 0, G_OPTION_ARG_FILENAME, &opt.cache, "Dosarul cache-ului (implicit <date>/cache)", "CALE" },
    { "hbbtv", 0, 0, G_OPTION_ARG_NONE, &opt.hbbtv, "Modul HbbTV: fundal transparent, tastele HbbTV, constantele VK_*", NULL },
    { "agent-adaugat", 0, 0, G_OPTION_ARG_STRING, &opt.agent_adaugat, "Text adaugat la sfarsitul User-Agent-ului (partea HbbTV)", "TEXT" },
    { "utilizator", 0, 0, G_OPTION_ARG_STRING, &opt.utilizator, "Dupa deschiderea dispozitivelor, ruleaza ca acest utilizator (nu root)", "NUME" },
    { "chenar", 0, 0, G_OPTION_ARG_NONE, &opt.chenar, "Chenarul pe elementul cu focalizare, desenat de lansator peste pagina", NULL },
    { "chenar-culoare", 0, 0, G_OPTION_ARG_STRING, &opt.chenar_culoare, "Culoarea chenarului: galben (implicit), alb, verde, albastru, portocaliu, rosu, auto", "NUME" },
    { "chenar-forma", 0, 0, G_OPTION_ARG_STRING, &opt.chenar_forma, "Forma chenarului: dreptunghi (implicit), rotunjit, subliniere, fundal", "NUME" },
    { "chenar-grosime", 0, 0, G_OPTION_ARG_STRING, &opt.chenar_grosime, "Grosimea chenarului: subtire, normal (implicit), gros", "NUME" },
    { "chenar-puls", 0, 0, G_OPTION_ARG_STRING, &opt.chenar_puls, "Pulsul chenarului: oprit, lent, normal (implicit), rapid", "NUME" },
    { "text", 0, 0, G_OPTION_ARG_STRING_ARRAY, &opt.texte, "Un text al stratului, tradus: scrie, fara-camp (se poate repeta)", "CHEIE=BASE64" },
    { "font", 0, 0, G_OPTION_ARG_FILENAME, &opt.font, "Fontul textelor stratului (implicit DejaVu Sans Bold)", "CALE" },
    { "hbbtv-js", 0, 0, G_OPTION_ARG_FILENAME, &opt.hbbtv_js, "Scriptul obiectelor HbbTV (implicit /usr/share/hds-navigator/hds-hbbtv.js)", "CALE" },
    { "hbbtv-parte", 0, 0, G_OPTION_ARG_STRING_ARRAY, &opt.hbbtv_parti, "O parte a starii HbbTV, JSON in base64 (se poate repeta)", "CHEIE=BASE64" },
    { "marire-la-copiere", 0, 0, G_OPTION_ARG_NONE, &opt.marire_copiere, "Modul HbbTV cu --scara 1.5: pagina desenata la scara 1 (1280x720) si marita de 1,5 ori la copierea pe ecran", NULL },
    { "dvb-dosar", 0, 0, G_OPTION_ARG_FILENAME, &opt.dvb_dosar, "Modul HbbTV: dosarul arborilor de carusel pentru adresele dvb:// (implicit /tmp/hds-carusel)", "CALE" },
    { NULL }
};

/* ---------------------------------------------------------------- rezerva GPU -> procesor */

/* Constantele EGL folosite de proba (EGL 1.4 si EGL_MESA_platform_surfaceless): lansatorul nu cere anteturi
 * EGL la constructie si nu e legat de libEGL, deci porneste si pe receptoare fara nicio biblioteca EGL. */
#define HDS_EGL_EXTENSIONS 0x3055
#define HDS_EGL_PLATFORM_SURFACELESS_MESA 0x31DD

typedef void *(*hds_egl_get_display)(void *);
typedef void *(*hds_egl_get_platform_display)(unsigned int, void *, const int *);
typedef unsigned int (*hds_egl_initialize)(void *, int *, int *);
typedef unsigned int (*hds_egl_terminate)(void *);
typedef const char *(*hds_egl_query_string)(void *, int);
typedef void *(*hds_egl_get_proc_address)(const char *);

/* In procesul copil: aceeasi ordine ca procesul web WPE fara GBM (ecranul „surfaceless”, apoi cel implicit). */
static int egl_proba_copil(void)
{
    void *lib = dlopen("libEGL.so.1", RTLD_NOW | RTLD_LOCAL);
    if (!lib)
        return 2;
    hds_egl_get_display get_display = (hds_egl_get_display)dlsym(lib, "eglGetDisplay");
    hds_egl_initialize initialize = (hds_egl_initialize)dlsym(lib, "eglInitialize");
    hds_egl_terminate terminate = (hds_egl_terminate)dlsym(lib, "eglTerminate");
    hds_egl_query_string query_string = (hds_egl_query_string)dlsym(lib, "eglQueryString");
    hds_egl_get_proc_address get_proc = (hds_egl_get_proc_address)dlsym(lib, "eglGetProcAddress");
    if (!get_display || !initialize || !terminate)
        return 3;

    void *d = NULL;
    const char *ext = query_string ? query_string(NULL, HDS_EGL_EXTENSIONS) : NULL;
    if (ext && strstr(ext, "EGL_MESA_platform_surfaceless") && get_proc) {
        hds_egl_get_platform_display gpd = (hds_egl_get_platform_display)get_proc("eglGetPlatformDisplayEXT");
        if (gpd) {
            d = gpd(HDS_EGL_PLATFORM_SURFACELESS_MESA, NULL, NULL);
            if (d && !initialize(d, NULL, NULL))
                d = NULL;
        }
    }
    if (!d) {
        d = get_display(NULL);
        if (d && !initialize(d, NULL, NULL))
            d = NULL;
    }
    if (!d)
        return 4;
    terminate(d);
    return 0;
}

/* Proba EGL intr-un proces copil: driverul nu ramane incarcat in lansator, iar daca se blocheaza (5 s) sau cade,
 * lansatorul merge mai departe pe procesor. Intoarce NULL cand GL se poate folosi, altfel motivul. */
static const char *egl_proba(void)
{
    fflush(stdout);
    fflush(stderr);
    pid_t pid = fork();
    if (pid < 0)
        return NULL; /* fara proba se incearca GL; daca procesul web cade, repornirea trece pe procesor */
    if (pid == 0) {
        int nul = open("/dev/null", O_WRONLY | O_CLOEXEC);
        if (nul >= 0) {
            dup2(nul, STDOUT_FILENO);
            dup2(nul, STDERR_FILENO);
        }
        alarm(5);
        _exit(egl_proba_copil());
    }
    int st = 0;
    while (waitpid(pid, &st, 0) < 0) {
        if (errno != EINTR)
            return "fara-proba";
    }
    if (WIFEXITED(st)) {
        switch (WEXITSTATUS(st)) {
        case 0: return NULL;
        case 2: return "fara-libEGL";
        case 3: return "libEGL-incomplet";
        default: return "fara-ecran-EGL";
        }
    }
    return WIFSIGNALED(st) && WTERMSIG(st) == SIGALRM ? "EGL-blocat" : "EGL-cazut";
}

/* ---------------------------------------------------------------- iesirea (ecranul) */

static struct {
    int fd;
    guint8 *mem;
    gsize marime;
    int latime;
    int inaltime;
    int pas;          /* octeti pe rand */
    gboolean este_fb;
    gboolean format_anuntat;
    gboolean ascuns;  /* framebufferul e al enigma2: cadrele raman numai in tamponul paginii */
} ecran = { .fd = -1 };

/* Copia intreaga a paginii (ARGB8888 premultiplicat, ca tamponul WPE), tinuta la zi din zonele fiecarui cadru, si cat
 * lansatorul e ascuns. Cu desenul pe procesor WPE 2.54 pune in tamponul unui cadru numai zonele schimbate (restul
 * tamponului nu e pagina; proba x86 H3 cu WPE-ul nostru): de aceea pe ecran se copiaza din aceasta copie, iar
 * redesenarea intreaga (la "arata") si stergerea stratului se fac tot din ea, nu din tamponul cel mai nou. */
static struct {
    guint8 *mem;
    int latime;
    int inaltime;
} copie_pagina;

/* --marire-la-copiere (lotul h4-h6; desenul pe procesor e lent la 1920x1080): WebKit
 * deseneaza pagina HbbTV la scara 1 (1280x720, de 2,25 ori mai putini pixeli), iar lansatorul o mareste de 1,5 ori la
 * copierea pe ecran: fiecare bloc de 2x2 pixeli ai paginii da 3x3 pe ecran (colturile copiate, marginile media a doi,
 * mijlocul media celor patru), in valori premultiplicate, apoi depremultiplicate. */
static gboolean ecran_x15;

static gboolean ecran_deschide_fb(const char *cale)
{
    struct fb_var_screeninfo v;
    struct fb_fix_screeninfo f;

    ecran.fd = open(cale, O_RDWR | O_CLOEXEC);
    if (ecran.fd < 0) {
        g_printerr("HDS-NAV EROARE fb-deschidere %d\n", errno);
        return FALSE;
    }
    if (ioctl(ecran.fd, FBIOGET_VSCREENINFO, &v) < 0 || ioctl(ecran.fd, FBIOGET_FSCREENINFO, &f) < 0) {
        g_printerr("HDS-NAV EROARE fb-ioctl %d\n", errno);
        return FALSE;
    }
    if (v.bits_per_pixel != 32) {
        g_printerr("HDS-NAV EROARE fb-bpp %u\n", v.bits_per_pixel);
        return FALSE;
    }
    ecran.marime = f.smem_len;
    ecran.mem = mmap(NULL, ecran.marime, PROT_READ | PROT_WRITE, MAP_SHARED, ecran.fd, 0);
    if (ecran.mem == MAP_FAILED) {
        ecran.mem = NULL;
        g_printerr("HDS-NAV EROARE fb-mmap %d\n", errno);
        return FALSE;
    }
    ecran.latime = v.xres;
    ecran.inaltime = v.yres;
    ecran.pas = f.line_length;
    ecran.este_fb = TRUE;
    return TRUE;
}

/* Pagina vizibila: enigma2 tine doua pagini (yres_virtual = 2 * yres) si o alege cu FBIOPAN_DISPLAY. */
static guint8 *ecran_pagina_vizibila(void)
{
    if (!ecran.este_fb)
        return ecran.mem;
    struct fb_var_screeninfo v;
    if (ioctl(ecran.fd, FBIOGET_VSCREENINFO, &v) < 0)
        return ecran.mem;
    gsize deplasare = (gsize)v.yoffset * ecran.pas + (gsize)v.xoffset * 4;
    if (deplasare + (gsize)ecran.inaltime * ecran.pas > ecran.marime)
        deplasare = 0;
    return ecran.mem + deplasare;
}

static void ecran_panza_asigura(int latime, int inaltime)
{
    if (ecran.este_fb || (ecran.mem && ecran.latime == latime && ecran.inaltime == inaltime))
        return;
    g_free(ecran.mem);
    ecran.latime = latime;
    ecran.inaltime = inaltime;
    ecran.pas = latime * 4;
    ecran.marime = (gsize)ecran.pas * inaltime;
    ecran.mem = g_malloc0(ecran.marime);
}

/* Depremultiplicarea (lotul h4-h6, masurat pe receptorul de proba): WebKit da ARGB premultiplicat (rosul de 50 % = 00 00 80 80 in
 * octetii B G R A), iar stratul grafic al u57 amesteca NEPREMULTIPLICAT (/proc/msp/hifb0: "Register Open Premul :
 * false"; asa scrie si enigma2 ferestrele ei semitransparente): fara conversie culorile semitransparente ale paginii ies
 * inmultite de doua ori cu alfa peste imaginea canalului (albul de 50 % ca un gri de 25 %). In modul HbbTV (fundal
 * transparent) fiecare pixel cu 0 < a < 255 se copiaza pe ecran ca C = rotunjit(C * 255 / a), dintr-o tabela 256x256
 * (64 KB, exacta); a = 0 si a = 255 raman cum sunt (copia paginii ramane premultiplicata, ea e sursa redesenarilor). Blocul dintre
 * DEPREMUL-INCEPUT si DEPREMUL-SFARSIT e C simplu (fara glib): testul de pe PC il compileaza singur si il compara cu
 * formula exacta pe toate cele 65 536 de perechi (a, C). */
/* DEPREMUL-INCEPUT */
static unsigned char depremul_tab[256][256];   /* [a][C premultiplicat] -> C nepremultiplicat */

static void depremul_pregateste(void)
{
    for (unsigned int a = 0; a < 256; a++) {
        for (unsigned int c = 0; c < 256; c++) {
            unsigned int v = c;
            if (a != 0 && a != 255) {
                v = (c * 255u + a / 2) / a;
                if (v > 255u)
                    v = 255u;
            }
            depremul_tab[a][c] = (unsigned char)v;
        }
    }
}

/* n pixeli ARGB8888 premultiplicati (B G R A in memorie) din src, nepremultiplicati in dest. */
static void depremul_rand(unsigned char *dest, const unsigned char *src, int n)
{
    for (int i = 0; i < n; i++, src += 4, dest += 4) {
        unsigned int a = src[3];
        if (a == 0 || a == 255) {
            dest[0] = src[0];
            dest[1] = src[1];
            dest[2] = src[2];
            dest[3] = (unsigned char)a;
            continue;
        }
        const unsigned char *t = depremul_tab[a];
        dest[0] = t[src[0]];
        dest[1] = t[src[1]];
        dest[2] = t[src[2]];
        dest[3] = (unsigned char)a;
    }
}
/* DEPREMUL-SFARSIT */

/* Un pixel pe ecran din valori premultiplicate (deja mediate), depremultiplicat din tabela, ca in depremul_rand. */
static inline void pune_x15(guint8 *d, unsigned int b, unsigned int g, unsigned int r, unsigned int a)
{
    const unsigned char *t = depremul_tab[a];
    d[0] = t[b];
    d[1] = t[g];
    d[2] = t[r];
    d[3] = (guint8)a;
}

/* un pixel al paginii; media a doi (rotunjita); media a patru (rotunjita) */
#define pune_x15_1(o, p) pune_x15((o), (p)[0], (p)[1], (p)[2], (p)[3])
#define pune_x15_2(o, p, q) pune_x15((o), ((p)[0] + (q)[0] + 1u) >> 1, ((p)[1] + (q)[1] + 1u) >> 1, \
    ((p)[2] + (q)[2] + 1u) >> 1, ((p)[3] + (q)[3] + 1u) >> 1)
#define pune_x15_4(o, p, q, u, v) pune_x15((o), ((p)[0] + (q)[0] + (u)[0] + (v)[0] + 2u) >> 2, \
    ((p)[1] + (q)[1] + (u)[1] + (v)[1] + 2u) >> 2, ((p)[2] + (q)[2] + (u)[2] + (v)[2] + 2u) >> 2, \
    ((p)[3] + (q)[3] + (u)[3] + (v)[3] + 2u) >> 2)

/* Zonele copiei paginii (1280x720) pe ecran marite de 1,5 ori: blocul de 2x2 de la (x, y) devine 3x3 la (3x/2, 3y/2).
 * Zonele se largesc la coordonate pare (blocurile nu depind unele de altele). n_zone 0: toata pagina. */
static void ecran_x15_copiaza(guint8 *dest, const WPERectangle *zone, guint n_zone)
{
    int bl = copie_pagina.latime & ~1, bi = copie_pagina.inaltime & ~1;
    WPERectangle tot = { 0, 0, bl, bi };
    if (!n_zone) {
        zone = &tot;
        n_zone = 1;
    }
    for (guint z = 0; z < n_zone; z++) {
        int x0 = MAX(zone[z].x, 0) & ~1, y0 = MAX(zone[z].y, 0) & ~1;
        int x1 = MIN((zone[z].x + zone[z].width + 1) & ~1, bl), y1 = MIN((zone[z].y + zone[z].height + 1) & ~1, bi);
        for (int y = y0; y < y1; y += 2) {
            int dy = y / 2 * 3;
            if (dy + 2 >= ecran.inaltime)
                break;
            const guint8 *s0 = copie_pagina.mem + (gsize)y * copie_pagina.latime * 4;
            const guint8 *s1 = s0 + (gsize)copie_pagina.latime * 4;
            guint8 *d0 = dest + (gsize)dy * ecran.pas;
            guint8 *d1 = d0 + ecran.pas;
            guint8 *d2 = d1 + ecran.pas;
            for (int x = x0; x < x1; x += 2) {
                int dx = x / 2 * 3;
                if (dx + 2 >= ecran.latime)
                    break;
                const guint8 *a = s0 + x * 4, *b = a + 4, *c = s1 + x * 4, *d = c + 4;
                guint8 *o0 = d0 + dx * 4, *o1 = d1 + dx * 4, *o2 = d2 + dx * 4;
                guint32 ga, gb, gc, gd;
                memcpy(&ga, a, 4);
                memcpy(&gb, b, 4);
                memcpy(&gc, c, 4);
                memcpy(&gd, d, 4);
                if (!(ga | gb | gc | gd)) {
                    /* blocul gol (transparent, premultiplicat = 0): 3x3 de zero */
                    memset(o0, 0, 12);
                    memset(o1, 0, 12);
                    memset(o2, 0, 12);
                    continue;
                }
                pune_x15_1(o0, a);
                pune_x15_2(o0 + 4, a, b);
                pune_x15_1(o0 + 8, b);
                pune_x15_2(o1, a, c);
                pune_x15_4(o1 + 4, a, b, c, d);
                pune_x15_2(o1 + 8, b, d);
                pune_x15_1(o2, c);
                pune_x15_2(o2 + 4, c, d);
                pune_x15_1(o2 + 8, d);
            }
        }
    }
}

/* Zonele din copia paginii pe ecran (pagina vizibila a fb0 sau panza din memorie); n_zone 0: toata pagina. Nimic cat
 * ecranul e al enigma2 (ascuns pe fb0); in modul HbbTV nici pe panza, ca proba sa vada aplicatia ascunsa. In modul HbbTV
 * pixelii semitransparenti se depremultiplica (mai sus). */
static void ecran_din_pagina(const WPERectangle *zone, guint n_zone)
{
    if (!copie_pagina.mem)
        return;
    int bl = copie_pagina.latime, bi = copie_pagina.inaltime;
    ecran_panza_asigura(ecran_x15 ? bl * 3 / 2 : bl, ecran_x15 ? bi * 3 / 2 : bi);
    if (ecran.ascuns && (ecran.este_fb || opt.hbbtv))
        return;
    if (!ecran.format_anuntat && ((ecran_x15 ? bl * 3 / 2 : bl) != ecran.latime || (ecran_x15 ? bi * 3 / 2 : bi) != ecran.inaltime)) {
        g_printerr("HDS-NAV AVERTISMENT marimi-diferite pagina %dx%d ecran %dx%d\n", bl, bi, ecran.latime, ecran.inaltime);
        ecran.format_anuntat = TRUE;
    }
    guint8 *dest = ecran_pagina_vizibila();
    if (ecran_x15) {
        ecran_x15_copiaza(dest, zone, n_zone);
        return;
    }
    WPERectangle tot = { 0, 0, bl, bi };
    if (!n_zone) {
        zone = &tot;
        n_zone = 1;
    }
    for (guint z = 0; z < n_zone; z++) {
        int x0 = MAX(zone[z].x, 0), y0 = MAX(zone[z].y, 0);
        int x1 = MIN(zone[z].x + zone[z].width, MIN(bl, ecran.latime));
        int y1 = MIN(zone[z].y + zone[z].height, MIN(bi, ecran.inaltime));
        if (x1 <= x0 || y1 <= y0)
            continue;
        gsize octeti = (gsize)(x1 - x0) * 4;
        for (int y = y0; y < y1; y++) {
            guint8 *d = dest + (gsize)y * ecran.pas + (gsize)x0 * 4;
            const guint8 *s = copie_pagina.mem + ((gsize)y * bl + x0) * 4;
            if (opt.hbbtv)
                depremul_rand(d, s, x1 - x0);
            else
                memcpy(d, s, octeti);
        }
    }
}

/* Dreptunghiurile schimbate din tamponul SHM al unui cadru (ARGB8888 premultiplicat, acelasi format ca OSD-ul): intai
 * in copia paginii, apoi pe ecran. Primul tampon (sau o alta marime) intra intreg in copie; un cadru fara zone nu
 * schimba nimic (cu desenul pe procesor tamponul lui are numai o parte din pagina; proba H3 cu tampoanele scrise pe
 * disc). */
static void ecran_afiseaza(WPEBufferSHM *tampon, const WPERectangle *zone, guint n_zone)
{
    int bl = wpe_buffer_get_width(WPE_BUFFER(tampon));
    int bi = wpe_buffer_get_height(WPE_BUFFER(tampon));
    guint bpas = wpe_buffer_shm_get_stride(tampon);
    gsize n = 0;
    const guint8 *sursa = g_bytes_get_data(wpe_buffer_shm_get_data(tampon), &n);

    if (!sursa || bl <= 0 || bi <= 0 || n < (gsize)bpas * bi)
        return;
    static int zone_de_aratat = -1;
    if (zone_de_aratat < 0)
        zone_de_aratat = g_getenv("HDS_NAV_ZONE") ? 20 : 0;
    for (guint z = 0; z < n_zone && zone_de_aratat > 0; z++, zone_de_aratat--)
        g_printerr("HDS-NAV ZONA %d,%d %dx%d in tampon %dx%d\n", zone[z].x, zone[z].y, zone[z].width, zone[z].height, bl, bi);

    WPERectangle tot = { 0, 0, bl, bi };
    if (!copie_pagina.mem || copie_pagina.latime != bl || copie_pagina.inaltime != bi) {
        g_free(copie_pagina.mem);
        copie_pagina.mem = g_malloc0((gsize)bl * bi * 4);
        copie_pagina.latime = bl;
        copie_pagina.inaltime = bi;
        zone = &tot;
        n_zone = 1;
    } else if (!n_zone)
        return;
    for (guint z = 0; z < n_zone; z++) {
        int x0 = MAX(zone[z].x, 0), y0 = MAX(zone[z].y, 0);
        int x1 = MIN(zone[z].x + zone[z].width, bl), y1 = MIN(zone[z].y + zone[z].height, bi);
        if (x1 <= x0 || y1 <= y0)
            continue;
        gsize octeti = (gsize)(x1 - x0) * 4;
        for (int y = y0; y < y1; y++)
            memcpy(copie_pagina.mem + ((gsize)y * bl + x0) * 4, sursa + (gsize)y * bpas + (gsize)x0 * 4, octeti);
    }
    ecran_din_pagina(zone, n_zone);
}

/* Modul HbbTV, la iesire si la "ascunde" (Application.hide): tot ce a desenat lansatorul pe pagina vizibila devine
 * transparent (alfa 0), ca imaginea canalului sa se vada pana cand enigma2 isi redeseneaza ecranul. */
static void ecran_goleste(void)
{
    if (ecran.ascuns || !ecran.mem || (!ecran.este_fb && !opt.hbbtv))
        return;
    guint8 *p = ecran_pagina_vizibila();
    for (int y = 0; y < ecran.inaltime; y++)
        memset(p + (gsize)y * ecran.pas, 0, (gsize)ecran.latime * 4);
}

/* Captura ecranului: PPM (RGB); cu o cale care se termina in ".pam", PAM cu alfa (RGB_ALPHA), ca proba sa vada si
 * transparenta (octetii exact cum sunt pe ecran, deci in modul HbbTV nepremultiplicati). */
static gboolean ecran_scrie_ppm(const char *cale)
{
    if (!ecran.mem)
        return FALSE;
    FILE *f = fopen(cale, "wb");
    if (!f)
        return FALSE;
    const guint8 *p = ecran_pagina_vizibila();
    int cu_alfa = g_str_has_suffix(cale, ".pam") ? 1 : 0;
    int k = 3 + cu_alfa;
    if (cu_alfa)
        fprintf(f, "P7\nWIDTH %d\nHEIGHT %d\nDEPTH 4\nMAXVAL 255\nTUPLTYPE RGB_ALPHA\nENDHDR\n", ecran.latime, ecran.inaltime);
    else
        fprintf(f, "P6\n%d %d\n255\n", ecran.latime, ecran.inaltime);
    guint8 *rand = g_malloc((gsize)ecran.latime * k);
    for (int y = 0; y < ecran.inaltime; y++) {
        const guint8 *s = p + (gsize)y * ecran.pas;
        for (int x = 0; x < ecran.latime; x++) {
            rand[x * k + 0] = s[x * 4 + 2];
            rand[x * k + 1] = s[x * 4 + 1];
            rand[x * k + 2] = s[x * 4 + 0];
            if (cu_alfa)
                rand[x * k + 3] = s[x * 4 + 3];
        }
        fwrite(rand, 1, (gsize)ecran.latime * k, f);
    }
    g_free(rand);
    return fclose(f) == 0;
}

/* ---------------------------------------------------------------- platforma WPE "hds-fbdev" */

#define HDS_TYPE_KEYMAP (hds_keymap_get_type())
G_DECLARE_FINAL_TYPE(HdsKeymap, hds_keymap, HDS, KEYMAP, WPEKeymap)
struct _HdsKeymap {
    WPEKeymap parent_instance;
};
G_DEFINE_FINAL_TYPE(HdsKeymap, hds_keymap, WPE_TYPE_KEYMAP)

/* Tastele vin gata traduse (keyval) din telecomanda: nu trebuie tabele XKB pe disc. */
static gboolean hds_keymap_get_entries_for_keyval(WPEKeymap *k, guint keyval, WPEKeymapEntry **e, guint *n)
{
    (void)k; (void)keyval; (void)e; (void)n;
    return FALSE;
}

static gboolean hds_keymap_translate_keyboard_state(WPEKeymap *k, guint keycode, WPEModifiers m, int group, guint *keyval,
    int *effective_group, int *level, WPEModifiers *consumed)
{
    (void)k; (void)keycode; (void)m; (void)group; (void)keyval; (void)effective_group; (void)level; (void)consumed;
    return FALSE;
}

static WPEModifiers hds_keymap_get_modifiers(WPEKeymap *k)
{
    (void)k;
    return (WPEModifiers)0;
}

static void hds_keymap_class_init(HdsKeymapClass *klass)
{
    WPEKeymapClass *kc = WPE_KEYMAP_CLASS(klass);
    kc->get_entries_for_keyval = hds_keymap_get_entries_for_keyval;
    kc->translate_keyboard_state = hds_keymap_translate_keyboard_state;
    kc->get_modifiers = hds_keymap_get_modifiers;
}

static void hds_keymap_init(HdsKeymap *self)
{
    (void)self;
}

#define HDS_TYPE_TOPLEVEL (hds_toplevel_get_type())
G_DECLARE_FINAL_TYPE(HdsToplevel, hds_toplevel, HDS, TOPLEVEL, WPEToplevel)
struct _HdsToplevel {
    WPEToplevel parent_instance;
};
G_DEFINE_FINAL_TYPE(HdsToplevel, hds_toplevel, WPE_TYPE_TOPLEVEL)

static gboolean hds_toplevel_view_resized(WPEToplevel *t, WPEView *v, gpointer data)
{
    (void)data;
    int l, i;
    wpe_toplevel_get_size(t, &l, &i);
    wpe_view_resized(v, l, i);
    return FALSE;
}

static gboolean hds_toplevel_resize(WPEToplevel *t, int latime, int inaltime)
{
    wpe_toplevel_resized(t, latime, inaltime);
    wpe_toplevel_foreach_view(t, hds_toplevel_view_resized, NULL);
    return TRUE;
}

static gboolean hds_toplevel_set_fullscreen(WPEToplevel *t, gboolean da)
{
    WPEToplevelState s = wpe_toplevel_get_state(t);
    s = da ? (WPEToplevelState)(s | WPE_TOPLEVEL_STATE_FULLSCREEN) : (WPEToplevelState)(s & ~WPE_TOPLEVEL_STATE_FULLSCREEN);
    wpe_toplevel_state_changed(t, s);
    return TRUE;
}

static void hds_toplevel_constructed(GObject *o)
{
    G_OBJECT_CLASS(hds_toplevel_parent_class)->constructed(o);
    wpe_toplevel_state_changed(WPE_TOPLEVEL(o), (WPEToplevelState)(WPE_TOPLEVEL_STATE_ACTIVE | WPE_TOPLEVEL_STATE_FULLSCREEN));
}

static void hds_toplevel_class_init(HdsToplevelClass *klass)
{
    G_OBJECT_CLASS(klass)->constructed = hds_toplevel_constructed;
    WPEToplevelClass *tc = WPE_TOPLEVEL_CLASS(klass);
    tc->resize = hds_toplevel_resize;
    tc->set_fullscreen = hds_toplevel_set_fullscreen;
}

static void hds_toplevel_init(HdsToplevel *self)
{
    (void)self;
}

#define HDS_TYPE_VIEW (hds_view_get_type())
G_DECLARE_FINAL_TYPE(HdsView, hds_view, HDS, VIEW, WPEView)
struct _HdsView {
    WPEView parent_instance;
    WPEBuffer *in_asteptare;
    WPEBuffer *afisat;
    GSource *cadru;
    gint64 ultimul_cadru;
};
G_DEFINE_FINAL_TYPE(HdsView, hds_view, WPE_TYPE_VIEW)

static void (*la_cadru_afisat)(void);
static HdsView *vedere_hds;  /* singura vedere a lansatorului, pentru redesenarea dupa „arata” */
static void strat_dupa_cadru(gboolean tot);

/* Toata pagina din nou pe ecran (din copia ei, nu din tamponul cel mai nou: acela are numai zonele ultimului cadru). */
static void ecran_redeseneaza_tot(void)
{
    if (!copie_pagina.mem)
        return;
    ecran_din_pagina(NULL, 0);
    strat_dupa_cadru(TRUE);
}

static gboolean hds_view_cadru_dispatch(GSource *s, GSourceFunc cb, gpointer data)
{
    if (g_source_get_ready_time(s) == -1)
        return G_SOURCE_CONTINUE;
    g_source_set_ready_time(s, -1);
    return cb(data);
}

static GSourceFuncs hds_view_cadru_funcs = { NULL, NULL, hds_view_cadru_dispatch, NULL, NULL, NULL };

/* Ritmul de 60 de cadre pe secunda, ca la platforma headless: tamponul afisat se elibereaza la cadrul urmator. */
static gboolean hds_view_cadru(gpointer data)
{
    HdsView *self = HDS_VIEW(data);
    WPEView *v = WPE_VIEW(data);
    if (self->afisat)
        wpe_view_buffer_released(v, self->afisat);
    g_clear_object(&self->afisat);
    self->afisat = self->in_asteptare;
    self->in_asteptare = NULL;
    if (self->afisat) {
        wpe_view_buffer_rendered(v, self->afisat);
        if (la_cadru_afisat)
            la_cadru_afisat();
    }
    return G_SOURCE_CONTINUE;
}

static gboolean hds_view_render_buffer(WPEView *v, WPEBuffer *tampon, const WPERectangle *zone, guint n_zone, GError **error)
{
    HdsView *self = HDS_VIEW(v);
    if (!WPE_IS_BUFFER_SHM(tampon)) {
        g_set_error_literal(error, WPE_VIEW_ERROR, WPE_VIEW_ERROR_RENDER_FAILED, "numai tampoane in memorie partajata");
        return FALSE;
    }
    ecran_afiseaza(WPE_BUFFER_SHM(tampon), zone, n_zone);

    g_clear_object(&self->in_asteptare);
    self->in_asteptare = g_object_ref(tampon);
    strat_dupa_cadru(FALSE);
    gint64 acum = g_get_monotonic_time();
    if (!self->ultimul_cadru)
        self->ultimul_cadru = acum;
    gint64 urmator = self->ultimul_cadru + G_USEC_PER_SEC / 60;
    self->ultimul_cadru = acum;
    g_source_set_ready_time(self->cadru, urmator <= acum ? 0 : urmator);
    return TRUE;
}

static void hds_view_toplevel_schimbat(WPEView *v, GParamSpec *p, gpointer d)
{
    (void)p; (void)d;
    WPEToplevel *t = wpe_view_get_toplevel(v);
    if (!t) {
        wpe_view_unmap(v);
        return;
    }
    int l, i;
    wpe_toplevel_get_size(t, &l, &i);
    if (l && i)
        wpe_view_resized(v, l, i);
    wpe_view_map(v);
}

static void hds_view_constructed(GObject *o)
{
    G_OBJECT_CLASS(hds_view_parent_class)->constructed(o);
    HdsView *self = HDS_VIEW(o);
    vedere_hds = self;
    g_signal_connect(o, "notify::toplevel", G_CALLBACK(hds_view_toplevel_schimbat), NULL);
    self->cadru = g_source_new(&hds_view_cadru_funcs, sizeof(GSource));
    g_source_set_name(self->cadru, "hds-navigator cadru");
    g_source_set_callback(self->cadru, hds_view_cadru, o, NULL);
    g_source_attach(self->cadru, g_main_context_get_thread_default());
    g_source_set_ready_time(self->cadru, -1);
}

static void hds_view_dispose(GObject *o)
{
    HdsView *self = HDS_VIEW(o);
    if (vedere_hds == self)
        vedere_hds = NULL;
    if (self->cadru) {
        g_source_destroy(self->cadru);
        g_source_unref(self->cadru);
        self->cadru = NULL;
    }
    g_clear_object(&self->in_asteptare);
    g_clear_object(&self->afisat);
    G_OBJECT_CLASS(hds_view_parent_class)->dispose(o);
}

static void hds_view_class_init(HdsViewClass *klass)
{
    G_OBJECT_CLASS(klass)->constructed = hds_view_constructed;
    G_OBJECT_CLASS(klass)->dispose = hds_view_dispose;
    WPE_VIEW_CLASS(klass)->render_buffer = hds_view_render_buffer;
}

static void hds_view_init(HdsView *self)
{
    (void)self;
}

/* ---------------------------------------------------------------- stratul lansatorului: chenarul pe selectie */

/* Dupa fiecare cadru copiat pe ecran, stratul se deseneaza din nou deasupra (zonele copiate l-au putut acoperi). Cand
 * se muta, ce acoperea se ia inapoi din tamponul paginii cel mai nou (numai fasiile lui, nu tot ecranul). Culorile sunt
 * opace: contur inchis, banda galbena, contur inchis, ca sa se vada si pe pagini albe, si pe pagini negre. */

typedef struct {
    int x, y, l, i;
} Zona;

#define STRAT_ZONE 16
#define PULS_PAS_MS 100
#define PULS_PASI 10                  /* un ciclu de luminozitate pe secunda */
#define CULOARE_CONTUR 0xFF101010u

static struct {
    gboolean are_tinta;               /* elementul cu focalizare se vede pe ecran */
    Zona tinta;                       /* dreptunghiul lui, in pixeli de ecran */
    int faza;                         /* pasul pulsului, 0 .. PULS_PASI - 1 */
    guint puls;                       /* ceasul pulsului */
    Zona desenate[STRAT_ZONE];        /* ce a acoperit stratul pe ecran */
    int n_desenate;
    gboolean camp;                    /* elementul cu focalizare e un camp de text */
    guint ceas_fara_camp;             /* cat se arata „Niciun câmp de scris pe ecran” */
    const void *eticheta;             /* textul de jos desenat acum (Eticheta), pus din nou dupa fiecare pas al pulsului */
    int eticheta_x, eticheta_y;
} strat;

/* Indicatorul (mouse din sageti); evenimentele lui sunt mai jos, la telecomanda. */
static struct {
    gboolean activ;
    double x, y;                      /* varful sagetii, in pixeli de ecran */
    gboolean sus, jos, stanga, dreapta, apasat;
    gint64 de_la;                     /* de cand se misca (accelerarea) */
    gint64 ultim;                     /* pasul de dinainte */
    guint ceas;                       /* pasul miscarii cat o sageata e tinuta */
    guint ceas_ajutor;                /* cat se arata textul indicatorului */
    Zona zona;                        /* unde a fost desenata sageata */
    gboolean are_zona;
} ind;

static void stare(const char *text);
static char *din_b64(const char *text);
static void stare_f(const char *format, ...) G_GNUC_PRINTF(1, 2);

/* ---------------------------------------------------------------- stilul chenarului (lotul chenar-027) */

/* Culoarea, forma, grosimea si pulsul alese de om (Setari navigator web, pe televizor si in pagina web /navigator).
 * Valorile din fabrica (primele de mai jos: galben, dreptunghi, normal, normal) dau chenarul din 0.4.0. */
static const char *const CULORI_NUME[] = { "galben", "alb", "verde", "albastru", "portocaliu", "rosu", "auto", NULL };
static const guint32 CULORI_RGB[] = { 0xFFFFBE28u, 0xFFFFFFFFu, 0xFF3CDC50u, 0xFF50BEFFu, 0xFFFF8C00u, 0xFFEB2828u, 0 };
static const char *const FORME_NUME[] = { "dreptunghi", "rotunjit", "subliniere", "fundal", NULL };
static const char *const GROSIMI_NUME[] = { "subtire", "normal", "gros", NULL };
static const double GROSIMI_CSS[] = { 1.5, 2.5, 4.0 };   /* latimea benzii, in puncte CSS (4 px la 1080p: normal) */
static const int FUNDAL_ALFA[] = { 64, 96, 128 };          /* fundalul colorat: opacitatea (din 255), dupa grosime */
static const char *const PULSURI_NUME[] = { "oprit", "lent", "normal", "rapid", NULL };
static const int PULSURI_PASI[] = { 0, 2 * PULS_PASI, PULS_PASI, PULS_PASI / 2 };   /* pasi de PULS_PAS_MS pe ciclu */

#define CULOARE_AUTO 6
#define CULOARE_ALBASTRU_INCHIS 0xFF1E3C9Bu   /* contrastul automat, pe pagini deschise */
#define CULOARE_CONTUR_DESCHIS 0xFFF0F0F0u    /* conturul culorilor inchise (rosu, albastru inchis) */
#define FORMA_DREPTUNGHI 0
#define FORMA_ROTUNJIT 1
#define FORMA_SUBLINIERE 2
#define FORMA_FUNDAL 3
#define LUMINA_PAGINA_DESCHISA 150            /* contrastul automat: peste atat pagina e deschisa (albastru inchis) */
#define LUMINA_PAGINA_INCHISA 110             /* sub atat pagina e inchisa (galben); intre ele ramane alegerea veche */

static struct {
    int culoare, forma, grosime, puls;        /* indicii in tabelele de mai sus */
    gboolean auto_inchis;                     /* contrastul automat a ales albastrul inchis */
    gboolean alege_din_nou;                   /* chenarul s-a mutat: contrastul se alege din nou, cu un singur prag */
} chenar = { 0, FORMA_DREPTUNGHI, 1, 2, FALSE, TRUE };

static int index_nume(const char *const *lista, const char *nume)
{
    for (int i = 0; nume && lista[i]; i++) {
        if (!strcmp(lista[i], nume))
            return i;
    }
    return -1;
}

/* Luminozitatea unei culori (0..255). */
static guint lumina(guint32 c)
{
    return (77u * ((c >> 16) & 0xFF) + 150u * ((c >> 8) & 0xFF) + 29u * (c & 0xFF)) >> 8;
}

/* Culoarea aleasa, la luminozitatea intreaga; la contrastul automat galben sau albastru inchis. */
static guint32 chenar_culoare(void)
{
    if (chenar.culoare == CULOARE_AUTO)
        return chenar.auto_inchis ? CULOARE_ALBASTRU_INCHIS : CULORI_RGB[0];
    return CULORI_RGB[chenar.culoare];
}

/* Conturul subtire de o parte si de alta a benzii: inchis la culorile deschise (ca in 0.4.0), deschis la cele inchise. */
static guint32 chenar_contur(void)
{
    return lumina(chenar_culoare()) < 100 ? CULOARE_CONTUR_DESCHIS : CULOARE_CONTUR;
}

/* Pulsul: 1 (luminozitatea intreaga) pana la 0,5 si inapoi, un triunghi pe pasii vitezei alese; fara puls 1. Cu
 * viteza normala (PULS_PASI pasi) valorile sunt cele din 0.4.0. */
static double puls_factor(void)
{
    int n = PULSURI_PASI[chenar.puls];
    if (n <= 0)
        return 1.0;
    double d = strat.faza - n / 2.0;
    return 0.5 + 0.5 * (d < 0 ? -d : d) / (n / 2.0);
}

/* ---------------------------------------------------------------- masurarea raspunsului la taste */

#define MASURA_LINISTE_US (300 * 1000)
#define MASURA_MAXIM_US (3000 * 1000)

static struct {
    gint64 tasta;                     /* cand a plecat tasta spre pagina (0: nimic de masurat) */
    gint64 primul, ultimul;           /* primul si ultimul cadru dupa ea */
    guint cadre;
    guint ceas;
    gboolean chenar;                  /* chenarul s-a mutat dupa tasta (anuntat o data) */
} masura;

static gboolean masura_verifica(gpointer d)
{
    (void)d;
    gint64 acum = g_get_monotonic_time();
    gint64 ultim = masura.ultimul ? masura.ultimul : masura.tasta;
    if (acum - ultim < MASURA_LINISTE_US && acum - masura.tasta < MASURA_MAXIM_US)
        return G_SOURCE_CONTINUE;
    if (masura.cadre)
        stare_f("TIMP tasta-gata %d %u", (int)((masura.ultimul - masura.tasta) / 1000), masura.cadre);
    else
        stare("TIMP tasta-fara-cadru");
    masura.tasta = 0;
    masura.ceas = 0;
    return G_SOURCE_REMOVE;
}

/* O tasta a plecat spre pagina: de aici se numara pana la cadre. */
static void masura_tasta(void)
{
    masura.tasta = g_get_monotonic_time();
    masura.primul = masura.ultimul = 0;
    masura.cadre = 0;
    masura.chenar = FALSE;
    if (!masura.ceas)
        masura.ceas = g_timeout_add(50, masura_verifica, NULL);
}

static void masura_cadru(void)
{
    if (!masura.tasta)
        return;
    gint64 acum = g_get_monotonic_time();
    if (!masura.primul) {
        masura.primul = acum;
        stare_f("TIMP tasta-cadru %d", (int)((acum - masura.tasta) / 1000));
    }
    masura.ultimul = acum;
    masura.cadre++;
}

/* ---------------------------------------------------------------- textele stratului (FreeType) */

/* O eticheta gata desenata: fundal inchis opac, margine galbena, litere albe. */
typedef struct {
    guint32 *px;
    int l, i;
} Eticheta;

typedef struct {
    const char *cheie;                /* cheia din --text */
    Eticheta *e;
    gboolean incercat;
} TextStrat;

static TextStrat text_scrie = { "scrie", NULL, FALSE };
static TextStrat text_fara_camp = { "fara-camp", NULL, FALSE };
static TextStrat text_indicator = { "indicator", NULL, FALSE };
static TextStrat text_scrie_indicator = { "scrie-indicator", NULL, FALSE };

#define CULOARE_ETICHETA 0xFF1C2638u
#define CULOARE_MARGINE 0xFFF5B83Du
#define CULOARE_LITERE 0xFFFFFFFFu
#define FARA_CAMP_MS 2500

static FT_Library ft_biblioteca;
static FT_Face ft_fata;
static int ft_stare;                  /* 0 neincercat, 1 gata, -1 fara font */

/* Fontul, o singura data: --font, apoi DejaVu Sans Bold (imaginea: /usr/share/fonts/truetype; Debian: .../dejavu),
 * apoi fontul ingrosat al enigma2. Fara niciunul, stratul ramane fara texte (chenarul merge mai departe). */
static gboolean litere_gata(void)
{
    if (ft_stare)
        return ft_stare > 0;
    ft_stare = -1;
    if (FT_Init_FreeType(&ft_biblioteca)) {
        stare("AVERTISMENT fara-freetype");
        return FALSE;
    }
    const char *cai[] = { opt.font ? opt.font : "", "/usr/share/fonts/truetype/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/HdsBold.ttf" };
    for (guint k = 0; k < G_N_ELEMENTS(cai); k++) {
        if (*cai[k] && !FT_New_Face(ft_biblioteca, cai[k], 0, &ft_fata)) {
            ft_stare = 1;
            return TRUE;
        }
    }
    stare("AVERTISMENT fara-font");
    return FALSE;
}

/* sus peste fund, cu acoperirea a (0..255), pe cele trei culori; rezultatul opac */
static guint32 amesteca(guint32 fund, guint32 sus, guint a)
{
    guint32 r = 0xFF000000u;
    for (int s = 0; s < 24; s += 8) {
        guint f = (fund >> s) & 0xFF, t = (sus >> s) & 0xFF;
        r |= ((f * (255 - a) + t * a + 127) / 255) << s;
    }
    return r;
}

/* Textul UTF-8 desenat o data intr-o eticheta, cu literele inalte de `marime` pixeli (fara despartire in randuri). */
static Eticheta *eticheta_noua(const char *text, int marime)
{
    if (!text || !*text || !g_utf8_validate(text, -1, NULL) || !litere_gata()
        || FT_Set_Pixel_Sizes(ft_fata, 0, (FT_UInt)marime))
        return NULL;
    int latime = 0;
    for (const char *p = text; *p; p = g_utf8_next_char(p)) {
        if (!FT_Load_Char(ft_fata, g_utf8_get_char(p), FT_LOAD_DEFAULT))
            latime += (int)(ft_fata->glyph->advance.x >> 6);
    }
    int urcare = (int)(ft_fata->size->metrics.ascender >> 6);
    int coborare = (int)(-ft_fata->size->metrics.descender >> 6);
    int pad_x = marime * 2 / 3, pad_y = marime / 3, margine = MAX(2, marime / 12);
    if (latime <= 0 || urcare <= 0)
        return NULL;
    Eticheta *e = g_new0(Eticheta, 1);
    e->l = latime + 2 * pad_x;
    e->i = urcare + coborare + 2 * pad_y;
    e->px = g_new(guint32, (gsize)e->l * e->i);
    for (int y = 0; y < e->i; y++) {
        for (int x = 0; x < e->l; x++) {
            gboolean pe_margine = x < margine || y < margine || x >= e->l - margine || y >= e->i - margine;
            e->px[(gsize)y * e->l + x] = pe_margine ? CULOARE_MARGINE : CULOARE_ETICHETA;
        }
    }
    int pana = pad_x, baza = pad_y + urcare;
    for (const char *p = text; *p; p = g_utf8_next_char(p)) {
        if (FT_Load_Char(ft_fata, g_utf8_get_char(p), FT_LOAD_RENDER))
            continue;
        FT_GlyphSlot g = ft_fata->glyph;
        const FT_Bitmap *b = &g->bitmap;
        for (int r = 0; r < (int)b->rows; r++) {
            int y = baza - g->bitmap_top + r;
            if (y < 0 || y >= e->i)
                continue;
            for (int c = 0; c < (int)b->width; c++) {
                int x = pana + g->bitmap_left + c;
                guint a = b->buffer[r * b->pitch + c];
                if (x >= 0 && x < e->l && a)
                    e->px[(gsize)y * e->l + x] = amesteca(e->px[(gsize)y * e->l + x], CULOARE_LITERE, a);
            }
        }
        pana += (int)(g->advance.x >> 6);
    }
    return e;
}

/* Textul tradus din --text CHEIE=base64, desenat la prima folosire; NULL daca lipseste sau nu se poate desena. */
static Eticheta *text_eticheta(TextStrat *t)
{
    if (t->incercat)
        return t->e;
    t->incercat = TRUE;
    size_t n = strlen(t->cheie);
    for (char **x = opt.texte; x && *x; x++) {
        if (!strncmp(*x, t->cheie, n) && (*x)[n] == '=') {
            char *text = din_b64(*x + n + 1);
            t->e = eticheta_noua(text, (int)(20 * opt.scara + 0.5));
            g_free(text);
            break;
        }
    }
    return t->e;
}

static gboolean strat_se_poate(void)
{
    return !opt.hbbtv && ecran.mem && !(ecran.este_fb && ecran.ascuns);
}

/* Rotunjiri fara libm (lansatorul nu se leaga de ea). */
static int rotunjit_jos(double v)
{
    int i = (int)v;
    return (double)i > v ? i - 1 : i;
}

static int rotunjit_sus(double v)
{
    int i = (int)v;
    return (double)i < v ? i + 1 : i;
}

/* Puncte CSS in pixeli de ecran (cel putin 1). */
static int px_ecran(double css)
{
    int v = (int)(css * opt.scara + 0.5);
    return v < 1 ? 1 : v;
}

/* Latimea benzii chenarului in pixeli de ecran, dupa grosimea aleasa (normal: px_ecran(2.5), ca in 0.4.0). */
static int chenar_banda(void)
{
    return px_ecran(GROSIMI_CSS[chenar.grosime]);
}

/* Un dreptunghi plin pe pagina vizibila, taiat la marginile ecranului. */
static void strat_umple(guint8 *pagina, int x, int y, int l, int i, guint32 culoare)
{
    int x0 = MAX(x, 0), y0 = MAX(y, 0);
    int x1 = MIN(x + l, ecran.latime), y1 = MIN(y + i, ecran.inaltime);
    for (int r = y0; r < y1; r++) {
        guint32 *p = (guint32 *)(void *)(pagina + (gsize)r * ecran.pas) + x0;
        for (int c = x0; c < x1; c++)
            *p++ = culoare;
    }
}

/* Zona tinuta minte (taiata la ecran), ca la mutare sa fie luata inapoi din pagina. */
static void strat_tine_minte(int x, int y, int l, int i)
{
    int x0 = MAX(x, 0), y0 = MAX(y, 0);
    int x1 = MIN(x + l, ecran.latime), y1 = MIN(y + i, ecran.inaltime);
    if (x1 > x0 && y1 > y0 && strat.n_desenate < STRAT_ZONE)
        strat.desenate[strat.n_desenate++] = (Zona){ x0, y0, x1 - x0, y1 - y0 };
}

/* Patru fasii care nu se suprapun: un inel de grosimea g pe marginea dreptunghiului. */
static void strat_inel(guint8 *pagina, int x, int y, int l, int i, int g, guint32 culoare)
{
    strat_umple(pagina, x, y, l, g, culoare);
    strat_umple(pagina, x, y + i - g, l, g, culoare);
    strat_umple(pagina, x, y + g, g, i - 2 * g, culoare);
    strat_umple(pagina, x + l - g, y + g, g, i - 2 * g, culoare);
}

/* Eticheta copiata pe ecran in (x, y), deja tinuta in el. */
static void eticheta_copiaza(guint8 *pagina, const Eticheta *e, int x, int y)
{
    int l = MIN(e->l, ecran.latime - x), i = MIN(e->i, ecran.inaltime - y);
    for (int r = 0; r < i; r++)
        memcpy(pagina + (gsize)(y + r) * ecran.pas + (gsize)x * 4, e->px + (gsize)r * e->l, (gsize)l * 4);
}

/* Eticheta pe ecran (tinuta in el), cu zona ei tinuta minte; locul ei ramane stiut pentru pasii pulsului. */
static void eticheta_pune(guint8 *pagina, const Eticheta *e, int x, int y)
{
    x = CLAMP(x, 0, MAX(0, ecran.latime - e->l));
    y = CLAMP(y, 0, MAX(0, ecran.inaltime - e->i));
    eticheta_copiaza(pagina, e, x, y);
    strat_tine_minte(x, y, MIN(e->l, ecran.latime - x), MIN(e->i, ecran.inaltime - y));
    strat.eticheta = e;
    strat.eticheta_x = x;
    strat.eticheta_y = y;
}

/* Ce acoperea stratul, inapoi din copia paginii; fara copie zonele se uita. */
static void strat_sterge(void)
{
    gboolean are = copie_pagina.mem != NULL;
    for (int k = 0; are && k < strat.n_desenate; k++) {
        WPERectangle r = { strat.desenate[k].x, strat.desenate[k].y, strat.desenate[k].l, strat.desenate[k].i };
        ecran_din_pagina(&r, 1);
    }
    strat.n_desenate = 0;
    if (are && ind.are_zona) {
        WPERectangle r = { ind.zona.x, ind.zona.y, ind.zona.l, ind.zona.i };
        ecran_din_pagina(&r, 1);
    }
    ind.are_zona = FALSE;
}

/* Sageata indicatorului: X contur negru, . alb, spatiul ramane pagina; fiecare semn e un patrat de k pixeli. */
static const char *const SAGEATA[] = {
    "X",
    "XX",
    "X.X",
    "X..X",
    "X...X",
    "X....X",
    "X.....X",
    "X......X",
    "X.......X",
    "X........X",
    "X.........X",
    "X......XXXXX",
    "X...X..X",
    "X..XX..X",
    "X.X  X..X",
    "XX   X..X",
    "X     X..X",
    "      X..X",
    "       XX",
};
#define SAGEATA_LATIME 12

static void indicator_deseneaza(guint8 *pagina)
{
    int k = px_ecran(2.0);
    int x0 = (int)ind.x, y0 = (int)ind.y;
    for (int r = 0; r < (int)G_N_ELEMENTS(SAGEATA); r++) {
        for (int c = 0; SAGEATA[r][c]; c++) {
            if (SAGEATA[r][c] != ' ')
                strat_umple(pagina, x0 + c * k, y0 + r * k, k, k, SAGEATA[r][c] == 'X' ? 0xFF000000u : 0xFFFFFFFFu);
        }
    }
    int x1 = MIN(x0 + SAGEATA_LATIME * k, ecran.latime), y1 = MIN(y0 + (int)G_N_ELEMENTS(SAGEATA) * k, ecran.inaltime);
    ind.are_zona = x1 > x0 && y1 > y0;
    ind.zona = (Zona){ x0, y0, x1 - x0, y1 - y0 };
}

/* Culoarea benzii: cea aleasa, cu luminozitatea pulsului (din fabrica galbenul (255,190,40) intre 100 % si 50 %, ca in
 * 0.4.0). */
static guint32 culoare_puls(void)
{
    guint32 c = chenar_culoare();
    double f = puls_factor();
    guint r = (guint)(((c >> 16) & 0xFF) * f + 0.5), g = (guint)(((c >> 8) & 0xFF) * f + 0.5);
    guint b = (guint)((c & 0xFF) * f + 0.5);
    return 0xFF000000u | (r << 16) | (g << 8) | b;
}

/* Pixelul paginii curate (din copia ei) sub punctul (x, y) al ecranului, sau NULL in afara copiei. */
static const guint32 *pagina_curata(int x, int y)
{
    if (!copie_pagina.mem || x < 0 || y < 0 || x >= copie_pagina.latime || y >= copie_pagina.inaltime)
        return NULL;
    return (const guint32 *)(const void *)(copie_pagina.mem + ((gsize)y * copie_pagina.latime + (gsize)x) * 4);
}

/* Contrastul automat: luminozitatea paginii curate intr-o zona (cel mult 16 x 8 esantioane), adunata in s si n. */
static void lumina_zona(int x, int y, int l, int i, guint64 *s, guint *n)
{
    if (l <= 0 || i <= 0)
        return;
    int px = MAX(1, l / 16), py = MAX(1, i / 8);
    for (int r = y + py / 2; r < y + i; r += py) {
        for (int c = x + px / 2; c < x + l; c += px) {
            const guint32 *p = pagina_curata(c, r);
            if (p) {
                *s += lumina(*p);
                (*n)++;
            }
        }
    }
}

/* Contrastul automat dupa luminozitatea medie a paginii de sub chenar: dupa o mutare se alege din nou (un singur prag,
 * la mijloc); la cadrele urmatoare pe acelasi loc pragul e dublu, ca o pagina cenusie sa nu schimbe culoarea mereu. */
static void contrast_alege(guint64 s, guint n)
{
    if (chenar.culoare != CULOARE_AUTO || !n)
        return;
    guint m = (guint)(s / n);
    if (chenar.alege_din_nou)
        chenar.auto_inchis = m >= (LUMINA_PAGINA_DESCHISA + LUMINA_PAGINA_INCHISA) / 2;
    else if (m > LUMINA_PAGINA_DESCHISA)
        chenar.auto_inchis = TRUE;
    else if (m < LUMINA_PAGINA_INCHISA)
        chenar.auto_inchis = FALSE;
    chenar.alege_din_nou = FALSE;
}

/* Contrastul automat pentru inel: pagina de sub cele patru laturi. */
static void contrast_inel(int x0, int y0, int l, int i, int gros)
{
    guint64 s = 0;
    guint n = 0;
    lumina_zona(x0, y0, l, gros, &s, &n);
    lumina_zona(x0, y0 + i - gros, l, gros, &s, &n);
    lumina_zona(x0, y0 + gros, gros, i - 2 * gros, &s, &n);
    lumina_zona(x0 + l - gros, y0 + gros, gros, i - 2 * gros, &s, &n);
    contrast_alege(s, n);
}

/* Unde cade un punct in coltul rotunjit, dupa patratul distantei d2 fata de centrul cercului: 0 pagina (in afara inelului
 * sau inauntrul lui), 1 contur, 2 banda. r[0..3]: razele de la marginea de afara spre interior. */
static int colt_strat(double d2, const double r[4])
{
    if (d2 > r[0] * r[0] || d2 <= r[3] * r[3])
        return 0;
    return d2 > r[1] * r[1] || d2 <= r[2] * r[2] ? 1 : 2;
}

/* Un colt al inelului rotunjit: patratul [x, x + raza) x [y, y + raza), cu centrul cercului in (cx, cy). Fiecare pixel
 * iese din 4 esantioane (contur, banda sau pagina curata din copia ei), deci marginea rotunda e neteda; fara calcule cu
 * radacina patrata (lansatorul nu se leaga de libm). */
static void colt_rotunjit(guint8 *pagina, int x, int y, int raza, double cx, double cy, const double r[4], guint32 banda,
    guint32 contur)
{
    static const double ES[4][2] = { { 0.25, 0.25 }, { 0.75, 0.25 }, { 0.25, 0.75 }, { 0.75, 0.75 } };
    for (int py = MAX(y, 0); py < MIN(y + raza, ecran.inaltime); py++) {
        guint32 *rand = (guint32 *)(void *)(pagina + (gsize)py * ecran.pas);
        for (int px = MAX(x, 0); px < MIN(x + raza, ecran.latime); px++) {
            const guint32 *fund = pagina_curata(px, py);
            guint sr = 0, sg = 0, sb = 0, din_pagina = 0;
            for (int k = 0; k < 4; k++) {
                double dx = px + ES[k][0] - cx, dy = py + ES[k][1] - cy;
                int s = colt_strat(dx * dx + dy * dy, r);
                guint32 c = s == 2 ? banda : s == 1 ? contur : fund ? *fund : rand[px];
                din_pagina += s == 0;
                sr += (c >> 16) & 0xFF;
                sg += (c >> 8) & 0xFF;
                sb += c & 0xFF;
            }
            if (din_pagina == 4 && !fund)
                continue;
            rand[px] = 0xFF000000u | (((sr + 2) / 4) << 16) | (((sg + 2) / 4) << 8) | ((sb + 2) / 4);
        }
    }
}

/* Inelul cu colturile rotunde (raza masurata pe marginea de afara): laturile drepte ca la dreptunghi (contur, banda,
 * contur), colturile netezite. numai_banda: la pasul pulsului numai banda laturilor, dar colturile intregi (pixelii lor
 * amesteca banda cu conturul si cu pagina). */
static void inel_rotunjit(guint8 *pagina, int x0, int y0, int l, int i, int d, int b, int raza, gboolean numai_banda)
{
    guint32 banda = culoare_puls(), contur = chenar_contur();
    int gros = d + b + d, x1 = x0 + l, y1 = y0 + i;
    int lat = l - 2 * raza, inalt = i - 2 * raza;     /* laturile drepte, fara colturi */
    strat_umple(pagina, x0 + raza, y0 + d, lat, b, banda);
    strat_umple(pagina, x0 + raza, y1 - d - b, lat, b, banda);
    strat_umple(pagina, x0 + d, y0 + raza, b, inalt, banda);
    strat_umple(pagina, x1 - d - b, y0 + raza, b, inalt, banda);
    if (!numai_banda) {
        for (int k = 0; k < 2; k++) {
            int a = k ? d + b : 0;                    /* conturul de afara, apoi cel dinauntru */
            strat_umple(pagina, x0 + raza, y0 + a, lat, d, contur);
            strat_umple(pagina, x0 + raza, y1 - a - d, lat, d, contur);
            strat_umple(pagina, x0 + a, y0 + raza, d, inalt, contur);
            strat_umple(pagina, x1 - a - d, y0 + raza, d, inalt, contur);
        }
    }
    const double r[4] = { raza, raza - d, raza - d - b, raza - gros };
    colt_rotunjit(pagina, x0, y0, raza, x0 + raza, y0 + raza, r, banda, contur);
    colt_rotunjit(pagina, x1 - raza, y0, raza, x1 - raza, y0 + raza, r, banda, contur);
    colt_rotunjit(pagina, x0, y1 - raza, raza, x0 + raza, y1 - raza, r, banda, contur);
    colt_rotunjit(pagina, x1 - raza, y1 - raza, raza, x1 - raza, y1 - raza, r, banda, contur);
}

/* Subliniere: o bara sub element, de latimea lui si de grosimea inelului (contur, banda, contur), tinuta in ecran. */
static void chenar_subliniere(guint8 *pagina, gboolean numai_banda, int d, int b, int dist)
{
    int gros = d + b + d;
    int x0 = MAX(strat.tinta.x, 0), x1 = MIN(strat.tinta.x + strat.tinta.l, ecran.latime);
    int y0 = MAX(MIN(strat.tinta.y + strat.tinta.i + dist, ecran.inaltime - gros), 0);
    int l = x1 - x0;
    if (l < 2 * d + 1 || gros > ecran.inaltime)
        return;
    if (!numai_banda) {
        guint64 s = 0;
        guint n = 0;
        lumina_zona(x0, y0, l, gros, &s, &n);
        contrast_alege(s, n);
        strat_umple(pagina, x0, y0, l, gros, chenar_contur());
        strat_tine_minte(x0, y0, l, gros);
    }
    strat_umple(pagina, x0 + d, y0 + d, l - 2 * d, b, culoare_puls());
}

/* Fundal colorat: culoarea aleasa, semitransparenta (opacitatea dupa grosime), peste element si o mica margine,
 * amestecata cu pagina curata din copia ei (deci la fiecare desen acelasi rezultat pentru aceeasi faza). Pulsul schimba
 * opacitatea. */
static void chenar_fundal(guint8 *pagina, gboolean numai_banda, int dist)
{
    int x0 = MAX(strat.tinta.x - dist, 0), y0 = MAX(strat.tinta.y - dist, 0);
    int x1 = MIN(strat.tinta.x + strat.tinta.l + dist, MIN(ecran.latime, copie_pagina.latime));
    int y1 = MIN(strat.tinta.y + strat.tinta.i + dist, MIN(ecran.inaltime, copie_pagina.inaltime));
    if (!copie_pagina.mem || x1 <= x0 || y1 <= y0)
        return;
    if (!numai_banda) {
        guint64 s = 0;
        guint n = 0;
        lumina_zona(x0, y0, x1 - x0, y1 - y0, &s, &n);
        contrast_alege(s, n);
        strat_tine_minte(x0, y0, x1 - x0, y1 - y0);
    }
    guint32 c = chenar_culoare();
    guint a = (guint)(FUNDAL_ALFA[chenar.grosime] * puls_factor() + 0.5);
    for (int y = y0; y < y1; y++) {
        const guint32 *sursa = (const guint32 *)(const void *)(copie_pagina.mem + ((gsize)y * copie_pagina.latime + x0) * 4);
        guint32 *p = (guint32 *)(void *)(pagina + (gsize)y * ecran.pas) + x0;
        for (int x = x0; x < x1; x++)
            *p++ = amesteca(*sursa++, c, a);
    }
}

/* Chenarul in afara elementului (cu o mica distanta), tinut in ecran cand elementul e mai mare sau iese din el, in forma,
 * culoarea si grosimea alese (din fabrica: dreptunghiul galben din 0.4.0). numai_banda: pasul pulsului, numai culoarea
 * benzii (sau a fundalului), fara contur si fara zone noi. */
static void chenar_deseneaza(guint8 *pagina, gboolean numai_banda)
{
    int d = 1, b = chenar_banda(), dist = px_ecran(1.0);
    if (chenar.forma == FORMA_SUBLINIERE) {
        chenar_subliniere(pagina, numai_banda, d, b, dist);
        return;
    }
    if (chenar.forma == FORMA_FUNDAL) {
        chenar_fundal(pagina, numai_banda, dist);
        return;
    }
    int gros = d + b + d;
    int x0 = MAX(strat.tinta.x - dist - gros, 0), y0 = MAX(strat.tinta.y - dist - gros, 0);
    int x1 = MIN(strat.tinta.x + strat.tinta.l + dist + gros, ecran.latime);
    int y1 = MIN(strat.tinta.y + strat.tinta.i + dist + gros, ecran.inaltime);
    int l = x1 - x0, i = y1 - y0;
    if (l < 2 * gros + 2 || i < 2 * gros + 2)
        return;
    if (!numai_banda)
        contrast_inel(x0, y0, l, i, gros);
    /* colturile rotunde: raza pe marginea de afara, cel mult jumatate din latura mica */
    int raza = chenar.forma == FORMA_ROTUNJIT ? MIN(gros + px_ecran(4.0), MIN(l, i) / 2) : 0;
    if (raza) {
        inel_rotunjit(pagina, x0, y0, l, i, d, b, raza, numai_banda);
    } else {
        strat_inel(pagina, x0 + d, y0 + d, l - 2 * d, i - 2 * d, b, culoare_puls());
        if (!numai_banda) {
            strat_inel(pagina, x0, y0, l, i, d, chenar_contur());
            strat_inel(pagina, x0 + d + b, y0 + d + b, l - 2 * (d + b), i - 2 * (d + b), d, chenar_contur());
        }
    }
    if (numai_banda)
        return;
    int t = MAX(gros, raza);   /* la colturile rotunde inelul intra mai adanc in patratul coltului */
    strat_tine_minte(x0, y0, l, t);
    strat_tine_minte(x0, y1 - t, l, t);
    strat_tine_minte(x0, y0 + t, t, i - 2 * t);
    strat_tine_minte(x1 - t, y0 + t, t, i - 2 * t);
}

/* Dupa pasul pulsului: textul de jos si sageata din nou deasupra (banda sau fundalul colorat le-ar putea acoperi). */
static void strat_sus_din_nou(guint8 *pagina)
{
    if (strat.eticheta)
        eticheta_copiaza(pagina, (const Eticheta *)strat.eticheta, strat.eticheta_x, strat.eticheta_y);
    if (ind.activ)
        indicator_deseneaza(pagina);
}

static gboolean puls_pas(gpointer d)
{
    (void)d;
    int pasi = PULSURI_PASI[chenar.puls];
    if (!opt.chenar || !strat.are_tinta || !strat_se_poate() || pasi <= 0) {
        strat.puls = 0;
        return G_SOURCE_REMOVE;
    }
    strat.faza = (strat.faza + 1) % pasi;
    chenar_deseneaza(ecran_pagina_vizibila(), TRUE);
    strat_sus_din_nou(ecran_pagina_vizibila());
    return G_SOURCE_CONTINUE;
}

/* Tot stratul din nou. mutat: s-a schimbat ce arata, deci ce acoperea inainte se ia intai inapoi din pagina. */
static void strat_deseneaza(gboolean mutat)
{
    if (!strat_se_poate())
        return;
    if (mutat)
        strat_sterge();
    strat.n_desenate = 0;
    strat.eticheta = NULL;
    guint8 *pagina = ecran_pagina_vizibila();
    if (opt.chenar && strat.are_tinta) {
        chenar_deseneaza(pagina, FALSE);
        if (!strat.puls && PULSURI_PASI[chenar.puls] > 0)
            strat.puls = g_timeout_add(PULS_PAS_MS, puls_pas, NULL);
    }
    /* textul de ajutor, jos pe mijloc (chenarul arata deja elementul); cu indicatorul, OK face clic, deci scrisul e TEXT */
    Eticheta *e = NULL;
    if (strat.ceas_fara_camp)
        e = text_eticheta(&text_fara_camp);
    else if (ind.activ && ind.ceas_ajutor)
        e = text_eticheta(&text_indicator);
    else if (strat.camp)
        e = text_eticheta(ind.activ ? &text_scrie_indicator : &text_scrie);
    if (e)
        eticheta_pune(pagina, e, (ecran.latime - e->l) / 2, ecran.inaltime - e->i - px_ecran(24));
    if (ind.activ)
        indicator_deseneaza(pagina);
}

/* Sageata s-a mutat: numai locul ei vechi se ia inapoi din pagina; chenarul si textul raman (se deseneaza peste). */
static void strat_muta_indicator(void)
{
    if (!strat_se_poate())
        return;
    if (copie_pagina.mem && ind.are_zona) {
        WPERectangle r = { ind.zona.x, ind.zona.y, ind.zona.l, ind.zona.i };
        ecran_din_pagina(&r, 1);
    }
    ind.are_zona = FALSE;
    strat_deseneaza(FALSE);
}

static gboolean fara_camp_gata(gpointer d)
{
    (void)d;
    strat.ceas_fara_camp = 0;
    strat_deseneaza(TRUE);
    return G_SOURCE_REMOVE;
}

/* TEXT fara niciun camp de scris pe ecran: textul se arata cateva secunde. */
static void strat_fara_camp(void)
{
    if (strat.ceas_fara_camp)
        g_source_remove(strat.ceas_fara_camp);
    strat.ceas_fara_camp = g_timeout_add(FARA_CAMP_MS, fara_camp_gata, NULL);
    strat_deseneaza(TRUE);
}

/* Felul elementului cu focalizare s-a schimbat: „OK sau TEXT: scrie” apare sau dispare. */
static void strat_camp(gboolean camp)
{
    if (camp == strat.camp)
        return;
    strat.camp = camp;
    strat_deseneaza(TRUE);
}

/* tot: toata pagina tocmai a fost copiata din nou (dupa „arata”), deci nimic de luat inapoi. */
static void strat_dupa_cadru(gboolean tot)
{
    if (tot)
        strat.n_desenate = 0;
    else
        masura_cadru();
    strat_deseneaza(FALSE);
}

/* Dreptunghiul elementului cu focalizare, de la SCRIPT_CHENAR: „x y latime inaltime latime-fereastra” in puncte CSS
 * ale ferestrei de sus (zecimale cu punct) sau „-” cand nu se vede niciun element. Pixelii de ecran pe punct CSS ies din
 * latimea ferestrei, deci cuprind si scara, si marirea paginii. */
static void chenar_schimbat(WebKitUserContentManager *m, JSCValue *v, gpointer d)
{
    (void)m; (void)d;
    if (!jsc_value_is_string(v))
        return;
    char *s = jsc_value_to_string(v);
    char **c = g_strsplit(s, " ", 6);
    gboolean are = FALSE;
    Zona z = { 0, 0, 0, 0 };
    if (g_strv_length(c) == 5) {
        double n[5];
        for (int k = 0; k < 5; k++)
            n[k] = CLAMP(g_ascii_strtod(c[k], NULL), -100000.0, 100000.0);
        if (n[4] >= 1.0 && n[2] > 0.0 && n[3] > 0.0) {
            double f = opt.latime * opt.scara / n[4];
            z.x = rotunjit_jos(n[0] * f);
            z.y = rotunjit_jos(n[1] * f);
            z.l = rotunjit_sus((n[0] + n[2]) * f) - z.x;
            z.i = rotunjit_sus((n[1] + n[3]) * f) - z.y;
            are = TRUE;
        }
    }
    g_strfreev(c);
    g_free(s);
    if (are == strat.are_tinta && (!are || !memcmp(&z, &strat.tinta, sizeof(z))))
        return;
    strat.are_tinta = are;
    strat.tinta = z;
    chenar.alege_din_nou = TRUE;   /* contrastul automat se alege din nou pentru locul nou */
    strat_deseneaza(TRUE);
    if (masura.tasta && !masura.chenar) {
        masura.chenar = TRUE;
        stare_f("TIMP tasta-chenar %d", (int)((g_get_monotonic_time() - masura.tasta) / 1000));
    }
}

/* La o pagina noua chenarul dispare pana cand scriptul trimite noul element. */
static void chenar_uita(void)
{
    if (!strat.are_tinta)
        return;
    strat.are_tinta = FALSE;
    strat_deseneaza(TRUE);
}

/* O valoare a stilului data la pornire (--chenar-culoare ...): indicele ei; necunoscuta, un avertisment si valoarea din
 * fabrica (navigatorul porneste oricum). */
static int chenar_optiune(const char *const *lista, const char *valoare, int implicit, const char *nume)
{
    if (!valoare)
        return implicit;
    int k = index_nume(lista, valoare);
    if (k < 0) {
        stare_f("AVERTISMENT chenar-%s", nume);
        return implicit;
    }
    return k;
}

static void chenar_din_optiuni(void)
{
    chenar.culoare = chenar_optiune(CULORI_NUME, opt.chenar_culoare, chenar.culoare, "culoare");
    chenar.forma = chenar_optiune(FORME_NUME, opt.chenar_forma, chenar.forma, "forma");
    chenar.grosime = chenar_optiune(GROSIMI_NUME, opt.chenar_grosime, chenar.grosime, "grosime");
    chenar.puls = chenar_optiune(PULSURI_NUME, opt.chenar_puls, chenar.puls, "puls");
}

/* "chenar <0|1> <culoare> <forma> <grosime> <puls>": chenarul pornit sau oprit si stilul lui, schimbate de om cat
 * navigatorul ruleaza (Setari navigator web pe televizor sau pagina web /navigator). Se vede pe loc: ce acoperea
 * chenarul vechi se ia inapoi din pagina, apoi se deseneaza cel nou (cat navigatorul e ascuns, la "arata"). Ceva
 * necunoscut: "EROARE chenar" si nimic schimbat. */
static void chenar_comanda(const char *arg)
{
    char **c = g_strsplit(arg ? arg : "", " ", 6);
    int cu = -1, fo = -1, gr = -1, pu = -1;
    gboolean bun = g_strv_length(c) == 5 && (!strcmp(c[0], "0") || !strcmp(c[0], "1"));
    if (bun) {
        cu = index_nume(CULORI_NUME, c[1]);
        fo = index_nume(FORME_NUME, c[2]);
        gr = index_nume(GROSIMI_NUME, c[3]);
        pu = index_nume(PULSURI_NUME, c[4]);
        bun = cu >= 0 && fo >= 0 && gr >= 0 && pu >= 0;
    }
    gboolean pornit = bun && c[0][0] == '1';
    g_strfreev(c);
    if (!bun) {
        stare("EROARE chenar");
        return;
    }
    opt.chenar = pornit;
    chenar.culoare = cu;
    chenar.forma = fo;
    chenar.grosime = gr;
    chenar.puls = pu;
    chenar.alege_din_nou = TRUE;
    strat.faza = 0;
    strat_deseneaza(TRUE);
    stare_f("CHENAR %d %s %s %s %s", pornit ? 1 : 0, CULORI_NUME[cu], FORME_NUME[fo], GROSIMI_NUME[gr], PULSURI_NUME[pu]);
}

#define HDS_TYPE_DISPLAY (hds_display_get_type())
G_DECLARE_FINAL_TYPE(HdsDisplay, hds_display, HDS, DISPLAY, WPEDisplay)
struct _HdsDisplay {
    WPEDisplay parent_instance;
    WPEKeymap *harta;
};
G_DEFINE_FINAL_TYPE(HdsDisplay, hds_display, WPE_TYPE_DISPLAY)

static gboolean hds_display_connect(WPEDisplay *d, GError **e)
{
    (void)d; (void)e;
    return TRUE;
}

static WPEView *hds_display_create_view(WPEDisplay *d)
{
    return WPE_VIEW(g_object_new(HDS_TYPE_VIEW, "display", d, NULL));
}

static WPEToplevel *hds_display_create_toplevel(WPEDisplay *d, guint max)
{
    (void)max;
    return WPE_TOPLEVEL(g_object_new(HDS_TYPE_TOPLEVEL, "display", d, NULL));
}

/* transfer none: harta ramane a afisajului */
static WPEKeymap *hds_display_get_keymap(WPEDisplay *d)
{
    HdsDisplay *self = HDS_DISPLAY(d);
    if (!self->harta)
        self->harta = WPE_KEYMAP(g_object_new(HDS_TYPE_KEYMAP, NULL));
    return self->harta;
}

static void hds_display_dispose(GObject *o)
{
    g_clear_object(&HDS_DISPLAY(o)->harta);
    G_OBJECT_CLASS(hds_display_parent_class)->dispose(o);
}

static void hds_display_class_init(HdsDisplayClass *klass)
{
    G_OBJECT_CLASS(klass)->dispose = hds_display_dispose;
    WPEDisplayClass *dc = WPE_DISPLAY_CLASS(klass);
    dc->connect = hds_display_connect;
    dc->create_view = hds_display_create_view;
    dc->create_toplevel = hds_display_create_toplevel;
    dc->get_keymap = hds_display_get_keymap;
}

static void hds_display_init(HdsDisplay *self)
{
    (void)self;
}

/* ---------------------------------------------------------------- navigatorul */

static GMainLoop *bucla;
static WebKitWebView *vedere;
static WebKitNetworkSession *sesiune;
static int cod_iesire;
static gboolean pagina_incarcata;
static gboolean prima_pagina_anuntata;
static guint captura_programata;
static char **argv_pornire;      /* argumentele initiale, pentru repornirea pe procesor */
static const char *url_pornire;  /* adresa data la pornire (argumentul fara optiune) */
static char *adresa_reluare;     /* pagina deschisa cand procesul web a cazut */
static gboolean reporneste_pe_cpu;
static guint cadre_primite;
static guint paza_cadre;

#define INTRARI_MAXIM 16
static int intrari_fd[INTRARI_MAXIM];
static int n_intrari;
static int ultim_progres = -1;
static char camp_fel[16] = "niciunul";      /* campul cu focalizare, dupa scriptul injectat in pagina */
static gboolean ok_spre_tastatura;          /* ridicarea lui OK care a cerut tastatura nu mai ajunge in pagina */
static WebKitAuthenticationRequest *autentificare_curenta;
static WebKitScriptDialog *dialog_curent;
static WebKitOptionMenu *meniu_curent;
static GHashTable *mariri;                  /* gazda -> marirea aleasa de om, in procente */
static char *fisier_mariri;                 /* <--date>/mariri.txt; NULL in modul fara profil */
static char *gazda_curenta;

static void stare(const char *text)
{
    fprintf(stdout, "HDS-NAV %s\n", text);
    fflush(stdout);
}

static void stare_f(const char *format, ...) G_GNUC_PRINTF(1, 2);
static void stare_f(const char *format, ...)
{
    va_list a;
    va_start(a, format);
    char *rand = g_strdup_vprintf(format, a);
    va_end(a);
    stare(rand);
    g_free(rand);
}

/* Textele din pagina si cele scrise de om trec spre enigma2 numai in base64 („-” pentru gol): un rand nu se poate
 * rupe si nimic din ele nu seamana cu un rand de stare. */
static char *b64(const char *text)
{
    if (!text || !*text)
        return g_strdup("-");
    return g_base64_encode((const guchar *)text, strlen(text));
}

static char *din_b64(const char *text)
{
    if (!text || !*text || !strcmp(text, "-"))
        return g_strdup("");
    gsize n = 0;
    guchar *date = g_base64_decode(text, &n);
    char *rez = g_malloc(n + 1);
    memcpy(rez, date, n);
    rez[n] = '\0';
    memset(date, 0, n);
    g_free(date);
    if (!g_utf8_validate(rez, -1, NULL)) {
        char *bun = g_utf8_make_valid(rez, -1);
        memset(rez, 0, n);
        g_free(rez);
        rez = bun;
    }
    return rez;
}

/* Sterge textul din memorie inainte de eliberare (parole, texte scrise de om). */
static void elibereaza_secret(char *text)
{
    if (text) {
        memset(text, 0, strlen(text));
        g_free(text);
    }
}

/* Un sir JavaScript intre ghilimele, cu semnele speciale scapate. */
static void js_sir(GString *s, const char *text)
{
    g_string_append_c(s, '"');
    for (const char *p = text; *p; p++) {
        guchar c = (guchar)*p;
        if (c == '"' || c == '\\')
            g_string_append_printf(s, "\\%c", c);
        else if (c < 0x20)
            g_string_append_printf(s, "\\u%04x", c);
        else
            g_string_append_c(s, (char)c);
    }
    g_string_append_c(s, '"');
}

/* Un sir JSON (pentru lista unui <select>). */
static void json_sir(GString *s, const char *text)
{
    js_sir(s, text ? text : "");
}

static void ruleaza_js(const char *script, GAsyncReadyCallback gata, gpointer date)
{
    webkit_web_view_evaluate_javascript(vedere, script, -1, NULL, NULL, NULL, gata, date);
}

/* Documentul care are focalizarea, coborand prin cadrele din aceeasi origine. */
#define JS_DOC_ACTIV \
    "var d=document;try{while(d.activeElement&&d.activeElement.contentDocument)d=d.activeElement.contentDocument;}catch(x){}"

/* Elementul activ al documentului d, coborand prin shadow DOM deschis (campurile din componentele web). */
#define JS_ACTIV \
    "var e=d.activeElement;try{while(e&&e.shadowRoot&&e.shadowRoot.activeElement)e=e.shadowRoot.activeElement;}catch(x){}"

/* Felul campului: niciunul, text, parola, numar, zona (textarea sau contenteditable). */
#define JS_FEL \
    "function hdsFel(e){if(!e)return'niciunul';var t=(e.tagName||'').toLowerCase();" \
    "if(e.isContentEditable||t==='textarea')return'zona';if(t!=='input')return'niciunul';" \
    "var y=(e.getAttribute('type')||'text').toLowerCase();if(y==='password')return'parola';" \
    "if(y==='number'||y==='tel')return'numar';" \
    "if(['text','search','url','email'].indexOf(y)>=0)return'text';return'niciunul';}"

/* Injectat in toate cadrele: spune lansatorului felul campului la fiecare schimbare a focalizarii. Un cadru interior
 * isi spune singur campul; documentul parinte tace cat focalizarea e intr-un cadru. */
static const char SCRIPT_CAMPURI[] =
    "(function(){if(window.__hdsNav)return;window.__hdsNav=1;" JS_FEL
    "function t(){var d=document;" JS_ACTIV "if(e&&(e.tagName==='IFRAME'||e.tagName==='FRAME'))return;"
    "try{window.webkit.messageHandlers.hdsnav.postMessage(hdsFel(e));}catch(x){}}"
    "document.addEventListener('focusin',t,true);"
    "document.addEventListener('focusout',function(){setTimeout(t,0);},true);})();";

/* Injectat in toate cadrele (in afara modului HbbTV): dreptunghiul elementului cu focalizare, spre lansator, la
 * schimbarea focalizarii, la derulare (orice element), la schimbarea marimii si de trei ori pe secunda cat un element
 * are focalizarea (mutari din pagina). Cadrul care are elementul il trimite, socotit in fereastra de sus prin
 * frameElement; un cadru din alta origine nu se poate socoti, deci se arata cadrul intreg (il trimite parintele).
 * Elementele din shadow DOM deschis se cauta prin shadowRoot.activeElement.
 * Tot aici, ocolirea unei caderi a WPE 2.54: o sageata cu focalizarea pe un element din shadow DOM (camp sau buton)
 * opreste procesul web in navigarea spatiala (proba pe x86, si cu lansatorul 0.3.0). Inainte de navigare, focalizarea
 * trece pe gazda (tabindex -1 daca nu are), deci navigarea pleaca din acelasi loc, dar din documentul obisnuit; la o
 * gazda care trimite singura focalizarea inapoi in umbra (delegatesFocus), elementul pierde focalizarea. */
static const char SCRIPT_CHENAR[] =
    "(function(){if(window.__hdsChenar)return;var ultim='',cerut=0,sus=(window===window.top);"
    "function trimite(t){if(t===ultim)return;ultim=t;"
    "try{window.webkit.messageHandlers.hdsnavchenar.postMessage(t);}catch(x){}}"
    "function activ(){var e=document.activeElement;"
    "try{while(e&&e.shadowRoot&&e.shadowRoot.activeElement)e=e.shadowRoot.activeElement;}catch(x){}return e;}"
    "function gol(e){return !e||e===document.body||e===document.documentElement;}"
    "function intra(e){try{return !!e.contentDocument;}catch(x){return false;}}"
    "function masoara(){cerut=0;var e=activ();"
    "if(gol(e)){if(sus||document.hasFocus())trimite('-');return;}"
    "if((e.tagName==='IFRAME'||e.tagName==='FRAME')&&intra(e))return;"
    "var r=e.getBoundingClientRect();"
    "if((r.width<1||r.height<1)&&e.firstElementChild){var q=e.firstElementChild.getBoundingClientRect();"
    "if(q.width>=1&&q.height>=1)r=q;}"
    "var x=r.left,y=r.top,w=r.width,h=r.height,f=window;"
    "try{while(f!==f.top){var fe=f.frameElement;if(!fe)return;var fr=fe.getBoundingClientRect(),"
    "cs=f.parent.getComputedStyle(fe);x+=fr.left+fe.clientLeft+(parseFloat(cs.paddingLeft)||0);"
    "y+=fr.top+fe.clientTop+(parseFloat(cs.paddingTop)||0);f=f.parent;}}catch(x){return;}"
    "var vw=f.innerWidth,vh=f.innerHeight;"
    "if(w<1||h<1||x+w<=0||y+h<=0||x>=vw||y>=vh){trimite('-');return;}"
    "function n(v){return String(Math.round(v*10)/10);}"
    "trimite(n(x)+' '+n(y)+' '+n(w)+' '+n(h)+' '+n(vw));}"
    "function curand(){if(!cerut){cerut=1;window.requestAnimationFrame(masoara);}}"
    "window.__hdsChenar=function(){ultim='';curand();};"
    "document.addEventListener('focusin',function(){ultim='';curand();},true);"
    "document.addEventListener('focusout',function(){setTimeout(curand,0);},true);"
    "document.addEventListener('scroll',curand,true);"
    "window.addEventListener('resize',curand);"
    "setInterval(function(){if(!gol(activ()))curand();},300);"
    "window.addEventListener('keydown',function(ev){if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight']"
    ".indexOf(ev.key)<0)return;var a=document.activeElement;if(!a||!a.shadowRoot||!a.shadowRoot.activeElement)return;"
    "try{if(a.shadowRoot.delegatesFocus){a.shadowRoot.activeElement.blur();return;}"
    "if(!a.hasAttribute('tabindex'))a.setAttribute('tabindex','-1');a.focus();}catch(x){}},true);})();";

/* Injectat in toate cadrele (in afara modului HbbTV): fiecare regula CSS cu :hover a paginii (si din @media) se copiaza,
 * cu :focus-within in loc de :hover, intr-o foaie <style id="hds-meniuri"> pusa la sfarsitul lui <head>; numai partile
 * selectorului care au :hover. Foile noi (<style>, <link> adaugate sau incarcate mai tarziu) se trec si ele, o singura
 * data fiecare; o foaie din alta origine (cssRules arunca) se sare. */
static const char SCRIPT_MENIURI[] =
    "(function(){if(window.__hdsMeniuri)return;window.__hdsMeniuri=1;var vazute=[],noua=null;"
    "function inlocuieste(sel){var p=sel.split(','),r=[];for(var i=0;i<p.length;i++){if(p[i].indexOf(':hover')>=0)"
    "r.push(p[i].replace(/:hover/g,':focus-within'));}return r.join(',');}"
    "function treci(reguli,iesire){for(var i=0;i<reguli.length;i++){var g=reguli[i];"
    "if(g.type===1&&g.selectorText&&g.selectorText.indexOf(':hover')>=0){var s=inlocuieste(g.selectorText);"
    "if(s)iesire.push(s+'{'+g.style.cssText+'}');}"
    "else if(g.type===4&&g.cssRules){var interior=[];treci(g.cssRules,interior);"
    "if(interior.length)iesire.push('@media '+g.media.mediaText+'{'+interior.join('')+'}');}}}"
    "function aplica(){var d=document,f=d.styleSheets,iesire=[];for(var i=0;i<f.length;i++){var o=f[i];"
    "if(o.ownerNode&&o.ownerNode.id==='hds-meniuri')continue;if(vazute.indexOf(o)>=0)continue;var reguli;"
    "try{reguli=o.cssRules;}catch(x){vazute.push(o);continue;}if(!reguli)continue;vazute.push(o);treci(reguli,iesire);}"
    "if(!iesire.length)return;if(!noua||!noua.parentNode){noua=d.createElement('style');noua.id='hds-meniuri';"
    "(d.head||d.documentElement).appendChild(noua);}noua.appendChild(d.createTextNode(iesire.join('')));}"
    "function curand(){try{aplica();}catch(x){}}"
    "document.addEventListener('DOMContentLoaded',curand);window.addEventListener('load',curand);"
    "document.addEventListener('load',function(e){if(e.target&&e.target.tagName==='LINK')curand();},true);"
    "try{new MutationObserver(function(m){for(var i=0;i<m.length;i++){for(var j=0;j<m[i].addedNodes.length;j++){"
    "var n=m[i].addedNodes[j];if(n.tagName==='STYLE'||n.tagName==='LINK'){setTimeout(curand,0);return;}}}})"
    ".observe(document,{childList:true,subtree:true});}catch(x){}})();";

/* Modul HbbTV: constantele tastelor (CEA-2014 / OIPF DAE, cerute de HbbTV), puse pe window si pe KeyEvent numai daca
 * pagina nu le are deja. Obiectele HbbTV (oipfApplicationManager, video/broadcast ...) sunt in hds-hbbtv.js. */
static const char SCRIPT_HBBTV_TASTE[] =
    "(function(){if(window.__hdsVk)return;window.__hdsVk=1;"
    "var k={VK_ENTER:13,VK_LEFT:37,VK_UP:38,VK_RIGHT:39,VK_DOWN:40,VK_0:48,VK_1:49,VK_2:50,VK_3:51,VK_4:52,"
    "VK_5:53,VK_6:54,VK_7:55,VK_8:56,VK_9:57,VK_RED:403,VK_GREEN:404,VK_YELLOW:405,VK_BLUE:406,VK_BACK:461,"
    "VK_PLAY:415,VK_PAUSE:19,VK_STOP:413,VK_FAST_FWD:417,VK_REWIND:412,VK_PAGE_UP:33,VK_PAGE_DOWN:34,"
    "VK_TELETEXT:459,VK_INFO:457,VK_PLAY_PAUSE:402,VK_NEXT:425,VK_PREV:424,VK_RECORD:416};"
    "var o=window.KeyEvent;if(!o){o={};try{window.KeyEvent=o;}catch(x){}}"
    "for(var n in k){try{if(o[n]===undefined)o[n]=k[n];}catch(x){}"
    "try{if(!(n in window))window[n]=k[n];}catch(x){}}})();";

/* VK_BACK (461) nu are keyval in WebKit (tasta Back da 166): evenimentul se face in pagina, pe elementul activ. */
#define HDS_VK_BACK 461

/* Tastele VCR (Keyset.VCR) si INFO: WebKit nu le da codurile HbbTV (CEA-2014 anexa F), deci evenimentul se face in
 * pagina, ca la BACK. 0 = tasta nu e una dintre ele. */
static int vk_media(guint cod)
{
    switch (cod) {
    case KEY_PLAY: return 415;
    case KEY_PAUSE: return 19;
    case KEY_PLAYPAUSE: return 402;
    case KEY_STOP: return 413;
    case KEY_FASTFORWARD: return 417;
    case KEY_REWIND: return 412;
    case KEY_NEXT: return 425;
    case KEY_PREVIOUS: return 424;
    case KEY_RECORD: return 416;
    case KEY_INFO: return 457;
    default: return 0;
    }
}

static void termina(int cod)
{
    cod_iesire = cod;
    if (bucla)
        g_main_loop_quit(bucla);
}

static gboolean captura_acum(gpointer d)
{
    (void)d;
    captura_programata = 0;
    if (opt.captura)
        stare(ecran_scrie_ppm(opt.captura) ? "CAPTURA scrisa" : "EROARE captura");
    return G_SOURCE_REMOVE;
}

/* Rezerva la rulare: GL mai departe pe procesor, prin repornirea lansatorului cu --cpu pe aceeasi pagina (o data). */
static void cere_repornire_pe_cpu(const char *motiv)
{
    char *rand = g_strdup_printf("REZERVA procesor %s", motiv);
    stare(rand);
    g_free(rand);
    const char *uri = vedere ? webkit_web_view_get_uri(vedere) : NULL;
    g_free(adresa_reluare);
    adresa_reluare = g_strdup(uri && *uri ? uri : opt.url);
    reporneste_pe_cpu = TRUE;
    termina(3);
}

static void anunta_prima_pagina(void)
{
    if (prima_pagina_anuntata)
        return;
    prima_pagina_anuntata = TRUE;
    if (paza_cadre) {
        g_source_remove(paza_cadre);
        paza_cadre = 0;
    }
    stare("PRIMA-PAGINA");
    if (opt.captura && !captura_programata)
        captura_programata = g_timeout_add(opt.captura_dupa_ms, captura_acum, NULL);
}

/* O pagina statica poate avea toate cadrele inainte de sfarsitul incarcarii: PRIMA-PAGINA se anunta la primul
 * cadru dupa incarcare sau chiar la incarcare, daca au venit deja cadre. */
static void cadru_afisat(void)
{
    cadre_primite++;
    if (pagina_incarcata)
        anunta_prima_pagina();
}

/* GL care porneste dar nu deseneaza (context refuzat de driver fara caderea procesului web): niciun cadru la
 * 15 s dupa incarcare inseamna trecerea pe procesor. */
static gboolean fara_cadre(gpointer d)
{
    (void)d;
    paza_cadre = 0;
    if (!cadre_primite && !opt.cpu)
        cere_repornire_pe_cpu("fara-cadre");
    return G_SOURCE_REMOVE;
}

/* ---------------------------------------------------------------- marirea paginii */

static const int TREPTE_MARIRE[] = { 100, 125, 150, 175, 200 };
#define N_TREPTE ((int)G_N_ELEMENTS(TREPTE_MARIRE))

static void mariri_incarca(void)
{
    mariri = g_hash_table_new_full(g_str_hash, g_str_equal, g_free, NULL);
    if (!fisier_mariri)
        return;
    char *text = NULL;
    if (!g_file_get_contents(fisier_mariri, &text, NULL, NULL))
        return;
    char **randuri = g_strsplit(text, "\n", 2000);
    for (char **r = randuri; *r; r++) {
        char **c = g_strsplit(*r, " ", 2);
        if (c[0] && c[1] && *c[0]) {
            int p = atoi(c[1]);
            if (p >= 50 && p <= 300)
                g_hash_table_replace(mariri, g_strdup(c[0]), GINT_TO_POINTER(p));
        }
        g_strfreev(c);
    }
    g_strfreev(randuri);
    g_free(text);
}

/* Se scrie numai la o schimbare facuta de om (Galben), intr-un fisier nou mutat peste cel vechi. */
static void mariri_scrie(void)
{
    if (!fisier_mariri)
        return;
    GString *s = g_string_new(NULL);
    GHashTableIter it;
    gpointer k, v;
    g_hash_table_iter_init(&it, mariri);
    while (g_hash_table_iter_next(&it, &k, &v))
        g_string_append_printf(s, "%s %d\n", (const char *)k, GPOINTER_TO_INT(v));
    char *nou = g_strconcat(fisier_mariri, ".nou", NULL);
    if (g_file_set_contents(nou, s->str, (gssize)s->len, NULL))
        rename(nou, fisier_mariri);
    g_free(nou);
    g_string_free(s, TRUE);
}

static int marire_procent(void)
{
    return (int)(webkit_web_view_get_zoom_level(vedere) * 100 + 0.5);
}

static void marire_aplica(int procent, gboolean anunta)
{
    procent = CLAMP(procent, 50, 300);
    webkit_web_view_set_zoom_level(vedere, procent / 100.0);
    if (!opt.hbbtv)
        ruleaza_js("if(window.__hdsChenar)window.__hdsChenar();", NULL, NULL);
    if (anunta)
        stare_f("MARIRE %d", procent);
}

static int marire_implicita(void)
{
    return (int)(opt.marire * 100 + 0.5);
}

/* +1 treapta urmatoare (dupa 200 % din nou 100 %), -1 cea de dinainte, 0 marirea implicita (si se uita cea aleasa). */
static void marire_pas(int pas)
{
    int acum = marire_procent();
    int m;
    if (pas == 0) {
        if (gazda_curenta)
            g_hash_table_remove(mariri, gazda_curenta);
        m = marire_implicita();
    } else if (pas > 0) {
        m = TREPTE_MARIRE[0];
        for (int i = 0; i < N_TREPTE; i++) {
            if (TREPTE_MARIRE[i] > acum + 1) {
                m = TREPTE_MARIRE[i];
                break;
            }
        }
    } else {
        m = TREPTE_MARIRE[N_TREPTE - 1];
        for (int i = N_TREPTE - 1; i >= 0; i--) {
            if (TREPTE_MARIRE[i] < acum - 1) {
                m = TREPTE_MARIRE[i];
                break;
            }
        }
    }
    if (pas != 0 && gazda_curenta)
        g_hash_table_replace(mariri, g_strdup(gazda_curenta), GINT_TO_POINTER(m));
    mariri_scrie();
    marire_aplica(m, TRUE);
}

/* La o pagina noua: marirea tinuta minte pe gazda ei, altfel cea implicita. */
static void marire_pentru_pagina(const char *uri)
{
    g_free(gazda_curenta);
    gazda_curenta = NULL;
    GUri *u = uri ? g_uri_parse(uri, G_URI_FLAGS_NONE, NULL) : NULL;
    if (u) {
        if (g_uri_get_host(u))
            gazda_curenta = g_ascii_strdown(g_uri_get_host(u), -1);
        g_uri_unref(u);
    }
    gpointer p = gazda_curenta ? g_hash_table_lookup(mariri, gazda_curenta) : NULL;
    marire_aplica(p ? GPOINTER_TO_INT(p) : marire_implicita(), FALSE);
}

/* --marire-auto: raportul dintre latimea ferestrei si latimea paginii; sub 0,97 pagina se micsoreaza (cel mult 0,7). */
static void potrivire_gata(GObject *o, GAsyncResult *r, gpointer d)
{
    (void)d;
    JSCValue *v = webkit_web_view_evaluate_javascript_finish(WEBKIT_WEB_VIEW(o), r, NULL);
    if (!v)
        return;
    double raport = jsc_value_is_number(v) ? jsc_value_to_double(v) : 1.0;
    g_object_unref(v);
    if (raport > 0.1 && raport < 0.97) {
        int m = (int)(marire_procent() * raport);
        marire_aplica(MAX(m, 70), FALSE);
    }
}

static void potriveste_latimea(void)
{
    if (!opt.marire_auto || (gazda_curenta && g_hash_table_contains(mariri, gazda_curenta)))
        return;
    ruleaza_js("(function(){var d=document.documentElement,b=document.body;"
        "var w=Math.max(d?d.scrollWidth:0,b?b.scrollWidth:0),v=window.innerWidth||0;"
        "return (w>0&&v>0)?v/w:1;})()", potrivire_gata, NULL);
}

static void progres_schimbat(WebKitWebView *v, GParamSpec *p, gpointer d)
{
    (void)p; (void)d;
    int procent = (int)(webkit_web_view_get_estimated_load_progress(v) * 100 + 0.5);
    if (procent >= ultim_progres + 5 || procent == 100 || procent < ultim_progres) {
        ultim_progres = procent;
        stare_f("PROGRES %d", procent);
    }
}

static void incarcare_schimbata(WebKitWebView *v, WebKitLoadEvent ev, gpointer d)
{
    (void)d;
    if (ev == WEBKIT_LOAD_STARTED) {
        ultim_progres = -1;
        stare("INCARCARE");
    } else if (ev == WEBKIT_LOAD_COMMITTED) {
        chenar_uita();
        marire_pentru_pagina(webkit_web_view_get_uri(v));
        if (strcmp(camp_fel, "niciunul")) {
            g_strlcpy(camp_fel, "niciunul", sizeof(camp_fel));
            stare("CAMP niciunul");
            strat_camp(FALSE);
        }
    } else if (ev == WEBKIT_LOAD_FINISHED) {
        stare("INCARCAT");
        pagina_incarcata = TRUE;
        if (cadre_primite)
            anunta_prima_pagina();
        else if (!opt.cpu && !paza_cadre)
            paza_cadre = g_timeout_add_seconds(15, fara_cadre, NULL);
        potriveste_latimea();
    }
}

/* Felul erorii de incarcare. Erorile retelei vin din libsoup/GIO cu domeniul lor pastrat (WebKit face GError din
 * numele quark-ului): numele gazdei care nu exista e G_RESOLVER_ERROR_NOT_FOUND ("dns"); fara DNS (retea cazuta) e tot
 * G_RESOLVER_ERROR, cu alt cod ("retea"), ca si legaturile refuzate sau fara raspuns (G_IO_ERROR). Un enigma2 care nu
 * stie "dns" il arata ca "alta". */
static const char *fel_eroare_incarcare(const GError *e)
{
    if (!e)
        return "alta";
    if (e->domain == G_RESOLVER_ERROR)
        return e->code == G_RESOLVER_ERROR_NOT_FOUND ? "dns" : "retea";
    if (e->domain == G_IO_ERROR) {
        switch (e->code) {
        case G_IO_ERROR_HOST_NOT_FOUND:
            return "dns";
        case G_IO_ERROR_CONNECTION_REFUSED:
        case G_IO_ERROR_TIMED_OUT:
        case G_IO_ERROR_NETWORK_UNREACHABLE:
        case G_IO_ERROR_HOST_UNREACHABLE:
        case G_IO_ERROR_CONNECTION_CLOSED:      /* acelasi cod ca G_IO_ERROR_BROKEN_PIPE */
        case G_IO_ERROR_PROXY_FAILED:
            return "retea";
        default:
            return "alta";
        }
    }
    if (e->domain == WEBKIT_NETWORK_ERROR)
        return "retea";
    if (e->domain == WEBKIT_POLICY_ERROR)
        return "politica";
    return "alta";
}

/* Pagina nu s-a incarcat: enigma2 afla felul (fara adresa); pagina de eroare a WebKit ramane pe ecran. */
static gboolean incarcare_esuata(WebKitWebView *v, WebKitLoadEvent ev, const char *uri, GError *e, gpointer d)
{
    (void)v; (void)ev; (void)uri; (void)d;
    if (g_error_matches(e, WEBKIT_NETWORK_ERROR, WEBKIT_NETWORK_ERROR_CANCELLED)
        || g_error_matches(e, WEBKIT_POLICY_ERROR, WEBKIT_POLICY_ERROR_FRAME_LOAD_INTERRUPTED_BY_POLICY_CHANGE))
        return FALSE;
    stare_f("EROARE-INCARCARE %s", fel_eroare_incarcare(e));
    return FALSE;
}

/* ---------------------------------------------------------------- ferestrele cerute de pagina, desenate de enigma2 */

static void autentificare_renuntata(WebKitAuthenticationRequest *r, gpointer d)
{
    (void)d;
    if (autentificare_curenta == r)
        g_clear_object(&autentificare_curenta);
}

/* Utilizatorul si parola (de exemplu Digest la interfata camului) le scrie omul in tastatura enigma2; raman numai in
 * memoria procesului, pentru sesiunea de acum. */
static gboolean autentificare(WebKitWebView *v, WebKitAuthenticationRequest *r, gpointer d)
{
    (void)v; (void)d;
    if (autentificare_curenta) {
        webkit_authentication_request_cancel(autentificare_curenta);
        g_clear_object(&autentificare_curenta);
    }
    autentificare_curenta = g_object_ref(r);
    g_signal_connect(r, "cancelled", G_CALLBACK(autentificare_renuntata), NULL);
    char *g = b64(webkit_authentication_request_get_host(r));
    stare_f("CERERE autentificare %s %d", g, webkit_authentication_request_is_retry(r) ? 1 : 0);
    g_free(g);
    return TRUE;
}

static void raspuns_autentificare(const char *arg)
{
    if (!autentificare_curenta)
        return;
    if (!arg) {
        webkit_authentication_request_cancel(autentificare_curenta);
        g_clear_object(&autentificare_curenta);
        return;
    }
    char **p = g_strsplit(arg, " ", 2);
    char *utilizator = din_b64(p[0]);
    char *parola = din_b64(p[0] ? p[1] : NULL);
    WebKitCredential *c = webkit_credential_new(utilizator, parola, WEBKIT_CREDENTIAL_PERSISTENCE_FOR_SESSION);
    webkit_authentication_request_authenticate(autentificare_curenta, c);
    webkit_credential_free(c);
    elibereaza_secret(utilizator);
    elibereaza_secret(parola);
    for (char **x = p; *x; x++)
        memset(*x, 0, strlen(*x));
    g_strfreev(p);
    g_clear_object(&autentificare_curenta);
}

static void dialog_inchide(void)
{
    if (dialog_curent) {
        webkit_script_dialog_close(dialog_curent);
        webkit_script_dialog_unref(dialog_curent);
        dialog_curent = NULL;
    }
}

/* alert, confirm, prompt si intrebarea la plecarea de pe pagina: raspunsul vine pe intrare („dialog 1|0 [b64]”). */
static gboolean dialog_script(WebKitWebView *v, WebKitScriptDialog *dlg, gpointer d)
{
    (void)v; (void)d;
    dialog_inchide();
    dialog_curent = webkit_script_dialog_ref(dlg);
    const char *fel = "alerta";
    switch (webkit_script_dialog_get_dialog_type(dlg)) {
    case WEBKIT_SCRIPT_DIALOG_CONFIRM: fel = "confirmare"; break;
    case WEBKIT_SCRIPT_DIALOG_PROMPT: fel = "intrebare"; break;
    case WEBKIT_SCRIPT_DIALOG_BEFORE_UNLOAD_CONFIRM: fel = "parasire"; break;
    default: break;
    }
    char *m = b64(webkit_script_dialog_get_message(dlg));
    if (webkit_script_dialog_get_dialog_type(dlg) == WEBKIT_SCRIPT_DIALOG_PROMPT) {
        char *implicit = b64(webkit_script_dialog_prompt_get_default_text(dlg));
        stare_f("CERERE dialog %s %s %s", fel, m, implicit);
        g_free(implicit);
    } else
        stare_f("CERERE dialog %s %s", fel, m);
    g_free(m);
    return TRUE;
}

static void raspuns_dialog(const char *arg)
{
    if (!dialog_curent || !arg)
        return;
    gboolean da = arg[0] == '1';
    WebKitScriptDialogType t = webkit_script_dialog_get_dialog_type(dialog_curent);
    if (t == WEBKIT_SCRIPT_DIALOG_CONFIRM || t == WEBKIT_SCRIPT_DIALOG_BEFORE_UNLOAD_CONFIRM)
        webkit_script_dialog_confirm_set_confirmed(dialog_curent, da);
    else if (t == WEBKIT_SCRIPT_DIALOG_PROMPT && da) {
        const char *b = strchr(arg, ' ');
        char *text = din_b64(b ? b + 1 : NULL);
        webkit_script_dialog_prompt_set_text(dialog_curent, text);
        elibereaza_secret(text);
    }
    dialog_inchide();
}

static void meniu_inchis(WebKitOptionMenu *m, gpointer d)
{
    (void)d;
    if (meniu_curent == m)
        g_clear_object(&meniu_curent);
}

/* Lista unui <select>: {"ales": i, "optiuni": [[text, activ, grup], ...]}, in base64. */
static gboolean arata_optiuni(WebKitWebView *v, WebKitOptionMenu *m, WebKitRectangle *r, gpointer d)
{
    (void)v; (void)r; (void)d;
    if (meniu_curent) {
        webkit_option_menu_close(meniu_curent);
        g_clear_object(&meniu_curent);
    }
    meniu_curent = g_object_ref(m);
    g_signal_connect(m, "close", G_CALLBACK(meniu_inchis), NULL);
    guint n = webkit_option_menu_get_n_items(m);
    int ales = -1;
    GString *s = g_string_new("{\"optiuni\":[");
    for (guint i = 0; i < n && i < 500; i++) {
        WebKitOptionMenuItem *it = webkit_option_menu_get_item(m, i);
        if (i)
            g_string_append_c(s, ',');
        g_string_append_c(s, '[');
        json_sir(s, webkit_option_menu_item_get_label(it));
        g_string_append_printf(s, ",%d,%d]", webkit_option_menu_item_is_enabled(it) ? 1 : 0,
            webkit_option_menu_item_is_group_label(it) ? 1 : 0);
        if (ales < 0 && webkit_option_menu_item_is_selected(it))
            ales = (int)i;
    }
    g_string_append_printf(s, "],\"ales\":%d}", ales);
    char *b = b64(s->str);
    stare_f("CERERE alegere %s", b);
    g_free(b);
    g_string_free(s, TRUE);
    return TRUE;
}

static void raspuns_alegere(const char *arg)
{
    if (!meniu_curent)
        return;
    WebKitOptionMenu *m = g_object_ref(meniu_curent);
    int i = arg ? atoi(arg) : -1;
    if (i >= 0 && (guint)i < webkit_option_menu_get_n_items(m))
        webkit_option_menu_activate_item(m, (guint)i);
    webkit_option_menu_close(m);
    g_object_unref(m);
    g_clear_object(&meniu_curent);
}

/* ---------------------------------------------------------------- campurile de text */

static void camp_schimbat(WebKitUserContentManager *m, JSCValue *v, gpointer d)
{
    (void)m; (void)d;
    static const char *const feluri[] = { "niciunul", "text", "parola", "numar", "zona", NULL };
    if (!jsc_value_is_string(v))
        return;
    char *f = jsc_value_to_string(v);
    for (int i = 0; feluri[i]; i++) {
        if (!g_strcmp0(f, feluri[i])) {
            if (strcmp(camp_fel, feluri[i])) {
                g_strlcpy(camp_fel, feluri[i], sizeof(camp_fel));
                stare_f("CAMP %s", camp_fel);
                strat_camp(i > 0);
            }
            break;
        }
    }
    g_free(f);
}

/* OK pe un camp de text (sau TEXT): enigma2 deschide tastatura lui, cu valoarea de acum (la parola fara valoare).
 * d nenul: cererea vine de la TEXT, deci fara camp se spune pe ecran ca nu e niciunul. */
static void tastatura_gata(GObject *o, GAsyncResult *r, gpointer d)
{
    JSCValue *v = webkit_web_view_evaluate_javascript_finish(WEBKIT_WEB_VIEW(o), r, NULL);
    if (!v)
        return;
    char *s = jsc_value_is_string(v) ? jsc_value_to_string(v) : NULL;
    g_object_unref(v);
    if (!s)
        return;
    char *valoare = strchr(s, '\n');
    if (valoare)
        *valoare++ = '\0';
    if (strcmp(s, "niciunul")) {
        char *b = b64(strcmp(s, "parola") ? valoare : NULL);
        stare_f("CERERE tastatura %s %s", s, b);
        elibereaza_secret(b);
    } else if (d) {
        stare("SCRIS fara-camp");
        strat_fara_camp();
    }
    elibereaza_secret(s);
}

static void cere_tastatura(void)
{
    ruleaza_js("(function(){" JS_DOC_ACTIV JS_ACTIV JS_FEL "var f=hdsFel(e),v='';"
        "if(f!=='parola'&&f!=='niciunul'){v=(e.value!==undefined)?String(e.value):String(e.innerText||'');}"
        "return f+'\\n'+v.slice(0,4096);})()", tastatura_gata, NULL);
}

/* TEXT: tastatura pentru campul cu focalizare; fara el, primul camp de text (activ, nu doar de citit) care se vede pe
 * ecran primeste focalizarea si tastatura. */
static void cere_scrisul(void)
{
    ruleaza_js("(function(){" JS_DOC_ACTIV JS_ACTIV JS_FEL "var f=hdsFel(e),v='';"
        "if(f==='niciunul'){var l=d.querySelectorAll('input,textarea,[contenteditable]'),"
        "h=window.innerHeight,w=window.innerWidth;"
        "for(var i=0;i<l.length;i++){var c=l[i];if(hdsFel(c)==='niciunul'||c.disabled||c.readOnly)continue;"
        "var r=c.getBoundingClientRect();if(r.width<4||r.height<4||r.bottom<=0||r.right<=0||r.top>=h||r.left>=w)continue;"
        "c.focus();e=c;f=hdsFel(c);break;}}"
        "if(f!=='parola'&&f!=='niciunul'){v=(e.value!==undefined)?String(e.value):String(e.innerText||'');}"
        "return f+'\\n'+v.slice(0,4096);})()", tastatura_gata, GINT_TO_POINTER(1));
}

/* Toata valoarea campului activ inlocuita (dupa tastatura enigma2); execCommand pastreaza evenimentele „input”. */
static void inlocuieste_valoarea(const char *text)
{
    GString *s = g_string_new("(function(t){" JS_DOC_ACTIV JS_ACTIV "if(!e)return;"
        "try{if(e.select)e.select();else d.execCommand('selectAll');}catch(x){d.execCommand('selectAll');}"
        "if(t)d.execCommand('insertText',false,t);else d.execCommand('delete');})(");
    js_sir(s, text);
    g_string_append(s, ");");
    ruleaza_js(s->str, NULL, NULL);
    memset(s->str, 0, s->len);
    g_string_free(s, TRUE);
}

/* ---------------------------------------------------------------- navigarea permisa */

static gboolean adresa_permisa(const char *uri)
{
    if (!opt.numai_gazda)
        return TRUE;
    if (!uri || g_str_has_prefix(uri, "about:"))
        return TRUE;
    gboolean da = FALSE;
    GUri *u = g_uri_parse(uri, G_URI_FLAGS_NONE, NULL);
    if (u) {
        const char *schema = g_uri_get_scheme(u);
        int port = g_uri_get_port(u);
        if (port < 0)
            port = !g_strcmp0(schema, "https") ? 443 : 80;
        char *aici = g_strdup_printf("%s:%d", g_uri_get_host(u) ? g_uri_get_host(u) : "", port);
        da = (!g_strcmp0(schema, "http") || !g_strcmp0(schema, "https")) && !g_ascii_strcasecmp(aici, opt.numai_gazda);
        g_free(aici);
        g_uri_unref(u);
    }
    return da;
}

static void hbbtv_script_la_zi(void);

/* Ferestrele noi (target=_blank) se deschid in aceeasi vedere; in modul cam, orice alta gazda se opreste. Inaintea
 * oricarei navigari scriptul stratului HbbTV e la zi (o refacere amanata se face acum). */
static gboolean decide(WebKitWebView *v, WebKitPolicyDecision *dec, WebKitPolicyDecisionType tip, gpointer d)
{
    (void)d;
    if (tip != WEBKIT_POLICY_DECISION_TYPE_NAVIGATION_ACTION && tip != WEBKIT_POLICY_DECISION_TYPE_NEW_WINDOW_ACTION)
        return FALSE;
    hbbtv_script_la_zi();
    WebKitNavigationAction *a = webkit_navigation_policy_decision_get_navigation_action(WEBKIT_NAVIGATION_POLICY_DECISION(dec));
    WebKitURIRequest *cerere = webkit_navigation_action_get_request(a);
    if (!adresa_permisa(webkit_uri_request_get_uri(cerere))) {
        webkit_policy_decision_ignore(dec);
        stare("BLOCAT");
        return TRUE;
    }
    if (tip == WEBKIT_POLICY_DECISION_TYPE_NEW_WINDOW_ACTION) {
        webkit_web_view_load_request(v, cerere);
        webkit_policy_decision_ignore(dec);
        return TRUE;
    }
    return FALSE;
}

/* Certificatul propriu al interfetei camului se primeste numai pentru gazda (implicit 127.0.0.1) si portul date la
 * pornire. */
static gboolean eroare_tls(WebKitWebView *v, const char *uri, GTlsCertificate *cert, GTlsCertificateFlags erori, gpointer d)
{
    (void)erori; (void)d;
    gboolean primit = FALSE;
    GUri *u = g_uri_parse(uri, G_URI_FLAGS_NONE, NULL);
    const char *gazda_permisa = opt.gazda_certificat ? opt.gazda_certificat : "127.0.0.1";
    if (u && opt.port_certificat > 0) {
        const char *gazda = g_uri_get_host(u);
        int port = g_uri_get_port(u);
        if (gazda && !g_strcmp0(gazda, gazda_permisa) && port == opt.port_certificat
            && !g_strcmp0(g_uri_get_scheme(u), "https")) {
            webkit_network_session_allow_tls_certificate_for_host(sesiune, cert, gazda);
            webkit_web_view_load_uri(v, uri);
            primit = TRUE;
        }
    }
    if (u)
        g_uri_unref(u);
    stare(primit ? "CERTIFICAT-LOCAL primit" : "EROARE certificat");
    return primit;
}

static void proces_web_oprit(WebKitWebView *v, WebKitWebProcessTerminationReason motiv, gpointer d)
{
    (void)v; (void)d;
    if (motiv == WEBKIT_WEB_PROCESS_CRASHED && !opt.cpu) {
        /* Procesul web a cazut cu GL (driver, ecran EGL, memorie video). In modul --cpu nu se mai reporneste. */
        cere_repornire_pe_cpu("proces-web-cazut");
        return;
    }
    stare(motiv == WEBKIT_WEB_PROCESS_EXCEEDED_MEMORY_LIMIT ? "EROARE memorie" : "EROARE proces-web");
    termina(3);
}

/* Copiii acestui proces (procesele WebKit ale incercarii cu GL: cel web, cazut, si cel de retea), din /proc. */
static int copiii_ramasi(pid_t *pid, int max)
{
    DIR *d = opendir("/proc");
    if (!d)
        return 0;
    pid_t eu = getpid();
    int n = 0;
    struct dirent *e;
    while (n < max && (e = readdir(d))) {
        char *capat = NULL;
        long p = strtol(e->d_name, &capat, 10);
        if (p <= 0 || !capat || *capat)
            continue;
        char cale[64], st[512];
        g_snprintf(cale, sizeof(cale), "/proc/%ld/stat", p);
        FILE *f = fopen(cale, "re");
        if (!f)
            continue;
        size_t k = fread(st, 1, sizeof(st) - 1, f);
        fclose(f);
        st[k] = 0;
        /* "pid (nume) stare ppid ...": numele poate avea spatii si paranteze, deci dupa ultima ')' */
        char *dupa = strrchr(st, ')');
        char fel;
        long ppid;
        if (dupa && sscanf(dupa + 1, " %c %ld", &fel, &ppid) == 2 && ppid == (long)eu)
            pid[n++] = (pid_t)p;
    }
    closedir(d);
    return n;
}

/* Inainte de repornirea pe procesor: dupa execv nimeni nu i-ar mai astepta pe copiii incercarii cu GL (bucla GLib care
 * ii culegea s-a oprit, iar imaginea noua nu stie de ei), deci ar ramane zombi pana la inchiderea aplicatiei. Se culeg
 * cei iesiti; cei inca vii (procesul de retea iese singur cand legatura cu el se inchide) se asteapta cel mult 1 s, apoi
 * se opresc cu SIGKILL si se culeg (repornirea pe procesor se face o singura data, deci intarzierea e rara). Numai
 * copiii acestui proces, luati din /proc: grupul de procese e al aplicatiei intregi, deci niciun semnal pe grup. */
static void culege_copiii(void)
{
    gint64 capat = g_get_monotonic_time() + G_USEC_PER_SEC;
    int culesi = 0;
    for (;;) {
        pid_t r = waitpid(-1, NULL, WNOHANG);
        if (r > 0) {
            culesi++;
            continue;
        }
        if (r < 0 && errno == EINTR)
            continue;
        if (r < 0 && errno == ECHILD)
            break;                              /* niciun copil ramas */
        if (r < 0 || g_get_monotonic_time() >= capat) {
            pid_t vii[64];
            int n = copiii_ramasi(vii, G_N_ELEMENTS(vii));
            for (int i = 0; i < n; i++)
                kill(vii[i], SIGKILL);
            for (int i = 0; i < n; i++) {
                while (waitpid(vii[i], NULL, 0) < 0 && errno == EINTR)
                    ;
                culesi++;
            }
            break;
        }
        g_usleep(10 * 1000);
    }
    if (culesi)
        g_printerr("hds-navigator: %d procese culese inainte de repornirea pe procesor\n", culesi);
}

/* Acelasi program, aceleasi optiuni, plus --cpu si pagina de reluat. Nu se intoarce decat daca execv esueaza. */
static void reporneste_cu_cpu(void)
{
    GPtrArray *a = g_ptr_array_new();
    for (char **p = argv_pornire; p && *p; p++) {
        if (p != argv_pornire && url_pornire && !strcmp(*p, url_pornire))
            continue;
        /* chenarul vechi (--chenar, --chenar-X V sau --chenar-X=V): mai jos vine cel de acum */
        if (p != argv_pornire && !strcmp(*p, "--chenar"))
            continue;
        if (p != argv_pornire && g_str_has_prefix(*p, "--chenar-")) {
            if (!strchr(*p, '=') && p[1])
                p++;
            continue;
        }
        g_ptr_array_add(a, *p);
    }
    /* stilul chenarului de acum (comanda "chenar" l-a putut schimba cat a rulat) */
    if (opt.chenar)
        g_ptr_array_add(a, (gpointer)"--chenar");
    const char *stil[] = { "--chenar-culoare", CULORI_NUME[chenar.culoare], "--chenar-forma", FORME_NUME[chenar.forma],
        "--chenar-grosime", GROSIMI_NUME[chenar.grosime], "--chenar-puls", PULSURI_NUME[chenar.puls] };
    for (guint k = 0; k < G_N_ELEMENTS(stil); k++)
        g_ptr_array_add(a, (gpointer)stil[k]);
    g_ptr_array_add(a, (gpointer)"--cpu");
    g_ptr_array_add(a, adresa_reluare);
    g_ptr_array_add(a, NULL);
    culege_copiii();
    stare("REPORNIRE procesor");
    fflush(stderr);
    execv("/proc/self/exe", (char **)a->pdata);
    stare("EROARE repornire");
    g_ptr_array_free(a, TRUE);
}

static guint32 timp_ms(void)
{
    return (guint32)(g_get_monotonic_time() / 1000);
}

static void trimite_tasta(guint keyval, guint cod_evdev, gboolean apasat)
{
    WPEView *v = webkit_web_view_get_wpe_view(vedere);
    if (!v)
        return;
    if (apasat)
        masura_tasta();
    WPEEvent *e = wpe_event_keyboard_new(apasat ? WPE_EVENT_KEYBOARD_KEY_DOWN : WPE_EVENT_KEYBOARD_KEY_UP,
        v, WPE_INPUT_SOURCE_KEYBOARD, timp_ms(), (WPEModifiers)0, cod_evdev + 8, keyval);
    wpe_view_event(v, e);
    wpe_event_unref(e);
}

/* ---------------------------------------------------------------- indicatorul: evenimentele */

#define INDICATOR_PAS_MS 20
#define INDICATOR_AJUTOR_MS 4000

/* Miscare, apasare sau eliberare in pozitia sagetii (puncte ale vederii = pixeli de ecran / scara). La apasare
 * numarul de apasari il socoteste vederea (dublu clic); la eliberare e 0, ca in WebKit (cu alt numar
 * wpe_event_pointer_button_new intoarce NULL). */
static void indicator_eveniment(WPEEventType tip, double dx, double dy)
{
    WPEView *v = webkit_web_view_get_wpe_view(vedere);
    if (!v)
        return;
    double x = ind.x / opt.scara, y = ind.y / opt.scara;
    guint32 t = timp_ms();
    WPEModifiers m = ind.apasat ? WPE_MODIFIER_POINTER_BUTTON1 : (WPEModifiers)0;
    WPEEvent *e;
    if (tip == WPE_EVENT_POINTER_MOVE)
        e = wpe_event_pointer_move_new(tip, v, WPE_INPUT_SOURCE_MOUSE, t, m, x, y, dx / opt.scara, dy / opt.scara);
    else {
        guint apasari = tip == WPE_EVENT_POINTER_DOWN ? wpe_view_compute_press_count(v, x, y, WPE_BUTTON_PRIMARY, t) : 0;
        if (tip == WPE_EVENT_POINTER_DOWN)
            masura_tasta();
        e = wpe_event_pointer_button_new(tip, v, WPE_INPUT_SOURCE_MOUSE, t, m, WPE_BUTTON_PRIMARY, x, y, apasari);
    }
    if (!e)
        return;
    wpe_view_event(v, e);
    wpe_event_unref(e);
}

/* Derularea in pozitia sagetii, cu cat a impins sageata dincolo de margine (pixeli de ecran). */
static void indicator_deruleaza(double dx, double dy)
{
    WPEView *v = webkit_web_view_get_wpe_view(vedere);
    if (!v)
        return;
    WPEEvent *e = wpe_event_scroll_new(v, WPE_INPUT_SOURCE_MOUSE, timp_ms(), (WPEModifiers)0,
        -dx / opt.scara, -dy / opt.scara, TRUE, FALSE, ind.x / opt.scara, ind.y / opt.scara);
    if (!e)
        return;
    wpe_view_event(v, e);
    wpe_event_unref(e);
}

static void indicator_muta(double mx, double my)
{
    double w = opt.latime * opt.scara - 1, h = opt.inaltime * opt.scara - 1;
    double nx = CLAMP(ind.x + mx, 0.0, w), ny = CLAMP(ind.y + my, 0.0, h);
    double peste_x = ind.x + mx - nx, peste_y = ind.y + my - ny;
    double dx = nx - ind.x, dy = ny - ind.y;
    ind.x = nx;
    ind.y = ny;
    if (dx != 0.0 || dy != 0.0) {
        indicator_eveniment(WPE_EVENT_POINTER_MOVE, dx, dy);
        strat_muta_indicator();
    }
    if (peste_x != 0.0 || peste_y != 0.0)
        indicator_deruleaza(peste_x, peste_y);
}

/* Cat o sageata e tinuta: viteza creste de la 150 la 1800 de pixeli pe secunda (la 1080p) in prima secunda. */
static gboolean indicator_pas(gpointer d)
{
    (void)d;
    int dx = (ind.dreapta ? 1 : 0) - (ind.stanga ? 1 : 0), dy = (ind.jos ? 1 : 0) - (ind.sus ? 1 : 0);
    if (!ind.activ || (!dx && !dy)) {
        ind.ceas = 0;
        return G_SOURCE_REMOVE;
    }
    gint64 acum = g_get_monotonic_time();
    double dt = (acum - ind.ultim) / 1e6, t = (acum - ind.de_la) / 1e6;
    ind.ultim = acum;
    double viteza = (150.0 + 1650.0 * CLAMP((t - 0.25) / 0.8, 0.0, 1.0)) * opt.scara / 1.5;
    indicator_muta(dx * viteza * dt, dy * viteza * dt);
    return G_SOURCE_CONTINUE;
}

static gboolean indicator_ajutor_gata(gpointer d)
{
    (void)d;
    ind.ceas_ajutor = 0;
    strat_deseneaza(TRUE);
    return G_SOURCE_REMOVE;
}

static void indicator_opreste_sagetile(void)
{
    ind.sus = ind.jos = ind.stanga = ind.dreapta = FALSE;
}

/* ALBASTRU (sau comanda „indicator”): pornit, sageata pleaca din mijlocul elementului cu focalizare (altfel din
 * mijlocul ecranului) si jos apare cateva secunde textul indicatorului. */
static void indicator_comuta(gboolean activ)
{
    if (activ == ind.activ)
        return;
    indicator_opreste_sagetile();
    if (ind.apasat) {
        ind.apasat = FALSE;
        indicator_eveniment(WPE_EVENT_POINTER_UP, 0, 0);
    }
    ind.activ = activ;
    if (ind.ceas_ajutor) {
        g_source_remove(ind.ceas_ajutor);
        ind.ceas_ajutor = 0;
    }
    if (activ) {
        if (strat.are_tinta) {
            ind.x = strat.tinta.x + strat.tinta.l / 2.0;
            ind.y = strat.tinta.y + strat.tinta.i / 2.0;
        } else {
            ind.x = opt.latime * opt.scara / 2.0;
            ind.y = opt.inaltime * opt.scara / 2.0;
        }
        ind.x = CLAMP(ind.x, 0.0, opt.latime * opt.scara - 1);
        ind.y = CLAMP(ind.y, 0.0, opt.inaltime * opt.scara - 1);
        indicator_eveniment(WPE_EVENT_POINTER_MOVE, 0, 0);
        ind.ceas_ajutor = g_timeout_add(INDICATOR_AJUTOR_MS, indicator_ajutor_gata, NULL);
    }
    stare_f("INDICATOR %d", activ ? 1 : 0);
    strat_deseneaza(TRUE);
}

/* Tastele cat indicatorul e pornit: sagetile il misca (la apasare un pas mic, apoi ceasul), OK face clic. TRUE daca
 * tasta a fost a indicatorului. */
static gboolean indicator_tasta(guint cod, int valoare)
{
    gboolean *sageata = NULL;
    double pas = px_ecran(4.0), mx = 0, my = 0;
    switch (cod) {
    case KEY_UP: sageata = &ind.sus; my = -pas; break;
    case KEY_DOWN: sageata = &ind.jos; my = pas; break;
    case KEY_LEFT: sageata = &ind.stanga; mx = -pas; break;
    case KEY_RIGHT: sageata = &ind.dreapta; mx = pas; break;
    case KEY_OK:
    case KEY_ENTER:
    case KEY_SELECT:
        if (valoare == 1 && !ind.apasat) {
            indicator_eveniment(WPE_EVENT_POINTER_MOVE, 0, 0);
            ind.apasat = TRUE;
            indicator_eveniment(WPE_EVENT_POINTER_DOWN, 0, 0);
        } else if (valoare == 0 && ind.apasat) {
            ind.apasat = FALSE;
            indicator_eveniment(WPE_EVENT_POINTER_UP, 0, 0);
        }
        return TRUE;
    default:
        return FALSE;
    }
    if (valoare == 2)
        return TRUE;  /* repetarea telecomenzii nu conteaza: ceasul misca sageata cat e tinuta */
    gboolean se_misca = ind.sus || ind.jos || ind.stanga || ind.dreapta;
    *sageata = valoare != 0;
    if (valoare == 0)
        stare_f("INDICATOR-LA %d %d", (int)ind.x, (int)ind.y);
    if (valoare == 1) {
        gint64 acum = g_get_monotonic_time();
        if (!se_misca)
            ind.de_la = acum;
        ind.ultim = acum;
        indicator_muta(mx, my);
        if (!ind.ceas)
            ind.ceas = g_timeout_add(INDICATOR_PAS_MS, indicator_pas, NULL);
    }
    return TRUE;
}

/* Telecomanda apucata numai cat navigatorul e pe ecran; enigma2 o ia inapoi dupa „ASCUNS”. */
static void intrari_apuca(gboolean da)
{
    for (int i = 0; i < n_intrari; i++) {
        if (ioctl(intrari_fd[i], EVIOCGRAB, da ? 1 : 0) < 0 && da)
            g_printerr("HDS-NAV AVERTISMENT apucare %d\n", errno);
    }
}

static void arata(gboolean da)
{
    if (!da && opt.hbbtv)
        ecran_goleste();   /* aplicatia HbbTV ascunsa: canalul se vede pana redeseneaza enigma2 */
    ecran.ascuns = !da;
    indicator_opreste_sagetile();
    intrari_apuca(da);
    if (da)
        ecran_redeseneaza_tot();
    stare(da ? "ARATAT" : "ASCUNS");
}

static gboolean camp_de_text(void)
{
    return strcmp(camp_fel, "niciunul") != 0;
}

static void tasta_js(int cod_vk, gboolean apasat)
{
    char *s = g_strdup_printf("(function(){var d=document,t=d.activeElement||d.body||d.documentElement;if(!t)return;"
        "var e=new KeyboardEvent('%s',{bubbles:true,cancelable:true,view:window});"
        "Object.defineProperty(e,'keyCode',{get:function(){return %d;}});"
        "Object.defineProperty(e,'which',{get:function(){return %d;}});"
        "t.dispatchEvent(e);})();", apasat ? "keydown" : "keyup", cod_vk, cod_vk);
    ruleaza_js(s, NULL, NULL);
    g_free(s);
}

/* Modul HbbTV: numai tastele aplicatiei (le alege enigma2, Components/HdsHbbtvPornire.py); fara tastatura enigma2,
 * fara mariri, fara tastele navigatorului. Culorile ajung in pagina cu keyCode 403-406 (tabelul WPE din WebKit). */
static void tasta_hbbtv(guint cod, int valoare)
{
    gboolean apasat = valoare != 0;
    guint keyval = 0;

    switch (cod) {
    case KEY_UP: keyval = WPE_KEY_Up; break;
    case KEY_DOWN: keyval = WPE_KEY_Down; break;
    case KEY_LEFT: keyval = WPE_KEY_Left; break;
    case KEY_RIGHT: keyval = WPE_KEY_Right; break;
    case KEY_OK:
    case KEY_ENTER:
    case KEY_SELECT: keyval = WPE_KEY_Return; break;
    case KEY_RED: keyval = WPE_KEY_Red; break;
    case KEY_GREEN: keyval = WPE_KEY_Green; break;
    case KEY_YELLOW: keyval = WPE_KEY_Yellow; break;
    case KEY_BLUE: keyval = WPE_KEY_Blue; break;
    case KEY_1: case KEY_2: case KEY_3: case KEY_4: case KEY_5:
    case KEY_6: case KEY_7: case KEY_8: case KEY_9:
        keyval = WPE_KEY_1 + (cod - KEY_1);
        break;
    case KEY_0: keyval = WPE_KEY_0; break;
    case KEY_BACK:
        tasta_js(HDS_VK_BACK, apasat);
        return;
    case KEY_PAGEUP: keyval = WPE_KEY_Page_Up; break;
    case KEY_PAGEDOWN: keyval = WPE_KEY_Page_Down; break;
    default:
        if (vk_media(cod))
            tasta_js(vk_media(cod), apasat);
        return;
    }
    trimite_tasta(keyval, cod, apasat);
}

/* Telecomanda: sagetile si OK merg in pagina (navigare spatiala); tastele navigatorului le hotaraste lansatorul si pe
 * cele care cer o fereastra le spune enigma2 („TASTA ...”, „CERERE ...”). Numai la apasare (valoare 1). */
static void tasta_telecomanda(guint cod, int valoare)
{
    gboolean apasat = valoare != 0;
    guint keyval = 0;

    if (opt.hbbtv) {
        tasta_hbbtv(cod, valoare);
        return;
    }
    if (ind.activ && indicator_tasta(cod, valoare))
        return;
    switch (cod) {
    case KEY_UP: keyval = WPE_KEY_Up; break;
    case KEY_DOWN: keyval = WPE_KEY_Down; break;
    case KEY_LEFT: keyval = WPE_KEY_Left; break;
    case KEY_RIGHT: keyval = WPE_KEY_Right; break;
    case KEY_OK:
    case KEY_ENTER:
    case KEY_SELECT:
        if (valoare == 1 && camp_de_text()) {
            ok_spre_tastatura = TRUE;
            cere_tastatura();
            return;
        }
        if (ok_spre_tastatura) {
            if (valoare == 0)
                ok_spre_tastatura = FALSE;
            return;
        }
        keyval = WPE_KEY_Return;
        break;
    case KEY_TEXT:
        if (valoare == 1)
            cere_scrisul();
        return;
    case KEY_ESC: keyval = WPE_KEY_Escape; break;
    case KEY_BACKSPACE: keyval = WPE_KEY_BackSpace; break;
    case KEY_TAB: keyval = WPE_KEY_Tab; break;
    case KEY_PAGEUP:
    case KEY_CHANNELUP: keyval = WPE_KEY_Page_Up; break;
    case KEY_PAGEDOWN:
    case KEY_CHANNELDOWN: keyval = WPE_KEY_Page_Down; break;
    case KEY_1: case KEY_2: case KEY_3: case KEY_4: case KEY_5:
    case KEY_6: case KEY_7: case KEY_8: case KEY_9:
        keyval = WPE_KEY_1 + (cod - KEY_1);
        break;
    case KEY_0: keyval = WPE_KEY_0; break;
    case KEY_EXIT:
        if (valoare == 1) {
            if (webkit_web_view_can_go_back(vedere))
                webkit_web_view_go_back(vedere);
            else
                stare("TASTA iesire");
        }
        return;
    case KEY_POWER:
        if (valoare == 1)
            stare("TASTA inchide");
        return;
    case KEY_MENU:
    case KEY_INFO:
        if (valoare == 1)
            stare("TASTA meniu");
        return;
    case KEY_BLUE:
        if (valoare == 1)
            indicator_comuta(!ind.activ);
        return;
    case KEY_BACK:
    case KEY_PREVIOUS:
        if (valoare == 1)
            webkit_web_view_go_back(vedere);
        return;
    case KEY_NEXT:
        if (valoare == 1)
            webkit_web_view_go_forward(vedere);
        return;
    case KEY_RED:
        if (valoare == 1) {
            char *b = b64(webkit_web_view_get_uri(vedere));
            stare_f("CERERE adresa %s", b);
            g_free(b);
        }
        return;
    case KEY_GREEN:
        if (valoare == 1)
            stare("TASTA favorite");
        return;
    case KEY_YELLOW:
        if (valoare == 1)
            marire_pas(1);
        return;
    default:
        return;
    }
    trimite_tasta(keyval, cod, apasat);
}

static gboolean intrare_evdev(int fd, GIOCondition c, gpointer d)
{
    (void)d;
    if (c & (G_IO_HUP | G_IO_ERR))
        return G_SOURCE_REMOVE;
    struct input_event ev[16];
    ssize_t n = read(fd, ev, sizeof(ev));
    if (n <= 0)
        return (n < 0 && errno == EAGAIN) ? G_SOURCE_CONTINUE : G_SOURCE_REMOVE;
    if (ecran.ascuns)
        return G_SOURCE_CONTINUE;  /* tastele sunt ale enigma2 cat navigatorul e ascuns */
    for (ssize_t i = 0; i < n / (ssize_t)sizeof(ev[0]); i++) {
        if (ev[i].type == EV_KEY)
            tasta_telecomanda(ev[i].code, ev[i].value);
    }
    return G_SOURCE_CONTINUE;
}

/* ---------------------------------------------------------------- stratul HbbTV (obiectele OIPF, etapa H3) */

#define HBBTV_JS_IMPLICIT "/usr/share/hds-navigator/hds-hbbtv.js"
#define HBBTV_JS_MAXIM (512 * 1024)
#define HBBTV_PARTE_MAXIM (256 * 1024)
#define HBBTV_MESAJ_MAXIM 3000
#define HBBTV_CUVINTE_MAXIM 9
#define HBBTV_MESAJE_PE_SECUNDA 40
#define HBBTV_EV_MAXIM (128 * 1024)         /* "hbbtv-ev": base64, de la enigma2 (si raspunsurile traducerii) */
#define HBBTV_TRADU_PE_SECUNDA 4
#define HBBTV_TRADU_ID_MAXIM 16

static const char *const PARTI_HBBTV[] = { "app", "canal", "config", "lista", "programe", "taste", NULL };
static const char *const COMENZI_HBBTV[] = { "arata", "ascunde", "taste", "distruge", "aplicatie", "leaga", "canal",
    "urmator", "anterior", "opreste", "elibereaza", "ecran-intreg", "fereastra", "tradu", "av", NULL };

static WebKitUserContentManager *continut_pagina;
static WebKitUserScript *script_hbbtv;
static char *sursa_hbbtv;                   /* hds-hbbtv.js; NULL fara strat */
static GHashTable *parti_hbbtv;             /* cheie -> JSON, ultima stare data de enigma2 */
static guint script_hbbtv_amanat;           /* refacerea scriptului, dupa randurile venite deodata */
static gboolean dvb_pornit;                 /* schema dvb:// inregistrata (modul HbbTV) */

static gboolean in_lista(const char *const *lista, const char *text)
{
    for (int i = 0; lista[i]; i++) {
        if (!strcmp(lista[i], text))
            return TRUE;
    }
    return FALSE;
}

/* Scriptul paginilor: starea (fiecare parte ca sir JavaScript scapat, citit cu JSON.parse), apoi hds-hbbtv.js. Se
 * face din nou la fiecare parte noua, ca urmatorul document sa porneasca de la starea de acum. */
static void hbbtv_script_pune(void)
{
    if (script_hbbtv_amanat) {
        g_source_remove(script_hbbtv_amanat);
        script_hbbtv_amanat = 0;
    }
    if (!sursa_hbbtv || !continut_pagina)
        return;
    GString *s = g_string_new("window.__hdsHbbtvStare={};");
    /* ce stie lansatorul (scriptul paginii alege dupa asta calea traducerii si adresele dvb://) */
    g_string_append_printf(s, "window.__hdsHbbtvStare.lansator={\"versiune\":\"%s\",\"tradu\":1,\"dvb\":%d,"
        "\"av\":1};", HDS_NAV_VERSIUNE, dvb_pornit ? 1 : 0);
    for (int i = 0; PARTI_HBBTV[i]; i++) {
        const char *json = g_hash_table_lookup(parti_hbbtv, PARTI_HBBTV[i]);
        if (!json)
            continue;
        g_string_append_printf(s, "try{window.__hdsHbbtvStare.%s=JSON.parse(", PARTI_HBBTV[i]);
        js_sir(s, json);
        g_string_append(s, ");}catch(x){}");
    }
    g_string_append_c(s, '\n');
    g_string_append(s, sursa_hbbtv);
    WebKitUserScript *nou = webkit_user_script_new(s->str, WEBKIT_USER_CONTENT_INJECT_TOP_FRAME,
        WEBKIT_USER_SCRIPT_INJECT_AT_DOCUMENT_START, NULL, NULL);
    g_string_free(s, TRUE);
    if (script_hbbtv) {
        webkit_user_content_manager_remove_script(continut_pagina, script_hbbtv);
        webkit_user_script_unref(script_hbbtv);
    }
    webkit_user_content_manager_add_script(continut_pagina, nou);
    script_hbbtv = nou;
}

static gboolean hbbtv_script_amanat_acum(gpointer d)
{
    (void)d;
    script_hbbtv_amanat = 0;
    hbbtv_script_pune();
    return G_SOURCE_REMOVE;
}

/* Refacerea scriptului dupa o parte noua se amana pana cand bucla nu mai are nimic de facut (prioritatea mai mica decat
 * citirea intrarii standard): partile venite una dupa alta (sase la "HBBTV strat 1") il refac o singura data. Pagina de
 * acum primeste fiecare parte pe loc (hbbtv_spre_pagina); scriptul refacut e numai pentru documentele urmatoare. */
static void hbbtv_script_amana(void)
{
    if (!script_hbbtv_amanat)
        script_hbbtv_amanat = g_idle_add_full(G_PRIORITY_DEFAULT_IDLE, hbbtv_script_amanat_acum, NULL, NULL);
}

/* O refacere amanata se face acum (inaintea unei navigari). */
static void hbbtv_script_la_zi(void)
{
    if (script_hbbtv_amanat)
        hbbtv_script_pune();
}

/* O parte a starii (JSON in base64): tinuta minte; FALSE daca nu e buna. */
static gboolean hbbtv_parte_pune(const char *cheie, const char *b)
{
    if (!parti_hbbtv || !cheie || !in_lista(PARTI_HBBTV, cheie) || !b || strlen(b) > HBBTV_PARTE_MAXIM * 4 / 3 + 4)
        return FALSE;
    char *json = din_b64(b);
    if (!*json) {
        g_free(json);
        return FALSE;
    }
    g_hash_table_replace(parti_hbbtv, g_strdup(cheie), json);
    return TRUE;
}

/* window.__hdsHbbtvPrimeste(cheie, JSON.parse("...")) in pagina de acum (daca are stratul). */
static void hbbtv_spre_pagina(const char *cheie, const char *json)
{
    GString *s = g_string_new("(function(){var f=window.__hdsHbbtvPrimeste;if(typeof f!=='function')return;var v;"
        "try{v=JSON.parse(");
    js_sir(s, json);
    g_string_append_printf(s, ");}catch(x){return;}f(\"%s\",v);})();", cheie);
    ruleaza_js(s->str, NULL, NULL);
    g_string_free(s, TRUE);
}

/* "hbbtv-parte CHEIE BASE64" */
static void hbbtv_parte(char *arg)
{
    char *b = strchr(arg, ' ');
    if (!b) {
        stare("EROARE hbbtv-parte");
        return;
    }
    *b++ = '\0';
    char *vechi = g_strdup(parti_hbbtv ? g_hash_table_lookup(parti_hbbtv, arg) : NULL);
    if (!hbbtv_parte_pune(arg, b)) {
        g_free(vechi);
        stare("EROARE hbbtv-parte");
        return;
    }
    const char *nou = g_hash_table_lookup(parti_hbbtv, arg);
    if (g_strcmp0(vechi, nou))
        hbbtv_script_amana();       /* o parte neschimbata (cele de pe linia de comanda, trimise din nou) nu il reface */
    g_free(vechi);
    hbbtv_spre_pagina(arg, nou);
}

/* "hbbtv-ev BASE64": un eveniment pentru pagina de acum (nu se tine minte). */
static void hbbtv_ev(const char *arg)
{
    if (!sursa_hbbtv || strlen(arg) > HBBTV_EV_MAXIM) {
        stare("EROARE hbbtv-ev");
        return;
    }
    char *json = din_b64(arg);
    if (*json)
        hbbtv_spre_pagina("ev", json);
    g_free(json);
}

/* Debitul traducerilor: cel mult HBBTV_TRADU_PE_SECUNDA cereri "tradu" pe secunda (pe langa debitul tuturor mesajelor). */
static gboolean hbbtv_tradu_debit(void)
{
    static gint64 inceput;
    static int n;
    static gboolean anuntat;
    gint64 acum = g_get_monotonic_time();
    if (acum - inceput >= G_USEC_PER_SEC) {
        inceput = acum;
        n = 0;
        anuntat = FALSE;
    }
    if (++n <= HBBTV_TRADU_PE_SECUNDA)
        return TRUE;
    if (!anuntat) {
        stare("AVERTISMENT hbbtv-prea-multe-traduceri");
        anuntat = TRUE;
    }
    return FALSE;
}

/* "tradu ID BASE64": exact doua argumente; ID din cifre si litere mici (cel mult HBBTV_TRADU_ID_MAXIM), apoi numai
 * semnele base64. Textele raman in base64 pana la enigma2 (care le decodeaza si raspunde cu acelasi ID). */
static gboolean hbbtv_tradu_bun(const char *t)
{
    const char *id = strchr(t, ' ');
    if (!id)
        return FALSE;
    id++;
    const char *b = strchr(id, ' ');
    if (!b || b == id || b - id > HBBTV_TRADU_ID_MAXIM || !b[1] || strchr(b + 1, ' '))
        return FALSE;
    for (const char *p = id; p < b; p++) {
        if (!g_ascii_isdigit(*p) && !g_ascii_islower(*p))
            return FALSE;
    }
    for (const char *p = b + 1; *p; p++) {
        if (!g_ascii_isalnum(*p) && *p != '+' && *p != '/' && *p != '=')
            return FALSE;
    }
    return hbbtv_tradu_debit();
}

/* Un mesaj al paginii: comanda cunoscuta, apoi argumente numai din [A-Za-z0-9+/=._:,-], despartite de un spatiu. */
static gboolean hbbtv_mesaj_bun(const char *t)
{
    size_t n = strlen(t);
    if (!n || n > HBBTV_MESAJ_MAXIM || t[0] == ' ' || t[n - 1] == ' ')
        return FALSE;
    int cuvinte = 1;
    for (size_t i = 0; i < n; i++) {
        guchar c = (guchar)t[i];
        if (c == ' ') {
            if (t[i + 1] == ' ' || ++cuvinte > HBBTV_CUVINTE_MAXIM)
                return FALSE;
        } else if (!g_ascii_isalnum(c) && !strchr("+/=._:,-", c))
            return FALSE;
    }
    const char *sp = strchr(t, ' ');
    char *comanda = g_strndup(t, sp ? (gsize)(sp - t) : n);
    gboolean bun = in_lista(COMENZI_HBBTV, comanda);
    if (bun && !strcmp(comanda, "tradu"))
        bun = hbbtv_tradu_bun(t);
    g_free(comanda);
    return bun;
}

/* Cel mult HBBTV_MESAJE_PE_SECUNDA mesaje pe secunda spre enigma2 (o pagina nu poate ineca firul enigma2). */
static gboolean hbbtv_debit(void)
{
    static gint64 inceput;
    static int n;
    static gboolean anuntat;
    gint64 acum = g_get_monotonic_time();
    if (acum - inceput >= G_USEC_PER_SEC) {
        inceput = acum;
        n = 0;
        anuntat = FALSE;
    }
    if (++n <= HBBTV_MESAJE_PE_SECUNDA)
        return TRUE;
    if (!anuntat) {
        stare("AVERTISMENT hbbtv-prea-multe-mesaje");
        anuntat = TRUE;
    }
    return FALSE;
}

static void hbbtv_mesaj(WebKitUserContentManager *m, JSCValue *v, gpointer d)
{
    (void)m; (void)d;
    if (!jsc_value_is_string(v))
        return;
    char *t = jsc_value_to_string(v);
    if (t && hbbtv_mesaj_bun(t) && hbbtv_debit())
        stare_f("HBBTV %s", t);
    g_free(t);
}

/* Modul HbbTV, la pornire: scriptul obiectelor, starea data pe linia de comanda si puntea. */
static void hbbtv_strat_incarca(WebKitUserContentManager *c)
{
    const char *cale = opt.hbbtv_js && *opt.hbbtv_js ? opt.hbbtv_js : HBBTV_JS_IMPLICIT;
    gchar *text = NULL;
    gsize n = 0;
    if (!g_file_get_contents(cale, &text, &n, NULL) || n == 0 || n > HBBTV_JS_MAXIM || !g_utf8_validate(text, (gssize)n, NULL)) {
        g_free(text);
        stare("HBBTV strat 0 lipsa");
        return;
    }
    sursa_hbbtv = text;
    parti_hbbtv = g_hash_table_new_full(g_str_hash, g_str_equal, g_free, g_free);
    for (char **p = opt.hbbtv_parti; p && *p; p++) {
        char *egal = strchr(*p, '=');
        if (!egal)
            continue;
        char *cheie = g_strndup(*p, (gsize)(egal - *p));
        if (!hbbtv_parte_pune(cheie, egal + 1))
            stare("EROARE hbbtv-parte");
        g_free(cheie);
    }
    continut_pagina = c;
    g_signal_connect(c, "script-message-received::hdshbbtv", G_CALLBACK(hbbtv_mesaj), NULL);
    webkit_user_content_manager_register_script_message_handler(c, "hdshbbtv", NULL);
    hbbtv_script_pune();
    stare("HBBTV strat 1");
}

/* ---------------------------------------------------------------- erorile JavaScript ale paginii (modul HbbTV) */

#define ERORI_JS_PE_DOCUMENT 20
#define ERORI_JS_PE_SECUNDA 10
#define ERORI_JS_MAXIM 200
#define ERORI_JS_SEMNE 200

/* Injectat in toate cadrele, la inceputul documentului: exceptiile neprinse (ErrorEvent pe window), promisiunile
 * respinse fara tratare, console.error si scripturile sau foile de stil care nu s-au incarcat (evenimentul "error" al
 * elementului, prins la capturare). Din adrese ramane numai numele fisierului; orice adresa din text devine <adresa>. */
static const char SCRIPT_ERORI[] =
    "(function(){if(window.__hdsErori)return;window.__hdsErori=1;var n=0,h=null;"
    "try{h=window.webkit.messageHandlers.hdsnaverori;}catch(x){h=null;}if(!h)return;"
    "function a(s){return String(s).replace(/\\b[a-z][a-z0-9+.-]*:\\/\\/[^\\s'\")]*/gi,'<adresa>')"
    ".replace(/\\s+/g,' ').slice(0," G_STRINGIFY(ERORI_JS_SEMNE) ");}"
    "function f(u){u=String(u||'').split(/[?#]/)[0];return u.slice(u.lastIndexOf('/')+1).slice(0,60)||'-';}"
    "function t(s){if(n>=" G_STRINGIFY(ERORI_JS_PE_DOCUMENT) ")return;n++;try{h.postMessage(String(s));}catch(x){}}"
    "window.addEventListener('error',function(e){var g=e&&e.target;"
    "if(g&&g!==window&&g.tagName){var x=String(g.tagName).toLowerCase();"
    "if(x==='script')t('scriptul nu s-a incarcat: '+f(g.src));"
    "else if(x==='link')t('foaia de stil nu s-a incarcat: '+f(g.href));return;}"
    "if(e)t('eroare: '+a(e.message)+' ('+f(e.filename)+':'+(e.lineno|0)+':'+(e.colno|0)+')');},true);"
    "window.addEventListener('unhandledrejection',function(e){var r=e&&e.reason;"
    "t('promisiune respinsa: '+a(r&&r.message?r.message:r));});"
    "var c=window.console;if(c&&typeof c.error==='function'){var o=c.error;"
    "c.error=function(){try{t('console.error: '+a(Array.prototype.slice.call(arguments).join(' ')));}catch(x){}"
    "return o.apply(c,arguments);};}})();";

/* Cel mult ERORI_JS_PE_SECUNDA randuri pe secunda si ERORI_JS_MAXIM de la pornire (o pagina nu poate umple jurnalul). */
static gboolean erori_js_debit(void)
{
    static gint64 inceput;
    static int n, total;
    gint64 acum = g_get_monotonic_time();
    if (acum - inceput >= G_USEC_PER_SEC) {
        inceput = acum;
        n = 0;
    }
    if (total > ERORI_JS_MAXIM || ++n > ERORI_JS_PE_SECUNDA)
        return FALSE;
    if (++total > ERORI_JS_MAXIM) {
        fputs("hds-navigator: pagina: alte erori nescrise\n", stderr);
        fflush(stderr);
        return FALSE;
    }
    return TRUE;
}

/* Un rand pe iesirea de erori: UTF-8 valid, fara caractere de control, cel mult ERORI_JS_SEMNE semne. */
static void erori_js_mesaj(WebKitUserContentManager *m, JSCValue *v, gpointer d)
{
    (void)m; (void)d;
    if (!jsc_value_is_string(v) || !erori_js_debit())
        return;
    char *t = jsc_value_to_string(v);
    if (!t)
        return;
    if (!g_utf8_validate(t, -1, NULL)) {
        char *bun = g_utf8_make_valid(t, -1);
        g_free(t);
        t = bun;
    }
    for (char *p = t; *p; p++) {
        if ((guchar)*p < 0x20 || *p == 0x7f)
            *p = ' ';
    }
    glong n = g_utf8_strlen(t, -1);
    char *scurt = g_utf8_substring(t, 0, MIN(n, ERORI_JS_SEMNE));
    fprintf(stderr, "hds-navigator: pagina: %s\n", scurt);
    fflush(stderr);
    g_free(scurt);
    g_free(t);
}

static void erori_js_incarca(WebKitUserContentManager *c)
{
    g_signal_connect(c, "script-message-received::hdsnaverori", G_CALLBACK(erori_js_mesaj), NULL);
    webkit_user_content_manager_register_script_message_handler(c, "hdsnaverori", NULL);
    WebKitUserScript *s = webkit_user_script_new(SCRIPT_ERORI, WEBKIT_USER_CONTENT_INJECT_ALL_FRAMES,
        WEBKIT_USER_SCRIPT_INJECT_AT_DOCUMENT_START, NULL, NULL);
    webkit_user_content_manager_add_script(c, s);
    webkit_user_script_unref(s);
}

/* ---------------------------------------------------------------- schema dvb:// (caruselul DSM-CC, modul HbbTV) */

#define DVB_DOSAR_IMPLICIT "/tmp/hds-carusel"
#define DVB_FISIER_MAXIM (16 * 1024 * 1024)
#define DVB_MANIFEST_MAXIM (4 * 1024 * 1024)
#define DVB_ASTEPTARE_MS 8000
#define DVB_PAS_MS 200
#define DVB_BUCATI_MAXIM 24
#define DVB_NUME_MAXIM 255
#define DVB_CALE_MAXIM 2048
#define DVB_TIP_XHTML "application/vnd.hbbtv.xhtml+xml"
#define DVB_TIP_NECUNOSCUT "application/octet-stream"

static const char *const DVB_TIPURI[][2] = {
    { ".html", "text/html" }, { ".htm", "text/html" }, { ".xhtml", DVB_TIP_XHTML }, { ".cehtml", DVB_TIP_XHTML },
    { ".js", "application/javascript" }, { ".css", "text/css" }, { ".json", "application/json" },
    { ".xml", "application/xml" }, { ".png", "image/png" }, { ".jpg", "image/jpeg" }, { ".jpeg", "image/jpeg" },
    { ".gif", "image/gif" }, { ".svg", "image/svg+xml" }, { ".bmp", "image/bmp" }, { ".ico", "image/x-icon" },
    { ".webp", "image/webp" }, { ".txt", "text/plain" }, { ".ttf", "font/ttf" }, { ".otf", "font/otf" },
    { ".woff", "font/woff" }, { ".woff2", "font/woff2" }, { ".mp3", "audio/mpeg" }, { ".aac", "audio/aac" },
    { ".mp4", "video/mp4" }, { NULL, NULL }
};

typedef struct {
    WebKitURISchemeRequest *cerere;
    guint n[4];                 /* onid, tsid, sid, component_tag */
    gboolean cu_tsid;
    char **bucati;              /* numele din cale, decodate si verificate */
    char *cale;                 /* bucatile unite cu "/" (cheia din manifest) */
    gint64 termen;
} CerereDvb;

static const char *dvb_radacina(void)
{
    return opt.dvb_dosar && *opt.dvb_dosar ? opt.dvb_dosar : DVB_DOSAR_IMPLICIT;
}

/* "dvb://<onid>.[<tsid>].<sid>.<tag>[$<id>]<cale>" (ETSI TS 102 851 Tabelul 1, numerele in hex, tsid poate lipsi) ->
 * numerele si calea (de la "/" pana la "?" sau "#"; "/" cand lipseste). FALSE pentru orice altceva (de exemplu
 * dvb://current.ait/..., pe care il trateaza scriptul paginii). */
static gboolean dvb_desparte(const char *uri, guint n[4], gboolean *cu_tsid, char **cale)
{
    if (!uri || g_ascii_strncasecmp(uri, "dvb://", 6))
        return FALSE;
    const char *a = uri + 6;
    size_t la = strcspn(a, "/?#");
    char *autoritate = g_strndup(a, la);
    char *dolar = strchr(autoritate, '$');
    if (dolar)
        *dolar = '\0';
    char **p = g_strsplit(autoritate, ".", -1);
    gboolean bun = g_strv_length(p) == 4;
    *cu_tsid = TRUE;
    for (int i = 0; bun && i < 4; i++) {
        size_t l = strlen(p[i]);
        if (i == 1 && !l) {
            *cu_tsid = FALSE;
            n[i] = 0;
            continue;
        }
        if (l < 1 || l > 8) {
            bun = FALSE;
            break;
        }
        for (size_t k = 0; k < l; k++) {
            if (!g_ascii_isxdigit(p[i][k]))
                bun = FALSE;
        }
        if (bun)
            n[i] = (guint)g_ascii_strtoull(p[i], NULL, 16);
    }
    g_strfreev(p);
    g_free(autoritate);
    if (!bun)
        return FALSE;
    const char *rest = a + la;
    size_t lc = *rest == '/' ? strcspn(rest, "?#") : 0;
    *cale = lc ? g_strndup(rest, lc) : g_strdup("/");
    return TRUE;
}

/* Un nume din cale, deja decodat: fara gol, ".", "..", "/", "\", caractere de control (si U+0080..U+009F), cel mult
 * DVB_NUME_MAXIM octeti (aceleasi reguli ca la scrierea arborelui si la serverul local). */
static gboolean dvb_nume_bun(const char *n)
{
    size_t l = strlen(n);
    if (!l || l > DVB_NUME_MAXIM || !strcmp(n, ".") || !strcmp(n, "..") || strchr(n, '/') || strchr(n, '\\'))
        return FALSE;
    for (const guchar *p = (const guchar *)n; *p; p++) {
        if (*p < 0x20 || *p == 0x7f)
            return FALSE;
    }
    if (g_utf8_validate(n, -1, NULL)) {
        for (const char *p = n; *p; p = g_utf8_next_char(p)) {
            gunichar c = g_utf8_get_char(p);
            if (c >= 0x80 && c < 0xa0)
                return FALSE;
        }
    }
    return TRUE;
}

/* Calea ceruta ("/a/b%20c/") -> bucatile decodate, sau NULL cand nu e voie: bucati goale (afara de "/" de la capat),
 * "/" sau "\" codate, %00, nume nepermise, prea multe bucati. */
static char **dvb_bucati(const char *cale)
{
    if (!cale || cale[0] != '/' || strlen(cale) > DVB_CALE_MAXIM)
        return NULL;
    char **brut = g_strsplit(cale + 1, "/", -1);
    guint n = g_strv_length(brut);
    if (n && !*brut[n - 1]) {
        g_free(brut[n - 1]);
        brut[--n] = NULL;
    }
    GPtrArray *rez = g_ptr_array_new_with_free_func(g_free);
    gboolean bun = n <= DVB_BUCATI_MAXIM;
    for (guint i = 0; bun && i < n; i++) {
        char *nume = *brut[i] && !strchr(brut[i], '\\') ? g_uri_unescape_string(brut[i], "/\\") : NULL;
        if (!nume || !dvb_nume_bun(nume)) {
            g_free(nume);
            bun = FALSE;
            break;
        }
        g_ptr_array_add(rez, nume);
    }
    g_strfreev(brut);
    if (!bun) {
        g_ptr_array_free(rez, TRUE);
        return NULL;
    }
    g_ptr_array_add(rez, NULL);
    return (char **)g_ptr_array_free(rez, FALSE);
}

/* Numele dosarului caruselului in radacina ("onid.tsid.sid.tag", hex mic), sau NULL. Fara tsid: dosarul unic cu
 * acelasi onid, sid si tag. */
static char *dvb_nume_carusel(int radacina, const CerereDvb *c)
{
    if (c->cu_tsid)
        return g_strdup_printf("%x.%x.%x.%x", c->n[0], c->n[1], c->n[2], c->n[3]);
    int fd = dup(radacina);
    DIR *d = fd >= 0 ? fdopendir(fd) : NULL;
    if (!d) {
        if (fd >= 0)
            close(fd);
        return NULL;
    }
    char *gasit = NULL;
    int cate = 0;
    struct dirent *e;
    while ((e = readdir(d))) {
        char **p = g_strsplit(e->d_name, ".", -1);
        gboolean bun = g_strv_length(p) == 4;
        guint v[4] = { 0, 0, 0, 0 };
        for (int i = 0; bun && i < 4; i++) {
            size_t l = strlen(p[i]);
            bun = l >= 1 && l <= 8;
            for (size_t k = 0; bun && k < l; k++)
                bun = g_ascii_isxdigit(p[i][k]) && !g_ascii_isupper(p[i][k]);
            if (bun)
                v[i] = (guint)g_ascii_strtoull(p[i], NULL, 16);
        }
        if (bun && v[0] == c->n[0] && v[2] == c->n[2] && v[3] == c->n[3] && ++cate == 1)
            gasit = g_strdup(e->d_name);
        g_strfreev(p);
    }
    closedir(d);
    if (cate != 1) {
        g_free(gasit);
        return NULL;
    }
    return gasit;
}

/* Manifestul caruselului (<dosar>.json, scris de enigma2), tinut in memorie cat nu se schimba. */
static struct {
    char *cale;
    gint64 mtime;
    off_t marime;
    char *text;
} dvb_manifest;

static const char *dvb_manifest_citeste(int radacina, const char *nume_carusel)
{
    char *nume = g_strconcat(nume_carusel, ".json", NULL);
    int fd = openat(radacina, nume, O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK);
    char *cale = g_build_filename(dvb_radacina(), nume, NULL);
    g_free(nume);
    struct stat st;
    if (fd < 0 || fstat(fd, &st) || !S_ISREG(st.st_mode) || st.st_size > DVB_MANIFEST_MAXIM) {
        if (fd >= 0)
            close(fd);
        g_free(cale);
        return NULL;
    }
    gint64 mtime = (gint64)st.st_mtim.tv_sec * G_USEC_PER_SEC + st.st_mtim.tv_nsec / 1000;
    if (dvb_manifest.text && !g_strcmp0(dvb_manifest.cale, cale) && dvb_manifest.mtime == mtime
        && dvb_manifest.marime == st.st_size) {
        close(fd);
        g_free(cale);
        return dvb_manifest.text;
    }
    char *text = g_malloc((gsize)st.st_size + 1);
    gsize citit = 0;
    while (citit < (gsize)st.st_size) {
        ssize_t r = read(fd, text + citit, (gsize)st.st_size - citit);
        if (r < 0 && errno == EINTR)
            continue;
        if (r <= 0)
            break;
        citit += (gsize)r;
    }
    close(fd);
    text[citit] = '\0';
    g_free(dvb_manifest.cale);
    g_free(dvb_manifest.text);
    dvb_manifest.cale = cale;
    dvb_manifest.mtime = mtime;
    dvb_manifest.marime = st.st_size;
    dvb_manifest.text = text;
    return text;
}

/* Un sir JSON numai ASCII, ca json.dumps(..., ensure_ascii=True) din Python (forma cailor din manifest). */
static void dvb_json_ascii(GString *s, const char *t)
{
    g_string_append_c(s, '"');
    for (const char *p = t; *p; p = g_utf8_next_char(p)) {
        gunichar c = g_utf8_get_char(p);
        switch (c) {
        case '"': g_string_append(s, "\\\""); break;
        case '\\': g_string_append(s, "\\\\"); break;
        case '\n': g_string_append(s, "\\n"); break;
        case '\r': g_string_append(s, "\\r"); break;
        case '\t': g_string_append(s, "\\t"); break;
        case '\b': g_string_append(s, "\\b"); break;
        case '\f': g_string_append(s, "\\f"); break;
        default:
            if (c < 0x20 || c > 0x7e) {
                if (c > 0xffff) {
                    c -= 0x10000;
                    g_string_append_printf(s, "\\u%04x\\u%04x", 0xd800 + (c >> 10), 0xdc00 + (c & 0x3ff));
                } else
                    g_string_append_printf(s, "\\u%04x", c);
            } else
                g_string_append_c(s, (char)c);
        }
    }
    g_string_append_c(s, '"');
}

/* Un tip MIME cu forma buna: [a-z0-9][a-z0-9.+-]* / [a-z0-9][a-z0-9.+-]*, cel mult 40 si 80 de semne. */
static gboolean dvb_tip_bun(const char *t, size_t n)
{
    const char *bara = memchr(t, '/', n);
    if (!bara)
        return FALSE;
    size_t a = (size_t)(bara - t), b = n - a - 1;
    if (a < 1 || a > 41 || b < 1 || b > 81)
        return FALSE;
    for (size_t i = 0; i < n; i++) {
        char ch = t[i];
        if (i == a)
            continue;
        gboolean prim = i == 0 || i == a + 1;
        if (!(g_ascii_isdigit(ch) || (ch >= 'a' && ch <= 'z') || (!prim && (ch == '.' || ch == '+' || ch == '-'))))
            return FALSE;
    }
    return TRUE;
}

/* content_type_descriptor-ul fisierului din manifest ("fisiere": [{"cale": ..., "marime": ..., "tip": ...}]), sau
 * NULL. */
static char *dvb_tip_din_manifest(const char *m, const char *cale)
{
    if (!m)
        return NULL;
    const char *f = strstr(m, "\"fisiere\": [");
    const char *sf = f ? strchr(f, ']') : NULL;
    if (!f || !sf)
        return NULL;
    GString *cheie = g_string_new("\"cale\": ");
    dvb_json_ascii(cheie, cale);
    g_string_append_c(cheie, ',');
    char *rez = NULL;
    const char *k = g_strstr_len(f, sf - f, cheie->str);
    const char *capat = k ? strchr(k, '}') : NULL;
    const char *tip = capat ? g_strstr_len(k, capat - k, "\"tip\": \"") : NULL;
    if (tip) {
        tip += 8;
        const char *gata = memchr(tip, '"', (size_t)(capat - tip));
        if (gata && dvb_tip_bun(tip, (size_t)(gata - tip)))
            rez = g_strndup(tip, (size_t)(gata - tip));
    }
    g_string_free(cheie, TRUE);
    return rez;
}

/* Tipul fisierului: din manifest, altfel dupa extensie; o pagina .html sau .htm fara tip in manifest e XHTML numai cand
 * primii ei octeti o declara asa (antetul <?xml sau spatiul de nume XHTML). */
static char *dvb_tip(const char *manifest, const CerereDvb *c, const guint8 *date, gsize n)
{
    char *din_manifest = dvb_tip_din_manifest(manifest, c->cale);
    if (din_manifest)
        return din_manifest;
    const char *nume = c->bucati[0] ? c->bucati[g_strv_length(c->bucati) - 1] : "";
    const char *punct = strrchr(nume, '.');
    const char *tip = DVB_TIP_NECUNOSCUT;
    for (int i = 0; punct && DVB_TIPURI[i][0]; i++) {
        if (!g_ascii_strcasecmp(punct, DVB_TIPURI[i][0])) {
            tip = DVB_TIPURI[i][1];
            break;
        }
    }
    if (!strcmp(tip, "text/html")) {
        gsize m = MIN(n, (gsize)4096), i = 0;
        if (m >= 3 && date[0] == 0xef && date[1] == 0xbb && date[2] == 0xbf)
            i = 3;
        while (i < m && (date[i] == ' ' || date[i] == '\t' || date[i] == '\r' || date[i] == '\n'))
            i++;
        if ((m - i >= 5 && !memcmp(date + i, "<?xml", 5))
            || g_strstr_len((const char *)date, (gssize)m, "http://www.w3.org/1999/xhtml"))
            tip = DVB_TIP_XHTML;
    }
    return g_strdup(tip);
}

static void dvb_raspunde(WebKitURISchemeRequest *r, guint cod, const char *tip, GBytes *corp)
{
    GInputStream *in = g_memory_input_stream_new_from_bytes(corp);
    WebKitURISchemeResponse *rs = webkit_uri_scheme_response_new(in, (gint64)g_bytes_get_size(corp));
    webkit_uri_scheme_response_set_status(rs, cod, cod == 200 ? "OK" : cod == 405 ? "Method Not Allowed" : "Not Found");
    webkit_uri_scheme_response_set_content_type(rs, tip);
    /* antetele inlocuiesc tot (WebKit le adauga peste raspuns): tipul se pune si in ele, altfel paginile nu il vad
     * (fetch, scripturile cu nosniff) */
    SoupMessageHeaders *h = soup_message_headers_new(SOUP_MESSAGE_HEADERS_RESPONSE);
    soup_message_headers_append(h, "Content-Type", tip);
    soup_message_headers_append(h, "Access-Control-Allow-Origin", "*");
    soup_message_headers_append(h, "Cache-Control", "no-store");
    soup_message_headers_append(h, "X-Content-Type-Options", "nosniff");
    if (cod == 405)
        soup_message_headers_append(h, "Allow", "GET");
    webkit_uri_scheme_response_set_http_headers(rs, h);
    webkit_uri_scheme_request_finish_with_response(r, rs);
    g_object_unref(rs);
    g_object_unref(in);
}

static void dvb_scurt(WebKitURISchemeRequest *r, guint cod)
{
    GBytes *gol = g_bytes_new_static("", 0);
    dvb_raspunde(r, cod, "text/plain; charset=utf-8", gol);
    g_bytes_unref(gol);
}

static gint dvb_compara(gconstpointer a, gconstpointer b)
{
    return strcmp(*(char *const *)a, *(char *const *)b);
}

/* Numele dintr-un dosar, in ordine, despartite prin virgula. */
static GBytes *dvb_lista(int fd)
{
    int d2 = dup(fd);
    DIR *d = d2 >= 0 ? fdopendir(d2) : NULL;
    if (!d) {
        if (d2 >= 0)
            close(d2);
        return NULL;
    }
    GPtrArray *nume = g_ptr_array_new_with_free_func(g_free);
    struct dirent *e;
    while ((e = readdir(d))) {
        if (strcmp(e->d_name, ".") && strcmp(e->d_name, ".."))
            g_ptr_array_add(nume, g_strdup(e->d_name));
    }
    closedir(d);
    g_ptr_array_sort(nume, dvb_compara);
    GString *s = g_string_new(NULL);
    for (guint i = 0; i < nume->len; i++) {
        if (i)
            g_string_append_c(s, ',');
        g_string_append(s, g_ptr_array_index(nume, i));
    }
    g_ptr_array_free(nume, TRUE);
    gsize n = s->len;
    return g_bytes_new_take(g_string_free(s, FALSE), n);
}

/* Fisierul deschis, intreg, daca e obisnuit si nu trece de DVB_FISIER_MAXIM. */
static GBytes *dvb_citeste(int fd, const struct stat *st)
{
    if (!S_ISREG(st->st_mode) || st->st_size > DVB_FISIER_MAXIM)
        return NULL;
    gsize marime = (gsize)st->st_size, citit = 0;
    guint8 *date = g_malloc(marime ? marime : 1);
    while (citit < marime) {
        ssize_t r = read(fd, date + citit, marime - citit);
        if (r < 0 && errno == EINTR)
            continue;
        if (r <= 0)
            break;
        citit += (gsize)r;
    }
    return g_bytes_new_take(date, citit);
}

/* O incercare: TRUE = cererea s-a terminat (raspuns dat), FALSE = un fisier inca nu a venit si caruselul nu e complet
 * (se incearca din nou dupa DVB_PAS_MS, pana la termen). */
static gboolean dvb_incearca(CerereDvb *c)
{
    int radacina = open(dvb_radacina(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    char *nume = radacina >= 0 ? dvb_nume_carusel(radacina, c) : NULL;
    int fd = nume ? openat(radacina, nume, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC) : -1;
    /* dosarul lipsa langa manifestul lui: arborele se inlocuieste chiar acum (dosar.nou -> dosar), deci se asteapta */
    gboolean lipsa_dosar = nume && fd < 0 && errno == ENOENT;
    gboolean lipsa = lipsa_dosar, gata = TRUE;
    for (int i = 0; fd >= 0 && c->bucati[i]; i++) {
        int urm = openat(fd, c->bucati[i], O_RDONLY | O_NOFOLLOW | O_CLOEXEC | O_NONBLOCK | O_NOCTTY);
        struct stat st;
        if (urm >= 0 && c->bucati[i + 1] && (fstat(urm, &st) || !S_ISDIR(st.st_mode))) {
            close(urm);
            urm = -1;
            errno = ENOTDIR;
        }
        if (urm < 0)
            lipsa = errno == ENOENT;
        close(fd);
        fd = urm;
    }
    if (fd < 0) {
        const char *m = lipsa && nume ? dvb_manifest_citeste(radacina, nume) : NULL;
        if (m && (lipsa_dosar || !strstr(m, "\"complet\": true")) && g_get_monotonic_time() < c->termen)
            gata = FALSE;
        else
            dvb_scurt(c->cerere, 404);
    } else {
        struct stat st;
        GBytes *corp = NULL;
        char *tip = NULL;
        if (!fstat(fd, &st) && S_ISDIR(st.st_mode)) {
            corp = dvb_lista(fd);
            tip = g_strdup("text/plain; charset=utf-8");
        } else if (!fstat(fd, &st) && (corp = dvb_citeste(fd, &st))) {
            gsize n = 0;
            const guint8 *date = g_bytes_get_data(corp, &n);
            tip = dvb_tip(dvb_manifest_citeste(radacina, nume), c, date, n);
        }
        if (corp)
            dvb_raspunde(c->cerere, 200, tip, corp);
        else
            dvb_scurt(c->cerere, 404);
        if (corp)
            g_bytes_unref(corp);
        g_free(tip);
        close(fd);
    }
    if (radacina >= 0)
        close(radacina);
    g_free(nume);
    return gata;
}

static void dvb_elibereaza(CerereDvb *c)
{
    g_object_unref(c->cerere);
    g_strfreev(c->bucati);
    g_free(c->cale);
    g_free(c);
}

static gboolean dvb_din_nou(gpointer d)
{
    CerereDvb *c = d;
    if (!dvb_incearca(c))
        return G_SOURCE_CONTINUE;
    dvb_elibereaza(c);
    return G_SOURCE_REMOVE;
}

static void dvb_cerere(WebKitURISchemeRequest *r, gpointer d)
{
    (void)d;
    const char *metoda = webkit_uri_scheme_request_get_http_method(r);
    if (metoda && strcmp(metoda, "GET")) {
        dvb_scurt(r, 405);
        return;
    }
    CerereDvb *c = g_new0(CerereDvb, 1);
    char *cale = NULL;
    if (!dvb_desparte(webkit_uri_scheme_request_get_uri(r), c->n, &c->cu_tsid, &cale)
        || !(c->bucati = dvb_bucati(cale))) {
        g_free(cale);
        g_free(c);
        dvb_scurt(r, 404);
        return;
    }
    g_free(cale);
    c->cerere = g_object_ref(r);
    c->cale = g_strjoinv("/", c->bucati);
    c->termen = g_get_monotonic_time() + (gint64)DVB_ASTEPTARE_MS * 1000;
    if (dvb_incearca(c))
        dvb_elibereaza(c);
    else
        g_timeout_add(DVB_PAS_MS, dvb_din_nou, c);
}

static void dvb_inregistreaza(WebKitWebContext *context)
{
    webkit_web_context_register_uri_scheme(context, "dvb", dvb_cerere, NULL, NULL);
    webkit_security_manager_register_uri_scheme_as_cors_enabled(webkit_web_context_get_security_manager(context), "dvb");
    dvb_pornit = TRUE;
}

/* Textul trimis din interfata web intra in campul activ, la cursor; nu se scrie in niciun jurnal. */
static void insereaza_text(const char *text)
{
    GString *s = g_string_new("(function(t){" JS_DOC_ACTIV "d.execCommand('insertText',false,t);})(");
    js_sir(s, text);
    g_string_append(s, ");");
    ruleaza_js(s->str, NULL, NULL);
    memset(s->str, 0, s->len);
    g_string_free(s, TRUE);
}

static void raspunde_favorit(void)
{
    char *a = b64(webkit_web_view_get_uri(vedere));
    char *t = b64(webkit_web_view_get_title(vedere));
    stare_f("FAVORIT %s %s", a, t);
    g_free(a);
    g_free(t);
}

/* Enter trimis direct paginii (formularul completat cu tastatura enigma2), fara cererea tastaturii. */
static void apasa_enter(void)
{
    trimite_tasta(WPE_KEY_Return, KEY_ENTER, TRUE);
    trimite_tasta(WPE_KEY_Return, KEY_ENTER, FALSE);
}

/* Comenzi pe intrarea standard, cate una pe rand (le trimite enigma2 prin eConsoleAppContainer.write). */
static void comanda(char *rand)
{
    g_strchomp(rand);
    char *arg = strchr(rand, ' ');
    if (arg)
        *arg++ = '\0';

    if (!strcmp(rand, "url") && arg)
        webkit_web_view_load_uri(vedere, arg);
    else if (!strcmp(rand, "inapoi"))
        webkit_web_view_go_back(vedere);
    else if (!strcmp(rand, "inainte"))
        webkit_web_view_go_forward(vedere);
    else if (!strcmp(rand, "reincarca"))
        webkit_web_view_reload(vedere);
    else if (!strcmp(rand, "marire") && arg)
        marire_aplica((int)(g_ascii_strtod(arg, NULL) * 100 + 0.5), TRUE);
    else if (!strcmp(rand, "marire-pas") && arg)
        marire_pas(atoi(arg));
    else if (!strcmp(rand, "text") && arg)
        insereaza_text(arg);
    else if (!strcmp(rand, "text64") && arg) {
        char *t = din_b64(arg);
        insereaza_text(t);
        elibereaza_secret(t);
    } else if (!strcmp(rand, "valoare64")) {
        char *t = din_b64(arg);
        inlocuieste_valoarea(t);
        elibereaza_secret(t);
    } else if (!strcmp(rand, "enter"))
        apasa_enter();
    else if (!strcmp(rand, "arata"))
        arata(TRUE);
    else if (!strcmp(rand, "ascunde"))
        arata(FALSE);
    else if (!strcmp(rand, "autentificare") && arg)
        raspuns_autentificare(arg);
    else if (!strcmp(rand, "autentificare-anulata"))
        raspuns_autentificare(NULL);
    else if (!strcmp(rand, "dialog") && arg)
        raspuns_dialog(arg);
    else if (!strcmp(rand, "alegere"))
        raspuns_alegere(arg);
    else if (!strcmp(rand, "favorit?"))
        raspunde_favorit();
    else if (!strcmp(rand, "adresa?")) {
        char *b = b64(webkit_web_view_get_uri(vedere));
        stare_f("CERERE adresa %s", b);
        g_free(b);
    } else if (!strcmp(rand, "tasta") && arg) {
        char *urm = NULL;
        guint64 cod = g_ascii_strtoull(arg, &urm, 10);
        int val = urm && *urm ? atoi(urm) : 1;
        tasta_telecomanda((guint)cod, val);
    } else if (!strcmp(rand, "captura") && arg)
        stare(ecran_scrie_ppm(arg) ? "CAPTURA scrisa" : "EROARE captura");
    else if (!strcmp(rand, "indicator"))
        indicator_comuta(arg ? atoi(arg) != 0 : !ind.activ);
    else if (!strcmp(rand, "scrie"))
        cere_scrisul();
    else if (!strcmp(rand, "chenar"))
        chenar_comanda(arg);
    else if (!strcmp(rand, "indicator-la") && arg && ind.activ) {
        char *urm = NULL;
        double x = g_ascii_strtod(arg, &urm);
        double y = urm ? g_ascii_strtod(urm, NULL) : ind.y;
        indicator_muta(CLAMP(x, 0.0, opt.latime * opt.scara - 1) - ind.x, CLAMP(y, 0.0, opt.inaltime * opt.scara - 1) - ind.y);
    }
    else if (!strcmp(rand, "hbbtv-parte") && arg && sursa_hbbtv)
        hbbtv_parte(arg);
    else if (!strcmp(rand, "hbbtv-ev") && arg && sursa_hbbtv)
        hbbtv_ev(arg);
    else if (!strcmp(rand, "vizibil") && arg && opt.hbbtv) {
        /* etapa H6: aplicatia pornita automat, inca nevazuta, nu deseneaza (pagina "hidden", fara cadre, ceasurile
         * JavaScript rarite); la ROSU enigma2 trimite "vizibil 1", apoi "arata" */
        gboolean da = atoi(arg) != 0;
        WPEView *wv = webkit_web_view_get_wpe_view(vedere);
        if (wv)
            wpe_view_set_visible(wv, da);
        stare_f("VIZIBIL %d", da ? 1 : 0);
    } else if (!strcmp(rand, "iesire"))
        termina(0);
    else
        stare("EROARE comanda");
}

static gboolean intrare_stdin(GIOChannel *ch, GIOCondition c, gpointer d)
{
    (void)d;
    if (c & (G_IO_HUP | G_IO_ERR)) {
        termina(0);
        return G_SOURCE_REMOVE;
    }
    char *rand = NULL;
    GIOStatus st = g_io_channel_read_line(ch, &rand, NULL, NULL, NULL);
    if (st == G_IO_STATUS_EOF) {
        termina(0);
        return G_SOURCE_REMOVE;
    }
    if (rand) {
        gsize n = strlen(rand);
        comanda(rand);
        memset(rand, 0, n);  /* comenzile pot purta parole sau texte scrise de om */
        g_free(rand);
    }
    return G_SOURCE_CONTINUE;
}

/* --utilizator: grupurile, apoi grupul, apoi utilizatorul; orice esec opreste lansatorul (nu merge mai departe ca root).
 * HOME devine dosarul utilizatorului (cache-ul fonturilor si alte fisiere ale bibliotecilor). */
static gboolean coboara_drepturile(const char *nume)
{
    if (geteuid() != 0) {
        stare("UTILIZATOR deja-fara-root");
        return TRUE;
    }
    struct passwd *p = getpwnam(nume);
    if (!p || p->pw_uid == 0) {
        stare("EROARE utilizator-necunoscut");
        return FALSE;
    }
    uid_t uid = p->pw_uid;
    gid_t gid = p->pw_gid;
    char *acasa = g_strdup(p->pw_dir && *p->pw_dir ? p->pw_dir : "/tmp");
    if (initgroups(nume, gid) != 0 || setgid(gid) != 0 || setuid(uid) != 0) {
        stare_f("EROARE utilizator-drepturi %d", errno);
        g_free(acasa);
        return FALSE;
    }
    if (setuid(0) == 0 || geteuid() == 0 || getegid() == 0) {
        stare("EROARE utilizator-root-ramas");
        g_free(acasa);
        return FALSE;
    }
    g_setenv("HOME", acasa, TRUE);
    g_setenv("USER", nume, TRUE);
    g_setenv("LOGNAME", nume, TRUE);
    g_free(acasa);
    stare_f("UTILIZATOR %u", (unsigned)uid);
    return TRUE;
}

static gboolean semn_de_viata(gpointer d)
{
    (void)d;
    stare("VIU");
    return G_SOURCE_CONTINUE;
}

static gboolean semnal_oprire(gpointer d)
{
    (void)d;
    termina(0);
    return G_SOURCE_REMOVE;
}

static gboolean iesire_programata(gpointer d)
{
    (void)d;
    stare("IESIRE timp");
    termina(0);
    return G_SOURCE_REMOVE;
}

int main(int argc, char **argv)
{
    GError *eroare = NULL;
    argv_pornire = g_strdupv(argv);
    GOptionContext *ctx = g_option_context_new("URL");
    g_option_context_add_main_entries(ctx, intrari_optiuni, NULL);
    if (!g_option_context_parse(ctx, &argc, &argv, &eroare)) {
        g_printerr("%s\n", eroare->message);
        return 2;
    }
    g_option_context_free(ctx);
    url_pornire = argc > 1 ? argv[1] : NULL;
    opt.url = argc > 1 ? argv[1] : "about:blank";
    if (opt.latime < 320 || opt.inaltime < 240 || opt.scara < 0.5 || opt.scara > 4.0) {
        g_printerr("marimi nepermise\n");
        return 2;
    }
    chenar_din_optiuni();
    if (opt.hbbtv)
        depremul_pregateste();
    /* Primul oprit cand se termina memoria: valoarea o mostenesc si procesele WebKit pornite de aici. */
    if (opt.oom >= -1000 && opt.oom <= 1000) {
        FILE *f = fopen("/proc/self/oom_score_adj", "w");
        if (f) {
            fprintf(f, "%d\n", opt.oom);
            fclose(f);
        }
    }
    ecran.ascuns = opt.ascuns;

    /* Dispozitivele (framebufferul, telecomanda) se deschid inainte de coborarea drepturilor: cer root. */
    if (opt.fb && !ecran_deschide_fb(opt.fb))
        return 1;
    for (char **p = opt.intrari; p && *p; p++) {
        int fd = open(*p, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
        if (fd < 0) {
            g_printerr("HDS-NAV EROARE intrare %d\n", errno);
            continue;
        }
        if (n_intrari < INTRARI_MAXIM)
            intrari_fd[n_intrari++] = fd;
        else
            close(fd);
    }
    if (opt.utilizator && *opt.utilizator && !coboara_drepturile(opt.utilizator))
        return 1;

    /* In modul HbbTV marirea nu se tine minte (aplicatiile sunt facute pe 1280x720). */
    if (opt.date && !opt.efemer && !opt.hbbtv)
        fisier_mariri = g_build_filename(opt.date, "mariri.txt", NULL);
    mariri_incarca();

    /* Rezerva la pornire: fara ecran EGL folosibil, totul pe procesor (si --pictura-cpu, care compune cu GL). */
    if (!opt.cpu) {
        const char *motiv = egl_proba();
        if (motiv) {
            char *rand = g_strdup_printf("REZERVA procesor %s", motiv);
            stare(rand);
            g_free(rand);
            opt.cpu = TRUE;
            opt.pictura_cpu = FALSE;
        }
    }
    stare(opt.cpu ? "DESEN procesor" : opt.pictura_cpu ? "DESEN pictura-procesor compunere-gl" : "DESEN gl");
    /* Procesul web mosteneste mediul. --pictura-cpu: Skia deseneaza cu procesorul, GLES ramane pentru compunere.
     * --cpu: fara GL deloc in procesul web (WPE_DISABLE_HARDWARE_ACCELERATION, patch-ul 0004 din reteta wpewebkit;
     * fara patch se comporta ca --pictura-cpu). */
    if (opt.pictura_cpu || opt.cpu)
        g_setenv("WEBKIT_SKIA_ENABLE_CPU_RENDERING", "1", TRUE);
    if (opt.cpu)
        g_setenv("WPE_DISABLE_HARDWARE_ACCELERATION", "1", TRUE);

    WPEDisplay *afisaj = WPE_DISPLAY(g_object_new(HDS_TYPE_DISPLAY, NULL));
    if (!wpe_display_connect(afisaj, &eroare)) {
        g_printerr("HDS-NAV EROARE afisaj %s\n", eroare->message);
        return 1;
    }
    la_cadru_afisat = cadru_afisat;

    if (opt.memorie_mb > 0) {
        WebKitMemoryPressureSettings *mps = webkit_memory_pressure_settings_new();
        webkit_memory_pressure_settings_set_memory_limit(mps, opt.memorie_mb);
        webkit_network_session_set_memory_pressure_settings(mps);
        webkit_memory_pressure_settings_free(mps);
    }
    WebKitWebContext *context;
    if (opt.memorie_mb > 0) {
        WebKitMemoryPressureSettings *mps = webkit_memory_pressure_settings_new();
        webkit_memory_pressure_settings_set_memory_limit(mps, opt.memorie_mb);
        context = WEBKIT_WEB_CONTEXT(g_object_new(WEBKIT_TYPE_WEB_CONTEXT, "memory-pressure-settings", mps, NULL));
        webkit_memory_pressure_settings_free(mps);
    } else
        context = webkit_web_context_new();
    if (opt.limba && *opt.limba) {
        const char *limbi[] = { opt.limba, "en", NULL };
        webkit_web_context_set_preferred_languages(context, limbi);
    }
    if (opt.hbbtv) {
        /* cache-ul aplicatiilor HbbTV sta in /tmp (memorie): modelul mic (20 MB pe disc, 16 MB in memorie) */
        webkit_web_context_set_cache_model(context, WEBKIT_CACHE_MODEL_DOCUMENT_BROWSER);
        dvb_inregistreaza(context);
    }

    if (opt.efemer || !opt.date)
        sesiune = webkit_network_session_new_ephemeral();
    else {
        char *cache = opt.cache ? g_strdup(opt.cache) : g_build_filename(opt.date, "cache", NULL);
        sesiune = webkit_network_session_new(opt.date, cache);
        g_free(cache);
    }

    WebKitSettings *setari = webkit_settings_new();
    /* In modul HbbTV aplicatia isi muta singura focalizarea cu sagetile (navigarea spatiala ar muta-o si ea). */
    webkit_settings_set_enable_spatial_navigation(setari, !opt.hbbtv);
    if (opt.agent_adaugat && *opt.agent_adaugat) {
        /* agentul WebKit ramane intreg (siturile il cer), partea HbbTV vine la sfarsit; fara semne de control */
        char *adaugat = g_strdup(opt.agent_adaugat);
        for (char *c = adaugat; *c; c++) {
            if ((guchar)*c < 0x20 || (guchar)*c == 0x7F)
                *c = ' ';
        }
        char *agent = g_strdup_printf("%s %s", webkit_settings_get_user_agent(setari), adaugat);
        webkit_settings_set_user_agent(setari, agent);
        g_free(agent);
        g_free(adaugat);
    }
    if (opt.font_minim > 0)
        webkit_settings_set_minimum_font_size(setari, (guint32)opt.font_minim);
    /* derularea fara animatie: pe procesorul receptorului fiecare pas al animatiei e un cadru desenat, iar chenarul
     * ar ajunge la element abia dupa ea */
    if (!opt.hbbtv)
        webkit_settings_set_enable_smooth_scrolling(setari, FALSE);

    WebKitUserContentManager *continut = webkit_user_content_manager_new();
    g_signal_connect(continut, "script-message-received::hdsnav", G_CALLBACK(camp_schimbat), NULL);
    webkit_user_content_manager_register_script_message_handler(continut, "hdsnav", NULL);
    WebKitUserScript *script = webkit_user_script_new(SCRIPT_CAMPURI, WEBKIT_USER_CONTENT_INJECT_ALL_FRAMES,
        WEBKIT_USER_SCRIPT_INJECT_AT_DOCUMENT_START, NULL, NULL);
    webkit_user_content_manager_add_script(continut, script);
    webkit_user_script_unref(script);
    if (opt.hbbtv) {
        WebKitUserScript *vk = webkit_user_script_new(SCRIPT_HBBTV_TASTE, WEBKIT_USER_CONTENT_INJECT_ALL_FRAMES,
            WEBKIT_USER_SCRIPT_INJECT_AT_DOCUMENT_START, NULL, NULL);
        webkit_user_content_manager_add_script(continut, vk);
        webkit_user_script_unref(vk);
        hbbtv_strat_incarca(continut);
        erori_js_incarca(continut);
    } else {
        /* stratul lansatorului: dreptunghiul elementului cu focalizare */
        g_signal_connect(continut, "script-message-received::hdsnavchenar", G_CALLBACK(chenar_schimbat), NULL);
        webkit_user_content_manager_register_script_message_handler(continut, "hdsnavchenar", NULL);
        WebKitUserScript *ch = webkit_user_script_new(SCRIPT_CHENAR, WEBKIT_USER_CONTENT_INJECT_ALL_FRAMES,
            WEBKIT_USER_SCRIPT_INJECT_AT_DOCUMENT_START, NULL, NULL);
        webkit_user_content_manager_add_script(continut, ch);
        webkit_user_script_unref(ch);
        /* meniurile deschise numai sub mouse se deschid si la focalizare */
        WebKitUserScript *mn = webkit_user_script_new(SCRIPT_MENIURI, WEBKIT_USER_CONTENT_INJECT_ALL_FRAMES,
            WEBKIT_USER_SCRIPT_INJECT_AT_DOCUMENT_START, NULL, NULL);
        webkit_user_content_manager_add_script(continut, mn);
        webkit_user_script_unref(mn);
        /* scroll-behavior: smooth din CSS-ul sitului ar anima derularea la element (foaia utilizatorului castiga) */
        WebKitUserStyleSheet *fara_animatie = webkit_user_style_sheet_new("*{scroll-behavior:auto!important}",
            WEBKIT_USER_CONTENT_INJECT_ALL_FRAMES, WEBKIT_USER_STYLE_LEVEL_USER, NULL, NULL);
        webkit_user_content_manager_add_style_sheet(continut, fara_animatie);
        webkit_user_style_sheet_unref(fara_animatie);
    }

    vedere = WEBKIT_WEB_VIEW(g_object_new(WEBKIT_TYPE_WEB_VIEW,
        "web-context", context,
        "network-session", sesiune,
        "settings", setari,
        "user-content-manager", continut,
        "display", afisaj,
        NULL));
    g_object_unref(setari);
    if (!continut_pagina)
        g_object_unref(continut);   /* in modul HbbTV ramane tinut: scriptul se schimba cat ruleaza */
    if (opt.hbbtv) {
        /* zonele paginii fara continut raman transparente: canalul de sub OSD se vede */
        WebKitColor transparent = { 0.0, 0.0, 0.0, 0.0 };
        webkit_web_view_set_background_color(vedere, &transparent);
    }

    WPEView *v = webkit_web_view_get_wpe_view(vedere);
    WPEToplevel *t = v ? wpe_view_get_toplevel(v) : NULL;
    if (!t) {
        g_printerr("HDS-NAV EROARE fereastra\n");
        return 1;
    }
    /* --marire-la-copiere: numai in modul HbbTV si numai pentru 1280 -> 1920 (scara 1,5); altfel scara obisnuita */
    if (opt.marire_copiere && opt.hbbtv && opt.scara > 1.499 && opt.scara < 1.501 && !(opt.latime & 1) && !(opt.inaltime & 1)) {
        ecran_x15 = TRUE;
        stare("MARIRE-LA-COPIERE 1.5");
    } else if (opt.marire_copiere)
        stare("AVERTISMENT marire-la-copiere-nefolosita");
    if (opt.scara != 1.0 && !ecran_x15)
        wpe_toplevel_scale_changed(t, opt.scara);
    wpe_toplevel_resize(t, opt.latime, opt.inaltime);
    wpe_view_focus_in(v);
    if (opt.marire != 1.0)
        webkit_web_view_set_zoom_level(vedere, opt.marire);

    g_signal_connect(vedere, "load-changed", G_CALLBACK(incarcare_schimbata), NULL);
    g_signal_connect(vedere, "load-failed", G_CALLBACK(incarcare_esuata), NULL);
    g_signal_connect(vedere, "load-failed-with-tls-errors", G_CALLBACK(eroare_tls), NULL);
    g_signal_connect(vedere, "web-process-terminated", G_CALLBACK(proces_web_oprit), NULL);
    g_signal_connect(vedere, "notify::estimated-load-progress", G_CALLBACK(progres_schimbat), NULL);
    g_signal_connect(vedere, "authenticate", G_CALLBACK(autentificare), NULL);
    g_signal_connect(vedere, "script-dialog", G_CALLBACK(dialog_script), NULL);
    g_signal_connect(vedere, "show-option-menu", G_CALLBACK(arata_optiuni), NULL);
    g_signal_connect(vedere, "decide-policy", G_CALLBACK(decide), NULL);

    for (int i = 0; i < n_intrari; i++)
        g_unix_fd_add(intrari_fd[i], G_IO_IN | G_IO_HUP | G_IO_ERR, intrare_evdev, NULL);
    if (!ecran.ascuns)
        intrari_apuca(TRUE);

    GIOChannel *in = g_io_channel_unix_new(STDIN_FILENO);
    g_io_add_watch(in, G_IO_IN | G_IO_HUP | G_IO_ERR, intrare_stdin, NULL);
    g_timeout_add_seconds(2, semn_de_viata, NULL);
    g_unix_signal_add(SIGTERM, semnal_oprire, NULL);
    g_unix_signal_add(SIGINT, semnal_oprire, NULL);
    if (opt.iesire_dupa_s > 0)
        g_timeout_add_seconds(opt.iesire_dupa_s, iesire_programata, NULL);

    stare("PORNIT");
    webkit_web_view_load_uri(vedere, opt.url);

    bucla = g_main_loop_new(NULL, FALSE);
    g_main_loop_run(bucla);

    g_object_unref(vedere);
    if (continut_pagina) {
        if (script_hbbtv)
            webkit_user_script_unref(script_hbbtv);
        g_object_unref(continut_pagina);
        g_hash_table_destroy(parti_hbbtv);
        g_free(sursa_hbbtv);
    }
    g_object_unref(sesiune);
    g_object_unref(context);
    g_object_unref(afisaj);
    g_io_channel_unref(in);
    if (opt.hbbtv && !reporneste_pe_cpu)
        ecran_goleste();
    if (ecran.este_fb)
        munmap(ecran.mem, ecran.marime);
    else
        g_free(ecran.mem);
    g_free(copie_pagina.mem);
    if (ecran.fd >= 0)
        close(ecran.fd);
    if (reporneste_pe_cpu)
        reporneste_cu_cpu();
    stare("OPRIT");
    g_strfreev(argv_pornire);
    g_free(adresa_reluare);
    return cod_iesire;
}
