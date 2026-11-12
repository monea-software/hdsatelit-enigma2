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

	def __init__(self, session, type=0, needupdate=True, skin_name=None, *argumente, **numite):
		# needupdate si skin_name: pluginurile altora le dau ca in celelalte imagini; lista se reface oricum, tema e a noastra
		HdsExtensii.__init__(self, session, fila='disponibile' if type == self.DOWNLOAD else 'instalate')


language.addCallback(languageChanged)


from Screens.Screen import ScreenSummary  # noqa: E402


class PluginBrowserSummary(ScreenSummary):
	"""Ecranul mic (afisajul din fata) al listei de pluginuri, cum il cer pluginurile din alte imagini (createSummary):
	numele si descrierea randului ales, in entry si value; parintele le trimite prin onChangedEntry(nume, descriere)."""
	def __init__(self, session, parent):
		from Components.Sources.StaticText import StaticText
		ScreenSummary.__init__(self, session, parent=parent)
		self.skinName = ["PluginBrowserSummary"] + list(self.skinName)
		self["entry"] = StaticText("")
		self["value"] = StaticText("")
		self.onShow.append(self.addWatcher)
		self.onHide.append(self.removeWatcher)

	def addWatcher(self):
		lista = getattr(self.parent, "onChangedEntry", None)
		if isinstance(lista, list) and self.selectionChanged not in lista:
			lista.append(self.selectionChanged)
		alege = getattr(self.parent, "selectionChanged", None)
		if callable(alege):
			try:
				alege()
			except Exception as e:
				print("[PluginBrowserSummary] %r" % (e,))

	def removeWatcher(self):
		lista = getattr(self.parent, "onChangedEntry", None)
		if isinstance(lista, list) and self.selectionChanged in lista:
			lista.remove(self.selectionChanged)

	def selectionChanged(self, name="", description=""):
		self["entry"].setText(name or "")
		self["value"].setText(description or "")
