# Modificat de moneasoftware.com si hdsatelit.com, 2026
from enigma import ePicLoad, eTimer, getDesktop

from Screens.Screen import Screen
from Tools.Directories import resolveFilename, pathExists, fileExists, SCOPE_MEDIA
from Plugins.Plugin import PluginDescriptor

from Components.Pixmap import Pixmap, MovingPixmap
from Components.ActionMap import ActionMap, NumberActionMap
from Components.Sources.StaticText import StaticText
from Components.FileList import FileList
from Components.AVSwitch import AVSwitch
from Components.Sources.List import List
from Components.ConfigList import ConfigList, ConfigListScreen

from Components.config import config, ConfigSubsection, ConfigInteger, ConfigSelection, ConfigText, ConfigEnableDisable, KEY_LEFT, KEY_RIGHT, KEY_0, getConfigListEntry
from Components.HdsNavigator import HdsPanouFisiere, breadcrumb, navigatorImage, imageSize, isPictureFile, shortName, safeText
# HDSatelit: the extensions of the file list, shared with the web interface (HdsWebControl/media_web.py)
from Components.HdsMedia import MODEL_POZE, ETICHETE_EXIF
from Tools.Directories import SCOPE_CURRENT_SKIN
import os

def hdsColor(name):
	"""a color of the HDSatelit skin as "#AARRGGBB", or None with another skin"""
	try:
		import skin
		c = skin.colorNames.get(name)
		if c is not None:
			return "#%08x" % c.argb()
	except Exception:
		pass
	return None

def hdsThumbnails():
	"""the thumbnails as cards (HDSatelit skin: its colors and the selection frame HdsMiniaturaImage)"""
	return hdsColor("hdsPanelDialog") is not None and hdsColor("hdsCell") is not None and navigatorImage("HdsMiniaturaImage")

def pictureRows(filelist, path):
	"""full paths of the pictures of a list: rows of a FileList ([(name, isDir), ...], names relative to `path`),
	rows made by filescan_open ([(full path, False), ...]) or rows of the thumbnails (T_FULL). The 2011 code guessed
	the kind by the length of the first row, which changes with the icons of the skin."""
	result = []
	dirs = 0
	for x in filelist:
		if isinstance(x, tuple) and len(x) > T_FULL:
			result.append(x[T_FULL])
			continue
		name, isDir = x[0][0], x[0][1]
		if isDir:
			dirs += 1
		elif name:
			result.append(name.startswith("/") and name or os.path.join(path or "/", name))
	return result, dirs

def getScale():
	return AVSwitch().getFramebufferScale()

config.pic = ConfigSubsection()
config.pic.framesize = ConfigInteger(default=30, limits=(5, 99))
config.pic.slidetime = ConfigInteger(default=10, limits=(10, 60))
config.pic.resize = ConfigSelection(default="1", choices = [("0", _("simple")), ("1", _("better"))])
config.pic.cache = ConfigEnableDisable(default=True)
config.pic.lastDir = ConfigText(default=resolveFilename(SCOPE_MEDIA))
config.pic.infoline = ConfigEnableDisable(default=True)
config.pic.loop = ConfigEnableDisable(default=True)
config.pic.bgcolor = ConfigSelection(default="#00000000", choices = [("#00000000", _("black")),("#009eb9ff", _("blue")),("#00ff5a51", _("red")), ("#00ffe875", _("yellow")), ("#0038FF48", _("green"))])
config.pic.textcolor = ConfigSelection(default="#0038FF48", choices = [("#00000000", _("black")),("#009eb9ff", _("blue")),("#00ff5a51", _("red")), ("#00ffe875", _("yellow")), ("#0038FF48", _("green"))])

