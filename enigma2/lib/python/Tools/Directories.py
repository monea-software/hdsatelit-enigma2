# -*- coding: utf-8 -*-
# Modificat de moneasoftware.com si hdsatelit.com, 2026

import re
from os import path as os_path, mkdir, rmdir, walk, stat as os_stat, listdir, readlink, makedirs, error as os_error, symlink, access, F_OK, R_OK, W_OK
from stat import S_IMODE
from glob import glob
import subprocess
try:
	from enigma import eEnv
except Exception:
	class _MockEnv:
		@staticmethod
		def resolve(path):
			return path.replace("${sysconfdir}", "/etc").replace("${datadir}", "/usr/share").replace("${libdir}", "/usr/lib")
	eEnv = _MockEnv

try:
	from os import chmod
	have_chmod = True
except:
	have_chmod = False

try:
	from os import utime
	have_utime = True
except:
	have_utime = False

SCOPE_TRANSPONDERDATA = 0
SCOPE_SYSETC = 1
SCOPE_FONTS = 2
SCOPE_SKIN = 3
SCOPE_SKIN_IMAGE = 4
SCOPE_USERETC = 5
SCOPE_CONFIG = 6
SCOPE_LANGUAGE = 7
SCOPE_HDD = 8
SCOPE_PLUGINS = 9
SCOPE_MEDIA = 10
SCOPE_PLAYLIST = 11
SCOPE_CURRENT_SKIN = 12
SCOPE_DEFAULTDIR = 13
SCOPE_DEFAULTPARTITION = 14
SCOPE_DEFAULTPARTITIONMOUNTDIR = 15
SCOPE_METADIR = 16
SCOPE_CURRENT_PLUGIN = 17

# numele cerute de pluginuri
SCOPE_GUISKIN = SCOPE_ACTIVE_SKIN = SCOPE_CURRENT_SKIN
SCOPE_LCDSKIN = 21
SCOPE_ACTIVE_LCDSKIN = SCOPE_CURRENT_LCDSKIN = 22
SCOPE_TIMESHIFT = SCOPE_HDD
SCOPE_LIBDIR = 18
SCOPE_SKINS = SCOPE_SKIN
SCOPE_PLUGIN = SCOPE_PLUGINS
SCOPE_PLUGIN_ABSOLUTE = 19
SCOPE_PLUGIN_RELATIVE = 20

PATH_CREATE = 0
PATH_DONTCREATE = 1
PATH_FALLBACK = 2
defaultPaths = {
		SCOPE_TRANSPONDERDATA: (eEnv.resolve("${sysconfdir}/"), PATH_DONTCREATE),
		SCOPE_SYSETC: (eEnv.resolve("${sysconfdir}/"), PATH_DONTCREATE),
		SCOPE_FONTS: (eEnv.resolve("${datadir}/fonts/"), PATH_DONTCREATE),
		SCOPE_CONFIG: (eEnv.resolve("${sysconfdir}/enigma2/"), PATH_CREATE),
		SCOPE_PLUGINS: (eEnv.resolve("${libdir}/enigma2/python/Plugins/"), PATH_CREATE),

		SCOPE_LANGUAGE: (eEnv.resolve("${datadir}/enigma2/po/"), PATH_DONTCREATE),

		SCOPE_SKIN: (eEnv.resolve("${datadir}/enigma2/"), PATH_DONTCREATE),
		SCOPE_SKIN_IMAGE: (eEnv.resolve("${datadir}/enigma2/"), PATH_DONTCREATE),
		SCOPE_LCDSKIN: (eEnv.resolve("${datadir}/enigma2/display/"), PATH_DONTCREATE),
		SCOPE_HDD: ("/hdd/movie/", PATH_DONTCREATE),
		SCOPE_MEDIA: ("/media/", PATH_DONTCREATE),
		SCOPE_PLAYLIST: (eEnv.resolve("${sysconfdir}/enigma2/playlist/"), PATH_CREATE),
		
		SCOPE_USERETC: ("", PATH_DONTCREATE), # user home directory
		
		SCOPE_DEFAULTDIR: (eEnv.resolve("${datadir}/enigma2/defaults/"), PATH_CREATE),
		SCOPE_DEFAULTPARTITION: ("/dev/mtdblock6", PATH_DONTCREATE),
		SCOPE_DEFAULTPARTITIONMOUNTDIR: (eEnv.resolve("${datadir}/enigma2/dealer"), PATH_CREATE),
		SCOPE_METADIR: (eEnv.resolve("${datadir}/meta"), PATH_CREATE),
	}

