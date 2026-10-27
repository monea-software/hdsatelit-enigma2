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
	from Components.Ipkg import IpkgComponent, opkgArguments, opkgProgram
except ImportError:  # probe pe PC
	from Ipkg import IpkgComponent, opkgArguments, opkgProgram

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
ETICHETA_SURSE = N_('Surse')
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
	if P.sursa_hdsatelit(adresa):
		return FEED_HDS
	if _X().e_feed_extern(adresa):
		return FEED_EXTERN
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
	return _t('Altă sursă'), '', False


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

def pachetPlugin(catalog, plugin):
	cale = getattr(plugin, 'path', None)
	if not cale:
		return None
	return catalog.pachet_pentru_dosar(posixpath.normpath(cale))


def pluginPentru(pluginuri, p):
	if not p.dosar_plugin:
		return None
	for plugin in pluginuri:
		if posixpath.normpath(getattr(plugin, 'path', '') or '') == posixpath.normpath(p.dosar_plugin):
			return plugin
	return None


def dupaRepornire(catalog, plugins):
	"""pachetele instalate care au un plugin inca neincarcat (instalat acum, porneste dupa repornirea interfetei)"""
	if not getattr(plugins, 'restartRequired', False):
		return []
	incarcate = set(posixpath.normpath(getattr(pl, 'path', '') or '') for pl in plugins.pluginList)
	rez = [p for p in catalog.pachete.values() if p.instalat and p.dosar_plugin and
		posixpath.normpath(p.dosar_plugin) not in incarcate]
	rez.sort(key=lambda p: p.titlu.lower())
	return rez


def file(catalog, nrInstalate):
	"""[(id, eticheta, numar)] ale filelor fara cautare si fara Din fisier, in ordinea de pe televizor: Pe receptor,
	Actualizari (doar cand sunt), categoriile care au pachete. Fila Din fisier si Surse le pune fiecare capat la
	sfarsit (Din fisier are numarul cautarii lui)."""
	rez = [('instalate', _t('Pe receptor'), nrInstalate)]
	n = len(catalog.actualizari())
	if n:
		rez.append(('actualizari', _t('Actualizări'), n))
	for cat, eticheta, numar in catalog.categorii():
		rez.append((cat, eticheta, numar))
	return rez


def filaSurse(catalog):
	"""(id, eticheta, numar) al filei Surse, ultima pe televizor si in pagina web; eticheta tradusa; numarul = randurile
	aratate (feedurile si sursele singure), nu sursele opkg"""
	return ('surse', _t(ETICHETA_SURSE), numarSurse(catalog))


def numarSurse(catalog):
	return len(feeduri(catalog)) + len(surseSingure(catalog))


def randuriCautare(catalog, pluginuri, text):
	t = (text or '').strip().lower()
	rez = []
	vazute = set()
	for plugin in pluginuri:
		nume = (plugin.name or '').lower()
		if t in nume or t in (plugin.description or '').lower():
			p = pachetPlugin(catalog, plugin)
			rez.append(('plugin', plugin, p))
			if p is not None:
				vazute.add(p.nume)
	for p in catalog.cauta(t):
		if p.nume not in vazute:
			rez.append(('pachet', p, None))
	return rez


def randuri(catalog, fila, pluginuri, plugins, cautare=''):
	"""[(fel, obiect, extra)] ale unei file, afara de Din fisier"""
	if fila == 'cautare':
		return randuriCautare(catalog, pluginuri, cautare)
	if fila == 'instalate':
		return [('plugin', pl, pachetPlugin(catalog, pl)) for pl in pluginuri] + \
			[('pachet', p, 'repornire') for p in dupaRepornire(catalog, plugins)]
	if fila == 'actualizari':
		return [('pachet', p, None) for p in catalog.actualizari()]
	if fila == 'surse':
		rez = [('feed', f, None) for f in feeduri(catalog)]
		rez += [('sursa', s, None) for s in surseSingure(catalog)]
		rez.append(('adauga', None, None))
		return rez
	return [('pachet', p, None) for p in catalog.din_categoria(fila)]


