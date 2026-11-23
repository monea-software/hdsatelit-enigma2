# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# Kodi-ul masinilor (stb-kodi-<masina>_22.bb din OE-Alliance), pus in feedul nostru prin enigma2-plugin-extensions-
# hdsmediacenter si REDENUMIT „Media Center” (Eduard, 13.11.2026 09:12, varianta b; politica marcii Kodi: o versiune
# modificata si neaprobata se redenumeste, „Powered by Kodi” e voie). Dupa Official:Rebranding_Guidelines:
#   - ecranul de pornire si siglele din tema (Estuary le ia din special://xbmc/media: splash.jpg, vendor_logo.png,
#     vendor_icon.png, icon256x256.png) inlocuite cu desenele noastre (files/media-center, facute de
#     unealta fa_sigle_media_center.py din depozitul de unelte; nimic derivat din sigla Kodi);
#   - siglele interfetei web (webinterface.default: favicon si iconitele); interfata web e oprita implicit in Kodi;
#   - numele in retea (services.devicename: AirPlay, Bonjour/Zeroconf, UPnP) implicit „Media Center”, nu „Kodi”;
#   - textele engleze (resource.language.en_gb) cu „Media Center” in loc de „Kodi”; limbile descarcate din depozitul
#     oficial raman cum sunt (RAMAS in STADIU-KOD);
#   - politica de confidentialitate a noastra (privacy-policy.txt).
# Fara depozitele de addonuri ale altora si fara vizualizarile grele pe GL (opkg instaleaza singur ce e in Recommends):
# politica de distributie Kodi nu da voie la depozite straine puse dinainte, iar pe flash conteaza fiecare MB. Raman
# inputstream.adaptive (fluxurile DASH/HLS cu Widevine, drumul spre serviciile cu cont) si inputstream.rtmp.
# Fara LTO la prima constructie: legarea Kodi cu LTO cere multa memorie, iar WSL a cazut din lipsa de memorie (12.11).
# 4K: interfata Kodi ramane 1080p (HIFB/Mali fix, peticele 0020/0033); video-ul merge pe decodorul receptorului la
# rezolutia lui, iesirea HDMI e cea pusa la pornirea Kodi (pluginul o trece pe 2160p cand televizorul o prefera).
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI:append = " file://media-center"
# Mali-450 clips subtitle glyphs placed exactly on the near plane. Keep the
# fix local to HiSilicon; ordinary GUI depths and other platforms stay intact.
SRC_URI:append = "${@' file://hds-mali-subtitle-depth.patch' if d.getVar('HISI_STB') == '1' else ''}"

PACKAGECONFIG:remove = "lto"

RRECOMMENDS:${PN}:remove = " \
    kodi-addon-repository-kodinerds \
    kodi-addon-repository-kus-allinone \
    kodi-addon-visualization-fishbmc \
    kodi-addon-visualization-pictureit \
    kodi-addon-visualization-matrix \
    kodi-addon-visualization-shadertoy \
"