FILE_COPY = 0 # copy files from fallback dir to the basedir
FILE_MOVE = 1 # move files
PATH_COPY = 2 # copy the complete fallback dir to the basedir
PATH_MOVE = 3 # move the fallback dir to the basedir (can be used for changes in paths)
fallbackPaths = {
		SCOPE_CONFIG: [("/home/root/", FILE_MOVE),
					   (eEnv.resolve("${datadir}/enigma2/defaults/"), FILE_COPY)],
		SCOPE_HDD: [("/hdd/movies", PATH_MOVE)]
	}

def runFileCommand(args):
	try:
		return subprocess.call(args)
	except OSError as e:
		print("resolveFilename: %s failed: %s" % (args[0], e))
		return 127

def _dosarSkin(nume_setare):
	try:
		from Components.config import config
		return os_path.dirname(getattr(getattr(config.skin, nume_setare, None), "value", "") or "")
	except Exception:
		return ""


def _inaltimeEcran(nr):
	try:
		from enigma import getDesktop
		return getDesktop(nr).size().height()
	except Exception:
		return 0


def _cautaSuprascriere(scope, base):
	"""Ordinea standard pentru locurile pe care cautarea noastra nu le avea; "" cand fisierul nu e in niciunul."""
	config_dir = defaultPaths[SCOPE_CONFIG][0]
	skin_dir = defaultPaths[SCOPE_SKIN][0]
	skin = _dosarSkin("primary_skin")
	if scope == SCOPE_CURRENT_SKIN:
		locuri = [os_path.join(config_dir, skin)] if skin else []
		locuri.append(os_path.join(config_dir, "skin_common"))
		if base.endswith(".xml"):
			locuri.append(config_dir)
		inaltime = _inaltimeEcran(0)
		dupa = [os_path.join(skin_dir, "skin_fallback_%d" % inaltime)] if inaltime else []
	elif scope == SCOPE_LCDSKIN:
		afisaj = _dosarSkin("display_skin")
		locuri = [os_path.join(config_dir, "display", afisaj)] if afisaj else []
		locuri.append(os_path.join(config_dir, "display", "skin_common"))
		dupa = []
	else:
		afisaj = _dosarSkin("display_skin")
		locuri = [os_path.join(config_dir, "fonts")]
		if skin:
			locuri += [os_path.join(config_dir, skin, "fonts"), os_path.join(config_dir, skin)]
		locuri += [os_path.join(config_dir, "skin_common", "fonts"), os_path.join(config_dir, "skin_common")]
		dupa = []
		if not fileExists(os_path.join(defaultPaths[SCOPE_FONTS][0], base)):
			# fonturile din dosarul skin-ului numai cand fontul nu e in /usr/share/fonts (cel de azi ramane primul)
			if skin:
				dupa += [os_path.join(skin_dir, skin, "fonts"), os_path.join(skin_dir, skin)]
			dupa += [os_path.join(skin_dir, "skin_default", "fonts"), os_path.join(skin_dir, "skin_default")]
			if afisaj:
				dupa += [os_path.join(defaultPaths[SCOPE_LCDSKIN][0], afisaj, "fonts"), os_path.join(defaultPaths[SCOPE_LCDSKIN][0], afisaj)]
	for dosar in locuri:
		cale = os_path.join(dosar, base)
		if os_path.isfile(cale):
			return cale
	for dosar in dupa:
		cale = os_path.join(dosar, base)
		if os_path.isfile(cale) and not (scope == SCOPE_CURRENT_SKIN and _gasitDeCautareaNoastra(base)):
			return cale
	return ""


