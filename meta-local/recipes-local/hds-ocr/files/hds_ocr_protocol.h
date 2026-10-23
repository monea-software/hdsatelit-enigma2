// hds_ocr_protocol.h - protocolul serviciului hds-ocr (recunoasterea textului din subtitrarile DVB)
//
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Monea Software pentru HD Satelit
//
// Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
// associated documentation files (the "Software"), to deal in the Software without restriction,
// including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense,
// and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so,
// subject to the following conditions: The above copyright notice and this permission notice shall be
// included in all copies or substantial portions of the Software.
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED.
//
// Licenta MIT e aleasa anume: fisierul poate fi copiat si in enigma2 (GPL-2.0-only), pentru ca MIT e
// compatibila cu GPL-2.0. Serviciul hds-ocr e legat de libtesseract (Apache-2.0), care NU e compatibila
// cu GPL-2.0, deci tesseract ramane numai in procesul hds-ocr; enigma2 vorbeste cu el doar prin socket.
//
// Pe scurt (detaliile in PROTOCOL.md):
//   - socket unix de tip flux (SOCK_STREAM), implicit /tmp/hds-ocr.sock;
//   - fiecare mesaj = antet de 12 octeti + corp; toate numerele sunt little-endian;
//   - clientul trimite RECOGNIZE (o regiune de subtitrare: indici de 8 biti + paleta ARGB) si primeste
//     RESULT cu acelasi request_id; raspunsurile pot veni in alta ordine decat cererile (dupa request_id).
//   - paleta: A = OPACITATE (0 = transparent, 255 = opac). In enigma2 gRGB.a e TRANSPARENTA, deci
//     clientul trimite 255 - gRGB.a (vezi argb_from_enigma2 mai jos).

#ifndef HDS_OCR_PROTOCOL_H
#define HDS_OCR_PROTOCOL_H

#include <cstddef>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>

