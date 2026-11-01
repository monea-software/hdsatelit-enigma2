# HD Satelit 0.6.19 pentru primul Amiko Viper 4K (V10): actualizarea din meniu

Pachetul `enigma2-hdsatelit` 0.6.19 pentru mașina `viper4k`, publicat ca actualizarea 7 a imaginii V10 0.6.6
(Meniu > Setări > Programe și actualizări > Actualizare software), e făcut din `enigma2/` de aici (aceeași comitere ca
versiunea 0.6.19 pentru Amiko Viper 4K V20, 693b0d8156860425e376e0a21e9e0b2cdace4333), în construcția imaginii V10 r3:
stratul `meta-local/` de aici, cu rețeta `enigma2-hdsatelit` construită cu `SRCREV` = comiterea de mai sus și
`PV = "0.6.19+git${SRCPV}"`. Tema (`skin/`, pachetul `hdsatelit-skin` r0.hds16) și pachetele de sistem `dropbear`
2026.94-r0.hds1, `hds-ocr` 0.2.1, `hdsatelit-jurnal` 0.1.0-r2 și `hdsatelit-ssh` 0.1.0-r3 sunt chiar cele ale
actualizării 0.6.19 a lui V20 (aceeași arhitectură, aceleași versiuni în imaginea de bază), din rețetele de aici
(`meta-local/recipes-local/`). Navigatorul și paznicul sunt cele ale actualizării 1, din sursa `v0.6.8-r1`.

# HD Satelit 0.6.19 for the first Amiko Viper 4K (V10): the update from the menu

The `enigma2-hdsatelit` 0.6.19 package for the `viper4k` machine, published as update 7 of the V10 0.6.6 image (Menu >
Settings > Software & Firmware > Software update), is built from `enigma2/` here (the same commit as version 0.6.19 for
the Amiko Viper 4K V20, 693b0d8156860425e376e0a21e9e0b2cdace4333), in the build of the V10 r3 image: the `meta-local/`
layer here, with the `enigma2-hdsatelit` recipe built with `SRCREV` = the commit above and `PV = "0.6.19+git${SRCPV}"`.
The skin (`skin/`, the `hdsatelit-skin` package r0.hds16) and the system packages `dropbear` 2026.94-r0.hds1, `hds-ocr`
0.2.1, `hdsatelit-jurnal` 0.1.0-r2 and `hdsatelit-ssh` 0.1.0-r3 are exactly those of the 0.6.19 update of the V20 (same
architecture, same versions in the base image), from the recipes here (`meta-local/recipes-local/`). The browser and the
watchdog are those of update 1, from the source `v0.6.8-r1`.
