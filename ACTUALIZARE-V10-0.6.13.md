# HD Satelit 0.6.13 pentru primul Amiko Viper 4K (V10): actualizarea din meniu

Pachetul `enigma2-hdsatelit` 0.6.13 pentru mașina `viper4k`, publicat ca actualizarea 5 a imaginii V10 0.6.6
(Meniu > Setări > Programe și actualizări > Actualizare software), e făcut din `enigma2/` de aici (aceeași comitere ca
versiunea 0.6.13 pentru Amiko Viper 4K V20, c344e3d523692dbd0bd8b7ff82c774b223c650f5), în construcția imaginii V10 r3:
stratul `meta-local/` de aici, cu rețeta `enigma2-hdsatelit` construită cu `SRCREV` = comiterea de mai sus și
`PV = "0.6.13+git${SRCPV}"`. Pielea (`skin/`, pachetul `hdsatelit-skin` r0.hds12) și pachetele de sistem `dropbear`
2026.94-r0.hds1, `hds-ocr` 0.2.1, `hdsatelit-jurnal` 0.1.0-r2 și `hdsatelit-ssh` 0.1.0-r2 sunt chiar cele ale
actualizării 0.6.13 a lui V20 (aceeași arhitectură, aceleași versiuni în imaginea de bază), din rețetele de aici
(`meta-local/recipes-local/`). Navigatorul și paznicul sunt cele ale actualizării 1, din sursa `v0.6.8-r1`.

# HD Satelit 0.6.13 for the first Amiko Viper 4K (V10): the update from the menu

The `enigma2-hdsatelit` 0.6.13 package for the `viper4k` machine, published as update 5 of the V10 0.6.6 image (Menu >
Settings > Software & Firmware > Software update), is built from `enigma2/` here (the same commit as version 0.6.13 for
the Amiko Viper 4K V20, c344e3d523692dbd0bd8b7ff82c774b223c650f5), in the build of the V10 r3 image: the `meta-local/`
layer here, with the `enigma2-hdsatelit` recipe built with `SRCREV` = the commit above and `PV = "0.6.13+git${SRCPV}"`.
The skin (`skin/`, the `hdsatelit-skin` package r0.hds12) and the system packages `dropbear` 2026.94-r0.hds1, `hds-ocr`
0.2.1, `hdsatelit-jurnal` 0.1.0-r2 and `hdsatelit-ssh` 0.1.0-r2 are exactly those of the 0.6.13 update of the V20 (same
architecture, same versions in the base image), from the recipes here (`meta-local/recipes-local/`). The browser and the
watchdog are those of update 1, from the source `v0.6.8-r1`.
