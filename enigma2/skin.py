# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Tools.Profile import profile
profile("LOAD:ElementTree")
import xml.etree.ElementTree
import re
from os import path
from traceback import print_exc

profile("LOAD:enigma_skin")
from enigma import eSize, ePoint, gFont, eWindow, eLabel, ePixmap, eWindowStyleManager, \
	addFont, gRGB, eWindowStyleSkinned
from Components.config import ConfigSubsection, ConfigText, ConfigSelection, config
from Components.Converter.Converter import Converter
from Components.Sources.Source import Source, ObsoleteSource
from Tools.Directories import resolveFilename, SCOPE_SKIN, SCOPE_SKIN_IMAGE, SCOPE_FONTS, SCOPE_CURRENT_SKIN, SCOPE_CONFIG, fileExists
from Tools.Import import my_import
from Tools.LoadPixmap import LoadPixmap

# Rule of this module: a mistake in a skin never stops the receiver. Every problem is written to
# the log as "[Skin] ..." and collected in `warnings` (shown once after start); the faulty
# widget, color or font is skipped and everything else is still drawn.

colorNames = dict()
fonts = dict()       # <alias name="Body" font="Regular" size="30" height="40"/> -> (font, size, height)
parameters = dict()  # <parameter name="X" value="1,2,3"/> -> (1, 2, 3); from <hdsparameters> also image paths
warnings = [ ]
MAX_WARNINGS = 50
_reportedAttributes = set()

def skinWarning(message):
	print("[Skin] %s" % message)
	if len(warnings) < MAX_WARNINGS and message not in warnings:
		warnings.append(message)

def skinNotice(message):
	# expected differences with skins written for other images: log only, no popup
	print("[Skin] %s" % message)

def dump(x, i=0):
	print(" " * i + str(x))
	try:
		for n in x.childNodes:
			dump(n, i + 1)
	except:
		None

class SkinError(Exception):
	def __init__(self, message):
		self.msg = message

	def __str__(self):
		return "{%s}: %s" % (config.skin.primary_skin.value, self.msg)

dom_skins = [ ]

def loadSkin(name, scope = SCOPE_SKIN):
	# read the skin
	filename = resolveFilename(scope, name)
	mpath = path.dirname(filename) + "/"
	dom_skins.append((mpath, xml.etree.ElementTree.parse(filename).getroot()))

# skins are loaded in order of priority: the skin with the highest priority is loaded last
# (usually the user-provided skin). loadSingleSkinData (colors, fonts, window style) is applied
# in ascending priority; dom_skins keeps the screens in descending priority, so the first screen
# found is used.
config.skin = ConfigSubsection()
# HDSatelit: skinul ales in Skin Selection (televizor) si in /skin (web), cu pornirea sigura din
# Components/HdsSkinuri.py: daca skinul ales lipseste, nu e un skin, are XML stricat sau interfata s-a oprit neasteptat la
# pornirea cu el, se incarca numai HDSatelit/skin.xml si omul afla de ce. HDSatelit/skin.xml se incarca mereu, dupa
# skinul ales, ca rezerva pentru ecranele pe care acela nu le are (ecranele Hds* ale imaginii).
config.skin.primary_skin = ConfigText(default = "HDSatelit/skin.xml")
# HDSatelit: aspect meniu -- lista clasica (o coloana) sau dale (grila cu carduri,
# ca pe console/smart TV-uri). Citit din Menu.py (MainMenu si sub-meniurile Settings); comutat
# din ecranul de Setari Skin (Screens/SkinSelector.py -> Plugins/SystemPlugins/SkinSelector).
# Valorile ("lista"/"dale") raman netraduse -- identificatori interni, nu text aratat; skin.py
# se incarca prea devreme la pornire ca sa foloseasca _() in siguranta (nimic altceva din acest
# fisier n-o foloseste). Eticheta tradusa se pune la afisare, in SkinSelector.py.
config.skin.layout_meniu = ConfigSelection(default="lista", choices=[("lista", "lista"), ("dale", "dale")])
# HDSatelit: tema interfetei de pe televizor, Clasic (skin.xml asa cum e) sau Pro (ecranele din
# HDSatelit/skin_pro.xml peste cele cu acelasi nume din skin.xml). Se alege din Meniu > Interfata si aspect > Tema
# interfetei (Screens/HdsTemaInterfata.py) si din web (/tema-tv); se aplica la repornirea interfetei. E separata de
# tema interfetei web (config.plugins.hdswebcontrol.tema_web). Valorile raman identificatori, ca layout_meniu.
config.skin.tema_tv = ConfigSelection(default="clasic", choices=[("clasic", "clasic"), ("pro", "pro")])
TEMA_PRO_FISIER = "HDSatelit/skin_pro.xml"

profile("LoadSkin")
# HDSatelit: in the safe mode started by enigma2.sh (HDS_MOD_SIGUR=1, Components/HdsModSigur.py) the user additions in
# skin_user.xml are not read (the file stays in place). The skin is HDSatelit/skin.xml as it is on disk, so with the
# colours and the info bar layout chosen in the skin settings (HdsSkinSetari, part of the image, writes them into it).
from os import environ as _mediu
from Components import HdsSkinuri as _HdsSkinuri
if _mediu.get("HDS_MOD_SIGUR") == "1":
	skinNotice("safe mode: skin_user.xml not loaded")
elif fileExists(resolveFilename(SCOPE_CONFIG, 'skin_user.xml')):
	try:
		loadSkin('skin_user.xml', SCOPE_CONFIG)
	except Exception as err:
		skinWarning("user skin not loaded: %s" % err)

def temaProDeIncarcat(mediu=None, exista=None, tema=None):
	"""True cand ecranele temei Pro se incarca peste skin.xml: tema aleasa e "pro", interfata nu e in modul sigur
	(acolo ramane mereu Clasic, ca o greseala in fisierul Pro sa nu blocheze pornirea) si fisierul exista (lipseste pe
	un skin mai vechi decat imaginea)."""
	mediu = _mediu if mediu is None else mediu
	exista = fileExists if exista is None else exista
	tema = config.skin.tema_tv.value if tema is None else tema
	if tema != "pro" or mediu.get("HDS_MOD_SIGUR") == "1":
		return False
	return bool(exista(resolveFilename(SCOPE_SKIN, TEMA_PRO_FISIER)))

# Skinul ales: altul decat HDSatelit numai daca Components/HdsSkinuri.skinDePornit il lasa (nu e modul sigur, fisierul e
# un skin, pornirea de dinainte cu el nu s-a oprit neasteptat). Altfel setarea se pune inapoi pe HDSatelit (salvata la
# pornirea sesiunii de extensia SkinSelector, care spune si motivul pe televizor).
skinPornit = _HdsSkinuri.SKIN_IMAGINE
try:
	skinAles, _skinRefuz = _HdsSkinuri.skinDePornit(config.skin.primary_skin.value, _mediu,
		resolveFilename(SCOPE_SKIN, ""))
except Exception as err:
	skinAles, _skinRefuz = None, None
	skinWarning("alegerea skinului nu s-a putut citi, ramane HDSatelit: %s" % err)
if _skinRefuz:
	config.skin.primary_skin.value = _HdsSkinuri.SKIN_IMAGINE
	config.skin.primary_skin.save()

# Tema Pro: fisierul are numai <screen> (ecrane si panouri); se incarca inaintea lui skin.xml, deci lookupScreen ia
# ecranul Pro cand exista si pe cel din skin.xml cand nu. Culorile, fonturile si restul raman ale lui skin.xml (cu
# paleta aleasa). Dupa skin_user.xml, ca adaugirile omului sa ramana deasupra. Tema e o varianta a skinului HDSatelit:
# cu alt skin ales nu se incarca.
try:
	if skinAles is None and temaProDeIncarcat():
		loadSkin(TEMA_PRO_FISIER)
		skinNotice("tema Pro: %s" % TEMA_PRO_FISIER)
except Exception as err:
	skinWarning("tema Pro nu s-a incarcat, ramane Clasic: %s" % err)

