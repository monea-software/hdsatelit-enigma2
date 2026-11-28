# lib/python/Plugins

The plugins that come with the image. `Plugin.py` is the plugin descriptor and `../Components/PluginComponent.py`
loads them; plugins installed later by the user from the feeds land in the same two folders on the receiver.
Most 2011 plugins were removed (see `doc/REMOVED-FILES` and `FILES.md`); the ones left are listed below.

## Extensions

- `HdsWebControl/`: the web interface of the receiver (a Twisted web server inside the enigma2 process). It has
  its own notes: `HdsWebControl/README.md`.
- `HdsNavigator/`: the web browser on the TV. `plugin.py` registers it, `lansator.py` starts and stops the browser
  program (`/usr/bin/hds-navigator`, WPE WebKit, from the `hds-navigator` package) and hands it the screen and the
  remote control, `ecrane.py` holds its screens, `setari.py` its settings and bookmarks, `campuri.py` sends text typed
  on a phone or computer to the active text field on the TV, `intrare_cam.py` opens the web page of the access module.
- `HdsImportSetari/`: "Import channels and settings" from the Scan menu: channels, bouquets and settings taken from a
  backup of another image (the logic is in `Components/HdsImportSurse.py`).
- `HdsCutListEditor/`: cut marks editor for the recording that is playing.
- `MediaPlayer/`, `MediaScanner/`, `PicturePlayer/`: the 2011 media plugins, changed for the HDSatelit file browsers
  (`Components/HdsNavigator.py`, `Components/HdsMedia.py`).

## SystemPlugins

- `HdsDvbI/`: DVB-I, channel lists delivered over the internet (the logic is in `Components/HdsDvbI*.py`, the screens
  in `Screens/HdsDvbI.py`).
- `Hotplug/`: follows the kernel device events and keeps the partition list of the disks and sticks up to date;
  other plugins use its `hotplugNotifier`.
- `Satfinder/`: kept only so that feed plugins written for OE-Alliance images find the Satfinder class they import;
  the signal finder of the image is `Components/HdsGasireSemnal.py`.
- `SkinSelector/`, `DiseqcTester/`: theme choice (logic in `Components/HdsSkinuri.py`) and the DiSEqC test.
- `Videomode/`: not a plugin of the image, only the module names (`VideoHardware`, `VideoSetup`) that plugins of
  other images import; `SystemPlugins/Makefile.am` installs its three files.

## How a plugin reaches the receiver

The `Makefile.am` files list explicitly the files that are installed; a file that is not listed there (like this
README) stays in the source only. The plugins of the HD Satelit feed that are not part of the
image (Radio online, DAB+ over USB) are in `pluginuri-feed/` at the root.
