# lib/python/Screens

The screens of the interface on the TV: every window the user sees is a `Screen` class here (or in a plugin), with
its skin in `data/skin_default.xml`, in the HDSatelit theme (`HDSatelit/skin.xml`) or in the skin of another theme.
The folder started as the 2011 enigma2 Screens folder; `FILES.md` at the root says what is unchanged.

## The 2011 screens we changed most

- `ChannelSelection.py`: the channel list (groups, search row, bouquet editing, number keys, the context menu).
- `InfoBar.py`, `InfoBarGenerics.py`: the channel bar while watching, timeshift, recordings, the coloured keys.
- `Menu.py`: the main menu, as a list or as tiles (the tile logic is in `Components/HdsDale.py`), with the search
  row at the top (`HdsCautaSetari.py`).
- `Ci.py`: the CI and CI+ module menus. `TimerEdit.py`, `VirtualKeyBoard.py`, `MessageBox.py`: timers, the
  on-screen keyboard, the message box used everywhere.

## Screens added by HD Satelit

About 95 `Hds*.py` files, plus screens added under their usual enigma2 names (`Information.py`, `SecondInfoBar.py`,
`ScreenSaver.py`), some of them only so that plugins written for other images find what they import (`Timers.py`,
`Toast.py`). Most `Hds*.py` screens only draw: more than half of them have a module of the same name in
`Components/` that holds the logic and is used by the web interface too (for example `Screens/HdsCopieSetari.py`
and `Components/HdsCopieSetari.py`). Main ones:

- Scanning: `ScanerSatelit.py`, `ScanerCablu.py`, `ScanerTerestru.py`, `ScanerMaiMultiSateliti.py`,
  `ScanerOarba.py` (blind scan), `HdsCulegereTotala.py` (detailed scan, channel by channel), `HdsListeInternet.py`
  and `HdsListeImplicite.py` (ready-made channel lists), `HdsImportSetari.py` (import from another image).
- Channels: `HdsEditorCanale.py` with `HdsEditorCanaleLogica.py`, `HdsEditorCanaleLegatura.py` and
  `HdsEditorCanaleUnelte.py` (channel editor), `HdsCautareCanale.py` (search in the list), `HdsIstoricCanale.py`,
  `HdsMozaic.py` (all channels of the transponder on one screen), `HdsPiconuri.py` (channel logos).
- Internet TV and media: `HdsIptvIncarcare.py`, `HdsIptvArhiva.py`, `HdsFilmeSeriale.py`, `HdsDvbI.py`,
  `HdsEcranRadio.py`, `HdsTeletext.py`, `HdsSubtitrariAspect.py`, `HdsSubtitrariFilm.py`, `HdsGhidInternet.py`.
- Settings: `HdsCalitateImagine.py`, `HdsEgalizator.py`, `HdsAfisaj.py`, `HdsTemaInterfata.py`,
  `HdsFontInterfata.py`, `HdsRezolutieTv.py`, `HdsVpn.py`, `HdsTransmisie.py`, `HdsLocInregistrari.py`.
- Software: `HdsActualizari.py`, `HdsSoftwareUpdate.py`, `HdsExtensii.py` (extension manager), `HdsCopieSetari.py`,
  `HdsCopieImagine.py`, `HdsImagineOnline.py`.
- Help and diagnosis: `HdsAjutor.py`, `HdsAsistenta.py` (remote assistance), `HdsModSigur.py`, `HdsPazaModel.py`,
  `HdsPaznic.py`, `HdsJurnalVersiuni.py` ("What is new"), `HdsStartWizard.py` (first start).

The menu entries that open these screens are in `data/menu.xml`; the settings rows are in `data/setup.xml`.
