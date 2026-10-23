# Modificat de moneasoftware.com si hdsatelit.com, 2026
from ServiceReference import ServiceReference
from enigma import eServiceReference
import os

def readPlaylistLines(filename):
	"""The lines of an m3u or pls file, or None if it cannot be read. The text is UTF-8 (a byte order mark is
	dropped); a list saved on Windows in a Romanian or other central European setup is cp1250, so a file that is
	not valid UTF-8 is read as cp1250: its names and paths keep their letters, and a path decoded that way is
	encoded back to UTF-8, the encoding of the file names on the receiver. A file that is neither keeps its
	bytes (surrogateescape), so the path still reaches os.* unchanged."""
	try:
		with open(filename, "rb") as f:
			data = f.read()
	except (IOError, OSError):
		return None
	for encoding, errors in (("utf-8-sig", "strict"), ("cp1250", "strict"), ("utf-8", "surrogateescape")):
		try:
			text = data.decode(encoding, errors)
			break
		except UnicodeDecodeError:
			continue
	return text.splitlines()

class PlaylistIO:
	def __init__(self):
		self.list = []
	
	# returns a list of services or None if filename is not a valid playlist
	def open(self, filename):
		return None
	
	OK = 0
	FILEEXISTS = 1
	WRITEERROR = 2
	ERROR = 3
	UNSUPPORTED_FILES_IN_PLAYLIST = 4
	
	REMOTE_PROTOS = ["http", "https", "udp", "rtsp", "rtp", "mmp"]
	
	def save(self, filename = None):
		return self.ERROR
		
	def clear(self):
		del self.list[:]
		
	def addService(self, service):
		self.list.append(service)

	def getRef(self, filename, entry):
		if entry[0] == "/":
			path = entry
		else:
			path = os.path.dirname(filename) + "/" + entry
			for proto in self.REMOTE_PROTOS:
				if entry.startswith(proto):
					path = entry
		ref = eServiceReference(4097, 0, path)
		return ServiceReference(ref)

class PlaylistIOInternal(PlaylistIO):
	def __init__(self):
		PlaylistIO.__init__(self)

	def open(self, filename):
		self.clear()
		try:
			# surrogateescape, like save(): a file name that is not UTF-8 is kept as its bytes
			file = open(filename, "r", encoding="utf-8", errors="surrogateescape")
		except IOError:
			return None
		while True:
			entry = file.readline().strip()
			if entry == "":
				break
			self.addService(ServiceReference(entry))
		file.close()
		return self.list
		
	def save(self, filename = None):
		print("Writing playlist into file", filename)
		# a service reference to a file whose name is not UTF-8 (a stick with Latin-1 names) comes with
		# surrogates; strict UTF-8 raised UnicodeEncodeError, which MediaPlayer.exit does not catch, so the
		# player could not be closed and playlist.e2pls was left empty. Written back as the original bytes.
		file = open(filename, "w", encoding="utf-8", errors="surrogateescape")
		for x in self.list:
			file.write(str(x) + "\n")
		file.close()
		
		return self.OK
	
class PlaylistIOM3U(PlaylistIO):
	def __init__(self):
		PlaylistIO.__init__(self)
	
	def open(self, filename):
		self.clear()
		self.displayname = None
		lines = readPlaylistLines(filename)
		if lines is None:
			return None
		for entry in lines:
			entry = entry.strip()
			if entry == "":
				continue
			if entry.startswith("#EXTINF:"):
				extinf = entry.split(',',1)
				if len(extinf) > 1:
					self.displayname = extinf[1]
				# TODO: use e2 facilities to create a service ref from file
			elif entry[0] != "#":
				sref = PlaylistIO.getRef(self, filename, entry)
				if self.displayname:
					sref.ref.setName(self.displayname)
					self.displayname = None
				self.addService(sref)
		return self.list
		
	def save(self, filename = None):
		return self.ERROR
	
class PlaylistIOPLS(PlaylistIO):
	def __init__(self):
		PlaylistIO.__init__(self)
	
	def open(self, filename):
		self.clear()
		lines = readPlaylistLines(filename)
		if lines is None:
			return None
		lines = [x.strip() for x in lines]
		if lines and lines[0] == "[playlist]": # extended pls
			for entry in lines[1:]:
				if entry[0:4] == "File":
					pos = entry.find('=') + 1
					newentry = entry[pos:]
					sref = PlaylistIO.getRef(self, filename, newentry)
					self.addService(sref)
		else:
			playlist = PlaylistIOM3U()
			return playlist.open(filename)
		return self.list
		
	def save(self, filename = None):
		return self.ERROR