class picshow(Screen):
	skin = """
		<screen name="picshow" position="center,center" size="560,440" title="PicturePlayer" >
			<ePixmap pixmap="skin_default/buttons/red.png" position="0,0" size="140,40" alphatest="on" />
			<ePixmap pixmap="skin_default/buttons/green.png" position="140,0" size="140,40" alphatest="on" />
			<ePixmap pixmap="skin_default/buttons/yellow.png" position="280,0" size="140,40" alphatest="on" />
			<ePixmap pixmap="skin_default/buttons/blue.png" position="420,0" size="140,40" alphatest="on" />
			<widget source="key_red" render="Label" position="0,0" zPosition="1" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="1" />
			<widget source="key_green" render="Label" position="140,0" zPosition="1" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="1" />
			<widget source="key_yellow" render="Label" position="280,0" zPosition="1" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="#a08500" transparent="1" />
			<widget source="key_blue" render="Label" position="420,0" zPosition="1" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="#18188b" transparent="1" />
			<widget source="label" render="Label" position="5,55" size="350,140" font="Regular;19" backgroundColor="#25062748" transparent="1"  />
			<widget name="thn" position="360,40" size="180,160" alphatest="on" />
			<widget name="filelist" position="5,205" zPosition="2" size="550,230" scrollbarMode="showOnDemand" />
		</screen>"""

	def __init__(self, session):
		Screen.__init__(self, session)

		self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions"],
		{
			"cancel": self.KeyExit,
			"red": self.KeyExit,
			"green": self.KeyGreen,
			"yellow": self.KeyYellow,
			"blue": self.KeyBlue,
			"ok": self.KeyOk
		}, -1)

		self["key_red"] = StaticText(_("Close"))
		self["key_green"] = StaticText(_("Thumbnails"))
		self["key_yellow"] = StaticText("")
		self["key_blue"] = StaticText(_("Setup"))
		self["label"] = StaticText("")
		self["thn"] = Pixmap()

		currDir = config.pic.lastDir.value
		# HDSatelit: the first time (and after the list of devices) it opens on the storage devices, not on "/"
		if not currDir or currDir in ("/", "/media/") or not pathExists(currDir):
			currDir = None

		self.filelist = FileList(currDir, matchingPattern = MODEL_POZE)
		self["filelist"] = self.filelist
		self["filelist"].onSelectionChanged.append(self.selectionChanged)
		# HDSatelit: path bar and details (kind, size, date, resolution read from the header of the picture)
		self.hdsPanou = HdsPanouFisiere(self, self.filelist, nameChars = 56)

		self.ThumbTimer = eTimer()
		self.ThumbTimer.callback.append(self.showThumb)

		self.picload = ePicLoad()
		self.picload.PictureData.get().append(self.showPic)
		# HDSatelit: a picture that cannot be decoded left the 2011 ePicLoad busy for good (every later preview
		# answered "thread running"); fixed in lib/gdi/picload.cpp, and here a new ePicLoad is made after such a
		# picture, from a timer (not inside the callback of the old one), for a receiver with an older enigma2
		self.renewTimer = eTimer()
		self.renewTimer.callback.append(self.renewPicload)

		self.onLayoutFinish.append(self.setConf)
		# any close path stops the timers, so none can fire on a torn-down screen
		self.onClose.append(self.hdsStopTimers)

	def hdsStopTimers(self):
		self.ThumbTimer.stop()
		self.renewTimer.stop()

	def renewPicload(self):
		old = self.picload
		self.picload = ePicLoad()
		self.picload.PictureData.get().append(self.showPic)
		self.setPicloadPara()
		del old

	def showPic(self, picInfo=""):
		ptr = self.picload.getData()
		if ptr != None:
			self["thn"].instance.setPixmap(ptr.__deref__())
			self["thn"].show()
		else:
			self["thn"].hide()
			self.renewTimer.start(10, True)

		text = picInfo.split('\n',1)
		# the HDSatelit skin shows the size (and the resolution) in the details panel, not in this label
		self["label"].setText(not navigatorImage("HdsNavigatorImage", "picture") and len(text) > 1 and text[1] or "")
		self["key_yellow"].setText(_("Exif"))

	def showThumb(self):
		if not self.filelist.canDescent():
			if self.filelist.getCurrentDirectory() and self.filelist.getFilename():
				path = self.filelist.getCurrentDirectory() + self.filelist.getFilename()
				if not isPictureFile(path):
					# not a picture (truncated or renamed file): no preview (asking again every 500 ms would never end)
					self["thn"].hide()
					return
				if self.picload.getThumbnail(path) == 1:
					self.ThumbTimer.start(500, True)

	def selectionChanged(self):
		if not self.filelist.canDescent():
			self.ThumbTimer.start(500, True)
		else:
			self["label"].setText("")
			self["thn"].hide()
			self["key_yellow"].setText("")

	def hasPictures(self):
		return self.filelist.getCurrentDirectory() is not None and bool(pictureRows(self.filelist.getFileList(), self.filelist.getCurrentDirectory())[0])

	def KeyGreen(self):
		# on the list of devices or in a folder without pictures there is nothing to show (and no path to join)
		if self.hasPictures():
			self.session.openWithCallback(self.callbackView, Pic_Thumb, self.filelist.getFileList(), self.filelist.getSelectionIndex(), self.filelist.getCurrentDirectory())

	def KeyYellow(self):
		if not self.filelist.canDescent() and self.filelist.getCurrentDirectory() and self.filelist.getFilename():
			self.session.open(Pic_Exif, self.picload.getInfo(self.filelist.getCurrentDirectory() + self.filelist.getFilename()))

	def KeyBlue(self):
		self.session.openWithCallback(self.setConf ,Pic_Setup)

	def KeyOk(self):
		if self.filelist.canDescent():
			self.filelist.descent()
		elif self.filelist.getFilename() and self.hasPictures():
			self.session.openWithCallback(self.callbackView, Pic_Full_View, self.filelist.getFileList(), self.filelist.getSelectionIndex(), self.filelist.getCurrentDirectory())

	def setConf(self):
		self.setTitle(_("PicturePlayer"))
		self.setPicloadPara()

	def setPicloadPara(self):
		sc = getScale()
		#0=Width 1=Height 2=Aspect 3=use_cache 4=resize_type 5=Background(#AARRGGBB)
		self.picload.setPara((self["thn"].instance.size().width(), self["thn"].instance.size().height(), sc[0], sc[1], config.pic.cache.value, int(config.pic.resize.value), "#00000000"))

	def callbackView(self, val=0):
		if val > 0:
			self.filelist.moveToIndex(val)

	def KeyExit(self):
		self.renewTimer.stop()
		self.ThumbTimer.stop()
		del self.picload

		if self.filelist.getCurrentDirectory() is None:
			# the list of devices: next time it opens there again
			config.pic.lastDir.value = "/media/"
		else:
			config.pic.lastDir.value = self.filelist.getCurrentDirectory()

		config.pic.save()
		self.close()

