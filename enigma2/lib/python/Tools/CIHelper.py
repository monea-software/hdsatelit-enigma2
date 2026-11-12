# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# CIHelper.py: alocarea modulelor CI pe canale, ceruta de pluginul de alocare CI al altor imagini (06.11.2026, lotul module-lipsa-071).
# Pluginul scrie pentru fiecare slot /etc/enigma2/ci<slot>.xml (<ci><slot><id>, <caid id="0x..."/>, <provider name dvbnamespace/>,
# <service name ref/>) si cheama cihelper.load_ci_assignment() la pornire si load_ci_assignment(force=True) dupa salvare. Aici fisierele
# se citesc si regulile se dau modulului CI prin eDVBCIInterfaces.setDescrambleRules(slot, (servicii, (furnizor, namespace), caid)),
# functia pe care imaginea o are deja (lib/dvb_ci/dvbci.cpp). Un fisier lipsa sau stricat lasa slotul neatins. Nu arunca.
# Imaginea cheama load_ci_assignment() la pornire (Screens/Ci.py, InitCiConfig), fara plugin.
# Slotul oprit (ci<slot>.oprit langa ci<slot>.xml): nucleul n-are oprirea slotului, deci slotul primeste o regula care
# nu se potriveste cu niciun canal (REGULI_OPRIT); modulul ramane alimentat si meniul lui merge, dar nu mai decodeaza
# nimic. Fisierul alocarilor omului ramane neatins. Regulile noi se folosesc de la urmatoarea schimbare de canal:
# nucleul nu muta un canal care ruleaza deja pe alt slot (recheckPMTHandlers).
import os
import re
import tempfile
import hashlib
import threading
from xml.etree.ElementTree import parse, fromstring, Element, SubElement, ElementTree

DOSAR = "/etc/enigma2"
LAMEDB = "/etc/enigma2/lamedb"
MAX_LAMEDB_OCTETI = 32 * 1024 * 1024
MAX_REGULI = 512
_REF_DVB = re.compile(r"1:0:(?:[0-9a-fA-F]{1,8}:){8}\Z")
# serviciul 0 nu ruleaza niciodata: un slot cu numai regula asta nu primeste niciun canal
REGULI_OPRIT = (["1:0:0:0:0:0:0:0:0:0:"], [], [])
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\ud800-\udfff]")
_EDITOR_LOCK = threading.RLock()
_neaplicate = {}
_deGolit = set()  # sloturi pornite din nou fara alocari valide: primesc o data listele goale


class AlocareSchimbata(ValueError):
	pass


class AlocareNeaplicata(RuntimeError):
	def __init__(self, revizie):
		super().__init__("CI")
		self.revizie = revizie


def caidDinText(text):
	"""CAID-ul scris de om este mereu hexazecimal."""
	if not isinstance(text, str) or not re.fullmatch(r"(?:0[xX])?[0-9a-fA-F]{1,4}", text.strip()):
		raise ValueError("CAID")
	numar = int(text.strip(), 16)
	if not 0 < numar <= 0xffff:
		raise ValueError("CAID")
	return numar


def refCanal(text):
	"""Referinta DVB a unui canal, fara numele pus de buchet: "1:0:" si cele opt campuri ale serviciului. Un canal
	dintr-un buchet cu #DESCRIPTION are numele in referinta (eServiceReference::toString, "...:0:0:0::Nume"), iar
	nucleul compara canalele fara nume; dosarele, marcajele, fluxurile si inregistrarile dau ValueError."""
	if not isinstance(text, str) or len(text) > 512:
		raise ValueError("serviciu")
	parti = text.strip().split(":")
	if len(parti) < 11 or parti[0] != "1" or parti[1] != "0" or parti[10] != "":
		raise ValueError("serviciu")
	campuri = parti[2:10]
	if not all(re.fullmatch(r"[0-9a-fA-F]{1,8}", c) for c in campuri):
		raise ValueError("serviciu")
	return "1:0:" + "".join("%X:" % int(c, 16) for c in campuri)


def _text(text, maxim=256):
	if not isinstance(text, str) or not text.strip() or len(text) > maxim or _CONTROL.search(text):
		raise ValueError("text")
	return text.strip()


