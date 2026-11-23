SUMMARY = "HDSatelit: lansatorul navigatorului web pe receptor (WPE WebKit pe framebuffer)"
DESCRIPTION = "Program mic care porneste WPE WebKit cu o platforma WPE proprie pentru fbdev: cadrele paginii \
vin in memorie partajata si se copiaza pe /dev/fb0, telecomanda se citeste din evdev, comenzile vin pe \
intrarea standard (o comanda pe rand), starea iese pe iesirea standard (randuri HDS-NAV). Proces separat \
de enigma2, pornit la cerere; intra in imagine prin hdsatelit-base. Monea Software pentru HD Satelit."
LICENSE = "GPL-2.0-only & MIT"
LIC_FILES_CHKSUM = "file://hds-navigator.c;beginline=2;endline=3;md5=fb87bc14f85a0e8e73d2e038b3c2f7e1 \
                    file://hds-hbbtv.js;beginline=2858;endline=2876;md5=a27e35cdfe59b078f9273144a89e57db"
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
PR = "r19"

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
