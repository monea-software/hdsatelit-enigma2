from enigma import loadPNG, loadJPG

pixmap_cache = {}

def LoadPixmap(path, desktop = None, cached = False, width = 0, height = 0, scaletoFit = 0, align = 0, autoDetect = False, size = None):
	# width/height/scaletoFit/align/autoDetect/size: argumentele trimise de pluginurile scrise pentru celelalte imagini Enigma2 (acolo
	# pentru SVG). Imaginea noastra incarca PNG si JPG la marimea lor; argumentele sunt primite, ca apelul sa nu cada.
	if autoDetect and path[-4:] not in (".png", ".jpg"):
		try:
			with open(path, "rb") as f:
				antet = bytearray(f.read(4))
			if antet[:4] == bytearray((0x89, 0x50, 0x4E, 0x47)):
				ptr = loadPNG(path)
			elif antet[:2] == bytearray((0xFF, 0xD8)):
				ptr = loadJPG(path)
			else:
				ptr = None
			if ptr and desktop:
				desktop.makeCompatiblePixmap(ptr)
			return ptr
		except (IOError, OSError):
			return None
	if path in pixmap_cache:
		return pixmap_cache[path]

	if path[-4:] == ".png":
		ptr = loadPNG(path)
	elif path[-4:] == ".jpg":
		ptr = loadJPG(path)
	elif path[-1:] == ".":
		alpha = loadPNG(path + "a.png")
		ptr = loadJPG(path + "rgb.jpg", alpha)
	else:
		raise Exception("neither .png nor .jpg, please fix file extension")
	if ptr and desktop:
		desktop.makeCompatiblePixmap(ptr)

	if cached:
		pixmap_cache[path] = ptr

	return ptr
