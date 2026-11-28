SUMMARY = "HDSatelit: lansatorul navigatorului web pe receptor (WPE WebKit pe framebuffer)"
DESCRIPTION = "Program mic care porneste WPE WebKit cu o platforma WPE proprie pentru fbdev: cadrele paginii \
vin in memorie partajata si se copiaza pe /dev/fb0, telecomanda se citeste din evdev, comenzile vin pe \
intrarea standard (o comanda pe rand), starea iese pe iesirea standard (randuri HDS-NAV). Proces separat \
de enigma2, pornit la cerere; intra in imagine prin hdsatelit-base. Monea Software pentru HD Satelit."
LICENSE = "GPL-2.0-only & MIT"
LIC_FILES_CHKSUM = "file://hds-navigator.c;beginline=2;endline=3;md5=fb87bc14f85a0e8e73d2e038b3c2f7e1 \
                    file://hds-hbbtv.js;beginline=4391;endline=4409;md5=a27e35cdfe59b078f9273144a89e57db"
PV = "0.7.0"
# r1: la repornirea pe procesor (GL cazut) procesele WebKit ale incercarii cu GL se culeg inainte de execv (nu mai raman
# zombi pana la inchiderea aplicatiei)
# r2: comanda paginii "av" (filmele aplicatiilor HbbTV, obiectul A/V) trece spre enigma2, care le reda pe playerul
# receptorului; starea data paginii spune "av":1
# r3 (versiunea 0.6.7): SCRIPT_MENIURI, in afara modului HbbTV: meniurile paginilor care se deschid numai sub mouse
# (reguli CSS :hover, ca "other files" din interfata web a unui modul) se deschid si la focalizarea data de sageti
# (aceleasi reguli copiate cu :focus-within intr-o foaie a lansatorului)
# r4 (0.7.4, NB): EXIT inchide de pe orice pagina, Inapoi/RECALL (KEY_BACK, KEY_LAST) si „<” merg o pagina inapoi si
# ies de pe prima; marginile paginii (--margine-x/-y); pe procesor nice 10 (si, in afara HbbTV, un fir de pictura si
# 25 de cadre pe secunda)
# r5 (0.7.5, HBB): adaptarile pe situri in hds-hbbtv.js; hub-ul TVP cu sectiunea lipsa la post trece pe pagina
# lui principala (#mainpage) in loc sa ramana la "Trwa wczytywanie"
# r6 (0.7.5, CRM): scurtaturile meniului Aplicatii: --agent (User-Agent-ul intreg) si --script (harta tastelor
# aplicatiei, pusa in fiecare document); aceleasi argumente ca hds-chromium
# r7 (0.7.5, H20-AUTOPLAY): in modul HbbTV autoplay permis si cu sunet (website-policies), pentru <video> HTML5
# r8 (0.7.5, WAS): hds-hbbtv.js da aplicatiilor HbbTV WebAssembly scris in JavaScript (polywasm 0.2.0, MIT,
# https://github.com/evanw/polywasm) cand WebKit nu-l are (ARMv7); de aici si MIT in LICENSE
# r9 (0.7.5, HBX): functiile de eveniment puse pe <object> inainte de type ajung la evenimente (aplicatia TVP de pe
# DVB-T afla ca filmul merge si scoate "Trwa wczytywanie"); acelasi numar de randuri, nota MIT neatinsa.
# r10 (0.7.7, YTB): --autoplay: filmele aplicatiilor din meniul Aplicatii (YouTube pentru televizor) pornesc si cu sunet
# r11 (0.7.7, HB4): hds-hbbtv.js: aplicatia TVP a canalelor terestre (hbb-prod.tvp.pl/apps/manager) primeste starea
# filmului motorului Object asa cum o citeste (stateReady) si merge pe playerul receptorului (MediaSource ascuns numai
# acolo); altfel cadea la primul PlayStateChange si ramanea la "Trwa wczytywanie". Tot r11 (HB4 runda 2, neconstruit
# inca): pe virtual-channel o singura reincarcare cand pagina sta la incarcare 20 s fara film (alta greseala TVP).
# Nota MIT neschimbata, mutata cu randurile adaugate inaintea ei.
# r12 (0.7.7, HB4 runda 3): in afara modului HbbTV si CAM pagina se arata (PRIMA-PAGINA) si la primul cadru dupa
# angajare, cu progresul peste 50 % sau dupa 3 s, nu abia la sfarsitul incarcarii (paginile grele pe procesoarele slabe:
# Vu+ Solo SE, Viper 4K V10); randul PRIMUL-CADRU spune cand vine primul cadru.
# r13 (0.7.7, SRV): hds-hbbtv.js: cand desenul e pe procesor (fara compunere: rezerva pe Mali-450) animatiile CSS fara
# sfarsit ale paginilor HbbTV merg cu ~10 cadre pe secunda (oprite si mutate de strat), altfel tineau firul paginii ocupat si
# aplicatia ramanea pe ecranul de incarcare (ServusTV On). Nota MIT neschimbata, mutata cu randurile adaugate (+88).
# r14 (0.7.7, V1S): tasta tinuta pe procesor: o singura sageata sau P+/P- in zbor spre pagina; repetarile telecomenzii
# venite cat pagina n-a terminat tasta de dinainte (mesajul hdsnavtasta) se sar, ca sa nu se adune la coada (Viper 4K V10:
# pagina se tot muta secunde dupa eliberare); la eliberare randul TIMP repetari-sarite N. Nota MIT neatinsa.
# r15 (0.7.7, ERT): hds-hbbtv.js: gaura filmului se pune si cand obiectul A/V are pointer-events:none (al lui sau de la un
# parinte; aplicatia ERT de pe ERT World 39,0E): elementsFromPoint nu-l intorcea, deci scena aplicatiei ramanea opaca peste
# film (sunet, ecran negru); pe durata cautarii o regula a stratului face tinta orice element. Nota MIT neschimbata, mutata
# cu randurile adaugate (+45).
# r16 (0.7.8, CR2): hds-hbbtv.js: pe paginile aplicatiei TVP manager (hub-ul TVP GO al TVP 1 de pe satelit, in afara de
# virtual-channel) cand "Trwa wczytywanie" sta pe ecran 30 s fara film: un rand in jurnalul paginii cu cererile neterminate
# si o singura reincarcare (asistenta 764371, Vu+ Uno 4K SE). Nota MIT neschimbata, mutata cu randurile adaugate (+114).
# r19 (0.7.8, NAVJ4): JSC_useDFGJIT=0 impus si cand vine din mediu; JIT-ul de baza cerut (JSC_useJIT=1) cand WebKit-ul il are.
# r20 (dupa 0.7.8, JIT8): rezerva fara JIT in lansator: dupa doua porniri la rand cu procesul web cazut pe procesor (caderea cu
# GL nu se numara) navigatorul porneste pe interpretor; /etc/enigma2/hds-navigator-jit-cazut tine numarul (0, 1, 2), facut de
# root cu scriere pentru toti (modul HbbTV ruleaza fara root). Vine in feed impreuna cu WebKit-ul cu JIT (r0.video3.jit3).
# Tot r20: JSC_useRegExpJIT=1 langa JSC_useJIT=1 (pe 32 de biti JIT-ul expresiilor regulate e oprit din fabrica), 0 in rezerva.
# Tot r20: cand rezerva a pus pornirea pe interpretor si procesul web cade si acolo, numaratoarea se sterge (pagina cade si fara JIT).
# r21 (0.8.0, HBB9): copia de rezerva hds-hbbtv.js adusa la zi cu cea din enigma2 (era ramasa la r16; intre timp AS191 si
# altele): <video>/<audio> HTML5 cu sursa http(s) HLS/DASH/MP4/TS/MP3 pe playerul receptorului prin comenzile "av" (si
# sursa scrisa in HTML: src, <source>, autoplay), pause()/resume() pe obiectul A/V (ADN Play). Nota MIT neschimbata,
# mutata cu randurile adaugate (randurile 3368-3386).
# r22 (0.8.0, VLY0): comanda "volum <0-100> <0|1> <ms>": bara de volum desenata de lansator in strat, sus in dreapta, cat
# lansatorul tine ecranul (aplicatia YouTube si celelalte); enigma2 nu poate desena atunci (lacatul pe fb0).
# r23 (0.8.0, YTS0): --marire-la-copiere si in afara HbbTV cand desenul e pe procesor (aplicatiile pe Vu+ Solo SE si
# celelalte placi fara EGL folosibil: pagina desenata la 1280x720, nu 1920x1080); stratul isi ia zonele inapoi la scara copiei.
# r24 (0.8.0, LAN1): copia de rezerva hds-hbbtv.js adusa la zi: canPlayType pe <video>/<audio> spune "maybe" la tipurile
# playerului receptorului; hls.js si dash.js care nu pot reda aici (fara MediaSource cu decodor) primesc o punte mica spre
# <video>, deci spre playerul receptorului (Rubidia: Video Mediterraneo, Video Regione; wedo tv pe 13E). Nota MIT neschimbata,
# mutata cu randurile adaugate (randurile 3763-3781).
# r26 (JITD; r25 e pastrat pentru lotul WVN1): treapta rapida a compilatorului JavaScript (DFG) pornita pe ARMv7 (JSC_useDFGJIT=1; cere libwpewebkit ...jit4,
# cu peticul 0033; o biblioteca fara DFG compilat nu ia in seama variabila). Rezerva pe trepte: fisierul numaratorii tine doua
# cifre; doua porniri la rand cazute cu treapta rapida -> numai treapta de baza ("JIT-REZERVA baza"), inca doua -> interpretor.
# r27 (0.8.0, WVN1; r25 a fost numele de proba): Encrypted Media Extensions pornite in setarile paginii (webkit_settings_set_enable_encrypted_media): in WPE
# sunt oprite din fabrica, deci filmele protejate (Netflix si celelalte, prin libocdm) nu ar avea EME nici cu WebKit-ul cu EME.
# Tot r27 (WVN1): cererea de permisiune EME (WebKitMediaKeySystemPermissionRequest) acceptata; WebKit refuza implicit orice
# permisiune, deci requestMediaKeySystemAccess dadea NotSupportedError (vazut pe Octagon 25.11).
# r29 (0.8.0, HBL1): copia de rezerva hds-hbbtv.js adusa la zi cu reparatiile facute de mana la Lanus (Octagon SF8008,
# AS211, AS218): puntea hls.js / dash.js pusa mereu (si cu MediaSource cu decodorul imprumutat; filmele protejate raman la
# biblioteca), fundalul propriu al <video> transparent cat filmul merge pe playerul receptorului, bara ADN PLAY ascunsa cat
# filmul reda, anuntul receptorului in pagina (ev "anunt"), paginile XHTML cu greseli de XML citite iar ca HTML (AS220, CLUB TV).
# Nota MIT neschimbata, mutata cu randurile adaugate (4307-4325).
# r32 (0.8.0, HBW1): copia de rezerva hds-hbbtv.js adusa la zi cu reparatiile facute de mana la Lanus (AS244, wedo tv
# de pe 13E), facute generale: bindToCurrentChannel() urmat de stop() in acelasi pas cat un film al paginii tine playerul
# receptorului nu mai opreste filmul ("leaga" amanat pana la sfarsitul pasului, anulat de stop()); aplicatiile Lightning fara
# WebGL (desen pe procesor) au optiunile readPixels* false (altfel gl.readPixels cu gl null, rotita); plasa rotitei wedo
# numai pe hbbtv.amtecco.com. Nota MIT neschimbata, mutata cu randurile adaugate (4391-4409).
# r33 (0.8.0, WKT1): pe ARM fara NEON (ZGEMMA H8.2H Plus, vfpv3d16) navigatorul porneste direct pe interpretorul
# JavaScript (getauxval AT_HWCAP; bitii lipsa = JIT ca inainte): pe .129 DFG oprea procesul web (abort) la ZDF HbbTV, iar treapta de baza lasa
# aplicatia ZDF goala la 66%; pe interpretor ZDF si ARD merg. Nota de licenta neschimbata (randurile 2-3).
PR = "r33"

