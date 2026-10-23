# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""HDSatelit: what the file browsers (media player, picture player, choice of a folder) show about the stick, the
internal memory and the files on them.

  - storage devices: a plain name ("Stick USB", "Memoria interna", "Retea"), a kind for the icon, the free space;
  - files: the kind ("Film", "Muzica", "Poza"...), the size and the date, the size of a picture read from its header;
  - the path as "Stick USB > Filme > Seriale";
  - HdsPanouFisiere: the path bar and the details panel of a screen with a FileList (widgets hds_*; a skin that does
    not place them simply does not draw them).

Nothing here runs a shell command: file names only go to os.* functions. The free space of a network folder is not
read (statvfs on a share that went away can block the receiver for a long time)."""

import os
import re
import struct
import time

# the fixed mount points of the image (Components/Harddisk.py) -> kind of device
FIXED_KINDS = {
	"/": "flash",
	"/media/usb": "usb",
	"/media/hdd": "hdd",
	"/media/net": "net",
	"/media/card": "card",
	"/media/cf": "card",
	"/media/mmc1": "card",
	"/media/cdrom": "dvd",
	"/media/dvd": "dvd",
}
DEVICE_KINDS = ("usb", "hdd", "net", "flash", "card", "dvd")
NETWORK_FS = ("cifs", "smbfs", "smb3", "nfs", "nfs4", "fuse.sshfs", "sshfs", "davfs", "fuse.davfs2", "ftpfs", "fuse.curlftpfs")

MOUNTS_FILE = "/proc/mounts"

_OCTAL = re.compile(r"\\([0-7]{3})")

def _octal(s):
	# /proc/mounts writes spaces and tabs in paths as octal escapes (a space is backslash 040)
	return _OCTAL.sub(lambda m: chr(int(m.group(1), 8)), s)

def readMountTable():
	"""{mountpoint without the last '/': (source, fstype)} from /proc/mounts (HDS_PROBA_MOUNTS in tests)"""
	table = {}
	try:
		with open(os.environ.get("HDS_PROBA_MOUNTS") or MOUNTS_FILE, encoding="utf-8", errors="surrogateescape") as f:
			for line in f:
				parts = line.split()
				if len(parts) >= 3:
					table[_octal(parts[1]).rstrip("/") or "/"] = (_octal(parts[0]), parts[2])
	except (IOError, OSError):
		pass
	return table

def isNetworkSource(source, fstype = ""):
	if fstype in NETWORK_FS:
		return True
	source = source or ""
	# //server/share (cifs), server:/path (nfs), user@server:path (sshfs)
	return source.startswith("//") or (":" in source and not source.startswith("/"))

def publicSource(source):
	"""the source of a network folder without a user name (user@server, //user@server/share)"""
	if "@" in source:
		prefix = source.startswith("//") and "//" or ""
		source = prefix + source.split("@", 1)[1]
	return source

def _usbDisk(device):
	# /sys/block/sda -> .../usb1/1-1/... for a USB disk
	name = "".join(c for c in (device or "")[:3] if c.isalnum())
	if not name:
		return False
	try:
		return "/usb" in os.path.realpath("/sys/block/" + name)
	except OSError:
		return False

def mountKey(path):
	return path.rstrip("/") or "/"

# /sys/block of the running system (tests point it to a folder of their own)
SYS_BLOCK = "/sys/block/"
_DISK_RX = re.compile(r"^(sd[a-z]+|hd[a-z]+|vd[a-z]+|mmcblk[0-9]+|nvme[0-9]+n[0-9]+)")

def removableDisk(device):
	"""/sys/block/<disk>/removable of a partition (sda1 -> sda): True for a stick or a card reader, False for a hard
	disk (also on USB), None when it is not known"""
	m = _DISK_RX.match(device or "")
	if not m:
		return None
	try:
		with open(SYS_BLOCK + m.group(1) + "/removable") as f:
			return f.read().strip() == "1"
	except (IOError, OSError, ValueError):
		return None

# model names without meaning for people, as makers of cheap sticks write them (read from /sys/block/<disk>/device/model)
GENERIC_MODELS = ("USB DRIVE", "USB DISK", "USB FLASH DRIVE", "USB FLASH DISK", "USB FLASH MEMORY", "FLASH DISK",
	"FLASH DRIVE", "FLASHDISK", "MASS STORAGE", "MASS STORAGE DEVICE", "USB MASS STORAGE", "USB STORAGE",
	"STORAGE DEVICE", "USB DEVICE", "DISK", "UDISK", "USB", "PRODUCT", "DISK 2 0", "USB DISK 2 0", "USB DISK 3 0")

def isGenericModel(description):
	name = re.sub(r"[^A-Z0-9]+", " ", (description or "").upper()).strip()
	return not name or name in GENERIC_MODELS or name.startswith("GENERIC")

def _mountedDevice(key, table):
	"""the device behind a stable name: the mount itself (/media/hdd mounted there) or the mount the link leads to
	(/media/hdd -> /run/media/<label>-sda1); local links in /media only"""
	source = table.get(key, ("", ""))[0]
	if not source:
		try:
			source = table.get(mountKey(os.path.realpath(key)), ("", ""))[0]
		except (OSError, ValueError):
			source = ""
	return source[5:] if source.startswith("/dev/") else None

def deviceKind(mountpoint, device = None, table = None):
	key = mountKey(mountpoint)
	if table is None:
		table = readMountTable()
	source, fstype = table.get(key, ("", ""))
	if isNetworkSource(source, fstype):
		return "net"
	if key == "/media/hdd" or key.startswith("/media/usb"):
		# the stable names (Components/Harddisk.py) go to the first devices, stick or disk: the kind comes from the
		# device, not from the name of the place
		removable = removableDisk(device or _mountedDevice(key, table))
		if removable is not None:
			return removable and "usb" or "hdd"
	if key in FIXED_KINDS:
		return FIXED_KINDS[key]
	if key.startswith("/media/usb"):
		return "usb"
	if _usbDisk(device):
		return removableDisk(device) is False and "hdd" or "usb"
	if key.startswith("/media/net") or key.startswith("/media/autofs"):
		return "net"
	if device and device.startswith(("mmcblk", "mmc")):
		return "card"
	if device and device.startswith("sr"):
		return "dvd"
	return "hdd"

def deviceName(mountpoint, description = "", device = None, kind = None, table = None):
	"""a plain name for a storage device, in the language of the menus"""
	if kind is None:
		kind = deviceKind(mountpoint, device, table)
	key = mountKey(mountpoint)
	if key == "/":
		return _("Internal memory")
	if key in FIXED_KINDS or not description or description.startswith("External Storage") or isGenericModel(description.split(" (Partition")[0]):
		base = {
			"usb": _("USB Stick"),
			"hdd": _("Harddisk"),
			"net": _("Network share"),
			"flash": _("Internal memory"),
			"card": _("Memory card"),
			"dvd": _("DVD Drive"),
		}.get(kind, _("Storage device"))
		if key in FIXED_KINDS:
			return base
		# a hotplug device without a model name: the kind and the partition
		return "%s (%s)" % (base, device or os.path.basename(key))
	# the model read from the device ("SanDisk Cruzer (Partition 1)") stays as it is
	return _(description)

def spaceInfo(path, kind = None):
	"""(free, total) in bytes, or None (network folder, not mounted, error)"""
	if kind == "net" or not path:
		return None
	try:
		s = os.statvfs(path)
	except (OSError, TypeError, ValueError):
		return None
	total = s.f_blocks * s.f_frsize
	if total <= 0:
		return None
	return s.f_bavail * s.f_frsize, total

def formatSize(n):
	"""4,3 GB / 734 MB / 12 kB / 512 B (in the Romanian way, with a comma)"""
	if n is None:
		return ""
	n = float(n)
	for unit in ("B", "kB", "MB", "GB"):
		if n < 1024:
			break
		n /= 1024.0
	else:
		unit = "TB"
	if unit == "B":
		return "%d B" % n
	text = n < 10 and ("%.1f" % n) or ("%d" % round(n))
	return "%s %s" % (text.replace(".", ","), unit)

def formatDate(timestamp):
	try:
		return time.strftime("%d.%m.%Y %H:%M", time.localtime(timestamp))
	except (ValueError, OverflowError, OSError, TypeError):
		return ""

def fileKind(name, isDir = False):
	"""the kind of a row: directory, parent, movie, music, picture, playlist, package, text, file"""
	if isDir:
		return name.startswith("<") and "parent" or "directory"
	from Components.FileList import EXTENSIONS, EXTRA_KINDS
	extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
	return EXTENSIONS.get(extension) or EXTRA_KINDS.get(extension) or "file"

def kindLabel(kind):
	return {
		"directory": _("Folder"),
		"parent": _("Folder"),
		"movie": _("Video file"),
		"music": _("Music file"),
		"picture": _("Picture file"),
		"playlist": _("Playlist file"),
		"package": _("Package or archive"),
		"text": _("Text file"),
	}.get(kind, _("Other file"))

# ------------------------------------------------------------------ the size of a picture, from its header

PICTURE_MAGIC = (b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"BM", b"\xff\xd8")

def isPictureFile(path):
	"""True when the first bytes are the header of a picture format the receiver can decode (JPEG, PNG, GIF, BMP,
	WEBP). A cheap check used as a gate before ePicLoad: a file that fails it is surely not a picture (a truncated
	or renamed file), so it is skipped; a file that passes it is handed to ePicLoad, which reports a decode failure
	on its own. It does not guarantee the picture is whole, only that it is worth trying."""
	try:
		with open(path, "rb") as f:
			head = f.read(16)
	except (IOError, OSError):
		return False
	if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
		return True
	return any(head.startswith(m) for m in PICTURE_MAGIC)

def imageSize(path, limit = 1 << 20):
	"""(width, height) of a JPEG, PNG, GIF, BMP or WEBP file read from its header (one bounded read), or None.
	At most `limit` bytes are read, and the JPEG scan runs over that buffer, so a huge file without a frame header
	cannot hold the receiver (this runs when the cursor rests on a picture row)."""
	try:
		with open(path, "rb") as f:
			buf = f.read(limit)
	except (IOError, OSError):
		return None
	def clamp(w, h):
		# a corrupt header can hold absurd numbers; a picture the receiver can open is far smaller
		if 0 < w <= 100000 and 0 < h <= 100000:
			return w, h
		return None
	try:
		if buf[:8] == b"\x89PNG\r\n\x1a\n" and buf[12:16] == b"IHDR":
			w, h = struct.unpack(">II", buf[16:24])
			return clamp(w, h)
		if buf[:6] in (b"GIF87a", b"GIF89a"):
			w, h = struct.unpack("<HH", buf[6:10])
			return clamp(w, h)
		if buf[:2] == b"BM" and len(buf) >= 26:
			w, h = struct.unpack("<ii", buf[18:26])
			return clamp(abs(w), abs(h))
		if buf[:4] == b"RIFF" and buf[8:12] == b"WEBP":
			chunk = buf[12:16]
			rest = buf[16:32]
			if chunk == b"VP8X":
				return clamp(1 + int.from_bytes(rest[8:11], "little"), 1 + int.from_bytes(rest[11:14], "little"))
			if chunk == b"VP8 ":
				w, h = struct.unpack("<HH", rest[10:14])
				return clamp(w & 0x3fff, h & 0x3fff)
			if chunk == b"VP8L":
				v = int.from_bytes(rest[5:9], "little")
				return clamp((v & 0x3fff) + 1, ((v >> 14) & 0x3fff) + 1)
			return None
		if buf[:2] != b"\xff\xd8":
			return None
		# JPEG: walk the segments of the buffer up to the frame header (SOFn)
		i = 2
		n = len(buf)
		for _step in range(512):
			while i < n and buf[i] != 0xff:
				i += 1
			while i < n and buf[i] == 0xff:
				i += 1
			if i >= n:
				return None
			marker = buf[i]
			i += 1
			if marker in (0xd8, 0x01) or 0xd0 <= marker <= 0xd7:
				continue
			if i + 2 > n:
				return None
			length = struct.unpack(">H", buf[i:i + 2])[0]
			if 0xc0 <= marker <= 0xcf and marker not in (0xc4, 0xc8, 0xcc):
				if i + 7 > n:
					return None
				h, w = struct.unpack(">HH", buf[i + 3:i + 7])
				return clamp(w, h)
			if length < 2:
				return None
			i += length
	except (struct.error, ValueError):
		pass
	return None

# ------------------------------------------------------------------ the path as "Stick USB > Filme > Seriale"

def safeText(s):
	"""a string the on-screen text can always draw. A file or folder name whose bytes are not valid UTF-8 (a stick
	formatted on another system) comes back from the system with lone surrogate characters; the text drawing cannot
	encode those and aborts the receiver when it tries to paint the row, so they are replaced with the standard mark.
	Names that are already valid (nearly all) are returned unchanged and cheaply."""
	if not isinstance(s, str):
		return s
	try:
		s.encode("utf-8")
		return s
	except UnicodeEncodeError:
		return s.encode("utf-8", "replace").decode("utf-8")

SEPARATOR = u" › "

def mountedPartitions():
	try:
		from Components.Harddisk import harddiskmanager
		return harddiskmanager.getMountedPartitions()
	except Exception:
		return []

def partitionFor(path, partitions = None):
	"""the mounted partition that holds `path` (the longest mount point that is a prefix of it)"""
	best = None
	path = os.path.join(path, "")
	for p in partitions if partitions is not None else mountedPartitions():
		m = os.path.join(p.mountpoint, "")
		if path.startswith(m) and (best is None or len(m) > len(os.path.join(best.mountpoint, ""))):
			best = p
	return best

def breadcrumb(directory, maxChars = 64, partitions = None, table = None):
	if not directory:
		return _("Storage devices")
	p = partitionFor(directory, partitions)
	if p is not None:
		head = deviceName(p.mountpoint, p.description, p.device, table = table)
		rest = directory[len(os.path.join(p.mountpoint, "")):]
	else:
		head = _("Internal memory")
		rest = directory.lstrip("/")
	parts = [x for x in rest.split("/") if x]
	text = SEPARATOR.join([head] + parts)
	# too long: the device, "...", then as many of the last folders as fit
	if len(text) > maxChars and parts:
		tail = []
		for x in reversed(parts):
			candidate = SEPARATOR.join([head, u"…"] + [x] + tail)
			if len(candidate) > maxChars and tail:
				break
			tail.insert(0, x)
		text = SEPARATOR.join([head, u"…"] + tail)
		if len(text) > maxChars:
			text = text[:maxChars - 1] + u"…"
	return safeText(text)

def shortName(name, maxChars):
	"""a long name cut in the middle to `maxChars` characters, keeping its end with the extension
	("Fotografie de…na veche.jpg"), as the file browsers of televisions do"""
	if not name or len(name) <= maxChars:
		return name
	stem, dot, ext = name.rpartition(".")
	tail = (dot and stem and 0 < len(ext) <= 5) and (len(ext) + 6) or 6
	tail = min(tail, maxChars // 2)
	head = max(1, maxChars - 1 - tail)
	return name[:head].rstrip(" -_,.") + u"…" + name[-tail:].lstrip(" -_,")

# ------------------------------------------------------------------ names typed by the user

def isSafeName(name):
	"""a new file or folder name typed on the remote: one name, no path. No '/' or '\\', no NUL, not '.' or '..'
	and not hidden (leading dot), at most 255 bytes"""
	if not name or name != name.strip() or len(name.encode("utf-8", "replace")) > 255:
		return False
	if "/" in name or "\\" in name or "\0" in name or name.startswith("."):
		return False
	return os.path.basename(name) == name

def unsafeNameMessage():
	return _("The name cannot contain / or \\, cannot start with a dot and must fit in 255 characters.")

# ------------------------------------------------------------------ details of the selected row

def rowPath(row, directory):
	"""(absolute path or None, isDir) of a FileList row: [ (absolute, isDir), ... ]; files are named relative to the
	current directory, or by an eServiceReference in the media player"""
	try:
		absolute, isDir = row[0][0], row[0][1]
	except (IndexError, TypeError):
		return None, False
	if absolute is None:
		return None, isDir
	if hasattr(absolute, "getPath"):
		absolute = absolute.getPath()
	if not isinstance(absolute, str):
		return None, isDir
	if not isDir and not absolute.startswith("/") and directory:
		absolute = os.path.join(directory, absolute)
	return absolute, isDir

def rowName(row):
	try:
		return row[1][7]
	except (IndexError, TypeError):
		return ""

class Details(object):
	"""what the details panel shows for one row"""
	def __init__(self):
		self.name = ""
		self.meta = ""
		self.extra = ""
		self.icon = None     # key of navigator/mare_<key>.png
		self.space = None    # percent used, for the bar of a device

def detailsFor(row, directory, table = None):
	d = Details()
	if row is None:
		return d
	path, isDir = rowPath(row, directory)
	name = rowName(row)
	d.name = name
	if directory is None and isDir and path:
		# a storage device
		p = partitionFor(path)
		if table is None:
			table = readMountTable()
		kind = deviceKind(path, p and p.device, table)
		d.icon = kind
		source, fstype = table.get(mountKey(path), ("", ""))
		label = kind == "net" and _("Network folder") or _("Storage device")
		d.meta = "  ·  ".join(x for x in (label, fstype) if x)
		if kind == "net":
			d.extra = publicSource(source)
		else:
			space = spaceInfo(path, kind)
			if space:
				free, total = space
				used = int(round(100.0 * (total - free) / total))
				d.space = max(0, min(100, used))
				d.extra = (_("%s free of %s") % (formatSize(free), formatSize(total))) + "  ·  " + (_("%d%% used") % d.space)
		return d
	if isDir:
		if name.startswith("<"):
			d.icon = "parent"
			d.meta = path and breadcrumb(path, 60, table = table) or _("Storage devices")
			return d
		d.icon = "directory"
		try:
			st = os.stat(path)
			d.meta = "  ·  ".join((_("Folder"), formatDate(st.st_mtime)))
		except (OSError, TypeError):
			d.meta = _("Folder")
		# the free space of the device that holds the folder (not for network folders)
		p = partitionFor(path)
		if p is not None:
			if table is None:
				table = readMountTable()
			space = spaceInfo(p.mountpoint, deviceKind(p.mountpoint, p.device, table))
			if space:
				free, total = space
				d.space = max(0, min(100, int(round(100.0 * (total - free) / total))))
				d.extra = _("%s free of %s") % (formatSize(free), formatSize(total))
		return d
	if not path:
		return d
	kind = fileKind(name)
	d.icon = kind
	parts = [kindLabel(kind)]
	try:
		st = os.stat(path)
		parts += [formatSize(st.st_size), formatDate(st.st_mtime)]
	except (OSError, TypeError):
		pass
	d.meta = "  ·  ".join(x for x in parts if x)
	if kind == "picture":
		size = imageSize(path)
		if size:
			d.extra = _("Resolution %d × %d") % size
	return d

# ------------------------------------------------------------------ the widgets of a screen

def navigatorImage(name, key = None):
	"""an image of the skin set in <hdsparameters> (HdsNavigatorImage = "navigator/mare_%s.png", HdsMiniaturaImage),
	for `key`; None with a skin that does not set it"""
	try:
		from skin import getListImage
		return getListImage(name, key)
	except Exception:
		return None

class HdsPanouFisiere(object):
	"""the path bar and the details panel of a screen that browses files with a FileList. Widgets:
	  hds_cale (path), hds_stare (empty or unreadable folder, over the list), and with details=True:
	  hds_nume, hds_detalii, hds_extra, hds_tip_icoana (96x96 icon, HdsNavigatorImage of the skin), hds_spatiu (bar
	  of used space of the device, for devices and folders).
	They are drawn only where the skin places them."""

	def __init__(self, screen, filelist, details = True, nameChars = 100):
		from Components.Label import Label
		from Components.Pixmap import Pixmap
		from Components.ProgressBar import ProgressBar
		self.screen = screen
		self.filelist = filelist
		self.details = details
		# the name in the details panel: two lines at most (about 100 characters at 948 px, 56 at 536 px)
		self.nameChars = nameChars
		screen["hds_cale"] = Label("")
		screen["hds_stare"] = Label("")
		if details:
			screen["hds_nume"] = Label("")
			screen["hds_detalii"] = Label("")
			screen["hds_extra"] = Label("")
			screen["hds_tip_icoana"] = Pixmap()
			screen["hds_spatiu"] = ProgressBar()
		self.lastIcon = False
		filelist.onSelectionChanged.append(self.updateSelection)
		hook = getattr(filelist, "onDirectoryChanged", None)
		if hook is not None:
			hook.append(self.updateDirectory)
		screen.onLayoutFinish.append(self.updateAll)
		screen.onClose.append(self.__onClose)

	def __onClose(self):
		try:
			self.filelist.onSelectionChanged.remove(self.updateSelection)
		except ValueError:
			pass
		hook = getattr(self.filelist, "onDirectoryChanged", None)
		if hook is not None and self.updateDirectory in hook:
			hook.remove(self.updateDirectory)

	def updateAll(self):
		self.updateDirectory()

	def updateDirectory(self):
		directory = self.filelist.getCurrentDirectory()
		self.screen["hds_cale"].setText(breadcrumb(directory))
		state = getattr(self.filelist, "hds_stare", None)
		self.screen["hds_stare"].setText({
			"gol": _("This folder is empty"),
			"nimic": _("Nothing to show in this folder"),
			"fara_dosare": _("There are no folders here"),
			"fara_acces": _("This folder cannot be read"),
		}.get(state, ""))
		self.updateSelection()

	def current(self):
		try:
			idx = self.filelist.getSelectionIndex()
			rows = self.filelist.list
			if rows and 0 <= idx < len(rows):
				return rows[idx]
		except Exception:
			pass
		return None

	def updateSelection(self):
		if not self.details:
			return
		try:
			d = detailsFor(self.current(), self.filelist.getCurrentDirectory())
		except Exception as e:
			print("[HdsNavigator] details:", e)
			d = Details()
		s = self.screen
		s["hds_nume"].setText(safeText(shortName(d.name, self.nameChars)))
		s["hds_detalii"].setText(d.meta)
		s["hds_extra"].setText(d.extra)
		if d.space is None:
			s["hds_spatiu"].hide()
		else:
			s["hds_spatiu"].setValue(d.space)
			s["hds_spatiu"].show()
		self.setIcon(d.icon)

	def setIcon(self, key):
		widget = self.screen["hds_tip_icoana"]
		if key == self.lastIcon or widget.instance is None:
			return
		self.lastIcon = key
		path = key and navigatorImage("HdsNavigatorImage", key)
		if not path:
			widget.hide()
			return
		from Tools.LoadPixmap import LoadPixmap
		ptr = LoadPixmap(path, cached = True)
		if ptr is None:
			widget.hide()
			return
		widget.instance.setPixmap(ptr)
		widget.show()
