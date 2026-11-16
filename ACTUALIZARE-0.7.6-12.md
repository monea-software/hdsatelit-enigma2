# HD Satelit 0.7.6: navigatorul web pentru Vu+ Solo SE în feedul din 16.11.2026

Feedul publicat pe 16.11.2026 pentru receptoarele cu imaginea de bază 0.7.1 (actualizarea 12) adaugă navigatorul web
pentru receptoarele MIPS (Vu+ Solo SE): pachetele `hds-navigator` 0.7.0-r9 și `libwpewebkit-2.0-1` 2.54.0-r0, plus
bibliotecile și fonturile de care au nevoie (brotli, fontconfig-utils, libepoxy0, libgcrypt, libgpg-error, libharfbuzz-icu0,
libicudata78, libicui18n78, libicuuc78, libx11-compose-data, libxkbcommon0, libxslt, ttf-dejavu-common, ttf-dejavu-sans,
ttf-dejavu-serif, woff2). Nu se instalează singure: se pun numai la cerere.

Pachetele sunt construite pentru mips32el cu straturile de aici. Față de eticheta `v0.7.6` se schimbă numai
`meta-local/recipes-local/wpewebkit/` (două petice noi, aplicate numai pe MIPS: `0020-libpas-use-the-ARM32-pair-paths-on-every-32-bit-target.patch`
și `0021-WTF-SequenceLocked-use-32-bit-words-without-lock-free-64-bit-atomics.patch`, și rândul `SRC_URI:append:mipsarch`
din `wpewebkit_2.54.0.bb`), `meta-local/recipes-local/packagegroups/hdsatelit-base.bbappend` (navigatorul permis pe MIPS)
și acest fișier. Codul imaginii (`enigma2/`), `skin/`, `LICENSE` și `README.md` sunt cele ale versiunii 0.7.6. Celelalte
pachete ale feedului sunt cele ale imaginii și ale actualizărilor de dinainte. Sursa WPE WebKit 2.54.0 este arhiva
oficială de la wpewebkit.org, cu peticele din `meta-local/recipes-local/wpewebkit/files/`.

# HD Satelit 0.7.6: the web browser for Vu+ Solo SE in the feed of 16.11.2026

The feed published on 16.11.2026 for receivers with the 0.7.1 base image (update 12) adds the web browser for the MIPS
receivers (Vu+ Solo SE): the `hds-navigator` 0.7.0-r9 and `libwpewebkit-2.0-1` 2.54.0-r0 packages, plus the libraries and
fonts they need (brotli, fontconfig-utils, libepoxy0, libgcrypt, libgpg-error, libharfbuzz-icu0, libicudata78,
libicui18n78, libicuuc78, libx11-compose-data, libxkbcommon0, libxslt, ttf-dejavu-common, ttf-dejavu-sans,
ttf-dejavu-serif, woff2). They are not installed automatically, only on request.

The packages are built for mips32el with the layers here. Compared with the `v0.7.6` tag only
`meta-local/recipes-local/wpewebkit/` (two new patches, applied on MIPS only:
`0020-libpas-use-the-ARM32-pair-paths-on-every-32-bit-target.patch` and
`0021-WTF-SequenceLocked-use-32-bit-words-without-lock-free-64-bit-atomics.patch`, and the `SRC_URI:append:mipsarch` line
in `wpewebkit_2.54.0.bb`), `meta-local/recipes-local/packagegroups/hdsatelit-base.bbappend` (the browser allowed on MIPS)
and this file change. The image code (`enigma2/`), `skin/`, `LICENSE` and `README.md` are those of version 0.7.6. The
other packages of the feed are those of the image and of the earlier updates. The WPE WebKit 2.54.0 source is the
official archive from wpewebkit.org, with the patches in `meta-local/recipes-local/wpewebkit/files/`.
