# HD Satelit 0.6.27 pentru Octagon SF8008 și SF8008 MINI: actualizarea 15 din meniu

Actualizarea 15 a imaginii 0.6.13 (Meniu > Setări > Programe și actualizări > Actualizare software) aduce trei pachete:
`enigma2-hdsatelit` pentru mașinile `sf8008` și `sf8008m`, făcut din `enigma2/` de aici (comiterea bfee49962366bf9d044ba9f17bec1ff1a428166d), în
construcția imaginii 0.6.13 a fiecărei mașini: stratul `meta-local/` de aici, cu rețeta `enigma2-hdsatelit` construită
cu `SRCREV` = comiterea de mai sus și `PV = "0.6.27+git${SRCPV}"`. Tema `hdsatelit-skin` r0.hds16 (`skin/`) și
`hdsatelit-ssh` 0.1.0-r3 rămân cele din actualizarea 7. Celelalte pachete sunt cele ale imaginii 0.6.13. Al doilea pachet: `ca-certificates`
20260816 (certificatele rădăcină, Mozilla august 2026, pachet `all`), din rețeta `meta-local/recipes-local/ca-certificates`
de aici (luată din openembedded-core, ramura OE-Alliance 6.0). Al treilea: `hdsatelit-watchdog` 0.1.0-r11 (paznicul
interfeței, pachet `all`), din rețeta `meta-local/recipes-local/hdsatelit-watchdog` de aici.

# HD Satelit 0.6.27 for the Octagon SF8008 and SF8008 MINI: update 15 from the menu

Update 15 of the 0.6.13 image (Menu > Settings > Software & Firmware > Software update) brings three packages:
`enigma2-hdsatelit` for the `sf8008` and `sf8008m` machines, built from `enigma2/` here (commit bfee49962366bf9d044ba9f17bec1ff1a428166d), in the
0.6.13 image build of each machine: the `meta-local/` layer here, with the `enigma2-hdsatelit` recipe built with
`SRCREV` = the commit above and `PV = "0.6.27+git${SRCPV}"`. The `hdsatelit-skin` theme r0.hds16 (`skin/`) and
`hdsatelit-ssh` 0.1.0-r3 stay those of update 7. The other packages are those of the 0.6.13 image. The second package: `ca-certificates`
20260816 (the root certificates, Mozilla August 2026, an `all` package), from the `meta-local/recipes-local/ca-certificates`
recipe here (taken from openembedded-core, the OE-Alliance 6.0 branch). The third: `hdsatelit-watchdog` 0.1.0-r11 (the interface
watchdog, an `all` package), from the `meta-local/recipes-local/hdsatelit-watchdog` recipe here.
