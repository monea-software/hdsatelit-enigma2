# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsConfigurareTraducere - configurarea traducerii subtitrarilor (Components/HdsTraducereSubtitrari.py) dintr-o
# cheie lipita sau dintr-o adresa de server: serviciul recunoscut dupa forma cheii, adresa adusa la forma buna, lista
# modelelor citita si un model ales, o traducere de proba, apoi cheia si setarile salvate; cautarea serverelor din
# casa (Ollama, LibreTranslate) in reteaua receptorului.
#
# FIRELE: toate cererile HTTP merg pe un fir separat (niciodata pe firul enigma2). Rezultatul se pune intr-o lista sub
# lacat, iar firul trezeste firul enigma2 prin T.Trezire (pipe + eSocketNotifier, plasa eTimer), ca Traducator.
# Numai pe firul enigma2 (proceseaza): cheia scrisa (T.chei().schimba), setarile puse si salvate, configfile.save(),
# T.instanta().ultima_proba completat si mesajul pe televizor. Valorile din setari (limba tinta, serviciul ales, cheia
# pentru schimbarea modelului) se citesc pe firul care porneste lucrarea, inainte de fir.
#
# CHEILE: cheia nu apare niciodata in stare(), in jurnal sau in mesaje; orice text care vine de la un server trece
# prin _faraCheie. O cheie nerecunoscuta nu pleaca nicaieri (omul alege serviciul); o cheie cu forma altui furnizor
# cunoscut (sk-ant-, :adm) nu se trimite. HTTPS cu certificatele verificate, fara redirectionari (T.trimite). O cheie
# noua pleaca numai pe https sau spre un server din reteaua de acasa; cheia deja salvata a unui server (libre, openai)
# pleaca numai spre gazda de care e legata (T.cheiePentru), iar la salvare cheia noua se leaga de adresa probata.
# ADRESELE: adresa receptorului insusi (127.x, localhost, 0.0.0.0, 169.254.x, IP-urile lui) e refuzata la scriere
# (normalizeazaAdresa) si la conectare (T.verificaConexiunea, si pentru numele care se rezolva in receptor).
#
# PRINCIPALUL: o cheie lipita pentru alt serviciu decat cel principal nu-i ia locul cand principalul merge
# (_principalRamane: traducerea pornita, campurile lui complete, ultima lui proba fara cheie refuzata sau cota
# terminata, nici oprit in lant pana la schimbarea setarilor, dupa refuzurile cheii sau pana a doua zi): serviciul
# cheii intra in rezerve (primul, daca nu era deja in lista), cu cheia si campurile lui, iar mesajul spune ca
# traducerea ramane pe principal
# (stare(): rezerva, principal, principal_nume). Altfel serviciul cheii devine principal, ca inainte; tot asa la cheia
# chiar a principalului, la serverul din casa ales anume (porneste_server) si la modelul schimbat (porneste_model).
# Omul il face principal dupa aceea cu „Fă-l principal” (T.punePrincipal, pe televizor si in web).
# FOSTUL PRINCIPAL nu iese din lant: cand serviciul cheii (sau serverul din casa ales) ia locul principalului, iar
# fostul principal avea campurile complete (de exemplu cheia lui a fost refuzata la proba), fostul intra primul in
# rezerve, ca la Fa-l principal; stare()["nota_rezerve"] spune asta (televizor, web).
#
# GROQ SI CLOUDFLARE WORKERS (adresa fixa, modelul ales din T.MODELE_GROQ / T.MODELE_CLOUDFLARE): cheia gsk_ se
# recunoaste ca Groq (lista modelelor citita cu cheia, fara cota, apoi proba cu modelul din setari sau primul propus);
# Cloudflare se alege anume si cere ID-ul contului (cont, 32 de semne hex; gol = cel din setari).
#
# API (ecranul de pe televizor, pagina pas cu pas din HdsWebControl):
#   normalizeazaAdresa(serviciu, text) -> (adresa, eroare)
#   recunoasteCheie(text) -> [{"serviciu", "adresa", "nume"}] in ordinea incercarilor
#   alegeModel(fel, modele, implicit=None) -> nume ("" daca nu e niciunul potrivit)
#   REGIUNI_AZURE, AJUTOR_RETEA
#   configurator().porneste_cheie(cheie, serviciu="auto", regiune="", fara_proba=False, cont="") -> (ok, mesaj)
#   configurator().porneste_server(serviciu, adresa, model="", cheie="") -> (ok, mesaj)
#   configurator().porneste_model(model) -> (ok, mesaj)
#   configurator().stare() -> dict fara cheie
#   cautare().porneste(tinte=None, laGata=None) -> (ok, mesaj); cautare().stare() -> dict

from __future__ import absolute_import

import json
import re
import socket
import threading
import time
from collections import deque

try:
	import queue as _coada
except ImportError:		# Python 2 (probele vechi); pe receptor e Python 3
	import Queue as _coada

try:
	from urllib.parse import urlsplit, quote
except ImportError:
	from urlparse import urlsplit
	from urllib import quote

def N_(text):
	"""marcaj pentru xgettext (--keyword=N_), fara efect; textul se traduce la folosire cu _()"""
	return text


# ------------------------------------------------------------------ reglaje

TERMEN_LISTA_S = 10.0           # lista modelelor
TERMEN_PROBA_S = 15.0           # proba la serviciile din internet
TERMEN_PROBA_CASA_S = 10.0      # prima cerere spre un server din casa
TERMEN_INCARCARE_S = 60.0       # reincercarea dupa termen depasit: modelul se incarca pe calculator
PRAG_LENT_MS = 1000             # peste atat, subtitrarile traduse nu mai vin la timp
MAX_PROBE_MODELE = 3            # modelele Ollama probate la o configurare
PRAG_FAMILIE = 70               # scorul familiei de la care un model Ollama traduce bine in romana
MAX_MILIARDE_PROBA = 14.5       # peste atatia parametri un model nu tine pasul cu subtitrarile pe un calculator obisnuit
MAX_PAGINI_GEMINI = 5
PAGINA_GEMINI = 1000
PAGINA_GEMINI_MICA = 100
MAX_MODELE = 300                # numele de modele tinute in stare
MAX_CHEIE = 512

CAUTARE_FIRE = 32
CAUTARE_TERMEN_CONECTARE_S = 0.3
CAUTARE_TERMEN_HTTP_S = 2.0
CAUTARE_MAX_HTTP = 16
CAUTARE_MAX_S = 15.0
CAUTARE_MAX_TINTE = 1024

PORT_OLLAMA = 11434
PORT_LIBRE = 5000
PORT_IMPLICIT = {"libre": PORT_LIBRE, "openai": PORT_OLLAMA}
ID_MESAJ = "HdsConfigurareTraducere"
AGENT = "HDSatelit-receptor"

GEMINI_MODELE = "https://generativelanguage.googleapis.com/v1beta/models"
BAZA_GROQ = "https://api.groq.com/openai/v1"
BAZA_OPENROUTER = "https://openrouter.ai/api/v1"
BAZA_OPENAI = "https://api.openai.com/v1"

# (cod, numele din portal); "" = Global (primul). Lista comuna e T.REGIUNI_AZURE cand exista (regiuniAzure()); asta e
# rezerva, aceeasi ca in Screens/HdsTraducereSubtitrari.py
REGIUNI_AZURE = (("", "Global"), ("westeurope", "West Europe"), ("northeurope", "North Europe"),
	("germanywestcentral", "Germany West Central"), ("francecentral", "France Central"), ("swedencentral", "Sweden Central"),
	("uksouth", "UK South"), ("switzerlandnorth", "Switzerland North"))
TERMEN_REGIUNE_S = 6.0          # o cerere scurta pe regiune, cand regiunea resursei Azure se cauta singura
# msgid, traduse la folosire cu _t() (ca toate textele pentru om din modul; jurnalul ramane netradus)
MESAJ_REGIUNE_LIPSA = N_("Lipsește regiunea resursei Azure: o găsești în portal, la resursa Translator, Overview › "
	"Location (de exemplu Germany West Central = germanywestcentral).")
MESAJ_REGIUNE_GRESITA = N_("Cheia sau regiunea nu se potrivesc: verifică amândouă în portal (Keys and Endpoint).")

# pasii aratati cand cautarea nu gaseste niciun server (web si televizor: msgid, tradus la folosire cu _t(), in
# Cautare._lucru)
AJUTOR_RETEA = (
	N_("Ollama ascultă din fabrică numai pe calculatorul lui. În Ollama 0.9.5 sau mai nou: Settings, pornește „Expose "
		"Ollama to the network”."),
	N_("Sau: închide Ollama de lângă ceas, pune variabila de mediu OLLAMA_HOST cu valoarea 0.0.0.0:11434 și pornește din "
		"nou Ollama."),
	N_("LM Studio: fila „Developer”, „Start server” și „Serve on Local Network”. Căutarea nu-l găsește: scrie adresa de "
		"mână (portul 1234), ca server compatibil OpenAI."),
	N_("Windows: la întrebarea paravanului apasă „Allow access”. Altfel: Windows Security, „Allow an app through "
		"firewall”, bifează Ollama la „Private”."),
	N_("Rețeaua de acasă pe calculator trebuie să fie „Private network” (Settings › Network & internet), iar receptorul "
		"și calculatorul în același router."),
)

NUME = {"gemini": "Gemini", "google": "Google Cloud Translation", "deepl": "DeepL API", "azure": "Azure Translator",
	"libre": "LibreTranslate", "openai": N_("Server compatibil OpenAI"), "groq": "Groq",
	"cloudflare": "Cloudflare Workers"}


def _numeAfisat(serviciu):
	"""numele serviciului pentru om; numai „Server compatibil OpenAI” se traduce, celelalte sunt nume de servicii"""
	return _t(NUME[serviciu]) if serviciu == "openai" else NUME.get(serviciu, serviciu)

SERVICII_CHEIE = ("gemini", "google", "deepl", "azure", "openai", "libre", "groq", "cloudflare")
# serviciile cu model ales de om la adresa lor fixa (lista propusa in T.MODELE_GROQ / T.MODELE_CLOUDFLARE)
CU_MODEL_FIX = ("groq", "cloudflare")
_CONT = re.compile(r"^[0-9a-f]{32}$")

E_CHEIE, E_COTA, E_RETEA, E_TERMEN, E_RASPUNS, E_LIMBA, E_LIPSA, E_ADRESA = (
	"cheie", "cota", "retea", "termen", "raspuns", "limba", "lipsa", "adresa")


def _jurnal(text):
	print("[HdsConfigurareTraducere] %s" % text)


def _t(text):
	try:
		return _(text)
	except NameError:
		return text


def _modulT(T=None):
	if T is not None:
		return T
	from Components import HdsTraducereSubtitrari
	return HdsTraducereSubtitrari


def _setare(s, camp, implicit=u""):
	"""valoarea unei setari care poate lipsi (ConfigSubsection da KeyError, nu AttributeError)"""
	try:
		return getattr(s, camp).value
	except (KeyError, AttributeError):
		return implicit


def _faraCheie(text, chei):
	"""textul fara nicio aparitie a cheilor date (raspunsurile serverelor pot repeta cheia)"""
	t = u"%s" % (text if text is not None else u"")
	for c in chei:
		if c and len(c) >= 4:
			t = t.replace(c, u"***")
	return t


class _Oprire(Exception):
	"""o incercare care nu a mers: felul erorii, textul pentru om si ce sa faca"""

	def __init__(self, fel, text, ce_faci=u"", cod=None, cod_intern=None, regiune_lipsa=False):
		Exception.__init__(self, fel)
		self.fel, self.text, self.ce_faci, self.cod = fel, text, ce_faci, cod
		self.cod_intern = cod_intern
		self.regiune_lipsa = regiune_lipsa


def _oprireDin(e):
	"""_Oprire dintr-o EroareTraducere: cu ceasul receptorului in urma (Components/HdsCeasHttps.py) cauza si ce sa faca
	vin de acolo, nu „Verifică internetul receptorului”."""
	return _Oprire(e.fel, getattr(e, "cauza", None) or e.text, getattr(e, "ce_faci", u"") or u"", e.cod)


