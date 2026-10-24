# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsImportRetea.py: rețeaua din copia altei imagini, aplicată după import (Components/HdsImportSurse.incheie_importul),
# pe firul enigma2, prin aceleași funcții ca ecranele de rețea ale imaginii: HdsRetea.aplicaPlaca și scrieDns pentru
# cablu (atributele lui iNetwork, ifdown / ifup, /etc/network/interfaces, /etc/resolv.conf) și HdsWlan.ConectareWlan
# pentru Wi-Fi (blocul rețelei în wpa_supplicant.conf, placa pornită din nou, așteptarea legăturii și a adresei).
# Planul vine din HdsImportExtra.citeste_retea: felul conexiunii (DHCP sau adresă fixă) pe cablu și pe Wi-Fi și rețeaua
# Wi-Fi. Placa de cablu a copiei merge pe prima placă de cablu a receptorului, cea Wi-Fi pe prima placă Wi-Fi.
#
# Pașii: proba legăturii de acum (iNetwork.checkNetworkState: 3 adrese din internet), fișierele rețelei ținute minte,
# cablul, Wi-Fi-ul, apoi proba: o placă configurată trebuie să fie activă (legată și cu adresă) în TERMEN_ADRESA_S, iar
# dacă înainte internetul mergea, trebuie să meargă și acum (HdsRetea.confirmat). Altfel fișierele de dinainte se pun la
# loc și rețeaua repornește (iNetwork.restartNetwork): receptorul se întoarce singur la ce era. Pe televizor nu apare
# nimic; rezultatul (fără parolă) merge în rezumatul importului și în web. Parola Wi-Fi nu se scrie în jurnal: trece
# numai în ConectareWlan, care o uită după ce face blocul rețelei.
#
# Modulul nu importă nimic din enigma2 la încărcare: probele de pe PC dau o rețea falsă (R), conectarea, ceasul și
# starea plăcilor.

import os

FISIERE = ("/etc/network/interfaces", "/etc/resolv.conf", "/etc/wpa_supplicant.conf")
TERMEN_ADRESA_S = 40
PAS_MS = 2000


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


def _jurnal(text):
	print("[HdsImportRetea] %s" % text)


def _citeste(cale):
	try:
		with open(cale, "rb") as f:
			return f.read()
	except (IOError, OSError):
		return None


def aplica(plan, gata, **optiuni):
	"""Pornește aplicarea planului; gata({"adus": bool, "intors": bool, "mesaje": [texte]}) vine o dată, pe firul
	enigma2. Întoarce AplicareRetea (ținută în viață de ea însăși până la capăt)."""
	a = AplicareRetea(plan, gata, **optiuni)
	a.porneste()
	return a


_VII = []


