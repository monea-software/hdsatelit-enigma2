# HD Satelit 0.6.13 pentru Octagon SF8008 4K UHD și SF8008 MINI 4K

Sursa imaginilor Enigma2 HD Satelit 0.6.13 (alfa, pentru testeri) pentru receptoarele Octagon SF8008 4K UHD și
Octagon SF8008 MINI 4K, făcută de Monea Software pentru HD Satelit. Versiunea 0.6.13 e publicată întâi pentru aceste
două receptoare, ca imagine întreagă: codul versiunii 0.6.12 plus pornirea pe aceste receptoare (programul plăcii
pentru imagine pornit în fundal și așteptat cel mult 60 de secunde, pasul pornirii pe afișaj și pe ecran), citirea
HDMI-CEC fără mesaje în jurnalul nucleului, tunerul combinat DVB-T2 și DVB-C văzut și pentru cablu, primul tuner de
satelit configurat după țara receptorului, răspunsul driverului la comenzile DiSEqC după convenția ioctl, citirile
din `/proc` ale driverului într-un fir separat, asistența de la distanță dintr-o singură pagină și actualizările prin
pachete alese după nume și arhitectură; în stratul de mai jos, driverele Wi-Fi USB (RTL8192EU, RTL8821CU, RTL8822CU,
MT7601U), pornirea fără cablu de rețea fără așteptare și licențele firmware-urilor. Pe Amiko Viper 4K V20, V30 și
V40 rămâne versiunea 0.6.12 (comitul `v0.6.12` din acest depozit); primul Amiko Viper 4K rămâne pe revizia r4
(eticheta `v0.6.11-r4`).

Imaginile gata construite și pașii de instalare de pe stick:

- https://stb.hdsatelit.com/receptoare/octagon-sf8008-4k-uhd/
- https://stb.hdsatelit.com/receptoare/octagon-sf8008-mini-4k/

