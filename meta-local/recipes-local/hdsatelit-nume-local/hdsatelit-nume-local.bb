SUMMARY = "HDSatelit: numele hdsatelit.local in reteaua de acasa"
DESCRIPTION = "Pe langa numele receptorului (viper4kv20.local), avahi-daemon publica si hdsatelit.local cu adresa \
IPv4 de acum, ca interfata web sa se deschida cu http://hdsatelit.local; al doilea receptor din casa primeste \
hdsatelit-2.local. /etc/hostname nu se schimba. Monea Software pentru HD Satelit."
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/GPL-2.0-only;md5=801f80980d171dd6425610833a22dbe6"
# 0.2.0 (11.11.2026, imaginea 0.7.4, TODO randul 1397): serviciul nou din imagine (fisa 79, comiterea 41e79b38c din
# hdsatelit-image) in locul scriptului shell. Cel vechi iesea pe loc cand receptorul nu avea inca adresa IPv4, fara
# fisierul pid, iar paznicul (hds-watchdog, nivelul 6) il credea cazut: 3 porniri pe ora, apoi "esec". Cel nou ramane
# pornit si asteapta reteaua si avahi; pid-ul ramane numeric in /var/run/hds-nume-local.pid, cum il citeste paznicul.
# files/hds-nume-local (initul) si files/hds-nume-local.py (serviciul) sunt COPII identice, octet cu octet, ale lui
# tools/hds-nume-local si tools/hds-nume-local.py din arborele imaginii (tools/Makefile.am le tine numai in EXTRA_DIST:
# le instaleaza un singur pachet, acesta). O schimbare acolo se copiaza din nou aici, cu PV mai mare; proba
# receptor/imagine-hdsatelit/teste/test_nume_local_reteta_074.py (hdsatelit-unelte) le compara.
PV = "0.2.0"

SRC_URI = "file://hds-nume-local \
           file://hds-nume-local.py \
           file://60hds-nume-local \
           file://hds-nume-local.if-up \
"
S = "${UNPACKDIR}"

inherit allarch update-rc.d

do_configure[noexec] = "1"
do_compile[noexec] = "1"

# avahi-publish (avahi-utils) vorbeste cu avahi-daemon prin D-Bus (dbus-1 e deja in imagine, S02); hook-urile sunt sh
# (busybox). Serviciul: os/re/select/shutil/signal/struct/subprocess/threading/time in python3-core, fcntl in
# python3-fcntl, socket in python3-io, json in python3-json (manifestul python3 din OE-Core 6.0).
RDEPENDS:${PN} = "avahi-daemon avahi-utils busybox python3-core python3-fcntl python3-io python3-json"
# jurnalul serviciului merge in syslog numai cu python3-syslog; fara el serviciul merge la fel (import syslog prins),
# deci e recomandare, nu dependinta: actualizarea din feed nu se opreste daca pachetul lipseste
RRECOMMENDS:${PN} = "python3-syslog"

INITSCRIPT_NAME = "hds-nume-local"
# S22 in rc2-5: dupa avahi-daemon (S21) si dupa retea (S10)
INITSCRIPT_PARAMS = "start 22 2 3 4 5 . stop 20 0 1 6 ."

do_install() {
	install -d ${D}${sysconfdir}/init.d ${D}${sysconfdir}/udhcpc.d ${D}${sysconfdir}/network/if-up.d ${D}${bindir}
	install -m 0755 ${S}/hds-nume-local ${D}${sysconfdir}/init.d/hds-nume-local
	install -m 0755 ${S}/hds-nume-local.py ${D}${bindir}/hds-nume-local.py
	install -m 0755 ${S}/60hds-nume-local ${D}${sysconfdir}/udhcpc.d/60hds-nume-local
	install -m 0755 ${S}/hds-nume-local.if-up ${D}${sysconfdir}/network/if-up.d/hds-nume-local
	for f in ${D}${sysconfdir}/init.d/hds-nume-local ${D}${bindir}/hds-nume-local.py \
		${D}${sysconfdir}/udhcpc.d/60hds-nume-local ${D}${sysconfdir}/network/if-up.d/hds-nume-local; do
		if grep -q "$(printf '\r')" "$f"; then
			bbfatal "hdsatelit-nume-local: $f are sfarsit de rand CRLF"
		fi
	done
	# initul cheama serviciul de la calea la care e instalat
	grep -qx 'exec /usr/bin/python3 /usr/bin/hds-nume-local.py "$@"' ${D}${sysconfdir}/init.d/hds-nume-local || \
		bbfatal "hdsatelit-nume-local: initul nu cheama /usr/bin/hds-nume-local.py"
	# numele receptorului ramane al lui: nici initul, nici serviciul nu scriu /etc/hostname sau avahi-daemon.conf
	for f in ${D}${sysconfdir}/init.d/hds-nume-local ${D}${bindir}/hds-nume-local.py; do
		if grep -v '^[[:space:]]*#' "$f" | grep -q '/etc/hostname\|avahi-daemon.conf\|avahi-set-host-name'; then
			bbfatal "hdsatelit-nume-local: $f schimba numele receptorului"
		fi
	done
	grep -q '"-a", "-R"' ${D}${bindir}/hds-nume-local.py || bbfatal "hdsatelit-nume-local: avahi-publish fara -a -R"
}

# Actualizarea de pe 0.1.0: scriptul de pe disc (cel vechi) isi opreste paznicul shell si avahi-publish INAINTE de
# inlocuirea fisierelor. Un paznic vechi ramas ar tine hdsatelit.local, iar serviciul nou nu l-ar vedea (nu are
# .identitate) si ar lua hdsatelit-2.local. De obicei o face si prerm-ul pachetului vechi (update-rc.d); aici e si
# pentru cazul in care acela nu ruleaza. O oprire nereusita nu opreste actualizarea.
pkg_preinst:${PN} () {
	if [ -z "$D" ] && [ -x ${sysconfdir}/init.d/hds-nume-local ]; then
		${sysconfdir}/init.d/hds-nume-local stop > /dev/null 2>&1 || true
	fi
}

FILES:${PN} = "${sysconfdir}/init.d/hds-nume-local ${bindir}/hds-nume-local.py \
               ${sysconfdir}/udhcpc.d/60hds-nume-local ${sysconfdir}/network/if-up.d/hds-nume-local"
