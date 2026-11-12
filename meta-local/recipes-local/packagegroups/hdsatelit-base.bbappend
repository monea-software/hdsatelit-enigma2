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
# Vu+ Duo 4K Lite (VU1): defconfig_initrd al nucleului lui are CONFIG_MTD_NAND_NANDSIM=m
RDEPENDS:${PN}:append:vuduo4klite = " kernel-module-nandsim"
# Vu+ Duo 4K Lite (VU1): vuplus-ddbootup (meta-vuplusde, numai Recommends acolo) scrie la pornire boxtype, vumodel si
# model (driverul nu le da) si porneste afisajul (lcd/mode 1, /dev/dbox/lcd0); garda de model si afisajul color au nevoie de el
RDEPENDS:${PN}:append:vuduo4klite = " vuplus-ddbootup"

# Vu+ Solo4K, Duo4K, Uno4K SE: stickurile Wi-Fi Ralink (RT2870, RT3070, RT5370, RT5372; Bogdanici13, Vu+ Solo4K, forum
# 1024 si asistenta 694576, 10.11.2026: stickul 148f:5372 se vedea pe USB, dar nu aparea nicio placa Wi-Fi). Nucleele
# Vu+ 4K au CONFIG_RT2800USB=m (inventarul drivere-usb-073), deci modulul rt2800usb si firmware-ul rt*.bin din
# linux-firmware-ralink, ca pe gbtrio4k. PR-ul pachetului de grup creste pe aceste masini: actualizarea din meniu ia numai
# pachetele instalate cu versiune noua (HdsActualizari.planul), deci fara el cine actualizeaza nu primea nici driverul,
# nici kernel-module-nandsim de mai sus.
RDEPENDS:${PN}:append:vusolo4k = " kernel-module-rt2800usb linux-firmware-ralink"
RDEPENDS:${PN}:append:vuduo4k = " kernel-module-rt2800usb linux-firmware-ralink"
RDEPENDS:${PN}:append:vuuno4kse = " kernel-module-rt2800usb linux-firmware-ralink"
RDEPENDS:${PN}:append:vuduo4klite = " kernel-module-rt2800usb linux-firmware-ralink"
PR:append:vusolo4k = ".1"
PR:append:vuduo4k = ".1"
PR:append:vuuno4kse = ".1"
PR:append:vuduo4klite = ".1"

# Stickuri Wi-Fi USB cu driverul in nucleu si adaptoare de retea USB (cererea din 10.11.2026, treapta A1 din
# lucru-sesiune/oe-60/drivere-usb-073/INVENTAR-DRIVERE.md). Raman in imagine, nu in feed: ele sunt chiar legatura la
# internet, iar omul fara cablu n-ar avea de unde lua driverul. Modulele sunt deja construite de nucleul fiecarei masini
# de mai jos (verificat in tmp/deploy/ipk pe toate, 10.11.2026); udev le incarca singur dupa ID-ul USB cand omul baga
# stickul (80-drivers.rules, modules.alias), iar S05modload.sh la pornire, cand stickul a ramas in mufa. Firmware-ul sta in
# /lib/firmware (linux-firmware impartit, arhitectura all). Dependintele (rt2x00, rtlwifi, ath9k-hw, mac80211, usbnet) vin
# singure din pachetele modulelor. Masinile sunt numite una cate una: o masina al carei nucleu nu face un modul ar opri
# constructia (o masina noua nu primeste lista fara verificare).
# rtl8xxxu nu intra: pe 4.4.35 are 59 de ID-uri USB comune cu rtl8192cu si doua module s-ar lega de acelasi stick.
# Firmware-ul 8188EU nu vine din linux-firmware-rtl8188: acela pune si rtl8188fufw.bin, care e deja in firmware-rt8188fu
# (doua pachete cu acelasi fisier opresc imaginea); el vine mai tarziu, din reteta lui (treapta A2 a inventarului).
HDS_WIFI_USB = "kernel-module-rt2800usb kernel-module-rt73usb kernel-module-rt2500usb kernel-module-rtl8192cu \
    kernel-module-r8188eu kernel-module-r8712u kernel-module-ath9k-htc kernel-module-carl9170 kernel-module-zd1211rw \
    kernel-module-rtl8187 linux-firmware-ralink linux-firmware-rtl8192cu linux-firmware-rtl8192su linux-firmware-ath9k \
    linux-firmware-carl9170"
