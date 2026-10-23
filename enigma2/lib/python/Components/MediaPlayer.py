# Modificat de moneasoftware.com si hdsatelit.com, 2026
from .MenuList import MenuList

from Tools.Directories import SCOPE_CURRENT_SKIN, resolveFilename
from os import path

from enigma import eListboxPythonMultiContent, RT_VALIGN_CENTER, eServiceCenter

from Tools.LoadPixmap import LoadPixmap
from skin import getListFont, getParameterFromSkin, getListPixmap, centerPixmap

# The rows of the play list are drawn here; the skin can set their look (names as used by other enigma2 skins, defaults = 2011):
#   <alias name="PlayList"/>: font and row height; PlayListName, PlayListIcon: x,y,w,h of the text and the icon
#   <hdsparameters>: PlayListImage ("...%s.png", %s = play, pause, stop, rewind, forward)

STATE_PLAY = 0
STATE_PAUSE = 1
STATE_STOP = 2
STATE_REWIND = 3
STATE_FORWARD = 4
STATE_NONE = 5

PlayIcon = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/icons/ico_mp_play.png"))
PauseIcon = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/icons/ico_mp_pause.png"))
StopIcon = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/icons/ico_mp_stop.png"))
RewindIcon = LoadPixmap(resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/icons/ico_mp_rewind.png"))
ForwardIcon = LoadPixmap(path=resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/icons/ico_mp_forward.png"))
STATE_ICONS = {
	STATE_PLAY: ("play", PlayIcon),
	STATE_PAUSE: ("pause", PauseIcon),
	STATE_STOP: ("stop", StopIcon),
	STATE_REWIND: ("rewind", RewindIcon),
	STATE_FORWARD: ("forward", ForwardIcon),
}

def PlaylistEntryComponent(serviceref, state):
	res = [ serviceref ]
	text = serviceref.getName()
	if text == "":
		text = path.split(serviceref.getPath().split('/')[-1])[1]
	# a name with bytes that are not valid UTF-8 would otherwise crash the text drawing (see HdsNavigator.safeText)
	from Components.HdsNavigator import safeText
	text = safeText(text)
	rect = getParameterFromSkin("PlayListName", (25, 1, 470, 22))[0]
	res.append((eListboxPythonMultiContent.TYPE_TEXT, rect[0], rect[1], rect[2], rect[3], 0, RT_VALIGN_CENTER, text))
	png = None
	from_skin = False
	if state in STATE_ICONS:
		key, old = STATE_ICONS[state]
		png, from_skin = getListPixmap("PlayListImage", key)
		if png is None:
			png = old

	if png is not None:
		rect, skinned = getParameterFromSkin("PlayListIcon", (5, 3, 16, 16))
		if skinned:
			rect = centerPixmap(rect, png)
		res.append((from_skin and eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND or eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST, rect[0], rect[1], rect[2], rect[3], png))

	return res

class PlayList(MenuList):
	def __init__(self, enableWrapAround = False):
		MenuList.__init__(self, [], enableWrapAround, eListboxPythonMultiContent)
		font, height = getListFont("PlayList", ("Regular", 18, 23))
		self.l.setFont(0, font)
		self.l.setItemHeight(height)
		self.currPlaying = -1
		self.oldCurrPlaying = -1
		self.serviceHandler = eServiceCenter.getInstance()

	def clear(self):
		del self.list[:]
		self.l.setList(self.list)
		self.currPlaying = -1
		self.oldCurrPlaying = -1

	def getSelection(self):
		return self.l.getCurrentSelection()[0]

	def addFile(self, serviceref):
		self.list.append(PlaylistEntryComponent(serviceref, STATE_NONE))

	def updateFile(self, index, newserviceref):
		if index < len(self.list):
		    self.list[index] = PlaylistEntryComponent(newserviceref, STATE_NONE)

	def deleteFile(self, index):
		if self.currPlaying >= index:
			self.currPlaying -= 1
		del self.list[index]

	def setCurrentPlaying(self, index):
		self.oldCurrPlaying = self.currPlaying
		self.currPlaying = index
		self.moveToIndex(index)

	def updateState(self, state):
		if len(self.list) > self.oldCurrPlaying and self.oldCurrPlaying != -1:
			self.list[self.oldCurrPlaying] = PlaylistEntryComponent(self.list[self.oldCurrPlaying][0], STATE_NONE)
		if self.currPlaying != -1 and self.currPlaying < len(self.list):
			self.list[self.currPlaying] = PlaylistEntryComponent(self.list[self.currPlaying][0], state)
		self.updateList()

	def playFile(self):
		self.updateState(STATE_PLAY)

	def pauseFile(self):
		self.updateState(STATE_PAUSE)
		
	def stopFile(self):
		self.updateState(STATE_STOP)

	def rewindFile(self):
		self.updateState(STATE_REWIND)

	def forwardFile(self):
		self.updateState(STATE_FORWARD)

	def updateList(self):
		self.l.setList(self.list)

	def getCurrentIndex(self):
		return self.currPlaying

	def getCurrentEvent(self):
		l = self.l.getCurrentSelection()
		return l and self.serviceHandler.info(l[0]).getEvent(l[0])

	def getCurrent(self):
		l = self.l.getCurrentSelection()
		return l and l[0]

	def getServiceRefList(self):
		return [ x[0] for x in self.list ]

	def __len__(self):
		return len(self.list)
