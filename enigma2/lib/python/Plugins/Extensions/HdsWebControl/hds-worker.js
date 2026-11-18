/* SPDX-License-Identifier: GPL-2.0-only
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 *
 * hds-worker.js: firul de lucru al playerului wasm din "TV in browser" (hds-player.js il porneste). Citeste fluxul TS
 * al transmisiei (fetch pe /api/tv-flux, cu antetele paginii), il desface in JS (PAT, PMT, PES), da imaginea MPEG-2 /
 * MPEG-1 si sunetul MP2 / MP3 / AC-3 decodorului wasm (tv-wasm/hdsdec.js + hdsdec.wasm: libavcodec din FFmpeg 8.1.3,
 * LGPL-2.1-or-later) si trimite paginii cadrele gata decodate.
 * H.264 SI AAC: numai cand decodorul le are (construit cu HDS_DEC_EXTRA=h264,aac). Dupa incarcare workerul incearca
 * dec_open("h264") si dec_open("aac") (cuDecodoare): imaginea H.264 merge atunci si aici, pentru navigatoarele fara H.264
 * in MediaSource (Opera sau Chromium pe Linux), iar sunetul AAC ADTS (0x0F) intra in alegere dupa MP2 / MP3. Fara ele,
 * ca inainte: la H.264 {tip: "eroare", fel: "format", video: "h264"}.
 *
 * Timpul: PTS-urile (33 de biti, 90 kHz) se desfac intr-un timp continuu (Cronologie): trecerea peste 2^33 (la ~26,5 h)
 * nu se vede, iar un salt mare (alt flux, emisiune lipita de alta, flux reluat) incepe o "epoca" noua; cadrele poarta
 * epoca, iar pagina se resincronizeaza la fiecare epoca noua. Decodoarele o iau de la capat la un salt (dec_reset).
 * Fila ascunsa: pagina trimite {cmd: "vizibil", da: false}; imaginea se decodeaza mai departe (referintele raman bune),
 * dar nu se mai copiaza si nu se mai trimite; sunetul merge. Oprirea: fetch-ul se intrerupe pe loc (AbortController),
 * decodoarele se inchid, apoi {tip: "oprit"}.
 *
 * IMAGINEA TINUTA NEDECODATA (15.11.2026, H.264 1080i pe playerul wasm): intr-un flux DVB imaginea vine cu 1-2 s
 * inaintea sunetului (cat tine tamponul decodorului), deci un cadru decodat ar astepta atat in coada paginii; la 1080
 * un cadru are ~3 MB, iar coada paginii (48 MB) arunca cadrele: 38 de cadre aratate din 371. Acum PES-urile imaginii
 * asteapta aici, NEDECODATE (zeci de KB), si se decodeaza numai cat in drum spre pagina si in coada ei sunt mai putin de
 * ~24 MB de cadre (limitaCadre: 7 la 1080, 38 la 576), SAU cand ora PES-ului a venit dupa ceasul paginii (pagina care
 * deseneaza rar, de pilda o fereastra acoperita, nu lasa imaginea in urma sunetului). Pagina spune cat a primit, cat
 * are in coada, ceasul si epoca ({cmd: "coada"}), de cateva ori pe secunda; fara raport de 2 s (pagina veche, fila
 * ascunsa) sau cu peste 12 MB tinuti aici, imaginea se decodeaza pe loc, ca inainte. PES-urile unei epoci pe care
 * pagina a lasat-o in urma se arunca. Sunetul nu asteapta niciodata.
 *
 * Mesaje primite: {cmd: "start", url, antete, versiune, sunet, program}; {cmd: "vizibil", da}; {cmd: "stop"};
 * {cmd: "coada", primite, n, ceas, epoca} (cadrele de imagine primite de pagina pana acum, cate asteapta in coada ei,
 * PTS-ul aratat acum sau null, epoca paginii).
 * Mesaje trimise: {tip: "gata"}, {tip: "info"}, {tip: "v"} (un cadru), {tip: "a"} (sunet), {tip: "stat"},
 * {tip: "eroare", fel: "http"|"retea"|"sfarsit"|"decodor"|"format", cod, text}, {tip: "oprit"}.
 * In node (probele de pe PC) fisierul exporta Demux, Cronologie si celelalte bucati fara decodor.
 */
"use strict";

var TS = 188;
var DOI_LA_33 = 8589934592;            // 2^33
var DOI_LA_32 = 4294967296;            // 2^32
var SALT_MAX = 90000 * 5;              // peste 5 s intre doua marci de timp = discontinuitate
var SALT_SEMNALAT = 90000;             // dupa discontinuity_indicator: peste 1 s
var PES_MAX = 4 * 1024 * 1024;         // un PES mai mare e stricat (fara sfarsit): se arunca

var VIDEO_TIP = {0x01: "mpeg1video", 0x02: "mpeg2video", 0x1B: "h264", 0x24: "hevc"};
var VIDEO_WASM = {mpeg1video: true, mpeg2video: true};     // h264 se adauga cand decodorul il are (cuDecodoare)

// ---------------------------------------------------------------- timpul

function dif33(a, b) {
	var d = a - b;
	if (d > DOI_LA_32) d -= DOI_LA_33;
	else if (d < -DOI_LA_32) d += DOI_LA_33;
	return d;
}

