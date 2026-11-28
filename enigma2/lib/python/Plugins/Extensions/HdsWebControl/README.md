# HdsWebControl: the web interface of the receiver

A web server written for this image on `twisted.web`, inside the enigma2 process (the same reactor that
`mytest.py` already runs). It serves the control panel at `http://<receiver>/` (port 80; 8080 redirects to it) and
the JSON API under `/api/`. No code is taken from other web interfaces.

## How it is put together

- `plugin.py` starts the server (`reactor.listenTCP`), holds the basic resources (`statusinfo`, `remotecontrol`,
  `zap`, `screenshot` and others) and the page frame, and mounts the routes of every other module: each `*_web.py`
  module has a `rute(...)` function that returns its resources, which `plugin.py` puts under `/api/` and under the
  page paths.
- About 120 `*_web.py` modules, one per page or group of settings: for example `canale_web.py` (channel list and
  zap), `setari_web.py` (every settings screen of `data/setup.xml`), `tv_web.py` (TV in the browser),
  `antena_web.py` (dish and motor), `asistenta_web.py` (remote assistance), `aplicatii_web.py` (the API for phone
  apps).
- A page keeps as little logic as it can: it calls the same `Components/Hds*.py` module as the screen on the TV, so
  that a menu, screen or setting of the receiver and its page here do the same thing (the rule of the project is that
  every one of them has its page).
- `traducere_pagini.py` gives the pages in the language of the receiver (the page templates are written in
  Romanian); `cadru_web.py` the header, the grouped menu and the themes; `tema_export.py` the colours of the theme as
  a small CSS file for the other web interfaces on the receiver.
- Access: the panel opens without a code; only when the user sets the receiver password (Settings > Network >
  Receiver password) the pages ask for it (`asociere.py`, `Components/HdsParolaLocala.py`).

## TV in the browser

`tv_web.py` streams the channel to the browser. `mpegts.js` (mpegts.js 1.8.0, Apache License 2.0, changes listed in
`mpegts-licenta.txt`) plays H.264 and HEVC through Media Source; `hds-player.js` and `hds-worker.js` are our own
player for MPEG-2 channels and for browsers without H.264, with the decoder in `tv-wasm/`: `hdsdec.wasm` and
`hdsdec.js` are built from `tv-wasm/hdsdec.c` and FFmpeg 8.1.3 (LGPL-2.1-or-later) by
`tv-wasm/construieste-decodor-wasm.sh`; the licenses of the parts are next to them. `osd_strat.py` sends the
receiver's menus as a transparent layer over the picture, `hds-sunet.js` decodes AC-3 sound in the page.

## Install and tests

`Makefile.am` lists every installed file (`install_PYTHON`, `install_DATA`, `tvwasm_DATA`); a new file must be
added there. The web modules load without enigma2 where they can, so they are tested on a PC with the tests kept
with the build tools of the image.