def _gasitDeCautareaNoastra(base):
	"""La SCOPE_CURRENT_SKIN: fisierul e deja in skin-ul ales, in HDSatelit/ sau skin_default/ (cautarea de azi)."""
	skin_dir = defaultPaths[SCOPE_SKIN][0]
	skin = _dosarSkin("primary_skin")
	for dosar in ([skin] if skin else []) + ["HDSatelit", "skin_default"]:
		if fileExists(os_path.join(skin_dir, dosar, base)):
			return True
	return False


def resolveFilename(scope, base = "", path_prefix = None):
	if scope == SCOPE_LIBDIR:
		return os_path.join(eEnv.resolve("${libdir}/"), base)
	if scope in (SCOPE_PLUGIN_ABSOLUTE, SCOPE_PLUGIN_RELATIVE):
		# un fisier din dosarul pluginului care intreaba, dupa cine a chemat
		from sys import _getframe
		cine = os_path.normpath(_getframe(1).f_code.co_filename)
		radacina = os_path.normpath(defaultPaths[SCOPE_PLUGINS][0])
		if cine.startswith(radacina + os_path.sep):
			parti = cine[len(radacina) + 1:].split(os_path.sep)
			if len(parti) > 2:
				if scope == SCOPE_PLUGIN_RELATIVE:
					return os_path.join(parti[0], parti[1], base)
				return os_path.join(radacina, parti[0], parti[1], base)
		return base
	if base[0:2] == "~/":
		# „~/” = dosarul dat in path_prefix (skin_path al ecranului). Fara el, ca in celelalte imagini Enigma2: un avertisment in jurnal
		# si numele ramane cum e (inainte: AssertionError, iar ecranul pluginului cadea).
		if path_prefix is not None:
			base = os_path.join(path_prefix, base[2:])
		else:
			print("[Directories] resolveFilename: %s fara path_prefix" % base)

	# don't resolve absolute paths
	if base[0:1] == '/':
		return base

	# standard (documentatia pentru dezvoltatori, skinning/files): inaintea skin-ului ales se cauta suprascrierile
	# omului, /etc/enigma2/<dosarul skin-ului>/ si /etc/enigma2/skin_common/ (la .xml si /etc/enigma2/); fonturile se cauta
	# si in dosarele skin-ului. Numai cand fisierul exista acolo: altfel totul ramane cum era.
	if base and scope in (SCOPE_CURRENT_SKIN, SCOPE_FONTS, SCOPE_LCDSKIN):
		gasit = _cautaSuprascriere(scope, base)
		if gasit:
			return gasit

	if scope == SCOPE_CURRENT_LCDSKIN:
		from Components.config import config
		tmp = defaultPaths[SCOPE_SKIN]
		ales = getattr(getattr(config.skin, "display_skin", None), "value", "")
		if ales:
			for radacina in (tmp[0], defaultPaths[SCOPE_LCDSKIN][0]):
				xml = os_path.join(radacina, ales)
				if fileExists(xml):
					candidat = os_path.join(os_path.dirname(xml), base)
					if fileExists(candidat):
						return candidat
		path = defaultPaths[SCOPE_LCDSKIN][0]
	elif scope == SCOPE_CURRENT_SKIN:
		from Components.config import config
		tmp = defaultPaths[SCOPE_SKIN]
		pos = config.skin.primary_skin.value.rfind('/')
		if pos != -1:
			#if basefile is not available use default skin path as fallback
			tmpfile = tmp[0]+config.skin.primary_skin.value[:pos+1] + base
			if fileExists(tmpfile):
				path = tmp[0]+config.skin.primary_skin.value[:pos+1]
			elif fileExists(tmp[0] + "HDSatelit/" + base):
				# HDSatelit: cu alt skin ales, imaginile ecranelor HD Satelit pe care acela nu le are vin din skinul
				# imaginii (incarcat dupa el ca rezerva, skin.py)
				path = tmp[0] + "HDSatelit/"
			elif fileExists(tmp[0] + "skin_default/" + base):
				# pictogramele comune cerute cu calea scurta (icons/lock_on.png), cum le cer pluginurile
				path = tmp[0] + "skin_default/"
			else:
				path = tmp[0]
		else:
			path = tmp[0]

	elif scope == SCOPE_CURRENT_PLUGIN:
		tmp = defaultPaths[SCOPE_PLUGINS]
		from Components.config import config
		skintmp = defaultPaths[SCOPE_SKIN]
		pos = config.skin.primary_skin.value.rfind('/')
		if pos != -1:
			#if basefile is not available inside current skin path, use the original provided file as fallback
			skintmpfile = skintmp[0]+config.skin.primary_skin.value[:pos+1] + base
			if fileExists(skintmpfile):
				path = skintmp[0]+config.skin.primary_skin.value[:pos+1]
			else:
				path = tmp[0]
		else:
			path = tmp[0]
	elif scope == SCOPE_SKIN_IMAGE:
		# HDSatelit 0.7.4: temele scrise pentru alte imagini cer imaginile cu calea scurta (buttons/key_red.png) si le
		# asteapta in dosarul temei sau in skin_default; aici calea scurta sub ${datadir}/enigma2/ nu le gasea si ecranul
		# cadea (forumul: o tema din afara pe SF8008, „pixmap file /usr/share/enigma2/buttons/... not found”). Locul de
		# pana acum ramane primul; numai cand fisierul nu e acolo: dosarul temei alese, HDSatelit/, skin_default/.
		tmp = defaultPaths[scope]
		path = tmp[0]
		if not fileExists(path + base):
			try:
				from Components.config import config
				ales = config.skin.primary_skin.value or ""
			except Exception:
				ales = ""
			pos = ales.rfind('/')
			for dosar in ([ales[:pos + 1]] if pos > 0 else []) + ["HDSatelit/", "skin_default/"]:
				if fileExists(tmp[0] + dosar + base):
					path = tmp[0] + dosar
					break
	else:
		tmp = defaultPaths[scope]
		path = tmp[0]

	flags = tmp[1]

	if flags == PATH_CREATE:
		if not pathExists(path):
			try:
				mkdir(path)
			except OSError:
				print("resolveFilename: Couldn't create %s" % path)
				return None

	fallbackPath = fallbackPaths.get(scope)

	# HDSatelit: base comes from the caller, so cp and mv get argument lists, never a shell string
	if fallbackPath and not fileExists(path + base):
		for x in fallbackPath:
			if x[1] == FILE_COPY:
				if fileExists(x[0] + base):
					runFileCommand(["cp", x[0] + base, path + base])
					break
			elif x[1] == FILE_MOVE:
				if fileExists(x[0] + base):
					runFileCommand(["mv", x[0] + base, path + base])
					break
			elif x[1] == PATH_COPY:
				if pathExists(x[0]):
					if not pathExists(defaultPaths[scope][0]):
						mkdir(path)
					# the shell glob of "cp -a dir/* path": names starting with a dot are left out, as before
					files = sorted(glob(x[0] + "*"))
					if files:
						runFileCommand(["cp", "-a"] + files + [path])
					break
			elif x[1] == PATH_MOVE:
				if pathExists(x[0]):
					runFileCommand(["mv", x[0], path])
					break

	# FIXME: we also have to handle DATADIR etc. here.
	return path + base
	# this is only the BASE - an extension must be added later.

