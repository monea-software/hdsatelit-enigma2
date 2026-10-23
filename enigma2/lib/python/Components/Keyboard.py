# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Components.Console import Console
from os import listdir as os_listdir, path as os_path
from re import compile as re_compile
from enigma import eEnv

# a keymap is a file name in ${datadir}/keymaps, never a path (HDSatelit)
KMAP_NAME_RX = re_compile(r'[A-Za-z0-9][A-Za-z0-9_.+-]*')

class Keyboard:
	def __init__(self):
		self.keyboardmaps = []
		self.readKeyboardMapFiles()

	def readKeyboardMapFiles(self):
		for keymapfile in os_listdir(eEnv.resolve('${datadir}/keymaps/')):
			if (keymapfile.endswith(".info")):
				f = open(eEnv.resolve('${datadir}/keymaps/') + keymapfile, encoding="utf-8", errors="replace")
				mapfile = None
				mapname = None
				for line in f:
					m = re_compile(r'^\s*(\w+)\s*=\s*(.*)\s*$').match(line)
					if m:
						key, val = m.groups()
						if key == 'kmap':
						    mapfile = val.strip() if KMAP_NAME_RX.fullmatch(val.strip()) else None
						if key == 'name':
						    mapname = val
						if (mapfile is not None) and (mapname is not None):
						    self.keyboardmaps.append(( mapfile,mapname))
				f.close()

		if len(self.keyboardmaps) == 0:
			self.keyboardmaps = [('dream-de.kmap', 'Keyboard Deutsch'), ('eng.kmap', 'Keyboard English')]

	def activateKeyboardMap(self, index):
		try:
			keymap = self.keyboardmaps[index]
			print("Activating keymap:",keymap[1])
			if not KMAP_NAME_RX.fullmatch(keymap[0]):
				print("Keymap name refused:", keymap[0])
				return
			keymappath = eEnv.resolve('${datadir}/keymaps/') + keymap[0]
			if os_path.exists(keymappath):
				# loadkmap reads the map on its standard input; the path is an argument of a fixed script, not shell text
				Console().ePopen(("/bin/sh", "sh", "-c", 'exec loadkmap < "$1"', "sh", keymappath))
		except:
			print("Selected keymap does not exist!")

	def getKeyboardMaplist(self):
		return self.keyboardmaps

	def getDefaultKeyboardMap(self):
		return 'eng.kmap'

keyboard = Keyboard()
