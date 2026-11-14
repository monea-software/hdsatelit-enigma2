# -*- coding: utf-8 -*-
# Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
# SPDX-License-Identifier: GPL-2.0-only
#
# HdsPornireMultipla.py: Porneste alte imagini (Meniu > Standby si repornire), fara ecran. Il folosesc ecranul de pe
# receptor (Screens/HdsPornireMultipla.py) si pagina web /alimentare (HdsWebControl/alimentare_web.py, cardul flash),
# deci amandoua arata aceleasi imagini si scriu la fel.
# Kexec deja instalat se citeste din STARTUP si initramfs, iar schema GPT din
# numele reale boot/kernelN/rootfsN. Nu exista o lista inchisa de modele.
# Alegerea foloseste acelasi ecran, aceeasi scriere si repornirea obisnuita.
#
# Octagon SF8008, SF8008 MINI si primul Amiko Viper 4K (V10, masina viper4k, aceeasi placa) au in memorie patru
# locuri de imagini: nucleul in linuxkernel1-4 (mmcblk0p12-p15) si sistemul in subdosarul linuxrootfs1-4 al partitiei
# userdata (mmcblk0p16); V10 si Uclan Ustym 4K PRO (bootargs.bin, emmc_partitions.xml si incarcatorul identice cu
# cele SF8008) folosesc aceeasi impartire a memoriei; GigaBlue UHD TRIO 4K la fel (aceeasi blkdevparts in bootargs.bin,
# acelasi emmc_partitions.xml si boot.img, dar alt fastboot.bin: nemasurat pe un aparat). Incarcatorul
# citeste la pornire fisierul STARTUP de pe partitia bootoptions (FAT, mmcblk0p3, montata la /boot), langa care stau
# STARTUP_1..4 (locurile din memorie), STARTUP_5..6 (stickul) si STARTUP_RECOVERY, puse de producator. Alegerea unei
# imagini = STARTUP_N copiat octet cu octet peste STARTUP, apoi repornirea; nimic altceva nu se scrie (bootargs si
# p1-p11 raman neatinse).
#
# SIGURANTA (e pornirea receptorului):
# - se scrie numai un loc cu forma stiuta, cu nucleu valid (antet uImage cu CRC bun, cat incape in partitie) si sistem cu
#   sbin/init; altfel locul se arata cu motivul sau nu se arata deloc (locurile goale);
# - in memorie: tinta emmcflash0.linuxkernelK, root si kernel sunt /dev/mmcblk0pN,
#   rootsubdir=linuxrootfsK. Partitiile vin din numele din blkdevparts,
#   cu aceeasi tabela ca in linia de comanda de acum;
# - pe card sau stick, forma stiuta: boot usb0.sdaK 'root=/dev/sdaM [rootfstype=ext4] kernel=/dev/sdaK rootwait ...', fara
#   rootsubdir, acelasi blkdevparts. Linux nu deosebeste aici cardul de stick (amandoua sunt /dev/sd*), deci textele spun
#   "card sau stick". Numele sda e scris in STARTUP_N, iar la pornire discurile isi pot schimba numele. De aceea locul se
#   alege numai cand /proc/partitions (arata numai discurile cu suport) are un singur disc sd* si el e chiar sda. Cu mai
#   multe discuri locul se arata, dar nu se alege: nici faptul ca imaginea de acum a pornit de pe sda nu dovedeste ca
#   nucleul imaginii alese va gasi discurile in aceeasi ordine;
# - cu nucleu intern, sistemul poate sta pe o partitie USB ext4, in linuxrootfsN;
#   tinta si kernel trebuie sa numeasca aceeasi partitie interna;
# - root=UUID se rezolva fara cache si trebuie sa fie unic. Suportul UUID se dovedeste prin nucleul locului, nu printr-un
#   fisier din imaginea aleasa: e nucleul pornit acum (cu root=UUID sau /dev/.newMB-uuid), sau nucleul din partitia
#   locului contine initramfs-ul care pune /dev/.newMB-uuid (nucleuCuUuid; sloturile de pe disc ale altor imagini folosesc
#   nucleul comun din linuxkernel1, deci imaginea pornita din alt slot din memorie nu-l ruleaza);
# - alta forma se arata cu motivul, nu se alege;
# - partitiile cardului sau ale stickului se citesc de unde le-a montat deja sistemul; altfel se monteaza numai pentru
#   citit (ro,noload: fara reluarea jurnalului ext4) si se demonteaza imediat. Nu se scrie nimic pe ele;
# - STARTUP vechi ramane in STARTUP.hds-inainte; scrierea: STARTUP.hds-nou, fsync, rename (os.replace) peste STARTUP, sync, apoi
#   citit inapoi si comparat; la o nepotrivire se pune la loc cel vechi;
# - directorul scris este partitia de pornire dovedita in /proc/mounts sau
#   radacina flash expusa de kexec, cu initramfs si sabloane de pornire existente.
#
# Vu+ 4K cu kexec (pus de alta imagine; initramfs-ul STARTUP.cpio.gz din radacina flash):
# - in orice loc pornit, si de pe USB, initramfs-ul pune radacina flash intreaga la /boot (bind sau move), cu STARTUP,
#   STARTUP_N, STARTUP_RECOVERY si STARTUP.cpio.gz; /proc/cmdline incepe cu kexec=1, are kernel= si rootsubdir= din
#   STARTUP, iar root= e dispozitivul gasit (un root=UUID=... din STARTUP apare aici ca /dev/sdXN);
# - locurile din memorie: kernel=/linuxrootfsN/zImage root=/dev/mmcblk0pX rootsubdir=linuxrootfsN; Recovery (locul 0
#   in lista): kernel=/zImage ... rootsubdir=linuxrootfs0; locurile de pe USB sau HDD, N de la 4:
#   kernel=<model>/linuxrootfsN/zImage root=UUID=<uuid> rootsubdir=<model>/linuxrootfsN [rootwait=40], cu kernel=
#   socotit de la radacina partitiei din root=;
# - UUID=/PARTUUID= le cauta initramfs-ul cu blkid, deci un asemenea loc se alege si cu mai multe discuri puse; un
#   nucleu sau un disc negasit la pornire il duce inapoi in Recovery, nu il lasa fara imagine.
# Locul pornit se recunoaste dupa partitie (UUID-ul rezolvat), subdosar si nucleu, nu dupa textul din root=.
#
# Qviart DUAL 4K UHD (masina dagsmv200, MACHINEBUILD=dual OEM=dags in linia de comanda; 0.7.5): alta schema, NUMAI aici.
# - Incarcatorul porneste locul scris in PRIMUL OCTET al partitiei „flag” (mmcblk0p22 in blkdevparts): 0 = Android
#   (nucleul in partitia boot), 1-4 = Linux. bootargs.bin al producatorului are pentru fiecare loc K comanda lui
#   (bootcmd_enigmaK: nucleul din linuxkernelK, p26-p29) si linia de comanda (bootargs_enigmaK: root=rootfs (p30),
#   rootsubdir=linuxrootfsK). Imaginea OE-Alliance pentru acest model citeste locul de acum din acest octet si il scrie
#   la alegere (Tools/MultiBoot.py: DUAL_BOOT_FILE = /dev/block/by-name/flag, pack("B", loc)).
# - Lista se face din blkdevparts (nu din fisierele STARTUP): locurile 1-4 cu nucleu valid si sistem cu sbin/init in
#   rootfs/linuxrootfsK (aceeasi verificare ca la SF8008), plus Android (locul 0) cand partitia boot are un nucleu uImage
#   valid. Locul de acum se ia din linia de comanda (rootsubdir si kernel), ca la celelalte modele.
# - Alegerea scrie UN SINGUR OCTET (0-4) la inceputul partitiei flag, si nimic altceva: fara STARTUP, fara alte partitii.
#   Inainte: dispozitivul e chiar partitia flag din blkdevparts (si /dev/block/by-name/flag, daca exista, duce la ea),
#   e un dispozitiv bloc de 1 MiB in /proc/partitions; deschis fara O_CREAT si fara O_TRUNC; dupa: fsync, citit inapoi
#   si comparat; la o nepotrivire se pune la loc octetul vechi. „Nu” la intrebarea de repornire pune la loc octetul vechi.
#
# Citirea listei poate monta multe partitii, deci ecranul si pagina web o fac pe un fir separat. Alegerea verifica din nou
# numai locul ales (locuri(numai=...)), deci ramane scurta pe firul enigma2.
#
# Fisierul nu importa nimic din enigma2 la incarcare: probele de pe PC dau `radacina` (un receptor fals) si
# `monteaza` (montarea partitiilor).

import os
import re
import stat
import struct
import subprocess
import zlib

FISIER_STARTUP = "STARTUP"
RECOVERY = "STARTUP_RECOVERY"
O_DATA = "STARTUP_ONCE"
LOC_RECOVERY = "0"
COPIE = "STARTUP.hds-inainte"
NOU = "STARTUP.hds-nou"
ABSENT = b"HDS-FARA-STARTUP\n"
MAXIM_STARTUP = 4096
UIMAGE_MAGIC = 0x27051956
TINTA_EMMC = re.compile(r"^boot emmcflash0\.linuxkernel([1-9])$")
# GigaBlue UHD Quad 4K Pro: opt locuri, tinta cu „:” (boot.bin al producatorului)
TINTA_GPT_SUBDOSAR = re.compile(r"emmcflash0\.linuxkernel([1-9][0-9]?):?")
TINTA_DISC = re.compile(r"^usb0\.sda([1-9][0-9]*)$")
PARTITIE_SDA = re.compile(r"^/dev/sda[1-9][0-9]*$")
PARTITIE_SCOASA = re.compile(r"^/dev/((?:sd[a-z]+|mmcblk[1-9][0-9]*p)[1-9][0-9]*)$")
UUID_DISC = re.compile(r"^UUID=([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})$")
# PARTUUID: GPT (ca un UUID) sau MBR (semnatura discului si numarul partitiei).
PARTUUID_DISC = re.compile(r"^PARTUUID=([0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}|[0-9a-fA-F]{8}-[0-9a-fA-F]{2})$")
SUBDOSAR_DISC = re.compile(r"^linuxrootfs[1-9][0-9]*$")
# Kexec: si <model>/linuxrootfsN (locurile de pe USB sau HDD facute de alte imagini), un singur nivel, fara ..
SUBDOSAR_KEXEC = re.compile(r"^(?:[A-Za-z0-9_-]+/)?linuxrootfs[1-9][0-9]*$")
LINIE = re.compile(r"^boot (\S+) '([ -&(-~]*)'\n?$")
OPTIUNI_CITIRE = "ro,noload"
# Qviart DUAL 4K (schema „flag”, mai sus)
FLAG_PARTITIE = "flag"
FLAG_LEGATURA = "dev/block/by-name/flag"
FLAG_MARIME = 1024 * 1024
FLAG_LOCURI = (1, 2, 3, 4)
LOC_ANDROID = 0
ANDROID = "Android"
_flagVechi = []   # [(dispozitivul, octetul de dinainte)]: ultima alegere, pentru inapoi()