namespace hdsocr {

// antetul: 'H' 'O' 'C' 'R', versiune (u16), tip (u16), lungimea corpului (u32)
static const uint8_t MAGIC[4] = {'H', 'O', 'C', 'R'};
static const uint16_t PROTOCOL_VERSION = 1;
static const size_t HEADER_SIZE = 12;
static const uint32_t MAX_PAYLOAD = 8u * 1024u * 1024u;   // corpul unui mesaj
static const unsigned MAX_DIM = 4096;                       // latime/inaltime maxima a unei regiuni
static const size_t MAX_PIXELS = 4u * 1024u * 1024u;       // latime * inaltime
static const size_t RECOGNIZE_FIXED = 28;                   // corpul RECOGNIZE fara paleta si pixeli
static const size_t RESULT_FIXED = 28;
static const size_t LINE_FIXED = 36;
static const size_t WORD_FIXED = 12;

enum MsgType : uint16_t {
	MSG_RECOGNIZE = 1,   // client -> serviciu
	MSG_PING = 2,        // client -> serviciu, corp gol; raspuns MSG_PONG
	MSG_RESULT = 0x81,   // serviciu -> client
	MSG_PONG = 0x82,     // serviciu -> client, corp = text JSON UTF-8 (stare, pentru diagnoza)
};

enum RequestFlags : uint32_t {
	FLAG_SUPERSEDE = 1u << 0,     // anuleaza cererile mai vechi (generation mai mica) de pe aceeasi conexiune
	FLAG_NO_CACHE = 1u << 1,      // nu folosi si nu umple memoria de randuri deja recunoscute
	FLAG_KEEP_CEDILLA = 1u << 2,  // la romana NU inlocui s/t cu sedila prin s/t cu virgula
	FLAG_NO_WORDS = 1u << 3,      // raspunsul fara lista de cuvinte (numai randuri)
};

enum Status : uint16_t {
	ST_OK = 0,           // gata (0 randuri = regiunea nu are text)
	ST_TIMEOUT = 1,      // timpul cererii s-a terminat; randurile deja recunoscute sunt in raspuns
	ST_CANCELLED = 2,    // anulata de o cerere mai noua (FLAG_SUPERSEDE) sau de inchiderea conexiunii
	ST_BAD_REQUEST = 3,  // cerere gresita (dimensiuni, paleta, lungime)
	ST_NO_MODEL = 4,     // limba ceruta e cunoscuta, dar modelul ei lipseste; sau pista fara limba si fara model implicit
	ST_BUSY = 5,         // coada plina
	ST_ERROR = 6,        // eroare interna (tesseract nu a pornit etc.)
};

enum LineFlags : uint8_t {
	LF_CACHED = 1,      // randul a venit din memoria de randuri (nu s-a recunoscut din nou)
	LF_TIMEOUT = 2,     // randul nu s-a mai recunoscut (timp terminat); text gol
	LF_LOW_CONF = 4,    // cel putin un cuvant are incredere sub 50
	LF_INVERTED = 8,    // text inchis pe fond deschis (caseta deschisa sau contur deschis)
};

struct Request {
	uint32_t request_id = 0;
	uint32_t generation = 0;   // numarul paginii de subtitrare; creste; regiunile aceleiasi pagini au acelasi numar
	uint32_t flags = 0;
	uint16_t timeout_ms = 0;   // 0 = implicit (1500 ms); maxim 10000
	// codul ISO 639-2 sau 639-1 al pistei DVB (ex. "rum", "ron", "eng", "ger") sau numele modelului cerut de client,
	// completat cu 0. Un model cu nume mai lung de 4 litere are un cod al clientului: "srpl" = srp_latn (LANG_MAP din
	// hds-ocr.cpp). Modelele se cauta in --tessdata si apoi in fiecare --tessdata-extra.
	char lang[4] = {0, 0, 0, 0};
	int16_t x = 0, y = 0;      // pozitia regiunii in pagina; se aduna la toate dreptunghiurile din raspuns
	uint16_t width = 0, height = 0;
	std::vector<uint32_t> palette;  // ARGB, A = opacitate; 1..256 intrari
	std::vector<uint8_t> pixels;    // width * height indici, rand dupa rand, fara umplutura
};

struct Word {
	int16_t x = 0, y = 0;
	uint16_t w = 0, h = 0;
	uint8_t confidence = 0;  // 0..100
	uint8_t flags = 0;       // rezervat (0)
	std::string text;        // UTF-8
};

struct Line {
	int16_t x = 0, y = 0;      // dreptunghiul randului (umplutura + contur) in coordonatele paginii
	uint16_t w = 0, h = 0;
	int16_t baseline = 0;      // ordonata liniei de baza (pagina)
	uint16_t x_height = 0;     // inaltimea literei x, pixeli de pagina (0 = necunoscuta)
	uint16_t ascender = 0;     // de la linia de baza pana la varful majusculelor/literelor inalte
	uint16_t descender = 0;    // sub linia de baza (pozitiv)
	uint32_t fill = 0;         // culoarea umpluturii literelor, ARGB (A = opacitate)
	uint32_t outline = 0;      // culoarea conturului; A = 0 daca nu are contur
	uint32_t box = 0;          // culoarea casetei de fundal; A = 0 daca nu are caseta
	uint8_t outline_px = 0;    // grosimea medie a conturului, pixeli de pagina
	uint8_t confidence = 0;    // increderea randului 0..100
	uint8_t flags = 0;         // LineFlags
	uint8_t reserved = 0;
	std::string text;          // UTF-8, fara sfarsit de rand
	std::vector<Word> words;
};

struct Result {
	uint32_t request_id = 0;
	uint32_t generation = 0;
	uint16_t status = ST_OK;
	uint32_t elapsed_us = 0;   // de la primirea cererii pana la trimiterea raspunsului
	char model[8] = {0};       // modelul folosit ("ron", "srp_latn" ...), completat cu 0; fara 0 la sfarsit cand
	                           // numele are 8 litere, deci se citeste cu lungime (strnlen), nu ca sir C
	uint16_t cache_hits = 0;   // cate randuri au venit din memorie
	std::vector<Line> lines;
};

// culoare din enigma2 (gRGB: r, g, b, a = TRANSPARENTA) in ARGB cu A = opacitate
inline uint32_t argb_from_enigma2(unsigned r, unsigned g, unsigned b, unsigned transparency)
{
	return ((uint32_t)(255 - (transparency & 255)) << 24) | ((r & 255) << 16) | ((g & 255) << 8) | (b & 255);
}

// ---- scriere/citire little-endian, independent de procesor ----
inline void put8(std::vector<uint8_t> &o, uint8_t v) { o.push_back(v); }
inline void put16(std::vector<uint8_t> &o, uint16_t v) { o.push_back(v & 255); o.push_back(v >> 8); }
inline void put32(std::vector<uint8_t> &o, uint32_t v)
{
	o.push_back(v & 255); o.push_back((v >> 8) & 255); o.push_back((v >> 16) & 255); o.push_back(v >> 24);
}
inline uint16_t get16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
inline uint32_t get32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }

