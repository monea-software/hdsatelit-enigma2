# HDSatelit: masurare rc S/3, numai pe cele patru modele investigate.
# Modifica local functia startup() instalata de sysvinit, fara copie de rc.
# Logul ramane in devtmpfs/tmpfs si nu este sincronizat pe flash.

PR:append:vuduo4k = ".hds35"
PR:append:vuuno4kse = ".hds35"
PR:append:vusolo4k = ".hds35"
PR:append:gbtrio4k = ".hds35"
PACKAGE_ARCH:vuduo4k = "${MACHINE_ARCH}"
PACKAGE_ARCH:vuuno4kse = "${MACHINE_ARCH}"
PACKAGE_ARCH:vusolo4k = "${MACHINE_ARCH}"
PACKAGE_ARCH:gbtrio4k = "${MACHINE_ARCH}"

python hds_init_timpi() {
    import pathlib
    import re
    import textwrap

    modele = {"vuduo4k", "vuuno4kse", "vusolo4k", "gbtrio4k"}
    # gbtrio4k e MACHINEBUILD (masina gbmv200); celelalte trei au MACHINE egal cu modelul
    if d.getVar("MACHINE") not in modele and d.getVar("MACHINEBUILD") not in modele:
        return

    cale = pathlib.Path(d.getVar("D")) / d.getVar("sysconfdir").lstrip("/") / "init.d/rc"
    if not cale.is_file():
        bb.fatal("HDSatelit timpi rc: lipseste %s" % cale)
    text = cale.read_text(encoding="utf-8")
    marcaj = "# HDSatelit: timpi rc numai in RAM, v1."
    inceput = '  hds_init_timp inceput "$1" "${2-}" -\n'
    sfarsit = ('  hds_init_status=$?\n'
               '  hds_init_timp sfarsit "$1" "${2-}" "$hds_init_status"\n')
    ajutor = textwrap.dedent(r'''
    # HDSatelit: timpi rc numai in RAM, v1.
    hds_init_ram_verificat=0
    hds_init_ram_pregatit=0
    hds_init_timp() {
      case "${runlevel-}" in S|3) ;; *) return 0 ;; esac
      if [ "$hds_init_ram_verificat" = 0 ]; then
        hds_init_ram_verificat=1
        if [ -r /proc/mounts ]; then
          while read -r hds_init_sursa hds_init_montare hds_init_fs hds_init_rest; do
            case "$hds_init_montare:$hds_init_fs" in
              /dev:devtmpfs|/dev:tmpfs) hds_init_ram_pregatit=1; break ;;
            esac
          done < /proc/mounts
        fi
      fi
      [ "$hds_init_ram_pregatit" = 1 ] || return 0
      {
        read -r hds_init_uptime hds_init_idle < /proc/uptime &&
        printf 'uptime=%s nivel=%s eveniment=%s script=%s actiune=%s cod=%s\n' \
          "$hds_init_uptime" "$runlevel" "$1" "$2" "$3" "$4" \
          >> /dev/.hds-init-timpi.log
      } 2>/dev/null || :
      return 0
    }

    ''').lstrip("\n")
    if marcaj in text:
        if text.count(ajutor) == 1 and text.count(inceput) == 1 and text.count(sfarsit) == 1:
            return
        bb.fatal("HDSatelit timpi rc: instrumentare anterioara incompleta")

    functii = list(re.finditer(r"(?ms)^startup\(\)[ \t]*\{(?P<corp>.*?)(?=^\})", text))
    if len(functii) != 1:
        bb.fatal("HDSatelit timpi rc: startup() lipseste sau nu este unica")
    functie = functii[0]
    corp = functie.group("corp")
    intrari = list(re.finditer(r'(?m)^[ \t]*case "\$1" in[ \t]*\n', corp))
    iesiri = list(re.finditer(r'(?m)^[ \t]*esac[ \t]*\n(?=[ \t]*startup_progress[ \t]*$)', corp))
    if len(intrari) != 1 or len(iesiri) != 1 or intrari[0].end() >= iesiri[0].start():
        bb.fatal("HDSatelit timpi rc: structura startup() s-a schimbat")
    intrare, iesire = intrari[0], iesiri[0]
    corp = (corp[:intrare.start()] + inceput + corp[intrare.start():iesire.end()]
            + sfarsit + corp[iesire.end():])
    rezultat = (text[:functie.start()] + ajutor
                + text[functie.start():functie.start("corp")] + corp
                + text[functie.end():])
    cale.write_text(rezultat, encoding="utf-8", newline="\n")
}

do_install[postfuncs] += " hds_init_timpi"
