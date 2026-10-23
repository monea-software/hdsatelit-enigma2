/* SPDX-License-Identifier: GPL-2.0-only
 * Copyright (C) 2026 moneasoftware.com (Monea Eduard) & hdsatelit.com (HD Satelit)
 *
 * hds-sunet.js: sunetul AC-3 al canalelor cu imagine H.264 / HEVC in "TV in browser", pentru browserele care nu il
 * redau singure (Chrome, Edge, Firefox). Imaginea ramane la mpegts.js si la decodorul browserului (MediaSource); aici
 * numai sunetul: mpegts.js (pe firul paginii, enableWorker: false) da fiecare PES AC-3 convertorului din
 * config.hdsSunetAc3, convertorul il decodeaza cu decodorul wasm al imaginii (tv-wasm/hdsdec.js + hdsdec.wasm:
 * libavcodec din FFmpeg 8.1.3, LGPL-2.1-or-later, decodorul "ac3" cu downmix stereo; acelasi decodor ca la canalele
 * MPEG-2) si scrie sunetul ca FLAC (RFC 9639: cadre cu bloc fix, stereo, 16 biti, subcadre VERBATIM sau CONSTANT),
 * pe care MediaSource il ia ca audio/mp4; codecs="flac" langa imagine. Marcile de timp (PTS) raman ale cadrelor AC-3,
 * deci MediaSource tine singur imaginea si sunetul impreuna. Receptorul trimite fluxul la fel (fara recodare).
 *
 * Decodorul se incarca la primul PES AC-3 (o singura data pe pagina); pana atunci PES-urile asteapta in coada, iar
 * mpegts.js nu trimite nici imaginea cat nu are segmentul de initializare al sunetului. Daca decodorul nu se poate
 * incarca, convertorul cheama laEsec(eroare) si nu mai da nimic (pagina porneste din nou fara AC-3, iar receptorul
 * spune atunci ca sunetul nu se aude).
 * Un gol de timp de cel mult GOL_MAX_S (pachete pierdute) se umple cu cadre de liniste, ca MediaSource sa nu repete
 * ultimul cadru; un salt mai mare (alt flux) incepe un timp nou, iar decodorul o ia de la capat.
 *
 * Folosire (player.js): HdsSunetAc3.poate() -> WebAssembly si FLAC in MediaSource;
 *   var c = HdsSunetAc3.convertor({laEsec: function (e) {}});   mpegts.createPlayer(..., {hdsSunetAc3: c, ...});
 *   c.ac3(pes, pts) -> [{date: cadrul FLAC, pts (90 kHz), n, rata, config}] (cheama mpegts.js);  c.inchide()
 * In node (testele de pe PC) fisierul exporta scriitorul FLAC (cadruFlac, blocDfla, crc8, crc16, ...) si convertorul;
 * decodorul il incarca proba (acelasi hdsdec.js + hdsdec.wasm) si il da prin foloseste(m), cu onAudio: laAudio.
 */
