# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Octagon SF8008 MINI 4K (sf8008m): libreader-ul producatorului (arhiva 20221220) verifica autorizarea placii inainte sa
# devina demon; cand datele de autorizare ale placii nu trec (de pilda dupa o reparatie a memoriei), ramane la
# nesfarsit in bucla lui ("Auth" pe afisaj), iar pornirea se opreste la rcS S05. Imaginile facute pentru aceasta masina
# il folosesc cu un singur octet schimbat (steagul de autorizare pornit implicit): aceeasi schimbare aici. Paze: md5-ul
# fisierului din arhiva, tiparul exact o data, md5-ul de dupa schimbare = cel al libreader-ului acelor imagini.
HDS_LIBREADER_MD5_ARHIVA = "be64e7666fbf56e363cd67972846050f"
HDS_LIBREADER_MD5_SCHIMBAT = "141c368093637f65416fbf079f030270"
PR:append = ".hds1"

do_install:append() {
	python3 - "${D}${bindir}/libreader" "${HDS_LIBREADER_MD5_ARHIVA}" "${HDS_LIBREADER_MD5_SCHIMBAT}" <<'EOF'
import hashlib
import sys
cale, md5_arhiva, md5_schimbat = sys.argv[1:4]
date = open(cale, 'rb').read()
if hashlib.md5(date).hexdigest() != md5_arhiva:
    sys.exit('libreader: md5 %s, astept %s (alta arhiva a producatorului)' % (hashlib.md5(date).hexdigest(), md5_arhiva))
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
