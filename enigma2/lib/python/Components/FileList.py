# Modificat de moneasoftware.com si hdsatelit.com, 2026
from re import compile as re_compile
from os import path as os_path, listdir, access as os_access, R_OK, X_OK
from unicodedata import normalize, combining
from .MenuList import MenuList
from Components.Harddisk import harddiskmanager

from Tools.Directories import SCOPE_CURRENT_SKIN, resolveFilename, fileExists

from enigma import RT_HALIGN_LEFT, RT_VALIGN_CENTER, eListboxPythonMultiContent, \
	eServiceReference, eServiceCenter
from skin import getListFont, getParameterFromSkin, getListPixmap, centerPixmap
from Components.HdsNavigator import safeText

# the stable names given by Components/Harddisk.py (a mount or a link to the system's mount)
MEDIA_NAME_RX = re_compile(r"^/media/(hdd|usb[0-9]*)/?$")

# The rows are drawn here; the skin can set their look (names as used by other enigma2 skins, defaults = the 2011 look):
#   <alias name="FileList"/>, <alias name="FileListMulti"/>: font and row height
#   FileListIcon, FileListName (x,y,w,h); FileListMultiLock, FileListMultiIcon, FileListMultiName (x,y,w,h)
#   <hdsparameters>: FileListImage ("liste/fisier_%s.png", %s = the kind below) and FileListMultiLockImage
#   ("liste/bifa_%s.png", %s = on / off). Kinds: directory, parent, storage, movie, music, picture, playlist,
#   package, text, file. Without the skin images: the 2011 icons (a folder, and movie/music/picture only).

EXTENSIONS = {
		"m4a": "music",
		"mp2": "music",
		"mp3": "music",
		"wav": "music",
		"ogg": "music",
		"flac": "music",
		"jpg": "picture",
		"jpeg": "picture",
		"png": "picture",
		"bmp": "picture",
		"ts": "movie",
		"avi": "movie",
		"divx": "movie",
		"m4v": "movie",
		"mpg": "movie",
		"mpeg": "movie",
		"mkv": "movie",
		"mp4": "movie",
		"mov": "movie",
		"m2ts": "movie",
	}

# more kinds of files, shown only with the images of the skin (FileListImage); the 2011 icons stay as they were
EXTRA_KINDS = {
	"aac": "music", "ac3": "music", "dts": "music", "m4b": "music", "opus": "music", "wma": "music", "mka": "music",
	"vob": "movie", "m2t": "movie", "mts": "movie", "trp": "movie", "webm": "movie", "wmv": "movie", "flv": "movie",
	"3gp": "movie", "iso": "movie",
	"gif": "picture", "jpe": "picture", "tif": "picture", "tiff": "picture", "webp": "picture", "mvi": "picture",
	"m3u": "playlist", "m3u8": "playlist", "pls": "playlist", "e2pls": "playlist", "xspf": "playlist",
	"ipk": "package", "deb": "package", "zip": "package", "tgz": "package", "gz": "package", "bz2": "package",
	"xz": "package", "tar": "package", "7z": "package", "rar": "package", "nfi": "package",
	"txt": "text", "log": "text", "conf": "text", "cfg": "text", "ini": "text", "xml": "text", "json": "text",
	"srt": "text", "sub": "text", "ass": "text", "nfo": "text", "md": "text", "csv": "text",
}

def sortKey(name):
	"""order of the rows: without case and without diacritics ("Ăla" next to "Ala", not after "Zebra")"""
	return "".join(c for c in normalize("NFKD", name) if not combining(c)).casefold()