function Cronologie() {
	this.epoca = 0;
	this.ref = null;          // {brut, ext}: cea mai noua marca de timp a epocii (orice flux)
	this.vechi = null;        // referinta epocii de dinainte: un PES intarziat din ea se arunca
	this.salturi = 0;
	this.semnalat = false;    // discontinuity_indicator vazut: urmatorul salt de peste 1 s e discontinuitate
}

// brut: PTS-ul de 33 de biti -> {ext: timpul continuu, epoca, intarziat: true daca PES-ul e din epoca de dinainte}
Cronologie.prototype.desface = function (brut) {
	if (this.ref === null) {
		this.ref = {brut: brut, ext: brut};
		return {ext: brut, epoca: this.epoca, intarziat: false};
	}
	var d = dif33(brut, this.ref.brut);
	var prag = this.semnalat ? SALT_SEMNALAT : SALT_MAX;
	if (Math.abs(d) <= prag) {
		var ext = this.ref.ext + d;
		if (d > 0) this.ref = {brut: brut, ext: ext};
		if (d > 0 || Math.abs(d) <= SALT_SEMNALAT) this.semnalat = false;
		return {ext: ext, epoca: this.epoca, intarziat: false};
	}
	if (this.vechi !== null && Math.abs(dif33(brut, this.vechi.brut)) <= SALT_MAX) {
		return {ext: -1, epoca: this.epoca - 1, intarziat: true};
	}
	this.vechi = this.ref;
	this.epoca++;
	this.salturi++;
	this.semnalat = false;
	// timpul continuu merge mai departe de unde era: pagina se resincronizeaza oricum la epoca noua
	var nou = this.ref.ext + 3600;
	this.ref = {brut: brut, ext: nou};
	return {ext: nou, epoca: this.epoca, intarziat: false};
};

// alt canal in acelasi flux (Demux.uita): epoca noua chiar daca marcile lui de timp sunt aproape de ale celui vechi; un
// PES intarziat al canalului vechi nu mai are unde ajunge (fluxurile lui nu se mai citesc)
Cronologie.prototype.nouaEpoca = function () {
	if (this.ref === null) return;
	this.epoca++;
	this.salturi++;
	this.semnalat = false;
	this.vechi = null;
	this.ref = null;
};

// ---------------------------------------------------------------- CRC-ul sectiunilor PSI

var TABEL_CRC = (function () {
	var t = new Uint32Array(256);
	for (var i = 0; i < 256; i++) {
		var c = i << 24;
		for (var k = 0; k < 8; k++) c = (c & 0x80000000) ? ((c << 1) ^ 0x04C11DB7) : (c << 1);
		t[i] = c >>> 0;
	}
	return t;
})();

function crc32Mpeg(b) {
	var crc = 0xFFFFFFFF;
	for (var i = 0; i < b.length; i++) crc = ((crc << 8) ^ TABEL_CRC[((crc >>> 24) ^ b[i]) & 0xFF]) >>> 0;
	return crc >>> 0;
}

// ---------------------------------------------------------------- demuxul TS

// fel = "mp2" (MPEG-1/2 Layer II sau III, se afla din antet), "ac3", sau un fel pe care decodorul imaginii nu il are
function felAudio(tip, descriptori) {
	if (tip === 0x03 || tip === 0x04) return "mpa";
	if (tip === 0x81) return "ac3";
	if (tip === 0x0F) return "aac";
	if (tip === 0x11) return "latm";
	if (tip === 0x87) return "eac3";
	if (tip === 0x06) {
		for (var k = 0; k + 2 <= descriptori.length; k += 2 + descriptori[k + 1]) {
			var e = descriptori[k];
			if (e === 0x6A) return "ac3";
			if (e === 0x7A) return "eac3";
			if (e === 0x05 && descriptori[k + 1] >= 4 && k + 6 <= descriptori.length) {
				var r = String.fromCharCode(descriptori[k + 2], descriptori[k + 3], descriptori[k + 4], descriptori[k + 5]);
				if (r === "AC-3") return "ac3";
				if (r === "EAC3") return "eac3";
			}
		}
	}
	return null;
}

var AUDIO_DECODABIL = {mpa: true, ac3: true};              // aac se adauga cand decodorul il are (cuDecodoare)
var ORDINE_AUDIO = ["mpa", "aac", "ac3"];                    // alegerea pistei: MP2 / MP3, AAC ADTS, AC-3

// ce mai are decodorul in afara de MPEG-2 / MP2 / MP3 / AC-3 (numele din libavcodec): imaginea H.264 si sunetul AAC
function cuDecodoare(nume) {
	for (var i = 0; i < (nume || []).length; i++) {
		if (nume[i] === "h264") VIDEO_WASM.h264 = true;
		if (nume[i] === "aac") AUDIO_DECODABIL.aac = true;
	}
}

