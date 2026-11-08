# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# GigaBlue UHD TRIO 4K (gbtrio4k): libreader-ul producatorului (arhiva gbtrio4k-libreader-20221220) verifica autorizarea
# placii inainte sa devina demon, ca la Octagon SF8008 MINI si Uclan Ustym 4K PRO (aceeasi marime, 555 960 o, alta
# compilare); cand datele de autorizare ale placii nu trec, ramane la nesfarsit in bucla lui, iar pornirea se opreste la
# rcS S05. Imaginile facute pentru aceasta masina il folosesc cu un singur octet schimbat (steagul de autorizare pornit
# implicit, tiparul 0a30c5e5 o data, la 0x27e08): reteta din OE-Alliance 6.0 face ea insasi schimbarea
# (do_install:append din gigablue-reader-gbtrio4k.bb), deci aici paza primeste fisierul cu md5-ul de dupa schimbare si nu
# mai schimba nimic; daca reteta n-ar mai face-o, o face paza. Paze: md5-ul fisierului din arhiva, tiparul exact o data,
# md5-ul de dupa schimbare.
HDS_LIBREADER_MD5_ARHIVA = "10e2d87df359536184ed2722b8a3d3a2"
HDS_LIBREADER_MD5_SCHIMBAT = "c8cf682118f38c181c963fb458c664f9"
PR:append = ".hds1"

do_install:append() {
	python3 - "${D}${bindir}/libreader" "${HDS_LIBREADER_MD5_ARHIVA}" "${HDS_LIBREADER_MD5_SCHIMBAT}" <<'EOF'
import hashlib
import sys
cale, md5_arhiva, md5_schimbat = sys.argv[1:4]
date = open(cale, 'rb').read()
if hashlib.md5(date).hexdigest() == md5_schimbat:
    # reteta din OE-Alliance 6.0 face ea insasi aceeasi schimbare (do_install:append din gigablue-reader-gbtrio4k.bb)
    print('libreader: octetul steagului e deja schimbat de reteta, md5 %s' % md5_schimbat)
    sys.exit(0)
if hashlib.md5(date).hexdigest() != md5_arhiva:
    sys.exit('libreader: md5 %s, astept %s sau %s (alta arhiva a producatorului)' % (hashlib.md5(date).hexdigest(), md5_arhiva, md5_schimbat))
vechi, nou = bytes.fromhex('0a30c5e5'), bytes.fromhex('0a20c5e5')
if date.count(vechi) != 1:
    sys.exit('libreader: tiparul apare de %d ori, astept o data' % date.count(vechi))
date = date.replace(vechi, nou, 1)
if hashlib.md5(date).hexdigest() != md5_schimbat:
    sys.exit('libreader: dupa schimbare md5 %s, astept %s' % (hashlib.md5(date).hexdigest(), md5_schimbat))
open(cale, 'wb').write(date)
print('libreader: octetul steagului de autorizare schimbat, md5 %s' % md5_schimbat)
EOF
}