#------------------------------------------------------------------------------------------

class Pic_Setup(Screen, ConfigListScreen):

	def __init__(self, session):
		Screen.__init__(self, session)
		# for the skin: first try MediaPlayerSettings, then Setup, this allows individual skinning
		self.skinName = ["PicturePlayerSetup", "Setup" ]
		self.setup_title = _("Settings")
		self.onChangedEntry = [ ]
		self.session = session

		self["actions"] = ActionMap(["SetupActions"],
			{
				"cancel": self.keyCancel,
				"save": self.keySave,
				"ok": self.keySave,
			}, -2)

		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("OK"))

		self.list = []
		ConfigListScreen.__init__(self, self.list, session = self.session, on_change = self.changedEntry)
		self.createSetup()
		self.onLayoutFinish.append(self.layoutFinished)

	def layoutFinished(self):
		self.setTitle(self.setup_title)

	def createSetup(self):
		self.list = []
		self.list.append(getConfigListEntry(_("Slideshow Interval (sec.)"), config.pic.slidetime))
		self.list.append(getConfigListEntry(_("Scaling Mode"), config.pic.resize))
		self.list.append(getConfigListEntry(_("Cache Thumbnails"), config.pic.cache))
		self.list.append(getConfigListEntry(_("show Infoline"), config.pic.infoline))
		self.list.append(getConfigListEntry(_("Frame size in full view"), config.pic.framesize))
		self.list.append(getConfigListEntry(_("slide picture in loop"), config.pic.loop))
		self.list.append(getConfigListEntry(_("backgroundcolor"), config.pic.bgcolor))
		self.list.append(getConfigListEntry(_("textcolor"), config.pic.textcolor))
		self["config"].list = self.list
		self["config"].l.setList(self.list)

	def keyLeft(self):
		ConfigListScreen.keyLeft(self)

	def keyRight(self):
		ConfigListScreen.keyRight(self)

	# for summary:
	def changedEntry(self):
		for x in self.onChangedEntry:
			x()

	def getCurrentEntry(self):
		return self["config"].getCurrent()[0]

	def getCurrentValue(self):
		return str(self["config"].getCurrent()[1].getText())

	def createSummary(self):
		from Screens.Setup import SetupSummary
		return SetupSummary

#---------------------------------------------------------------------------

class Pic_Exif(Screen):
	skin = """
		<screen name="Pic_Exif" position="center,center" size="560,360" title="Info" >
			<ePixmap pixmap="skin_default/buttons/red.png" position="0,0" size="140,40" alphatest="on" />
			<widget source="key_red" render="Label" position="0,0" zPosition="1" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="1" />
			<widget source="menu" render="Listbox" position="5,50" size="550,310" scrollbarMode="showOnDemand" selectionDisabled="1" >
				<convert type="TemplatedMultiContent">
				{
					"template": [  MultiContentEntryText(pos = (5, 5), size = (250, 30), flags = RT_HALIGN_LEFT, text = 0), MultiContentEntryText(pos = (260, 5), size = (290, 30), flags = RT_HALIGN_LEFT, text = 1)],
					"fonts": [gFont("Regular", 20)],
					"itemHeight": 30
				}
				</convert>
			</widget>
		</screen>"""

	def __init__(self, session, exiflist):
		Screen.__init__(self, session)

		self["actions"] = ActionMap(["SetupActions", "ColorActions"],
		{
			"cancel": self.close
		}, -1)

		self["key_red"] = StaticText(_("Close"))

		# the labels after the file name are shared with the web interface (Components/HdsMedia.py)
		exifdesc = [_("filename")+':'] + [e for e in ETICHETE_EXIF]   # list e numele unei variabile de mai jos
		list = []

		for x in range(len(exiflist)):
			if x>0:
				list.append((exifdesc[x], exiflist[x]))
			else:
				name = exiflist[x].split('/')[-1]
				list.append((exifdesc[x], name))
		self["menu"] = List(list)
		self.onLayoutFinish.append(self.layoutFinished)

	def layoutFinished(self):
		self.setTitle(_("Info"))