class AplicareRetea(object):

	def __init__(self, plan, gata, R=None, conectare=None, timer=None, stare=None, fisiere=FISIERE,
			scrie_inapoi=None, este_wifi=None):
		self.plan = plan or {}
		self.gata = gata
		self.R = R
		self.conectare = conectare
		self.timer = timer
		self.stare = stare
		self.fisiere = fisiere
		self.scrie_inapoi = scrie_inapoi
		self.este_wifi = este_wifi
		self.copii = {}
		self.placi = []
		self.internet_inainte = False
		self.secunde = 0
		self.mesaje = []
		self.terminat = False
		self.ceas = None
		self.wlan = None

	# ---- unelte
	def net(self):
		if self.R is None:
			from Components.Network import iNetwork
			self.R = iNetwork
		return self.R

	def _wifi(self, placa):
		if self.este_wifi is not None:
			return self.este_wifi(placa)
		try:
			if self.net().isWirelessInterface(placa):
				return True
		except Exception:
			pass
		return os.path.exists("/sys/class/net/%s/wireless" % placa) or os.path.exists("/sys/class/net/%s/phy80211" % placa)

	def _stare(self, placa):
		if self.stare is not None:
			return self.stare(placa)
		from Components import HdsRetea
		return HdsRetea.stareAdaptor(placa, self.net().getAdapterAttribute(placa, "ip"))

	def _ceas(self, functie):
		if self.timer is not None:
			t = self.timer()
		else:
			from enigma import eTimer
			t = eTimer()
		t.callback.append(functie)
		return t

	# ---- pașii
	def porneste(self):
		_VII.append(self)
		try:
			from Components import HdsRetea
			placi = list(HdsRetea.adaptoare(self.net()))
		except Exception as eroare:
			_jurnal("plăcile: %s" % eroare.__class__.__name__)
			placi = []
		self.cablu = next((p for p in placi if not self._wifi(p)), None)
		self.wifi = next((p for p in placi if self._wifi(p)), None)
		for cale in self.fisiere:
			self.copii[cale] = _citeste(cale)
		try:
			self.net().checkNetworkState(self._inainte)
		except Exception as eroare:
			_jurnal("proba de dinainte: %s" % eroare.__class__.__name__)
			self._inainte(3)

	def _inainte(self, esecuri):
		from Components import HdsRetea
		self.internet_inainte = HdsRetea.confirmat(esecuri)
		self._aplica_cablu()

	def _aplica_cablu(self):
		d = self.plan.get("cablu")
		if not d:
			self._aplica_wifi()
			return
		if self.cablu is None:
			self.mesaje.append(_("Receptorul nu are placă de rețea pe cablu; setările cablului din copie au rămas deoparte."))
			self._aplica_wifi()
			return
		from Components import HdsRetea
		R = self.net()
		self.placi.append(self.cablu)
		_jurnal("cablul pe %s: %s" % (self.cablu, "dhcp" if d["dhcp"] else "adresă fixă"))
		if not d["dhcp"] and self.plan.get("dns"):
			HdsRetea.scrieDns(self.plan["dns"], R)
		HdsRetea.aplicaPlaca(self.cablu, True, d["dhcp"], d["ip"], d["masca"], None if d["dhcp"] else d.get("poarta"),
			R.getAdapterAttribute(self.cablu, "up"), self._dupa_cablu, R)

	def _dupa_cablu(self, ok=True):
		if not self.terminat:
			self._aplica_wifi()

	def _aplica_wifi(self):
		d = self.plan.get("wifi")
		if not d:
			self._verifica()
			return
		retea = d.get("retea")
		if self.wifi is None:
			self.mesaje.append(_("Receptorul nu are placă Wi-Fi; rețeaua Wi-Fi din copie a rămas deoparte."))
			self._uita()
			self._verifica()
			return
		R = self.net()
		self.placi.append(self.wifi)
		R.setAdapterAttribute(self.wifi, "dhcp", d["dhcp"])
		if not d["dhcp"]:
			R.setAdapterAttribute(self.wifi, "ip", d["ip"])
			R.setAdapterAttribute(self.wifi, "netmask", d["masca"])
			if d.get("poarta"):
				R.setAdapterAttribute(self.wifi, "gateway", d["poarta"])
			if self.plan.get("dns") and not (self.plan.get("cablu") and not self.plan["cablu"]["dhcp"]):
				from Components import HdsRetea
				HdsRetea.scrieDns(self.plan["dns"], R)
		_jurnal("Wi-Fi pe %s: %s" % (self.wifi, "dhcp" if d["dhcp"] else "adresă fixă"))
		fabrica = self.conectare
		if fabrica is None:
			from Components.HdsWlan import ConectareWlan as fabrica
		self.wlan = fabrica(self.wifi, retea.ssid, retea.securitate, retea.parola, retea.ascunsa,
			show=lambda text: None, finished=self._dupa_wifi, network=R)
		self._uita()
		self.wlan.begin()

	def _uita(self):
		"""Parola nu mai stă în plan după ce a ajuns la ConectareWlan."""
		d = self.plan.get("wifi") or {}
		retea = d.get("retea")
		if retea is not None:
			retea.parola = None
		d["retea"] = None

	def _dupa_wifi(self, rezultat):
		if self.terminat:
			return
		if not rezultat:
			self._intoarce(_("Receptorul nu s-a putut lega la rețeaua Wi-Fi din copie."))
			return
		self._verifica()

	def _verifica(self):
		if not self.placi:
			self._termina(False, False)
			return
		self.secunde = 0
		self.ceas = self._ceas(self._pas)
		self.ceas.start(PAS_MS, False)

	def _pas(self):
		if self.terminat:
			return
		self.secunde += PAS_MS // 1000
		activa = False
		for placa in self.placi:
			try:
				activa = activa or bool(self._stare(placa).get("activa"))
			except Exception:
				pass
		if activa:
			self.ceas.stop()
			try:
				self.net().checkNetworkState(self._dupa_proba)
			except Exception:
				self._dupa_proba(0)
			return
		if self.secunde >= TERMEN_ADRESA_S:
			self.ceas.stop()
			self._intoarce(_("Cu setările de rețea din copie receptorul nu a primit adresă."))

	def _dupa_proba(self, esecuri):
		if self.terminat:
			return
		from Components import HdsRetea
		if HdsRetea.confirmat(esecuri) or not self.internet_inainte:
			self._termina(True, False)
		else:
			self._intoarce(_("Cu setările de rețea din copie receptorul nu mai ajungea la internet."))

	def _intoarce(self, motiv):
		"""Fișierele rețelei de dinainte la loc și rețeaua pornită din nou cu ele."""
		self.mesaje.append(motiv)
		if self.wlan is not None:
			try:
				self.wlan.stop()
			except Exception:
				pass
		scrie = self.scrie_inapoi
		if scrie is None:
			from Components.HdsWlan import writeBack as scrie
		for cale, date in self.copii.items():
			scrie(cale, date, cale.endswith("wpa_supplicant.conf"))
		_jurnal("rețeaua din copie nu a mers; fișierele de dinainte sunt la loc")
		try:
			self.net().restartNetwork(lambda *_a: self._termina(False, True))
		except Exception as eroare:
			_jurnal("repornirea rețelei: %s" % eroare.__class__.__name__)
			self._termina(False, True)

	def _termina(self, adus, intors):
		if self.terminat:
			return
		self.terminat = True
		if self.ceas is not None:
			self.ceas.stop()
		mesaje = list(self.mesaje)
		if adus:
			from Components import HdsImportExtra
			texte = HdsImportExtra.descriere_retea(dict((k, self.plan.get(k)) for k in ("cablu", "wifi")
				if (k == "cablu" and self.cablu and self.plan.get(k)) or (k == "wifi" and self.wifi and self.plan.get(k))))
			mesaje.append(_("Rețeaua din copie: %s.") % "; ".join(texte))
		elif intors:
			mesaje.append(_("Am pus la loc rețeaua de dinainte."))
		rez = {"adus": bool(adus), "intors": bool(intors), "mesaje": mesaje}
		if self in _VII:
			_VII.remove(self)
		try:
			self.gata(rez)
		except Exception as eroare:
			_jurnal("după rețea: %s" % eroare.__class__.__name__)