def pathExists(path):
	return os_path.exists(path)

def isMount(path):
	# /media/hdd si /media/usb pot fi legaturi spre /run/media/...: ismount pe legatura da False
	return os_path.ismount(os_path.realpath(path))

def createDir(path, makeParents = False):
	try:
		if makeParents:
			makedirs(path)
		else:
			mkdir(path)
	except:
		ret = 0
	else:
		ret = 1
	return ret

def removeDir(path):
	try:
		rmdir(path)
	except:
		ret = 0
	else:
		ret = 1
	return ret

def fileExists(f, mode='r'):
	if mode == 'r':
		acc_mode = R_OK
	elif mode == 'w':
		acc_mode = W_OK
	else:
		acc_mode = F_OK
	return access(f, acc_mode)

def getRecordingFilename(basename, dirname = None):
	# filter out non-allowed characters
	non_allowed_characters = "/.\\:*?<>|\""
	filename = ""
	
	basename = basename.replace('\xc2\x86', '').replace('\xc2\x87', '')
	
	for c in basename:
		if c in non_allowed_characters or ord(c) < 32:
			c = "_"
		filename += c

	if dirname is not None:
		filename = ''.join((dirname, filename))

	# 240 = limita de OCTETI a numelui pe disc; un titlu venit stricat de la emitator (sau un dosar de pe un
	# stick FAT) are surogate U+DC80..U+DCFF, iar encode('UTF-8') strict arunca UnicodeEncodeError si
	# inregistrarea nu mai porneste deloc. "surrogateescape" da exact octetii care ajung pe disc.
	while len(filename.encode('UTF-8', 'surrogateescape')) > 240:
		filename = filename[:-1]

	i = 0
	while True:
		path = resolveFilename(SCOPE_HDD, filename)
		if i > 0:
			path += "_%03d" % i
		try:
			open(path + ".ts")
			i += 1
		except IOError:
			return path

