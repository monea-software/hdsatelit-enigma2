# HD Satelit 0.6.19 pentru Octagon SF8008 și SF8008 MINI: actualizarea 7 din meniu

Actualizarea 7 a imaginii 0.6.13 (Meniu > Setări > Programe și actualizări > Actualizare software) aduce trei pachete:
`enigma2-hdsatelit` pentru mașinile `sf8008` și `sf8008m`, făcut din `enigma2/` de aici (comiterea 693b0d8156860425e376e0a21e9e0b2cdace4333), în
construcția imaginii 0.6.13 a fiecărei mașini: stratul `meta-local/` de aici, cu rețeta `enigma2-hdsatelit` construită
cu `SRCREV` = comiterea de mai sus și `PV = "0.6.19+git${SRCPV}"`; tema `hdsatelit-skin` r0.hds16, din `skin/` de
aici, și `hdsatelit-ssh` 0.1.0-r3, din `meta-local/recipes-local/hdsatelit-ssh`, aceleași pachete ca în versiunea
0.6.19 pentru Amiko Viper 4K V20 (eticheta `v0.6.19`). Celelalte pachete sunt cele ale imaginii 0.6.13.

# HD Satelit 0.6.19 for the Octagon SF8008 and SF8008 MINI: update 7 from the menu

Update 7 of the 0.6.13 image (Menu > Settings > Software & Firmware > Software update) brings three packages:
`enigma2-hdsatelit` for the `sf8008` and `sf8008m` machines, built from `enigma2/` here (commit 693b0d8156860425e376e0a21e9e0b2cdace4333), in the
0.6.13 image build of each machine: the `meta-local/` layer here, with the `enigma2-hdsatelit` recipe built with
`SRCREV` = the commit above and `PV = "0.6.19+git${SRCPV}"`; the `hdsatelit-skin` theme r0.hds16, from `skin/` here,
and `hdsatelit-ssh` 0.1.0-r3, from `meta-local/recipes-local/hdsatelit-ssh`, the same packages as in version 0.6.19 for
the Amiko Viper 4K V20 (tag `v0.6.19`). The other packages are those of the 0.6.13 image.