inline void put_header(std::vector<uint8_t> &o, uint16_t type, uint32_t payload_len)
{
	o.insert(o.end(), MAGIC, MAGIC + 4);
	put16(o, PROTOCOL_VERSION);
	put16(o, type);
	put32(o, payload_len);
}

// antet: intoarce false daca nu e un antet HOCR valid (conexiunea trebuie inchisa)
inline bool parse_header(const uint8_t *p, uint16_t &type, uint32_t &payload_len)
{
	if (memcmp(p, MAGIC, 4) != 0 || get16(p + 4) != PROTOCOL_VERSION)
		return false;
	type = get16(p + 6);
	payload_len = get32(p + 8);
	return payload_len <= MAX_PAYLOAD;
}

inline std::vector<uint8_t> encode_request(const Request &r)
{
	std::vector<uint8_t> o;
	size_t n = r.palette.size();
	uint32_t len = (uint32_t)(RECOGNIZE_FIXED + 4 * n + r.pixels.size());
	o.reserve(HEADER_SIZE + len);
	put_header(o, MSG_RECOGNIZE, len);
	put32(o, r.request_id);
	put32(o, r.generation);
	put32(o, r.flags);
	put16(o, r.timeout_ms);
	for (int i = 0; i < 4; ++i)
		put8(o, (uint8_t)r.lang[i]);
	put16(o, (uint16_t)r.x);
	put16(o, (uint16_t)r.y);
	put16(o, r.width);
	put16(o, r.height);
	put16(o, (uint16_t)n);
	for (size_t i = 0; i < n; ++i)
		put32(o, r.palette[i]);
	o.insert(o.end(), r.pixels.begin(), r.pixels.end());
	return o;
}

// corpul unui RECOGNIZE (fara antet); false = cerere gresita
inline bool decode_request(const uint8_t *p, size_t len, Request &r)
{
	if (len < RECOGNIZE_FIXED)
		return false;
	r.request_id = get32(p);
	r.generation = get32(p + 4);
	r.flags = get32(p + 8);
	r.timeout_ms = get16(p + 12);
	memcpy(r.lang, p + 14, 4);
	r.x = (int16_t)get16(p + 18);
	r.y = (int16_t)get16(p + 20);
	r.width = get16(p + 22);
	r.height = get16(p + 24);
	unsigned n = get16(p + 26);
	if (n < 1 || n > 256 || r.width < 1 || r.height < 1 || r.width > MAX_DIM || r.height > MAX_DIM)
		return false;
	size_t npix = (size_t)r.width * r.height;
	if (npix > MAX_PIXELS || len != RECOGNIZE_FIXED + 4 * (size_t)n + npix)
		return false;
	r.palette.resize(n);
	for (unsigned i = 0; i < n; ++i)
		r.palette[i] = get32(p + RECOGNIZE_FIXED + 4 * i);
	const uint8_t *px = p + RECOGNIZE_FIXED + 4 * n;
	r.pixels.assign(px, px + npix);
	return true;
}