def N_(text):
	"""Marcaj pentru xgettext (--keyword=N_): textul se traduce la folosire."""
	return text


def _(text):
	try:
		import builtins
		return builtins._(text)
	except (AttributeError, ImportError, NameError):
		return text


TITLU = N_("Repornește în altă imagine")
NOTA = N_("Alegi imaginea și apeși OK: receptorul repornește în ea. Lista arată imaginile instalate în memoria "
	"receptorului.")
CAUT = N_("Caut imaginile instalate...")
RAND = N_("Locul %(loc)s: %(imagine)s")
RAND_ACUM = N_("Locul %(loc)s: %(imagine)s, pornită acum")
RAND_STRICAT = N_("Locul %(loc)s: %(imagine)s, nu poate porni")
RAND_STICK = N_("Pe card sau stick: %(imagine)s, pornită acum")
RAND_DISC = N_("Locul %(loc)s, pe card sau stick: %(imagine)s")
RAND_DISC_ACUM = N_("Locul %(loc)s, pe card sau stick: %(imagine)s, pornită acum")
RAND_DISC_STRICAT = N_("Locul %(loc)s, pe card sau stick: %(imagine)s, nu poate porni")
RAND_DISC_REFUZ = N_("Locul %(loc)s, pe card sau stick: %(imagine)s, nu se alege: %(motiv)s")
MOTIV_DISCURI = N_("mai multe discuri puse")
MOTIV_FORMA = N_("formă necunoscută")
MOTIV_PARTITIE = N_("partiția nu este prezentă sau UUID-ul nu este unic")
MOTIV_CITIRE = N_("nu pot citi partiția imaginii")
MOTIV_UUID = N_("suportul UUID al nucleului ales nu este dovedit")
NOTA_DISC = N_("Alegi imaginea și apeși OK: receptorul repornește în ea. Lista arată imaginile din memoria receptorului "
	"și de pe card sau stick.")
NOTA_DISCURI = N_("Sunt mai multe discuri puse în receptor, iar la pornire numele lor se pot încurca. Scoate discurile de "
	"care nu ai nevoie: lista se actualizează singură.")
PE_STICK = N_("Imaginea de acum rulează de pe card sau stick, dar nu îi găsesc locul printre cele de pornire.")
NICIUNA = N_("Nu am găsit alte imagini instalate, nici în memorie, nici pe card sau stick.")
NOTA_O_DATA = N_("Altă imagine a cerut ca următoarea pornire să fie o singură dată în imaginea ei. Imaginea aleasă aici "
	"pornește la repornirea de după aceea.")
INTREBARE = N_("Receptorul repornește în imaginea %s. Continui?")
BUTON = N_("Pornește")
DEJA = N_("Aceasta e imaginea pornită acum.")
REFUZ = N_("Imaginea din locul %s nu poate porni (lipsește nucleul sau sistemul), deci nu o aleg.")
REFUZ_DISCURI = N_("Sunt mai multe discuri puse în receptor, iar la pornire numele lor se pot încurca și receptorul n-ar "
	"mai porni. Scoate discurile de care nu ai nevoie, apoi alege din nou.")
REFUZ_FORMA = N_("Locul %s are o formă de pornire pe care nu o cunosc, deci nu îl aleg.")
REFUZ_MOTIV = N_("Locul %(loc)s nu se alege: %(motiv)s.")
NEGASIT = N_("Locul ales nu mai e în listă. Deschide din nou lista.")
EROARE = N_("Nu am putut scrie alegerea, deci receptorul rămâne în imaginea de acum.")
FARA_NUME = N_("Imagine fără nume")


def _log(text):
	print("[HdsPornireMultipla] %s" % text)


def _cale(radacina, rel):
	return os.path.join(radacina or "/", rel.lstrip("/"))


def _citeste(cale, maxim=65536):
	try:
		with open(cale, "rb") as f:
			return f.read(maxim)
	except (IOError, OSError):
		return None


def _text(cale, maxim=65536):
	d = _citeste(cale, maxim)
	return d.decode("utf-8", "replace") if d is not None else ""


# ------------------------------------------------------------------ linia de comanda si partitiile

def parametri(text):
	"""cheie=valoare din linia de comanda (prima aparitie castiga)."""
	p = {}
	for cuv in (text or "").split():
		k, semn, v = cuv.partition("=")
		if semn and k not in p:
			p[k] = v
	return p


def partitii(blkdevparts):
	"""blkdevparts=mmcblk0:1M(boot),...,-(userdata) -> ("mmcblk0", [(nume, marime_octeti sau None)])."""
	disc, semn, lista = (blkdevparts or "").partition(":")
	if not semn:
		return None, []
	rez = []
	for bucata in lista.split(","):
		m = re.match(r"^(-|\d+)([KMG]?)\(([A-Za-z0-9_]+)\)$", bucata.strip())
		if not m:
			return None, []
		if m.group(1) == "-":
			marime = None
		else:
			marime = int(m.group(1)) * {"": 1, "K": 1024, "M": 1024 * 1024, "G": 1024 * 1024 * 1024}[m.group(2)]
		rez.append((m.group(3), marime))
	return disc, rez


def dispozitivPartitie(blkdevparts, nume):
	"""(/dev/mmcblk0pN, marime) pentru partitia cu numele `nume`; (None, None) cand lipseste."""
	disc, lista = partitii(blkdevparts)
	for i, (n, marime) in enumerate(lista):
		if n == nume:
			return "/dev/%sp%d" % (disc, i + 1), marime
	return None, None


def linieComanda(radacina=None):
	return _text(_cale(radacina, "proc/cmdline"), 16384).strip()


def disponibil(radacina=None):
	"""Capacitatea receptorului: bootoptions sau pornire kexec deja instalata.
	Nu instaleaza si nu initializeaza pornirea multipla."""
	if _dual(radacina):
		return True
	dev, _m = dispozitivPartitie(parametri(linieComanda(radacina)).get("blkdevparts", ""), "bootoptions")
	if dev or _dosarKexec(radacina) or os.path.exists(_cale(radacina, "dev/block/by-name/bootoptions")):
		return True
	boot = dosarBoot(radacina)
	if boot and any(_verificaNativ(citesteStartup(date), {}, radacina) for _n, _fisier, date in startupuri(boot)):
		return True
	# GigaBlue UHD Quad 4K Pro (0.7.5): partitia boot (FAT, STARTUP_1..8 ale producatorului) poate sta
	# nemontata; cu locurile numite in GPT (linuxkernel1 si userdata) lista o monteaza la cerere (_deschideBoot)
	return bool(not boot and _gptSubdosare(radacina))


# ------------------------------------------------------------------ fisierele STARTUP

def citesteStartup(date):
	"""Octetii unui STARTUP_N -> {"tinta", "argumente", "p"} sau None cand nu are forma `boot TINTA '...'`."""
	if date is None or len(date) > MAXIM_STARTUP:
		return None
	try:
		text = date.decode("ascii")
	except UnicodeDecodeError:
		return None
	m = LINIE.match(text)
	if m:
		tinta, argumente = m.group(1), m.group(2)
	elif re.fullmatch(r"[A-Za-z0-9_./:=,+ -]+\n?", text):
		# Incarcatorul kexec citeste direct parametrii din STARTUP.
		tinta, argumente = "", text.strip()
	else:
		return None
	chei = [c.split("=", 1)[0] for c in argumente.split() if "=" in c]
	sensibile = ("root", "kernel", "rootsubdir", "rootfstype", "blkdevparts",
		"userdataroot", "userdatasubdir", "initrd")
	repetate = any(chei.count(k) > 1 for k in sensibile)
	return {"tinta": tinta, "argumente": argumente,
		"p": parametri(argumente), "repetate": repetate}


def _subKexec(sub):
	"""linuxrootfs0 inseamna radacina flash insasi (Recovery)."""
	return "" if sub in ("", "linuxrootfs0") else sub


def _parametriKexec(st, radacina=None):
	"""Forma instalata de kexec, cu nucleul pastrat in dosarul imaginii -> (partitia din root=, subdosarul); None altfel.
	kernel= poate fi scris cu sau fara / la inceput; calea lui fata de radacina partitiei: _nucleuRelativ."""
	if not st or st["tinta"] or st.get("repetate"):
		return None
	p = st["p"]
	sub = _subKexec(p.get("rootsubdir", ""))
	nucleu = p.get("kernel", "")
	if not sub:
		if nucleu != "/zImage":
			return None
	elif not SUBDOSAR_KEXEC.fullmatch(sub) or nucleu.lstrip("/") != sub + "/zImage":
		return None
	if p.get("rootfstype", "ext4") != "ext4" or p.get("initrd", "/STARTUP.cpio.gz").lstrip("/") != "STARTUP.cpio.gz":
		return None
	ref = p.get("root", "")
	dev = ref if re.fullmatch(r"/dev/mmcblk0p[1-9][0-9]*", ref) else _radacinaDisc(ref, radacina)
	if not dev:
		return None
	return dev, sub