// optiuni: {program: sid sau 0 (primul cu imagine sau sunet), sunet: true|false, pista: PID-ul audio dorit sau 0}
// asculta: {pmt(alegere), pes(pid, date, pts, discontinuu), salt(), uitat(alegere)}
// ALT CANAL IN ACELASI FLUX (proba din 14.10, ProSieben <-> RTL Television): la inceputul fluxului unui canal nou pot
// trece inca PAT-ul transponderului vechi si PMT-ul canalului vechi. Programul cerut (sid-ul canalului, din pagina) se
// alege dupa PID-ul pe care il da PAT-ul pentru el; cat PAT-ul nu-l are, se ia primul program, ca inainte. Un PAT nou
// in care programul ales nu mai e pe PID-ul lui (sau in care programul cerut e pe alt PID) uita alegerea: urmatorul
// PMT o face din nou, cu decodoare noi (uitat).
function Demux(optiuni, asculta) {
	this.o = optiuni || {};
	this.a = asculta || {};
	this.rest = null;
	this.patProg = null;          // numarul programului -> PID-ul PMT-ului lui, din PAT
	this.pmtPids = null;          // PID -> numarul programului, din PAT
	this.pmtStrans = {};          // PID -> {date: [], lung}: sectiunea PMT care trece de un pachet
	this.pmtSemn = null;          // CRC-ul PMT-ului ales acum (o schimbare = alegere noua)
	this.alegere = null;          // {video: {pid, fel}, audio: {pid, fel}, fluxuri: [...]}
	this.pes = {};                // PID -> {parti, lung, asteptat, stricat}
	this.cc = {};                 // PID -> ultimul contor de continuitate
	this.st = {pachete: 0, sincron_pierdut: 0, erori_cc: 0, pes: 0, pes_aruncate: 0, pmt: 0, pmt_crc_gresit: 0};
}

Demux.prototype.impinge = function (b) {
	if (this.rest) {
		var t = new Uint8Array(this.rest.length + b.length);
		t.set(this.rest);
		t.set(b, this.rest.length);
		b = t;
		this.rest = null;
	}
	var i = 0, n = b.length;
	while (i + TS <= n) {
		if (b[i] !== 0x47) {
			// sincronul pierdut: urmatorul loc cu 0x47 si inca unul la 188 octeti
			var j = i + 1;
			while (j + TS < n && !(b[j] === 0x47 && b[j + TS] === 0x47)) j++;
			this.st.sincron_pierdut++;
			if (j + TS >= n) { i = j; break; }
			i = j;
			continue;
		}
		this.pachet(b, i);
		i += TS;
	}
	if (i < n) this.rest = b.slice(i);
};

Demux.prototype.pachet = function (b, o) {
	this.st.pachete++;
	if (b[o + 1] & 0x80) return;                  // transport_error_indicator
	var pid = ((b[o + 1] & 0x1F) << 8) | b[o + 2];
	if (pid === 0x1FFF) return;
	var pusi = (b[o + 1] & 0x40) !== 0;
	var afc = (b[o + 3] >> 4) & 3;
	var cc = b[o + 3] & 0x0F;
	var p = o + 4;
	var discont = false;
	if (afc & 2) {
		var la = b[o + 4];
		if (la > 0 && (b[o + 5] & 0x80)) discont = true;
		p += 1 + la;
	}
	if (discont && this.pes[pid] && this.a.semnal) this.a.semnal(pid);
	if (!(afc & 1) || p >= o + TS) return;
	// contorul de continuitate, numai pe PID-urile citite (PAT, PMT, imaginea, sunetul)
	var urmarit = pid === 0 || (this.pmtPids && this.pmtPids[pid] !== undefined) || this.pes[pid];
	var stricat = false;
	if (urmarit) {
		var u = this.cc[pid];
		if (u !== undefined && !discont && cc !== ((u + 1) & 0x0F) && cc !== u) {
			this.st.erori_cc++;
			stricat = true;
		}
		this.cc[pid] = cc;
	}
	var sarcina = b.subarray(p, o + TS);
	if (pid === 0) { if (pusi) this.pat(sarcina); return; }
	if (this.pmtPids && this.pmtPids[pid] !== undefined) { this.strangePmt(pid, pusi, sarcina, stricat); return; }
	var s = this.pes[pid];
	if (!s) return;
	if (pusi) {
		if (stricat) s.stricat = true;      // pachetul lipsa era sfarsitul PES-ului de dinainte
		this.goleste(pid, s);
		s.parti = [sarcina];
		s.lung = sarcina.length;
		s.asteptat = sarcina.length >= 6 ? ((sarcina[4] << 8) | sarcina[5]) : 0;
		s.stricat = false;
	} else if (s.parti.length) {
		if (stricat) s.stricat = true;
		s.parti.push(sarcina);
		s.lung += sarcina.length;
		if (s.lung > PES_MAX) { s.parti = []; s.lung = 0; this.st.pes_aruncate++; return; }
	} else {
		return;
	}
	if (s.asteptat && s.lung >= s.asteptat + 6) this.goleste(pid, s);
};

function sectiuneDin(sarcina) {
	if (!sarcina.length) return null;
	var s = sarcina.subarray(1 + sarcina[0]);
	return s.length >= 3 ? s : null;
}