inline void put_text(std::vector<uint8_t> &o, const std::string &s)
{
	size_t n = s.size() > 65535 ? 65535 : s.size();
	o.insert(o.end(), s.begin(), s.begin() + n);
}

inline std::vector<uint8_t> encode_result(const Result &r)
{
	std::vector<uint8_t> b;
	put32(b, r.request_id);
	put32(b, r.generation);
	put16(b, r.status);
	put16(b, (uint16_t)r.lines.size());
	put32(b, r.elapsed_us);
	for (int i = 0; i < 8; ++i)
		put8(b, (uint8_t)r.model[i]);
	put16(b, r.cache_hits);
	put16(b, 0);
	for (const Line &l : r.lines)
	{
		put16(b, (uint16_t)l.x); put16(b, (uint16_t)l.y); put16(b, l.w); put16(b, l.h);
		put16(b, (uint16_t)l.baseline); put16(b, l.x_height); put16(b, l.ascender); put16(b, l.descender);
		put32(b, l.fill); put32(b, l.outline); put32(b, l.box);
		put8(b, l.outline_px); put8(b, l.confidence); put8(b, l.flags); put8(b, 0);
		put16(b, (uint16_t)(l.text.size() > 65535 ? 65535 : l.text.size()));
		put16(b, (uint16_t)l.words.size());
		put_text(b, l.text);
		for (const Word &w : l.words)
		{
			put16(b, (uint16_t)w.x); put16(b, (uint16_t)w.y); put16(b, w.w); put16(b, w.h);
			put8(b, w.confidence); put8(b, w.flags);
			put16(b, (uint16_t)(w.text.size() > 65535 ? 65535 : w.text.size()));
			put_text(b, w.text);
		}
	}
	std::vector<uint8_t> o;
	o.reserve(HEADER_SIZE + b.size());
	put_header(o, MSG_RESULT, (uint32_t)b.size());
	o.insert(o.end(), b.begin(), b.end());
	return o;
}

// corpul unui RESULT (fara antet); false = raspuns stricat
inline bool decode_result(const uint8_t *p, size_t len, Result &r)
{
	if (len < RESULT_FIXED)
		return false;
	r.request_id = get32(p);
	r.generation = get32(p + 4);
	r.status = get16(p + 8);
	unsigned nl = get16(p + 10);
	r.elapsed_us = get32(p + 12);
	memcpy(r.model, p + 16, 8);
	r.cache_hits = get16(p + 24);
	size_t o = RESULT_FIXED;
	r.lines.clear();
	for (unsigned i = 0; i < nl; ++i)
	{
		if (o + LINE_FIXED > len)
			return false;
		const uint8_t *q = p + o;
		Line l;
		l.x = (int16_t)get16(q); l.y = (int16_t)get16(q + 2); l.w = get16(q + 4); l.h = get16(q + 6);
		l.baseline = (int16_t)get16(q + 8); l.x_height = get16(q + 10); l.ascender = get16(q + 12); l.descender = get16(q + 14);
		l.fill = get32(q + 16); l.outline = get32(q + 20); l.box = get32(q + 24);
		l.outline_px = q[28]; l.confidence = q[29]; l.flags = q[30]; l.reserved = q[31];
		unsigned tl = get16(q + 32), nw = get16(q + 34);
		o += LINE_FIXED;
		if (o + tl > len)
			return false;
		l.text.assign((const char *)p + o, tl);
		o += tl;
		for (unsigned k = 0; k < nw; ++k)
		{
			if (o + WORD_FIXED > len)
				return false;
			const uint8_t *w = p + o;
			Word wd;
			wd.x = (int16_t)get16(w); wd.y = (int16_t)get16(w + 2); wd.w = get16(w + 4); wd.h = get16(w + 6);
			wd.confidence = w[8]; wd.flags = w[9];
			unsigned wl = get16(w + 10);
			o += WORD_FIXED;
			if (o + wl > len)
				return false;
			wd.text.assign((const char *)p + o, wl);
			o += wl;
			l.words.push_back(wd);
		}
		r.lines.push_back(l);
	}
	return o == len;
}

} // namespace hdsocr

#endif