#----------------------------------------------------------------------------------------

T_INDEX = 0
T_FRAME_POS = 1
T_PAGE = 2
T_NAME = 3
T_FULL = 4

class Pic_Thumb(Screen):
	def __init__(self, session, piclist, lastindex, path):

		self.textcolor = config.pic.textcolor.value
		self.color = config.pic.bgcolor.value
		frame = hdsThumbnails()
		self.hdsCards = bool(frame)
		if frame:
			self.makeCardSkin(frame)
		else:
			self.makeSkin()

		Screen.__init__(self, session)
		self["hds_pozitie"] = StaticText("")
		self["hds_ajutor"] = StaticText(_("OK full screen, INFO details, EXIT back to the list"))
		self.hdsTitle = _("Thumbnails")
		if path:
			self.hdsTitle += u"  \u00b7  " + breadcrumb(path, 52)
		# a bound method: this image runs every other entry of onLayoutFinish as code (exec)
		self.onLayoutFinish.append(self.setHdsTitle)

		self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions", "MovieSelectionActions"],
		{
			"cancel": self.Exit,
			"ok": self.KeyOk,
			"left": self.key_left,
			"right": self.key_right,
			"up": self.key_up,
			"down": self.key_down,
			"showEventInfo": self.StartExif,
		}, -1)

		self["frame"] = MovingPixmap()
		for x in range(self.thumbsC):
			self["label"+str(x)] = StaticText()
			self["thumb"+str(x)] = Pixmap()

		self.Thumbnaillist = []
		self.filelist = []
		self.currPage = -1
		self.dirlistcount = 0
		self.path = path

		index = 0
		framePos = 0
		Page = 0
		for x in piclist:
			if x[0][1] == False:
				if not x[0][0]:
					continue
				self.filelist.append((index, framePos, Page, x[0][0], os.path.join(path or "/", x[0][0])))
				index += 1
				framePos += 1
				if framePos > (self.thumbsC -1):
					framePos = 0
					Page += 1
			else:
				self.dirlistcount += 1

		self.maxentry = len(self.filelist)-1
		self.index = lastindex - self.dirlistcount
		if self.index < 0:
			self.index = 0

		self.picload = ePicLoad()
		self.picload.PictureData.get().append(self.showPic)

		self.onLayoutFinish.append(self.setPicloadConf)

		self.ThumbTimer = eTimer()
		self.ThumbTimer.callback.append(self.showPic)
		# HDSatelit: a new ePicLoad after a picture that could not be decoded (see picshow.renewPicload)
		self.renewTimer = eTimer()
		self.renewTimer.callback.append(self.renewPicload)
		self.brokenPixmap = None
		# any close path stops the timers (Exit only covers the cancel key)
		self.onClose.append(self.hdsStopTimers)

	def hdsStopTimers(self):
		self.ThumbTimer.stop()
		self.renewTimer.stop()

	def setHdsTitle(self):
		self.setTitle(self.hdsTitle)

	def renewPicload(self):
		old = self.picload
		self.picload = ePicLoad()
		self.picload.PictureData.get().append(self.showPic)
		self.setPicloadPara()
		del old
		self.showPic()

	def showBroken(self, pos):
		"""the card of a picture that cannot be shown: the placeholder of the skin (HdsMiniaturaLipsaImage), if any"""
		if self.brokenPixmap is None:
			path = navigatorImage("HdsMiniaturaLipsaImage")
			if path:
				from Tools.LoadPixmap import LoadPixmap
				self.brokenPixmap = LoadPixmap(path, cached = True)
		widget = self["thumb" + str(pos)]
		if self.brokenPixmap is not None and widget.instance is not None:
			widget.instance.setPixmap(self.brokenPixmap)
			widget.show()

	def makeSkin(self):
		"""the 2011 grid over the whole screen (skins other than HDSatelit)"""
		textsize = 20
		self.spaceX = 35
		self.picX = 190
		self.spaceY = 30
		self.picY = 200

		size_w = getDesktop(0).size().width()
		size_h = getDesktop(0).size().height()
		self.thumbsX = size_w // (self.spaceX + self.picX) # thumbnails in X
		self.thumbsY = size_h // (self.spaceY + self.picY) # thumbnails in Y
		self.thumbsC = self.thumbsX * self.thumbsY # all thumbnails

		self.positionlist = []
		skincontent = ""

		posX = -1
		for x in range(self.thumbsC):
			posY = x // self.thumbsX
			posX += 1
			if posX >= self.thumbsX:
				posX = 0

			absX = self.spaceX + (posX*(self.spaceX + self.picX))
			absY = self.spaceY + (posY*(self.spaceY + self.picY))
			self.positionlist.append((absX, absY))
			skincontent += "<widget source=\"label" + str(x) + "\" render=\"Label\" position=\"" + str(absX+5) + "," + str(absY+self.picY-textsize) + "\" size=\"" + str(self.picX - 10) + ","  + str(textsize) + "\" font=\"Regular;14\" zPosition=\"2\" transparent=\"1\" noWrap=\"1\" foregroundColor=\"" + self.textcolor + "\" />"
			skincontent += "<widget name=\"thumb" + str(x) + "\" position=\"" + str(absX+5)+ "," + str(absY+5) + "\" size=\"" + str(self.picX -10) + "," + str(self.picY - (textsize*2)) + "\" zPosition=\"2\" transparent=\"1\" alphatest=\"on\" />"

		# Screen, backgroundlabel and MovingPixmap
		self.skin = "<screen position=\"0,0\" size=\"" + str(size_w) + "," + str(size_h) + "\" flags=\"wfNoBorder\" > \
			<eLabel position=\"0,0\" zPosition=\"0\" size=\""+ str(size_w) + "," + str(size_h) + "\" backgroundColor=\"" + self.color + "\" /><widget name=\"frame\" position=\"35,30\" size=\"190,200\" pixmap=\"pic_frame.png\" zPosition=\"1\" alphatest=\"on\" />"  + skincontent + "</screen>"

	def makeCardSkin(self, frame):
		"""HDSatelit: a window like the others (title, clock, lines, the keys at the bottom) with 6 x 3 cards: the
		picture on a darker card, its name under it, a light frame around the selected card"""
		W, H = 1776, 1000
		cardW, cardH, gapX, gapY = 264, 248, 25, 30
		picW, picH = 240, 180
		self.thumbsX, self.thumbsY = 6, 3
		self.thumbsC = self.thumbsX * self.thumbsY
		x0 = 32 + (1712 - (self.thumbsX * cardW + (self.thumbsX - 1) * gapX)) // 2
		y0 = 104
		self.color = hdsColor("hdsCell")
		self.positionlist = []
		cards = []
		for i in range(self.thumbsC):
			cx = x0 + (i % self.thumbsX) * (cardW + gapX)
			cy = y0 + (i // self.thumbsX) * (cardH + gapY)
			# the frame (276 x 260) goes 6 px around the card
			self.positionlist.append((cx - 6, cy - 6))
			cards.append('<eLabel position="%d,%d" size="%d,%d" backgroundColor="hdsCell" zPosition="1" />' % (cx, cy, cardW, cardH))
			cards.append('<widget name="thumb%d" position="%d,%d" size="%d,%d" zPosition="3" transparent="1" alphatest="on" />' % (i, cx + 12, cy + 12, picW, picH))
			cards.append('<widget source="label%d" render="Label" position="%d,%d" size="%d,36" font="HdsCond;26" foregroundColor="hdsText" backgroundColor="hdsCell" halign="center" valign="center" zPosition="3" transparent="1" noWrap="1" />' % (i, cx + 12, cy + cardH - 44, picW))
		self.skin = ('<screen position="72,40" size="%d,%d" flags="wfNoBorder" backgroundColor="hdsPanelDialog">' % (W, H) +
			'<eLabel position="0,0" size="%d,2" backgroundColor="hdsLine" zPosition="1" />' % W +
			'<widget source="Title" render="Label" position="32,18" size="1536,56" font="HdsBold;40" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" transparent="1" valign="center" noWrap="1" zPosition="1" />' +
			'<widget source="global.CurrentTime" render="Label" position="1584,18" size="160,56" font="HdsBold;40" foregroundColor="hdsText" backgroundColor="hdsPanelDialog" transparent="1" halign="right" valign="center" zPosition="1"><convert type="ClockToText">Format:%H:%M</convert></widget>' +
			'<eLabel position="32,88" size="1712,1" backgroundColor="hdsDivider" zPosition="1" />' +
			"".join(cards) +
			'<widget name="frame" position="%d,%d" size="276,260" pixmap="%s" zPosition="2" alphatest="blend" />' % (self.positionlist[0] + (frame,)) +
			'<eLabel position="32,924" size="1712,1" backgroundColor="hdsDivider" zPosition="1" />' +
			'<widget source="hds_pozitie" render="Label" position="32,936" size="900,48" font="HdsCond;28" foregroundColor="hdsText2" backgroundColor="hdsPanelDialog" transparent="1" valign="center" noWrap="1" zPosition="1" />' +
			'<widget source="hds_ajutor" render="Label" position="944,936" size="800,48" font="HdsCond;28" foregroundColor="hdsLabel" backgroundColor="hdsPanelDialog" transparent="1" halign="right" valign="center" noWrap="1" zPosition="1" />' +
			'</screen>')

	def setPicloadConf(self):
		self.setPicloadPara()
		self.paintFrame()

	def setPicloadPara(self):
		sc = getScale()
		self.picload.setPara([self["thumb0"].instance.size().width(), self["thumb0"].instance.size().height(), sc[0], sc[1], config.pic.cache.value, int(config.pic.resize.value), self.color])

	def paintFrame(self):
		#print "index=" + str(self.index)
		if self.maxentry < self.index or self.index < 0:
			return

		pos = self.positionlist[self.filelist[self.index][T_FRAME_POS]]
		self["frame"].moveTo( pos[0], pos[1], 1)
		self["frame"].startMoving()
		pages = self.maxentry // self.thumbsC + 1
		text = _("Picture %d of %d") % (self.index + 1, self.maxentry + 1)
		if pages > 1:
			text += "  \u00b7  " + _("page %d of %d") % (self.filelist[self.index][T_PAGE] + 1, pages)
		self["hds_pozitie"].setText(safeText(text + "  \u00b7  " + self.filelist[self.index][T_NAME]))

		if self.currPage != self.filelist[self.index][T_PAGE]:
			self.currPage = self.filelist[self.index][T_PAGE]
			self.newPage()

	def newPage(self):
		self.Thumbnaillist = []
		#clear Labels and Thumbnail
		for x in range(self.thumbsC):
			self["label"+str(x)].setText("")
			self["thumb"+str(x)].hide()
		#paint Labels and fill Thumbnail-List
		for x in self.filelist:
			if x[T_PAGE] == self.currPage:
				if self.hdsCards:
					# the cards: only the name, cut to the width of the card (the number is in the line at the bottom)
					self["label"+str(x[T_FRAME_POS])].setText(safeText(shortName(x[T_NAME], 19)))
				else:
					self["label"+str(x[T_FRAME_POS])].setText(safeText("(" + str(x[T_INDEX]+1) + ") " + x[T_NAME]))
				self.Thumbnaillist.append([0, x[T_FRAME_POS], x[T_FULL]])

		#paint Thumbnail start
		self.showPic()

	def showPic(self, picInfo=""):
		for x in range(len(self.Thumbnaillist)):
			if self.Thumbnaillist[x][0] == 0:
				if not isPictureFile(self.Thumbnaillist[x][2]):
					# not a picture (too short, renamed, unknown format): the ePicLoad would refuse it forever
					self.Thumbnaillist[x][0] = 2
					self.showBroken(self.Thumbnaillist[x][1])
					continue
				if self.picload.getThumbnail(self.Thumbnaillist[x][2]) == 1: #zu tun probier noch mal
					self.ThumbTimer.start(500, True)
				else:
					self.Thumbnaillist[x][0] = 1
				break
			elif self.Thumbnaillist[x][0] == 1:
				self.Thumbnaillist[x][0] = 2
				ptr = self.picload.getData()
				if ptr != None:
					self["thumb" + str(self.Thumbnaillist[x][1])].instance.setPixmap(ptr.__deref__())
					self["thumb" + str(self.Thumbnaillist[x][1])].show()
				else:
					# it could not be decoded: placeholder, a new ePicLoad, then the next thumbnails
					self.showBroken(self.Thumbnaillist[x][1])
					self.renewTimer.start(10, True)
					return

	def key_left(self):
		self.index -= 1
		if self.index < 0:
			self.index = self.maxentry
		self.paintFrame()

	def key_right(self):
		self.index += 1
		if self.index > self.maxentry:
			self.index = 0
		self.paintFrame()

	def key_up(self):
		self.index -= self.thumbsX
		if self.index < 0:
			self.index =self.maxentry
		self.paintFrame()

	def key_down(self):
		self.index += self.thumbsX
		if self.index > self.maxentry:
			self.index = 0
		self.paintFrame()

	def StartExif(self):
		if self.maxentry < 0:
			return
		self.session.open(Pic_Exif, self.picload.getInfo(self.filelist[self.index][T_FULL]))

	def KeyOk(self):
		if self.maxentry < 0:
			return
		self.old_index = self.index
		self.session.openWithCallback(self.callbackView, Pic_Full_View, self.filelist, self.index, self.path)

	def callbackView(self, val=0):
		self.index = val
		if self.old_index != self.index:
			self.paintFrame()
	def Exit(self):
		self.renewTimer.stop()
		self.ThumbTimer.stop()
		del self.picload
		self.close(self.index + self.dirlistcount)

#---------------------------------------------------------------------------

class Pic_Full_View(Screen):
	def __init__(self, session, filelist, index, path):

		self.textcolor = config.pic.textcolor.value
		self.bgcolor = config.pic.bgcolor.value
		space = config.pic.framesize.value
		size_w = getDesktop(0).size().width()
		size_h = getDesktop(0).size().height()

		self.skin = "<screen position=\"0,0\" size=\"" + str(size_w) + "," + str(size_h) + "\" flags=\"wfNoBorder\" > \
			<eLabel position=\"0,0\" zPosition=\"0\" size=\""+ str(size_w) + "," + str(size_h) + "\" backgroundColor=\""+ self.bgcolor +"\" /><widget name=\"pic\" position=\"" + str(space) + "," + str(space) + "\" size=\"" + str(size_w-(space*2)) + "," + str(size_h-(space*2)) + "\" zPosition=\"1\" alphatest=\"on\" /> \
			<widget name=\"point\" position=\""+ str(space+5) + "," + str(space+2) + "\" size=\"20,20\" zPosition=\"2\" pixmap=\"skin_default/icons/record.png\" alphatest=\"on\" /> \
			<widget name=\"play_icon\" position=\""+ str(space+25) + "," + str(space+2) + "\" size=\"20,20\" zPosition=\"2\" pixmap=\"skin_default/icons/ico_mp_play.png\"  alphatest=\"on\" /> \
			<widget source=\"file\" render=\"Label\" position=\""+ str(space+45) + "," + str(space) + "\" size=\""+ str(size_w-(space*2)-50) + ",25\" font=\"Regular;20\" halign=\"left\" foregroundColor=\"" + self.textcolor + "\" zPosition=\"2\" noWrap=\"1\" transparent=\"1\" /></screen>"

		Screen.__init__(self, session)

		self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions", "MovieSelectionActions"],
		{
			"cancel": self.Exit,
			"green": self.PlayPause,
			"yellow": self.PlayPause,
			"blue": self.nextPic,
			"red": self.prevPic,
			"left": self.prevPic,
			"right": self.nextPic,
			"showEventInfo": self.StartExif,
		}, -1)

		self["point"] = Pixmap()
		self["pic"] = Pixmap()
		self["play_icon"] = Pixmap()
		self["file"] = StaticText(_("please wait, loading picture..."))

		self.old_index = 0
		self.filelist = []
		self.lastindex = index
		self.currPic = []
		self.shownow = True
		self.dirlistcount = 0

		# rows of the FileList, of a scan (full paths) or of the thumbnails (see pictureRows)
		self.filelist, self.dirlistcount = pictureRows(filelist, path)

		self.maxentry = len(self.filelist)-1
		self.index = index - self.dirlistcount
		if self.index < 0:
			self.index = 0

		self.picload = ePicLoad()
		self.picload.PictureData.get().append(self.finish_decode)

		self.slideTimer = eTimer()
		self.slideTimer.callback.append(self.slidePic)
		# HDSatelit: pictures that cannot be shown are skipped (before, the slideshow stopped on the first one)
		self.renewTimer = eTimer()
		self.renewTimer.callback.append(self.renewPicload)
		self.failed = 0
		# any close path stops the timers (Exit only covers the cancel key)
		self.onClose.append(self.hdsStopTimers)

		if self.maxentry >= 0:
			self.onLayoutFinish.append(self.setPicloadConf)

	def hdsStopTimers(self):
		self.slideTimer.stop()
		self.renewTimer.stop()

	def hdsShow(self, filelist, index, path):
		"""HDSatelit, for the web interface (HdsWebControl/media_web.py, page /poze): another folder or picture in the
		open full view, as if it had been opened on it (a running slideshow keeps running). A fresh ePicLoad, so a
		picture still being decoded for the old list cannot come up under the new one."""
		self.filelist, self.dirlistcount = pictureRows(filelist, path)
		self.maxentry = len(self.filelist) - 1
		self.index = max(0, min(index - self.dirlistcount, self.maxentry))
		self.lastindex = self.index
		self.failed = 0
		self.currPic = []
		self.shownow = True
		if self.maxentry >= 0:
			self.renewPicload()

	def setPicloadPara(self):
		sc = getScale()
		self.picload.setPara([self["pic"].instance.size().width(), self["pic"].instance.size().height(), sc[0], sc[1], 0, int(config.pic.resize.value), self.bgcolor])

	def renewPicload(self):
		old = self.picload
		self.picload = ePicLoad()
		self.picload.PictureData.get().append(self.finish_decode)
		self.setPicloadPara()
		del old
		self.start_decode()

	def advanceOrStop(self):
		# the next picture, unless every one of them failed since the last good one
		self.failed += 1
		if self.failed > self.maxentry:
			self["point"].hide()
			self["file"].setText(_("No picture could be shown"))
			return False
		next(self)
		return True

	def skipBroken(self):
		# a picture whose header looked right could not be decoded: a fresh ePicLoad, then the next one
		if self.advanceOrStop():
			self.renewTimer.start(10, True)

	def setPicloadConf(self):
		self.setPicloadPara()

		self["play_icon"].hide()
		if config.pic.infoline.value == False:
			self["file"].setText("")
		self.start_decode()

	def ShowPicture(self):
		if self.shownow and len(self.currPic):
			self.shownow = False
			self["file"].setText(safeText(self.currPic[0]))
			self.lastindex = self.currPic[1]
			self["pic"].instance.setPixmap(self.currPic[2].__deref__())
			self.currPic = []

			next(self)
			self.start_decode()

	def finish_decode(self, picInfo=""):
		self["point"].hide()
		ptr = self.picload.getData()
		if ptr is None:
			self.skipBroken()
			return
		self.failed = 0
		if ptr != None:
			text = ""
			try:
				text = picInfo.split('\n',1)
				text = "(" + str(self.index+1) + "/" + str(self.maxentry+1) + ") " + text[0].split('/')[-1]
			except:
				pass
			self.currPic = []
			self.currPic.append(text)
			self.currPic.append(self.index)
			self.currPic.append(ptr)
			self.ShowPicture()

	def start_decode(self):
		# skip files that are not pictures at all, in a loop (not by calling ourselves, so a long run of them cannot
		# overflow the stack); a file with a valid header but corrupt content is handed to ePicLoad, which reports the
		# failure to finish_decode -> skipBroken
		while self.maxentry >= 0:
			if isPictureFile(self.filelist[self.index]):
				self.picload.startDecode(self.filelist[self.index])
				self["point"].show()
				return
			if not self.advanceOrStop():
				return

	def __next__(self):
		self.index += 1
		if self.index > self.maxentry:
			self.index = 0

	def prev(self):
		self.index -= 1
		if self.index < 0:
			self.index = self.maxentry

	def slidePic(self):
		print("slide to next Picture index=" + str(self.lastindex))
		if config.pic.loop.value==False and self.lastindex == self.maxentry:
			self.PlayPause()
		self.shownow = True
		self.ShowPicture()

	def PlayPause(self):
		if self.slideTimer.isActive():
			self.slideTimer.stop()
			self["play_icon"].hide()
		else:
			self.slideTimer.start(config.pic.slidetime.value*1000)
			self["play_icon"].show()
			self.nextPic()

	def prevPic(self):
		self.currPic = []
		self.index = self.lastindex
		self.prev()
		self.start_decode()
		self.shownow = True

	def nextPic(self):
		self.shownow = True
		self.ShowPicture()

	def StartExif(self):
		if self.maxentry < 0:
			return
		self.session.open(Pic_Exif, self.picload.getInfo(self.filelist[self.lastindex]))

	def Exit(self):
		self.renewTimer.stop()
		self.slideTimer.stop()
		del self.picload
		self.close(self.lastindex + self.dirlistcount)

