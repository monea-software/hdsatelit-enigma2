# procps-sysctl: /etc/sysctl.conf cu kernel.sysrq = 0 (tastele SysRq ale unei tastaturi oprite).
#
# Nucleul receptorului porneste cu SysRq deschis (CONFIG_MAGIC_SYSRQ_DEFAULT_ENABLE=0x1, /proc/sys/kernel/sysrq = 1).
# O tastatura USB pusa in receptor nu e apucata de enigma2, deci Alt+PrintScreen+B (si celelalte taste SysRq) ar
# reporni receptorul pe loc, fara oprirea curata a interfetei. /etc/init.d/bootmisc.sh (initscripts, S55 in rcS)
# aplica la fiecare pornire `/sbin/sysctl -p /etc/sysctl.conf`; /etc/sysctl.d nu e citit acolo, de aceea randul sta
# chiar in /etc/sysctl.conf.
# Fisierul vine din stratul comun (meta-oe-alliance, procps_4.0.%.bbappend si procps/sysctl.conf) si se termina fara
# sfarsit de rand: blocul de aici incepe cu un sfarsit de rand, ca randul nostru sa nu se lipeasca de ultimul, si sta
# la sfarsit (sysctl -p aplica randurile in ordine).
# /proc/sysrq-trigger ramane deschis pentru root oricare ar fi kernel.sysrq: repornirea dura a paznicului
# (hds-watchdog.py, sysrq 's' si 'b') merge la fel.
# procps-sysctl nu are fisierul in CONFFILES (CONFFILES e pus pe procps, iar fisierul e in procps-sysctl), deci o
# actualizare a pachetului scrie /etc/sysctl.conf din nou, fara copie -opkg.
# PR ".hds1": alt continut la aceeasi versiune, ca opkg sa ia pachetul (4.0.5-r0.1.hds1 e mai mare decat 4.0.5-r0.1).
# Constructia se opreste daca fisierul lipseste, daca are deja un rand kernel.sysrq activ (de lamurit de un om), daca
# continutul de dinainte nu a ramas intreg sau daca randul nostru nu e ultimul.

PR:append = ".hds1"

do_install:append() {
	f=${D}${sysconfdir}/sysctl.conf
	if [ ! -f "$f" ]; then
		bbfatal "procps: lipseste $f"
	fi
	if grep -q '^[[:space:]]*kernel\.sysrq[[:space:]]*=' "$f"; then
		bbfatal "procps: sysctl.conf are deja un rand kernel.sysrq activ; de lamurit inainte de a adauga altul"
	fi
	cp "$f" ${T}/sysctl.conf.inainte
	c='# HD Satelit: no SysRq from a keyboard (root can still use /proc/sysrq-trigger)'
	printf '\n%s\n%s\n' "$c" 'kernel.sysrq = 0' >> "$f"
	n=$(wc -c < ${T}/sysctl.conf.inainte)
	if ! cmp -s -n "$n" ${T}/sysctl.conf.inainte "$f"; then
		bbfatal "procps: continutul de dinainte al lui sysctl.conf nu a ramas intreg"
	fi
	if [ "$(grep -c '^[[:space:]]*kernel\.sysrq[[:space:]]*=' "$f")" != "1" ]; then
		bbfatal "procps: sysctl.conf nu are exact un rand kernel.sysrq activ"
	fi
	if [ "$(tail -n 1 "$f")" != "kernel.sysrq = 0" ]; then
		bbfatal "procps: kernel.sysrq = 0 nu e ultimul rand din sysctl.conf"
	fi
	if grep -q "$(printf '\r')" "$f"; then
		bbfatal "procps: sysctl.conf are CR"
	fi
}
