# HD Satelit 0.6.25 pentru primul Amiko Viper 4K (V10): actualizarea din meniu

Pachetul `enigma2-hdsatelit` 0.6.25 pentru mașina `viper4k`, publicat ca actualizarea 13 a imaginii V10 0.6.6
(Meniu > Setări > Programe și actualizări > Actualizare software), e făcut din `enigma2/` de aici (comiterea c239465c528fe64512f43fdfa4ab149c25ffa9e6), în
construcția imaginii V10 r3: stratul `meta-local/` de aici, cu rețeta `enigma2-hdsatelit` construită cu `SRCREV` =
comiterea de mai sus și `PV = "0.6.25+git${SRCPV}"`. Tot în actualizarea 13 vine `ca-certificates` 20260816
(certificatele rădăcină, Mozilla august 2026, pachet `all`), din rețeta `meta-local/recipes-local/ca-certificates` de
aici (luată din openembedded-core, ramura OE-Alliance 6.0), și paznicul interfeței `hdsatelit-watchdog` 0.1.0-r11 (pachet `all`), din rețeta
`meta-local/recipes-local/hdsatelit-watchdog` de aici. Tema (`skin/`) și celelalte pachete de sistem rămân cele ale
actualizării 7 (eticheta `v0.6.19-v10`).

# HD Satelit 0.6.25 for the first Amiko Viper 4K (V10): the update from the menu

The `enigma2-hdsatelit` 0.6.25 package for the `viper4k` machine, published as update 13 of the V10 0.6.6 image (Menu >
Settings > Software & Firmware > Software update), is built from `enigma2/` here (commit c239465c528fe64512f43fdfa4ab149c25ffa9e6), in the build of the V10
r3 image: the `meta-local/` layer here, with the `enigma2-hdsatelit` recipe built with `SRCREV` = the commit above and
`PV = "0.6.25+git${SRCPV}"`. Update 13 also brings `ca-certificates` 20260816 (the root certificates, Mozilla
August 2026, an `all` package), from the `meta-local/recipes-local/ca-certificates` recipe here (taken from
openembedded-core, the OE-Alliance 6.0 branch), and the interface watchdog `hdsatelit-watchdog` 0.1.0-r11 (an `all`
package), from the `meta-local/recipes-local/hdsatelit-watchdog` recipe here. The skin (`skin/`) and the other system packages stay those of update 7
(tag `v0.6.19-v10`).
