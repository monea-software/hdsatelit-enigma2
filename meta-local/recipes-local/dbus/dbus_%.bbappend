# Copyright (C) 2026 moneasoftware.com & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
# ZER1: OE init cauta pid-ul in /var/run, dar daemonul il scrie in /run.
# Un pid ramas dupa reset impiedica daemonul sa porneasca; init ascundea eroarea.
PR:append = ".hdszer1.hdsbld1"

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