def _nucleuRelativ(st):
	"""kernel= din sablon, socotit de la radacina partitiei din root= (asa il citeste initramfs-ul)."""
	return st["p"].get("kernel", "").lstrip("/")


def _aceeasiPartitie(a, b, radacina=None):
	"""Doua referinte root= (/dev/..., UUID=..., PARTUUID=...) numesc aceeasi partitie."""
	if not a or not b:
		return False
	if a == b:
		return True
	da = a if a.startswith("/dev/mmcblk0p") else _radacinaDisc(a, radacina)
	db = b if b.startswith("/dev/mmcblk0p") else _radacinaDisc(b, radacina)
	return bool(da) and da == db


def _acumKexec(st, cmd, radacina=None):
	"""Sablonul descrie pornirea de acum: aceeasi partitie (initramfs-ul pune in linia de comanda dispozitivul gasit, nu
	UUID-ul scris in STARTUP), acelasi subdosar si, cand linia de comanda il are, acelasi nucleu."""
	p = st["p"]
	if _subKexec(p.get("rootsubdir", "")) != _subKexec(cmd.get("rootsubdir", "")):
		return False
	# Unele initramfs nu pastreaza kernel= in linia de comanda expusa imaginii.
	if cmd.get("kernel") and p.get("kernel", "").lstrip("/") != cmd["kernel"].lstrip("/"):
		return False
	return _aceeasiPartitie(p.get("root", ""), cmd.get("root", ""), radacina)


def _sabloane(dosar):
	"""STARTUP_<cifre>, apoi Recovery ca locul 0 (numai cand nu exista un STARTUP_0 adevarat): [(loc, fisier, octeti)]."""
	rez = startupuri(dosar)
	if not any(n == LOC_RECOVERY for n, _f, _d in rez):
		date = _citeste(os.path.join(dosar, RECOVERY), MAXIM_STARTUP + 1)
		if date is not None:
			rez.insert(0, (LOC_RECOVERY, RECOVERY, date))
	return rez


def _dosarKexec(radacina=None):
	"""Radacina flash expusa de incarcator la /boot, nu dosarul unui slot. Trebuie sa aiba initramfs-ul kexec si cel
	putin un sablon kexec bun. Dovada ca e chiar radacina pornirii de acum: kexec=1 in linia de comanda (initramfs-ul
	o rescrie mereu asa si pune mereu radacina flash la /boot), sau un sablon care descrie pornirea de acum, sau pornirea
	direct din flash."""
	cmd = parametri(linieComanda(radacina))
	sub_curent = bool(_subKexec(cmd.get("rootsubdir", "")))
	for rand in _text(_cale(radacina, "proc/mounts")).splitlines():
		c = rand.split()
		if (len(c) < 4 or c[1] not in ("/boot", "/") or c[2] != "ext4" or "rw" not in c[3].split(",") or
			not re.fullmatch(r"/dev/mmcblk0p[1-9][0-9]*", c[0])):
			continue
		if c[1] == "/" and sub_curent:
			continue
		dosar = _cale(radacina, c[1])
		initrd = os.path.join(dosar, "STARTUP.cpio.gz")
		if os.path.islink(initrd) or _citeste(initrd, 2) != b"\x1f\x8b":
			continue
		for _n, _fisier, date in _sabloane(dosar):
			st = citesteStartup(date)
			if _parametriKexec(st, radacina) and (_acumKexec(st, cmd, radacina) or
				(cmd.get("kexec") == "1" and c[1] == "/boot") or
				(not sub_curent and cmd.get("root") == c[0] and radacinaValida(_cale(radacina, "/")))):
				return dosar
	return None


def _nucleuKexec(cale, marime_partitie=None):
	"""Antet ARM zImage si lungimea declarata, fara a executa nucleul."""
	if os.path.islink(cale) or (marime_partitie is None and not os.path.isfile(cale)):
		return False
	antet = _citeste(cale, 48)
	if not antet or len(antet) < 48:
		return False
	magie, inceput, sfarsit = struct.unpack("<III", antet[36:48])
	marime = os.path.getsize(cale) if marime_partitie is None else marime_partitie
	return magie == 0x016f2818 and 0 < sfarsit - inceput <= marime


def verificaEmmc(st, cmd):
	"""Locul K din memorie, cu forma stiuta si aceleasi partitii ca acum -> (K, dispozitivul nucleului, marimea lui,
	dispozitivul radacinii, subdosarul); None altfel."""
	if not st or st.get("repetate"):
		return None
	m = TINTA_EMMC.match("boot " + st["tinta"])
	if not m:
		return None
	k = m.group(1)
	p = st["p"]
	blk = p.get("blkdevparts", "")
	if not blk or blk != cmd.get("blkdevparts"):
		return None
	nucleu, marime = dispozitivPartitie(blk, "linuxkernel" + k)
	rad, _m = dispozitivPartitie(blk, "userdata")
	if not nucleu or not rad or p.get("kernel") != nucleu or p.get("root") != rad:
		return None
	if p.get("rootsubdir") != "linuxrootfs" + k or p.get("rootfstype", "ext4") != "ext4":
		return None
	return k, nucleu, marime, rad, p["rootsubdir"]


def _radacinaDisc(referinta, radacina=None):
	"""Partitia externa numita direct sau printr-un UUID sau PARTUUID unic, fara cache. Numele sdX de acum nu conteaza:
	UUID-ul si PARTUUID-ul raman aceleasi oricum s-ar numi discul la pornire."""
	if PARTITIE_SCOASA.fullmatch(referinta):
		return referinta
	m = UUID_DISC.fullmatch(referinta)
	cheie, fals = "UUID", "dev/uuid/"
	if not m:
		m = PARTUUID_DISC.fullmatch(referinta)
		cheie, fals = "PARTUUID", "dev/partuuid/"
	if not m:
		return ""
	valoare = m.group(1).lower()
	if radacina:
		# Receptorul fals nu ruleaza unelte pe discurile calculatorului.
		_de, part = discuriScoase(radacina)
		gasite = ["/dev/" + n for n in part
			if _text(_cale(radacina, fals + n)).strip().lower() == valoare]
	else:
		try:
			date = subprocess.check_output(["blkid", "-c", "/dev/null",
				"-t", cheie + "=" + valoare, "-o", "device"],
				stderr=subprocess.DEVNULL, timeout=5)
			gasite = date.decode("ascii").split()
		except (OSError, ValueError, subprocess.SubprocessError):
			return ""
	return gasite[0] if len(gasite) == 1 and PARTITIE_SCOASA.fullmatch(gasite[0]) else ""


def _uuidDovedit(st, cmd, radacina):
	"""Capacitatea apartine nucleului locului. Dovezile: (1) e chiar nucleul pornit acum, iar acum radacina e UUID= sau
	initramfs-ul lui a pus /dev/.newMB-uuid; (2) nucleul din partitia locului contine el insusi initramfs-ul care pune
	/dev/.newMB-uuid (nucleuCuUuid). A doua e pentru locurile de pe disc ale altor imagini, care folosesc toate nucleul
	comun din linuxkernel1, cand imaginea de acum ruleaza cu alt nucleu (Wlad, Amiko Viper 4K V10, asistenta 366732,
	13.11.2026: din slotul 3 toate cele 14 imagini de pe disc erau refuzate, desi pornesc). PARTUUID nu e dovedit pentru
	initramfs-ul locurilor din bootoptions (el cauta numai UUID-ul), deci un asemenea loc se arata, dar nu se alege."""
	p = st["p"]
	if PARTUUID_DISC.fullmatch(p.get("root", "")):
		return False
	if not UUID_DISC.fullmatch(p.get("root", "")):
		return True
	if p.get("kernel") == cmd.get("kernel") and (
		bool(UUID_DISC.fullmatch(cmd.get("root", ""))) or
		os.path.exists(_cale(radacina, "dev/.newMB-uuid"))):
		return True
	nucleu = p.get("kernel", "")
	if not PARTITIE_NUCLEU.fullmatch(nucleu):
		return False
	return nucleuCuUuid(_cale(radacina, nucleu), _marimePartitie(nucleu, radacina))


def verificaDisc(st, cmd, radacina=None, cuUuid=True):
	"""Nucleu USB separat sau nucleu intern cu sistem USB in linuxrootfsN.
	Intoarce (nucleu, radacina); fara rootwait sau cu alte partitii, None. `cuUuid=False`: numai forma, fara dovada
	suportului UUID (ca un loc gol cu forma stiuta sa nu se arate, oricare ar fi nucleul pornit acum)."""
	if not st or st.get("repetate"):
		return None
	p = st["p"]
	blk = p.get("blkdevparts", "")
	if not blk or blk != cmd.get("blkdevparts"):
		return None
	if p.get("rootfstype", "ext4") != "ext4" or "rootwait" not in st["argumente"].split():
		return None
	emmc = TINTA_EMMC.fullmatch("boot " + st["tinta"])
	if emmc:
		nucleu, _m = dispozitivPartitie(blk, "linuxkernel" + emmc.group(1))
		rad = _radacinaDisc(p.get("root", ""), radacina)
		if (not nucleu or not nucleu.startswith("/dev/mmcblk0p") or
			p.get("kernel") != nucleu or not rad):
			return None
		if not SUBDOSAR_DISC.fullmatch(p.get("rootsubdir", "")):
			return None
		if p.get("userdataroot", p["root"]) != p["root"]:
			return None
		return (nucleu, rad) if not cuUuid or _uuidDovedit(st, cmd, radacina) else None
	m = TINTA_DISC.match(st["tinta"])
	if not m:
		return None
	nucleu = "/dev/sda" + m.group(1)
	rad = p.get("root", "")
	if p.get("kernel") != nucleu or not PARTITIE_SDA.match(rad) or rad == nucleu:
		return None
	if "rootsubdir" in p:
		return None
	date = p.get("userdataroot")
	if date is not None and not PARTITIE_SDA.match(date):
		return None
	return nucleu, rad


