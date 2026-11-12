# Modificat de moneasoftware.com si hdsatelit.com, 2026
from Tools.Profile import profile
profile("LOAD:ElementTree")
import xml.etree.ElementTree
import re
from os import path
from glob import glob
from traceback import print_exc

profile("LOAD:enigma_skin")
from enigma import eSize, ePoint, gFont, eWindow, eLabel, ePixmap, eWindowStyleManager, \
	addFont, gRGB, eWindowStyleSkinned, getDesktop
from Components.config import ConfigSubsection, ConfigText, ConfigSelection, ConfigYesNo, config
from Components.Converter.Converter import Converter
from Components.Sources.Source import Source, ObsoleteSource
from Tools.Directories import resolveFilename, SCOPE_SKIN, SCOPE_SKIN_IMAGE, SCOPE_FONTS, SCOPE_CURRENT_SKIN, SCOPE_CONFIG, fileExists
from Tools.Import import my_import
from Tools.LoadPixmap import LoadPixmap

# Rule of this module: a mistake in a skin never stops the receiver. Every problem is written to
# the log as "[Skin] ..." and collected in `warnings` (shown once after start); the faulty
# widget, color or font is skipped and everything else is still drawn.

colorNames = dict()
# HDSatelit 0.7.4: culorile din <colors> al caror value e un degrade ("a,b[,c],directie[,alphablend]", skin-urile straine:
# <color name="ListSelection" value="selection,selectionShade,vertical"/>): nume -> textul degradeului. colorNames are
# atunci prima culoare (ce desena si inainte), iar degradeul se ia oriunde se cere unul.
gradients = dict()
fonts = dict()       # <alias name="Body" font="Regular" size="30" height="40"/> -> (font, size, height)
# HDSatelit 0.7.4: latimea unui caracter din <alias width="..."/> (skin-urile straine; "w" si "h" in coordonate). fonts ramane cu
# trei campuri (ecranele noastre il despacheteaza asa).
latimiFont = dict()
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
_surseSkin = {}
_xmlAfisaj = set()

def loadSkin(name = None, scope = SCOPE_SKIN, desktop = None, screenID = None, filename = None):
	# read the skin. HDSatelit: si cu numele argumentelor OE-Alliance (filename=, desktop=, screenID=), ca la pluginurile
	# scrise pentru acele imagini; desktop/screenID nu schimba nimic aici (datele se incarca in loadSkinData)
	if name is None:
		name = filename
	filename = resolveFilename(scope, name)
	mpath = path.dirname(filename) + "/"
	radacina = xml.etree.ElementTree.parse(filename).getroot()
	dom_skins.append((mpath, radacina))
	_surseSkin[id(radacina)] = name
	return radacina

# HDSatelit: tema externa aleasa de om. Tot ce s-a adaugat pentru temele scrise de altii (includerile, pozitiile relative,
# convertoarele cu tipuri in plus, rezerva unui ecran care nu se poate folosi: Components/HdsTemaExterna.py) se aplica numai
# ecranelor din dosarele de aici. Cu tema HD Satelit (Clasic, Pro) multimea e goala si nimic din ele nu ruleaza.
dosareSkinStraine = set()
# ce nu s-a putut din tema: numele ecranului -> {"rezerva": motivul sau None, "lipsa": [componentele lipsa]}
raportTema = dict()
_modulTema = [ ]

def _Tema():
	if not _modulTema:
		from Components import HdsTemaExterna
		_modulTema.append(HdsTemaExterna)
	return _modulTema[0]

def pregatesteTemaExterna(name):
	"""Dupa loadSkin pe tema aleasa de om: includerile puse la loc, rezolutia verificata, dosarul tinut minte. O tema stricata iese din
	lista si arunca exceptie, iar skin.py revine la HDSatelit."""
	mpath, radacina = dom_skins[-1]
	try:
		if radacina.find("include") is not None:
			_Tema().puneIncluderile(radacina, mpath, resolveFilename(SCOPE_SKIN, name), resolveFilename(SCOPE_SKIN, ""))
		_Tema().verificaRezolutia(radacina)
	except Exception:
		dom_skins.pop()
		raise
	_Tema().pornesteImportul()
	dosareSkinStraine.add(mpath)

# HDSatelit 0.7.4 (TL): sabloanele listei de canale, ca in standardul OE-Alliance (advanced/channel-styles,
# template-reference): <template component="serviceList" name="..." fonts="..."><mode name="services|bouquets|other">...
# in skinTemplates.xml langa tema aleasa (si skinUserTemplates.xml), altfel in widgeturile ecranelor temei. Numele cerute de
# pluginurile temelor (UmbraSettings: componentTemplates, domScreens, reloadSkinTemplates; config.channelSelection.screenStyle
# si widgetStyle). Se citesc numai pentru o tema straina; cu tema HD Satelit registrul ramane gol si setarile au numai
# „lista clasica”. Ca acolo, din fabrica lista ramane cea clasica (screenStyle gol). Lista de canale nu se deseneaza inca
# dupa sablon: registrul si setarile sunt pentru pluginurile temelor (vezi STADIU-TL-SABLOANE-RETEA.md).
class ComponentTemplates(object):
	"""sabloanele cu component= din tema: (componenta, nume) -> elementul <template>; ultimul cu acelasi nume castiga"""
	def __init__(self):
		self.changedTimes = {}
		self.templates = {}

	def add(self, template, fileName=None):
		if fileName and fileName not in self.changedTimes:
			try:
				self.changedTimes[fileName] = path.getmtime(fileName)
			except OSError:
				self.changedTimes[fileName] = None
		component = template.get("component")
		name = template.get("name")
		if component and name:
			self.templates.setdefault(component, {})[name] = template

	def clear(self):
		self.templates = {}
		self.changedTimes = {}

	def get(self, component, name):
		return self.templates.get(component, {}).get(name)

	def names(self, component):
		if component in self.templates:
			return list(self.templates[component].keys())
		return None

	def isChanged(self):
		for fileName, timp in self.changedTimes.items():
			try:
				if path.getmtime(fileName) != timp:
					return True
			except OSError:
				if timp is not None:
					return True
		return False

componentTemplates = ComponentTemplates()
# fisierul skin.xml al temei alese (cale relativa la SCOPE_SKIN), cum il stiu pluginurile temelor
currentPrimarySkin = "HDSatelit/skin.xml"
COMPONENTE_SABLOANE = ("serviceList",)

class _EcraneDom(object):
	"""domScreens: numele ecranului -> (elementul <screen>, dosarul fisierului), primul gasit in ordinea cautarii
	(ca lookupScreen); citit din dom_skins la fiecare folosire, deci mereu la zi"""
	def _toate(self):
		rez = {}
		for (mpath, radacina) in dom_skins:
			for x in radacina.findall("screen"):
				nume = x.attrib.get("name")
				if nume and nume not in rez:
					rez[nume] = (x, mpath)
		return rez

	def items(self):
		return self._toate().items()

	def keys(self):
		return self._toate().keys()

	def values(self):
		return self._toate().values()

	def get(self, nume, implicit=None):
		return self._toate().get(nume, implicit)

	def __getitem__(self, nume):
		return self._toate()[nume]

	def __contains__(self, nume):
		return nume in self._toate()

	def __iter__(self):
		return iter(self._toate())

	def __len__(self):
		return len(self._toate())

domScreens = _EcraneDom()

def loadSkinTemplates(skinTemplatesFileNames):
	"""sabloanele cu component= cunoscut: din fisierele date (<skin><template .../></skin>), altfel din ecranele temei"""
	def adauga(template, fileName):
		if template.get("component", "") in COMPONENTE_SABLOANE:
			componentTemplates.add(template, fileName)
	if skinTemplatesFileNames:
		for fileName in skinTemplatesFileNames:
			try:
				radacina = xml.etree.ElementTree.parse(fileName).getroot()
			except Exception as err:
				skinWarning("sabloanele din %s nu s-au citit: %s" % (fileName, err))
				continue
			for template in radacina.findall("template"):
				adauga(template, fileName)
	else:
		for (mpath, radacina) in dom_skins:
			if mpath not in dosareSkinStraine:
				continue
			for template in radacina.findall(".//widget/templates/template"):
				adauga(template, None)

def reloadSkinTemplates(clear=False):
	"""sabloanele temei alese: skinTemplates.xml langa skin.xml si skinUserTemplates.xml (din dosarul temei); fara ele, din
	ecrane. Cu tema HD Satelit nu se citeste nimic. Dupa citire se refac alegerile setarilor listei de canale."""
	if clear:
		componentTemplates.clear()
	fisiere = []
	if dosareSkinStraine:
		for nume in (path.join(path.dirname(currentPrimarySkin), "skinTemplates.xml"), path.join(path.dirname(currentPrimarySkin), "skinUserTemplates.xml")):
			cale = resolveFilename(SCOPE_SKIN, nume)
			if path.isfile(cale):
				fisiere.append(cale)
		loadSkinTemplates(fisiere)
	refreshChannelSelectionStyleChoices()

def getcomponentTemplateNames(component):
	return componentTemplates.names(component)

def refreshChannelSelectionStyleChoices():
	"""config.channelSelection.screenStyle (ecranele temei cu base="ChannelSelection"; "" = lista clasica, din fabrica) si
	widgetStyle (sabloanele serviceList; primul din fabrica), ca in standard; nu sunt in meniurile noastre"""
	if getattr(config, "channelSelection", None) is None:
		config.channelSelection = ConfigSubsection()
	ecrane = [("", "Lista clasică")]
	stiluri = componentTemplates.names("serviceList") or []
	if stiluri:
		for nume, (element, _p) in domScreens.items():
			if element.get("base") == "ChannelSelection":
				ecrane.append((nume, element.get("label", nume)))
	sabloane = [(stil, stil) for stil in stiluri]
	for nume, alegeri, implicit in (("screenStyle", ecrane, ""), ("widgetStyle", sabloane or [("", "")], stiluri[0] if stiluri else "")):
		setare = getattr(config.channelSelection, nume, None)
		if setare is None:
			setattr(config.channelSelection, nume, ConfigSelection(default=implicit, choices=alegeri))
		else:
			setare.setChoices(alegeri, default=implicit)
	# cerute de sabloane (conditional="config.channelSelection.piconRatio.value == 167", 42 de randuri in corpusul de teme)
	# si de pluginul de setari al temei Umbra (showNumber, showPicon...); ca in standard, numai daca lipsesc, fara meniu
	if getattr(config.channelSelection, "piconRatio", None) is None:
		config.channelSelection.piconRatio = ConfigSelection(default=167, choices=[(167, "16:10"), (235, "1:2.35"), (250, "1:2.5")])
	for nume in ("showNumber", "showPicon", "showProgress", "showCryptoIcon", "showServiceTypeIcon", "showTimers"):
		if getattr(config.channelSelection, nume, None) is None:
			setattr(config.channelSelection, nume, ConfigYesNo(default=True))

# skins are loaded in order of priority: the skin with the highest priority is loaded last
# (usually the user-provided skin). loadSingleSkinData (colors, fonts, window style) is applied
# in ascending priority; dom_skins keeps the screens in descending priority, so the first screen
# found is used.
config.skin = ConfigSubsection()


def _progresColoratSchimbat(element):
	# Bara pastreaza culorile temei; alegerea se vede la redesenare.
	from enigma import eSlider
	eSlider.setForegroundGradientEnabled(element.value)


config.skin.progres_colorat = ConfigYesNo(default=True)
config.skin.progres_colorat.addNotifier(_progresColoratSchimbat)

AFISAJ_HDS = "HDSatelit/display/skin_display.xml"


def afisajImplicit():
	# Geometria vine din driver, inclusiv cand imaginea porneste prin NeoBoot.
	try:
		s = getDesktop(1).size()
		if (s.width(), s.height()) in ((480, 320), (400, 240), (800, 480)):
			return AFISAJ_HDS
	except Exception:
		pass
	return ""


