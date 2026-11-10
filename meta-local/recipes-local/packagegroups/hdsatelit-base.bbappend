# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Octagon SF8008 (masina sf8008, lotul imagine-060-sf8008): nucleul lui (linux-octagon 4.4.35, defconfig sf8008 din
# meta-octagon) are CONFIG_TUN=y, adica driverul tun e in nucleu, nu modul; pachetul kernel-module-tun nu se face pe
# aceasta masina, iar cererea din hdsatelit-base.bb ar opri constructia imaginii. /dev/net/tun exista oricum, deci
# OpenVPN merge la fel ca pe V20 (unde tun e modul). Numai pe sf8008: pe celelalte masini lista ramane neschimbata,
# iar hdsatelit-base.bb nu se atinge (verificarile lui fata de 0.5.0 raman aceleasi).
RDEPENDS:${PN}:remove:sf8008 = "kernel-module-tun"
#
# Octagon SF8008: load-ul producatorului incarca rtk_8822cbtusb.ko pe orice placa sf8008, iar placile cu cipul 8822C
# (Supreme, V3 Supreme) ii cer firmware-ul; imaginile facute pentru masina il au in /lib/firmware (rtl8822cu_fw si
# rtl8822cu_config, reteta OE-Alliance firmware-rtk8822cbtusb). Numai pe sf8008 (MINI nu are cipul).
RDEPENDS:${PN}:append:sf8008 = " firmware-rtk8822cbtusb"
#
# Octagon SF8008 si SF8008 MINI: Wi-Fi USB ca in imaginile facute pentru aceste masini (OE-Alliance,
# recipes-oe-alliance/image/oe-alliance-wifi.bb pune pe sf8008 si sf8008m enigma2-plugin-drivers-network-usb-rtl8821cu,
# -rtl8192eu, -mt7601u, -rtl8822cu si -rtl8188fu). Aici direct pachetele pe care le recomanda acestea (driverul si
# firmware-ul), fiindca o recomandare nu e o dependinta: rt8821cu + linux-firmware-8821cu, rtl8192eu + firmware-rtl8192eu,
# kernel-module-mt7601u (modulul din nucleu, CONFIG_MT7601U=m) + firmware-mt7601u, rt8822cu + firmware-rtk8822cbtusb;
# rt8188fu si firmware-rt8188fu sunt deja in hdsatelit-base.bb. Fara Bluetooth (rtk-btusb nu se recomanda pe sf8008).
HDS_WIFI_OCTAGON = "rt8821cu linux-firmware-8821cu rtl8192eu firmware-rtl8192eu kernel-module-mt7601u firmware-mt7601u rt8822cu"
RDEPENDS:${PN}:append:sf8008 = " ${HDS_WIFI_OCTAGON}"
RDEPENDS:${PN}:append:sf8008m = " ${HDS_WIFI_OCTAGON} firmware-rtk8822cbtusb"
#
# Uclan Ustym 4K PRO (ustym4kpro, geamanul lui SF8008): nucleul linux-uclan are CONFIG_TUN=m (defconfig ustym4kpro), deci
# kernel-module-tun din hdsatelit-base.bb ramane (ca pe V20). Wi-Fi USB ca pe SF8008 MINI: imaginile facute pentru
# masina au rtl8822cu (88x2cu.ko) cu firmware-rtk8822cbtusb, iar celelalte drivere sunt aceleasi ca pe familia Octagon.
RDEPENDS:${PN}:append:ustym4kpro = " ${HDS_WIFI_OCTAGON} firmware-rtk8822cbtusb"
#
# GigaBlue UHD TRIO 4K (masina gbmv200, MACHINEBUILD gbtrio4k): nucleul linux-gigablue are CONFIG_TUN=m si
# CONFIG_MT7601U=m (defconfig gbmv200), deci kernel-module-tun din hdsatelit-base.bb ramane (ca pe V20). Wi-Fi USB ca pe
# Ustym (aceleasi drivere din afara nucleului, acelasi nucleu 4.4.35): imaginile facute pentru masina recomanda si ele
# rtl8192eu (packagegroup-oea-wifi.bb, MACHINE_BRAND GigaBlue); celelalte se pun ca pe familia Octagon, ca un stick
# Wi-Fi obisnuit sa mearga la fel pe toata familia libreader.
RDEPENDS:${PN}:append:gbtrio4k = " ${HDS_WIFI_OCTAGON} firmware-rtk8822cbtusb"
# Stickurile Wi-Fi Ralink (RT3070, RT2870, RT5370; cerute de un tester pe forum, 08.11.2026): nucleul gbmv200 are
# CONFIG_RT2800USB=m (cu RT33XX, RT35XX, RT53XX), deci modulul rt2800usb si firmware-ul rt*.bin din linux-firmware-ralink.
RDEPENDS:${PN}:append:gbtrio4k = " kernel-module-rt2800usb linux-firmware-ralink"
# Receptoarele cu memorie interna mica (suprascrierea hdsflashmic, conf/distro/hdsatelit.conf; Vu+ Solo SE, lotul
# mips-solose, 06.11.2026): imaginea trebuie sa incapa instalata in NAND-ul de 256 MB (hotararea lui Eduard, 06.11.2026),
# deci pachetele mari care nu tin de televizor stau in feedul imaginii si se instaleaza la cerere: navigatorul
# (hds-navigator: WPE WebKit 34,5 MB si ICU 10,2 MB comprimate), recunoasterea textului (hds-ocr si hds-ocr-modele:
# tesseract, leptonica, modelele de limba, ~14 MB). Wi-Fi USB rt8188fu: driver din afara nucleului, scris pentru nucleele
# 4.x; Solo SE nu are Wi-Fi si nucleul lui e 3.13.5, deci nu intra (masuratorile: lucru-sesiune/oe-60/mips-solose).
RDEPENDS:${PN}:remove:hdsflashmic = "hds-navigator hds-ocr hds-ocr-modele rt8188fu firmware-rt8188fu"
# Partea a doua pe stick (componenta hdsatelit-partea-doua, 06.11.2026 seara): descrierea modelului, sablonul ext4 si
# scriptul de pornire, pe toate masinile cu memorie mica; fiecare are files/modele/<MACHINEBUILD>.conf (altfel reteta e
# sarita si constructia se opreste aici, ca sa nu uitam descrierea unui model nou).
RDEPENDS:${PN}:append:hdsflashmic = " hdsatelit-partea-doua"

