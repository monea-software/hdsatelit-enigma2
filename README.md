# HD Satelit 0.7.0 beta pentru Amiko Viper 4K V20

Sursa imaginii Enigma2 HD Satelit 0.7.0 (beta) pentru receptorul de satelit Amiko Viper 4K V20, făcută de Monea
Software pentru HD Satelit. Interfața e enigma2 pe Python 3, cu skinul HDSatelit și interfața web proprie.

Aceeași sursă este și a celorlalte modele cu imaginea 0.7.0: Amiko Viper 4K V10, V30 și V40, Octagon SF8008 4K UHD, Octagon SF8008 MINI 4K și Uclan Ustym 4K PRO. Rețetele lor sunt în `meta-local/`.

Imaginea gata construită și pașii de instalare de pe stick: https://stb.hdsatelit.com/receptoare/amiko-viper-4k-v20/

[English below](#hd-satelit-070-beta-for-the-amiko-viper-4k-v20)

## Ce e în depozit

| Dosarul | Ce conține |
|---|---|
| `enigma2/` | codul imaginii: enigma2 și modulele HD Satelit (rețeta `enigma2-hdsatelit`) |
| `meta-local/` | stratul OpenEmbedded HD Satelit: distribuția `hdsatelit`, imaginea `hdsatelit-image` și celelalte rețete |
| `skin/usr/` | skinul HDSatelit (rețeta `hdsatelit-skin`) |

Sunt fișierele din care s-a construit versiunea 0.7.0. Arborele git al dosarului `enigma2/` este
`5bd1917f4395068b09e57a5b2d984db23a74bb55`, același cu cel construit (`git rev-parse HEAD:enigma2`). Depozitul are câte un comit pe versiune.

## Construirea

Pe Linux, Ubuntu 24.04 (sau un container cu el), cu pachetele de la sfârșitul secțiunii, cu localizarea
`en_US.UTF-8` și cu `/bin/sh` legat la `bash`. Receptorul: mașina `u57`, numele imaginii `viper4kv20`. Memoria:
navigatorul web (WPE WebKit) s-a compilat cu 8 fire în aproximativ 22 GB.

1. Mediul de construire OE-Alliance, ramura `6.0`, la comiterea folosită:

   ```
   git clone -b 6.0 https://github.com/oe-alliance/build-enviroment.git
   cd build-enviroment
   git checkout 1535ababccf743f9936117cee074ce1863fc829f
   git submodule update --init --recursive
   ```

   Comiterile submodulelor la construire:

   | Submodulul | Comiterea |
   |---|---|
   | `bitbake` | `1763256342ae4d7f8028e8222400c6fc8c24d4a3` |
   | `meta-oe-alliance` | `87fb81188909919291203c000561328eff2468ef` |
   | `meta-openembedded` | `533d0a63ac2a38e77746e32458e09461f12737b6` |
   | `meta-qt5.15` | `1da7e2dd0b88ad95e4e3bab84d765d4f7efdb6e9` |
   | `openembedded-core` | `ae5cafacec8e99c5a27fa5b3b378eefc595910ef` |

2. Stratul HD Satelit în locul lui `meta-local`, apoi dosarul de construire (`builds/hdsatelit/release/u57`):

   ```
   rm -rf meta-local
   cp -a /calea/spre/hdsatelit-enigma2/meta-local meta-local
   make MACHINEBUILD=viper4kv20 DISTRO=hdsatelit init
   ```

3. Sursele locale cerute de rețete: `enigma2-hdsatelit` ia codul din depozitul git `/hds/hdsatelit-image`, ramura
   `main`, iar `hdsatelit-skin` ia skinul din `/hds/skin`:

   ```
   sudo mkdir -p /hds && sudo chown "$USER" /hds
   cp -a /calea/spre/hdsatelit-enigma2/skin/usr /hds/skin
   cp -a /calea/spre/hdsatelit-enigma2/enigma2 /hds/hdsatelit-image
   cd /hds/hdsatelit-image
   git init -b main
   git add -A -f
   GIT_COMMITTER_DATE="2026-11-04 18:45:17 +0200" git commit -m "HD Satelit 0.7.0"
   ```

   `-f` adaugă și fișierele pe care `.gitignore` din cod le-ar sări. Data comiterii intră în `/etc/image-version`
   (versiunea arătată pe receptor); cu data de mai sus iese la fel ca în imaginea publicată.

4. Construirea:

   ```
   cd /calea/spre/build-enviroment/builds/hdsatelit/release/u57
   source env.source
   bitbake hdsatelit-image
   ```

   Rezultatul: `tmp/deploy/images/u57/hdsatelit-0.7.0-viper4kv20-<data>_mmc.zip`.

Componentele fabricantului receptorului (driverele și bibliotecile Dinobot) sunt arhive binare închise. Le descarcă
rețetele OE-Alliance la construire; nu sunt în acest depozit.

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
23.10.2026). În rețetele versiunii 0.7.0 scrie încă `LICENSE = "CLOSED"`; se corectează în versiunea următoare.
Tot așa, nota din [enigma2/README.md](enigma2/README.md) după care skinul HDSatelit e „declarat deocamdată închis” nu
mai e valabilă: skinul, din `skin/` și din `enigma2/HDSatelit/`, e sub GPLv2.

