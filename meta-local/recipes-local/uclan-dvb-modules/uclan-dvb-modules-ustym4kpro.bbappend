# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Uclan Ustym 4K PRO (masina ustym4kpro): driverul butoanelor din fata (hisi_keys.ko din arhiva ustym4kpro-hiko-20230804)
# e octet cu octet acelasi ca la Octagon SF8008 (arhiva sf8008-hiko-20240104, md5 00695f49...), deci are aceeasi
# problema: trimite KEY_UNKNOWN pentru orice cod pe care harta lui nu il are, iar interfata le ia drept taste. Imaginile
# facute pentru aceasta masina il folosesc cu aceleasi doua schimbari ca pe SF8008 (acelasi md5 dupa schimbare,
# 07cbb45a...): harta se termina dupa KEY_POWER, iar bucla de citire sare codurile necunoscute. Corpul e cel din
# octagon-dvb-modules-sf8008.bbappend. Pe OE-Alliance 6.0 reteta producatorului face deja schimbarile: atunci paza
# primeste fisierul cu md5-ul de dupa schimbare si nu mai schimba nimic. Paze: md5-ul fisierului din arhiva, fiecare tipar exact o data, md5-ul de dupa.
HDS_TASTE_MD5_ARHIVA = "00695f497c44462455d03f4f7dc71aa8"
HDS_TASTE_MD5_SCHIMBAT = "07cbb45a9c0aaa8f61dc084c6f0fe197"
# bucla de citire a nucleului 4.4.35 (forma scurta, fara mesaje), inainte si dupa
HDS_TASTE_BUCLA = "000050e3b820d011f020a003000054e3 000050e3b820d0110300000a000054e3"
PR:append = ".hds2"

# R2K (0.7.5, Wlad, forum 948): interfata 2560x1440 pentru temele 2K (Fury-FHD cu „Skin Resolution” 2K). Driverul hi_fb.ko
# refuza orice latime peste 1920; clasa OE-Alliance hisi-hifb-wqhd (meta-oe/classes, commitul 67bc3f2a90, mostenita deja de
# reteta) ridica limitele la 2560x1440 in hifb_set_par si hifb_disp_setdispsize; o pornim aici si fara e2egl. Memoria video
# ramane cea din fabrica a driverului (clasa ar pune vram0_size=43200): enigma2 al nostru cere 2 pagini, 2560x1440x2 = 28800 KB,
# care incap (40500 KB pe Viper 4K V20, 49152 KB pe V10). Probat pe receptorul de probe (V20) cu Fury-FHD 9.0 pe 2K, 13.11.2026
# (paralel-1111b/STADIU-R2K.md). Unde n-ar incapea, enigma2 refuza curat rezolutia si tema ramane pe HD Satelit (R2K, skin.py).
HISI_HIFB_WQHD_PATCH = "1"

do_install:append() {
	python3 - "${D}/lib/modules/${KV}/extra/hisi_keys.ko" "${HDS_TASTE_MD5_ARHIVA}" "${HDS_TASTE_MD5_SCHIMBAT}" ${HDS_TASTE_BUCLA} <<'EOF'
import hashlib
import sys
cale, md5_arhiva, md5_schimbat, bucla_v, bucla_n = sys.argv[1:6]
date = bytearray(open(cale, 'rb').read())
if hashlib.md5(date).hexdigest() == md5_schimbat:
    # reteta din OE-Alliance 6.0 face ea insasi aceleasi schimbari (hisi_keys_power_only_patch in uclan-dvb-modules-hisi.inc)
    print('hisi_keys.ko: deja schimbat de reteta, md5 %s' % md5_schimbat)
    sys.exit(0)
if hashlib.md5(date).hexdigest() != md5_arhiva:
    sys.exit('hisi_keys.ko: md5 %s, astept %s sau %s (alta arhiva a producatorului)' % (hashlib.md5(date).hexdigest(), md5_arhiva, md5_schimbat))
harta = bytes.fromhex('010000005700000074000000')
for vechi, nou in ((bytes.fromhex(bucla_v), bytes.fromhex(bucla_n)),
                   (harta + bytes.fromhex('01000000'), harta + bytes.fromhex('00000000'))):
    if date.count(vechi) != 1:
        sys.exit('hisi_keys.ko: tiparul %s apare de %d ori, astept o data' % (vechi.hex(), date.count(vechi)))
    i = date.find(vechi)
    date[i:i + len(vechi)] = nou
if hashlib.md5(date).hexdigest() != md5_schimbat:
    sys.exit('hisi_keys.ko: dupa schimbare md5 %s, astept %s' % (hashlib.md5(date).hexdigest(), md5_schimbat))
open(cale, 'wb').write(bytes(date))
print('hisi_keys.ko: harta oprita dupa KEY_POWER si codurile necunoscute sarite, md5 %s' % md5_schimbat)
EOF
	# R2K: hi_fb.ko peticit de clasa hisi-hifb-wqhd (mai sus); memoria video ramane cea din fabrica (load fara vram0_size)
	ldhds="$(find ${D} -path '*/modules/*/extra/load' | head -1)"
	kohds="$(find ${D} -path '*/modules/*/extra/hi_fb.ko' | head -1)"
	[ -n "$kohds" ] && [ -n "$ldhds" ] || bbfatal "R2K: hi_fb.ko sau load lipsesc din ${PN}"
	sed -i -e 's/^insmod hi_fb\.ko video="hi_fb:vram0_size:${HISI_HIFB_WQHD_VRAM0_SIZE}"$/insmod hi_fb.ko/' "$ldhds"
	[ "$(grep -c -x 'insmod hi_fb\.ko' "$ldhds")" = "1" ] || bbfatal "R2K: load din ${PN} nu are exact un rand 'insmod hi_fb.ko'"
	python3 -c 'import sys; d = open(sys.argv[1], "rb").read(); sys.exit(0 if any(bytes.fromhex(n) in d for n in sys.argv[2:]) else 1)' \
		"$kohds" a03500e30a0c52e3 0a0c52e33e0000ca041091e5a03500e3 a03500e3030058e10a0c5793 \
		|| bbfatal "R2K: hi_fb.ko din ${PN} nu e peticit pentru 2560x1440 (alta arhiva a producatorului: de citit din nou)"
}