#------------------------------------------------------------------------------------------

def main(session, **kwargs):
	session.open(picshow)

def filescan_open(list, session, **kwargs):
	# Recreate List as expected by PicView
	filelist = [((file.path, False), None) for file in list]
	session.open(Pic_Full_View, filelist, 0, file.path)

def filescan(**kwargs):
	from Components.Scanner import Scanner, ScanPath

	# Overwrite checkFile to only detect local
	class LocalScanner(Scanner):
		def checkFile(self, file):
			return fileExists(file.path)

	return \
		LocalScanner(mimetypes = ["image/jpeg", "image/png", "image/gif", "image/bmp"],
			paths_to_scan = 
				[
					ScanPath(path = "DCIM", with_subdirs = True),
					ScanPath(path = "", with_subdirs = False),
				],
			name = "Pictures", 
			description = _("View Photos..."),
			openfnc = filescan_open,
		)

def Plugins(**kwargs):
	# 0.2.6: pozele se deschid din meniu, Media > Poze (data/menu.xml, prin
	# Screens/PicturePlayer.py), nu din lista de extensii; aici ramane numai cititorul de fisiere pentru MediaScanner
	return \
		[PluginDescriptor(name=_("PicturePlayer"), where = PluginDescriptor.WHERE_FILESCAN, needsRestart = False, fnc = filescan)]
