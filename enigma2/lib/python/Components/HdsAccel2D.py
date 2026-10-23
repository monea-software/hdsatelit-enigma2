# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsAccel2D.py: setarea „Accelerare 2D pe placa video".
#
# Desenul ecranului poate folosi motorul 2D al placii (TDE HiSilicon, prin libhiaccel): umplerile mari de
# dreptunghiuri si copierile simple de 32 de biti. Partea din C++ (lib/gdi/accel.cpp) hotaraste la pornirea interfetei:
#   - intai ce exista: /dev/hi_tde, receptorul u4/u5, biblioteca libhiaccel.so (incarcata cu dlopen numai cand se
#     foloseste; o imagine fara ea porneste la fel); daca lipseste ceva, desenul ramane pe procesor fara niciun mesaj,
#     iar setarea nu se arata (nici pe televizor, nici in web);
#   - accelerarea e PORNITA implicit: o imagine noua nu are niciun fisier si incearca placa. Singurul comutator de
#     oprire e /etc/enigma2/hds-fara-accel, pus de alegerea „Oprita” de aici, de C++ dupa o cadere cu placa pornita, de
#     tools/enigma2.sh dupa 3 opriri neasteptate in 10 minute, sau de mana din ssh (touch, cand ecranul nu se mai
#     vede); primul lui rand e motivul. /etc/enigma2/hds-cu-accel (fisierul imaginilor in care accelerarea trebuia
#     pornita) nu mai inseamna nimic: cu el sau fara el accelerarea e pornita; se sterge la urmatoarea alegere;
#   - face o proba (umplere si copiere intr-o memorie care nu se vede, citite inapoi), iar in timpul folosirii
#     verifica fiecare apel; la orice esec deseneaza cu procesorul;
#   - cat placa deseneaza tine semnul /tmp/hds-accel.activ, sters la iesirea curata a enigma2; gasit la pornire (o
#     cadere a interfetei cu placa folosita, pusa la loc si de tools/enigma2.sh dupa o iesire prin semnal, afara de
#     oprirea ceruta de paznic, care nu e o cadere: dupa ea enigma2.sh sterge semnul si pe cel de pe disc) = scrie
#     hds-fara-accel si deseneaza cu procesorul (codul „cadere-in-lucru”), ca o cadere a bibliotecii sa nu reporneasca
#     interfata in bucla;
#   - in primele 10 minute cu placa folosita tine si semnul /etc/enigma2/hds-accel.lucru (pe disc, trece de o
#     repornire a receptorului, pe care /tmp nu o vede: blocarea nucleului si paznicul, sau o pana de curent); gasit la
#     a doua pornire la rand = scrie hds-fara-accel (codul „repornire”), ca o placa ce blocheaza nucleul sa nu
#     reporneasca receptorul in bucla;
#   - scrie ce s-a intamplat in /tmp/hds-accel.stare: „pornit"/„oprit"/„asteapta", un cod si detalii.
# Aici: setarea config.usage.hds_accel_2d pune sau scoate fisierul de oprire. FISIERUL e adevarul, iar setarea il
# urmeaza la pornire. Schimbarea se vede la urmatoarea pornire a interfetei. Aceleasi functii le foloseste pagina web
# (HdsWebControl/accel_web.py). Tot aici, dupa 10 minute cu interfata vie (un ceas al buclei principale), se sterge
# semnul hds-accel.lucru: pornirea cu placa a mers, numaratoarea repornirilor o ia de la capat.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC il folosesc direct.

import os

FISIER_OPRIT = '/etc/enigma2/hds-fara-accel'
# fisierul imaginilor in care accelerarea trebuia pornita: fara efect acum, sters la urmatoarea alegere
FISIER_VECHI = '/etc/enigma2/hds-cu-accel'
FISIER_STARE = '/tmp/hds-accel.stare'
# semnul pus de accel.cpp cand placa incepe sa deseneze (HISI_WORK_MARK); sters de aici dupa FEREASTRA_MS
FISIER_LUCRU = '/etc/enigma2/hds-accel.lucru'
FEREASTRA_MS = 10 * 60 * 1000
# primul rand pus in FISIER_OPRIT de alegerea „Oprita” (C++ il scrie in starea de la pornire, ca detaliu)
MOTIV_SETARE = 'oprita din setari'
# inceputul primului rand pus de oprirea automata (accel.cpp, tools/enigma2.sh)
MOTIV_AUTOMAT = 'oprita automat'