Demux.prototype.pat = function (sarcina) {
	var s = sectiuneDin(sarcina);
	if (!s || s[0] !== 0x00) return;
	var lung = ((s[1] & 0x0F) << 8) | s[2];
	if (s.length < 3 + lung || lung < 9) return;      // un PAT mai lung de un pachet nu se citeste (RescrierePsi lasa unul scurt)
	s = s.subarray(0, 3 + lung);
	if (crc32Mpeg(s) !== 0) return;
	var pids = {}, progs = {};
	for (var j = 8; j + 4 <= s.length - 4; j += 4) {
		var prog = (s[j] << 8) | s[j + 1];
		var pidPmt = ((s[j + 2] & 0x1F) << 8) | s[j + 3];
		if (prog) {
			pids[pidPmt] = prog;
			if (progs[prog] === undefined) progs[prog] = pidPmt;
		}
	}
	this.pmtPids = pids;
	this.patProg = progs;
	var a = this.alegere, dorit = this.pidDorit();
	if (a && (pids[a.pmtPid] === undefined || (dorit !== undefined && dorit !== a.pmtPid))) this.uita();
};

// PID-ul PMT-ului programului cerut, cand PAT-ul de acum il are (altfel undefined: primul program)
Demux.prototype.pidDorit = function () {
	return this.o.program && this.patProg ? this.patProg[this.o.program] : undefined;
};

// alegerea veche nu mai e a fluxului (alt canal): fluxurile ei nu se mai citesc, PMT-ul urmator alege din nou
Demux.prototype.uita = function () {
	var vechi = this.alegere;
	this.alegere = null;
	this.pmtSemn = null;
	this.pmtStrans = {};
	this.pes = {};
	this.st.uitari = (this.st.uitari || 0) + 1;
	if (this.a.uitat) this.a.uitat(vechi);
};

Demux.prototype.strangePmt = function (pid, pusi, sarcina, stricat) {
	var x = this.pmtStrans[pid];
	if (pusi) {
		var s = sectiuneDin(sarcina);
		if (!s) { delete this.pmtStrans[pid]; return; }
		x = this.pmtStrans[pid] = {date: [s], lung: s.length};
	} else if (x && !stricat) {
		x.date.push(sarcina);
		x.lung += sarcina.length;
	} else {
		delete this.pmtStrans[pid];
		return;
	}
	if (x.lung < 3) return;
	var tot = new Uint8Array(x.lung), o = 0;
	for (var i = 0; i < x.date.length; i++) { tot.set(x.date[i], o); o += x.date[i].length; }
	var lung = ((tot[1] & 0x0F) << 8) | tot[2];
	if (tot.length < 3 + lung) { x.date = [tot]; return; }
	delete this.pmtStrans[pid];
	this.pmt(pid, tot.subarray(0, 3 + lung));
};

Demux.prototype.pmt = function (pid, s) {
	if (s[0] !== 0x02 || s.length < 16) return;
	if (crc32Mpeg(s) !== 0) { this.st.pmt_crc_gresit++; return; }
	var program = (s[3] << 8) | s[4];
	// programul cerut, dupa PID-ul lui din PAT; pe acel PID trece si un PMT cu un numar de program pe care PAT-ul nu-l
	// are (fluxuri stricate), dar nu PMT-ul altui program din PAT (doua programe pe acelasi PID)
	var dorit = this.pidDorit();
	if (dorit !== undefined && (pid !== dorit || (program !== this.o.program && this.patProg[program] !== undefined))) return;
	var semn = (s[s.length - 4] << 24 | s[s.length - 3] << 16 | s[s.length - 2] << 8 | s[s.length - 1]) >>> 0;
	if (this.alegere && this.alegere.pmtPid === pid && semn === this.pmtSemn) return;
	if (this.alegere && this.alegere.pmtPid !== pid) return;     // alt program decat cel ales
	this.st.pmt++;
	var info = ((s[10] & 0x0F) << 8) | s[11];
	var j = 12 + info, fluxuri = [];
	while (j + 5 <= s.length - 4) {
		var tip = s[j], pidEs = ((s[j + 1] & 0x1F) << 8) | s[j + 2];
		var ld = ((s[j + 3] & 0x0F) << 8) | s[j + 4];
		var desc = s.subarray(j + 5, Math.min(j + 5 + ld, s.length - 4));
		var fel = VIDEO_TIP[tip] || felAudio(tip, desc);
		if (fel) fluxuri.push({tip: tip, pid: pidEs, fel: fel, video: !!VIDEO_TIP[tip], limba: limba(desc)});
		j += 5 + ld;
	}
	var video = null, audio = null, k;
	for (k = 0; k < fluxuri.length; k++) if (fluxuri[k].video) { video = fluxuri[k]; break; }
	var audioToate = fluxuri.filter(function (f) { return !f.video; });
	if (this.o.sunet !== false) {
		if (this.o.pista) audio = audioToate.filter(function (f) { return f.pid === this.o.pista && AUDIO_DECODABIL[f.fel]; }, this)[0] || null;
		var ordine = ORDINE_AUDIO.filter(function (f) { return AUDIO_DECODABIL[f]; });
		for (k = 0; !audio && k < ordine.length; k++) {
			audio = audioToate.filter(function (f) { return f.fel === ordine[k]; })[0] || null;
		}
	}
	if (!video && !audioToate.length) return;
	var vechi = this.alegere;
	this.pmtSemn = semn;
	this.alegere = {pmtPid: pid, program: program, video: video, audio: audio, fluxuri: fluxuri};
	// PES-urile fluxurilor care nu mai sunt alese se lasa; cele noi incep la urmatorul inceput de PES
	var noi = {};
	if (video) noi[video.pid] = this.pes[video.pid] || {parti: [], lung: 0, asteptat: 0, stricat: false};
	if (audio) noi[audio.pid] = this.pes[audio.pid] || {parti: [], lung: 0, asteptat: 0, stricat: false};
	this.pes = noi;
	if (this.a.pmt) this.a.pmt(this.alegere, vechi);
};