config.skin.display_skin = ConfigText(default=afisajImplicit())
# Alegerea explicita a temei proprii se pastreaza si cand coincide cu implicitul.
config.skin.display_skin.save_forced = True


def fisierAfisaj(nume):
	filename = resolveFilename(SCOPE_SKIN, nume)
	if not fileExists(filename) and not path.isabs(nume):
		filename = resolveFilename(SCOPE_SKIN, path.join("display", nume))
	return filename


def citesteAfisaj(nume):
	"""Citeste un XML LCD fara sa schimbe setarea salvata sau numele ecranelor."""
	filename = fisierAfisaj(nume)
	radacina = xml.etree.ElementTree.parse(filename).getroot()
	if radacina.tag != "skin" or not radacina.findall("screen"):
		raise ValueError("fisierul nu contine ecrane de afisaj")
	for tip in ("output", "windowstyle"):
		if any(c.get("id") not in ("1", "2") for c in radacina.findall(tip)):
			raise ValueError("fisierul contine un desktop care nu este LCD")
	if any(c.get("id") not in (None, "1", "2") for c in radacina.findall("screen")):
		raise ValueError("fisierul contine ecrane care nu sunt LCD")
	# Un XML LCD separat poate omite id. El nu trebuie sa intre pe televizor.
	try:
		stil = str(getDesktop(1).getStyleID())
	except Exception:
		stil = "1"
	if stil not in ("1", "2"):
		stil = "1"
	for ecran in radacina.findall("screen"):
		if ecran.get("id") is None:
			ecran.set("id", stil)
	return filename, radacina


def incarcaAfisaj(skin_tv=None, rezerva=False):
	"""Tema LCD explicita, apoi tema TV; rezerva proprie se incarca dupa ele."""
	if rezerva:
		alegeri = [afisajImplicit()]
	elif _mediu.get("HDS_MOD_SIGUR") == "1":
		return
	else:
		ales = config.skin.display_skin.value
		explicit = getattr(config.skin.display_skin, "saved_value", None) is not None
		alegeri = [ales] if ales and (ales != AFISAJ_HDS or explicit) else []
		if not alegeri and skin_tv and not explicit:
			alegeri = [path.join(path.dirname(skin_tv), "skin_display.xml").replace("\\", "/")]
	for nume in alegeri:
		if nume == AFISAJ_HDS and not afisajImplicit():
			continue
		if not nume or not fileExists(fisierAfisaj(nume)):
			continue
		if any(_surseSkin.get(id(r)) == nume for _p, r in dom_skins):
			continue
		try:
			filename, radacina = citesteAfisaj(nume)
			dom_skins.append((path.dirname(filename) + "/", radacina))
			_surseSkin[id(radacina)] = nume
			_xmlAfisaj.add(id(radacina))
			return
		except Exception as err:
			skinNotice("afisajul %s nu s-a incarcat: %s" % (nume, err))


def afisajExternActiv():
	"""Sursa LCD externa incarcata; un Summary TV generic nu ocupa afisajul."""
	for _dosar, radacina in dom_skins:
		nume = _surseSkin.get(id(radacina), "")
		if id(radacina) in _xmlAfisaj:
			return "" if nume == AFISAJ_HDS else nume
		if not nume or nume in ("HDSatelit/skin.xml", "HDSatelit/skin_pro.xml", "skin_default.xml"):
			continue
		if any(
			e.get("id") in ("1", "2") for e in radacina.findall("screen")):
			return nume
	return ""


def listaAfisaje(pastreaza_ales=True):
	"""(cale, eticheta) pentru XML-urile LCD instalate; alegerea lipsa ramane vizibila."""
	radacina = resolveFilename(SCOPE_SKIN, "")
	alegeri = [(AFISAJ_HDS, "HD Satelit")]
	for filename in sorted(glob(path.join(radacina, "**", "skin_display*.xml"), recursive=True)):
		nume = path.relpath(filename, radacina).replace(path.sep, "/")
		if nume != AFISAJ_HDS:
			alegeri.append((nume, nume))
	ales = config.skin.display_skin.value
	if pastreaza_ales and ales and ales not in [n for n, _e in alegeri]:
		alegeri.append((ales, ales))
	return alegeri


def alegeAfisaj(nume, salveaza=True):
	"""Valideaza alegerea explicita. Ecranele se aplica la repornirea interfetei."""
	if nume not in [n for n, _e in listaAfisaje(False)]:
		return False, "Tema de afisaj nu este instalata."
	try:
		citesteAfisaj(nume)
	except Exception:
		return False, "Tema de afisaj nu poate fi citita."
	config.skin.display_skin.value = nume
	config.skin.display_skin.save()
	if salveaza:
		from Components.config import configfile
		configfile.save()
	return True, "Tema de afisaj se aplica la repornirea interfetei."
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

# Ecranele utilizatorului raman primele. Tema LCD aleasa precede tema TV.
incarcaAfisaj(skinAles)

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

def partiTema(nume, dosar_skin=None):
	"""Partile unei teme straine, ca in imaginile pentru care e scrisa (nota OEA8): <dosarul temei>/mySkin/skin_*.xml, in
	ordine alfabetica (pluginurile de setari ale temelor scriu acolo alegerile omului: culori, vreme, postere). Cai
	intregi; [] fara dosar."""
	dosar_skin = dosar_skin if dosar_skin is not None else resolveFilename(SCOPE_SKIN, "")
	dosar = path.join(path.dirname(path.join(dosar_skin, nume)), "mySkin")
	if not path.isdir(dosar):
		return [ ]
	return sorted(glob(path.join(dosar, "skin_*.xml")))

def incarcaPartiTema(nume):
	"""partile temei inaintea temei (dom_skins: primul gasit castiga, deci partile trec peste ecranele si culorile ei);
	o parte stricata se sare cu un rand in jurnal. Intoarce cate s-au incarcat."""
	n = 0
	for cale in partiTema(nume):
		try:
			loadSkin(cale)
			dosareSkinStraine.add(dom_skins[-1][0])
			n += 1
		except Exception as err:
			skinWarning("partea temei %s nu s-a incarcat: %s" % (cale, err))
	return n

if skinAles is not None:
	_inaintePartilor = len(dom_skins)
	try:
		incarcaPartiTema(skinAles)
		loadSkin(skinAles)
		pregatesteTemaExterna(skinAles)
		skinPornit = skinAles
		currentPrimarySkin = skinAles
		skinNotice("skinul ales: %s, cu HDSatelit/skin.xml ca rezerva" % skinAles)
	except Exception as err:
		# numai in jurnal: mesajul pentru om, tradus, il da extensia SkinSelector la pornirea sesiunii (HdsSkinuri)
		skinNotice("skinul ales %s nu s-a incarcat, ramane HDSatelit: %s" % (skinAles, err))
		# partile temei pleaca odata cu ea
		for _mpath, _r in dom_skins[_inaintePartilor:]:
			dosareSkinStraine.discard(_mpath)
		del dom_skins[_inaintePartilor:]
		_HdsSkinuri.incarcareCazuta(skinAles, err)
		config.skin.primary_skin.value = _HdsSkinuri.SKIN_IMAGINE
		config.skin.primary_skin.save()
		# omul revine la tema HD Satelit cu varianta aleasa de el (Clasic sau Pro), chiar de la pornirea asta
		try:
			if temaProDeIncarcat():
				loadSkin(TEMA_PRO_FISIER)
		except Exception as err2:
			skinWarning("tema Pro nu s-a incarcat, ramane Clasic: %s" % err2)

# sabloanele listei de canale ale temei alese (registrul componentTemplates; cu tema HD Satelit nu se citeste nimic)
try:
	reloadSkinTemplates()
except Exception as err:
	skinWarning("sabloanele listei de canale nu s-au citit: %s" % err)

# Rezerva LCD nu acopera ecranele explicite ale temei TV externe.
incarcaAfisaj(rezerva=True)

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

