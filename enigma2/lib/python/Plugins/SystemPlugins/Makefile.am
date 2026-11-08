# Modificat de moneasoftware.com si hdsatelit.com, 2026
installdir = $(pkglibdir)/python/Plugins/SystemPlugins

# 0.2.6: EmulatorMouse scos din imagine: e numai pentru emulatorul de pe PC, care isi
# pune copia lui; pe receptor nu face nimic.
SUBDIRS = SkinSelector DiseqcTester Hotplug HdsDvbI

install_PYTHON =	\
	__init__.py

# 0.7.1: pachetul subtire Videomode (numele cerute de pluginurile altor imagini: VideoHardware, video_hw, VideoSetup), FARA plugin.py.
# Nu e un plugin al imaginii, deci nu sta in SUBDIRS (lista pluginurilor imaginii); fisierele lui se pun de aici.
videomodedir = $(pkglibdir)/python/Plugins/SystemPlugins/Videomode
videomode_PYTHON = Videomode/__init__.py Videomode/VideoHardware.py Videomode/VideoSetup.py
