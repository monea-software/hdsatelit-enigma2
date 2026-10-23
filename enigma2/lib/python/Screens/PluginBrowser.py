# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Components.Language import language
from Components.PluginComponent import plugins
from Components.PluginList import *
from Tools.Directories import resolveFilename, SCOPE_PLUGINS

# HDSatelit: the Dreambox plugin browser is replaced by the HDSatelit extension manager
# (Screens/HdsExtensii.py): installed plugins (OK starts one, as before), the packages of the configured sources by
# category, updates, .ipk files from USB/disk/network, the sources, search. The two class names stay, so the menu
# entries (data/menu.xml: module="PluginBrowser" screen="PluginBrowser") and any plugin opening them keep working.
# The old PluginDownloadBrowser built shell strings ("opkg install " + a name read from opkg output) and ran them
# through /bin/sh; that code is gone. opkg now runs only through Components/Ipkg.py, with a list of arguments.
from Screens.HdsExtensii import HdsExtensii


def languageChanged():
	plugins.clearPluginList()
	plugins.readPluginList(resolveFilename(SCOPE_PLUGINS))


class PluginBrowser(HdsExtensii):
	"""the extension manager, opened on the installed plugins"""
	def __init__(self, session):
		HdsExtensii.__init__(self, session, fila='instalate')


class PluginDownloadBrowser(HdsExtensii):
	"""the extension manager: DOWNLOAD opens it on the packages of the sources, REMOVE on the installed plugins"""
	DOWNLOAD = 0
	REMOVE = 1

	def __init__(self, session, type=0):
		HdsExtensii.__init__(self, session, fila='extensions' if type == self.DOWNLOAD else 'instalate')


language.addCallback(languageChanged)