def discuriScoase(radacina=None):
	"""Din /proc/partitions, care arata numai discurile cu suport: ([discurile sd*], {partitie: marime in octeti}). Intra si
	partitiile mmcblkNpM ale cardurilor vazute ca mmc (N >= 1), pentru locurile cu alta forma."""
	discuri, partitii_ = [], {}
	for rand in _text(_cale(radacina, "proc/partitions")).splitlines():
		c = rand.split()
		if len(c) != 4 or not c[2].isdigit():
			continue
		if re.match(r"^sd[a-z]+$", c[3]):
			discuri.append(c[3])
		elif PARTITIE_SCOASA.match("/dev/" + c[3]):
			partitii_[c[3]] = int(c[2]) * 1024
	return sorted(discuri), partitii_


def semnDiscuri(radacina=None):
	"""Ce discuri sunt puse acum: lista se reface cand se schimba."""
	return tuple(discuriScoase(radacina)[0])


def nucleuValid(cale, marime_partitie):
	"""Antetul uImage al nucleului: magia, CRC-ul antetului, marimea care incape in partitie."""
	antet = _citeste(cale, 64)
	if not antet or len(antet) < 64:
		return False
	magie, hcrc, _t, marime = struct.unpack(">IIII", antet[:16])
	if magie != UIMAGE_MAGIC or marime <= 0:
		return False
	if zlib.crc32(antet[:4] + b"\0\0\0\0" + antet[8:]) & 0xffffffff != hcrc:
		return False
	return marime_partitie is None or marime + 64 <= marime_partitie


# Dovada suportului UUID in nucleul unui loc (nu in cel pornit acum). Initramfs-ul de pornire multipla din OE-Alliance
# (/init: resolve_root_device pentru root=UUID=, apoi mark_new_multiboot cu `touch /dev/.newMB-uuid`) sta in nucleu:
# uImage -> zImage -> Image comprimat gzip -> in Image arhiva cpio newc (comprimata gzip sau nu). Masurat pe kernel.bin
# Amiko Viper 4K al nostru (0.7.3): Image 14,6 MB, initramfs gzip de 3,6 MB cu 596 de fisiere. Acelasi semn il crede
# deja codul pentru nucleul pornit acum, iar managerul altei imagini scrie sloturile UUID numai dupa el. Semnul se cauta
# NUMAI in fisierul init al unei arhive cpio, fluxurile trebuie sa fie intregi (gzip cu CRC bun), iar orice eroare
# inseamna „nedovedit”. Alt fel de comprimare (xz, lzo, lz4) ramane nedovedit: locul se arata, dar nu se alege.
PARTITIE_NUCLEU = re.compile(r"^/dev/mmcblk0p[1-9][0-9]*$")
SEMN_UUID = b"/dev/.newMB-uuid"
NUCLEU_MAXIM = 32 * 1024 * 1024
DECOMPRIMAT_MAXIM = 64 * 1024 * 1024
INCERCARI_GZIP = 64
INCERCARI_CPIO = 256
INTRARI_CPIO = 100000
_nucleeUuid = {}   # (cale, hcrc, dcrc, marime) -> True/False; alegerea reverifica fara sa mai decomprime


def _gzipuri(buf, maxim=DECOMPRIMAT_MAXIM, incercari=INCERCARI_GZIP):
	"""Fluxurile gzip intregi din `buf` (fiecare cel mult `maxim` octeti decomprimat), in ordine. Un inceput fals sau un
	flux taiat (fara sfarsit sau cu CRC gresit) se sare."""
	vedere = memoryview(buf)
	i, n = 0, 0
	while n < incercari:
		i = buf.find(b"\x1f\x8b\x08", i)
		if i < 0:
			return
		n += 1
		d = zlib.decompressobj(16 + zlib.MAX_WBITS)
		try:
			iesire = d.decompress(vedere[i:], maxim)
		except zlib.error:
			iesire = None
		if iesire is not None and d.eof:
			yield iesire
			i = len(buf) - len(d.unused_data)
		else:
			i += 3


def _initCuSemn(buf):
	"""Exista in `buf` o arhiva cpio newc al carei fisier init (obisnuit) contine SEMN_UUID?"""
	i, n = 0, 0
	while n < INCERCARI_CPIO:
		i = buf.find(b"070701", i)
		if i < 0:
			return False
		n += 1
		j = i
		for _k in range(INTRARI_CPIO):
			antet = buf[j:j + 110]
			if len(antet) < 110 or antet[:6] != b"070701" or not re.fullmatch(rb"[0-9A-Fa-f]{104}", antet[6:]):
				break
			mod, marime, nume_lung = int(antet[14:22], 16), int(antet[54:62], 16), int(antet[94:102], 16)
			if nume_lung < 1 or j + 110 + nume_lung > len(buf):
				break
			nume = buf[j + 110:j + 110 + nume_lung - 1]
			inceput = (j + 110 + nume_lung + 3) & ~3
			if inceput + marime > len(buf):
				break
			if nume == b"TRAILER!!!":
				break
			if nume.lstrip(b"./") == b"init" and mod & 0o170000 == 0o100000 and SEMN_UUID in buf[inceput:inceput + marime]:
				return True
			j = (inceput + marime + 3) & ~3
		i += 6
	return False


def _initramfsCuSemn(continut):
	"""Continutul unui uImage (fara antet): Image necomprimat, zImage cu Image gzip, initramfs gzip sau necomprimat."""
	if _initCuSemn(continut):
		return True
	for imagine in _gzipuri(continut):
		if _initCuSemn(imagine):
			return True
		for arhiva in _gzipuri(imagine):
			if _initCuSemn(arhiva):
				return True
	return False


def nucleuCuUuid(cale, marime_partitie):
	"""Nucleul uImage din `cale` (antet si CRC-ul datelor bune, cat incape in partitie) are initramfs-ul de pornire
	multipla care rezolva root=UUID= si pune /dev/.newMB-uuid. Rezultatul se tine minte dupa antet (CRC-urile si
	marimea), deci a doua intrebare (alegerea, pe firul enigma2) citeste numai cei 64 de octeti ai antetului."""
	if not marime_partitie or not nucleuValid(cale, marime_partitie):
		return False
	antet = _citeste(cale, 64)
	_magie, hcrc, _t, marime, _inc, _intr, dcrc = struct.unpack(">7I", antet[:28])
	if marime > NUCLEU_MAXIM:
		return False
	cheie = (cale, hcrc, dcrc, marime)
	if cheie in _nucleeUuid:
		return _nucleeUuid[cheie]
	date = _citeste(cale, 64 + marime)
	if not date or len(date) != 64 + marime:
		return False
	rez = False
	continut = date[64:]   # o singura copie (7-8 MB pe receptor)
	del date
	if zlib.crc32(continut) & 0xffffffff == dcrc:
		try:
			rez = _initramfsCuSemn(continut)
		except (MemoryError, ValueError, zlib.error) as e:
			_log("nucleul %s: %r" % (cale, e))
	_nucleeUuid[cheie] = rez
	_log("nucleul %s: suportul UUID %s" % (cale, "dovedit (initramfs cu /dev/.newMB-uuid)" if rez else "nedovedit"))
	return rez


def radacinaValida(dosar):
	return os.path.lexists(os.path.join(dosar, "sbin", "init"))


def _cheiValori(text):
	d = {}
	for rand in text.splitlines():
		k, semn, v = rand.partition("=")
		if semn and k.strip() not in d:
			d[k.strip()] = v.strip()
	return d


def _versiuneOpkg(dosar, versiune_imagine=""):
	# Status-ul arata pachetele instalate; fisierele control pot fi ramase vechi.
	text = _text(os.path.join(dosar, "var", "lib", "opkg", "status"), 8 * 1024 * 1024)
	pachete = {}
	for strofa in re.split(r"\r?\n\s*\r?\n", text):
		campuri = {}
		for rand in strofa.splitlines():
			k, semn, v = rand.partition(":")
			if semn and not rand.startswith((" ", "\t")):
				campuri[k.lower()] = v.strip()
		nume = campuri.get("package", "")
		stare = campuri.get("status", "").split()
		if nume not in ("enigma2-hdsatelit", "enigma2") or "installed" not in stare:
			continue
		v = campuri.get("version", "").split(":")[-1]
		m = re.fullmatch(r"([0-9]{1,3}(?:\.[0-9]{1,3}){2,3})(?:[+-].*)?", v)
		if m:
			pachete[nume] = m.group(1)
	# Pachetul generic poate avea versiunea interfetei, diferita de a imaginii.
	return pachete.get("enigma2-hdsatelit") or versiune_imagine or pachete.get("enigma2", "")


def numeImagine(dosar):
	"""Numele si versiunea imaginii dintr-o radacina (etc/image-version, etc/issue): "HD Satelit 0.6.18"."""
	iv = _cheiValori(_text(os.path.join(dosar, "etc", "image-version")))
	info = _cheiValori(_text(os.path.join(dosar, "usr", "lib", "enigma.info")))
	info.update(_cheiValori(_text(os.path.join(dosar, "usr", "lib", "enigma.conf"))))
	info = {k: v.strip("\"'") for k, v in info.items()}
	nume = (info.get("displaydistro") or info.get("distro") or
		iv.get("imagename") or iv.get("distro") or iv.get("creator") or "")
	versiune = info.get("imgversion") or iv.get("imageversion", "")
	if info.get("imgrevision"):
		versiune = "%s.%s" % (versiune, info["imgrevision"])
	if "".join(nume.lower().split()) == "hdsatelit":
		try:
			from Components.HdsJurnalVersiuni import versiune_din_build
		except ImportError:
			from HdsJurnalVersiuni import versiune_din_build
		# Pachetele si image-version se schimba la actualizare; metadatele bazei nu.
		versiune_fisier = versiune_din_build(iv.get("version", ""))
		for cheie in ("imageversion", "version"):
			v = iv.get(cheie, "")
			if not versiune_fisier and re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", v):
				versiune_fisier = v
		nume = "HD Satelit"
		versiune = _versiuneOpkg(dosar, versiune_fisier) or _cheiValori(
			_text(os.path.join(dosar, "etc", "hdsatelit-model"))).get("version", "") or versiune
	if not versiune and re.match(r"^\d+(\.\d+)+$", iv.get("version", "")):
		versiune = iv["version"]
	if not nume:
		rand = _text(os.path.join(dosar, "etc", "issue"), 4096).strip().splitlines()
		nume = re.sub(r"\\[a-zA-Z]|%[a-z]", "", rand[0] if rand else "").strip()
	nume = re.sub(r"[^\w .,:()+-]", "", nume, flags=re.UNICODE).strip()[:40]
	if versiune and versiune not in nume:
		nume = "%s %s" % (nume, versiune[:20])
	return nume.strip() or _(FARA_NUME)