def valideazaAlocarea(reguli):
	"""Aceeasi verificare pentru televizor si web, inainte de scriere."""
	if not isinstance(reguli, dict) or set(reguli) != {"servicii", "furnizori", "caid"}:
		raise ValueError("reguli")
	rezultat = {"servicii": [], "furnizori": [], "caid": []}
	for fel in rezultat:
		if not isinstance(reguli[fel], list) or len(reguli[fel]) > MAX_REGULI:
			raise ValueError("reguli")
	for serviciu in reguli["servicii"]:
		if not isinstance(serviciu, dict) or set(serviciu) != {"ref", "name"}:
			raise ValueError("serviciu")
		ref = refCanal(_text(serviciu["ref"], 512))
		nou = {"ref": ref, "name": _text(serviciu["name"])}
		if not any(s["ref"] == ref for s in rezultat["servicii"]):
			rezultat["servicii"].append(nou)
	for furnizor in reguli["furnizori"]:
		if not isinstance(furnizor, dict) or set(furnizor) != {"name", "namespace"}:
			raise ValueError("furnizor")
		ns = furnizor["namespace"]
		if type(ns) is not int or not 0 <= ns <= 0xffffffff:
			raise ValueError("namespace")
		nou = {"name": _text(furnizor["name"]), "namespace": ns}
		if nou not in rezultat["furnizori"]:
			rezultat["furnizori"].append(nou)
	for caid in reguli["caid"]:
		if type(caid) is not int or not 0 < caid <= 0xffff:
			raise ValueError("CAID")
		if caid not in rezultat["caid"]:
			rezultat["caid"].append(caid)
	return rezultat


def citesteDetalii(slot):
	return citesteEditor(slot)["reguli"]


def citesteEditor(slot):
	"""Regulile si revizia provin din aceeasi citire a fisierului."""
	if type(slot) is not int or not 0 <= slot < 4:
		raise ValueError("slot")
	cale = os.path.join(DOSAR, "ci%d.xml" % slot)
	with _EDITOR_LOCK:
		try:
			with open(cale, "rb") as fisier:
				continut = fisier.read()
		except FileNotFoundError:
			continut = None
		revizie = hashlib.sha256(b"lipsa" if continut is None else continut).hexdigest()
		reguli = _detalii(continut)
		return {"reguli": reguli, "revizie": revizie, "neaplicata": _neaplicate.get(slot) == revizie}


def _detalii(continut):
	reguli = {"servicii": [], "furnizori": [], "caid": []}
	if continut is None:
		return reguli
	for nod in fromstring(continut).findall("slot"):
		for serviciu in nod.findall("service"):
			ref = serviciu.get("ref", "")
			reguli["servicii"].append({"ref": ref, "name": serviciu.get("name") or ref})
		for furnizor in nod.findall("provider"):
			reguli["furnizori"].append({"name": furnizor.get("name", ""),
				"namespace": _numar(furnizor.get("dvbnamespace"))})
		for caid in nod.findall("caid"):
			reguli["caid"].append(_numar(caid.get("id")))
	return valideazaAlocarea(reguli)


def _verificaRevizie(slot, revizie):
	if not isinstance(revizie, str) or not re.fullmatch(r"[0-9a-f]{64}", revizie):
		raise ValueError("revizie")
	if citesteEditor(slot)["revizie"] != revizie:
		raise AlocareSchimbata("revizie")


def salveazaEditor(slot, reguli, revizie):
	"""Un editor vechi nu inlocuieste o salvare mai noua TV sau web."""
	with _EDITOR_LOCK:
		_verificaRevizie(slot, revizie)
		salveazaAlocarea(slot, reguli)
		return citesteEditor(slot)


def reaplicaAlocarea(slot, revizie):
	"""Reincearca numai aplicarea starii salvate, fara rescrierea fisierului."""
	with _EDITOR_LOCK:
		_verificaRevizie(slot, revizie)
		if not os.path.isfile(os.path.join(DOSAR, "ci%d.xml" % slot)):
			raise ValueError("reguli")
		_aplicaAlocarea(slot)
		return citesteEditor(slot)


def _verificaSlot(slot):
	if type(slot) is not int or not 0 <= slot < 4:
		raise ValueError("slot")


def _caleOprit(slot):
	return os.path.join(DOSAR, "ci%d.oprit" % slot)


def slotOprit(slot):
	"""Slotul nu primeste niciun canal (oprit din meniul CI sau din web)."""
	_verificaSlot(slot)
	return os.path.isfile(_caleOprit(slot))


