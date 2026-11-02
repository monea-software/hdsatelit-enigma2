# HDSatelit Image

Imagine Linux pentru receptoare de satelit cu procesor HiSilicon Hi3798MV200, făcută de Monea Software pentru
HD Satelit (hdsatelit.com). Interfața e enigma2 pe Python 3, cu tema HDSatelit și interfața web proprie. Meniurile sunt
traduse în 30 de limbi; câteva traduceri sunt încă incomplete.

Stadiu: versiune beta publică (0.6.x). Imaginile și actualizările: https://stb.hdsatelit.com/ și feedul imaginii, din
meniul receptorului.

## Receptoarele

| Receptorul | Mașina OpenEmbedded | Stadiul |
|---|---|---|
| Amiko Viper 4K V20 | `u57` (`viper4kv20`) | beta |
| Amiko Viper 4K V30 | `u57` | beta |
| Amiko Viper 4K V40 | `u571` | la beta testeri |
| Amiko Viper 4K V10 | `viper4k` | la beta testeri |
| Octagon SF8008 4K UHD | `sf8008` | la beta testeri |
| Octagon SF8008 MINI 4K | `sf8008m` | la beta testeri |

- Toate au procesorul HiSilicon Hi3798MV200 (4 nuclee ARM Cortex-A53) și memorie internă eMMC.
- Fiecare imagine se scrie și pornește numai pe receptorul pentru care e făcută; pe alt model arată numai un mesaj.

## Licența

Codul din acest depozit (enigma2 și modulele HDSatelit) are licența GNU GPL, versiunea 2 (GPL-2.0-only).
Excepție, până la hotărârea licenței lui: skinul HDSatelit (dosarul `HDSatelit/`, pachetul `hdsatelit-skin`), declarat
deocamdată închis în rețeta lui. Pornește din sursa enigma2 publicată de Dream Multimedia în starea din 14 septembrie 2011, derivată sub GPLv2 așa
cum permite licența originală a acelei versiuni. Detalii în [LICENSE](LICENSE), textul original în
[LICENSE.original-2011](LICENSE.original-2011), textul GPLv2 în [LICENSE.GPLv2](LICENSE.GPLv2), autorii în
[AUTHORS](AUTHORS) și [CREDITS](CREDITS), fișierele scoase în [doc/REMOVED-FILES](doc/REMOVED-FILES).

Fișierele din acest depozit care au licența lor, cu textul licenței lângă ele:

| Fișierele | Ce sunt | Licența |
|---|---|---|
| `data/fonts/tuxtxt.ttf` | Bitstream Vera Sans Mono Bold 1.10, nemodificat | Bitstream Vera (`tuxtxt.license`) |
| `data/fonts/DejaVuSansMono-Bold.ttf` | DejaVu Sans Mono Bold 2.35; schimbat numai spațiul dintre rânduri | Bitstream Vera, Arev, domeniul public (`DejaVuSansMono-Bold.license`) |
| `data/fonts/Hds*.ttf`, `HDSatelit/fonts/Hds*.ttf` | Open Sans; Noto Sans Arabic, Hebrew și Thai (instanțe statice, submulțimi) | SIL Open Font License 1.1 (`OFL.txt`) |
| `data/fonts/ae_AlMateen.ttf` | ae_AlMateen, Arabeyes.org | GNU GPL (`ae_AlMateen.license`) |

Imaginea construită conține și programele altora, fiecare cu licența lui:

- pachetele OpenEmbedded și OE-Alliance: nucleul Linux, BusyBox, glibc, Python, GStreamer și celelalte;
- componentele fabricantului receptorului (Dinobot): driverele HiSilicon, bibliotecile lor și programele lor de
  sunet și imagine. Sunt arhive binare, descărcate la construire de rețetele OE-Alliance de pe serverul lor de surse
  (source.mynonpublic.com). Sunt închise: nu sunt în acest depozit și nu avem sursa lor. Decodoarele de sunet AC3,
  E-AC3, DTS și TrueHD ale driverului conțin FFmpeg 3.3.2 (LGPL 2.1 sau mai nouă), construit de fabricantul
  driverului.

Lista completă a programelor din imagine și a licențelor lor, cu textul fiecărei licențe, se face la fiecare
construire și se vede pe receptor (Meniu > Informații sistem > Licențe) și în interfața web (pagina `/licente`).
Sursele componentelor GPL și LGPL se publică împreună cu fiecare versiune, la https://hdsatelit.com/codul-sursa/.

„Enigma” și „Dreambox” sunt mărci ale Dream Property GmbH; celelalte nume de produse aparțin deținătorilor lor.
HDSatelit Image e un proiect independent, fără legătură cu Dream Multimedia, cu fabricantul receptorului sau cu alte
echipe de imagini.

## Construirea

Imaginea se construiește cu OpenEmbedded, în mediul de construire OE-Alliance (ramura 5.6), pe Linux (Ubuntu 24.04
sau un container cu el), pentru mașina `u57` (`MACHINEBUILD=viper4kv20`), cu stratul rețetelor HDSatelit
(distribuția `hdsatelit`, imaginea `hdsatelit-image`, rețeta `enigma2-hdsatelit` care construiește acest cod).
Stratul se publică împreună cu sursa fiecărei versiuni și se pune primul în `BBLAYERS`. În dosarul de construire al
mașinii, cu `DISTRO=hdsatelit` în `env.source`:

