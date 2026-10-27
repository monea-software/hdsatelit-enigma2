# HDSatelit: trezirea din oprirea completa (inregistrari programate) si pe Amiko Viper 4K V40 (masina u571): aceeasi
# schimbare ca dinobot-hihalt-u57.bbappend (acolo e explicatia intreaga: hihalt cheama "python /usr/bin/timerTask.py",
# imaginea are numai python3, iar timerTask.py al producatorului ar cadea; il inlocuim cu files/hds-timerTask.py, cod
# propriu).
#
# Arhiva u571-hihalt-20210727 (sha256 cf9315b7, lotul imagine-060-v40, drivere-v20-v40.md): hihalt si timerTask.py
# IDENTICE, octet cu octet, cu cele din u57-hihalt-20210604; hipmoc e alt program (aceiasi pasi de oprire prin
# HI_UNF_PMOC_*, dar fara scrierea lui /proc/stb/hdmi/output inainte de oprire: de probat pe un V40 starea HDMI si
# trezirea la un temporizator). Pachetul are aceleasi 4 fisiere (hihalt, hipmoc, timerTask.py, init.d/suspend), deci
# pazele trec la fel. Corpul lui do_install:append e acelasi cu cel din dinobot-hihalt-u57.bbappend, in afara numelui
# pachetului din mesaje (${PN}); pregateste-meta-local-060.sh opreste stratul daca cele doua se despart.
# PR cu ".hds1", ca pachetul schimbat sa se vada in manifest si in "opkg list-installed" (20210727-r3.hds1).

PR:append = ".hds1"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://hds-timerTask.py"

RDEPENDS:${PN} += "python3-compat2 python3-core python3-misc python3-xml"

do_install:append() {
    f=${D}${bindir}/timerTask.py
    [ -f $f ] || bbfatal "HDSatelit: reteta ${PN} nu mai instaleaza ${bindir}/timerTask.py, de revazut bbappend-ul"
    grep -a -q 'python /usr/bin/timerTask.py' ${D}${bindir}/hihalt || \
        bbfatal "HDSatelit: hihalt din ${PN} nu mai cheama 'python /usr/bin/timerTask.py', de revazut bbappend-ul"
    install -m 0755 ${S}/hds-timerTask.py $f
    if grep -q "$(printf '\r')" $f; then
        bbfatal "HDSatelit: timerTask.py are CRLF, nu ar porni pe receptor"
    fi
    grep -q '^# HDSatelit timerTask.py: trezirea din oprirea completa' $f || \
        bbfatal "HDSatelit: timerTask.py instalat nu e scriptul nostru"
    python3 -c 'import ast, sys; ast.parse(open(sys.argv[1]).read(), sys.argv[1])' $f || \
        bbfatal "HDSatelit: timerTask.py are eroare de sintaxa Python"
    # Paza: in pachet trebuie sa fie exact hihalt, hipmoc, timerTask.py si init.d/suspend.
    rest=$(find ${D} ! -type d ! -path ${D}${bindir}/hihalt ! -path ${D}${bindir}/hipmoc \
        ! -path ${D}${bindir}/timerTask.py ! -path ${D}${sysconfdir}/init.d/suspend)
    if [ -n "$rest" ]; then
        bbfatal "HDSatelit: in pachetul ${PN} a aparut altceva: $rest"
    fi
    if [ "$(find ${D} ! -type d | wc -l)" != "4" ]; then
        bbfatal "HDSatelit: pachetul ${PN} nu are exact 4 fisiere"
    fi
}