# ------------------------------------------------------------ filtrul listelor (dupa feed si dupa fel)
# Primul rand al filelor cu pachete e filtrul ('filtru'): OK (sau clic) deschide alegerile, Rosu arata tot. Feedul se
# alege in orice fila cu pachete; felul (categoria) numai in filele amestecate, unde stau pachete de mai multe feluri
# (in celelalte fila insasi e felul). Pagina web are aceleasi alegeri, ca liste (feed=, fel=).
FILE_AMESTECATE = ('instalate', 'actualizari', 'cautare')
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
	if fel == 'plugin':
		return extra
	if fel == 'pachet':
		return obj
	return None


def feedRand(catalog, fel, obj, extra):
	"""feedul unui rand cu pachet: FEED_HDS, FEED_EXTERN, FEED_IMAGINE (vine cu imaginea), PREFIX_SURSA + numele sursei
	omului sau al altei surse, FEED_ALTA (pachet instalat de nicaieri, de pilda din fisier); '' la celelalte randuri"""
	if fel not in ('plugin', 'pachet'):
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
		return _t('Altă sursă')
	if cheie.startswith(PREFIX_SURSA):
		return cheie[len(PREFIX_SURSA):]
	return _t('Toate feedurile')


def numeFelFiltru(cheie):
	return _t(P.ETICHETE[cheie]) if cheie in P.ETICHETE else _t('Toate felurile')


def potrivesteFiltru(catalog, rand, filtru, fila):
	fel, obj, extra = rand
	if fel not in ('plugin', 'pachet'):
		return True
	f = filtru or {}
	if f.get('feed') and feedRand(catalog, fel, obj, extra) != f['feed']:
		return False
	if f.get('fel') and fila in FILE_AMESTECATE and felRand(catalog, fel, obj, extra) != f['fel']:
		return False
	return True


def filtreaza(catalog, randuri_, filtru, fila):
	"""randurile filei care trec de filtru (randurile fara pachet raman)"""
	if not areFiltru(fila) or not filtruActiv(filtru, fila):
		return list(randuri_)
	return [r for r in randuri_ if potrivesteFiltru(catalog, r, filtru, fila)]


def _ordineFeed(cheie):
	return ({FEED_HDS: 0, FEED_EXTERN: 1, FEED_IMAGINE: 2}.get(cheie, 4 if cheie == FEED_ALTA else 3), cheie)


def alegeriFiltru(catalog, randuri_, fila):
	"""(feeduri, feluri): [(cheie, text cu numarul pachetelor)] din randurile filei (nefiltrate), prima fiind ('', toate);
	felurile numai in filele amestecate, altfel []"""
	feeds = {}
	kinds = {}
	for fel, obj, extra in randuri_:
		if fel not in ('plugin', 'pachet'):
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
	"""randurile filei pentru televizor: randul filtrului primul, ('filtru', filtrul, (fila, aratate, total)), cand
	fila are pachete sau filtrul e activ; apoi randurile care trec de filtru"""
	if not areFiltru(fila):
		return list(randuri_)
	cu_pachet = [r for r in randuri_ if r[0] in ('plugin', 'pachet')]
	if not cu_pachet and not filtruActiv(filtru, fila):
		return list(randuri_)
	rez = filtreaza(catalog, randuri_, filtru, fila)
	aratate = sum(1 for r in rez if r[0] in ('plugin', 'pachet'))
	return [('filtru', dict(filtru or filtruGol()), (fila, aratate, len(cu_pachet)))] + rez