# codul scris de accel.cpp -> ce inseamna, in cuvinte simple (pagina web si jurnalul)
TEXTE_COD = {
	'ok': 'Pornită: umplerile mari se fac pe placa video.',
	'asteapta-proba': 'Pornită, dar proba de la pornire nu s-a făcut încă.',
	'setare': 'Oprită din setări: totul se desenează cu procesorul.',
	'cadere': 'Oprită singură: pornirea plăcii de data trecută nu s-a terminat (interfața sau receptorul s-a oprit '
		'între timp). Se poate porni din nou din setări.',
	'cadere-in-lucru': 'Oprită singură: interfața s-a oprit neașteptat cât placa video desena ecranul. Se poate porni '
		'din nou din setări.',
	'repornire': 'Oprită singură: receptorul a repornit de două ori la rând în primele 10 minute cât placa video '
		'desena ecranul (blocare sau pană de curent). Se poate porni din nou din setări.',
	'lipsa-tde': 'Nu există: receptorul nu are motorul 2D (/dev/hi_tde lipsește).',
	'alt-receptor': 'Nu există: receptorul nu este din familia u4/u5.',
	'lipsa-biblioteca': 'Nu există: biblioteca plăcii (libhiaccel.so) lipsește din imagine.',
	'lipsa-showiframe': 'Oprită: programul de sistem al plăcii (showiframe) nu pornise încă.',
	'biblioteca': 'Oprită: biblioteca plăcii (libhiaccel.so) nu s-a putut încărca.',
	'functie': 'Oprită: biblioteca plăcii nu are funcțiile cunoscute (altă versiune a ei).',
	'init': 'Oprită: biblioteca plăcii nu a pornit motorul 2D.',
	'proba': 'Oprită: proba de la pornire a ieșit greșit, totul se desenează cu procesorul.',
	'memorie': 'Oprită: nu este memorie pentru probă.',
	'eroare': 'Oprită în timpul folosirii: placa a lucrat greșit sau prea încet. Totul se desenează cu procesorul până '
		'la următoarea pornire a interfeței.',
}
# codurile care spun ca receptorul (sau imaginea) nu are deloc accelerarea 2D: setarea nu se arata
CODURI_INDISPONIBIL = ('lipsa-tde', 'alt-receptor', 'lipsa-biblioteca')
TEXT_NECUNOSCUT = 'Nu există în interfața pornită acum (versiune fără accelerarea 2D) sau interfața încă pornește.'
# codul „setare” cu motivul pus de oprirea automata (fisierul de oprire nu l-a pus omul)
TEXT_OPRITA_AUTOMAT = ('Oprită singură, după o problemă cu placa video: totul se desenează cu procesorul. Se poate '
	'porni din nou din setări.')


def pornita_in_setari():
	"""True daca la urmatoarea pornire a interfetei accelerarea are voie sa porneasca: fisierul de oprire lipseste.
	Implicit (imagine noua, fara fisiere): True."""
	return not os.path.exists(FISIER_OPRIT)


def seteaza(pornita):
	"""pornita=True: scoate fisierul de oprire (alegerea omului trece peste oprirea automata); pornita=False: pune
	fisierul de oprire, numai daca lipseste (salvarea ecranului de setari cheama si ea notificarea: un motiv scris de
	oprirea automata ramane). Fisierul vechi de pornire se sterge daca exista. Intoarce True daca a reusit."""
	try:
		if pornita:
			if os.path.exists(FISIER_OPRIT):
				os.remove(FISIER_OPRIT)
		elif not os.path.exists(FISIER_OPRIT):
			with open(FISIER_OPRIT, 'w') as f:
				f.write(MOTIV_SETARE + '\n')
		if os.path.exists(FISIER_VECHI):
			os.remove(FISIER_VECHI)
		return True
	except Exception as eroare:
		print('[HdsAccel2D] nu pot schimba %s: %s' % (FISIER_OPRIT, eroare))
		return False