if skinAles is not None:
	try:
		loadSkin(skinAles)
		skinPornit = skinAles
		skinNotice("skinul ales: %s, cu HDSatelit/skin.xml ca rezerva" % skinAles)
	except Exception as err:
		# numai in jurnal: mesajul pentru om, tradus, il da extensia SkinSelector la pornirea sesiunii (HdsSkinuri)
		skinNotice("skinul ales %s nu s-a incarcat, ramane HDSatelit: %s" % (skinAles, err))
		_HdsSkinuri.incarcareCazuta(skinAles, err)
		config.skin.primary_skin.value = _HdsSkinuri.SKIN_IMAGINE
		config.skin.primary_skin.save()

try:
	loadSkin("HDSatelit/skin.xml")
except Exception as err:
	# Skinul HDSatelit nu s-a incarcat: NU cadem pe skinul Dreambox (este sters).
	# Enigma2 va functiona cu skinul default minim incorporat (fara fisier extern).
	skinWarning("skinul HDSatelit nu s-a incarcat: %s" % err)


profile("LoadSkinDefault")
try:
	loadSkin('skin_default.xml')
except Exception as err:
	skinWarning("fallback skin not loaded: %s" % err)
profile("LoadSkinDefaultDone")

def evalPos(pos, wsize, ssize, scale):
	if pos == "center":
		pos = (ssize - wsize) // 2
	else:
		pos = int(pos) * scale[0] // scale[1]
	return int(pos)

def parsePosition(s, scale, desktop = None, size = None):
	if not s:
		return ePoint(0, 0)
	x, y = s.split(',')

	wsize = 1, 1
	ssize = 1, 1
	if desktop is not None:
		ssize = desktop.size().width(), desktop.size().height()
	if size is not None:
		wsize = size.width(), size.height()

	x = evalPos(x.strip(), wsize[0], ssize[0], scale[0])
	y = evalPos(y.strip(), wsize[1], ssize[1], scale[1])

	return ePoint(x, y)