# Limite hardware, indiferent de locul sistemului: rt8188fu cere nucleu 4.x.
# Navigatorul si OCR asteapta constructia MIPS si auditul scripturilor.
# Pachetul se scoate din aceasta lista numai dupa acea poarta, apoi se trece
# in HDS_FUNCTII_MIPS_PREGATITE. Nu este o limita a memoriei USB.
HDS_FUNCTII_MIPS_PREGATITE ?= ""
HDS_FUNCTII_MIPS_IN_ASTEPTARE = "hds-navigator hds-ocr hds-ocr-modele"
RDEPENDS:${PN}:remove:vusolose = "rt8188fu firmware-rt8188fu ${@' '.join(p for p in d.getVar('HDS_FUNCTII_MIPS_IN_ASTEPTARE').split() if p not in (d.getVar('HDS_FUNCTII_MIPS_PREGATITE') or '').split())}"
RDEPENDS:${PN}:append:vusolose = " hdsatelit-radacina-usb"

# Vu+ 4K (lotul a4-boot, 09.11.2026; lazcengiz, Uno4K SE, asistenta 742005): OpenMultiboot, luat de om din alt feed,
# cere pachetul kernel-module-nandsim, iar feedul nostru nu il avea, deci opkg refuza instalarea. Pe Vu+ 4K (eMMC,
# arhive tar.bz2) OpenMultiboot nu incarca nandsim (il foloseste numai la imaginile UBI de pe NAND), dar dependenta din
# reteta lui e neconditionata. Toate nucleele Vu+ 4K au CONFIG_MTD_NAND_NANDSIM=m (defconfig-urile linux-vuplus 3.14.28,
# 4.1.20, 4.1.45), deci modulul se face oricum (~20 KB) si nu se incarca singur. Masinile sunt numite una cate una, nu
# dupa MACHINE_FEATURES omb: o masina al carei nucleu nu face modulul ar opri constructia imaginii.
RDEPENDS:${PN}:append:vusolo4k = " kernel-module-nandsim"
RDEPENDS:${PN}:append:vuuno4k = " kernel-module-nandsim"
RDEPENDS:${PN}:append:vuuno4kse = " kernel-module-nandsim"
RDEPENDS:${PN}:append:vuultimo4k = " kernel-module-nandsim"
RDEPENDS:${PN}:append:vuduo4k = " kernel-module-nandsim"
RDEPENDS:${PN}:append:vuduo4kse = " kernel-module-nandsim"
RDEPENDS:${PN}:append:vuzero4k = " kernel-module-nandsim"

# Vu+ Solo4K, Duo4K, Uno4K SE: stickurile Wi-Fi Ralink (RT2870, RT3070, RT5370, RT5372; Bogdanici13, Vu+ Solo4K, forum
# 1024 si asistenta 694576, 10.11.2026: stickul 148f:5372 se vedea pe USB, dar nu aparea nicio placa Wi-Fi). Nucleele
# Vu+ 4K au CONFIG_RT2800USB=m (inventarul drivere-usb-073), deci modulul rt2800usb si firmware-ul rt*.bin din
# linux-firmware-ralink, ca pe gbtrio4k. PR-ul pachetului de grup creste pe aceste masini: actualizarea din meniu ia numai
# pachetele instalate cu versiune noua (HdsActualizari.planul), deci fara el cine actualizeaza nu primea nici driverul,
# nici kernel-module-nandsim de mai sus.
RDEPENDS:${PN}:append:vusolo4k = " kernel-module-rt2800usb linux-firmware-ralink"
RDEPENDS:${PN}:append:vuduo4k = " kernel-module-rt2800usb linux-firmware-ralink"
RDEPENDS:${PN}:append:vuuno4kse = " kernel-module-rt2800usb linux-firmware-ralink"
PR:append:vusolo4k = ".1"
PR:append:vuduo4k = ".1"
PR:append:vuuno4kse = ".1"
