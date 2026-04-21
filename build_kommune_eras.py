"""
build_kommune_eras.py — one-off helper that emits distribution dicts for the
BOSATT_KOMMUNE by_date realism block (pre-2020, 2020-2023, 2024+ regimes).

Run once during implementation; the emitted JSON is pasted into
variable_metadata.json. Does NOT need to be deployed alongside m2py.py.

Usage:
    python build_kommune_eras.py > kommune_eras_output.json
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Data source 1 — the user's 2019 -> 2020 recode table (verbatim from session).
# Format per entry: (pre2020_code = post2020_code 'post2020_label')
# ---------------------------------------------------------------------------

RECODE_2019_TO_2020 = r"""
(0101 = 3001 'Halden')
(0104 = 3002 'Moss')
(0105 = 3003 'Sarpsborg')
(0106 = 3004 'Fredrikstad')
(0111 = 3011 'Hvaler')
(0118 = 3012 'Aremark')
(0119 = 3013 'Marker')
(0121 = 3026 'Aurskog-Høland')
(0122 = 3014 'Indre Østfold')
(0123 = 3014 'Indre Østfold')
(0124 = 3014 'Indre Østfold')
(0125 = 3014 'Indre Østfold')
(0127 = 3015 'Skiptvet')
(0128 = 3016 'Rakkestad')
(0135 = 3017 'Råde')
(0136 = 3002 'Moss')
(0137 = 3018 'Våler (Viken)')
(0138 = 3014 'Indre Østfold')
(0211 = 3019 'Vestby')
(0213 = 3020 'Nordre Follo')
(0214 = 3021 'Ås')
(0215 = 3022 'Frogn')
(0216 = 3023 'Nesodden')
(0217 = 3020 'Nordre Follo')
(0219 = 3024 'Bærum')
(0220 = 3025 'Asker')
(0221 = 3026 'Aurskog-Høland')
(0226 = 3030 'Lillestrøm')
(0227 = 3030 'Lillestrøm')
(0228 = 3027 'Rælingen')
(0229 = 3028 'Enebakk')
(0230 = 3029 'Lørenskog')
(0231 = 3030 'Lillestrøm')
(0233 = 3031 'Nittedal')
(0234 = 3032 'Gjerdrum')
(0235 = 3033 'Ullensaker')
(0236 = 3034 'Nes')
(0237 = 3035 'Eidsvoll')
(0238 = 3036 'Nannestad')
(0239 = 3037 'Hurdal')
(0301 = 0301 'Oslo')
(0402 = 3401 'Kongsvinger')
(0403 = 3403 'Hamar')
(0412 = 3411 'Ringsaker')
(0415 = 3412 'Løten')
(0417 = 3413 'Stange')
(0418 = 3414 'Nord-Odal')
(0419 = 3415 'Sør-Odal')
(0420 = 3416 'Eidskog')
(0423 = 3417 'Grue')
(0425 = 3418 'Åsnes')
(0426 = 3419 'Våler (Innlandet)')
(0427 = 3420 'Elverum')
(0428 = 3421 'Trysil')
(0429 = 3422 'Åmot')
(0430 = 3423 'Stor-Elvdal')
(0432 = 3424 'Rendalen')
(0434 = 3425 'Engerdal')
(0436 = 3426 'Tolga')
(0437 = 3427 'Tynset')
(0438 = 3428 'Alvdal')
(0439 = 3429 'Folldal')
(0441 = 3430 'Os (Innlandet)')
(0501 = 3405 'Lillehammer')
(0502 = 3407 'Gjøvik')
(0511 = 3431 'Dovre')
(0512 = 3432 'Lesja')
(0513 = 3433 'Skjåk')
(0514 = 3434 'Lom')
(0515 = 3435 'Vågå')
(0516 = 3436 'Nord-Fron')
(0517 = 3437 'Sel')
(0519 = 3438 'Sør-Fron')
(0520 = 3439 'Ringebu')
(0521 = 3440 'Øyer')
(0522 = 3441 'Gausdal')
(0528 = 3442 'Østre Toten')
(0529 = 3443 'Vestre Toten')
(0532 = 3053 'Jevnaker')
(0533 = 3054 'Lunner')
(0534 = 3446 'Gran')
(0536 = 3447 'Søndre Land')
(0538 = 3448 'Nordre Land')
(0540 = 3449 'Sør-Aurdal')
(0541 = 3450 'Etnedal')
(0542 = 3451 'Nord-Aurdal')
(0543 = 3452 'Vestre Slidre')
(0544 = 3453 'Øystre Slidre')
(0545 = 3454 'Vang')
(0602 = 3005 'Drammen')
(0604 = 3006 'Kongsberg')
(0605 = 3007 'Ringerike')
(0612 = 3038 'Hole')
(0615 = 3039 'Flå')
(0616 = 3040 'Nesbyen')
(0617 = 3041 'Gol')
(0618 = 3042 'Hemsedal')
(0619 = 3043 'Ål')
(0620 = 3044 'Hol')
(0621 = 3045 'Sigdal')
(0622 = 3046 'Krødsherad')
(0623 = 3047 'Modum')
(0624 = 3048 'Øvre Eiker')
(0625 = 3005 'Drammen')
(0626 = 3049 'Lier')
(0627 = 3025 'Asker')
(0628 = 3025 'Asker')
(0631 = 3050 'Flesberg')
(0632 = 3051 'Rollag')
(0633 = 3052 'Nore Og Uvdal')
(0701 = 3801 'Horten')
(0704 = 3803 'Tønsberg')
(0710 = 3804 'Sandefjord')
(0711 = 3005 'Drammen')
(0712 = 3805 'Larvik')
(0713 = 3802 'Holmestrand')
(0715 = 3802 'Holmestrand')
(0716 = 3803 'Tønsberg')
(0729 = 3811 'Færder')
(0805 = 3806 'Porsgrunn')
(0806 = 3807 'Skien')
(0807 = 3808 'Notodden')
(0811 = 3812 'Siljan')
(0814 = 3813 'Bamble')
(0815 = 3814 'Kragerø')
(0817 = 3815 'Drangedal')
(0819 = 3816 'Nome')
(0821 = 3817 'Midt-Telemark')
(0822 = 3817 'Midt-Telemark')
(0826 = 3818 'Tinn')
(0827 = 3819 'Hjartdal')
(0828 = 3820 'Seljord')
(0829 = 3821 'Kviteseid')
(0830 = 3822 'Nissedal')
(0831 = 3823 'Fyresdal')
(0833 = 3824 'Tokke')
(0834 = 3825 'Vinje')
(0901 = 4201 'Risør')
(0904 = 4202 'Grimstad')
(0906 = 4203 'Arendal')
(0911 = 4211 'Gjerstad')
(0912 = 4212 'Vegårshei')
(0914 = 4213 'Tvedestrand')
(0919 = 4214 'Froland')
(0926 = 4215 'Lillesand')
(0928 = 4216 'Birkenes')
(0929 = 4217 'Åmli')
(0935 = 4218 'Iveland')
(0937 = 4219 'Evje Og Hornnes')
(0938 = 4220 'Bygland')
(0940 = 4221 'Valle')
(0941 = 4222 'Bykle')
(1001 = 4204 'Kristiansand')
(1002 = 4205 'Lindesnes')
(1003 = 4206 'Farsund')
(1004 = 4207 'Flekkefjord')
(1014 = 4223 'Vennesla')
(1017 = 4204 'Kristiansand')
(1018 = 4204 'Kristiansand')
(1021 = 4205 'Lindesnes')
(1026 = 4224 'Åseral')
(1027 = 4225 'Lyngdal')
(1029 = 4205 'Lindesnes')
(1032 = 4225 'Lyngdal')
(1034 = 4226 'Hægebostad')
(1037 = 4227 'Kvinesdal')
(1046 = 4228 'Sirdal')
(1101 = 1101 'Eigersund')
(1102 = 1108 'Sandnes')
(1103 = 1103 'Stavanger')
(1106 = 1106 'Haugesund')
(1111 = 1111 'Sokndal')
(1112 = 1112 'Lund')
(1114 = 1114 'Bjerkreim')
(1119 = 1119 'Hå')
(1120 = 1120 'Klepp')
(1121 = 1121 'Time')
(1122 = 1122 'Gjesdal')
(1124 = 1124 'Sola')
(1127 = 1127 'Randaberg')
(1129 = 1108 'Sandnes')
(1130 = 1130 'Strand')
(1133 = 1133 'Hjelmeland')
(1134 = 1134 'Suldal')
(1135 = 1135 'Sauda')
(1141 = 1103 'Stavanger')
(1142 = 1103 'Stavanger')
(1144 = 1144 'Kvitsøy')
(1145 = 1145 'Bokn')
(1146 = 1146 'Tysvær')
(1149 = 1149 'Karmøy')
(1151 = 1151 'Utsira')
(1160 = 1160 'Vindafjord')
(1201 = 4601 'Bergen')
(1211 = 4611 'Etne')
(1216 = 4612 'Sveio')
(1219 = 4613 'Bømlo')
(1221 = 4614 'Stord')
(1222 = 4615 'Fitjar')
(1223 = 4616 'Tysnes')
(1224 = 4617 'Kvinnherad')
(1227 = 4618 'Ullensvang')
(1228 = 4618 'Ullensvang')
(1231 = 4618 'Ullensvang')
(1232 = 4619 'Eidfjord')
(1233 = 4620 'Ulvik')
(1234 = 4621 'Voss')
(1235 = 4621 'Voss')
(1238 = 4622 'Kvam')
(1241 = 4624 'Bjørnafjorden')
(1242 = 4623 'Samnanger')
(1243 = 4624 'Bjørnafjorden')
(1244 = 4625 'Austevoll')
(1245 = 4626 'Øygarden')
(1246 = 4626 'Øygarden')
(1247 = 4627 'Askøy')
(1251 = 4628 'Vaksdal')
(1252 = 4629 'Modalen')
(1253 = 4630 'Osterøy')
(1256 = 4631 'Alver')
(1259 = 4626 'Øygarden')
(1260 = 4631 'Alver')
(1263 = 4631 'Alver')
(1264 = 4632 'Austrheim')
(1265 = 4633 'Fedje')
(1266 = 4634 'Masfjorden')
(1401 = 4602 'Kinn')
(1411 = 4635 'Gulen')
(1412 = 4636 'Solund')
(1413 = 4637 'Hyllestad')
(1416 = 4638 'Høyanger')
(1417 = 4639 'Vik')
(1418 = 4640 'Sogndal')
(1419 = 4640 'Sogndal')
(1420 = 4640 'Sogndal')
(1421 = 4641 'Aurland')
(1422 = 4642 'Lærdal')
(1424 = 4643 'Årdal')
(1426 = 4644 'Luster')
(1428 = 4645 'Askvoll')
(1429 = 4646 'Fjaler')
(1430 = 4647 'Sunnfjord')
(1431 = 4647 'Sunnfjord')
(1432 = 4647 'Sunnfjord')
(1433 = 4647 'Sunnfjord')
(1438 = 4648 'Bremanger')
(1439 = 4602 'Kinn')
(1441 = 4649 'Stad')
(1443 = 4649 'Stad')
(1444 = 1577 'Volda')
(1445 = 4650 'Gloppen')
(1449 = 4651 'Stryn')
(1502 = 1506 'Molde')
(1504 = 1507 'Ålesund')
(1505 = 1505 'Kristiansund')
(1511 = 1511 'Vanylven')
(1514 = 1514 'Sande')
(1515 = 1515 'Herøy')
(1516 = 1516 'Ulstein')
(1517 = 1517 'Hareid')
(1519 = 1577 'Volda')
(1520 = 1520 'Ørsta')
(1523 = 1507 'Ålesund')
(1524 = 1578 'Fjord')
(1525 = 1525 'Stranda')
(1526 = 1578 'Fjord')
(1528 = 1528 'Sykkylven')
(1529 = 1507 'Ålesund')
(1531 = 1531 'Sula')
(1532 = 1532 'Giske')
(1534 = 1507 'Ålesund')
(1535 = 1535 'Vestnes')
(1539 = 1539 'Rauma')
(1543 = 1506 'Molde')
(1545 = 1506 'Molde')
(1546 = 1507 'Ålesund')
(1547 = 1547 'Aukra')
(1548 = 1579 'Hustadvika')
(1551 = 1579 'Hustadvika')
(1554 = 1554 'Averøy')
(1557 = 1557 'Gjemnes')
(1560 = 1560 'Tingvoll')
(1563 = 1563 'Sunndal')
(1566 = 1566 'Surnadal')
(1571 = 5055 'Heim')
(1573 = 1573 'Smøla')
(1576 = 1576 'Aure')
(1804 = 1804 'Bodø')
(1805 = 1806 'Narvik')
(1811 = 1811 'Bindal')
(1812 = 1812 'Sømna')
(1813 = 1813 'Brønnøy')
(1815 = 1815 'Vega')
(1816 = 1816 'Vevelstad')
(1818 = 1818 'Herøy')
(1820 = 1820 'Alstahaug')
(1822 = 1822 'Leirfjord')
(1824 = 1824 'Vefsn')
(1825 = 1825 'Grane')
(1826 = 1826 'Hattfjelldal')
(1827 = 1827 'Dønna')
(1828 = 1828 'Nesna')
(1832 = 1832 'Hemnes')
(1833 = 1833 'Rana')
(1834 = 1834 'Lurøy')
(1835 = 1835 'Træna')
(1836 = 1836 'Rødøy')
(1837 = 1837 'Meløy')
(1838 = 1838 'Gildeskål')
(1839 = 1839 'Beiarn')
(1840 = 1840 'Saltdal')
(1841 = 1841 'Fauske')
(1845 = 1845 'Sørfold')
(1848 = 1848 'Steigen')
(1849 = 1875 'Hamarøy')
(1850 = 1806 'Narvik')
(1850 = 1875 'Hamarøy')
(1851 = 1851 'Lødingen')
(1852 = 5412 'Tjeldsund')
(1853 = 1853 'Evenes')
(1854 = 1806 'Narvik')
(1856 = 1856 'Røst')
(1857 = 1857 'Værøy')
(1859 = 1859 'Flakstad')
(1860 = 1860 'Vestvågøy')
(1865 = 1865 'Vågan')
(1866 = 1866 'Hadsel')
(1867 = 1867 'Bø')
(1868 = 1868 'Øksnes')
(1870 = 1870 'Sortland')
(1871 = 1871 'Andøy')
(1874 = 1874 'Moskenes')
(1902 = 5401 'Tromsø')
(1903 = 5402 'Harstad')
(1911 = 5411 'Kvæfjord')
(1913 = 5412 'Tjeldsund')
(1917 = 5413 'Ibestad')
(1919 = 5414 'Gratangen')
(1920 = 5415 'Lavangen')
(1922 = 5416 'Bardu')
(1923 = 5417 'Salangen')
(1924 = 5418 'Målselv')
(1925 = 5419 'Sørreisa')
(1926 = 5420 'Dyrøy')
(1927 = 5421 'Senja')
(1928 = 5421 'Senja')
(1929 = 5421 'Senja')
(1931 = 5421 'Senja')
(1933 = 5422 'Balsfjord')
(1936 = 5423 'Karlsøy')
(1938 = 5424 'Lyngen')
(1939 = 5425 'Storfjord')
(1940 = 5426 'Kåfjord')
(1941 = 5427 'Skjervøy')
(1942 = 5428 'Nordreisa')
(1943 = 5429 'Kvænangen')
(2002 = 5404 'Vardø')
(2003 = 5405 'Vadsø')
(2004 = 5406 'Hammerfest')
(2011 = 5430 'Kautokeino')
(2012 = 5403 'Alta')
(2014 = 5432 'Loppa')
(2015 = 5433 'Hasvik')
(2017 = 5406 'Hammerfest')
(2018 = 5434 'Måsøy')
(2019 = 5435 'Nordkapp')
(2020 = 5436 'Porsanger')
(2021 = 5437 'Karasjok')
(2022 = 5438 'Lebesby')
(2023 = 5439 'Gamvik')
(2024 = 5440 'Berlevåg')
(2025 = 5441 'Tana')
(2027 = 5442 'Nesseby')
(2028 = 5443 'Båtsfjord')
(2030 = 5444 'Sør-Varanger')
(5001 = 5001 'Trondheim')
(5004 = 5006 'Steinkjer')
(5005 = 5007 'Namsos')
(5011 = 5055 'Heim')
(5012 = 5055 'Heim')
(5012 = 5056 'Hitra')
(5012 = 5059 'Orkland')
(5013 = 5056 'Hitra')
(5014 = 5014 'Frøya')
(5015 = 5057 'Ørland')
(5016 = 5059 'Orkland')
(5017 = 5057 'Ørland')
(5018 = 5058 'Åfjord')
(5019 = 5058 'Åfjord')
(5020 = 5020 'Osen')
(5021 = 5021 'Oppdal')
(5022 = 5022 'Rennebu')
(5023 = 5059 'Orkland')
(5024 = 5059 'Orkland')
(5025 = 5025 'Røros')
(5026 = 5026 'Holtålen')
(5027 = 5027 'Midtre Gauldal')
(5028 = 5028 'Melhus')
(5029 = 5029 'Skaun')
(5030 = 5001 'Trondheim')
(5031 = 5031 'Malvik')
(5032 = 5032 'Selbu')
(5033 = 5033 'Tydal')
(5034 = 5034 'Meråker')
(5035 = 5035 'Stjørdal')
(5036 = 5036 'Frosta')
(5037 = 5037 'Levanger')
(5038 = 5038 'Verdal')
(5039 = 5006 'Steinkjer')
(5040 = 5007 'Namsos')
(5041 = 5041 'Snåsa')
(5042 = 5042 'Lierne')
(5043 = 5043 'Røyrvik')
(5044 = 5044 'Namsskogan')
(5045 = 5045 'Grong')
(5046 = 5046 'Høylandet')
(5047 = 5047 'Overhalla')
(5048 = 5007 'Namsos')
(5049 = 5049 'Flatanger')
(5050 = 5060 'Nærøysund')
(5051 = 5060 'Nærøysund')
(5052 = 5052 'Leka')
(5053 = 5053 'Inderøy')
(5054 = 5054 'Indre Fosen')
(5061 = 5061 'Rindal')
"""

# ---------------------------------------------------------------------------
# Data source 2 — authoritative 2020-era -> 2024+ code mapping for the 3
# split counties (Viken, Vestfold og Telemark, Troms og Finnmark) plus the
# Haram re-split. Compiled from Kartverket / regjeringen.no 2024 reform docs.
# Unchanged counties (Oslo 03, Rogaland 11, M&R 15, Nordland 18, Innlandet 34,
# Agder 42, Vestland 46, Trøndelag 50) keep their 2020 codes in 2024+.
# ---------------------------------------------------------------------------

# Former Viken (30xx) -> Østfold (31xx) / Akershus (32xx) / Buskerud (33xx)
MAP_2020_TO_2024 = {
    # Viken -> Østfold (31)
    "3001": "3101",  # Halden
    "3002": "3103",  # Moss
    "3003": "3105",  # Sarpsborg
    "3004": "3107",  # Fredrikstad
    "3011": "3110",  # Hvaler
    "3012": "3124",  # Aremark
    "3013": "3122",  # Marker
    "3014": "3118",  # Indre Østfold
    "3015": "3116",  # Skiptvet
    "3016": "3120",  # Rakkestad
    "3017": "3112",  # Råde
    "3018": "3114",  # Våler (Østfold) — new label
    # Viken -> Akershus (32)
    "3019": "3216",  # Vestby
    "3020": "3207",  # Nordre Follo
    "3021": "3218",  # Ås
    "3022": "3214",  # Frogn
    "3023": "3212",  # Nesodden
    "3024": "3201",  # Bærum
    "3025": "3203",  # Asker
    "3026": "3226",  # Aurskog-Høland
    "3027": "3224",  # Rælingen
    "3028": "3220",  # Enebakk
    "3029": "3222",  # Lørenskog
    "3030": "3205",  # Lillestrøm
    "3031": "3232",  # Nittedal
    "3032": "3230",  # Gjerdrum
    "3033": "3209",  # Ullensaker
    "3034": "3228",  # Nes
    "3035": "3240",  # Eidsvoll
    "3036": "3238",  # Nannestad
    "3037": "3242",  # Hurdal
    "3053": "3236",  # Jevnaker
    "3054": "3234",  # Lunner
    # Viken -> Buskerud (33)
    "3005": "3301",  # Drammen
    "3006": "3303",  # Kongsberg
    "3007": "3305",  # Ringerike
    "3038": "3310",  # Hole
    "3039": "3320",  # Flå
    "3040": "3322",  # Nesbyen
    "3041": "3324",  # Gol
    "3042": "3326",  # Hemsedal
    "3043": "3328",  # Ål
    "3044": "3330",  # Hol
    "3045": "3332",  # Sigdal
    "3046": "3318",  # Krødsherad
    "3047": "3316",  # Modum
    "3048": "3314",  # Øvre Eiker
    "3049": "3312",  # Lier
    "3050": "3334",  # Flesberg
    "3051": "3336",  # Rollag
    "3052": "3338",  # Nore og Uvdal

    # Former Vestfold og Telemark (38xx) -> Vestfold (39) / Telemark (40)
    "3801": "3901",  # Horten
    "3802": "3903",  # Holmestrand
    "3803": "3905",  # Tønsberg
    "3804": "3907",  # Sandefjord
    "3805": "3909",  # Larvik
    "3811": "3911",  # Færder
    "3806": "4001",  # Porsgrunn
    "3807": "4003",  # Skien
    "3808": "4005",  # Notodden
    "3812": "4010",  # Siljan
    "3813": "4012",  # Bamble
    "3814": "4014",  # Kragerø
    "3815": "4016",  # Drangedal
    "3816": "4018",  # Nome
    "3817": "4020",  # Midt-Telemark
    "3818": "4026",  # Tinn
    "3819": "4024",  # Hjartdal
    "3820": "4022",  # Seljord
    "3821": "4028",  # Kviteseid
    "3822": "4030",  # Nissedal
    "3823": "4032",  # Fyresdal
    "3824": "4034",  # Tokke
    "3825": "4036",  # Vinje

    # Former Troms og Finnmark (54xx) -> Troms (55) / Finnmark (56)
    "5401": "5501",  # Tromsø
    "5402": "5503",  # Harstad
    "5411": "5510",  # Kvæfjord
    "5412": "5512",  # Tjeldsund
    "5413": "5514",  # Ibestad
    "5414": "5516",  # Gratangen
    "5415": "5518",  # Lavangen
    "5416": "5520",  # Bardu
    "5417": "5522",  # Salangen
    "5418": "5524",  # Målselv
    "5419": "5526",  # Sørreisa
    "5420": "5528",  # Dyrøy
    "5421": "5530",  # Senja
    "5422": "5532",  # Balsfjord
    "5423": "5534",  # Karlsøy
    "5424": "5536",  # Lyngen
    "5425": "5538",  # Storfjord
    "5426": "5540",  # Kåfjord
    "5427": "5542",  # Skjervøy
    "5428": "5544",  # Nordreisa
    "5429": "5546",  # Kvænangen
    "5403": "5601",  # Alta
    "5404": "5634",  # Vardø
    "5405": "5607",  # Vadsø
    "5406": "5603",  # Hammerfest
    "5430": "5612",  # Guovdageaidnu - Kautokeino
    "5432": "5614",  # Loppa
    "5433": "5616",  # Hasvik
    "5434": "5618",  # Måsøy
    "5435": "5620",  # Nordkapp
    "5436": "5622",  # Porsanger
    "5437": "5610",  # Kárášjohka - Karasjok
    "5438": "5624",  # Lebesby
    "5439": "5626",  # Gamvik
    "5440": "5630",  # Berlevåg
    "5441": "5628",  # Deatnu - Tana
    "5442": "5636",  # Unjárga - Nesseby
    "5443": "5632",  # Båtsfjord
    "5444": "5605",  # Sør-Varanger
}

# Haram (1580) split off from Ålesund (1507) on 2024-01-01, within the
# unchanged Møre og Romsdal (15xx) county.
HARAM_RESPLIT = {"1580": "Haram"}


# ---------------------------------------------------------------------------
# Data source 3 — major city population weights (canonical, not code-keyed).
# Numbers approximate 2024 Norwegian population shares for each city.
# ---------------------------------------------------------------------------

MAJOR_CITY_WEIGHTS = {
    "Oslo": 0.125,
    "Bergen": 0.055,
    "Trondheim": 0.040,
    "Stavanger": 0.028,
    "Bærum": 0.024,
    "Kristiansand": 0.022,
    "Drammen": 0.020,
    "Asker": 0.019,
    "Fredrikstad": 0.017,
    "Lillestrøm": 0.017,
    "Sandnes": 0.015,
    "Tromsø": 0.015,
    "Sarpsborg": 0.012,
    "Skien": 0.011,
    "Ålesund": 0.012,
    "Bodø": 0.010,
    "Sandefjord": 0.011,
    "Arendal": 0.009,
    "Tønsberg": 0.009,
    "Haugesund": 0.007,
    "Porsgrunn": 0.007,
    "Moss": 0.009,
    "Ullensaker": 0.008,
    "Karmøy": 0.008,
    "Nordre Follo": 0.012,
    "Lier": 0.006,
    "Ringerike": 0.006,
    "Ringsaker": 0.007,
    "Halden": 0.006,
    "Kongsberg": 0.006,
    "Larvik": 0.010,
    "Lørenskog": 0.009,
    "Nittedal": 0.005,
    "Askøy": 0.006,
    "Hamar": 0.007,
    "Gjøvik": 0.006,
    "Jessheim": 0.000,  # now part of Ullensaker
    "Molde": 0.006,
    "Horten": 0.006,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_name(s: str) -> str:
    """Strip parenthetical disambiguation, lowercase, and collapse diacritics."""
    s = re.sub(r"\s*\([^)]*\)\s*", "", s)  # remove "(Viken)", "(Innlandet)"
    s = re.sub(r"\s*-\s*[A-ZÆØÅa-zæøå\s]+$", "", s)  # strip Sami alt names after dash
    s = s.strip().lower()
    s = unicodedata.normalize("NFC", s)
    # Handle "X og Y" / "X Og Y" consistency
    s = s.replace(" og ", " og ").replace(" Og ", " og ")
    return s


def parse_recode_table(text: str):
    """Parse the recode table into a list of (pre2020, post2020, label) tuples."""
    pattern = re.compile(r"\((\d{4})\s*=\s*(\d{4})\s+'([^']+)'\)")
    triples = []
    for m in pattern.finditer(text):
        triples.append((m.group(1), m.group(2), m.group(3)))
    return triples


def build_era_code_sets(triples, map_2024, haram_resplit):
    """Compute the three era code lists + per-code canonical labels."""
    # Pre-2020 codes
    pre2020 = {}  # code -> label
    # 2020-era codes
    era2020 = {}  # code -> label
    # Pre-2020 -> 2020 map (for pre-2020 merged cases, use post-2020 label as proxy)
    for pre, post, label in triples:
        era2020.setdefault(post, label)
        # For pre-2020 label, if the post-2020 name applies, use it as best-available.
        # Cities that just renumbered (same name) are accurate; mergers get the merged name.
        pre2020.setdefault(pre, label)

    # 2024+ codes
    era2024 = {}  # code -> label
    for code2020, label in era2020.items():
        code2024 = map_2024.get(code2020, code2020)  # unchanged if not in map
        era2024[code2024] = label

    # Haram re-split: add 1580 to era2024, inherits label from source
    for code, label in haram_resplit.items():
        era2024[code] = label

    return pre2020, era2020, era2024


def resolve_city_code(name: str, code_to_label: dict) -> str | None:
    """Find the kommune code in `code_to_label` matching city `name`."""
    target = _normalise_name(name)
    for code, label in code_to_label.items():
        if _normalise_name(label) == target:
            return code
    return None


def build_weighted_distribution(
    era_codes: dict,
    major_weights: dict,
) -> dict:
    """Return {code: weight} with major cities hand-weighted + uniform tail.

    Weights are rounded to 5 decimal places and normalised to sum to 1.0.
    """
    dist = {}
    matched_major_mass = 0.0

    # First: assign major-city weights
    for city_name, weight in major_weights.items():
        code = resolve_city_code(city_name, era_codes)
        if code is None:
            continue
        # If the code already has a weight (e.g. multiple names resolve), take max
        dist[code] = max(dist.get(code, 0.0), weight)
        matched_major_mass += weight

    # Second: remaining mass goes uniform across non-major codes
    remaining = max(0.0, 1.0 - sum(dist.values()))
    tail_codes = [c for c in era_codes if c not in dist]
    if tail_codes and remaining > 0:
        per_code = remaining / len(tail_codes)
        for c in tail_codes:
            dist[c] = round(per_code, 6)

    # Normalise exactly to 1.0 (correct accumulated rounding error)
    total = sum(dist.values())
    if total > 0:
        dist = {c: round(w / total, 6) for c, w in dist.items()}
    # Round pass 2 to force sum ~= 1
    s = sum(dist.values())
    # Distribute rounding residual into the largest entry
    if abs(s - 1.0) > 1e-9 and dist:
        largest_code = max(dist, key=dist.get)
        dist[largest_code] = round(dist[largest_code] + (1.0 - s), 6)

    return dist


def build_labels_union(pre2020: dict, era2020: dict, era2024: dict) -> dict:
    """Return a union of code -> label across all three eras (later eras win ties)."""
    out = {}
    out.update(pre2020)
    out.update(era2020)
    out.update(era2024)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    triples = parse_recode_table(RECODE_2019_TO_2020)
    print(f"# Parsed {len(triples)} recode entries", file=sys.stderr)

    pre2020, era2020, era2024 = build_era_code_sets(
        triples, MAP_2020_TO_2024, HARAM_RESPLIT
    )
    print(f"# Pre-2020 era: {len(pre2020)} codes", file=sys.stderr)
    print(f"# 2020-2023 era: {len(era2020)} codes", file=sys.stderr)
    print(f"# 2024+ era: {len(era2024)} codes", file=sys.stderr)

    # Verify major cities resolve in each era
    print("\n# Major-city lookup verification:", file=sys.stderr)
    for city in ["Oslo", "Bergen", "Halden", "Bærum", "Tromsø", "Drammen"]:
        p = resolve_city_code(city, pre2020)
        e20 = resolve_city_code(city, era2020)
        e24 = resolve_city_code(city, era2024)
        print(f"  {city:15s}: pre={p}  2020={e20}  2024={e24}", file=sys.stderr)

    dist_pre = build_weighted_distribution(pre2020, MAJOR_CITY_WEIGHTS)
    dist_2020 = build_weighted_distribution(era2020, MAJOR_CITY_WEIGHTS)
    dist_2024 = build_weighted_distribution(era2024, MAJOR_CITY_WEIGHTS)

    labels_union = build_labels_union(pre2020, era2020, era2024)
    print(f"# Union labels: {len(labels_union)} codes", file=sys.stderr)

    output = {
        "pre2020_distribution": dist_pre,
        "era2020_distribution": dist_2020,
        "era2024_distribution": dist_2024,
        "labels_union": labels_union,
        "_meta": {
            "pre2020_count": len(pre2020),
            "era2020_count": len(era2020),
            "era2024_count": len(era2024),
            "labels_union_count": len(labels_union),
            "pre2020_sum": round(sum(dist_pre.values()), 6),
            "era2020_sum": round(sum(dist_2020.values()), 6),
            "era2024_sum": round(sum(dist_2024.values()), 6),
        },
    }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    print()


if __name__ == "__main__":
    main()
