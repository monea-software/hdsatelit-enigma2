# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .MenuList import MenuList

from Tools.Directories import resolveFilename, SCOPE_SKIN_IMAGE
from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmapAlphaTest, MultiContentEntryPixmapAlphaBlend

from enigma import eListboxPythonMultiContent, RT_HALIGN_LEFT, RT_VALIGN_TOP, RT_VALIGN_CENTER
from skin import getListFont, getParameterFromSkin, getListPixmap, centerPixmap

# The rows are drawn here; the skin can set their look (names as used by other enigma2 skins, defaults = the 2011 look):
#   <alias name="PluginBrowser0"/>: font of the name and row height; <alias name="PluginBrowser1"/>: description
#   PluginBrowserName, PluginBrowserDescr: x,y,h (the text reaches the right edge of the list);
#   PluginBrowserIcon: x,y,w,h of the icon; the same for the download list: PluginBrowserDownloadName,
#   PluginBrowserDownloadDescr, PluginBrowserDownloadIcon
#   <hdsparameters>: PluginBrowserWidth (the width of the list, for the text) and PluginBrowserImage (the icon
#   of a plugin without its own, "liste/extensie.png")

def _text(name, default, font, text):
	"""a text of the row from the x,y,h parameter `name`; with the skin it is centered in its height and
	reaches the right edge of the list (PluginBrowserWidth, else as far as the list lets it)"""
	(x, y, h), skinned = getParameterFromSkin(name, default[:3])
	if skinned:
		width = getParameterFromSkin("PluginBrowserWidth", 1920)[0]
		return MultiContentEntryText(pos=(x, y), size=(max(0, width - x), h), font=font, flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER, text=text)
	return MultiContentEntryText(pos=(x, y), size=(default[3], h), font=font, flags=RT_HALIGN_LEFT | RT_VALIGN_TOP, text=text)

def _icon(name, default, png):
	rect, skinned = getParameterFromSkin(name, default)
	if skinned and png is not None:
		x, y, w, h = centerPixmap(rect, png)
		return MultiContentEntryPixmapAlphaBlend(pos=(x, y), size=(w, h), png=png)
	return MultiContentEntryPixmapAlphaTest(pos=(rect[0], rect[1]), size=(rect[2], rect[3]), png=png)

def _pluginIcon(plugin):
	if plugin.icon is not None:
		return plugin.icon
	return getListPixmap("PluginBrowserImage", None, resolveFilename(SCOPE_SKIN_IMAGE, "skin_default/icons/plugin.png"))[0]

def PluginEntryComponent(plugin):
	return [
		plugin,
		_text("PluginBrowserName", (120, 5, 25, 320), 0, plugin.name),
		_text("PluginBrowserDescr", (120, 26, 17, 320), 1, plugin.description),
		_icon("PluginBrowserIcon", (10, 5, 100, 40), _pluginIcon(plugin))
	]

def PluginCategoryComponent(name, png):
	return [
		name,
		_text("PluginBrowserDownloadName", (120, 5, 25, 320), 0, name),
		_icon("PluginBrowserDownloadIcon", (10, 0, 100, 50), png)
	]

def PluginDownloadComponent(plugin, name):
	return [
		plugin,
		_text("PluginBrowserDownloadName", (120, 5, 25, 320), 0, name),
		_text("PluginBrowserDownloadDescr", (120, 26, 17, 320), 1, plugin.description),
		_icon("PluginBrowserDownloadIcon", (10, 0, 100, 50), _pluginIcon(plugin))
	]


class PluginList(MenuList):
	def __init__(self, list, enableWrapAround=False):
		MenuList.__init__(self, list, enableWrapAround, eListboxPythonMultiContent)
		font, height = getListFont("PluginBrowser0", ("Regular", 20, 50))
		self.l.setFont(0, font)
		self.l.setFont(1, getListFont("PluginBrowser1", ("Regular", 14))[0])
		self.l.setItemHeight(height)