function limba(desc) {
	for (var k = 0; k + 2 <= desc.length; k += 2 + desc[k + 1]) {
		if (desc[k] === 0x0A && desc[k + 1] >= 3 && k + 5 <= desc.length) {
			var t = String.fromCharCode(desc[k + 2], desc[k + 3], desc[k + 4]).toLowerCase();
			return /^[a-z]{3}$/.test(t) ? t : "";
		}
	}
	return "";
}

// PTS-ul din antetul PES (33 de biti), sau -1
function ptsDin(d) {
	if (d.length < 14 || !(d[7] & 0x80)) return -1;
	return (d[9] & 0x0E) * 536870912 + d[10] * 4194304 + (d[11] & 0xFE) * 16384 + d[12] * 128 + (d[13] >> 1);
}

Demux.prototype.goleste = function (pid, s) {
	if (!s.parti.length) return;
	var d;
	if (s.parti.length === 1) d = s.parti[0];
	else {
		d = new Uint8Array(s.lung);
		var o = 0;
		for (var i = 0; i < s.parti.length; i++) { d.set(s.parti[i], o); o += s.parti[i].length; }
	}
	var stricat = s.stricat;
	s.parti = []; s.lung = 0; s.asteptat = 0; s.stricat = false;
	if (d.length < 9 || d[0] !== 0 || d[1] !== 0 || d[2] !== 1) { this.st.pes_aruncate++; return; }
	var inceput = 9 + d[8];
	if (inceput > d.length) { this.st.pes_aruncate++; return; }
	this.st.pes++;
	if (this.a.pes) this.a.pes(pid, d.subarray(inceput), ptsDin(d), stricat);
};

// stratul MPEG audio al primului cadru (2 = Layer II, 3 = Layer III, 1 = Layer I), sau 0 daca nu se gaseste
function stratMpegAudio(d) {
	for (var i = 0; i + 4 <= d.length; i++) {
		if (d[i] === 0xFF && (d[i + 1] & 0xE0) === 0xE0) {
			var strat = (d[i + 1] >> 1) & 3, rata = (d[i + 2] >> 2) & 3, debit = d[i + 2] >> 4;
			if (strat && rata !== 3 && debit !== 15) return 4 - strat;
		}
	}
	return 0;
}

// ---------------------------------------------------------------- legatura cu decodorul (numai in worker)

var M = null;                 // modulul wasm (HdsDec)
var oprit = false, vizibil = true, controler = null;
var ptrIn = 0, marimeIn = 0;
var cronologie = null, demux = null;
var DEC = {};                 // PID -> {d, tip: "v"|"a", nume, epoca}
var curent = null;            // decodorul in lucru (cadrele ies in timpul lui dec_push)
var ultimPtsV = -1, ultimPtsA = -1, durataV = 3600;
var st = null;
// imaginea tinuta nedecodata (sus): cadrele trimise, ultimul raport al paginii, PES-urile care asteapta
var OCTETI_DECODATE_MAX = 24 * 1024 * 1024;   // cadre decodate in drum spre pagina si in coada ei
var ASTEPTARE_OCTETI_MAX = 12 * 1024 * 1024;  // PES-uri de imagine tinute aici; peste, se decodeaza pe loc
var RAPORT_VECHI_MS = 2000;
var LA_TIMP = 9000;                           // un PES cu ora sub ceasul paginii + 100 ms se decodeaza oricum
var trimiseV = 0, raport = null, asteptare = [], asteptareOcteti = 0, octetiCadru = 0, ultimExtAsteptare = -1;

function inZbor() {
	return raport ? trimiseV - raport.primite + raport.n : 0;
}

// ceasul paginii acum (aceleasi unitati ca ext), dupa ultimul raport; null cand pagina inca nu are ceas
function ceasPagina() {
	if (!raport || raport.ceas === null || raport.ceas === undefined) return null;
	return raport.ceas + (performance.now() - raport.t) * 90;
}

// PES-ul de imagine e la rand: e loc in drum si in coada paginii, sau ora lui a venit (pagina care deseneaza rar, de
// pilda o fereastra acoperita: imaginea nu ramane in urma sunetului; coada paginii arunca atunci cadrele vechi)
function laRand(e) {
	if (inZbor() < limitaCadre()) return true;
	var c = ceasPagina();
	return c !== null && raport.epoca === e.epoca && e.ord >= 0 && e.ord <= c + LA_TIMP;
}

// cate cadre decodate pot fi in drum si in coada paginii; inaintea primului cadru (marimea nestiuta), ca la 1080
function limitaCadre() {
	return octetiCadru ? Math.max(4, Math.min(40, Math.floor(OCTETI_DECODATE_MAX / octetiCadru))) : 8;
}

function retine() {
	return raport !== null && vizibil && !oprit && performance.now() - raport.t < RAPORT_VECHI_MS &&
		asteptareOcteti < ASTEPTARE_OCTETI_MAX;
}