# this is clearly a hack:
def InitFallbackFiles():
	resolveFilename(SCOPE_CONFIG, "userbouquet.favourites.tv")
	resolveFilename(SCOPE_CONFIG, "bouquets.tv")
	resolveFilename(SCOPE_CONFIG, "userbouquet.favourites.radio")
	resolveFilename(SCOPE_CONFIG, "bouquets.radio")

# returns a list of tuples containing pathname and filename matching the given pattern
# example-pattern: match all txt-files: ".*\.txt$"
def crawlDirectory(directory, pattern):
	list = []
	if directory:
		expression = re.compile(pattern)
		for root, dirs, files in walk(directory):
			for file in files:
				if expression.match(file) is not None:
					list.append((root, file))
	return list

def copyfile(src, dst):
	try:
		f1 = open(src, "rb")
		if os_path.isdir(dst):
			dst = os_path.join(dst, os_path.basename(src))
		f2 = open(dst, "w+b")
		while True:
			buf = f1.read(16*1024)
			if not buf:
				break
			f2.write(buf)
		st = os_stat(src)
		mode = S_IMODE(st.st_mode)
		if have_chmod:
			chmod(dst, mode)
		if have_utime:
			utime(dst, (st.st_atime, st.st_mtime))
	except:
		print("copy", src, "to", dst, "failed!")
		return -1
	return 0

def copytree(src, dst, symlinks=False):
	names = listdir(src)
	if os_path.isdir(dst):
		dst = os_path.join(dst, os_path.basename(src))
		if not os_path.isdir(dst):
			mkdir(dst)
	else:
		makedirs(dst)
	for name in names:
		srcname = os_path.join(src, name)
		dstname = os_path.join(dst, name)
		try:
			if symlinks and os_path.islink(srcname):
				linkto = readlink(srcname)
				symlink(linkto, dstname)
			elif os_path.isdir(srcname):
				copytree(srcname, dstname, symlinks)
			else:
				copyfile(srcname, dstname)
		except:
			print("dont copy srcname (no file or link or folder)")
	try:
		st = os_stat(src)
		mode = S_IMODE(st.st_mode)
		if have_chmod:
			chmod(dst, mode)
		if have_utime:
			utime(dst, (st.st_atime, st.st_mtime))
	except:
		print("copy stats for", src, "failed!")

def getSize(path, pattern=".*"):
	path_size = 0
	if os_path.isdir(path):
		files = crawlDirectory(path, pattern)
		for file in files:
			filepath = os_path.join(file[0], file[1])
			path_size += os_path.getsize(filepath)
	elif os_path.isfile(path):
		path_size = os_path.getsize(path)
	return path_size

