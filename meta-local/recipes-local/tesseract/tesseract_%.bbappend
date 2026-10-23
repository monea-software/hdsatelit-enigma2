# HDSatelit (25.09.2026, lotul ocr-dvb/motor): tesseract numai ca biblioteca pentru hds-ocr (proces separat
# de enigma2; Apache-2.0 nu se leaga niciodata in enigma2, care e GPL-2.0-only).
# --disable-legacy: modelele tessdata_fast sunt numai LSTM, motorul vechi nu se foloseste (biblioteca mai mica).
# --disable-openmp: un singur fir; pe receptor procesorul e impartit cu enigma2, iar pe un rand de
#   subtitrare firele OpenMP doar adauga cost (si hds-ocr pune oricum OMP_THREAD_LIMIT=1).
# --disable-graphics: fara ScrollView (depanare prin retea). Fara curl/libarchive: nu citim URL-uri sau arhive.
EXTRA_OECONF += "--disable-legacy --disable-openmp --disable-graphics --disable-doc --without-curl --without-archive"
# reteta din meta-oe recomanda tesseract-lang-eng (depozitul tessdata MARE); noi folosim hds-ocr-modele (tessdata_fast)
RRECOMMENDS:${PN}:remove = "tesseract-lang-eng"
