# PDF fonts

Noto Sans Bengali (regular/bold, including its Latin glyphs) is bundled so
downloaded farm reports render Bangla and English without a network connection.
The font software is licensed under the SIL Open Font License 1.1; see
`OFL-Noto.txt`.

Source: https://github.com/google/fonts/tree/main/ofl/notosansbengali

The official variable font `NotoSansBengali[wdth,wght].ttf` was downloaded on
2 November 2026. Static instances were produced with fontTools 4.68.0 at
`wdth=100`, `wght=400` and `wght=700`. fontTools is not needed at runtime.

ReportLab uses HarfBuzz shaping for Bangla text. One face covers both scripts
to preserve shaping beside punctuation. Fonts are embedded as subsets in each
report; no remote font request is made during export.
