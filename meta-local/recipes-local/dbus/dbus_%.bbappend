# Copyright (C) 2026 moneasoftware.com & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# ZER1: OE init cauta pid-ul in /var/run, dar daemonul il scrie in /run.
# Un pid ramas dupa reset impiedica daemonul sa porneasca; init ascundea eroarea.
PR:append = ".hdszer1.hdsbld1.hdsrun1"

do_install:append:class-target() {
    f=${D}${sysconfdir}/init.d/dbus-1
    if [ -f "$f" ]; then
        # Formele OE-core si OE-Alliance sunt diferite. Verificam intregul
        # script inainte de schimbare, normalizand numai bindir din reteta OE.
        suma=$(sed 's|^DAEMON=${bindir}/dbus-daemon$|DAEMON=@bindir@/dbus-daemon|' "$f" | sha256sum | cut -d ' ' -f 1)
        case "$suma" in
            a162136178e80e0ff522e16e1b16cf6515900cddbf088170cc4e2978677fa590)
                sed -i -e 's|^PIDFILE=/var/run/dbus/pid .*|PIDFILE=${runtimedir}/dbus/pid|' \
                    -e 's/^    --user $DAEMONUSER --exec $DAEMON -- --system $PARAMS$/    --user $DAEMONUSER --exec $DAEMON -- --system $PARAMS || return $?/' \
                    -e 's/^    start_it_up$/    start_it_up || exit $?/' "$f"
                ;;
            bef1f1615a4afaf406558132056a68d21c91270ca3a32ef4f5ad4db8774c5b5e)
                # Aceasta forma foloseste deja /run si sterge pid-ul ramas.
                # do_start returneaza eroarea, dar exit 0 de la sfarsit o ascundea.
                sed -i -e 's/do_start   ;;/do_start || exit $? ;;/' \
                    -e 's/^           do_start$/           do_start || exit $?/' \
                    -e '/^    log_end_msg $rc$/a\    [ "$rc" = 0 ] || return "$rc"' "$f"
                ;;
            *) bbfatal "dbus: init cu forma schimbata ($suma)" ;;
        esac
        sh -n "$f" || bbfatal "dbus: init nu e sh valid"
    fi
}

# RUN1 (0.8.0, TODO 23.11 22:40): dupa o oprire brusca /run/dbus/pid a ramas gol (/run statea pe disc). Forma OE-Alliance
# intreaba `kill -0 "$(cat pid)"`, adica `kill -0 ""`, care sub /bin/sh = bash intoarce 0: init-ul credea ca dbus merge si iesea
# fara sa-l porneasca (si cand il chema paznicul), avahi cadea, hdsatelit.local nu mai raspundea ore intregi. Ca la OE-core, dbus
# merge numai daca pid-ul din fisier e chiar dbus-daemon (/proc/<pid>/exe); pid gol, mort sau al altui program = porneste.
# Rezerva: o magistrala de sistem vie gasita dupa nume (fisierul lipsa sau stricat) ramane pornita, fara sa i se stearga soclul.
# Forma OE-core (fara pre_start_cleanup) verifica deja /proc/<pid>/exe si ramane cum e.
python hds_dbus_pid_viu() {
    import pathlib
    import subprocess
    cale = pathlib.Path(d.getVar('D') + d.getVar('sysconfdir') + '/init.d/dbus-1')
    if not cale.is_file():
        return
    text = cale.read_text()
    if 'pre_start_cleanup() {' not in text:
        return
    curata = '        if ! kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; then\n'
    porneste = '    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; then\n'
    ancora = '\npre_start_cleanup() {\n'
    if text.count(curata) != 1 or text.count(porneste) != 1 or text.count(ancora) != 1:
        bb.fatal('dbus: verificarea pid-ului din init s-a schimbat; trebuie vazuta din nou (RUN1)')
    functie = '\n'.join([
        '# HDSatelit: dbus merge numai daca pid-ul din fisier e chiar dbus-daemon; pid gol, mort sau al altui program nu.',
        '# Fara pid bun, o magistrala de sistem vie gasita dupa nume ramane pornita (nu i se sterge soclul).',
        'hds_dbus_viu() {',
        '    hds_pid=$(cat "$PIDFILE" 2>/dev/null)',
        '    case "$hds_pid" in',
        "        ''|*[!0-9]*) ;;",
        '        *) [ "$(readlink -f "/proc/$hds_pid/exe" 2>/dev/null)" = "$DAEMON" ] && return 0 ;;',
        '    esac',
        '    for hds_pid in $(pidof dbus-daemon 2>/dev/null); do',
        "        tr '\\0' '\\n' < \"/proc/$hds_pid/cmdline\" 2>/dev/null | grep -qx -- '--system' && return 0",
        '    done',
        '    return 1',
        '}',
        ''])
    text = text.replace(curata, '        if ! hds_dbus_viu; then\n')
    text = text.replace(porneste, '    if hds_dbus_viu; then\n')
    text = text.replace(ancora, '\n' + functie + ancora)
    cale.write_text(text)
    if subprocess.run(['sh', '-n', str(cale)]).returncode != 0:
        bb.fatal('dbus: init nu e sh valid dupa RUN1')
}
do_install[postfuncs] += "hds_dbus_pid_viu"