def isPluginInstalled(pluginName, pluginFile='plugin', pluginType=None):
	types = [pluginType] if pluginType else ['Extensions', 'SystemPlugins']
	for type_name in types:
		for extension in ('c', ''):
			if os_path.isfile(os_path.join(resolveFilename(SCOPE_PLUGINS), type_name, pluginName, f"{pluginFile}.py{extension}")):
				return True
	return False

# ---------------------------------------------------------------- numele cerute de pluginuri
def fileCheck(f, mode="r"):
	return fileExists(f, mode) and f or ""


def fileHas(f, content, mode="r"):
	try:
		with open(f, mode, encoding="utf-8", errors="replace") as fd:
			return content in fd.read()
	except OSError:
		return False


def fileReadLine(filename, default=None, source="", debug=False):
	try:
		with open(filename, "r", encoding="utf-8", errors="replace") as fd:
			return fd.read().strip().replace("\0", "")
	except OSError:
		return default


def fileReadLines(filename, default=None, source="", debug=False):
	try:
		with open(filename, "r", encoding="utf-8", errors="replace") as fd:
			return fd.read().splitlines()
	except OSError:
		return default


def fileWriteLine(filename, line, source="", debug=False):
	try:
		with open(filename, "w", encoding="utf-8") as fd:
			fd.write(str(line))
		return 1
	except OSError:
		return 0


def fileAppendLine(filename, line, source="", debug=False):
	try:
		with open(filename, "a", encoding="utf-8") as fd:
			fd.write(str(line))
		return 1
	except OSError:
		return 0


def fileWriteLines(filename, lines, source="", debug=False):
	try:
		with open(filename, "w", encoding="utf-8") as fd:
			fd.write("\n".join(lines) if isinstance(lines, list) else str(lines))
			if isinstance(lines, list) and lines:
				fd.write("\n")
		return 1
	except OSError:
		return 0


def fileReadXML(filename, default=None, *args, **kwargs):
	from xml.etree.ElementTree import fromstring, parse
	try:
		with open(filename, "r", encoding="utf-8") as fd:
			return parse(fd).getroot()
	except Exception as e:
		print("[Directories] XML %s: %s" % (filename, e))
	if default:
		try:
			return fromstring(default)
		except Exception as e:
			print("[Directories] XML implicit: %s" % e)
	return None


def sanitizeFilename(filename, maximum=255):
	"""Un nume de fisier fara semne interzise, cat incape pe disc."""
	import re
	nume = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|]', "_", str(filename)).strip(" .")
	if not nume:
		return "_"
	baza, extensie = os_path.splitext(nume)
	return baza[:maximum - len(extensie)] + extensie


def shellquote(text):
	return "'%s'" % str(text).replace("'", "'\\''")


copyFile = copyfile


def moveFiles(fileList):
	"""[(sursa, destinatie), ...]; la o eroare ce s-a mutat se pune la loc"""
	import shutil
	mutate = []
	try:
		for sursa, destinatie in fileList:
			shutil.move(sursa, destinatie)
			mutate.append((sursa, destinatie))
	except Exception:
		for sursa, destinatie in reversed(mutate):
			try:
				shutil.move(destinatie, sursa)
			except Exception as e:
				print("[Directories] mutarea inapoi: %s" % e)
		raise


def defaultRecordingLocation(candidate=None):
	if candidate and pathExists(candidate):
		return candidate
	return resolveFilename(SCOPE_HDD)


# ---------------------------------------------------------------------------------------------------------------------
# Numele cerute de pluginurile scrise pentru celelalte imagini Enigma2 (OEA4, 11.11.2026). Numai nume noi; ce exista mai sus
# ramane neschimbat (sanitizeFilename primeste si maxlen=, cum il cheama ele).
import os as _os
from os.path import basename, dirname, exists, getsize, isdir, isfile, islink, join, normpath, splitext  # noqa: F401  (numele importate de pluginuri din acest modul)
from os import sep, stat, remove, rename, link  # noqa: F401
try:
	from os import statvfs
except ImportError:  # Windows (probele de pe PC): nu exista
	statvfs = None