def _partitieNume(nume, radacina=None):
	"""Partitia interna cu numele GPT cerut. Un nume repetat nu se foloseste."""
	gasite = []
	dosar = _cale(radacina, "sys/class/block")
	try:
		partitii_ = os.listdir(dosar)
	except OSError:
		partitii_ = []
	for part in partitii_:
		if re.fullmatch(r"mmcblk0p[1-9][0-9]*", part) and _cheiValori(
			_text(os.path.join(dosar, part, "uevent"))).get("PARTNAME") == nume:
			gasite.append("/dev/" + part)
	if not gasite and not radacina:
		try:
			date = subprocess.check_output(["blkid", "-c", "/dev/null", "-t",
				"PARTLABEL=" + nume, "-o", "device"], stderr=subprocess.DEVNULL, timeout=5)
			gasite = [dev for dev in date.decode("ascii").split()
				if re.fullmatch(r"/dev/mmcblk0p[1-9][0-9]*", dev)]
		except (OSError, ValueError, subprocess.SubprocessError):
			pass
	return gasite[0] if len(gasite) == 1 else ""


def _dispozitivBoot(radacina=None):
	dev, _m = dispozitivPartitie(parametri(linieComanda(radacina)).get("blkdevparts", ""), "bootoptions")
	if dev:
		return dev
	if os.path.exists(_cale(radacina, "dev/block/by-name/bootoptions")):
		return "/dev/block/by-name/bootoptions"
	return _partitieNume("boot", radacina)


def _marimePartitie(dispozitiv, radacina=None):
	"""Marimea in octeti a partitiei /dev/<nume> din /proc/partitions, sau None."""
	for rand in _text(_cale(radacina, "proc/partitions")).splitlines():
		c = rand.split()
		if len(c) == 4 and c[3] == dispozitiv[5:] and c[2].isdigit():
			return int(c[2]) * 1024
	return None


def _gptSubdosare(radacina=None):
	"""Schema GigaBlue UHD Quad 4K Pro: fara blkdevparts in linia de comanda, cu partitiile GPT boot, linuxkernel1 si
	userdata (nucleele in linuxkernelK, sistemele in userdata/linuxrootfsK)."""
	if parametri(linieComanda(radacina)).get("blkdevparts"):
		return False
	return bool(_partitieNume("boot", radacina) and _partitieNume("linuxkernel1", radacina) and
		_partitieNume("userdata", radacina))


def verificaGptSubdosar(st, cmd, radacina=None):
	"""Locul K al schemei GigaBlue UHD Quad 4K Pro (boot.bin din initrd_gbquad4kpro_20260508r0 al producatorului, si
	linia de comanda a unui Quad 4K Pro real): `boot emmcflash0.linuxkernelK: 'root=/dev/mmcblk0p13
	rootsubdir=linuxrootfsK kernel=/dev/mmcblk0p<K+3> rootwait rw ...'`, cu „:” dupa tinta si fara blkdevparts. Nucleul
	si radacina se verifica dupa numele GPT (linuxkernelK, userdata), nu dupa numere. -> (K, nucleu, marime, radacina,
	subdosar) sau None."""
	if not st or st.get("repetate"):
		return None
	p = st["p"]
	if p.get("blkdevparts") or cmd.get("blkdevparts"):
		return None
	m = TINTA_GPT_SUBDOSAR.fullmatch(st["tinta"])
	if not m or p.get("rootfstype", "ext4") != "ext4":
		return None
	k = m.group(1)
	if p.get("rootsubdir") != "linuxrootfs" + k:
		return None
	nucleu, rad = _partitieNume("linuxkernel" + k, radacina), _partitieNume("userdata", radacina)
	if not nucleu or not rad or p.get("kernel") != nucleu or p.get("root") != rad:
		return None
	marime = _marimePartitie(nucleu, radacina)
	return (k, nucleu, marime, rad, p["rootsubdir"]) if marime else None


def _verificaNativ(st, cmd, radacina=None):
	"""Schema bootoptions existenta, kernelN/rootfsN numite in GPT sau linuxkernelK cu userdata/linuxrootfsK numite in
	GPT (GigaBlue UHD Quad 4K Pro)."""
	emmc = verificaEmmc(st, cmd)
	if emmc:
		return emmc
	gpt = verificaGptSubdosar(st, cmd, radacina)
	if gpt:
		return gpt
	if not st or st.get("repetate") or st["p"].get("rootsubdir"):
		return None
	m = re.fullmatch(r"emmcflash0\.kernel([1-9][0-9]*):?", st["tinta"])
	if not m or st["p"].get("rootfstype", "ext4") != "ext4":
		return None
	n = m.group(1)
	nucleu, rad = _partitieNume("kernel" + n, radacina), _partitieNume("rootfs" + n, radacina)
	if not nucleu or not rad or st["p"].get("root") != rad or st["p"].get("kernel", nucleu) != nucleu:
		return None
	marime = _marimePartitie(nucleu, radacina)
	return (n, nucleu, marime, rad, "") if marime else None


def dosarBoot(radacina=None):
	"""Punctul de montare al partitiei bootoptions din /proc/mounts (vfat, rw), cu radacina; None cand nu e montata."""
	dev = _dispozitivBoot(radacina)
	if not dev:
		return None
	tinta = os.path.realpath(_cale(radacina, dev))
	for rand in _text(_cale(radacina, "proc/mounts")).splitlines():
		c = rand.split()
		if len(c) < 4 or c[2] != "vfat" or "rw" not in c[3].split(","):
			continue
		if c[0] == dev or os.path.realpath(_cale(radacina, c[0])) == tinta:
			return _cale(radacina, c[1])
	return None


