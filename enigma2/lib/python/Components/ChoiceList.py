# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .MenuList import MenuList
from Tools.Directories import SCOPE_CURRENT_SKIN, resolveFilename
from enigma import RT_HALIGN_LEFT, RT_HALIGN_CENTER, RT_VALIGN_CENTER, eListboxPythonMultiContent
from .MultiContent import MultiContentEntryText
from skin import getListFont, getParameterFromSkin, getListPixmap, centerPixmap
from .SkinIcon import nativ, pictograma, fontPictograme

# The rows are drawn here; the skin can set their look (names as used by other enigma2 skins, defaults = the 2011 look):
#   <alias name="ChoiceList"/>: font and row height
#   ChoicelistDash, ChoicelistName, ChoicelistIcon, ChoicelistNameSingle: x,y,w,h of the separator line,
#   of the text next to a key, of the key and of the text of a row without key
#   <hdsparameters>: ChoicelistKeyImage ("liste/tasta_%s.png", %s = 1..9, 0, red, green, yellow, blue, menu,
#   info, text) and ChoicelistDashImage (a thin line drawn in place of the row of dashes)
#   OE-Alliance: ChoiceListNative=1 and ChoiceListIcon_<key> = code[,color[,selected color]] draw the key as a glyph of
#   the font <alias name="ChoiceListIcons"/> (enigma2icons by default) in the ChoicelistIcon box (ChoicelistIconExpanded,
#   ChoicelistIconVerticalline for those two keys); the digits are then written with the list font. Without these
#   parameters (our skins) the rows are drawn exactly as before.
# HDSatelit: with a larger text size (config.osd.fontscale 105-130, Screens/FontSetup.py) the row grows like its font:
# the y and the height of every rectangle of a row and the row height from the skin (itemHeight) are multiplied by the
# percent (getListFont already grows the font and the alias row height, but itemHeight in the skin set it back, and at
# 130 % the rows touched). At 100 % nothing changes. A text wider than its rectangle stays whole: the list draws it from
# its beginning, cut cleanly at the edge, and scrolls it on the selected row (eDerulare, lib/gui/elabel.h).

def _percent():
	try:
		import skin
		return int(skin.getFontScalePercent())
	except Exception:
		return 100


def _grown(rect, percent):
	if percent <= 100:
		return rect
	return (rect[0], rect[1] * percent // 100, rect[2], rect[3] * percent // 100)


def _fitted(text, width, percent):
	"""the text of a row, whole: one that does not fit scrolls on the selected row (it is no longer shortened)"""
	return text


def _glifaNativa(key):
	"""(text, font, color, selected color) of a key drawn from the font (OE-Alliance, ChoiceListNative); None otherwise"""
	if not key or key in ("dummy", "none") or not nativ("ChoiceListNative"):
		return None
	if len(key) == 1 and key in "0123456789":
		return key, 0, None, None
	icon = pictograma("ChoiceList", key, "ChoiceListNative")
	if icon is None:
		return None
	return icon.text, 1, icon.color, icon.selectedColor


def ChoiceEntryComponent(key = "", text = ["--"]):
	res = [ text ]
	percent = _percent()
	if text[0] == "--":
		rect, skinned = getParameterFromSkin("ChoicelistDash", (0, 0, 800, 25))
		rect = _grown(rect, percent)
		line, from_skin = getListPixmap("ChoicelistDashImage")
		if line is not None:
			x, y, w, h = centerPixmap(rect, line)
			res.append((eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND, x, y, w, h, line))
		else:
			res.append((eListboxPythonMultiContent.TYPE_TEXT, rect[0], rect[1], rect[2], rect[3], 0, RT_HALIGN_LEFT | (skinned and RT_VALIGN_CENTER or 0), "-"*200))
	else:
		glyph = _glifaNativa(key)
		if glyph is not None:
			png, from_skin = None, False
		else:
			png, from_skin = getListPixmap("ChoicelistKeyImage", key, resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/buttons/key_" + key + ".png"))
		if png is not None or glyph is not None:
			rect, skinned = getParameterFromSkin("ChoicelistName", (45, 0, 800, 25))
		else:
			rect, skinned = getParameterFromSkin("ChoicelistNameSingle", (45, 0, 800, 25))
		rect = _grown(rect, percent)
		res.append((eListboxPythonMultiContent.TYPE_TEXT, rect[0], rect[1], rect[2], rect[3], 0, RT_HALIGN_LEFT | (skinned and RT_VALIGN_CENTER or 0), _fitted(text[0], rect[2], percent)))
		if glyph is not None:
			icon = getParameterFromSkin("ChoicelistIcon", (5, 0, 35, 25))[0]
			if key in ("expanded", "verticalline"):
				icon = getParameterFromSkin("ChoicelistIcon" + key.capitalize(), icon)[0]
			icon = _grown(icon, percent)
			res.append(MultiContentEntryText(pos = (icon[0], icon[1]), size = (icon[2], icon[3]), font = glyph[1], flags = RT_HALIGN_CENTER | RT_VALIGN_CENTER, text = glyph[0], color = glyph[2], color_sel = glyph[3]))
		elif png is not None:
			icon, skinned = getParameterFromSkin("ChoicelistIcon", (5, 0, 35, 25))
			icon = _grown(icon, percent)
			if skinned:
				icon = centerPixmap(icon, png)
			res.append((from_skin and eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND or eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST, icon[0], icon[1], icon[2], icon[3], png))

	return res

def _marimeAlias(alias, implicit):
	"""the size of <alias name=`alias`> of the skin, unscaled (fontPictograme scales it), else `implicit`"""
	try:
		from skin import fonts
		return int(fonts[alias][1]) or implicit
	except Exception:
		return implicit


class ChoiceList(MenuList):
	def __init__(self, list, selection = 0, enableWrapAround=False):
		MenuList.__init__(self, list, enableWrapAround, eListboxPythonMultiContent)
		font, height = getListFont("ChoiceList", ("Regular", 20, 25))
		self.l.setFont(0, font)
		if nativ("ChoiceListNative"):
			# OE-Alliance: the glyphs of the keys (ChoiceEntryComponent), at the size of the list font by default
			self.l.setFont(1, fontPictograme("ChoiceListIcons", _marimeAlias("ChoiceList", 20)))
		self.l.setItemHeight(height)
		self.selection = selection

	def postWidgetCreate(self, instance):
		MenuList.postWidgetCreate(self, instance)
		self.moveToIndex(self.selection)

	def applySkin(self, desktop, parent):
		ret = MenuList.applySkin(self, desktop, parent)
		# HDSatelit: the row height from the skin grows with a larger text size, like the rows (see _grown above)
		percent = _percent()
		if percent > 100:
			for (attrib, value) in self.skinAttributes or ():
				if attrib == "itemHeight":
					try:
						height = int(value) * percent // 100
						self.l.setItemHeight(height)
						# whole rows only: a cut half row is not drawn at the bottom
						from Components.HdsMarireText import randuriIntregi
						randuriIntregi(self.instance, height)
					except Exception:
						pass
		return ret