DEFAULT_MODULE_NAME = __name__.split(".")[-1]
try:
	from enigma import eGetEnigmaDebugLvl as _nivelJurnal
	forceDebug = _nivelJurnal() > 4
except Exception:
	forceDebug = False

SCOPE_HOME = SCOPE_USERETC
SCOPE_KEYMAPS = 23
SCOPE_HARDWARE = 24
defaultPaths.setdefault(SCOPE_KEYMAPS, (eEnv.resolve("${datadir}/keymaps/"), PATH_DONTCREATE))
defaultPaths.setdefault(SCOPE_HARDWARE, (eEnv.resolve("${datadir}/enigma2/hardware/"), PATH_DONTCREATE))
defaultPaths.setdefault(SCOPE_LIBDIR, (eEnv.resolve("${libdir}/"), PATH_DONTCREATE))
defaultPaths.setdefault(SCOPE_CURRENT_SKIN, defaultPaths[SCOPE_SKIN])
defaultPaths.setdefault(SCOPE_CURRENT_PLUGIN, defaultPaths[SCOPE_PLUGINS])
defaultPaths.setdefault(SCOPE_CURRENT_LCDSKIN, defaultPaths[SCOPE_LCDSKIN])
defaultPaths.setdefault(SCOPE_PLUGIN_ABSOLUTE, (defaultPaths[SCOPE_PLUGINS][0], PATH_DONTCREATE))
defaultPaths.setdefault(SCOPE_PLUGIN_RELATIVE, (defaultPaths[SCOPE_PLUGINS][0], PATH_DONTCREATE))

scopeConfig = defaultPaths[SCOPE_CONFIG][0]
scopeGUISkin = defaultPaths[SCOPE_SKIN][0]
scopeLCDSkin = defaultPaths[SCOPE_LCDSKIN][0]
scopeFonts = defaultPaths[SCOPE_FONTS][0]
scopePlugins = defaultPaths[SCOPE_PLUGINS][0]

pluginBlacklist = set()


def InitDefaultPaths():
	resolveFilename(SCOPE_CONFIG)


class ResolveLists:
	"""Listele de cautare tinute minte la standard; la noi cautarea nu le tine minte, deci raman goale."""
	skin = []
	lcdSkin = []
	fonts = []


def clearResolveLists():
	del ResolveLists.skin[:]
	del ResolveLists.lcdSkin[:]
	del ResolveLists.fonts[:]


def fileAccess(file, mode="r"):
	fel = F_OK
	if "r" in mode:
		fel |= R_OK
	if "w" in mode:
		fel |= W_OK
	try:
		return access(file, fel)
	except (OSError, TypeError):
		return False


def fileContains(file, content, mode="r"):
	return fileHas(file, content, mode)


def fileUpdateLine(filename, conditionValue, replacementValue, create=False, source=DEFAULT_MODULE_NAME, debug=False):
	"""Rescrie primul rand cu replacementValue cand incepe cu conditionValue (sau, cu create=True, cand fisierul e gol)."""
	rand = fileReadLine(filename, default="", source=source, debug=debug) or ""
	if conditionValue and rand.startswith(conditionValue):
		return fileWriteLine(filename, replacementValue, source=source, debug=debug)
	if create and not conditionValue:
		return fileWriteLine(filename, replacementValue, source=source, debug=debug)
	return 0


def copyTree(src, dst, symlinks=False):
	return copytree(src, dst, symlinks)


def renameDir(oldPath, newPath):
	try:
		_os.rename(oldPath, newPath)
		return 1
	except OSError as e:
		print("[Directories] renameDir %s -> %s: %s" % (oldPath, newPath, e))
		return 0


def comparePaths(leftPath, rightPath):
	"""Adevarat cand leftPath e rightPath sau un dosar parinte al lui."""
	if leftPath.endswith(sep):
		leftPath = leftPath[:-1]
	stanga = leftPath.split(sep)
	dreapta = rightPath.split(sep)
	if len(stanga) > len(dreapta):
		return False
	return all(a == b for a, b in zip(stanga, dreapta))


