# HDSatelit Image

Imagine Linux pentru receptoare de satelit Enigma2, făcută de Monea Software pentru HD Satelit (hdsatelit.com).
Interfața e enigma2 pe Python 3, cu tema HDSatelit și interfața web proprie. Meniurile sunt traduse în 31 de limbi;
câteva traduceri sunt încă incomplete.

Stadiu: versiune beta publică (0.8.0). Imaginile și actualizările: https://stb.hdsatelit.com/ și feedul imaginii, din
meniul receptorului.

## Receptoarele

Starea din 24.11.2026; lista la zi, cu pagina fiecărui receptor: https://stb.hdsatelit.com/receptoare/

| Receptorul | Mașina OpenEmbedded | Stadiul |
|---|---|---|
| Amiko Viper 4K V20, V30 | `u57` | beta |
| Amiko Viper 4K V40 | `u571` | beta |
| Amiko Viper 4K V10 | `viper4k` | beta |
| AX HD51 | `hd51` | beta |
| GigaBlue UHD TRIO 4K | `gbmv200` | beta |
| Octagon SF8008 4K UHD | `sf8008` | beta |
| Uclan Ustym 4K PRO | `ustym4kpro` | beta |
| Vu+ Duo4K, Duo4K SE, Duo4K Lite | `vuduo4k`, `vuduo4kse`, `vuduo4klite` | beta |
| Vu+ Solo4K, Ultimo4K, Uno4K SE, Zero4K | `vusolo4k`, `vuultimo4k`, `vuuno4kse`, `vuzero4k` | beta |
| Vu+ Solo SE | `vusolose` | beta |
| Dreambox DM900, DM920 | `dm900`, `dm920` | la beta testeri |
| GigaBlue UHD QUAD 4K PRO | `gb7252` | la beta testeri |
| Mut@nt HD51 | `hd51` | la beta testeri |
| Octagon SF8008 MINI 4K | `sf8008m` | la beta testeri |
| Vu+ Duo², Uno4K | `vuduo2`, `vuuno4k` | la beta testeri |

- Procesoarele: ARM (HiSilicon și Broadcom) și, la Vu+ Duo² și Solo SE, MIPS (Broadcom).
- Fiecare imagine se scrie și pornește numai pe receptorul pentru care e făcută; pe alt model arată numai un mesaj.

## Licența

Codul din acest depozit (enigma2 și modulele HDSatelit) are licența GNU GPL, versiunea 2 (GPL-2.0-only).
Excepție, până la hotărârea licenței lui: tema HDSatelit (dosarul `HDSatelit/`, pachetul `hdsatelit-skin`), declarat
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
- componentele fabricanților receptoarelor: driverele (HiSilicon de la Dinobot, Broadcom de la fabricanții
  receptoarelor Broadcom), bibliotecile lor și programele lor de sunet și imagine. Sunt arhive binare, descărcate la
  construire de rețetele OE-Alliance de pe serverele lor de surse. Sunt închise: nu sunt în acest depozit și nu avem
  sursa lor. Decodoarele de sunet AC3, E-AC3, DTS și TrueHD ale driverului HiSilicon conțin FFmpeg 3.3.2 (LGPL 2.1
  sau mai nouă), construit de fabricantul driverului.

Lista completă a programelor din imagine și a licențelor lor, cu textul fiecărei licențe, se face la fiecare
construire și se vede pe receptor (Meniu > Informații sistem > Licențe) și în interfața web (pagina `/licente`).
Sursele componentelor GPL și LGPL se publică împreună cu fiecare versiune, la https://hdsatelit.com/codul-sursa/.

„Enigma” și „Dreambox” sunt mărci ale Dream Property GmbH; celelalte nume de produse aparțin deținătorilor lor.
HDSatelit Image e un proiect independent, fără legătură cu Dream Multimedia, cu fabricantul receptorului sau cu alte
echipe de imagini.

## Construirea

Imaginea se construiește cu OpenEmbedded, în mediul de construire OE-Alliance (ramura 5.6), pe Linux (Ubuntu 24.04
sau un container cu el), pentru mașina receptorului din tabelul de mai sus (de pildă `u57` cu
`MACHINEBUILD=viper4kv20`), cu stratul rețetelor HDSatelit (distribuția `hdsatelit`, imaginea `hdsatelit-image`,
rețeta `enigma2-hdsatelit` care construiește acest cod). Stratul se publică împreună cu sursa fiecărei versiuni și se
pune primul în `BBLAYERS`. În dosarul de construire al mașinii, cu `DISTRO=hdsatelit` în `env.source`:

