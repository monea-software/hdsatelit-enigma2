# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
"""Logica gestionarului de extensii, comuna ecranului de pe televizor (Screens/HdsExtensii.py) si paginii web
/extensii (Plugins/Extensions/HdsWebControl/extensii_web.py). Doar in imaginea HDSatelit.

Datele (catalogul din fisierele opkg, sursele, fisierele .ipk, iesirea opkg pe romaneste) sunt in
Components/HdsPachete.py. Aici sunt cele care stateau in ecran si de care are nevoie si pagina:
 - randurile filelor (Pe receptor, Actualizari, categoriile, Surse, cautarea) si textele fiecarui rand: titlul,
   insigna, detaliile, tastele (actiunile) lui; randul cautarii in retea si fila Din fisier tin de starea cautarii
   fiecarui capat;
 - planurile confirmarilor: intrebarea, randurile, argumentele opkg (instalare, actualizare, stergere, fisier .ipk);
   nota despre sursele externe o scrie fiecare capat din surseExterne();
 - sursele adaugate si sterse de utilizator; fila Surse arata feedurile, nu sursele opkg una cate una (0.6.6): un
   rand "HD Satelit" pentru toate sursele HD Satelit (arhitecturile si canalul de proba
   sunt numai in detalii), un rand "Pluginuri externe" pentru feedul de pe moneasoftware.com
   (Components/HdsPluginuriExterne.py), apoi sursele adaugate de om (si alte surse), fiecare pe randul ei;
 - descarcarea listei (opkg update) si lucrarea opkg (Lucrare: progres, jurnal scurt, raspunsul N la fisierele de
   configurare schimbate, reincarcarea pluginurilor, textele de la sfarsit, oprirea dupa un minut fara raspuns). Cate
   una odata in tot procesul: ce porneste pagina vede si televizorul, si invers. Iesirea opkg intreaga merge in
   /home/root/logs/hds-extensii.log (memoria interna: ramane dupa repornire, o vad Jurnalele sistemului; rotit). O
   lucrare e reusita cand codul opkg e 0 SAU cand toate tintele ei s-au facut (versiunea ceruta instalata, pachetul
   sters): opkg iese cu 255 si cand cade numai configurarea altui pachet din receptor, ramas neconfigurat;
 - catalogul tinut minte pentru pagina (citit din nou numai dupa o schimbare).
opkg porneste numai prin Components/Ipkg.py (lista de argumente, nume verificate, fara shell). Pluginurile
(PluginComponent) si caile se cer numai in functii, ca probele de pe PC sa incarce modulul singur."""
import os
import posixpath       # caile pluginurilor sunt ale receptorului (si in probele de pe PC)
import re
import time

try:
	from Components import HdsPachete as P
except ImportError:  # probe pe PC: modulul incarcat singur, din dosarul Components
	import HdsPachete as P
try:
	from Components import HdsPluginuriImagine as I
except ImportError:  # probe pe PC
	import HdsPluginuriImagine as I
try:
	from Components.Ipkg import IpkgComponent, opkgArguments, opkgProgram
except ImportError:  # probe pe PC
	from Ipkg import IpkgComponent, opkgArguments, opkgProgram
try:
	from Components import HdsTemeSuprascrise as TS
except ImportError:  # probe pe PC
	import HdsTemeSuprascrise as TS

JURNAL_OPKG = P.DOSAR_JURNALE + '/hds-extensii.log'
FARA_RASPUNS_S = 60              # dupa atata timp fara niciun rand de la opkg se poate opri lucrarea

# starea comuna a procesului: ultima descarcare a listei (automata sau ceruta), rezultatul ei, lucrarea curenta
STARE = {'ultima_descarcare': 0, 'descarcare': None, 'lucrare': None}
# descarcarile listei care ruleaza (pornite de ecran sau de pagina, si cele ramase dupa inchiderea ecranului): tinute
# aici pana se termina, altfel colectorul de cicluri putea sterge IpkgComponent, iar destructorul lui
# eConsoleAppContainer omora opkg la jumatatea listei
_descarcari = []
# catalogul paginii web: tinut minte, citit din nou dupa o schimbare (lucrare, lista, sursa) sau cand fisierele opkg
# s-au schimbat de altundeva
_CATALOG = {'catalog': None, 'semn': None, 'vechi': True}