def centruCuDeplasare(pos, wsize, ssize, scale = (1, 1)):
	""""center", "center+20", "center-8" (ghidul coordonatelor din skin-urile straine): elementul centrat plus deplasarea
	(scalata), cel putin 0; None pentru orice alta forma"""
	pos = pos.strip()
	if not pos.startswith("center"):
		return None
	rest = pos[6:].replace(" ", "")
	deplasare = 0
	if rest:
		if rest[0] not in "+-" or not rest[1:].isdigit():
			return None
		deplasare = int(rest) * scale[0] // scale[1]
	return max((ssize - wsize) // 2 + deplasare, 0)

def evalPos(pos, wsize, ssize, scale):
	if pos == "center":
		pos = (ssize - wsize) // 2
	elif pos.startswith("center"):
		v = centruCuDeplasare(pos, wsize, ssize, scale)
		if v is None:
			raise ValueError("pozitia \"%s\" nu e inteleasa" % pos)
		pos = v
	else:
		pos = int(pos) * scale[0] // scale[1]
	return int(pos)

def _esteDesktop(o):
	return o is None or hasattr(o, "getStyleID")

def parsePosition(s, scale, desktop = None, size = None, *oea):
	"""ale noastre: (s, scale, desktop, size). Pluginurile scrise pentru imaginile OE-Alliance cheama si
	(value, scale, object, desktop, size): al treilea e atunci elementul, nu desktopul; se recunoaste dupa tip."""
	if oea or not _esteDesktop(desktop):
		obiect, desktop, size = desktop, size, (oea[0] if oea else None)
		if not _esteDesktop(desktop):
			desktop = None
		s = _relativFataDeParinte(s, obiect, desktop, size)
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

def parseSize(s, scale, obiect = None, desktop = None):
	"""(value, scale) la noi; pluginurile OE-Alliance dau si (object, desktop), ca "e", "c" si "%" sa fie fata de parinte"""
	if obiect is not None or desktop is not None:
		s = _relativFataDeParinte(s, obiect, desktop, None)
	if not s:
		return eSize(0, 0)
	x, y = s.split(',')
	return eSize(int(x) * scale[0][0] // scale[0][1], int(y) * scale[1][0] // scale[1][1])

def _relativFataDeParinte(s, obiect, desktop, size):
	"""o pereche cu e, c, % (forma pluginurilor scrise pentru imaginile OE-Alliance) -> numere, fata de parintele
	elementului (sau fata de desktop); fara asa ceva, valoarea asa cum e"""
	if not s or not isinstance(s, str) or not _valoareRelativa(s):
		return s
	parinte = None
	try:
		p = obiect.getParent() if obiect is not None and hasattr(obiect, "getParent") else None
		if p is not None and p.size().width() <= 0 and hasattr(p, "getParent") and p.getParent() is not None:
			p = p.getParent()
		if p is not None:
			parinte = (p.size().width(), p.size().height())
	except Exception:
		parinte = None
	if parinte is None and desktop is not None:
		parinte = (desktop.size().width(), desktop.size().height())
	if parinte is None:
		return s
	atribute = [("position", s)]
	if size is not None:
		atribute.append(("size", "%d,%d" % (size.width(), size.height())))
	return dict(_Tema().rezolvaRelative(atribute, parinte[0], parinte[1])).get("position", s)

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
				rez.append(scaleazaExpresie(p, f))
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
			if atribut in ("pointer", "seek_pointer", "seekPointer"):
				nume, sep, poz = v.rpartition(':')
				return nume + sep + self.pereche(poz) if sep else v
			if atribut in ("pixmap", "backgroundPixmap", "selectionPixmap") or atribut in POZE_BARA or atribut in POZE_PISTA:
				return self.imagine(v)
			if atribut == "itemWidth":
				return str(_marime(int(v), self.sx))
			if a.endswith("height"):
				return str(_marime(int(v), self.sy))
			if a.endswith("padding") and "," in v:
				# padding="stanga,sus[,dreapta,jos]" (skin-urile straine)
				return ",".join(str(_marime(int(x), self.sf)) for x in v.split(","))
			if a.endswith("width") or a.endswith("padding"):
				return str(_marime(int(v), self.sf))
			if atribut in ("cornerRadius", "itemCornerRadius", "itemCornerRadiusSelected"):
				raza, sep, colturi = v.partition(';')
				return str(_marime(int(raza), self.sf)) + sep + colturi
			if atribut == "itemSpacing":
				return self.pereche(v if "," in v else "%s,%s" % (v, v))
			if atribut in ("scrollbarRadius", "scrollbarOffset"):
				return str(_marime(int(v), self.sf))
			if atribut == "colposition":
				return str(_ori(int(v), self.sx))
		if "font" in a:
			return self.font(v)
		if self.culori and (atribut in ("foregroundGradient", "backgroundGradient") or
				(atribut in ("backgroundColor", "foregroundColor") and ',' in v)):
			# culorile cu nume ale unui degrade; directia si alphablend nu sunt nume de culori si raman
			return ','.join([self.culori.get(p.strip(), p.strip()) for p in v.split(',')])
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

_TERMENI = re.compile(r'([+-])')

def scaleazaExpresie(p, f):
	"""o coordonata cu expresie a unui ecran scalat ("e-48", "center+20", "c-10"): numai termenii facuti doar din cifre
	se scaleaza (sunt pixeli ai grilei de proiectare); e, c, %, w, h, f si termenii care le contin (e/4, 3*e, 25%) raman,
	fiindca se socotesc din marimea deja scalata a parintelui. "center", "fill", cuvintele raman cum sunt."""
	bucati = _TERMENI.split(p)
	if len(bucati) == 1:
		return p
	rez = [ ]
	for b in bucati:
		t = b.strip()
		rez.append(str(_ori(int(t), f)) if t.isdigit() else b)
	return ''.join(rez)

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
_rameFerestre = {}

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
			lcd_path = path.dirname(resolveFilename(SCOPE_SKIN, AFISAJ_HDS))
			if skin_path and path.normpath(skin_path) == path.normpath(lcd_path):
				s = desktop.size()
				if s.width() > 0 and s.height() > 0:
					return ScaraEcran((480, 320), (s.width(), s.height()))
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


class _PozitieFereastra(str):
	"""Pozitia unei ferestre de plugin se calculeaza dupa rama ei reala."""
	pass


def fereastraPlugin(element, skin_path, desktop, modul):
	"""Baza ferestrei din codul unui plugin, fata de desktop si rama temei."""
	if skin_path is not None or not (modul or "").startswith("Plugins.") or modulImagine(modul):
		return None
	if desktop.getStyleID() != 0:
		return None
	marime = rezolutieAtribut(element.get("size"))
	if marime is None:
		return None
	baza = rezolutieAtribut(element.get("resolution"))
	s = desktop.size()
	ecran = (s.width(), s.height())
	pozitie = element.get("position", "0,0").split(",")
	if len(pozitie) != 2:
		return None
	try:
		p = [None if v.strip() == "center" else int(v) for v in pozitie]
	except ValueError:
		return None
	if baza is None:
		# Nu deducem baza din tema: un plugin FHD poate rula sub o tema HD pe desktop FHD.
		baza = ecran
		if ecran == (1280, 720) and all(0 < m <= b for m, b in zip(marime, BAZA_HDS_IMPLICITA)):
			limite = [m if v is None else v + m for v, m in zip(p, marime)]
			if any(l > d for l, d in zip(limite, ecran)) and all(l <= b for l, b in zip(limite, BAZA_HDS_IMPLICITA)):
				baza = BAZA_HDS_IMPLICITA
	# Rama ramane a temei. Rezervam loc pentru ea inainte sa scalam si elementele pluginului.
	rama = (0, 0, 0, 0) if "wfNoBorder" in [v.strip() for v in element.get("flags", "").split(",")] else _rameFerestre.get(0, (0, 0, 0, 0))
	disponibil = (max(1, ecran[0] - rama[0] - rama[2]), max(1, ecran[1] - rama[1] - rama[3]))
	marime_scalata = tuple(_marime(m, (d, b)) for m, d, b in zip(marime, ecran, baza))
	factor = min([1.0] + [float(d) / m for d, m in zip(disponibil, marime_scalata)])
	tinta = tuple(max(1, int(d * factor)) for d in ecran)
	# Coordonatele numerice care centreaza continutul cer aceeasi centrare si cu rama.
	pozitie = ["center" if v is None or v == (b - m) // 2 else str(v)
		for v, b, m in zip(p, baza, marime)]
	if "position" not in element.attrib and (baza != ecran or tinta != ecran):
		pozitie = ["center", "center"]
	if baza != tinta:
		scara = ScaraEcran(baza, tinta)
		pozitie = scara.pereche(",".join(pozitie))
	else:
		scara, pozitie = None, ",".join(pozitie)
	return scara, _PozitieFereastra(pozitie)


def pozitieFereastra(guiObject, desktop, valoare, scale):
	"""Centrarea foloseste exteriorul; move primeste pozitia continutului."""
	poz = parsePosition(valoare, scale, desktop, guiObject.csize())
	marime, ecran = guiObject.size(), desktop.size()
	offset = guiObject.child().position()
	valori = []
	for text, v, m, d, o in zip(valoare.split(","), (poz.x(), poz.y()),
		(marime.width(), marime.height()), (ecran.width(), ecran.height()), (offset.x(), offset.y())):
		if text.strip() == "center":
			v = (d - m) // 2 + o
		elif m <= d:
			v = max(o, min(v, d - m + o))
		valori.append(v)
	return ePoint(*valori)

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

def parseColor(s, default = None):
	"""o culoare #aarrggbb, #rrggbb sau un nume. default (forma OE-Alliance, parseColor(value, default=)): ce se intoarce
	in locul unei culori gresite, in loc de SkinError"""
	if default is not None:
		try:
			return parseColor(s)
		except Exception:
			return gRGB(default) if isinstance(default, int) else default
	if not s:
		raise SkinError("missing color value")
	if s[0] != '#':
		try:
			return colorNames[s]
		except KeyError:
			# HDSatelit: pluginurile altor imagini cer culorile de baza dupa nume (parseColor("red")), pe care le are skinul
			# implicit al acelor imagini; numai cand skinul nostru nu are numele
			if s.lower() in CULORI_DE_BAZA:
				return gRGB(CULORI_DE_BAZA[s.lower()])
			# tema externa cu gradient intre culori cu nume: se deseneaza prima culoare
			if dosareSkinStraine and "," in s:
				return parseColor(s.split(",")[0].strip())
			raise SkinError("color '%s' must be #aarrggbb or valid named color" % (s))
	try:
		return gRGB(int(s[1:], 0x10))
	except ValueError:
		# tema externa cu gradient: se deseneaza prima culoare, ca fundalul sa ramana
		if dosareSkinStraine and "," in s:
			return parseColor(s.split(",")[0].strip())
		raise

# HDSatelit: culorile de baza dupa nume, #aarrggbb (aa = 00 opac, ff transparent), cand skinul nu le defineste
CULORI_DE_BAZA = {"black": 0x00000000, "white": 0x00ffffff, "red": 0x00ff0000, "green": 0x0000ff00, "blue": 0x000000ff,
	"yellow": 0x00ffff00, "grey": 0x00808080, "gray": 0x00808080, "darkgrey": 0x00404040, "darkgray": 0x00404040,
	"lightgrey": 0x00c0c0c0, "lightgray": 0x00c0c0c0, "orange": 0x00ffa500, "transparent": 0xff000000,
	# numele de rol din skinurile altor imagini: textul alb pe fundal negru
	"foreground": 0x00ffffff, "background": 0x00000000}

# HDSatelit: degradeurile din teme (backgroundGradient, foregroundGradient, backgroundColor/foregroundColor cu virgula ale
# skin-urilor straine): "start[,mijloc],sfarsit,directie[,alphablend]", culori #aarrggbb sau nume din <colors>; directia
# vertical (de sus in jos) sau horizontal; alphablend 1/true/on/yes. Directiile ca eWidget.GRADIENT_* (lib/gui/ewidget.h).
GRADIENT_VERTICAL = 1
GRADIENT_HORIZONTAL = 2

def _esteCuloare(s):
	if s[:1] == '#':
		return len(s) in (7, 9)
	return s in colorNames or s.lower() in CULORI_DE_BAZA

def citesteDegrade(value):
	"""'a,b[,c],directie[,alphablend]' -> ([2 sau 3 culori gRGB], vertical (bool), alphablend (0 sau 1)). SkinError fara
	cel putin doua culori si o directie. O directie necunoscuta (alt cuvant) e verticala, ca in skin-urile straine."""
	value = gradients.get(value.strip(), value)
	parti = [p.strip() for p in value.split(',')]
	culori = [ ]
	for p in parti:
		if len(culori) == 3 or not _esteCuloare(p):
			break
		culori.append(parseColor(p))
	rest = parti[len(culori):]
	if len(culori) < 2 or not rest or len(rest) > 2 or not rest[0]:
		raise SkinError("degradeul \"%s\" trebuie sa fie start[,mijloc],sfarsit,horizontal|vertical[,alphablend]" % value)
	directie = rest[0].lower()
	if directie not in ("horizontal", "vertical"):
		skinNotice("degradeul \"%s\": directia \"%s\" necunoscuta, se ia vertical" % (value, rest[0]))
	alpha = len(rest) == 2 and rest[1].lower() in ("1", "alphablend", "enabled", "on", "true", "yes")
	return culori, directie != "horizontal", int(alpha)

def parseGradient(value):
	"""ca in skin-urile straine: (start, mijloc, sfarsit, directie, alphablend) pentru setBackgroundGradient; la doua
	culori mijlocul e chiar sfarsitul (asa le deosebeste eWidget)"""
	culori, vertical, alpha = citesteDegrade(value)
	if len(culori) == 2:
		culori.append(culori[1])
	return culori[0], culori[1], culori[2], GRADIENT_VERTICAL if vertical else GRADIENT_HORIZONTAL, alpha

def parseForegroundGradient(value):
	"""pentru eSlider.setForegroundGradient: ([2 sau 3 culori], 1 = vertical)"""
	culori, vertical, alpha = citesteDegrade(value)
	return culori, int(vertical)

def parseRadius(value):
	"""cornerRadius: '20' -> (20, 15); '20;top' sau '20;topLeft,bottomRight' -> raza si colturile rotunjite (bitii
	RADIUS_* din lib/gui/ewidget.h: 1 stanga sus, 2 dreapta sus, 4 stanga jos, 8 dreapta jos); un nume necunoscut nu adauga nimic"""
	raza, sep, colturi = value.partition(';')
	raza = int(raza.strip())
	if not sep:
		return raza, 15
	biti = {"topleft": 1, "topright": 2, "top": 3, "bottomleft": 4, "bottomright": 8, "bottom": 12, "left": 5, "right": 10, "all": 15}
	rez = 0
	for c in colturi.split(','):
		rez |= biti.get(c.strip().lower(), 0)
	return raza, rez


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

# HDSatelit 0.7.4 (OEA15): parametrii pictogramelor listelor, ca in OE-Alliance (ChoiceListNative, ChoiceListIcon_red,
# FileListNativeIcons, FileListIcon_movie, MovieListIcon_play, VirtualKeyboardNative, VirtualKeyboardNativeColors...).
# Valorile au si coduri 0x.., culori #.. si nume de culori din tema; numai aceste nume primesc forma lor, ca o valoare
# straina gresita pentru alt parametru sa nu treaca drept numere. Numele culorilor se citesc la desen (SkinIcon.culoare).
_PARAMETRU_PICTOGRAMA = re.compile(r"^(ChoiceList|FileList|MovieList|VirtualKeyboard)(Native\w*|Icon_\w+)$")

def parametruPictograma(s):
	"""'59922,red,red' -> (59922, 'red', 'red'); '0xea86,live' -> (0xEA86, 'live'); '#00ff0000' -> 0xff0000.
	ValueError pentru o parte goala."""
	parti = []
	for p in s.split(','):
		p = p.strip()
		if not p:
			raise ValueError("empty part")
		if p[:2].lower() == "0x":
			p = int(p, 16)
		elif p[0] == "#":
			p = int(p[1:], 16)
		elif p.lstrip("-").isdigit():
			p = int(p)
		elif p[0] == "*":
			p = p[1:]
		parti.append(p)
	return parti[0] if len(parti) == 1 else tuple(parti)

def readParameter(parameter, path_prefix, images = False, scara = None):
	"""<parameter name="..." value="..."/> into `parameters`; a bad value is skipped with one log line. `scara`
	(ScaraEcran, fisierele HDSatelit pe alt ecran): numerele se scaleaza (scaleazaParametru)."""
	name = parameter.attrib.get("name")
	value = parameter.attrib.get("value")
	if not name or value is None:
		skinWarning("%s: parameter without name or value skipped" % path_prefix)
		return
	if _PARAMETRU_PICTOGRAMA.match(name):
		# pictogramele din listele desenate in Python, forma OE-Alliance (Components/SkinIcon.py): cod, culoare, culoare
		# aleasa; inaintea numerelor obisnuite, ca un cod sa nu fie scalat niciodata
		try:
			parameters[name] = parametruPictograma(value)
			return
		except ValueError:
			pass
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
	if path_prefix in dosareSkinStraine:
		# parametrii temelor externe pe care imaginea nu ii foloseste (culori, texte) nu sunt erori
		skinNotice("parameter %s=\"%s\" of the theme not used here" % (name, value))
		return
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
		if attrib in ("pixmap", "backgroundPixmap", "selectionPixmap") or attrib in POZE_BARA or attrib in POZE_PISTA:
			value = resolveSkinImage(value, skin_path_prefix)
		elif attrib in ("pointer", "seek_pointer", "seekPointer"):
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
# <windowstyle><color name="...">: numele din skin-urile straine -> numele culorilor eWindowStyleSkinned de la noi
CULORI_STIL_NUME = {"Foreground": "LabelForeground", "ListboxBackgroundSelected": "ListboxSelectedBackground",
	"ListboxForegroundSelected": "ListboxSelectedForeground", "ListboxBackgroundMarked": "ListboxMarkedBackground",
	"ListboxForegroundMarked": "ListboxMarkedForeground", "ListboxBackgroundMarkedSelected": "ListboxMarkedAndSelectedBackground",
	"ListboxForegroundMarkedSelected": "ListboxMarkedAndSelectedForeground"}
# poza partii care se misca a barei de derulare din liste, cu numele din skin-urile straine
POZE_BARA = ("scrollbarSliderPicture", "scrollbarForegroundPixmap", "scrollbarSliderPixmap", "sliderPixmap")
# poza de sub bara (pista), cu numele din skin-urile straine
POZE_PISTA = ("scrollbarBackgroundPicture", "scrollbarBackgroundPixmap", "scrollbarbackgroundPixmap")
# scale/scaleFlags din skin-urile straine -> bitii lui ePixmap.setScale (lib/gui/epixmap.h): 1 intinsa, 2 proportiile
# pastrate (incape), 4 umple, 8 nescalata; aliniere 16 centru / 32 dreapta pe orizontala, 64 centru / 128 jos pe verticala
_SC_ASPECT, _SC_UMPLE, _SC_MUTA = 2, 4, 8
_SC_ORIZ = {"left": 0, "center": 16, "middle": 16, "right": 32}
_SC_VERT = {"top": 0, "center": 64, "middle": 64, "bottom": 128}

def parseScaleImagine(value):
	"""valoarea lui scale/scaleFlags -> bitii pentru ePixmap.setScale; ValueError pentru un nume necunoscut"""
	v = value.strip()
	if v.isdigit():
		# un numar (skin-urile vechi si ale noastre: scale="1", "2"...): 0 = cum e, orice alt numar = intinsa, ca inainte
		return 1 if int(v) else 0
	fix = {"0": 0, "none": 0, "off": 0, "1": 1, "scale": 1, "stretch": 1, "keepAspect": _SC_ASPECT, "scaleKeepAspect": _SC_ASPECT,
		"on": _SC_ASPECT, "aspect": _SC_ASPECT, "center": _SC_MUTA | 16 | 64, "width": _SC_ASPECT | 16 | 64,
		"height": _SC_ASPECT | 16 | 64, "fill": _SC_UMPLE | 16 | 64}
	if v in fix:
		return fix[v]
	for prefix, baza in (("scale", _SC_ASPECT), ("move", _SC_MUTA), ("", _SC_ASPECT)):
		if not v.startswith(prefix):
			continue
		rest = v[len(prefix):]
		if rest in ("Center", "Middle", "Scaled"):
			return baza | 16 | 64
		# leftTop, centerScaled, scaleRightBottom, moveMiddleTop...: orizontala apoi verticala
		m = re.match(r'^(left|center|middle|right)(Top|Center|Middle|Bottom|Scaled)$', rest[:1].lower() + rest[1:])
		if m:
			oriz, vert = m.group(1), m.group(2).lower()
			return baza | _SC_ORIZ[oriz] | (64 if vert == "scaled" else _SC_VERT[vert])
	raise ValueError("scale \"%s\" necunoscut" % value)
ADEVARAT = frozenset(("1", "true", "yes", "on", "enabled"))

def parsePadding(value):
	"""padding/textPadding din skin-urile straine: "a" (toate), "a,b" (stanga/dreapta, sus/jos) sau "a,b,c,d" (stanga,
	sus, dreapta, jos) -> 4 numere ca text; ValueError pentru alta forma"""
	parti = [str(int(p.strip())) for p in value.split(",")]
	if len(parti) in (1, 2):
		parti = (parti * 4)[:4]
	if len(parti) != 4:
		raise ValueError("padding \"%s\" trebuie sa aiba 1, 2 sau 4 numere" % value)
	return parti
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
			guiObject.move(pozitieFereastra(guiObject, desktop, value, scale) if isinstance(value, _PozitieFereastra)
				else parsePosition(value, scale, desktop, guiObject.csize()))
		elif attrib == 'size':
			guiObject.resize(parseSize(value, scale))
		elif attrib == 'title':
			guiObject.setTitle(_(value))
		elif attrib == 'text':
			guiObject.setText(_(value))
		elif attrib == 'font':
			guiObject.setFont(parseFont(value, scale))
		elif attrib == 'headerFont' and hasattr(guiObject, "setHeaderFont"):
			# lista de setari in skin-urile straine: fontul randurilor de titlu (fara valoare)
			guiObject.setHeaderFont(parseFont(value, scale))
		elif attrib == 'entryFont' and hasattr(guiObject, "setSecondFont"):
			# lista de setari in skin-urile straine: fontul randurilor (stanga); valueFont e al valorilor
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
		elif attrib in ("alphatest", "alphaTest"): # used by ePixmap; alphaTest = numele din skin-urile straine
			guiObject.setAlphatest(ALPHATEST[value])
		elif attrib in ("scale", "scaleFlags"):
			# skin-urile straine: "0"/"none"/"off" = imaginea cum e; "1"/"scale"/"stretch" = intinsa pe tot elementul;
			# keepAspect, centerScaled, leftTop... = cu proportiile pastrate si aliniata; "center"/"move..." = nescalata,
			# aliniata; "fill" = umple elementul (ce iese se taie). Inainte orice valoare, chiar si "0", o intindea.
			guiObject.setScale(parseScaleImagine(value))
		elif attrib == "orientation": # used by eSlider
			name, swapped = ORIENTATION[value]
			guiObject.setOrientation(getattr(guiObject, name), swapped)
		elif attrib in ("valign", "verticalAlignment", "vAlign"):
			# verticalAlignment/vAlign: numele noi din skin-urile straine; "middle" = center
			guiObject.setVAlign({ "top": guiObject.alignTop, "center": guiObject.alignCenter, "middle": guiObject.alignCenter, "bottom": guiObject.alignBottom }[value.strip()])
		elif attrib in ("halign", "horizontalAlignment", "hAlign"):
			guiObject.setHAlign({ "left": guiObject.alignLeft, "center": guiObject.alignCenter, "right": guiObject.alignRight, "block": guiObject.alignBlock }[value.strip()])
		elif attrib == "flags":
			for f in value.split(','):
				f = f.strip()
				if hasattr(eWindow, f):
					guiObject.setFlag(getattr(eWindow, f))
				elif f == "wfBorder":
					# skin-urile straine: fereastra cu rama, adica ce face si fara steag
					pass
				else:
					skinWarning("unknown window flag %s" % f)
		elif attrib == "backgroundColor":
			value = gradients.get(value.strip(), value)
			if ',' in value and hasattr(guiObject, "setBackgroundGradient"):
				# skin-urile straine: o culoare cu virgula e un degrade. Prima culoare ramane fundalul simplu (listele si
				# ferestrele nu deseneaza degradeul), degradeul se deseneaza peste ea pe etichete si pe celelalte elemente.
				guiObject.setBackgroundColor(parseColor(value.split(',')[0].strip()))
				guiObject.setBackgroundGradient(*parseGradient(value))
			else:
				guiObject.setBackgroundColor(parseColor(value))
		elif attrib == "backgroundGradient" and hasattr(guiObject, "setBackgroundGradient"):
			guiObject.setBackgroundGradient(*parseGradient(value))
		elif attrib == "backgroundColorSelected":
			guiObject.setBackgroundColorSelected(parseColor(value))
		elif attrib == "foregroundColor":
			value = gradients.get(value.strip(), value)
			if ',' in value and hasattr(guiObject, "setForegroundGradient"):
				# bara de progres din skin-urile straine: degradeul in foregroundColor; prima culoare cand degradeurile sunt oprite
				culori, vertical = parseForegroundGradient(value)
				guiObject.setForegroundColor(culori[0])
				guiObject.setForegroundGradient(*(culori + [vertical]))
			else:
				guiObject.setForegroundColor(parseColor(value))
		elif attrib == "foregroundGradient" and hasattr(guiObject, "setForegroundGradient"):
			culori, vertical = parseForegroundGradient(value)
			guiObject.setForegroundGradient(*(culori + [vertical]))
		elif attrib == "foregroundGradient" and hasattr(guiObject, "setForegroundColor"):
			# Widgeturile vechi pot folosi prima culoare.
			guiObject.setForegroundColor(parseForegroundGradient(value)[0][0])
		elif attrib in ("itemCornerRadius", "itemCornerRadiusSelected") and hasattr(guiObject, "setItemCornerRadius"):
			# randurile listelor in skin-urile straine: colturile rotunjite ale randului (Selected = al celui ales)
			factor = min(scale[0][0] / float(scale[0][1]), scale[1][0] / float(scale[1][1]))
			raza, colturi = parseRadius(value)
			getattr(guiObject, "set" + attrib[0].upper() + attrib[1:])(max(0, int(round(raza * factor))), colturi)
		elif attrib in ("itemGradient", "itemGradientSelected") and hasattr(guiObject, "setItemGradient"):
			# degradeul din spatele randului (Selected = al celui ales); forma ca la backgroundColor cu virgula
			getattr(guiObject, "set" + attrib[0].upper() + attrib[1:])(*parseGradient(value))
		elif attrib == "itemSpacing" and hasattr(guiObject, "setItemSpacing"):
			# spatiul dintre elementele listei (x, y; un singur numar = amandoua); "0,0" = lista ca pana acum
			parti = [int(v) for v in value.split(",")]
			x, y = (parti * 2)[:2]
			guiObject.setItemSpacing(ePoint(x * scale[0][0] // scale[0][1], y * scale[1][0] // scale[1][1]))
		elif attrib == "itemSpacing" and all(int(p) == 0 for p in value.split(",")):
			# o imagine fara setItemSpacing: "0,0" e chiar ce face lista
			pass
		elif attrib == "listOrientation" and hasattr(guiObject, "setOrientation") and hasattr(guiObject, "orGrid"):
			# listele orizontale si in grila ale skin-urilor straine (vertical = ca pana acum)
			guiObject.setOrientation({"vertical": guiObject.orVertical, "horizontal": guiObject.orHorizontal,
				"grid": guiObject.orGrid}[value.strip()])
		elif attrib == "animationMode":
			# animatia ferestrei la deschidere/inchidere, cu valorile din OE-Alliance (Components/HdsAnimatiiFerestre.py);
			# pe elementele care nu sunt ferestre nu inseamna nimic
			if hasattr(guiObject, "setAnimationMode"):
				guiObject.setAnimationMode(parseAnimationMode(value))
		elif attrib == "scrollbarScroll" and hasattr(guiObject, "setScrollMargin"):
			# "byLine": lista se muta rand cu rand (la noi: cu un rand vazut dincolo de cel ales); "byPage": pe pagini, ca acum
			guiObject.setScrollMargin(1 if value.strip() == "byLine" else 0)
		elif attrib == "separatorLineColor" and hasattr(guiObject, "setSeparatorColor"):
			# linia dintre randurile listei (skin-urile straine)
			guiObject.setSeparatorColor(parseColor(value))
		elif attrib == "separatorLineSize" and hasattr(guiObject, "setSeparatorSize"):
			guiObject.setSeparatorSize(int(value) * scale[1][0] // scale[1][1])
		elif attrib == "spacingColor" and hasattr(guiObject, "setSpacingColor"):
			# culoarea spatiilor dintre elementele listei (cu itemSpacing)
			guiObject.setSpacingColor(parseColor(value))
		elif attrib == "itemWidth" and hasattr(guiObject, "setItemWidth"):
			guiObject.setItemWidth(int(value) * scale[0][0] // scale[0][1])
		elif attrib == "itemAlignment" and hasattr(guiObject, "setItemAlignment"):
			# unde sta blocul elementelor cand e mai mic decat lista; justify = spatiile cresc pana o umplu
			v = value.strip()
			v = {"default": "leftTop", "center": "centerMiddle", "justify": "justifyFull"}.get(v, v)
			guiObject.setItemAlignment(getattr(guiObject, "itemAlign" + v[0].upper() + v[1:]))
		elif attrib == "cornerRadius" and hasattr(guiObject, "setCornerRadius"):
			factor = min(scale[0][0] / float(scale[0][1]), scale[1][0] / float(scale[1][1]))
			raza, colturi = parseRadius(value)
			guiObject.setCornerRadius(max(0, int(round(raza * factor))))
			# "20;top": numai colturile alese; toate (15) e chiar ce face setCornerRadius singur
			if colturi != 15 and hasattr(guiObject, "setCornerEdges"):
				guiObject.setCornerEdges(colturi)
		elif attrib == "foregroundColorSelected":
			guiObject.setForegroundColorSelected(parseColor(value))
		elif attrib == "shadowColor":
			guiObject.setShadowColor(parseColor(value))
		elif attrib == "selectionDisabled":
			guiObject.setSelectionEnable(0)
		elif attrib == "selection":
			# skin-urile straine: selection="0"/"false" = fara bara de alegere
			guiObject.setSelectionEnable(int(value.strip().lower() in ADEVARAT))
		elif attrib == "transparent":
			# skin-urile straine scriu si "yes"/"true"/"on"
			v = value.strip().lower()
			guiObject.setTransparent(int(v) if v.isdigit() else int(v in ADEVARAT))
		elif attrib == "borderColor" and (hasattr(guiObject, "setBorderColor") or not hasattr(guiObject, "setWidgetBorderColor")):
			guiObject.setBorderColor(parseColor(value))
		elif attrib == "borderWidth" and (hasattr(guiObject, "setBorderWidth") or not hasattr(guiObject, "setWidgetBorderWidth")):
			guiObject.setBorderWidth(int(value))
		elif attrib in ("borderColor", "widgetBorderColor") and hasattr(guiObject, "setWidgetBorderColor"):
			# chenarul elementului (skin-urile straine: widgetBorder*; pe liste si alte elemente fara chenar propriu si
			# borderColor/borderWidth, ca acolo); pe etichete borderColor ramane conturul textului
			guiObject.setWidgetBorderColor(parseColor(value))
		elif attrib in ("borderWidth", "widgetBorderWidth") and hasattr(guiObject, "setWidgetBorderWidth"):
			guiObject.setWidgetBorderWidth(int(value))
		elif attrib == "underline" and hasattr(guiObject, "setUnderline"):
			# ghidul recipes/underline: 1/yes/true/on/enabled/underline = subliniat
			guiObject.setUnderline(int(value.strip().lower() in ADEVARAT or value.strip().lower() == "underline"))
		elif attrib == "fontScale" and hasattr(guiObject, "setFontScale"):
			# skin-urile straine: "size[;limita]" sau "width[;limita]" (limita implicita -4: cel mult 4 puncte mai mic):
			# textul prea lat pentru eticheta se scrie cu litere mai mici, numai unde tema cere asta
			fel, sep, limita = value.partition(";")
			limita = int(limita) if sep and limita.strip() else -4
			guiObject.setFontScale({"size": 1, "width": 2}[fel.strip()], limita * scale[1][0] // scale[1][1])
		elif attrib == "alphaBlend" and hasattr(guiObject, "setWidgetAlphaBlend"):
			# alphaBlend="1": culoarea de fundal cu transparenta se amesteca cu fundalul de dedesubt
			guiObject.setWidgetAlphaBlend(int(value.strip().lower() in ADEVARAT))
		elif attrib == "textBorderColor" and hasattr(guiObject, "setTextBorderColor"):
			# conturul textului cu numele nou al skin-urilor straine (pe etichete, borderColor e acelasi lucru)
			guiObject.setTextBorderColor(parseColor(value))
		elif attrib == "textBorderWidth" and hasattr(guiObject, "setTextBorderWidth"):
			guiObject.setTextBorderWidth(int(value))
		elif attrib == "scrollbarMode":
			# skin-urile straine: showOnDemandShrink (la noi lista isi strange singura coloana din dreapta) si barele din
			# stanga/sus (showLeftOnDemand, showLeftAlways, showLeft, showTopOnDemand, showTopAlways): la noi bara e in dreapta
			v = value.strip()
			mod = { "showOnDemand": "showOnDemand", "showOnDemandShrink": "showOnDemand", "showLeftOnDemand": "showOnDemand",
				"showLeft": "showOnDemand", "showTopOnDemand": "showOnDemand", "showAlways": "showAlways",
				"showLeftAlways": "showAlways", "showTopAlways": "showAlways", "showNever": "showNever" }[v]
			guiObject.setScrollbarMode(getattr(guiObject, mod))
		elif attrib in ("scrollbarForegroundColor", "scrollbarSliderForegroundColor") and hasattr(guiObject, "setScrollbarForegroundColor"):
			# bara de derulare a listelor, numele din skin-urile straine (cele vechi scrollbarSlider* si cele noi)
			guiObject.setScrollbarForegroundColor(parseColor(value))
		elif attrib in POZE_BARA and hasattr(guiObject, "setScrollbarForegroundPixmap"):
			guiObject.setScrollbarForegroundPixmap(loadPixmap(value, desktop))
		elif attrib in POZE_PISTA and hasattr(guiObject, "setScrollbarBackgroundPixmap"):
			guiObject.setScrollbarBackgroundPixmap(loadPixmap(value, desktop))
		elif attrib == "scrollbarBackgroundColor" and hasattr(guiObject, "setScrollbarBackgroundColor"):
			guiObject.setScrollbarBackgroundColor(parseColor(value))
		elif attrib in ("scrollbarBorderColor", "scrollbarSliderBorderColor") and hasattr(guiObject, "setScrollbarBorderColor"):
			guiObject.setScrollbarBorderColor(parseColor(value))
		elif attrib == "scrollbarBorderWidth" and hasattr(guiObject, "setScrollbarSliderBorderWidth"):
			guiObject.setScrollbarSliderBorderWidth(int(value))
		elif attrib == "scrollbarRadius" and hasattr(guiObject, "setScrollbarRadius"):
			guiObject.setScrollbarRadius(parseRadius(value)[0])
		elif attrib == "scrollbarOffset" and hasattr(guiObject, "setScrollbarOffset"):
			guiObject.setScrollbarOffset(int(value))
		elif attrib == "scrollbarWidth":
			# HDSatelit 0.7.4: latimea barei de derulare din tema (inainte primita si ignorata)
			guiObject.setScrollbarWidth(parseScale(value) * scale[0][0] // scale[0][1])
		elif attrib == "scrollbarSliderBorderWidth":
			guiObject.setScrollbarSliderBorderWidth(int(value))
		elif attrib == "enableWrapAround":
			guiObject.setWrapAround(value.strip().lower() not in ("0", "false", "off", "no"))
		elif attrib in ("pointer", "seek_pointer", "seekPointer"):
			(name, pos) = value.split(':')
			pos = parsePosition(pos, scale)
			ptr = loadPixmap(name, desktop)
			guiObject.setPointer(0 if attrib == "pointer" else 1, ptr, pos)
		elif attrib == 'shadowOffset':
			guiObject.setShadowOffset(parsePosition(value, scale))
		elif attrib == 'noWrap':
			guiObject.setNoWrap(int(value) if value.isdigit() else 1)
		elif attrib == 'wrap':
			# skin-urile straine: wrap="1"/"wrap" = randuri multe; "0"/"noWrap"/"ellipsis" = un singur rand (la noi textul
			# prea lung pe un rand se deruleaza, in loc sa fie taiat cu "...")
			v = value.strip()
			guiObject.setNoWrap(0 if v == "wrap" or v.lower() in ADEVARAT else 1)
		elif attrib == 'textOffset' and not hasattr(guiObject, "setTextOffset") and hasattr(guiObject, "setPadding"):
			# skin-urile straine: textOffset pe etichete e acelasi lucru cu padding (x stanga si dreapta, y sus si jos)
			x, y = [int(v) for v in parsePadding(value)[:2]]
			sx, sy = scale
			guiObject.setPadding(x * sx[0] // sx[1], y * sy[0] // sy[1], x * sx[0] // sx[1], y * sy[0] // sy[1])
		elif attrib == 'textOffset':
			guiObject.setTextOffset(parsePosition(value, scale))
		elif attrib in ('padding', 'textPadding') and hasattr(guiObject, "setTextOffset"):
			# skin-urile straine, la liste: "stanga,sus[,dreapta,jos]" (sau un numar pentru toate); la noi lista stie
			# numai departarea textului de stanga si de sus
			guiObject.setTextOffset(parsePosition(",".join(parsePadding(value)[:2]), scale))
		elif attrib in ('padding', 'textPadding') and hasattr(guiObject, "setPadding"):
			# etichetele: textul la departarea data de margini (stanga, sus, dreapta, jos), fundalul pe tot elementul
			l, t, r, b = [int(v) for v in parsePadding(value)]
			sx, sy = scale
			guiObject.setPadding(l * sx[0] // sx[1], t * sy[0] // sy[1], r * sx[0] // sx[1], b * sy[0] // sy[1])
		elif attrib in ('secondfont', 'secondFont', 'valueFont'):
			# valueFont/secondFont: numele noi ale fontului valorilor din lista de setari
			guiObject.setSecondFont(parseFont(value, scale))
		elif attrib == 'scrollText':
			# skin-urile straine: derularea textului prea lung; la noi eticheta il deruleaza singura (eDerulare)
			pass
		elif attrib == 'id':
			pass
		elif attrib not in _reportedAttributes:
			# attributes of newer skins that this image does not draw yet: reported once, never fatal
			_reportedAttributes.add(attrib)
			print("[Skin] attribute %s is not supported yet (first seen on %s)" % (attrib, guiObject.__class__.__name__))
	except Exception as e:
		skinWarning("%s: attribute %s=\"%s\" not applied (%s)" % (guiObject.__class__.__name__, attrib, value, e))

def applyAllAttributes(guiObject, desktop, attributes, scale):
	# position dupa size, ca la ecran (GUISkin.applySkin): "center" se socoteste cu marimea elementului, iar pluginurile
	# scriu des position inaintea lui size; inainte de resize marimea e (-1,-1) si elementul pleca de la mijlocul ecranului.
	# Ordinea celorlalte atribute ramane (sortare stabila); o pozitie cu numere iese la fel in orice ordine.
	for (attrib, value) in sorted(attributes, key=lambda a: a[0] == "position"):
		applySingleAttribute(guiObject, desktop, attrib, value, scale)

def resolveFontFile(filename, path_prefix):
	for candidate in (path.join(path_prefix or "", filename), resolveFilename(SCOPE_FONTS, filename, path_prefix=path_prefix), resolveFilename(SCOPE_CURRENT_SKIN, filename)):
		if candidate and fileExists(candidate):
			return candidate
	return None

def _fontTema(resolved_font, filename, name):
	"""tema externa: un fisier care nu e font ar opri enigma2 din cod nativ, deci nu ajunge la addFont; un font lipsa sau
	stricat al carui nume nu l-a dat deja HDSatelit ia un font al imaginii cu acelasi rol. Calea de folosit sau None."""
	T = _Tema()
	if resolved_font is not None and T.fontBun(resolved_font):
		return resolved_font
	skinNotice("font %s (%s) of the theme is missing or not a font" % (filename, name))
	if T.fontDinImagine(name, [x for x in dom_skins if x[0] not in dosareSkinStraine]):
		return None
	return T.fontRezerva(name, resolveFilename(SCOPE_FONTS, ""))

def _cuFactor(atribute):
	"""get pentru atributele unui element din tema, cu expresiile cu f ("Regular;20*f") socotite"""
	valori = _Tema().valoareCuFactor
	def citeste(nume, implicit = None):
		v = atribute.get(nume)
		return valori(v) if v else (implicit if v is None else v)
	return citeste

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
	dinTema = path_prefix in dosareSkinStraine

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
				if value and "," in value:
					gradients[name] = value
					colorNames[name] = parseColor(value.split(",")[0].strip())
				else:
					gradients.pop(name, None)
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
				if dinTema:
					resolved_font = _fontTema(resolved_font, filename, name)
					if resolved_font is None:
						continue
				if resolved_font is None:
					skinWarning("font file %s (%s) not found" % (filename, name))
					continue
				addFont(resolved_font, name, scale, get_attr("replacement") and True or False)
			except Exception as e:
				skinWarning("font %s: %s" % (name, e))
		for alias in c.findall("alias"):
			get_attr = alias.attrib.get
			if dinTema:
				get_attr = _cuFactor(alias.attrib)
			try:
				size, height = int(get_attr("size")), int(get_attr("height") or 0)
				if scara is not None:
					size, height = _marime(size, scara.sf), _marime(height, scara.sy)
				fonts[get_attr("name")] = (get_attr("font"), size, height)
				latime = int(get_attr("width") or 0)
				if scara is not None and latime:
					latime = _marime(latime, scara.sx)
				latimiFont[get_attr("name")] = latime
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
			rama = {}

			# defaults
			font = gFont("Regular", 20)
			offset = eSize(20, 5)
			for title in windowstyle.findall("title"):
				get_attr = title.attrib.get
				if dinTema:
					get_attr = _cuFactor(title.attrib)
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
						if bsName == "bsWindow":
							try:
								m = png.size()
								w, h = int(m.width()), int(m.height())
								for parte in ("bpTopLeft", "bpTop", "bpTopRight", "bpLeft", "bpRight", "bpBottomLeft", "bpBottom", "bpBottomRight"):
									if bpName in (parte, "bpAll"):
										rama[parte] = (w, h)
							except (AttributeError, TypeError, ValueError):
								pass
					except Exception as e:
						skinWarning("borderset %s/%s: %s" % (bsName, bpName, e))

			for color in windowstyle.findall("color"):
				get_attr = color.attrib.get
				colorType = get_attr("name")
				# skin-urile straine: numele noi ale culorilor ferestrei (ListboxBackgroundSelected...), puse pe ale noastre
				colorType = CULORI_STIL_NUME.get(colorType, colorType)
				try:
					style.setColor(getattr(eWindowStyleSkinned, "col" + colorType), parseColor(get_attr("color")))
				except Exception as e:
					skinWarning("window style color %s: %s" % (colorType, e))

			eWindowStyleManager.getInstance().setStyle(id, style)
			_rameFerestre[id] = (rama.get("bpLeft", (0, 0))[0],
				max(rama.get(p, (0, 0))[1] for p in ("bpTopLeft", "bpTop", "bpTopRight")),
				rama.get("bpRight", (0, 0))[0],
				max(rama.get(p, (0, 0))[1] for p in ("bpBottomLeft", "bpBottom", "bpBottomRight")))
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
	# tema externa: numele pe care le importa fisierele aduse de teme si de extensiile lor, inainte sa se incarce extensiile
	if dosareSkinStraine:
		_Tema().puneNumeLipsa(globals())

def lookupScreen(name, style_id, numaiHds=False):
	for (path, skin) in dom_skins:
		if numaiHds and not esteDinHds(path):
			continue
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

def lookupScreenTema(name, style_id):
	"""Ca lookupScreen, numai in tema externa"""
	for (p, radacina) in dom_skins:
		if p not in dosareSkinStraine:
			continue
		for x in radacina.findall("screen"):
			if x.attrib.get('name', '') == name:
				try:
					screen_style_id = int(x.attrib.get('id', '-1'))
				except ValueError:
					screen_style_id = -1
				if screen_style_id == -1 and name.find('ummary') > 0:
					screen_style_id = 1
				if (style_id != 2 and screen_style_id == -1) or screen_style_id == style_id:
					return x, p
	return None, None

def ecranulTemei(screen, names, style_id):
	"""(nume, <screen>, cale) din tema externa pentru un ecran obisnuit al imaginii cu mai multe nume, dintre care pe primul
	il are numai rezerva (ChannelSelection: HdsListaCanale, ChannelSelection; meniul: menu_mainmenu, Menu). Altfel
	HDSatelit/skin.xml, incarcat dupa tema, ar da de fiecare data ecranul nostru. Ecranele Hds* raman ale noastre."""
	if len(names) > 1 and not screen.__class__.__name__.startswith("Hds"):
		for n in names:
			if not n.startswith("Hds"):
				x, p = lookupScreenTema(n, style_id)
				if x is not None:
					return n, x, p
	return None, None, None

def motivRezervaTema(screen, element, style_id):
	"""De ce nu se poate folosi ecranul temei ((fel, detaliu)), inainte sa se construiasca ceva, sau None"""
	try:
		return _Tema().motivEcran(screen, element, lambda n: lookupScreen(n, style_id)[0])
	except Exception as e:
		skinNotice("verificarea ecranului temei: %s" % e)
		return None

# clasele ecranelor care au cazut la deschidere cu ecranul temei: raman pe rezerva pana la repornirea interfetei (mytest.py)
_ecraneFaraTema = set()

def ecranFaraTema(screen):
	_ecraneFaraTema.add(screen.__class__.__name__)

def notaTema(name, cheie, valoare):
	"""raportTema: ce nu s-a putut din tema pentru ecranul `name`"""
	e = raportTema.setdefault(name, {"rezerva": None, "lipsa": []})
	if cheie == "rezerva":
		e["rezerva"] = valoare
	elif valoare not in e["lipsa"] and len(e["lipsa"]) < 20:
		e["lipsa"].append(valoare)

def panouLipsa(element, style_id, visited = None):
	"""Numele primului <panel name="X"/> din element (sau din panourile lui) pe care niciun skin nu-l are; None daca
	toate se gasesc. Fara avertismente: le da expandPanels."""
	if visited is None:
		visited = set()
	for child in element:
		if child.tag != "panel":
			continue
		panel_name = child.attrib.get("name")
		if not panel_name or panel_name in visited:
			continue
		panel, panel_path = lookupScreen(panel_name, style_id)
		if panel is None:
			return panel_name
		lipsa = panouLipsa(panel, style_id, visited | {panel_name})
		if lipsa:
			return lipsa
	return None

def expandPanels(element, skin_path, style_id, screen_name, visited = None, cadru = None):
	"""children of a screen, with every <panel name="X"/> replaced by the children of screen X
	(recursively). Returns (child, skin path of the file the child comes from). `cadru`: numai la ecranele din tema externa, locul
	in care se aseaza panourile fara nume, cu pozitie si marime."""
	if visited is None:
		visited = set()
	children = [ ]
	for child in element:
		if child.tag != "panel":
			children.append((child, skin_path))
			continue
		panel_name = child.attrib.get("name")
		if not panel_name and cadru is not None:
			children += _Tema().panouFaraNume(child, skin_path, cadru, lambda n: lookupScreen(n, style_id))
			continue
		if panel_name and cadru is not None and child.attrib.get("position") and child.attrib.get("size") and panel_name not in visited:
			# panoul cu nume si cu locul lui (skin-urile straine): copiii ecranului numit se aseaza in originea panoului,
			# urmati de copiii scrisi chiar in <panel>
			panel, panel_path = lookupScreen(panel_name, style_id)
			if panel is None:
				skinWarning("%s: panel %s not found" % (screen_name, panel_name))
				continue
			loc = xml.etree.ElementTree.Element("panel", dict((k, v) for k, v in child.attrib.items() if k != "name"))
			loc.extend(list(panel) + list(child))
			children += _Tema().panouFaraNume(loc, panel_path, cadru, lambda n: lookupScreen(n, style_id))
			continue
		if not panel_name or panel_name in visited:
			skinWarning("%s: panel %s skipped (missing name or used in a loop)" % (screen_name, panel_name))
			continue
		panel = None
		# sub o tema externa, ecranele noastre iau panourile noastre, chiar daca tema are unul cu acelasi nume
		if dosareSkinStraine and esteDinHds(skin_path):
			panel, panel_path = lookupScreen(panel_name, style_id, numaiHds=True)
		if panel is None:
			panel, panel_path = lookupScreen(panel_name, style_id)
		if panel is None:
			skinWarning("%s: panel %s not found" % (screen_name, panel_name))
			continue
		children += expandPanels(panel, panel_path, style_id, screen_name, visited | {panel_name}, cadru)
	return children

def widgetIsWanted(screen, get_attr):
	# conditional="a,b": the widget is used only when the screen has all these components
	conditional = get_attr('conditional')
	if conditional and [c for c in conditional.split(',') if c.strip() not in screen]:
		return False
	# excludes="a,b" (OE-Alliance): the widget is NOT used when the screen has any of these components; a skin draws one
	# variant with conditional="x" and the other with excludes="x" (Obsidian-FHD, the menu list with and without menuimage)
	excludes = get_attr('excludes')
	if excludes and [c for c in excludes.split(',') if c.strip() and c.strip() in screen]:
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

# convertoarele imaginii pe care temele externe le folosesc cu tipuri in plus: ecranele din tema primesc clasa cu acelasi nume
# din Components/Converter/HdsConvertoareStraine.py, derivata din cea a imaginii; ecranele imaginii, clasa imaginii neschimbata
CONVERTOARE_STRAINE = frozenset(("ServiceInfo", "EventName", "EventTime", "ClockToText", "ServiceName", "ConditionalShowHide", "TemplatedMultiContent", "FrontendInfo",
	"RdsInfo", "MovieInfo", "TunerInfo"))

def convertorStrain(ctype, clasa):
	try:
		from Components.Converter import HdsConvertoareStraine
		return getattr(HdsConvertoareStraine, ctype, None) or clasa
	except Exception as e:
		skinNotice("convertorul %s pentru temele externe: %s" % (ctype, e))
		return clasa

# HDSatelit 0.7.4: listele desenate dintr-un sablon XML (forma standardului OE-Alliance, folosita de temele scrise pentru el:
# NetworkOverview, NetworkMountsOverview, QuickMenu, PlayerSelectorGrid... si de pluginuri ca FileCommander):
#   <widget source="list" render="Listbox" ...><template name="Default" fonts="Regular;24" itemHeight="50">
#     <mode name="default"><text index="Name" position="0,0" size="400,50" font="0" /></mode></template></widget>
# (sau aceleasi <template> intr-un <templates>). Sursa e o lista (Sources/List) cu numele coloanelor in indexNames.
# Convertorul (Components/Converter/XmlMultiContent.py) se leaga aici, fara <convert>; scara temei (resolution=) e a
# ecranului. Sabloanele listei de canale (component="serviceList") nu sunt pentru o sursa: le citeste registrul de mai jos.
def sabloaneXml(widget):
	"""elementul care tine <template>-urile unui widget (<templates> sau widgetul insusi), sau None"""
	sabloane = widget.find("templates")
	if sabloane is None and widget.find("template") is not None:
		sabloane = widget
	if sabloane is None:
		return None
	if all(t.get("component") for t in sabloane.findall("template")):
		return None
	return sabloane

def _numarAtribut(widget, nume, axa):
	"""itemWidth/itemHeight ale widgetului, apoi latimea/inaltimea din size= cand e un numar; 0 altfel"""
	try:
		return int(widget.get(nume) or 0) or int((widget.get("size") or "").split(",")[axa])
	except (ValueError, IndexError):
		return 0

def convertorSablonXml(widget, source, scara = None):
	"""convertorul XmlMultiContent pentru <template> din widget, legat de sursa (acelasi, daca sursa il are deja), sau None"""
	sabloane = sabloaneXml(widget)
	if sabloane is None:
		return None
	# un sablon care nu poate citi nicio coloana din lista (numai coloane cu nume, pe care lista nu le stie: ecranul nostru nu
	# are contractul ecranului pentru care e scris sablonul, de pilda meniul sub o tema care cere NumberText/Text): ramane
	# forma de dinainte, nu randuri goale. Un singur index numar sau un nume cunoscut ajunge ca sablonul sa se foloseasca.
	indexuri = [x.get("index") for x in sabloane.iter() if x.get("index")]
	nume = set(i for i in indexuri if not i.lstrip("+-").isdigit())
	if indexuri and len(nume) == len(set(indexuri)) and not nume & set(getattr(source, "indexNames", None) or {}):
		skinNotice("lista %s: sablonul cere coloanele %s, lista nu le are; ramane desenul de dinainte" % (widget.get("source"), ", ".join(sorted(nume))))
		return None
	from Components.Converter.XmlMultiContent import XmlMultiContent
	for c in source.downstream_elements:
		if isinstance(c, XmlMultiContent) and c.dom is sabloane:
			return c
	c = XmlMultiContent({"dom": sabloane, "scara": scara, "itemWidth": _numarAtribut(widget, "itemWidth", 0),
		"itemHeight": _numarAtribut(widget, "itemHeight", 1),
		"selectionEnabled": (widget.get("selection") or "1").lower() not in ("0", "false", "no", "off")})
	c.connect(source)
	return c

def readSourceWidget(screen, widget, name, skin_path_prefix, scara = None, strain = False):
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
		if strain and ctype in CONVERTOARE_STRAINE:
			converter_class = convertorStrain(ctype, converter_class)

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
	# lista desenata dintr-un sablon XML (<template> sau <templates> in widget; vezi convertorSablonXml)
	if wrender == "Listbox" and not hasattr(source, "content"):
		c = convertorSablonXml(widget, source, scara)
		if c is not None:
			source = c
	# tema externa: o lista desenata fara convertor (o lista de texte) trece prin StringList, cum cere randatorul imaginii; o bara legata direct
	# de o emisiune arata cat a trecut din ea
	if strain and wrender == "Listbox" and not hasattr(source, "content"):
		from Components.Converter.StringList import StringList
		c = StringList("")
		c.connect(source)
		source = c
	elif strain and wrender == "Progress" and not hasattr(source, "range") and hasattr(source, "event"):
		c = convertorStrain("EventTime", None)("Progress")
		c.connect(source)
		source = c

	renderer = renderer_class() # instantiate renderer
	renderer.connect(source) # connect to source
	attributes = renderer.skinAttributes = [ ]
	collectAttributes(attributes, widget, skin_path_prefix, ignore=('render', 'source', 'conditional', 'excludes', 'objectTypes'))
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
	# tema externa: un nume pe care il are tema trece inaintea unuia pe care il are numai rezerva
	if dosareSkinStraine and not screen.__class__.__name__ in _ecraneFaraTema:
		n, myscreen, path = ecranulTemei(screen, names, style_id)
		if myscreen is not None:
			name = n
	if myscreen is None:
		for n in names:
			myscreen, path = lookupScreen(n, style_id)
			if myscreen is not None:
				# use this name for debug output
				name = n
				break

	# HDSatelit, numai temele externe: un ecran al temei care cere un panou pe care tema nu-l are ramane fara elementele
	# panoului (o tema reala: menu_mainmenu -> panel menulist: meniul fara lista, iar OK cadea in Sources/List). Atunci
	# se ia ecranul HDSatelit pentru unul din nume (Menu), daca il avem; altfel ramane al temei, ca pana acum.
	if myscreen is not None and path is not None and not esteDinHds(path):
		if path in dosareSkinStraine:
			# si cand lipseste lista ecranului sau cea mai mare parte din componente; se hotaraste inainte sa se construiasca
			# ceva, deci nu e nimic de desfacut. Ecranul care a cazut o data cu tema ramane pe rezerva (mytest.py).
			motiv = ("cadere", "") if screen.__class__.__name__ in _ecraneFaraTema else motivRezervaTema(screen, myscreen, style_id)
			if motiv:
				gasit = False
				for n in names:
					alNostru, caleNoastra = lookupScreen(n, style_id, numaiHds=True)
					if alNostru is not None:
						skinWarning("%s: panel %s not found, HDSatelit screen %s used" % (name, motiv[1], n) if motiv[0] == "panou" else
							"%s: %s %s, HDSatelit screen %s used" % (name, motiv[0], motiv[1], n))
						myscreen, path = alNostru, caleNoastra
						gasit = True
						break
				if not gasit and (getattr(screen, "parsedSkin", None) is not None or getattr(screen, "skin", None)):
					# fara ecran al nostru: cel scris in codul ecranului
					skinWarning("%s: %s %s, screen written in the code used" % (name, motiv[0], motiv[1]))
					myscreen, path = None, None
					gasit = True
				if gasit:
					notaTema(name, "rezerva", motiv)
					_Tema().rezervaFolosita(_HdsSkinuri.numeDinValoare(skinPornit) or skinPornit, name, motiv)
		else:
			lipsa = panouLipsa(myscreen, style_id)
			if lipsa:
				for n in names:
					alNostru, caleNoastra = lookupScreen(n, style_id, numaiHds=True)
					if alNostru is not None:
						skinWarning("%s: panel %s not found, HDSatelit screen %s used" % (name, lipsa, n))
						myscreen, path, name = alNostru, caleNoastra, n
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
	fereastra = fereastraPlugin(myscreen, path, desktop, screen.__class__.__module__)
	if fereastra is not None:
		scara = fereastra[0]
	scari = {path: scara}
	# scara ecranului, pentru sabloanele listei de canale (Components/HdsServiceListSablon: aceeasi grila de proiectare)
	screen.hdsScara = scara
	# ecranul nostru sub alt skin ales: si stilul ferestrei HDSatelit (GUISkin.applySkin -> puneStilHds)
	screen.stilHds = scara is not None and scara.fonturi is not None
	strain = path in dosareSkinStraine
	pluginStrain = path is None and (screen.__class__.__module__ or "").startswith("Plugins.") and not modulImagine(screen.__class__.__module__)
	if dosareSkinStraine:
		screen.hdsSursaTema = path

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
	if fereastra is not None:
		screen.skinAttributes = [(a, fereastra[1] if a == "position" else v) for a, v in screen.skinAttributes]
		if not any(a == "position" for a, _v in screen.skinAttributes):
			screen.skinAttributes.append(("position", fereastra[1]))

	screen.additionalWidgets = [ ]
	screen.renderer = [ ]

	if strain:
		s = desktop.size()
		children = expandPanels(myscreen, path, style_id, name, None, _Tema().cadruEcran(myscreen, s.width(), s.height()))
	else:
		# ecranele pluginurilor cu <panel> fara nume sau cu locul lui (position/size): copiii se aseaza in originea
		# panoului, ca in ghidul skin-urilor straine (inainte se pierdeau: "panel None skipped"). Ecranele imaginii nu au.
		children = expandPanels(myscreen, path, style_id, name, None, cadruPanouri(myscreen, desktop))

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
				collectAttributes(attributes, widget, prefix, ignore=('name', 'conditional', 'excludes', 'objectTypes'))
				if sc is not None:
					if wname == "config":
						# lista de setari (eListboxPythonConfigContent) scrie cu "Regular;20" si "Regular;16" cand skinul
						# nu da font si secondfont: numele si marimile acelea trec si ele prin scara
						puse = set(a for a, v in attributes)
						for a, v in (("font", "Regular;20"), ("secondfont", "Regular;16")):
							if a not in puse:
								attributes.append((a, v))
					screen[wname].skinAttributes = sc.atribute(attributes)
			elif wsource and strain and wsource in screen and hasattr(screen[wsource], "GUIcreate") and not hasattr(screen[wsource], "connectDownstream"):
				# tema externa: source= pentru ce la noi e un element al ecranului (o tasta Button in loc de StaticText): atributele merg la el
				attributes = screen[wsource].skinAttributes = [ ]
				collectAttributes(attributes, widget, prefix, ignore=('source', 'render', 'conditional', 'excludes', 'objectTypes'))
			elif wsource:
				# tipurile OE-Alliance in plus ale convertoarelor (ServiceInfo IsHD, EventName Genre...) si pentru pluginurile
				# straine cu skin in cod sub tema HD Satelit, nu numai sub tema externa (propunerea lui OEA3)
				readSourceWidget(screen, widget, name, prefix, sc, strain or pluginStrain)
			elif get_attr('addon'):
				# addon-urile de tema OE-Alliance (Components/Addons: Pager, ScreenHeader...; lotul TOT): vezi widgetAddon()
				widgetAddon(screen, widget, name, prefix, sc)
			else:
				raise SkinError("widget has no name and no source")
		except Exception as e:
			skinWarning("%s/%s: %s" % (name, wname or wsource, e))
			if strain:
				notaTema(name, "lipsa", str(e)[:120])

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
			elif w_tag in ("eRectangle", "rectangle"):
				# skin-urile straine: un dreptunghi plin (culoare, degrade, colturi rotunjite); la noi o eticheta fara text
				w.widget = eLabel
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

	if strain or areRelative(screen):
		# tema externa aleasa, sau ecranul unui plugin scris pentru imaginile din care vin pluginurile straine
		# (position="fill", "e-10,c-50", "50%,10", "left"/"top" cu size="*,40"...): numerele, fata de ecran
		metriciFont(screen, name)
		rezolvaEcranTema(screen, desktop, name)
	centreazaElemente(screen, desktop, name)

def cadruPanouri(element, desktop):
	"""locul copiilor (0, 0, latime, inaltime) cand ecranul are un <panel> fara nume sau cu position/size; altfel None.
	Latimea si inaltimea sunt in grila ecranului (resolution=, daca o are; altfel ecranul televizorului)."""
	if not any(c.tag == "panel" and (not c.attrib.get("name") or c.attrib.get("position") or c.attrib.get("size")) for c in element):
		return None
	s = desktop.size()
	grila = rezolutieAtribut(element.attrib.get("resolution")) or (s.width(), s.height())
	return _Tema().cadruEcran(element, grila[0], grila[1])

_RX_WH = re.compile(r'(?<![A-Za-z_])(\d*)\s*\*?\s*([wh])(?![A-Za-z_])')

def _cuMetrici(v, alias):
	"""'10w,2h' (skin-urile straine): w = latimea unui caracter, h = inaltimea randului aliasului de font (implicit Body),
	ca numere; fara w/h, valoarea cum e"""
	if not isinstance(v, str) or not _RX_WH.search(v):
		return v
	nume = alias if alias in fonts else "Body"
	if nume not in fonts:
		return v
	marimi = {"w": latimiFont.get(nume, 0), "h": fonts[nume][2]}
	return _RX_WH.sub(lambda m: "(%s*%d)" % (m.group(1) or "1", marimi[m.group(2)]), v)

def metriciFont(screen, name):
	"""w si h din position/size (cu fontul elementului, cand e un alias), inainte de rezolvarea pozitiilor relative"""
	try:
		for x in [screen] + list(screen.renderer) + list(screen.additionalWidgets) + list(screen.values()):
			atribute = getattr(x, "skinAttributes", None)
			if not atribute or not any(a in ("position", "size") and isinstance(v, str) and _RX_WH.search(v) for a, v in atribute):
				continue
			alias = dict(atribute).get("font")
			rez = []
			for a, v in atribute:
				if a in ("position", "size") and isinstance(v, str):
					parti = [_cuMetrici(p, alias) for p in v.split(",")]
					parti = [str(_Tema().calculeaza(p) if _Tema().calculeaza(p) is not None else p) for p in parti]
					v = ",".join(parti)
				rez.append((a, v))
			x.skinAttributes = rez
	except Exception as e:
		skinWarning("%s: w/h in pozitii: %s" % (name, e))

def _valoareRelativa(v):
	"""True pentru o pozitie/marime care nu e facuta numai din numere si "center" (fill, e, c, %, *, f, left...)"""
	return isinstance(v, str) and v.replace("center", "").strip(" ,0123456789-") != ""

def areRelative(screen):
	"""True cand ecranul sau un element al lui are pozitii/marimi relative; ecranele imaginii nu au (numai numere si
	"center"), deci la ele nu se schimba nimic si nu se incarca nimic in plus."""
	for x in [screen] + list(screen.renderer) + list(screen.additionalWidgets) + list(screen.values()):
		for a, v in getattr(x, "skinAttributes", None) or ():
			if a in ("position", "size") and _valoareRelativa(v):
				return True
	return False

def centreazaElemente(screen, desktop, name):
	"""Pozitia "center" a unui element (widget, ePixmap, eLabel) e fata de ecranul lui: (marimea ecranului - marimea
	elementului) // 2, cel putin 0, cum il asteapta temele si pluginurile facute pentru alte imagini (acolo position si
	size se citesc impreuna, fata de ecran); parsePosition ar centra fata de televizor. Se scrie ca numar, dupa scara si dupa
	pozitiile relative ale temei. Un element fara marime numerica ramane cum e. Elementele imaginii nu folosesc "center",
	deci la ele nu se schimba nimic."""
	try:
		s = desktop.size()
		parinte = rezolutieAtribut(dict(screen.skinAttributes).get("size")) or (s.width(), s.height())
		for x in list(screen.renderer) + list(screen.additionalWidgets) + list(screen.values()):
			atribute = getattr(x, "skinAttributes", None)
			if not atribute or not any(a == "position" and "center" in str(v) for a, v in atribute):
				continue
			marime = rezolutieAtribut(dict(atribute).get("size"))
			if marime is None:
				continue
			def centrat(v):
				parti = v.split(",")
				if len(parti) != 2:
					return v
				# "center" si "center+N"/"center-N" (deplasarea e deja scalata, ca restul valorilor)
				return ",".join(str(centruCuDeplasare(c, m, p)) if centruCuDeplasare(c, m, p) is not None else c
					for c, p, m in zip(parti, parinte, marime))
			x.skinAttributes = [(a, centrat(v) if a == "position" and isinstance(v, str) else v) for a, v in atribute]
	except Exception as e:
		skinWarning("%s: centrarea elementelor: %s" % (name, e))

def rezolvaEcranTema(screen, desktop, name):
	"""Numai ecranele din tema externa: pozitiile si marimile relative (fill, c+N, e-N, N%) si factorul f, intai ale ecranului
	(fata de televizor), apoi ale elementelor lui (fata de ecran)"""
	try:
		T = _Tema()
		s = desktop.size()
		ecran = (s.width(), s.height())
		screen.skinAttributes = T.rezolvaRelative(screen.skinAttributes, ecran[0], ecran[1])
		w, h = T.marimeDinAtribute(screen.skinAttributes, ecran)
		for x in list(screen.renderer) + list(screen.additionalWidgets) + list(screen.values()):
			if getattr(x, "skinAttributes", None):
				x.skinAttributes = T.rezolvaRelative(x.skinAttributes, w, h)
	except Exception as e:
		skinWarning("%s: pozitiile relative: %s" % (name, e))


# ---------------------------------------------------------------- numele cerute de pluginuri
colors = colorNames
GUI_SKIN_ID = 0


class AttributeParser:
	"""Pluginurile intreaba numai hasattr(AttributeParser, "..."); atributele temelor se aplica mai sus, in applySingleAttribute."""
	pass


def getSkinFactor(screen=GUI_SKIN_ID):
	from enigma import getDesktop
	return getDesktop(screen).size().height() / 720.0


def applySkinFactor(*valori):
	factor = getSkinFactor()
	rez = tuple(int(x * factor) if isinstance(x, (int, float)) else x for x in valori)
	return rez[0] if len(rez) == 1 else rez


# HDSatelit: doua nume din skin.py al altor imagini, cerute de pluginurile lor (GraphMultiEPG,
# RemoteControlSelection, PiconCockpit). parseScale: un numar din tema, intreg sau o formula cu f, factorul temei fata de 720.
def parseScale(s):
	try:
		return int(s)
	except (TypeError, ValueError):
		pass
	try:
		return int(eval(str(s), {"__builtins__": {}}, {"f": getSkinFactor()}))
	except Exception as e:
		print("[Skin] parseScale: %r nu se poate calcula: %s" % (s, e))
		return 0


def findSkinScreen(names):
	"""Primul nume din lista pentru care tema are ecran, sau None (atunci pluginul isi da singur skinul)."""
	if not isinstance(names, (list, tuple)):
		names = [names]
	for nume in names:
		if lookupScreen(nume, GUI_SKIN_ID)[0] is not None:
			return nume
	return None


def parseAnimationMode(value):
	# HDSatelit 0.7.4: valorile atributului animationMode din OE-Alliance (0x01 la aratare, 0x10 la ascundere); un numar
	# (zecimal sau 0x..) trece asa cum e; o valoare necunoscuta = oprita
	valoare = value.strip()
	optiuni = {"disable": 0x00, "off": 0x00, "offshow": 0x10, "offhide": 0x01, "onshow": 0x01, "onhide": 0x10,
		"disable_onshow": 0x10, "disable_onhide": 0x01, "on": 0x11, "enable": 0x11}
	if valoare in optiuni:
		return optiuni[valoare]
	try:
		return int(valoare, 0) & 0x11
	except ValueError:
		return 0x00


def parseBoolean(attribute, value):
	return value.lower() in ("1", attribute, "enabled", "on", "true", "yes")


# ------------------------------------------------------- culorile si fonturile listelor din pluginuri
# HDSatelit: pluginurile scrise pentru alt fel de Enigma2 cer skin.TemplatedColors, skin.TemplatedListFonts si skin.componentSizes.
# Culorile vin din culorile cu nume ale skinului curent (rolurile ferestrei nu se copiaza aici: blocul windowstyle ramane neatins);
# pluginurile intreaba daca o cheie exista si au valoarea lor cand lipseste.


class TemplatedColors:
	@property
	def colors(self):
		"""Culorile skinului curent ca intregi ARGB; o cheie lipsa ramane in grija pluginului."""
		rez = { }
		for nume, culoare in colorNames.items():
			try:
				rez[nume] = int(culoare.argb())
			except (AttributeError, TypeError, ValueError):
				pass
		return rez


class TemplatedListFonts:
	SMALLER = "Smaller"
	SMALL = "Small"
	MEDIUM = "Medium"
	BIG = "Big"
	_MARIMI = {SMALLER: 16, SMALL: 18, MEDIUM: 20, BIG: 22}

	def _font(self, rol):
		# Body da fata skinului; randurile fixe ale pluginurilor au nevoie de marimi mai mici.
		fata = "Regular"
		body = fonts.get("Body")
		if isinstance(body, (tuple, list)) and len(body) == 3 and isinstance(body[0], str) and body[0]:
			fata = body[0]
		alias = fonts.get(rol)
		if alias:
			try:
				nume, marime, inaltime = alias
				marime = int(marime)
				if isinstance(nume, str) and nume and marime > 0:
					return nume, marime
			except (TypeError, ValueError, OverflowError):
				pass
		return fata, self._MARIMI.get(rol, self._MARIMI[self.MEDIUM])

	def face(self, rol):
		return self._font(rol)[0]

	def size(self, rol):
		return _hds_scaleaza(self._font(rol)[1])


class _DimensiuniComponente(dict):
	# Nu reinterpretam parameters: pluginurile au valori implicite pentru fiecare dimensiune.
	ITEM_WIDTH = "itemWidth"
	ITEM_HEIGHT = "itemHeight"

	def __missing__(self, nume):
		valori = { }
		self[nume] = valori
		return valori

	def itemHeight(self, nume, implicit):
		try:
			inaltime = int(self[nume].get(self.ITEM_HEIGHT, implicit))
			if inaltime > 0:
				return inaltime
		except (TypeError, ValueError, OverflowError):
			pass
		return implicit


componentSizes = _DimensiuniComponente()

# Numele clasei cerut de pluginuri foloseste aceleasi chei si acelasi registru.
ComponentSizes = _DimensiuniComponente


# Numele OE-Alliance cerute de teme si de pluginurile lor (lotul TOT, 12.11.2026; temele si pluginurile lor de setari le importa).
# Imaginea nu reincarca temele din mers: o tema schimbata se vede dupa repornirea interfetei, iar functiile spun asta in jurnal.
windowStyles = {}  # stilurile de fereastra pe ecran (screenID: argumentele lui loadSingleSkinData), ca in OE-Alliance


def reloadWindowStyles():
	"""Reincarca stilurile de fereastra inregistrate in windowStyles (in imagine, de obicei niciunul)."""
	if not windowStyles:
		print("[Skin] reloadWindowStyles: culorile temei se schimba dupa repornirea interfetei")
	for screenID in list(windowStyles):
		try:
			loadSingleSkinData(*windowStyles[screenID])
		except Exception as e:
			print("[Skin] reloadWindowStyles %s: %s" % (screenID, e))


def reloadSkins():
	"""Imaginea nu reincarca temele din mers (False): schimbarile se vad dupa repornirea interfetei."""
	print("[Skin] reloadSkins: tema se reincarca dupa repornirea interfetei")
	return False


def widgetAddon(screen, widget, name, prefix, sc=None):
	"""<widget addon="Pager" connection="list" .../>: addon-ul de tema OE-Alliance din Components/Addons, legat de elementul
	ecranului numit in connection (lotul TOT, 12.11.2026). Un addon pe care imaginea nu-l are ridica SkinError (elementul
	lipseste si se scrie in jurnal, ca orice componenta lipsa a unei teme)."""
	get_attr = widget.attrib.get
	fel = get_attr('addon')
	legatura = get_attr('connection')
	if not legatura:
		raise SkinError("addon %s fara connection" % fel)
	try:
		clasa = getattr(__import__("Components.Addons." + fel, fromlist=[fel]), fel)
	except (ImportError, AttributeError):
		raise SkinError("addon '%s' not found" % fel)
	baza = "%s_%s_%s_" % (name, fel, legatura)
	i = 0
	while ("%s%d" % (baza, i)) in screen:
		i += 1
	cheie = "%s%d" % (baza, i)
	addon = clasa()
	addon.connectRelatedElement(legatura, screen)
	screen[cheie] = addon
	attributes = addon.skinAttributes = []
	collectAttributes(attributes, widget, prefix, ignore=('addon', 'connection', 'conditional', 'excludes', 'objectTypes'))
	if sc is not None:
		addon.skinAttributes = sc.atribute(attributes)
