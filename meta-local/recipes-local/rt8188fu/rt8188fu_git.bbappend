# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Octagon SF8008 si SF8008 MINI: rt8188fu (driverul Wi-Fi USB pus din fabrica pe toate placile acestor imagini) aduce
# si celelalte drivere Wi-Fi USB ale masinii (cele din oe-alliance-wifi.bb: rt8821cu, rtl8192eu, rt8822cu, mt7601u cu
# firmware-urile lor; in imagine le cere hdsatelit-base.bbappend). De ce aici: receptoarele deja instalate le primesc
# prin Actualizare software, care actualizeaza numai pachetele instalate si verifica numai dependintele lor directe,
# dupa numele pachetelor (Components/HdsActualizari: dependinte_lipsa); hdsatelit-base cere si nume date prin Provides
# (libdvdread, showiframe), pe care verificarea nu le gaseste, deci nu poate purta actualizarea. rt8188fu cere numai
# pachete cu numele lor adevarat (modulul mt7601u cu numele pachetului, nucleul linux-octagon e 4.4.35 pe ambele
# masini). La instalarea pe receptor (nu la facerea imaginii, cand $D e dat) modulele noi se leaga singure de un
# adaptor deja pus in USB: depmod, apoi modprobe pe alias-ul fiecarei interfete USB fara driver; fara repornire.
HDS_WIFI_PURTAT = "rt8821cu rtl8192eu rt8822cu kernel-module-mt7601u-4.4.35 firmware-mt7601u firmware-rtl8192eu linux-firmware-8821cu"
PR:append:sf8008 = ".hds1"
PR:append:sf8008m = ".hds1"
PR:append:ustym4kpro = ".hds1"
RDEPENDS:${PN}:append:sf8008 = " ${HDS_WIFI_PURTAT}"
RDEPENDS:${PN}:append:sf8008m = " ${HDS_WIFI_PURTAT}"
# Uclan Ustym 4K PRO (ustym4kpro): la fel ca pe SF8008 si MINI (nucleul linux-uclan e tot 4.4.35)
RDEPENDS:${PN}:append:ustym4kpro = " ${HDS_WIFI_PURTAT}"
# GigaBlue UHD TRIO 4K (MACHINEBUILD gbtrio4k): la fel (nucleul linux-gigablue e tot 4.4.35)
PR:append:gbtrio4k = ".hds1"
RDEPENDS:${PN}:append:gbtrio4k = " ${HDS_WIFI_PURTAT}"

pkg_postinst:${PN}:sf8008 () {
if [ -z "$D" ]; then
	depmod -a 2>/dev/null || :
	for m in /sys/bus/usb/devices/*/modalias; do
		if [ -e "$m" ] && [ ! -e "${m%/modalias}/driver" ]; then
			modprobe -q "$(cat "$m")" 2>/dev/null || :
		fi
	done
fi
exit 0
}

pkg_postinst:${PN}:sf8008m () {
if [ -z "$D" ]; then
	depmod -a 2>/dev/null || :
	for m in /sys/bus/usb/devices/*/modalias; do
		if [ -e "$m" ] && [ ! -e "${m%/modalias}/driver" ]; then
			modprobe -q "$(cat "$m")" 2>/dev/null || :
		fi
	done
fi
exit 0
}

pkg_postinst:${PN}:ustym4kpro () {
if [ -z "$D" ]; then
	depmod -a 2>/dev/null || :
	for m in /sys/bus/usb/devices/*/modalias; do
		if [ -e "$m" ] && [ ! -e "${m%/modalias}/driver" ]; then
			modprobe -q "$(cat "$m")" 2>/dev/null || :
		fi
	done
fi
exit 0
}

pkg_postinst:${PN}:gbtrio4k () {
if [ -z "$D" ]; then
	depmod -a 2>/dev/null || :
	for m in /sys/bus/usb/devices/*/modalias; do
		if [ -e "$m" ] && [ ! -e "${m%/modalias}/driver" ]; then
			modprobe -q "$(cat "$m")" 2>/dev/null || :
		fi
	done
fi
exit 0
}

# Amiko Viper 4K V20, V30, Protek 4K X2 (u57) si V40 (u571): rtl8188fu.ko (in imagine, pus din fabrica pe placa) cu
# -mlong-calls, ca modulele nucleului (motivul in dinobot-kernel/linux-dinobot_%.bbappend: zona modulelor e la 32,25 MB
# de capatul codului nucleului; modulul cade cu "relocation out of range" daca nimereste la inceputul ei). Modulul e
# din afara nucleului, deci KCFLAGS (din kcflags.inc, dat lui make prin mediu) atinge numai modulul.
KCFLAGS:append:u57 = " -mlong-calls"
KCFLAGS:append:u571 = " -mlong-calls"
PR:append:u57 = ".hds1"
PR:append:u571 = ".hds1"