def stare(cale=None):
	"""Ce a hotarat interfata la pornire: {'stare': 'pornit'|'oprit'|'asteapta'|None, 'cod', 'text', 'detalii'}."""
	try:
		with open(cale or FISIER_STARE) as f:
			randuri = f.read(2000).split('\n')
	except Exception:
		return {'stare': None, 'cod': '', 'text': TEXT_NECUNOSCUT, 'detalii': ''}
	cuvant = randuri[0].strip() if randuri else ''
	cod = randuri[1].strip() if len(randuri) > 1 else ''
	detalii = randuri[2].strip() if len(randuri) > 2 else ''
	if cuvant not in ('pornit', 'oprit', 'asteapta'):
		return {'stare': None, 'cod': cod, 'text': TEXT_NECUNOSCUT, 'detalii': detalii}
	text = TEXTE_COD.get(cod, cuvant)
	if cod == 'setare' and detalii.startswith(MOTIV_AUTOMAT):
		text = TEXT_OPRITA_AUTOMAT
	return {'stare': cuvant, 'cod': cod, 'text': text, 'detalii': detalii}


def disponibila(cale=None):
	"""True daca receptorul si interfata pornita au accelerarea 2D (setarea se arata pe televizor si in web): C++ a
	scris starea la pornire si nu a gasit lipsa placa, alt receptor sau lipsa biblioteca. Fara fisierul de stare
	(interfata construita fara accelerare, de exemplu emulatorul de pe PC): False."""
	s = stare(cale)
	return s['stare'] is not None and s['cod'] not in CODURI_INDISPONIBIL


# ultima valoare pusa pe disc de setare (sau citita la pornire); notificarea schimba fisierul numai cand valoarea
# setarii e alta: salvarea unui ecran (toate randurile) sau config.usage.save() nu sterge un hds-fara-accel pus intre
# timp din ssh sau de alta parte
_aplicata = [None]
# ceasul care inchide fereastra de 10 minute (tinut aici, altfel se pierde)
_fereastra = []


def _aplica(element):
	valoare = bool(element.value)
	if valoare == _aplicata[0]:
		return
	if seteaza(valoare):
		_aplicata[0] = valoare


def inchideFereastra():
	"""Interfata a trait 10 minute cu placa folosita: semnul de pe disc se sterge, o repornire de acum nu mai e pusa pe
	seama placii. Intoarce True daca semnul nu mai exista."""
	try:
		if os.path.exists(FISIER_LUCRU):
			os.remove(FISIER_LUCRU)
		return True
	except Exception as eroare:
		print('[HdsAccel2D] nu pot sterge %s: %s' % (FISIER_LUCRU, eroare))
		return False


def pornesteFereastra():
	"""Daca placa deseneaza (accel.cpp a scris semnul la aceasta pornire), porneste ceasul de 10 minute. Pe un receptor
	fara placa, sau cu ea oprita, nu face nimic (semnul lipseste)."""
	del _fereastra[:]
	if not os.path.exists(FISIER_LUCRU):
		return False
	try:
		from enigma import eTimer
		ceas = eTimer()
		ceas.callback.append(inchideFereastra)
		ceas.start(FEREASTRA_MS, True)
		_fereastra.append(ceas)
		return True
	except Exception as eroare:
		print('[HdsAccel2D] fereastra de 10 minute: %s' % eroare)
		return False


def initConfig():
	"""Din InitUsageConfig: setarea urmeaza fisierul de oprire (implicit pornita); o schimbare din ecranul de setari
	pune sau scoate fisierul pe loc, iar „Renunta" il aduce inapoi la valoarea salvata (notificarea e chemata si la
	salvare si la renuntare, dar schimba fisierul numai cand valoarea difera de cea pusa ultima data).
	SystemInfo["HdsAccel2D"] ascunde randul din setup.xml (requires) pe un receptor fara accelerare. Porneste si ceasul
	de 10 minute al semnului hds-accel.lucru."""
	from Components.config import config, ConfigYesNo
	element = ConfigYesNo(default=True)
	config.usage.hds_accel_2d = element
	element.value = pornita_in_setari()
	_aplicata[0] = bool(element.value)
	element.save()
	element.callNotifiersOnSaveAndCancel = True
	element.addNotifier(_aplica, initial_call=False)
	try:
		from Components.SystemInfo import SystemInfo
		SystemInfo["HdsAccel2D"] = disponibila()
	except Exception as eroare:
		print('[HdsAccel2D] SystemInfo: %s' % eroare)
	pornesteFereastra()
