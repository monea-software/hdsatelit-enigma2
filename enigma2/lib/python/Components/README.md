# lib/python/Components

The non-visual part of the enigma2 interface: settings (`config.py`), the tuner and satellite models
(`NimManager.py`), the lists, sources, converters and renderers that the screens and the skins use. The folder
started as the 2011 enigma2 Components folder; `FILES.md` at the root says which files are still unchanged.

## Subfolders

- `Sources/`, `Converter/`, `Renderer/`: the skin building blocks (`<widget source=... render=...>`,
  `<convert type=...>`). Many of the added ones exist so that skins written for OE-Alliance images find every
  component they ask for; each such file names its source in its header.
- `Addons/`: the skin addons of the OE-Alliance standard (`<widget addon=...>`).
- `HdsSubtitrariInternet/`: search and download of subtitles for the film that is playing, from services with an
  official API (`surse/`: OpenSubtitles, SubDL, subs.ro), the same for the TV screen and the web page (`lucru.py`).

## The Hds modules

About 330 `Hds*.py` files hold the logic of the HD Satelit features (a few of them are taken from other projects,
for example `HdsChromeOS.py`; `FILES.md` gives the origin of every file). The rule they follow: one module holds the
logic and the data, without drawing anything, and both the screen on the TV (`Screens/`) and the page of the web
interface (`Plugins/Extensions/HdsWebControl/*_web.py`) call it, so the TV and the web always do the same thing.
The first lines of every file say what it does and who calls it. The main groups:

- Tuners and scanning: `HdsLnb.py`, `HdsLnbAplicare.py` (LNB setup), `HdsUnicableConfig.py`, `HdsFbc.py`,
  `HdsMotorComenzi.py`, `HdsMotorPozitie.py`, `HdsMotorTuner.py` (DiSEqC 1.2 dish motor), `HdsLocul.py` (location of
  the dish for USALS), `HdsCautareOarba.py` (blind scan), `HdsGasireSemnal.py` (signal finder), `HdsOperatoriSatelit.py`.
- Channel list and channel data: `HdsBazaCanale.py` (one store of the technical values per channel),
  `HdsCulegereCanale.py` (fills it from the channel that is playing), `HdsListaSetari.py` (look of the list),
  `HdsEditorCanale.py`, `HdsEditorCanaleDate.py`, `HdsEditorCanaleUnelte.py` (channel editor), `HdsIndexCanale.py`.
- Internet TV: `HdsIptvSurse.py` (the sources of the user), `HdsIptvClient.py` (M3U, Xtream, Stalker),
  `HdsIptvLucru.py` (loads them in the background), `HdsIptvRedare.py`, `HdsIptvEpg.py`, `HdsVod.py` (films and series),
  `HdsDvbI*.py` (DVB-I lists).
- Programme guide, teletext, subtitles: `HdsEpgSalvare.py`, `HdsGhidInternet.py`, `HdsTeletext.py`,
  `HdsSubtitrariAspect.py`, `HdsSubtitrariFilm.py`, `HdsOcrSubtitrari.py` (text read from DVB picture subtitles),
  `HdsTraducereSubtitrari.py`.
- Conditional access: `HdsModuleAcces.py` (installed access modules), `HdsEcm.py`, `HdsPasiDecriptare.py`,
  `HdsSoftCsa.py`, `HdsStreamRelay.py`.
- Sound, picture and display: `HdsSunet.py`, `HdsSetariSunet.py`, `HdsEgalizator.py`, `HdsCalitateImagine.py`,
  `HdsAfisaj.py` (front display), `HdsAfisajColor.py` (colour LCD), `HdsRadioDate.py` (radio screen).
- Network and storage: `HdsRetea.py`, `HdsWlan.py`, `HdsStareRetea.py`, `HdsVpn.py`, `HdsStocareRetea.py`,
  `HdsDiscuri.py`, `HdsMontareDiscuri.py`, `HdsTransmisie.py` (TV in the browser).
- Software and packages: `HdsActualizari.py` (updates through opkg), `HdsSemnatura.py` (signed feed), `HdsPachete.py`
  and `HdsExtensiiLucru.py` (extension manager), `HdsPluginuriExterne.py`, `HdsModuleLipsa.py`, `HdsCopieSetari.py`,
  `HdsCopieImagine.py`, `HdsImagineOnline.py`.
- Compatibility with plugins and skins written for other images: `HdsEnigmaCompat.py`, `HdsBoxInfoModele.py`,
  `HdsPython2Traducere.py`, `HdsTemaExterna.py`, `HdsNumeStandard.py`, `HdsPluginExtern.py`.
- Remote assistance: `HdsAsistenta.py`, `HdsAsistentaCatalog.py` (the fixed list of operations),
  `HdsAsistentaBroker.py` (runs one operation), `HdsAsistentaControl.py`.
- Logs and safety nets: `HdsJurnal.py` (same log format as `lib/base/hdsjurnal.h`), `HdsJurnale.py`, `HdsDiagnostic.py`,
  `HdsModSigur.py` (safe mode), `HdsPaznic.py` (watchdog), `HdsPazaModel.py` (runs only on its own receiver model).

## Where the tests are

The Hds modules avoid importing enigma2 at load time where they can, so that they can be tested on a PC with a
fake `enigma` module. Those tests are kept with the build tools of the image, not in this repository; the folder
`tests/` at the root holds only the enigma2 timer tests of 2011, adapted to this tree.