function golesteAsteptarea() {
	while (asteptare.length) {
		var e = asteptare[0];
		// din epoca de dinainte a paginii: cadrele ei nu se mai arata (decodorul o ia oricum de la capat la epoca noua)
		var vechi = raport !== null && e.epoca < raport.epoca;
		if (!vechi && retine() && !laRand(e)) break;
		asteptare.shift();
		asteptareOcteti -= e.date.length;
		if (!vechi) impinge(e.pid, "v", e.date, e.ext, e.epoca);
	}
}

function uitaAsteptarea() {
	asteptare = [];
	asteptareOcteti = 0;
	ultimExtAsteptare = -1;
}

function stareNoua() {
	return {incarcare_ms: 0, octeti: 0, pornit: 0, primul_cadru_ms: -1, erori: 0,
		v: {cadre: 0, ms: 0, max: 0, nevazute: 0}, a: {cadre: 0, ms: 0, esantioane: 0, pes_stricate: 0},
		salturi: 0, intarziate: 0, info: null};
}

function trimite(m, transfer) {
	if (transfer) self.postMessage(m, transfer); else self.postMessage(m);
}

function incarcaDecodorul(versiune) {
	if (M) return Promise.resolve();
	var t0 = performance.now();
	var v = versiune ? "?v=" + encodeURIComponent(versiune) : "";
	importScripts("/tv/tv-wasm/hdsdec.js" + v);
	return HdsDec({locateFile: function (f) { return "/tv/tv-wasm/" + f + v; }, onVideo: laVideo, onAudio: laAudio})
		.then(function (m) { M = m; cuDecodoare(decodoareInPlus()); st.incarcare_ms = performance.now() - t0; });
}

// decodoarele din afara celor de baza pe care hdsdec.wasm chiar le are (dec_open da 0 pentru cele lipsa)
function decodoareInPlus() {
	var are = [];
	["h264", "aac"].forEach(function (nume) {
		var d = M.ccall("dec_open", "number", ["string", "number"], [nume, 1]);
		if (d) { are.push(nume); M._dec_close(d); }
	});
	return are;
}

function deschide(nume, tip) {
	var d = M.ccall("dec_open", "number", ["string", "number"], [nume, 1]);
	if (!d) throw new Error("decodorul " + nume + " nu s-a deschis");
	return {d: d, tip: tip, nume: nume, epoca: cronologie.epoca};
}

function inchide(pid) {
	var x = DEC[pid];
	if (!x) return;
	st.erori += M._dec_erori(x.d);
	M._dec_close(x.d);
	delete DEC[pid];
}

function laPmt(alegere, vechi) {
	var info = {video: alegere.video ? alegere.video.fel : "", audio: "", fluxuri: alegere.fluxuri.map(function (f) {
		return {pid: f.pid, fel: f.fel, limba: f.limba, video: f.video};
	})};
	if (alegere.video && !VIDEO_WASM[alegere.video.fel]) {
		trimite({tip: "eroare", fel: "format", cod: 0, text: "imaginea e " + alegere.video.fel + ", decodorul nu o are",
			video: alegere.video.fel});
		oprit = true;
		return;
	}
	// imaginea: acelasi PID si acelasi fel raman (referintele decodorului), altfel decodor nou
	var pid;
	for (pid in DEC) {
		var x = DEC[pid], ramane = false;
		if (x.tip === "v" && alegere.video && +pid === alegere.video.pid && x.nume === alegere.video.fel) ramane = true;
		if (x.tip === "a" && alegere.audio && +pid === alegere.audio.pid && x.fel === alegere.audio.fel) ramane = true;
		if (!ramane) inchide(pid);
	}
	if (alegere.video && !DEC[alegere.video.pid]) DEC[alegere.video.pid] = deschide(alegere.video.fel, "v");
	if (alegere.audio) {
		info.audio = alegere.audio.fel === "mpa" ? "mp2" : alegere.audio.fel;
		info.pista = alegere.audio.pid;
	}
	st.info = info;
	trimite({tip: "info", info: info});
}

// alt canal in acelasi flux (Demux.uita): decodoarele canalului vechi se inchid, timpul incepe o epoca noua (pagina se
// resincronizeaza), iar PMT-ul canalului nou deschide altele
function laUitat() {
	for (var pid in DEC) inchide(pid);
	uitaAsteptarea();
	cronologie.nouaEpoca();
	st.salturi = cronologie.salturi;
	ultimPtsV = -1;
	ultimPtsA = -1;
}

