# HD Satelit 0.6.21 pentru Octagon SF8008 și SF8008 MINI: actualizarea 9 din meniu

Actualizarea 9 a imaginii 0.6.13 (Meniu > Setări > Programe și actualizări > Actualizare software) aduce un pachet:
`enigma2-hdsatelit` pentru mașinile `sf8008` și `sf8008m`, făcut din `enigma2/` de aici (comiterea 6d7af9a9acba7fc7892d649360da7e1fb290cfa0), în
construcția imaginii 0.6.13 a fiecărei mașini: stratul `meta-local/` de aici, cu rețeta `enigma2-hdsatelit` construită
cu `SRCREV` = comiterea de mai sus și `PV = "0.6.21+git${SRCPV}"`. Tema `hdsatelit-skin` r0.hds16 (`skin/`) și
`hdsatelit-ssh` 0.1.0-r3 rămân cele din actualizarea 7. Celelalte pachete sunt cele ale imaginii 0.6.13.

# HD Satelit 0.6.21 for the Octagon SF8008 and SF8008 MINI: update 9 from the menu

Update 9 of the 0.6.13 image (Menu > Settings > Software & Firmware > Software update) brings one package:
`enigma2-hdsatelit` for the `sf8008` and `sf8008m` machines, built from `enigma2/` here (commit 6d7af9a9acba7fc7892d649360da7e1fb290cfa0), in the
0.6.13 image build of each machine: the `meta-local/` layer here, with the `enigma2-hdsatelit` recipe built with
`SRCREV` = the commit above and `PV = "0.6.21+git${SRCPV}"`. The `hdsatelit-skin` theme r0.hds16 (`skin/`) and
`hdsatelit-ssh` 0.1.0-r3 stay those of update 7. The other packages are those of the 0.6.13 image.