HDS_RETEA_USB = "kernel-module-r8152 kernel-module-asix kernel-module-cdc-ether kernel-module-cdc-ncm kernel-module-rndis-host \
    kernel-module-smsc95xx kernel-module-dm9601 kernel-module-sr9700"
RDEPENDS:${PN}:append:sf8008 = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
RDEPENDS:${PN}:append:sf8008m = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
RDEPENDS:${PN}:append:ustym4kpro = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
RDEPENDS:${PN}:append:gbtrio4k = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
# Amiko Viper 4K (V10): nucleul face si mt7601u (CONFIG_MT7601U=m), ca familia Octagon
RDEPENDS:${PN}:append:viper4k = " ${HDS_WIFI_USB} ${HDS_RETEA_USB} kernel-module-mt7601u firmware-mt7601u"
# Viper 4K V20, V30, Protek 4K X2 (u57) si V40 (u571): asix, cdc-ether, cdc-ncm si dm9601 sunt in nucleu, iar rndis-host,
# smsc95xx si sr9700 lipsesc; dintre adaptoarele de retea ramane numai r8152.
RDEPENDS:${PN}:append:u57 = " ${HDS_WIFI_USB} kernel-module-r8152"
RDEPENDS:${PN}:append:u571 = " ${HDS_WIFI_USB} kernel-module-r8152"
# Vu+ 4K (nucleele Vu+ n-au MT7601U)
RDEPENDS:${PN}:append:vusolo4k = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
RDEPENDS:${PN}:append:vuduo4k = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
RDEPENDS:${PN}:append:vuuno4kse = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
# Vu+ Duo 4K Lite (VU1): toate modulele din cele doua liste sunt =m in defconfig_initrd (meta-vuplusde, 12.11.2026)
RDEPENDS:${PN}:append:vuduo4klite = " ${HDS_WIFI_USB} ${HDS_RETEA_USB}"
# Vu+ Solo SE (NAND 256 MB, nucleu 3.13.5 fara rtl8192cu): nimic.
# Cine actualizeaza din meniu primeste driverele numai prin pachetul de grup: actualizarea ia numai pachetele instalate
# cu versiune noua (HdsActualizari.planul), iar opkg aduce apoi dependintele lui noi din feed. Deci PR-ul lui
# hdsatelit-base creste pe fiecare masina care primeste lista de mai sus; pe Vu+ 4K peste ".1" din 0.7.3 (rt2800usb),
# deci r0.1.1. Pe Solo SE nu se schimba nimic. Pachetele din liste trebuie culese in feedul fiecarei baze (--cu).
PR:append:sf8008 = ".1"
PR:append:sf8008m = ".1"
PR:append:ustym4kpro = ".1"
PR:append:gbtrio4k = ".1"
PR:append:viper4k = ".1"
PR:append:u57 = ".1"
PR:append:u571 = ".1"
PR:append:vusolo4k = ".1"
PR:append:vuduo4k = ".1"
PR:append:vuuno4kse = ".1"
PR:append:vuduo4klite = ".1"

# Imaginea mica (0.7.4, 10.11.2026; PROIECT-IMAGINE-MICA.md, treapta T2, hotararea 3 a coordonatorului): recunoasterea
# textului (hds-ocr si hds-ocr-modele: tesseract, leptonica, modelele celor 8 limbi, ~27 MB necomprimat) nu mai sta in
# imagine pe nicio masina. O foloseste numai traducerea subtitrarilor din imagine (subtitrarile DVB desenate,
# Components/HdsOcrSubtitrari.py); cand omul o porneste, receptorul o instaleaza singur din feed, semnat
# (Components/HdsLimbaRestaurare.py, ceriOcr). Pe hdsflashmic era deja scoasa (mai sus).
RDEPENDS:${PN}:remove = "hds-ocr hds-ocr-modele"