function laPes(pid, date, pts, stricat) {
	var x = DEC[pid], tip = x ? x.tip : null;
	if (!x) {
		// sunetul MPEG se deschide la primul PES: Layer II (mp2float) sau Layer III (mp3float), dupa antetul cadrului
		var al = demux.alegere && demux.alegere.audio;
		if (!al || al.pid !== pid) return;
		var nume = al.fel === "ac3" ? "ac3" : (al.fel === "aac" && AUDIO_DECODABIL.aac ? "aac" : null);
		if (al.fel === "mpa") {
			var strat = stratMpegAudio(date);
			nume = strat === 2 ? "mp2float" : (strat === 3 ? "mp3float" : null);
			if (!strat) return;                    // inca nu s-a vazut un antet: urmatorul PES
			if (!nume) { al.fel = "mp1"; st.info.audio = "mp1"; trimite({tip: "info", info: st.info}); return; }
		}
		if (!nume) return;
		x = DEC[pid] = deschide(nume, "a");
		x.fel = al.fel;
		tip = "a";
	}
	if (tip === "a" && stricat) { st.a.pes_stricate++; return; }
	var ext = -1;
	if (pts >= 0) {
		var t = cronologie.desface(pts);
		if (t.intarziat) { st.intarziate++; return; }
		ext = t.ext;
		st.salturi = cronologie.salturi;
	}
	if (tip === "v" && (asteptare.length || (retine() && inZbor() >= limitaCadre()))) {
		// imaginea asteapta nedecodata (sus), in ordinea sosirii; timpul si epoca ei sunt cele de la sosire; ord = ora
		// pentru laRand (al doilea camp fara PTS merge odata cu primul)
		if (ext >= 0) ultimExtAsteptare = ext;
		asteptare.push({pid: pid, date: date, ext: ext, ord: ext >= 0 ? ext : ultimExtAsteptare, epoca: cronologie.epoca});
		asteptareOcteti += date.length;
		golesteAsteptarea();
		return;
	}
	impinge(pid, tip, date, ext, cronologie.epoca);
}

// un PES la decodorul lui (imaginea poate veni aici mai tarziu decat a sosit: epoca e cea de la sosire)
function impinge(pid, tip, date, ext, epoca) {
	var x = DEC[pid];
	if (!x) return;                              // decodorul s-a inchis intre timp (alt PMT, alt canal)
	if (x.epoca !== epoca) {
		// discontinuitate: decodorul o ia de la capat; cadrele vechi nu mai ies
		M._dec_reset(x.d);
		x.epoca = epoca;
		if (tip === "v") { ultimPtsV = -1; } else { ultimPtsA = -1; }
	}
	if (date.length > marimeIn) {
		if (ptrIn) M._free(ptrIn);
		marimeIn = Math.max(date.length, 1 << 20);
		ptrIn = M._malloc(marimeIn);
	}
	M.HEAPU8.set(date, ptrIn);
	var t0 = performance.now();
	curent = x;
	M._dec_push(x.d, ptrIn, date.length, ext);
	curent = null;
	var dt = performance.now() - t0;
	if (tip === "v") { st.v.ms += dt; if (dt > st.v.max) st.v.max = dt; } else st.a.ms += dt;
}

function laVideo(w, h, fmt, y, u, v, ly, lu, lv, pts, flags, sarN, sarD, matrice, gama, afd) {
	st.v.cadre++;
	if (st.primul_cadru_ms < 0) st.primul_cadru_ms = performance.now() - st.pornit;
	if (pts < 0 && ultimPtsV >= 0) pts = ultimPtsV + durataV;
	if (pts >= 0 && ultimPtsV >= 0 && pts > ultimPtsV && pts - ultimPtsV < 9000) durataV = pts - ultimPtsV;
	if (pts >= 0) ultimPtsV = pts;
	if (!vizibil) { st.v.nevazute++; return; }
	if (!fmt || (fmt & 0xFF) !== 8 || pts < 0) return;
	var sw = (fmt >> 8) & 0xF, sh = (fmt >> 12) & 0xF;
	var cw = (w + (1 << sw) - 1) >> sw, ch = (h + (1 << sh) - 1) >> sh;
	var buf = new Uint8Array(w * h + 2 * cw * ch);
	trimiseV++;
	octetiCadru = buf.length;
	var H = M.HEAPU8;
	copiaza(H, y, ly, buf, 0, w, h);
	copiaza(H, u, lu, buf, w * h, cw, ch);
	copiaza(H, v, lv, buf, w * h + cw * ch, cw, ch);
	trimite({tip: "v", w: w, h: h, cw: cw, ch: ch, buf: buf.buffer, pts: pts, durata: durataV, flags: flags,
		sar: sarN > 0 && sarD > 0 ? sarN / sarD : 0, matrice: matrice, gama: gama, afd: afd,
		epoca: curent ? curent.epoca : cronologie.epoca}, [buf.buffer]);
}

function copiaza(H, src, linie, dst, o, w, h) {
	if (linie === w) { dst.set(H.subarray(src, src + w * h), o); return; }
	for (var r = 0; r < h; r++) dst.set(H.subarray(src + r * linie, src + r * linie + w), o + r * w);
}

function laAudio(n, canale, rata, fmt, date, pts) {
	st.a.cadre++;
	st.a.esantioane += n;
	if (pts < 0 && ultimPtsA >= 0) pts = ultimPtsA + n * 90000 / rata;
	if (pts >= 0) ultimPtsA = pts;
	if (fmt !== 8 || pts < 0 || !canale) return;     // AV_SAMPLE_FMT_FLTP: mp2float, mp3float, ac3 si aac dau asa
	var U32 = M.HEAPU32, F32 = M.HEAPF32, can = [];
	for (var i = 0; i < canale; i++) {
		var p = U32[(date >> 2) + i] >> 2;
		can.push(F32.subarray(p, p + n));
	}
	var l = new Float32Array(n), r = new Float32Array(n);
	if (canale === 1) { l.set(can[0]); r.set(can[0]); }
	else if (canale === 2) { l.set(can[0]); r.set(can[1]); }
	else {
		// mai mult de doua canale (AC-3 fara downmix in decodor): FL FR FC LFE SL SR, coeficientii ITU-R BS.775
		var k = 0.7071, c = can[2] || null, sl = can[4] || null, sr = can[5] || null;
		for (var j = 0; j < n; j++) {
			var cj = c ? c[j] * k : 0;
			l[j] = (can[0][j] + cj + (sl ? sl[j] * k : 0)) * 0.5858;
			r[j] = (can[1][j] + cj + (sr ? sr[j] * k : 0)) * 0.5858;
		}
	}
	trimite({tip: "a", rata: rata, l: l.buffer, r: r.buffer, pts: pts, n: n,
		epoca: curent ? curent.epoca : cronologie.epoca}, [l.buffer, r.buffer]);
}

