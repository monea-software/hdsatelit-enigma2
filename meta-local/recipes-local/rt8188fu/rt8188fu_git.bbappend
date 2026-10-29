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
RDEPENDS:${PN}:append:sf8008 = " ${HDS_WIFI_PURTAT}"
RDEPENDS:${PN}:append:sf8008m = " ${HDS_WIFI_PURTAT}"

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
