# HD Satelit 0.7.4: actualizarea din meniu din 14.11.2026

Actualizarea software din meniu publicată pe 14.11.2026 aduce pachetul `enigma2-hdsatelit` 0.7.4+git0+c56b96f3f5-r0,
împreună cu pachetele lui de traduceri (`enigma2-hdsatelit-po-*`). Pachetul e făcut din `enigma2/` de aici: comiterea
c56b96f3f5c054b332ffa6098ec3c991d21320a5 a codului imaginii, fără dosarele `audit/` și `pluginuri-feed/`, care nu intră în
imagine. Arborele git al dosarului `enigma2/` este `b6d35d2bc58c82b02f71f449006e1d42d8e34e6a` (`git rev-parse HEAD:enigma2`).

Pachetul s-a construit în construcția imaginii 0.7.4 a fiecărei mașini (gbmv200, gb7252, hd51, sf8008, sf8008m, u57,
u571, ustym4kpro, viper4k, vuduo4k, vuduo4klite, vuduo4kse, vusolo4k, vusolose, vuultimo4k, vuuno4kse, vuzero4k), cu
rețeta `meta-local/recipes-local/enigma2-hdsatelit` de aici (aceeași pe toate mașinile), `SRCREV` = comiterea de mai sus
și `PV = "0.7.4+git${SRCPV}"`. Față de eticheta `v0.7.4` se schimbă numai `enigma2/` și acest fișier: `meta-local/`,
`skin/`, `LICENSE` și `README.md` sunt cele ale versiunii 0.7.4. Celelalte pachete sunt cele ale imaginii și ale
actualizărilor de dinainte.

Numărul actualizării depinde de imaginea de pe receptor: imaginea 0.7.0 o primește ca actualizarea 9, imaginea 0.7.1 ca
actualizarea 8, imaginea 0.7.3 ca actualizarea 6, imaginea 0.7.4 ca actualizarea 8. Pe toate, pachetul e făcut din
aceeași sursă.

# HD Satelit 0.7.4: the menu update of 14.11.2026

The software update from the menu published on 14.11.2026 brings the `enigma2-hdsatelit` package
0.7.4+git0+c56b96f3f5-r0, together with its translation packages (`enigma2-hdsatelit-po-*`). The package is built from
`enigma2/` here: commit c56b96f3f5c054b332ffa6098ec3c991d21320a5 of the image code, without the `audit/` and
`pluginuri-feed/` folders, which do not go into the image. The git tree of the `enigma2/` folder is
`b6d35d2bc58c82b02f71f449006e1d42d8e34e6a` (`git rev-parse HEAD:enigma2`).

The package was built in the 0.7.4 image build of each machine (gbmv200, gb7252, hd51, sf8008, sf8008m, u57, u571,
ustym4kpro, viper4k, vuduo4k, vuduo4klite, vuduo4kse, vusolo4k, vusolose, vuultimo4k, vuuno4kse, vuzero4k), with the
`meta-local/recipes-local/enigma2-hdsatelit` recipe here (the same on all machines), `SRCREV` = the commit above and
`PV = "0.7.4+git${SRCPV}"`. Compared with the `v0.7.4` tag only `enigma2/` and this file change: `meta-local/`,
`skin/`, `LICENSE` and `README.md` are those of version 0.7.4. The other packages are those of the image and of the
earlier updates.

The update number depends on the image on the receiver: the 0.7.0 image gets it as update 9, the 0.7.1 image as update 8,
the 0.7.3 image as update 6, the 0.7.4 image as update 8. On all of them the package is built from the same source.