# 0.7.4: pachetul real „enigma2” 2.7+hds1 (hds-enigma2-compat.bb) pentru pluginurile scrise pentru alte imagini, in imagine si
# prin actualizare; Provides-ul enigma2 din enigma2-hdsatelit e scos (vezi reteta). Cerut pe numele retetei, nu pe „enigma2”,
# ca nicio alta reteta numita enigma2 sa nu poata intra. Revizia creste pe toate masinile (.2), ca receptoarele cu 0.7.3 sa ia
# noul hdsatelit-base (si deci pachetul) la actualizare, in aceeasi tranzactie cu enigma2-hdsatelit.
RDEPENDS:${PN}:append = " hds-enigma2-compat"
# 0.7.4, constructia comuna (CB074, 12.11.2026): revizia urca la ".3" pe toate masinile, ca receptoarele care au deja o 0.7.4
# de proba (hdsatelit-base r0.1.2 din constructiile de pe 11.11) sa primeasca prin actualizare driverele Wi-Fi din imagine (WD2) si
# openssl3-compat, venite dupa acele constructii. Pentru 0.7.3 -> 0.7.4 nu schimba nimic (tot mai nou).
PR:append = ".3"

# 0.7.4 (Eduard, 11.11.2026 18:56: „il pui in imagine”): openssl3-compat (recipes-local/openssl3-compat: libssl3 si libcrypto3,
# numai bibliotecile OpenSSL 3.5.9, ~4,3 MB instalati pe ARM, fara fisiere comune cu OpenSSL 4 al imaginii) pe toate masinile,
# pentru modulele si pluginurile altora facute pe OpenSSL 3 (OSCam-ul lui Levi45 si preinst-ul lui, care cauta libssl3 si
# libcrypto3 in /var/lib/opkg/status; forumul nostru 768 #1564, STADIU-P3-LIBSSL3.md). Cerut aici, deci vine si prin
# actualizarea din meniu 0.7.3 -> 0.7.4: PR-ul ".2" de mai sus (pachetul enigma2, tot 0.7.4, nepublicat inca) face
# hdsatelit-base mai nou pe toate masinile, iar opkg aduce openssl3-compat, libssl3 si libcrypto3 din feed in aceeasi
# tranzactie (culegerea feedului 0.7.4 trebuie sa ia hdsatelit-base cu --cu, ca pe hds-enigma2-compat).
RDEPENDS:${PN}:append = " openssl3-compat"

# 0.7.4 (Eduard, 11.11.2026: „decodarea sunetului in software pentru orice receptor care nu poate decoda hardware”): sunetul DAB+
# (AAC cu cadre de 960, HE-AAC) decodat de releul DAB in receptor pe placile care nu-l stiu (Vu+ Broadcom); libfaad2 si twolame
# (~0,38 MB) numai pe aceste masini. Pe HiSilicon decodeaza placa (Hds/DabT2/sunet_software.py, agentul DA).
RDEPENDS:${PN}:append:vuuno4kse = " libfaad2 twolame"
RDEPENDS:${PN}:append:vuduo4klite = " libfaad2 twolame"
RDEPENDS:${PN}:append:vuduo4k = " libfaad2 twolame"
RDEPENDS:${PN}:append:vusolo4k = " libfaad2 twolame"
RDEPENDS:${PN}:append:vusolose = " libfaad2 twolame"

# 0.7.4 (agentul WD, 11.11.2026): r8188eu e in imagine, dar fara firmware-ul lui stickurile RTL8188EUS (foarte raspandite) nu porneau;
# firmware-ul (13 KB, recipes-local/firmware-rtl8188eu) intra acolo unde intra driverele Wi-Fi USB.
HDS_WIFI_USB:append = " firmware-rtl8188eu"