„Enigma” și „Dreambox” sunt mărci ale Dream Property GmbH. HD Satelit e un proiect independent, fără legătură cu
Dream Multimedia sau cu fabricantul receptorului.

## Contact

contact@hdsatelit.com

---

# HD Satelit 0.7.0 beta for the Amiko Viper 4K V20

Source code of the HD Satelit Enigma2 image 0.7.0 (beta) for the Amiko Viper 4K V20 satellite receiver, made by
Monea Software for HD Satelit. The user interface is enigma2 on Python 3, with the HDSatelit skin and its own web
interface.

The same source covers the other models with the 0.7.0 image: Amiko Viper 4K V10, V30 and V40, Octagon SF8008 4K UHD, Octagon SF8008 MINI 4K and Uclan Ustym 4K PRO. Their recipes are in `meta-local/`.

The ready-built image and the steps to install it from a USB stick:
https://stb.hdsatelit.com/receptoare/amiko-viper-4k-v20/

## What is in this repository

| Folder | Contents |
|---|---|
| `enigma2/` | the image code: enigma2 and the HD Satelit modules (recipe `enigma2-hdsatelit`) |
| `meta-local/` | the HD Satelit OpenEmbedded layer: distro `hdsatelit`, image `hdsatelit-image` and the other recipes |
| `skin/usr/` | the HDSatelit skin (recipe `hdsatelit-skin`) |

These are the files version 0.7.0 was built from. The git tree of the `enigma2/` folder is `5bd1917f4395068b09e57a5b2d984db23a74bb55`,
the same as the one that was built (`git rev-parse HEAD:enigma2`). The repository has one commit per version.

## Building

On Linux, Ubuntu 24.04 (or a container running it), with the packages listed at the end of this section, the
`en_US.UTF-8` locale and `/bin/sh` linked to `bash`. The receiver: machine `u57`, image name `viper4kv20`. Memory:
the web browser (WPE WebKit) was compiled with 8 threads in about 22 GB.

1. The OE-Alliance build environment, branch `6.0`, at the commit that was used:

   ```
   git clone -b 6.0 https://github.com/oe-alliance/build-enviroment.git
   cd build-enviroment
   git checkout 1535ababccf743f9936117cee074ce1863fc829f
   git submodule update --init --recursive
   ```

   The submodule commits used for the build:

   | Submodule | Commit |
   |---|---|
   | `bitbake` | `1763256342ae4d7f8028e8222400c6fc8c24d4a3` |
   | `meta-oe-alliance` | `87fb81188909919291203c000561328eff2468ef` |
   | `meta-openembedded` | `533d0a63ac2a38e77746e32458e09461f12737b6` |
   | `meta-qt5.15` | `1da7e2dd0b88ad95e4e3bab84d765d4f7efdb6e9` |
   | `openembedded-core` | `ae5cafacec8e99c5a27fa5b3b378eefc595910ef` |

2. The HD Satelit layer in place of `meta-local`, then the build folder (`builds/hdsatelit/release/u57`):

   ```
   rm -rf meta-local
   cp -a /path/to/hdsatelit-enigma2/meta-local meta-local
   make MACHINEBUILD=viper4kv20 DISTRO=hdsatelit init
   ```

3. The local sources the recipes expect: `enigma2-hdsatelit` takes the code from the git repository
   `/hds/hdsatelit-image`, branch `main`, and `hdsatelit-skin` takes the skin from `/hds/skin`:

   ```
   sudo mkdir -p /hds && sudo chown "$USER" /hds
   cp -a /path/to/hdsatelit-enigma2/skin/usr /hds/skin
   cp -a /path/to/hdsatelit-enigma2/enigma2 /hds/hdsatelit-image
   cd /hds/hdsatelit-image
   git init -b main
   git add -A -f
   GIT_COMMITTER_DATE="2026-11-04 18:45:17 +0200" git commit -m "HD Satelit 0.7.0"
   ```

   `-f` also adds the files that the code's `.gitignore` would skip. The commit date goes into `/etc/image-version`
   (the version shown on the receiver); with the date above it comes out the same as in the published image.

4. The build:

   ```
   cd /path/to/build-enviroment/builds/hdsatelit/release/u57
   source env.source
   bitbake hdsatelit-image
   ```

   The result: `tmp/deploy/images/u57/hdsatelit-0.7.0-viper4kv20-<date>_mmc.zip`.

The receiver manufacturer's components (the Dinobot drivers and libraries) are closed binary archives. The OE-Alliance
recipes download them during the build; they are not in this repository.

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
(decision of 23.10.2026). The recipes of version 0.7.0 still say `LICENSE = "CLOSED"`; this is corrected in the
next version. Likewise, the note in [enigma2/README.md](enigma2/README.md) that the HDSatelit skin is "declared closed
for now" no longer applies: the skin, in `skin/` and in `enigma2/HDSatelit/`, is under the GPLv2.

"Enigma" and "Dreambox" are trademarks of Dream Property GmbH. HD Satelit is an independent project, not affiliated
with Dream Multimedia or with the receiver manufacturer.

## Contact

contact@hdsatelit.com
