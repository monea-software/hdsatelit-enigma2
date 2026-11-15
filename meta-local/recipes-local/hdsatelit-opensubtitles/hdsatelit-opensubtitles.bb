SUMMARY = "HD Satelit: cheia aplicatiei OpenSubtitles.com pentru cautarea subtitrarilor pe internet"
DESCRIPTION = "Pune cheia aplicatiei HD Satelit la OpenSubtitles.com (cheia de consumator a API-ului REST v1, antetul \
Api-Key) in /usr/share/hdsatelit/opensubtitles-aplicatie.key, unde o cauta \
Components/HdsSubtitrariInternet/surse/opensubtitles.py (FISIER_CHEIE). Cu ea, omul cu un cont gratuit OpenSubtitles \
cauta si descarca subtitrari fara sa-si faca o cheie a lui. Cheia NU sta in git: o citeste constructia dintr-un fisier \
din dosarul privat (HDS_OS_CHEIE, implicit feed-privat/opensubtitles-aplicatie.key, langa cheile de semnare ale \
feedului). Fara fisier pachetul e gol, iar sursa merge ca pana acum (cheia scrisa de om in setari). Monea Software \
pentru HD Satelit."
LICENSE = "CLOSED"
PV = "1.0"
PR = "r0"

# Dosarul privat al constructiei (in afara git-ului; HDS_FEED_PRIVAT il muta). Implicit /oe/feed-privat: /oe este dosarul ~/oe
# din WSL, legat in containerul de constructie (oe-60.sh), deci fisierul cheii se copiaza in ~/oe/feed-privat inainte de constructie.
# Fisierul: un singur rand, cheia aplicatiei, asa cum o da pagina de consumatori API a contului de dezvoltator
# OpenSubtitles. Cheia nu se tipareste nicaieri (nici bbnote, nici jurnalul): numai se copiaza.
HDS_FEED_PRIVAT ??= "/oe/feed-privat"
HDS_OS_CHEIE ??= "${HDS_FEED_PRIVAT}/opensubtitles-aplicatie.key"

inherit allarch

S = "${UNPACKDIR}"
ALLOW_EMPTY:${PN} = "1"
FILES:${PN} = "${datadir}/hdsatelit/opensubtitles-aplicatie.key"

do_configure[noexec] = "1"
do_compile[noexec] = "1"

# Suma fisierului intra in semnatura sarcinii (numai suma, nu cheia): cand fisierul apare sau se schimba, pachetul se
# face din nou, fara nimic de schimbat aici. Cat timp lipseste, bitbake spune un avertisment ca nu-i poate face suma.
do_install[file-checksums] += "${HDS_OS_CHEIE}:True"

do_install() {
	if [ -s "${HDS_OS_CHEIE}" ]; then
		cheie=$(head -c 300 "${HDS_OS_CHEIE}" | tr -d '\r\n\t ')
		# paza: un singur sir de litere si cifre (cheile OpenSubtitles au 32); altfel constructia se opreste, ca sa nu
		# ajunga in imagine un fisier gresit (de pilda o parola sau un text lipit din greseala)
		if ! printf '%s' "$cheie" | grep -q -E '^[A-Za-z0-9]{16,128}$'; then
			bbfatal "hdsatelit-opensubtitles: fisierul cheii aplicatiei nu are forma unei chei (litere si cifre, 16-128)"
		fi
		install -d ${D}${datadir}/hdsatelit
		printf '%s' "$cheie" > ${D}${datadir}/hdsatelit/opensubtitles-aplicatie.key
		chmod 0644 ${D}${datadir}/hdsatelit/opensubtitles-aplicatie.key
		bbnote "hdsatelit-opensubtitles: cheia aplicatiei pusa (${#cheie} semne)"
	else
		bbnote "hdsatelit-opensubtitles: fara cheia aplicatiei (pachet gol); OpenSubtitles cauta numai cu cheia scrisa de om"
	fi
}