[English below](#hd-satelit-0613-for-the-octagon-sf8008-4k-uhd-and-sf8008-mini-4k)

## Ce e în depozit

| Dosarul | Ce conține |
|---|---|
| `enigma2/` | codul imaginii: enigma2 și modulele HD Satelit (rețeta `enigma2-hdsatelit`) |
| `meta-local/` | stratul OpenEmbedded HD Satelit folosit la constructiile reviziei, cu regulile celor două receptoare |
| `skin/usr/` | skinul HDSatelit (rețeta `hdsatelit-skin`), același ca la versiunea 0.6.13 |

Sunt fișierele din care s-au construit imaginile 0.6.13 pentru Octagon (eticheta `v0.6.13-octagon`). Arborele git al dosarului
`enigma2/` este `63c10a41f15b11f97901a62673d2a17ab18ef5f6`, același cu cel construit (`git rev-parse HEAD:enigma2`).

## Construirea

Pe Linux, Ubuntu 24.04 (sau un container cu el), cu pachetele de la sfârșitul secțiunii, cu localizarea
`en_US.UTF-8` și cu `/bin/sh` legat la `bash`. Memoria: navigatorul web (WPE WebKit) s-a compilat cu 8 fire în
aproximativ 22 GB. Receptorul, mașina și numele imaginii:

| Receptorul | Mașina (`MACHINE`) | Numele imaginii (`MACHINEBUILD`) |
|---|---|---|
| Octagon SF8008 4K UHD | `sf8008` | `sf8008` |
| Octagon SF8008 MINI 4K | `sf8008m` | `sf8008m` |

1. Mediul de construire OE-Alliance, ramura `5.6`, la comiterea folosită:

   ```
   git clone -b 5.6 https://github.com/oe-alliance/build-enviroment.git
   cd build-enviroment
   git checkout fcb3d042006a66a548dd0227a22130984c80b302
   git submodule update --init --recursive
   ```

   Comiterile submodulelor la construire:

   | Submodulul | Comiterea |
   |---|---|
   | `bitbake` | `5d722b5d65e4eef7befe6376983385421e993f86` |
   | `meta-oe-alliance` | `967608e7b0ba9d8fd917a7cf29f9f3ff749c5dbe` |
   | `meta-oe-alliance/meta-oe/recipes-oe-alliance/enigma2-plugins/e2openplugins` | `2b6f4ea801f5d368b2766e9625cf0e66d32feb31` |
   | `meta-openembedded` | `7e9941ab0f69576542cbfeb6576750c878bdd6ca` |
   | `meta-python2` | `f075bd21099260526c1cee76b7c7524daae50a34` |
   | `meta-qt5.15` | `1c3a6a0a2d89c73a0eaf92e2c396206ff6cb67ff` |
   | `openembedded-core` | `2c134301b55892ecf3c0ae9fa4912bc827579ece` |

2. Stratul HD Satelit în locul lui `meta-local`, apoi dosarul de construire al receptorului ales
   (`builds/hdsatelit/release/<mașina>`):

   ```
   rm -rf meta-local
   cp -a /calea/spre/hdsatelit-enigma2/meta-local meta-local
   make MACHINEBUILD=sf8008 DISTRO=hdsatelit init
   ```

   (`sf8008m` pentru SF8008 MINI 4K.)

3. Sursele locale cerute de rețete: `enigma2-hdsatelit` ia codul din depozitul git `/hds/hdsatelit-image`, ramura
   `main`, iar `hdsatelit-skin` ia skinul din `/hds/skin`:

   ```
   sudo mkdir -p /hds && sudo chown "$USER" /hds
   cp -a /calea/spre/hdsatelit-enigma2/skin/usr /hds/skin
   cp -a /calea/spre/hdsatelit-enigma2/enigma2 /hds/hdsatelit-image
   cd /hds/hdsatelit-image
   git init -b main
   git add -A -f
   GIT_COMMITTER_DATE="2026-10-29 23:58:13 +0200" git commit -m "HD Satelit 0.6.13 (Octagon SF8008 4K UHD, SF8008 MINI 4K)"
   ```

   `-f` adaugă și fișierele pe care `.gitignore` din cod le-ar sări. Data comiterii intră în `/etc/image-version`
   (versiunea arătată pe receptor); cu data de mai sus iese la fel ca în imaginile publicate.

4. Construirea:

   ```
   cd /calea/spre/build-enviroment/builds/hdsatelit/release/sf8008
   source env.source
   bitbake hdsatelit-image
   ```

   Rezultatul: `tmp/deploy/images/sf8008/hdsatelit-0.6.13-sf8008-<data>_mmc.zip` (la celelalte, cu mașina lor).

Componentele fabricanților receptoarelor (driverele și bibliotecile Octagon și Amiko) sunt arhive binare închise. Le
descarcă rețetele OE-Alliance la construire; nu sunt în acest depozit.

Pachetele Ubuntu folosite pentru construire:

```
apt-get install -y python3-html5lib autoconf automake bison bzip2 chrpath cmake coreutils cpio curl cvs debianutils default-jre default-jre-headless diffstat flex g++ gawk gcc gcc-12 gcc-multilib g++-multilib gettext git gzip help2man info iputils-ping java-common libc6-dev libc6-dev-i386 libglib2.0-dev libncurses-dev libperl4-corelibs-perl libproc-processtable-perl libsdl1.2-dev libserf-dev libtool libxml2-utils make ncurses-bin patch perl pkg-config psmisc python3 python3-git python3-jinja2 python3-pexpect python3-pip python3-setuptools quilt socat sshpass subversion tar texi2html texinfo unzip wget xsltproc xterm xz-utils zip zlib1g-dev zstd fakeroot lz4 git-lfs file locales
```

## Licența

Codul din `enigma2/` are licența GNU GPL, versiunea 2 (GPL-2.0-only); textul licenței e în [LICENSE](LICENSE). El
pornește din sursa enigma2 publicată de Dream Multimedia în starea din 14 septembrie 2011, derivată sub GPLv2 așa cum
permite licența originală a acelei versiuni. Detalii în [enigma2/LICENSE](enigma2/LICENSE), textul original în
[enigma2/LICENSE.original-2011](enigma2/LICENSE.original-2011), autorii în [enigma2/AUTHORS](enigma2/AUTHORS) și
[enigma2/CREDITS](enigma2/CREDITS).

Fiecare rețetă din `meta-local/` are licența scrisă în ea (`LICENSE = ...`); programele altora aduse de rețete au
licența lor.
Componentele HD Satelit `hdsatelit-bootlogo`, `hdsatelit-netguard`, `hdsatelit-noduri`, `hdsatelit-skin` și `hdsatelit-watchdog` sunt publicate sub licența GPLv2, ca restul imaginii (hotărârea din
23.10.2026). În rețetele versiunii 0.6.13 scrie încă `LICENSE = "CLOSED"`; se corectează în versiunea următoare.
Tot așa, nota din [enigma2/README.md](enigma2/README.md) după care skinul HDSatelit e „declarat deocamdată închis” nu
mai e valabilă: skinul, din `skin/` și din `enigma2/HDSatelit/`, e sub GPLv2.

„Enigma” și „Dreambox” sunt mărci ale Dream Property GmbH. HD Satelit e un proiect independent, fără legătură cu
Dream Multimedia sau cu fabricanții receptoarelor.

## Contact

contact@hdsatelit.com

---

# HD Satelit 0.6.13 for the Octagon SF8008 4K UHD and SF8008 MINI 4K

Source code of the HD Satelit Enigma2 images 0.6.13 (alpha, for testers) for the Octagon SF8008 4K UHD and the
Octagon SF8008 MINI 4K receivers, made by Monea Software for HD Satelit. Version 0.6.13 is published first for these
two receivers, as a complete image: the code of version 0.6.12 plus the start-up on these receivers (the board's
video program started in the background and waited for at most 60 seconds, the start step on the front display and
on the screen), HDMI-CEC reading without messages in the kernel log, the combined DVB-T2 and DVB-C tuner also seen
for cable, the first satellite tuner set up for the receiver's country, the driver's answer to DiSEqC commands read
by the ioctl convention, the driver's `/proc` reads in a separate thread, remote assistance from a single page and
package updates chosen by name and architecture; in the layer below, the USB Wi-Fi drivers (RTL8192EU, RTL8821CU,
RTL8822CU, MT7601U), the start without a network cable with no waiting and the firmware licences. The Amiko Viper 4K
V20, V30 and V40 stay on version 0.6.12 (commit `v0.6.12` in this repository); the first Amiko Viper 4K stays on
revision r4 (tag `v0.6.11-r4`).

The ready-built images and the steps to install them from a USB stick:

- https://stb.hdsatelit.com/en/receptoare/octagon-sf8008-4k-uhd/
- https://stb.hdsatelit.com/en/receptoare/octagon-sf8008-mini-4k/

## What is in this repository

| Folder | Contents |
|---|---|
| `enigma2/` | the image code: enigma2 and the HD Satelit modules (recipe `enigma2-hdsatelit`) |
| `meta-local/` | the HD Satelit OpenEmbedded layer used for the builds of the revision, with the rules of the two receivers |
| `skin/usr/` | the HDSatelit skin (recipe `hdsatelit-skin`), the same as in version 0.6.13 |

These are the files the 0.6.13 images for the Octagon (tag `v0.6.13-octagon`) were built from. The git tree of the `enigma2/`
folder is `63c10a41f15b11f97901a62673d2a17ab18ef5f6`, the same as the one built (`git rev-parse HEAD:enigma2`).

## Building

On Linux, Ubuntu 24.04 (or a container with it), with the packages listed at the end of this section, the
`en_US.UTF-8` locale and `/bin/sh` linked to `bash`. Memory: the web browser (WPE WebKit) was compiled with 8 threads
in about 22 GB. The receiver, the machine and the image name:

| Receiver | Machine (`MACHINE`) | Image name (`MACHINEBUILD`) |
|---|---|---|
| Octagon SF8008 4K UHD | `sf8008` | `sf8008` |
| Octagon SF8008 MINI 4K | `sf8008m` | `sf8008m` |

1. The OE-Alliance build environment, branch `5.6`, at the commit used:

   ```
   git clone -b 5.6 https://github.com/oe-alliance/build-enviroment.git
   cd build-enviroment
   git checkout fcb3d042006a66a548dd0227a22130984c80b302
   git submodule update --init --recursive
   ```

   The submodule commits at build time:

   | Submodule | Commit |
   |---|---|
   | `bitbake` | `5d722b5d65e4eef7befe6376983385421e993f86` |
   | `meta-oe-alliance` | `967608e7b0ba9d8fd917a7cf29f9f3ff749c5dbe` |
   | `meta-oe-alliance/meta-oe/recipes-oe-alliance/enigma2-plugins/e2openplugins` | `2b6f4ea801f5d368b2766e9625cf0e66d32feb31` |
   | `meta-openembedded` | `7e9941ab0f69576542cbfeb6576750c878bdd6ca` |
   | `meta-python2` | `f075bd21099260526c1cee76b7c7524daae50a34` |
   | `meta-qt5.15` | `1c3a6a0a2d89c73a0eaf92e2c396206ff6cb67ff` |
   | `openembedded-core` | `2c134301b55892ecf3c0ae9fa4912bc827579ece` |

2. The HD Satelit layer in place of `meta-local`, then the build folder of the chosen receiver
   (`builds/hdsatelit/release/<machine>`):

   ```
   rm -rf meta-local
   cp -a /path/to/hdsatelit-enigma2/meta-local meta-local
   make MACHINEBUILD=sf8008 DISTRO=hdsatelit init
   ```

   (`sf8008m` for the SF8008 MINI 4K.)

3. The local sources the recipes need: `enigma2-hdsatelit` takes the code from the git repository
   `/hds/hdsatelit-image`, branch `main`, and `hdsatelit-skin` takes the skin from `/hds/skin`:

   ```
   sudo mkdir -p /hds && sudo chown "$USER" /hds
   cp -a /path/to/hdsatelit-enigma2/skin/usr /hds/skin
   cp -a /path/to/hdsatelit-enigma2/enigma2 /hds/hdsatelit-image
   cd /hds/hdsatelit-image
   git init -b main
   git add -A -f
   GIT_COMMITTER_DATE="2026-10-29 23:58:13 +0200" git commit -m "HD Satelit 0.6.13 (Octagon SF8008 4K UHD, SF8008 MINI 4K)"
   ```

   `-f` also adds the files that the `.gitignore` of the code would skip. The commit date goes into
   `/etc/image-version` (the version shown on the receiver); with the date above it comes out the same as in the
   published images.

4. The build:

   ```
   cd /path/to/build-enviroment/builds/hdsatelit/release/sf8008
   source env.source
   bitbake hdsatelit-image
   ```

   The result: `tmp/deploy/images/sf8008/hdsatelit-0.6.13-sf8008-<date>_mmc.zip` (for the others, with their machine).

The receiver manufacturers' components (the Octagon and Amiko drivers and libraries) are closed binary archives. The
OE-Alliance recipes download them during the build; they are not in this repository.

The Ubuntu packages used for the build:

```
apt-get install -y python3-html5lib autoconf automake bison bzip2 chrpath cmake coreutils cpio curl cvs debianutils default-jre default-jre-headless diffstat flex g++ gawk gcc gcc-12 gcc-multilib g++-multilib gettext git gzip help2man info iputils-ping java-common libc6-dev libc6-dev-i386 libglib2.0-dev libncurses-dev libperl4-corelibs-perl libproc-processtable-perl libsdl1.2-dev libserf-dev libtool libxml2-utils make ncurses-bin patch perl pkg-config psmisc python3 python3-git python3-jinja2 python3-pexpect python3-pip python3-setuptools quilt socat sshpass subversion tar texi2html texinfo unzip wget xsltproc xterm xz-utils zip zlib1g-dev zstd fakeroot lz4 git-lfs file locales
```

## License

The code in `enigma2/` is licensed under the GNU GPL, version 2 (GPL-2.0-only); the license text is in
[LICENSE](LICENSE). It starts from the enigma2 source code published by Dream Multimedia at the state of
14 September 2011, derived under the GPLv2 as the original license of that version allows. Details in
[enigma2/LICENSE](enigma2/LICENSE), the original text in [enigma2/LICENSE.original-2011](enigma2/LICENSE.original-2011),
the authors in [enigma2/AUTHORS](enigma2/AUTHORS) and [enigma2/CREDITS](enigma2/CREDITS).

Each recipe in `meta-local/` states its license (`LICENSE = ...`); the third-party programs brought in by the recipes
keep their own licenses.
The HD Satelit components `hdsatelit-bootlogo`, `hdsatelit-netguard`, `hdsatelit-noduri`, `hdsatelit-skin` and `hdsatelit-watchdog` are published under the GPLv2 license, like the rest of the image
(decision of 23.10.2026). The recipes of version 0.6.13 still say `LICENSE = "CLOSED"`; this is corrected in the
next version. Likewise, the note in [enigma2/README.md](enigma2/README.md) that the HDSatelit skin is "declared closed
for now" no longer applies: the skin, in `skin/` and in `enigma2/HDSatelit/`, is under the GPLv2.

"Enigma" and "Dreambox" are trademarks of Dream Property GmbH. HD Satelit is an independent project, not affiliated
with Dream Multimedia or with the receiver manufacturers.

## Contact

contact@hdsatelit.com
