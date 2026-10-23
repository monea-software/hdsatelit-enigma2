SUMMARY = "HDSatelit: drepturile nodurilor de baza din /dev, puse la loc dupa mdev -s"
DESCRIPTION = "Script de pornire (rcS, S42) care asteapta sa se termine `mdev -s` (pornit in fundal de S06hotplug.sh din \
initscripts, dupa udev) si pune la loc drepturile pe care mdev le strica la fiecare pornire: null, zero, full, random, \
urandom 0666 root:root; tty, ptmx 0666 root:tty; fb0, mali 0660 root:video. Fara ele navigatorul HbbTV, care ruleaza \
ca utilizatorul fara root hdsnav, cade (GLib nu poate deschide /dev/null) si nu poate folosi placa video. Nimic altceva \
nu se deschide altor utilizatori. Din 0.1.1 (lotul marunte-028) si regula udev 90-hds-noduri.rules: /dev/mali facut \
dupa S42 (modulul incarcat mai tarziu) primeste tot root:video 0660 (atunci numai udev atinge nodul). Monea Software \
pentru HD Satelit. Dovezile: lucru-sesiune/pilot-26-09/hbbtv/receptor-027/progres.md si marunte-028/progres.md."
LICENSE = "CLOSED"
PV = "0.1.1"

# 90-hds-noduri.rules (0.1.1, lotul marunte-028): /dev/mali facut DUPA S42 (mali.ko incarcat mai tarziu sau din nou) il
# atinge numai udev (mdev nu e hotplug: /proc/sys/kernel/hotplug gol), deci fara regula ar ramane cu drepturile udev
# (root:root). De ce regula si nu o a doua trecere a scriptului in fundal: nodul e misc, facut de nucleu la insmod, deci
# are eveniment udev oricand ar aparea; regula il prinde fara ceas, fara bucla si fara sa tina pornirea, iar trecerea
# in fundal ar prinde numai o fereastra de cateva secunde. Scriptul ramane pentru pornire: mdev -s (S06) vine dupa udev
# si suprascrie si regula.
SRC_URI = "file://hds-noduri file://90-hds-noduri.rules"
S = "${UNPACKDIR}"

inherit allarch update-rc.d

do_configure[noexec] = "1"
do_compile[noexec] = "1"

INITSCRIPT_NAME = "hds-noduri"
# S42 in rcS: dupa S05udev, S05loadmodules (Dinobot: hi_fb.ko face /dev/fb0, mali.ko face /dev/mali), S06hotplug.sh
# (`mdev -s &`, scriptul il asteapta), S39dinobot-pvr si S41hds-netguard; inainte de runlevel 3 (dbus, avahi, enigma2).
INITSCRIPT_PARAMS = "start 42 S ."

# Ca la hdsatelit-netguard (defectul D1): postinst-ul clasei update-rc.d nu porneste scriptul pe un receptor deja pornit
# (runlevel 3 != S), deci la instalarea sau actualizarea pachetului drepturile se pun imediat aici. La facerea imaginii
# $D e setat si nu se face nimic. Oprirea scriptului nu face nimic, deci prerm-ul clasei ramane cum e.
pkg_postinst:${PN}() {
#!/bin/sh
if [ -z "$D" ] && [ -x /etc/init.d/hds-noduri ]; then
	/etc/init.d/hds-noduri start || :
	# regula noua se foloseste de la urmatorul eveniment, fara repornire
	if command -v udevadm >/dev/null 2>&1; then udevadm control --reload-rules || :; fi
fi
}

do_install() {
    install -d ${D}${sysconfdir}/init.d
    install -m 0755 ${S}/hds-noduri ${D}${sysconfdir}/init.d/hds-noduri
    install -d ${D}${sysconfdir}/udev/rules.d
    install -m 0644 ${S}/90-hds-noduri.rules ${D}${sysconfdir}/udev/rules.d/90-hds-noduri.rules
    # paze: scriptul instalat are asteptarea dupa mdev si exact cele trei liste; altfel constructia se opreste
    grep -q 'pidof mdev' ${D}${sysconfdir}/init.d/hds-noduri || \
        bbfatal "hds-noduri: lipseste asteptarea dupa mdev"
    grep -qx 'NODURI_TOTI="null zero full random urandom"' ${D}${sysconfdir}/init.d/hds-noduri || \
        bbfatal "hds-noduri: lista NODURI_TOTI schimbata"
    grep -qx 'NODURI_TTY="tty ptmx"' ${D}${sysconfdir}/init.d/hds-noduri || \
        bbfatal "hds-noduri: lista NODURI_TTY schimbata"
    grep -qx 'NODURI_VIDEO="fb0 mali"' ${D}${sysconfdir}/init.d/hds-noduri || \
        bbfatal "hds-noduri: lista NODURI_VIDEO schimbata"
    if grep -q "$(printf '\r')" ${D}${sysconfdir}/init.d/hds-noduri; then
        bbfatal "hds-noduri: scriptul are sfarsit de rand CRLF, nu ar porni pe receptor"
    fi
    # regula udev: un singur rand de regula, numai pentru mali, fara CRLF
    grep -qx 'KERNEL=="mali", GROUP="video", MODE="0660"' ${D}${sysconfdir}/udev/rules.d/90-hds-noduri.rules || \
        bbfatal "hds-noduri: regula udev pentru /dev/mali schimbata"
    [ "$(grep -v -c '^#' ${D}${sysconfdir}/udev/rules.d/90-hds-noduri.rules)" = "1" ] || \
        bbfatal "hds-noduri: regula udev are alte randuri decat cel pentru /dev/mali"
    if grep -q "$(printf '\r')" ${D}${sysconfdir}/udev/rules.d/90-hds-noduri.rules; then
        bbfatal "hds-noduri: regula udev are sfarsit de rand CRLF"
    fi
}

FILES:${PN} = "${sysconfdir}/init.d/hds-noduri ${sysconfdir}/udev/rules.d/90-hds-noduri.rules"
