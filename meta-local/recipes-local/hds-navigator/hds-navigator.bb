SUMMARY = "HDSatelit: lansatorul navigatorului web pe receptor (WPE WebKit pe framebuffer)"
DESCRIPTION = "Program mic care porneste WPE WebKit cu o platforma WPE proprie pentru fbdev: cadrele paginii \
vin in memorie partajata si se copiaza pe /dev/fb0, telecomanda se citeste din evdev, comenzile vin pe \
intrarea standard (o comanda pe rand), starea iese pe iesirea standard (randuri HDS-NAV). Proces separat \
de enigma2, pornit la cerere; intra in imagine prin hdsatelit-base. Monea Software pentru HD Satelit."
LICENSE = "GPL-2.0-only & MIT"
LIC_FILES_CHKSUM = "file://hds-navigator.c;beginline=2;endline=3;md5=fb87bc14f85a0e8e73d2e038b3c2f7e1 \
                    file://hds-hbbtv.js;beginline=2515;endline=2533;md5=a27e35cdfe59b078f9273144a89e57db"
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
PR = "r9"

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