def codIntern(corp, cod=None):
	"""codul de eroare al serviciului din corpul raspunsului (Azure: error.code, de ex. 401000; Google: error.status),
	sau None"""
	try:
		j = json.loads(corp.decode("utf-8", "replace") if isinstance(corp, bytes) else corp)
	except (ValueError, TypeError, AttributeError):
		return None
	e = j.get("error") if isinstance(j, dict) else None
	if not isinstance(e, dict):
		# Cloudflare: {"success": false, "errors": [{"code": 5035, "message": ...}]}
		lista = j.get("errors") if isinstance(j, dict) else None
		if isinstance(lista, list) and lista and isinstance(lista[0], dict):
			c = lista[0].get("code")
			if isinstance(c, int) and not isinstance(c, bool):
				return c
			if isinstance(c, str) and c.strip():
				return c.strip()[:40]
		return None
	c = e.get("code")
	if isinstance(c, int) and not isinstance(c, bool) and c != cod:
		return c
	if isinstance(c, str) and c.strip():
		return c.strip()[:40]
	st = e.get("status")
	if isinstance(st, str) and st.strip():
		return st.strip()[:40]
	return c if isinstance(c, int) and not isinstance(c, bool) else None


def regiuniAzure(T=None):
	"""[(cod, nume din portal)]: lista comuna T.REGIUNI_AZURE daca exista, altfel REGIUNI_AZURE; Global primul"""
	try:
		lista = getattr(_modulT(T), "REGIUNI_AZURE", None)
	except Exception:
		lista = None
	rez = []
	for r in lista or REGIUNI_AZURE:
		if isinstance(r, (list, tuple)) and r:
			cod, nume = u"%s" % r[0], u"%s" % (r[1] if len(r) > 1 else r[0])
		else:
			cod = nume = u"%s" % r
		if cod.lower() == "global":
			cod = u""
		if not any(x[0] == cod for x in rez):
			rez.append((cod, nume or u"Global"))
	if not any(x[0] == u"" for x in rez):
		rez.insert(0, (u"", u"Global"))
	return rez


def _regiuneScrisa(text):
	"""regiunea scrisa de om: codul („westeurope”) sau numele din portal („West Europe”, „(Europe) West Europe”)"""
	r = re.sub(r"^\(.*?\)\s*", "", (text or "").strip())
	return re.sub(r"[\s_\-]", "", r).lower()


# ------------------------------------------------------------------ adresele serverelor

_SUFIXE = {
	"libre": ("/translate", "/languages"),
	"openai": ("/chat/completions", "/models", "/api/tags", "/api/chat", "/api/generate"),
}
_GAZDA_BUNA = re.compile(r"^[a-z0-9._\-:]+$")


def normalizeazaAdresa(serviciu, text, T=None):
	"""adresa unui server LibreTranslate sau compatibil OpenAI, adusa la forma pe care o foloseste traducerea:
	http:// pus daca lipseste, portul implicit daca lipsesc si schema si portul, fara „/” la final, fara caile
	cererilor (/translate, /chat/completions...). Adresa receptorului insusi e refuzata (T.clasaGazda, fara DNS).
	-> (adresa, "") sau ("", eroare pe intelesul omului)"""
	if serviciu not in PORT_IMPLICIT:
		return "", _t("Serviciul ales nu are adresă de server.")
	a = (text or "").strip()
	if not a:
		return "", _t("Scrie adresa serverului, de exemplu http://192.168.1.50:%d.") % PORT_IMPLICIT[serviciu]
	if len(a) > 300 or any(c.isspace() or ord(c) < 33 for c in a):
		return "", _t("Adresa are spații sau caractere care nu pot fi într-o adresă.")
	fara_schema = "://" not in a
	if fara_schema:
		a = "http://" + a.lstrip("/")
	try:
		p = urlsplit(a)
		port = p.port
	except ValueError:
		return "", _t("Portul din adresă nu e bun: trebuie un număr între 1 și 65535.")
	schema = (p.scheme or "").lower()
	if schema not in ("http", "https"):
		return "", _t("Adresa trebuie să înceapă cu http:// sau https://.")
	if "@" in (p.netloc or ""):
		return "", _t("Adresa nu poate avea nume de utilizator sau parolă. Scrie numai adresa serverului; cheia, dacă "
			"serverul cere una, se pune separat.")
	gazda = (p.hostname or "").lower()
	if not gazda or not _GAZDA_BUNA.match(gazda):
		return "", _t("Adresa nu are numele sau IP-ul serverului.")
	if port == 0:
		return "", _t("Portul din adresă nu e bun: trebuie un număr între 1 și 65535.")
	if fara_schema and port is None:
		port = PORT_IMPLICIT[serviciu]
	try:
		M = _modulT(T)
		if M.clasaGazda(gazda, port or {"http": 80, "https": 443}[schema]) == M.RECEPTOR:
			return "", M.textAdresaOprita(M.RECEPTOR, gazda)
	except (ImportError, AttributeError):
		pass
	cale = (p.path or "").rstrip("/")
	schimbat = True
	while schimbat:
		schimbat = False
		for s in _SUFIXE[serviciu]:
			if cale.lower().endswith(s):
				cale = cale[:-len(s)].rstrip("/")
				schimbat = True
	nume = ("[%s]" % gazda) if ":" in gazda else gazda
	return "%s://%s%s%s" % (schema, nume, (":%d" % port) if port else "", cale), ""


def _inCasa(adresa, T=None):
	try:
		return bool(_modulT(T).adresaInCasa(adresa))
	except Exception:
		return False


# ------------------------------------------------------------------ recunoasterea cheii

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_HEX32 = re.compile(r"^[0-9a-fA-F]{32}$")
_AZURE_LUNG = re.compile(r"^[A-Za-z0-9]{70,100}$")
_GHILIMELE = u"\"'`\u201c\u201d\u201e\u00ab\u00bb"


def curataCheieLipita(text):
	"""cheia asa cum a fost lipita, fara ghilimele, fara „Bearer ” / „DeepL-Auth-Key ” / „NUME_CHEIE=” in fata si fara
	spatii; "" daca nu ramane nimic"""
	if text is None:
		return ""
	v = u"%s" % text
	for _i in range(2):
		v = v.strip().strip(_GHILIMELE).strip()
		m = re.match(r"^(?:bearer|deepl-auth-key)\s+(\S+)$", v, re.I)
		if m:
			v = m.group(1)
		m = re.match(r"^[A-Z][A-Z0-9_]{2,40}\s*=\s*(\S+)$", v)
		if m:
			v = m.group(1)
	return u"".join(v.split())


def _cheieBuna(v):
	return bool(v) and len(v) <= MAX_CHEIE and all(33 <= ord(c) <= 126 for c in v)


def _cand(serviciu, adresa="", nume=None):
	return {"serviciu": serviciu, "adresa": adresa, "nume": nume or _numeAfisat(serviciu)}


def recunoasteCheie(text):
	"""serviciile la care se potriveste forma cheii, in ordinea incercarilor (gol daca forma nu se recunoaste)"""
	v = curataCheieLipita(text)
	if not _cheieBuna(v):
		return []
	if v.endswith(":adm"):
		return []			# cheie de administrare DeepL: nu traduce
	if v.endswith(":fx") or _UUID.match(v):
		return [_cand("deepl")]
	if v.startswith("AIza") or v.startswith("AQ."):
		return [_cand("gemini"), _cand("google")]	# lista modelelor Gemini nu consuma cota: Gemini intai
	if v.startswith("gsk_"):
		return [_cand("groq")]
	if v.startswith("sk-or-"):
		return [_cand("openai", BAZA_OPENROUTER, "OpenRouter")]
	if v.startswith("sk-ant-"):
		return []			# alt furnizor, fara traducere aici: cheia nu pleaca nicaieri
	if v.startswith("sk-"):
		return [_cand("openai", BAZA_OPENAI, "OpenAI")]
	if _HEX32.match(v) or _AZURE_LUNG.match(v):
		return [_cand("azure")]
	return []


# ------------------------------------------------------------------ alegerea modelului

_NU_GEMINI = ("preview", "exp", "tts", "image", "live", "embed", "aqa", "audio", "veo", "imagen", "learnlm",
	"robotics", "computer-use", "thinking", "native")


def _numeGemini(n):
	n = (u"%s" % (n or u"")).strip()
	return n[7:] if n.startswith("models/") else n


def _versiuneGemini(n):
	m = re.search(r"gemini-(\d+)(?:\.(\d+))?", n)
	return (int(m.group(1)), int(m.group(2) or 0)) if m else (0, 0)


def _modelGeminiImplicit():
	try:
		return _modulT().MODEL_GEMINI_IMPLICIT
	except Exception:
		return "gemini-3.5-flash-lite"


def _modeleFixe(serviciu, T=None):
	"""modelele propuse la Groq si la Cloudflare Workers (primul e cel din fabrica)"""
	try:
		M = _modulT(T)
		return list({"groq": M.MODELE_GROQ, "cloudflare": M.MODELE_CLOUDFLARE}[serviciu])
	except Exception:
		return {"groq": ["openai/gpt-oss-20b"], "cloudflare": ["@cf/google/gemma-4-26b-a4b-it"]}.get(serviciu, [])


def _modelImplicit(serviciu, T=None):
	m = _modeleFixe(serviciu, T)
	return m[0] if m else u""


def _alegeGemini(modele, implicit):
	nume = [_numeGemini(m) for m in modele if m]
	if implicit and implicit in nume:
		return implicit
	bune = [n for n in nume if n.startswith("gemini-") and not any(r in n for r in _NU_GEMINI)]
	for fel in ("flash-lite", "flash"):
		lista = [n for n in bune if fel in n and (fel == "flash-lite" or "flash-lite" not in n)]
		if lista:
			return sorted(lista, key=lambda n: (_versiuneGemini(n), -len(n)), reverse=True)[0]
	if bune:
		return sorted(bune, key=lambda n: (_versiuneGemini(n), -len(n)), reverse=True)[0]
	return nume[0] if nume else ""


# Ollama: scorul familiei (dupa inceputul numelui, altfel dupa details.family). translategemma cere un prompt de alta
# forma decat cel al traducerii: ramane in lista, dar nu se alege singur. qwen2.5 traduce slab in romana.
_FAMILII_OLLAMA = (
	("translategemma", 0), ("gemma3n", 78), ("gemma3", 90), ("gemma4", 86), ("gemma2", 70), ("aya-expanse", 80),
	("aya", 74), ("qwen3", 72), ("qwen2.5", 45), ("qwen2", 40), ("mistral-nemo", 66), ("mistral-small", 68),
	("mistral", 60), ("llama3.3", 64), ("llama3.1", 62), ("llama3.2", 60), ("llama3", 58), ("llama", 45),
	("phi4", 50), ("phi", 35), ("granite", 40),
)
_RAU_OLLAMA = (("guard", -200), ("code", -70), ("coder", -10), ("deepseek-r1", -50), ("uncensored", -40),
	("abliterated", -40), ("math", -50), ("vision", -10), ("ocr", -60), ("sql", -60))


def _miliarde(m, nume):
	d = m.get("details") if isinstance(m.get("details"), dict) else {}
	t = (u"%s" % (d.get("parameter_size") or u"")).strip().upper()
	r = re.match(r"^([\d.]+)\s*([KMBT]?)", t)
	if r:
		try:
			return float(r.group(1)) * {"K": 1e-6, "M": 1e-3, "B": 1.0, "T": 1000.0, "": 1.0}[r.group(2)]
		except ValueError:
			pass
	r = re.search(r"[:\-_](\d+(?:\.\d+)?)b\b", nume.lower())
	if r:
		return float(r.group(1))
	marime = m.get("size")
	if isinstance(marime, (int, float)) and marime > 0:
		return marime / 0.6e9		# cam 0,6 GB pe miliard de parametri (Q4)
	return None