# 0.7.4 (agentul WD2, 12.11.2026; Eduard 04:40, „Both”): omul care are NUMAI un stick Wi-Fi si niciun cablu nu putea lua
# driverul din feed (n-are internet fara el). Driverele stickurilor Wi-Fi 5 (AC) cele mai vandute stau deci in imagine;
# restul raman in feed (hdsatelit-drivere-feed), instalate singure la conectare cand receptorul are internet.
# Ales dupa ID-ul USB din modulele construite (tabela data/hds-drivere-pachete.json), nu dupa numele din cutie (acelasi nume
# de produs are alt cip la alta versiune), si dupa clasamentele magazinelor (STADIU-WD2-DRIVERE-IMAGINE-OFFLINE.md):
#   rtl8821au (RTL8811AU/8821AU, AC600): TP-Link Archer T2U Nano, T2U Plus, T2U, Edimax EW-7811UTC; ~3,1 MB instalat;
#   rtl88x2bu (RTL8812BU/8822BU, AC1300): Archer T3U, T3U Nano, T3U Plus, T4U v3, T4U Plus, Comfast CF-812AC; ~4,3 MB;
#     cere usb-modeswitch (stickurile care pornesc ca CD), fara tcl (recipes-local/usb-modeswitch);
#   rtl88xxau (RTL8812AU, AC1200): Archer T4U v1/v2 si stickurile RTL8812AU fara nume; ~2,9 MB;
#   rt8821cu (RTL8811CU/8821CU, AC600 ieftin): Comfast CF-811AC si multe stickuri fara nume; ~3,4 MB; deja in imagine pe
#     familia Octagon/Uclan/GigaBlue (HDS_WIFI_OCTAGON), aici si pe Viper 4K, V20/V30/Protek, V40 si Vu+ 4K.
# Toate sunt driverele comunitatii din organizatia de drivere, nemodificate, GPL-2.0-only (lista licentelor imaginii le ia
# singura); pe u57/u571 cu -mlong-calls (bbappend-urile lor). Locul: radacinile 0.7.4 masurate pe 11.11 aveau 80-132 MB
# liberi (sf8008 79,6, viper4k 97,3, u57 132,4), driverele iau ~10-14 MB. Nu intra: mt7610u (driverul MediaTek, fisiere
# .dat in /etc/Wireless, neprobat inca cu ecranul Wi-Fi), rtl8852bu (Wi-Fi 6, 6,9 MB, cel mai mare), rt8814au, rtl8192fu,
# rtl8852cu (rare). Masinile sunt numite una cate una, ca mai sus. Revizia: PR-ul ".2" de 0.7.4 (nepublicat inca) ajunge;
# culegerea feedului 0.7.4 ia hdsatelit-base cu --cu, deci si driverele, pentru cine actualizeaza din meniu.
HDS_WIFI_VANDUTE = "rtl8821au rtl88x2bu rtl88xxau usb-modeswitch usb-modeswitch-data"
RDEPENDS:${PN}:append:sf8008 = " ${HDS_WIFI_VANDUTE}"
RDEPENDS:${PN}:append:sf8008m = " ${HDS_WIFI_VANDUTE}"
RDEPENDS:${PN}:append:ustym4kpro = " ${HDS_WIFI_VANDUTE}"
RDEPENDS:${PN}:append:gbtrio4k = " ${HDS_WIFI_VANDUTE}"
RDEPENDS:${PN}:append:viper4k = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:u57 = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:u571 = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:vusolo4k = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:vuduo4k = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:vuuno4kse = " ${HDS_WIFI_VANDUTE} rt8821cu"
RDEPENDS:${PN}:append:vuduo4klite = " ${HDS_WIFI_VANDUTE} rt8821cu"
# Vu+ Solo SE (NAND 256 MB, hotararea lui Eduard din 06.11: imaginea incape in NAND, ce e mare sta in feed; ~72 MiB raman
# omului dupa instalare): numai primul, rtl8821au (Archer T2U Nano / T2U Plus, cele mai ieftine si mai vandute AC600; ~3,2 MB
# necomprimat, mai putin in UBIFS). Celelalte trei ar lua inca ~11 MB din locul omului; raman in feed si in pachetul de
# completari de pe stick. De confirmat de coordonator la constructia comuna (limita 150 MiB, verifica-model-nand-070.py).
RDEPENDS:${PN}:append:vusolose = " rtl8821au"