```
source env.source
bitbake hdsatelit-image
```

Rezultatul: `tmp/deploy/images/u57/hdsatelit-<versiunea>-viper4kv20-<data>_mmc.zip`, cu `kernel.bin`,
`rootfs.tar.bz2` și `imageversion` în dosarul `e2/update/`.

## Instalarea pe receptor

Cele trei fișiere din arhivă se copiază pe un stick USB formatat FAT32, în dosarul `amiko/viper4kv20/`. Receptorul
se pornește în modul de întreținere (Maintenance Mode) și se alege actualizarea de pe USB. Receptorul nu are nicio
blocare: oricine poate construi imaginea din aceste surse, cu schimbările lui, și o poate instala la fel.

---

# HDSatelit Image (English)

Linux image for HiSilicon Hi3798MV200 satellite receivers, made by Monea Software for HD Satelit (hdsatelit.com).
The user interface is enigma2 on Python 3, with the HDSatelit theme and its own web interface. The menus are
translated into 30 languages; a few translations are still incomplete.

Status: public beta (0.6.x). Images and updates: https://stb.hdsatelit.com/ and the image feed, from the receiver menu.

## Receivers

| Receiver | OpenEmbedded machine | Status |
|---|---|---|
| Amiko Viper 4K V20 | `u57` (`viper4kv20`) | beta |
| Amiko Viper 4K V30 | `u57` | beta |
| Amiko Viper 4K V40 | `u571` | with beta testers |
| Amiko Viper 4K V10 | `viper4k` | with beta testers |
| Octagon SF8008 4K UHD | `sf8008` | with beta testers |
| Octagon SF8008 MINI 4K | `sf8008m` | with beta testers |

- All have the HiSilicon Hi3798MV200 processor (4 ARM Cortex-A53 cores) and eMMC storage.
- Each image is written and starts only on the receiver it is made for; on another model it shows only a message.

## License

The code in this repository (enigma2 and the HDSatelit modules) is licensed under the GNU GPL, version 2 only
(GPL-2.0-only). Exception, until its license is decided: the HDSatelit skin (the `HDSatelit/` folder, the
`hdsatelit-skin` package), declared closed in its recipe for now. It is based on the enigma2 source code published by Dream Multimedia (state of 14 September 2011),
derived under the GPLv2 as allowed by the original license of that version. See [LICENSE](LICENSE),
[LICENSE.original-2011](LICENSE.original-2011), [LICENSE.GPLv2](LICENSE.GPLv2), [AUTHORS](AUTHORS),
[CREDITS](CREDITS) and [doc/REMOVED-FILES](doc/REMOVED-FILES).

Files in this repository with their own license (the license text is next to them): the fonts listed in the table
above (Bitstream Vera, DejaVu, Open Sans and Noto under the SIL Open Font License 1.1, ae_AlMateen under the GNU
GPL).

The built image also contains software by others, each under its own license: the OpenEmbedded and OE-Alliance
packages (Linux kernel, BusyBox, glibc, Python, GStreamer and others), and the receiver manufacturer's components
(Dinobot: HiSilicon drivers, their libraries and their audio and video programs), binary archives downloaded at
build time by the OE-Alliance recipes from their source server (source.mynonpublic.com). These are closed: they
are not in this repository and their source is not available to us. The AC3, E-AC3, DTS and TrueHD audio
decoders of the driver contain FFmpeg 3.3.2 (LGPL 2.1 or later), built by the driver manufacturer. The full list of
the programs in the image and their licenses, with the text of each license, is produced at every build and shown on
the receiver (Menu > System information > Licenses) and in the web interface (the `/licente` page); the sources of
the GPL and LGPL components are published with every version, at https://hdsatelit.com/codul-sursa/.

"Enigma" and "Dreambox" are trademarks of Dream Property GmbH; other product names belong to their owners.
HDSatelit Image is an independent project, not affiliated with Dream Multimedia, with the receiver manufacturer or
with any other image team.

## Building

The image is built with OpenEmbedded, in the OE-Alliance build environment (branch 5.6), on Linux (Ubuntu 24.04 or a
container with it), for the machine `u57` (`MACHINEBUILD=viper4kv20`), with the HDSatelit recipe layer (the
`hdsatelit` distro, the `hdsatelit-image` image, the `enigma2-hdsatelit` recipe that builds this code). The layer is
published with the source of every version and goes first in `BBLAYERS`. In the build folder of the machine, with
`DISTRO=hdsatelit` in `env.source`:

```
source env.source
bitbake hdsatelit-image
```

Result: `tmp/deploy/images/u57/hdsatelit-<version>-viper4kv20-<date>_mmc.zip`, with `kernel.bin`, `rootfs.tar.bz2`
and `imageversion` in `e2/update/`.

## Installing on the receiver

Copy the three files from the archive to a FAT32 USB stick, in the folder `amiko/viper4kv20/`. Start the receiver
in Maintenance Mode and choose the USB update. The receiver has no lock: anyone can build the image from these
sources, with their own changes, and install it the same way.