def _inNor(m, nume):
	"""modelele „cloud” din Ollama trimit textul in afara casei"""
	n = nume.lower()
	return bool(m.get("remote_host") or m.get("remote_model")) or n.endswith(":cloud") or n.endswith("-cloud") \
		or ":cloud" in n


def scorOllama(m):
	"""scorul unui model din /api/tags pentru traducere (None = nu se alege singur: embedding, in nor, fara text)"""
	r = _scoruriOllama(m)
	return r[1] if r else None


def potrivitOllama(m):
	"""familia traduce bine (gemma, aya, qwen3), fara modelele de cod sau de gandire lunga, si modelul nu e prea mare
	pentru un calculator de acasa"""
	r = _scoruriOllama(m)
	return bool(r) and r[0] >= PRAG_FAMILIE and (r[2] is None or r[2] <= MAX_MILIARDE_PROBA)


def _scoruriOllama(m):
	"""(scorul familiei cu numele rele scazute, scorul intreg cu marimea, miliardele de parametri) sau None"""
	if not isinstance(m, dict):
		return None
	nume = u"%s" % (m.get("name") or m.get("model") or u"")
	if not nume:
		return None
	n = nume.lower()
	d = m.get("details") if isinstance(m.get("details"), dict) else {}
	familia = (u"%s" % (d.get("family") or u"")).lower()
	familii = [(u"%s" % f).lower() for f in (d.get("families") or []) if f]
	cap = [(u"%s" % c).lower() for c in (m.get("capabilities") or [])]
	if "embed" in n or "bert" in familia or any("bert" in f for f in familii) or "embedding" in cap:
		return None
	if cap and "completion" not in cap:
		return None
	if _inNor(m, nume):
		return None
	baza = n.split(":")[0].split("/")[-1]
	scor = None
	for f, s in _FAMILII_OLLAMA:
		if baza.startswith(f):
			scor = s
			break
	if scor is None:
		for f, s in _FAMILII_OLLAMA:
			if familia.startswith(f.replace(".", "")) or familia == f:
				scor = s
				break
	if scor is None:
		scor = 30
	if baza.startswith("translategemma"):
		return -1000, -1000, None	# numai ales de om
	for r, s in _RAU_OLLAMA:
		if r in n:
			scor += s
	familie = scor
	if "thinking" in cap:
		scor -= 8			# gandurile intarzie raspunsul
	b = _miliarde(m, nume)
	if b is None:
		scor += 10
	elif b < 0.8:
		scor -= 40
	elif b < 1.5:
		scor -= 5
	elif b < 3:
		scor += 15
	elif b <= 5:
		scor += 35			# mic si bun: gemma3:4b inaintea lui gemma3:12b
	elif b <= 9.5:
		scor += 26
	elif b <= 14.5:
		scor += 12
	elif b <= 35:
		scor -= 20
	else:
		scor -= 45
	return familie, scor, b


def ordineOllama(modele, numai_potrivite=False):
	"""modelele din /api/tags bune pentru traducere, cel mai bun intai (acelasi fisier sub doua nume: o data);
	numai_potrivite: numai familiile care traduc bine si modelele nu prea mari (potrivitOllama)"""
	vazute = set()
	lista = []
	for m in modele or []:
		r = _scoruriOllama(m)
		if r is None or r[1] <= -500 or (numai_potrivite and not potrivitOllama(m)):
			continue
		s = r[1]
		nume = u"%s" % (m.get("name") or m.get("model"))
		lista.append((-s, len(nume), nume, m.get("digest") or nume))
	lista.sort()
	rez = []
	for _s, _l, nume, semn in lista:
		if semn in vazute:
			continue
		vazute.add(semn)
		rez.append(nume)
	return rez


_PREFERINTE_OPENAI = ("gemma-3", "gemma3", "gemma-4", "gemma4", "llama-3.3-70b", "gpt-oss-20b", "llama-3.1-8b",
	"qwen3", "gpt-4.1-mini", "gpt-4o-mini", "gpt-5-mini", "gpt-5-nano", "mistral-small", "llama", "mistral")
_NU_OPENAI = ("embed", "whisper", "tts", "guard", "moderation", "audio", "realtime", "image", "dall-e", "transcribe",
	"search", "rerank", "code", "vision", "orpheus", "playai", "compound", "translategemma")


def _alegeOpenAI(modele):
	ids = [u"%s" % m for m in modele if m]
	bune = [i for i in ids if not any(r in i.lower() for r in _NU_OPENAI)]
	for p in _PREFERINTE_OPENAI:
		lista = [i for i in bune if p in i.lower()]
		if lista:
			return sorted(lista, key=lambda i: (i.endswith(":free"), len(i), i))[0]
	if bune:
		return bune[0]
	return ""


def alegeModel(fel, modele, implicit=None):
	"""fel "gemini" (nume models/...), "ollama" (dict din /api/tags) sau "openai" (id din /models) -> nume sau "" """
	modele = list(modele or [])
	if fel == "gemini":
		return _alegeGemini(modele, implicit if implicit is not None else _modelGeminiImplicit())
	if fel == "ollama":
		o = ordineOllama(modele)
		return o[0] if o else ""
	if fel == "openai":
		return _alegeOpenAI(modele)
	return ""


# ------------------------------------------------------------------ ce sa faca omul

def _serviciuOprit(corp):
	t = corp.decode("utf-8", "replace") if isinstance(corp, bytes) else u"%s" % (corp or u"")
	return "SERVICE_DISABLED" in t or "accessNotConfigured" in t or "has not been used in project" in t


def ceFaci(fel, serviciu, nume=u"", local=False, adresa=u"", corp=b"", cod=None, tinta=u""):
	"""ce sa faca omul dupa o eroare (pagina web si televizor; tradus cu _t)"""
	if fel == E_ADRESA:
		return _t("Scrie adresa calculatorului din casă (de exemplu http://192.168.1.50:11434) sau a serverului din "
			"internet, cu https://.")
	if fel == E_CHEIE:
		if local:
			return (_t("Serverul de la %s cere o cheie. Scrie cheia serverului, sau pornește serverul fără cheie.") %
				(adresa or _t("adresa scrisă")))
		if serviciu == "gemini":
			return _t("Copiaz-o întreagă din pagina cheii, fără spații. Cheia pentru Gemini se face pe "
				"aistudio.google.com/apikey.")
		if serviciu == "google":
			if _serviciuOprit(corp):
				return _t("Cheia e bună, dar în proiectul ei nu e pornit „Cloud Translation API”. În Google Cloud "
					"(console.cloud.google.com) mergi la „APIs & Services”, caută „Cloud Translation API”, apasă "
					"„Enable”, așteaptă câteva minute și încearcă din nou.")
			return _t("Copiaz-o întreagă din pagina cheii (console.cloud.google.com/apis/credentials), fără spații. În "
				"proiectul cheii pornește „Cloud Translation API” și verifică să nu fie cheia restrânsă la alt API.")
		if serviciu == "azure":
			return _t("Copiaz-o întreagă din portal (resursa Translator, „Keys and Endpoint”, KEY 1), fără spații, și "
				"verifică regiunea: scrisă exact ca în portal (de exemplu westeurope), sau Global dacă resursa e globală.")
		if serviciu == "deepl":
			return _t("Copiaz-o întreagă din pagina cheilor DeepL (www.deepl.com/your-account/keys), fără spații. "
				"Trebuie o cheie de la DeepL API, nu de la traducătorul obișnuit.")
		if serviciu == "openai":
			pagina = {"Groq": "console.groq.com/keys", "OpenRouter": "openrouter.ai/settings/keys",
				"OpenAI": "platform.openai.com/settings/organization/api-keys"}.get(nume)
			if pagina:
				return _t("Copiaz-o întreagă din pagina cheilor (%s), fără spații.") % pagina
		if serviciu == "groq":
			return _t("Copiaz-o întreagă din pagina cheilor (%s), fără spații.") % "console.groq.com/keys"
		if serviciu == "cloudflare":
			return _t("Verifică jetonul și ID-ul contului: copiază din nou jetonul (în panoul Cloudflare, pagina "
				"„Workers AI”, „Use REST API”) și ID-ul contului (la „Account ID”), fără spații.")
		return _t("Copiaz-o întreagă din pagina cheii, fără spații, și încearcă din nou.")
	if fel == E_COTA and cod == 402:
		return _t("Contul nu are credit pentru acest model. Cumpără credit sau alege alt model.")
	if fel == E_COTA:
		if serviciu == "gemini":
			return _t("Cheia e bună, dar cota s-a terminat. Traducerea merge din nou după ce se reface cota (la Gemini, "
				"de obicei a doua zi, în jurul orei 10, ora României).")
		if serviciu == "azure":
			return _t("Cheia e bună, dar cota s-a terminat. Traducerea merge din nou după ce se reface cota (la Azure, "
				"luna următoare).")
		return _t("Cheia e bună, dar cota s-a terminat. Traducerea merge din nou după ce se reface cota.")
	if fel in (E_RETEA, E_TERMEN):
		lent = (u" " + _t("Serverul a răspuns prea încet.")) if fel == E_TERMEN else u""
		if local:
			text = (_t("Verifică dacă serverul de la %s e pornit și dacă receptorul îl vede (același router).") %
				(adresa or _t("adresa scrisă"))) + lent
			if serviciu == "openai":
				text += u" " + _t("La Ollama, pe calculator trebuie OLLAMA_HOST=0.0.0.0:11434 (vezi instrucțiunile).")
			return text
		return _t("Verifică internetul receptorului (Meniu › Setări › Rețea) și încearcă din nou.") + lent
	if fel == E_LIMBA:
		if serviciu == "libre":
			return (_t("Pornește serverul LibreTranslate și cu limba „%s” (de exemplu --load-only "
				"en,ro,de,fr,it,es,hu).") % (tinta or "?"))
		return _t("Serviciul nu traduce în limba aleasă. Alege altă limbă în setările traducerii.")
	if fel == E_LIPSA:
		if serviciu == "libre":
			return _t("La adresa asta nu răspunde LibreTranslate. Verifică adresa și portul (de obicei 5000).")
		if serviciu in CU_MODEL_FIX:
			return _t("%s nu dă modelul ales (nu există sau cere planul plătit). Alege alt model din listă; cel din "
				"fabrică e %s.") % (_numeAfisat(serviciu), _modelImplicit(serviciu))
		return _t("Modelul nu e pe server. Alege alt model din listă.")
	if cod == 402:
		return _t("Contul nu are credit pentru acest model. Cumpără credit sau alege alt model.")
	if local:
		return _t("Serverul a răspuns neașteptat. Verifică adresa și portul și încearcă din nou.")
	return _t("Serviciul a răspuns neașteptat. Încearcă din nou peste câteva minute.")


def sfatLent(ms, serviciu, local):
	"""textul pentru o proba lenta (peste PRAG_LENT_MS), sau "" """
	if ms is None or ms <= PRAG_LENT_MS:
		return ""
	text = (_t("Proba a durat %s secunde: serverul e prea lent ca subtitrările traduse să apară la timp; vor veni "
		"târziu, după original.") % (u"%.1f" % (ms / 1000.0)).replace(u".", u","))
	if local and serviciu == "openai":
		return text + u" " + _t("Folosește un serviciu din internet (Gemini, gratuit, fără card) sau un model mai mic "
			"(de exemplu gemma3:4b).")
	if local:
		return text + u" " + _t("Folosește un serviciu din internet (Gemini, gratuit, fără card).")
	return text + u" " + _t("Încearcă un model mai mic sau alt serviciu (Gemini, gratuit, fără card).")


# ------------------------------------------------------------------ configuratorul