def fileEntryIcon(name, isDir, kind = None, images = "FileListImage"):
	"""(pixmap, from skin) for a row: the skin image of its kind, else the 2011 icon (a folder for directories,
	movie/music/picture for the EXTENSIONS above, nothing for the rest)"""
	extension = name.split('.')[-1].lower()
	if isDir:
		old = "extensions/directory.png"
	elif extension in EXTENSIONS:
		old = "extensions/" + EXTENSIONS[extension] + ".png"
	else:
		old = None
	if kind is None:
		if isDir:
			kind = name.startswith('<') and "parent" or "directory"
		else:
			kind = EXTENSIONS.get(extension) or EXTRA_KINDS.get(extension, "file")
	return getListPixmap(images, kind, old and resolveFilename(SCOPE_CURRENT_SKIN, old))

def _skinColor(name, default):
	"""a color of the skin (<colors>) as the number the list rows take, or `default`"""
	try:
		import skin
		c = skin.colorNames.get(name)
		if c is not None:
			v = c.argb()
			# alpha FF would be read by the list as "the color of the template"
			return v & 0xFFFFFF if (v >> 24) == 0xFF else v
	except Exception:
		pass
	return default

def storageCards():
	"""True when the skin draws the storage devices as cards (FileListStorageName, see StorageEntryComponent)"""
	return getParameterFromSkin("FileListStorageName", (0, 0, 0, 0))[1]

STORAGE_ORDER = { "usb": 0, "hdd": 1, "card": 2, "dvd": 3, "net": 4, "flash": 5 }

def StorageEntryComponent(partition, path, table = None):
	"""a storage device as a card (HDSatelit): its icon, its name, and under it the free space (a bar and
	"12 GB libere din 29 GB"), or the address of a network folder. Skin: <alias name="FileListStorage"/> (font of
	the name, height of the card), <alias name="FileListStorageInfo"/>; FileListStorageIcon, FileListStorageName,
	FileListStorageBar, FileListStorageInfo (x,y,w,h); FileListStorageImage ("navigator/disp_%s.png", %s = usb,
	hdd, net, flash, card, dvd). Row: [ (path, True), name, ... ] like FileEntryComponent."""
	from Components.HdsNavigator import deviceKind, deviceName, spaceInfo, formatSize, publicSource, mountKey, readMountTable
	if table is None:
		table = readMountTable()
	kind = deviceKind(path, partition.device, table)
	name = deviceName(path, partition.description, partition.device, kind, table)
	res = [ (path, True) ]
	x, y, w, h = getParameterFromSkin("FileListStorageName", (100, 10, 900, 48))[0]
	res.append((eListboxPythonMultiContent.TYPE_TEXT, x, y, w, h, 2, RT_HALIGN_LEFT | RT_VALIGN_CENTER, name))
	png, from_skin = getListPixmap("FileListStorageImage", kind, None)
	if png is None:
		png, from_skin = fileEntryIcon(name, True, "storage")
	if png is not None:
		rect = centerPixmap(getParameterFromSkin("FileListStorageIcon", (16, 20, 64, 64))[0], png)
		res.append((from_skin and eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND or eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST, rect[0], rect[1], rect[2], rect[3], png))
	info = ""
	used = None
	if kind == "net":
		info = publicSource(table.get(mountKey(path), ("", ""))[0])
	else:
		space = spaceInfo(path, kind)
		if space:
			free, total = space
			used = max(0, min(100, int(round(100.0 * (total - free) / total))))
			info = _("%s free of %s") % (formatSize(free), formatSize(total))
	text2 = _skinColor("hdsText2", 0xC9D2E3)
	white = _skinColor("hdsSelText", 0xFFFFFF)
	if used is not None:
		bx, by, bw, bh = getParameterFromSkin("FileListStorageBar", (100, 70, 300, 12))[0]
		track = _skinColor("hdsTrack", 0x2A3350)
		fill = used >= 90 and _skinColor("hdsAmber", 0xF5B83D) or _skinColor("hdsBrandLight", 0x9FB4FF)
		# the track (100 %, its own color) and over it the used part; no border
		res.append((eListboxPythonMultiContent.TYPE_PROGRESS, bx, by, bw, bh, 100, 0, track, track, None, None))
		if used > 0:
			res.append((eListboxPythonMultiContent.TYPE_PROGRESS, bx, by, bw, bh, used, 0, fill, fill, None, None))
	if info:
		x, y, w, h = getParameterFromSkin("FileListStorageInfo", (420, 56, 560, 40))[0]
		if used is None:
			# no bar (network folder, space not readable): the text starts where the bar would be
			x = getParameterFromSkin("FileListStorageBar", (100, 70, 300, 12))[0][0]
		res.append((eListboxPythonMultiContent.TYPE_TEXT, x, y, w, h, 1, RT_HALIGN_LEFT | RT_VALIGN_CENTER, info, text2, white))
	return res

