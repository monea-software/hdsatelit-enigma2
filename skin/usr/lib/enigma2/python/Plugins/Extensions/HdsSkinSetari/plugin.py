# -*- coding: utf-8 -*-
# Copyright (C) 2026 Monea Software pentru HD Satelit (https://hdsatelit.com, contact@moneasoftware.com)
# Licenta: GNU GPL versiunea 2. HDS-MARCA: skin HDSatelit, Monea Software pentru HD Satelit, 2026
#
# Panoul de setari al skinului HDSatelit: intrarea in lista de pluginuri, in meniul de interfata al
# imaginii si verificarea de la pornire. Tot ce e greu (palete, ecrane) se importa doar la deschidere.
# Pe imaginea HDSatelit (din 0.2.6) panoul are intrarea lui in menu.xml (Setari > Interfata si aspect): acolo
# pluginul nu se mai pune in lista de pluginuri si nu se mai agata de meniu, ramane numai verificarea de la pornire.
import os

from Components.config import config, ConfigSubsection, ConfigSelection
from Plugins.Plugin import PluginDescriptor


def _manual():
	try:
		from .texte import tr_str
		return tr_str("set_page_manual")
	except Exception:
		return "Manual"


# pagina tehnica (a doua bara): "0" = manual, doar cu stanga / dreapta (implicit din 24.09.2026); altfel secunde de rotire.
# Valorile salvate inainte (4..20, fara 7, care era implicitul si nu se salva in settings) raman.
try:
	config.plugins.HdsSkin = ConfigSubsection()
	config.plugins.HdsSkin.pagina = ConfigSelection(default="0", choices=[("0", _manual())] + [(str(x), "%d s" % x) for x in (4, 5, 6, 7, 8, 10, 12, 15, 20)])
except Exception:
	pass

# id-urile meniului de interfata, in ordinea preferintei; se foloseste primul care exista in menu.xml
MENIURI = ("osd_setup", "osd_menu", "gui", "system")
_meniu = [None]


def _t(cheie):
	try:
		from .texte import tr_str
		return tr_str(cheie)
	except Exception:
		return "HDSatelit"


def deschide(session, **kwargs):
	from .ecrane import HdsSkinSetari
	session.open(HdsSkinSetari)


def _alege_meniu():
	if _meniu[0] is None:
		ales = "system"
		try:
			for cale in ("/usr/share/enigma2/menu.xml",):
				with open(cale, "rb") as f:
					date = f.read()
				for m in MENIURI:
					if ('"%s"' % m).encode("ascii") in date:
						ales = m
						break
		except Exception:
			pass
		_meniu[0] = ales
	return _meniu[0]


def meniu(menuid, **kwargs):
	try:
		if menuid == _alege_meniu():
			return [(_t("set_title"), deschide, "hds_skin_setari", 60)]
	except Exception:
		pass
	return []


def pornire(reason, session=None, **kwargs):
	"""Dupa o actualizare a pachetului skin.xml vine cu culorile implicite: se pun la loc cele alese.
	Daca .conf a fost sters, skinul cu alte culori revine la cele implicite. Se citesc doar primii 64 kB din skin.xml
	(si palete.txt doar cand skinul nu e pe implicit). Nu reporneste nimic:
	culorile se vad de la urmatoarea pornire a interfetei."""
	if reason != 0 or session is None:
		return
	try:
		from . import paleta as P
		if not os.path.isfile(P.SKIN_XML):
			return
		c = P.citeste_conf()
		if not P.skin_la_zi(c):
			P.scrie_skin(P.paleta_din_conf(c), c["paleta"])
		# pagina tehnica pe tot ecranul sau in fereastra (24.09.2026): skin.xml din pachet vine pe tot ecranul
		if not P.afisaj_la_zi(c):
			P.scrie_afisaj(c["afisaj"])
	except Exception as e:
		print("[HdsSkinSetari] pornire: %s" % e)
	# tastele afisajului detaliat pe celelalte imagini (pe imaginea HDSatelit le are chiar ecranul, nu se face nimic)
	try:
		from . import taste_afisaj
		taste_afisaj.porneste(session)
	except Exception as e:
		print("[HdsSkinSetari] taste afisaj: %s" % e)


def infobar_incarcat(reason=1, session=None, instance=None, **kwargs):
	"""Imaginile cu carligul WHERE_INFOBARLOADED: bara (InfoBar sau MoviePlayer) tocmai a fost creata."""
	if reason != 1 or instance is None:
		return
	try:
		from . import taste_afisaj
		taste_afisaj.urmareste(instance)
	except Exception as e:
		print("[HdsSkinSetari] taste afisaj: %s" % e)


# intrarea panoului in menu.xml-ul imaginii HDSatelit (data/menu.xml, Setari > Interfata si aspect, din 0.2.6)
INTRARE_IMAGINE = b'entryID="hds_skin_setari"'


def _imagineaAreIntrarea(cale="/usr/share/enigma2/menu.xml"):
	"""True pe imaginea HDSatelit, care deschide panoul din meniul ei (Screens/HdsSkinSetari.py): acolo pluginul nu
	se mai pune in lista de pluginuri. Pe celelalte imagini (sau fara menu.xml) False: ramane plugin, ca pana acum."""
	try:
		with open(cale, "rb") as f:
			return INTRARE_IMAGINE in f.read()
	except Exception:
		return False


def Plugins(**kwargs):
	la_pornire = [PluginDescriptor(where=PluginDescriptor.WHERE_SESSIONSTART, fnc=pornire)] + _infobar_incarcat()
	if _imagineaAreIntrarea():
		return la_pornire
	nume = _t("set_title")
	return [
		PluginDescriptor(name=nume, description="hdsatelit.com", where=PluginDescriptor.WHERE_PLUGINMENU, fnc=deschide),
		PluginDescriptor(name=nume, description="hdsatelit.com", where=PluginDescriptor.WHERE_MENU, fnc=meniu),
	] + la_pornire


def _infobar_incarcat():
	"""Carligul WHERE_INFOBARLOADED, doar pe imaginile care il au."""
	w = getattr(PluginDescriptor, "WHERE_INFOBARLOADED", None)
	if w is None:
		return []
	return [PluginDescriptor(where=w, fnc=infobar_incarcat)]