class _Lucrare(object):
	"""o configurare pornita: ce s-a cerut si ce trebuie ca sa se salveze (cheia sta numai aici, in RAM)"""

	def __init__(self, nr, fel):
		self.id = nr
		self.fel = fel				# cheie, server, model
		self.cheie = ""				# cheia data acum (se salveaza la reusita)
		self.cheie_veche = ""		# cheia deja salvata a serviciului (numai pentru cereri)
		self.candidati = []
		self.regiune = ""
		self.regiune_data = False	# omul a scris o regiune (si Global): nu se cauta alta
		self.fara_proba = False
		self.tinta = "ro"
		self.adresa = ""
		self.model = ""
		self.serviciu = ""
		self.local = False
		self.cont = ""				# ID-ul contului Cloudflare
		self.ultim = []				# [(cod, inceputul raspunsului)] al ultimei cereri, pentru diagnostic

	def chei(self):
		return (self.cheie, self.cheie_veche)


class Configurator(object):
	def __init__(self, T=None, trimite_=None, cu_trezire=True):
		self.T = _modulT(T)
		self._trimite = trimite_
		self.lacat = threading.Lock()
		self._id = 0
		self._lucreaza = False
		self._rezultate = deque()
		self._stare = self._stareGoala()
		self.trezire = self.T.Trezire(self.proceseaza) if cu_trezire else None

	# ------------------------------------------------------------------ starea
	def _stareGoala(self):
		return {"stare": "nimic", "pas": u"", "pas_fel": u"", "serviciu": u"", "serviciu_nume": u"", "model": u"", "modele": [],
			"adresa": u"", "regiune": u"", "proba": None, "ms": None, "lent": False, "sfat_lent": u"", "incercate": [],
			"mesaj": u"", "ce_faci": u"", "cod_http": None, "cod_intern": None, "salvat": False, "rezerva": False,
			"principal": u"", "principal_nume": u"", "nota_rezerve": u"", "ora": time.strftime("%H:%M:%S"),
			"id": self._id}

	def stare(self):
		with self.lacat:
			s = dict(self._stare)
			s["modele"] = list(s.get("modele") or [])
			s["incercate"] = [dict(i) for i in (s.get("incercate") or [])]
			s["proba"] = dict(s["proba"]) if s.get("proba") else None
		if s["stare"] == "regiune":
			s["regiuni"] = [[c, n] for c, n in regiuniAzure(self.T)]
		else:
			s.pop("regiuni", None)
		return s

	def _pune(self, l, **campuri):
		"""schimba starea lucrarii l (de pe orice fir); textele trec prin _faraCheie"""
		chei = l.chei() if l is not None else ()
		with self.lacat:
			if l is not None and l.id != self._id:
				return
			for k, v in campuri.items():
				if isinstance(v, str):
					v = _faraCheie(v, chei)
				elif k == "modele":
					v = [_faraCheie(x, chei) for x in v][:MAX_MODELE]
				self._stare[k] = v
			self._stare["ora"] = time.strftime("%H:%M:%S")

	def _pas(self, l, text, fel=u""):
		"""pasul de acum: textul (tradus, pentru om) si felul lui ("incarcare" = modelul se incarca pe calculator; pagina
		web il recunoaste dupa fel, nu dupa cuvinte, ca sa mearga in orice limba)"""
		self._pune(l, pas=text, pas_fel=fel)

	# ------------------------------------------------------------------ pornirea
	def _incepe(self, fel):
		"""-> _Lucrare sau None daca merge deja una (sub lacat)"""
		with self.lacat:
			if self._lucreaza:
				return None
			self._lucreaza = True
			self._id += 1
			l = _Lucrare(self._id, fel)
			self._stare = self._stareGoala()
			self._stare.update({"stare": "lucru", "id": self._id})
		return l

	def _tinta(self):
		try:
			return self.T.limbaTinta()
		except Exception:
			return "ro"

	def _cheiSalvate(self):
		try:
			return self.T.chei().citeste()
		except Exception:
			return {}

	def _cheiePoatePleca(self, adresa):
		"""o cheie noua poate pleca spre adresa: https, sau http spre un server din reteaua de acasa"""
		a = (adresa or u"").strip().lower()
		return a.startswith("https://") or (a.startswith("http://") and _inCasa(adresa, self.T))

	def _cheieVeche(self, serviciu, adresa):
		"""cheia deja salvata a serviciului, numai daca e legata de gazda adresei (T.cheiePentru); altfel "" """
		try:
			return self.T.cheiePentru(serviciu, adresa)[0]
		except Exception:
			return u""

	def _pornesteFir(self, l, functie):
		def lucru():
			try:
				rez = functie(l)
			except _Oprire as e:
				rez = self._eroare(l, e)
			except self.T.EroareTraducere as e:
				rez = self._eroare(l, _oprireDin(e))
			except Exception as e:
				_jurnal("lucrare: %s" % e.__class__.__name__)
				rez = self._eroare(l, _Oprire(E_RASPUNS, _t("Configurarea s-a oprit neașteptat.")))
			with self.lacat:
				self._rezultate.append((l, rez))
			if self.trezire is not None:
				self.trezire.trezeste()
		t = threading.Thread(target=lucru, name="HdsConfigurareTraducere")
		t.daemon = True
		t.start()
		if self.trezire is not None:
			self.trezire.cereCeas(True)

	def porneste_cheie(self, cheie, serviciu="auto", regiune="", fara_proba=False, cont=""):
		"""o cheie lipita: serviciul recunoscut (sau cel ales), proba, apoi salvarea. La Cloudflare Workers si ID-ul
		contului (cont; gol = cel din setari). -> (ok, mesaj)"""
		v = curataCheieLipita(cheie)
		if not v:
			return False, _t("Lipește cheia.")
		if not _cheieBuna(v):
			return False, _t("Cheia are caractere care nu pot fi într-o cheie, sau e prea lungă. Copiaz-o din nou, "
				"întreagă.")
		serviciu = (serviciu or "auto").strip().lower()
		recunoscute = recunoasteCheie(v)
		if serviciu == "auto":
			if not recunoscute:
				return False, _t("Nu recunosc cheia după formă. Alege serviciul din listă și încearcă din nou; cheia nu "
					"a plecat nicăieri.")
			candidati = recunoscute
		elif serviciu in SERVICII_CHEIE:
			ales = [c for c in recunoscute if c["serviciu"] == serviciu][:1] or [_cand(serviciu)]
			candidati = ales + [c for c in recunoscute if c["serviciu"] != serviciu]
		else:
			return False, _t("Serviciu necunoscut.")
		reg = _regiuneScrisa(regiune)
		regiune_data = bool(reg)
		if reg == "global":
			reg = ""
		if reg and not re.match(r"^[a-z0-9]{2,40}$", reg):
			return False, _t("Regiunea nu e bună: scrie-o exact ca în portalul Azure, de exemplu westeurope.")
		cheile = self._cheiSalvate()
		tinta = self._tinta()
		adrese = {}
		modele = {}
		cont_salvat = u""
		try:
			s = self.T.initConfig()
			adrese = {"libre": (s.adresa_libre.value or "").strip(), "openai": (s.adresa_openai.value or "").strip()}
			modele = dict((c, (_setare(s, "model_" + c) or u"").strip()) for c in CU_MODEL_FIX)
			cont_salvat = (_setare(s, "cont_cloudflare") or u"").strip().lower()
		except Exception:
			pass
		cont = (cont or u"").strip().lower()
		if any(c["serviciu"] == "cloudflare" for c in candidati):
			if cont and not _CONT.match(cont):
				return False, _t("ID-ul contului Cloudflare are 32 de litere și cifre (de la „Account ID”). Cheia nu a "
					"plecat nicăieri.")
			cont = cont or (cont_salvat if _CONT.match(cont_salvat) else u"")
			if not cont:
				return False, _t("Pentru Cloudflare Workers scrie și ID-ul contului (32 de litere și cifre, de la "
					"„Account ID”). Cheia nu a plecat nicăieri.")
		for c in candidati:
			if c["serviciu"] in ("libre", "openai") and not c["adresa"]:
				c["adresa"] = adrese.get(c["serviciu"], "")
		candidati = [c for c in candidati if c["serviciu"] not in ("libre", "openai") or c["adresa"]]
		if not candidati:
			return False, _t("Pentru un server din casă scrie întâi adresa lui (pasul cu adresa serverului).")
		candidati = [c for c in candidati
			if c["serviciu"] not in ("libre", "openai") or self._cheiePoatePleca(c["adresa"])]
		if not candidati:
			return False, _t("O cheie pleacă numai pe https:// sau spre un server din rețeaua de acasă. Scrie adresa cu "
				"https://. Cheia nu a plecat nicăieri.")
		l = self._incepe("cheie")
		if l is None:
			return False, _t("Merge deja o configurare. Așteaptă să se termine.")
		l.cheie = v
		l.cheie_veche = cheile.get(candidati[0]["serviciu"], "")
		l.candidati = candidati
		l.regiune = reg
		l.regiune_data = regiune_data
		l.fara_proba = bool(fara_proba)
		l.tinta = tinta
		l.cont = cont
		l.model = modele.get(candidati[0]["serviciu"], u"")
		self._pune(l, pas=_t("Recunosc cheia..."), serviciu=candidati[0]["serviciu"], serviciu_nume=candidati[0]["nume"],
			regiune=reg)
		self._pornesteFir(l, self._lucruCheie)
		return True, _t("Am pornit verificarea cheii.")

	def porneste_server(self, serviciu, adresa, model="", cheie=""):
		"""un server LibreTranslate sau compatibil OpenAI (de ex. Ollama): modelele, proba, salvarea. -> (ok, mesaj)"""
		serviciu = (serviciu or "").strip().lower()
		if serviciu not in ("libre", "openai"):
			return False, _t("Serverul poate fi numai LibreTranslate sau compatibil OpenAI.")
		a, eroare = normalizeazaAdresa(serviciu, adresa)
		if eroare:
			return False, eroare
		model = (model or "").strip()
		if model and (len(model) > 200 or any(c.isspace() or ord(c) < 33 for c in model)):
			return False, _t("Numele modelului nu e bun.")
		v = curataCheieLipita(cheie) if cheie else ""
		if cheie and not _cheieBuna(v):
			return False, _t("Cheia are caractere care nu pot fi într-o cheie, sau e prea lungă.")
		if v and not self._cheiePoatePleca(a):
			return False, _t("O cheie pleacă numai pe https:// sau spre un server din rețeaua de acasă. Scrie adresa cu "
				"https://. Cheia nu a plecat nicăieri.")
		veche = self._cheieVeche(serviciu, a)
		tinta = self._tinta()
		l = self._incepe("server")
		if l is None:
			return False, _t("Merge deja o configurare. Așteaptă să se termine.")
		l.serviciu = serviciu
		l.adresa = a
		l.model = model
		l.cheie = v
		l.cheie_veche = veche
		l.tinta = tinta
		l.local = _inCasa(a, self.T)
		self._pune(l, pas=_t("Mă uit la server..."), serviciu=serviciu, serviciu_nume=_numeAfisat(serviciu), adresa=a,
			model=model)
		self._pornesteFir(l, self._lucruServer)
		return True, _t("Am pornit verificarea serverului.")

	def porneste_model(self, model):
		"""alt model pentru serviciul ales acum (Gemini sau compatibil OpenAI): proba, apoi salvarea. -> (ok, mesaj)"""
		model = _numeGemini(model or "")
		if not model or len(model) > 200 or any(c.isspace() or ord(c) < 33 for c in model):
			return False, _t("Alege un model din listă.")
		try:
			cfg = self.T.configuratia()
		except Exception:
			return False, _t("Setările traducerii nu se pot citi.")
		serv = cfg.get("serviciu")
		if serv not in ("gemini", "openai") + CU_MODEL_FIX:
			return False, _t("Modelul se schimbă numai la Gemini, Groq, Cloudflare Workers și la serverele compatibile "
				"OpenAI.")
		if serv == "gemini" and not cfg.get("cheie"):
			return False, _t("Pentru Gemini lipsește cheia. Pune întâi cheia.")
		if serv == "openai" and not cfg.get("adresa"):
			return False, _t("Pentru serverul compatibil OpenAI lipsește adresa. Pune întâi adresa.")
		if serv in CU_MODEL_FIX:
			lipsa = [c for c in self.T.ceLipseste(dict(cfg, model=model)) if c != "model"]
			if lipsa:
				return False, self.T.textCeLipseste(dict(cfg, model=model))
		with self.lacat:
			vechi = dict(self._stare)
		l = self._incepe("model")
		if l is None:
			return False, _t("Merge deja o configurare. Așteaptă să se termine.")
		l.serviciu = serv
		l.cheie_veche = cfg.get("cheie") or ""
		l.adresa = cfg.get("adresa") or ""
		l.model = model
		l.cont = cfg.get("cont") or u""
		l.tinta = cfg.get("tinta") or self._tinta()
		l.local = serv == "openai" and _inCasa(l.adresa, self.T)
		modele = vechi.get("modele") if vechi.get("serviciu") == serv else []
		if not modele and serv in CU_MODEL_FIX:
			modele = _modeleFixe(serv, self.T)
		self._pune(l, pas=_t("Probez modelul %s...") % model, serviciu=serv,
			serviciu_nume=vechi.get("serviciu_nume") if vechi.get("serviciu") == serv and vechi.get("serviciu_nume")
			else _numeAfisat(serv), adresa=l.adresa if serv == "openai" else u"", model=model, modele=list(modele or []))
		self._pornesteFir(l, self._lucruModel)
		return True, _t("Am pornit proba modelului.")

	# ------------------------------------------------------------------ cererile (pe firul lucrarii)
	def _trimitator(self, l):
		baza = self._trimite or self.T.trimite

		def trimite(adresa, antete, corp, termen_s):
			cod, date = baza(adresa, antete, corp, termen_s)
			l.ultim[:] = [(cod, (date or b"")[:8192])]
			return cod, date
		return trimite

	def _antete(self, alte=None):
		a = {"Accept": "application/json", "User-Agent": AGENT}
		a.update(alte or {})
		return a

	def _json(self, date):
		try:
			return json.loads(date.decode("utf-8"))
		except (ValueError, UnicodeDecodeError, AttributeError):
			return None

	def _eroareHttp(self, serv, cod, date):
		fel = self.T.felEroareHttp(serv, cod, date)
		return self.T.EroareTraducere(fel, self.T.textEroare(fel, serv, cod), cod)

	def _modeleGemini(self, l, cheie):
		trimite = self._trimitator(l)
		antete = self._antete({"x-goog-api-key": cheie})
		nume = []
		token = ""
		marime = PAGINA_GEMINI
		pagini = 0
		while pagini < MAX_PAGINI_GEMINI:
			pagini += 1
			adresa = GEMINI_MODELE + "?pageSize=%d" % marime + (("&pageToken=" + quote(token, safe="")) if token else "")
			try:
				cod, date = trimite(adresa, antete, None, TERMEN_LISTA_S)
			except self.T.EroareTraducere as e:
				if e.fel == E_RASPUNS and marime > PAGINA_GEMINI_MICA and not nume and not token:
					marime = PAGINA_GEMINI_MICA		# raspunsul a fost prea mare: pagini mai mici
					continue
				raise
			_jurnal("gemini: lista modelelor HTTP %s" % cod)
			if cod != 200:
				raise self._eroareHttp("gemini", cod, date)
			j = self._json(date)
			if not isinstance(j, dict):
				raise self.T.EroareTraducere(E_RASPUNS, self.T.textEroare(E_RASPUNS, "gemini", cod), cod)
			for m in j.get("models") or []:
				if isinstance(m, dict) and "generateContent" in (m.get("supportedGenerationMethods") or []):
					n = _numeGemini(m.get("name"))
					if n and n not in nume:
						nume.append(n)
			token = j.get("nextPageToken") or ""
			if not token:
				break
		return nume

	def _modeleOpenAI(self, l, adresa, cheie, local):
		"""-> (fel, lista bruta, nume): fel "ollama" (din /api/tags) sau "openai" (din /models)"""
		trimite = self._trimitator(l)
		antete = self._antete({"Authorization": "Bearer " + cheie} if cheie else None)
		a = adresa.rstrip("/")
		if a.endswith("/v1"):
			incercari = [("openai", a + "/models")]
			if local:
				incercari.append(("ollama", a[:-3] + "/api/tags"))
		elif local:
			incercari = [("ollama", a + "/api/tags"), ("openai", a + "/v1/models")]
		else:
			incercari = [("openai", a + "/v1/models"), ("ollama", a + "/api/tags")]
		ultim_cod = None
		for fel, url in incercari:
			cod, date = trimite(url, antete, None, TERMEN_LISTA_S)
			_jurnal("openai: lista modelelor (%s) HTTP %s" % (fel, cod))
			if cod == 200:
				j = self._json(date)
				if fel == "ollama" and isinstance(j, dict) and isinstance(j.get("models"), list):
					bruta = [m for m in j["models"] if isinstance(m, dict) and (m.get("name") or m.get("model"))]
					return "ollama", bruta, [u"%s" % (m.get("name") or m.get("model")) for m in bruta]
				if fel == "openai" and isinstance(j, dict) and isinstance(j.get("data"), list):
					ids = [u"%s" % m.get("id") for m in j["data"] if isinstance(m, dict) and m.get("id")]
					return "openai", ids, ids
			elif cod in (401, 403, 407):
				raise self._eroareHttp("openai", cod, date)
			elif cod == 429:
				raise self._eroareHttp("openai", cod, date)
			ultim_cod = cod
		raise _Oprire(E_LIPSA, (_t("Serverul nu dă lista modelelor (HTTP %s).") % ultim_cod) if ultim_cod else
			_t("Serverul nu dă lista modelelor."), _t("Verifică adresa, sau scrie numele modelului."), ultim_cod)

	def _limbiLibre(self, l, adresa, cheie):
		trimite = self._trimitator(l)
		cod, date = trimite(adresa.rstrip("/") + "/languages", self._antete(), None, TERMEN_LISTA_S)
		_jurnal("libre: limbile HTTP %s" % cod)
		if cod in (401, 403):
			raise self._eroareHttp("libre", cod, date)
		j = self._json(date) if cod == 200 else None
		if not isinstance(j, list) or not all(isinstance(x, dict) and "code" in x for x in j):
			raise _Oprire(E_LIPSA, (_t("La adresa asta nu răspunde un server LibreTranslate (HTTP %s).") % cod)
				if cod != 200 else _t("La adresa asta nu răspunde un server LibreTranslate."),
				ceFaci(E_LIPSA, "libre", local=l.local, adresa=adresa), cod)
		return j

	def _proba(self, l, cfg, nume, termen):
		"""o traducere de proba -> {"original", "traducere", "ms"}; cota terminata -> None (cheia e buna)"""
		T = self.T
		texte, sursa = T.frazaProba(l.tinta)
		inceput = time.monotonic()
		try:
			rez = T.traduceAcum(cfg, list(texte), sursa, l.tinta, (), termen, self._trimitator(l))
		except T.EroareTraducere as e:
			_jurnal("%s: proba eroare %s%s" % (cfg["serviciu"], e.fel, (" (HTTP %s)" % e.cod) if e.cod else ""))
			if e.fel == E_COTA:
				return None
			raise
		ms = int((time.monotonic() - inceput) * 1000)
		_jurnal("%s: proba reusita (%d ms)" % (cfg["serviciu"], ms))
		return {"original": u" ".join(texte), "traducere": u" ".join(rez), "ms": ms}

	def _probaCasa(self, l, cfg, eticheta):
		"""proba la un server din casa: termen depasit la prima cerere = modelul se incarca, o reincercare lunga; o
		proba lenta se mai face o data (prima poate cuprinde incarcarea modelului) si ramane timpul mai bun"""
		self._pas(l, _t("Probez traducerea cu %s...") % eticheta)
		try:
			p = self._proba(l, cfg, eticheta, TERMEN_PROBA_CASA_S)
		except self.T.EroareTraducere as e:
			if e.fel != E_TERMEN:
				raise
			self._pas(l, _t("Se încarcă modelul pe calculator... (%s, până la un minut)") % eticheta, u"incarcare")
			p = self._proba(l, cfg, eticheta, TERMEN_INCARCARE_S)
		if p is not None and p["ms"] > PRAG_LENT_MS:
			self._pas(l, _t("Măsor viteza cu %s...") % eticheta)
			try:
				a_doua = self._proba(l, cfg, eticheta, TERMEN_INCARCARE_S)
				if a_doua is not None and a_doua["ms"] < p["ms"]:
					p = a_doua
			except self.T.EroareTraducere:
				pass
		return p

	def _cfg(self, serviciu, cheie="", adresa="", model="", regiune="", tinta="ro", cont=""):
		c = {"serviciu": serviciu, "cheie": cheie or "", "regiune": regiune or "", "adresa": adresa or "",
			"model": model or "", "tinta": tinta}
		if serviciu == "cloudflare":
			c["cont"] = cont or ""
		return c

	def _reusita(self, l, serviciu, nume, model=u"", modele=(), adresa=u"", regiune=u"", proba=None, cota=False,
			incercate=(), afisat=None, regiune_gasita=None, cont=u""):
		return {"stare": "ok", "serviciu": serviciu, "serviciu_nume": nume, "model": model or u"",
			"modele": list(modele or []), "adresa": adresa or u"", "regiune": regiune or u"", "proba": proba,
			"cota": cota, "incercate": list(incercate or []), "afisat": afisat or nume, "regiune_gasita": regiune_gasita,
			"cont": cont or u""}

	def _eroare(self, l, e, serviciu=None, nume=u""):
		serv = serviciu or l.serviciu or (l.candidati[0]["serviciu"] if l.candidati else "")
		corp = l.ultim[0][1] if l.ultim else b""
		ce = e.ce_faci or ceFaci(e.fel, serv, nume, l.local, l.adresa, corp, e.cod, l.tinta)
		return {"stare": "eroare", "fel": e.fel, "mesaj": e.text, "ce_faci": ce, "cod": e.cod,
			"cod_intern": getattr(e, "cod_intern", None) or (codIntern(corp, e.cod) if e.cod else None)}

	# ------------------------------------------------------------------ lucrarile
	def _lucruCheie(self, l):
		T = self.T
		refuzuri = []
		cere_regiune = None
		for cand in l.candidati:
			serv, nume = cand["serviciu"], cand["nume"]
			l.ultim[:] = []
			self._pune(l, serviciu=serv, serviciu_nume=nume, adresa=cand["adresa"] if serv in ("libre", "openai") else u"",
				model=u"", modele=[])
			try:
				return self._incearcaCheie(l, cand)
			except (T.EroareTraducere, _Oprire) as e:
				oprire = e if isinstance(e, _Oprire) else _oprireDin(e)
				_jurnal("%s: %s%s" % (serv, oprire.fel, (" (HTTP %s)" % oprire.cod) if oprire.cod else ""))
				corp = l.ultim[0][1] if l.ultim else b""
				local = serv in ("libre", "openai") and _inCasa(cand["adresa"], T)
				if oprire.fel in (E_RETEA, E_TERMEN, E_ADRESA):
					l.local = local
					l.adresa = cand["adresa"]
					return self._eroare(l, oprire, serv, nume)
				if serv == "azure" and oprire.regiune_lipsa:
					cere_regiune = oprire
				if oprire.cod_intern is None and oprire.cod:
					oprire.cod_intern = codIntern(corp, oprire.cod)
				ce = oprire.ce_faci or ceFaci(oprire.fel, serv, nume, local, cand["adresa"], corp, oprire.cod, l.tinta)
				refuzuri.append((cand, oprire, ce, _serviciuOprit(corp)))
		if cere_regiune is not None:
			return {"stare": "regiune", "serviciu": "azure", "serviciu_nume": NUME["azure"], "fel": E_CHEIE,
				"mesaj": cere_regiune.text, "ce_faci": cere_regiune.ce_faci, "cod": cere_regiune.cod,
				"cod_intern": cere_regiune.cod_intern}
		# cel mai lamuritor refuz: API-ul Google oprit (cheia e buna), altfel primul candidat
		alese = [r for r in refuzuri if r[3]] or refuzuri
		cand, oprire, ce, _o = alese[0]
		if len(refuzuri) > 1 and not alese[0][3]:
			nume = refuzuri[0][0]["nume"]
			for r in refuzuri[1:]:
				nume = _t("%s și %s") % (nume, r[0]["nume"])		# = " și ".join(...), cu msgid-ul din po
			mesaj = _t("Cheia nu a mers la %s.") % nume
			ce = u" ".join([ce] + [_t("Dacă e cheie pentru %s: %s") % (r[0]["nume"], r[2]) for r in refuzuri[1:]
				if r[2] != ce])
		else:
			mesaj = oprire.text
		return {"stare": "eroare", "fel": oprire.fel, "mesaj": mesaj, "ce_faci": ce, "cod": oprire.cod,
			"cod_intern": oprire.cod_intern, "serviciu": cand["serviciu"], "serviciu_nume": cand["nume"]}

	def _incearcaCheie(self, l, cand):
		T = self.T
		serv, nume, cheie = cand["serviciu"], cand["nume"], l.cheie
		if serv == "gemini":
			self._pas(l, _t("Citesc modelele %s...") % "Gemini")
			try:
				modele = self._modeleGemini(l, cheie)
			except T.EroareTraducere as e:
				if e.fel == E_COTA:
					model = _modelGeminiImplicit()
					return self._reusita(l, serv, nume, model=model, cota=True, afisat=u"%s (%s)" % (nume, model))
				if e.fel != E_RASPUNS:
					raise
				modele = []
			model = alegeModel("gemini", modele) or _modelGeminiImplicit()
			self._pune(l, model=model, modele=modele)
			if l.fara_proba:
				return self._reusita(l, serv, nume, model=model, modele=modele, afisat=u"%s (%s)" % (nume, model))
			self._pas(l, _t("Probez traducerea cu %s...") % "Gemini")
			p = self._proba(l, self._cfg(serv, cheie, model=model, tinta=l.tinta), nume, TERMEN_PROBA_S)
			return self._reusita(l, serv, nume, model=model, modele=modele, proba=p, cota=p is None,
				afisat=u"%s (%s)" % (nume, model))
		if serv == "openai":
			baza = cand["adresa"]
			local = _inCasa(baza, T)
			self._pas(l, _t("Citesc modelele %s...") % nume)
			fel, bruta, modele = self._modeleOpenAI(l, baza, cheie, local)
			model = alegeModel(fel, bruta)
			if not model:
				raise _Oprire(E_LIPSA, _t("%s nu are niciun model potrivit pentru traducere.") % nume,
					_t("Alege un model din listă."))
			self._pune(l, model=model, modele=modele)
			if l.fara_proba:
				return self._reusita(l, serv, nume, model=model, modele=modele, adresa=baza,
					afisat=u"%s (%s)" % (nume, model))
			self._pas(l, _t("Probez traducerea cu %s (%s)...") % (nume, model))
			cfg = self._cfg(serv, cheie, adresa=baza, model=model, tinta=l.tinta)
			p = self._probaCasa(l, cfg, model) if local else self._proba(l, cfg, nume, TERMEN_PROBA_S)
			return self._reusita(l, serv, nume, model=model, modele=modele, adresa=baza, proba=p, cota=p is None,
				afisat=u"%s (%s)" % (nume, model))
		if serv == "libre":
			l.local = _inCasa(cand["adresa"], T)
			l.adresa = cand["adresa"]
			return self._libre(l, cand["adresa"], cheie)
		if serv == "azure":
			return self._azure(l, cand)
		if serv in CU_MODEL_FIX:
			return self._modelFix(l, cand)
		# google, deepl: numai traducerea de proba arata daca cheia e buna
		if l.fara_proba:
			return self._reusita(l, serv, nume, regiune=l.regiune if serv == "azure" else u"")
		self._pas(l, _t("Probez traducerea cu %s...") % nume)
		cfg = self._cfg(serv, cheie, regiune=l.regiune if serv == "azure" else "", tinta=l.tinta)
		p = self._proba(l, cfg, nume, TERMEN_PROBA_S)
		return self._reusita(l, serv, nume, regiune=l.regiune if serv == "azure" else u"", proba=p, cota=p is None)

	def _modeleGroq(self, l, cheie):
		"""lista modelelor Groq (GET /models, cu cheia; nu consuma din cota) -> id-urile"""
		trimite = self._trimitator(l)
		cod, date = trimite(BAZA_GROQ + "/models", self._antete({"Authorization": "Bearer " + cheie}), None,
			TERMEN_LISTA_S)
		_jurnal("groq: lista modelelor HTTP %s" % cod)
		if cod != 200:
			raise self._eroareHttp("groq", cod, date)
		j = self._json(date)
		if not isinstance(j, dict) or not isinstance(j.get("data"), list):
			raise self.T.EroareTraducere(E_RASPUNS, self.T.textEroare(E_RASPUNS, "groq", cod), cod)
		return [u"%s" % m.get("id") for m in j["data"] if isinstance(m, dict) and m.get("id")]

	def _modelFix(self, l, cand):
		"""Groq si Cloudflare Workers: modelul din setari (sau primul propus); la Groq intai lista modelelor (cheia se
		verifica fara cota, iar un model scos din lista se inlocuieste cu primul propus care e acolo), apoi proba"""
		T = self.T
		serv, nume, cheie = cand["serviciu"], cand["nume"], l.cheie
		propuse = _modeleFixe(serv, T)
		model = l.model or (propuse[0] if propuse else u"")
		modele = list(propuse)
		if serv == "groq":
			self._pas(l, _t("Citesc modelele %s...") % nume)
			try:
				lista = self._modeleGroq(l, cheie)
			except T.EroareTraducere as e:
				if e.fel == E_COTA:
					return self._reusita(l, serv, nume, model=model, modele=modele, cota=True,
						afisat=u"%s (%s)" % (nume, model))
				if e.fel not in (E_RASPUNS, E_LIPSA):
					raise
				lista = []
			if lista:
				bune = [m for m in propuse if m in lista]
				altele = [m for m in lista if m not in bune and not any(r in m.lower() for r in _NU_OPENAI)]
				modele = bune + altele
				if model not in lista:
					model = bune[0] if bune else (alegeModel("openai", lista) or model)
		if model and model not in modele:
			modele.insert(0, model)
		self._pune(l, model=model, modele=modele)
		if l.fara_proba:
			return self._reusita(l, serv, nume, model=model, modele=modele, cont=l.cont,
				afisat=u"%s (%s)" % (nume, model))
		self._pas(l, _t("Probez traducerea cu %s (%s)...") % (nume, model))
		cfg = self._cfg(serv, cheie, model=model, tinta=l.tinta, cont=l.cont)
		p = self._proba(l, cfg, nume, TERMEN_PROBA_S)
		return self._reusita(l, serv, nume, model=model, modele=modele, proba=p, cota=p is None, cont=l.cont,
			afisat=u"%s (%s)" % (nume, model))

	def _azure(self, l, cand):
		"""Azure: intai regiunea scrisa de om (sau Global); fara regiune si refuzat, regiunile uzuale pe rand, cate o
		cerere scurta; prima care merge se salveaza"""
		T = self.T
		serv, nume, cheie = "azure", cand["nume"], l.cheie
		if l.fara_proba:
			return self._reusita(l, serv, nume, regiune=l.regiune)
		self._pas(l, _t("Probez traducerea cu %s...") % nume)
		try:
			p = self._proba(l, self._cfg(serv, cheie, regiune=l.regiune, tinta=l.tinta), nume, TERMEN_PROBA_S)
			return self._reusita(l, serv, nume, regiune=l.regiune, proba=p, cota=p is None)
		except T.EroareTraducere as e:
			if e.fel != E_CHEIE:
				raise
			prima_cod, prima_intern = e.cod, codIntern(l.ultim[0][1] if l.ultim else b"", e.cod)
		if l.regiune_data:
			raise _Oprire(E_CHEIE, _t(MESAJ_REGIUNE_GRESITA),
				_t("Copiază din nou KEY 1 de la „Keys and Endpoint”, întreagă, și alege regiunea scrisă acolo la "
				"„Location/Region” (sau Global, dacă resursa e globală)."), prima_cod, prima_intern)
		texte, sursa = T.frazaProba(l.tinta)
		texte = list(texte)[:1]
		incercate = refuzate = 0
		for cod, nume_reg in regiuniAzure(T):
			if not cod:
				continue
			incercate += 1
			self._pas(l, _t("Caut regiunea resursei Azure: %s (%s)...") % (nume_reg, cod))
			cfg = self._cfg(serv, cheie, regiune=cod, tinta=l.tinta)
			inceput = time.monotonic()
			try:
				rez = T.traduceAcum(cfg, texte, sursa, l.tinta, (), TERMEN_REGIUNE_S, self._trimitator(l))
			except T.EroareTraducere as e:
				_jurnal("azure: regiunea %s: %s%s" % (cod, e.fel, (" (HTTP %s)" % e.cod) if e.cod else ""))
				if e.fel == E_COTA:			# cheia si regiunea sunt bune, cota s-a terminat
					return self._reusita(l, serv, nume, regiune=cod, cota=True, regiune_gasita=(cod, nume_reg))
				if e.fel == E_CHEIE:
					refuzate += 1
				if e.fel in (E_CHEIE, E_RASPUNS, E_LIPSA):
					continue
				raise
			ms = int((time.monotonic() - inceput) * 1000)
			_jurnal("azure: regiunea gasita %s (%d ms)" % (cod, ms))
			p = {"original": u" ".join(texte), "traducere": u" ".join(rez), "ms": ms}
			return self._reusita(l, serv, nume, regiune=cod, proba=p, regiune_gasita=(cod, nume_reg))
		if incercate and refuzate == incercate and hasattr(T, "textAzureRefuzaPeste"):
			# fara regiune (Global) si cu fiecare regiune din lista: tot cheie refuzata, deci cheia sau resursa
			# (abonamentul) nu mai sunt bune, ori resursa e intr-o regiune din afara listei; omul poate alege regiunea
			_jurnal("azure: cheia refuzata in toate cele %d regiuni" % (incercate + 1))
			raise _Oprire(E_CHEIE, T.textAzureRefuzaPeste(), T.textCeFaciRefuz("azure"), prima_cod, prima_intern,
				regiune_lipsa=True)
		raise _Oprire(E_CHEIE, _t(MESAJ_REGIUNE_LIPSA),
			_t("Alege regiunea resursei din listă și pornește din nou. Dacă nici cu regiunea bună nu merge, cheia e "
			"greșită: copiaz-o din nou, întreagă (KEY 1, la „Keys and Endpoint”)."), prima_cod, prima_intern,
			regiune_lipsa=True)

	def _libre(self, l, adresa, cheie):
		T = self.T
		self._pas(l, _t("Mă uit la serverul LibreTranslate..."))
		limbi = self._limbiLibre(l, adresa, cheie)
		cod_tinta = getattr(T, "_COD_LIBRE", {}).get(l.tinta, l.tinta)
		if not any(cod_tinta in (x.get("targets") or []) for x in limbi):
			raise _Oprire(E_LIMBA, _t("Serverul LibreTranslate nu are limba „%s”.") % cod_tinta,
				ceFaci(E_LIMBA, "libre", tinta=cod_tinta))
		if l.fara_proba:
			return self._reusita(l, "libre", NUME["libre"], adresa=adresa)
		cfg = self._cfg("libre", cheie, adresa=adresa, tinta=l.tinta)
		p = self._probaCasa(l, cfg, NUME["libre"]) if l.local else self._proba(l, cfg, NUME["libre"], TERMEN_PROBA_S)
		return self._reusita(l, "libre", NUME["libre"], adresa=adresa, proba=p, cota=p is None)

	def _lucruServer(self, l):
		cheie = l.cheie or l.cheie_veche
		if l.serviciu == "libre":
			return self._libre(l, l.adresa, cheie)
		self._pas(l, _t("Citesc modelele de pe server..."))
		try:
			fel, bruta, modele = self._modeleOpenAI(l, l.adresa, cheie, l.local)
		except _Oprire as e:
			if e.fel == E_LIPSA and l.model:
				fel, bruta, modele = "openai", [], []
			else:
				raise
		nume = u"Ollama" if fel == "ollama" else _numeAfisat("openai")
		self._pune(l, serviciu_nume=nume, modele=modele)
		if l.model:
			if modele and l.model not in modele:
				raise _Oprire(E_LIPSA, _t("Modelul „%s” nu e pe server.") % l.model, _t("Alege un model din listă."))
			ordine = [l.model]
		elif fel == "ollama":
			# se probeaza numai familiile care traduc bine (un model rapid dar slab la romana nu castiga); altfel
			# cele mai bune dupa scor
			ordine = (ordineOllama(bruta, numai_potrivite=True) or ordineOllama(bruta))[:MAX_PROBE_MODELE]
		else:
			m = alegeModel("openai", bruta)
			ordine = [m] if m else []
		if not ordine:
			raise _Oprire(E_LIPSA, _t("Serverul nu are niciun model potrivit pentru traducere."),
				_t("Pe calculator descarcă un model, de exemplu: ollama pull gemma3:4b.") if fel == "ollama" else
				_t("Încarcă un model pe server și încearcă din nou."))
		if l.fara_proba:
			return self._reusita(l, "openai", nume, model=ordine[0], modele=modele, adresa=l.adresa,
				afisat=u"%s (%s)" % (nume, ordine[0]))
		incercate = []
		bune = []
		ultima = None
		for i, model in enumerate(ordine):
			self._pune(l, model=model, incercate=list(incercate))
			cfg = self._cfg("openai", cheie, adresa=l.adresa, model=model, tinta=l.tinta)
			eticheta = model if len(ordine) == 1 else _t("%s, %d din %d") % (model, i + 1, len(ordine))
			try:
				p = self._probaCasa(l, cfg, eticheta) if l.local else self._proba(l, cfg, model, TERMEN_PROBA_S)
			except self.T.EroareTraducere as e:
				ultima = _oprireDin(e)
				incercate.append({"model": model, "ms": None, "ok": False})
				if e.fel in (E_CHEIE, E_RETEA, E_ADRESA):
					break
				continue
			if p is None:			# cota terminata (server din internet)
				return self._reusita(l, "openai", nume, model=model, modele=modele, adresa=l.adresa, cota=True,
					incercate=incercate, afisat=u"%s (%s)" % (nume, model))
			buna = bool(p["traducere"].strip()) and p["traducere"].strip() != p["original"].strip()
			incercate.append({"model": model, "ms": p["ms"], "ok": buna})
			if buna:
				bune.append((p["ms"], i, model, p))
		self._pune(l, incercate=list(incercate))
		if not bune:
			if ultima is None:
				ultima = _Oprire(E_RASPUNS, _t("Modelele probate nu au dat o traducere."),
					_t("Alege alt model din listă, sau un serviciu din internet."))
			raise ultima
		# cel mai rapid care a tradus; la timpi apropiati (sub 15%) ramane cel cu scorul mai bun
		bune.sort()
		ales = bune[0]
		for b in bune[1:]:
			if b[1] < ales[1] and b[0] <= ales[0] * 1.15:
				ales = b
		ms, _i, model, p = ales
		return self._reusita(l, "openai", nume, model=model, modele=modele, adresa=l.adresa, proba=p,
			incercate=incercate, afisat=u"%s (%s)" % (nume, model))

	def _lucruModel(self, l):
		cfg = self._cfg(l.serviciu, l.cheie_veche, adresa=l.adresa, model=l.model, tinta=l.tinta, cont=l.cont)
		nume = NUME[l.serviciu] if l.serviciu in ("gemini",) + CU_MODEL_FIX else (self._stare.get("serviciu_nume") or
			_numeAfisat("openai"))
		if l.local:
			p = self._probaCasa(l, cfg, l.model)
		else:
			self._pas(l, _t("Probez traducerea cu %s...") % l.model)
			p = self._proba(l, cfg, l.model, TERMEN_PROBA_S)
		return self._reusita(l, l.serviciu, nume, model=l.model, adresa=l.adresa if l.serviciu == "openai" else u"",
			proba=p, cota=p is None, afisat=u"%s (%s)" % (nume, l.model))

	# ------------------------------------------------------------------ rezultatele (firul enigma2)
	def asteapta(self, termen_s=10.0):
		"""probele: pana se termina lucrarea, apoi proceseaza()"""
		sfarsit = time.monotonic() + termen_s
		while time.monotonic() < sfarsit:
			with self.lacat:
				gata = bool(self._rezultate) or not self._lucreaza
			if gata:
				break
			time.sleep(0.01)
		self.proceseaza()

	def proceseaza(self):
		while True:
			with self.lacat:
				if not self._rezultate:
					break
				l, rez = self._rezultate.popleft()
			try:
				self._aplica(l, rez)
			except Exception as e:
				_jurnal("aplicarea: %s" % e.__class__.__name__)
				self._pune(l, stare="eroare", pas=u"", salvat=False, mesaj=_t("Setările nu s-au putut salva."),
					ce_faci=_t("Încearcă din nou."))
			finally:
				l.cheie = l.cheie_veche = ""
				with self.lacat:
					self._lucreaza = False
		with self.lacat:
			liber = not self._lucreaza and not self._rezultate
		if liber and self.trezire is not None:
			self.trezire.cereCeas(False)

	def _principalRamane(self, l, serv):
		"""o cheie lipita (l.fel "cheie") pentru alt serviciu decat cel principal: codul principalului cand ramane (vezi
		PRINCIPALUL, sus), altfel "" (serviciul cheii devine principal). Pe firul enigma2, inainte de orice scriere."""
		if l.fel != "cheie":
			return u""
		T = self.T
		try:
			s = T.initConfig()
			principal = s.serviciu.value
			if not s.pornit.value or not principal or principal == serv:
				return u""
			cfg = T.configuratia(s)
			if T.ceLipseste(cfg):
				return u""
			inst = T.instanta()
			p = inst.ultima_proba or {}
			if p.get("stare") == "eroare" and p.get("fel") in (E_CHEIE, E_COTA) and \
					p.get("serviciu") == T.numeServiciu(principal):
				return u""
			for x in inst.stareLant([cfg]):
				if x.get("stare") in ("setari", "refuzat") or (x.get("stare") == "asteapta" and x.get("pe_zi")):
					return u""
		except Exception as e:
			_jurnal("principalul: %s" % e.__class__.__name__)
			return u""
		return principal

	def _fostulPrincipal(self, s, serv):
		"""serviciul principal de acum, cand `serv` ii ia locul si el are campurile complete (cheia, adresa, modelul):
		intra primul in rezerve (FOSTUL PRINCIPAL, sus), ca sa nu iasa din lant; altfel "" """
		T = self.T
		try:
			vechi = s.serviciu.value
			if not vechi or vechi == serv or T.ceLipseste(T.configuratia(s)):
				return u""
		except Exception as e:
			_jurnal("fostul principal: %s" % e.__class__.__name__)
			return u""
		return vechi

	def _aplica(self, l, rez):
		if rez.get("stare") != "ok":
			campuri = {"stare": rez.get("stare", "eroare"), "pas": u"", "salvat": False,
				"mesaj": rez.get("mesaj") or u"", "ce_faci": rez.get("ce_faci") or u"",
				"cod_http": rez.get("cod"), "cod_intern": rez.get("cod_intern")}
			for k in ("serviciu", "serviciu_nume"):
				if rez.get(k):
					campuri[k] = rez[k]
			self._pune(l, **campuri)
			_jurnal("configurare: %s%s" % (campuri["stare"], (" (%s)" % rez["fel"]) if rez.get("fel") else ""))
			return
		T = self.T
		serv = rez["serviciu"]
		principal = self._principalRamane(l, serv)
		if l.cheie:
			if serv in ("libre", "openai"):
				# cheia legata de adresa probata (cea care se salveaza mai jos), nu de cea veche din setari
				ok, mesaj = T.chei().schimba(serv, l.cheie, adresa=rez.get("adresa") or u"")
			else:
				ok, mesaj = T.chei().schimba(serv, l.cheie)
			if not ok:
				self._pune(l, stare="eroare", pas=u"", salvat=False, mesaj=mesaj,
					ce_faci=_t("Încearcă din nou; dacă se repetă, repornește receptorul."))
				_jurnal("configurare: cheia nu s-a salvat")
				return
		s = T.initConfig()
		fostul = u""
		if principal:
			lista = T.rezerve(s)
			if serv not in lista and not T.puneRezerve([serv] + lista, s)[0]:
				_jurnal("configurare: rezervele nu s-au schimbat")
		else:
			fostul = self._fostulPrincipal(s, serv)
			lista = T.rezerve(s)		# inainte de schimbare: rezerve() scoate serviciul principal
			s.serviciu.value = serv
			if fostul and not T.puneRezerve([fostul] + [c for c in lista if c not in (serv, fostul)], s)[0]:
				_jurnal("configurare: fostul principal nu a intrat in rezerve")
				fostul = u""
		if serv == "gemini" and rez["model"]:
			s.model_gemini.value = rez["model"]
		elif serv == "openai":
			s.adresa_openai.value = rez["adresa"]
			if rez["model"]:
				s.model_openai.value = rez["model"]
		elif serv == "libre":
			s.adresa_libre.value = rez["adresa"]
		elif serv == "azure":
			s.regiune.value = rez["regiune"]
		elif serv in CU_MODEL_FIX:
			if serv == "cloudflare" and rez.get("cont"):
				s.cont_cloudflare.value = rez["cont"]
			if rez["model"]:
				getattr(s, "model_" + serv).value = rez["model"]
		s.pornit.value = True
		s.save()
		try:
			from Components.config import configfile
			configfile.save()
		except Exception as e:
			_jurnal("configfile: %s" % e.__class__.__name__)
		inst = T.instanta()
		p = rez.get("proba")
		ms = p["ms"] if p else None
		ora = time.strftime("%H:%M:%S")
		# ultima_proba e a serviciului principal („Probează traducerea”): proba unei rezerve nu o inlocuieste
		if p and not principal:
			inst.ultima_proba = {"stare": "ok", "original": p["original"], "traducere": p["traducere"], "ms": ms,
				"serviciu": T.numeServiciu(serv), "ora": ora}
		elif rez.get("cota") and not principal:
			inst.ultima_proba = {"stare": "eroare", "original": u"", "traducere": T.textEroare(E_COTA, serv),
				"ms": None, "serviciu": T.numeServiciu(serv), "ora": ora, "fel": E_COTA}
		try:
			inst.setariSchimbate()
		except Exception:
			pass
		afisat = rez.get("afisat") or rez["serviciu_nume"]
		if principal:
			popup = mesaj = _t("Cheia pentru %s e salvată ca rezervă; traducerea rămâne pe %s.") % (
				rez["serviciu_nume"], T.numeServiciu(principal))
			ce = ceFaci(E_COTA, serv) if rez.get("cota") else u""
		elif p:
			popup = _t("Traducerea subtitrărilor e gata, cu %s. Proba: %s") % (afisat, p["traducere"])
			mesaj = _t("Gata: traducerea subtitrărilor e pornită, cu %s.") % afisat
			ce = u""
		elif rez.get("cota"):
			popup = _t("Traducerea subtitrărilor e pornită, cu %s, dar cota gratuită s-a terminat. Merge din nou după "
				"ce se reface cota.") % afisat
			mesaj = _t("Cheia e bună și e salvată, cu %s, dar cota s-a terminat.") % afisat
			ce = ceFaci(E_COTA, serv)
		else:
			popup = _t("Traducerea subtitrărilor e pornită, cu %s (fără probă).") % afisat
			mesaj = _t("Salvat fără probă: traducerea subtitrărilor e pornită, cu %s.") % afisat
			ce = u""
		if rez.get("regiune_gasita"):
			mesaj = _t("Am găsit regiunea: %s (%s). %s") % (rez["regiune_gasita"][0], rez["regiune_gasita"][1], mesaj)
		nota = (_t("%s e acum serviciul principal; %s e primul la rezerve.") % (T.numeServiciu(serv),
			T.numeServiciu(fostul))) if fostul else u""
		if nota:
			mesaj += u" " + nota
		local = serv in ("libre", "openai") and _inCasa(rez["adresa"], T)
		self._pune(l, stare="ok", pas=u"", salvat=True, serviciu=serv, serviciu_nume=rez["serviciu_nume"],
			model=rez["model"], modele=rez["modele"] or self._stare.get("modele") or [], adresa=rez["adresa"],
			regiune=rez["regiune"], proba=dict(p) if p else None, ms=ms, lent=bool(ms is not None and ms > PRAG_LENT_MS),
			sfat_lent=sfatLent(ms, serv, local), incercate=rez.get("incercate") or [], mesaj=mesaj, ce_faci=ce,
			rezerva=bool(principal), principal=principal or serv, principal_nume=T.numeServiciu(principal or serv),
			nota_rezerve=nota)
		if principal:
			_jurnal("configurare: salvat ca rezerva (%s), principalul ramane %s" % (serv, principal))
		elif fostul:
			_jurnal("configurare: salvat (%s), fostul principal %s e primul la rezerve" % (serv, fostul))
		else:
			_jurnal("configurare: salvat (%s)" % serv)
		self._mesaj(_faraCheie(popup, l.chei()))

	def _mesaj(self, text):
		_jurnal("mesaj pe televizor")
		try:
			from Tools import Notifications
			from Screens.MessageBox import MessageBox
			Notifications.AddPopup(text, MessageBox.TYPE_INFO, 10, ID_MESAJ)
		except Exception as e:
			_jurnal("mesajul nu s-a putut arata: %s" % e.__class__.__name__)


