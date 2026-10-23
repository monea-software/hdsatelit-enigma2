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
 - sursele adaugate si sterse de utilizator;
 - descarcarea listei (opkg update) si lucrarea opkg (Lucrare: progres, jurnal scurt, raspunsul N la fisierele de
   configurare schimbate, reincarcarea pluginurilor, textele de la sfarsit, oprirea dupa un minut fara raspuns). Cate
   una odata in tot procesul: ce porneste pagina vede si televizorul, si invers. Iesirea opkg intreaga merge in
   /tmp/hds-extensii.log;
 - catalogul tinut minte pentru pagina (citit din nou numai dupa o schimbare).
opkg porneste numai prin Components/Ipkg.py (lista de argumente, nume verificate, fara shell). Pluginurile
(PluginComponent) si caile se cer numai in functii, ca probele de pe PC sa incarce modulul singur."""
import os
import posixpath       # caile pluginurilor sunt ale receptorului (si in probele de pe PC)
import time

try:
	from Components import HdsPachete as P
except ImportError:  # probe pe PC: modulul incarcat singur, din dosarul Components
	import HdsPachete as P
try:
	from Components.Ipkg import IpkgComponent, opkgArguments, opkgProgram
except ImportError:  # probe pe PC
	from Ipkg import IpkgComponent, opkgArguments, opkgProgram

JURNAL_OPKG = '/tmp/hds-extensii.log'
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


# eticheta filei Surse, aceeasi pe televizor si in pagina web (tradusa la folosire)
ETICHETA_SURSE = N_('Surse')


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

def sursa(catalog, nume):
	"""(eticheta scurta, adresa, e HD Satelit) a unei surse din configurare"""
	if not nume:
		return '', '', False
	adresa = catalog.configurare.adresa(nume)
	if P.sursa_hdsatelit(adresa):
		return 'HD Satelit', adresa, True
	return nume, adresa, False


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
		if not hds and p.sursa:
			x = (p.sursa, P._curat(adresa, 70) if adresa else '')
			if x not in rez:
				rez.append(x)
	return rez


def culoareNota(catalog, pachete):
	"""verde cand totul vine din sursa HD Satelit, altfel chihlimbar"""
	if pachete and all(p.sursa and sursaPachet(catalog, p)[2] for p in pachete):
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
	"""(id, eticheta, numar) al filei Surse, ultima pe televizor si in pagina web; eticheta tradusa."""
	return ('surse', _t(ETICHETA_SURSE), len(catalog.configurare.surse))


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
		rez = [('sursa', s, None) for s in catalog.configurare.surse]
		rez.append(('adauga', None, None))
		return rez
	return [('pachet', p, None) for p in catalog.din_categoria(fila)]


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
		if p is not None:
			mic.append(sursaPachet(catalog, p)[0])
			if p.versiune_instalata:
				mic.append(p.versiune_instalata)
		return (P.ICOANE.get(cat, 'extensii'), obj.name or '', obj.description or '', insigna, culoare, ' · '.join(mic))
	if fel == 'pachet':
		p = obj
		if extra == 'repornire':
			insigna, culoare = _t('După repornire'), 'chihlimbar'
		elif p.actualizare:
			insigna, culoare = _t('Actualizare'), 'chihlimbar'
		elif p.instalat:
			insigna, culoare = _t('Instalat'), 'bun'
		else:
			insigna = culoare = None
		mic = [x for x in (sursaPachet(catalog, p)[0], textVersiuni(p), P.marime_text(p.marime or p.marime_instalat)) if x]
		return (P.ICOANE.get(p.categorie, 'altele'), p.titlu, p.subtitlu, insigna, culoare, ' · '.join(mic))
	if fel == 'fisier':
		f = obj
		pInstalat = catalog._toate.get(f.nume) if f.nume else None
		if not f.citit:
			insigna, culoare = _t('Nu se poate citi'), 'rau'
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
		if not hds and p.sursa:
			text = (text + '\n' if text else '') + _t('Pachetul vine dintr-o sursă externă și nu este verificat de HD Satelit.')
		d.update(icoana=P.ICOANE.get(p.categorie, 'altele'), titlu=p.titlu, descriere=text)
		if extra == 'repornire':
			d.update(insigna=_t('Pornește după repornire'), culoare='chihlimbar',
				indiciu=_t('Verde repornește interfața acum'))
		elif p.actualizare:
			d['indiciu'] = _t('OK actualizează · Roșu șterge')
		elif p.instalat:
			d['indiciu'] = _t('Instalat și la zi · Roșu șterge') if p.se_poate_sterge else _t('Instalat și la zi')
		elif p.se_poate_instala:
			d['indiciu'] = _t('OK instalează')
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
	elif fel == 'adauga':
		d.update(icoana='surse', titlu=_t('Adaugă o sursă'), insigna=_t('Sursă de pachete de pe internet'), culoare='eticheta',
			descriere=_t('Scrii un nume scurt și adresa depozitului (începe cu http:// sau https://). Pachetele din el '
			'apar apoi în file, cu numele sursei. Nu sunt verificate de HD Satelit.'), indiciu=_t('OK adaugă'))
	return d


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
		if obj.se_poate_sterge:
			rosu = N_('Șterge')
	elif fel == 'fisier':
		verde = N_('Instalează') if obj.utf8 else ''
	elif fel == 'sursa':
		if catalog.configurare.e_a_utilizatorului(obj[0]):
			rosu = N_('Șterge sursa')
	elif fel == 'adauga':
		verde = N_('Adaugă')
	return rosu, verde


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
	a = (argumente or opkgArguments)('install', [p.nume])
	if a is None:
		return None, (_t('Numele pachetului nu este valid. Nu se instalează.'), 'rau')
	dep = catalog.dependente_de_instalat(p)
	total = p.marime + sum(d.marime for d in dep)
	s, _hds = randSursa(catalog, p)
	rand = [(_t('Versiune'), p.versiune), (_t('Mărime'), P.marime_text(total) or _t('necunoscută')), (_t('Sursa'), s)]
	if dep:
		rand.append((_t('Se mai instalează'), ', '.join(d.titlu for d in dep[:3]) + (' ' + _t('și încă %d') % (len(dep) - 3) if len(dep) > 3 else '')))
	return {'fel': 'instaleaza', 'titlu': 'Instalezi %s?' % p.titlu, 'nume': p.titlu, 'subtitlu': p.subtitlu,
		'icoana': P.ICOANE.get(p.categorie, 'altele'), 'randuri': rand, 'nota': _nota(catalog, [p] + dep, nota),
		'externe': surseExterne(catalog, [p] + dep), 'notaCuloare': culoareNota(catalog, [p] + dep),
		'buton': N_('Instalează'), 'argumente': a, 'repornire': p.categorie not in ('extensions', 'picons', 'settings'),
		'pachete': [p.nume]}, None


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
		titlu, nume, sub, ic = 'Actualizezi %d extensii?' % len(pachete), '%d extensii' % len(pachete), '', 'actualizari'
		nume_ = ', '.join(p.titlu for p in pachete[:3]) + (' ' + _t('și încă %d') % (len(pachete) - 3) if len(pachete) > 3 else '')
		rand = [(_t('Extensii'), nume_)]
	rand += [(_t('Mărime'), P.marime_text(total) or _t('necunoscută')), (_t('Sursa'), ', '.join(surse))]
	return {'fel': 'actualizeaza', 'titlu': titlu, 'nume': nume, 'subtitlu': sub, 'icoana': ic, 'randuri': rand,
		'nota': _nota(catalog, pachete, nota), 'externe': surseExterne(catalog, pachete),
		'notaCuloare': culoareNota(catalog, pachete), 'buton': N_('Actualizează'), 'argumente': a, 'repornire': True,
		'textGata': _t('Gata. Extensiile sunt la zi.') if len(pachete) > 1 else None,
		'pachete': [p.nume for p in pachete]}, None


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
		'buton': N_('Șterge'), 'argumente': a, 'repornire': True, 'implicitRenunta': True, 'pachete': [p.nume]}, None


def planFisier(f, argumente=None):
	if not f.utf8:
		return None, (_t('Numele fișierului nu se poate citi pe receptor. Redenumește-l fără diacritice.'), 'rau')
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

def scrieJurnal(linie):
	"""iesirea opkg, intreaga, pentru service: /tmp/hds-extensii.log (in memorie, cel mult 256 KB; fara a urma o
	legatura simbolica pusa in locul fisierului)"""
	try:
		mod = os.O_WRONLY | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0)
		try:
			if os.path.getsize(JURNAL_OPKG) > 262144:
				mod |= os.O_TRUNC
			else:
				mod |= os.O_APPEND
		except OSError:
			mod |= os.O_APPEND
		fd = os.open(JURNAL_OPKG, mod, 0o600)
		with os.fdopen(fd, 'a') as fh:
			fh.write('%s %s\n' % (time.strftime('%H:%M:%S'), P._curat(linie, 400)))
	except (IOError, OSError):
		pass


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


def pornesteDescarcarea(ipkg=None):
	"""opkg update. `ipkg`: IpkgComponent-ul ecranului, cu ascultatorul lui pus deja; altfel unul nou (pagina).
	Descarcarea se tine aici pana la sfarsit, deci se vede si de pe televizor, si din pagina. La sfarsit:
	STARE['descarcare'] = {'cod', 'motiv', 'cand'} si catalogul paginii se citeste din nou."""
	d = ipkg if ipkg is not None else IpkgComponent()
	linii = []
	STARE['ultima_descarcare'] = time.time()

	def eveniment(e, parametru):
		if e == IpkgComponent.EVENT_LINE:
			linii.append(parametru)
			scrieJurnal(parametru)
		elif e == IpkgComponent.EVENT_DONE:
			d.removeCallback(eveniment)
			STARE['descarcare'] = {'cod': parametru, 'motiv': '' if parametru == 0 else P.motiv_eroare(linii),
				'cand': time.time()}
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
		scrieJurnal('---- %s %s' % (self.plan.get('fel'), ' '.join(self.plan.get('argumente') or ())))
		self.ipkg.runCmd(self.plan.get('argumente'))

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
		if cod == 0:
			texte = {'instaleaza': _t('Gata. %s este instalat.'), 'fisier': _t('Gata. %s este instalat.'),
				'actualizeaza': _t('Gata. %s este la zi.'), 'sterge': _t('Gata. %s a fost șters.')}
			titlu = self.plan.get('textGata') or (texte.get(fel) or 'Gata. %s') % nume
			stare, culoare = _t('Gata'), 'bun'
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
		self.rezultat = {'reusit': cod == 0, 'titlu': titlu, 'stare': stare, 'culoare': culoare, 'butoane': butoane,
			'ales': ales, 'repornire': 'Repornește interfața' in butoane}
		scrieJurnal('---- cod %s' % cod)
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