def FileEntryComponent(name, absolute = None, isDir = False, kind = None):
	# kind (optional): "parent" or "storage" for the rows that are not a plain folder or file
	res = [ (absolute, isDir) ]
	rect, skinned = getParameterFromSkin("FileListName", (35, 1, 470, 20))
	# safeText: a file name with bytes that are not valid UTF-8 would otherwise crash the text drawing (see HdsNavigator)
	res.append((eListboxPythonMultiContent.TYPE_TEXT, rect[0], rect[1], rect[2], rect[3], 0, RT_HALIGN_LEFT | (skinned and RT_VALIGN_CENTER or 0), safeText(name)))
	png, from_skin = fileEntryIcon(name, isDir, kind)
	if png is not None:
		rect, skinned = getParameterFromSkin("FileListIcon", (10, 2, 20, 20))
		if skinned:
			rect = centerPixmap(rect, png)
		res.append((from_skin and eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND or eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST, rect[0], rect[1], rect[2], rect[3], png))

	return res

class FileList(MenuList):
	def __init__(self, directory, showDirectories = True, showFiles = True, showMountpoints = True, matchingPattern = None, useServiceRef = False, inhibitDirs = False, inhibitMounts = False, isTop = False, enableWrapAround = False, additionalExtensions = None):
		MenuList.__init__(self, list, enableWrapAround, eListboxPythonMultiContent)
		self.additional_extensions = additionalExtensions
		self.mountpoints = []
		self.current_directory = None
		self.current_mountpoint = None
		self.useServiceRef = useServiceRef
		self.showDirectories = showDirectories
		self.showMountpoints = showMountpoints
		self.showFiles = showFiles
		self.isTop = isTop
		# example: matching .nfi and .ts files: "^.*\.(nfi|ts)"
		self.matchingPattern = matchingPattern
		self.inhibitDirs = inhibitDirs or []
		self.inhibitMounts = inhibitMounts or []
		# HDSatelit: called after every change of folder (path bar, details panel of the screens)
		self.onDirectoryChanged = [ ]
		# state of the folder shown: None, "gol" (empty), "nimic" (nothing matches), "fara_dosare" (no subfolders, in a
		# list of folders only), "fara_acces" (cannot be read)
		self.hds_stare = None
		# the storage devices as cards (taller rows) when the skin draws them; the other rows keep their height
		self.cardsShown = False
		self.cardHeight = None
		if storageCards():
			self.l.setFont(1, getListFont("FileListStorageInfo", ("Regular", 18))[0])
			font, self.cardHeight = getListFont("FileListStorage", ("Regular", 22, 60))
			self.l.setFont(2, font)

		font, height = getListFont("FileList", ("Regular", 18, 23))
		self.normalHeight = height
		self.refreshMountpoints()
		self.changeDir(directory)
		self.l.setFont(0, font)
		if not self.cardsShown:
			self.l.setItemHeight(height)
		self.serviceHandler = eServiceCenter.getInstance()

	def applySkin(self, desktop, parent):
		# itemHeight= of the widget is the height of the file rows; the storage cards keep their own height
		for attrib, value in self.skinAttributes or []:
			if attrib == "itemHeight":
				try:
					self.normalHeight = int(value)
				except ValueError:
					pass
		ret = MenuList.applySkin(self, desktop, parent)
		if self.cardsShown and self.cardHeight:
			self.l.setItemHeight(self.cardHeight)
		return ret

	def setCards(self, cards):
		cards = bool(cards and self.cardHeight)
		if cards != self.cardsShown:
			self.cardsShown = cards
			self.l.setItemHeight(cards and self.cardHeight or self.normalHeight)

	def refreshMountpoints(self):
		self.mountpoints = [os_path.join(p.mountpoint, "") for p in harddiskmanager.getMountedPartitions()]
		self.mountpoints.sort(reverse = True)
		# HDSatelit: the stable names /media/hdd, /media/usb* can be links to where the system mounted the device
		# (/media/hdd -> /run/media/<label>-sda1, Components/Harddisk.py); a real path is matched to them too
		self.realMountpoints = dict((m, os_path.join(os_path.realpath(m), "")) for m in self.mountpoints if MEDIA_NAME_RX.match(m))

	def getMountpoint(self, file):
		file = os_path.join(os_path.realpath(file), "")
		real = getattr(self, "realMountpoints", {})
		for m in self.mountpoints:
			if file.startswith(m) or file.startswith(real.get(m, m)):
				return m
		return False

	def getMountpointLink(self, file):
		if os_path.realpath(file) == file:
			return self.getMountpoint(file)
		else:
			if file[-1] == "/":
				file = file[:-1]
			mp = self.getMountpoint(file)
			last = file
			file = os_path.dirname(file)
			while last != "/" and mp == self.getMountpoint(file):
				last = file
				file = os_path.dirname(file)
			return os_path.join(last, "")

	def getSelection(self):
		if self.l.getCurrentSelection() is None:
			return None
		return self.l.getCurrentSelection()[0]

	def getCurrentEvent(self):
		l = self.l.getCurrentSelection()
		if not l or l[0][1] == True:
			return None
		else:
			return self.serviceHandler.info(l[0][0]).getEvent(l[0][0])

	def getFileList(self):
		return self.list

	def inParentDirs(self, dir, parents):
		dir = os_path.realpath(dir)
		for p in parents:
			if dir.startswith(p):
				return True
		return False

	def changeDir(self, directory, select = None):
		self.list = []

		# if we are just entering from the list of mount points:
		if self.current_directory is None:
			if directory and self.showMountpoints:
				self.current_mountpoint = self.getMountpointLink(directory)
			else:
				self.current_mountpoint = None
		self.current_directory = directory
		directories = []
		files = []
		self.hds_stare = None
		unreadable = False
		cards = False

		if directory is None and self.showMountpoints: # present available mountpoints
			from Components.HdsNavigator import deviceKind, deviceName, readMountTable
			table = readMountTable()
			devices = []
			for p in harddiskmanager.getMountedPartitions():
				path = os_path.join(p.mountpoint, "")
				if path not in self.inhibitMounts and not self.inParentDirs(path, self.inhibitDirs):
					devices.append((STORAGE_ORDER.get(deviceKind(path, p.device, table), 9), len(devices), p, path))
			# removable devices first, the internal memory last; the names in the language of the menus
			devices.sort(key = lambda d: d[:2])
			cards = bool(devices) and storageCards() and self.cardHeight is not None
			for order, n, p, path in devices:
				if cards:
					self.list.append(StorageEntryComponent(p, path, table))
				else:
					self.list.append(FileEntryComponent(name = deviceName(path, p.description, p.device, table = table), absolute = path, isDir = True, kind = "storage"))
			files = [ ]
			directories = [ ]
		elif directory is None:
			files = [ ]
			directories = [ ]
		elif self.useServiceRef:
			root = eServiceReference("2:0:1:0:0:0:0:0:0:0:" + directory)
			if self.additional_extensions:
				root.setName(self.additional_extensions)
			serviceHandler = eServiceCenter.getInstance()
			list = serviceHandler.list(root)

			while 1:
				s = list.getNext()
				if not s.valid():
					del list
					break
				if s.flags & s.mustDescent:
					directories.append(s.getPath())
				else:
					files.append(s)
			directories.sort(key = sortKey)
			files.sort(key = lambda s: sortKey(s.getPath()))
			unreadable = not directories and not files and not os_access(directory, R_OK | X_OK)
		else:
			if fileExists(directory):
				try:
					files = listdir(directory)
				except:
					files = []
					unreadable = True
				files.sort(key = sortKey)
				tmpfiles = files[:]
				for x in tmpfiles:
					if os_path.isdir(directory + x):
						directories.append(directory + x + "/")
						files.remove(x)

		if directory is not None and self.showDirectories and not self.isTop:
			if directory == self.current_mountpoint and self.showMountpoints:
				self.list.append(FileEntryComponent(name = "<" +_("List of Storage Devices") + ">", absolute = None, isDir = True, kind = "parent"))
			elif (directory != "/") and not (self.inhibitMounts and self.getMountpoint(directory) in self.inhibitMounts):
				self.list.append(FileEntryComponent(name = "<" +_("Parent Directory") + ">", absolute = '/'.join(directory.split('/')[:-2]) + '/', isDir = True, kind = "parent"))

		if self.showDirectories:
			for x in directories:
				if not (self.inhibitMounts and self.getMountpoint(x) in self.inhibitMounts) and not self.inParentDirs(x, self.inhibitDirs):
					name = x.split('/')[-2]
					self.list.append(FileEntryComponent(name = name, absolute = x, isDir = True))

		if self.showFiles:
			for x in files:
				if self.useServiceRef:
					path = x.getPath()
					name = path.split('/')[-1]
				else:
					path = directory + x
					name = x

				if (self.matchingPattern is None) or re_compile(self.matchingPattern).search(path):
					self.list.append(FileEntryComponent(name = name, absolute = x , isDir = False))

		if self.showMountpoints and len(self.list) == 0:
			self.list.append(FileEntryComponent(name = _("nothing connected"), absolute = None, isDir = False, kind = "storage"))

		if directory is not None:
			shown = [x for x in self.list if x[0][0] is not None and not (x[0][1] and x[1][7].startswith('<'))]
			if unreadable:
				self.hds_stare = "fara_acces"
			elif not shown:
				try:
					# a list of folders only (the choice of a folder): "no folders here", not "nothing to show"
					self.hds_stare = listdir(directory) and (self.showFiles and "nimic" or "fara_dosare") or "gol"
				except OSError:
					self.hds_stare = "fara_acces"

		self.setCards(cards)
		self.l.setList(self.list)

		if select is not None:
			i = 0
			self.moveToIndex(0)
			for x in self.list:
				p = x[0][0]
				
				if isinstance(p, eServiceReference):
					p = p.getPath()
				
				if p == select:
					self.moveToIndex(i)
				i += 1

		for f in self.onDirectoryChanged:
			f()

	def getCurrentDirectory(self):
		return self.current_directory

	def canDescent(self):
		if self.getSelection() is None:
			return False
		return self.getSelection()[1]

	def descent(self):
		if self.getSelection() is None:
			return
		self.changeDir(self.getSelection()[0], select = self.current_directory)

	def getFilename(self):
		if self.getSelection() is None:
			return None
		x = self.getSelection()[0]
		if isinstance(x, eServiceReference):
			x = x.getPath()
		return x

	def getServiceRef(self):
		if self.getSelection() is None:
			return None
		x = self.getSelection()[0]
		if isinstance(x, eServiceReference):
			return x
		return None

	def execBegin(self):
		harddiskmanager.on_partition_list_change.append(self.partitionListChanged)

	def execEnd(self):
		harddiskmanager.on_partition_list_change.remove(self.partitionListChanged)

	def refresh(self):
		self.changeDir(self.current_directory, self.getFilename())

	def partitionListChanged(self, action, device):
		self.refreshMountpoints()
		if self.current_directory is None:
			self.refresh()