def opresteSlot(slot, oprit):
	"""Opreste (oprit=True) sau porneste slotul, fara sa atinga alocarile omului; apoi regulile noi se dau modulului.
	AlocareNeaplicata cand nucleul nu le primeste (starea ramane schimbata pe disc si se aplica la pornire)."""
	_verificaSlot(slot)
	cale = _caleOprit(slot)
	with _EDITOR_LOCK:
		if oprit:
			if not os.path.isfile(cale):
				fd, temporar = tempfile.mkstemp(prefix=".ci%d-" % slot, suffix=".oprit", dir=DOSAR)
				try:
					with os.fdopen(fd, "wb") as fisier:
						fisier.write(b"oprit\n")
						fisier.flush()
						os.fsync(fisier.fileno())
					os.replace(temporar, cale)
				finally:
					if os.path.exists(temporar):
						os.unlink(temporar)
		else:
			if os.path.isfile(cale):
				os.unlink(cale)
			_deGolit.add(slot)
		_aplicaAlocarea(slot)
		return slotOprit(slot)


def reguliEfective(slot):
	"""Regulile date nucleului pentru slot, aceleasi la pornire, la salvare, la reincercare si la oprire / pornire:
	slotul oprit nu primeste nimic; altfel alocarile din ci<slot>.xml. Fara fisier (sau cu unul stricat): None, slotul
	ramane cum e; numai dupa „Pornește slotul” listele goale (alegerea automata a modulului), ca regula de oprire sa
	nu ramana in nucleu."""
	_verificaSlot(slot)
	if slotOprit(slot):
		return tuple(list(x) for x in REGULI_OPRIT)
	reguli = citesteAlocarea(os.path.join(DOSAR, "ci%d.xml" % slot))
	if reguli is None and slot in _deGolit:
		return ([], [], [])
	return reguli


def _aplicaAlocarea(slot):
	try:
		aplicata = cihelper.load_ci_assignment(force=True).get(slot, False)
	except Exception:
		aplicata = False
	if not aplicata:
		revizie = citesteEditor(slot)["revizie"]
		_neaplicate[slot] = revizie
		raise AlocareNeaplicata(revizie)
	_neaplicate.pop(slot, None)


def salveazaAlocarea(slot, reguli):
	"""Scriere atomica, apoi reincarcarea existenta, fara repornire."""
	with _EDITOR_LOCK:
		return _scrieAlocarea(slot, reguli)


def _scrieAlocarea(slot, reguli):
	if type(slot) is not int or not 0 <= slot < 4:
		raise ValueError("slot")
	reguli = valideazaAlocarea(reguli)
	radacina = Element("ci")
	nod = SubElement(radacina, "slot")
	SubElement(nod, "id").text = str(slot)
	for serviciu in reguli["servicii"]:
		SubElement(nod, "service", serviciu)
	for furnizor in reguli["furnizori"]:
		SubElement(nod, "provider", {"name": furnizor["name"], "dvbnamespace": "0x%08X" % furnizor["namespace"]})
	for caid in reguli["caid"]:
		SubElement(nod, "caid", {"id": "0x%04X" % caid})
	fd, temporar = tempfile.mkstemp(prefix=".ci%d-" % slot, suffix=".xml", dir=DOSAR)
	try:
		with os.fdopen(fd, "wb") as fisier:
			ElementTree(radacina).write(fisier, encoding="utf-8", xml_declaration=True)
			fisier.flush()
			os.fsync(fisier.fileno())
		os.replace(temporar, os.path.join(DOSAR, "ci%d.xml" % slot))
	finally:
		if os.path.exists(temporar):
			os.unlink(temporar)
	_aplicaAlocarea(slot)
	return reguli


def _canale():
	from enigma import eServiceCenter, eServiceReference
	centru = eServiceCenter.getInstance()
	cerere = '1:7:1:0:0:0:0:0:0:0: (type == 1) || (type == 2) || (type == 17) || (type == 22) || (type == 25) || (type == 31) || (type == 32) ORDER BY name'
	lista = centru.list(eServiceReference(cerere))
	if lista is not None:
		while True:
			ref = lista.getNext()
			if not ref.valid():
				break
			if _REF_DVB.fullmatch(ref.toString()):
				yield centru, ref


