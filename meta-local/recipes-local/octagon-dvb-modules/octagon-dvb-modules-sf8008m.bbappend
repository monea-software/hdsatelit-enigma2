# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Octagon SF8008 MINI 4K (sf8008m): driverul butoanelor din fata (hisi_keys.ko, arhiva 20221108) trimite KEY_UNKNOWN
# pentru orice cod pe care harta lui nu il are, iar interfata le ia drept taste (meniuri si canale schimbate singure).
# Imaginile facute pentru aceasta masina il folosesc cu doua schimbari: harta se termina dupa KEY_POWER, iar bucla de
# citire sare codurile necunoscute. Aceleasi doua schimbari aici. Paze: md5-ul fisierului din arhiva, fiecare tipar
# exact o data, md5-ul de dupa schimbare = cel al driverului acelor imagini.
HDS_TASTE_MD5_ARHIVA = "af003feddb24396181576c90d812a796"
HDS_TASTE_MD5_SCHIMBAT = "d97993c06abe4704620bd282ce082d94"
# bucla de citire a nucleului 4.4.35 (forma cu mesaje de depanare), inainte si dupa
HDS_TASTE_BUCLA = "000050e30410a0e1b850d011f050a003 000050e30410a0e1b850d0110800000a"
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