def MultiFileSelectEntryComponent(name, absolute = None, isDir = False, selected = False, kind = None):
	res = [ (absolute, isDir, selected, name) ]
	rect, skinned = getParameterFromSkin("FileListMultiName", (55, 1, 470, 20))
	res.append((eListboxPythonMultiContent.TYPE_TEXT, rect[0], rect[1], rect[2], rect[3], 0, RT_HALIGN_LEFT | (skinned and RT_VALIGN_CENTER or 0), safeText(name)))
	png, from_skin = fileEntryIcon(name, isDir, kind)
	if png is not None:
		rect, skinned = getParameterFromSkin("FileListMultiIcon", (30, 2, 20, 20))
		if skinned:
			rect = centerPixmap(rect, png)
		res.append((from_skin and eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND or eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST, rect[0], rect[1], rect[2], rect[3], png))

	if not name.startswith('<'):
		state = selected is False and "off" or "on"
		icon, from_skin = getListPixmap("FileListMultiLockImage", state, resolveFilename(SCOPE_CURRENT_SKIN, "skin_default/icons/lock_%s.png" % state))
		if icon is not None:
			rect, skinned = getParameterFromSkin("FileListMultiLock", (2, 0, 25, 25))
			if skinned:
				rect = centerPixmap(rect, icon)
			res.append((from_skin and eListboxPythonMultiContent.TYPE_PIXMAP_ALPHABLEND or eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST, rect[0], rect[1], rect[2], rect[3], icon))

	return res


