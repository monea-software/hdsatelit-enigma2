# HDSatelit, 24.09.2026: trezirea din oprirea completa (inregistrari programate), ceruta de Eduard pe 24.09 la 10:02.
#
# De ce: la oprirea din meniu, /etc/rc0.d/S89suspend porneste /usr/bin/hihalt (binar Dinobot inchis), care face
# system("python /usr/bin/timerTask.py"). Imaginea avea numai python3, deci comanda cadea, hipmoc nu rula niciodata:
# receptorul ramanea cu Linux pornit si afisajul stins si nu se trezea singur pentru inregistrari.
#
# Ce face acest fisier:
#  - RDEPENDS pe python3-compat2 (reteta din stratul comun OE-Alliance): /usr/bin/python -> python3.
#    Nimic din imagine nu se poarta altfel cand exista `python` (verificat in radacina si in sursa enigma2; singurul
#    care cauta `python` e Hds/DabT2/compat.py, care alege python3 cand exista);
#  - inlocuieste /usr/bin/timerTask.py (Dinobot, ar cadea la noi: deschide /etc/enigma2/pm_timers.xml, care nu exista,
#    ia primul temporizator din fisier in loc de cel mai devreme si poate da hipmoc un numar negativ) cu scriptul
#    nostru, files/hds-timerTask.py (cod propriu; fisierul Dinobot citit doar pentru comportament, nimic copiat);
#  - RDEPENDS pe modulele Python folosite (dovada din pkgdata-ul build-ului, nu din manifest):
#    python3-xml (xml/etree/ElementTree.pyc, pyexpat), python3-misc (os.pyc, subprocess.pyc; imaginea are numai .pyc,
#    care cad in misc), python3-core (_posixsubprocess);
#  - opreste compilarea cu eroare, nu trece tacut, daca: timerTask.py al Dinobot nu mai e unde il stim, hihalt nu mai
#    cheama exact "python /usr/bin/timerTask.py", scriptul nostru are CRLF, nu e Python valid sau nu e al nostru, ori
#    pachetul are alte fisiere decat cele 4 stiute;
#  - PR cu ".hds1", ca pachetul schimbat sa se vada in manifest si in "opkg list-installed" (20210604-r3.hds1).

PR:append = ".hds1"

FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://hds-timerTask.py"

RDEPENDS:${PN} += "python3-compat2 python3-core python3-misc python3-xml"

do_install:append() {
    f=${D}${bindir}/timerTask.py
    [ -f $f ] || bbfatal "HDSatelit: reteta Dinobot nu mai instaleaza ${bindir}/timerTask.py, de revazut bbappend-ul"
    grep -a -q 'python /usr/bin/timerTask.py' ${D}${bindir}/hihalt || \
        bbfatal "HDSatelit: hihalt nu mai cheama 'python /usr/bin/timerTask.py', de revazut bbappend-ul"
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
        bbfatal "HDSatelit: in pachetul dinobot-hihalt-u57 a aparut altceva: $rest"
    fi
    if [ "$(find ${D} ! -type d | wc -l)" != "4" ]; then
        bbfatal "HDSatelit: pachetul dinobot-hihalt-u57 nu are exact 4 fisiere"
    fi
}