def _monteazaReal(dispozitiv, fel, optiuni=None):
	"""Montare intr-un dosar din /tmp -> (dosar, demonteaza) sau (None, None). Fara optiuni, montarea simpla (o a doua
	montare a lui p16 cu -o ro da EBUSY pe nucleul 4.4, cand p16 e deja montat)."""
	import tempfile
	d = tempfile.mkdtemp(prefix="hds-pornire-", dir="/tmp")
	cerere = ["mount", "-t", fel] + (["-o", optiuni] if optiuni else []) + [dispozitiv, d]
	try:
		cod = subprocess.call(cerere, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
	except OSError:
		cod = -1
	if cod != 0:
		os.rmdir(d)
		return None, None

	def demonteaza():
		subprocess.call(["umount", d], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
		try:
			os.rmdir(d)
		except OSError:
			pass
	return d, demonteaza


def _deschideBoot(radacina, monteaza):
	"""(dosarul bootoptions, demonteaza sau None); (None, None) cand nu se poate dovedi."""
	d = dosarBoot(radacina) or _dosarKexec(radacina)
	if d:
		return d, None
	if radacina:
		return None, None
	dev = _dispozitivBoot()
	if not dev:
		return None, None
	return (monteaza or _monteazaReal)(dev, "vfat")


def startupuri(dosar):
	"""[(N, octetii)] pentru STARTUP_<cifre>, in ordinea numerelor."""
	rez = []
	try:
		nume = os.listdir(dosar)
	except OSError:
		return rez
	for n in nume:
		if n.upper().startswith("STARTUP_") and n[8:].isdigit():
			date = _citeste(os.path.join(dosar, n), MAXIM_STARTUP + 1)
			if date is not None:
				rez.append((n[8:], n, date))
	rez.sort(key=lambda x: int(x[0]))
	return rez


# ------------------------------------------------------------------ lista locurilor

def _montate(radacina):
	"""{dispozitiv: dosarul} din /proc/mounts, cu radacina."""
	rez = {}
	sub = parametri(linieComanda(radacina)).get("rootsubdir", "") not in ("", "linuxrootfs0")
	for rand in _text(_cale(radacina, "proc/mounts")).splitlines():
		c = rand.split()
		if len(c) < 4 or c[2] != "ext4" or (c[1] == "/" and sub):
			continue
		if c[0] not in rez:
			rez[c[0]] = _cale(radacina, c[1].replace("\\040", " "))
	return rez


def _dispozitiveMontate(radacina):
	"""Toate dispozitivele din /proc/mounts, si cel al radacinii / cand ea e numai un subdosar al partitiei."""
	return set(rand.split()[0] for rand in _text(_cale(radacina, "proc/mounts")).splitlines() if rand.split())


def _deschideDisc(dispozitiv, montate, radacina, monteaza, oriunde=()):
	"""Dosarul unei partitii de pe card sau stick: de unde a montat-o sistemul sau montata acum numai pentru citit ->
	(dosar, demonteaza sau None); (None, None) cand nu se poate monta. O partitie deja montata altundeva (de exemplu
	radacina / a imaginii pornite de pe USB, care e doar subdosarul ei) se monteaza simplu, fara optiuni: o a doua
	montare ro a unei partitii montate rw da EBUSY pe nucleele 4.x."""
	if dispozitiv in montate:
		return montate[dispozitiv], None
	optiuni = None if dispozitiv in oriunde else OPTIUNI_CITIRE
	return (monteaza or _monteazaReal)(_cale(radacina, dispozitiv) if radacina else dispozitiv, "ext4", optiuni)


def _rand(n, nume_fisier, date, imagine, acum=False, alegere=False, strica=False, motiv=""):
	return {"loc": n, "fel": "stick", "imagine": imagine, "acum": acum, "alegere": alegere, "strica": strica, "motiv": motiv,
		"fisier": nume_fisier, "date": date}


def _locDisc(n, nume_fisier, date, st, cmd, discuri, partitii_, montate, radacina, monteaza, oriunde=None):
	"""Randul unui loc care nu e din memorie (card, stick sau o forma necunoscuta); None cand locul e gol sau discul lui nu
	e pus (STARTUP_5 si STARTUP_6 ale fabricii stau pe orice receptor, si fara disc)."""
	p = st["p"] if st else {}
	ref = p.get("root", "")
	dev = _radacinaDisc(ref, radacina)
	curent = cmd.get("root", "")
	aceeasi = bool(ref) and (ref == curent or bool(dev) and dev == _radacinaDisc(curent, radacina))
	if (st and not st.get("repetate") and aceeasi and
		p.get("kernel") == cmd.get("kernel") and
		p.get("rootsubdir") == cmd.get("rootsubdir")):
		return _rand(n, nume_fisier, date, numeImagine(_cale(radacina, "/")), acum=True)
	# Numai cele doua sabloane goale ale fabricii pot lipsi fara explicatie.
	sablon = {"5": ("usb0.sda1", "/dev/sda2"), "6": ("usb0.sda3", "/dev/sda4")}.get(n)
	fabrica = (st and sablon == (st["tinta"], ref) and "rootsubdir" not in p and
		bool(verificaDisc(st, cmd, radacina)))
	if not dev or dev[5:] not in partitii_:
		return None if fabrica else _rand(n, nume_fisier, date, _(FARA_NUME), motiv=MOTIV_PARTITIE)
	sub = p.get("rootsubdir", "")
	if sub and not SUBDOSAR_DISC.fullmatch(sub):
		return _rand(n, nume_fisier, date, _(FARA_NUME), motiv=MOTIV_FORMA)
	if oriunde is None:
		oriunde = _dispozitiveMontate(radacina)
	dosar, demonteaza = _deschideDisc(dev, montate, radacina, monteaza, oriunde)
	if not dosar:
		return _rand(n, nume_fisier, date, _(FARA_NUME), motiv=MOTIV_CITIRE)
	try:
		sistem = os.path.join(dosar, sub) if sub else dosar
		# Subdosarul nu trebuie sa iasa din partitia montata printr-o legatura.
		baza, real = os.path.realpath(dosar), os.path.realpath(sistem)
		if real != baza and not real.startswith(baza + os.sep):
			return _rand(n, nume_fisier, date, _(FARA_NUME), motiv=MOTIV_FORMA)
		# Intai numai forma: un loc gol cu forma stiuta nu se arata, chiar daca suportul UUID al nucleului lui nu e inca
		# dovedit (din slotul 3 al lui Wlad, locurile goale 19..28 apareau ca „Imagine fara nume”).
		forma = verificaDisc(st, cmd, radacina, cuUuid=False)
		if forma and forma[1] != dev:
			return _rand(n, nume_fisier, date, _(FARA_NUME), motiv=MOTIV_PARTITIE)
		if not os.path.isdir(os.path.join(sistem, "etc")):
			return None if forma else _rand(n, nume_fisier, date, _(FARA_NUME), motiv=MOTIV_FORMA)
		imagine = numeImagine(sistem)
		if forma and not _uuidDovedit(st, cmd, radacina):
			forma = None
		if not forma:
			motiv = MOTIV_UUID if st and not _uuidDovedit(st, cmd, radacina) else MOTIV_FORMA
			return _rand(n, nume_fisier, date, imagine, motiv=motiv)
		nucleu, _rad = forma
		marime = partitii_.get(nucleu[5:])
		if nucleu.startswith("/dev/mmcblk0p"):
			_m, marime = dispozitivPartitie(p["blkdevparts"], st["tinta"].split(".")[1])
		bun = radacinaValida(sistem) and nucleuValid(_cale(radacina, nucleu), marime)
		if not nucleu.startswith("/dev/mmcblk0p") and nucleu[5:] not in partitii_:
			bun = False
		# UUID nu depinde de ordinea discurilor. Numele sd* da, ca la forma veche.
		unul = bool(UUID_DISC.fullmatch(ref)) or discuri == ["sda"] and dev.startswith("/dev/sda")
		rand = _rand(n, nume_fisier, date, imagine, alegere=bool(bun and unul), strica=not bun,
			motiv=MOTIV_DISCURI if bun and not unul else "")
		rand["radacina"] = dev
		return rand
	finally:
		if demonteaza:
			demonteaza()


def _inPartitie(baza, cale):
	"""`cale` ramane in partitia montata la `baza` si dupa legaturi (fara .. si fara legaturi spre afara)."""
	baza, real = os.path.realpath(baza), os.path.realpath(cale)
	return real == baza or real.startswith(baza.rstrip(os.sep) + os.sep)


def _locKexec(n, fisier, date, cmd, montate, radacina, monteaza, oriunde=None):
	"""Randul unui loc kexec: din memorie, Recovery (locul 0, radacina flash) sau de pe USB/HDD (<model>/linuxrootfsN)."""
	st = citesteStartup(date)
	pereche = _parametriKexec(st, radacina)
	if not pereche:
		return None
	dev, sub = pereche
	if not any(len(c) == 4 and c[3] == dev[5:]
		for c in (rand.split() for rand in _text(_cale(radacina, "proc/partitions")).splitlines())):
		return None
	if oriunde is None:
		oriunde = _dispozitiveMontate(radacina)
	dosar, demonteaza = _deschideDisc(dev, montate, radacina, monteaza, oriunde)
	if not dosar:
		return _rand(n, fisier, date, _(FARA_NUME), motiv=MOTIV_CITIRE)
	try:
		sistem = os.path.join(dosar, sub) if sub else dosar
		nucleu = os.path.join(dosar, _nucleuRelativ(st))
		# Un dosar de imagine sau un nucleu nu pot iesi din partitia citita printr-o legatura.
		if (os.path.islink(sistem) or not _inPartitie(dosar, sistem) or not _inPartitie(dosar, nucleu) or
			not os.path.isdir(os.path.join(sistem, "etc"))):
			return None
		acum = _acumKexec(st, cmd, radacina)
		bun = radacinaValida(sistem) and _nucleuKexec(nucleu)
		extern = not dev.startswith("/dev/mmcblk0p")
		# UUID= si PARTUUID= le cauta initramfs-ul kexec cu blkid, in ambele etape: ordinea discurilor nu conteaza. Un
		# nume /dev/sdXN scris direct depinde de ea, deci se alege numai cu un singur disc, chiar sda.
		stabil = bool(UUID_DISC.fullmatch(st["p"]["root"]) or PARTUUID_DISC.fullmatch(st["p"]["root"]))
		sigur = not extern or stabil or (dev.startswith("/dev/sda") and semnDiscuri(radacina) == ("sda",))
		return {"loc": n, "fel": "kexec", "imagine": numeImagine(sistem), "acum": acum,
			"alegere": bool(bun and sigur and not acum), "strica": not bun,
			"motiv": MOTIV_DISCURI if bun and not sigur else "", "extern": extern,
			"fisier": fisier, "date": date, "radacina": dev}
	finally:
		if demonteaza:
			demonteaza()


def locuri(radacina=None, monteaza=None, numai=None):
	"""{"locuri": [...], "pe_stick": bool, "eroare": bool}. Fiecare loc: loc, imagine, acum, alegere (se poate scrie),
	fel (emmc / stick, adica orice nu e din memorie), strica, motiv (de ce nu se alege). Locurile goale (fara radacina) nu
	apar. `numai`: numai locul acela (alegerea il verifica din nou)."""
	dual = _dual(radacina)
	if dual:
		return _locuriFlag(dual, radacina, monteaza, numai)
	cmd = parametri(linieComanda(radacina))
	rez = {"locuri": [], "pe_stick": False, "eroare": False}
	pe_stick = bool(_radacinaDisc(cmd.get("root", ""), radacina))
	boot, demonteazaBoot = _deschideBoot(radacina, monteaza)
	if not boot:
		rez["eroare"] = True
		return rez
	kexec = boot == _dosarKexec(radacina)
	try:
		# Recovery (locul 0) numai la kexec: acolo e o imagine in radacina flash; la bootoptions e meniul fabricii.
		fisiere = _sabloane(boot) if kexec else startupuri(boot)
		o_data = kexec and os.path.lexists(os.path.join(boot, O_DATA))
	finally:
		if demonteazaBoot:
			demonteazaBoot()
	if numai is not None:
		fisiere = [x for x in fisiere if x[0] == str(numai)]
	if kexec:
		montate = _montate(radacina)
		oriunde = _dispozitiveMontate(radacina)
		for n, fisier, date in fisiere:
			try:
				loc = _locKexec(n, fisier, date, cmd, montate, radacina, monteaza, oriunde)
			except (IOError, OSError) as e:
				_log("locul %s: %r" % (n, e))
				rez["eroare"] = True
				continue
			if loc:
				rez["locuri"].append(loc)
		rez["pe_stick"] = any(l.get("extern") and l["acum"] for l in rez["locuri"])
		# STARTUP_ONCE (pus de alta imagine) are intaietate la pornirea urmatoare; nu e al nostru, deci il spunem doar.
		rez["o_data"] = o_data
		return rez
	emmc, altele = [], []
	for n, nume_fisier, date in fisiere:
		st = citesteStartup(date)
		e = _verificaNativ(st, cmd, radacina)
		if e:
			emmc.append((n, nume_fisier, date, e))
		elif date.strip() and (not date.startswith(b"boot emmcflash0.") or
			re.search(rb"\broot=(?:/dev/(?:sd|mmcblk[1-9])|UUID=|PARTUUID=)", date)):
			altele.append((n, nume_fisier, date, st))
	rez["pe_stick"] = pe_stick
	montate = _montate(radacina)
	if altele:
		discuri, partitii_ = discuriScoase(radacina)
		oriunde = _dispozitiveMontate(radacina)
		for n, nume_fisier, date, st in altele:
			try:
				l = _locDisc(n, nume_fisier, date, st, cmd, discuri, partitii_, montate, radacina, monteaza, oriunde)
			except (IOError, OSError) as e:
				_log("locul %s: %r" % (n, e))
				l = _rand(n, nume_fisier, date, _(FARA_NUME), motiv=MOTIV_CITIRE)
			if l:
				rez["locuri"].append(l)
	_locuriEmmc(rez, emmc, cmd, montate, radacina, monteaza)
	rez["locuri"].sort(key=lambda l: int(l["loc"]))
	if pe_stick and numai is None and not any(l["acum"] for l in rez["locuri"]):
		rez["locuri"].insert(0, {"loc": "", "fel": "stick", "imagine": numeImagine(_cale(radacina, "/")),
			"acum": True, "alegere": False, "fara_loc": True})
	return rez


def _locuriEmmc(rez, emmc, cmd, montate, radacina, monteaza):
	"""Locurile din memorie. Cu imaginea de acum pe card sau stick, partitia userdata nu e montata de sistem: se monteaza
	numai pentru citit. Cu imaginea de acum in memorie, montarea simpla dintotdeauna (a doua montare a aceleiasi partitii)."""
	if not emmc:
		return
	montari = {}
	try:
		for n, nume_fisier, date, (k, nucleu, marime, rad, sub) in emmc:
			if rad not in montari:
				dispozitiv = _cale(radacina, rad) if radacina else rad
				if rad in montate or rad == cmd.get("root"):
					montari[rad] = (monteaza or _monteazaReal)(dispozitiv, "ext4")
				else:
					montari[rad] = (monteaza or _monteazaReal)(dispozitiv, "ext4", OPTIUNI_CITIRE)
			dosar_rad = montari[rad][0]
			if not dosar_rad:
				rez["eroare"] = True
				continue
			sistem = os.path.join(dosar_rad, sub)
			if not os.path.isdir(os.path.join(sistem, "etc")):
				continue  # loc gol
			acum = (cmd.get("root") == rad and cmd.get("rootsubdir", "") == sub and
				(cmd.get("kernel") == nucleu or not sub and not cmd.get("kernel")))
			# zImage: kernelN/rootfsN fara subdosar si schema GPT fara blkdevparts (Quad 4K Pro, linuxrootfsK); cu
			# blkdevparts (SF8008 si inruditele) numai uImage, ca pana acum
			bun = radacinaValida(sistem) and (nucleuValid(_cale(radacina, nucleu), marime) or (
				(not sub or not cmd.get("blkdevparts")) and _nucleuKexec(_cale(radacina, nucleu), marime)))
			rez["locuri"].append({"loc": n, "fel": "emmc", "imagine": numeImagine(sistem), "acum": acum,
				"alegere": bool(bun and not acum), "strica": not bun, "fisier": nume_fisier, "date": date})
	finally:
		for d, demonteaza in montari.values():
			if demonteaza:
				demonteaza()


def randuri(stare):
	"""Textele randurilor, in ordinea locurilor."""
	rez = []
	for l in stare.get("locuri", []):
		d = {"loc": l["loc"], "imagine": l["imagine"]}
		if l.get("fara_loc"):
			rez.append(_(RAND_STICK) % d)
		elif l["fel"] == "stick" or l.get("extern"):
			# Locurile kexec de pe USB sau HDD au aceleasi texte (deja traduse) ca locurile de pe card sau stick.
			if l["acum"]:
				rez.append(_(RAND_DISC_ACUM) % d)
			elif l.get("strica"):
				rez.append(_(RAND_DISC_STRICAT) % d)
			elif l.get("motiv"):
				d["motiv"] = _(l["motiv"])
				rez.append(_(RAND_DISC_REFUZ) % d)
			else:
				rez.append(_(RAND_DISC) % d)
		elif l["acum"]:
			rez.append(_(RAND_ACUM) % d)
		elif l.get("strica"):
			rez.append(_(RAND_STRICAT) % d)
		else:
			rez.append(_(RAND) % d)
	return rez


def maiMulteDiscuri(stare):
	"""Un loc nu se alege pentru ca sunt mai multe discuri puse: lista merita refacuta cand se schimba discurile."""
	return any(l.get("motiv") == MOTIV_DISCURI for l in stare.get("locuri", []))


def nota(stare):
	"""Textul de sub lista."""
	lista = stare.get("locuri", [])
	if any(l["alegere"] for l in lista):
		text = [_(NOTA_DISC if any((l["fel"] == "stick" or l.get("extern")) and
			not l.get("fara_loc") for l in lista) else NOTA)]
	elif any(l.get("motiv") for l in lista):
		text = []
	else:
		text = [_(NICIUNA)]
	if maiMulteDiscuri(stare):
		text.append(_(NOTA_DISCURI))
	if any(l.get("fara_loc") for l in lista):
		text.append(_(PE_STICK))
	if stare.get("o_data"):
		text.append(_(NOTA_O_DATA))
	return " ".join(text)


def textRefuz(l):
	"""De ce nu se alege locul `l`: textul de pe ecran, la OK, si din web."""
	if l.get("motiv") == MOTIV_DISCURI:
		return _(REFUZ_DISCURI)
	if l.get("motiv") == MOTIV_FORMA:
		return _(REFUZ_FORMA) % l["loc"]
	if l.get("motiv"):
		return _(REFUZ_MOTIV) % {"loc": l["loc"], "motiv": _(l["motiv"])}
	return _(REFUZ) % l["loc"]


def publice(stare):
	"""Starea fara octetii fisierelor, pentru web."""
	return {"pe_stick": stare.get("pe_stick", False), "eroare": stare.get("eroare", False),
		"mai_multe_discuri": maiMulteDiscuri(stare),
		"locuri": [{"loc": l["loc"], "imagine": l["imagine"], "acum": l["acum"], "alegere": l["alegere"],
			"fel": l["fel"], "strica": bool(l.get("strica")),
			"refuz": "" if l["acum"] or l["alegere"] or not (l.get("strica") or l.get("motiv")) else textRefuz(l)}
			for l in stare.get("locuri", [])],
		"randuri": randuri(stare), "nota": nota(stare)}


# ------------------------------------------------------------------ scrierea

def _scrieAtomic(dosar, nume, date):
	"""nume.hds-nou (sau NOU pentru STARTUP), fsync, rename peste `nume`, sync; apoi citit inapoi. True daca e la fel."""
	temp = os.path.join(dosar, NOU if nume == FISIER_STARTUP else nume + ".nou")
	tinta = os.path.join(dosar, nume)
	with open(temp, "wb") as f:
		f.write(date)
		f.flush()
		os.fsync(f.fileno())
	os.replace(temp, tinta)   # rename(2) pe receptor; pe vfat intrarea STARTUP ramane aceeasi
	try:
		fd = os.open(dosar, os.O_RDONLY)
		try:
			os.fsync(fd)
		finally:
			os.close(fd)
	except OSError:
		pass
	if hasattr(os, "sync"):
		os.sync()
	try:
		fd = os.open(tinta, os.O_RDONLY)
		try:
			os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
		finally:
			os.close(fd)
	except (AttributeError, OSError):
		pass
	return _citeste(tinta, MAXIM_STARTUP + 1) == date


def _restaureazaStartup(boot, vechi):
	if vechi != ABSENT:
		return _scrieAtomic(boot, FISIER_STARTUP, vechi)
	try:
		os.unlink(os.path.join(boot, FISIER_STARTUP))
	except FileNotFoundError:
		pass
	if hasattr(os, "sync"):
		os.sync()
	return not os.path.exists(os.path.join(boot, FISIER_STARTUP))


# ------------------------------------------------------------------ Qviart DUAL 4K: partitia flag

def _dual(radacina=None):
	"""(linia de comanda, dispozitivul partitiei flag) pe Qviart DUAL 4K: MACHINEBUILD=dual si OEM=dags in linia de
	comanda, iar in blkdevparts flag (1 MiB), linuxkernel1-4 si rootfs. None pe orice alt receptor."""
	cmd = parametri(linieComanda(radacina))
	if cmd.get("MACHINEBUILD") != "dual" or cmd.get("OEM") != "dags":
		return None
	blk = cmd.get("blkdevparts", "")
	dev, marime = dispozitivPartitie(blk, FLAG_PARTITIE)
	if not dev or marime != FLAG_MARIME or not dispozitivPartitie(blk, "rootfs")[0]:
		return None
	if not all(dispozitivPartitie(blk, "linuxkernel%d" % k)[0] for k in FLAG_LOCURI):
		return None
	return cmd, dev


def _flagSigur(dev, radacina=None):
	"""Calea de scris a partitiei flag, numai daca e chiar ea: /dev/mmcblk0pN, in /proc/partitions cu 1 MiB,
	/dev/block/by-name/flag (cand exista) duce la ea si e un dispozitiv bloc (pe receptorul fals al probelor: un fisier
	obisnuit). None altfel."""
	if not re.fullmatch(r"/dev/mmcblk0p[1-9][0-9]*", dev or ""):
		return None
	if not any(len(c) == 4 and c[3] == dev[5:] and c[2] == str(FLAG_MARIME // 1024)
		for c in (rand.split() for rand in _text(_cale(radacina, "proc/partitions")).splitlines())):
		return None
	cale = _cale(radacina, dev)
	legatura = _cale(radacina, FLAG_LEGATURA)
	if os.path.lexists(legatura) and os.path.realpath(legatura) != os.path.realpath(cale):
		return None
	try:
		mod = os.stat(cale).st_mode
	except OSError:
		return None
	bun = stat.S_ISREG(mod) if radacina else stat.S_ISBLK(mod)
	return cale if bun else None


def _citesteFlag(cale):
	"""Primul octet al partitiei flag (0-255) sau None."""
	d = _citeste(cale, 1)
	return d[0] if d and len(d) == 1 else None


def _scrieFlag(cale, valoare):
	"""Un singur octet la inceputul partitiei: fara O_CREAT (o cale gresita nu devine fisier nou) si fara O_TRUNC; fsync,
	apoi citit inapoi. True daca e la fel."""
	if isinstance(valoare, bool) or not isinstance(valoare, int) or not 0 <= valoare <= 255:
		return False
	fd = os.open(cale, os.O_WRONLY | getattr(os, "O_BINARY", 0))
	try:
		if os.lseek(fd, 0, os.SEEK_SET) != 0 or os.write(fd, bytes((valoare,))) != 1:
			return False
		os.fsync(fd)
	finally:
		os.close(fd)
	try:
		fd = os.open(cale, os.O_RDONLY)
		try:
			os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
		finally:
			os.close(fd)
	except (AttributeError, OSError):
		pass
	return _citesteFlag(cale) == valoare


def _locuriFlag(dual, radacina=None, monteaza=None, numai=None):
	"""Locurile DUAL 4K din blkdevparts: 1-4 in rootfs/linuxrootfsK (ca locurile SF8008), apoi Android (locul 0) cand
	partitia boot are un nucleu uImage valid. Fara fisierele STARTUP."""
	cmd = dual[0]
	blk = cmd["blkdevparts"]
	rad, _m = dispozitivPartitie(blk, "rootfs")
	rez = {"locuri": [], "pe_stick": False, "eroare": False}
	emmc = []
	for k in FLAG_LOCURI:
		if numai is not None and str(numai) != str(k):
			continue
		nucleu, marime = dispozitivPartitie(blk, "linuxkernel%d" % k)
		emmc.append((str(k), FLAG_PARTITIE, b"flag=%d\n" % k, (str(k), nucleu, marime, rad, "linuxrootfs%d" % k)))
	_locuriEmmc(rez, emmc, cmd, _montate(radacina), radacina, monteaza)
	for l in rez["locuri"]:
		l["fel"] = "flag"
	if numai is None or str(numai) == str(LOC_ANDROID):
		nucleu, marime = dispozitivPartitie(blk, "boot")
		if nucleu and dispozitivPartitie(blk, "system")[0] and nucleuValid(_cale(radacina, nucleu), marime):
			rez["locuri"].append({"loc": str(LOC_ANDROID), "fel": "flag", "imagine": ANDROID, "acum": False,
				"alegere": True, "strica": False, "fisier": FLAG_PARTITIE, "date": b"flag=0\n"})
	rez["locuri"].sort(key=lambda l: int(l["loc"]))
	return rez


def _alegeFlag(l, radacina=None):
	"""Scrie numarul locului (0-4) in primul octet al partitiei flag. (True, imaginea) sau (False, motivul)."""
	dual = _dual(radacina)
	loc = str(l.get("loc", ""))
	valoare = int(loc) if loc.isdigit() and len(loc) == 1 else -1
	if not dual or not (valoare == LOC_ANDROID or valoare in FLAG_LOCURI):
		return False, _(EROARE)
	cale = _flagSigur(dual[1], radacina)
	if not cale:
		return False, _(EROARE)
	vechi = None
	try:
		vechi = _citesteFlag(cale)
		if vechi is None:
			return False, _(EROARE)
		if not _scrieFlag(cale, valoare):
			_scrieFlag(cale, vechi)
			return False, _(EROARE)
	except (IOError, OSError) as e:
		_log("flag: %r" % e)
		if vechi is not None:
			try:
				_scrieFlag(cale, vechi)
			except (IOError, OSError):
				pass
		return False, _(EROARE)
	del _flagVechi[:]
	_flagVechi.append((dual[1], vechi))
	_log("flag = %d (%s), inainte %d" % (valoare, l["imagine"], vechi))
	return True, l["imagine"]


def _inapoiFlag(radacina=None):
	"""Octetul flag de dinainte de ultima alegere, pus la loc. True daca s-a pus."""
	dual = _dual(radacina)
	if not dual or not _flagVechi or _flagVechi[0][0] != dual[1]:
		return False
	cale = _flagSigur(dual[1], radacina)
	if not cale:
		return False
	try:
		ok = _scrieFlag(cale, _flagVechi[0][1])
	except (IOError, OSError) as e:
		_log("flag inapoi: %r" % e)
		return False
	if ok:
		del _flagVechi[:]
	_log("flag pus inapoi: %s" % ok)
	return ok


def alege(loc, radacina=None, monteaza=None, asteptat=None):
	"""Scrie STARTUP din STARTUP_<loc> dupa o verificare din nou a locului. (True, imaginea) sau (False, motivul)."""
	stare = locuri(radacina, monteaza, numai=loc)
	gasit = [l for l in stare["locuri"] if l["loc"] == str(loc)]
	if not gasit:
		return False, _(NEGASIT)
	l = gasit[0]
	if asteptat is not None and (l.get("date"), l["imagine"]) != asteptat:
		return False, _(NEGASIT)
	if l["acum"]:
		return False, _(DEJA)
	if not l["alegere"]:
		return False, textRefuz(l)
	if l["fel"] == "flag":
		return _alegeFlag(l, radacina)
	boot, demonteaza = _deschideBoot(radacina, monteaza)
	if not boot:
		return False, _(EROARE)
	try:
		date = _citeste(os.path.join(boot, l["fisier"]), MAXIM_STARTUP + 1)
		st, cmd = citesteStartup(date), parametri(linieComanda(radacina))
		if date != l["date"]:
			return False, _(EROARE)
		if l["fel"] == "emmc":
			if not _verificaNativ(st, cmd, radacina):
				return False, _(EROARE)
		elif l["fel"] == "kexec":
			nou = _locKexec(str(loc), l["fisier"], date, cmd,
				_montate(radacina), radacina, monteaza)
			if (not nou or not nou["alegere"] or nou.get("radacina") != l.get("radacina") or
				nou["imagine"] != l["imagine"]):
				return False, textRefuz(nou) if nou else _(NEGASIT)
		elif not verificaDisc(st, cmd, radacina):
			return False, _(EROARE)
		elif (not UUID_DISC.fullmatch(st["p"].get("root", "")) and
			semnDiscuri(radacina) != ("sda",)):
			return False, _(REFUZ_DISCURI)
		if l["fel"] == "stick":
			# Discul poate fi scos sau UUID-ul poate indica alt suport intre citire
			# si alegere. Recitim si sistemul, nu doar forma STARTUP.
			discuri, part = discuriScoase(radacina)
			nou = _locDisc(str(loc), l["fisier"], date, st, cmd, discuri, part,
				_montate(radacina), radacina, monteaza)
			if not nou or not nou["alegere"]:
				return False, textRefuz(nou) if nou else _(NEGASIT)
			if nou.get("radacina") != l.get("radacina") or nou["imagine"] != l["imagine"]:
				return False, _(EROARE)
		vechi = _citeste(os.path.join(boot, FISIER_STARTUP), MAXIM_STARTUP + 1)
		vechi = ABSENT if vechi is None else vechi
		if not _scrieAtomic(boot, COPIE, vechi):
			return False, _(EROARE)
		if not _scrieAtomic(boot, FISIER_STARTUP, date):
			_restaureazaStartup(boot, vechi)
			return False, _(EROARE)
		_log("STARTUP = %s (%s)" % (l["fisier"], l["imagine"]))
		return True, l["imagine"]
	except (IOError, OSError) as e:
		_log("scrierea: %r" % e)
		return False, _(EROARE)
	finally:
		if demonteaza:
			demonteaza()


def inapoi(radacina=None, monteaza=None):
	"""STARTUP inapoi din STARTUP.hds-inainte (repornirea a fost oprita pe ecran). True daca s-a pus la loc.
	Pe DUAL 4K: octetul flag de dinainte de alegere."""
	if _dual(radacina):
		return _inapoiFlag(radacina)
	boot, demonteaza = _deschideBoot(radacina, monteaza)
	if not boot:
		return False
	try:
		vechi = _citeste(os.path.join(boot, COPIE), MAXIM_STARTUP + 1)
		if vechi is None or vechi != ABSENT and not citesteStartup(vechi):
			return False
		ok = _restaureazaStartup(boot, vechi)
		_log("STARTUP pus inapoi: %s" % ok)
		return ok
	except (IOError, OSError) as e:
		_log("inapoi: %r" % e)
		return False
	finally:
		if demonteaza:
			demonteaza()


def reporneste(sesiune, loc, dupa_ms=0, fabrica_ceas=None, radacina=None, monteaza=None, Standby=None, asteptat=None):
	"""Scrie alegerea, apoi TryQuitMainloop(2) pe receptor (dupa `dupa_ms`). Daca omul spune Nu la intrebarea de pe
	ecran (o inregistrare, o lucrare), fereastra se inchide cu apel inapoi si STARTUP se pune la loc; la Da enigma2 iese
	si apelul nu mai vine. (True, imaginea) sau (False, motivul)."""
	if sesiune is None:
		return False, _(EROARE)
	ok, text = alege(loc, radacina, monteaza) if asteptat is None else alege(loc, radacina, monteaza, asteptat=asteptat)
	if not ok:
		return ok, text

	def renuntat(*_a):
		inapoi(radacina, monteaza)

	def acum():
		try:
			S = Standby
			if S is None:
				from Screens import Standby as S
			sesiune.openWithCallback(renuntat, S.TryQuitMainloop, 2)
		except Exception as e:
			_log("repornirea: %r" % e)
			inapoi(radacina, monteaza)

	if dupa_ms <= 0:
		acum()
	else:
		from Components import HdsAlimentare
		HdsAlimentare.programeaza(acum, dupa_ms, fabrica_ceas, nume="pornire-multipla")
	return True, text