def bestRecordingLocation(candidates):
	"""Din [(nume, cale), ...]: calea cu cel mai mult loc (locul liber socotit de doua ori); "" cand nu e niciuna."""
	cale, cel_mai_mare = "", 0
	if statvfs is None:
		return cale
	for candidat in candidates:
		try:
			st = statvfs(candidat[1])
		except OSError as e:
			print("[Directories] bestRecordingLocation %s: %s" % (candidat[1], e))
			continue
		if st.f_bavail:
			marime = (st.f_blocks + st.f_bavail) * st.f_bsize
			if marime > cel_mai_mare:
				cel_mai_mare, cale = marime, candidat[1]
	return cale


def hasHardLinks(path):
	"""Daca discul de sub path stie legaturi tari (pentru inregistrarile mutate fara copiere)."""
	import tempfile
	try:
		fd, sursa = tempfile.mkstemp(prefix="HardLink_", suffix=".test", dir=path)
		_os.close(fd)
	except OSError:
		return False
	tinta = splitext(sursa)[0] + ".link"
	try:
		link(sursa, tinta)
		rezultat = True
	except OSError:
		rezultat = False
	for f in (sursa, tinta):
		try:
			remove(f)
		except OSError:
			pass
	return rezultat


def shellQuote(string):
	return shellquote(string)


def lsof():
	"""[(pid, program, fisier deschis), ...] pentru toate procesele care se pot citi."""
	rezultat = []
	try:
		procese = listdir("/proc")
	except OSError:
		return rezultat
	for pid in procese:
		if not pid.isdigit():
			continue
		try:
			program = readlink(join("/proc", pid, "exe"))
			dosar = join("/proc", pid, "fd")
			for fd in listdir(dosar):
				rezultat.append((pid, program, readlink(join(dosar, fd))))
		except OSError:
			pass
	return rezultat


def getExtension(file):
	return splitext(file)[1]


def mediaFilesInUse(session):
	"""Numele fisierelor video deschise acum (fara cel pe care il reda chiar receptorul, cand e deschis o singura data)."""
	try:
		from Components.MovieList import KNOWN_EXTENSIONS
	except Exception:
		KNOWN_EXTENSIONS = {".ts", ".mkv", ".mp4", ".avi", ".mpg", ".m2ts", ".mov", ".wmv", ".divx", ".flv", ".iso", ".mp3", ".flac", ".ogg", ".wav"}
	fisiere = [basename(x[2]) for x in lsof() if getExtension(x[2]) in KNOWN_EXTENSIONS]
	redat = None
	try:
		serviciu = session.nav.getCurrentlyPlayingServiceOrGroup()
		redat = serviciu and serviciu.getPath()
	except Exception:
		pass
	if redat:
		redat = None if "://" in redat else basename(redat)
	return set(f for f in fisiere if not (redat and f == redat and fisiere.count(redat) < 2))


def readPluginBlacklist():
	pluginBlacklist.clear()
	for fisier in (join(scopeConfig, "plugin_blacklist"), "/tmp/plugin_blacklist"):
		pluginBlacklist.update(x.strip() for x in (fileReadLines(fisier, default=[]) or []) if x.strip())
	return pluginBlacklist


def prettySize(size):
	"""Marimea cu unitatea (B, KB, MB, GB, TB), cum o arata pluginurile de fisiere."""
	try:
		size = float(size)
	except (TypeError, ValueError):
		return str(size)
	for unitate in ("B", "KB", "MB", "GB"):
		if abs(size) < 1024.0:
			return "%3.1f %s" % (size, unitate) if unitate != "B" else "%d %s" % (size, unitate)
		size /= 1024.0
	return "%3.1f TB" % size


_sanitizeFilenameVechi = sanitizeFilename


def sanitizeFilename(filename, maximum=255, maxlen=None):
	"""Un nume de fisier fara semne interzise, cat incape pe disc (maxlen= e numele argumentului la standard)."""
	return _sanitizeFilenameVechi(filename, maxlen if maxlen is not None else maximum)