do_install:append() {
    mc=${UNPACKDIR}/media-center
    for f in splash.jpg vendor_logo.png vendor_icon.png icon256x256.png; do
        install -m 0644 $mc/media/$f ${D}${datadir}/kodi/media/$f
    done
    w=${D}${datadir}/kodi/addons/webinterface.default
    if [ -d $w ]; then
        for f in favicon.png icon-128.png icon-144.png icon-152.png icon-192.png icon.png; do
            install -m 0644 $mc/web/$f $w/$f
        done
    fi
    install -m 0644 $mc/privacy-policy.txt ${D}${datadir}/kodi/privacy-policy.txt

    s=${D}${datadir}/kodi/system/settings/settings.xml
    sed -i '/id="services.devicename"/,/<\/setting>/ s|<default>Kodi</default>|<default>Media Center</default>|' $s
    sed -n '/id="services.devicename"/,/<\/setting>/p' $s | grep -q '<default>Media Center</default>' || \
        bbfatal "stb-kodi: numele implicit services.devicename nu s-a schimbat in $s"

    # FFmpeg-ul propriu al lui Media Center (media-center-ffmpeg, /usr/lib/kodi/ffmpeg): cel al imaginii e taiat (fara
    # demultiplexoare si decodoare) si Kodi cadea la pornire. Dosarul intra primul in LD_LIBRARY_PATH in invelisul
    # /usr/bin/kodi: randul se pune chiar inainte de kodi-stb-runtime.sh, deci DUPA blocul HiSilicon care pune
    # LD_LIBRARY_PATH="/usr/lib:..."; asa dosarul nostru ajunge primul in cautare)
    w=${D}${bindir}/kodi
    grep -q '^\. /usr/lib/kodi/kodi-stb-runtime.sh$' $w || bbfatal "stb-kodi: invelisul $w nu are randul kodi-stb-runtime.sh"
    sed -i '/^\. \/usr\/lib\/kodi\/kodi-stb-runtime.sh$/i LD_LIBRARY_PATH="/usr/lib/kodi/ffmpeg${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"; export LD_LIBRARY_PATH  # HD Satelit: FFmpeg-ul lui Media Center' $w
    grep -q '^LD_LIBRARY_PATH="/usr/lib/kodi/ffmpeg' $w || bbfatal "stb-kodi: randul FFmpeg nu s-a pus in $w"

    p=${D}${datadir}/kodi/addons/resource.language.en_gb/resources/strings.po
    if [ -f $p ]; then
        sed -i '/^msgid "/ s/\bKodi\b/Media Center/g' $p
    fi

    # Fara ferestre la prima pornire (proba a doua pe receptorul de probe, 13.11.2026; KOD3): Kodi trece in baza lui OPRITE addonurile
    # gasite pe disc care nu sunt in system/addon-manifest.xml si intreaba omul la pornire „Disabled add-ons: enable ...?”
    # (Application.cpp, xbmc 8c36cc7f). Addonurile aduse de pachetele noastre (inputstream.rtmp, visualization.waveform,
    # script.xbmc.lcdproc pentru afisajul din fata prin stb-lcdd) intra in manifest ca „optional”: pornite din oficiu,
    # omul le poate opri din Setari.
    m=${D}${datadir}/kodi/system/addon-manifest.xml
    for a in inputstream.rtmp visualization.waveform script.xbmc.lcdproc; do
        grep -q ">$a</addon>" $m || sed -i "s|^\(\s*\)<addon optional=\"true\">inputstream.adaptive</addon>|&\n\1<addon optional=\"true\">$a</addon>|" $m
        grep -q "<addon optional=\"true\">$a</addon>" $m || bbfatal "stb-kodi: $a nu s-a pus in $m"
    done

    # Verificarea de versiune (service.xbmc.versioncheck) oprita din oficiu: Kodi-ul nostru vine din feedul imaginii, nu
    # de la kodi.tv, deci „versiune noua de Kodi” ar trimite omul in alta parte. Addonul ramane (omul il poate porni din
    # Setari > Addonuri); pluginul enigma2 scrie si valoarea omului „false” in profil la prima pornire, ca o actualizare
    # a addonului din depozit (care vine cu implicitul „true”) sa nu-l porneasca la loc.
    v=${D}${datadir}/kodi/addons/service.xbmc.versioncheck/resources/settings.xml
    if [ -f $v ]; then
        sed -i '/id="versioncheck_enable"/,/<\/setting>/ s|<default>true</default>|<default>false</default>|' $v
        sed -n '/id="versioncheck_enable"/,/<\/setting>/p' $v | grep -q '<default>false</default>' || \
            bbfatal "stb-kodi: versioncheck_enable nu s-a oprit in $v"
    fi
}

RDEPENDS:${PN} += "media-center-ffmpeg"
# libass (subtitrarile) cere conversia „macintosh” la numele fonturilor: fara ea „iconv_open() for macintosh -> UTF-8
# failed” la fiecare redare (proba a doua pe receptorul de probe)
RDEPENDS:${PN} += "glibc-gconv-macintosh"

PR:append = ".hds5"
