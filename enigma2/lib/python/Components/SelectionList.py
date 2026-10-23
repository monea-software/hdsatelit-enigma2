# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .MenuList import MenuList
from Tools.Directories import resolveFilename, SCOPE_CURRENT_SKIN
from enigma import eListboxPythonMultiContent, eListbox, RT_HALIGN_LEFT, RT_VALIGN_CENTER
from skin import getListFont, getParameterFromSkin, getListPixmap, centerPixmap

# The rows are drawn here; the skin can set their look (names as used by other enigma2 skins, defaults = the 2011 look):
#   <alias name="SelectionList"/>: font and row height
#   SelectionListDescr: x,y,w,h of the text; SelectionListLock: x,y,w,h of the mark
#   <hdsparameters>: SelectionListImage ("liste/bifa_%s.png", %s = on / off): with it an unticked row shows
#   an empty box; without it only the ticked rows show the 2011 cross, as before

def SelectionEntryComponent(description, value, index, selected):
	rect, skinned = getParameterFromSkin("SelectionListDescr", (30, 3, 500, 30))
	res = [
		(description, value, index, selected),
		(eListboxPythonMultiContent.TYPE_TEXT, rect[0], rect[1], rect[2], rect[3], 0, RT_HALIGN_LEFT | (skinned and RT_VALIGN_CENTER or 0), description)
	]
	png, from_skin = getListPixmap("SelectionListImage", selected and "on" or "off")
	if png is None and selected:
		png, from_skin = getListPixmap(None, None, resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/icons/selectioncross.png"))
	if png is not None:
		rect, skinned = getParameterFromSkin("SelectionListLock", (0, 0, 30, 30))
		if skinned:
			rect = centerPixmap(rect, png)
		res.append((from_skin and eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND or eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST, rect[0], rect[1], rect[2], rect[3], png))
	return res

class SelectionList(MenuList):
	def __init__(self, list = None, enableWrapAround = False):
		MenuList.__init__(self, list or [], enableWrapAround, content = eListboxPythonMultiContent)
		font, height = getListFont("SelectionList", ("Regular", 20, 30))
		self.l.setFont(0, font)
		self.l.setItemHeight(height)

	def addSelection(self, description, value, index, selected = True):
		self.list.append(SelectionEntryComponent(description, value, index, selected))
		self.setList(self.list)

	def toggleSelection(self):
		idx = self.getSelectedIndex()
		item = self.list[idx][0]
		self.list[idx] = SelectionEntryComponent(item[0], item[1], item[2], not item[3])
		self.setList(self.list)

	def getSelectionsList(self):
		return [ (item[0][0], item[0][1], item[0][2]) for item in self.list if item[0][3] ]