(function (radacina) {
	"use strict";

	// aceeasi ca in hds-player.js: primele 12 cifre din sha256 al tv-wasm/hdsdec.wasm (adresa decodorului, cache o zi)
	var VERSIUNE_DECODOR = "099cf027855f";
	var COADA_MAX = 400;              // PES-uri AC-3 in asteptare cat se incarca decodorul (~13 s de sunet)
	var GOL_MAX_S = 10;               // un gol de timp pana la atat se umple cu liniste; peste: timp nou
	// codul ratei in antetul cadrului FLAC (RFC 9639, 9.1.3); alta rata: 0 = cea din STREAMINFO
	var COD_RATA = {88200: 1, 176400: 2, 192000: 3, 8000: 4, 16000: 5, 22050: 6, 24000: 7, 32000: 8, 44100: 9, 48000: 10,
		96000: 11};

	// ---------------------------------------------------------------- FLAC (RFC 9639)

	function tabelCrc(biti, polinom) {
		var t = new Uint16Array(256), sus = 1 << (biti - 1), masca = (1 << biti) - 1;
		for (var i = 0; i < 256; i++) {
			var c = i << (biti - 8);
			for (var k = 0; k < 8; k++) c = (c & sus) ? ((c << 1) ^ polinom) & masca : (c << 1) & masca;
			t[i] = c;
		}
		return t;
	}
	var T8 = tabelCrc(8, 0x07), T16 = tabelCrc(16, 0x8005);

	// CRC-8 al antetului cadrului (x^8 + x^2 + x + 1) si CRC-16 al cadrului intreg (x^16 + x^15 + x^2 + 1), de la 0
	function crc8(b, de, la) {
		var c = 0;
		for (var i = de; i < la; i++) c = T8[c ^ b[i]];
		return c;
	}
	function crc16(b, de, la) {
		var c = 0;
		for (var i = de; i < la; i++) c = ((c << 8) & 0xFFFF) ^ T16[(c >> 8) ^ b[i]];
		return c;
	}

	// numarul cadrului, scris ca in UTF-8 (cel mult 31 de biti, 6 octeti)
	function numarUtf8(n) {
		n = n & 0x7FFFFFFF;
		if (n < 0x80) return [n];
		var octeti = n < 0x800 ? 2 : n < 0x10000 ? 3 : n < 0x200000 ? 4 : n < 0x4000000 ? 5 : 6;
		var r = [];
		for (var i = octeti - 1; i > 0; i--) { r.unshift(0x80 | (n & 0x3F)); n = n >>> 6; }
		r.unshift(((0xFF00 >> octeti) & 0xFF) | n);
		return r;
	}

	// STREAMINFO (34 de octeti): blocul fix `bloc`, marimile cadrelor nestiute (0), fara numarul total si fara MD5
	function streamInfo(rata, canale, biti, bloc) {
		var s = new Uint8Array(34);
		s[0] = bloc >> 8; s[1] = bloc & 0xFF; s[2] = bloc >> 8; s[3] = bloc & 0xFF;
		s[10] = (rata >> 12) & 0xFF;
		s[11] = (rata >> 4) & 0xFF;
		s[12] = ((rata & 0x0F) << 4) | ((canale - 1) << 1) | (((biti - 1) >> 4) & 1);
		s[13] = ((biti - 1) & 0x0F) << 4;
		return s;
	}

	// continutul cutiei dfLa dupa versiune si steaguri (pe acelea le pune mpegts.js): antetul blocului de metadate
	// (ultimul bloc, tipul 0 = STREAMINFO, 34 de octeti) si STREAMINFO
	function blocDfla(rata, canale, biti, bloc) {
		var b = new Uint8Array(38);
		b[0] = 0x80; b[1] = 0; b[2] = 0; b[3] = 34;
		b.set(streamInfo(rata, canale, biti, bloc), 4);
		return b;
	}

	function laFel(x) {
		for (var i = 1; i < x.length; i++) if (x[i] !== x[0]) return false;
		return true;
	}

	// un cadru FLAC, cu bloc fix, din canalele pe 16 biti (Int16Array, aceeasi lungime; 1..8 canale, independente)
	function cadruFlac(canale, rata, numar) {
		var n = canale[0].length, nc = canale.length;
		var numarB = numarUtf8(numar), constant = canale.map(laFel);
		var lung = 4 + numarB.length + 2 + 1 + 2;
		for (var c = 0; c < nc; c++) lung += 1 + (constant[c] ? 2 : 2 * n);
		var b = new Uint8Array(lung), o = 0;
		b[o++] = 0xFF; b[o++] = 0xF8;                          // sincronul; bloc fix
		b[o++] = 0x70 | (COD_RATA[rata] || 0);                 // marimea blocului: 16 biti la sfarsitul antetului
		b[o++] = ((nc - 1) << 4) | 0x08;                       // canale independente; 16 biti pe esantion
		for (var k = 0; k < numarB.length; k++) b[o++] = numarB[k];
		b[o++] = ((n - 1) >> 8) & 0xFF; b[o++] = (n - 1) & 0xFF;
		b[o] = crc8(b, 0, o); o++;
		for (c = 0; c < nc; c++) {
			var x = canale[c];
			if (constant[c]) {
				b[o++] = 0x00;                                 // subcadru CONSTANT
				b[o++] = (x[0] >> 8) & 0xFF; b[o++] = x[0] & 0xFF;
			} else {
				b[o++] = 0x02;                                 // subcadru VERBATIM
				for (var i = 0; i < n; i++) { b[o++] = (x[i] >> 8) & 0xFF; b[o++] = x[i] & 0xFF; }
			}
		}
		var crc = crc16(b, 0, o);
		b[o++] = crc >> 8; b[o++] = crc & 0xFF;
		return b;
	}

	// esantioanele float (-1..1) pe 16 biti, rotunjite si taiate la margini
	function laInt16(f, iesire) {
		for (var i = 0; i < f.length; i++) {
			var v = Math.round(f[i] * 32767);
			iesire[i] = v > 32767 ? 32767 : (v < -32768 ? -32768 : v);
		}
		return iesire;
	}

	// ---------------------------------------------------------------- decodorul (unul pe pagina)

	var M = null, incarcare = null, curent = null, ptrIn = 0, marimeIn = 0;

	// probele din node: decodorul (acelasi hdsdec.js + hdsdec.wasm) il incarca proba si il da aici
	function foloseste(m) {
		M = m;
		incarcare = Promise.resolve(m);
	}

	function laAudio(n, canale, rata, fmt, date, pts) {
		if (curent) curent._sunet(n, canale, rata, fmt, date, pts);
	}

	function incarcaDecodorul() {
		if (incarcare) return incarcare;
		incarcare = new Promise(function (da, nu) {
			var v = "?v=" + VERSIUNE_DECODOR;
			function porneste() {
				radacina.HdsDec({locateFile: function (f) { return "/tv/tv-wasm/" + f + v; }, onVideo: function () {},
					onAudio: laAudio}).then(function (m) { M = m; da(m); }, nu);
			}
			if (typeof radacina.HdsDec === "function") { porneste(); return; }
			var s = document.createElement("script");
			s.src = "/tv/tv-wasm/hdsdec.js" + v;
			s.onload = function () {
				if (typeof radacina.HdsDec === "function") porneste();
				else nu(new Error("Decodorul de sunet nu s-a încărcat de pe receptor."));
			};
			s.onerror = function () { nu(new Error("Decodorul de sunet nu s-a încărcat de pe receptor.")); };
			document.head.appendChild(s);
		});
		return incarcare;
	}

	function poate() {
		try {
			var MS = radacina.ManagedMediaSource || radacina.MediaSource;
			return typeof WebAssembly === "object" && typeof WebAssembly.instantiate === "function" &&
				!!(MS && MS.isTypeSupported && MS.isTypeSupported('audio/mp4; codecs="flac"'));
		} catch (e) { return false; }
	}

	// ---------------------------------------------------------------- convertorul (unul pe pornire)

	function Convertor(o) {
		this.o = o || {};
		this.d = 0;
		this.coada = [];
		this.gata = false;
		this.esuat = false;
		this.inchis = false;
		this.seIncarca = false;
		this.iesire = null;
		this.numar = 0;              // numarul cadrului FLAC
		this.urm = null;             // PTS-ul asteptat al urmatorului cadru (90 kHz)
		this.ultimIn = -1;           // ultimul PTS intrat (al PES-ului)
		this.fmt = null;             // {rata, bloc, config}
		// statisticile (probele de pe PC): mutare_max = cel mai mare PTS lipit de cadrul de dinainte (90 kHz)
		this.st = {pes: 0, cadre: 0, liniste: 0, reluari: 0, ms: 0, esantioane: 0, erori: 0, octeti: 0, incarcare_ms: null,
			coada_max: 0, aruncate: 0, mutare_max: 0};
	}

	// cheama mpegts.js la fiecare PES AC-3 (pts in 90 kHz, sau undefined); da cadrele FLAC gata de pus in MP4
	Convertor.prototype.ac3 = function (pes, pts) {
		if (this.esuat || this.inchis || !pes || !pes.length) return [];
		this.st.pes++;
		var p = (typeof pts === "number" && pts >= 0) ? pts : -1;
		if (!this.gata) {
			if (this.coada.length < COADA_MAX) this.coada.push([pes.slice(), p]);
			else this.st.aruncate++;
			if (this.coada.length > this.st.coada_max) this.st.coada_max = this.coada.length;
			this._incarca();
			return [];
		}
		var iesire = this.iesire = [];
		if (this.coada.length) {
			var c = this.coada;
			this.coada = [];
			for (var i = 0; i < c.length; i++) this._decodeaza(c[i][0], c[i][1]);
		}
		this._decodeaza(pes, p);
		this.iesire = null;
		return iesire;
	};

	Convertor.prototype._incarca = function () {
		if (this.seIncarca) return;
		this.seIncarca = true;
		var self = this, t0 = performance.now();
		incarcaDecodorul().then(function () {
			if (self.inchis) return;
			self.d = M.ccall("dec_open", "number", ["string", "number"], ["ac3", 1]);
			if (!self.d) throw new Error("Decodorul AC-3 nu a pornit în browser.");
			self.gata = true;
			self.st.incarcare_ms = Math.round(performance.now() - t0);
		}).catch(function (e) {
			self.esuat = true;
			self.coada = [];
			if (!self.inchis && self.o.laEsec) self.o.laEsec(e);
		});
	};

	Convertor.prototype._decodeaza = function (pes, pts) {
		// un salt de timp (inapoi, sau mai mare decat un gol): decodorul o ia de la capat, cadrele vechi nu se mai leaga
		if (pts >= 0 && this.ultimIn >= 0 && (pts < this.ultimIn - 90000 || pts > this.ultimIn + GOL_MAX_S * 90000)) {
			M._dec_reset(this.d);
			this.urm = null;
			this.st.reluari++;
		}
		if (pts >= 0) this.ultimIn = pts;
		if (pes.length > marimeIn) {
			if (ptrIn) M._free(ptrIn);
			marimeIn = Math.max(pes.length, 65536);
			ptrIn = M._malloc(marimeIn);
		}
		M.HEAPU8.set(pes, ptrIn);
		var t0 = performance.now();
		curent = this;
		try {
			if (M._dec_push(this.d, ptrIn, pes.length, pts) < 0) this.st.erori++;
		} finally {
			curent = null;
		}
		this.st.ms += performance.now() - t0;
	};

	// un cadru decodat (float planar, de la decodor): stereo pe 16 biti, eventual liniste in fata, apoi FLAC
	Convertor.prototype._sunet = function (n, canale, rata, fmt, date, pts) {
		if (fmt !== 8 || !canale || !n || !rata || !this.iesire) return;     // AV_SAMPLE_FMT_FLTP
		var U32 = M.HEAPU32, F32 = M.HEAPF32, can = [];
		for (var i = 0; i < canale; i++) {
			var a = U32[(date >> 2) + i] >> 2;
			can.push(F32.subarray(a, a + n));
		}
		var l = new Int16Array(n), r = new Int16Array(n);
		if (canale === 1) { laInt16(can[0], l); r.set(l); }
		else if (canale === 2) { laInt16(can[0], l); laInt16(can[1], r); }
		else {
			// mai mult de doua canale (fara downmix in decodor): FL FR FC LFE SL SR, coeficientii ITU-R BS.775
			var k = 0.7071, c = can[2] || null, sl = can[4] || null, sr = can[5] || null;
			var fl = new Float32Array(n), fr = new Float32Array(n);
			for (var j = 0; j < n; j++) {
				var cj = c ? c[j] * k : 0;
				fl[j] = (can[0][j] + cj + (sl ? sl[j] * k : 0)) * 0.5858;
				fr[j] = (can[1][j] + cj + (sr ? sr[j] * k : 0)) * 0.5858;
			}
			laInt16(fl, l); laInt16(fr, r);
		}
		var durata = n * 90000 / rata;
		if (pts < 0) pts = this.urm !== null ? this.urm : -1;
		if (pts < 0) return;                     // inainte de primul PTS: fara loc in timp
		if (this.urm !== null) {
			var gol = pts - this.urm;
			if (gol > durata * 1.5 && gol <= GOL_MAX_S * 90000) {
				// pachete pierdute: liniste in locul cadrelor lipsa
				var lipsa = Math.round(gol / durata), z = new Int16Array(n), de_la = this.urm;
				for (var q = 0; q < lipsa; q++) this._scrie([z, z], rata, de_la + q * durata, true);
			} else if (Math.abs(gol) < durata / 2) {
				// lipit de cadrul de dinainte (rotunjirile); cat s-a mutat se tine minte (probele: sub o jumatate de cadru)
				if (Math.abs(gol) > this.st.mutare_max) this.st.mutare_max = Math.abs(gol);
				pts = this.urm;
			}
		}
		this._scrie([l, r], rata, pts, false);
		this.urm = pts + durata;
		this.st.esantioane += n;
	};

	Convertor.prototype._scrie = function (canale, rata, pts, liniste) {
		var n = canale[0].length;
		if (!this.fmt || this.fmt.rata !== rata || n > this.fmt.bloc) {
			// formatul se schimba (alta rata, bloc mai mare): alt STREAMINFO, deci alt segment de initializare
			this.fmt = {rata: rata, bloc: n, config: blocDfla(rata, 2, 16, n)};
		}
		var date = cadruFlac(canale, rata, this.numar);
		this.numar = (this.numar + 1) & 0x7FFFFFFF;
		this.iesire.push({date: date, pts: pts, n: n, rata: rata, config: this.fmt.config});
		this.st.cadre++;
		this.st.octeti += date.length;
		if (liniste) this.st.liniste++;
		if (this.urm === null || pts + n * 90000 / rata > this.urm) this.urm = pts + n * 90000 / rata;
	};

	Convertor.prototype.inchide = function () {
		if (this.inchis) return;
		this.inchis = true;
		this.coada = [];
		if (this.d && M) { try { M._dec_close(this.d); } catch (e) {} }
		this.d = 0;
	};

	function convertor(o) {
		return new Convertor(o);
	}

	if (typeof module === "object" && module.exports) {
		module.exports = {crc8: crc8, crc16: crc16, numarUtf8: numarUtf8, streamInfo: streamInfo, blocDfla: blocDfla,
			cadruFlac: cadruFlac, laInt16: laInt16, convertor: convertor, laAudio: laAudio, foloseste: foloseste,
			VERSIUNE_DECODOR: VERSIUNE_DECODOR, GOL_MAX_S: GOL_MAX_S, COADA_MAX: COADA_MAX};
		return;
	}
	if (radacina.HdsSunetAc3) return;
	radacina.HdsSunetAc3 = {
		poate: poate,
		convertor: convertor,
		VERSIUNE_DECODOR: VERSIUNE_DECODOR
	};
})(typeof window !== "undefined" ? window : this);
