# Files of the HD Satelit enigma2 tree, by origin

This list puts every file of this source tree in one group, by where it comes from. The base is enigma2 as
published by Dream Multimedia: git commit 75d5fba59 of 14 September 2011 ("Merge branch
'bug_747_cancel_waiting_tasks'"). Every commit after it is by HD Satelit / Monea Software; the files they took
from other projects are in group 3, with their source. The list is generated from git only (git ls-tree,
git diff -M, the file headers as committed), never from the files on disk. The commit it describes is not
written here, so the list does not change by itself.

To regenerate it, at the root of the repository: `python3 tools/file_origins.py` (on Windows:
`py -3 tools/file_origins.py`); `--check` exits with code 1 when FILES.md is not up to date. It is regenerated
and committed before every version tag, so the published source always carries the list of its own files.
Regenerating it needs the git repository of the image, with its history back to the base commit; a published
source tree is only a copy of the files and cannot regenerate the list, but every path can be checked in it.

## Counts

| Group | Files |
|---|---:|
| 1. Unchanged from the enigma2 base | 431 |
| 2. Modified from the enigma2 base | 499 |
| 3. Added from other sources | 497 |
| 4. Added by HD Satelit / Monea Software | 1614 |
| Total files in this tree | 3041 |
| Removed from the enigma2 base | 242 |

Group 3 holds 0 files with "origin not recorded"; group 4 holds 930 source files with our copyright line and 684 pictures,
fonts, data, build and documentation files.

## How the added files are sorted

- A text file goes to group 4 when one of its first 40 lines is our copyright line: a line with
  "Copyright" and moneasoftware.com or Monea Software, or a line that starts with "HD Satelit
  (moneasoftware.com ...)" and has a year. A line that says only that the file was changed by moneasoftware.com
  is not a copyright line: such files stay in group 3.
- Pictures, fonts, data, build and documentation files carry no header. They are sorted by folder, using the
  table in `tools/file_origins.py`, written from the commits that added them: the folders created by HD Satelit
  (the HDSatelit theme, the feed plugins, the Hds modules and plugins, the image data) go to group 4; fonts and
  icons from other projects go to group 3 with their source; anything else is "origin not recorded". A code file
  never goes to group 4 because of its folder. No commit of this repository is written here, so the list
  depends only on the files of the tree.
- Every file of group 3 has its origin: the source named in its header (the headers of this tree are in
  Romanian; "Luat din sursele GPL enigma2 (OE-Alliance), commitul ..." means taken from the GPL enigma2
  sources of OE-Alliance at that commit), or the source from the table. The licenses named in the header are
  given next to it. "origin not recorded" means that neither the header nor the table says where the file
  comes from.

## 1. Unchanged from the enigma2 base (431)

- **`./`** (13): `AUTHORS`, `COPYING`, `ChangeLog`, `GlobalActions.py`, `LICENSE.GPLv2`, `NEWS`, `NavigationInstance.py`, `autogen.sh`, `enigma2.bb`, `lamedb`, `stamp-h.in`, `timers.xml`, `tools.py`
- **`data/`** (6): `defaultsatlists.xml`, `defaultwizard.xml`, `dreampackagewizard.xml`, `encoding.conf`, `prev.png`, `rcpositions.xml`
- **`data/countries/`** (31): `ad.png`, `ae.png`, `cz.png`, `de.png`, `dk.png`, `ee.png`, `en.png`, `es.png`, `fi.png`, `fr.png`, `gr.png`, `hr.png`, `hu.png`, `is.png`, `it.png`, `lt.png`, `lv.png`, `missing.png`, `nl.png`, `no.png`, `pl.png`, `pt.png`, `ro.png`, `ru.png`, `se.png`, `si.png`, `sk.png`, `tr.png`, `ua.png`, `x-fy.png`, `yu.png`
- **`data/defaults/`** (1): `Makefile.am`
- **`data/defaults/Dream/`** (14): `Makefile.am`, `bouquets.tv`, `dm500hd.info`, `dm7020hd.info`, `dm7025.info`, `dm800.info`, `dm8000.info`, `dm800se.info`, `settings.500hd`, `settings.7020hd`, `settings.7025`, `settings.800`, `settings.8000`, `settings.800se`
- **`data/defaults/Dream/hdbouquets/`** (1): `Makefile.am`
- **`data/defaults/Dream/sdbouquets/`** (1): `Makefile.am`
- **`data/extensions/`** (5): `Makefile.am`, `directory.png`, `movie.png`, `music.png`, `picture.png`
- **`data/fonts/`** (2): `ae_AlMateen.ttf`, `tuxtxt.ttf`
- **`data/keymaps/`** (3): `Makefile.am`, `dream-de.info`, `eng.info`
- **`data/skin_default/`** (66): `arrowdown.png`, `arrowup.png`, `b_b.png`, `b_bl.png`, `b_br.png`, `b_l.png`, `b_r.png`, `b_t.png`, `b_tl.png`, `b_tr.png`, `bar_ber.png`, `bar_snr.png`, `border_epg.png`, `border_eventinfo.png`, `border_info.png`, `border_menu.png`, `border_menu_300.png`, `border_menu_350.png`, `border_multiepg.png`, `bottombar.png`, `celserviceeventprogressbar.png`, `div-h.png`, `div-v.png`, `epg_more.png`, `epg_next.png`, `epg_now.png`, `expandable-plugins.png`, `expanded-plugins.png`, `info-bg.png`, `info-bg_mp.png`, `mediaplayer_bg.png`, `mute.png`, `nim_active.png`, `no_coverArt.png`, `pal.png`, `picon_default.png`, `position_arrow.png`, `position_pointer.png`, `progress_bg.png`, `progress_big.png`, `progress_medium.png`, `progress_small.png`, `rc.png`, `rcold.png`, `screws.png`, `screws_mp.png`, `sleeptimer.png`, `timeline-now.png`, `timeline.png`, `unhandled-key.png`, `verticalline-plugins.png`, `vkey_backspace.png`, `vkey_bg.png`, `vkey_clr.png`, `vkey_esc.png`, `vkey_icon.png`, `vkey_left.png`, `vkey_ok.png`, `vkey_right.png`, `vkey_sel.png`, `vkey_shift.png`, `vkey_shift_sel.png`, `vkey_space.png`, `vkey_text.png`, `volume.png`, `wizard.png`
- **`data/skin_default/buttons/`** (32): `blue.png`, `blue_pressed.png`, `button_blue.png`, `button_blue_off.png`, `button_green.png`, `button_green_off.png`, `button_red.png`, `button_red_off.png`, `button_yellow.png`, `button_yellow_off.png`, `green-big.png`, `green.png`, `key_0.png`, `key_1.png`, `key_2.png`, `key_3.png`, `key_4.png`, `key_5.png`, `key_6.png`, `key_7.png`, `key_8.png`, `key_9.png`, `key_blue.png`, `key_green.png`, `key_info.png`, `key_menu.png`, `key_red.png`, `key_text.png`, `key_yellow.png`, `red-big.png`, `red.png`, `yellow.png`
- **`data/skin_default/icons/`** (63): `clock.png`, `dish.png`, `dish_scan.png`, `epgclock.png`, `epgclock_add.png`, `epgclock_post.png`, `epgclock_pre.png`, `epgclock_prepost.png`, `folder.png`, `ico_mp_forward.png`, `ico_mp_pause.png`, `ico_mp_play.png`, `ico_mp_rewind.png`, `ico_mp_stop.png`, `icon_crypt.png`, `icon_dolby.png`, `icon_event.png`, `icon_format.png`, `icon_rec.png`, `icon_rec_off.png`, `icon_txt.png`, `icon_view.png`, `icons_off.png`, `input_error.png`, `input_info.png`, `input_keyboard-configured.png`, `input_keyboard.png`, `input_mouse-configured.png`, `input_mouse.png`, `input_question.png`, `input_rcnew-configured.png`, `input_rcnew.png`, `input_rcold-configured.png`, `input_rcold.png`, `lock.png`, `lockBouquet.png`, `lock_error.png`, `lock_off.png`, `lock_on.png`, `marker.png`, `mp_buttons.png`, `network_wired-active.png`, `network_wired-inactive.png`, `network_wired.png`, `network_wireless-active.png`, `network_wireless-inactive.png`, `network_wireless.png`, `plugin.png`, `rass_logo.png`, `rass_page1.png`, `rass_page2.png`, `rass_page3.png`, `rass_page4.png`, `record.png`, `redx.png`, `repeat_off.png`, `repeat_on.png`, `scan-c.png`, `scan-s.png`, `scan-t.png`, `selectioncross.png`, `unlock.png`, `unlockBouquet.png`
- **`data/skin_default/menu/`** (10): `Makefile.am`, `dvd_player.png`, `information.png`, `media_player.png`, `plugins.png`, `scart.png`, `setup.png`, `shutdown.png`, `subtitles.png`, `timer.png`
- **`doc/`** (8): `DEFAULTS`, `FILEFORMAT`, `PLUGINS`, `RETURNCODES`, `RULES`, `SKINS`, `SOURCES`, `TPM`
- **`include/`** (1): `Makefile.am`
- **`lib/`** (1): `Makefile.am`
- **`lib/actions/`** (2): `.gitignore`, `Makefile.am`
- **`lib/base/`** (25): `.gitignore`, `buffer.cpp`, `buffer.h`, `connection.cpp`, `eenv.h`, `elock.cpp`, `elock.h`, `encoding.cpp`, `encoding.h`, `estring.h`, `etpm.cpp`, `etpm.h`, `i18n.h`, `init.cpp`, `init.h`, `init_num.h`, `ioprio.cpp`, `ioprio.h`, `itssource.h`, `nconfig.h`, `object.h`, `rawfile.h`, `ringbuffer.h`, `smartptr.cpp`, `smartptr.h`
- **`lib/components/`** (1): `Makefile.am`
- **`lib/driver/`** (8): `etimezone.cpp`, `etimezone.h`, `input_fake.h`, `misc_options.h`, `rcdbox.h`, `rcdreambox2.h`, `rfmod.cpp`, `rfmod.h`
- **`lib/dvb/`** (12): `crc32.cpp`, `crc32.h`, `eit.cpp`, `list.h`, `metaparser.cpp`, `metaparser.h`, `pesparse.cpp`, `pesparse.h`, `pvrparse.h`, `rotor_calc.cpp`, `rotor_calc.h`, `tstools.h`
- **`lib/dvb/lowlevel/`** (3): `Makefile.am`, `eit.h`, `mhw.h`
- **`lib/dvb_ci/`** (5): `dvbci_appmgr.h`, `dvbci_camgr.h`, `dvbci_mmi.h`, `dvbci_resmgr.h`, `dvbci_session.h`
- **`lib/gdi/`** (13): `bcm.cpp`, `compositing.cpp`, `epng.h`, `epoint.h`, `erect.cpp`, `erect.h`, `esize.h`, `gfbdc.h`, `gfont.cpp`, `gfont.h`, `glcddc.h`, `picexif.h`, `region.h`
- **`lib/gui/`** (13): `ebutton.cpp`, `ebutton.h`, `einput.cpp`, `einput.h`, `einputnumber.cpp`, `einputnumber.h`, `einputstring.cpp`, `einputstring.h`, `epositiongauge.h`, `evideo.h`, `ewidgetanimation.cpp`, `ewidgetanimation.h`, `ewindowstyle.cpp`
- **`lib/mmi/`** (1): `Makefile.am`
- **`lib/nav/`** (1): `Makefile.am`
- **`lib/python/`** (2): `.gitignore`, `swig.h`
- **`lib/python/Components/`** (7): `FIFOList.py`, `GUIComponent.py`, `HTMLComponent.py`, `HTMLSkin.py`, `VariableText.py`, `__init__.py`, `components.py`
- **`lib/python/Components/Converter/`** (8): `Converter.py`, `MenuEntryCompare.py`, `Poll.py`, `SensorToText.py`, `StaticText.py`, `StringListSelection.py`, `TunerInfo.py`, `ValueToPixmap.py`
- **`lib/python/Components/Sources/`** (2): `Source.py`, `__init__.py`
- **`lib/python/Plugins/`** (1): `__init__.py`
- **`lib/python/Plugins/Extensions/`** (1): `__init__.py`
- **`lib/python/Plugins/Extensions/MediaPlayer/`** (2): `Makefile.am`, `__init__.py`
- **`lib/python/Plugins/Extensions/MediaPlayer/meta/`** (3): `Makefile.am`, `mediaplayer_de.jpg`, `mediaplayer_en.jpg`
- **`lib/python/Plugins/Extensions/MediaScanner/`** (2): `Makefile.am`, `__init__.py`
- **`lib/python/Plugins/Extensions/MediaScanner/meta/`** (3): `Makefile.am`, `mediascanner_de.jpg`, `mediascanner_en.jpg`
- **`lib/python/Plugins/Extensions/PicturePlayer/`** (2): `__init__.py`, `pictureplayer.png`
- **`lib/python/Plugins/Extensions/PicturePlayer/data/`** (2): `Makefile.am`, `pic_frame.png`
- **`lib/python/Plugins/Extensions/PicturePlayer/meta/`** (2): `Makefile.am`, `pictureplayer.jpg`
- **`lib/python/Plugins/SystemPlugins/`** (1): `__init__.py`
- **`lib/python/Plugins/SystemPlugins/DiseqcTester/`** (2): `Makefile.am`, `__init__.py`
- **`lib/python/Plugins/SystemPlugins/DiseqcTester/meta/`** (3): `Makefile.am`, `diseqctester_de.jpg`, `diseqctester_en.jpg`
- **`lib/python/Plugins/SystemPlugins/Hotplug/`** (1): `__init__.py`
- **`lib/python/Plugins/SystemPlugins/Satfinder/`** (1): `__init__.py`
- **`lib/python/Plugins/SystemPlugins/SkinSelector/`** (3): `Makefile.am`, `__init__.py`, `noprev.png`
- **`lib/python/Plugins/SystemPlugins/SkinSelector/meta/`** (3): `Makefile.am`, `skinselector_de.jpg`, `skinselector_en.jpg`
- **`lib/python/Screens/`** (3): `FactoryReset.py`, `SimpleSummary.py`, `__init__.py`
- **`lib/python/Tools/`** (5): `BoundFunction.py`, `CList.py`, `Event.py`, `Import.py`, `XMLTools.py`
- **`lib/service/`** (3): `service.h`, `servicefs.h`, `servicem2ts.h`
- **`m4/`** (6): `.gitignore`, `ax_pkg_swig.m4`, `ax_pthread.m4`, `ax_python_devel.m4`, `ax_swig_enable_cxx.m4`, `ax_swig_python.m4`
- **`main/`** (6): `.gitignore`, `enigma-gdi.cpp`, `enigma-gui.cpp`, `version_info.h`, `xmlgenerator.cpp`, `xmlgenerator.h`
- **`po/`** (1): `.gitignore`
- **`tests/`** (6): `FakeNotifications.py`, `README`, `test_timer_repeating.results`, `test_timer_repeating_dst_skip.results`, `test_timer_repeating_dst_start.results`, `tests.py`
- **`tests/hdd/movie/`** (1): `dummy`
- **`tools/`** (2): `convert_argb_png.c`, `libopen.c`
- **`tools/host_tools/FormatConverter/`** (5): `README`, `datasource.pyc`, `input.pyc`, `lamedb.pyc`, `satxml.pyc`

## 2. Modified from the enigma2 base (499)

- **`./`** (19): `.gitignore`, `LICENSE`, `Makefile.am`, `Navigation.py`, `README`, `RecordTimer.py`, `ServiceReference.py`, `SleepTimer.py`, `configure.ac`, `e2reactor.py`, `enigma2.pc.in`, `keyids.py`, `keymapparser.py`, `mytest.py`, `skin.py`, `timer.py`, `userbouquet.orf.tv`, `userbouquet.premiere.tv`, `userbouquet.srgssr.tv`
- **`data/`** (9): `Makefile.am`, `keymap.xml`, `menu.xml`, `radio.mvi`, `setup.xml`, `skin.xml`, `skin_default.xml`, `tutorialwizard.xml`, `unicable.xml`
- **`data/countries/`** (1): `Makefile.am`
- **`data/defaults/Dream/`** (2): `settings.c`, `settings.t`
- **`data/defaults/Dream/hdbouquets/`** (1): `userbouquet.favourites.tv`
- **`data/defaults/Dream/sdbouquets/`** (1): `userbouquet.favourites.tv`
- **`data/fonts/`** (2): `Makefile.am`, `ae_AlMateen.license`
- **`data/keymaps/`** (2): `dream-de.kmap`, `eng.kmap`
- **`data/skin_default/`** (1): `Makefile.am`
- **`data/skin_default/buttons/`** (1): `Makefile.am`
- **`data/skin_default/icons/`** (1): `Makefile.am`
- **`data/skin_default/spinner/`** (5): `Makefile.am`, `wait1.png`, `wait2.png`, `wait3.png`, `wait4.png`
- **`include/`** (2): `connection.h`, `libsig_comp.h`
- **`lib/actions/`** (3): `action.cpp`, `action.h`, `parseactions.py`
- **`lib/base/`** (18): `Makefile.am`, `console.cpp`, `console.h`, `ebase.cpp`, `ebase.h`, `eenv.cpp.in`, `eerror.cpp`, `eerror.h`, `eptrlist.h`, `estring.cpp`, `filepush.cpp`, `filepush.h`, `message.cpp`, `message.h`, `nconfig.cpp`, `rawfile.cpp`, `thread.cpp`, `thread.h`
- **`lib/components/`** (4): `file_eraser.cpp`, `file_eraser.h`, `scan.cpp`, `scan.h`
- **`lib/driver/`** (12): `Makefile.am`, `avswitch.cpp`, `avswitch.h`, `misc_options.cpp`, `rc.cpp`, `rc.h`, `rcconsole.cpp`, `rcconsole.h`, `rcinput.cpp`, `rcinput.h`, `rcsdl.cpp`, `rcsdl.h`
- **`lib/dvb/`** (39): `Makefile.am`, `db.cpp`, `db.h`, `decoder.cpp`, `decoder.h`, `demux.cpp`, `demux.h`, `dvb.cpp`, `dvb.h`, `dvbtime.cpp`, `dvbtime.h`, `eit.h`, `epgcache.cpp`, `epgcache.h`, `esection.cpp`, `esection.h`, `frontend.cpp`, `frontend.h`, `frontendparms.h`, `idemux.h`, `idvb.h`, `isection.h`, `pmt.cpp`, `pmt.h`, `pvrparse.cpp`, `radiotext.cpp`, `radiotext.h`, `scan.cpp`, `scan.h`, `sec.cpp`, `sec.h`, `specs.h`, `subtitle.cpp`, `subtitle.h`, `teletext.cpp`, `teletext.h`, `tstools.cpp`, `volume.cpp`, `volume.h`
- **`lib/dvb_ci/`** (12): `Makefile.am`, `dvbci.cpp`, `dvbci.h`, `dvbci_appmgr.cpp`, `dvbci_camgr.cpp`, `dvbci_datetimemgr.cpp`, `dvbci_datetimemgr.h`, `dvbci_mmi.cpp`, `dvbci_resmgr.cpp`, `dvbci_session.cpp`, `dvbci_ui.cpp`, `dvbci_ui.h`
- **`lib/gdi/`** (26): `Makefile.am`, `accel.cpp`, `accel.h`, `compositing.h`, `epng.cpp`, `fb.cpp`, `fb.h`, `font.cpp`, `font.h`, `font_arabic.cpp`, `gfbdc.cpp`, `glcddc.cpp`, `gmaindc.cpp`, `gmaindc.h`, `gpixmap.cpp`, `gpixmap.h`, `grc.cpp`, `grc.h`, `lcd.cpp`, `lcd.h`, `picexif.cpp`, `picload.cpp`, `picload.h`, `region.cpp`, `sdl.cpp`, `sdl.h`
- **`lib/gui/`** (26): `Makefile.am`, `ecanvas.cpp`, `ecanvas.h`, `elabel.cpp`, `elabel.h`, `elistbox.cpp`, `elistbox.h`, `elistboxcontent.cpp`, `elistboxcontent.h`, `epixmap.cpp`, `epixmap.h`, `epositiongauge.cpp`, `eslider.cpp`, `eslider.h`, `esubtitle.cpp`, `esubtitle.h`, `evideo.cpp`, `ewidget.cpp`, `ewidget.h`, `ewidgetdesktop.cpp`, `ewidgetdesktop.h`, `ewindow.cpp`, `ewindow.h`, `ewindowstyle.h`, `ewindowstyleskinned.cpp`, `ewindowstyleskinned.h`
- **`lib/mmi/`** (2): `mmi_ui.cpp`, `mmi_ui.h`
- **`lib/nav/`** (4): `core.cpp`, `core.h`, `pcore.cpp`, `pcore.h`
- **`lib/python/`** (7): `Makefile.am`, `connections.cpp`, `connections.h`, `enigma_py_patcher.py`, `enigma_python.i`, `python.cpp`, `python.h`
- **`lib/python/Components/`** (68): `AVSwitch.py`, `About.py`, `ActionMap.py`, `BlinkingPixmap.py`, `Button.py`, `ChoiceList.py`, `Clock.py`, `ConditionalWidget.py`, `ConfigList.py`, `Console.py`, `DiskInfo.py`, `DreamInfoHandler.py`, `Element.py`, `EpgList.py`, `FanControl.py`, `FileList.py`, `GUISkin.py`, `Harddisk.py`, `HelpMenuList.py`, `Input.py`, `InputDevice.py`, `Ipkg.py`, `Keyboard.py`, `Label.py`, `Language.py`, `Lcd.py`, `Makefile.am`, `MediaPlayer.py`, `MenuList.py`, `MovieList.py`, `MultiContent.py`, `Network.py`, `NimManager.py`, `ParentalControl.py`, `ParentalControlList.py`, `PerServiceDisplay.py`, `Pixmap.py`, `Playlist.py`, `PluginComponent.py`, `PluginList.py`, `ProgressBar.py`, `RFmod.py`, `RecordingConfig.py`, `ResourceManager.py`, `Scanner.py`, `ScrollLabel.py`, `SelectionList.py`, `Sensors.py`, `ServiceEventTracker.py`, `ServiceList.py`, `ServicePosition.py`, `ServiceScan.py`, `SetupDevices.py`, `Slider.py`, `SystemInfo.py`, `Task.py`, `TimerList.py`, `TimerSanityCheck.py`, `Timezones.py`, `TuneTest.py`, `TunerInfo.py`, `UsageConfig.py`, `VariableValue.py`, `VideoWindow.py`, `VolumeBar.py`, `VolumeControl.py`, `config.py`, `language_cache.py`
- **`lib/python/Components/Addons/`** (1): `__init__.py` (renamed from `lib/python/Plugins/DemoPlugins/TPMDemo/__init__.py`)
- **`lib/python/Components/Converter/`** (23): `ClockToText.py`, `Combine.py`, `ConditionalShowHide.py`, `ConfigEntryTest.py`, `EventName.py`, `EventTime.py`, `FrontendInfo.py`, `Makefile.am`, `MovieInfo.py`, `ProgressToText.py`, `RdsInfo.py`, `RemainingToText.py`, `ServiceInfo.py`, `ServiceName.py`, `ServicePosition.py`, `ServiceTime.py`, `StaticMultiList.py`, `Streaming.py`, `StringList.py`, `TemplatedMultiContent.py`, `ValueBitTest.py`, `ValueRange.py`, `__init__.py`
- **`lib/python/Components/Renderer/`** (13): `Canvas.py`, `FixedLabel.py`, `FrontpanelLed.py`, `Label.py`, `Listbox.py`, `Makefile.am`, `Picon.py`, `Pig.py`, `Pixmap.py`, `PositionGauge.py`, `Progress.py`, `Renderer.py`, `__init__.py`
- **`lib/python/Components/Sources/`** (20): `Boolean.py`, `CanvasSource.py`, `Clock.py`, `Config.py`, `CurrentService.py`, `Event.py`, `EventInfo.py`, `FrontendInfo.py`, `FrontendStatus.py`, `List.py`, `Makefile.am`, `Progress.py`, `RdsDecoder.py`, `RecordState.py`, `Sensor.py`, `ServiceEvent.py`, `ServiceList.py`, `StaticText.py`, `StreamService.py`, `TunerInfo.py`
- **`lib/python/Plugins/`** (3): `Makefile.am`, `Plugin.py`, `newplugin.py`
- **`lib/python/Plugins/Extensions/`** (1): `Makefile.am`
- **`lib/python/Plugins/Extensions/MediaPlayer/`** (2): `plugin.py`, `settings.py`
- **`lib/python/Plugins/Extensions/MediaPlayer/meta/`** (1): `plugin_mediaplayer.xml`
- **`lib/python/Plugins/Extensions/MediaScanner/`** (1): `plugin.py`
- **`lib/python/Plugins/Extensions/MediaScanner/meta/`** (1): `plugin_mediascanner.xml`
- **`lib/python/Plugins/Extensions/PicturePlayer/`** (2): `Makefile.am`, `plugin.py`
- **`lib/python/Plugins/Extensions/PicturePlayer/meta/`** (1): `plugin_pictureplayer.xml`
- **`lib/python/Plugins/SystemPlugins/`** (1): `Makefile.am`
- **`lib/python/Plugins/SystemPlugins/DiseqcTester/`** (1): `plugin.py`
- **`lib/python/Plugins/SystemPlugins/DiseqcTester/meta/`** (1): `plugin_diseqctester.xml`
- **`lib/python/Plugins/SystemPlugins/Hotplug/`** (2): `Makefile.am`, `plugin.py`
- **`lib/python/Plugins/SystemPlugins/Satfinder/`** (2): `Makefile.am`, `plugin.py`
- **`lib/python/Plugins/SystemPlugins/SkinSelector/`** (1): `plugin.py`
- **`lib/python/Plugins/SystemPlugins/SkinSelector/meta/`** (1): `plugin_skinselector.xml`
- **`lib/python/Plugins/SystemPlugins/Videomode/`** (2): `VideoHardware.py`, `__init__.py`
- **`lib/python/Screens/`** (62): `About.py`, `AudioSelection.py`, `ChannelSelection.py`, `ChoiceBox.py`, `Ci.py`, `Console.py`, `DefaultWizard.py`, `Dish.py`, `EpgSelection.py`, `EventView.py`, `FixedMenu.py`, `Globals.py`, `HarddiskSetup.py`, `HelpMenu.py`, `InfoBar.py`, `InfoBarGenerics.py`, `InputBox.py`, `InputDeviceSetup.py`, `Ipkg.py`, `LanguageSelection.py`, `LocationBox.py`, `Makefile.am`, `Menu.py`, `MessageBox.py`, `MinuteInput.py`, `MovieSelection.py`, `Mute.py`, `NetworkSetup.py`, `NumericalTextInputHelpDialog.py`, `PVRState.py`, `ParentalControlSetup.py`, `PiPSetup.py`, `PictureInPicture.py`, `PluginBrowser.py`, `Rc.py`, `RdsDisplay.py`, `RecordPaths.py`, `Satconfig.py`, `ScanSetup.py`, `Scart.py`, `Screen.py`, `ServiceInfo.py`, `ServiceScan.py`, `ServiceStopScreen.py`, `SessionGlobals.py`, `Setup.py`, `SleepTimerEdit.py`, `Standby.py`, `StartWizard.py`, `SubservicesQuickzap.py`, `SubtitleDisplay.py`, `TaskView.py`, `TextBox.py`, `TimeDateInput.py`, `TimerEdit.py`, `TimerEntry.py`, `TimerSelection.py`, `UnhandledKey.py`, `VirtualKeyBoard.py`, `Volume.py`, `Wizard.py`, `WizardLanguage.py`
- **`lib/python/Tools/`** (16): `ASCIItranslit.py`, `Directories.py`, `Downloader.py`, `DreamboxHardware.py`, `FuzzyDate.py`, `HardwareInfo.py`, `ISO639.py`, `KeyBindings.py`, `LoadPixmap.py`, `Makefile.am`, `Notifications.py`, `NumericalTextInput.py`, `Profile.py`, `RedirectOutput.py`, `Transponder.py`, `__init__.py`
- **`lib/service/`** (17): `Makefile.am`, `event.cpp`, `event.h`, `iservice.h`, `listboxservice.cpp`, `listboxservice.h`, `service.cpp`, `servicedvb.cpp`, `servicedvb.h`, `servicedvbrecord.cpp`, `servicedvbrecord.h`, `servicefs.cpp`, `servicem2ts.cpp`, `servicemp3.cpp`, `servicemp3.h`, `servicexine.cpp`, `servicexine.h`
- **`m4/`** (1): `tuxbox.m4`
- **`main/`** (8): `Makefile.am`, `bsod.cpp`, `bsod.h`, `enigma-dvbtest.cpp`, `enigma-playlist.cpp`, `enigma-scan.cpp`, `enigma.cpp`, `version_info.cpp`
- **`po/`** (31): `Makefile.am`, `ar.po`, `ca.po`, `cs.po`, `da.po`, `de.po`, `el.po`, `en.po`, `es.po`, `et.po`, `fi.po`, `fr.po`, `fy.po`, `hr.po`, `hu.po`, `is.po`, `it.po`, `lt.po`, `lv.po`, `nl.po`, `no.po`, `pl.po`, `pt.po`, `ru.po`, `sk.po`, `sl.po`, `sr.po`, `sv.po`, `tr.po`, `uk.po`, `xml2po.py`
- **`tests/`** (4): `enigma.py`, `events.py`, `fake_time.py`, `test_timer.py`
- **`tools/`** (6): `.gitignore`, `Makefile.am`, `create_picon_links.py`, `enigma2.sh.in`, `genmetaindex.py`, `svg2skin.py`
- **`tools/host_tools/FormatConverter/`** (6): `datasource.py`, `input.py`, `lamedb.py`, `lamedb2satxml.py`, `main.py`, `satxml.py`

## 3. Added from other sources (497)

### `./`

- `LICENSE.original-2011`: the license of the 2011 enigma2 source (Dream Multimedia), kept unchanged.

### `HDSatelit/afisaj-color/fonturi/`

- `NotoSans-SemiBold.ttf`, `NotoSansCondensed-SemiBold.ttf`: Noto Sans, The Noto Project Authors; SIL Open Font License 1.1.
- `OFL.txt`: text of the SIL Open Font License 1.1, with the copyright lines of the fonts next to it.

### `HDSatelit/fonts/`

- `HdsBold.ttf`, `HdsCond.ttf`, `HdsRegular.ttf`, `HdsScripturi.ttf`: Open Sans; Noto Sans Arabic, Hebrew and Thai (static instances, subsets); SIL Open Font License 1.1 (OFL.txt in the same folder).
- `OFL.txt`: text of the SIL Open Font License 1.1, with the copyright lines of the fonts next to it.

### `HDSatelit/meniu/alb/`

- `acces-conditionat.png`, `actualizare.png`, `afisaj-luminozitate.png`, `afisaj.png`, `antena-orientare.png`, `aparate-retea.png`, `aspect-ecrane.png`, `automat.png`, `banda.png`, `cablu.png`, `calitate-imagine.png`, `canal-info.png`, `cauta.png`, `ceas.png`, `comutator.png`, `conexiune.png`, `control-parental.png`, `copie.png`, `curatenie.png`, `decriptare-info.png`, `despre.png`, `disc-oprire.png`, `disc.png`, `dns.png`, `dosare.png`, `ecran-pornire.png`, `ecran-radio.png`, `editor-canale.png`, `egalizator.png`, `extensie.png`, `extensii.png`, `font.png`, `fonturi-descarcare.png`, `formatare.png`, `frecventa.png`, `iesire-sunet.png`, `imagine.png`, `import.png`, `informatii.png`, `inregistrari-discuri.png`, `interfata-web.png`, `interfata.png`, `intrare.png`, `jurnal-caderi.png`, `jurnal.png`, `licente.png`, `limba.png`, `limbi.png`, `lista-redare.png`, `liste-implicite.png`, `lnb.png`, `loc-inregistrari.png`, `locul-antenei.png`, `manual.png`, `margini.png`, `marime-text.png`, `media.png`, `memoria-interna.png`, `memorie.png`, `mod-sigur.png`, `modul-ci.png`, `mufa-video.png`, `multicast.png`, `multiplex.png`, `navigator-setari.png`, `navigator.png`, `noutati.png`, `operator.png`, `oprire-programata.png`, `oprire.png`, `paznic.png`, `player.png`, `pornire.png`, `poze.png`, `procesor.png`, `programari.png`, `programe.png`, `radio.png`, `receptor.png`, `regiune.png`, `reincarca.png`, `repornire-interfata.png`, `repornire.png`, `retea-comutare.png`, `retea-internet.png`, `retea.png`, `revenire.png`, `rotire.png`, `sageata-jos.png`, `sageata-sus.png`, `satelit.png`, `sateliti.png`, `scanare-detaliata.png`, `scanare.png`, `semnal.png`, `setari-generale.png`, `setari-skin.png`, `setari.png`, `sistem.png`, `standby-tv.png`, `standby.png`, `stick.png`, `subtitrari-aspect.png`, `subtitrari-descarcare.png`, `subtitrari-film.png`, `sunet-subtitrari.png`, `surse-internet.png`, `swap.png`, `tastatura.png`, `taste-colorate.png`, `telecomanda.png`, `telecomenzi.png`, `tema.png`, `terestru.png`, `terminal.png`, `traducere.png`, `transmisie.png`, `tuner.png`, `tv-internet.png`, `unghi.png`, `verificare-disc.png`, `verificare-internet.png`, `video-avansat.png`, `volum.png`, `vpn.png`, `wifi-aglomerare.png`: menu icons made from Google Material Symbols (Apache License 2.0), in the colors of the HDSatelit theme.

### `HDSatelit/meniu/deschis/`

- `acces-conditionat.png`, `actualizare.png`, `afisaj-luminozitate.png`, `afisaj.png`, `antena-orientare.png`, `aparate-retea.png`, `aspect-ecrane.png`, `automat.png`, `banda.png`, `cablu.png`, `calitate-imagine.png`, `canal-info.png`, `cauta.png`, `ceas.png`, `comutator.png`, `conexiune.png`, `control-parental.png`, `copie.png`, `curatenie.png`, `decriptare-info.png`, `despre.png`, `disc-oprire.png`, `disc.png`, `dns.png`, `dosare.png`, `ecran-pornire.png`, `ecran-radio.png`, `editor-canale.png`, `egalizator.png`, `extensie.png`, `extensii.png`, `font.png`, `fonturi-descarcare.png`, `formatare.png`, `frecventa.png`, `iesire-sunet.png`, `imagine.png`, `import.png`, `informatii.png`, `inregistrari-discuri.png`, `interfata-web.png`, `interfata.png`, `intrare.png`, `jurnal-caderi.png`, `jurnal.png`, `licente.png`, `limba.png`, `limbi.png`, `lista-redare.png`, `liste-implicite.png`, `lnb.png`, `loc-inregistrari.png`, `locul-antenei.png`, `manual.png`, `margini.png`, `marime-text.png`, `media.png`, `memoria-interna.png`, `memorie.png`, `mod-sigur.png`, `modul-ci.png`, `mufa-video.png`, `multicast.png`, `multiplex.png`, `navigator-setari.png`, `navigator.png`, `noutati.png`, `operator.png`, `oprire-programata.png`, `oprire.png`, `paznic.png`, `player.png`, `pornire.png`, `poze.png`, `procesor.png`, `programari.png`, `programe.png`, `radio.png`, `receptor.png`, `regiune.png`, `reincarca.png`, `repornire-interfata.png`, `repornire.png`, `retea-comutare.png`, `retea-internet.png`, `retea.png`, `revenire.png`, `rotire.png`, `sageata-jos.png`, `sageata-sus.png`, `satelit.png`, `sateliti.png`, `scanare-detaliata.png`, `scanare.png`, `semnal.png`, `setari-generale.png`, `setari-skin.png`, `setari.png`, `sistem.png`, `standby-tv.png`, `standby.png`, `stick.png`, `subtitrari-aspect.png`, `subtitrari-descarcare.png`, `subtitrari-film.png`, `sunet-subtitrari.png`, `surse-internet.png`, `swap.png`, `tastatura.png`, `taste-colorate.png`, `telecomanda.png`, `telecomenzi.png`, `tema.png`, `terestru.png`, `terminal.png`, `traducere.png`, `transmisie.png`, `tuner.png`, `tv-internet.png`, `unghi.png`, `verificare-disc.png`, `verificare-internet.png`, `video-avansat.png`, `volum.png`, `vpn.png`, `wifi-aglomerare.png`: menu icons made from Google Material Symbols (Apache License 2.0), in the colors of the HDSatelit theme.

### `HDSatelit/meniu/inchis/`

- `acces-conditionat.png`, `actualizare.png`, `afisaj-luminozitate.png`, `afisaj.png`, `antena-orientare.png`, `aparate-retea.png`, `aspect-ecrane.png`, `automat.png`, `banda.png`, `cablu.png`, `calitate-imagine.png`, `canal-info.png`, `cauta.png`, `ceas.png`, `comutator.png`, `conexiune.png`, `control-parental.png`, `copie.png`, `curatenie.png`, `decriptare-info.png`, `despre.png`, `disc-oprire.png`, `disc.png`, `dns.png`, `dosare.png`, `ecran-pornire.png`, `ecran-radio.png`, `editor-canale.png`, `egalizator.png`, `extensie.png`, `extensii.png`, `font.png`, `fonturi-descarcare.png`, `formatare.png`, `frecventa.png`, `iesire-sunet.png`, `imagine.png`, `import.png`, `informatii.png`, `inregistrari-discuri.png`, `interfata-web.png`, `interfata.png`, `intrare.png`, `jurnal-caderi.png`, `jurnal.png`, `licente.png`, `limba.png`, `limbi.png`, `lista-redare.png`, `liste-implicite.png`, `lnb.png`, `loc-inregistrari.png`, `locul-antenei.png`, `manual.png`, `margini.png`, `marime-text.png`, `media.png`, `memoria-interna.png`, `memorie.png`, `mod-sigur.png`, `modul-ci.png`, `mufa-video.png`, `multicast.png`, `multiplex.png`, `navigator-setari.png`, `navigator.png`, `noutati.png`, `operator.png`, `oprire-programata.png`, `oprire.png`, `paznic.png`, `player.png`, `pornire.png`, `poze.png`, `procesor.png`, `programari.png`, `programe.png`, `radio.png`, `receptor.png`, `regiune.png`, `reincarca.png`, `repornire-interfata.png`, `repornire.png`, `retea-comutare.png`, `retea-internet.png`, `retea.png`, `revenire.png`, `rotire.png`, `sageata-jos.png`, `sageata-sus.png`, `satelit.png`, `sateliti.png`, `scanare-detaliata.png`, `scanare.png`, `semnal.png`, `setari-generale.png`, `setari-skin.png`, `setari.png`, `sistem.png`, `standby-tv.png`, `standby.png`, `stick.png`, `subtitrari-aspect.png`, `subtitrari-descarcare.png`, `subtitrari-film.png`, `sunet-subtitrari.png`, `surse-internet.png`, `swap.png`, `tastatura.png`, `taste-colorate.png`, `telecomanda.png`, `telecomenzi.png`, `tema.png`, `terestru.png`, `terminal.png`, `traducere.png`, `transmisie.png`, `tuner.png`, `tv-internet.png`, `unghi.png`, `verificare-disc.png`, `verificare-internet.png`, `video-avansat.png`, `volum.png`, `vpn.png`, `wifi-aglomerare.png`: menu icons made from Google Material Symbols (Apache License 2.0), in the colors of the HDSatelit theme.

### `data/`

- `hds-locuri.tsv.gz`: generated by HD Satelit; city data from GeoNames (geonames.org), CC BY 4.0 (source in the first lines of the file).
- `hds-producatori-mac.txt.gz`: Wireshark manuf list, made from the public IEEE registries; GPL-2.0-or-later (source in the first lines of the file).

### `data/countries/`

- `al.png`: flag of Albania drawn by HD Satelit; the shine taken from data/countries/ua.png of the enigma2 base (Dream Multimedia).
- `bg.png`: flag of Bulgaria drawn by HD Satelit; the shine taken from data/countries/ru.png of the enigma2 base (Dream Multimedia).
- `uz.png`: flag of Uzbekistan drawn by HD Satelit; the shine taken from data/countries/ua.png of the enigma2 base (Dream Multimedia).

### `data/fonts/`

- `AtkinsonHyperlegible-Bold.ttf`, `AtkinsonHyperlegible-OFL.txt`, `AtkinsonHyperlegible-Regular.ttf`: Atkinson Hyperlegible, Braille Institute of America; SIL Open Font License 1.1.
- `Barlow-Bold.ttf`, `Barlow-OFL.txt`, `Barlow-Regular.ttf`, `BarlowSemiCondensed-Regular.ttf`: Barlow, The Barlow Project Authors; SIL Open Font License 1.1.
- `DejaVuSansMono-Bold.license`, `DejaVuSansMono-Bold.ttf`: DejaVu Sans Mono Bold 2.35, only the line gap changed; Bitstream Vera and Arev licenses (DejaVuSansMono-Bold.license).
- `HdsBold.ttf`, `HdsCond.ttf`, `HdsRegular.ttf`: Open Sans; Noto Sans Arabic, Hebrew and Thai (static instances, subsets); SIL Open Font License 1.1 (OFL.txt in the same folder).
- `OFL.txt`: text of the SIL Open Font License 1.1, with the copyright lines of the fonts next to it.
- `PT_Sans-Narrow-Web-Regular.ttf`, `PT_Sans-OFL.txt`, `PT_Sans-Web-Bold.ttf`, `PT_Sans-Web-Regular.ttf`: PT Sans, ParaType Ltd.; SIL Open Font License 1.1.
- `enigma2icons.license`, `enigma2icons.ttf`: icon font built by HD Satelit from Google Material Symbols; Apache License 2.0 (enigma2icons.license).
- `tuxtxt.license`: license of tuxtxt.ttf (Bitstream Vera Sans Mono Bold 1.10).

### `data/skin_default/buttons/`

- `vkey_icon.png`: copy of data/skin_default/vkey_icon.png of the enigma2 base (Dream Multimedia), unchanged.

### `lib/dvb/`

- `cahandler.cpp`, `cahandler.h`, `csaengine.cpp`, `csaengine.h`, `csasession.cpp`, `csasession.h`, `cwhandler.cpp`, `cwhandler.h`: SoftCSA code by WXbet and Betacentauri (authors named in the header), GPL-2.0-only; changed by HD Satelit.
- `hdsvtuner.cpp`, `hdsvtuner.h`: based on enigma2 (OE-Alliance), lib/dvb/dvb.cpp; changed by HD Satelit; license named in the header: GPL-2.0.

### `lib/dvb_ci/`

- `aes_xcbc_mac.cpp`, `aes_xcbc_mac.h`, `descrambler.cpp`, `descrambler.h`, `dvbci_app_mmi.cpp`, `dvbci_app_mmi.h`, `dvbci_cam_upgrade.cpp`, `dvbci_cam_upgrade.h`, `dvbci_ccmgr.cpp`, `dvbci_ccmgr.h`, `dvbci_ccmgr_helper.cpp`, `dvbci_ccmgr_helper.h`, `dvbci_hlcmgr.cpp`, `dvbci_hlcmgr.h`, `dvbci_host_ctrl.cpp`, `dvbci_host_ctrl.h`, `dvbci_operatorprofile.cpp`, `dvbci_operatorprofile.h`: enigma2 (OE-Alliance), commit 29d951a6ec2e; changed by HD Satelit; license named in the header: GPL-2.0.

### `lib/python/Components/`

- `HdsChromeOS.py`: taken from inputstreamhelper (script.module.inputstreamhelper, lib/inputstreamhelper/widevine/arm_chromeos.py), MIT License (header).
- `HdsLocuriDate.py`: generated by HD Satelit; city data from GeoNames (geonames.org), CC BY 4.0 (header).
- `SkinIcon.py`: based on enigma2 (OE-Alliance), lib/python/Components/SkinIcon.py; changed by HD Satelit.

### `lib/python/Components/Addons/`

- `ButtonSequence.py`, `ColorButtonsSequence.py`, `GUIAddon.py`, `Pager.py`, `ScreenButtonsBar.py`, `ScreenHeader.py`, `ServiceInfoBar.py`: enigma2 (OE-Alliance), commit 29d951a6ec2e; license named in the header: GPL-2.0.

### `lib/python/Components/Converter/`

- `BitrateInfo.py`: a public enigma2 tree, commit 73ab10edaeee; license named in the header: GPL-2.0.
- `ChannelNumbers.py`, `EGAnalogic.py`, `EtAnalogClock.py`, `ExtremeInfo.py`, `HbbtvApplicationInfo.py`, `RemoteControlInfo.py`, `SmartInfo.py`, `Streaming2.py`, `TrackInfo.py`, `VServiceOrbitalPosition.py`, `VWeather.py`, `VfdDisplay.py`, `VtiInfo.py`, `VtiTempFan.py`, `pstrCnvrt.py`: enigma2 (OE-Alliance), commit 29d951a6ec2e; license named in the header: GPL-2.0.
- `VExtraNumText.py`: enigma2 (OE-Alliance), commit 29d951a6ec2e; license named in the header: GPL-2.0-or-later.

### `lib/python/Components/Renderer/`

- `BoxLogo.py`: e2-boxlogos (github.com/DimitarCC/e2-boxlogos) by DimitarCC, commit 45a845077cfb, GPL-2.0; changed by HD Satelit (header).
- `EGclock.py`, `EtAnalogClockLCD.py`, `PrimeTime.py`, `QRCode.py`, `VWeatherUpdater.py`, `VtiEmuInfo.py`, `VtiImageVersion.py`, `pstrRndr.py`: enigma2 (OE-Alliance), commit 29d951a6ec2e; license named in the header: GPL-2.0.
- `VReference.py`, `VWatches.py`: enigma2 (OE-Alliance), commit 29d951a6ec2e; license named in the header: GPL-2.0-or-later.
- `YWeatherPicon.py`: a public enigma2 tree, commit 73ab10edaeee; license named in the header: GPL-2.0.

### `lib/python/Components/Sources/`

- `HbbtvApplication.py`: based on enigma2 (OE-Alliance), lib/python/Components/Sources/HbbtvApplication.py; changed by HD Satelit; license named in the header: GPL-2.0.

### `lib/python/Plugins/Extensions/HdsWebControl/`

- `mpegts-licenta.txt`: license and list of changes of mpegts.js.
- `mpegts.js`: mpegts.js 1.8.0 (github.com/xqq/mpegts.js), Apache License 2.0; changed by HD Satelit (header and mpegts-licenta.txt).

### `lib/python/Plugins/Extensions/HdsWebControl/tv-wasm/`

- `compiler-rt-licenta.txt`, `dlmalloc-licenta.txt`, `emscripten-licenta.txt`, `ffmpeg-licenta.txt`, `musl-licenta.txt`: license text of the component named in the file name, built into hdsdec.wasm.
- `hdsdec.js`, `hdsdec.wasm`: decoder built by HD Satelit from FFmpeg 8.1.3 (LGPL-2.1-or-later) with Emscripten; licenses in tv-wasm/*-licenta.txt.

### `lib/python/Tools/`

- `GetEcmInfo.py`, `WeatherID.py`: enigma2 (OE-Alliance), commit 29d951a6ec2e; license named in the header: GPL-2.0.

### `lib/service/`

- `iservicescrambled.h`, `servicedvbsoftdecoder.cpp`, `servicedvbsoftdecoder.h`: SoftCSA code by WXbet and Betacentauri (authors named in the header), GPL-2.0-only; changed by HD Satelit.

### `m4/`

- `mm-ax_cxx_compile_stdcxx.m4`: GNU Autoconf Archive, ax_cxx_compile_stdcxx (license in the header).

### `pluginuri-feed/DabTerestru/`

- `LICENSE`: text of the GNU General Public License, version 2 (Free Software Foundation).

## 4. Added by HD Satelit / Monea Software (1614)

### Source files with our copyright line (930)

- **`./`** (1): `boxbranding.py`
- **`HDSatelit/`** (3): `bootlogo_osd.py`, `hds_bootlogo.py`, `skin.xml`
- **`audit/probe/`** (4): `probe_asistenta5_corelare.py`, `regresie_osd.py`, `test_receptor_1.py`, `test_receptor_3.py`
- **`lib/base/`** (5): `hdsdm920.h`, `hdsfinalredare.h`, `hdsjurnal.cpp`, `hdsjurnal.h`, `xmltree.h`
- **`lib/driver/`** (3): `hdsconsolacitire.h`, `rcmapper.cpp`, `rcmapper.h`
- **`lib/dvb/`** (41): `dvbapi_compat.h`, `hdsait.cpp`, `hdsait.h`, `hdscalitate.h`, `hdscedare.h`, `hdscitirifrontend.h`, `hdsepgloc.h`, `hdsepgpoarta.h`, `hdsfastscan.cpp`, `hdsfastscan.h`, `hdsfastscantabele.cpp`, `hdsfastscantabele.h`, `hdsgrad.h`, `hdsjurnaldecodor.cpp`, `hdsjurnaldecodor.h`, `hdsjurnaltuner.cpp`, `hdsjurnaltuner.h`, `hdslistetext.h`, `hdsmultistream.h`, `hdspazademux.cpp`, `hdspazademux.h`, `hdspazaphi.h`, `hdspazavideo.h`, `hdsretea.cpp`, `hdsretea.h`, `hdsrotire.cpp`, `hdsrotire.h`, `hdsscanreguli.h`, `hdsspectru.cpp`, `hdsspectru.h`, `hdsspectru_tabele.h`, `hdsstatdvb5.h`, `hdst2mi.h`, `hdsteletext.cpp`, `hdsteletext.h`, `hdsterestru.h`, `hdstipales.h`, `hdsunicable.h`, `hdsurmamotor.cpp`, `hdsurmamotor.h`, `hdsvct.h`
- **`lib/dvb_ci/`** (5): `dvbci_hds_compat.h`, `hdscica.h`, `hdscicale.h`, `hdsdatetimeci.h`, `hdstsmux.h`
- **`lib/gdi/`** (12): `desennetezit.cpp`, `desennetezit.h`, `ecranpornire.cpp`, `ecranpornire.h`, `emvi.cpp`, `emvi.h`, `hdsanimatie.cpp`, `hdsanimatie.h`, `hdsgpu.cpp`, `hdsgpu.h`, `mpeg2intra.cpp`, `mpeg2intra.h`
- **`lib/gui/`** (2): `ehdsteletext.cpp`, `ehdsteletext.h`
- **`lib/python/`** (5): `HdsEnigmaCompat.py`, `Scheduler.py`, `crypt.py`, `imp.py`, `spwd.py`
- **`lib/python/Components/`** (357): `DishMath.py`, `Genres.py`, `HdsAccel2D.py`, `HdsAccesCanale.py`, `HdsAccesSsh.py`, `HdsActualizari.py`, `HdsAdaptariPluginuri.py`, `HdsAdaptorModule.py`, `HdsAfisaj.py`, `HdsAfisajColor.py`, `HdsAfisajCompat.py`, `HdsAfisajDate.py`, `HdsAfisajLitere.py`, `HdsAfisajPersonaj.py`, `HdsAfisajRandare.py`, `HdsAfisajScena.py`, `HdsAjutor.py`, `HdsAlimentare.py`, `HdsAltPython.py`, `HdsAnalizaFlux.py`, `HdsAnimatiiFerestre.py`, `HdsAnuntStocare.py`, `HdsAparateRetea.py`, `HdsAplicatii.py`, `HdsAplicatiiStick.py`, `HdsAsistenta.py`, `HdsAsistentaBroker.py`, `HdsAsistentaCatalog.py`, `HdsAsistentaControl.py`, `HdsAsistentaFlux.py`, `HdsAspectFilm.py`, `HdsAspectLista.py`, `HdsBazaCanale.py`, `HdsBazaPornire.py`, `HdsBetaTester.py`, `HdsBibliotecaLipsa.py`, `HdsBluetooth.py`, `HdsBluetoothSunet.py`, `HdsBoxInfoModele.py`, `HdsBucheteOrfane.py`, `HdsCalitateImagine.py`, `HdsCampText.py`, `HdsCanalTinut.py`, `HdsCapLista.py`, `HdsCapturi.py`, `HdsCarusel.py`, `HdsCaruselDemux.py`, `HdsCaruselServer.py`, `HdsCautaSetari.py`, `HdsCautaSetariAnunt.py`, `HdsCautareOarba.py`, `HdsCeas.py`, `HdsCeasHttps.py`, `HdsCheiPublice.py`, `HdsCodorMpeg2.py`, `HdsComutareRetea.py`, `HdsConfigurareTraducere.py`, `HdsControlParental.py`, `HdsCopieImagine.py`, `HdsCopieSetari.py`, `HdsCulegereCanale.py`, `HdsCulegereTotala.py`, `HdsCuratenie.py`, `HdsCursorLista.py`, `HdsDabUsb.py`, `HdsDale.py`, `HdsDecodare.py`, `HdsDecodorWeb.py`, `HdsDeschidereAmanata.py`, `HdsDespreFilm.py`, `HdsDiagnostic.py`, `HdsDiscuri.py`, `HdsDispozitiveIntrare.py`, `HdsDosareInregistrari.py`, `HdsDreamboxIon.py`, `HdsDriverLipsa.py`, `HdsDvbIDate.py`, `HdsDvbIIncercare.py`, `HdsDvbILegare.py`, `HdsDvbIRegistru.py`, `HdsDvbIRezerva.py`, `HdsDvbISetari.py`, `HdsDvbISurse.py`, `HdsEcm.py`, `HdsEcranNegru.py`, `HdsEcranePornire.py`, `HdsEditorCanale.py`, `HdsEditorCanaleDate.py`, `HdsEditorCanaleUnelte.py`, `HdsEditorSateliti.py`, `HdsEditorSigle.py`, `HdsEgalizator.py`, `HdsEnigmaCompat.py`, `HdsEpgDatLimbi.py`, `HdsEpgSalvare.py`, `HdsExtensiiLucru.py`, `HdsFavorite.py`, `HdsFbc.py`, `HdsFbcFaraSincron.py`, `HdsFbcMutare.py`, `HdsFilmRedare.py`, `HdsFirPluginuri.py`, `HdsFisierSigur.py`, `HdsFontInterfata.py`, `HdsFonturiGoogle.py`, `HdsForumReceptor.py`, `HdsFunctii.py`, `HdsFunctiiImagine.py`, `HdsFundalPro.py`, `HdsFurnizori.py`, `HdsFusTara.py`, `HdsGalerieSigle.py`, `HdsGasireSemnal.py`, `HdsGhidGrila.py`, `HdsGhidInternet.py`, `HdsGrade.py`, `HdsHbbtv.py`, `HdsHbbtvAplicatii.py`, `HdsHbbtvPornire.py`, `HdsHdmiDate.py`, `HdsImagineDupaPlayer.py`, `HdsImagineOnline.py`, `HdsImportAltaImagine.py`, `HdsImportExtra.py`, `HdsImportRetea.py`, `HdsImportSurse.py`, `HdsIndexCanale.py`, `HdsInformatiiCanal.py`, `HdsInformatiiTabel.py`, `HdsInregistrariProgramate.py`, `HdsInterfeteCam.py`, `HdsIptv4K.py`, `HdsIptvAdrese.py`, `HdsIptvCitire.py`, `HdsIptvClient.py`, `HdsIptvEpg.py`, `HdsIptvFisier.py`, `HdsIptvFullHd.py`, `HdsIptvLucru.py`, `HdsIptvReconectare.py`, `HdsIptvRedare.py`, `HdsIptvSeriale.py`, `HdsIptvSigle.py`, `HdsIptvSubtitrari.py`, `HdsIptvSurse.py`, `HdsIptvTransfer.py`, `HdsIpv6.py`, `HdsIstoricCanale.py`, `HdsIstoricSemnal.py`, `HdsJurnal.py`, `HdsJurnalAfisaj.py`, `HdsJurnalInregistrari.py`, `HdsJurnalModul.py`, `HdsJurnalSistem.py`, `HdsJurnalTuner.py`, `HdsJurnalVersiuni.py`, `HdsJurnalZapAudio.py`, `HdsJurnalZapFlux.py`, `HdsJurnale.py`, `HdsJurnaleSloturi.py`, `HdsLamedbSalvare.py`, `HdsLatimeText.py`, `HdsLedSigla.py`, `HdsLicente.py`, `HdsLimbaEpg.py`, `HdsLimbaRestaurare.py`, `HdsLimbaTara.py`, `HdsLimiteTuner.py`, `HdsListaSetari.py`, `HdsListeCabluTerestru.py`, `HdsListeInternet.py`, `HdsListeText.py`, `HdsLnb.py`, `HdsLnbAplicare.py`, `HdsLocInregistrari.py`, `HdsLocul.py`, `HdsLoculInternet.py`, `HdsLocuriLista.py`, `HdsMabrSetari.py`, `HdsMargini.py`, `HdsMarimeText.py`, `HdsMarireText.py`, `HdsMasuraZap.py`, `HdsMedia.py`, `HdsMemorieDriver.py`, `HdsMeniuOrdine.py`, `HdsModSigur.py`, `HdsModulNepornit.py`, `HdsModulPropriu.py`, `HdsModuleAcces.py`, `HdsModuleLipsa.py`, `HdsMontareDiscuri.py`, `HdsMotorComenzi.py`, `HdsMotorPlafon.py`, `HdsMotorPozitie.py`, `HdsMotorStare.py`, `HdsMotorTuner.py`, `HdsMotorViteza.py`, `HdsMouseEcran.py`, `HdsMouseFileCommander.py`, `HdsMouseUsb.py`, `HdsMozaic.py`, `HdsMultumiri.py`, `HdsMutareSetari.py`, `HdsNavigator.py`, `HdsNeoBoot.py`, `HdsNumeStandard.py`, `HdsOarbaVuplus.py`, `HdsOcrLimbaGhicita.py`, `HdsOcrModele.py`, `HdsOcrSubtitrari.py`, `HdsOperatoriSatelit.py`, `HdsOprireAutomata.py`, `HdsPachete.py`, `HdsPacheteDTH.py`, `HdsPachetePornire.py`, `HdsParolaLocala.py`, `HdsParteaDoua.py`, `HdsPartiTema.py`, `HdsPasiDecriptare.py`, `HdsPazaBara.py`, `HdsPazaModel.py`, `HdsPazaScripturi.py`, `HdsPazaWifi.py`, `HdsPaznic.py`, `HdsPiconBare.py`, `HdsPiconInstalare.py`, `HdsPictogramaBare.py`, `HdsPisteCanale.py`, `HdsPisteLimbi.py`, `HdsPlacaVuplus.py`, `HdsPlatforma.py`, `HdsPluginExtern.py`, `HdsPluginuriExterne.py`, `HdsPluginuriImagine.py`, `HdsPlural.py`, `HdsPornireMultipla.py`, `HdsPortal.py`, `HdsPorturi.py`, `HdsPrimaImagine.py`, `HdsProcFundal.py`, `HdsProcesor.py`, `HdsProcesorRaport.py`, `HdsPycRamase.py`, `HdsPython2.py`, `HdsPython2Compat.py`, `HdsPython2Traducere.py`, `HdsQr.py`, `HdsQrRapoarte.py`, `HdsRadacinaUsb.py`, `HdsRadioAnaliza.py`, `HdsRadioDate.py`, `HdsRadioDesen.py`, `HdsRadioMeniu.py`, `HdsRadioOnline.py`, `HdsRadioSetari.py`, `HdsRaportCanal.py`, `HdsRdsText.py`, `HdsRecuperare.py`, `HdsRedenumireBuchet.py`, `HdsRedenumireCanal.py`, `HdsReglajeImagine.py`, `HdsReinstalare.py`, `HdsReleuVideo.py`, `HdsReparaBuchete.py`, `HdsResetareFabrica.py`, `HdsRetea.py`, `HdsReteaProtocoale.py`, `HdsReteaSmb.py`, `HdsReteaUnealta.py`, `HdsRetele.py`, `HdsRezolutieTv.py`, `HdsSageti.py`, `HdsSalvareLista.py`, `HdsSamba.py`, `HdsSatelitiImagine.py`, `HdsScanareUltima.py`, `HdsScreensavere.py`, `HdsSemnatura.py`, `HdsSemnaturaPornire.py`, `HdsSemneBaza.py`, `HdsServiceListSablon.py`, `HdsSetariDinCopie.py`, `HdsSetariSunet.py`, `HdsSincronRadio.py`, `HdsSkinuri.py`, `HdsSoftCsa.py`, `HdsSportAzi.py`, `HdsSrvid.py`, `HdsStandbyTv.py`, `HdsStareMeniu.py`, `HdsStareOsd.py`, `HdsStareRetea.py`, `HdsStocare.py`, `HdsStocareDisc.py`, `HdsStocareMontare.py`, `HdsStocareRetea.py`, `HdsStreamRelay.py`, `HdsSubtitrareLipsa.py`, `HdsSubtitrariAspect.py`, `HdsSubtitrariFilm.py`, `HdsSunet.py`, `HdsSursaPachet.py`, `HdsSurseOpkg.py`, `HdsSwap.py`, `HdsTastaturaUsb.py`, `HdsTasteRapide.py`, `HdsTelecomenziDate.py`, `HdsTeletext.py`, `HdsTeletextCopie.py`, `HdsTemaExterna.py`, `HdsTemaStergere.py`, `HdsTemaTv.py`, `HdsTemeSuprascrise.py`, `HdsTemporizare.py`, `HdsTextUnicode.py`, `HdsTexteOfgwrite.py`, `HdsTimpCautare.py`, `HdsTraducereEpg.py`, `HdsTraducereSubtitrari.py`, `HdsTraducereTeletext.py`, `HdsTraducereTexte.py`, `HdsTranscodareInfo.py`, `HdsTransmisie.py`, `HdsTunerAspect.py`, `HdsTunerB.py`, `HdsTunerRezerva.py`, `HdsTwistedCompat.py`, `HdsUltimaImagine.py`, `HdsUnicableConfig.py`, `HdsVarianteCanal.py`, `HdsVentilator.py`, `HdsVod.py`, `HdsVodDisc.py`, `HdsVodPoze.py`, `HdsVodPozitii.py`, `HdsVodServere.py`, `HdsVorbire.py`, `HdsVorbireAudio.py`, `HdsVorbireTV.py`, `HdsVpn.py`, `HdsVpnFurnizori.py`, `HdsVremea.py`, `HdsWidevine.py`, `HdsWidevineGoogle.py`, `HdsWifiCanale.py`, `HdsWlan.py`, `HdsYouTube.py`, `HdsYouTubeDale.py`, `HdsZgemma.py`, `International.py`, `NetworkTime.py`, `Opkg.py`, `QRCode.py`, `VideoOutput.py`, `WlanControl.py`, `WlanTools.py`
- **`lib/python/Components/Converter/`** (55): `EGExtraInfo.py`, `HdsCommon.py`, `HdsConvertoareStraine.py`, `HdsInfo.py`, `HdsInfoTehnice.py`, `HdsLang.py`, `HdsLang_ar.py`, `HdsLang_bg.py`, `HdsLang_ca.py`, `HdsLang_cs.py`, `HdsLang_da.py`, `HdsLang_de.py`, `HdsLang_el.py`, `HdsLang_es.py`, `HdsLang_et.py`, `HdsLang_fa.py`, `HdsLang_fi.py`, `HdsLang_fr.py`, `HdsLang_fy.py`, `HdsLang_gl.py`, `HdsLang_he.py`, `HdsLang_hr.py`, `HdsLang_hu.py`, `HdsLang_id.py`, `HdsLang_is.py`, `HdsLang_it.py`, `HdsLang_ku.py`, `HdsLang_lt.py`, `HdsLang_lv.py`, `HdsLang_mk.py`, `HdsLang_nb.py`, `HdsLang_nl.py`, `HdsLang_nn.py`, `HdsLang_pl.py`, `HdsLang_pt.py`, `HdsLang_pt_br.py`, `HdsLang_ro.py`, `HdsLang_ru.py`, `HdsLang_sk.py`, `HdsLang_sl.py`, `HdsLang_sq.py`, `HdsLang_sr.py`, `HdsLang_sv.py`, `HdsLang_th.py`, `HdsLang_tr.py`, `HdsLang_uk.py`, `HdsLang_uz.py`, `HdsLang_vi.py`, `HdsLang_zh_cn.py`, `HdsLang_zh_hk.py`, `HdsReteaPictograma.py`, `HdsSignal.py`, `HdsTransmis.py`, `XmlMultiContent.py`, `genre.py`
- **`lib/python/Components/HdsSubtitrariInternet/`** (11): `Makefile.am`, `__init__.py`, `conturi.py`, `ecrane.py`, `film.py`, `identificare.py`, `limbi.py`, `lucru.py`, `retea.py`, `salvare.py`, `tv.py`
- **`lib/python/Components/HdsSubtitrariInternet/surse/`** (5): `Makefile.am`, `__init__.py`, `opensubtitles.py`, `subdl.py`, `subsro.py`
- **`lib/python/Components/Renderer/`** (7): `HdsRandatoareStraine.py`, `LcdPicon.py`, `NextEvent.py`, `RollerCharLCD.py`, `RollerCharLCDLong.py`, `RunningText.py`, `ZZPicon.py`
- **`lib/python/Components/Sources/`** (2): `OnlineUpdate.py`, `PTSCurrentService.py`
- **`lib/python/Hds/`** (1): `__init__.py`
- **`lib/python/Hds/DabT2/`** (34): `__init__.py`, `abertis.py`, `aspect.py`, `bataie.py`, `buchete.py`, `captura.py`, `compat.py`, `coordonator.py`, `detector.py`, `ecrane.py`, `fir.py`, `fundal.py`, `imagine.py`, `intrare.py`, `jurnal.py`, `lamedb.py`, `limba.py`, `liste.py`, `marcaj.py`, `nume.py`, `pornire.py`, `proces.py`, `profil.py`, `receptie.py`, `releu_http.py`, `scanare.py`, `server8001.py`, `sesiuni8001.py`, `straine.py`, `sunet_software.py`, `surse.py`, `text_dvb.py`, `tuner.py`, `versiune.py`
- **`lib/python/Hds/DabT2/dab/motor/`** (3): `dab_edi.py`, `eti.py`, `releu_dab.py`
- **`lib/python/Hds/DabT2/t2/bin/`** (1): `t2mi_decap.c`
- **`lib/python/Hds/DabT2/t2/motor/`** (2): `releu_t2.py`, `t2mi.py`
- **`lib/python/Plugins/Extensions/HdsCutListEditor/`** (2): `__init__.py`, `plugin.py`
- **`lib/python/Plugins/Extensions/HdsImportSetari/`** (2): `__init__.py`, `plugin.py`
- **`lib/python/Plugins/Extensions/HdsLcdTv/`** (3): `__init__.py`, `lcdtv.py`, `plugin.py`
- **`lib/python/Plugins/Extensions/HdsNavigator/`** (9): `__init__.py`, `campuri.py`, `ecrane.py`, `hds-hbbtv.js`, `intrare_cam.py`, `lansator.py`, `plugin.py`, `qr.py`, `setari.py`
- **`lib/python/Plugins/Extensions/HdsWebControl/`** (141): `__init__.py`, `accel_web.py`, `acces_conditionat_web.py`, `acces_extern.py`, `acces_ssh_web.py`, `acces_web.py`, `actualizare_web.py`, `actualizari_web.py`, `afisaj_web.py`, `ajutor_web.py`, `alimentare_web.py`, `antena_web.py`, `aparate_web.py`, `aplicatii_tv_web.py`, `aplicatii_web.py`, `asistenta_web.py`, `asociere.py`, `aspect_web.py`, `betatester_web.py`, `bluetooth_web.py`, `cadru_web.py`, `calitate_imagine_web.py`, `canal_info_web.py`, `canale_web.py`, `captura_sigura.py`, `cauta_setari_web.py`, `cautare_web.py`, `ceas_web.py`, `ci_web.py`, `copie_imagine_web.py`, `copie_setari_web.py`, `culegere_canale_web.py`, `culori_web.py`, `dab_usb_web.py`, `dabt2_web.py`, `descarcare_subtitrari_web.py`, `despre_film_web.py`, `disc_web.py`, `diseqc_web.py`, `ecran_negru_web.py`, `ecran_pornire_web.py`, `editor_canale_web.py`, `egalizator_web.py`, `extensii_web.py`, `filme_seriale_web.py`, `filme_web.py`, `fisiere_core.py`, `fisiere_pagina.py`, `fisiere_web.py`, `flux_transcodare_web.py`, `font_interfata_web.py`, `forum_web.py`, `functii_imagine_web.py`, `galerie_sigle_web.py`, `ghid_internet_web.py`, `ghid_web.py`, `hds-player.js`, `hds-sunet.js`, `hds-worker.js`, `https_web.py`, `imagine_online_web.py`, `informatii_tabel_web.py`, `informatii_web.py`, `internet_web.py`, `intrari_web.py`, `jurnal_web.py`, `jurnale_sistem_web.py`, `licente_web.py`, `limba_interfata_web.py`, `limbi_web.py`, `liste_internet_web.py`, `locuri_retea_web.py`, `margini_web.py`, `marime_text_web.py`, `media_web.py`, `meniu_comun_web.py`, `meniu_pagini_web.py`, `meniu_web.py`, `mod_sigur_web.py`, `montare_web.py`, `mouse-ecran.js`, `mouse_web.py`, `mozaic_web.py`, `navigator_web.py`, `oarba_web.py`, `ocr_limbi_web.py`, `osd_strat.py`, `parental_web.py`, `partea_doua_web.py`, `pasi_decriptare_web.py`, `paza_model_web.py`, `paznic_web.py`, `piconuri_web.py`, `piste.py`, `player.js`, `playlisturi_web.py`, `plugin.py`, `portal_web.py`, `porturi_web.py`, `procesor_web.py`, `radio_live_web.py`, `radio_online_web.py`, `radio_web.py`, `reglaje_imagine_web.py`, `resetare_web.py`, `retea_web.py`, `scanare_import_web.py`, `scanare_liste_web.py`, `scanare_web.py`, `screensaver_web.py`, `setari_copie_web.py`, `setari_deschise_web.py`, `setari_web.py`, `sloturi_web.py`, `sport_azi_web.py`, `standby_tv_web.py`, `stare_retea_web.py`, `stocare_web.py`, `subtitrari_film_web.py`, `subtitrari_web.py`, `sunet_web.py`, `telecomenzi_web.py`, `teletext_web.py`, `tema_export.py`, `tema_tv_web.py`, `temporizatoare_web.py`, `traducere_configurare_web.py`, `traducere_hbbtv_web.py`, `traducere_pagini.py`, `traducere_subtitrari_web.py`, `tv_web.py`, `unelte_retea_web.py`, `ventilator_web.py`, `vezi_live_web.py`, `video_web.py`, `volum_intarziere_web.py`, `vorbire_web.py`, `vpn_furnizori_web.py`, `vpn_web.py`, `vremea_web.py`, `youtube_web.py`
- **`lib/python/Plugins/Extensions/HdsWebControl/tv-wasm/`** (2): `construieste-decodor-wasm.sh`, `hdsdec.c`
- **`lib/python/Plugins/Extensions/PicturePlayer/`** (1): `ui.py`
- **`lib/python/Plugins/SystemPlugins/HdsDvbI/`** (2): `__init__.py`, `plugin.py`
- **`lib/python/Plugins/SystemPlugins/Videomode/`** (1): `VideoSetup.py`
- **`lib/python/Screens/`** (134): `ButtonSetup.py`, `CamInfo.py`, `CamSetup.py`, `CleanupWizard.py`, `ConfigLNB.py`, `DVD.py`, `FontSetup.py`, `HdsAccesSsh.py`, `HdsActualizari.py`, `HdsAdaugaFeed.py`, `HdsAfisaj.py`, `HdsAfisajColor.py`, `HdsAjutor.py`, `HdsAnuntRetea.py`, `HdsAnuntStocare.py`, `HdsAplicatii.py`, `HdsAsistenta.py`, `HdsAsistentaSemn.py`, `HdsBetaTester.py`, `HdsBluetooth.py`, `HdsCalitateImagine.py`, `HdsCautaSetari.py`, `HdsCautareCanale.py`, `HdsComunPrincipal.py`, `HdsCopieImagine.py`, `HdsCopieSetari.py`, `HdsCrashlogAutoSubmit.py`, `HdsCulegereTotala.py`, `HdsDabUsb.py`, `HdsDescarcareSubtitrari.py`, `HdsDespreFilm.py`, `HdsDishMotor.py`, `HdsDvbI.py`, `HdsDvbMABR.py`, `HdsEcranNegru.py`, `HdsEcranPornire.py`, `HdsEcranRadio.py`, `HdsEditorCanale.py`, `HdsEditorCanaleLegatura.py`, `HdsEditorCanaleLogica.py`, `HdsEditorCanaleUnelte.py`, `HdsEgalizator.py`, `HdsExtensii.py`, `HdsFilmeSeriale.py`, `HdsFontInterfata.py`, `HdsFonturi.py`, `HdsForumReceptor.py`, `HdsFundalPro.py`, `HdsGalerieSigle.py`, `HdsGhidGrafic.py`, `HdsGhidInternet.py`, `HdsHdmiInfo.py`, `HdsImagineOnline.py`, `HdsImportSetari.py`, `HdsIptv4K.py`, `HdsIptvArhiva.py`, `HdsIptvIncarcare.py`, `HdsIstoricCanale.py`, `HdsJurnalVersiuni.py`, `HdsJurnaleSloturi.py`, `HdsLicente.py`, `HdsListeImplicite.py`, `HdsListeInternet.py`, `HdsLocInregistrari.py`, `HdsLocul.py`, `HdsLocuriRetea.py`, `HdsModSigur.py`, `HdsMontareDiscuri.py`, `HdsMozaic.py`, `HdsNavigatorWeb.py`, `HdsOcrLimbi.py`, `HdsParteaDoua.py`, `HdsPazaModel.py`, `HdsPaznic.py`, `HdsPiconuri.py`, `HdsPisteLimbi.py`, `HdsPornireMultipla.py`, `HdsProcesor.py`, `HdsQrRapoarte.py`, `HdsRadioOnline.py`, `HdsRaportCanal.py`, `HdsReteaStandard.py`, `HdsRezolutieTv.py`, `HdsScanareFluxuri.py`, `HdsScreensaver.py`, `HdsSkinSetari.py`, `HdsSoftwareUpdate.py`, `HdsSportAzi.py`, `HdsStartWizard.py`, `HdsSubtitrariAspect.py`, `HdsSubtitrariFilm.py`, `HdsTelecomenzi.py`, `HdsTeletext.py`, `HdsTemaInterfata.py`, `HdsTraducereSubtitrari.py`, `HdsTransmisie.py`, `HdsUnelteRetea.py`, `HdsVorbire.py`, `HdsVpn.py`, `HdsVpnBara.py`, `HdsVpnFurnizor.py`, `HdsVremea.py`, `HdsWebControlSetup.py`, `HdsWebTelefon.py`, `HdsYouTube.py`, `Information.py`, `IptvSetup.py`, `LogManager.py`, `MediaPlayer.py`, `NetworkServices.py`, `OSDCalibration.py`, `Opkg.py`, `PicturePlayer.py`, `PositionerSetup.py`, `Processing.py`, `Satfinder.py`, `ScanerCablu.py`, `ScanerMaiMultiSateliti.py`, `ScanerOarba.py`, `ScanerSatelit.py`, `ScanerTerestru.py`, `ScreenSaver.py`, `SecondInfoBar.py`, `SkinSelection.py`, `SkinSelector.py`, `SwapManager.py`, `TagEditor.py`, `TaskList.py`, `TempFanControl.py`, `Time.py`, `Timers.py`, `Toast.py`, `VideoSetup.py`, `WlanSetup.py`
- **`lib/python/Tools/`** (24): `Alternatives.py`, `BlockDevices.py`, `CIHelper.py`, `Conversions.py`, `CopyFiles.py`, `CountryCodes.py`, `FallbackTimer.py`, `HdsJurnalInterfata.py`, `HdsNumeData.py`, `HdsPreFlight.py`, `Hex2strColor.py`, `IO.py`, `Log.py`, `LogConfig.py`, `MediuImagine.py`, `MultiBoot.py`, `OEMInfo.py`, `PiconResolver.py`, `ScaledSkin.py`, `StbHardware.py`, `TextBoundary.py`, `Trashcan.py`, `Unicable.py`, `Weatherinfo.py`
- **`lib/service/`** (18): `hdsegalizator.cpp`, `hdsegalizator.h`, `hdsegalizator_dsp.h`, `hdsegalizator_flux.h`, `hdsfluxhttp.cpp`, `hdsfluxhttp.h`, `hdshttp.h`, `hdshttporigin.h`, `hdsjurnalzap.cpp`, `hdsjurnalzap.h`, `hdsradioonline.h`, `hdsreleut2.h`, `hdssoftcsapornire.h`, `hdssubimagini.cpp`, `hdssubimagini.h`, `hdssubtitrareceas.h`, `hdssubtitraresincron.h`, `hdsvorbire.h`
- **`pluginuri-feed/DabTerestru/`** (8): `__init__.py`, `date.py`, `ecran.py`, `locuri.py`, `motor.py`, `plugin.py`, `proces.py`, `releu.py`
- **`pluginuri-feed/RadioOnline/`** (14): `__init__.py`, `adrese.py`, `date.py`, `director.py`, `ecran.py`, `ecran_filtre.py`, `ecran_lista.py`, `filtre.py`, `locuri.py`, `motor.py`, `plugin.py`, `releu.py`, `sigle.py`, `web.py`
- **`po/`** (4): `bg.po`, `ro.po`, `sq.po`, `uz.po`
- **`tools/`** (10): `file_origins.py`, `hds-actualizare-intrerupta.py`, `hds-blindscan.c`, `hds-nume-local`, `hds-nume-local.py`, `hds-raport.sh.in`, `hds-rezerva-ecran.py`, `hds-rezerva-litere.py`, `hds-rezerva.sh.in`, `hds-wifi-reporneste.py`

### Pictures, fonts, data, build and documentation files of our folders (684)

- **`./`** (4): `.gitattributes`, `CREDITS`, `FILES.md`, `README.md`
- **`HDSatelit/`** (6): `hds_rc.png`, `hds_rc_glow_colors.png`, `hds_rc_glow_dpad.png`, `hds_rc_glow_ok.png`, `picon_default.png`, `prev.png`
- **`HDSatelit/afisaj-color/400x240/`** (9): `canal.png`, `ceas.png`, `fond.png`, `lucru.png`, `nivel.png`, `rec.png`, `semnal.png`, `usb.png`, `volum.png`
- **`HDSatelit/afisaj-color/400x240/personaj/`** (14): `adoarme.png`, `ameteste.png`, `casca.png`, `cauta_semnalul.png`, `clipit.png`, `doarme.png`, `face_cu_ochiul.png`, `inchide_ochii.png`, `priveste.png`, `rade.png`, `se_mira.png`, `se_trezeste.png`, `urmareste_volumul.png`, `zambeste.png`
- **`HDSatelit/afisaj-color/400x240/stari/`** (16): `00.png`, `01.png`, `02.png`, `03.png`, `04.png`, `05.png`, `06.png`, `07.png`, `08.png`, `09.png`, `10.png`, `11.png`, `12.png`, `13.png`, `14.png`, `15.png`
- **`HDSatelit/afisaj-color/480x320/`** (9): `canal.png`, `ceas.png`, `fond.png`, `lucru.png`, `nivel.png`, `rec.png`, `semnal.png`, `usb.png`, `volum.png`
- **`HDSatelit/afisaj-color/480x320/personaj/`** (14): `adoarme.png`, `ameteste.png`, `casca.png`, `cauta_semnalul.png`, `clipit.png`, `doarme.png`, `face_cu_ochiul.png`, `inchide_ochii.png`, `priveste.png`, `rade.png`, `se_mira.png`, `se_trezeste.png`, `urmareste_volumul.png`, `zambeste.png`
- **`HDSatelit/afisaj-color/480x320/stari/`** (16): `00.png`, `01.png`, `02.png`, `03.png`, `04.png`, `05.png`, `06.png`, `07.png`, `08.png`, `09.png`, `10.png`, `11.png`, `12.png`, `13.png`, `14.png`, `15.png`
- **`HDSatelit/afisaj-color/orbita/400x240/`** (99): `00-personaj-e019-character.png`, `00-personaj-fond.png`, `01-ceas-e020-icon.png`, `01-ceas-e036-separator.png`, `01-ceas-fond.png`, `02-ceas-vreme-e025-icon.png`, `02-ceas-vreme-e028-panel.png`, `02-ceas-vreme-e030-icon.png`, `02-ceas-vreme-fond.png`, `03-canal-cinci-cifre-e025-progress-track.png`, `03-canal-cinci-cifre-e026-progress-fill.png`, `03-canal-cinci-cifre-e027-progress-cap.png`, `03-canal-cinci-cifre-e030-separator.png`, `03-canal-cinci-cifre-fond-fara-picon.png`, `03-canal-cinci-cifre-fond.png`, `03-canal-e019-panel.png`, `03-canal-e021-separator.png`, `03-canal-e023-progress-track.png`, `03-canal-e024-progress-fill.png`, `03-canal-e025-progress-cap.png`, `03-canal-e028-separator.png`, `03-canal-fara-epg-e021-panel.png`, `03-canal-fara-epg-e023-picon-decoration.png`, `03-canal-fara-epg-e025-icon.png`, `03-canal-fara-epg-fond-fara-picon.png`, `03-canal-fara-epg-fond.png`, `03-canal-fara-picon-mut-e017-icon.png`, `03-canal-fara-picon-mut-e025-picon-decoration.png`, `03-canal-fara-picon-mut-e031-progress-track.png`, `03-canal-fara-picon-mut-e032-progress-fill.png`, `03-canal-fara-picon-mut-e033-progress-cap.png`, `03-canal-fara-picon-mut-e037-separator.png`, `03-canal-fara-picon-mut-fond.png`, `03-canal-fond-fara-picon.png`, `03-canal-fond.png`, `04-vreme-date-vechi-e015-icon.png`, `04-vreme-date-vechi-e019-separator.png`, `04-vreme-date-vechi-e021-panel.png`, `04-vreme-date-vechi-e024-icon.png`, `04-vreme-date-vechi-e030-panel.png`, `04-vreme-date-vechi-fond.png`, `04-vreme-e024-icon.png`, `04-vreme-e034-panel.png`, `04-vreme-e038-icon.png`, `04-vreme-e046-panel.png`, `04-vreme-e050-icon.png`, `04-vreme-fond.png`, `05-volum-e027-icon.png`, `05-volum-e033-progress-track.png`, `05-volum-e034-progress-fill.png`, `05-volum-e035-progress-overlay.png`, `05-volum-fond.png`, `05-volum-mut-e025-icon.png`, `05-volum-mut-e035-progress-track.png`, `05-volum-mut-e036-progress-fill.png`, `05-volum-mut-e037-progress-overlay.png`, `05-volum-mut-e038-progress-overlay.png`, `05-volum-mut-e039-progress-overlay.png`, `05-volum-mut-e040-progress-overlay.png`, `05-volum-mut-e041-progress-overlay.png`, `05-volum-mut-e042-progress-overlay.png`, `05-volum-mut-e043-progress-overlay.png`, `05-volum-mut-e044-progress-overlay.png`, `05-volum-mut-e045-progress-overlay.png`, `05-volum-mut-fond.png`, `06-schimbare-canal-e022-panel.png`, `06-schimbare-canal-e024-picon-decoration.png`, `06-schimbare-canal-fond-fara-picon.png`, `06-schimbare-canal-fond.png`, `07-inregistrare-e013-icon.png`, `07-inregistrare-e017-separator.png`, `07-inregistrare-esuata-e015-separator.png`, `07-inregistrare-esuata-e018-icon.png`, `07-inregistrare-esuata-e030-separator.png`, `07-inregistrare-esuata-fond.png`, `07-inregistrare-fond.png`, `07-lipsa-semnal-e017-separator.png`, `07-lipsa-semnal-e020-icon.png`, `07-lipsa-semnal-fond.png`, `08-asteptare-e016-status.png`, `08-asteptare-e024-separator.png`, `08-asteptare-fond.png`, `09-actualizare-e013-icon.png`, `09-actualizare-e019-progress-track.png`, `09-actualizare-e020-progress-fill.png`, `09-actualizare-fara-procent-e019-icon.png`, `09-actualizare-fara-procent-e023-icon.png`, `09-actualizare-fara-procent-e029-separator.png`, `09-actualizare-fara-procent-fond.png`, `09-actualizare-fond.png`, `09-antena-e019-icon.png`, `09-antena-e026-icon.png`, `09-antena-e042-separator.png`, `09-antena-fond.png`, `manifest.json`, `vreme-nori.png`, `vreme-partial.png`, `vreme-ploaie.png`, `vreme-zapada.png`
- **`HDSatelit/afisaj-color/orbita/480x320/`** (92): `00-personaj-e020-panel.png`, `00-personaj-e021-character.png`, `00-personaj-fond.png`, `01-ceas-e024-icon.png`, `01-ceas-fond.png`, `02-ceas-vreme-e020-panel.png`, `02-ceas-vreme-e022-icon.png`, `02-ceas-vreme-e033-icon.png`, `02-ceas-vreme-fond.png`, `03-canal-cinci-cifre-e018-panel.png`, `03-canal-cinci-cifre-e024-separator.png`, `03-canal-cinci-cifre-e026-progress-track.png`, `03-canal-cinci-cifre-e027-progress-fill.png`, `03-canal-cinci-cifre-e028-progress-cap.png`, `03-canal-cinci-cifre-fond-fara-picon.png`, `03-canal-cinci-cifre-fond.png`, `03-canal-e020-panel.png`, `03-canal-e022-picon-decoration.png`, `03-canal-e026-separator.png`, `03-canal-e029-progress-track.png`, `03-canal-e030-progress-fill.png`, `03-canal-e031-progress-cap.png`, `03-canal-fara-epg-e022-panel.png`, `03-canal-fara-epg-e024-picon-decoration.png`, `03-canal-fara-epg-e026-icon.png`, `03-canal-fara-epg-fond-fara-picon.png`, `03-canal-fara-epg-fond.png`, `03-canal-fara-picon-mut-e018-icon.png`, `03-canal-fara-picon-mut-e024-picon-decoration.png`, `03-canal-fara-picon-mut-e030-separator.png`, `03-canal-fara-picon-mut-e032-progress-track.png`, `03-canal-fara-picon-mut-e033-progress-fill.png`, `03-canal-fara-picon-mut-e034-progress-cap.png`, `03-canal-fara-picon-mut-fond.png`, `03-canal-fond-fara-picon.png`, `03-canal-fond.png`, `04-vreme-date-vechi-e015-icon.png`, `04-vreme-date-vechi-e027-icon.png`, `04-vreme-date-vechi-e033-panel.png`, `04-vreme-date-vechi-e036-icon.png`, `04-vreme-date-vechi-e042-panel.png`, `04-vreme-date-vechi-e045-icon.png`, `04-vreme-date-vechi-fond.png`, `04-vreme-e021-icon.png`, `04-vreme-e027-panel.png`, `04-vreme-e030-icon.png`, `04-vreme-e036-panel.png`, `04-vreme-e039-icon.png`, `04-vreme-fond.png`, `05-volum-e022-icon.png`, `05-volum-e034-progress-track.png`, `05-volum-e035-progress-fill.png`, `05-volum-e036-progress-overlay.png`, `05-volum-fond.png`, `05-volum-mut-e024-icon.png`, `05-volum-mut-e032-progress-track.png`, `05-volum-mut-e033-progress-fill.png`, `05-volum-mut-e034-progress-overlay.png`, `05-volum-mut-fond.png`, `06-schimbare-canal-e021-panel.png`, `06-schimbare-canal-e023-picon-decoration.png`, `06-schimbare-canal-fond-fara-picon.png`, `06-schimbare-canal-fond.png`, `07-inregistrare-e013-icon.png`, `07-inregistrare-e017-separator.png`, `07-inregistrare-esuata-e013-status.png`, `07-inregistrare-esuata-e016-icon.png`, `07-inregistrare-esuata-fond.png`, `07-inregistrare-fond.png`, `07-lipsa-semnal-e024-separator.png`, `07-lipsa-semnal-e027-icon.png`, `07-lipsa-semnal-fond.png`, `08-asteptare-e015-status.png`, `08-asteptare-e021-separator.png`, `08-asteptare-fond.png`, `09-actualizare-e018-icon.png`, `09-actualizare-e025-progress-track.png`, `09-actualizare-e026-progress-fill.png`, `09-actualizare-fara-procent-e028-icon.png`, `09-actualizare-fara-procent-e032-icon.png`, `09-actualizare-fara-procent-e042-separator.png`, `09-actualizare-fara-procent-fond.png`, `09-actualizare-fond.png`, `09-antena-e026-icon.png`, `09-antena-e036-icon.png`, `09-antena-e047-separator.png`, `09-antena-fond.png`, `manifest.json`, `vreme-nori.png`, `vreme-partial.png`, `vreme-ploaie.png`, `vreme-zapada.png`
- **`HDSatelit/afisaj-color/orbita/800x480/`** (93): `00-personaj-e018-panel.png`, `00-personaj-e019-character.png`, `00-personaj-fond.png`, `01-ceas-e025-icon.png`, `01-ceas-e037-separator.png`, `01-ceas-fond.png`, `02-ceas-vreme-e023-panel.png`, `02-ceas-vreme-e025-icon.png`, `02-ceas-vreme-e032-icon.png`, `02-ceas-vreme-fond.png`, `03-canal-cinci-cifre-e022-panel.png`, `03-canal-cinci-cifre-e028-progress-track.png`, `03-canal-cinci-cifre-e029-progress-fill.png`, `03-canal-cinci-cifre-e030-progress-cap.png`, `03-canal-cinci-cifre-e034-separator.png`, `03-canal-cinci-cifre-fond-fara-picon.png`, `03-canal-cinci-cifre-fond.png`, `03-canal-e022-panel.png`, `03-canal-e024-picon-decoration.png`, `03-canal-e027-progress-track.png`, `03-canal-e028-progress-fill.png`, `03-canal-e029-progress-cap.png`, `03-canal-e032-separator.png`, `03-canal-fara-epg-e026-panel.png`, `03-canal-fara-epg-e028-picon-decoration.png`, `03-canal-fara-epg-e030-icon.png`, `03-canal-fara-epg-fond-fara-picon.png`, `03-canal-fara-epg-fond.png`, `03-canal-fara-picon-mut-e017-icon.png`, `03-canal-fara-picon-mut-e023-picon-decoration.png`, `03-canal-fara-picon-mut-e028-progress-track.png`, `03-canal-fara-picon-mut-e029-progress-fill.png`, `03-canal-fara-picon-mut-e030-progress-cap.png`, `03-canal-fara-picon-mut-e033-separator.png`, `03-canal-fara-picon-mut-fond.png`, `03-canal-fond-fara-picon.png`, `03-canal-fond.png`, `04-vreme-date-vechi-e036-icon.png`, `04-vreme-date-vechi-e042-panel.png`, `04-vreme-date-vechi-e046-icon.png`, `04-vreme-date-vechi-e056-panel.png`, `04-vreme-date-vechi-fond.png`, `04-vreme-e036-icon.png`, `04-vreme-e043-panel.png`, `04-vreme-e047-icon.png`, `04-vreme-e054-panel.png`, `04-vreme-e058-icon.png`, `04-vreme-fond.png`, `05-volum-e028-icon.png`, `05-volum-e034-progress-track.png`, `05-volum-e035-progress-fill.png`, `05-volum-e036-progress-overlay.png`, `05-volum-fond.png`, `05-volum-mut-e028-icon.png`, `05-volum-mut-e034-progress-track.png`, `05-volum-mut-e035-progress-fill.png`, `05-volum-mut-e036-progress-overlay.png`, `05-volum-mut-e047-separator.png`, `05-volum-mut-fond.png`, `06-schimbare-canal-e024-panel.png`, `06-schimbare-canal-e026-picon-decoration.png`, `06-schimbare-canal-fond-fara-picon.png`, `06-schimbare-canal-fond.png`, `07-inregistrare-e017-icon.png`, `07-inregistrare-e022-separator.png`, `07-inregistrare-esuata-e017-icon.png`, `07-inregistrare-esuata-e023-separator.png`, `07-inregistrare-esuata-fond.png`, `07-inregistrare-fond.png`, `07-lipsa-semnal-e021-separator.png`, `07-lipsa-semnal-e024-icon.png`, `07-lipsa-semnal-fond.png`, `08-asteptare-e012-status.png`, `08-asteptare-e021-separator.png`, `08-asteptare-fond.png`, `09-actualizare-e017-icon.png`, `09-actualizare-e023-progress-track.png`, `09-actualizare-e024-progress-fill.png`, `09-actualizare-e027-separator.png`, `09-actualizare-fara-procent-e018-icon.png`, `09-actualizare-fara-procent-e022-icon.png`, `09-actualizare-fara-procent-e038-separator.png`, `09-actualizare-fara-procent-fond.png`, `09-actualizare-fond.png`, `09-antena-e023-icon.png`, `09-antena-e033-icon.png`, `09-antena-e046-separator.png`, `09-antena-fond.png`, `manifest.json`, `vreme-nori.png`, `vreme-partial.png`, `vreme-ploaie.png`, `vreme-zapada.png`
- **`HDSatelit/bar/`** (1): `pointer.png`
- **`HDSatelit/bs/`** (2): `edge.png`, `top.png`
- **`HDSatelit/display/`** (1): `skin_display.xml`
- **`HDSatelit/epg/`** (20): `BorderBottom.svg`, `BorderLeft.svg`, `BorderRight.svg`, `BorderTop.svg`, `CurrentEvent.svg`, `CurrentService.svg`, `OtherEvent.svg`, `OtherService.svg`, `RecordEvent.svg`, `SelectedBorderBottom.svg`, `SelectedBorderLeft.svg`, `SelectedBorderRight.svg`, `SelectedBorderTop.svg`, `SelectedCurrentEvent.svg`, `SelectedEvent.svg`, `SelectedRecordEvent.svg`, `SelectedZapEvent.svg`, `TimeLineDate.svg`, `TimeLineTime.svg`, `ZapEvent.svg`
- **`HDSatelit/icon/`** (2): `mute.png`, `vol.png`
- **`HDSatelit/icons/`** (2): `vpn-off.png`, `vpn-on.png`
- **`HDSatelit/liste/`** (67): `bifa_off.png`, `bifa_on.png`, `ceas_epgclock.png`, `ceas_epgclock_add.png`, `ceas_epgclock_post.png`, `ceas_epgclock_pre.png`, `ceas_epgclock_prepost.png`, `ext_actualizari_160.png`, `ext_actualizari_88.png`, `ext_altele_160.png`, `ext_altele_88.png`, `ext_emulatoare_160.png`, `ext_emulatoare_88.png`, `ext_extensii_160.png`, `ext_extensii_88.png`, `ext_fisier_160.png`, `ext_fisier_88.png`, `ext_liste_160.png`, `ext_liste_88.png`, `ext_sigle_160.png`, `ext_sigle_88.png`, `ext_sistem_160.png`, `ext_sistem_88.png`, `ext_skinuri_160.png`, `ext_skinuri_88.png`, `ext_surse_160.png`, `ext_surse_88.png`, `extensie.png`, `fisier_directory.png`, `fisier_file.png`, `fisier_movie.png`, `fisier_music.png`, `fisier_package.png`, `fisier_parent.png`, `fisier_picture.png`, `fisier_playlist.png`, `fisier_storage.png`, `fisier_text.png`, `lacat_lock.png`, `lacat_lockBouquet.png`, `lacat_unlock.png`, `lacat_unlockBouquet.png`, `linie.png`, `redare_forward.png`, `redare_pause.png`, `redare_play.png`, `redare_rewind.png`, `redare_stop.png`, `tasta_0.png`, `tasta_1.png`, `tasta_2.png`, `tasta_3.png`, `tasta_4.png`, `tasta_5.png`, `tasta_6.png`, `tasta_7.png`, `tasta_8.png`, `tasta_9.png`, `tasta_blue.png`, `tasta_green.png`, `tasta_info.png`, `tasta_menu.png`, `tasta_red.png`, `tasta_text.png`, `tasta_yellow.png`, `temporizator_disabled.png`, `transmis.png`
- **`HDSatelit/meniu/dala/`** (14): `aleasa-100.png`, `aleasa-105.png`, `aleasa-110.png`, `aleasa-115.png`, `aleasa-120.png`, `aleasa-125.png`, `aleasa-130.png`, `normala-100.png`, `normala-105.png`, `normala-110.png`, `normala-115.png`, `normala-120.png`, `normala-125.png`, `normala-130.png`
- **`HDSatelit/navigator/`** (24): `cadru_miniatura.png`, `coperta.png`, `disp_card.png`, `disp_dvd.png`, `disp_flash.png`, `disp_hdd.png`, `disp_net.png`, `disp_usb.png`, `mare_card.png`, `mare_directory.png`, `mare_dvd.png`, `mare_file.png`, `mare_flash.png`, `mare_hdd.png`, `mare_movie.png`, `mare_music.png`, `mare_net.png`, `mare_package.png`, `mare_parent.png`, `mare_picture.png`, `mare_playlist.png`, `mare_text.png`, `mare_usb.png`, `miniatura_lipsa.png`
- **`HDSatelit/retea/`** (28): `cablu_fara_internet.png`, `cablu_fara_internet@2x.png`, `cablu_fara_router.png`, `cablu_fara_router@2x.png`, `cablu_ok.png`, `cablu_ok@2x.png`, `cablu_verific.png`, `cablu_verific@2x.png`, `wifi1_fara_internet.png`, `wifi1_fara_internet@2x.png`, `wifi1_ok.png`, `wifi1_ok@2x.png`, `wifi2_fara_internet.png`, `wifi2_fara_internet@2x.png`, `wifi2_ok.png`, `wifi2_ok@2x.png`, `wifi3_fara_internet.png`, `wifi3_fara_internet@2x.png`, `wifi3_ok.png`, `wifi3_ok@2x.png`, `wifi4_fara_internet.png`, `wifi4_fara_internet@2x.png`, `wifi4_ok.png`, `wifi4_ok@2x.png`, `wifi_fara_router.png`, `wifi_fara_router@2x.png`, `wifi_verific.png`, `wifi_verific@2x.png`
- **`audit/`** (1): `README.md`
- **`data/`** (20): `black.mvi`, `cablu-romania.json`, `contributori.json`, `hbbtv-aplicatii.json`, `hds-baza-pornire.jsonl.gz`, `hds-cursor-mouse.png`, `hds-drivere-pachete.json`, `hds-module-pachete.json`, `hds-protectie-sigla.png`, `hds_rcpositions.xml`, `jurnal-versiuni.json`, `multumiri-producatori.json`, `multumiri-testeri.json`, `nota-testeri.json`, `operatori-satelit.json`, `softcsa`, `telecomanda-viper.json`, `telecomanda-viper.png`, `telecomanda-viper.svg`, `terestru-romania.json`
- **`data/asistenta/`** (1): `catalog.json`
- **`data/hds-aplicatii/`** (6): `hdsatelit-browser.png`, `hdsatelit.png`, `media-center.png`, `navigator.png`, `satbase.png`, `stb.png`
- **`data/sigle-pornire/`** (1): `radio.mvi`
- **`data/skin_default/`** (6): `hds_rc.png`, `hds_rc_glow_colors.png`, `hds_rc_glow_dpad.png`, `hds_rc_glow_ok.png`, `picon_lista_radio.png`, `picon_lista_tv.png`
- **`data/skin_default/icons/`** (4): `expandable.png`, `expanded.png`, `timer_rec.png`, `timer_zap.png`
- **`data/skin_default/spinner/`** (46): `wait10.png`, `wait11.png`, `wait12.png`, `wait13.png`, `wait14.png`, `wait15.png`, `wait16.png`, `wait17.png`, `wait18.png`, `wait19.png`, `wait20.png`, `wait21.png`, `wait22.png`, `wait23.png`, `wait24.png`, `wait25.png`, `wait26.png`, `wait27.png`, `wait28.png`, `wait29.png`, `wait30.png`, `wait31.png`, `wait32.png`, `wait33.png`, `wait34.png`, `wait35.png`, `wait36.png`, `wait37.png`, `wait38.png`, `wait39.png`, `wait40.png`, `wait41.png`, `wait42.png`, `wait43.png`, `wait44.png`, `wait45.png`, `wait46.png`, `wait47.png`, `wait48.png`, `wait49.png`, `wait5.png`, `wait50.png`, `wait6.png`, `wait7.png`, `wait8.png`, `wait9.png`
- **`data/vremea/`** (8): `ceata.png`, `furtuna.png`, `noapte.png`, `nori.png`, `ploaie.png`, `soare.png`, `surse.json`, `zapada.png`
- **`doc/`** (1): `REMOVED-FILES`
- **`doc/modules/`** (1): `HDSatelit.md`
- **`lib/dvb/`** (1): `README.md`
- **`lib/python/Components/`** (1): `README.md`
- **`lib/python/Components/Addons/`** (1): `Makefile.am`
- **`lib/python/Hds/`** (1): `Makefile.am`
- **`lib/python/Hds/DabT2/`** (1): `Makefile.am`
- **`lib/python/Hds/DabT2/dab/date/`** (1): `frecvente.json`
- **`lib/python/Hds/DabT2/t2/bin/`** (1): `Makefile.am`
- **`lib/python/Hds/DabT2/t2/date/`** (1): `frecvente.json`
- **`lib/python/Plugins/`** (1): `README.md`
- **`lib/python/Plugins/Extensions/HdsCutListEditor/`** (1): `Makefile.am`
- **`lib/python/Plugins/Extensions/HdsImportSetari/`** (1): `Makefile.am`
- **`lib/python/Plugins/Extensions/HdsLcdTv/`** (1): `Makefile.am`
- **`lib/python/Plugins/Extensions/HdsNavigator/`** (1): `Makefile.am`
- **`lib/python/Plugins/Extensions/HdsWebControl/`** (2): `Makefile.am`, `README.md`
- **`lib/python/Plugins/Extensions/HdsWebControl/tv-wasm/`** (1): `decodoare.txt`
- **`lib/python/Plugins/SystemPlugins/HdsDvbI/`** (1): `Makefile.am`
- **`lib/python/Screens/`** (1): `README.md`
- **`lib/service/`** (1): `README.md`
- **`pluginuri-feed/`** (1): `README.md`
- **`pluginuri-feed/DabTerestru/`** (2): `PROVENIENTA.md`, `plugin.png`
- **`pluginuri-feed/DabTerestru/po/`** (2): `DabTerestru.pot`, `ro.po`
- **`pluginuri-feed/RadioOnline/`** (1): `plugin.png`
- **`pluginuri-feed/RadioOnline/po/`** (30): `ar.po`, `ca.po`, `cs.po`, `da.po`, `de.po`, `el.po`, `en.po`, `es.po`, `et.po`, `fi.po`, `fr.po`, `fy.po`, `hr.po`, `hu.po`, `is.po`, `it.po`, `lt.po`, `lv.po`, `nl.po`, `no.po`, `pl.po`, `pt.po`, `ro.po`, `ru.po`, `sk.po`, `sl.po`, `sr.po`, `sv.po`, `tr.po`, `uk.po`
- **`tools/`** (1): `README.md`

## Removed from the enigma2 base (242)

Why they were removed: `doc/REMOVED-FILES`.

- **`data/`** (1): `startwizard.xml`
- **`data/fonts/`** (3): `lcd.ttf`, `md_khmurabi_10.ttf`, `nmsbd.ttf`
- **`data/skin_default/icons/`** (1): `dmm_logo.png`
- **`lib/python/Plugins/DemoPlugins/`** (2): `Makefile.am`, `__init__.py`
- **`lib/python/Plugins/DemoPlugins/TPMDemo/`** (3): `Makefile.am`, `README`, `plugin.py`
- **`lib/python/Plugins/DemoPlugins/TestPlugin/`** (4): `Makefile.am`, `__init__.py`, `maintainer.info`, `plugin.py`
- **`lib/python/Plugins/Extensions/CutListEditor/`** (5): `LICENSE`, `Makefile.am`, `__init__.py`, `keymap.xml`, `plugin.py`
- **`lib/python/Plugins/Extensions/CutListEditor/meta/`** (3): `Makefile.am`, `cutlisteditor.jpg`, `plugin_cutlisteditor.xml`
- **`lib/python/Plugins/Extensions/DVDBurn/`** (22): `DVDProject.py`, `DVDTitle.py`, `DVDToolbox.py`, `DreamboxDVD.ddvdp.xml`, `LICENSE`, `Makefile.am`, `Process.py`, `ProjectSettings.py`, `Text_menu_boat.ddvdm.xml`, `Thumbs_menu_clouds.ddvdm.xml`, `TitleCutter.py`, `TitleList.py`, `TitleProperties.py`, `__init__.py`, `dreamdvd_boat.jpg`, `dreamdvd_clouds.jpg`, `dvdburn.png`, `keymap.xml`, `plugin.py`, `silence.mp2`, `vmgmblank.mpg`, `vmgmdream.mpg`
- **`lib/python/Plugins/Extensions/DVDBurn/meta/`** (4): `Makefile.am`, `dvdburn_de.jpg`, `dvdburn_en.jpg`, `plugin_dvdburn.xml`
- **`lib/python/Plugins/Extensions/DVDPlayer/`** (5): `LICENSE`, `Makefile.am`, `__init__.py`, `keymap.xml`, `plugin.py`
- **`lib/python/Plugins/Extensions/DVDPlayer/meta/`** (3): `Makefile.am`, `dvdplayer.jpg`, `plugin_dvdplayer.xml`
- **`lib/python/Plugins/Extensions/DVDPlayer/src/`** (3): `Makefile.am`, `servicedvd.cpp`, `servicedvd.h`
- **`lib/python/Plugins/Extensions/GraphMultiEPG/`** (5): `GraphMultiEpg.py`, `LICENSE`, `Makefile.am`, `__init__.py`, `plugin.py`
- **`lib/python/Plugins/Extensions/GraphMultiEPG/meta/`** (4): `Makefile.am`, `graphmultiepg_de.jpg`, `graphmultiepg_en.jpg`, `plugin_graphmultiepg.xml`
- **`lib/python/Plugins/Extensions/Modem/`** (4): `Makefile.am`, `__init__.py`, `keymap.xml`, `plugin.py`
- **`lib/python/Plugins/Extensions/SocketMMI/`** (5): `LICENSE`, `Makefile.am`, `SocketMMI.py`, `__init__.py`, `plugin.py`
- **`lib/python/Plugins/Extensions/SocketMMI/meta/`** (2): `Makefile.am`, `plugin_socketmmi.xml`
- **`lib/python/Plugins/Extensions/SocketMMI/src/`** (3): `Makefile.am`, `socket_mmi.cpp`, `socket_mmi.h`
- **`lib/python/Plugins/Extensions/TuxboxPlugins/`** (5): `Makefile.am`, `__init__.py`, `plugin.py`, `pluginrunner.py`, `tuxbox.png`
- **`lib/python/Plugins/Extensions/TuxboxPlugins/meta/`** (2): `Makefile.am`, `plugin_tuxboxplugins.xml`
- **`lib/python/Plugins/SystemPlugins/CleanupWizard/`** (6): `CleanupWizard.py`, `LICENSE`, `Makefile.am`, `__init__.py`, `cleanupwizard.xml`, `plugin.py`
- **`lib/python/Plugins/SystemPlugins/CleanupWizard/meta/`** (4): `Makefile.am`, `cleanupwizard_de.jpg`, `cleanupwizard_en.jpg`, `plugin_cleanupwizard.xml`
- **`lib/python/Plugins/SystemPlugins/CommonInterfaceAssignment/`** (4): `LICENSE`, `Makefile.am`, `__init__.py`, `plugin.py`
- **`lib/python/Plugins/SystemPlugins/CommonInterfaceAssignment/meta/`** (3): `Makefile.am`, `ciassignment.jpg`, `plugin_commoninterfaceassignment.xml`
- **`lib/python/Plugins/SystemPlugins/CrashlogAutoSubmit/`** (4): `LICENSE`, `Makefile.am`, `__init__.py`, `plugin.py`
- **`lib/python/Plugins/SystemPlugins/CrashlogAutoSubmit/meta/`** (4): `Makefile.am`, `crashlogautosubmit_de.jpg`, `crashlogautosubmit_en.jpg`, `plugin_crashlogautosubmit.xml`
- **`lib/python/Plugins/SystemPlugins/DefaultServicesScanner/`** (3): `Makefile.am`, `__init__.py`, `plugin.py`
- **`lib/python/Plugins/SystemPlugins/DefaultServicesScanner/meta/`** (3): `Makefile.am`, `defaultservicescanner.jpg`, `plugin_defaultservicesscanner.xml`
- **`lib/python/Plugins/SystemPlugins/FrontprocessorUpgrade/`** (3): `Makefile.am`, `__init__.py`, `plugin.py`
- **`lib/python/Plugins/SystemPlugins/FrontprocessorUpgrade/meta/`** (2): `Makefile.am`, `plugin_frontprocessorupgrade.xml`
- **`lib/python/Plugins/SystemPlugins/Hotplug/`** (1): `LICENSE`
- **`lib/python/Plugins/SystemPlugins/Hotplug/meta/`** (2): `Makefile.am`, `plugin_hotplug.xml`
- **`lib/python/Plugins/SystemPlugins/NFIFlash/`** (6): `Makefile.am`, `__init__.py`, `downloader.py`, `flash.png`, `flasher.py`, `plugin.py`
- **`lib/python/Plugins/SystemPlugins/NFIFlash/meta/`** (4): `Makefile.am`, `nfiflash_de.jpg`, `nfiflash_en.jpg`, `plugin_nfiflash.xml`
- **`lib/python/Plugins/SystemPlugins/NetworkWizard/`** (6): `LICENSE`, `Makefile.am`, `NetworkWizard.py`, `__init__.py`, `networkwizard.xml`, `plugin.py`
- **`lib/python/Plugins/SystemPlugins/NetworkWizard/meta/`** (4): `Makefile.am`, `networkwizard_de.jpg`, `networkwizard_en.jpg`, `plugin_networkwizard.xml`
- **`lib/python/Plugins/SystemPlugins/OldSoftwareUpdate/`** (4): `Makefile.am`, `__init__.py`, `plugin.py`, `update.png`
- **`lib/python/Plugins/SystemPlugins/PositionerSetup/`** (4): `LICENSE`, `Makefile.am`, `__init__.py`, `plugin.py`
- **`lib/python/Plugins/SystemPlugins/PositionerSetup/meta/`** (3): `Makefile.am`, `plugin_positionersetup.xml`, `positionersetup.jpg`
- **`lib/python/Plugins/SystemPlugins/SatelliteEquipmentControl/`** (4): `LICENSE`, `Makefile.am`, `__init__.py`, `plugin.py`
- **`lib/python/Plugins/SystemPlugins/SatelliteEquipmentControl/meta/`** (3): `Makefile.am`, `plugin_satelliteequipmentcontrol.xml`, `satcontrol.jpg`
- **`lib/python/Plugins/SystemPlugins/Satfinder/`** (1): `LICENSE`
- **`lib/python/Plugins/SystemPlugins/Satfinder/meta/`** (3): `Makefile.am`, `plugin_satfinder.xml`, `satfinder.jpg`
- **`lib/python/Plugins/SystemPlugins/SoftwareManager/`** (16): `BackupRestore.py`, `ImageWizard.py`, `LICENSE`, `Makefile.am`, `SoftwareTools.py`, `__init__.py`, `imagewizard.xml`, `install.png`, `installable.png`, `installed.png`, `noprev.png`, `plugin.py`, `remove.png`, `update.png`, `upgrade.png`, `upgradeable.png`
- **`lib/python/Plugins/SystemPlugins/SoftwareManager/meta/`** (4): `Makefile.am`, `plugin_softwaremanager.xml`, `softwaremanager_de.jpg`, `softwaremanager_en.jpg`
- **`lib/python/Plugins/SystemPlugins/TempFanControl/`** (4): `LICENSE`, `Makefile.am`, `__init__.py`, `plugin.py`
- **`lib/python/Plugins/SystemPlugins/TempFanControl/meta/`** (2): `Makefile.am`, `plugin_tempfancontrol.xml`
- **`lib/python/Plugins/SystemPlugins/VideoEnhancement/`** (5): `LICENSE`, `Makefile.am`, `VideoEnhancement.py`, `__init__.py`, `plugin.py`
- **`lib/python/Plugins/SystemPlugins/VideoEnhancement/meta/`** (4): `Makefile.am`, `plugin_videoenhancement.xml`, `videoenhancement_de.jpg`, `videoenhancement_en.jpg`
- **`lib/python/Plugins/SystemPlugins/VideoTune/`** (5): `LICENSE`, `Makefile.am`, `VideoFinetune.py`, `__init__.py`, `plugin.py`
- **`lib/python/Plugins/SystemPlugins/VideoTune/meta/`** (3): `Makefile.am`, `plugin_videotune.xml`, `videotune.jpg`
- **`lib/python/Plugins/SystemPlugins/Videomode/`** (13): `DVI.png`, `HDMI.png`, `LICENSE`, `Makefile.am`, `Scart.png`, `VideoWizard.py`, `YPbPr.png`, `lcd_DVI.png`, `lcd_HDMI.png`, `lcd_Scart.png`, `lcd_YPbPr.png`, `plugin.py`, `videowizard.xml`
- **`lib/python/Plugins/SystemPlugins/Videomode/meta/`** (4): `Makefile.am`, `plugin_videomode.xml`, `videomode_de.jpg`, `videomode_en.jpg`
- **`lib/python/Plugins/SystemPlugins/WirelessLan/`** (5): `LICENSE`, `Makefile.am`, `Wlan.py`, `__init__.py`, `plugin.py`
- **`lib/python/Plugins/SystemPlugins/WirelessLan/meta/`** (4): `Makefile.am`, `plugin_wirelesslan.xml`, `wirelesslan_de.jpg`, `wirelesslan_en.jpg`
- **`lib/python/Screens/`** (3): `ClockDisplay.py`, `ConfigMenu.py`, `TutorialWizard.py`