class MultiFileSelectList(FileList):
	def __init__(self, preselectedFiles, directory, showMountpoints = False, matchingPattern = None, showDirectories = True, showFiles = True,  useServiceRef = False, inhibitDirs = False, inhibitMounts = False, isTop = False, enableWrapAround = False, additionalExtensions = None):
		self.selectedFiles = preselectedFiles
		if self.selectedFiles is None:
			self.selectedFiles = []
		FileList.__init__(self, directory, showMountpoints = showMountpoints, matchingPattern = matchingPattern, showDirectories = showDirectories, showFiles = showFiles,  useServiceRef = useServiceRef, inhibitDirs = inhibitDirs, inhibitMounts = inhibitMounts, isTop = isTop, enableWrapAround = enableWrapAround, additionalExtensions = additionalExtensions)
		self.changeDir(directory)			
		font, height = getListFont("FileListMulti", ("Regular", 20, 25))
		self.l.setItemHeight(height)
		self.l.setFont(0, font)
		self.onSelectionChanged = [ ]

	def selectionChanged(self):
		for f in self.onSelectionChanged:
			f()

	def changeSelectionState(self):
		idx = self.l.getCurrentSelectionIndex()
		count = 0
		newList = []
		for x in self.list:
			if idx == count:
				if x[0][3].startswith('<'):
					newList.append(x)
				else:
					if x[0][1] is True:
						realPathname = x[0][0]
					else:
						realPathname = self.current_directory + x[0][0]
					if x[0][2] == True:
						SelectState = False
						for entry in self.selectedFiles:
							if entry == realPathname:
								self.selectedFiles.remove(entry)
	
					else:
						SelectState = True
						alreadyinList = False	
						for entry in self.selectedFiles:
							if entry == realPathname:
								alreadyinList = True
						if not alreadyinList:
							self.selectedFiles.append(realPathname)
					newList.append(MultiFileSelectEntryComponent(name = x[0][3], absolute = x[0][0], isDir = x[0][1], selected = SelectState ))
			else:
				newList.append(x)
			
			count += 1
		
		self.list = newList
		self.l.setList(self.list)
	
	def getSelectedList(self):
		return self.selectedFiles

	def changeDir(self, directory, select = None):
		self.list = []

		# if we are just entering from the list of mount points:
		if self.current_directory is None:
			if directory and self.showMountpoints:
				self.current_mountpoint = self.getMountpointLink(directory)
			else:
				self.current_mountpoint = None
		self.current_directory = directory
		directories = []
		files = []

		if directory is None and self.showMountpoints: # present available mountpoints
			for p in harddiskmanager.getMountedPartitions():
				path = os_path.join(p.mountpoint, "")
				if path not in self.inhibitMounts and not self.inParentDirs(path, self.inhibitDirs):
					self.list.append(MultiFileSelectEntryComponent(name = p.description, absolute = path, isDir = True, kind = "storage"))
			files = [ ]
			directories = [ ]
		elif directory is None:
			files = [ ]
			directories = [ ]
		elif self.useServiceRef:
			root = eServiceReference("2:0:1:0:0:0:0:0:0:0:" + directory)
			if self.additional_extensions:
				root.setName(self.additional_extensions)
			serviceHandler = eServiceCenter.getInstance()
			list = serviceHandler.list(root)

			while 1:
				s = list.getNext()
				if not s.valid():
					del list
					break
				if s.flags & s.mustDescent:
					directories.append(s.getPath())
				else:
					files.append(s)
			directories.sort()
			files.sort()
		else:
			if fileExists(directory):
				try:
					files = listdir(directory)
				except:
					files = []
				files.sort()
				tmpfiles = files[:]
				for x in tmpfiles:
					if os_path.isdir(directory + x):
						directories.append(directory + x + "/")
						files.remove(x)

		if directory is not None and self.showDirectories and not self.isTop:
			if directory == self.current_mountpoint and self.showMountpoints:
				self.list.append(MultiFileSelectEntryComponent(name = "<" +_("List of Storage Devices") + ">", absolute = None, isDir = True, kind = "parent"))
			elif (directory != "/") and not (self.inhibitMounts and self.getMountpoint(directory) in self.inhibitMounts):
				self.list.append(MultiFileSelectEntryComponent(name = "<" +_("Parent Directory") + ">", absolute = '/'.join(directory.split('/')[:-2]) + '/', isDir = True, kind = "parent"))

		if self.showDirectories:
			for x in directories:
				if not (self.inhibitMounts and self.getMountpoint(x) in self.inhibitMounts) and not self.inParentDirs(x, self.inhibitDirs):
					name = x.split('/')[-2]
					alreadySelected = False
					for entry in self.selectedFiles:
						if entry  == x:
							alreadySelected = True					
					if alreadySelected:		
						self.list.append(MultiFileSelectEntryComponent(name = name, absolute = x, isDir = True, selected = True))
					else:
						self.list.append(MultiFileSelectEntryComponent(name = name, absolute = x, isDir = True, selected = False))
						
		if self.showFiles:
			for x in files:
				if self.useServiceRef:
					path = x.getPath()
					name = path.split('/')[-1]
				else:
					path = directory + x
					name = x

				if (self.matchingPattern is None) or re_compile(self.matchingPattern).search(path):
					alreadySelected = False
					for entry in self.selectedFiles:
						if os_path.basename(entry)  == x:
							alreadySelected = True	
					if alreadySelected:
						self.list.append(MultiFileSelectEntryComponent(name = name, absolute = x , isDir = False, selected = True))
					else:
						self.list.append(MultiFileSelectEntryComponent(name = name, absolute = x , isDir = False, selected = False))

		self.l.setList(self.list)

		if select is not None:
			i = 0
			self.moveToIndex(0)
			for x in self.list:
				p = x[0][0]
				
				if isinstance(p, eServiceReference):
					p = p.getPath()
				
				if p == select:
					self.moveToIndex(i)
				i += 1