```
source env.source
bitbake hdsatelit-image
```

Rezultatul, pentru Amiko Viper 4K V20: `tmp/deploy/images/u57/hdsatelit-<versiunea>-viper4kv20-<data>_mmc.zip`, cu
`kernel.bin`, `rootfs.tar.bz2` și `imageversion` în dosarul `e2/update/`. Celelalte mașini dau arhiva lor, în
dosarul mașinii.

## Instalarea pe receptor

Pașii diferă de la un receptor la altul și sunt pe pagina lui (https://stb.hdsatelit.com/receptoare/). De pildă, pe
Amiko Viper 4K V20 cele trei fișiere din arhivă se copiază pe un stick USB formatat FAT32, în dosarul
`amiko/viper4kv20/`, receptorul se pornește în modul de întreținere (Maintenance Mode) și se alege actualizarea de pe
USB. Imaginea nu blochează receptorul: oricine poate construi imaginea din aceste surse, cu schimbările lui, și o poate
instala la fel.

## De unde începi să citești codul

- [FILES.md](FILES.md): fiecare fișier al acestui arbore după origine: neschimbat față de baza enigma2 din 2011,
  schimbat, adus din alte proiecte (cu sursa fiecăruia), adăugat de HD Satelit. Se reface cu
  `python3 tools/file_origins.py` înaintea fiecărei versiuni.
- Notele despre dosarele principale: [lib/python/Components](lib/python/Components/README.md) (logica, cu modulele
  `Hds*.py`), [lib/python/Screens](lib/python/Screens/README.md) (ecranele de pe televizor),
  [lib/python/Plugins](lib/python/Plugins/README.md), [interfața web](lib/python/Plugins/Extensions/HdsWebControl/README.md),
  [lib/dvb](lib/dvb/README.md) și [lib/service](lib/service/README.md) (miezul C++),
  [HDSatelit](doc/modules/HDSatelit.md) (resursele temei), [pluginuri-feed](pluginuri-feed/README.md) (pluginurile din
  feed), [tools](tools/README.md) și [audit](audit/README.md).
- O funcție are de obicei trei părți cu același nume: logica în `lib/python/Components/Hds<Nume>.py`, ecranul în
  `lib/python/Screens/Hds<Nume>.py` și pagina web în `lib/python/Plugins/Extensions/HdsWebControl/`. Intrările din
  meniu sunt în `data/menu.xml`, rândurile de setări în `data/setup.xml`.

---

# HDSatelit Image (English)

Linux image for Enigma2 satellite receivers, made by Monea Software for HD Satelit (hdsatelit.com). The user
interface is enigma2 on Python 3, with the HDSatelit theme and its own web interface. The menus are translated into
31 languages; a few translations are still incomplete.

Status: public beta (0.8.0). Images and updates: https://stb.hdsatelit.com/ and the image feed, from the receiver menu.

## Receivers

State of 24 November 2026; the current list, with the page of each receiver: https://stb.hdsatelit.com/receptoare/

| Receiver | OpenEmbedded machine | Status |
|---|---|---|
| Amiko Viper 4K V20, V30 | `u57` | beta |
| Amiko Viper 4K V40 | `u571` | beta |
| Amiko Viper 4K V10 | `viper4k` | beta |
| AX HD51 | `hd51` | beta |
| GigaBlue UHD TRIO 4K | `gbmv200` | beta |
| Octagon SF8008 4K UHD | `sf8008` | beta |
| Uclan Ustym 4K PRO | `ustym4kpro` | beta |
| Vu+ Duo4K, Duo4K SE, Duo4K Lite | `vuduo4k`, `vuduo4kse`, `vuduo4klite` | beta |
| Vu+ Solo4K, Ultimo4K, Uno4K SE, Zero4K | `vusolo4k`, `vuultimo4k`, `vuuno4kse`, `vuzero4k` | beta |
| Vu+ Solo SE | `vusolose` | beta |
| Dreambox DM900, DM920 | `dm900`, `dm920` | with beta testers |
| GigaBlue UHD QUAD 4K PRO | `gb7252` | with beta testers |
| Mut@nt HD51 | `hd51` | with beta testers |
| Octagon SF8008 MINI 4K | `sf8008m` | with beta testers |
| Vu+ Duo², Uno4K | `vuduo2`, `vuuno4k` | with beta testers |

- Processors: ARM (HiSilicon and Broadcom) and, on the Vu+ Duo² and Solo SE, MIPS (Broadcom).
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
packages (Linux kernel, BusyBox, glibc, Python, GStreamer and others), and the components of the receiver
manufacturers (the drivers: HiSilicon from Dinobot, Broadcom from the makers of the Broadcom receivers; their
libraries and their audio and video programs), binary archives downloaded at build time by the OE-Alliance recipes
from their source servers. These are closed: they are not in this repository and their source is not available to
us. The AC3, E-AC3, DTS and TrueHD audio decoders of the HiSilicon driver contain FFmpeg 3.3.2 (LGPL 2.1 or later), built by the driver manufacturer. The full list of
the programs in the image and their licenses, with the text of each license, is produced at every build and shown on
the receiver (Menu > System information > Licenses) and in the web interface (the `/licente` page); the sources of
the GPL and LGPL components are published with every version, at https://hdsatelit.com/codul-sursa/.

"Enigma" and "Dreambox" are trademarks of Dream Property GmbH; other product names belong to their owners.
HDSatelit Image is an independent project, not affiliated with Dream Multimedia, with the receiver manufacturer or
with any other image team.

## Building

The image is built with OpenEmbedded, in the OE-Alliance build environment (branch 5.6), on Linux (Ubuntu 24.04 or a
container with it), for the machine of the receiver in the table above (for example `u57` with
`MACHINEBUILD=viper4kv20`), with the HDSatelit recipe layer (the
`hdsatelit` distro, the `hdsatelit-image` image, the `enigma2-hdsatelit` recipe that builds this code). The layer is
published with the source of every version and goes first in `BBLAYERS`. In the build folder of the machine, with
`DISTRO=hdsatelit` in `env.source`:

```
source env.source
bitbake hdsatelit-image
```

Result, for the Amiko Viper 4K V20: `tmp/deploy/images/u57/hdsatelit-<version>-viper4kv20-<date>_mmc.zip`, with
`kernel.bin`, `rootfs.tar.bz2` and `imageversion` in `e2/update/`. The other machines give their own archive, in the
folder of the machine.

## Installing on the receiver

The steps differ from one receiver to another and are on its page (https://stb.hdsatelit.com/receptoare/). For
example, on the Amiko Viper 4K V20 copy the three files from the archive to a FAT32 USB stick, in the folder
`amiko/viper4kv20/`, start the receiver in Maintenance Mode and choose the USB update. The image does not lock the
receiver: anyone can build the image from these sources, with their own changes, and install it the same way.

## Where to start reading the code

- [FILES.md](FILES.md): every file of this tree by origin: unchanged from the 2011 enigma2 base, modified, added
  from other projects (with the source of each), added by HD Satelit. It is regenerated with
  `python3 tools/file_origins.py` before every version tag.
- Notes on the main folders: [lib/python/Components](lib/python/Components/README.md) (the logic, with the
  `Hds*.py` modules), [lib/python/Screens](lib/python/Screens/README.md) (the screens on the TV),
  [lib/python/Plugins](lib/python/Plugins/README.md), [the web interface](lib/python/Plugins/Extensions/HdsWebControl/README.md),
  [lib/dvb](lib/dvb/README.md) and [lib/service](lib/service/README.md) (the C++ core),
  [HDSatelit](doc/modules/HDSatelit.md) (the theme resources), [pluginuri-feed](pluginuri-feed/README.md) (the feed
  plugins), [tools](tools/README.md) and [audit](audit/README.md).
- A feature usually has three parts with the same name: the logic in `lib/python/Components/Hds<Name>.py`, the
  screen in `lib/python/Screens/Hds<Name>.py` and the web page in `lib/python/Plugins/Extensions/HdsWebControl/`.
  The menu entries are in `data/menu.xml`, the settings rows in `data/setup.xml`.
