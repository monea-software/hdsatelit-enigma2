SUMMARY = "HD Satelit: partea a doua a imaginii pe un stick USB, pentru receptoarele cu memorie interna mica"
DESCRIPTION = "Componenta comuna (Eduard, 06.11.2026 22:35-22:42: baza porneste din memoria interna, iar limbile, \
recunoasterea textului, navigatorul si restul se aseaza pe stick si se leaga singure la pornire; o metoda refolosibila pe \
multe modele). Reteta nu stie de niciun model: modelul da numai descrierea, files/modele/<MACHINEBUILD>.conf (PACHETE, \
PRAG_MIB, MARIME_MIB, EXT4, ASTEAPTA_S). Pune in imagine: /etc/hdsatelit-partea-doua.conf (descrierea), sablonul ext4 gol \
(xz, cu trasaturile nucleului modelului: receptorul il scrie pe stick fara mke2fs) si scriptul de pornire (rc3 S05, \
inainte de Enigma2). Motorul e Components/HdsParteaDoua.py din imagine. Pachetul ${PN}-continut (in feed, nu in imagine) \
depinde de pachetele partii a doua; receptorul il instaleaza pe stick, in destinatia opkg partea2. Proiectul si dovezile: \
lucru-sesiune/oe-60/mips-solose/STADIU-STICK.md. Monea Software pentru HD Satelit."
LICENSE = "CLOSED"
PV = "0.1.0"

SRC_URI = "file://hdsatelit-partea-doua file://modele"
S = "${UNPACKDIR}"
DEPENDS = "e2fsprogs-native xz-native"
# descrierea si sablonul tin de masina
PACKAGE_ARCH = "${MACHINE_ARCH}"

inherit update-rc.d

INITSCRIPT_PACKAGES = "${PN}"
INITSCRIPT_NAME:${PN} = "hdsatelit-partea-doua"
# rc3 S05: dupa rcS (udev, montarea automata a stickurilor) si inainte de gui (enigma2.sh) din inittab
INITSCRIPT_PARAMS:${PN} = "start 05 3 ."

PACKAGES =+ "${PN}-continut"
ALLOW_EMPTY:${PN}-continut = "1"
SUMMARY:${PN}-continut = "HD Satelit: continutul partii a doua (limbile si celelalte functii care nu incap in memoria interna)"
FILES:${PN} = "${sysconfdir} ${datadir}/hdsatelit-partea-doua"
FILES:${PN}-continut = ""
RDEPENDS:${PN} = "python3-core e2fsprogs-e2fsck"

HDS_PD_MODELE := "${THISDIR}/files/modele"

python () {
    import os, re
    mb = d.getVar('MACHINEBUILD') or ''
    cale = os.path.join(d.getVar('HDS_PD_MODELE'), mb + '.conf')
    if not mb or '/' in mb or not os.path.isfile(cale):
        raise bb.parse.SkipRecipe('partea a doua: modelul %s nu are descriere (files/modele/%s.conf)' % (mb, mb))
    c = {}
    with open(cale, encoding='utf-8') as f:
        for nr, rand in enumerate(f.read().splitlines(), 1):
            if not rand.strip() or rand.lstrip().startswith('#'):
                continue
            k, egal, v = rand.partition('=')
            if not egal or k not in ('PACHETE', 'PRAG_MIB', 'MARIME_MIB', 'EXT4', 'ASTEAPTA_S'):
                bb.fatal('partea a doua: %s randul %d nu e o cheie cunoscuta: %r' % (cale, nr, rand[:80]))
            c[k] = v.strip()
    for k in ('PRAG_MIB', 'MARIME_MIB', 'ASTEAPTA_S'):
        if not c.get(k, '').isdigit():
            bb.fatal('partea a doua: %s: %s= trebuie sa fie numar' % (cale, k))
    if not 64 <= int(c['MARIME_MIB']) <= 4000:
        bb.fatal('partea a doua: %s: MARIME_MIB intre 64 si 4000 (limita FAT32 e 4 GiB)' % cale)
    if not re.fullmatch(r'[a-z0-9_]+(,[a-z0-9_]+)*', c.get('EXT4', '')):
        bb.fatal('partea a doua: %s: EXT4= lista de trasaturi ext4 (litere mici, despartite prin virgula)' % cale)
    if not re.fullmatch(r'[a-z0-9.+-]+( [a-z0-9.+-]+)*', c.get('PACHETE', '')):
        bb.fatal('partea a doua: %s: PACHETE= lista de pachete, despartite prin spatiu' % cale)
    for k, v in c.items():
        d.setVar('HDS_PD_' + k, v)
    d.setVar('RDEPENDS:%s-continut' % d.getVar('PN'), c['PACHETE'])
}