SRC_URI = "file://hds-navigator.c file://hds-hbbtv.js"
S = "${UNPACKDIR}"

# freetype: textele de ajutor desenate de lansator peste pagina (libfreetype6 e deja in imagine, a enigma2)
# libsoup: antetele raspunsurilor schemei dvb:// (biblioteca e deja in imagine, a WebKit-ului)
DEPENDS = "wpewebkit glib-2.0 freetype libsoup"

inherit pkgconfig useradd

# Utilizatorul fara root al aplicatiilor HbbTV (etapa H2): lansatorul deschide /dev/fb0 ca root, apoi coboara pe el
# (--utilizator hdsnav, cerut de enigma2 numai in modul HbbTV). Grupul video pentru placa video (/dev/mali), daca
# dispozitivul il cere; altfel desenul trece singur pe procesor (rezerva lansatorului). Dosarul lui, cu datele
# aplicatiilor HbbTV, il face enigma2 la prima pornire (Components/HdsHbbtvPornire.py).
USERADD_PACKAGES = "${PN}"
USERADD_PARAM:${PN} = "--system --home-dir /var/lib/hds-navigator --no-create-home --shell /bin/false --user-group --groups video hdsnav"

do_configure[noexec] = "1"

do_compile() {
    if grep -q "$(printf '\r')" ${S}/hds-navigator.c ${S}/hds-hbbtv.js; then
        bbfatal "hds-navigator: sursa are sfarsit de rand CRLF"
    fi
    ${CC} ${CFLAGS} ${LDFLAGS} -std=gnu11 -Wall -Wextra -Werror=implicit-function-declaration \
        -DHDS_NAV_VERSIUNE='"${PV}"' \
        -o ${B}/hds-navigator ${S}/hds-navigator.c $(pkg-config --cflags --libs wpe-webkit-2.0 wpe-platform-2.0 freetype2 libsoup-3.0)
}

# hds-hbbtv.js (etapa H3): obiectele OIPF/HbbTV puse de lansator in paginile aplicatiilor HbbTV (--hbbtv). enigma2 da
# lansatorului copia din pachetul lui (--hbbtv-js, se poate actualiza prin feed); aceasta e rezerva, folosita numai cand
# aceea lipseste, tinuta la fel cu cea din enigma2 de la constructia imaginii.
do_install() {
    install -d ${D}${bindir} ${D}${datadir}/hds-navigator
    install -m 0755 ${B}/hds-navigator ${D}${bindir}/hds-navigator
    install -m 0644 ${S}/hds-hbbtv.js ${D}${datadir}/hds-navigator/hds-hbbtv.js
}

FILES:${PN} = "${bindir}/hds-navigator ${datadir}/hds-navigator"
# DejaVu Sans si Serif (meta-oe, ttf-dejavu): fonturile cerute de paginile obisnuite (sans-serif, serif) cu litere
# romanesti, grecesti si chirilice; pe receptor sunt numai fonturile enigma2. 4,5 MB instalate (masurat, 0.2.6).
RDEPENDS:${PN} = "wpewebkit ttf-dejavu-sans ttf-dejavu-serif"
