# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Uclan Ustym 4K PRO (ustym4kpro): libreader-ul producatorului (arhiva ustym4kpro-libreader-20221220) verifica
# autorizarea placii inainte sa devina demon; cand datele de autorizare ale placii nu trec, ramane la nesfarsit in bucla
# lui, iar pornirea se opreste la rcS S05. E acelasi program ca la Octagon SF8008 MINI (arhiva din aceeasi zi, aceeasi
# marime, 2 octeti diferiti: o constanta de producator la 0xcb50 si 0x284d8), cu tiparul steagului la acelasi loc.
# Imaginile facute pentru aceasta masina il folosesc cu un singur octet schimbat (steagul de autorizare pornit implicit):
# aceeasi schimbare aici. Paze: md5-ul fisierului din arhiva, tiparul exact o data, md5-ul de dupa schimbare = cel al
# libreader-ului acelor imagini. Pe OE-Alliance 6.0 reteta producatorului face deja schimbarea: atunci paza primeste
# fisierul cu md5-ul de dupa schimbare si nu mai schimba nimic.
HDS_LIBREADER_MD5_ARHIVA = "8814bf88bb2f450a0fe9a8d5bff1177f"
HDS_LIBREADER_MD5_SCHIMBAT = "7abbc883afcb48edb140be5c580257e7"
PR:append = ".hds1"

do_install:append() {
	python3 - "${D}${bindir}/libreader" "${HDS_LIBREADER_MD5_ARHIVA}" "${HDS_LIBREADER_MD5_SCHIMBAT}" <<'EOF'
import hashlib
import sys
cale, md5_arhiva, md5_schimbat = sys.argv[1:4]
date = open(cale, 'rb').read()
if hashlib.md5(date).hexdigest() == md5_schimbat:
    # reteta din OE-Alliance 6.0 face ea insasi aceeasi schimbare (do_install:append din uclan-reader-ustym4kpro.bb)
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
