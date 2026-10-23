SUMMARY = "HDSatelit: numele hdsatelit.local in reteaua de acasa"
DESCRIPTION = "Pe langa numele receptorului (viper4kv20.local), avahi-daemon publica si hdsatelit.local cu adresa \
IPv4 de acum, ca interfata web sa se deschida cu http://hdsatelit.local; al doilea receptor din casa primeste \
hdsatelit-2.local. /etc/hostname nu se schimba. Monea Software pentru HD Satelit."
LICENSE = "GPL-2.0-only"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/GPL-2.0-only;md5=801f80980d171dd6425610833a22dbe6"
PV = "0.1.0"

SRC_URI = "file://hds-nume-local \
           file://60hds-nume-local \
           file://hds-nume-local.if-up \
"
S = "${UNPACKDIR}"

inherit allarch update-rc.d

do_configure[noexec] = "1"
do_compile[noexec] = "1"

# avahi-publish (avahi-utils) vorbeste cu avahi-daemon prin D-Bus (dbus-1 e deja in imagine, S02)
RDEPENDS:${PN} = "avahi-daemon avahi-utils busybox"

INITSCRIPT_NAME = "hds-nume-local"
# S22 in rc2-5: dupa avahi-daemon (S21) si dupa retea (S10)
INITSCRIPT_PARAMS = "start 22 2 3 4 5 . stop 20 0 1 6 ."

do_install() {
	install -d ${D}${sysconfdir}/init.d ${D}${sysconfdir}/udhcpc.d ${D}${sysconfdir}/network/if-up.d
	install -m 0755 ${S}/hds-nume-local ${D}${sysconfdir}/init.d/hds-nume-local
	install -m 0755 ${S}/60hds-nume-local ${D}${sysconfdir}/udhcpc.d/60hds-nume-local
	install -m 0755 ${S}/hds-nume-local.if-up ${D}${sysconfdir}/network/if-up.d/hds-nume-local
	for f in ${D}${sysconfdir}/init.d/hds-nume-local ${D}${sysconfdir}/udhcpc.d/60hds-nume-local \
		${D}${sysconfdir}/network/if-up.d/hds-nume-local; do
		if grep -q "$(printf '\r')" "$f"; then
			bbfatal "hdsatelit-nume-local: $f are sfarsit de rand CRLF"
		fi
	done
	# numele receptorului ramane al lui: scriptul nu scrie /etc/hostname si nici avahi-daemon.conf
	if grep -v '^#' ${D}${sysconfdir}/init.d/hds-nume-local | grep -q '/etc/hostname\|avahi-daemon.conf\|avahi-set-host-name'; then
		bbfatal "hdsatelit-nume-local: scriptul schimba numele receptorului"
	fi
	grep -q -- '-a -R' ${D}${sysconfdir}/init.d/hds-nume-local || bbfatal "hdsatelit-nume-local: avahi-publish fara -a -R"
}

FILES:${PN} = "${sysconfdir}/init.d/hds-nume-local ${sysconfdir}/udhcpc.d/60hds-nume-local \
               ${sysconfdir}/network/if-up.d/hds-nume-local"