function trimiteStat() {
	var erori = st.erori;
	for (var pid in DEC) erori += M._dec_erori(DEC[pid].d);
	var s = JSON.parse(JSON.stringify(st));
	s.erori = erori;
	s.demux = demux ? demux.st : null;
	s.asteptare = {pes: asteptare.length, octeti: asteptareOcteti, in_zbor: inZbor(), limita: limitaCadre()};
	trimite({tip: "stat", st: s, timp_ms: performance.now() - st.pornit});
}

function curata() {
	uitaAsteptarea();
	for (var pid in DEC) inchide(pid);
	if (ptrIn && M) { M._free(ptrIn); ptrIn = 0; marimeIn = 0; }
}

function porneste(m) {
	st = stareNoua();
	oprit = false;
	trimiseV = 0;
	raport = null;
	octetiCadru = 0;
	uitaAsteptarea();
	cronologie = new Cronologie();
	var incarcare;
	try { incarcare = incarcaDecodorul(m.versiune); } catch (e) { incarcare = Promise.reject(e); }
	return incarcare.then(function () {
		trimite({tip: "gata", incarcare_ms: st.incarcare_ms});
		if (oprit) return;
		demux = new Demux({program: m.program || 0, sunet: m.sunet !== false, pista: 0},
			{pmt: laPmt, pes: laPes, semnal: function () { cronologie.semnalat = true; }, uitat: laUitat});
		st.pornit = performance.now();
		controler = typeof AbortController === "function" ? new AbortController() : null;
		return fetch(m.url, {headers: m.antete || {}, cache: "no-store", credentials: "same-origin",
			signal: controler ? controler.signal : undefined});
	}, function (e) {
		trimite({tip: "eroare", fel: "decodor", cod: 0, text: String(e && e.message || e)});
		return null;
	}).then(function (r) {
		if (!r) return;
		if (!r.ok) { trimite({tip: "eroare", fel: "http", cod: r.status, text: "HTTP " + r.status}); return; }
		if (!r.body || !r.body.getReader) { trimite({tip: "eroare", fel: "decodor", cod: 0, text: "fara ReadableStream"}); return; }
		var cititor = r.body.getReader(), ultimaStat = performance.now();
		var bucla = function () {
			return cititor.read().then(function (x) {
				if (oprit) { try { cititor.cancel(); } catch (e) {} return; }
				if (x.done) { trimiteStat(); trimite({tip: "eroare", fel: "sfarsit", cod: 0, text: "fluxul s-a terminat"}); return; }
				st.octeti += x.value.length;
				try {
					demux.impinge(x.value);
				} catch (e) {
					trimite({tip: "eroare", fel: "decodor", cod: 0, text: String(e && e.message || e)});
					oprit = true;
					try { cititor.cancel(); } catch (e2) {}
					return;
				}
				if (performance.now() - ultimaStat > 1000) { trimiteStat(); ultimaStat = performance.now(); }
				if (oprit) { try { cititor.cancel(); } catch (e3) {} return; }
				return bucla();
			});
		};
		return bucla();
	}).catch(function (e) {
		if (oprit) return;
		trimite({tip: "eroare", fel: "retea", cod: 0, text: String(e && e.message || e)});
	});
}

if (typeof importScripts === "function" && typeof self !== "undefined") {
	self.onmessage = function (e) {
		var m = e.data || {};
		if (m.cmd === "start") {
			porneste(m);
		} else if (m.cmd === "vizibil") {
			vizibil = !!m.da;
			if (M) golesteAsteptarea();      // fila ascunsa: imaginea se decodeaza pe loc (referintele raman bune)
		} else if (m.cmd === "coada") {
			raport = {primite: +m.primite || 0, n: +m.n || 0, t: performance.now(),
				ceas: typeof m.ceas === "number" ? m.ceas : null, epoca: +m.epoca || 0};
			if (M && !oprit) golesteAsteptarea();
		} else if (m.cmd === "stop") {
			oprit = true;
			if (controler) { try { controler.abort(); } catch (e2) {} }
			if (M) curata();
			trimite({tip: "oprit"});
		}
	};
}

if (typeof module === "object" && module.exports) {
	module.exports = {Demux: Demux, Cronologie: Cronologie, dif33: dif33, crc32Mpeg: crc32Mpeg, ptsDin: ptsDin,
		stratMpegAudio: stratMpegAudio, felAudio: felAudio, SALT_MAX: SALT_MAX, cuDecodoare: cuDecodoare,
		VIDEO_WASM: VIDEO_WASM, AUDIO_DECODABIL: AUDIO_DECODABIL};
}