# ------------------------------------------------------------------ cautarea serverelor din casa

def ipReceptor():
	"""IP-ul receptorului in reteaua locala (socket UDP fara trimitere: connect() alege interfata), sau "" """
	try:
		s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		try:
			s.connect(("10.254.254.254", 9))
			ip = s.getsockname()[0]
		finally:
			s.close()
	except Exception:
		return ""
	return ip if ip and not ip.startswith("0.") else ""


def retePrivata(ip):
	"""10/8, 172.16/12, 192.168/16 (nu 127, nu 169.254)"""
	try:
		p = [int(x) for x in ip.split(".")]
	except (ValueError, AttributeError):
		return False
	if len(p) != 4 or any(x < 0 or x > 255 for x in p):
		return False
	return p[0] == 10 or (p[0] == 172 and 16 <= p[1] <= 31) or (p[0] == 192 and p[1] == 168)


def _cheieIp(gazda):
	try:
		return tuple(int(x) for x in gazda.split("."))
	except ValueError:
		return (999, gazda)


class _Cautarea(object):
	def __init__(self, tinte, tinta, sfarsit):
		self.tinte = tinte
		self.tinta = tinta
		self.sfarsit = sfarsit
		self.cereri = 0
		self.progres = 0
		self.gasite = []
		self.inchisa = False


