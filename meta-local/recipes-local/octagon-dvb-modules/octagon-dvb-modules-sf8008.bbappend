# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Octagon SF8008 (masina sf8008): driverul butoanelor din fata (hisi_keys.ko, arhiva 20240104) trimite KEY_UNKNOWN
# pentru orice cod pe care harta lui nu il are, iar interfata le ia drept taste (meniuri si canale schimbate singure).
# Imaginile facute pentru aceasta masina il folosesc cu doua schimbari: harta se termina dupa KEY_POWER, iar bucla de
# citire sare codurile necunoscute. Aceleasi doua schimbari aici. Paze: md5-ul fisierului din arhiva, fiecare tipar
# exact o data, md5-ul de dupa schimbare = cel al driverului acelor imagini.
HDS_TASTE_MD5_ARHIVA = "00695f497c44462455d03f4f7dc71aa8"
HDS_TASTE_MD5_SCHIMBAT = "07cbb45a9c0aaa8f61dc084c6f0fe197"
# bucla de citire a nucleului 4.4.35 (forma scurta, fara mesaje), inainte si dupa
HDS_TASTE_BUCLA = "000050e3b820d011f020a003000054e3 000050e3b820d0110300000a000054e3"
PR:append = ".hds1"

do_install:append() {
	python3 - "${D}/lib/modules/${KV}/extra/hisi_keys.ko" "${HDS_TASTE_MD5_ARHIVA}" "${HDS_TASTE_MD5_SCHIMBAT}" ${HDS_TASTE_BUCLA} <<'EOF'
import hashlib
import sys
cale, md5_arhiva, md5_schimbat, bucla_v, bucla_n = sys.argv[1:6]
date = bytearray(open(cale, 'rb').read())
if hashlib.md5(date).hexdigest() != md5_arhiva:
    sys.exit('hisi_keys.ko: md5 %s, astept %s (alta arhiva a producatorului)' % (hashlib.md5(date).hexdigest(), md5_arhiva))
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
}