def descriereRand(catalog, fel, obj, extra):
	"""(icoana, titlu, subtitlu, insigna, culoarea insignei, textul mic din dreapta) al unui rand din lista. Culoarea e
	o cheie ('bun', 'chihlimbar', 'rau') sau None. Randul cautarii in retea il face fiecare capat. Textele sunt
	intregi: un rand care nu incape deruleaza (lib/gui/elabel.h)."""
	if fel == 'plugin':
		p = extra
		cat = p.categorie if p is not None else categoriePlugin(getattr(obj, 'path', ''))
		insigna = culoare = None
		if p is not None and p.actualizare:
			insigna, culoare = _t('Actualizare'), 'chihlimbar'
		mic = []
		sub = obj.description or ''
		if p is not None:
			# de unde vine pachetul, sub nume (0.6.6): feedurile stau amestecate in liste
			sub = cuSursa(sursaPachet(catalog, p)[0], sub)
			if p.versiune_instalata:
				mic.append(p.versiune_instalata)
		return (P.ICOANE.get(cat, 'extensii'), obj.name or '', sub, insigna, culoare, ' · '.join(mic))
	if fel == 'pachet':
		p = obj
		if extra == 'repornire':
			insigna, culoare = _t('După repornire'), 'chihlimbar'
		elif p.actualizare:
			insigna, culoare = _t('Actualizare'), 'chihlimbar'
		elif p.instalat:
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
			insigna, culoare = _t('Verificată'), 'bun'
		elif catalog.configurare.e_a_utilizatorului(nume):
			insigna, culoare = _t('Adăugată de tine'), 'chihlimbar'
		else:
			insigna, culoare = _t('Externă'), 'chihlimbar'
		mic = _pachete_sursa(n) if nume in catalog.surse_cu_lista else _t('lista nedescărcată')
		return ('surse', eticheta if hds else nume, adresa, insigna, culoare, mic)
	if fel == 'feed':
		f = obj
		if f.id == FEED_HDS:
			insigna, culoare = _t('Verificată'), 'bun'
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
			titlu, insigna, culoare = _t('Filtru: toate pachetele'), None, None
		if fila in FILE_AMESTECATE:
			sub = _t('OK alege feedul sau felul pachetelor arătate.')
		else:
			sub = _t('OK alege feedul pachetelor arătate.')
		return ('liste', titlu, sub, insigna, culoare, _t('%d din %d') % (aratate, total))
	# adauga
	return ('surse', _t('Adaugă o sursă'), _t('Adresa unui depozit de pachete (feed opkg) de pe internet'), None, None, '')