do_configure[noexec] = "1"

# sablonul: un ext4 gol de MARIME_MIB, facut aici (pe receptor mke2fs-ul imaginii nu e folosit), cu NUMAI trasaturile date
# (MKE2FS_CONFIG gol: fara valorile implicite ale e2fsprogs nou, de pilda metadata_csum sau orphan_file, pe care un nucleu
# vechi nu le stie), apoi xz: din 1 GiB raman ~160 KB
do_compile() {
	rm -f ${B}/sablon.img ${B}/sablon.img.xz
	dd if=/dev/zero of=${B}/sablon.img bs=1M count=0 seek=${HDS_PD_MARIME_MIB} 2> /dev/null
	MKE2FS_CONFIG=/dev/null mke2fs -F -q -t ext4 -b 4096 -I 256 -i 16384 -O none,${HDS_PD_EXT4} \
		-E lazy_itable_init=1,lazy_journal_init=1 -L hds-partea2 ${B}/sablon.img
	trasaturi=$(dumpe2fs -h ${B}/sablon.img 2> /dev/null | sed -n 's/^Filesystem features:[[:space:]]*//p')
	for t in $(echo ${HDS_PD_EXT4} | tr ',' ' '); do
		echo " $trasaturi " | grep -q " $t " || bbfatal "partea a doua: sablonul nu are trasatura $t ($trasaturi)"
	done
	for t in $trasaturi; do
		echo ",${HDS_PD_EXT4}," | grep -q ",$t," || bbfatal "partea a doua: sablonul are trasatura $t, care nu e ceruta"
	done
	xz -9e -T1 -c ${B}/sablon.img > ${B}/sablon.img.xz
	rm -f ${B}/sablon.img
}

do_install() {
	install -d ${D}${sysconfdir}/init.d ${D}${datadir}/hdsatelit-partea-doua
	install -m 0755 ${S}/hdsatelit-partea-doua ${D}${sysconfdir}/init.d/hdsatelit-partea-doua
	install -m 0644 ${B}/sablon.img.xz ${D}${datadir}/hdsatelit-partea-doua/sablon-${HDS_PD_MARIME_MIB}.img.xz
	printf '%s\n' \
		"# HD Satelit: descrierea partii a doua pentru ${MACHINEBUILD} (din hdsatelit-partea-doua/files/modele)" \
		"MODEL=${MACHINEBUILD}" \
		"PACHET=${PN}-continut" \
		"SABLON=${datadir}/hdsatelit-partea-doua/sablon-${HDS_PD_MARIME_MIB}.img.xz" \
		"PRAG_MIB=${HDS_PD_PRAG_MIB}" \
		"MARIME_MIB=${HDS_PD_MARIME_MIB}" \
		"ASTEAPTA_S=${HDS_PD_ASTEAPTA_S}" \
		> ${D}${sysconfdir}/hdsatelit-partea-doua.conf
	chmod 0644 ${D}${sysconfdir}/hdsatelit-partea-doua.conf
	if grep -q "$(printf '\r')" ${D}${sysconfdir}/init.d/hdsatelit-partea-doua; then
		bbfatal "partea a doua: scriptul de pornire are CRLF, nu ar porni pe receptor"
	fi
}