def alegeriAlocare(fel, text="", de_la=0, cate=100):
	"""Canalele si furnizorii din lista receptorului, cu pagini mici in web."""
	from enigma import iServiceInformation
	if fel not in ("servicii", "furnizori"):
		raise ValueError("fel")
	rezultat, vazute = [], set()
	for centru, ref in _canale():
		info = centru.info(ref)
		if info is None:
			continue
		if fel == "servicii":
			nou = {"ref": ref.toString(), "name": info.getName(ref) or ref.toString()}
			cheie = nou["ref"]
		else:
			nume = info.getInfoString(ref, iServiceInformation.sProvider)
			if not nume:
				continue
			nou = {"name": nume, "namespace": ref.getUnsignedData(4)}
			cheie = (nou["name"], nou["namespace"])
		if cheie not in vazute and text.casefold() in nou["name"].casefold():
			vazute.add(cheie)
			rezultat.append(nou)
			if len(rezultat) > de_la + cate:
				break
	return {"alegeri": rezultat[de_la:de_la + cate], "mai_sunt": len(rezultat) > de_la + cate}


def caidLamedb(cale=None, maxim=MAX_LAMEDB_OCTETI):
	"""{CAID: multimea furnizorilor} din lamedb (formatul scris de eDVBDB::saveServicelist): randul de date al fiecarui
	canal are „p:furnizor” si „C:xxxx” (CAID-urile puse la scanare din descriptorul CA_identifier al SDT). Informatia
	statica a unui canal nu da CAID-urile in Python (eDVBService::getInfoObject da numai sTransponderData), de aceea
	se citeste fisierul. Listele din pachete n-au de obicei „C:”. Fisier lipsa, prea mare sau stricat: {}."""
	cale = cale or LAMEDB
	try:
		if os.path.getsize(cale) > maxim:
			return {}
		with open(cale, "r", encoding="utf-8", errors="replace") as fisier:
			text = fisier.read()
	except (IOError, OSError):
		return {}
	text = text.replace("\r", "")
	inceput = text.find("\nservices\n")
	if inceput < 0:
		return {}
	randuri = text[inceput + 10:].split("\n")
	gasite, j = {}, 0
	while j + 2 < len(randuri):
		if randuri[j].startswith("end"):
			break
		date = randuri[j + 2]
		j += 3
		if "C:" not in date:
			continue
		furnizor, caids = "", []
		for camp in date.split(","):
			if camp.startswith("p:"):
				furnizor = camp[2:].strip()
			elif camp.startswith("C:"):
				try:
					caids.append(int(camp[2:6], 16))
				except ValueError:
					pass
		for caid in caids:
			if 0 < caid <= 0xffff:
				gasite.setdefault(caid, set())
				if furnizor:
					gasite[caid].add(furnizor)
	return gasite


def _caidCanalPornit():
	"""(CAID-urile din PMT ale canalului pornit, furnizorul lui); ([], "") fara canal DVB pornit."""
	try:
		import NavigationInstance
		from enigma import iServiceInformation
		serviciu = NavigationInstance.instance.getCurrentService()
		info = serviciu.info() if serviciu is not None else None
		if info is None:
			return [], ""
		caids = info.getInfoObject(iServiceInformation.sCAIDs) or []
		furnizor = info.getInfoString(iServiceInformation.sProvider) or ""
		return [c for c in caids if type(c) is int and 0 < c <= 0xffff], furnizor
	except Exception as e:
		print("[CIHelper] CAID-urile canalului pornit: %r" % (e,))
		return [], ""


def _caidModul(slot):
	"""CAID-urile spuse de modul (ca_info), goale cand modulul nu e gata."""
	try:
		from enigma import eDVBCIInterfaces
		return [c for c in eDVBCIInterfaces.getInstance().readCICaIds(slot) or [] if type(c) is int and 0 < c <= 0xffff]
	except Exception as e:
		print("[CIHelper] CAID-urile modulului din slotul %d: %r" % (slot, e))
		return []


def _numeSistem(caid):
	try:
		from Components.Converter.HdsCommon import caid_name
		return caid_name(caid) or ""
	except Exception:
		return ""


