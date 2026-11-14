# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Driverele Amiko Viper 4K V10 (masina viper4k, arhiva viper4k-hiko-20201218): numai interfata 2560x1440 (R2K, mai jos); hi_fb.ko e acelasi fisier ca la Octagon SF8008 (md5 217694ef).
#
# R2K (0.7.5, Wlad, forum 948): interfata 2560x1440 pentru temele 2K (Fury-FHD cu „Skin Resolution” 2K). Driverul hi_fb.ko
# refuza orice latime peste 1920; clasa OE-Alliance hisi-hifb-wqhd (meta-oe/classes, commitul 67bc3f2a90, mostenita deja de
# reteta) ridica limitele la 2560x1440 in hifb_set_par si hifb_disp_setdispsize; o pornim aici si fara e2egl. Memoria video
# ramane cea din fabrica a driverului (clasa ar pune vram0_size=43200): enigma2 al nostru cere 2 pagini, 2560x1440x2 = 28800 KB,
# care incap (40500 KB pe Viper 4K V20, 49152 KB pe V10). Probat pe receptorul de probe (V20) cu Fury-FHD 9.0 pe 2K, 13.11.2026
# (paralel-1111b/STADIU-R2K.md). Unde n-ar incapea, enigma2 refuza curat rezolutia si tema ramane pe HD Satelit (R2K, skin.py).
HISI_HIFB_WQHD_PATCH = "1"
PR:append = ".hds1"

do_install:append() {
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