class Cautare(object):
	def __init__(self, T=None, cu_trezire=True, trimite_=None):
		self.T = _modulT(T)
		self._trimite = trimite_
		self.lacat = threading.Lock()
		self._curenta = None
		self._laGata = []
		self._stare = {"stare": "nimic", "progres": 0, "total": 0, "gasite": [], "mesaj": u"", "retea": u"",
			"ajutor": []}
		self.trezire = self.T.Trezire(self.proceseaza) if cu_trezire else None

	def stare(self):
		with self.lacat:
			s = dict(self._stare)
			c = self._curenta
			if c is not None and s["stare"] == "lucru":
				s["progres"] = c.progres
			s["gasite"] = [dict(g, modele=list(g["modele"]), limbi=list(g["limbi"])) for g in s["gasite"]]
			s["ajutor"] = list(s.get("ajutor") or [])
		return s

	def porneste(self, tinte=None, laGata=None):
		"""cauta serverele Ollama (11434) si LibreTranslate (5000) in /24 al receptorului. -> (ok, mesaj)"""
		with self.lacat:
			if self._curenta is not None:
				return False, _t("Caută deja. Așteaptă să se termine.")
		try:
			tinta = self.T.limbaTinta()
		except Exception:
			tinta = "ro"
		if tinte is None:
			ip = ipReceptor()
			if not ip:
				return False, _t("Receptorul nu are rețea.")
			if not retePrivata(ip):
				return False, _t("Receptorul nu e într-o rețea de acasă (adresă privată); nu caut.")
			prefix = ip.rsplit(".", 1)[0]
			retea = prefix + ".0/24"
			lista = []
			for i in range(1, 255):
				g = "%s.%d" % (prefix, i)
				if g != ip:
					lista.append((g, PORT_OLLAMA))
					lista.append((g, PORT_LIBRE))
		else:
			retea = u""
			lista = []
			for t in tinte:
				try:
					lista.append((u"%s" % t[0], int(t[1])))
				except (TypeError, ValueError, IndexError):
					continue
			lista = lista[:CAUTARE_MAX_TINTE]
		c = _Cautarea(lista, tinta, time.monotonic() + CAUTARE_MAX_S)
		with self.lacat:
			if self._curenta is not None:
				return False, _t("Caută deja. Așteaptă să se termine.")
			self._curenta = c
			if laGata is not None:
				self._laGata.append(laGata)
			self._stare = {"stare": "lucru", "progres": 0, "total": len(lista), "gasite": [],
				"mesaj": _t("Caut servere în rețeaua de acasă..."), "retea": retea, "ajutor": []}
		t = threading.Thread(target=self._lucru, args=(c, retea), name="HdsCautareServere")
		t.daemon = True
		t.start()
		if self.trezire is not None:
			self.trezire.cereCeas(True)
		return True, _t("Am pornit căutarea.")

	def _deschis(self, gazda, port, termen):
		try:
			s = socket.create_connection((gazda, port), timeout=termen)
		except (OSError, socket.error, ValueError):
			return False
		try:
			s.close()
		except Exception:
			pass
		return True

	def _get(self, c, adresa):
		with self.lacat:
			if c.cereri >= CAUTARE_MAX_HTTP:
				return None, None
			c.cereri += 1
		ramas = c.sfarsit - time.monotonic()
		if ramas < 0.2:
			return None, None
		try:
			return (self._trimite or self.T.trimite)(adresa, {"Accept": "application/json", "User-Agent": AGENT}, None,
				min(CAUTARE_TERMEN_HTTP_S, ramas))
		except Exception:
			return False, None

	def _identifica(self, c, gazda, port):
		nume = ("[%s]" % gazda) if ":" in gazda else gazda
		baza = "http://%s:%d" % (nume, port)
		ordine = ("libre", "ollama") if port == PORT_LIBRE else ("ollama", "libre")
		for fel in ordine:
			cod, date = self._get(c, baza + ("/api/tags" if fel == "ollama" else "/languages"))
			if cod is None or cod is False:
				return None			# limita de cereri, timpul sau portul nu mai raspunde
			if cod != 200:
				continue
			try:
				j = json.loads(date.decode("utf-8"))
			except (ValueError, UnicodeDecodeError, AttributeError):
				continue
			if fel == "ollama" and isinstance(j, dict) and isinstance(j.get("models"), list):
				modele = [m for m in j["models"] if isinstance(m, dict) and (m.get("name") or m.get("model"))]
				ales = alegeModel("ollama", modele)
				return {"fel": "ollama", "adresa": baza, "gazda": gazda, "port": port,
					"modele": [u"%s" % (m.get("name") or m.get("model")) for m in modele][:MAX_MODELE],
					"model_ales": ales, "limbi": [], "are_tinta": bool(ales)}
			if fel == "libre" and isinstance(j, list) and j and all(isinstance(x, dict) and "code" in x and
					isinstance(x.get("targets", []), list) for x in j):
				cod_tinta = getattr(self.T, "_COD_LIBRE", {}).get(c.tinta, c.tinta)
				return {"fel": "libre", "adresa": baza, "gazda": gazda, "port": port, "modele": [], "model_ales": u"",
					"limbi": [u"%s" % x["code"] for x in j][:100],
					"are_tinta": any(cod_tinta in (x.get("targets") or []) for x in j)}
		return None

	def _lucru(self, c, retea):
		q = _coada.Queue()
		for t in c.tinte:
			q.put(t)

		def lucrator():
			while time.monotonic() < c.sfarsit:
				try:
					gazda, port = q.get_nowait()
				except _coada.Empty:
					return
				ramas = c.sfarsit - time.monotonic()
				deschis = ramas > 0 and self._deschis(gazda, port, min(CAUTARE_TERMEN_CONECTARE_S, ramas))
				with self.lacat:
					c.progres += 1
				if deschis:
					g = self._identifica(c, gazda, port)
					if g is not None:
						with self.lacat:
							if not c.inchisa:
								c.gasite.append(g)

		fire = []
		for _i in range(max(1, min(CAUTARE_FIRE, len(c.tinte)))):
			f = threading.Thread(target=lucrator, name="HdsCautareFir")
			f.daemon = True
			f.start()
			fire.append(f)
		for f in fire:
			f.join(max(0.0, c.sfarsit + 0.5 - time.monotonic()))		# firele intarziate nu mai conteaza (inchisa)
		with self.lacat:
			c.inchisa = True
			gasite = sorted(c.gasite, key=lambda g: (_cheieIp(g["gazda"]), g["port"]))
			oprita = c.progres < len(c.tinte)
			if gasite:
				n = len(gasite)
				mesaj = _t("Am găsit un server.") if n == 1 else _t("Am găsit %d servere.") % n
				ajutor = []
			elif retea:
				mesaj = _t("Nu am găsit niciun server Ollama sau LibreTranslate în rețeaua %s. Ollama ascultă din "
					"fabrică numai pe calculatorul lui, așa că receptorul nu-l vede până nu-l pornești pentru "
					"rețea.") % retea
				ajutor = [_t(a) for a in AJUTOR_RETEA]
			else:
				mesaj = _t("Nu am găsit niciun server Ollama sau LibreTranslate. Ollama ascultă din fabrică numai pe "
					"calculatorul lui, așa că receptorul nu-l vede până nu-l pornești pentru rețea.")
				ajutor = [_t(a) for a in AJUTOR_RETEA]
			if oprita:
				mesaj += u" " + _t("Căutarea s-a oprit după %d secunde.") % int(CAUTARE_MAX_S)
			self._stare = {"stare": "gata", "progres": c.progres, "total": len(c.tinte), "gasite": gasite,
				"mesaj": mesaj, "retea": retea, "ajutor": ajutor}
			self._curenta = None
		_jurnal("cautare: %d servere, %d cereri HTTP" % (len(gasite), c.cereri))
		if self.trezire is not None:
			self.trezire.trezeste()

	def asteapta(self, termen_s=20.0):
		"""probele: pana se termina cautarea, apoi proceseaza()"""
		sfarsit = time.monotonic() + termen_s
		while time.monotonic() < sfarsit:
			with self.lacat:
				gata = self._curenta is None
			if gata:
				break
			time.sleep(0.01)
		self.proceseaza()

	def proceseaza(self):
		with self.lacat:
			if self._curenta is not None:
				return
			functii, self._laGata = self._laGata, []
		if self.trezire is not None:
			self.trezire.cereCeas(False)
		if functii:
			s = self.stare()
			for f in functii:
				try:
					f(s)
				except Exception as e:
					_jurnal("cautare: %s" % e.__class__.__name__)


# ------------------------------------------------------------------ instantele

_CONFIGURATOR = [None]
_CAUTARE = [None]


def configurator():
	if _CONFIGURATOR[0] is None:
		_CONFIGURATOR[0] = Configurator()
	return _CONFIGURATOR[0]


def cautare():
	if _CAUTARE[0] is None:
		_CAUTARE[0] = Cautare()
	return _CAUTARE[0]
