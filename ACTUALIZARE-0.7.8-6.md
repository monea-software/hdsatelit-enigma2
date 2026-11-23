# HD Satelit 0.7.8: actualizarea 6 din meniu, ZGEMMA H8.2H SE și H8.2H Plus

Actualizarea 6 a imaginii 0.7.8 aduce un singur pachet nou: `enigma2-hdsatelit` 0.7.8+git0+4bd49f6057-r2, numai pentru
ZGEMMA H8.2H SE (mașina `h8se`) și ZGEMMA H8.2H Plus (mașina `h8`). Celelalte pachete ale feedului și celelalte receptoare
rămân cu cele ale versiunii 0.7.8 și ale actualizărilor de dinainte.

Pachetul e făcut din `enigma2/` de aici, adică din codul versiunii 0.7.8 (comiterea 4bd49f6057fc436ec004b42489ad966653a9140e,
arborele git `6690c9917b24c48aeccf5ae6e32f67f8c89d52cc`, același ca la eticheta `v0.7.8`), cu rețetele din `meta-local/`:

- `meta-local/recipes-local/enigma2-hdsatelit/enigma2-hdsatelit.bb`: pe cele două mașini, `-DHDS_FARA_MEMORIE_ES=1` (driverele
  acestor receptoare nu au maparea memoriei video pe care o păzește codul; fără steag, filmele și fluxurile IPTV ar fi refuzate);
- `meta-local/recipes-local/enigma2-h8-r2/`: peticul `files/zgm1-h8-r2.patch`, pus de bitbake peste `enigma2/` numai pe
  `h8` și `h8se`, și `PR = "r2"`. Peticul are două reparații ale tunerelor: în bucla de după comanda motorului, după 3 s fără
  semnal acordarea se cere din nou (demodulatorul acestor receptoare nu caută singur semnalul după ce antena ajunge pe poziție);
  un tuner fără rânduri „Mode” și fără satelit (tunerul B al H8.2H Plus) primește cablu și terestru după ce spune nucleul
  (`DTV_ENUM_DELSYS`).

Față de eticheta `v0.7.8` se schimbă numai `meta-local/` (stratul construcțiilor H8, făcut din aceleași comiteri ca
pachetul) și acest fișier; `enigma2/`, `skin/`, `LICENSE` și `README.md` sunt cele ale versiunii 0.7.8.

Construirea pachetului: pașii din `README.md`, cu `make MACHINEBUILD=zgemmah8se DISTRO=hdsatelit init` (sau
`MACHINEBUILD=zgemmah82hplus` pentru Plus) și `bitbake enigma2-hdsatelit` în loc de `bitbake hdsatelit-image`. Rezultatul:
`tmp/deploy/ipk/h8se/enigma2-hdsatelit_0.7.8+git0+4bd49f6057-r2_h8se.ipk` (pe Plus, `h8` în loc de `h8se`).

# HD Satelit 0.7.8: menu update 6, ZGEMMA H8.2H SE and H8.2H Plus

Update 6 of the 0.7.8 image brings a single new package: `enigma2-hdsatelit` 0.7.8+git0+4bd49f6057-r2, only for the
ZGEMMA H8.2H SE (machine `h8se`) and the ZGEMMA H8.2H Plus (machine `h8`). The other packages of the feed and the other
receivers stay with those of version 0.7.8 and of the earlier updates.

The package is built from `enigma2/` here, that is the code of version 0.7.8 (commit 4bd49f6057fc436ec004b42489ad966653a9140e,
git tree `6690c9917b24c48aeccf5ae6e32f67f8c89d52cc`, the same as in the `v0.7.8` tag), with the recipes in `meta-local/`:

- `meta-local/recipes-local/enigma2-hdsatelit/enigma2-hdsatelit.bb`: on the two machines, `-DHDS_FARA_MEMORIE_ES=1` (the
  drivers of these receivers do not have the video memory mapping that the code guards; without the flag, films and IPTV
  streams would be refused);
- `meta-local/recipes-local/enigma2-h8-r2/`: the patch `files/zgm1-h8-r2.patch`, applied by bitbake on top of `enigma2/`
  only on `h8` and `h8se`, and `PR = "r2"`. The patch has two tuner fixes: in the loop after the motor command, after 3 s
  without signal the tuning is requested again (the demodulator of these receivers does not search for the signal by itself
  once the dish reaches its position); a tuner without "Mode" rows and without satellite (tuner B of the H8.2H Plus) gets
  cable and terrestrial from what the kernel reports (`DTV_ENUM_DELSYS`).

Compared with the `v0.7.8` tag only `meta-local/` (the layer of the H8 builds, made from the same commits as the package)
and this file change; `enigma2/`, `skin/`, `LICENSE` and `README.md` are those of version 0.7.8.

Building the package: the steps in `README.md`, with `make MACHINEBUILD=zgemmah8se DISTRO=hdsatelit init` (or
`MACHINEBUILD=zgemmah82hplus` for the Plus) and `bitbake enigma2-hdsatelit` instead of `bitbake hdsatelit-image`. The
result: `tmp/deploy/ipk/h8se/enigma2-hdsatelit_0.7.8+git0+4bd49f6057-r2_h8se.ipk` (on the Plus, `h8` instead of `h8se`).
