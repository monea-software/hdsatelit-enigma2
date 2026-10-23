# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .MenuList import MenuList
from Components.ParentalControl import IMG_WHITESERVICE, IMG_WHITEBOUQUET, IMG_BLACKSERVICE, IMG_BLACKBOUQUET
from Tools.Directories import SCOPE_SKIN_IMAGE, resolveFilename

from enigma import eListboxPythonMultiContent, RT_HALIGN_LEFT, RT_VALIGN_CENTER
from skin import getListFont, getParameterFromSkin, getListPixmap, centerPixmap

# The rows are drawn here; the skin can set their look (HDSatelit names, defaults = the 2011 look):
#   <alias name="ParentalControlList"/>: font and row height
#   ParentalControlListName, ParentalControlListIcon: x,y,w,h of the channel name and of the lock
#   <hdsparameters>: ParentalControlListImage ("...%s.png", %s = lock, lockBouquet, unlock, unlockBouquet)

#Now there is a list of pictures instead of one...
entryPicture = {
	IMG_BLACKSERVICE: "lock",
	IMG_BLACKBOUQUET: "lockBouquet",
	IMG_WHITESERVICE: "unlock",
	IMG_WHITEBOUQUET: "unlockBouquet",
}

def ParentalControlEntryComponent(service, name, protectionType):
	locked = protectionType[0]
	sImage = protectionType[1]
	rect, skinned = getParameterFromSkin("ParentalControlListName", (80, 5, 300, 50))
	res = [
		(service, name, locked),
		(eListboxPythonMultiContent.TYPE_TEXT, rect[0], rect[1], rect[2], rect[3], 0, RT_HALIGN_LEFT | (skinned and RT_VALIGN_CENTER or 0), name)
	]
	#Changed logic: The image is defined by sImage, not by locked anymore
	if sImage in entryPicture:
		key = entryPicture[sImage]
		png, from_skin = getListPixmap("ParentalControlListImage", key, resolveFilename(SCOPE_SKIN_IMAGE, "skin_default/icons/%s.png" % key))
		if png is not None:
			rect, skinned = getParameterFromSkin("ParentalControlListIcon", (0, 0, 32, 32))
			if skinned:
				rect = centerPixmap(rect, png)
			res.append((from_skin and eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND or eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST, rect[0], rect[1], rect[2], rect[3], png))
	return res

class ParentalControlList(MenuList):
	def __init__(self, list, enableWrapAround = False):
		MenuList.__init__(self, list, enableWrapAround, eListboxPythonMultiContent)
		font, height = getListFont("ParentalControlList", ("Regular", 20, 32))
		self.l.setFont(0, font)
		self.l.setItemHeight(height)

	def toggleSelectedLock(self):
		from Components.ParentalControl import parentalControl
		print("self.l.getCurrentSelection():", self.l.getCurrentSelection())
		print("self.l.getCurrentSelectionIndex():", self.l.getCurrentSelectionIndex())
		curSel = self.l.getCurrentSelection()
		if curSel[0][2]:
			parentalControl.unProtectService(self.l.getCurrentSelection()[0][0])
		else:
			parentalControl.protectService(self.l.getCurrentSelection()[0][0])
		#Instead of just negating the locked- flag, now I call the getProtectionType every time...
		self.list[self.l.getCurrentSelectionIndex()] = ParentalControlEntryComponent(curSel[0][0], curSel[0][1], parentalControl.getProtectionType(curSel[0][0]))
		self.l.setList(self.list)
