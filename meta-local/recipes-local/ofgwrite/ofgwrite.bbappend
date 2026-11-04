# ofgwrite pornit din sistem (ecranul de actualizare) de pe un stick cu spatiu in eticheta golea radacina: dosarul de
# montare se cerea fara ghilimele (REGULI-FLASH-RECEPTOR.md, Regula 1b; 03.11.2026). Peticul se aplica pe ramurile 5.0
# (OE-Alliance 6.0) si master (5.6).
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
# Al doilea petic: daca arhiva nu se mai vede dupa mutarea montarii, oprire si repornire inainte de orice stergere. Pe
# ramura master e oprire-fara-arhiva.patch: mesajele au alte functii acolo.
# 04.11.2026: textele ferestrei in limba omului (numai afisarea; enigma2 da tabela in OFGWRITE_TEXTS, fara ea engleza) si fontul cu ș, ț, greaca, chirilica.
# Sursa e fixata pe 5.0.4: peticele sunt probate pe aceasta comitere, iar un program care scrie in memoria interna nu se schimba singur.
SRCREV = "9ef59e0a50d4ad37db1fbbeeb0c6e11be64f5108"
SRC_URI += "file://cale-cu-spatiu.patch file://oprire-fara-arhiva-50.patch file://ofgwrite-texte-5.0.4.patch file://ofgwrite-font-5.0.4.patch"
# Aceeasi versiune de sursa: fara asta, feedul nu ar aduce pachetul reparat pe receptoarele care il au deja.
PR:append = ".hds2"
