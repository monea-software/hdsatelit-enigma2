# HD Satelit 0.6.14 pentru Octagon SF8008 și SF8008 MINI: actualizarea 2 din meniu

Pachetul `enigma2-hdsatelit` pentru mașinile `sf8008` și `sf8008m`, publicat ca actualizarea 2 a imaginii 0.6.13 (Meniu >
Setări > Programe și actualizări > Actualizare software), e făcut din `enigma2/` de aici (aceeași comitere ca versiunea
0.6.14 pentru Amiko Viper 4K V20, 83bd32055ae89f8cf7ed0891b21e2a674e3a39f7), în construcția imaginii 0.6.13 a fiecărei
mașini: stratul `meta-local/` de aici (al imaginii, neschimbat), cu rețeta `enigma2-hdsatelit` construită cu `SRCREV` =
comiterea de mai sus și `PV = "0.6.14+git${SRCPV}"`. Pielea
(`skin/`) și celelalte pachete sunt cele ale imaginii 0.6.13.

# HD Satelit 0.6.14 for the Octagon SF8008 and SF8008 MINI: update 2 from the menu

The `enigma2-hdsatelit` package for the `sf8008` and `sf8008m` machines, published as update 2 of the 0.6.13 image (Menu >
Settings > Software & Firmware > Software update), is built from `enigma2/` here (the same commit as version 0.6.14 for
the Amiko Viper 4K V20, 83bd32055ae89f8cf7ed0891b21e2a674e3a39f7), in the 0.6.13 image build of each machine: the
`meta-local/` layer here (the image's, unchanged), with the `enigma2-hdsatelit` recipe built with `SRCREV` = the commit
above and `PV = "0.6.14+git${SRCPV}"`. The skin (`skin/`) and
the other packages are those of the 0.6.13 image.
