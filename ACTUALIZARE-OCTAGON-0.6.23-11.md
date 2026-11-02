# HD Satelit 0.6.23 pentru Octagon SF8008 și SF8008 MINI: actualizarea 11 din meniu

Actualizarea 11 a imaginii 0.6.13 (Meniu > Setări > Programe și actualizări > Actualizare software) aduce un pachet:
`enigma2-hdsatelit` pentru mașinile `sf8008` și `sf8008m`, făcut din `enigma2/` de aici (comiterea ce4fcd31045e8ffc4d430b9e3de5498de2985fb4), în
construcția imaginii 0.6.13 a fiecărei mașini: stratul `meta-local/` de aici, cu rețeta `enigma2-hdsatelit` construită
cu `SRCREV` = comiterea de mai sus și `PV = "0.6.23+git${SRCPV}"`. Tema `hdsatelit-skin` r0.hds16 (`skin/`) și
`hdsatelit-ssh` 0.1.0-r3 rămân cele din actualizarea 7. Celelalte pachete sunt cele ale imaginii 0.6.13.

# HD Satelit 0.6.23 for the Octagon SF8008 and SF8008 MINI: update 11 from the menu

Update 11 of the 0.6.13 image (Menu > Settings > Software & Firmware > Software update) brings one package:
`enigma2-hdsatelit` for the `sf8008` and `sf8008m` machines, built from `enigma2/` here (commit ce4fcd31045e8ffc4d430b9e3de5498de2985fb4), in the
0.6.13 image build of each machine: the `meta-local/` layer here, with the `enigma2-hdsatelit` recipe built with
`SRCREV` = the commit above and `PV = "0.6.23+git${SRCPV}"`. The `hdsatelit-skin` theme r0.hds16 (`skin/`) and
`hdsatelit-ssh` 0.1.0-r3 stay those of update 7. The other packages are those of the 0.6.13 image.