def parseSize(s, scale):
	if not s:
		return eSize(0, 0)
	x, y = s.split(',')
	return eSize(int(x) * scale[0][0] // scale[0][1], int(y) * scale[1][0] // scale[1][1])

# ------------------------------------------------------------------ ecranele scrise pentru alta rezolutie
# HDSatelit: un skin ales care nu e 1920x1080 (1280x720, 1024x576, 720x576, 3840x2160) arata ecranele lui; ecranele pe
# care nu le are (toate ecranele HD Satelit) vin din HDSatelit/skin.xml, scris pentru 1920x1080, sau din skinurile scrise
# in cod. Ca sa incapa si sa se citeasca, valorile lor se inmultesc cu marimea ecranului impartita la rezolutia de baza.
#
# BAZA unui ecran, in ordine: atributul resolution="latime,inaltime" al lui <screen> (ca in alte imagini; il au
# skinurile din cod scrise cu numere fixe pe 1920); un ecran (sau un panou) dintr-un fisier din dosarul HDSatelit
# (skin.xml, skin_pro.xml): rezolutia din <output> a lui HDSatelit/skin.xml; altfel ecranul nu se schimba (skinul ales,
# skin_default.xml, skin_user.xml, skinurile din cod fara atribut, ecranele afisajului din fata: getStyleID() != 0).
#
# CUM (readSkin, ScaraEcran.atribute): valorile se schimba cand se citesc, inainte sa ajunga la applySingleAttribute, la
# componentele care isi citesc singure atributele (ServiceList: serviceItemHeight...) si la convertorul
# TemplatedMultiContent; GUISkin.applySkin ramane cu scara 1:1. sx = latimea ecranului / latimea bazei, sy = la fel pe
# inaltime, sf = cea mai mica dintre ele (fonturile si grosimile, ca textul sa incapa si la 720x576, unde sx < sy):
#   position, size, textOffset, shadowOffset si pozitia din pointer/seek_pointer: x cu sx, y cu sy ("center" ramane);
#   font si orice atribut cu "font" in nume, de forma Nume;marime: marimea cu sf;
#   itemHeight si orice *Height: sy;  orice *Width (borderWidth...) si *Padding: sf;  colposition: sx;
#   o marime sau o grosime mai mare ca 0 nu ajunge 0; rotunjirea e la cel mai apropiat intreg;
#   pixmap, backgroundPixmap, selectionPixmap: imaginea se incarca la marimea ei inmultita ("#size=LxI" citit de
#     loadPixmap, prin ePicLoad), deci si iconitele mai mici decat cutia lor raman proportionale;
#   TemplatedMultiContent: pos=(x, y), size=(l, i), gFont("Nume", marime), "itemHeight": n, "itemWidth": n,
#     border_width=n si inaltimea sabloanelor cu nume ("nume": (n, [...])); font=, text=, png=, culorile si steagurile
#     raman.
# La incarcare (loadSkinData), cand rezolutia finala nu e cea a lui HDSatelit: parametrii (<parameters>,
# <hdsparameters>), aliasurile de font (marimea cu sf, inaltimea randului cu sy), stilurile subtitrarilor si titlul si
# rama ferestrei din fisierele HDSatelit se scaleaza la fel; imaginile listelor desenate in Python (getListPixmap) se
# incarca la marimea noua. Skinul ales se incarca dupa HDSatelit, deci valorile lui (scrise pentru ecranul lui) raman
# deasupra.
#
# CULORI SI FONTURI: cu alt skin ales, ecranele noastre (din dosarul HDSatelit, cele din cod cu resolution= si cele din
# cod ale imaginii, modulImagine: Screens.*, Components.*, Hds.*, extensiile Hds*, care nu se scaleaza daca nu au
# resolution=, fiindca isi socotesc singure marimea din ecran) iau culorile cu nume din paleta HDSatelit (un nume pe
# care il are HDSatelit/skin.xml se inlocuieste cu valoarea lui de acolo, deci un "white" sau "key_red" al skinului ales
# nu le schimba), iar fonturile Regular, Bold, Fixed si RegularHD devin HdsRegular, HdsBold, HdsCond (aceleasi fisiere
# ca la HDSatelit; skinul ales poate da alte fisiere numelor Regular...). Lista de setari "config" fara font sau
# secondfont primeste "Regular;20" si "Regular;16" (ce ar folosi C++-ul), trecute prin aceeasi scara. Fereastra lor ia
# stilul ferestrelor HDSatelit (STIL_HDS: fundalul, culorile listelor, titlul, rama; GUISkin.applySkin -> puneStilHds),
# iar codul care deseneaza din Python cu gFont("Regular", ...) poate cere fontul nostru cu fontHds(). Cu HDSatelit ales
# nu se schimba nimic.

DOSAR_HDS = path.normpath(path.dirname(resolveFilename(SCOPE_SKIN, "HDSatelit/skin.xml")))
BAZA_HDS_IMPLICITA = (1920, 1080)
FONTURI_HDS = {"Regular": "HdsRegular", "Bold": "HdsBold", "Fixed": "HdsCond", "RegularHD": "HdsRegular"}
culoriHds = dict()   # culorile din fisierele HDSatelit: nume -> "#aarrggbb" (loadSingleSkinData)
_bazaHds = [ ]
_scaraHds = [ None ]   # ScaraEcran a fisierelor HDSatelit fata de ecranul final (loadSkinData), None la 1:1
_ecraneScalate = set()

def esteDinHds(skin_path):
	"""True cand dosarul (ca in dom_skins, cu / la sfarsit) e dosarul skinului HDSatelit"""
	try:
		return bool(skin_path) and path.normpath(skin_path) == DOSAR_HDS
	except Exception:
		return False

def _imagineDinHds(cale):
	try:
		return bool(cale) and path.normpath(cale).startswith(DOSAR_HDS + path.sep)
	except Exception:
		return False

def rezolutieOutput(radacina):
	"""(xres, yres) din <output id="0"><resolution> al unui skin, sau None"""
	try:
		for c in radacina.findall("output"):
			if int(c.attrib.get("id") or 0) != 0:
				continue
			for res in c.findall("resolution"):
				return int(res.attrib.get("xres") or 720), int(res.attrib.get("yres") or 576)
	except (ValueError, AttributeError):
		pass
	return None

def rezolutieAtribut(valoare):
	"""resolution="1920,1080" -> (1920, 1080); None cand nu sunt doua numere mai mari ca 0"""
	try:
		w, h = [int(v) for v in valoare.split(",")]
	except (ValueError, AttributeError):
		return None
	return (w, h) if w > 0 and h > 0 else None

def bazaHds():
	"""rezolutia skinului HDSatelit (<output> al fisierului din dosarul HDSatelit care il are), altfel 1920x1080"""
	if not _bazaHds:
		for (p, radacina) in dom_skins:
			if esteDinHds(p):
				r = rezolutieOutput(radacina)
				if r:
					_bazaHds.append(r)
					break
		else:
			return BAZA_HDS_IMPLICITA
	return _bazaHds[0]

def _ori(v, f):
	"""v inmultit cu fractia f = (numarator, numitor), rotunjit la cel mai apropiat intreg"""
	n, d = f
	q = (2 * abs(v) * n + d) // (2 * d)
	return q if v >= 0 else -q

def _marime(v, f):
	"""o marime sau o grosime: una mai mare ca 0 ramane cel putin 1"""
	r = _ori(v, f)
	return max(1, r) if v > 0 else r

_RX_POZ = re.compile(r'\b(pos|size)(\s*=\s*\(\s*)(-?\d+)(\s*,\s*)(-?\d+)(\s*\))')
_RX_GFONT = re.compile(r'\bgFont(\(\s*)("[^"]*"|\'[^\']*\')(\s*,\s*)(\d+)(\s*\))')
_RX_ITEM = re.compile(r'(["\']item(Height|Width)["\']\s*:\s*)(\d+)')
_RX_SABLON = re.compile(r'(["\'][^"\']*["\']\s*:\s*\(\s*)(\d+)(\s*,\s*\[)')
_RX_GROSIME = re.compile(r'\b(border_width|borderWidth)(\s*=\s*)(\d+)')

class ScaraEcran(object):
	"""cum se schimba valorile unui ecran scris pentru `baza` cand se arata pe `ecran` (amandoua (latime, inaltime));
	`culori` (nume -> valoare) si `fonturi` (nume -> nume) se pun in locul celor din skin, cand nu sunt None"""
	def __init__(self, baza, ecran, culori = None, fonturi = None):
		self.baza = (int(baza[0]), int(baza[1]))
		self.ecran = (int(ecran[0]), int(ecran[1]))
		self.sx = (self.ecran[0], self.baza[0])
		self.sy = (self.ecran[1], self.baza[1])
		# cea mai mica dintre sx si sy: sx <= sy cand ecran_x * baza_y <= ecran_y * baza_x
		self.sf = self.sx if self.ecran[0] * self.baza[1] <= self.ecran[1] * self.baza[0] else self.sy
		self.scaleaza = self.baza != self.ecran
		self.culori = culori or None
		self.fonturi = fonturi or None

	def __repr__(self):
		return "ScaraEcran(%dx%d -> %dx%d%s%s)" % (self.baza + self.ecran + (self.culori and ", culori" or "",
			self.fonturi and ", fonturi" or ""))

	def pereche(self, s, marime = False):
		"""'x,y' -> x cu sx, y cu sy; "center" si orice nu e numar raman"""
		parti = s.split(',')
		if len(parti) != 2:
			return s
		rez = [ ]
		for p, f in zip(parti, (self.sx, self.sy)):
			try:
				v = int(p.strip())
			except ValueError:
				rez.append(p)
				continue
			rez.append(str(_marime(v, f) if marime else _ori(v, f)))
		return ','.join(rez)

	def font(self, s):
		"""'Nume;marime' -> numele de pus (fonturi) si marimea cu sf; un alias sau un nume fara marime ramane"""
		nume, sep, marime = s.partition(';')
		if not sep:
			return s
		if self.fonturi:
			nume = self.fonturi.get(nume.strip(), nume)
		try:
			m = int(marime)
		except ValueError:
			return nume + sep + marime
		if self.scaleaza:
			m = _marime(m, self.sf)
		return "%s;%d" % (nume, m)

	def imagine(self, valoare):
		"""calea unei imagini (cu optiunile de dupa #) -> aceeasi, cu size=LxI: marimea fisierului inmultita"""
		baza, sep, optiuni = valoare.partition('#')
		m = marimeImagine(baza)
		if m is None:
			return valoare
		opt = [ o for o in optiuni.split(',') if o and not o.startswith("size=") ]
		opt.append("size=%dx%d" % (_marime(m[0], self.sx), _marime(m[1], self.sy)))
		return baza + '#' + ','.join(opt)

	def valoare(self, atribut, v):
		a = atribut.lower()
		if self.scaleaza:
			if atribut in ("position", "textOffset", "shadowOffset"):
				return self.pereche(v)
			if atribut == "size":
				return self.pereche(v, True)
			if atribut in ("pointer", "seek_pointer"):
				nume, sep, poz = v.rpartition(':')
				return nume + sep + self.pereche(poz) if sep else v
			if atribut in ("pixmap", "backgroundPixmap", "selectionPixmap"):
				return self.imagine(v)
			if a.endswith("height"):
				return str(_marime(int(v), self.sy))
			if a.endswith("width") or a.endswith("padding"):
				return str(_marime(int(v), self.sf))
			if atribut == "colposition":
				return str(_ori(int(v), self.sx))
		if "font" in a:
			return self.font(v)
		if self.culori and "color" in a and v in self.culori:
			return self.culori[v]
		return v

	def atribute(self, lista):
		"""lista (atribut, valoare) a unui element -> lista noua, cu valorile schimbate; o valoare care nu se poate
		schimba ramane cum e (un rand in jurnal)"""
		rez = [ ]
		for (atribut, v) in lista:
			try:
				v = self.valoare(atribut, v)
			except Exception as e:
				skinNotice("%s=\"%s\" nu s-a scalat (%s)" % (atribut, v, e))
			rez.append((atribut, v))
		return rez

	def sablon(self, text):
		"""textul unui TemplatedMultiContent, cu pozitiile, marimile, fonturile si inaltimile randurilor schimbate"""
		sx, sy, sf = self.sx, self.sy, self.sf
		if self.scaleaza:
			def poz(m):
				marime = m.group(1) == "size"
				x, y = int(m.group(3)), int(m.group(5))
				x, y = (_marime(x, sx), _marime(y, sy)) if marime else (_ori(x, sx), _ori(y, sy))
				return "%s%s%d%s%d%s" % (m.group(1), m.group(2), x, m.group(4), y, m.group(6))
			text = _RX_POZ.sub(poz, text)
			text = _RX_ITEM.sub(lambda m: "%s%d" % (m.group(1), _marime(int(m.group(3)), sy if m.group(2) == "Height" else sx)), text)
			text = _RX_SABLON.sub(lambda m: "%s%d%s" % (m.group(1), _marime(int(m.group(2)), sy), m.group(3)), text)
			text = _RX_GROSIME.sub(lambda m: "%s%s%d" % (m.group(1), m.group(2), _marime(int(m.group(3)), sf)), text)
		def font(m):
			nume = m.group(2)
			if self.fonturi and nume[1:-1] in self.fonturi:
				nume = nume[0] + self.fonturi[nume[1:-1]] + nume[-1]
			marime = int(m.group(4))
			if self.scaleaza:
				marime = _marime(marime, sf)
			return "gFont%s%s%s%d%s" % (m.group(1), nume, m.group(3), marime, m.group(5))
		if self.scaleaza or self.fonturi:
			text = _RX_GFONT.sub(font, text)
		return text

def altSkinActiv():
	"""True cand interfata a pornit cu alt skin decat HDSatelit"""
	try:
		return skinPornit != _HdsSkinuri.SKIN_IMAGINE
	except NameError:
		return False

# STIL_HDS[0]: stilul ferestrelor HDSatelit (eWindowStyleSkinned facut de loadSingleSkinData din windowstyle id 0 al
# fisierului HDSatelit), tinut aici cand e ales alt skin, al carui stil il inlocuieste pe id 0 in eWindowStyleManager.
# Obiectul insusi (nu getStyle al managerului: SWIG nu da inapoi un eWindowStyle * folosibil, iar un id nepus e ASSERT).
STIL_HDS = [ None ]

def puneStilHds(fereastra):
	"""GUISkin.applySkin, pentru ecranele noastre sub alt skin ales (screen.stilHds, pus de readSkin): fereastra (si
	elementele facute dupa ea, care iau stilul ei) primeste stilul ferestrelor HDSatelit: fundalul, culorile listelor,
	titlul si rama raman ale noastre. Fara stil tinut (HDSatelit ales, sau skinul HDSatelit fara windowstyle): nimic."""
	stil = STIL_HDS[0]
	if stil is None:
		return
	try:
		fereastra.setStyle(stil)
		# elementele ecranului au ca parinte copilul ferestrei (eWindow.child(), facut odata cu ea, cu stilul de
		# atunci) si iau stilul lui; tot el deseneaza fundalul
		fereastra.child().setStyle(stil)
	except Exception as e:
		skinNotice("stilul ferestrelor HDSatelit nu s-a pus: %s" % e)

def fontHds(nume):
	"""numele de font de folosit in codul ecranelor noastre (gFont("Regular", ...) desenat din Python): cu alt skin ales,
	fontul HDSatelit cu acelasi rol (Regular -> HdsRegular...), altfel numele asa cum e"""
	if altSkinActiv():
		return FONTURI_HDS.get(nume, nume)
	return nume

def modulImagine(modul):
	"""True pentru modulele ecranelor imaginii (Screens.*, Components.*, Hds.*, extensiile Hds*): skinul lor scris in
	cod e al nostru, deci isi pastreaza culorile si fonturile sub alt skin; extensiile instalate din alta parte nu"""
	modul = modul or ""
	return modul.startswith(("Screens.", "Components.", "Hds.")) or (modul.startswith("Plugins.") and ".Hds" in modul)

def scaraEcran(element, skin_path, desktop, modul = None):
	"""ScaraEcran pentru un <screen> citit din skin_path (None = scris in cod, in modulul `modul`) si aratat pe desktop,
	sau None cand nu se schimba nimic (vezi mai sus: baza ecranului, culorile si fonturile)"""
	try:
		if desktop.getStyleID() != 0:
			return None
		s = desktop.size()
		ecran = (s.width(), s.height())
	except Exception:
		return None
	if ecran[0] <= 0 or ecran[1] <= 0:
		return None
	baza = rezolutieAtribut(element.attrib.get("resolution")) if element is not None else None
	alNostru = esteDinHds(skin_path) or (not skin_path and (baza is not None or modulImagine(modul)))
	if baza is None and not esteDinHds(skin_path):
		# un skin din cod fara resolution= e deja pe marimea ecranului: numai culorile si fonturile, sub alt skin
		baza = ecran if alNostru else None
	if baza is None and esteDinHds(skin_path):
		baza = bazaHds()
	if baza is None:
		return None
	culori = fonturi = None
	if alNostru and altSkinActiv():
		culori = culoriHds or None
		fonturi = FONTURI_HDS
	if baza == ecran and culori is None and fonturi is None:
		return None
	return ScaraEcran(baza, ecran, culori, fonturi)

def factorHds():
	"""(sx, sy, sf) ca numere reale: marimea ecranului fata de skinul HDSatelit, (1.0, 1.0, 1.0) pe 1920x1080. Pentru
	codul care deseneaza cu numere scrise pe 1920 (randuri de liste, fonturi puse din Python)."""
	try:
		from enigma import getDesktop
		s = getDesktop(0).size()
		w, h = s.width(), s.height()
	except Exception:
		return 1.0, 1.0, 1.0
	b = bazaHds()
	if w <= 0 or h <= 0:
		return 1.0, 1.0, 1.0
	sx, sy = float(w) / b[0], float(h) / b[1]
	return sx, sy, min(sx, sy)

_AXE_PARAMETRI = {
	"EPGListSingleColumns": "xxxx",   # marginea, coloana zilei, coloana orei, spatiul dintre ele (Components/EpgList.py)
	"EPGListMultiColumns": "xxxx",
	"EPGListProgress": "y",           # inaltimea barei
	"MessageBoxDupaText": "y",        # marginea de jos (Screens/MessageBox.py)
}

def scaleazaParametru(nume, valoare, scara):
	"""un parametru numeric al unui fisier HDSatelit, la ecranul final: 4 numere = x, y, latime, inaltime; 3 numere =
	x, y, inaltime (PluginBrowserName...); 2 = x, y; unul: *Width cu sx, *Height cu sy, altfel sf. Caile (imaginile)
	raman."""
	if scara is None or not scara.scaleaza or isinstance(valoare, str):
		return valoare
	f = {"x": scara.sx, "y": scara.sy}
	if isinstance(valoare, int):
		axa = _AXE_PARAMETRI.get(nume)
		if axa is None:
			n = nume.lower()
			axa = "x" if n.endswith("width") else "y" if n.endswith("height") else "f"
		return _marime(valoare, f.get(axa, scara.sf))
	axe = _AXE_PARAMETRI.get(nume) or {2: "xy", 3: "xyy", 4: "xyxy"}.get(len(valoare), "f" * len(valoare))
	return tuple(_marime(v, f.get(a, scara.sf)) for v, a in zip(valoare, axe))

_marimiImagini = { }

def marimeImagine(cale):
	"""(latime, inaltime) din antetul unui .png sau .jpg, None cand nu se poate citi"""
	if cale in _marimiImagini:
		return _marimiImagini[cale]
	m = None
	try:
		with open(cale, "rb") as f:
			cap = f.read(24)
			if cap[:8] == b"\x89PNG\r\n\x1a\n" and cap[12:16] == b"IHDR":
				m = (int.from_bytes(cap[16:20], "big"), int.from_bytes(cap[20:24], "big"))
			elif cap[:2] == b"\xff\xd8":
				f.seek(2)
				while True:
					b = f.read(1)
					while b and b != b"\xff":
						b = f.read(1)
					while b == b"\xff":
						b = f.read(1)
					if not b:
						break
					marker = b[0]
					if marker == 0x01 or 0xd0 <= marker <= 0xd8:
						continue
					lung = int.from_bytes(f.read(2), "big")
					if 0xc0 <= marker <= 0xcf and marker not in (0xc4, 0xc8, 0xcc):
						d = f.read(5)
						m = (int.from_bytes(d[3:5], "big"), int.from_bytes(d[1:3], "big"))
						break
					if lung < 2:
						break
					f.seek(lung - 2, 1)
	except (IOError, OSError, ValueError, IndexError):
		m = None
	if m is not None and (m[0] <= 0 or m[1] <= 0):
		m = None
	_marimiImagini[cale] = m
	return m

_pixmapuriScalate = { }
_incarcator = [ ]

def incarcaPixmapScalat(cale, w, h, desktop = None):
	"""imaginea `cale` la marimea w x h (ePicLoad, pe loc), tinuta minte; None la orice eroare (atunci se ia imaginea
	asa cum e). Aspectul dat lui setPara, (h * latime) / (inaltime * w), face ca resizePic sa umple exact w x h si cand
	latimea si inaltimea se schimba diferit (720x576); ce ramane din rotunjiri e transparent."""
	cheie = (cale, w, h)
	if cheie in _pixmapuriScalate:
		return _pixmapuriScalate[cheie]
	ptr = None
	m = marimeImagine(cale)
	if m is not None and w > 0 and h > 0:
		try:
			if m == (w, h):
				ptr = LoadPixmap(cale, desktop, True)
			else:
				from enigma import ePicLoad
				if not _incarcator:
					_incarcator.append(ePicLoad())
				incarcator = _incarcator[0]
				incarcator.setPara((w, h, h * m[0], m[1] * w, False, 1, "#00000000"))
				if incarcator.startDecode(cale, w, h, False) == 0:
					ptr = incarcator.getData()
				if ptr is not None and desktop is not None:
					desktop.makeCompatiblePixmap(ptr)
		except Exception as e:
			skinNotice("imaginea %s nu s-a incarcat la %dx%d: %s" % (cale, w, h, e))
			ptr = None
	_pixmapuriScalate[cheie] = ptr
	return ptr

# HDSatelit: procent global de marire/micsorare a fonturilor OSD (80-130), setat din
# Screens/FontSetup.py si salvat in config.osd.fontscale. 100 = fara nicio schimbare.
# Cod propriu, foloseste doar mecanismul de scalare deja existent al lui parseFont().
_hds_fontscale_procent = 100


def setFontScalePercent(procent):
	global _hds_fontscale_procent
	_hds_fontscale_procent = max(80, min(130, int(procent)))


def getFontScalePercent():
	return _hds_fontscale_procent


def _hds_scaleaza(marime):
	if _hds_fontscale_procent == 100:
		return marime
	return max(1, (marime * _hds_fontscale_procent) // 100)


def parseFont(s, scale):
	if not s:
		return gFont("Regular", _hds_scaleaza(20))
	if ';' in s:
		name, size = s.split(';')
		return gFont(name, _hds_scaleaza(int(size) * scale[0][0] // scale[0][1]))
	# a font alias from <fonts>, or a bare font name
	if s in fonts:
		name, size, height = fonts[s]
		return gFont(name, _hds_scaleaza(size * scale[0][0] // scale[0][1]))
	return gFont(s, _hds_scaleaza(20 * scale[0][0] // scale[0][1]))

def parseColor(s):
	if not s:
		raise SkinError("missing color value")
	if s[0] != '#':
		try:
			return colorNames[s]
		except KeyError:
			raise SkinError("color '%s' must be #aarrggbb or valid named color" % (s))
	return gRGB(int(s[1:], 0x10))

def parseParameter(s):
	"""'1, 2, -3' -> (1, 2, -3); '7' -> 7. ValueError when a part is not a whole number."""
	values = tuple(int(p.strip()) for p in s.split(','))
	return values[0] if len(values) == 1 else values

def parseImageParameter(s, path_prefix):
	"""an image for the lists drawn in Python (only in <hdsparameters>): a .png path relative to the folder of the
	skin, '%s' stands for the key (file type, remote key...). ValueError for anything else: no absolute paths,
	no '..', so a skin cannot point the receiver at files outside its folder."""
	s = s.strip()
	parts = s.split('/')
	if not s.lower().endswith('.png') or s[0] == '/' or '\\' in s or '\0' in s or '..' in parts or '' in parts:
		raise ValueError("not a .png file inside the skin folder")
	return path.join(path_prefix or "", s)

def readParameter(parameter, path_prefix, images = False, scara = None):
	"""<parameter name="..." value="..."/> into `parameters`; a bad value is skipped with one log line. `scara`
	(ScaraEcran, fisierele HDSatelit pe alt ecran): numerele se scaleaza (scaleazaParametru)."""
	name = parameter.attrib.get("name")
	value = parameter.attrib.get("value")
	if not name or value is None:
		skinWarning("%s: parameter without name or value skipped" % path_prefix)
		return
	try:
		parameters[name] = scaleazaParametru(name, parseParameter(value), scara)
		return
	except ValueError:
		pass
	if images:
		try:
			parameters[name] = parseImageParameter(value, path_prefix)
			return
		except ValueError:
			pass
	skinWarning("parameter %s=\"%s\" skipped (expected whole numbers separated by commas%s)" % (name, value, images and ", or a .png file in the skin folder" or ""))

# --- the lists drawn in Python (FileList, ChoiceList, PluginList...) read their look from the skin ---------
# Every value has a default equal to what the 2011 code drew, so a skin without these entries looks as before.

_reportedParameters = set()

def getParameterFromSkin(name, default):
	"""(value, True) when the skin sets `name` with the shape of `default` (one number or a tuple of as many
	numbers), else (default, False). Another shape (a skin written for another image) is noted once in the log."""
	value = parameters.get(name)
	if value is None:
		return default, False
	if isinstance(default, tuple):
		good = isinstance(value, tuple) and len(value) == len(default)
	else:
		good = isinstance(value, int)
	if good:
		return value, True
	if name not in _reportedParameters:
		_reportedParameters.add(name)
		skinNotice("parameter %s=%r not used here (this image expects %s), default kept" % (name, value, isinstance(default, tuple) and "%d numbers" % len(default) or "one number"))
	return default, False

def getParameter(name, default):
	return getParameterFromSkin(name, default)[0]

def getListFont(name, default):
	"""(gFont, row height) for a list drawn in Python: <alias name=`name`> of the skin, else `default`
	= (font, size[, height]). A missing or zero height keeps the default one (None when there is none).
	The OSD font scale (FontSetup) applies to the size and to the row height."""
	family, size = default[0], default[1]
	height = len(default) > 2 and default[2] or None
	alias = fonts.get(name)
	if alias:
		try:
			a_family, a_size, a_height = alias
			if a_family and int(a_size) > 0:
				family, size = a_family, int(a_size)
			if a_height and int(a_height) > 0:
				height = int(a_height)
		except (TypeError, ValueError):
			if name not in _reportedParameters:
				_reportedParameters.add(name)
				skinNotice("font alias %s=%r not used here, default kept" % (name, alias))
	return gFont(family, _hds_scaleaza(size)), height and _hds_scaleaza(height)

def hasListFont(name):
	return name in fonts

def getListImage(name, key = None):
	"""the file of a list image set in <hdsparameters> (value="liste/fisier_%s.png"), for `key`; None when the
	skin does not set it or the file is missing. Keys are plain words (letters, digits, '_')."""
	value = parameters.get(name)
	if not isinstance(value, str):
		return None
	if key is not None:
		key = str(key)
		if not key or not all(c.isalnum() or c == '_' for c in key) or not key.isascii():
			return None
		value = value.replace('%s', key)
	elif '%s' in value:
		return None
	return fileExists(value) and value or None

def getListPixmap(name, key = None, default = None):
	"""(pixmap, True) for the skin image of `name`/`key`; else (pixmap of the file `default`, False); else (None, False).
	The skin images are drawn smooth (alpha blend), the old ones as before (alpha test)."""
	for filename, from_skin in ((getListImage(name, key), True), (default, False)):
		if filename and fileExists(filename):
			# o imagine a skinului HDSatelit pe alt ecran: la marimea ei inmultita (ca randurile, scalate la incarcare)
			scara = _scaraHds[0]
			if from_skin and scara is not None and _imagineDinHds(filename):
				m = marimeImagine(filename)
				ptr = m and incarcaPixmapScalat(filename, _marime(m[0], scara.sx), _marime(m[1], scara.sy))
				if ptr is not None:
					return ptr, from_skin
			try:
				ptr = LoadPixmap(filename, cached = True)
			except Exception as e:
				ptr = None
				print("[Skin] list image %s: %s" % (filename, e))
			if ptr is not None:
				return ptr, from_skin
	return None, False

def listRect(rect, width):
	"""(x, y, w, h) of an element in a list row `width` pixels wide: x below 0 counts from the right edge of
	the row, w of 0 or below reaches the right edge minus |w|"""
	x, y, w, h = rect
	if x < 0:
		x += width
	if w <= 0:
		w += width - x
	return x, y, max(0, w), h

def centerPixmap(rect, pixmap):
	"""(x, y, w, h) of `pixmap` centered in `rect`: this image draws a pixmap at its own size from the
	top left corner of its box (no scaling), so a smaller icon is moved to the middle of the box"""
	x, y, w, h = rect
	try:
		size = pixmap.size()
		pw, ph = size.width(), size.height()
	except Exception:
		return rect
	if pw <= 0 or ph <= 0:
		return rect
	return x + max(0, (w - pw) // 2), y + max(0, (h - ph) // 2), min(w, pw), min(h, ph)

def resolveSkinImage(filename, path_prefix):
	"""a skin image: next to the skin first (how skins for other images are written),
	then in the current skin, then the classic image path"""
	if not filename or filename[0] == '/':
		return filename
	base, sep, options = filename.partition('#')
	for candidate in (path.join(path_prefix, base) if path_prefix else None, resolveFilename(SCOPE_CURRENT_SKIN, base)):
		if candidate and fileExists(candidate):
			return candidate + sep + options
	return resolveFilename(SCOPE_SKIN_IMAGE, filename, path_prefix=path_prefix)

def collectAttributes(skinAttributes, node, skin_path_prefix=None, ignore=()):
	# walk all attributes
	for attrib, value in list(node.items()):
		if attrib in ignore:
			continue
		if attrib in ("pixmap", "backgroundPixmap", "selectionPixmap"):
			value = resolveSkinImage(value, skin_path_prefix)
		elif attrib in ("pointer", "seek_pointer"):
			# "file.png:x,y": only the file part is a path
			name, sep, pos = value.partition(':')
			value = resolveSkinImage(name, skin_path_prefix) + sep + pos
		skinAttributes.append((attrib, value))

def loadPixmap(path, desktop):
	cached = False
	marime = None
	option = path.find("#")
	if option != -1:
		options = path[option+1:].split(',')
		path = path[:option]
		cached = "cached" in options
		# size=LxI: imaginea la alta marime (ecranele scalate, ScaraEcran.imagine); la o eroare, asa cum e
		for o in options:
			if o.startswith("size="):
				try:
					w, h = [int(v) for v in o[5:].split('x')]
					marime = (w, h)
				except ValueError:
					pass
	if marime is not None:
		ptr = incarcaPixmapScalat(path, marime[0], marime[1], desktop)
		if ptr is not None:
			return ptr
	ptr = LoadPixmap(path, desktop, cached)
	if ptr is None:
		raise SkinError("pixmap file %s not found!" % (path))
	return ptr

ALPHATEST = { "on": 1, "off": 0, "blend": 2 }
ORIENTATION = {
	"orVertical": ("orVertical", False),
	"orTopToBottom": ("orVertical", False),
	"orBottomToTop": ("orVertical", True),
	"orHorizontal": ("orHorizontal", False),
	"orLeftToRight": ("orHorizontal", False),
	"orRightToLeft": ("orHorizontal", True),
}

def applySingleAttribute(guiObject, desktop, attrib, value, scale = ((1,1),(1,1))):
	try:
		if attrib == 'position':
			guiObject.move(parsePosition(value, scale, desktop, guiObject.csize()))
		elif attrib == 'size':
			guiObject.resize(parseSize(value, scale))
		elif attrib == 'title':
			guiObject.setTitle(_(value))
		elif attrib == 'text':
			guiObject.setText(_(value))
		elif attrib == 'font':
			guiObject.setFont(parseFont(value, scale))
		elif attrib == 'zPosition':
			guiObject.setZPosition(int(value))
		elif attrib == 'itemHeight':
			guiObject.setItemHeight(int(value))
		elif attrib in ("pixmap", "backgroundPixmap", "selectionPixmap"):
			ptr = loadPixmap(value, desktop) # this should already have been filename-resolved.
			if attrib == "pixmap":
				guiObject.setPixmap(ptr)
			elif attrib == "backgroundPixmap":
				guiObject.setBackgroundPicture(ptr)
			else:
				guiObject.setSelectionPicture(ptr)
		elif attrib == "alphatest": # used by ePixmap
			guiObject.setAlphatest(ALPHATEST[value])
		elif attrib == "scale":
			guiObject.setScale(1)
		elif attrib == "orientation": # used by eSlider
			name, swapped = ORIENTATION[value]
			guiObject.setOrientation(getattr(guiObject, name), swapped)
		elif attrib == "valign":
			guiObject.setVAlign({ "top": guiObject.alignTop, "center": guiObject.alignCenter, "bottom": guiObject.alignBottom }[value])
		elif attrib == "halign":
			guiObject.setHAlign({ "left": guiObject.alignLeft, "center": guiObject.alignCenter, "right": guiObject.alignRight, "block": guiObject.alignBlock }[value])
		elif attrib == "flags":
			for f in value.split(','):
				f = f.strip()
				if hasattr(eWindow, f):
					guiObject.setFlag(getattr(eWindow, f))
				else:
					skinWarning("unknown window flag %s" % f)
		elif attrib == "backgroundColor":
			guiObject.setBackgroundColor(parseColor(value))
		elif attrib == "backgroundColorSelected":
			guiObject.setBackgroundColorSelected(parseColor(value))
		elif attrib == "foregroundColor":
			guiObject.setForegroundColor(parseColor(value))
		elif attrib == "foregroundColorSelected":
			guiObject.setForegroundColorSelected(parseColor(value))
		elif attrib == "shadowColor":
			guiObject.setShadowColor(parseColor(value))
		elif attrib == "selectionDisabled":
			guiObject.setSelectionEnable(0)
		elif attrib == "transparent":
			guiObject.setTransparent(int(value))
		elif attrib == "borderColor":
			guiObject.setBorderColor(parseColor(value))
		elif attrib == "borderWidth":
			guiObject.setBorderWidth(int(value))
		elif attrib == "scrollbarMode":
			guiObject.setScrollbarMode({ "showOnDemand": guiObject.showOnDemand, "showAlways": guiObject.showAlways, "showNever": guiObject.showNever }[value])
		elif attrib == "enableWrapAround":
			guiObject.setWrapAround(value not in ("0", "false"))
		elif attrib == "pointer" or attrib == "seek_pointer":
			(name, pos) = value.split(':')
			pos = parsePosition(pos, scale)
			ptr = loadPixmap(name, desktop)
			guiObject.setPointer({"pointer": 0, "seek_pointer": 1}[attrib], ptr, pos)
		elif attrib == 'shadowOffset':
			guiObject.setShadowOffset(parsePosition(value, scale))
		elif attrib == 'noWrap':
			guiObject.setNoWrap(int(value) if value.isdigit() else 1)
		elif attrib == 'textOffset':
			guiObject.setTextOffset(parsePosition(value, scale))
		elif attrib == 'secondfont':
			guiObject.setSecondFont(parseFont(value, scale))
		elif attrib == 'id':
			pass
		elif attrib not in _reportedAttributes:
			# attributes of newer skins that this image does not draw yet: reported once, never fatal
			_reportedAttributes.add(attrib)
			print("[Skin] attribute %s is not supported yet (first seen on %s)" % (attrib, guiObject.__class__.__name__))
	except Exception as e:
		skinWarning("%s: attribute %s=\"%s\" not applied (%s)" % (guiObject.__class__.__name__, attrib, value, e))

def applyAllAttributes(guiObject, desktop, attributes, scale):
	for (attrib, value) in attributes:
		applySingleAttribute(guiObject, desktop, attrib, value, scale)

def resolveFontFile(filename, path_prefix):
	for candidate in (path.join(path_prefix or "", filename), resolveFilename(SCOPE_FONTS, filename, path_prefix=path_prefix), resolveFilename(SCOPE_CURRENT_SKIN, filename)):
		if candidate and fileExists(candidate):
			return candidate
	return None

def loadSingleSkinData(desktop, skin, path_prefix, scara = None):
	"""loads skin data like colors, fonts, window style; each entry on its own, a bad one is skipped. `scara`
	(ScaraEcran): un fisier HDSatelit cand ecranul final are alta rezolutie (loadSkinData)."""
	if skin.tag != "skin":
		skinWarning("%s: root element must be 'skin'" % path_prefix)
		return
	if scara is not None and not scara.scaleaza:
		scara = None
	# fonturile (parseFont ia primul factor) cu sf, pozitiile si marimile cu sx si sy
	scara_font = scara and (scara.sf, scara.sf) or ((1,1),(1,1))
	scara_xy = scara and (scara.sx, scara.sy) or ((1,1),(1,1))
	dinHds = esteDinHds(path_prefix)

	for c in skin.findall("output"):
		try:
			id = int(c.attrib.get('id') or 0)
			if id == 0: # framebuffer
				for res in c.findall("resolution"):
					get_attr = res.attrib.get
					xres = int(get_attr("xres") or 720)
					yres = int(get_attr("yres") or 576)
					from enigma import gMainDC
					gMainDC.getInstance().setResolution(xres, yres)
					desktop.resize(eSize(xres, yres))
		except Exception as e:
			skinWarning("%s: output: %s" % (path_prefix, e))

	for c in skin.findall("colors"):
		for color in c.findall("color"):
			name = color.attrib.get("name")
			value = color.attrib.get("value")
			try:
				colorNames[name] = parseColor(value)
				# paleta HDSatelit, pentru ecranele noastre cand e ales alt skin (ScaraEcran.culori)
				if dinHds and name and value:
					if value[0] == '#':
						culoriHds[name] = value
					elif value in culoriHds:
						culoriHds[name] = culoriHds[value]
			except Exception as e:
				skinWarning("color %s=%s: %s" % (name, value, e))

	for c in skin.findall("fonts"):
		for font in c.findall("font"):
			get_attr = font.attrib.get
			filename = get_attr("filename", "<NONAME>")
			name = get_attr("name", "Regular")
			try:
				scale = int(get_attr("scale") or 100)
				resolved_font = resolveFontFile(filename, path_prefix)
				if resolved_font is None:
					skinWarning("font file %s (%s) not found" % (filename, name))
					continue
				addFont(resolved_font, name, scale, get_attr("replacement") and True or False)
			except Exception as e:
				skinWarning("font %s: %s" % (name, e))
		for alias in c.findall("alias"):
			get_attr = alias.attrib.get
			try:
				size, height = int(get_attr("size")), int(get_attr("height") or 0)
				if scara is not None:
					size, height = _marime(size, scara.sf), _marime(height, scara.sy)
				fonts[get_attr("name")] = (get_attr("font"), size, height)
			except Exception as e:
				skinWarning("font alias %s: %s" % (get_attr("name"), e))

	for c in skin.findall("parameters"):
		for parameter in c.findall("parameter"):
			readParameter(parameter, path_prefix, scara = scara)
	# only this image reads <hdsparameters> (the others skip unknown elements): numbers that replace the ones
	# above for this image, and the images of the lists drawn in Python
	for c in skin.findall("hdsparameters"):
		for parameter in c.findall("parameter"):
			readParameter(parameter, path_prefix, images = True, scara = scara)

	for c in skin.findall("subtitles"):
		from enigma import eSubtitleWidget
		scale = scara_font
		for substyle in c.findall("sub"):
			get_attr = substyle.attrib.get
			try:
				face = getattr(eSubtitleWidget, get_attr("name") or "", None)
				# Subtitle_MAX is the number of styles, not a style: newer skins list it anyway
				if not isinstance(face, int) or face < 0 or face >= eSubtitleWidget.Subtitle_MAX:
					skinNotice("subtitle style %s ignored (not used by this image)" % get_attr("name"))
					continue
				font = parseFont(get_attr("font"), scale)
				col = get_attr("foregroundColor")
				foregroundColor = parseColor(col) if col else gRGB(0xFFFFFF)
				haveColor = col and 1 or 0
				# newer skins describe an outline (borderColor/borderWidth); here it becomes a shadow
				col = get_attr("shadowColor") or get_attr("borderColor")
				shadowColor = parseColor(col) if col else gRGB(0)
				offset = get_attr("shadowOffset")
				if not offset and get_attr("borderWidth"):
					offset = "%s,%s" % (get_attr("borderWidth"), get_attr("borderWidth"))
				shadowOffset = parsePosition(offset, scale)
				eSubtitleWidget.setFontStyle(face, font, haveColor, foregroundColor, shadowColor, shadowOffset)
			except Exception as e:
				skinWarning("subtitle style %s: %s" % (get_attr("name"), e))

	for windowstyle in skin.findall("windowstyle"):
		try:
			style = eWindowStyleSkinned()
			id = int(windowstyle.attrib.get("id") or 0)

			# defaults
			font = gFont("Regular", 20)
			offset = eSize(20, 5)
			for title in windowstyle.findall("title"):
				get_attr = title.attrib.get
				if get_attr("offset"):
					offset = parseSize(get_attr("offset"), scara_xy)
				if get_attr("font"):
					font = parseFont(get_attr("font"), scara_font)
			style.setTitleFont(font)
			style.setTitleOffset(offset)

			for borderset in windowstyle.findall("borderset"):
				bsName = str(borderset.attrib.get("name"))
				for pixmap in borderset.findall("pixmap"):
					get_attr = pixmap.attrib.get
					bpName = get_attr("pos")
					filename = get_attr("filename")
					if not (filename and bpName):
						continue
					try:
						imagine = resolveSkinImage(filename, path_prefix)
						png = loadPixmap(scara.imagine(imagine) if scara is not None else imagine, desktop)
						style.setPixmap(getattr(eWindowStyleSkinned, bsName), getattr(eWindowStyleSkinned, bpName), png)
					except Exception as e:
						skinWarning("borderset %s/%s: %s" % (bsName, bpName, e))

			for color in windowstyle.findall("color"):
				get_attr = color.attrib.get
				colorType = get_attr("name")
				try:
					style.setColor(getattr(eWindowStyleSkinned, "col" + colorType), parseColor(get_attr("color")))
				except Exception as e:
					skinWarning("window style color %s: %s" % (colorType, e))

			eWindowStyleManager.getInstance().setStyle(id, style)
			# cu alt skin ales, stilul ferestrelor HDSatelit (culorile listelor, fundalul, titlul, rama) se tine si in
			# STIL_HDS, pentru ecranele noastre (GUISkin.applySkin, puneStilHds); skinul ales il inlocuieste pe id 0
			if dinHds and id == 0 and altSkinActiv():
				STIL_HDS[0] = style
		except Exception as e:
			skinWarning("%s: window style: %s" % (path_prefix, e))

def loadSkinData(desktop):
	skins = dom_skins[:]
	skins.reverse()
	# rezolutia finala: a ultimului fisier cu <output> (skinul cu prioritatea cea mai mare care o spune); fisierele
	# HDSatelit se scaleaza la ea cand e alta (ScaraEcran, vezi mai sus)
	final = None
	for (p, dom_skin) in skins:
		final = rezolutieOutput(dom_skin) or final
	scara = None
	if final is not None and final != bazaHds():
		scara = ScaraEcran(bazaHds(), final)
		skinNotice("ecranele HDSatelit (%dx%d) se arata pe %dx%d" % (bazaHds() + final))
	_scaraHds[0] = scara
	for (path, dom_skin) in skins:
		try:
			loadSingleSkinData(desktop, dom_skin, path, scara if esteDinHds(path) else None)
		except Exception as e:
			skinWarning("%s: %s" % (path, e))
			print_exc()

def lookupScreen(name, style_id):
	for (path, skin) in dom_skins:
		# first, find the corresponding screen element
		for x in skin.findall("screen"):
			if x.attrib.get('name', '') == name:
				try:
					screen_style_id = int(x.attrib.get('id', '-1'))
				except ValueError:
					screen_style_id = -1
				if screen_style_id == -1 and name.find('ummary') > 0:
					screen_style_id = 1
				if (style_id != 2 and screen_style_id == -1) or screen_style_id == style_id:
					return x, path
	return None, None

def expandPanels(element, skin_path, style_id, screen_name, visited = None):
	"""children of a screen, with every <panel name="X"/> replaced by the children of screen X
	(recursively). Returns (child, skin path of the file the child comes from)."""
	if visited is None:
		visited = set()
	children = [ ]
	for child in element:
		if child.tag != "panel":
			children.append((child, skin_path))
			continue
		panel_name = child.attrib.get("name")
		if not panel_name or panel_name in visited:
			skinWarning("%s: panel %s skipped (missing name or used in a loop)" % (screen_name, panel_name))
			continue
		panel, panel_path = lookupScreen(panel_name, style_id)
		if panel is None:
			skinWarning("%s: panel %s not found" % (screen_name, panel_name))
			continue
		children += expandPanels(panel, panel_path, style_id, screen_name, visited | {panel_name})
	return children

def widgetIsWanted(screen, get_attr):
	# conditional="a,b": the widget is used only when the screen has all these components
	conditional = get_attr('conditional')
	if conditional and [c for c in conditional.split(',') if c.strip() not in screen]:
		return False
	# objectTypes="name,Class1,Class2": only when that component is one of these classes
	objectTypes = get_attr('objectTypes')
	if objectTypes:
		parts = [ p.strip() for p in objectTypes.split(',') ]
		if len(parts) > 1 and (parts[0] not in screen or screen[parts[0]].__class__.__name__ not in parts[1:]):
			return False
	return True

class additionalWidget:
	pass

def readSourceWidget(screen, widget, name, skin_path_prefix, scara = None):
	get_attr = widget.attrib.get
	wsource = get_attr('source')

	while True: # until we found a non-obsolete source
		# "wsource" might specify a related screen before the dot, for example to reference a
		# parent, global or session-global screen.
		scr = screen
		source_path = wsource.split('.')
		while len(source_path) > 1:
			scr = screen.getRelatedScreen(source_path[0])
			if scr is None:
				raise SkinError("related screen of source '%s' not found" % wsource)
			source_path = source_path[1:]

		source = scr.get(source_path[0])
		if isinstance(source, ObsoleteSource):
			print("[Skin] %s uses obsolete source %s, use %s instead" % (name, wsource, source.new_source))
			wsource = source.new_source
		else:
			break

	if source is None:
		raise SkinError("source '%s' not found" % wsource)

	wrender = get_attr('render')
	if not wrender:
		raise SkinError("no render= for source '%s'" % wsource)

	for converter in widget.findall("convert"):
		ctype = converter.get('type')
		if not ctype:
			raise SkinError("convert without type")
		parms = (converter.text or "").strip()
		if scara is not None and ctype == "TemplatedMultiContent":
			parms = scara.sablon(parms)
		converter_class = my_import('.'.join(("Components", "Converter", ctype))).__dict__.get(ctype)
		if converter_class is None:
			raise SkinError("converter %s not found" % ctype)

		c = None
		for i in source.downstream_elements:
			if isinstance(i, converter_class) and i.converter_arguments == parms:
				c = i
		if c is None:
			c = converter_class(parms)
			c.connect(source)
		source = c

	renderer_class = my_import('.'.join(("Components", "Renderer", wrender))).__dict__.get(wrender)
	if renderer_class is None:
		raise SkinError("renderer %s not found" % wrender)

	renderer = renderer_class() # instantiate renderer
	renderer.connect(source) # connect to source
	attributes = renderer.skinAttributes = [ ]
	collectAttributes(attributes, widget, skin_path_prefix, ignore=('render', 'source', 'conditional', 'objectTypes'))
	if scara is not None:
		renderer.skinAttributes = scara.atribute(attributes)
	screen.renderer.append(renderer)

def readSkin(screen, skin, names, desktop):
	if not isinstance(names, list):
		names = [names]

	name = "<embedded-in-'%s'>" % screen.__class__.__name__

	style_id = desktop.getStyleID()

	# try all skins, first existing one have priority
	myscreen, path = None, None
	for n in names:
		myscreen, path = lookupScreen(n, style_id)
		if myscreen is not None:
			# use this name for debug output
			name = n
			break

	# otherwise try embedded skin
	if myscreen is None:
		myscreen = getattr(screen, "parsedSkin", None)

	# try uncompiled embedded skin
	if myscreen is None and getattr(screen, "skin", None):
		skin_tuple = screen.skin
		if not isinstance(skin_tuple, tuple):
			skin_tuple = (skin_tuple,)
		for sskin in skin_tuple:
			try:
				parsedSkin = xml.etree.ElementTree.fromstring(sskin)
			except Exception as e:
				skinWarning("%s: embedded skin is not valid XML (%s)" % (name, e))
				continue
			try:
				screen_style_id = int(parsedSkin.attrib.get('id', '-1'))
			except ValueError:
				screen_style_id = -1
			if (style_id != 2 and screen_style_id == -1) or screen_style_id == style_id:
				myscreen = screen.parsedSkin = parsedSkin
				break

	if myscreen is None:
		print("[Skin] no skin for", names)
		myscreen = screen.parsedSkin = xml.etree.ElementTree.fromstring("<screen></screen>")

	screen.skinAttributes = [ ]

	skin_path_prefix = getattr(screen, "skin_path", path)

	# ecranele scrise pentru alta rezolutie (si culorile, fonturile noastre sub alt skin): ScaraEcran, vezi mai sus
	scara = scaraEcran(myscreen, path, desktop, screen.__class__.__module__ if path is None else None)
	scari = {path: scara}
	# ecranul nostru sub alt skin ales: si stilul ferestrei HDSatelit (GUISkin.applySkin -> puneStilHds)
	screen.stilHds = scara is not None and scara.fonturi is not None

	def scaraCopil(widget_path):
		# un panou din alt fisier se scaleaza dupa fisierul lui
		if widget_path not in scari:
			scari[widget_path] = scaraEcran(None, widget_path, desktop)
		return scari[widget_path]

	collectAttributes(screen.skinAttributes, myscreen, skin_path_prefix, ignore=("name", "resolution"))
	if scara is not None:
		screen.skinAttributes = scara.atribute(screen.skinAttributes)
		if scara.scaleaza and name not in _ecraneScalate:
			_ecraneScalate.add(name)
			skinNotice("%s: %dx%d -> %dx%d" % ((name,) + scara.baza + scara.ecran))

	screen.additionalWidgets = [ ]
	screen.renderer = [ ]

	children = expandPanels(myscreen, path, style_id, name)

	# now walk all widgets: 1:1-mapped widgets (name=) or source->renderer widgets (source=)
	for (widget, widget_path) in children:
		if widget.tag != "widget":
			continue
		get_attr = widget.attrib.get
		wname = get_attr('name')
		wsource = get_attr('source')
		prefix = getattr(screen, "skin_path", widget_path)
		try:
			if not widgetIsWanted(screen, get_attr):
				continue
			sc = scaraCopil(widget_path)
			if wname:
				if wname not in screen:
					raise SkinError("component '%s' not found" % wname)
				attributes = screen[wname].skinAttributes = [ ]
				collectAttributes(attributes, widget, prefix, ignore=('name', 'conditional', 'objectTypes'))
				if sc is not None:
					if wname == "config":
						# lista de setari (eListboxPythonConfigContent) scrie cu "Regular;20" si "Regular;16" cand skinul
						# nu da font si secondfont: numele si marimile acelea trec si ele prin scara
						puse = set(a for a, v in attributes)
						for a, v in (("font", "Regular;20"), ("secondfont", "Regular;16")):
							if a not in puse:
								attributes.append((a, v))
					screen[wname].skinAttributes = sc.atribute(attributes)
			elif wsource:
				readSourceWidget(screen, widget, name, prefix, sc)
			else:
				raise SkinError("widget has no name and no source")
		except Exception as e:
			skinWarning("%s/%s: %s" % (name, wname or wsource, e))

	# now walk additional objects
	for (widget, widget_path) in children:
		w_tag = widget.tag
		if w_tag == "widget":
			continue
		try:
			if w_tag == "applet":
				codeText = (widget.text or "").strip()
				widgetType = widget.attrib.get('type')
				code = compile(codeText, "skin applet", "exec")
				if widgetType == "onLayoutFinish":
					screen.onLayoutFinish.append(code)
				else:
					raise SkinError("applet type '%s' unknown" % widgetType)
				continue

			w = additionalWidget()
			if w_tag == "eLabel":
				w.widget = eLabel
			elif w_tag == "ePixmap":
				w.widget = ePixmap
			else:
				raise SkinError("unsupported element <%s>" % w_tag)

			w.skinAttributes = [ ]
			collectAttributes(w.skinAttributes, widget, getattr(screen, "skin_path", widget_path), ignore=('name',))
			sc = scaraCopil(widget_path)
			if sc is not None:
				w.skinAttributes = sc.atribute(w.skinAttributes)
			screen.additionalWidgets.append(w)
		except Exception as e:
			skinWarning("%s/<%s>: %s" % (name, w_tag, e))