def caidCunoscute(slot, lamedb=None, pornit=None, modul=None):
	"""CAID-urile de ales in editorul de alocari (televizor si web), ca omul sa nu le scrie: cele spuse de modul,
	cele ale canalului pornit si cele din canalele scanate. Fiecare: {"caid", "name" (sistemul si cel mult trei
	furnizori), "modul" (il spune modulul), "acum" (il are canalul pornit)}; intai ale modulului, apoi ale canalului
	pornit, apoi dupa numar. pornit / modul: pentru probe ((caids, furnizor) si lista modulului)."""
	_verificaSlot(slot)
	gasite = {}

	def pune(caid, furnizori=(), **semne):
		x = gasite.setdefault(caid, {"furnizori": set(), "modul": False, "acum": False})
		x["furnizori"].update(f for f in furnizori if f)
		x.update(semne)

	for caid, furnizori in caidLamedb(lamedb).items():
		pune(caid, furnizori)
	caids, furnizor = pornit if pornit is not None else _caidCanalPornit()
	for caid in caids:
		pune(caid, (furnizor,), acum=True)
	for caid in (modul if modul is not None else _caidModul(slot)):
		pune(caid, modul=True)
	rezultat = []
	for caid, x in gasite.items():
		unici = {}
		for f in sorted(x["furnizori"]):
			unici.setdefault(f.casefold(), f)  # „AB Sat” si „AB SAT” din lamedb: un singur nume
		furnizori = sorted(unici.values(), key=lambda f: f.casefold())
		text = ", ".join(furnizori[:3]) + (" +%d" % (len(furnizori) - 3) if len(furnizori) > 3 else "")
		sistem = _numeSistem(caid)
		nume = "%s: %s" % (sistem, text) if sistem and text else (sistem or text)
		rezultat.append({"caid": caid, "name": nume, "modul": x["modul"], "acum": x["acum"]})
	rezultat.sort(key=lambda c: (not c["modul"], not c["acum"], c["caid"]))
	return rezultat


def _numar(text):
	"""0x0b00, 0B00 sau 2816 -> 2816; altfel None"""
	text = (text or "").strip()
	if not text:
		return None
	try:
		if text.lower().startswith("0x"):
			return int(text, 16)
		return int(text)
	except ValueError:
		try:
			return int(text, 16)
		except ValueError:
			return None


def citesteAlocarea(cale):
	"""(servicii, furnizori, caid) din fisierul unui slot, in forma ceruta de setDescrambleRules, sau None (lipsa, stricat)"""
	if not os.path.isfile(cale):
		return None
	try:
		radacina = parse(cale).getroot()
	except Exception as e:
		print("[CIHelper] %s nu se poate citi: %s" % (cale, e))
		return None
	servicii, furnizori, caid = [], [], []
	for slot in radacina.findall("slot"):
		for c in slot.findall("caid"):
			n = _numar(c.get("id"))
			if n is not None and n not in caid:
				caid.append(n)
		for s in slot.findall("service"):
			ref = (s.get("ref") or "").strip()
			if ref and ref not in servicii:
				servicii.append(ref)
		for p in slot.findall("provider"):
			nume = p.get("name") or ""
			ns = _numar(p.get("dvbnamespace"))
			if nume and ns is not None and (nume, ns) not in furnizori:
				furnizori.append((nume, ns))
	return (servicii, furnizori, caid)


class _CIHelper:
	def __init__(self):
		self.incarcat = False

	def load_ci_assignment(self, force=False):
		"""regulile din /etc/enigma2/ci<slot>.xml date fiecarui slot; o singura data, afara de force=True"""
		rezultat = {}
		if self.incarcat and not force:
			return rezultat
		self.incarcat = True
		try:
			from enigma import eDVBCIInterfaces
			ci = eDVBCIInterfaces.getInstance()
			sloturi = ci.getNumOfSlots() if ci is not None else 0
		except Exception as e:
			print("[CIHelper] fara modul CI: %s" % e)
			return rezultat
		for slot in range(min(sloturi or 0, 4)):
			try:
				reguli = reguliEfective(slot)
			except Exception as e:
				print("[CIHelper] slotul %d: %s" % (slot, e))
				rezultat[slot] = False
				continue
			if reguli is None:
				continue  # fara fisier sau cu unul stricat: slotul ramane cum e
			try:
				cod = ci.setDescrambleRules(slot, reguli)
				if cod not in (None, 0):
					raise RuntimeError("CI")
				rezultat[slot] = True
				_deGolit.discard(slot)
				print("[CIHelper] slotul %d: %d canale, %d furnizori, %d CAID" % (slot, len(reguli[0]), len(reguli[1]), len(reguli[2])))
			except Exception as e:
				rezultat[slot] = False
				print("[CIHelper] slotul %d: %s" % (slot, e))
		return rezultat


cihelper = _CIHelper()