def _jurnal(text):
	print('[HdsExtensii] %s' % text)


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_), fara efect: textul se traduce la folosire."""
	return text


def _t(text):
	"""Traducerea enigma2 (functia _ din builtins), sau textul insusi pe PC."""
	try:
		return _(text)  # noqa: F821
	except NameError:
		return text


def _vecin(nume):
	"""un modul Hds din acelasi dosar (Components): pe receptor din pachet; pe PC din sys.path sau, cand o proba incarca
	acest fisier singur, chiar din dosarul lui"""
	import importlib
	for complet in ('Components.' + nume, nume):
		try:
			return importlib.import_module(complet)
		except ImportError:
			pass
	import importlib.util
	spec = importlib.util.spec_from_file_location(nume, os.path.join(os.path.dirname(os.path.abspath(__file__)), nume + '.py'))
	m = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(m)
	return m


_VECINI = {}


def _X():
	"""Components/HdsPluginuriExterne (feedul pluginurilor externe), incarcat la prima folosire"""
	if 'X' not in _VECINI:
		_VECINI['X'] = _vecin('HdsPluginuriExterne')
	return _VECINI['X']


def _S():
	"""Components/HdsSursaPachet (descarcarea sursei unui plugin), incarcat la prima folosire"""
	if 'S' not in _VECINI:
		_VECINI['S'] = _vecin('HdsSursaPachet')
	return _VECINI['S']


def __getattr__(nume):
	# L.X si L.S pentru ecranul de pe televizor si pagina web (aceleasi module)
	if nume == 'X':
		return _X()
	if nume == 'S':
		return _S()
	raise AttributeError(nume)


# eticheta filei Surse, aceeasi pe televizor si in pagina web (tradusa la folosire)
ETICHETA_SURSE = N_('Surse feeduri')
ETICHETA_FISIERE = N_('Instalează de pe stick')
TEXT_FARA_FISIERE = N_('Pune fișierul .ipk pe stick sau în /tmp prin FTP. '
	'Lista se reface singură când introduci stickul.')
# pluginul din feedul Monea Software care adauga singur mai multe surse; randul despre el apare in Surse feeduri numai
# cand pachetul chiar se poate lua (Eduard, 04.11.2026)
PACHET_FEEDURI = 'enigma2-plugin-extensions-hdsfeeduri'
# feedurile din fila Surse (0.6.6): toate sursele HD Satelit intr-un rand, feedul pluginurilor externe in altul
FEED_HDS = 'hds'
FEED_EXTERN = 'externe'
ETICHETA_EXTERNE = N_('Monea Software (pluginuri externe)')
# textul feedului extern, in detaliile randului lui, pe televizor si in pagina web
TEXT_EXTERNE = N_('Feed întreținut și oferit de Monea Software (moneasoftware.com), care se ocupă de pluginuri și de tot '
	'ce e nevoie pentru ele. Vrei și alte pluginuri aici? Scrie la contact@moneasoftware.com.')
# nota confirmarii si a detaliilor unui pachet din feedul extern (in locul frazei "nu este verificat de HD Satelit", care
# ramane pentru sursele adaugate de om si pentru celelalte surse)
NOTA_EXTERNE = N_('Vine din feedul pluginurilor externe, întreținut de Monea Software (moneasoftware.com).')
# categoriile care nu cer repornirea interfetei dupa instalare (0.6.6: si modulele de acces conditionat, pornite si
# alese din ecranul lor, fara interfata)
FARA_REPORNIRE_INSTALARE = ('extensions', 'picons', 'settings', 'acces')
FARA_REPORNIRE_SCHIMBARE = ('acces',)


# ---------------------------------------------------------------- texte mici

def scurt(text, maxim):
	text = text or ''
	return text if len(text) <= maxim else text[:maxim - 1].rstrip('-_. ') + '…'


def etichetaLoc(cale, retea=False):
	"""de unde e un fisier .ipk: stick, disc, retea sau memoria receptorului (`retea`: gasit la cautarea in retea)"""
	c = cale.lower()
	if retea or c.startswith('/media/net') or c.startswith('/media/autofs') or c.startswith('/autofs'):
		return N_('Rețea')
	if c.startswith('/media/usb') or '/usb' in c:
		return N_('Stick USB')
	if c.startswith('/media/hdd') or c.startswith('/hdd'):
		return N_('Disc')
	if c.startswith('/mnt'):
		return N_('Rețea')
	if c.startswith('/tmp'):
		return N_('Memoria receptorului')
	return N_('Stick sau disc')


def deUnde(cale, retea=False):
	# etichetaLoc da cheia (romaneasca, N_); textul se traduce aici
	return _t({'Stick USB': N_('de pe stick-ul USB'), 'Disc': N_('de pe disc'), 'Rețea': N_('din rețea'),
		'Memoria receptorului': N_('din memoria receptorului')}.get(etichetaLoc(cale, retea), N_('de pe stick sau disc')))


def categoriePlugin(cale):
	c = (cale or '').replace('\\', '/')
	if '/SystemPlugins/' in c:
		return 'systemplugins'
	return 'extensions'


def textVersiuni(p):
	return p.versiune or p.versiune_instalata or ''


def varstaLista(catalog, nume):
	"""de cand e lista descarcata a sursei (azi, 14:32), '' daca nu e"""
	try:
		cale = os.path.join(catalog.configurare.lists_dir, nume)
		if os.path.isfile(cale):
			return P.text_varsta(os.path.getmtime(cale))
	except Exception:
		pass
	return ''


# ---------------------------------------------------------------- sursele

def felFeed(catalog, nume, adresa):
	"""FEED_HDS, FEED_EXTERN sau None (o sursa adaugata de om sau alta sursa: rand separat in fila Surse). O sursa
	adaugata de om ramane a lui, chiar cu adresa unui feed cunoscut (asa o poate sterge)."""
	if catalog.configurare.e_a_utilizatorului(nume):
		return None
	# intai feedul extern: rezerva lui sta pe stb.hdsatelit.com (0.7.4), dar ramane feedul extern, nu cel HD Satelit
	if _X().e_feed_extern(adresa):
		return FEED_EXTERN
	if P.sursa_hdsatelit(adresa):
		return FEED_HDS
	return None


class Feed(object):
	"""un rand din fila Surse care tine mai multe surse opkg (cate una pe arhitectura si canal)"""
	__slots__ = ('id', 'surse')

	def __init__(self, id_, surse):
		self.id = id_
		self.surse = surse              # [(nume, adresa)] in ordinea din configurare

	def nume(self):
		return [n for n, _a in self.surse]


def feeduri(catalog):
	"""[Feed] ale filei Surse, in ordine: HD Satelit, Pluginuri externe (numai cele care au macar o sursa)"""
	grupe = {FEED_HDS: [], FEED_EXTERN: []}
	for nume, adresa in catalog.configurare.surse:
		f = felFeed(catalog, nume, adresa)
		if f is not None:
			grupe[f].append((nume, adresa))
	return [Feed(i, grupe[i]) for i in (FEED_HDS, FEED_EXTERN) if grupe[i]]


def surseSingure(catalog):
	"""sursele care au rand propriu in fila Surse: cele adaugate de om si cele care nu tin de un feed cunoscut"""
	return [(n, a) for n, a in catalog.configurare.surse if felFeed(catalog, n, a) is None]


def numeFeed(f):
	return 'HD Satelit' if f.id == FEED_HDS else _t(ETICHETA_EXTERNE)


def sursa(catalog, nume):
	"""(eticheta scurta, adresa, e HD Satelit) a unei surse din configurare"""
	if not nume:
		return '', '', False
	adresa = catalog.configurare.adresa(nume)
	fel = felFeed(catalog, nume, adresa)
	if fel == FEED_HDS:
		return 'HD Satelit', adresa, True
	if fel == FEED_EXTERN:
		return _t(ETICHETA_EXTERNE), adresa, False
	return nume, adresa, False


def cuSursa(sursa_, text):
	"""randul de sub numele unui pachet: de unde vine, apoi descrierea scurta"""
	if sursa_ and text:
		return '%s · %s' % (sursa_, text)
	return sursa_ or text or ''


def dinFeedulExtern(catalog, p):
	return p is not None and bool(p.sursa) and felFeed(catalog, p.sursa, catalog.configurare.adresa(p.sursa)) == FEED_EXTERN


def sursaPachet(catalog, p):
	if p is None:
		return _t('Imaginea HD Satelit'), '', True
	if p.sursa:
		return sursa(catalog, p.sursa)
	if p.din_imagine:
		return _t('Imaginea HD Satelit'), '', True
	return _t('Alt feed'), '', False


def randSursa(catalog, p):
	s, adresa, hds = sursaPachet(catalog, p)
	if adresa:
		return s + ' (%s)' % P.gazda(adresa), hds
	return s, hds


def surseExterne(catalog, pachete):
	"""[(numele sursei, adresa scurtata sau '')] pentru pachetele din surse externe, fara repetari; fiecare capat isi
	scrie nota din ele. Adresa e scurtata: nota are doua randuri pe televizor."""
	rez = []
	for p in pachete:
		_s, adresa, hds = sursaPachet(catalog, p)
		if not hds and p.sursa and not dinFeedulExtern(catalog, p):
			x = (p.sursa, P._curat(adresa, 70) if adresa else '')
			if x not in rez:
				rez.append(x)
	return rez


def notaFeedExtern(catalog, pachete):
	"""nota pentru pachetele din feedul pluginurilor externe (cand nu e niciunul din alte surse externe), altfel ''"""
	if any(dinFeedulExtern(catalog, p) for p in pachete) and not surseExterne(catalog, pachete):
		return _t(NOTA_EXTERNE)
	return ''


def culoareNota(catalog, pachete):
	"""verde cand totul vine din sursa HD Satelit sau din feedul pluginurilor externe, altfel chihlimbar"""
	if pachete and all(p.sursa and (sursaPachet(catalog, p)[2] or dinFeedulExtern(catalog, p)) for p in pachete):
		return 'bun'
	return 'chihlimbar'


def adaugaSursa(catalog, nume, adresa):
	"""Scrie sursa noua in fisierul utilizatorului (dupa intrebare). None sau textul erorii."""
	motiv = P.verifica_sursa(nume, adresa, catalog.configurare.nume_surse())
	if motiv:
		return motiv
	eroare = P.scrie_surse_utilizator(P.citeste_surse_utilizator() + [(nume, adresa)])
	if eroare:
		return eroare
	_jurnal('sursa adaugata: %s %s' % (nume, adresa))
	catalogVechi()
	return None


def stergeSursa(catalog, nume):
	"""Scoate sursa din fisierul utilizatorului si sterge lista ei descarcata. None sau textul erorii."""
	surse = [s for s in P.citeste_surse_utilizator() if s[0] != nume]
	eroare = P.scrie_surse_utilizator(surse)
	if eroare:
		return eroare
	# lista veche a sursei nu mai foloseste la nimic
	try:
		if P.verifica_sursa(nume, 'http://x') is None:
			cale = os.path.join(catalog.configurare.lists_dir, nume)
			if os.path.isfile(cale):
				os.remove(cale)
	except OSError:
		pass
	_jurnal('sursa stearsa: %s' % nume)
	catalogVechi()
	return None


# ---------------------------------------------------------------- filele si randurile lor

# randurile care numara si se filtreaza ca extensii; 'indisponibil' = ('indisponibil', randul din indisponibile(), pachetul sau None)
RANDURI_CU_PACHET = ('plugin', 'pachet', 'indisponibil')


def pachetPlugin(catalog, plugin):
	cale = getattr(plugin, 'path', None)
	if not cale:
		return None
	return catalog.pachet_pentru_dosar(posixpath.normpath(cale))


def pluginPentru(pluginuri, p, plugins=None):
	"""Pluginul de deschis pentru un pachet instalat: randul lui din Extensii (unulPePlugin), nu o unealta interna a lui din
	meniul extensiilor (AJPanel: „Deschide” pornea File Manager, prima lui intrare din lista comuna)."""
	if not p.dosar_plugin:
		return None
	dosar = posixpath.normpath(p.dosar_plugin)
	ale_lui = [x for x in pluginuri if posixpath.normpath(getattr(x, 'path', '') or '') == dosar]
	return unulPePlugin(ale_lui, plugins)[0] if ale_lui else None


def pluginuriDeDeschis(plugins):
	"""Pluginurile omului cu ecran, aceleasi in Extensii, la albastru si in web. Extensii arata din ele cate un rand pe
	plugin (unulPePlugin)."""
	f = getattr(plugins, 'pluginuriDeDeschis', None)
	return [p for p in f() if not I.pluginImagine(getattr(p, 'path', ''))] if f is not None else []


# PluginDescriptor.WHERE_PLUGINMENU (Plugins/Plugin.py), fara import: probele de pe PC incarca modulul singur
_LISTA_PLUGINURI = 2


def _dosar(plugin):
	cale = getattr(plugin, 'path', None) or ''
	return posixpath.normpath(cale) if isinstance(cale, str) and cale else ''


def _are(plugin, loc):
	try:
		return loc in (getattr(plugin, 'where', None) or ())
	except TypeError:
		return False


def _componenta(plugins):
	"""componenta pluginurilor data, altfel cea a imaginii (None cand nu se poate lua)"""
	if plugins is not None:
		return plugins
	try:
		from Components.PluginComponent import plugins as componenta
		return componenta
	except Exception:
		return None


def unulPePlugin(pluginuri, plugins=None):
	"""Randurile pluginurilor in Extensii (televizor si web), luate din lista comuna (pluginuriDeDeschis): fiecare plugin o
	data, cu intrarile lui din lista pluginurilor (WHERE_PLUGINMENU); pluginul fara asemenea intrare, cu prima lui intrare.
	Pluginurile scrise pentru alte imagini pun in meniul extensiilor si unelte interne (AJPanel: File Manager, Terminal,
	Player Bar si inca cinci, pornite implicit; Pluto TV: „Pluto TV Update”), care din 0.7.1 apareau in Extensii cate un
	rand, ca niste pluginuri separate (JAKITAKI, 08.11 si 10.11.2026). Ele raman la tasta albastra si in pluginul lor.
	Intrarea din meniul extensiilor cu aceeasi functie ca una din lista pluginurilor (geamanul pastrat de lista comuna, de
	pilda la XStreamity) tine locul aceleia. Un plugin cu mai multe intrari in lista pluginurilor (SubsSupport: setarile,
	descarcarea, playerul DVB) le pastreaza pe toate, ca in lista pluginurilor din orice imagine. Ordinea ramane a listei
	comune; un descriptor fara dosar ramane cum e."""
	f = getattr(_componenta(plugins), 'getPlugins', None)
	try:
		din_lista = list(f(_LISTA_PLUGINURI)) if f is not None else []
	except Exception as e:
		_jurnal('lista pluginurilor: %s' % e)
		din_lista = []

	def inLista(p):
		if _are(p, _LISTA_PLUGINURI):
			return True
		d = _dosar(p)
		return any(x == p and _dosar(x) == d for x in din_lista)
	grupe = {}
	for p in pluginuri:
		grupe.setdefault(_dosar(p), []).append(p)
	rez, vazute = [], set()
	for p in pluginuri:
		d = _dosar(p)
		if not d:
			rez.append(p)
		elif d not in vazute:
			vazute.add(d)
			grupa = grupe[d]
			rez.extend([x for x in grupa if inLista(x)] or grupa[:1])
	return rez


# ---------------------------------------------------------------- pachetul instalat fara rand in lista pluginurilor
# (tamiciav7, LinuxSat 164122, 14.11.2026): OK pe EPGImport cu "Show in plugins" = Nu spunea "este instalat si la zi", desi
# pluginul are intrarea lui in meniu (WHERE_MENU). Acum OK deschide intrarea din meniu (si randul spune unde e), pe un modul de
# acces deschide ecranul modulelor (pornire, oprire, repornire), iar la un pachet fara ecran spune la ce foloseste.

# PluginDescriptor.WHERE_MENU (Plugins/Plugin.py), fara import, ca _LISTA_PLUGINURI
_MENIU = 4
MENIU_XML = '/usr/share/enigma2/menu.xml'
_meniuri = {}
# randul ecranului modulelor de acces din menu.xml (entryID cam_setup, in meniul cu id cam_menu)
MENIU_ACCES = 'cam_menu'
RAND_ACCES = N_('Module de acces condiționat')


def meniurile(cale=None):
	"""[(id, drum)] din menu.xml, in ordinea din fisier: id-ul fiecarui meniu (<id val=...>) si titlurile netraduse de la
	"Menu" pana la el. Citit o data; [] cand fisierul lipseste sau e stricat."""
	if cale is None:
		try:
			from Tools.Directories import resolveFilename, SCOPE_SKIN
			cale = resolveFilename(SCOPE_SKIN, 'menu.xml')
		except Exception:
			cale = MENIU_XML
	if cale in _meniuri:
		return _meniuri[cale]
	rez = []
	try:
		import xml.etree.ElementTree as ET

		def mergi(nod, drum):
			for i in nod.findall('id'):
				if i.get('val'):
					rez.append((i.get('val'), drum))
			for m in nod.findall('menu'):
				mergi(m, drum + (m.get('text') or '',))
		radacina = ET.parse(cale).getroot()
		# <menuxml><menu key="mainmenu">...: meniul principal e "Menu", ca in textele noastre (HdsAsistenta.drumMeniu)
		for principal in ([radacina] if radacina.tag == 'menu' else radacina.findall('menu')):
			mergi(principal, (N_('Menu'),))
	except Exception as e:
		_jurnal('meniurile din %s: %s' % (cale, e))
	_meniuri[cale] = rez
	return rez


def drumText(drum):
	""""Meniu > Setări > EPG-Importer", in limba receptorului"""
	return ' > '.join(_t(x) for x in drum if x)


def intrareMeniu(dosar, plugins=None, meniuri=None):
	"""Prima intrare de meniu pusa de pluginul din `dosar` (WHERE_MENU), cautata in meniurile imaginii in ordinea din menu.xml
	si pe id-urile de referinta ale fiecaruia (HdsPluginuriImagine.ID_MENIU_REFERINTA, ca Screens/Menu.py): {'titlu',
	'functie', 'drum'} (drumul pana la intrare, cu ea), sau None. Un plugin care cade pe un id nu strica cautarea."""
	f = getattr(_componenta(plugins), 'getPlugins', None)
	if f is None or not dosar:
		return None
	dosar = posixpath.normpath(dosar)
	try:
		ale_lui = [x for x in f(_MENIU) if _dosar(x) == dosar]
	except Exception as e:
		_jurnal('intrarile de meniu: %s' % e)
		return None
	if not ale_lui:
		return None
	referinte = getattr(I, 'ID_MENIU_REFERINTA', {})
	for ident, drum in (meniurile() if meniuri is None else meniuri):
		for cerut in (ident,) + tuple(referinte.get(ident, ())):
			for x in ale_lui:
				try:
					intrari = x(cerut) or []
				except Exception:
					continue
				for e in intrari:
					try:
						titlu, functie = e[0], e[1]
					except (TypeError, IndexError, KeyError):
						continue
					if callable(functie):
						return {'titlu': str(titlu), 'functie': functie, 'drum': tuple(drum) + (str(titlu),)}
	return None


def drumAcces(meniuri=None):
	"""drumul ecranului modulelor de acces (CamSetup), din menu.xml"""
	for ident, drum in (meniurile() if meniuri is None else meniuri):
		if ident == MENIU_ACCES:
			return tuple(drum) + (RAND_ACCES,)
	return (N_('Menu'), RAND_ACCES)


def folositDe(catalog, p):
	"""titlurile pachetelor instalate care depind de p (cel mult 5, dupa nume)"""
	toate = getattr(catalog, '_toate', None) or {}
	return sorted(set(x.titlu for x in toate.values()
		if x is not p and x.instalat and p.nume in (x.depinde or ())), key=lambda t: t.lower())[:5]


def deschidereFaraPlugin(catalog, p, plugins=None, meniuri=None, texte=True):
	"""Ce face OK pe un pachet instalat care nu are rand in lista pluginurilor (pluginPentru da None), aceeasi pe televizor si
	in web: {'fel': 'meniu', 'titlu', 'functie', 'drum'} (intrarea lui din meniu), {'fel': 'acces', 'drum'} (un modul de
	acces: ecranul modulelor), {'fel': 'fara_ecran', 'text', 'rand'} (la ce foloseste), sau None (pachet neinstalat).
	texte=False (tastele si butoanele fiecarui rand): fara textul pachetului fara ecran, care cauta prin toate pachetele."""
	if p is None or not p.instalat:
		return None
	if p.dosar_plugin:
		m = intrareMeniu(p.dosar_plugin, plugins, meniuri)
		if m is not None:
			m['fel'] = 'meniu'
			return m
	if p.categorie == 'acces':
		return {'fel': 'acces', 'drum': drumAcces(meniuri)}
	if not texte:
		return {'fel': 'fara_ecran'}
	rand = primulRandFaraEcran(catalog, p)
	return {'fel': 'fara_ecran', 'text': textFaraEcran(catalog, p, rand), 'rand': rand}


def textFaraEcran(catalog, p, rand=None):
	"""textul ferestrei de la OK pe un pachet fara ecran (o biblioteca a altor pluginuri, ca MPHelp): ce e, cine il foloseste,
	apoi descrierea din feed"""
	text = rand or primulRandFaraEcran(catalog, p)
	descriere = (p.descriere or p.subtitlu or '').strip()
	return (text + '\n\n' + descriere) if descriere else text


def primulRandFaraEcran(catalog, p):
	lor = folositDe(catalog, p)
	if lor:
		return _t('%s nu are ecran propriu; îl folosesc alte extensii: %s.') % (p.titlu, ', '.join(lor))
	return _t('%s nu are ecran propriu.') % p.titlu


def notaFaraPlugin(d):
	"""randul din detalii (televizor si web) pentru deschidereFaraPlugin: unde se deschide"""
	if d is None:
		return ''
	if d['fel'] == 'meniu':
		return _t('Nu are rând în lista pluginurilor; se deschide din %s.') % drumText(d['drum'])
	if d['fel'] == 'acces':
		return _t('Modul de acces: se pornește, se oprește și se repornește din %s.') % drumText(d['drum'])
	return d.get('rand') or ''


def descriptoriiPluginului(plugin, plugins=None):
	"""Ceilalti descriptori ai aceluiasi plugin (acelasi dosar), intai geamanii (aceeasi functie), pentru icoana randului:
	XStreamity, XKlass, EStalker, BouquetMakerXtream si TV Garden pun icoana numai pe intrarea din lista pluginurilor, iar
	randul din Extensii poate fi geamanul ei din meniul extensiilor, fara icoana."""
	d = _dosar(plugin)
	if not d:
		return []
	toti = [x for x in (getattr(_componenta(plugins), 'pluginList', None) or ()) if x is not plugin and _dosar(x) == d]
	return [x for x in toti if x == plugin] + [x for x in toti if not x == plugin]


def indisponibile(plugins):
	"""ce e pe receptor si nu se poate deschide acum, cu motivul (PluginComponent.indisponibile)"""
	f = getattr(plugins, 'indisponibile', None)
	return [e for e in f() if not I.pluginImagine(e.get('path', ''))] if f is not None else []


def pachetIndisponibil(catalog, e):
	return catalog.pachet_pentru_dosar(posixpath.normpath(e['path']))


def indisponibilPachet(catalog, plugins, p):
	"""randul din indisponibile() al unui pachet instalat, sau None"""
	for e in indisponibile(plugins):
		if pachetIndisponibil(catalog, e) is p:
			return e
	return None


def listaCanale():
	"""lista de canale a barei, pentru pluginurile care o cer; None cand bara nu exista inca"""
	try:
		from Screens.InfoBar import InfoBar
		return getattr(InfoBar.instance, 'servicelist', None)
	except Exception:
		return None


def motivDeschidere(plugin):
	f = getattr(plugin, 'motivDeschidere', None)
	return f() if f is not None else ''


def dupaRepornire(catalog, plugins):
	"""Pachetele instalate cu un plugin amanat efectiv pana la repornirea interfetei (PluginComponent.amanate). Un plugin
	cazut la import sau oprit in modul sigur nu e aici: repornirea nu il repara, iar randul lui are motivul adevarat."""
	rez = {}
	for cale in getattr(plugins, 'amanate', None) or ():
		if I.pluginImagine(cale):
			continue
		p = catalog.pachet_pentru_dosar(posixpath.normpath(cale))
		if p is not None and p.instalat:
			rez[p.nume] = p
	return sorted(rez.values(), key=lambda p: p.titlu.lower())


def randuriInstalate(catalog, pluginuri, plugins):
	"""Fila Instalate: tot ce e pe receptor, o singura data: pluginurile care se deschid, cele care nu se pot deschide (cu
	motivul), pachetele care asteapta repornirea si restul pachetelor instalate, fara plugin in lista (module de acces,
	teme). Numarul de pe fila e numarul acestor randuri. Un plugin are un singur rand (unulPePlugin), nu cate unul pentru
	fiecare unealta pusa de el in meniul extensiilor."""
	rez = [('plugin', pl, pachetPlugin(catalog, pl)) for pl in unulPePlugin(pluginuri, plugins)
		if not I.pluginImagine(getattr(pl, 'path', ''))]
	vazute = set(x[2].nume for x in rez if x[2] is not None)
	for e in indisponibile(plugins):
		p = pachetIndisponibil(catalog, e)
		# amanat cu pachet: randul pachetului de mai jos
		if e['fel'] != 'repornire' or p is None:
			rez.append(('indisponibil', e, p))
			if p is not None:
				vazute.add(p.nume)
	for p in dupaRepornire(catalog, plugins):
		rez.append(('pachet', p, 'repornire'))
		vazute.add(p.nume)
	restul = [p for p in catalog.pachete.values() if p.instalat and p.nume not in vazute]
	restul.sort(key=lambda p: (p.titlu.lower(), p.nume))
	# in fila asta „Instalat” pe rand nu spune nimic (Eduard, 04.11.2026), deci randul nu poarta insigna
	rez += [('pachet', p, 'in-instalate') for p in restul]
	# ordinea omului si pluginurile ascunse de el (MENU, 0.7.5)
	ordine, ascunse = ordineExtensii()
	rez = aplicaOrdinea(rez, ordine, ascunse)
	# ce are versiune noua sta sus, intr-o sectiune a ei: fila Actualizari nu mai exista
	noi = [r for r in rez if _areActualizare(r)]
	if not noi:
		return rez
	return [('sectiune', _t('Actualizări'), len(noi)), ('actualizeaza', None, len(noi))] + noi + \
		[('sectiune', _t('Instalate'), len(rez) - len(noi))] + [r for r in rez if not _areActualizare(r)]


# ------------------------------------------------------------ ordinea si ascunderea pluginurilor in Instalate (0.7.5)
# Cerute de hoolman (LinuxSat 164121, 14.11.2026 04:16): pluginurile se pot muta si ascunde, ca in alte imagini. Acelasi fel
# ca in meniul Aplicatii (Screens/HdsAplicatii.py): MENU pe randul pluginului, "Mută mai sus", "Mută mai jos", "Mută la
# început", "Ascunde extensia", iar "Arată toate extensiile (N ascunse)" le aduce inapoi; in pagina web /extensii aceleasi
# butoane. Cheia unui plugin e dosarul lui sub Plugins (Extensions/XStreamity): toate randurile aceluiasi plugin se muta si
# se ascund impreuna. Ordinea si cele ascunse stau in config.plugins.hdsextensii (doua siruri de chei, cu "|" intre ele).
# Numai fila Instalate se schimba: lista comuna a pluginurilor (tasta albastra, celelalte meniuri) ramane cum e, iar
# Cautarea gaseste si pluginurile ascunse.
SEP_ORDINE = '|'
_CONFIG_EXTENSII = [None]


def idPlugin(cale):
	"""cheia unui plugin: ultimele doua dosare ale caii lui (Extensions/XStreamity), '' fara cale"""
	cale = posixpath.normpath(cale.replace('\\', '/')) if isinstance(cale, str) and cale else ''
	parti = [x for x in cale.split('/') if x and x != '.']
	if not parti:
		return ''
	return '/'.join(parti[-2:]).replace(SEP_ORDINE, '_')


def idRand(rand):
	"""cheia pluginului unui rand din Instalate ('plugin' sau 'indisponibil'), altfel ''"""
	fel, obj, _extra = rand
	if fel == 'plugin':
		return idPlugin(getattr(obj, 'path', ''))
	if fel == 'indisponibil':
		return idPlugin(obj.get('path', ''))
	return ''


def listaIduri(text):
	vazute = []
	for x in (text or '').split(SEP_ORDINE):
		x = x.strip()
		if x and len(x) <= 160 and x.isprintable() and x not in vazute:
			vazute.append(x)
	return vazute


def configExtensii(config=None):
	"""config.plugins.hdsextensii (ordine, ascunse), creata o singura data; None cand setarile nu se pot lua (probele)"""
	if _CONFIG_EXTENSII[0] is not None:
		return _CONFIG_EXTENSII[0]
	try:
		from Components.config import ConfigSubsection, ConfigText
		if config is None:
			from Components.config import config
		c = ConfigSubsection()
		c.ordine = ConfigText(default='', fixed_size=False)
		c.ascunse = ConfigText(default='', fixed_size=False)
		config.plugins.hdsextensii = c
	except Exception as e:
		_jurnal('setarile ordinii: %s' % e)
		return None
	_CONFIG_EXTENSII[0] = c
	return c


def ordineExtensii():
	"""(ordinea, cele ascunse): sirurile din setari, ('', '') fara setari"""
	c = configExtensii()
	if c is None:
		return '', ''
	return c.ordine.value or '', c.ascunse.value or ''


def aplicaOrdinea(randuri_, ordine, ascunse):
	"""Randurile din Instalate fara pluginurile ascunse si cu randurile pluginurilor in ordinea omului: intai cele din
	`ordine`, apoi cele noi, in ordinea de fabrica (randurile unui plugin raman impreuna, in ordinea lor). Celelalte randuri
	(pachetele fara plugin) raman pe locul lor, dupa pluginuri."""
	ascunse = set(listaIduri(ascunse))
	vazute = [r for r in randuri_ if idRand(r) not in ascunse or not idRand(r)]
	ordine = listaIduri(ordine)
	if not ordine:
		return vazute
	loc = dict((k, i) for i, k in enumerate(ordine))
	pluginuri = [(i, r) for i, r in enumerate(vazute) if r[0] == 'plugin']
	if not pluginuri:
		return vazute
	primul = {}
	for i, r in pluginuri:
		primul.setdefault(idRand(r), i)
	ordonate = sorted(pluginuri, key=lambda x: (loc.get(idRand(x[1]), len(ordine)), primul[idRand(x[1])], x[0]))
	locuri = [i for i, _r in pluginuri]
	rez = list(vazute)
	for i, (_j, r) in zip(locuri, ordonate):
		rez[i] = r
	return rez


def iduriVazute(randuri_):
	"""cheile pluginurilor din Instalate, o data fiecare, in ordinea din lista"""
	rez = []
	for r in randuri_:
		if r[0] == 'plugin':
			k = idRand(r)
			if k and k not in rez:
				rez.append(k)
	return rez


def iduriPluginuri(pluginuri):
	return set(k for k in (idPlugin(getattr(x, 'path', '')) for x in pluginuri or ()) if k)


def nrAscunse(pluginuri, plugins=None):
	"""cate pluginuri instalate sunt ascunse acum (si cele care nu pornesc, dupa dosar)"""
	toate = iduriPluginuri(pluginuri) | set(idPlugin(e.get('path', '')) for e in indisponibile(plugins))
	return len(toate & set(listaIduri(ordineExtensii()[1])))


PASI_ORDINE = ('sus', 'jos', 'inceput', 'ascunde')


def pasiPosibili(randuri_, id_):
	"""ce se poate face cu pluginul `id_` din Instalate: pasii din PASI_ORDINE, in ordinea lor"""
	vazute = iduriVazute(randuri_)
	if id_ not in vazute:
		return []
	i = vazute.index(id_)
	rez = []
	if i > 0:
		rez += ['sus', 'inceput']
	if i < len(vazute) - 1:
		rez.append('jos')
	return rez + ['ascunde']


TEXTE_ORDINE = {'sus': N_('Mută mai sus'), 'jos': N_('Mută mai jos'), 'inceput': N_('Mută la început'),
	'ascunde': N_('Ascunde extensia')}


def schimbaOrdinea(randuri_, id_, pas, salveaza=True):
	"""Muta sau ascunde pluginul `id_` (pas din PASI_ORDINE) fata de randurile din Instalate de acum. True daca s-a schimbat
	ceva. Ordinea noua pastreaza locul celor ascunse (dupa cele vazute)."""
	c = configExtensii()
	if c is None or pas not in pasiPosibili(randuri_, id_):
		return False
	if pas == 'ascunde':
		ascunse = [x for x in listaIduri(c.ascunse.value) if x != id_] + [id_]
		c.ascunse.value = SEP_ORDINE.join(ascunse)
		if salveaza:
			c.ascunse.save()
		_jurnal('extensie ascunsa: %s' % id_)
		return True
	vazute = iduriVazute(randuri_)
	i = vazute.index(id_)
	j = {'sus': i - 1, 'jos': i + 1, 'inceput': 0}[pas]
	vazute.insert(j, vazute.pop(i))
	ascunse = set(listaIduri(c.ascunse.value))
	c.ordine.value = SEP_ORDINE.join(vazute + [x for x in listaIduri(c.ordine.value) if x in ascunse and x not in vazute])
	if salveaza:
		c.ordine.save()
	_jurnal('ordinea extensiilor: %s %s' % (id_, pas))
	return True


def arataToateExtensiile(salveaza=True):
	c = configExtensii()
	if c is None or not c.ascunse.value:
		return False
	c.ascunse.value = ''
	if salveaza:
		c.ascunse.save()
	return True


def textArataToate(n):
	return _t('Arată toate extensiile (%d ascunse)') % n


def _areActualizare(rand):
	p = _pachetRand(*rand)
	return p is not None and bool(p.actualizare)


def nrInstalate(catalog, pluginuri, plugins):
	"""numarul de pe fila Instalate: numai randurile cu ceva instalat"""
	return sum(1 for r in randuriInstalate(catalog, pluginuri, plugins) if r[0] in RANDURI_CU_PACHET)


def deDescarcat(catalog):
	"""Fila Disponibile: ce se poate lua din surse si nu e pe receptor, de orice fel; felul se alege din filtru"""
	rez = [p for p in catalog.pachete.values() if p.disponibil and not p.instalat]
	rez.sort(key=lambda p: (p.titlu.lower(), p.nume))
	return rez


# sectiunile din feed: pluginurile, media, apoi celelalte feluri in ordinea din P.CATEGORII (Eduard, 04.11.2026: „secțiuni în
# interiorul feedurilor, unde se poate”). Media se recunoaste dupa Section din lista feedului.
SECTIUNI_MEDIA = ('multimedia', 'media', 'video', 'audio', 'radio')


def _ordineFeed(cheie):
	if cheie == FEED_EXTERN:
		return (0, '')
	if cheie == FEED_HDS:
		return (1, '')
	if cheie.startswith(PREFIX_SURSA):
		return (2, cheie.lower())
	return (3, cheie)


def sectiunePachet(p):
	"""(ordinea, eticheta) sectiunii unui pachet in feedul lui"""
	if p.categorie == 'extensions':
		if p.sectiune in SECTIUNI_MEDIA or any(c in p.sectiune.split('/') for c in SECTIUNI_MEDIA):
			return (1, _t('Media'))
		return (0, _t('Pluginuri'))
	return (2 + P.ORDINE.get(p.categorie, len(P.CATEGORII)), _t(P.ETICHETE.get(p.categorie, 'Altele')))


# ------------------------------------------------------------ dosarele din Disponibile (0.7.5)
# Cerute de oameni (monuser, LinuxSat 164173, 14.11.2026 02:21; JAKITAKI, Satedu 32518, 14.11.2026 10:36): Disponibile pe
# dosare care se deschid si se inchid cu OK (Pluginuri, Media, Drivere, Skinuri, Acces conditionat, Sigle...), ca in alte
# imagini; pachetele noastre (HD Satelit si feedul pluginurilor externe) in dosarele dupa fel, iar cele din sursele
# adaugate de alte programe sau de om (de pilda feedul adaugat de un manager de pluginuri) intr-un dosar al lor, ultimul,
# "Din alte surse", cu o sectiune pe sursa. Nimic de setat: dosarele vin inchise; un singur dosar, sau filtrul activ,
# le deschide singur. Randul ('dosar', Dosar, None) se alege cu cursorul; L.randuri da mereu toate randurile (numaratorile
# filtrului raman bune), iar fiecare capat le strange dupa dosarele deschise (strangeDosare, pe televizor; in pagina web,
# scriptul).
DOSAR_ALTE = 'alte'
ETICHETA_ALTE = N_('Din alte surse')
TEXT_DOSAR_ALTE = N_('Pachetele din feedurile adăugate de alte programe sau de tine: %s. Nu sunt verificate de HD Satelit.')


class Dosar(object):
	"""un dosar din Disponibile: cheia (felul pachetelor sau DOSAR_ALTE), cate pachete are si daca e deschis acum"""
	__slots__ = ('cheie', 'numar', 'deschis')

	def __init__(self, cheie, numar, deschis=True):
		self.cheie = cheie
		self.numar = numar
		self.deschis = deschis

	def cu(self, **schimbari):
		d = Dosar(self.cheie, self.numar, self.deschis)
		for k, v in schimbari.items():
			setattr(d, k, v)
		return d

	def __eq__(self, alt):
		return isinstance(alt, Dosar) and (self.cheie, self.numar, self.deschis) == (alt.cheie, alt.numar, alt.deschis)

	def __ne__(self, alt):
		return not self.__eq__(alt)

	__hash__ = None

	def __repr__(self):
		return 'Dosar(%r, %r, %r)' % (self.cheie, self.numar, self.deschis)


def dinAlteSurse(catalog, p):
	"""pachetul vine dintr-o sursa care nu e a noastra (nici HD Satelit, nici feedul pluginurilor externe). O sursa adaugata
	de om ramane a lui, chiar cu adresa unui feed al nostru (felFeed), deci sta tot aici."""
	feed = feedRand(catalog, 'pachet', p, None)
	return feed == FEED_ALTA or feed.startswith(PREFIX_SURSA)


def dosarPachet(catalog, p):
	"""(ordinea, cheia) dosarului unui pachet din Disponibile"""
	if dinAlteSurse(catalog, p):
		return (1000, DOSAR_ALTE)
	ordine, _eticheta = sectiunePachet(p)
	if ordine == 0:
		return (0, 'pluginuri')
	if ordine == 1:
		return (1, 'media')
	return (ordine, p.categorie if p.categorie in P.ETICHETE else 'altele')


def numeDosar(cheie):
	if cheie == DOSAR_ALTE:
		return _t(ETICHETA_ALTE)
	if cheie == 'pluginuri':
		return _t('Pluginuri')
	if cheie == 'media':
		return _t('Media')
	return _t(P.ETICHETE.get(cheie, 'Altele'))


def icoanaDosar(cheie):
	if cheie in ('pluginuri', 'media'):
		return 'extensii'
	return P.ICOANE.get(cheie, 'altele')


def surseAlte(catalog):
	"""numele surselor din dosarul "Din alte surse" (cele care au pachete de luat), in ordinea filtrului"""
	chei = set(feedRand(catalog, 'pachet', p, None) for p in deDescarcat(catalog) if dinAlteSurse(catalog, p))
	return [numeFeedFiltru(k) for k in sorted(chei, key=_ordineFeed)]


def randuriDeDescarcat(catalog):
	"""Fila Disponibile, pe dosare (0.7.5): un rand ('dosar', Dosar, None) inaintea pachetelor lui. In dosarul "Din alte
	surse", un rand ('sectiune', numele sursei, numarul) inaintea pachetelor fiecarei surse; pe randul de sectiune nu se
	ajunge cu cursorul. Randul fiecarui pachet spune si de unde vine (cuSursa)."""
	grupe = {}
	for p in deDescarcat(catalog):
		grupe.setdefault(dosarPachet(catalog, p), []).append(p)
	rez = []
	for cheie in sorted(grupe):
		lista = grupe[cheie]
		rez.append(('dosar', Dosar(cheie[1], len(lista)), None))
		if cheie[1] != DOSAR_ALTE:
			rez += [('pachet', p, None) for p in lista]
			continue
		pe_sursa = {}
		for p in lista:
			pe_sursa.setdefault(feedRand(catalog, 'pachet', p, None), []).append(p)
		for feed in sorted(pe_sursa, key=_ordineFeed):
			rez.append(('sectiune', numeFeedFiltru(feed), len(pe_sursa[feed])))
			rez += [('pachet', p, None) for p in pe_sursa[feed]]
	return rez


def dosareDeschiseImplicit(randuri_, filtru=None, fila=''):
	"""Dosarele vin inchise; un singur dosar, sau filtrul activ (lista e deja ingustata de om), le deschide pe toate."""
	return sum(1 for r in randuri_ if r[0] == 'dosar') <= 1 or filtruActiv(filtru, fila)


def strangeDosare(randuri_, alese=None, implicit=False):
	"""Randurile aratate: sub un dosar inchis nu se vede nimic. `alese`: {cheie: deschis} schimbate de om cu OK in sesiunea
	ecranului; celelalte dosare sunt `implicit` (dosareDeschiseImplicit). Fiecare rand de dosar spune daca e deschis."""
	alese = alese or {}
	rez = []
	inchis = False
	for r in randuri_:
		if r[0] == 'dosar':
			deschis = alese.get(r[1].cheie, implicit)
			inchis = not deschis
			rez.append(('dosar', r[1].cu(deschis=deschis), r[2]))
		elif not inchis:
			rez.append(r)
	return rez


def textDosar(d):
	"""subtitlul randului unui dosar: cate pachete are si ce face OK"""
	numar = _t('un pachet') if d.numar == 1 else _t('%d pachete') % d.numar
	return '%s · %s' % (numar, _t('OK închide dosarul') if d.deschis else _t('OK deschide dosarul'))


def descriereDosar(catalog, d):
	"""descrierea din detaliile unui dosar: sursele lui (Din alte surse) sau primele pachete"""
	if d.cheie == DOSAR_ALTE:
		return _t(TEXT_DOSAR_ALTE) % ', '.join(surseAlte(catalog))
	titluri = [p.titlu for p in deDescarcat(catalog) if dosarPachet(catalog, p)[1] == d.cheie]
	text = ', '.join(titluri[:12])
	if len(titluri) > 12:
		text += ' ' + _t('și încă %d') % (len(titluri) - 12)
	return text


def textGolDisponibile(catalog):
	"""Fila Disponibile fara nimic: de ce, pentru fiecare feed (Eduard, 04.11.2026: „deocamdată ai instalat toate extensiile
	disponibile” sau „această sursă nu are nicio extensie deocamdată”). '' cand lista nu e descarcata sau nu sunt surse: atunci
	spune altceva fiecare capat."""
	if not catalog.configurare.surse or not catalog.surse_cu_lista:
		return ''
	din_surse = {}
	for p in catalog.pachete.values():
		if p.disponibil:
			k = feedRand(catalog, 'pachet', p, None)
			din_surse[k] = din_surse.get(k, 0) + 1
	randuri_ = [_t('Deocamdată nu e nimic nou de descărcat.')]
	chei = [f.id for f in feeduri(catalog)] + [PREFIX_SURSA + s[0] for s in surseSingure(catalog)]
	for k in sorted(chei, key=_ordineFeed):
		n = din_surse.get(k, 0)
		nume = numeFeedFiltru(k)
		if n:
			randuri_.append(_t('%s: ai instalat toate extensiile lui (%d).') % (nume, n))
		else:
			randuri_.append(_t('%s: nu are deocamdată nicio extensie.') % nume)
	return '\n'.join(randuri_)


def file(catalog, nrInstalate, nrFisiere=None):
	"""Cele trei file permanente, in aceeasi ordine pe televizor si in web. Numarul fisierelor vine din cautarea
	in fundal; None inseamna ca prima cautare nu s-a terminat. Surse feeduri se deschide cu tasta verde."""
	return [('instalate', _t('Instalate'), nrInstalate), ('disponibile', _t('Disponibile'), len(deDescarcat(catalog))),
		('fisiere', _t(ETICHETA_FISIERE), nrFisiere)]


def semnLocuriFisiere(tmp='/tmp'):
	"""Montarile si fisierele .ipk puse direct in /tmp (nume, marime, data), fara acces la stick, disc sau retea. O
	schimbare cere o noua cautare.
	Nu data dosarului /tmp (12.11.2026, Eduard pe Octagon SF8008 0.7.4): modulul de acces conditionat rescrie fisiere in
	/tmp la cateva secunde, data dosarului se schimba mereu, iar Extensii (si pagina web) porneau o cautare noua la fiecare
	verificare (2 s), fara sfarsit: semnul se misca sus tot timpul, fiecare cautare citea 10 s pachetele (verificarea
	Python 2), iar decodarea Sky se oprea (46 de opriri in 14 minute). Un .ipk incarcat din web sau copiat in /tmp, sau
	sters dupa instalare, schimba tot semnul."""
	ipk = []
	try:
		for e in os.scandir(tmp):
			try:
				if e.name.lower().endswith('.ipk') and e.is_file(follow_symlinks=False):
					st = e.stat(follow_symlinks=False)
					ipk.append((e.name, st.st_size, getattr(st, 'st_mtime_ns', st.st_mtime)))
			except OSError:
				continue
	except OSError:
		ipk = None
	return tuple(sorted(P.readMountTable().items())), tuple(sorted(ipk)) if ipk is not None else None


def filaSurse(catalog):
	"""(id, eticheta, numar) al filei Surse, ultima pe televizor si in pagina web; eticheta tradusa; numarul = randurile
	aratate (feedurile si sursele singure), nu sursele opkg"""
	return ('surse', _t(ETICHETA_SURSE), numarSurse(catalog))


def numarSurse(catalog):
	return len(feeduri(catalog)) + len(surseSingure(catalog))


def randuriCautare(catalog, pluginuri, text, plugins=None):
	t = (text or '').strip().lower()
	rez = []
	vazute = set()
	for plugin in unulPePlugin(pluginuri, plugins):
		if I.pluginImagine(getattr(plugin, 'path', '')):
			continue
		nume = (plugin.name or '').lower()
		if t in nume or t in (plugin.description or '').lower():
			p = pachetPlugin(catalog, plugin)
			rez.append(('plugin', plugin, p))
			if p is not None:
				vazute.add(p.nume)
	gasite = catalog.cauta(t)
	for e in indisponibile(plugins):
		p = pachetIndisponibil(catalog, e)
		if t in str(e['nume']).lower() or p in gasite:
			rez.append(('indisponibil', e, p))
			if p is not None:
				vazute.add(p.nume)
	for p in gasite:
		if p.nume not in vazute:
			rez.append(('pachet', p, None))
	return rez


def randuri(catalog, fila, pluginuri, plugins, cautare=''):
	"""[(fel, obiect, extra)] ale unei file, afara de Din fisier"""
	if fila == 'cautare':
		return randuriCautare(catalog, pluginuri, cautare, plugins)
	if fila == 'instalate':
		return randuriInstalate(catalog, pluginuri, plugins)
	if fila == 'disponibile':
		return randuriDeDescarcat(catalog)
	if fila == 'actualizari':
		return [('pachet', p, None) for p in catalog.actualizari()]
	if fila == 'surse':
		rez = [('feed', f, None) for f in feeduri(catalog)]
		rez += [('sursa', s, None) for s in surseSingure(catalog)]
		# „Adaugă feed” e pe tasta verde, nu mai are rand (Eduard, 04.11.2026)
		p = catalog.pachete.get(PACHET_FEEDURI)
		if p is not None:
			rez.append(('pluginsurse', p, None))
		return rez
	return [('pachet', p, None) for p in catalog.din_categoria(fila)]


# ------------------------------------------------------------ filtrul listelor (dupa feed si dupa fel)
# Primul rand al filelor cu pachete e filtrul ('filtru'): OK (sau clic) deschide alegerile, Rosu arata tot. Feedul se
# alege in orice fila cu pachete; felul (categoria) numai in filele amestecate, unde stau pachete de mai multe feluri
# (in celelalte fila insasi e felul). Pagina web are aceleasi alegeri, ca liste (feed=, fel=).
FILE_AMESTECATE = ('instalate', 'actualizari', 'disponibile', 'cautare')
FILE_FARA_FILTRU = ('fisiere', 'surse')
FEED_IMAGINE = 'imagine'
FEED_ALTA = 'alta'
PREFIX_SURSA = 'sursa:'


def filtruGol():
	return {'feed': '', 'fel': ''}


def areFiltru(fila):
	return fila not in FILE_FARA_FILTRU


def filtruActiv(filtru, fila):
	f = filtru or {}
	return bool(f.get('feed')) or bool(f.get('fel') and fila in FILE_AMESTECATE)


def _pachetRand(fel, obj, extra):
	if fel in ('plugin', 'indisponibil'):
		return extra
	if fel == 'pachet':
		return obj
	return None


def feedRand(catalog, fel, obj, extra):
	"""feedul unui rand cu pachet: FEED_HDS, FEED_EXTERN, FEED_IMAGINE (vine cu imaginea), PREFIX_SURSA + numele sursei
	omului sau al altei surse, FEED_ALTA (pachet instalat de nicaieri, de pilda din fisier); '' la celelalte randuri"""
	if fel not in RANDURI_CU_PACHET:
		return ''
	p = _pachetRand(fel, obj, extra)
	if p is None:
		return FEED_IMAGINE
	if p.sursa:
		f = felFeed(catalog, p.sursa, catalog.configurare.adresa(p.sursa))
		return f if f is not None else PREFIX_SURSA + p.sursa
	return FEED_IMAGINE if p.din_imagine else FEED_ALTA


def felRand(catalog, fel, obj, extra):
	"""categoria unui rand cu pachet (P.CATEGORII), '' la celelalte randuri"""
	if fel == 'plugin':
		return extra.categorie if extra is not None else categoriePlugin(getattr(obj, 'path', ''))
	if fel == 'indisponibil':
		return extra.categorie if extra is not None else categoriePlugin(obj['path'])
	if fel == 'pachet':
		return obj.categorie
	return ''


def numeFeedFiltru(cheie):
	if cheie == FEED_HDS:
		return 'HD Satelit'
	if cheie == FEED_EXTERN:
		return _t(ETICHETA_EXTERNE)
	if cheie == FEED_IMAGINE:
		return _t('Imaginea HD Satelit')
	if cheie == FEED_ALTA:
		return _t('Alt feed')
	if cheie.startswith(PREFIX_SURSA):
		return cheie[len(PREFIX_SURSA):]
	return _t('Toate feedurile')


def numeFelFiltru(cheie):
	return _t(P.ETICHETE[cheie]) if cheie in P.ETICHETE else _t('Toate felurile')


def potrivesteFiltru(catalog, rand, filtru, fila):
	fel, obj, extra = rand
	if fel not in RANDURI_CU_PACHET:
		return True
	f = filtru or {}
	if f.get('feed') and feedRand(catalog, fel, obj, extra) != f['feed']:
		return False
	if f.get('fel') and fila in FILE_AMESTECATE and felRand(catalog, fel, obj, extra) != f['fel']:
		return False
	return True


def filtreaza(catalog, randuri_, filtru, fila):
	"""randurile filei care trec de filtru (randurile fara pachet raman, afara de sectiunile ramase goale)"""
	if not areFiltru(fila) or not filtruActiv(filtru, fila):
		return list(randuri_)
	bune = [r for r in randuri_ if potrivesteFiltru(catalog, r, filtru, fila)]
	if not any(r[0] == 'dosar' for r in bune):
		return [r for i, r in enumerate(bune) if r[0] != 'sectiune' or (i + 1 < len(bune) and bune[i + 1][0] in RANDURI_CU_PACHET)]
	# Disponibile pe dosare (0.7.5): dosarele si sectiunile fara pachete raman pe dinafara; cele ramase isi numara din nou
	# pachetele (altfel "Drivere (14)" ar sta deasupra a doua pachete)
	rez = []
	n_sectiune = n_dosar = 0
	for r in reversed(bune):
		if r[0] in RANDURI_CU_PACHET:
			n_sectiune += 1
			n_dosar += 1
			rez.append(r)
		elif r[0] == 'sectiune':
			if n_sectiune:
				rez.append((r[0], r[1], n_sectiune))
			n_sectiune = 0
		elif r[0] == 'dosar':
			if n_dosar:
				rez.append((r[0], r[1].cu(numar=n_dosar), r[2]))
			n_sectiune = n_dosar = 0
		else:
			rez.append(r)
	rez.reverse()
	return rez


def _ordineFeed(cheie):
	return ({FEED_HDS: 0, FEED_EXTERN: 1, FEED_IMAGINE: 2}.get(cheie, 4 if cheie == FEED_ALTA else 3), cheie)


def alegeriFiltru(catalog, randuri_, fila):
	"""(feeduri, feluri): [(cheie, text cu numarul pachetelor)] din randurile filei (nefiltrate), prima fiind ('', toate);
	felurile numai in filele amestecate, altfel []"""
	feeds = {}
	kinds = {}
	for fel, obj, extra in randuri_:
		if fel not in RANDURI_CU_PACHET:
			continue
		k = feedRand(catalog, fel, obj, extra)
		feeds[k] = feeds.get(k, 0) + 1
		c = felRand(catalog, fel, obj, extra)
		kinds[c] = kinds.get(c, 0) + 1
	total = sum(feeds.values())
	feeduri_ = [('', '%s (%d)' % (_t('Toate feedurile'), total))]
	feeduri_ += [(k, '%s (%d)' % (numeFeedFiltru(k), feeds[k])) for k in sorted(feeds, key=_ordineFeed)]
	feluri_ = []
	if fila in FILE_AMESTECATE:
		feluri_ = [('', '%s (%d)' % (_t('Toate felurile'), total))]
		feluri_ += [(c, '%s (%d)' % (numeFelFiltru(c), kinds[c])) for c, _e, _i in P.CATEGORII if c in kinds]
	return feeduri_, feluri_


def alegeriEcran(catalog, randuri_, fila):
	"""randurile ferestrei de alegere de pe televizor: [(text, (dimensiune, cheie))], cu titlurile grupelor (cheia None)"""
	feeduri_, feluri_ = alegeriFiltru(catalog, randuri_, fila)
	rez = [(_t('Arată tot'), ('tot', '')), (_t('Feedul') + ':', None)]
	rez += [('   ' + t, ('feed', k)) for k, t in feeduri_]
	if feluri_:
		rez.append((_t('Felul') + ':', None))
		rez += [('   ' + t, ('fel', k)) for k, t in feluri_]
	return rez


def aplicaAlegere(filtru, alegere):
	"""filtrul nou dupa un rand ales din alegeriEcran ((dimensiune, cheie))"""
	if not alegere:
		return dict(filtru or filtruGol())
	dim, cheie = alegere
	if dim == 'tot':
		return filtruGol()
	nou = dict(filtru or filtruGol())
	if dim in ('feed', 'fel'):
		nou[dim] = cheie or ''
	return nou


def textFiltru(filtru, fila):
	"""'HD Satelit · Skinuri' (ce e ales), '' cand filtrul nu e activ in fila"""
	f = filtru or {}
	parti = []
	if f.get('feed'):
		parti.append(numeFeedFiltru(f['feed']))
	if f.get('fel') and fila in FILE_AMESTECATE:
		parti.append(numeFelFiltru(f['fel']))
	return ' · '.join(parti)


def cuRandFiltru(catalog, randuri_, filtru, fila):
	"""randurile filei pentru televizor: cele care trec de filtru. Filtrul nu mai are rand in lista (Eduard, 04.11.2026): se
	deschide cu tasta albastra, iar starea lui se scrie in randul de sus (textStareFiltru)."""
	if not areFiltru(fila):
		return list(randuri_)
	return filtreaza(catalog, randuri_, filtru, fila)


def textStareFiltru(catalog, randuri_, filtru, fila):
	"""„Filtru: X, 3 din 8”, pentru randul de stare, cand filtrul e activ; altfel ''"""
	if not areFiltru(fila) or not filtruActiv(filtru, fila):
		return ''
	cu_pachet = [r for r in randuri_ if r[0] in RANDURI_CU_PACHET]
	aratate = sum(1 for r in filtreaza(catalog, randuri_, filtru, fila) if r[0] in RANDURI_CU_PACHET)
	return '%s, %s' % (_t('Filtru: %s') % textFiltru(filtru, fila), _t('%d din %d') % (aratate, len(cu_pachet)))


def _insignaIndisponibil(e):
	"""(insigna, culoarea ei) pentru un plugin care nu se poate deschide acum; motivul intreg sta sub nume"""
	if e['fel'] == 'repornire':
		return _t('După repornire'), 'chihlimbar'
	if e['fel'] == 'mod_sigur':
		return _t('Oprit'), 'chihlimbar'
	return _t('Nu pornește'), 'rau'


def descriereRand(catalog, fel, obj, extra):
	"""(icoana, titlu, subtitlu, insigna, culoarea insignei, textul mic din dreapta) al unui rand din lista. Culoarea e
	o cheie ('bun', 'chihlimbar', 'rau') sau None. Randul cautarii in retea il face fiecare capat. Textele sunt
	intregi: un rand care nu incape deruleaza (lib/gui/elabel.h)."""
	if fel == 'dosar':
		alte = obj.cheie == DOSAR_ALTE
		sub = cuSursa(', '.join(surseAlte(catalog)), textDosar(obj)) if alte else textDosar(obj)
		return (icoanaDosar(obj.cheie), numeDosar(obj.cheie), sub, str(obj.numar), 'chihlimbar' if alte else 'eticheta', '')
	if fel == 'plugin':
		p = extra
		cat = p.categorie if p is not None else categoriePlugin(getattr(obj, 'path', ''))
		insigna = culoare = None
		if p is not None and p.actualizare:
			insigna, culoare = _t('De actualizat'), 'chihlimbar'
		mic = []
		sub = obj.description or ''
		if p is not None:
			# de unde vine pachetul, sub nume (0.6.6): feedurile stau amestecate in liste
			sub = cuSursa(sursaPachet(catalog, p)[0], sub)
			if p.versiune_instalata:
				mic.append(p.versiune_instalata)
		# ultima deschidere a cazut: motivul sta sub nume pana la o deschidere reusita
		motiv = motivDeschidere(obj)
		if motiv:
			sub = motiv
			if not insigna:
				insigna, culoare = _t('Nu pornește'), 'rau'
		return (P.ICOANE.get(cat, 'extensii'), obj.name or '', sub, insigna, culoare, ' · '.join(mic))
	if fel == 'indisponibil':
		p = extra
		cat = p.categorie if p is not None else categoriePlugin(obj['path'])
		insigna, culoare = _insignaIndisponibil(obj)
		return (P.ICOANE.get(cat, 'extensii'), p.titlu if p is not None else obj['nume'], obj['motiv'], insigna, culoare,
			p.versiune_instalata if p is not None and p.versiune_instalata else '')
	if fel == 'pachet':
		p = obj
		if extra == 'repornire':
			insigna, culoare = _t('După repornire'), 'chihlimbar'
		elif p.actualizare:
			insigna, culoare = _t('De actualizat'), 'chihlimbar'
		elif p.instalat and extra != 'in-instalate':
			insigna, culoare = _t('Instalat'), 'bun'
		elif p.python2:
			insigna, culoare = _t(INSIGNA_PYTHON2), 'rau'
		else:
			insigna = culoare = None
		mic = [x for x in (textVersiuni(p), P.marime_text(p.marime or p.marime_instalat)) if x]
		return (P.ICOANE.get(p.categorie, 'altele'), p.titlu, cuSursa(sursaPachet(catalog, p)[0], p.subtitlu), insigna,
			culoare, ' · '.join(mic))
	if fel == 'fisier':
		f = obj
		pInstalat = catalog._toate.get(f.nume) if f.nume else None
		if not f.citit:
			insigna, culoare = _t('Nu se poate citi'), 'rau'
		elif getattr(f, 'python2', None):
			insigna, culoare = _t(INSIGNA_PYTHON2), 'rau'
		elif pInstalat is not None and pInstalat.instalat:
			insigna, culoare = _t('Instalat'), 'bun'
		else:
			insigna = culoare = None
		mic = [x for x in (_t(etichetaLoc(f.cale, f.retea)), f.versiune, P.marime_text(f.marime)) if x]
		return ('fisier', f.titlu, f.rezumat or f.nume_fisier, insigna, culoare, ' · '.join(mic))
	if fel == 'sursa':
		nume, adresa = obj
		eticheta, _a, hds = sursa(catalog, nume)
		n = sum(1 for p in catalog._toate.values() if p.sursa == nume)
		if hds:
			insigna, culoare = _t('Oficială'), 'bun'
		elif catalog.configurare.e_a_utilizatorului(nume):
			insigna, culoare = _t('Adăugată de tine'), 'chihlimbar'
		else:
			insigna, culoare = _t('Externă'), 'chihlimbar'
		mic = _pachete_sursa(n) if nume in catalog.surse_cu_lista else _t('lista nedescărcată')
		return ('surse', eticheta if hds else nume, adresa, insigna, culoare, mic)
	if fel == 'feed':
		f = obj
		if f.id == FEED_HDS:
			insigna, culoare = _t('Oficială'), 'bun'
		else:
			insigna, culoare = _t('Externă'), 'bun'
		gazde = []
		for _n, a in f.surse:
			g = P.gazda(a)
			if g and g not in gazde:
				gazde.append(g)
		return ('surse', numeFeed(f), ', '.join(gazde), insigna, culoare, stareFeed(catalog, f))
	if fel == 'filtru':
		fila, aratate, total = extra
		text = textFiltru(obj, fila)
		if text:
			titlu, insigna, culoare = _t('Filtru: %s') % text, _t('Activ'), 'chihlimbar'
		else:
			titlu, insigna, culoare = _t('Filtru: toate extensiile'), None, None
		if fila in FILE_AMESTECATE:
			sub = _t('OK alege feedul sau felul extensiilor arătate.')
		else:
			sub = _t('OK alege feedul extensiilor arătate.')
		return ('liste', titlu, sub, insigna, culoare, _t('%d din %d') % (aratate, total))
	if fel == 'actualizeaza':
		return ('actualizari', _t('Actualizează tot'), _t('Toate extensiile cu o versiune nouă: %d') % extra, None, None, '')
	if fel == 'dinfisier':
		return ('fisier', _t('Din fișier'),
			_t('Fișiere .ipk de pe stick, disc, din /tmp sau din rețea'), None, None, '')
	if fel == 'pluginsurse':
		return ('surse', _t('Mai multe feeduri, automat'), _t('Un plugin din Monea Software le adaugă singur'), None, None, '')
	# adauga
	return ('surse', _t('Adaugă un feed'), _t('Adresa unui feed de pe internet'), None, None, '')


def detalii(catalog, fel, obj, extra):
	"""Detaliile randului ales: {'icoana', 'titlu', 'insigna', 'culoare', 'etichete', 'valori', 'descriere', 'indiciu'}
	(indiciul spune tastele telecomenzii). Randul cautarii in retea il face fiecare capat."""
	d = {'icoana': None, 'titlu': '', 'insigna': '', 'culoare': 'eticheta', 'etichete': [], 'valori': [],
		'descriere': '', 'indiciu': ''}
	if fel == 'dosar':
		numar = _t('un pachet') if obj.numar == 1 else _t('%d pachete') % obj.numar
		d.update(icoana=icoanaDosar(obj.cheie), titlu=numeDosar(obj.cheie), insigna=numar,
			culoare='chihlimbar' if obj.cheie == DOSAR_ALTE else 'eticheta', descriere=descriereDosar(catalog, obj),
			indiciu=_t('OK închide dosarul') if obj.deschis else _t('OK deschide dosarul'))
		return d
	if fel == 'plugin':
		p = extra
		cat = p.categorie if p is not None else categoriePlugin(getattr(obj, 'path', ''))
		s, adresa, _hds = sursaPachet(catalog, p)
		d.update(icoana=P.ICOANE.get(cat, 'extensii'), titlu=obj.name or '', insigna=_t('Pe receptor'), culoare='bun')
		if p is not None and p.actualizare:
			d.update(insigna=_t('Actualizare disponibilă: %s') % p.versiune, culoare='chihlimbar')
		rand = [(_t('Versiune'), p.versiune_instalata if p is not None else ''),
			(_t('Ocupă'), P.marime_text(p.marime_instalat) if p is not None else ''),
			(_t('Feed'), s),
			(_t('Adresa'), P.gazda(adresa) if adresa and not _hds else ''),
			(_t('Locul'), _t(P.ETICHETE.get(cat, N_('Extensii'))))]
		d['etichete'] = [a for a, b in rand if b]
		d['valori'] = [b for a, b in rand if b]
		text = obj.description or ''
		if p is not None and p.descriere and p.descriere != text:
			text = (text + '\n' + p.descriere).strip()
		# ce nu merge se vede intai: ultima deschidere cazuta, un keymap stricat (pluginul se deschide mai departe)
		motiv = motivDeschidere(obj)
		if motiv:
			d.update(insigna=motiv, culoare='rau')
		motivTaste = getattr(obj, 'motivTaste', None)
		if motivTaste is not None and motivTaste():
			text = (motivTaste() + '\n' + text).strip()
		d['descriere'] = text
		ind = [_t('OK deschide')]
		if p is not None and p.actualizare:
			ind.append(_t('Roșu actualizează'))
		elif p is not None and p.se_poate_sterge:
			ind.append(_t('Roșu șterge'))
		if areSursa(catalog, p):
			ind.append(_t('INFO descarcă sursa'))
		d['indiciu'] = ' · '.join(ind)
	elif fel == 'indisponibil':
		p = extra
		cat = p.categorie if p is not None else categoriePlugin(obj['path'])
		# fara pachet nu stim de unde vine: nu e neaparat al imaginii
		s = sursaPachet(catalog, p)[0] if p is not None else ''
		culoare = _insignaIndisponibil(obj)[1]
		d.update(icoana=P.ICOANE.get(cat, 'extensii'), titlu=p.titlu if p is not None else obj['nume'], insigna=obj['motiv'], culoare=culoare)
		rand = [(_t('Versiune'), p.versiune_instalata if p is not None else ''),
			(_t('Feed'), s),
			(_t('Locul'), _t(P.ETICHETE.get(cat, N_('Extensii'))))]
		d['etichete'] = [a for a, b in rand if b]
		d['valori'] = [b for a, b in rand if b]
		d['descriere'] = obj['mesaj']
		ind = [_t('OK repornește interfața acum') if obj['fel'] == 'repornire' else _t('OK arată motivul')]
		if p is not None and p.se_poate_sterge:
			ind.append(_t('Roșu șterge'))
		d['indiciu'] = ' · '.join(ind)
	elif fel == 'pachet':
		p = obj
		s, adresa, hds = sursaPachet(catalog, p)
		if p.actualizare:
			d.update(insigna=_t('Actualizare de la %s la %s') % (p.versiune_instalata, p.versiune), culoare='chihlimbar')
		elif p.instalat:
			d.update(insigna=_t('Instalat, versiunea %s') % p.versiune_instalata, culoare='bun')
		else:
			d.update(insigna=_t('Neinstalat'), culoare='eticheta')
		marime = P.marime_text(p.marime)
		ocupa = P.marime_text(p.marime_instalat)
		rand = [(_t('Versiune'), p.versiune or p.versiune_instalata),
			(_t('Mărime'), ', '.join(x for x in (marime, ocupa and _t('ocupă %s') % ocupa) if x)),
			(_t('Feed'), s),
			(_t('Adresa'), P.gazda(adresa) if adresa and not hds else ''),
			(_t('Categoria'), _t(P.ETICHETE.get(p.categorie, N_('Altele'))))]
		d['etichete'] = [a for a, b in rand if b]
		d['valori'] = [b for a, b in rand if b]
		text = p.descriere
		if dinFeedulExtern(catalog, p):
			text = (text + '\n' if text else '') + _t(NOTA_EXTERNE)
		elif not hds and p.sursa:
			text = (text + '\n' if text else '') + _t('Extensia vine dintr-un feed extern și nu este verificată de HD Satelit.')
		if p.python2 and p.instalat:
			# versiunea din sursa e numai pentru Python 2: nu e o actualizare (0.6.8)
			text = (text + '\n' if text else '') + _t('Versiunea %s din feedul %s e făcută pentru Python 2 și nu se '
				'instalează.') % (p.versiune, s)
		d.update(icoana=P.ICOANE.get(p.categorie, 'altele'), titlu=p.titlu, descriere=text)
		if extra == 'repornire':
			d.update(insigna=_t('Pornește după repornire'), culoare='chihlimbar',
				indiciu=_t('OK repornește interfața acum'))
		elif p.actualizare:
			d['indiciu'] = _t('OK actualizează · Roșu șterge')
		elif p.instalat:
			# fara rand in lista pluginurilor: unde se deschide (intrarea din meniu, ecranul modulelor de acces)
			fara = deschidereFaraPlugin(catalog, p) if pluginPentru(pluginuriDeDeschis(_componenta(None)), p) is None else None
			nota = notaFaraPlugin(fara)
			if nota:
				d['descriere'] = (d['descriere'] + '\n' if d['descriere'] else '') + nota
			if fara is not None and fara['fel'] in ('meniu', 'acces'):
				d['indiciu'] = ' · '.join([_t('OK deschide')] + ([_t('Roșu șterge')] if p.se_poate_sterge else []))
			else:
				d['indiciu'] = _t('Instalat și la zi · Roșu șterge') if p.se_poate_sterge else _t('Instalat și la zi')
		elif p.python2:
			d.update(insigna=_t(INSIGNA_PYTHON2), culoare='rau', descriere=descrierePython2(catalog, fel, obj, extra),
				indiciu=_indiciuPython2(catalog, fel, obj, extra))
		elif p.se_poate_instala:
			d['indiciu'] = _t('OK instalează')
		if areSursa(catalog, p):
			d['indiciu'] = ' · '.join(x for x in (d['indiciu'], _t('INFO descarcă sursa')) if x)
	elif fel == 'fisier':
		f = obj
		rand = [(_t('Extensie'), f.nume or _t('necunoscut')), (_t('Versiune'), f.versiune),
			(_t('Mărime'), P.marime_text(f.marime)),
			(_t('Fișierul'), f.cale_text)]
		d['etichete'] = [a for a, b in rand if b]
		d['valori'] = [b for a, b in rand if b]
		d.update(icoana='fisier', titlu=f.titlu, insigna=_t('%s, neverificat de HD Satelit') % _t(etichetaLoc(f.cale, f.retea)),
			culoare='chihlimbar', descriere=(f.rezumat + ('\n' + f.descriere if f.descriere else '')).strip())
		if not f.citit:
			# si un .ipk vechi (tar.gz) cu date mari inaintea lui control ajunge aici (citirea se opreste la 16 MB)
			d.update(insigna=_t('Detaliile extensiei nu s-au putut citi'), culoare='rau',
				descriere=_t('Se poate încerca instalarea. Dacă fișierul este stricat, opkg îl refuză și nu se schimbă nimic.'))
		d['indiciu'] = _t('OK instalează fișierul')
		if getattr(f, 'python2', None):
			d.update(insigna=_t(INSIGNA_PYTHON2), culoare='rau', descriere=descrierePython2(catalog, fel, obj, extra),
				indiciu=_indiciuPython2(catalog, fel, obj, extra))
		if not f.utf8:
			d.update(insigna=_t('Numele fișierului nu se poate citi'), culoare='rau',
				indiciu=_t('Redenumește fișierul fără diacritice'),
				descriere=_t('Stick-ul a fost scris pe un sistem care păstrează literele altfel. Redenumește fișierul '
				'pe calculator, fără diacritice, apoi apasă albastru ca să cauți din nou.'))
	elif fel == 'sursa':
		nume, adresa = obj
		eticheta, _a, hds = sursa(catalog, nume)
		n = sum(1 for p in catalog._toate.values() if p.sursa == nume)
		fisier = catalog.configurare.fisier_sursa.get(nume, '')
		lista = varstaLista(catalog, nume)
		rand = [(_t('Nume'), nume), (_t('Adresa'), adresa), (_t('Extensii'), str(n) if lista else ''), (_t('Lista'), lista or _t('nedescărcată')),
			(_t('Fișierul'), fisier)]
		d['etichete'] = [a for a, b in rand if b]
		d['valori'] = [b for a, b in rand if b]
		if hds:
			d.update(insigna=_t('Feedul oficial HD Satelit'), culoare='bun',
				descriere=_t('Extensiile făcute și verificate de HD Satelit pentru acest receptor.'))
		else:
			d.update(insigna=_t('Feed extern, neverificat de HD Satelit'), culoare='chihlimbar',
				descriere=_t('Extensiile din acest feed nu sunt verificate de HD Satelit. Instalează doar ce cunoști.'))
		d.update(icoana='surse', titlu=eticheta if hds else nume)
		if catalog.configurare.e_a_utilizatorului(nume):
			d['indiciu'] = _t('Roșu șterge feedul · Albastru descarcă lista')
		else:
			d['indiciu'] = _t('Albastru descarcă lista')
	elif fel == 'feed':
		d.update(detaliiFeed(catalog, obj))
	elif fel == 'actualizeaza':
		d.update(icoana='actualizari', titlu=_t('Actualizează tot'), descriere=_t('Se instalează versiunea nouă pentru toate '
			'extensiile de mai jos.'), indiciu=_t('OK actualizează'))
	elif fel == 'dinfisier':
		d.update(icoana='fisier', titlu=_t('Din fișier'),
			descriere=_t('Instalezi un fișier .ipk de pe stick, de pe disc sau din memoria receptorului (/tmp). '
				'Pentru dosarele de rețea, alege Caută și în rețea.'), indiciu=_t('OK deschide'))
	elif fel == 'pluginsurse':
		d.update(icoana='surse', titlu=_t('Mai multe feeduri, automat'), descriere=_t('În feedul Monea Software există un plugin '
			'care adaugă singur mai multe feeduri. Îl găsești la Disponibile.'), indiciu=_t('OK îl arată'))
	elif fel == 'adauga':
		d.update(icoana='surse', titlu=_t('Adaugă un feed'), insigna=_t('Feed de pe internet'), culoare='eticheta',
			descriere=_t('Scrii un nume scurt și adresa feedului (începe cu http:// sau https://). Extensiile din el apar '
			'apoi la Disponibile, cu numele feedului. Nu sunt verificate de HD Satelit.'), indiciu=_t('OK adaugă'))
	elif fel == 'filtru':
		fila, aratate, total = extra
		activ = filtruActiv(obj, fila)
		rand = [(_t('Feedul'), numeFeedFiltru(obj.get('feed') or ''))]
		if fila in FILE_AMESTECATE:
			rand.append((_t('Felul'), numeFelFiltru(obj.get('fel') or '')))
		rand.append((_t('Arătate'), _t('%d din %d') % (aratate, total)))
		d['etichete'] = [a for a, b in rand]
		d['valori'] = [b for a, b in rand]
		d.update(icoana='liste', titlu=_t('Filtrul listei'), insigna=_t('Activ') if activ else _t('Toate extensiile'),
			culoare='chihlimbar' if activ else 'eticheta',
			descriere=_t('Arată numai extensiile dintr-un feed (HD Satelit, Monea Software, feedurile tale) sau de un anumit '
			'fel. Filtrul rămâne cât stai în Extensii și se aplică în toate filele cu extensii.'),
			indiciu=_t('OK alege · Roșu arată tot') if activ else _t('OK alege'))
	return d


def stareFeed(catalog, f):
	"""starea unui feed pe intelesul omului, pentru randul lui: cate pluginuri are, "Niciun plugin deocamdată" cand
	lista lui e descarcata dar goala (sau nu are ce arata pe acest receptor), "Lista nedescărcată" numai cand nicio
	lista a lui nu exista si nici nu s-a descarcat nimic in aceasta sesiune"""
	nume = set(f.nume())
	n = sum(1 for p in catalog.pachete.values() if p.sursa in nume)
	if n:
		return _pluginuri(n)
	if any(x in catalog.surse_cu_lista for x in nume) or (STARE.get('descarcare') or {}).get('cand'):
		return _t('Niciun plugin deocamdată')
	return _t('Lista nedescărcată')


def _baza_si_arhitectura(adresa):
	a = (adresa or '').rstrip('/')
	if '/' not in a.split('://', 1)[-1]:
		return a, ''
	return a.rsplit('/', 1)


def detaliiFeed(catalog, f):
	"""detaliile unui rand de feed: adresa (fara arhitectura), arhitecturile alese de receptor, canalul de proba (numai
	o mentiune), pluginurile, lista, fisierele"""
	baze, arh, proba = [], [], []
	for _n, a in f.surse:
		b, x = _baza_si_arhitectura(a)
		tinta = proba if ('/proba/' in b + '/' or b.endswith('-proba')) else baze
		if b not in tinta:
			tinta.append(b)
		if x and x not in arh:
			arh.append(x)
	nume = set(f.nume())
	n = sum(1 for p in catalog.pachete.values() if p.sursa in nume)
	vechime = 0
	for x in nume:
		try:
			vechime = max(vechime, os.path.getmtime(os.path.join(catalog.configurare.lists_dir, x)))
		except (OSError, TypeError):
			pass
	fisiere = []
	for x in f.nume():
		b = os.path.basename(catalog.configurare.fisier_sursa.get(x, ''))
		if b and b not in fisiere:
			fisiere.append(b)
	rand = [(_t('Adresa'), b) for b in baze[:2]]
	rand += [(_t('Probă'), b) for b in proba[:1]]
	rand += [(_t('Arhitecturi'), ', '.join(arh)), (_t('Pluginuri'), str(n) if n else stareFeed(catalog, f)),
		(_t('Lista'), P.text_varsta(vechime) if vechime else _t('nedescărcată')), (_t('Fișierele'), ', '.join(fisiere))]
	d = {'icoana': 'surse', 'titlu': numeFeed(f), 'etichete': [a for a, b in rand if b], 'valori': [b for a, b in rand if b],
		'indiciu': _t('OK sau Albastru descarcă lista')}
	if f.id == FEED_HDS:
		d.update(insigna=_t('Feedul oficial HD Satelit'), culoare='bun',
			descriere=_t('Extensiile făcute și verificate de HD Satelit pentru acest receptor.') + ' ' +
			_t('Receptorul alege singur adresele potrivite pentru procesorul și modelul lui.'))
	else:
		d.update(insigna=_t('Feed întreținut de Monea Software'), culoare='bun', descriere=_t(TEXT_EXTERNE))
	return d


def areSursa(catalog, p):
	"""pachetul are arhiva sursei langa el in feed (butonul "Descarcă sursa", tasta albastra)"""
	return _S().adresa_arhivei(catalog, p) is not None


def pachetCuSursa(catalog, fel, obj, extra):
	"""pachetul randului, cand are arhiva sursei (randurile pachet si plugin), altfel None"""
	p = obj if fel == 'pachet' else extra if fel == 'plugin' else None
	return p if p is not None and areSursa(catalog, p) else None


def taste(catalog, fel, obj, extra, pluginuri):
	"""(rosu, verde): actiunile randului, cu numele tastelor de pe televizor ('' = nimic). Pagina web are aceleasi
	actiuni, ca butoane. Randul cautarii in retea si fila Actualizari (verde: Actualizeaza tot) le pune fiecare capat."""
	rosu = verde = ''
	if fel == 'plugin':
		verde = N_('Actualizează') if extra is not None and extra.actualizare else N_('Deschide')
		if extra is not None and extra.se_poate_sterge:
			rosu = N_('Șterge')
	elif fel == 'indisponibil':
		if obj['fel'] == 'repornire':
			verde = N_('Repornește interfața')
		elif extra is not None and extra.actualizare:
			verde = N_('Actualizează')
		if extra is not None and extra.se_poate_sterge:
			rosu = N_('Șterge')
	elif fel == 'pachet':
		if extra == 'repornire':
			verde = N_('Repornește interfața')
		elif obj.actualizare:
			verde = N_('Actualizează')
		elif not obj.instalat and obj.se_poate_instala:
			verde = N_('Instalează')
		elif obj.instalat and pluginPentru(pluginuri, obj) is not None:
			verde = N_('Deschide')
		elif obj.instalat and (deschidereFaraPlugin(catalog, obj, texte=False) or {}).get('fel') in ('meniu', 'acces'):
			# intrarea pluginului din meniu sau ecranul modulelor de acces (tamiciav7, 14.11.2026)
			verde = N_('Deschide')
		elif python2Rand(fel, obj, extra) and inlocuitorRand(catalog, fel, obj, extra)[1] == 'instalabil':
			verde = BUTON_INLOCUITOR
		if obj.se_poate_sterge:
			rosu = N_('Șterge')
	elif fel == 'fisier':
		if python2Rand(fel, obj, extra):
			verde = BUTON_INLOCUITOR if inlocuitorRand(catalog, fel, obj, extra)[1] == 'instalabil' else ''
		else:
			verde = N_('Instalează') if obj.utf8 else ''
	elif fel == 'sursa':
		if catalog.configurare.e_a_utilizatorului(obj[0]):
			rosu = N_('Șterge feedul')
	elif fel == 'adauga':
		verde = N_('Adaugă')
	elif fel == 'actualizeaza':
		verde = N_('Actualizează tot')
	elif fel in ('dinfisier', 'pluginsurse'):
		verde = N_('Deschide')
	elif fel == 'filtru':
		verde = N_('Filtrează')
		if filtruActiv(obj, extra[0]):
			rosu = N_('Arată tot')
	return rosu, verde


def tastaAlbastra(catalog, fel, obj, extra):
	"""numele tastei albastre pe rand: "Descarcă sursa" la un pachet cu arhiva sursei, altfel '' (fiecare capat pune
	actiunea lui obisnuita: Descarcă lista, Caută fișiere)"""
	return N_('Descarcă sursa') if pachetCuSursa(catalog, fel, obj, extra) is not None else ''


def descarcareSursa(catalog, fel, obj, extra, **kw):
	"""(Descarcare, None) pornita pentru pachetul randului, sau (None, motiv)"""
	p = pachetCuSursa(catalog, fel, obj, extra)
	if p is None:
		return None, _t(_S().TEXT_NEGASIT)
	titlu = obj.name if fel == 'plugin' and getattr(obj, 'name', '') else p.titlu
	return _S().noua(catalog, p, titlu, sursaPachet(catalog, p)[0], **kw)


# ---------------------------------------------------------------- pachetele numai pentru Python 2 (0.6.8)
# Recunoasterea e in Components/HdsPython2.py (prin HdsPachete: Pachet.python2 dupa lista, FisierIpk.python2 dupa
# fisier). Aici: textele (aceleasi pe televizor si in pagina web), inlocuitorul din feedurile noastre si planul ferestrei.
# Un pachet dintr-o sursa straina se descarca intai (opkg --download-only) si se citeste inainte de instalare (Lucrare).
INSIGNA_PYTHON2 = N_('Făcut pentru Python 2')
TITLU_PYTHON2 = N_('%s este făcut pentru Python 2')
# 0.7.5 (MA9, TODO 06.11 05:30, raportul 919342): un pachet cu module .so facute numai pentru alt Python 3 nu se instaleaza.
# Incarcarea lor e oprita deja (Components/HdsAltPython.py, a06e48570, 693c5e6bf), dar pluginul instalat nu mergea si
# lasa fisiere straine; acum omul afla inainte, din fila Din fisier si la pachetele surselor straine (dupa descarcare).
TITLU_ALT_PYTHON = N_('%s este făcut pentru alt Python')
TEXT_ALT_PYTHON = N_('%(nume)s nu se instalează: e făcut pentru Python %(alt)s, iar imaginea are Python %(acum)s. '
	'Cere autorului varianta pentru Python %(acum)s.')


def pythonAcum():
	import sys
	return '%d.%d' % tuple(sys.version_info[:2])


# 0.7.5 (CTU, TODO 15.11 07:08, Ustym 4K PRO raportul 340957): un pachet care ar inlocui pachetele Python de care porneste
# interfata (python3-attrs, twisted si dependintele lor, Components/HdsPachetePornire.py) nu se instaleaza: un attrs strain
# a oprit interfata la fiecare pornire, chiar si in modul sigur.
TITLU_PORNIRE = N_('%s ar opri pornirea interfeței')
TEXT_PORNIRE = N_('%(nume)s nu se instalează: ar înlocui %(pachet)s al imaginii (%(motiv)s), iar fără el interfața nu mai '
	'pornește. Pachetele Python ale imaginii vin numai din actualizările HD Satelit.')
MOTIVE_PORNIRE = {
	'nume': N_('versiunea %(versiune)s în locul celei din imagine, %(instalata)s'),
	'inlocuieste': N_('pachetul spune că îl înlocuiește'),
	'fisiere': N_('are fișierul lui %(fisier)s'),
}


def refuzPornire(cale, radacina='/'):
	"""None, sau ce ar inlocui pachetul din pachetele pornirii (HdsPachetePornire.verifica); o eroare nu opreste nimic"""
	try:
		try:
			from Components import HdsPachetePornire
		except ImportError:  # probe pe PC
			import HdsPachetePornire
		return HdsPachetePornire.verifica(cale, radacina)
	except Exception as e:
		_jurnal('pachetele pornirii: %s' % e)
		return None


def textPornire(nume, r):
	"""mesajul refuzului unui pachet care ar inlocui pachetele pornirii (acelasi pe televizor si in pagina web)"""
	motiv = _t(MOTIVE_PORNIRE.get(r.get('fel'), MOTIVE_PORNIRE['inlocuieste'])) % {
		'versiune': r.get('versiune') or '?', 'instalata': r.get('instalata') or '?', 'fisier': r.get('fisier') or ''}
	return _t(TEXT_PORNIRE) % {'nume': nume or r.get('pachet') or _t('Extensia'), 'pachet': r.get('inlocuit') or '?',
		'motiv': motiv}


def textAltPython(nume, alt):
	"""mesajul refuzului unui pachet facut pentru alt Python 3 (acelasi pe televizor si in pagina web)"""
	return _t(TEXT_ALT_PYTHON) % {'nume': nume or _t('Extensia'), 'alt': alt, 'acum': pythonAcum()}


TEXT_PYTHON2 = (N_('Extensia e făcută pentru imaginile vechi, cu Python 2.'),
	N_('Imaginea aceasta are Python 3, deci nu se instalează.'))
BUTON_INLOCUITOR = N_('Instalează înlocuitorul')
TEXT_VERIFICARE = N_('Se verifică extensia înainte de instalare.')
MOTIVE_PYTHON2 = {
	'dependinta': N_('cere %s'),
	'biblioteca': N_('e o bibliotecă Python 2'),
	'dosar': N_('are fișiere în dosarul Python 2'),
	'compilat': N_('are fișiere compilate pentru Python 2 (%s)'),
	'legat': N_('e legat de biblioteca Python 2 (%s)'),
	'sursa': N_('codul nu se compilează în Python 3 (%s)'),
	'module': N_('folosește module scoase din Python 3 (%s)'),
	'feed': N_('vine dintr-un feed al imaginilor cu Python 2 (%s)'),
}


def textPython2():
	"""mesajul scurt, in limba receptorului: facut pentru imaginile vechi, cu Python 2; aici e Python 3"""
	return ' '.join(_t(x) for x in TEXT_PYTHON2)


def textMotiv(motiv):
	"""motivul (cod, detaliu) din Components/HdsPython2.py, pe intelesul omului; '' cand nu e"""
	cod, detaliu = motiv or (None, '')
	t = MOTIVE_PYTHON2.get(cod)
	if not t:
		return ''
	t = _t(t)
	return t % P._curat(detaliu or '', 60) if '%s' in t else t


def dinFeedurileNoastre(catalog, p):
	"""pachetul vine din feedul HD Satelit sau din feedul pluginurilor externe (Monea Software)"""
	return p is not None and bool(p.sursa) and \
		felFeed(catalog, p.sursa, catalog.configurare.adresa(p.sursa)) in (FEED_HDS, FEED_EXTERN)


def dinSursaStraina(catalog, p):
	"""pachetul vine din alta sursa decat feedurile noastre (adaugata de om sau alta): se verifica inainte de instalare"""
	return p is not None and bool(p.sursa) and not dinFeedurileNoastre(catalog, p)


def _feedScurt(catalog, p):
	return 'HD Satelit' if felFeed(catalog, p.sursa, catalog.configurare.adresa(p.sursa)) == FEED_HDS else 'Monea Software'


def inlocuitor(catalog, nume, dosare=()):
	"""(pachet, 'instalabil' | 'instalat') al inlocuitorului pentru Python 3 din feedurile noastre, sau (None, None).
	Candidatii: Components/HdsPython2.candidati (acelasi nume, fara sufixul vechi, tabelele facute din date). Numai
	cand pachetul ales de opkg pentru acel nume (cel din catalog, versiunea cea mai noua) e chiar cel din feedurile
	noastre si nu e pentru Python 2: asa butonul nu poate instala niciodata pachetul vechi."""
	if catalog is None:
		return None, None
	for c in P.H.candidati(nume, dosare):
		p = catalog._toate.get(c)
		if p is None or p.python2 or not dinFeedurileNoastre(catalog, p) or not P.se_arata(p.nume):
			continue
		if p.instalat and not p.actualizare:
			return p, 'instalat'
		if p.se_poate_instala:
			return p, 'instalabil'
	return None, None


def notaInlocuitor(catalog, p, stare):
	if stare == 'instalabil':
		return _t('Pentru Python 3 există %s, în feedul %s.') % (numeCuVersiune(p.titlu, p.versiune), _feedScurt(catalog, p))
	if stare == 'instalat':
		return _t('%s, făcut pentru Python 3, este deja instalat.') % p.titlu
	return ''


def planPython2(catalog, titlu, subtitlu, versiune, motiv, nume, dosare=(), icoana='altele'):
	"""Fereastra unui pachet numai pentru Python 2 (in locul confirmarii instalarii): de ce nu se instaleaza si, cand
	exista, inlocuitorul pentru Python 3 cu butonul lui. Nu porneste niciun opkg (argumente None)."""
	inl, stare = inlocuitor(catalog, nume, dosare)
	rand = [(_t('Extensie'), nume or ''), (_t('Versiune'), versiune or ''), (_t('Motivul'), textMotiv(motiv))]
	return {'fel': 'python2', 'titlu': _t(TITLU_PYTHON2) % titlu, 'nume': titlu, 'subtitlu': textPython2(),
		'icoana': icoana, 'randuri': [r for r in rand if r[1]], 'nota': notaInlocuitor(catalog, inl, stare),
		'notaCuloare': 'bun', 'externe': [], 'buton': BUTON_INLOCUITOR if stare == 'instalabil' else None,
		'inlocuitor': inl.nume if stare == 'instalabil' else None, 'argumente': None, 'repornire': False,
		'pachete': [], 'tinte': []}


def python2Rand(fel, obj, extra=None):
	"""motivul (cod, detaliu) cand randul e un pachet neinstalat sau un fisier numai pentru Python 2, altfel None"""
	if fel == 'pachet' and extra != 'repornire' and not obj.instalat:
		return obj.python2
	if fel == 'fisier':
		return getattr(obj, 'python2', None)
	return None


def inlocuitorRand(catalog, fel, obj, extra=None):
	"""(pachet, stare) al inlocuitorului pentru randul unui pachet sau fisier numai pentru Python 2, altfel (None, None)"""
	if not python2Rand(fel, obj, extra):
		return None, None
	if fel == 'fisier':
		v = obj.verdict
		return inlocuitor(catalog, obj.nume, v.dosare if v is not None else ())
	return inlocuitor(catalog, obj.nume)


def _indiciuPython2(catalog, fel, obj, extra=None):
	if inlocuitorRand(catalog, fel, obj, extra)[1] == 'instalabil':
		return _t('OK arată de ce · Verde instalează înlocuitorul')
	return _t('OK arată de ce')


def descrierePython2(catalog, fel, obj, extra=None):
	"""textul detaliilor unui rand numai pentru Python 2: mesajul, motivul, inlocuitorul"""
	parti = [textPython2()]
	m = textMotiv(python2Rand(fel, obj, extra))
	if m:
		parti.append('%s: %s' % (_t('Motivul'), m))
	inl, stare = inlocuitorRand(catalog, fel, obj, extra)
	nota = notaInlocuitor(catalog, inl, stare)
	if nota:
		parti.append(nota)
	return '\n'.join(parti)


def planPython2Pachet(catalog, p, motiv=None):
	return planPython2(catalog, p.titlu, p.subtitlu, p.versiune, motiv or p.python2, p.nume, (),
		P.ICOANE.get(p.categorie, 'altele'))


def planPython2Fisier(catalog, f):
	v = f.verdict
	return planPython2(catalog, f.titlu, f.rezumat, f.versiune, f.python2, f.nume, v.dosare if v is not None else (),
		'fisier')


# 0.7.4 (decizia 5 a lotului traducatorului): pachetul vechi care cere pachete Python 2 (python-core, python-twisted-web ...) se
# instaleaza cu perechile lor din Python 3, intr-o singura comanda: opkg install --force-depends <perechile> <pachetul>; pluginul
# se traduce apoi singur la prima incarcare (Components/HdsPython2Traducere.py). Perechile se iau numai daca sunt instalate sau
# daca versiunea lor cea mai noua vine din feedurile noastre (ca la Components/HdsModuleLipsa.py: o sursa straina nu poate da un
# "python3-x"). Ce nu are pereche nu opreste instalarea: se spune pe randul "Python 2" al ferestrei (televizor si pagina web, din
# acelasi plan); un modul care chiar lipseste il aduce la incarcare HdsModuleLipsa. Fara dependinte Python 2: nimic schimbat.
TEXT_PERECHI = N_('se mai instalează %s, apoi se traduce singură')
TEXT_FARA_PERECHI = N_('se traduce singură la prima pornire')
TEXT_FARA_PERECHE = N_('fără pereche pentru Python 3: %s')
OPKG_INFO = '/var/lib/opkg/info'


def perechiPython3(catalog, dependinte, radacina='/'):
	"""(de instalat, fara pereche) pentru pachetele Python 2 `dependinte`: perechile python3 care nu sunt inca instalate (din
	feedurile noastre) si numele Python 2 fara pereche. Fara catalog se socotesc numai pachetele instalate."""
	if not dependinte:
		return [], []
	instalate = getattr(catalog, 'python3_instalate', None) if catalog is not None else None
	lista = (getattr(catalog, 'python3', None) or {}) if catalog is not None else {}

	def eInstalat(n):
		if instalate is not None:
			return n in instalate
		return os.path.exists(P._cale(radacina, '%s/%s.control' % (OPKG_INFO, n)))

	def bune(n):
		if not P.nume_valid(n):
			return False
		if eInstalat(n):
			return True
		x = lista.get(n)
		return x is not None and felFeed(catalog, x[1], catalog.configurare.adresa(x[1])) in (FEED_HDS, FEED_EXTERN)
	alese, fara = P.H.perechi(dependinte, bune)
	return [n for n in alese if not eInstalat(n)], fara


def randPython2(perechi, fara):
	"""randul "Python 2" al ferestrei: ce se mai instaleaza (si ca pluginul se traduce), ce nu are pereche"""
	parti = [_t(TEXT_PERECHI) % ', '.join(perechi) if perechi else _t(TEXT_FARA_PERECHI)]
	if fara:
		# intai: o tema straina, fara randurile care deruleaza, scurteaza valoarea la sfarsit
		parti.insert(0, _t(TEXT_FARA_PERECHE) % ', '.join(fara))
	return ('Python 2', '; '.join(parti))


def dependintePython2(pachete):
	"""pachetele Python 2 cerute de pachetele date (Pachet.dependinte_py2 / FisierIpk.dependinte_py2), fara repetari"""
	rez = []
	for x in pachete:
		for d in getattr(x, 'dependinte_py2', None) or ():
			if d not in rez:
				rez.append(d)
	return rez


# ---------------------------------------------------------------- planurile confirmarilor

def motivOcupat(descarcare=None, program=None):
	"""None cand opkg poate porni acum, altfel (mesaj, culoare): o descarcare a listei sau o alta lucrare in curs (de
	pe televizor sau din pagina), ori o imagine fara opkg. `descarcare`: a ecranului care intreaba."""
	if descarcare is not None or descarcareInCurs():
		return _t('Așteaptă să se termine descărcarea listei.'), 'chihlimbar'
	if lucrareInCurs():
		return _t('Altă instalare rulează acum. Așteaptă să se termine.'), 'chihlimbar'
	if not (program or opkgProgram)():
		return _t('Instalarea extensiilor nu este disponibilă în această imagine.'), 'chihlimbar'
	return None


def titluri(catalog):
	"""numele pachetelor -> titlurile din lista, ca jurnalul instalarii sa spuna DAB+ din satelit, nu numele pachetului"""
	return dict((n, p.titlu) for n, p in catalog._toate.items())


def _nota(catalog, pachete, nota):
	return nota(pachete) if nota is not None else ''


def planInstalare(catalog, p, argumente=None, nota=None):
	"""(plan, None) sau (None, (mesaj, culoare)). `argumente`: opkgArguments (ecranul da functia lui); `nota`:
	functia capatului care scrie nota din surseExterne()."""
	dep = catalog.dependente_de_instalat(p)
	# un pachet numai pentru Python 2 (sau care cere unul): fereastra cu motivul si inlocuitorul, fara opkg (0.6.8)
	if p.python2:
		return planPython2Pachet(catalog, p), None
	for d in dep:
		if d.python2:
			return planPython2Pachet(catalog, p, (P.H.DEPENDINTA, d.nume)), None
	py2 = dependintePython2([p] + dep)
	perechi, fara = perechiPython3(catalog, py2)
	optiuni = optiuniTema(p.nume, ('--force-depends',) if py2 else ())
	a = (argumente or opkgArguments)('install', (perechi if py2 else []) + [p.nume], optiuni)
	if a is None:
		return None, (_t('Numele extensiei nu este valid. Nu se instalează.'), 'rau')
	total = p.marime + sum(d.marime for d in dep)
	s, _hds = randSursa(catalog, p)
	rand = [(_t('Versiune'), p.versiune), (_t('Mărime'), P.marime_text(total) or _t('necunoscută')), (_t('Feed'), s)]
	if dep:
		rand.append((_t('Se mai instalează'), ', '.join(d.titlu for d in dep[:3]) + (' ' + _t('și încă %d') % (len(dep) - 3) if len(dep) > 3 else '')))
	if py2:
		rand.append(randPython2(perechi, fara))
	plan = {'fel': 'instaleaza', 'titlu': _t('Instalezi %s?') % p.titlu, 'nume': p.titlu, 'subtitlu': p.subtitlu,
		'icoana': P.ICOANE.get(p.categorie, 'altele'), 'randuri': rand, 'nota': _nota(catalog, [p] + dep, nota),
		'externe': surseExterne(catalog, [p] + dep), 'notaCuloare': culoareNota(catalog, [p] + dep),
		'buton': N_('Instalează'), 'argumente': a,
		'repornire': any(x.categorie not in FARA_REPORNIRE_INSTALARE for x in [p] + dep),
		'pachete': [p.nume], 'tinte': [_tinta(p)]}
	_cuVerificare(catalog, plan, [p] + dep, 'install', [p.nume], argumente, optiuni)
	return plan, None


def optiuniTema(nume, optiuni=(), actualizare=False):
	"""Optiunile opkg ale unei teme (enigma2-plugin-skins-*), ca in imaginile OE-Alliance: --force-overwrite (tema poate
	aduce un fisier pe care imaginea il are; HdsTemeSuprascrise il copiaza inainte si il pune la loc dupa stergerea temei)
	si, la instalare, --force-reinstall (o incercare veche cazuta lasa tema „half-installed” si opkg n-o mai ia). Numai la
	teme; optiunea se aplica intregii comenzi, deci si dependintelor aduse odata cu tema (de pilda OAWeather)."""
	if not TS.eTema(nume):
		return tuple(optiuni)
	return tuple(optiuni) + (TS.OPTIUNI_ACTUALIZARE if actualizare else TS.OPTIUNI_INSTALARE)


def deVerificat(catalog, p):
	"""pachetul se descarca si se citeste inainte de instalare: vine dintr-o sursa straina, e o extensie sau un plugin
	de sistem (cod Python) si lista nu spune pentru ce Python e (nici Depends, nici feedul unei imagini cu Python 2)"""
	return dinSursaStraina(catalog, p) and p.categorie in P.H.FELURI_VERIFICATE and p.python2 is None


def _cuVerificare(catalog, plan, pachete, comanda, nume, argumente=None, optiuni=()):
	"""Un pachet dintr-o sursa straina se descarca intai (opkg --download-only) si se citeste din cache-ul opkg, inainte
	de instalare (Lucrare): dupa Depends se vede numai o parte din pachetele pentru Python 2 (masurat: 34 din 69).
	`optiuni`: --force-depends pentru un pachet cu dependinte Python 2 (fara ea opkg nu descarca nimic: nimeni nu da
	python-core). Cu --force-overwrite (o tema) pachetul se descarca intai si din feedurile noastre: din el se afla ce
	fisiere ale imaginii suprascrie, ca sa fie copiate inainte (HdsTemeSuprascrise)."""
	teme = '--force-overwrite' in optiuni
	if not teme and not any(deVerificat(catalog, x) for x in pachete):
		return
	v = (argumente or opkgArguments)(comanda, nume, ('--download-only',) + tuple(optiuni))
	if v is not None:
		plan['verifica'] = v
		if teme:
			plan['teme'] = True
		plan['catalog'] = catalog
		# numele fisierelor din liste: opkg 0.8.0 pastreaza in cache data serverului, nu pe cea a descarcarii, si nu
		# scrie mereu randul "Downloading" (masurat pe receptorul de proba): asa se recunoaste si un pachet
		# ramas in cache
		plan['fisiere'] = [os.path.basename(x.fisier) for x in pachete if x.fisier]


def planActualizare(catalog, pachete, argumente=None, nota=None):
	"""(plan, None), (None, (mesaj, culoare)) sau (None, None) cand nu e nimic de actualizat"""
	pachete = [p for p in pachete if p.actualizare and P.nume_valid(p.nume)]
	if not pachete:
		return None, None
	# numai teme: --force-overwrite, ca la instalare (o versiune noua poate aduce alt fisier al imaginii); amestecate cu
	# alte extensii („Actualizează toate”): fara, ca optiunea sa nu ajunga la ele (o tema instalata tine deja fisierele ei)
	optiuni = optiuniTema(pachete[0].nume, actualizare=True) if all(TS.eTema(p.nume) for p in pachete) else ()
	a = (argumente or opkgArguments)('upgrade', [p.nume for p in pachete], optiuni)
	if a is None:
		return None, (_t('Un nume de extensie nu este valid. Nu se actualizează.'), 'rau')
	total = sum(p.marime for p in pachete)
	surse = []
	for p in pachete:
		s = sursaPachet(catalog, p)[0] if len(pachete) > 1 else randSursa(catalog, p)[0]
		if s not in surse:
			surse.append(s)
	if len(pachete) == 1:
		p = pachete[0]
		titlu, nume, sub, ic = (_t('Actualizezi %s?') % p.titlu, p.titlu, p.subtitlu,
			P.ICOANE.get(p.categorie, 'altele'))
		rand = [(_t('Versiune'), _t('%s (acum %s)') % (p.versiune, p.versiune_instalata))]
	else:
		# "Actualizeaza toate": lista lor, fiecare cu versiunea noua (cel mult trei randuri, apoi "si inca N")
		titlu, nume, sub, ic = (_t('Actualizezi %d extensii?') % len(pachete),
			_t('%d extensii') % len(pachete), '', 'actualizari')
		lista = [numeCuVersiune(p.titlu, p.versiune) for p in pachete]
		if len(lista) > 3:
			lista = lista[:2] + [_t('și încă %d') % (len(lista) - 2)]
		rand = [(_t('Extensii') if k == 0 else '', x) for k, x in enumerate(lista)]
	rand += [(_t('Mărime'), P.marime_text(total) or _t('necunoscută')), (_t('Feed'), ', '.join(surse))]
	plan = {'fel': 'actualizeaza', 'titlu': titlu, 'nume': nume, 'subtitlu': sub, 'icoana': ic, 'randuri': rand,
		'nota': _nota(catalog, pachete, nota), 'externe': surseExterne(catalog, pachete),
		'notaCuloare': culoareNota(catalog, pachete), 'buton': N_('Actualizează'), 'argumente': a,
		'repornire': any(p.categorie not in FARA_REPORNIRE_SCHIMBARE for p in pachete),
		'textGata': _t('Gata. Extensiile sunt la zi.') if len(pachete) > 1 else None,
		'pachete': [p.nume for p in pachete], 'tinte': [_tinta(p) for p in pachete]}
	# o versiune noua dintr-o sursa straina se citeste inainte (o actualizare numai pentru Python 2 ar strica pluginul)
	_cuVerificare(catalog, plan, pachete, 'upgrade', [p.nume for p in pachete], argumente, optiuni)
	return plan, None


def planStergere(catalog, p, argumente=None):
	a = (argumente or opkgArguments)('remove', [p.nume], ('--autoremove',))
	if a is None:
		return None, (_t('Numele extensiei nu este valid. Nu se șterge.'), 'rau')
	s, _hds = randSursa(catalog, p)
	rand = [(_t('Versiune'), p.versiune_instalata)]
	# pachetele fara Installed-Size in starea opkg: marimea din fisierele lor; fara ea randul lipseste
	marime = P.marime_text(p.marime_instalat or P.marime_din_fisiere(p.nume))
	if marime:
		rand.append((_t('Eliberează'), marime))
	rand.append((_t('Feed'), s))
	note = []
	if p.din_imagine:
		note.append(_t('Face parte din imagine.'))
	if p.disponibil:
		note.append(_t('O poți instala din nou oricând, din același feed.'))
	else:
		note.append(_t('Nu se află în niciun feed, deci nu se va mai putea instala din nou de aici.'))
	return {'fel': 'sterge', 'titlu': _t('Ștergi %s?') % p.titlu, 'nume': p.titlu, 'subtitlu': p.subtitlu,
		'icoana': P.ICOANE.get(p.categorie, 'altele'), 'randuri': rand, 'nota': ' '.join(note), 'externe': [],
		'buton': N_('Șterge'), 'argumente': a, 'repornire': p.categorie not in FARA_REPORNIRE_SCHIMBARE,
		'implicitRenunta': True, 'pachete': [p.nume], 'tinte': [_tinta(p)]}, None


def _tinta(p):
	"""un pachet al planului: numele, titlul, versiunea de dupa (la) si de dinainte (de), daca e modul de acces"""
	return {'nume': p.nume, 'titlu': p.titlu, 'la': p.versiune or '', 'de': p.versiune_instalata or '',
		'acces': p.categorie == 'acces'}


def versiuneScurta(versiune):
	"""Versiunea fara partea de git a constructiei, pentru titlul de la sfarsitul lucrarii, care are un rand
	(2.4.1-git376+006598e-r1 -> 2.4.1); versiunea intreaga sta in randul de sub titlu si in jurnal."""
	return re.split(r'[-+~]git|\+', versiune or '', maxsplit=1)[0]


def numeCuVersiune(titlu, versiune):
	"""numele pachetului cu versiunea, pentru mesaje: "DAB+ din satelit 0.1.6"; cand versiunea e deja in nume
	("Alfa 2.26.09-11968"), numai numele"""
	v = (versiune or '').split(':')[-1]
	baza = v.rsplit('-', 1)[0] if re.search(r'-r[0-9]', v) else v
	cifre = re.findall(r'[0-9]+', baza)
	titlu = titlu or ''
	if not cifre:
		return titlu
	if '.'.join(cifre[:2]) in titlu:
		return titlu
	return ('%s %s' % (titlu, baza)).strip()


def rezultatePachete(plan, radacina='/'):
	"""([tintele facute], [tintele nefacute]) dupa opkg, din starea pachetelor: instalat sau actualizat = versiunea din
	plan e instalata; sters = nu mai e instalat"""
	inst = {}
	try:
		conf = P.citeste_configurarea(radacina)
		for s in P.citeste_strofe(P._cale(radacina, conf.status_file)):
			st = s.get('status', '').split()
			if 'installed' in st and 'not-installed' not in st:
				inst[s.get('package', '')] = s.get('version', '')
	except Exception as e:
		_jurnal('starea pachetelor: %s' % e)
		return [], []
	bune, rele = [], []
	for t in plan.get('tinte') or []:
		if plan.get('fel') == 'sterge':
			facut = t['nume'] not in inst
		else:
			facut = inst.get(t['nume']) == t['la'] if t['la'] else t['nume'] in inst
		(bune if facut else rele).append(t)
	return bune, rele


# ---------------------------------------------------------------- rezumatul listei descarcate

def instantaneu(catalog):
	"""{nume: versiune} ale pachetelor din liste, inainte de descarcare (pentru "nou" in rezumat)"""
	if catalog is None:
		return None
	return dict((n, p.versiune) for n, p in catalog.pachete.items() if p.versiune)


def rezumatListe(catalog, inainte=None, maxim=5):
	"""Ce contine lista dupa descarcare, pe randuri, pentru fiecare feed si sursa singura: cate pluginuri si care (cu
	versiunea; cel mult `maxim`, apoi "si inca N"), cele noi (care nu erau in lista de dinainte) si cele cu actualizare.
	Acelasi text pe televizor si in pagina web."""
	randuri = [_t('Lista extensiilor s-a descărcat.')]
	grupe = [(numeFeed(f), set(f.nume())) for f in feeduri(catalog)] + [(n, {n}) for n, _a in surseSingure(catalog)]
	for nume_g, surse in grupe:
		pachete = sorted((p for p in catalog.pachete.values() if p.sursa in surse), key=lambda p: (p.titlu.lower(), p.nume))
		if not pachete:
			stare = _t('Niciun plugin deocamdată') if any(x in catalog.surse_cu_lista for x in surse) else \
				_t('lista nu s-a putut descărca')
			randuri.append('%s: %s' % (nume_g, stare))
			continue
		randuri.append('%s: %s' % (nume_g, _pluginuri(len(pachete))))
		for p in pachete[:maxim]:
			if p.actualizare:
				semn = _t('actualizare de la %s') % p.versiune_instalata
			elif inainte is not None and p.nume not in inainte:
				semn = _t('nou')
			elif p.instalat:
				semn = _t('instalat')
			else:
				semn = ''
			randuri.append('   %s%s' % (numeCuVersiune(p.titlu, p.versiune), ' (%s)' % semn if semn else ''))
		if len(pachete) > maxim:
			randuri.append('   ' + _t('și încă %d') % (len(pachete) - maxim))
	return '\n'.join(randuri)


def textDescarcare(catalog, stare, inainte=None):
	"""mesajul de la sfarsitul descarcarii listei (cerute de om): rezumatul, sau motivul pe intelesul omului si, daca
	s-a putut descarca macar o lista, rezumatul a ce este"""
	stare = stare or {}
	if stare.get('cod') == 0:
		return rezumatListe(catalog, inainte)
	motiv = stare.get('motiv') or _t('Lista extensiilor nu s-a putut descărca.')
	if catalog.surse_cu_lista:
		return motiv + '\n' + rezumatListe(catalog, inainte).split('\n', 1)[-1]
	return motiv


def planFisier(f, argumente=None, catalog=None):
	"""(plan, None) sau (None, (mesaj, culoare)). `catalog`: pentru inlocuitorul unui fisier numai pentru Python 2."""
	if not f.utf8:
		return None, (_t('Numele fișierului nu se poate citi pe receptor. Redenumește-l fără diacritice.'), 'rau')
	# fisierul numai pentru Python 2 (0.6.8): de obicei aflat deja pe firul cautarii; altfel citit acum
	verifica = getattr(f, 'verificaPython2', None)
	if verifica is not None:
		verifica(refa=True)
	if getattr(f, 'python2', None):
		return planPython2Fisier(catalog, f), None
	# 0.7.5: module .so facute numai pentru alt Python 3 (de pilda 3.7): nu se instaleaza (TODO 06.11 05:30)
	alt = P.H.alt_python(getattr(f, 'verdict', None))
	if alt:
		return None, (textAltPython(f.titlu, alt), 'rau')
	# 0.7.5 (CTU): pachetele Python de care porneste interfata nu se inlocuiesc (TODO 15.11 07:08)
	r = refuzPornire(getattr(f, '_citire', None) or f.cale, getattr(catalog, 'radacina', None) or '/')
	if r:
		return None, (textPornire(f.titlu, r), 'rau')
	cale = P.fisier_ipk_permis(f.cale)
	# 0.7.4: un fisier vechi care cere pachete Python 2: cu perechile python3 si --force-depends (vezi perechiPython3)
	py2 = dependintePython2([f])
	perechi, fara = perechiPython3(catalog, py2)
	optiuni = optiuniTema(getattr(f, 'nume', '') or '', ('--force-depends',) if py2 else ())
	if not cale:
		a = None
	else:
		a = (argumente or opkgArguments)('install', (perechi if py2 else []) + [cale], optiuni)
	if a is None:
		return None, (_t('Fișierul nu se poate instala de aici (nu mai există sau nu e pe stick, disc sau rețea).'), 'rau')
	rand = [(_t('Extensie'), f.nume or _t('necunoscut')), (_t('Versiune'), f.versiune or _t('necunoscută')),
		(_t('Mărime'), P.marime_text(f.marime)), (_t('Fișierul'), f.cale_text)]
	if py2:
		rand.append(randPython2(perechi, fara))
	return {'fel': 'fisier', 'titlu': _t('Instalezi %s?') % f.titlu, 'nume': f.titlu, 'subtitlu': f.rezumat,
		'icoana': 'fisier', 'randuri': [r for r in rand if r[1]],
		# intai fraza despre verificare: o cale lunga (pana la 255 de semne) o impingea sub marginea notei; calea
		# scurtata la mijloc, ca sa ramana numele fisierului
		'nota': _t('Nu este verificată de HD Satelit. Extensie dintr-un fișier %s: %s') % (deUnde(f.cale, f.retea),
			P.scurt_mijloc(f.cale_text, 70)),
		'externe': [], 'buton': N_('Instalează'), 'argumente': a, 'repornire': True, 'pachete': [f.nume or f.cale],
		'cale_fisier': cale, 'teme': '--force-overwrite' in optiuni}, None


# 0.7.4: un .ipk pus direct in /tmp (incarcat din pagina web sau copiat de om) sta in RAM pana la repornirea intreaga
# (/tmp e tmpfs: repornirea interfetei nu-l sterge). Dupa instalarea lui reusita din fila Din fisier se sterge. De pe
# stick, disc, retea sau din alte dosare nu se sterge nimic: sunt fisierele omului.
DOSARE_TMP = ('/tmp', '/var/volatile/tmp')


def stergeIpkDinTmp(cale, radacina='/'):
	"""Sterge fisierul .ipk `cale` (calea reala din P.fisier_ipk_permis) numai cand sta direct in /tmp, e un fisier
	obisnuit si nu e o legatura. True daca l-a sters."""
	if not isinstance(cale, str) or not cale.lower().endswith('.ipk') or posixpath.dirname(cale) not in DOSARE_TMP:
		return False
	p = P._cale(radacina, cale)
	try:
		import stat
		s = os.lstat(p)
		if not stat.S_ISREG(s.st_mode):
			return False
		os.remove(p)
		return True
	except OSError:
		return False


# 0.7.4 (randul 816, jurnalele testerilor din 31.10): extensiile din afara au uneori scripturile (preinst, postinst,
# prerm, postrm) scrise pe Windows: cu BOM in fata lui #!/bin/sh sau cu randuri CRLF. Shell-ul nu le poate porni
# („﻿#!/bin/sh: No such file or directory”), deci configurarea sau stergerea extensiei cade. Inainte de fiecare
# lucrare opkg, scripturile din dosarul info al lui opkg care au BOM sau CRLF se scriu din nou fara ele (acelasi mod de
# fisier, prin .nou si rename); celelalte nu se ating. Cel mult SCRIPT_MAXIM octeti pe script.
SCRIPTURI_PACHET = ('.preinst', '.postinst', '.prerm', '.postrm')
SCRIPT_MAXIM = 256 * 1024
BOM = b'\xef\xbb\xbf'
# randuri din iesirea unei lucrari incheiate cu codul 0 care arata ca scriptul extensiei n-a facut tot (o pagina HTML
# descarcata in locul arhivei, o arhiva taiata, o comanda care nu exista pe aceasta imagine): extensia e pusa, dar poate
# nu merge, deci rezultatul nu mai spune „Terminat fără erori.”
SEMNE_SCRIPT_RAU = ('invalid tar magic', 'truncated input file', 'not in gzip format', 'unexpected end of file',
	': command not found', 'syntax error')


def reparaScripturiPachete(radacina='/', dosar=None):
	"""Scoate BOM-ul si CR-urile din scripturile pachetelor din dosarul info al lui opkg. Intoarce numele reparate."""
	if dosar is None:
		try:
			dosar = P._cale(radacina, P.citeste_configurarea(radacina).info_dir)
		except Exception:
			dosar = P._cale(radacina, P.DOSAR_INFO)
	try:
		nume = sorted(os.listdir(dosar))
	except OSError:
		return []
	reparate = []
	for n in nume:
		if not n.endswith(SCRIPTURI_PACHET):
			continue
		cale = os.path.join(dosar, n)
		try:
			if os.path.islink(cale) or os.path.getsize(cale) > SCRIPT_MAXIM:
				continue
			with open(cale, 'rb') as f:
				date = f.read()
			if not (date.startswith(BOM) or b'\r' in date):
				continue
			nou = date[len(BOM):] if date.startswith(BOM) else date
			nou = nou.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
			mod = os.stat(cale).st_mode & 0o7777
			with open(cale + '.nou', 'wb') as f:
				f.write(nou)
			os.chmod(cale + '.nou', mod)
			os.replace(cale + '.nou', cale)
			reparate.append(n)
		except OSError as e:
			_jurnal('scriptul %s: %s' % (n, e))
	return reparate


def eroareScriptPachet(linii):
	"""Primul rand din iesire care arata o eroare a scriptului extensiei (SEMNE_SCRIPT_RAU), scurtat; '' daca nu e."""
	for linie in linii or ():
		text = linie if isinstance(linie, str) else str(linie)
		mic = text.lower()
		if any(s in mic for s in SEMNE_SCRIPT_RAU) or mic.lstrip().startswith('﻿#!'):
			return P._curat(text.strip(), 160)
	return ''


# ---------------------------------------------------------------- jurnalul opkg si pluginurile

def scrieJurnal(linie, sincron=False):
	"""iesirea opkg, intreaga, pentru service si pentru testeri: JURNAL_OPKG, in dosarul jurnalelor de pe memoria
	interna (ramane dupa repornire), cel mult P.MARIME_JURNAL plus o copie veche (.1); fara a urma o legatura simbolica
	pusa in locul fisierului; numele si parola din adresele surselor nu se scriu (P.fara_parola). sincron (fsync):
	numai randurile de rezumat (inceputul si sfarsitul lucrarii, avertismentele), ca sa ramana si dupa o repornire dura"""
	P.scrie_jurnal_rotit(JURNAL_OPKG, '%s %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'),
		P._curat(P.fara_parola(linie), 400)), P.MARIME_JURNAL, sincron)


def reincarcaPluginuri(plugins=None):
	"""dupa opkg: pluginurile sterse dispar imediat; cele noi apar imediat doar daca nu cer repornire (in imaginea
	aceasta, un plugin nou fara needsRestart=False apare dupa repornirea interfetei: plugins.restartRequired)"""
	try:
		if plugins is None:
			from Components.PluginComponent import plugins
		from Tools.Directories import resolveFilename, SCOPE_PLUGINS
		import importlib
		importlib.invalidate_caches()
		plugins.readPluginList(resolveFilename(SCOPE_PLUGINS))
		try:
			from Components import HdsLocuriLista
			HdsLocuriLista.curataOrfane()
		except Exception as e:
			print("[HdsExtensiiLucru] locurile extensiilor: %s" % e)
	except Exception as e:
		_jurnal('reincarcarea pluginurilor: %s' % e)
	return bool(getattr(plugins, 'restartRequired', False))


# ---------------------------------------------------------------- descarcarea listei (opkg update)

def pastreazaPanaLaSfarsit(ipkg):
	"""tine IpkgComponent-ul unei descarcari pana se termina (o singura data)"""
	if ipkg in _descarcari:
		return

	def cand(eveniment, _parametru):
		if eveniment == IpkgComponent.EVENT_DONE:
			ipkg.removeCallback(cand)
			if ipkg in _descarcari:
				_descarcari.remove(ipkg)
	_descarcari.append(ipkg)
	ipkg.addCallback(cand)


def descarcareInCurs():
	return any(d.isRunning() for d in _descarcari)


def pazesteListeleHds():
	"""dupa opkg update, listele surselor HD Satelit care nu sunt cele din ultima stare.json
	semnata se sterg (Components/HdsActualizari.pazeste_listele), ca un pachet pus pe serverul nostru de altcineva sa
	nu se vada si sa nu se instaleze din Extensii. 0.7.5 (FED): cand feedul se republica in timpul descarcarii, in locul
	listei noi se pune copia semnata de dinainte (pastreazaListeleHds). Intoarce numele listelor nepotrivite (sterse si
	puse la loc), pentru reincercare."""
	try:
		try:
			from Components.HdsActualizari import pazeste_listele, ULTIMA_PAZA
		except ImportError:
			from HdsActualizari import pazeste_listele, ULTIMA_PAZA
		sterse = pazeste_listele()
		puse = list(ULTIMA_PAZA.get('puse_la_loc') or [])
	except Exception as e:
		_jurnal('paza listelor HD Satelit: %s' % e)
		return []
	for nume in puse:
		scrieJurnal('lista %s pusa la loc (cea semnata de dinainte): lista noua nu e inca cea semnata de HD Satelit' % nume)
	for nume in sterse:
		scrieJurnal('lista %s stearsa: nu e cea semnata de HD Satelit' % nume)
	return list(sterse) + puse


def pastreazaListeleHds():
	"""chiar inainte de opkg update: copia listelor HD Satelit (Components/HdsActualizari.pastreaza_listele)"""
	try:
		try:
			from Components import HdsActualizari as A
		except ImportError:
			import HdsActualizari as A
		return A.pastreaza_listele()
	except Exception as e:
		_jurnal('copia listelor HD Satelit: %s' % e)
		return []


def pornesteDescarcarea(ipkg=None, inainte=None, rezerva=False, reincercare=False):
	"""opkg update. `ipkg`: IpkgComponent-ul ecranului, cu ascultatorul lui pus deja; altfel unul nou (pagina).
	Descarcarea se tine aici pana la sfarsit, deci se vede si de pe televizor, si din pagina. La sfarsit:
	STARE['descarcare'] = {'cod', 'motiv', 'cand', 'rezerva'} si catalogul paginii se citeste din nou. `rezerva`: a doua
	descarcare, de pe serverul de rezerva al feedului extern (treciPeRezerva). `reincercare`: descarcarea pornita de
	reincearcaListele (listele HD Satelit nepotrivite cat se republica feedul), care nu se mai reincearca."""
	d = ipkg if ipkg is not None else IpkgComponent()
	linii = []
	STARE['ultima_descarcare'] = time.time()
	# pagina web: descarcarea de acum e cea de pe serverul de rezerva al feedului extern
	STARE['rezerva_acum'] = rezerva
	if inainte is None:
		inainte = instantaneu(_CATALOG['catalog'])

	def eveniment(e, parametru):
		if e == IpkgComponent.EVENT_LINE:
			linii.append(parametru)
			scrieJurnal(parametru)
		elif e == IpkgComponent.EVENT_DONE:
			d.removeCallback(eveniment)
			STARE['descarcare'] = {'cod': parametru, 'motiv': '' if parametru == 0 else P.motiv_eroare(linii),
				'cand': time.time(), 'inainte': inainte, 'rezerva': rezerva}
			catalogVechi()
	d.addCallback(eveniment)

	def paza(e, parametru):
		if e == IpkgComponent.EVENT_DONE:
			d.removeCallback(paza)
			if pazesteListeleHds() and not reincercare:
				reincearcaListele()
			if parametru != 0:
				treciPeRezerva(linii)
	# paza listelor HD Satelit inaintea ascultatorului ecranului (pus deja), care citeste
	# catalogul chiar la EVENT_DONE: o lista nesemnata nu se vede nici o data
	ascultatori = getattr(d, 'callbackList', None)
	if isinstance(ascultatori, list):
		ascultatori.insert(0, paza)
	else:
		d.addCallback(paza)
	pastreazaPanaLaSfarsit(d)
	pastreazaListeleHds()
	d.startCmd(IpkgComponent.CMD_UPDATE)
	return d


# 0.7.5 (FED, TODO 14.11 02:12): listele HD Satelit nepotrivite dupa opkg update (feedul se republica chiar atunci; s-au pus
# la loc cele semnate de dinainte sau s-au sters): inca un opkg update, o singura data, dupa atatea ms, numai daca nu
# lucreaza deja opkg. Serverul trece publicarea deodata; peste cateva secunde listele si stare.json sunt iar din aceeasi.
INTARZIERE_REINCERCARE_LISTE_MS = 45000
FABRICA_CEAS = None     # eTimer; probele de pe PC dau altul
_reincercareListe = {'ceas': None}


def reincearcaListele():
	"""programeaza descarcarea reincercata (pornesteDescarcarea(reincercare=True)); False cand e deja programata sau nu
	se poate (pe PC fara ceas)"""
	if _reincercareListe['ceas'] is not None:
		return False
	fabrica = FABRICA_CEAS
	if fabrica is None:
		try:
			from enigma import eTimer as fabrica
		except ImportError:  # probe pe PC
			return False

	def acum():
		_reincercareListe['ceas'] = None
		if descarcareInCurs() or lucrareInCurs() or rezervaAsteapta():
			return
		scrieJurnal('reincerc descarcarea listei pachetelor (feedul HD Satelit se republica)')
		pornesteDescarcarea(reincercare=True)
	ceas = fabrica()
	ceas.callback.append(acum)
	ceas.start(INTARZIERE_REINCERCARE_LISTE_MS, True)
	_reincercareListe['ceas'] = ceas
	return True


# rezerva feedului extern (0.7.4): dupa trecere, inca un opkg update, pornit putin mai tarziu (ascultatorii descarcarii
# cazute pot porni ei ceva chiar acum) si numai daca nu lucreaza deja opkg
INTARZIERE_REZERVA_MS = 2000
_rezerva = {'ceas': None, 'ascultatori': []}


def rezervaAsteapta():
	"""True cat timp descarcarea de pe serverul de rezerva e programata (treciPeRezerva), dar nu a pornit inca"""
	return _rezerva['ceas'] is not None


def laRezerva(cb):
	"""Ecranul Extensii, deschis cand a cazut moneasoftware.com: cb(d) primeste descarcarea de pe serverul de rezerva
	(IpkgComponent-ul ei, ca sa o urmareasca pana la sfarsit, cu mesajul si catalogul ca la o descarcare a lui), sau
	cb(None) daca nu a mai pornit (alta lucrare opkg ruleaza). O singura data."""
	if cb not in _rezerva['ascultatori']:
		_rezerva['ascultatori'].append(cb)


def scoateAscultatorRezerva(cb):
	if cb in _rezerva['ascultatori']:
		_rezerva['ascultatori'].remove(cb)


def _anuntaRezerva(d):
	ascultatori, _rezerva['ascultatori'] = _rezerva['ascultatori'], []
	for cb in ascultatori:
		try:
			cb(d)
		except Exception as e:
			_jurnal('ascultatorul rezervei: %s' % e)


def treciPeRezerva(linii):
	"""opkg update cu cod de eroare: daca a cazut lista feedului extern de pe moneasoftware.com, sursa trece pe rezerva
	(Components/HdsPluginuriExterne.dupa_update) si lista se descarca inca o data, de acolo. Omul nu face nimic: Extensii
	reciteste catalogul la sfarsitul descarcarii, iar ModuleLipsa si DriverLipsa reincearca singure."""
	try:
		if not _X().dupa_update(list(linii)):
			return False
	except Exception as e:
		_jurnal('rezerva feedului extern: %s' % e)
		return False
	scrieJurnal('moneasoftware.com nu raspunde: feedul pluginurilor externe trece pe serverul de rezerva')
	try:
		from enigma import eTimer
	except ImportError:  # probe pe PC
		return True

	def acum():
		_rezerva['ceas'] = None
		if descarcareInCurs() or lucrareInCurs():
			_anuntaRezerva(None)
			return
		_anuntaRezerva(pornesteDescarcarea(rezerva=True))
	ceas = eTimer()
	ceas.callback.append(acum)
	ceas.start(INTARZIERE_REZERVA_MS, True)
	_rezerva['ceas'] = ceas
	return True


# ---------------------------------------------------------------- lucrarea opkg (instalare, actualizare, stergere)

def lucrareInCurs():
	l = STARE['lucrare']
	return l is not None and l.faza == 'lucru'


class Lucrare(object):
	"""Un plan (planInstalare, planActualizare, planStergere, planFisier) de la pornirea opkg pana la rezultat.
	Ascultatorii primesc ('jurnal', fel, text) la fiecare rand nou din jurnalul scurt si ('gata', cod) la sfarsit."""

	TITLURI_LUCRU = {'instaleaza': N_('Se instalează %s'), 'actualizeaza': N_('Se actualizează %s'),
		'sterge': N_('Se șterge %s'), 'fisier': N_('Se instalează %s')}

	def __init__(self, plan, ipkg=None, program=None, plugins=None, din_web=False):
		self.plan = plan
		self.program = program or opkgProgram
		self.plugins = plugins
		self.din_web = din_web
		self.faza = 'confirmare'         # 'lucru', apoi 'gata'
		self.linii = []
		self.jurnal = []                 # [(fel, text)], cel mult 40
		self.pas = ''
		self.schimbat = False
		self.oprit = False
		self.intrebatOprire = False
		self.ultimaLinie = time.time()
		self.pornita = 0
		self.cod = None
		self.rezultat = None
		self._ascultatori = []
		self.ipkg = ipkg if ipkg is not None else IpkgComponent()
		self.ipkg.addCallback(self._eveniment)
		self.radacina = '/'              # pentru starea pachetelor de la sfarsit (probele de pe PC dau alta)
		self.etapa = None                # 'verificare' (numai descarcarea, 0.6.8), apoi 'instalare'
		self._inainte = {}
		self._ceas = None
		# pachetele ramase neconfigurate dinainte de lucrare (None = nu se stie): numai ele pot fi motivul unui cod opkg
		# nenul la o lucrare cu toate tintele facute
		self.neconfigurateInainte = None

	def asculta(self, functie):
		if functie not in self._ascultatori:
			self._ascultatori.append(functie)

	def lasa(self, functie):
		if functie in self._ascultatori:
			self._ascultatori.remove(functie)

	def _anunta(self, *date):
		for f in list(self._ascultatori):
			try:
				f(*date)
			except Exception as e:
				_jurnal('ascultatorul lucrarii: %s' % e)

	def titluLucru(self):
		return (_t(self.TITLURI_LUCRU.get(self.plan.get('fel'))) or '%s') % self.plan.get('nume', '')

	def porneste(self):
		self.faza = 'lucru'
		self.ultimaLinie = self.pornita = time.time()
		STARE['lucrare'] = self
		self.plan.setdefault('titluri', {})
		if self.plan.get('verifica'):
			# 0.6.8: intai numai descarcarea (opkg --download-only), apoi pachetele din cache se citesc pentru Python 2
			self.etapa = 'verificare'
			self._inainte = self._dinCache()
			self._scrie('pas', _t(TEXT_VERIFICARE))
			scrieJurnal('---- verificare %s' % ' '.join(self.plan.get('verifica')))
			self.ipkg.runCmd(self.plan.get('verifica'))
			return
		if self.plan.get('teme') and self.plan.get('cale_fisier'):
			# o tema dintr-un fisier: fisierele imaginii pe care le suprascrie se copiaza intai (pe un fir: un .ipk de
			# tema are zeci de MB dezarhivati), apoi instalarea
			self._scrie('pas', _t(TEXT_VERIFICARE))
			cale, radacina = self.plan.get('cale_fisier'), self.radacina
			self._peFir(lambda: TS.pastreazaDinIpk(cale, radacina), lambda _r: self._instaleaza())
			return
		self._instaleaza()

	def _peFir(self, lucru, apoi):
		"""lucru() pe un fir separat, apoi apoi(rezultat) pe firul enigma2 (un eTimer culege rezultatul, ca la
		verificare); pe PC, pe loc"""
		stare = {'gata': False, 'rez': None}

		def fir():
			try:
				stare['rez'] = lucru()
			except Exception as e:
				_jurnal('lucrul pe fir: %s' % e)
			stare['gata'] = True
		try:
			from enigma import eTimer
		except ImportError:          # probele de pe PC: pe loc
			fir()
			apoi(stare['rez'])
			return
		self._ceas = eTimer()

		def uitaTe():
			if stare['gata']:
				self._ceas.stop()
				apoi(stare['rez'])
		self._ceas.callback.append(uitaTe)
		P._fire.start_new_thread(fir, ())
		self._ceas.start(150, False)

	def _instaleaza(self):
		self.etapa = 'instalare'
		scrieJurnal('---- %s %s' % (self.plan.get('fel'), ' '.join(self.plan.get('argumente') or ())), True)
		try:
			self.neconfigurateInainte = P.pachete_neconfigurate(self.radacina)
		except Exception as e:
			self.neconfigurateInainte = None
			_jurnal('pachetele neconfigurate: %s' % e)
		if self.neconfigurateInainte:
			scrieJurnal('pachete neconfigurate in receptor (opkg le configureaza din nou la sfarsit): %s' %
				', '.join(self.neconfigurateInainte), True)
		try:
			reparate = reparaScripturiPachete(self.radacina)
			if reparate:
				scrieJurnal('scripturi de pachet fara BOM/CRLF acum: %s' % ', '.join(reparate), True)
		except Exception as e:
			_jurnal('scripturile pachetelor: %s' % e)
		self.ipkg.runCmd(self.plan.get('argumente'))

	# ------------------------------------------------------------ verificarea pentru Python 2 (0.6.8)

	def _dinCache(self):
		"""{cale: mtime} ale fisierelor .ipk din cache-ul opkg (acolo le lasa --download-only, in RAM pe receptor;
		numele lor: <semn>_<fisierul din feed>)"""
		rez = {}
		try:
			dosar = P._cale(self.radacina, P.citeste_configurarea(self.radacina).cache_dir)
			for n in os.listdir(dosar):
				if n.endswith('.ipk'):
					c = os.path.join(dosar, n)
					try:
						rez[c] = os.path.getmtime(c)
					except OSError:
						pass
		except OSError:
			pass
		return rez

	def _descarcate(self):
		"""pachetele planului din cache: cele numite in randurile "Downloading ..." ale lui opkg, cele cu numele din
		listele surselor (Filename, si cand erau deja in cache) si cele noi sau schimbate de la pornire (dependintele;
		un pachet ramas de altadata, care nu e al planului, nu se socoteste)"""
		numite = set(n for n in self.plan.get('fisiere') or () if n)
		for linie in self.linii:
			m = re.match(r'^Downloading (\S+?)\.?$', linie.strip())
			if m:
				numite.add(m.group(1).rsplit('/', 1)[-1])
		rez = []
		for c, t in self._dinCache().items():
			b = os.path.basename(c)
			if any(b == n or b.endswith('_' + n) for n in numite) or self._inainte.get(c) != t:
				rez.append(c)
		return sorted(rez)

	def _dupaDescarcare(self, cod):
		if cod != 0:
			# descarcarea n-a mers (retea, sursa): nimic instalat, motivul din randurile opkg
			self.etapa = None
			self._gata(cod)
			return
		noi = self._descarcate()
		scrieJurnal('verificare: %d pachete descarcate' % len(noi))
		stare = {'gata': False, 'rez': []}

		teme = self.plan.get('teme')
		radacina = self.radacina

		def lucru():
			try:
				stare['rez'] = [(c, P.H.din_ipk(c)) for c in noi]
			except Exception as e:
				_jurnal('verificarea pachetelor: %s' % e)
			# 0.7.5 (CTU): si dependintele descarcate (un python3-attrs strain cerut de plugin), tot pe firul acesta
			stare['pornire'] = [(c, refuzPornire(c, radacina)) for c in noi]
			if teme:
				# o tema: fisierele imaginii pe care le suprascrie, copiate inainte de instalare (HdsTemeSuprascrise)
				for c in noi:
					try:
						copiate = TS.pastreazaDinIpk(c, radacina)
						if copiate:
							scrieJurnal('tema %s: fisiere ale imaginii copiate inainte: %s' % (os.path.basename(c),
								', '.join(copiate)))
					except Exception as e:
						_jurnal('copia fisierelor temei: %s' % e)
			stare['gata'] = True
		try:
			from enigma import eTimer
		except ImportError:          # probele de pe PC: pe loc
			lucru()
			self._verificate(stare['rez'], stare.get('pornire'))
			return
		# citirea pe un fir separat; rezultatul il culege un eTimer pe firul enigma2 (tragere, ca in HdsLocInregistrari)
		self._ceas = eTimer()

		def uitaTe():
			if stare['gata']:
				self._ceas.stop()
				self._verificate(stare['rez'], stare.get('pornire'))
		self._ceas.callback.append(uitaTe)
		P._fire.start_new_thread(lucru, ())
		self._ceas.start(150, False)

	def _verificate(self, rezultate, pornire=None):
		for cale, v in rezultate:
			if v.python2:
				self._refuzPython2(cale, v)
				return
		for cale, v in rezultate:
			alt = P.H.alt_python(v)
			if alt:
				self._refuzAltPython(cale, v, alt)
				return
		for cale, r in pornire or ():
			if r:
				self._refuzPornire(cale, r)
				return
		self._instaleaza()

	def _refuzPornire(self, cale, r):
		"""un pachet descarcat ar inlocui pachetele Python de care porneste interfata: nu se instaleaza nimic, cache-ul golit"""
		nume = r.get('pachet') if P.nume_valid(r.get('pachet') or '') else ''
		titlu = (self.plan.get('titluri') or {}).get(nume) or (P.nume_scurt(nume) if nume else self.plan.get('nume', ''))
		scrieJurnal('verificare: %s ar inlocui %s (%s %s, instalat %s, %s)' % (nume, r.get('inlocuit'), r.get('fel'),
			r.get('fisier') or r.get('versiune') or '', r.get('instalata') or '', os.path.basename(cale)))
		self.etapa = None
		self.faza = 'gata'
		self.cod = 'pornire'
		self._scrie('eroare', textPornire(titlu, r))
		self.rezultat = {'reusit': False, 'titlu': _t(TITLU_PORNIRE) % titlu, 'stare': _t('Nu s-a instalat nimic.'),
			'culoare': 'rau', 'butoane': [N_('Închide')], 'ales': 0, 'repornire': False, 'python2': False,
			'inlocuitor': None, 'textInlocuitor': ''}
		scrieJurnal('---- cod pornire')
		try:
			P.curata_cache(self.radacina)
		except Exception as e:
			_jurnal('cache opkg: %s' % e)
		catalogVechi()
		self._anunta('gata', self.cod)

	def _refuzAltPython(self, cale, v, alt):
		"""un pachet descarcat are module .so numai pentru alt Python 3: nu se instaleaza nimic, cache-ul golit"""
		control = P.citeste_control_ipk(cale)
		nume = control.get('package', '') if P.nume_valid(control.get('package', '')) else ''
		titlu = (self.plan.get('titluri') or {}).get(nume) or (P.nume_scurt(nume) if nume else self.plan.get('nume', ''))
		scrieJurnal('verificare: %s facut pentru Python %s (%s, %s)' % (nume, alt, v.altpy[0] if v.altpy else '',
			os.path.basename(cale)))
		self.etapa = None
		self.faza = 'gata'
		self.cod = 'altpython'
		self._scrie('eroare', textAltPython(titlu, alt))
		self.rezultat = {'reusit': False, 'titlu': _t(TITLU_ALT_PYTHON) % titlu, 'stare': _t('Nu s-a instalat nimic.'),
			'culoare': 'rau', 'butoane': [N_('Închide')], 'ales': 0, 'repornire': False, 'python2': False,
			'inlocuitor': None, 'textInlocuitor': ''}
		scrieJurnal('---- cod altpython')
		try:
			P.curata_cache(self.radacina)
		except Exception as e:
			_jurnal('cache opkg: %s' % e)
		catalogVechi()
		self._anunta('gata', self.cod)

	def _refuzPython2(self, cale, v):
		"""un pachet descarcat e numai pentru Python 2: nu se instaleaza nimic; textele, inlocuitorul, cache-ul golit"""
		control = P.citeste_control_ipk(cale)
		nume = control.get('package', '') if P.nume_valid(control.get('package', '')) else ''
		titlu = (self.plan.get('titluri') or {}).get(nume) or (P.nume_scurt(nume) if nume else self.plan.get('nume', ''))
		inl, stare = inlocuitor(self.plan.get('catalog'), nume, v.dosare)
		scrieJurnal('verificare: %s %s %s (%s)' % (nume, v.motiv[0], v.motiv[1], os.path.basename(cale)))
		self.etapa = None
		self.faza = 'gata'
		self.cod = 'python2'
		for t in TEXT_PYTHON2:
			self._scrie('eroare', _t(t))
		m = textMotiv(v.motiv)
		if m:
			self._scrie('eroare', '%s: %s' % (_t('Motivul'), m))
		nota = notaInlocuitor(self.plan.get('catalog'), inl, stare)
		if nota:
			self._scrie('bun', nota)
		instalabil = stare == 'instalabil'
		self.rezultat = {'reusit': False, 'titlu': _t(TITLU_PYTHON2) % titlu, 'stare': _t('Nu s-a instalat nimic.'),
			'culoare': 'rau', 'butoane': [BUTON_INLOCUITOR, N_('Închide')] if instalabil else [N_('Închide')], 'ales': 0,
			'repornire': False, 'python2': True, 'inlocuitor': inl.nume if instalabil else None,
			'textInlocuitor': _t(BUTON_INLOCUITOR) if instalabil else ''}
		scrieJurnal('---- cod python2')
		try:
			P.curata_cache(self.radacina)
		except Exception as e:
			_jurnal('cache opkg: %s' % e)
		catalogVechi()
		self._anunta('gata', self.cod)

	def _scrie(self, fel, text):
		if not text or (self.jurnal and self.jurnal[-1] == (fel, text)):
			return
		self.jurnal.append((fel, text))
		self.jurnal = self.jurnal[-40:]
		if fel == 'pas' and self.faza == 'lucru':
			self.pas = text
		self._anunta('jurnal', fel, text)

	def _eveniment(self, eveniment, parametru):
		if eveniment == IpkgComponent.EVENT_LINE:
			self.ultimaLinie = time.time()
			self.intrebatOprire = False
			self.linii.append(parametru)
			scrieJurnal(parametru)
			fel, text = P.linie_jurnal(parametru, self.plan.get('titluri'))
			if fel:
				self._scrie(fel, text)
		elif eveniment in (IpkgComponent.EVENT_INSTALL, IpkgComponent.EVENT_UPGRADE, IpkgComponent.EVENT_REMOVE,
				IpkgComponent.EVENT_CONFIGURING):
			self.schimbat = True
		elif eveniment == IpkgComponent.EVENT_MODIFIED:
			# un fisier de configurare schimbat de utilizator: il pastram pe al lui (raspunsul N al opkg)
			self._scrie('pas', _t('Se păstrează setările tale din %s') % P._curat(str(parametru), 80))
			self.ipkg.write('N')
		elif eveniment == IpkgComponent.EVENT_DONE:
			if self.etapa == 'verificare':
				self._dupaDescarcare(parametru)
			else:
				self._gata(parametru)

	def secundeFaraRaspuns(self):
		return max(0, int(time.time() - self.ultimaLinie)) if self.faza == 'lucru' else 0

	def poateOpri(self):
		"""opkg nu se opreste la jumatatea unei instalari (starea pachetelor ar ramane amestecata); doar daca nu mai
		scrie nimic de un minut (retea blocata)"""
		return self.faza == 'lucru' and time.time() - self.ultimaLinie > FARA_RASPUNS_S

	def opreste(self):
		"""Opreste opkg (numai dupa un minut fara raspuns). Intai randul din jurnal, apoi oprirea: stop() anunta acum
		sfarsitul (EVENT_DONE), deci lucrarea trece in 'gata'."""
		if not self.poateOpri():
			return False
		self._scrie('eroare', _t('Oprit de tine, după un minut fără răspuns.'))
		self.oprit = True
		self.ipkg.stop()
		return True

	def cerereOprire(self):
		"""EXIT pe televizor in timpul lucrului: 'asteapta' (inca raspunde), 'intreaba' (prima apasare dupa un minut
		fara raspuns) sau 'oprit' (a doua)"""
		if self.poateOpri():
			if self.intrebatOprire:
				self.opreste()
				return 'oprit'
			self.intrebatOprire = True
			return 'intreaba'
		return 'asteapta'

	def _gata(self, cod):
		self.faza = 'gata'
		self.cod = cod
		fel = self.plan.get('fel')
		nume = self.plan.get('nume', '')
		ales = 0
		trebuieRepornire = False
		if self.schimbat or cod == 0:
			self.schimbat = True
			trebuieRepornire = reincarcaPluginuri(self.plugins)
		tinte = self.plan.get('tinte') or []
		bune, rele = rezultatePachete(self.plan, self.radacina) if tinte and (cod == 0 or self.schimbat) else ([], tinte)
		# reusita: codul 0, sau toate tintele facute si numai pachete neconfigurate de dinainte (opkg iese cu 255 si cand
		# cade numai configurarea altui pachet din receptor, ramas asa de la o instalare de dinainte: atunci lucrarea
		# ceruta s-a facut). Un pachet ramas neconfigurat acum, care nu era asa inainte (o dependinta adusa de lucrare),
		# e o greseala a lucrarii.
		reusit = cod == 0
		if not reusit and tinte and bune and not rele and self.schimbat and not self.oprit and (
				self.neconfigurateInainte is not None):
			try:
				acum = P.pachete_neconfigurate(self.radacina)
			except Exception:
				acum = None
			if acum is not None:
				noi = [n for n in acum if n not in self.neconfigurateInainte]
				reusit = not noi
				scrieJurnal(('opkg a iesit cu %s, dar toate pachetele cerute s-au facut: lucrarea e reusita; pachete '
					'neconfigurate in receptor (de dinainte): %s' % (cod, ', '.join(acum) or 'niciunul')) if reusit else
					'pachete ramase neconfigurate dupa lucrare (nu erau inainte): %s' % ', '.join(noi), True)
		if tinte and (cod == 0 or self.schimbat):
			# ce s-a facut si ce nu, pachet cu pachet, cu versiunea (0.6.6)
			facut = {'instaleaza': N_('Instalat: %s'), 'actualizeaza': N_('Actualizat: %s'), 'sterge': N_('Șters: %s')}
			nefacut = {'instaleaza': N_('Nu s-a instalat: %s'), 'actualizeaza': N_('Nu s-a actualizat: %s'),
				'sterge': N_('Nu s-a șters: %s')}
			for t in bune:
				self._scrie('bun', _t(facut.get(fel, '%s')) % numeCuVersiune(t['titlu'], t['de'] if fel == 'sterge' else t['la']))
			for t in rele:
				self._scrie('eroare', _t(nefacut.get(fel, '%s')) % numeCuVersiune(t['titlu'], t['de'] if fel == 'sterge' else t['la']))
		if reusit:
			if len(tinte) == 1 and bune:
				# cu numele si versiunea: "Gata. Alfa 2.26.09-11968 a fost instalat."
				t = tinte[0]
				texte = {'instaleaza': _t('Gata. %s a fost instalat.'), 'actualizeaza': _t('Gata. %s a fost actualizat.'),
					'sterge': _t('Gata. %s a fost șters.')}
				titlu = texte.get(fel, _t('Gata. %s')) % numeCuVersiune(t['titlu'],
					versiuneScurta(t['de'] if fel == 'sterge' else t['la']))
			else:
				texte = {'instaleaza': _t('Gata. %s este instalat.'), 'fisier': _t('Gata. %s este instalat.'),
					'actualizeaza': _t('Gata. %s este la zi.'), 'sterge': _t('Gata. %s a fost șters.')}
				titlu = self.plan.get('textGata') or (texte.get(fel) or _t('Gata. %s')) % nume
			stare, culoare = _t('Gata'), 'bun'
			eroareScript = eroareScriptPachet(self.linii) if cod == 0 and fel != 'sterge' else ''
			if eroareScript:
				# randul 816: codul 0, dar scriptul extensiei a scris o eroare (de pilda o pagina HTML in locul arhivei)
				self._scrie('eroare', _t('Scriptul extensiei a scris o eroare: %s') % eroareScript)
				scrieJurnal('codul %s, dar scriptul extensiei a scris o eroare: %s' % (cod, eroareScript), True)
			elif cod == 0:
				self._scrie('bun', _t('Terminat fără erori.'))
			butoane = [N_('Închide')]
			if trebuieRepornire and fel != 'sterge':
				# extensia noua apare in lista (si porneste) abia dupa repornirea interfetei; ales Mai tarziu: un OK
				# apasat in timpul instalarii (ca sa vezi daca s-a terminat) nu reporneste interfata
				butoane = [N_('Repornește interfața'), N_('Mai târziu')]
				ales = 1
				stare = _t('Schimbările se văd după repornirea interfeței.') if fel == 'actualizeaza' else \
					_t('Extensia apare în listă după repornirea interfeței.')
				culoare = 'chihlimbar'
			elif self.plan.get('repornire'):
				butoane = [N_('Închide'), N_('Repornește interfața')]
				stare = _t('Unele schimbări se văd după repornirea interfeței.')
			elif fel == 'instaleaza' and any(t['acces'] for t in bune):
				# un modul de acces nou: nu porneste singur, se alege din ecranul modulelor
				stare = _t('Îl pornești din ecranul modulelor.')
			if eroareScript:
				stare = _t('Extensia e pusă, dar scriptul ei a scris o eroare: poate nu merge.')
				culoare = 'chihlimbar'
		else:
			motiv = P.motiv_eroare(self.linii)
			if self.oprit:
				motiv = _t('Oprit după un minut fără răspuns. Verifică legătura la internet.')
			elif cod == -1 and not self.linii and not self.program():
				motiv = _t('Instalarea extensiilor nu este disponibilă în această imagine.')
			texte = {'instaleaza': _t('%s nu a fost instalat.'), 'fisier': _t('%s nu a fost instalat.'),
				'actualizeaza': _t('%s nu a fost actualizat.'), 'sterge': _t('%s nu a fost șters.')}
			titlu = (texte.get(fel) or _t('%s: nu a reușit.')) % nume
			stare, culoare = motiv, 'rau'
			butoane = [N_('Închide')]
		self.rezultat = {'reusit': reusit, 'titlu': titlu, 'stare': stare, 'culoare': culoare, 'butoane': butoane,
			'ales': ales, 'repornire': 'Repornește interfața' in butoane}
		if self.schimbat:
			# fisierele imaginii suprascrise de o tema stearsa acum (sau altfel) se pun la loc (HdsTemeSuprascrise)
			try:
				puse = TS.refa(self.radacina)
				if puse:
					scrieJurnal('fisierele imaginii puse la loc dupa stergerea temei: %s' % ', '.join(puse), True)
			except Exception as e:
				_jurnal('fisierele imaginii: %s' % e)
		scrieJurnal('---- cod %s' % cod, True)
		# 0.7.4: fisierul instalat din /tmp nu mai tine RAM (de pe stick sau disc ramane)
		if reusit and fel == 'fisier' and stergeIpkDinTmp(self.plan.get('cale_fisier'), self.radacina):
			scrieJurnal('fisierul instalat sters din /tmp: %s' % posixpath.basename(self.plan.get('cale_fisier')))
		# pachetele descarcate de opkg nu mai trebuie (cache-ul e in RAM): sterse acum, nu la repornire (0.6.6)
		try:
			n = P.curata_cache()
			if n:
				scrieJurnal('cache opkg: %s pachete sterse' % n)
		except Exception as e:
			_jurnal('cache opkg: %s' % e)
		catalogVechi()
		self._anunta('gata', cod)
		if self.schimbat and fel != 'sterge':
			# 0.7.4: ce s-a instalat poate cere un port pe care il are alt serviciu (Components/HdsPorturi.py)
			try:
				from Components import HdsPorturi
				HdsPorturi.dupa_schimbare()
			except Exception:
				pass


def pornesteLucrarea(plan, plugins=None, din_web=True):
	"""Lucrarea unui plan, pornita acum (pagina web; ecranul porneste lucrarea lui dupa confirmarea de pe televizor)"""
	l = Lucrare(plan, plugins=plugins, din_web=din_web)
	l.porneste()
	return l


# ---------------------------------------------------------------- catalogul paginii web

def catalogVechi():
	_CATALOG['vechi'] = True


def _semn(catalog):
	"""ce s-a schimbat in fisierele opkg (configurarea, listele, starea pachetelor): numai stat, fara citire"""
	conf = catalog.configurare if catalog is not None else P.Configurare()
	parti = []
	for cale in ('/etc/opkg', conf.status_file, conf.lists_dir):
		try:
			parti.append(os.stat(cale).st_mtime)
		except OSError:
			parti.append(None)
	try:
		for nume in sorted(os.listdir(conf.lists_dir))[:64]:
			try:
				parti.append((nume, os.stat(os.path.join(conf.lists_dir, nume)).st_mtime))
			except OSError:
				pass
	except OSError:
		pass
	return tuple(parti)


def semnCatalog(catalog):
	"""Semnul fisierelor opkg ale catalogului (numai stat): se schimba dupa o instalare, o stergere, o sursa sau o lista
	noua, facute de pe televizor, din pagina web sau de alt program. Ecranul de pe televizor il tine minte la citire si
	se uita la el din cand in cand (Screens/HdsExtensii.py, _verificaSchimbari)."""
	return _semn(catalog)


def catalogLaZi():
	"""catalogul tinut minte daca e inca la zi, altfel None (pagina il citeste din nou cu incarcaCatalog, pe un fir)"""
	c = _CATALOG['catalog']
	if c is None or _CATALOG['vechi']:
		return None
	if _semn(c) != _CATALOG['semn']:
		return None
	return c


def incarcaCatalog(incarca=None):
	"""citeste catalogul (HdsPachete.incarca: numai fisiere, se poate pe un fir separat) si il tine minte"""
	_CATALOG['vechi'] = False
	c = (incarca or P.incarca)()
	_CATALOG['semn'] = _semn(c)
	_CATALOG['catalog'] = c
	return c


def _pluginuri(n):
	"""un plugin, 2 pluginuri, 20 de pluginuri (starea unui feed din fila Surse), cu formele de plural ale limbii"""
	try:
		from Components.HdsImportSurse import ngettext
		return ngettext("%d plugin", "%d pluginuri", n) % n
	except ImportError:
		pass
	if n == 1:
		return _t("un plugin")
	return _t("%d pluginuri") % n


def _pachete_sursa(n):
	"""un pachet, 2 pachete, 20 pachete (lista surselor de extensii); in alta limba, formele ei de plural (ngettext
	din Components/HdsImportSurse.py, care fara traducere tine regula romaneasca)"""
	try:
		from Components.HdsImportSurse import ngettext
		return ngettext("%d pachet", "%d pachete", n) % n
	except ImportError:
		pass
	if n == 1:
		return _t("un pachet")
	return _t("%d pachete") % n