def detalii(catalog, fel, obj, extra):
	"""Detaliile randului ales: {'icoana', 'titlu', 'insigna', 'culoare', 'etichete', 'valori', 'descriere', 'indiciu'}
	(indiciul spune tastele telecomenzii). Randul cautarii in retea il face fiecare capat."""
	d = {'icoana': None, 'titlu': '', 'insigna': '', 'culoare': 'eticheta', 'etichete': [], 'valori': [],
		'descriere': '', 'indiciu': ''}
	if fel == 'plugin':
		p = extra
		cat = p.categorie if p is not None else categoriePlugin(getattr(obj, 'path', ''))
		s, adresa, _hds = sursaPachet(catalog, p)
		d.update(icoana=P.ICOANE.get(cat, 'extensii'), titlu=obj.name or '', insigna=_t('Pe receptor'), culoare='bun')
		if p is not None and p.actualizare:
			d.update(insigna=_t('Actualizare disponibilă: %s') % p.versiune, culoare='chihlimbar')
		rand = [(_t('Versiune'), p.versiune_instalata if p is not None else ''),
			(_t('Ocupă'), P.marime_text(p.marime_instalat) if p is not None else ''),
			(_t('Sursa'), s),
			(_t('Adresa'), P.gazda(adresa) if adresa and not _hds else ''),
			(_t('Locul'), _t(P.ETICHETE.get(cat, N_('Extensii'))))]
		d['etichete'] = [a for a, b in rand if b]
		d['valori'] = [b for a, b in rand if b]
		text = obj.description or ''
		if p is not None and p.descriere and p.descriere != text:
			text = (text + '\n' + p.descriere).strip()
		d['descriere'] = text
		ind = [_t('OK deschide')]
		if p is not None and p.actualizare:
			ind.append(_t('Verde actualizează'))
		if p is not None and p.se_poate_sterge:
			ind.append(_t('Roșu șterge'))
		if areSursa(catalog, p):
			ind.append(_t('Albastru descarcă sursa'))
		d['indiciu'] = ' · '.join(ind)
	elif fel == 'pachet':
		p = obj
		s, adresa, hds = sursaPachet(catalog, p)
		if p.actualizare:
			d.update(insigna=_t('Actualizare de la %s la %s') % (p.versiune_instalata, p.versiune), culoare='chihlimbar')
		elif p.instalat:
			d.update(insigna='Instalat, versiunea %s' % p.versiune_instalata, culoare='bun')
		else:
			d.update(insigna=_t('Neinstalat'), culoare='eticheta')
		marime = P.marime_text(p.marime)
		ocupa = P.marime_text(p.marime_instalat)
		rand = [(_t('Versiune'), p.versiune or p.versiune_instalata),
			(_t('Mărime'), ', '.join(x for x in (marime, ocupa and 'ocupă %s' % ocupa) if x)),
			(_t('Sursa'), s),
			(_t('Adresa'), P.gazda(adresa) if adresa and not hds else ''),
			(_t('Categoria'), _t(P.ETICHETE.get(p.categorie, N_('Altele'))))]
		d['etichete'] = [a for a, b in rand if b]
		d['valori'] = [b for a, b in rand if b]
		text = p.descriere
		if dinFeedulExtern(catalog, p):
			text = (text + '\n' if text else '') + _t(NOTA_EXTERNE)
		elif not hds and p.sursa:
			text = (text + '\n' if text else '') + _t('Pachetul vine dintr-o sursă externă și nu este verificat de HD Satelit.')
		if p.python2 and p.instalat:
			# versiunea din sursa e numai pentru Python 2: nu e o actualizare (0.6.8)
			text = (text + '\n' if text else '') + _t('Versiunea %s din sursa %s e făcută pentru Python 2 și nu se '
				'instalează.') % (p.versiune, s)
		d.update(icoana=P.ICOANE.get(p.categorie, 'altele'), titlu=p.titlu, descriere=text)
		if extra == 'repornire':
			d.update(insigna=_t('Pornește după repornire'), culoare='chihlimbar',
				indiciu=_t('Verde repornește interfața acum'))
		elif p.actualizare:
			d['indiciu'] = _t('OK actualizează · Roșu șterge')
		elif p.instalat:
			d['indiciu'] = _t('Instalat și la zi · Roșu șterge') if p.se_poate_sterge else _t('Instalat și la zi')
		elif p.python2:
			d.update(insigna=_t(INSIGNA_PYTHON2), culoare='rau', descriere=descrierePython2(catalog, fel, obj, extra),
				indiciu=_indiciuPython2(catalog, fel, obj, extra))
		elif p.se_poate_instala:
			d['indiciu'] = _t('OK instalează')
		if areSursa(catalog, p):
			d['indiciu'] = ' · '.join(x for x in (d['indiciu'], _t('Albastru descarcă sursa')) if x)
	elif fel == 'fisier':
		f = obj
		rand = [(_t('Pachet'), f.nume or 'necunoscut'), (_t('Versiune'), f.versiune), (_t('Mărime'), P.marime_text(f.marime)),
			(_t('Fișierul'), f.cale_text)]
		d['etichete'] = [a for a, b in rand if b]
		d['valori'] = [b for a, b in rand if b]
		d.update(icoana='fisier', titlu=f.titlu, insigna=_t('%s, neverificat de HD Satelit') % _t(etichetaLoc(f.cale, f.retea)),
			culoare='chihlimbar', descriere=(f.rezumat + ('\n' + f.descriere if f.descriere else '')).strip())
		if not f.citit:
			# si un .ipk vechi (tar.gz) cu date mari inaintea lui control ajunge aici (citirea se opreste la 16 MB)
			d.update(insigna=_t('Detaliile pachetului nu s-au putut citi'), culoare='rau',
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
		rand = [(_t('Nume'), nume), (_t('Adresa'), adresa), (_t('Pachete'), str(n) if lista else ''), (_t('Lista'), lista or _t('nedescărcată')),
			(_t('Fișierul'), fisier)]
		d['etichete'] = [a for a, b in rand if b]
		d['valori'] = [b for a, b in rand if b]
		if hds:
			d.update(insigna=_t('Sursa HD Satelit, verificată'), culoare='bun',
				descriere=_t('Extensiile făcute și verificate de HD Satelit pentru acest receptor.'))
		else:
			d.update(insigna=_t('Sursă externă, neverificată de HD Satelit'), culoare='chihlimbar',
				descriere=_t('Pachetele din această sursă nu sunt verificate de HD Satelit. Instalează doar ce cunoști.'))
		d.update(icoana='surse', titlu=eticheta if hds else nume)
		if catalog.configurare.e_a_utilizatorului(nume):
			d['indiciu'] = _t('Roșu șterge sursa · Albastru descarcă lista')
		else:
			d['indiciu'] = _t('Albastru descarcă lista')
	elif fel == 'feed':
		d.update(detaliiFeed(catalog, obj))
	elif fel == 'adauga':
		d.update(icoana='surse', titlu=_t('Adaugă o sursă'), insigna=_t('Sursă de pachete de pe internet'), culoare='eticheta',
			descriere=_t('Scrii un nume scurt și adresa depozitului (începe cu http:// sau https://). Pachetele din el '
			'apar apoi în file, cu numele sursei. Nu sunt verificate de HD Satelit.'), indiciu=_t('OK adaugă'))
	elif fel == 'filtru':
		fila, aratate, total = extra
		activ = filtruActiv(obj, fila)
		rand = [(_t('Feedul'), numeFeedFiltru(obj.get('feed') or ''))]
		if fila in FILE_AMESTECATE:
			rand.append((_t('Felul'), numeFelFiltru(obj.get('fel') or '')))
		rand.append((_t('Arătate'), _t('%d din %d') % (aratate, total)))
		d['etichete'] = [a for a, b in rand]
		d['valori'] = [b for a, b in rand]
		d.update(icoana='liste', titlu=_t('Filtrul listei'), insigna=_t('Activ') if activ else _t('Toate pachetele'),
			culoare='chihlimbar' if activ else 'eticheta',
			descriere=_t('Arată numai pachetele dintr-un feed (HD Satelit, Monea Software, sursele tale) sau de un anumit '
			'fel. Filtrul rămâne cât stai în Extensii și se aplică în toate filele cu pachete.'),
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
		d.update(insigna=_t('Sursa HD Satelit, verificată'), culoare='bun',
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
	elif fel == 'pachet':
		if extra == 'repornire':
			verde = N_('Repornește interfața')
		elif obj.actualizare:
			verde = N_('Actualizează')
		elif not obj.instalat and obj.se_poate_instala:
			verde = N_('Instalează')
		elif obj.instalat and pluginPentru(pluginuri, obj) is not None:
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
			rosu = N_('Șterge sursa')
	elif fel == 'adauga':
		verde = N_('Adaugă')
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
TEXT_PYTHON2 = (N_('Pachetul e făcut pentru imaginile vechi, cu Python 2.'),
	N_('Imaginea aceasta are Python 3, deci nu se instalează.'))
BUTON_INLOCUITOR = N_('Instalează înlocuitorul')
TEXT_VERIFICARE = N_('Se verifică pachetul înainte de instalare.')
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
	rand = [(_t('Pachet'), nume or ''), (_t('Versiune'), versiune or ''), (_t('Motivul'), textMotiv(motiv))]
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


# ---------------------------------------------------------------- planurile confirmarilor

def motivOcupat(descarcare=None, program=None):
	"""None cand opkg poate porni acum, altfel (mesaj, culoare): o descarcare a listei sau o alta lucrare in curs (de
	pe televizor sau din pagina), ori o imagine fara opkg. `descarcare`: a ecranului care intreaba."""
	if descarcare is not None or descarcareInCurs():
		return _t('Așteaptă să se termine descărcarea listei.'), 'chihlimbar'
	if lucrareInCurs():
		return _t('Altă instalare rulează acum. Așteaptă să se termine.'), 'chihlimbar'
	if not (program or opkgProgram)():
		return _t('Instalarea pachetelor nu este disponibilă în această imagine.'), 'chihlimbar'
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
	a = (argumente or opkgArguments)('install', [p.nume])
	if a is None:
		return None, (_t('Numele pachetului nu este valid. Nu se instalează.'), 'rau')
	total = p.marime + sum(d.marime for d in dep)
	s, _hds = randSursa(catalog, p)
	rand = [(_t('Versiune'), p.versiune), (_t('Mărime'), P.marime_text(total) or _t('necunoscută')), (_t('Sursa'), s)]
	if dep:
		rand.append((_t('Se mai instalează'), ', '.join(d.titlu for d in dep[:3]) + (' ' + _t('și încă %d') % (len(dep) - 3) if len(dep) > 3 else '')))
	plan = {'fel': 'instaleaza', 'titlu': 'Instalezi %s?' % p.titlu, 'nume': p.titlu, 'subtitlu': p.subtitlu,
		'icoana': P.ICOANE.get(p.categorie, 'altele'), 'randuri': rand, 'nota': _nota(catalog, [p] + dep, nota),
		'externe': surseExterne(catalog, [p] + dep), 'notaCuloare': culoareNota(catalog, [p] + dep),
		'buton': N_('Instalează'), 'argumente': a,
		'repornire': any(x.categorie not in FARA_REPORNIRE_INSTALARE for x in [p] + dep),
		'pachete': [p.nume], 'tinte': [_tinta(p)]}
	_cuVerificare(catalog, plan, [p] + dep, 'install', [p.nume], argumente)
	return plan, None


def deVerificat(catalog, p):
	"""pachetul se descarca si se citeste inainte de instalare: vine dintr-o sursa straina, e o extensie sau un plugin
	de sistem (cod Python) si lista nu spune pentru ce Python e (nici Depends, nici feedul unei imagini cu Python 2)"""
	return dinSursaStraina(catalog, p) and p.categorie in P.H.FELURI_VERIFICATE and p.python2 is None


def _cuVerificare(catalog, plan, pachete, comanda, nume, argumente=None):
	"""Un pachet dintr-o sursa straina se descarca intai (opkg --download-only) si se citeste din cache-ul opkg, inainte
	de instalare (Lucrare): dupa Depends se vede numai o parte din pachetele pentru Python 2 (masurat: 34 din 69)."""
	if not any(deVerificat(catalog, x) for x in pachete):
		return
	v = (argumente or opkgArguments)(comanda, nume, ('--download-only',))
	if v is not None:
		plan['verifica'] = v
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
	a = (argumente or opkgArguments)('upgrade', [p.nume for p in pachete])
	if a is None:
		return None, (_t('Un nume de pachet nu este valid. Nu se actualizează.'), 'rau')
	total = sum(p.marime for p in pachete)
	surse = []
	for p in pachete:
		s = sursaPachet(catalog, p)[0] if len(pachete) > 1 else randSursa(catalog, p)[0]
		if s not in surse:
			surse.append(s)
	if len(pachete) == 1:
		p = pachete[0]
		titlu, nume, sub, ic = 'Actualizezi %s?' % p.titlu, p.titlu, p.subtitlu, P.ICOANE.get(p.categorie, 'altele')
		rand = [(_t('Versiune'), '%s (acum %s)' % (p.versiune, p.versiune_instalata))]
	else:
		# "Actualizeaza toate": lista lor, fiecare cu versiunea noua (cel mult trei randuri, apoi "si inca N")
		titlu, nume, sub, ic = 'Actualizezi %d extensii?' % len(pachete), '%d extensii' % len(pachete), '', 'actualizari'
		lista = [numeCuVersiune(p.titlu, p.versiune) for p in pachete]
		if len(lista) > 3:
			lista = lista[:2] + [_t('și încă %d') % (len(lista) - 2)]
		rand = [(_t('Extensii') if k == 0 else '', x) for k, x in enumerate(lista)]
	rand += [(_t('Mărime'), P.marime_text(total) or _t('necunoscută')), (_t('Sursa'), ', '.join(surse))]
	plan = {'fel': 'actualizeaza', 'titlu': titlu, 'nume': nume, 'subtitlu': sub, 'icoana': ic, 'randuri': rand,
		'nota': _nota(catalog, pachete, nota), 'externe': surseExterne(catalog, pachete),
		'notaCuloare': culoareNota(catalog, pachete), 'buton': N_('Actualizează'), 'argumente': a,
		'repornire': any(p.categorie not in FARA_REPORNIRE_SCHIMBARE for p in pachete),
		'textGata': _t('Gata. Extensiile sunt la zi.') if len(pachete) > 1 else None,
		'pachete': [p.nume for p in pachete], 'tinte': [_tinta(p) for p in pachete]}
	# o versiune noua dintr-o sursa straina se citeste inainte (o actualizare numai pentru Python 2 ar strica pluginul)
	_cuVerificare(catalog, plan, pachete, 'upgrade', [p.nume for p in pachete], argumente)
	return plan, None


def planStergere(catalog, p, argumente=None):
	a = (argumente or opkgArguments)('remove', [p.nume], ('--autoremove',))
	if a is None:
		return None, (_t('Numele pachetului nu este valid. Nu se șterge.'), 'rau')
	s, _hds = randSursa(catalog, p)
	rand = [(_t('Versiune'), p.versiune_instalata), (_t('Eliberează'), P.marime_text(p.marime_instalat) or 'necunoscut'),
		(_t('Sursa'), s)]
	note = []
	if p.din_imagine:
		note.append(_t('Face parte din imagine.'))
	if p.disponibil:
		note.append(_t('O poți instala din nou oricând, din aceeași sursă.'))
	else:
		note.append(_t('Nu se află în nicio sursă, deci nu se va mai putea instala din nou de aici.'))
	return {'fel': 'sterge', 'titlu': _t('Ștergi %s?') % p.titlu, 'nume': p.titlu, 'subtitlu': p.subtitlu,
		'icoana': P.ICOANE.get(p.categorie, 'altele'), 'randuri': rand, 'nota': ' '.join(note), 'externe': [],
		'buton': N_('Șterge'), 'argumente': a, 'repornire': p.categorie not in FARA_REPORNIRE_SCHIMBARE,
		'implicitRenunta': True, 'pachete': [p.nume], 'tinte': [_tinta(p)]}, None


def _tinta(p):
	"""un pachet al planului: numele, titlul, versiunea de dupa (la) si de dinainte (de), daca e modul de acces"""
	return {'nume': p.nume, 'titlu': p.titlu, 'la': p.versiune or '', 'de': p.versiune_instalata or '',
		'acces': p.categorie == 'acces'}


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
	randuri = [_t('Lista pachetelor s-a descărcat.')]
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
	motiv = stare.get('motiv') or _t('Lista pachetelor nu s-a putut descărca.')
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
	cale = P.fisier_ipk_permis(f.cale)
	a = (argumente or opkgArguments)('install', [cale]) if cale else None
	if a is None:
		return None, (_t('Fișierul nu se poate instala de aici (nu mai există sau nu e pe stick, disc sau rețea).'), 'rau')
	rand = [(_t('Pachet'), f.nume or 'necunoscut'), (_t('Versiune'), f.versiune or _t('necunoscută')),
		(_t('Mărime'), P.marime_text(f.marime)), (_t('Fișierul'), f.cale_text)]
	return {'fel': 'fisier', 'titlu': 'Instalezi %s?' % f.titlu, 'nume': f.titlu, 'subtitlu': f.rezumat,
		'icoana': 'fisier', 'randuri': [r for r in rand if r[1]],
		# intai fraza despre verificare: o cale lunga (pana la 255 de semne) o impingea sub marginea notei; calea
		# scurtata la mijloc, ca sa ramana numele fisierului
		'nota': _t('Nu este verificat de HD Satelit. Pachet dintr-un fișier %s: %s') % (deUnde(f.cale, f.retea),
			P.scurt_mijloc(f.cale_text, 70)),
		'externe': [], 'buton': N_('Instalează'), 'argumente': a, 'repornire': True, 'pachete': [f.nume or f.cale]}, None


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
	nu se vada si sa nu se instaleze din Extensii"""
	try:
		try:
			from Components.HdsActualizari import pazeste_listele
		except ImportError:
			from HdsActualizari import pazeste_listele
		sterse = pazeste_listele()
	except Exception as e:
		_jurnal('paza listelor HD Satelit: %s' % e)
		return []
	for nume in sterse:
		scrieJurnal('lista %s stearsa: nu e cea semnata de HD Satelit' % nume)
	return sterse


def pornesteDescarcarea(ipkg=None, inainte=None):
	"""opkg update. `ipkg`: IpkgComponent-ul ecranului, cu ascultatorul lui pus deja; altfel unul nou (pagina).
	Descarcarea se tine aici pana la sfarsit, deci se vede si de pe televizor, si din pagina. La sfarsit:
	STARE['descarcare'] = {'cod', 'motiv', 'cand'} si catalogul paginii se citeste din nou."""
	d = ipkg if ipkg is not None else IpkgComponent()
	linii = []
	STARE['ultima_descarcare'] = time.time()
	if inainte is None:
		inainte = instantaneu(_CATALOG['catalog'])

	def eveniment(e, parametru):
		if e == IpkgComponent.EVENT_LINE:
			linii.append(parametru)
			scrieJurnal(parametru)
		elif e == IpkgComponent.EVENT_DONE:
			d.removeCallback(eveniment)
			STARE['descarcare'] = {'cod': parametru, 'motiv': '' if parametru == 0 else P.motiv_eroare(linii),
				'cand': time.time(), 'inainte': inainte}
			catalogVechi()
	d.addCallback(eveniment)

	def paza(e, _parametru):
		if e == IpkgComponent.EVENT_DONE:
			d.removeCallback(paza)
			pazesteListeleHds()
	# paza listelor HD Satelit inaintea ascultatorului ecranului (pus deja), care citeste
	# catalogul chiar la EVENT_DONE: o lista nesemnata nu se vede nici o data
	ascultatori = getattr(d, 'callbackList', None)
	if isinstance(ascultatori, list):
		ascultatori.insert(0, paza)
	else:
		d.addCallback(paza)
	pastreazaPanaLaSfarsit(d)
	d.startCmd(IpkgComponent.CMD_UPDATE)
	return d


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
		self._instaleaza()

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

		def lucru():
			try:
				stare['rez'] = [(c, P.H.din_ipk(c)) for c in noi]
			except Exception as e:
				_jurnal('verificarea pachetelor: %s' % e)
			stare['gata'] = True
		try:
			from enigma import eTimer
		except ImportError:          # probele de pe PC: pe loc
			lucru()
			self._verificate(stare['rez'])
			return
		# citirea pe un fir separat; rezultatul il culege un eTimer pe firul enigma2 (tragere, ca in HdsLocInregistrari)
		self._ceas = eTimer()

		def uitaTe():
			if stare['gata']:
				self._ceas.stop()
				self._verificate(stare['rez'])
		self._ceas.callback.append(uitaTe)
		P._fire.start_new_thread(lucru, ())
		self._ceas.start(150, False)

	def _verificate(self, rezultate):
		for cale, v in rezultate:
			if v.python2:
				self._refuzPython2(cale, v)
				return
		self._instaleaza()

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
				titlu = texte.get(fel, 'Gata. %s') % numeCuVersiune(t['titlu'], t['de'] if fel == 'sterge' else t['la'])
			else:
				texte = {'instaleaza': _t('Gata. %s este instalat.'), 'fisier': _t('Gata. %s este instalat.'),
					'actualizeaza': _t('Gata. %s este la zi.'), 'sterge': _t('Gata. %s a fost șters.')}
				titlu = self.plan.get('textGata') or (texte.get(fel) or 'Gata. %s') % nume
			stare, culoare = _t('Gata'), 'bun'
			if cod == 0:
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
		else:
			motiv = P.motiv_eroare(self.linii)
			if self.oprit:
				motiv = _t('Oprit după un minut fără răspuns. Verifică legătura la internet.')
			elif cod == -1 and not self.linii and not self.program():
				motiv = _t('Instalarea pachetelor nu este disponibilă în această imagine.')
			texte = {'instaleaza': _t('%s nu a fost instalat.'), 'fisier': _t('%s nu a fost instalat.'),
				'actualizeaza': _t('%s nu a fost actualizat.'), 'sterge': _t('%s nu a fost șters.')}
			titlu = (texte.get(fel) or _t('%s: nu a reușit.')) % nume
			stare, culoare = motiv, 'rau'
			butoane = [N_('Închide')]
		self.rezultat = {'reusit': reusit, 'titlu': titlu, 'stare': stare, 'culoare': culoare, 'butoane': butoane,
			'ales': ales, 'repornire': 'Repornește interfața' in butoane}
		scrieJurnal('---- cod %s' % cod, True)
		# pachetele descarcate de opkg nu mai trebuie (cache-ul e in RAM): sterse acum, nu la repornire (0.6.6)
		try:
			n = P.curata_cache()
			if n:
				scrieJurnal('cache opkg: %s pachete sterse' % n)
		except Exception as e:
			_jurnal('cache opkg: %s' % e)
		catalogVechi()
		self._anunta('gata', cod)


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
		return "un plugin"
	return "%d pluginuri" % n


def _pachete_sursa(n):
	"""un pachet, 2 pachete, 20 pachete (lista surselor de extensii); in alta limba, formele ei de plural (ngettext
	din Components/HdsImportSurse.py, care fara traducere tine regula romaneasca)"""
	try:
		from Components.HdsImportSurse import ngettext
		return ngettext("%d pachet", "%d pachete", n) % n
	except ImportError:
		pass
	if n == 1:
		return "un pachet"
	return "%d pachete" % n
