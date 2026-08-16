"""
Full syllabus topics & subtopics for the levels/subjects that had NO data:

  - PRIMARY (Kiswahili-medium, muhtasari mpya wa elimu ya msingi):
      Hesabu, Kusoma, Kuandika, Sayansi, Maarifa ya Jamii, Stadi za Kazi,
      Elimu ya Dini, Uchoraji, Muziki, Michezo  → Standards 1-7
  - SECONDARY extras: Bible Knowledge, Islamic Knowledge, French, Arabic → Form 1-4
  - ADVANCED (A-Level): masomo 16 → Form 5-6
  - TECHNICAL / VETA (masomo ya ufundi 36): Electrical Installation, Plumbing,
      Masonry, Carpentry, Welding, Motor Vehicle Mechanics, ICT, n.k.
      → Grade III, Grade II, Grade I, NTA 4, NTA 5, NTA 6

Mpangilio wa topics kwa kila darasa unafuata mtaala wa sasa wa TIE/NECTA.
Inatumiwa na management command `seed_full_syllabus` na data migration
0011_full_syllabus_topics (inaendesha kiotomatiki wakati wa `migrate`).
"""

import importlib as _importlib

PRIMARY_STANDARDS = [
    "Standard 1", "Standard 2", "Standard 3", "Standard 4",
    "Standard 5", "Standard 6", "Standard 7",
]

SECONDARY_FORMS = ["Form 1", "Form 2", "Form 3", "Form 4"]

ADVANCED_FORMS = ["Form 5", "Form 6"]

TECHNICAL_CLASSES = [
    "Grade III", "Grade II", "Grade I",
    "NTA 4 (Basic Certificate)", "NTA 5 (Certificate)", "NTA 6 (Diploma)",
]


def _same_classes(topic_list, classes):
    """Same topic list applied to every class in `classes`."""
    return {c: list(topic_list) for c in classes}


# =============================================================================
# PRIMARY — HESABU (Hisabati)
# =============================================================================

PRIMARY_HESABU = {
    "Standard 1": [
        {"name": "Namba Hadi 100", "order": 1, "subtopics": [
            "Kuhesabu vitu hadi 100",
            "Kutambua namba hadi 100",
            "Kuandika namba kwa tarakimu",
            "Kuandika namba kwa maneno",
            "Kulinganisha na kupanga namba",
            "Namba kabla, baina na baada",
        ]},
        {"name": "Kujumlisha", "order": 2, "subtopics": [
            "Kujumlisha vitu",
            "Kujumlisha namba hadi 20",
            "Kujumlisha kwa njia ya mstari",
            "Matatizo ya maneno ya kujumlisha",
        ]},
        {"name": "Kutoa", "order": 3, "subtopics": [
            "Kutoa vitu",
            "Kutoa namba hadi 20",
            "Kutoa kwa njia ya mstari",
            "Matatizo ya maneno ya kutoa",
        ]},
        {"name": "Vipimo", "order": 4, "subtopics": [
            "Urefu (sentimita na mita)",
            "Uzito (gramu na kilo)",
            "Ujazo (lita)",
            "Wakati (saa, siku, wiki na miezi)",
        ]},
        {"name": "Pesa", "order": 5, "subtopics": [
            "Sarafu za Tanzania",
            "Noti za Tanzania",
            "Kuhesabu pesa",
            "Kubadilisha pesa",
        ]},
        {"name": "Jiometri", "order": 6, "subtopics": [
            "Maumbo ya kawaida (mduara, mraba, pembetatu, mstatili)",
            "Kuchora maumbo rahisi",
            "Nafasi (juu, chini, mbele, nyuma)",
        ]},
    ],
    "Standard 2": [
        {"name": "Namba Hadi 1000", "order": 1, "subtopics": [
            "Kuhesabu vitu hadi 1000",
            "Kutambua na kuandika namba hadi 1000",
            "Thamani ya nafasi (moja, kumi, mia)",
            "Kulinganisha na kupanga namba",
            "Namba za Kirumi (I hadi XX)",
        ]},
        {"name": "Kujumlisha na Kutoa", "order": 2, "subtopics": [
            "Kujumlisha namba zenye tarakimu 3",
            "Kutoa namba zenye tarakimu 3",
            "Kujumlisha na kutoa kwa kukopa",
            "Matatizo ya maneno",
        ]},
        {"name": "Kuzidisha", "order": 3, "subtopics": [
            "Majedwali ya kuzidisha (2 hadi 5)",
            "Kuzidisha kwa namba ya tarakimu moja",
            "Kuzidisha kwa njia ya mstari",
            "Matatizo ya maneno ya kuzidisha",
        ]},
        {"name": "Kugawanya", "order": 4, "subtopics": [
            "Kugawanya vitu kwa usawa",
            "Kugawanya kwa majedwali (2 hadi 5)",
            "Kugawanya kwa namba ya tarakimu moja",
            "Matatizo ya maneno ya kugawanya",
        ]},
        {"name": "Sehemu", "order": 5, "subtopics": [
            "Dhana ya sehemu (nusu, robo, theluthi)",
            "Kutambua sehemu katika vitu",
            "Kulinganisha sehemu rahisi",
            "Sehemu sawa",
        ]},
        {"name": "Vipimo", "order": 6, "subtopics": [
            "Urefu (mita na kilometa)",
            "Uzito (kilo na tani)",
            "Ujazo (lita na mililita)",
            "Wakati (saa, dakika, sekunde)",
            "Kalenda (siku, wiki, miezi, mwaka)",
        ]},
        {"name": "Pesa", "order": 7, "subtopics": [
            "Kujumlisha pesa",
            "Kutoa pesa",
            "Kubadilisha fedha",
            "Manunuzi na mabadiliko",
        ]},
        {"name": "Jiometri", "order": 8, "subtopics": [
            "Maumbo ya 2D na sifa zake",
            "Maumbo ya 3D (mchemraba, piramidi)",
            "Mistari (nyoofu, mlalo, wima)",
            "Mwelekeo (kaskazini, kusini, mashariki, magharibi)",
        ]},
    ],
    "Standard 3": [
        {"name": "Namba Hadi 100000", "order": 1, "subtopics": [
            "Kuhesabu na kuandika namba hadi 100000",
            "Thamani ya nafasi (hadi makumi elfu)",
            "Kulinganisha na kupanga namba",
            "Namba za Kirumi (hadi C)",
            "Kujumlisha na kutoa namba kubwa",
        ]},
        {"name": "Kuzidisha", "order": 2, "subtopics": [
            "Majedwali ya kuzidisha (2 hadi 12)",
            "Kuzidisha namba ya tarakimu 2 kwa tarakimu 1",
            "Kuzidisha namba ya tarakimu 3 kwa tarakimu 1",
            "Matatizo ya maneno ya kuzidisha",
        ]},
        {"name": "Kugawanya", "order": 3, "subtopics": [
            "Kugawanya namba za tarakimu 2 na 3",
            "Kugawanya kwa tarakimu moja",
            "Mgawanyiko wenye baki",
            "Matatizo ya maneno ya kugawanya",
        ]},
        {"name": "Sehemu", "order": 4, "subtopics": [
            "Sehemu sawa na tofauti",
            "Kujumlisha sehemu zenye madhehebu sawa",
            "Kutoa sehemu zenye madhehebu sawa",
            "Kubadilisha sehemu kuwa namba nzima",
            "Kulinganisha na kupanga sehemu",
        ]},
        {"name": "Desimali", "order": 5, "subtopics": [
            "Dhana ya desimali (tenths, hundredths)",
            "Kuandika na kusoma desimali",
            "Kujumlisha na kutoa desimali",
            "Kubadilisha sehemu kuwa desimali",
        ]},
        {"name": "Asilimia", "order": 6, "subtopics": [
            "Dhana ya asilimia",
            "Kuandika asilimia kwa ishara (%)",
            "Asilimia za rahisi (50%, 25%, 10%)",
            "Kubadilisha asilimia kuwa sehemu",
        ]},
        {"name": "Vipimo", "order": 7, "subtopics": [
            "Kubadilisha vitengo vya urefu",
            "Kubadilisha vitengo vya uzito",
            "Kubadilisha vitengo vya ujazo",
            "Eneo la mraba na mstatili",
            "Mzunguko wa maumbo",
        ]},
        {"name": "Takwimu", "order": 8, "subtopics": [
            "Kukusanya data",
            "Kupanga data kwenye jedwali",
            "Kusoma na kutengeneza grafu rahisi",
        ]},
        {"name": "Jiometri", "order": 9, "subtopics": [
            "Pembe (nyoofu, kali, butu)",
            "Mistari sambamba na inayokatiza",
            "Maumbo ya 3D na sifa zake",
            "Kupima mzunguko",
        ]},
    ],
    "Standard 4": [
        {"name": "Namba Hadi Milioni", "order": 1, "subtopics": [
            "Kuhesabu na kuandika namba hadi milioni",
            "Thamani ya nafasi (hadi mamia ya maelfu)",
            "Kulinganisha na kupanga namba kubwa",
            "Namba za Kirumi (hadi M)",
            "Kujumlisha na kutoa namba kubwa",
        ]},
        {"name": "Kuzidisha na Kugawanya", "order": 2, "subtopics": [
            "Kuzidisha namba ya tarakimu 3 kwa tarakimu 2",
            "Kugawanya namba ya tarakimu 3 kwa tarakimu 2",
            "Kuzidisha na kugawanya kwa 10, 100, 1000",
            "Matatizo ya maneno",
        ]},
        {"name": "Sehemu", "order": 3, "subtopics": [
            "Kujumlisha sehemu zenye madhehebu tofauti",
            "Kutoa sehemu zenye madhehebu tofauti",
            "Kuzidisha sehemu",
            "Kugawanya sehemu",
            "Sehemu mchanganyiko na zisizofaa",
        ]},
        {"name": "Desimali", "order": 4, "subtopics": [
            "Kujumlisha na kutoa desimali",
            "Kuzidisha desimali",
            "Kugawanya desimali",
            "Kubadilisha desimali kuwa sehemu na kinyume",
        ]},
        {"name": "Asilimia", "order": 5, "subtopics": [
            "Kubadilisha asilimia kuwa sehemu na desimali",
            "Kukokotoa asilimia ya kiasi",
            "Pato na hasara (rahisi)",
            "Asilimia katika biashara",
        ]},
        {"name": "Uwiano", "order": 6, "subtopics": [
            "Dhana ya uwiano",
            "Uwiano sawa",
            "Kugawanya kiasi kwa uwiano",
            "Matatizo ya maneno ya uwiano",
        ]},
        {"name": "Vipimo", "order": 7, "subtopics": [
            "Eneo la pembetatu",
            "Eneo la mraba na mstatili",
            "Mzunguko wa maumbo",
            "Kubadilisha vitengo vya kipimo",
        ]},
        {"name": "Takwimu", "order": 8, "subtopics": [
            "Kukusanya na kupanga data",
            "Grafu za pau na mchoro",
            "Kusoma data kwenye grafu",
            "Wastani (rahisi)",
        ]},
        {"name": "Jiometri", "order": 9, "subtopics": [
            "Pembe na aina zake",
            "Kupima pembe kwa kipimo cha pembe",
            "Mistari sambamba na pembeni",
            "Maumbo ya 3D (mchemraba, silinda, koni)",
        ]},
    ],
    "Standard 5": [
        {"name": "Namba", "order": 1, "subtopics": [
            "Namba kamili na namba hasi",
            "Kujumlisha na kutoa namba hasi",
            "Namba za desimali na sehemu (kina)",
            "Mpangilio wa namba",
        ]},
        {"name": "Sehemu na Desimali", "order": 2, "subtopics": [
            "Kuzidisha na kugawanya sehemu (kina)",
            "Kuzidisha na kugawanya desimali",
            "Kubadilisha sehemu, desimali na asilimia",
            "Matatizo ya maneno",
        ]},
        {"name": "Asilimia", "order": 3, "subtopics": [
            "Kukokotoa asilimia ya kiasi",
            "Pato, hasara na punguzo",
            "Riba rahisi",
            "Asilimia katika mazingira halisi",
        ]},
        {"name": "Uwiano na Mlinganyo", "order": 4, "subtopics": [
            "Uwiano wa moja kwa moja",
            "Uwiano kinyume",
            "Mizani (scale)",
            "Matatizo ya maneno ya uwiano",
        ]},
        {"name": "Aljebra", "order": 5, "subtopics": [
            "Milinganyo rahisi ya aljebra",
            "Kujumlisha na kutoa mitajo ya aljebra",
            "Kuzidisha mitajo ya aljebra",
            "Kutatua milinganyo ya mstari",
        ]},
        {"name": "Vipimo", "order": 6, "subtopics": [
            "Eneo la maumbo mbalimbali",
            "Mzunguko wa maumbo",
            "Ujazo wa mchemraba na mstatili",
            "Kubadilisha vitengo vya kipimo",
        ]},
        {"name": "Takwimu", "order": 7, "subtopics": [
            "Kukusanya data kwa utafiti mdogo",
            "Jedwali la masafa",
            "Grafu za pau, mchoro na mstari",
            "Wastani, wastani wa kati na modi",
        ]},
        {"name": "Jiometri", "order": 8, "subtopics": [
            "Pembe kwenye mstari na pointi",
            "Mistari sambamba na pembe zinazofanana",
            "Ulinganifu wa maumbo",
            "Maumbo ya 3D na mipasuko yake",
        ]},
        {"name": "Pesa na Biashara", "order": 9, "subtopics": [
            "Faida na hasara",
            "Punguzo na ongezeko",
            "Akiba na benki",
            "Bajeti rahisi",
        ]},
    ],
    "Standard 6": [
        {"name": "Namba", "order": 1, "subtopics": [
            "Namba kamili na namba hasi (kina)",
            "Namba za desimali (kina)",
            "Vipeo (mraba na mchemraba)",
            "Mizizi ya mraba na mchemraba",
        ]},
        {"name": "Sehemu, Desimali na Asilimia", "order": 2, "subtopics": [
            "Kubadilisha kati ya sehemu, desimali na asilimia",
            "Kukokotoa kwa sehemu (kina)",
            "Asilimia katika biashara na riba",
            "Matatizo ya maneno",
        ]},
        {"name": "Uwiano na Mlinganyo", "order": 3, "subtopics": [
            "Uwiano wa moja kwa moja na kinyume",
            "Mizani katika ramani",
            "Kugawanya kwa uwiano",
            "Matatizo ya maneno",
        ]},
        {"name": "Aljebra", "order": 4, "subtopics": [
            "Milinganyo ya mstari (kina)",
            "Kujumlisha, kutoa, kuzidisha na kugawanya mitajo",
            "Kutatua matatizo kwa kutumia aljebra",
            "Ushahidi wa fomula rahisi",
        ]},
        {"name": "Jiometri", "order": 5, "subtopics": [
            "Pembe kwenye duara",
            "Eneo na mzunguko wa duara",
            "Mistari sambamba na pembeni (kina)",
            "Ulinganifu na mabadiliko (rahisi)",
        ]},
        {"name": "Vipimo", "order": 6, "subtopics": [
            "Eneo la maumbo ya mchanganyiko",
            "Ujazo wa maumbo ya 3D",
            "Kubadilisha vitengo vya kipimo",
            "Kipimo cha muda na umbali (kasi)",
        ]},
        {"name": "Takwimu", "order": 7, "subtopics": [
            "Kukusanya na kuchambua data",
            "Jedwali la masafa (kina)",
            "Grafu na mchanganuo wake",
            "Wastani, wastani wa kati na modi",
            "Uwezekano rahisi",
        ]},
        {"name": "Pesa, Benki na Biashara", "order": 8, "subtopics": [
            "Riba na akiba",
            "Mikopo na rehani (rahisi)",
            "Bajeti na usimamizi wa fedha",
            "Malipo kwa njia za kisasa (rahisi)",
        ]},
    ],
    "Standard 7": [
        {"name": "Namba", "order": 1, "subtopics": [
            "Mapitio ya namba kamili na hasi",
            "Vipeo na mizizi (kina)",
            "Mpangilio na ulinganifu wa namba",
            "Namba za Kirumi",
        ]},
        {"name": "Sehemu, Desimali na Asilimia", "order": 2, "subtopics": [
            "Mapitio ya sehemu na desimali",
            "Asilimia katika biashara (faida, hasara, riba)",
            "Kubadilisha kati ya aina za namba",
            "Matatizo ya maneno ya mtihani",
        ]},
        {"name": "Uwiano, Mlinganyo na Mizani", "order": 3, "subtopics": [
            "Mapitio ya uwiano",
            "Milinganyo ya mstari",
            "Mizani na ramani",
            "Matatizo ya maneno ya mtihani",
        ]},
        {"name": "Aljebra", "order": 4, "subtopics": [
            "Milinganyo na mitajo (kina)",
            "Kutatua milinganyo yenye mabano",
            "Matumizi ya aljebra katika maisha",
        ]},
        {"name": "Jiometri", "order": 5, "subtopics": [
            "Mapitio ya pembe na mistari",
            "Eneo, mzunguko na ujazo",
            "Maumbo ya 3D",
            "Ulinganifu na mabadiliko",
        ]},
        {"name": "Takwimu", "order": 6, "subtopics": [
            "Kukusanya na kuchambua data",
            "Grafu mbalimbali",
            "Wastani, wastani wa kati na modi",
            "Uwezekano",
        ]},
        {"name": "Pesa na Biashara", "order": 7, "subtopics": [
            "Riba, akiba na mikopo",
            "Bajeti na usimamizi wa fedha",
            "Biashara ndogo ndogo",
        ]},
        {"name": "Mazoezi ya Mtihani wa Taifa", "order": 8, "subtopics": [
            "Mazoezi ya maswali ya PSLE (Hesabu)",
            "Kutatua matatizo ya maneno",
            "Udhibiti wa muda katika mtihani",
        ]},
    ],
}


# =============================================================================
# PRIMARY — KUSOMA
# =============================================================================

PRIMARY_KUSOMA = {
    "Standard 1": [
        {"name": "Kutambua Herufi", "order": 1, "subtopics": [
            "Kutambua herufi za alfabeti (A-Z, a-z)",
            "Kutamka herufi kwa sauti sahihi",
            "Kutofautisha herufi kubwa na ndogo",
            "Kutambua sauti za vokali na konsonanti",
        ]},
        {"name": "Kusoma Silabi", "order": 2, "subtopics": [
            "Kuunganisha herufi kuunda silabi",
            "Kusoma silabi za vokali (ba, be, bi, bo, bu)",
            "Kusoma silabi za konsonanti",
            "Kutengeneza maneno kutoka silabi",
        ]},
        {"name": "Kusoma Maneno", "order": 3, "subtopics": [
            "Kusoma maneno ya silabi moja",
            "Kusoma maneno ya silabi mbili",
            "Kusoma maneno ya kila siku",
            "Kusoma majina ya vitu",
        ]},
        {"name": "Kusoma Sentensi Fupi", "order": 4, "subtopics": [
            "Kusoma sentensi fupi",
            "Kusoma vifungu vya maneno",
            "Kuelewa maana ya sentensi",
            "Kusoma kwa sauti na kwa ukimya",
        ]},
        {"name": "Kusoma Hadithi Fupi", "order": 5, "subtopics": [
            "Kusoma hadithi fupi za picha",
            "Kujibu maswali rahisi kutoka kwa hadithi",
            "Kusimulia hadithi kwa maneno yake",
        ]},
    ],
    "Standard 2": [
        {"name": "Kusoma Maneno", "order": 1, "subtopics": [
            "Kusoma maneno ya silabi tatu",
            "Kusoma maneno ya silabi nne",
            "Kutambua maana ya maneno",
            "Kusoma maneno ya matumizi ya kila siku",
        ]},
        {"name": "Kusoma Sentensi", "order": 2, "subtopics": [
            "Kusoma sentensi kamili",
            "Kusoma sentensi za maelekezo",
            "Kusoma sentensi za maswali na majibu",
            "Kusoma kwa ufasaha",
        ]},
        {"name": "Kusoma Vifungu Fupi", "order": 3, "subtopics": [
            "Kusoma vifungu vya sentensi 3-5",
            "Kutambua wazo kuu la kifungu",
            "Kujibu maswali ya ufahamu rahisi",
            "Kusimulia kile kilichosomwa",
        ]},
        {"name": "Ufahamu Rahisi", "order": 4, "subtopics": [
            "Kusikiliza na kuelewa hadithi",
            "Kujibu maswali ya ufahamu",
            "Kutambua mhusika na matukio",
            "Kueleza mfuatano wa matukio",
        ]},
        {"name": "Kusoma kwa Sauti", "order": 5, "subtopics": [
            "Kusoma kwa sauti na matamshi sahihi",
            "Kusoma kwa mwendo unaofaa",
            "Kutumia viimbo sahihi",
            "Kusoma mbele ya wengine",
        ]},
    ],
    "Standard 3": [
        {"name": "Kusoma kwa Ufasaha", "order": 1, "subtopics": [
            "Kusoma kwa mwendo unaofaa",
            "Kusoma kwa matamshi sahihi",
            "Kusoma kwa maana",
            "Kusoma kwa ukimya na kwa sauti",
        ]},
        {"name": "Kusoma Vifungu", "order": 2, "subtopics": [
            "Kusoma vifungu virefu",
            "Kutambua mawazo makuu",
            "Kutambua maelezo ya ziada",
            "Kujibu maswali ya ufahamu",
        ]},
        {"name": "Ufahamu wa Kusoma", "order": 3, "subtopics": [
            "Kusoma na kuelewa hadithi",
            "Kusoma na kuelewa maelezo",
            "Kujibu maswali kwa sentensi kamili",
            "Kufanya utabiri kutoka kwa maandishi",
        ]},
        {"name": "Msamiati na Maana", "order": 4, "subtopics": [
            "Kutambua maana ya maneno mapya",
            "Kutumia maneno katika sentensi",
            "Visawe na kinyume maana",
            "Nahau na methali rahisi",
        ]},
        {"name": "Kusoma Aina Mbalimbali", "order": 5, "subtopics": [
            "Kusoma habari za magazeti",
            "Kusoma matangazo",
            "Kusoma barua",
            "Kusoma taarifa rahisi",
        ]},
    ],
    "Standard 4": [
        {"name": "Ufasaha na Matamshi", "order": 1, "subtopics": [
            "Kusoma kwa ufasaha wa hali ya juu",
            "Kutamka maneno kwa usahihi",
            "Kusoma kwa viimbo na lafudhi",
            "Kusoma kwa kasi inayofaa",
        ]},
        {"name": "Ufahamu wa Kina", "order": 2, "subtopics": [
            "Kusoma na kuelewa vifungu virefu",
            "Kutambua wazo kuu na maelezo ya ziada",
            "Kujibu maswali ya ufahamu kwa kina",
            "Kufupisha maandishi (rahisi)",
        ]},
        {"name": "Kusoma Fasihi", "order": 3, "subtopics": [
            "Kusoma hadithi na ngano",
            "Kusoma mashairi",
            "Kutambua wahusika na sifa zao",
            "Kujadili maudhui ya kazi ya fasihi",
        ]},
        {"name": "Kusoma Taarifa", "order": 4, "subtopics": [
            "Kusoma ripoti na taarifa",
            "Kusoma maelekezo na kanuni",
            "Kusoma habari za gazeti",
            "Kutambua tofauti kati ya ukweli na maoni",
        ]},
        {"name": "Msamiati", "order": 5, "subtopics": [
            "Kujenga msamiati mpya",
            "Matumizi ya kamusi",
            "Visawe, kinyume maana na viunganishi",
            "Nahau na vitendawili",
        ]},
    ],
    "Standard 5": [
        {"name": "Ufahamu wa Kina", "order": 1, "subtopics": [
            "Kusoma vifungu na kuelewa kwa kina",
            "Kutambua wazo kuu, maelezo na hitimisho",
            "Kujibu maswali ya uchambuzi",
            "Kufupisha maandishi",
        ]},
        {"name": "Uchambuzi wa Maandishi", "order": 2, "subtopics": [
            "Kuchambua muundo wa maandishi",
            "Kutambua madhumuni ya mwandishi",
            "Kutathmini maandishi",
            "Kulinganisha maandishi mawili",
        ]},
        {"name": "Kusoma Fasihi", "order": 3, "subtopics": [
            "Kusoma hadithi fupi na riwaya",
            "Kusoma mashairi na tamthilia",
            "Kuchambua wahusika na maudhui",
            "Kujadili mbinu za kisanii",
        ]},
        {"name": "Kusoma kwa Madhumuni", "order": 4, "subtopics": [
            "Kusoma kwa burudani",
            "Kusoma kwa kupata taarifa",
            "Kusoma kwa kujifunza",
            "Kusoma kwa kufuata maelekezo",
        ]},
        {"name": "Msamiati na Lugha", "order": 5, "subtopics": [
            "Kujenga msamiati wa kitaaluma",
            "Matumizi ya kamusi (kina)",
            "Nahau, methali na misemo",
            "Semi za Kiswahili",
        ]},
    ],
    "Standard 6": [
        {"name": "Ufahamu wa Makala", "order": 1, "subtopics": [
            "Kusoma makala na ripoti",
            "Kutambua wazo kuu na hoja",
            "Kujibu maswali ya uchambuzi",
            "Kufupisha makala",
        ]},
        {"name": "Uchambuzi wa Fasihi", "order": 2, "subtopics": [
            "Kusoma riwaya na tamthilia",
            "Kuchambua maudhui na wahusika",
            "Kutambua mbinu za kisanii",
            "Kutoa maoni kuhusu kazi ya fasihi",
        ]},
        {"name": "Ufupisho", "order": 3, "subtopics": [
            "Kufupisha vifungu virefu",
            "Kutambua mawazo makuu",
            "Kuandika kwa maneno yako",
            "Kufupisha kwa kiwango kinachohitajika",
        ]},
        {"name": "Kusoma kwa Madhumuni Mbalimbali", "order": 4, "subtopics": [
            "Kusoma kwa utafiti",
            "Kusoma kwa burudani",
            "Kusoma kwa kuthamini fasihi",
            "Kusoma kwa kujenga ujuzi",
        ]},
        {"name": "Lugha na Msamiati", "order": 5, "subtopics": [
            "Matumizi ya istilahi",
            "Nahau, methali, misemo na vitendawili",
            "Maana za maneno katika muktadha",
            "Uboreshaji wa matamshi",
        ]},
    ],
    "Standard 7": [
        {"name": "Mapitio ya Ufahamu", "order": 1, "subtopics": [
            "Mapitio ya ufahamu wa aina zote",
            "Kujibu maswali ya mtihani wa taifa",
            "Kufupisha maandishi",
            "Kusoma kwa kasi na usahihi",
        ]},
        {"name": "Ufahamu wa Mtihani wa Taifa", "order": 2, "subtopics": [
            "Mazoezi ya ufahamu wa PSLE",
            "Kusoma na kuchambua maswali",
            "Kuandika majibu kwa usahihi",
            "Udhibiti wa muda",
        ]},
        {"name": "Uchambuzi wa Fasihi", "order": 3, "subtopics": [
            "Kuchambua riwaya, tamthilia na mashairi",
            "Kutambua mbinu za kisanii",
            "Kujadili maudhui ya kazi",
            "Kuandika uhakiki rahisi",
        ]},
        {"name": "Msamiati na Lugha", "order": 4, "subtopics": [
            "Mapitio ya nahau, methali na misemo",
            "Matumizi ya kamusi",
            "Maana za maneno katika muktadha",
            "Istilahi za kitaaluma",
        ]},
        {"name": "Usomaji Bora", "order": 5, "subtopics": [
            "Kusoma kwa ufasaha wa juu",
            "Kusoma kwa madhumuni mbalimbali",
            "Kusoma kwa furaha na thamani",
            "Kuwa msomaji bora wa maisha",
        ]},
    ],
}


# =============================================================================
# PRIMARY — KUANDIKA
# =============================================================================

PRIMARY_KUANDIKA = {
    "Standard 1": [
        {"name": "Kuandika Herufi", "order": 1, "subtopics": [
            "Kushika penseli kwa usahihi",
            "Kuandika herufi kubwa (A-Z)",
            "Kuandika herufi ndogo (a-z)",
            "Kuandika kwa mwandiko mzuri",
        ]},
        {"name": "Kuandika Namba", "order": 2, "subtopics": [
            "Kuandika namba 0-9",
            "Kuandika namba hadi 100",
            "Kuandika namba kwa maneno",
        ]},
        {"name": "Kuandika Maneno", "order": 3, "subtopics": [
            "Kuandika maneno ya silabi moja",
            "Kuandika maneno ya silabi mbili",
            "Kuandika majina ya vitu",
            "Tahajia sahihi ya maneno",
        ]},
        {"name": "Kuandika Sentensi Fupi", "order": 4, "subtopics": [
            "Kuandika sentensi fupi",
            "Kuanza sentensi kwa herufi kubwa",
            "Kutumia nukta mwishoni",
            "Kuandika vifungu vya maneno",
        ]},
    ],
    "Standard 2": [
        {"name": "Uandishi wa Maneno", "order": 1, "subtopics": [
            "Kuandika maneno ya silabi tatu na nne",
            "Tahajia sahihi",
            "Kuandika maneno ya kila siku",
            "Kuongeza herufi mwanzo na mwisho",
        ]},
        {"name": "Uandishi wa Sentensi", "order": 2, "subtopics": [
            "Kuandika sentensi kamili",
            "Kuandika sentensi za aina mbalimbali",
            "Matumizi ya alama za uakifishaji (rahisi)",
            "Kuandika kwa mpangilio",
        ]},
        {"name": "Tahajia", "order": 3, "subtopics": [
            "Kutahajia maneno kwa usahihi",
            "Kutambua na kurekebisha makosa ya tahajia",
            "Kuandika maneno kwa kumbukumbu",
        ]},
        {"name": "Kuandika Vifungu Fupi", "order": 4, "subtopics": [
            "Kuandika vifungu vya sentensi 2-3",
            "Kuandika maelezo mafupi",
            "Kuandika barua fupi ya kirafiki",
            "Kuandika kadi ya mwaliko",
        ]},
    ],
    "Standard 3": [
        {"name": "Sentensi Kamili", "order": 1, "subtopics": [
            "Kuandika sentensi kamili na sahihi",
            "Kuandika aina za sentensi",
            "Matumizi ya alama za uakifishaji",
            "Kutengeneza sentensi kwa maneno",
        ]},
        {"name": "Aya Fupi", "order": 2, "subtopics": [
            "Dhana ya aya",
            "Kuandika aya fupi",
            "Kuandika aya kwa mpangilio wa matukio",
            "Kutambua wazo kuu la aya",
        ]},
        {"name": "Tahajia na Sarufi", "order": 3, "subtopics": [
            "Tahajia sahihi ya maneno",
            "Nomino na vitenzi (rahisi)",
            "Kurekebisha makosa ya tahajia",
            "Matumizi ya herufi kubwa",
        ]},
        {"name": "Uandishi wa Maelezo Mafupi", "order": 4, "subtopics": [
            "Kuandika maelezo kuhusu mtu",
            "Kuandika maelezo kuhusu kitu",
            "Kuandika maelezo kuhusu tukio",
            "Kuandika taarifa fupi",
        ]},
    ],
    "Standard 4": [
        {"name": "Uandishi wa Aya", "order": 1, "subtopics": [
            "Kuandika aya kamili",
            "Mpangilio wa mawazo katika aya",
            "Kuunganisha aya kuwa taarifa",
            "Matumizi ya viunganishi",
        ]},
        {"name": "Insha Fupi", "order": 2, "subtopics": [
            "Insha za maelezo",
            "Insha za simulizi",
            "Sehemu za insha (utangulizi, kiini, hitimisho)",
            "Kuandika insha kwa mpangilio",
        ]},
        {"name": "Barua za Kirafiki", "order": 3, "subtopics": [
            "Sehemu za barua ya kirafiki",
            "Kuandika barua ya kirafiki",
            "Kuandika barua ya kumwalika",
            "Kuandika barua ya kuomba radhi",
        ]},
        {"name": "Tahajia na Sarufi", "order": 4, "subtopics": [
            "Tahajia sahihi",
            "Nomino, vitenzi, vivumishi na vielezi",
            "Ngeli za nomino (rahisi)",
            "Kurekebisha makosa ya lugha",
        ]},
        {"name": "Muhtasari", "order": 5, "subtopics": [
            "Dhana ya muhtasari",
            "Kutambua mawazo makuu",
            "Kuandika muhtasari mfupi",
        ]},
    ],
    "Standard 5": [
        {"name": "Insha za Kina", "order": 1, "subtopics": [
            "Insha za maelezo (kina)",
            "Insha za simulizi (kina)",
            "Insha za kubuni",
            "Kuandika insha bora",
        ]},
        {"name": "Barua Rasmi na Kirafiki", "order": 2, "subtopics": [
            "Barua rasmi (sehemu na muundo)",
            "Barua ya kirafiki (kina)",
            "Kuandika barua ya maombi",
            "Kuandika barua ya kukaribisha",
        ]},
        {"name": "Ripoti Fupi", "order": 3, "subtopics": [
            "Dhana ya ripoti",
            "Sehemu za ripoti",
            "Kuandika ripoti ya shughuli",
            "Kuandika taarifa ya tukio",
        ]},
        {"name": "Sarufi", "order": 4, "subtopics": [
            "Ngeli za nomino",
            "Nyakati za vitenzi",
            "Viunganishi na vihusishi",
            "Uundaji wa maneno (rahisi)",
        ]},
        {"name": "Tahajia na Uakifishaji", "order": 5, "subtopics": [
            "Tahajia sahihi ya maneno magumu",
            "Alama za uakifishaji (kina)",
            "Kurekebisha makosa",
        ]},
    ],
    "Standard 6": [
        {"name": "Insha za Hoja", "order": 1, "subtopics": [
            "Dhana ya insha ya hoja",
            "Kuandika hoja zenye ushahidi",
            "Kuandika insha ya kukubaliana",
            "Kuandika insha ya kupinga",
        ]},
        {"name": "Makala", "order": 2, "subtopics": [
            "Dhana ya makala",
            "Sehemu za makala",
            "Kuandika makala kuhusu mada",
            "Kuchapisha makala (rahisi)",
        ]},
        {"name": "Barua Rasmi", "order": 3, "subtopics": [
            "Kuandika barua rasmi kamili",
            "Barua ya maombi ya kazi",
            "Barua ya kufuta makosa",
            "Barua kwa mamlaka",
        ]},
        {"name": "Muhtasari", "order": 4, "subtopics": [
            "Kuandika muhtasari wa vifungu",
            "Kuandika muhtasari wa hadithi",
            "Kuandika muhtasari kwa kiwango kinachohitajika",
        ]},
        {"name": "Sarufi ya Kina", "order": 5, "subtopics": [
            "Ngeli za nomino (kina)",
            "Unyambuaji na utohoaji wa maneno",
            "Matumizi sahihi ya lugha",
            "Kurekebisha makosa ya kisarufi",
        ]},
    ],
    "Standard 7": [
        {"name": "Mapitio ya Insha", "order": 1, "subtopics": [
            "Mapitio ya aina zote za insha",
            "Kuandika insha bora ya mtihani",
            "Mpangilio wa mawazo",
            "Udhibiti wa muda katika mtihani",
        ]},
        {"name": "Insha za Mtihani wa Taifa", "order": 2, "subtopics": [
            "Mazoezi ya insha za PSLE",
            "Kuchambua mada ya insha",
            "Kuandika utangulizi, kiini na hitimisho",
            "Kusahihisha kazi yako",
        ]},
        {"name": "Uandishi wa Taarifa", "order": 3, "subtopics": [
            "Kuandika taarifa kamili",
            "Kuandika ripoti",
            "Kuandika makala",
            "Kuandika barua rasmi za mtihani",
        ]},
        {"name": "Sarufi Kamili", "order": 4, "subtopics": [
            "Mapitio ya ngeli",
            "Mapitio ya nyakati",
            "Uundaji wa maneno",
            "Matumizi sahihi ya lugha",
        ]},
        {"name": "Muhtasari wa Mwisho", "order": 5, "subtopics": [
            "Muhtasari wa vifungu",
            "Muhtasari wa hadithi",
            "Kuandika kwa usahihi na uzuri",
        ]},
    ],
}


# =============================================================================
# PRIMARY — SAYANSI NA TEKNOLOJIA
# =============================================================================

PRIMARY_SAYANSI = {
    "Standard 1": [
        {"name": "Mwili Wangu", "order": 1, "subtopics": [
            "Sehemu za mwili",
            "Majukumu ya sehemu za mwili",
            "Kutunza mwili (usafi)",
            "Kujitambua (jinsia)",
        ]},
        {"name": "Afya na Usafi", "order": 2, "subtopics": [
            "Usafi wa mwili",
            "Usafi wa mazingira",
            "Chakula na lishe (rahisi)",
            "Magonjwa ya kawaida na kujikinga",
        ]},
        {"name": "Mazingira", "order": 3, "subtopics": [
            "Mazingira ya nyumbani na shuleni",
            "Kutunza mazingira",
            "Uchafuzi wa mazingira (rahisi)",
        ]},
        {"name": "Mimea na Wanyama", "order": 4, "subtopics": [
            "Sehemu za mimea",
            "Aina za wanyama",
            "Makazi ya viumbe",
            "Kutunza mimea na wanyama",
        ]},
        {"name": "Maji", "order": 5, "subtopics": [
            "Umuhimu wa maji",
            "Vyanzo vya maji",
            "Kutunza maji safi",
        ]},
        {"name": "Hewa na Nishati", "order": 6, "subtopics": [
            "Dhana ya hewa",
            "Umuhimu wa hewa",
            "Nishati ya jua na upepo",
        ]},
    ],
    "Standard 2": [
        {"name": "Mwili wa Binadamu", "order": 1, "subtopics": [
            "Sehemu za mwili na majukumu yake",
            "Fahamu (kuona, kusikia, kunusa, kuonja, kugusa)",
            "Kutunza fahamu",
        ]},
        {"name": "Usafi na Afya", "order": 2, "subtopics": [
            "Usafi wa mwili na mazingira",
            "Lishe bora",
            "Magonjwa ya kuambukiza na kujikinga",
            "Chanjo",
        ]},
        {"name": "Mimea", "order": 3, "subtopics": [
            "Sehemu za mimea na majukumu",
            "Ukuaji wa mimea",
            "Umuhimu wa mimea",
            "Kutunza mimea",
        ]},
        {"name": "Wanyama", "order": 4, "subtopics": [
            "Aina za wanyama",
            "Makazi ya wanyama",
            "Wanyama wenye faida na madhara",
            "Kutunza wanyama",
        ]},
        {"name": "Maji", "order": 5, "subtopics": [
            "Umuhimu wa maji",
            "Vyanzo vya maji",
            "Usafishaji wa maji (rahisi)",
            "Kutunza maji",
        ]},
        {"name": "Hewa na Nishati", "order": 6, "subtopics": [
            "Sifa za hewa",
            "Umuhimu wa hewa kwa viumbe",
            "Nishati ya jua, upepo na maji",
        ]},
    ],
    "Standard 3": [
        {"name": "Mifumo ya Mwili", "order": 1, "subtopics": [
            "Mfumo wa mifupa",
            "Mfumo wa misuli",
            "Mfumo wa upumuaji",
            "Mfumo wa mzunguko wa damu",
        ]},
        {"name": "Lishe", "order": 2, "subtopics": [
            "Aina za vyakula",
            "Virutubisho na umuhimu wake",
            "Mlo kamili",
            "Utapiamlo na athari zake",
        ]},
        {"name": "Mimea", "order": 3, "subtopics": [
            "Ukuaji na usambazaji wa mimea",
            "Umuhimu wa mimea kwa viumbe",
            "Kuhifadhi mimea",
        ]},
        {"name": "Wanyama", "order": 4, "subtopics": [
            "Aina za wanyama (kina)",
            "Mwendo wa wanyama",
            "Mahusiano kati ya viumbe",
        ]},
        {"name": "Hali ya Hewa", "order": 5, "subtopics": [
            "Vipengele vya hali ya hewa",
            "Joto, mvua na upepo",
            "Mabadiliko ya hali ya hewa (rahisi)",
        ]},
        {"name": "Umeme", "order": 6, "subtopics": [
            "Dhana ya umeme",
            "Vyanzo vya umeme",
            "Matumizi salama ya umeme",
        ]},
        {"name": "Sumaku", "order": 7, "subtopics": [
            "Dhana ya sumaku",
            "Sifa za sumaku",
            "Matumizi ya sumaku",
        ]},
        {"name": "Mwendo", "order": 8, "subtopics": [
            "Dhana ya mwendo",
            "Aina za mwendo",
            "Nguvu na mwendo (rahisi)",
        ]},
    ],
    "Standard 4": [
        {"name": "Mifumo ya Mwili", "order": 1, "subtopics": [
            "Mfumo wa mmeng'enyo wa chakula",
            "Mfumo wa fahamu",
            "Mfumo wa mkojo",
            "Mfumo wa uzazi (rahisi)",
        ]},
        {"name": "Magonjwa", "order": 2, "subtopics": [
            "Magonjwa ya kuambukiza",
            "Magonjwa yasiyoambukiza",
            "Njia za maambukizi na kujikinga",
            "Dawa na matumizi yake",
        ]},
        {"name": "Mimea", "order": 3, "subtopics": [
            "Mimea inayotengeneza chakula chake",
            "Uoto wa mimea",
            "Umuhimu wa mimea kwa mazingira",
        ]},
        {"name": "Wanyama", "order": 4, "subtopics": [
            "Wanyama wa nyumbani na porini",
            "Lishe ya wanyama",
            "Kuzaliana kwa wanyama (rahisi)",
        ]},
        {"name": "Maji na Hewa", "order": 5, "subtopics": [
            "Usafishaji wa maji",
            "Sifa za hewa",
            "Matumizi ya hewa",
        ]},
        {"name": "Nishati", "order": 6, "subtopics": [
            "Aina za nishati",
            "Nishati ya jua, upepo, maji na umeme",
            "Kuhifadhi nishati",
        ]},
        {"name": "Mwendo na Nguvu", "order": 7, "subtopics": [
            "Dhana ya nguvu",
            "Aina za nguvu",
            "Matumizi ya nguvu",
        ]},
        {"name": "Mazingira", "order": 8, "subtopics": [
            "Uchafuzi wa mazingira",
            "Uhifadhi wa mazingira",
            "Mabadiliko ya tabianchi (rahisi)",
        ]},
    ],
    "Standard 5": [
        {"name": "Mifumo ya Mwili", "order": 1, "subtopics": [
            "Mfumo wa mifupa na misuli",
            "Mfumo wa mzunguko wa damu",
            "Mfumo wa upumuaji",
            "Mfumo wa mmeng'enyo",
        ]},
        {"name": "Vidudu na Magonjwa", "order": 2, "subtopics": [
            "Dhana ya vidudu",
            "Aina za vidudu (virusi, bakteria, fangasi)",
            "Magonjwa yanayosababishwa na vidudu",
            "Kinga na chanjo",
        ]},
        {"name": "Mimea", "order": 3, "subtopics": [
            "Uchavushaji na urutubishaji",
            "Usambazaji wa mbegu na matunda",
            "Ukuaji wa mimea (kina)",
        ]},
        {"name": "Wanyama", "order": 4, "subtopics": [
            "Mnyambuliko wa wanyama",
            "Mifumo ya mwili wa wanyama",
            "Mahusiano ya viumbe katika mazingira",
        ]},
        {"name": "Vipimo vya Sayansi", "order": 5, "subtopics": [
            "Kupima urefu",
            "Kupima uzito",
            "Kupima ujazo",
            "Kupima muda na joto",
        ]},
        {"name": "Umeme", "order": 6, "subtopics": [
            "Sakiti rahisi za umeme",
            "Mfululizo na sambamba (rahisi)",
            "Usalama wa umeme",
        ]},
        {"name": "Sumaku", "order": 7, "subtopics": [
            "Sifa za sumaku (kina)",
            "Uga wa sumaku",
            "Matumizi ya sumaku",
        ]},
        {"name": "Mwanga na Sauti", "order": 8, "subtopics": [
            "Dhana ya mwanga",
            "Vyanzo vya mwanga",
            "Dhana ya sauti",
            "Uenezaji wa sauti",
        ]},
    ],
    "Standard 6": [
        {"name": "Mfumo wa Neva na Homoni", "order": 1, "subtopics": [
            "Mfumo wa neva",
            "Mfumo wa homoni",
            "Uratibu wa mwili",
            "Athari za dawa na madawa ya kulevya",
        ]},
        {"name": "Uzazi", "order": 2, "subtopics": [
            "Mfumo wa uzazi wa binadamu",
            "Mzunguko wa hedhi",
            "Ujauzito na ukuaji wa mtoto",
            "Afya ya uzazi",
        ]},
        {"name": "Mimea", "order": 3, "subtopics": [
            "Uchavushaji (kina)",
            "Uzalishaji wa mbegu",
            "Ukuaji wa mimea (kina)",
            "Umuhimu wa mimea",
        ]},
        {"name": "Wanyama", "order": 4, "subtopics": [
            "Mifumo ya mwili wa wanyama",
            "Uzazi wa wanyama",
            "Mahusiano ya viumbe (mlolongo wa chakula)",
        ]},
        {"name": "Nguvu na Mwendo", "order": 5, "subtopics": [
            "Mashine rahisi",
            "Koleo, mashoka na visu",
            "Mguu wa kuku na mwendo",
        ]},
        {"name": "Umeme", "order": 6, "subtopics": [
            "Sakiti za mfululizo na sambamba",
            "Kipimo cha umeme (rahisi)",
            "Usalama wa umeme (kina)",
        ]},
        {"name": "Mwanga na Lenzi", "order": 7, "subtopics": [
            "Mwanga (kina)",
            "Lenzi na matumizi yake",
            "Kioo na matumizi yake",
        ]},
        {"name": "Teknolojia", "order": 8, "subtopics": [
            "Dhana ya teknolojia",
            "Teknolojia ya habari na mawasiliano (ICT)",
            "Matumizi ya teknolojia katika maisha",
        ]},
    ],
    "Standard 7": [
        {"name": "Mapitio ya Mifumo ya Mwili", "order": 1, "subtopics": [
            "Mapitio ya mifumo yote ya mwili",
            "Afya na magonjwa",
            "Lishe na afya",
        ]},
        {"name": "Uzazi na Urithi", "order": 2, "subtopics": [
            "Uzazi (kina)",
            "Dhana ya urithi",
            "Sifa za kurithi (rahisi)",
        ]},
        {"name": "Mimea na Wanyama", "order": 3, "subtopics": [
            "Mapitio ya mimea",
            "Mapitio ya wanyama",
            "Mahusiano ya viumbe",
            "Uhifadhi wa viumbe",
        ]},
        {"name": "Nishati na Mwendo", "order": 4, "subtopics": [
            "Mapitio ya nishati",
            "Mashine rahisi (kina)",
            "Umeme na usalama",
        ]},
        {"name": "Teknolojia na Mazingira", "order": 5, "subtopics": [
            "Teknolojia katika maisha",
            "Mazingira na maendeleo endelevu",
            "Mabadiliko ya tabianchi",
        ]},
        {"name": "Mazoezi ya Mtihani wa Taifa", "order": 6, "subtopics": [
            "Mazoezi ya maswali ya PSLE (Sayansi)",
            "Kuchambua maswali",
            "Udhibiti wa muda",
        ]},
    ],
}


# =============================================================================
# PRIMARY — MAARIFA YA JAMII
# =============================================================================

PRIMARY_MAARIFA = {
    "Standard 1": [
        {"name": "Familia Yangu", "order": 1, "subtopics": [
            "Dhana ya familia",
            "Aina za familia",
            "Wajumbe wa familia na majukumu yao",
            "Uhusiano katika familia",
        ]},
        {"name": "Jamii Yangu", "order": 2, "subtopics": [
            "Dhana ya jamii",
            "Majirani na umoja",
            "Mila na desturi za jamii",
            "Kushirikiana katika jamii",
        ]},
        {"name": "Shule Yangu", "order": 3, "subtopics": [
            "Sehemu za shule",
            "Wafanyakazi wa shule na majukumu",
            "Kanuni za shule",
            "Kujisikia salama shuleni",
        ]},
        {"name": "Nyumbani Kwangu", "order": 4, "subtopics": [
            "Sehemu za nyumba",
            "Majukumu nyumbani",
            "Usafi na utunzaji wa nyumba",
        ]},
        {"name": "Mazingira Yangu", "order": 5, "subtopics": [
            "Mazingira ya karibu",
            "Viumbe katika mazingira",
            "Kutunza mazingira",
        ]},
        {"name": "Vyombo vya Usafiri", "order": 6, "subtopics": [
            "Aina za vyombo vya usafiri",
            "Usafiri wa nchi kavu, majini na angani",
            "Usalama barabarani",
        ]},
    ],
    "Standard 2": [
        {"name": "Familia", "order": 1, "subtopics": [
            "Majukumu ya familia",
            "Ushirikiano katika familia",
            "Mabadiliko katika familia",
            "Utunzaji wa watoto na wazee",
        ]},
        {"name": "Jamii na Utamaduni", "order": 2, "subtopics": [
            "Mila na desturi",
            "Sherehe za jadi",
            "Kuheshimiana katika jamii",
            "Kuhifadhi utamaduni",
        ]},
        {"name": "Shughuli za Kiuchumi", "order": 3, "subtopics": [
            "Kilimo",
            "Ufugaji",
            "Uvuvi",
            "Biashara ndogo ndogo",
        ]},
        {"name": "Mazingira", "order": 4, "subtopics": [
            "Uhifadhi wa mazingira",
            "Upandaji miti",
            "Uchafuzi wa mazingira",
            "Usafi wa mazingira",
        ]},
        {"name": "Usafiri na Mawasiliano", "order": 5, "subtopics": [
            "Njia za mawasiliano",
            "Vyombo vya mawasiliano",
            "Usalama barabarani",
        ]},
        {"name": "Afya na Usafi", "order": 6, "subtopics": [
            "Usafi wa mwili na mazingira",
            "Chakula na lishe",
            "Magonjwa na kujikinga",
        ]},
    ],
    "Standard 3": [
        {"name": "Historia ya Tanzania", "order": 1, "subtopics": [
            "Jamii za awali",
            "Makabila na utamaduni",
            "Ukoloni (rahisi)",
            "Harakati za uhuru (rahisi)",
        ]},
        {"name": "Shughuli za Kiuchumi", "order": 2, "subtopics": [
            "Kilimo (kina)",
            "Ufugaji (kina)",
            "Uvuvi na misitu",
            "Uchimbaji madini (rahisi)",
        ]},
        {"name": "Biashara", "order": 3, "subtopics": [
            "Dhana ya biashara",
            "Aina za biashara",
            "Soko na bei",
            "Fedha za Tanzania",
        ]},
        {"name": "Serikali za Mitaa", "order": 4, "subtopics": [
            "Dhana ya serikali",
            "Serikali ya kijiji/kata",
            "Majukumu ya serikali za mitaa",
            "Ushiriki wa wananchi",
        ]},
        {"name": "Mazingira na Hali ya Hewa", "order": 5, "subtopics": [
            "Hali ya hewa na tabianchi",
            "Misimu ya mwaka",
            "Uhifadhi wa mazingira",
        ]},
        {"name": "Maadili na Uraia", "order": 6, "subtopics": [
            "Maadili mema",
            "Haki na wajibu",
            "Uaminifu na uwajibikaji",
        ]},
    ],
    "Standard 4": [
        {"name": "Jiografia ya Tanzania", "order": 1, "subtopics": [
            "Nafasi ya Tanzania (mikoa)",
            "Hali ya hewa ya Tanzania",
            "Vyanzo vya maji na ardhi",
            "Wanyamapori na uhifadhi",
        ]},
        {"name": "Historia ya Tanzania", "order": 2, "subtopics": [
            "Ukoloni wa Tanzania",
            "Wakoloni (Wajerumani na Waingereza)",
            "Harakati za uhuru",
            "Uhuru wa Tanganyika na Zanzibar",
        ]},
        {"name": "Serikali ya Tanzania", "order": 3, "subtopics": [
            "Muundo wa serikali",
            "Matawi ya serikali",
            "Majukumu ya serikali",
            "Ushiriki wa wananchi katika utawala",
        ]},
        {"name": "Shughuli za Kiuchumi", "order": 4, "subtopics": [
            "Kilimo na mazao ya biashara",
            "Ufugaji na uvuvi",
            "Viwanda",
            "Utalii",
        ]},
        {"name": "Utamaduni na Uraia", "order": 5, "subtopics": [
            "Utamaduni wa Tanzania",
            "Umoja na mshikamano",
            "Haki za binadamu (rahisi)",
            "Majukumu ya raia",
        ]},
        {"name": "Afya na Usalama", "order": 6, "subtopics": [
            "Afya ya jamii",
            "Usalama wa raia",
            "Usalama barabarani",
            "Dharura na msaada",
        ]},
    ],
    "Standard 5": [
        {"name": "Jiografia", "order": 1, "subtopics": [
            "Maeneo makuu ya Tanzania",
            "Maji (mito, maziwa, bahari)",
            "Ardhi na matumizi yake",
            "Ramani (rahisi)",
        ]},
        {"name": "Historia", "order": 2, "subtopics": [
            "Jamii za Tanzania kabla ya ukoloni",
            "Ukoloni na athari zake",
            "Harakati za uhuru (kina)",
            "Muungano wa Tanganyika na Zanzibar",
        ]},
        {"name": "Serikali ya Tanzania", "order": 3, "subtopics": [
            "Katiba ya Tanzania (rahisi)",
            "Matawi ya serikali (kina)",
            "Uchaguzi na demokrasia",
            "Majukumu ya raia",
        ]},
        {"name": "Uchumi", "order": 4, "subtopics": [
            "Fedha na benki",
            "Akiba na uwekezaji",
            "Biashara ya ndani na nje",
            "Usafirishaji wa bidhaa",
        ]},
        {"name": "Utamaduni na Mila", "order": 5, "subtopics": [
            "Utamaduni wa makabila",
            "Lugha na mawasiliano",
            "Kuhifadhi utamaduni",
            "Utamaduni na maendeleo",
        ]},
        {"name": "Uraia na Maadili", "order": 6, "subtopics": [
            "Haki za binadamu",
            "Majukumu ya raia",
            "Maadili ya kijamii",
            "Kukabiliana na tabia mbaya",
        ]},
    ],
    "Standard 6": [
        {"name": "Jiografia", "order": 1, "subtopics": [
            "Hali ya hewa na tabianchi ya Tanzania",
            "Mazingira na uhifadhi",
            "Watu na shughuli zao",
            "Maeneo yanayovutia utalii",
        ]},
        {"name": "Historia", "order": 2, "subtopics": [
            "Jamhuri ya Muungano",
            "Mashirika ya kikanda na kimataifa (rahisi)",
            "Tanzania katika siasa za Afrika",
        ]},
        {"name": "Uchumi", "order": 3, "subtopics": [
            "Biashara ya kimataifa",
            "Uwekezaji",
            "Miradi ya maendeleo",
            "Usimamizi wa fedha",
        ]},
        {"name": "Serikali na Siasa", "order": 4, "subtopics": [
            "Uchaguzi (kina)",
            "Vyama vya siasa",
            "Mawasiliano ya kijamii",
            "Ushiriki wa vijana na wanawake",
        ]},
        {"name": "Utafiti wa Jamii", "order": 5, "subtopics": [
            "Dhana ya utafiti",
            "Kukusanya taarifa",
            "Kuchambua taarifa",
            "Kutoa ripoti",
        ]},
        {"name": "Uraia na Maadili", "order": 6, "subtopics": [
            "Katiba na haki",
            "Maadili ya kazi",
            "Kujitolea na kujenga taifa",
            "Kukabiliana na rushwa na ufisadi",
        ]},
    ],
    "Standard 7": [
        {"name": "Mapitio ya Jiografia", "order": 1, "subtopics": [
            "Tanzania na Afrika (kina)",
            "Ramani na mizani",
            "Mazingira na maendeleo",
        ]},
        {"name": "Mapitio ya Historia", "order": 2, "subtopics": [
            "Tanzania kabla na baada ya uhuru",
            "Mashirika ya Afrika (AU, EAC)",
            "Tanzania katika jumuiya za kimataifa",
        ]},
        {"name": "Uchumi na Maendeleo", "order": 3, "subtopics": [
            "Maendeleo ya uchumi",
            "Miundombinu",
            "Uwekezaji na biashara",
            "Uchumi wa kidijitali (rahisi)",
        ]},
        {"name": "Serikali na Uraia", "order": 4, "subtopics": [
            "Katiba ya Tanzania (kina)",
            "Demokrasia na uchaguzi",
            "Haki na wajibu wa raia",
            "Kujenga taifa",
        ]},
        {"name": "Mazoezi ya Mtihani wa Taifa", "order": 5, "subtopics": [
            "Mazoezi ya maswali ya PSLE (Maarifa ya Jamii)",
            "Kuchambua maswali",
            "Udhibiti wa muda",
        ]},
    ],
}


# =============================================================================
# PRIMARY — STADI ZA KAZI
# =============================================================================

PRIMARY_STADI = _same_classes([
    {"name": "Usafi na Utunzaji wa Mazingira", "order": 1, "subtopics": [
        "Usafi wa mwili",
        "Usafi wa mazingira",
        "Kutunza vitu vya shule na nyumbani",
        "Utunzaji wa mazingira",
    ]},
    {"name": "Ushonaji", "order": 2, "subtopics": [
        "Sindano na uzi",
        "Kushona mshono rahisi",
        "Kushona vifungo",
        "Kushona nguo rahisi",
        "Kukarabati nguo",
    ]},
    {"name": "Upishi", "order": 3, "subtopics": [
        "Usafi wa jikoni",
        "Chakula rahisi cha kienyeji",
        "Kupika mlo kamili",
        "Kuhudumia wageni",
        "Usalama jikoni",
    ]},
    {"name": "Kilimo", "order": 4, "subtopics": [
        "Maandalizi ya shamba",
        "Kupanda mbegu na miche",
        "Kutunza mazao",
        "Mazao ya mboga",
        "Mazao ya biashara",
        "Kilimo bora",
    ]},
    {"name": "Ufugaji", "order": 5, "subtopics": [
        "Kutunza kuku",
        "Kutunza mbuzi",
        "Kutunza ng'ombe",
        "Utunzaji wa wanyama vipenzi",
        "Ufugaji bora",
    ]},
    {"name": "Ufundi na Ujenzi", "order": 6, "subtopics": [
        "Kutumia zana rahisi",
        "Kutengeneza vitu vya mbao",
        "Kutengeneza vitu vya chuma (rahisi)",
        "Mifano ya nyumba",
        "Kutengeneza na kukarabati vitu",
    ]},
    {"name": "Uchonga na Usanii", "order": 7, "subtopics": [
        "Uchonga wa mbao",
        "Usanii wa udongo",
        "Kutengeneza vitu vya mapambo",
        "Biashara ya kazi za sanaa",
    ]},
    {"name": "Ujasiriamali na Miradi", "order": 8, "subtopics": [
        "Dhana ya ujasiriamali",
        "Kutengeneza bidhaa",
        "Kuandaa mradi mdogo",
        "Kuuza bidhaa",
        "Usimamizi wa mradi",
    ]},
], PRIMARY_STANDARDS)


# =============================================================================
# PRIMARY — ELIMU YA DINI
# =============================================================================

PRIMARY_DINI = _same_classes([
    {"name": "Mungu na Uumbaji", "order": 1, "subtopics": [
        "Dhana ya Mungu",
        "Uumbaji wa ulimwengu",
        "Kumshukuru Mungu",
        "Mahusiano na Mungu",
    ]},
    {"name": "Vitabu Vitakatifu", "order": 2, "subtopics": [
        "Vitabu vitakatifu vya dini zetu",
        "Maandiko na mafundisho",
        "Kusoma na kuelewa maandiko",
        "Matumizi ya maandiko katika maisha",
    ]},
    {"name": "Kuabudu na Maombi", "order": 3, "subtopics": [
        "Dhana ya kuabudu",
        "Maombi na aina zake",
        "Mahali pa kuabudia",
        "Sherehe za kidini",
    ]},
    {"name": "Maadili", "order": 4, "subtopics": [
        "Ukweli na uaminifu",
        "Upendo na huruma",
        "Heshima na adabu",
        "Wajibu na uwajibikaji",
        "Kujitolea kwa jamii",
    ]},
    {"name": "Watu wa Mungu", "order": 5, "subtopics": [
        "Manabii na viongozi wa dini",
        "Historia ya waumini",
        "Watu wa mfano katika maandiko",
        "Jumuiya ya waumini",
    ]},
    {"name": "Maadili ya Kijamii na Taifa", "order": 6, "subtopics": [
        "Amani na umoja",
        "Haki na usawa",
        "Kujenga taifa",
        "Mazingira na uumbaji",
        "Maadili katika teknolojia (rahisi)",
    ]},
], PRIMARY_STANDARDS)


# =============================================================================
# PRIMARY — UCHORAJI (SANA ZA UONI)
# =============================================================================

PRIMARY_UCHORAJI = _same_classes([
    {"name": "Rangi", "order": 1, "subtopics": [
        "Kutambua rangi za msingi",
        "Kuchanganya rangi",
        "Rangi za joto na baridi",
        "Matumizi ya rangi katika kazi za sanaa",
    ]},
    {"name": "Kuchora", "order": 2, "subtopics": [
        "Kuchora vitu rahisi",
        "Kuchora watu na wanyama",
        "Kuchora mazingira",
        "Kuchora kwa mtazamo (rahisi)",
        "Kuchora kwa kumbukumbu",
    ]},
    {"name": "Kupaka Rangi na Upambaji", "order": 3, "subtopics": [
        "Kupaka rangi ndani ya mstari",
        "Upambaji wa kazi za sanaa",
        "Kutengeneza picha za rangi",
        "Upambaji wa vitu vya nyumbani",
    ]},
    {"name": "Michoro ya Kitamaduni", "order": 4, "subtopics": [
        "Michoro ya jadi ya Tanzania",
        "Alama na ishara",
        "Michoro kwenye nguo",
        "Kuhifadhi utamaduni kupitia sanaa",
    ]},
    {"name": "Ubunifu wa Kisanii", "order": 5, "subtopics": [
        "Kubuni kazi mpya za sanaa",
        "Kutengeneza mabango (posters)",
        "Kuchora katika matukio maalum",
        "Uwasilishaji wa kazi za sanaa",
    ]},
    {"name": "Uchambuzi wa Kazi za Sanaa", "order": 6, "subtopics": [
        "Kuangalia na kuthamini kazi za sanaa",
        "Kutambua ujumbe katika kazi za sanaa",
        "Kujadili kazi za wengine",
        "Mradi wa sanaa",
    ]},
], PRIMARY_STANDARDS)


# =============================================================================
# PRIMARY — MUZIKI
# =============================================================================

PRIMARY_MUZIKI = _same_classes([
    {"name": "Kuimba", "order": 1, "subtopics": [
        "Nyimbo rahisi",
        "Nyimbo za kienyeji",
        "Kuimba kwa pamoja (kwaya)",
        "Kuimba kwa sauti sahihi",
        "Nyimbo za matukio mbalimbali",
    ]},
    {"name": "Mdundo na Kipimo", "order": 2, "subtopics": [
        "Kupiga makofi kwa mdundo",
        "Midundo mbalimbali",
        "Kipimo katika muziki",
        "Kutumia vyombo rahisi vya mdundo",
    ]},
    {"name": "Ala za Muziki", "order": 3, "subtopics": [
        "Aina za ala za muziki",
        "Ala za jadi za Tanzania",
        "Matumizi ya ala za muziki",
        "Utunzaji wa ala za muziki",
    ]},
    {"name": "Mwendo na Ngoma", "order": 4, "subtopics": [
        "Dansi rahisi",
        "Ngoma za jadi",
        "Mwendo unaoendana na muziki",
        "Uwasilishaji wa ngoma",
    ]},
    {"name": "Utungo na Ubunifu", "order": 5, "subtopics": [
        "Kutunga nyimbo rahisi",
        "Kutunga mashairi ya nyimbo",
        "Ubunifu katika muziki",
        "Muziki wa kisasa na wa jadi",
    ]},
    {"name": "Uthaminifu wa Muziki", "order": 6, "subtopics": [
        "Kusikiliza muziki kwa makini",
        "Kutambua ujumbe wa nyimbo",
        "Uhakiki rahisi wa muziki",
        "Tamasha na uwasilishaji",
    ]},
], PRIMARY_STANDARDS)


# =============================================================================
# PRIMARY — MICHEZO
# =============================================================================

PRIMARY_MICHEZO = _same_classes([
    {"name": "Michezo ya Riadha", "order": 1, "subtopics": [
        "Mbio rahisi",
        "Mbio za vipindi",
        "Kuruka",
        "Kurusha",
        "Mashindano ya riadha",
    ]},
    {"name": "Michezo ya Mpira", "order": 2, "subtopics": [
        "Mpira wa miguu (rahisi)",
        "Mpira wa kikapu (rahisi)",
        "Mpira wa wavu (rahisi)",
        "Sheria rahisi za michezo",
        "Michezo ya timu",
    ]},
    {"name": "Michezo ya Jadi", "order": 3, "subtopics": [
        "Michezo ya jadi ya Tanzania",
        "Michezo ya kukimbia na kuruka",
        "Michezo ya nguvu na ustadi",
        "Kuhifadhi michezo ya jadi",
    ]},
    {"name": "Mazoezi ya Mwili", "order": 4, "subtopics": [
        "Mazoezi ya viungo",
        "Gymnastics rahisi",
        "Mazoezi ya nguvu",
        "Mazoezi ya kubadilika kwa mwili",
    ]},
    {"name": "Usalama na Afya katika Michezo", "order": 5, "subtopics": [
        "Usalama wakati wa michezo",
        "Mavazi na vifaa sahihi",
        "Afya na lishe ya mwanaspoti",
        "Kujikinga na majeraha",
        "Kusaidia wakati wa dharura",
    ]},
    {"name": "Maadili na Uongozi katika Michezo", "order": 6, "subtopics": [
        "Uchezaji wa haki",
        "Kukubali kushinda na kushindwa",
        "Ushirikiano wa timu",
        "Uongozi katika michezo",
        "Mashindano ya shule",
    ]},
], PRIMARY_STANDARDS)


# =============================================================================
# SECONDARY EXTRAS
# =============================================================================

SECONDARY_BIBLE = {
    "Form 1": [
        {"name": "Introduction to Bible Knowledge", "order": 1, "subtopics": [
            "Meaning of Bible Knowledge",
            "Importance of studying Bible Knowledge",
            "The structure of the Bible",
            "Sources of the Bible",
        ]},
        {"name": "Creation and Early History", "order": 2, "subtopics": [
            "The story of creation",
            "The fall of man",
            "Cain and Abel",
            "Noah and the flood",
            "The tower of Babel",
        ]},
        {"name": "The Patriarchs", "order": 3, "subtopics": [
            "Abraham — the call and faith",
            "Isaac — the promised son",
            "Jacob — the covenant and struggles",
            "The twelve tribes of Israel",
        ]},
        {"name": "Joseph and His Family", "order": 4, "subtopics": [
            "Joseph's dreams",
            "Joseph sold into slavery",
            "Joseph in Egypt",
            "Joseph forgives his brothers",
            "Lessons from Joseph's life",
        ]},
        {"name": "Moses and the Exodus", "order": 5, "subtopics": [
            "The birth and call of Moses",
            "The ten plagues",
            "The Passover",
            "Crossing the Red Sea",
            "The journey to the Promised Land",
        ]},
        {"name": "The Ten Commandments", "order": 6, "subtopics": [
            "The giving of the Law at Sinai",
            "Commandments about God",
            "Commandments about human relationships",
            "The meaning of the Law today",
        ]},
        {"name": "The Promised Land", "order": 7, "subtopics": [
            "Joshua leads Israel",
            "The conquest of Canaan",
            "The judges of Israel",
            "Ruth and Naomi",
        ]},
    ],
    "Form 2": [
        {"name": "The Monarchy of Israel", "order": 1, "subtopics": [
            "Samuel anoints Saul",
            "The reign of King Saul",
            "David — the shepherd king",
            "Solomon — wisdom and the Temple",
            "The division of the kingdom",
        ]},
        {"name": "The Prophets of Israel", "order": 2, "subtopics": [
            "Elijah and the prophets of Baal",
            "Elisha — miracles and ministry",
            "Amos — justice and righteousness",
            "Hosea — God's love for Israel",
            "Isaiah — the call and message",
        ]},
        {"name": "The Divided Kingdom", "order": 3, "subtopics": [
            "The kingdom of Israel (North)",
            "The kingdom of Judah (South)",
            "The Assyrian captivity",
            "The fall of Jerusalem and the Babylonian exile",
        ]},
        {"name": "The Babylonian Exile", "order": 4, "subtopics": [
            "Life in exile",
            "Jeremiah — prophecies of hope",
            "Ezekiel — visions of restoration",
            "Daniel — faith in a foreign land",
        ]},
        {"name": "The Return from Exile", "order": 5, "subtopics": [
            "Cyrus allows the return",
            "Rebuilding the Temple (Ezra)",
            "Rebuilding the walls (Nehemiah)",
            "Esther — deliverance of the Jews",
        ]},
        {"name": "Wisdom Literature", "order": 6, "subtopics": [
            "The book of Job — suffering and faith",
            "The Psalms — worship and prayer",
            "The Proverbs — practical wisdom",
            "Ecclesiastes — the meaning of life",
        ]},
    ],
    "Form 3": [
        {"name": "The Life of Jesus Christ", "order": 1, "subtopics": [
            "The birth of Jesus",
            "The baptism and temptation of Jesus",
            "The calling of the disciples",
            "The transfiguration",
        ]},
        {"name": "The Teachings of Jesus", "order": 2, "subtopics": [
            "The Sermon on the Mount",
            "The parables of the Kingdom",
            "Parables of forgiveness and love",
            "The Lord's Prayer",
            "Teachings on wealth and possessions",
        ]},
        {"name": "The Miracles of Jesus", "order": 3, "subtopics": [
            "Miracles of healing",
            "Miracles over nature",
            "Miracles of provision",
            "Raising the dead",
            "The meaning of miracles",
        ]},
        {"name": "The Passion and Resurrection", "order": 4, "subtopics": [
            "The triumphal entry",
            "The last supper",
            "The arrest and trials of Jesus",
            "The crucifixion",
            "The resurrection and appearances",
            "The ascension",
        ]},
        {"name": "The Early Church", "order": 5, "subtopics": [
            "The day of Pentecost",
            "The life of the early believers",
            "Peter and John before the Sanhedrin",
            "Stephen — the first martyr",
            "The conversion of Saul",
        ]},
        {"name": "The Mission of the Apostles", "order": 6, "subtopics": [
            "Paul's missionary journeys",
            "The Jerusalem Council",
            "The spread of the Gospel to the Gentiles",
            "Paul's arrest and trial",
        ]},
    ],
    "Form 4": [
        {"name": "The Epistles of Paul", "order": 1, "subtopics": [
            "Romans — salvation by faith",
            "Corinthians — the church and love",
            "Galatians — freedom in Christ",
            "Ephesians — unity in Christ",
            "Philippians — joy and humility",
        ]},
        {"name": "The General Epistles", "order": 2, "subtopics": [
            "Hebrews — the supremacy of Christ",
            "James — faith and works",
            "Peter — suffering and hope",
            "John — love and truth",
            "Jude — contending for the faith",
        ]},
        {"name": "Christian Living and Ethics", "order": 3, "subtopics": [
            "The fruit of the Spirit",
            "Christian relationships (family, work, society)",
            "Stewardship of God's creation",
            "Integrity and honesty",
            "Handling wealth and possessions",
        ]},
        {"name": "The Church in Tanzania", "order": 4, "subtopics": [
            "The coming of Christianity to Tanzania",
            "The role of the Church in education and health",
            "The Church and national development",
            "Church leadership and unity",
        ]},
        {"name": "Christianity and Social Issues", "order": 5, "subtopics": [
            "Poverty and wealth",
            "Corruption and justice",
            "HIV/AIDS and health",
            "Environmental responsibility",
            "Gender equality",
        ]},
        {"name": "The Second Coming and Final Things", "order": 6, "subtopics": [
            "Signs of the end times",
            "The second coming of Christ",
            "The resurrection of the dead",
            "The final judgment",
            "Review for CSEE",
        ]},
    ],
}


SECONDARY_ISLAMIC = {
    "Form 1": [
        {"name": "Introduction to Islam", "order": 1, "subtopics": [
            "Meaning of Islam",
            "Sources of Islamic teachings (Qur'an and Sunnah)",
            "The Shahada (testimony of faith)",
            "Pillars of Iman (belief)",
        ]},
        {"name": "The Holy Qur'an", "order": 2, "subtopics": [
            "Revelation of the Qur'an",
            "Structure of the Qur'an (Surahs and Ayahs)",
            "Compilation of the Qur'an",
            "Etiquette of reading the Qur'an",
            "Memorisation of selected Surahs",
        ]},
        {"name": "The Life of Prophet Muhammad (PBUH) — Makkah Period", "order": 3, "subtopics": [
            "Birth and early life",
            "The first revelation",
            "The early call to Islam",
            "Persecution of the Muslims",
            "The migration to Abyssinia",
        ]},
        {"name": "The Hijra to Madinah", "order": 4, "subtopics": [
            "The pledge of Aqabah",
            "The journey to Madinah",
            "Building the first mosque",
            "The brotherhood between Muhajirun and Ansar",
            "The Constitution of Madinah",
        ]},
        {"name": "The Five Pillars of Islam", "order": 5, "subtopics": [
            "Shahada (Testimony)",
            "Salah (Prayer)",
            "Sawm (Fasting)",
            "Zakat (Almsgiving)",
            "Hajj (Pilgrimage)",
        ]},
        {"name": "Islamic Beliefs (Aqeedah)", "order": 6, "subtopics": [
            "Belief in Allah",
            "Belief in the angels",
            "Belief in the revealed books",
            "Belief in the prophets",
            "Belief in the Last Day",
            "Belief in destiny (Qadar)",
        ]},
    ],
    "Form 2": [
        {"name": "The Life of Prophet Muhammad — Madinah Period", "order": 1, "subtopics": [
            "The battles of Badr and Uhud",
            "The Treaty of Hudaibiyah",
            "The conquest of Makkah",
            "The farewell sermon",
            "The death of the Prophet (PBUH)",
        ]},
        {"name": "Qur'anic Sciences (Ulum al-Qur'an)", "order": 2, "subtopics": [
            "Tafsir (interpretation) — introduction",
            "Asbab al-Nuzul (occasions of revelation)",
            "Makki and Madani surahs",
            "Selected surahs and their messages",
        ]},
        {"name": "Hadith and Sunnah", "order": 3, "subtopics": [
            "Meaning of Hadith and Sunnah",
            "Classification of Hadith (Sahih, Hasan, Da'if)",
            "The collection of Hadith",
            "Selected Hadiths and their lessons",
        ]},
        {"name": "Islamic Ethics (Akhlaq)", "order": 4, "subtopics": [
            "Honesty and truthfulness",
            "Respect for parents and elders",
            "Good neighbourliness",
            "Trustworthiness and responsibility",
            "Forbidden behaviours in Islam",
        ]},
        {"name": "Salah in Detail", "order": 5, "subtopics": [
            "Conditions and pillars of Salah",
            "The five daily prayers",
            "Congregational prayer (Jama'ah)",
            "Friday prayer (Jumu'ah)",
            "Prayer for the sick and traveller",
        ]},
        {"name": "Sawm and Zakat", "order": 6, "subtopics": [
            "Fasting in Ramadan — rules and wisdom",
            "Laylat al-Qadr",
            "Zakat — types and beneficiaries",
            "Sadaqah and charity",
        ]},
    ],
    "Form 3": [
        {"name": "Hajj and Umrah", "order": 1, "subtopics": [
            "The rites of Hajj",
            "The wisdom of Hajj",
            "Umrah — rules and significance",
            "Visiting the Prophet's mosque",
        ]},
        {"name": "Islamic Jurisprudence (Fiqh)", "order": 2, "subtopics": [
            "Meaning and sources of Fiqh",
            "Purification (Taharah)",
            "Worship and transactions",
            "Marriage and family law (basics)",
            "Inheritance (Miras) — introduction",
        ]},
        {"name": "Islamic History — The Rightly Guided Caliphs", "order": 3, "subtopics": [
            "The caliphate of Abu Bakr",
            "The caliphate of Umar",
            "The caliphate of Uthman",
            "The caliphate of Ali",
            "The spread of Islam after the caliphs",
        ]},
        {"name": "Family Life in Islam", "order": 4, "subtopics": [
            "Marriage — purpose and conditions",
            "Rights and responsibilities of spouses",
            "Rights of children and parents",
            "Divorce — rules and procedures",
            "Family relationships in Islam",
        ]},
        {"name": "Islamic Economics", "order": 5, "subtopics": [
            "Halal and haram earnings",
            "Trade and business ethics in Islam",
            "Riba (interest) and its prohibition",
            "Zakat as an economic system",
            "Wealth and poverty in Islam",
        ]},
        {"name": "Contemporary Islamic Issues", "order": 6, "subtopics": [
            "Islam and science",
            "Islam and modernity",
            "Extremism and moderation",
            "Muslims in a multicultural society",
        ]},
    ],
    "Form 4": [
        {"name": "Islamic Jurisprudence (Muamalat)", "order": 1, "subtopics": [
            "Contracts and transactions",
            "Sales and trade laws",
            "Partnership and agency",
            "Lending and debt",
            "Dispute resolution in Islam",
        ]},
        {"name": "Islamic Civilisation and Contributions", "order": 2, "subtopics": [
            "Contributions in science and medicine",
            "Contributions in mathematics and astronomy",
            "Islamic architecture and arts",
            "The golden age of Islamic learning",
            "The influence of Islamic civilisation",
        ]},
        {"name": "Da'wah (Call to Islam)", "order": 3, "subtopics": [
            "Meaning and importance of Da'wah",
            "Methods of Da'wah",
            "Qualities of a Da'ee (caller)",
            "Da'wah in contemporary society",
        ]},
        {"name": "Islam in East Africa and Tanzania", "order": 4, "subtopics": [
            "The coming of Islam to the East African coast",
            "The role of trade in spreading Islam",
            "Islamic education in Tanzania",
            "Muslim institutions and organisations in Tanzania",
            "Islam and national unity",
        ]},
        {"name": "Islamic Ethics in Modern Society", "order": 5, "subtopics": [
            "Islam and social justice",
            "Islamic responses to corruption",
            "Islam and environmental stewardship",
            "Islam and family values today",
            "Islam and youth challenges",
        ]},
        {"name": "Review for CSEE", "order": 6, "subtopics": [
            "Revision of the five pillars",
            "Revision of the life of the Prophet (PBUH)",
            "Revision of Fiqh and Muamalat",
            "Revision of Islamic history",
            "Past paper practice",
        ]},
    ],
}


SECONDARY_FRENCH = {
    "Form 1": [
        {"name": "Les Salutations (Greetings)", "order": 1, "subtopics": [
            "Dire bonjour et bonsoir",
            "Demander et dire comment ça va",
            "Se présenter (nom, âge, origine)",
            "Prendre congé",
        ]},
        {"name": "L'alphabet et les Nombres", "order": 2, "subtopics": [
            "L'alphabet français",
            "Les nombres de 0 à 100",
            "Les jours de la semaine",
            "Les mois et les saisons",
        ]},
        {"name": "La Famille", "order": 3, "subtopics": [
            "Les membres de la famille",
            "Décrire sa famille",
            "Les adjectifs possessifs (mon, ma, mes)",
            "Parler de ses proches",
        ]},
        {"name": "L'école", "order": 4, "subtopics": [
            "Les objets de la classe",
            "Les matières scolaires",
            "Le verbe être et avoir",
            "Parler de son école",
        ]},
        {"name": "Les Couleurs et les Objets", "order": 5, "subtopics": [
            "Les couleurs",
            "Les objets de la maison",
            "Les articles (un, une, des, le, la, les)",
            "Décrire des objets",
        ]},
        {"name": "Se Présenter", "order": 6, "subtopics": [
            "Présenter son identité",
            "Présenter sa nationalité",
            "Parler de sa ville",
            "La carte d'identité",
        ]},
    ],
    "Form 2": [
        {"name": "Les Verbes Réguliers", "order": 1, "subtopics": [
            "Les verbes en -er (parler, chanter)",
            "Les verbes en -ir (finir, choisir)",
            "Les verbes en -re (vendre, attendre)",
            "La conjugaison au présent",
        ]},
        {"name": "Le Genre et les Articles", "order": 2, "subtopics": [
            "Le masculin et le féminin",
            "Le singulier et le pluriel",
            "Les articles définis et indéfinis",
            "Les articles partitifs (du, de la, des)",
        ]},
        {"name": "La Nourriture", "order": 3, "subtopics": [
            "Les aliments et les boissons",
            "Au marché et au restaurant",
            "Commander un repas",
            "Le verbe manger et boire",
        ]},
        {"name": "Les Vêtements", "order": 4, "subtopics": [
            "Les vêtements et les couleurs",
            "Acheter des vêtements",
            "Décrire une tenue",
            "Les saisons et les vêtements",
        ]},
        {"name": "L'heure et le Temps", "order": 5, "subtopics": [
            "Demander et dire l'heure",
            "Les activités quotidiennes",
            "Le temps qu'il fait",
            "Les verbes du quotidien",
        ]},
        {"name": "La Maison", "order": 6, "subtopics": [
            "Les pièces de la maison",
            "Les meubles",
            "Les prépositions de lieu",
            "Décrire sa maison",
        ]},
    ],
    "Form 3": [
        {"name": "Les Verbes Irréguliers", "order": 1, "subtopics": [
            "Aller, venir, faire, dire",
            "Prendre, mettre, voir, pouvoir",
            "Vouloir, devoir, savoir",
            "La conjugaison et l'usage",
        ]},
        {"name": "Le Passé Composé", "order": 2, "subtopics": [
            "Le passé composé avec avoir",
            "Le passé composé avec être",
            "Les participes passés",
            "Raconter un événement passé",
        ]},
        {"name": "Les Voyages", "order": 3, "subtopics": [
            "Les moyens de transport",
            "À la gare et à l'aéroport",
            "Réserver une chambre d'hôtel",
            "Demander le chemin",
        ]},
        {"name": "La Santé", "order": 4, "subtopics": [
            "Les parties du corps",
            "Les maladies courantes",
            "Chez le médecin",
            "Les conseils de santé",
        ]},
        {"name": "Les Loisirs", "order": 5, "subtopics": [
            "Les sports",
            "Les passe-temps",
            "La télévision et la musique",
            "Exprimer ses goûts",
        ]},
        {"name": "Les Métiers et la Ville", "order": 6, "subtopics": [
            "Les métiers et professions",
            "Les lieux de la ville",
            "Acheter et vendre",
            "Les services publics",
        ]},
    ],
    "Form 4": [
        {"name": "Le Futur et l'Imparfait", "order": 1, "subtopics": [
            "Le futur proche (aller + infinitif)",
            "Le futur simple",
            "L'imparfait",
            "Raconter au passé et parler de l'avenir",
        ]},
        {"name": "La Culture Francophone", "order": 2, "subtopics": [
            "Les pays francophones",
            "Les fêtes et traditions",
            "La musique et la littérature francophones",
            "La francophonie dans le monde",
        ]},
        {"name": "Les Médias", "order": 3, "subtopics": [
            "La presse écrite",
            "La radio et la télévision",
            "Internet et les réseaux sociaux",
            "Exprimer son opinion",
        ]},
        {"name": "L'environnement", "order": 4, "subtopics": [
            "La pollution",
            "La protection de la nature",
            "Le changement climatique",
            "Les gestes écologiques",
        ]},
        {"name": "Le Commerce et les Affaires", "order": 5, "subtopics": [
            "Le vocabulaire du commerce",
            "Écrire une lettre commerciale",
            "Négocier et discuter",
            "Le tourisme et l'économie",
        ]},
        {"name": "Révision pour l'Examen", "order": 6, "subtopics": [
            "Révision de la grammaire",
            "Révision du vocabulaire",
            "La compréhension écrite",
            "La production écrite",
            "Les examens antérieurs",
        ]},
    ],
}


SECONDARY_ARABIC = {
    "Form 1": [
        {"name": "L'alphabet Arabe", "order": 1, "subtopics": [
            "Les 28 lettres de l'alphabet",
            "La prononciation des lettres",
            "Les voyelles (harakat)",
            "L'écriture des lettres (début, milieu, fin)",
        ]},
        {"name": "La Lecture et l'Écriture", "order": 2, "subtopics": [
            "Lire les syllabes",
            "Lire des mots simples",
            "Écrire des mots simples",
            "La calligraphie de base",
        ]},
        {"name": "Le Vocabulaire de Base", "order": 3, "subtopics": [
            "Les nombres (1-100)",
            "Les couleurs",
            "Les objets de la classe",
            "Les jours et les mois",
        ]},
        {"name": "Les Salutations", "order": 4, "subtopics": [
            "Les salutations courantes",
            "Se présenter",
            "Demander des nouvelles",
            "Prendre congé",
        ]},
        {"name": "La Grammaire Simple", "order": 5, "subtopics": [
            "Le nom et le verbe (introduction)",
            "Le masculin et le féminin",
            "Le singulier, le duel et le pluriel",
            "La phrase nominale simple",
        ]},
        {"name": "La Conversation", "order": 6, "subtopics": [
            "Conversations de la vie quotidienne",
            "À l'école",
            "À la maison",
            "Dialogues simples",
        ]},
    ],
    "Form 2": [
        {"name": "La Lecture", "order": 1, "subtopics": [
            "Lire des textes courts",
            "Lire des histoires simples",
            "La compréhension de lecture",
            "Répondre aux questions",
        ]},
        {"name": "L'Écriture", "order": 2, "subtopics": [
            "Écrire des phrases simples",
            "Écrire des paragraphes",
            "L'orthographe",
            "La dictée",
        ]},
        {"name": "Le Vocabulaire", "order": 3, "subtopics": [
            "La famille",
            "L'école",
            "Les aliments",
            "Les vêtements",
        ]},
        {"name": "La Grammaire (Nahw)", "order": 4, "subtopics": [
            "Les types de phrases",
            "Le nom (ism) et ses catégories",
            "Le verbe (fi'l) et ses types",
            "La particule (harf)",
            "L'accord sujet-verbe",
        ]},
        {"name": "La Morphologie (Sarf)", "order": 5, "subtopics": [
            "Les schèmes verbaux",
            "Le passé et le présent",
            "L'impératif",
            "Les dérivés du verbe",
        ]},
        {"name": "La Conversation", "order": 6, "subtopics": [
            "Parler de soi",
            "Parler de sa famille",
            "Exprimer des besoins",
            "Dialogues dirigés",
        ]},
    ],
    "Form 3": [
        {"name": "La Grammaire Avancée", "order": 1, "subtopics": [
            "La phrase verbale",
            "Le complément d'objet",
            "Les prépositions",
            "Les conjonctions",
            "La construction des phrases complexes",
        ]},
        {"name": "La Conversation", "order": 2, "subtopics": [
            "Discussions sur des sujets simples",
            "Exprimer une opinion",
            "Raconter un événement",
            "Jeux de rôle",
        ]},
        {"name": "La Littérature Arabe", "order": 3, "subtopics": [
            "La poésie arabe (introduction)",
            "La prose arabe",
            "Les proverbes et dictons",
            "Analyse de textes simples",
        ]},
        {"name": "Le Vocabulaire Thématique", "order": 4, "subtopics": [
            "Les voyages",
            "La santé",
            "Le commerce",
            "L'environnement",
        ]},
        {"name": "La Calligraphie", "order": 5, "subtopics": [
            "Les styles de calligraphie",
            "Écrire des phrases décoratives",
            "La calligraphie et la culture",
        ]},
        {"name": "La Traduction", "order": 6, "subtopics": [
            "Traduire de l'arabe vers le français",
            "Traduire du français vers l'arabe",
            "La traduction de textes simples",
            "Les erreurs courantes",
        ]},
    ],
    "Form 4": [
        {"name": "La Grammaire (Syntaxe)", "order": 1, "subtopics": [
            "Les règles de syntaxe",
            "L'analyse grammaticale",
            "Les cas et les marques",
            "La phrase complexe avancée",
        ]},
        {"name": "La Littérature", "order": 2, "subtopics": [
            "La poésie avancée",
            "Le récit et le roman",
            "Les grands auteurs arabes",
            "L'analyse littéraire",
        ]},
        {"name": "La Rédaction", "order": 3, "subtopics": [
            "Écrire une composition",
            "Écrire une lettre",
            "Rédiger un texte argumentatif",
            "Rédiger un texte narratif",
        ]},
        {"name": "La Compréhension", "order": 4, "subtopics": [
            "Comprendre des textes longs",
            "Identifier les idées principales",
            "Répondre aux questions de compréhension",
            "Le résumé",
        ]},
        {"name": "La Traduction", "order": 5, "subtopics": [
            "La traduction avancée",
            "La traduction de textes littéraires",
            "La traduction de documents",
            "Les techniques de traduction",
        ]},
        {"name": "Révision pour l'Examen", "order": 6, "subtopics": [
            "Révision de la grammaire",
            "Révision du vocabulaire",
            "Révision de la littérature",
            "Les examens antérieurs",
        ]},
    ],
}


# =============================================================================
# ADVANCED (A-LEVEL) — Form 5 & 6
# =============================================================================

ADVANCED_MATHEMATICS = {
    "Form 5": [
        {"name": "Algebra", "order": 1, "subtopics": [
            "Polynomials and rational functions",
            "Exponents, logarithms and surds",
            "Quadratic functions and equations",
            "Inequalities",
            "Partial fractions",
            "Matrices (operations and determinants)",
        ]},
        {"name": "Coordinate Geometry", "order": 2, "subtopics": [
            "The straight line",
            "The circle",
            "The parabola and ellipse",
            "The hyperbola",
            "Transformation geometry",
        ]},
        {"name": "Trigonometry", "order": 3, "subtopics": [
            "Trigonometric functions and identities",
            "Compound and multiple angles",
            "Trigonometric equations",
            "Inverse trigonometric functions",
            "Applications of trigonometry",
        ]},
        {"name": "Differentiation", "order": 4, "subtopics": [
            "Limits and continuity",
            "The derivative and its rules",
            "The chain rule",
            "Implicit and parametric differentiation",
            "Applications (rates, maxima and minima)",
            "Curve sketching",
        ]},
        {"name": "Integration", "order": 5, "subtopics": [
            "The indefinite integral",
            "Standard integrals",
            "Integration by substitution",
            "Integration by parts",
            "Definite integrals and areas",
            "Volumes of revolution",
        ]},
        {"name": "Vectors", "order": 6, "subtopics": [
            "Vector algebra",
            "Scalar and vector products",
            "Equations of lines and planes",
            "Applications of vectors",
        ]},
        {"name": "Statistics and Probability", "order": 7, "subtopics": [
            "Measures of central tendency and dispersion",
            "Probability rules",
            "Conditional probability",
            "Binomial and Poisson distributions",
        ]},
    ],
    "Form 6": [
        {"name": "Advanced Integration", "order": 1, "subtopics": [
            "Integration by partial fractions",
            "Reduction formulae",
            "Numerical integration (trapezium and Simpson)",
            "Improper integrals",
        ]},
        {"name": "Differential Equations", "order": 2, "subtopics": [
            "First order differential equations",
            "Separable and linear equations",
            "Second order equations",
            "Applications of differential equations",
        ]},
        {"name": "Complex Numbers", "order": 3, "subtopics": [
            "The complex plane",
            "Modulus and argument",
            "De Moivre's theorem",
            "Roots of complex numbers",
            "Applications of complex numbers",
        ]},
        {"name": "Matrices and Transformations", "order": 4, "subtopics": [
            "Matrix algebra (advanced)",
            "Determinants and inverses",
            "Linear transformations",
            "Eigenvalues and eigenvectors",
            "Applications of matrices",
        ]},
        {"name": "Linear Programming", "order": 5, "subtopics": [
            "Formulating linear programming problems",
            "Graphical methods",
            "The simplex method (introduction)",
            "Applications in business and industry",
        ]},
        {"name": "Mechanics", "order": 6, "subtopics": [
            "Forces and equilibrium",
            "Momentum and impulse",
            "Work, energy and power",
            "Projectiles and circular motion",
            "Simple harmonic motion",
        ]},
        {"name": "Further Statistics", "order": 7, "subtopics": [
            "Continuous distributions",
            "The normal distribution",
            "Sampling and estimation",
            "Hypothesis testing",
            "Correlation and regression",
        ]},
        {"name": "Proof and Problem Solving", "order": 8, "subtopics": [
            "Methods of proof",
            "Mathematical induction",
            "Problem-solving strategies",
            "Revision for ACSEE",
        ]},
    ],
}


ADVANCED_PHYSICS = {
    "Form 5": [
        {"name": "Measurements and Errors", "order": 1, "subtopics": [
            "Physical quantities and SI units",
            "Measurement techniques and instruments",
            "Accuracy, precision and errors",
            "Graphical analysis of data",
        ]},
        {"name": "Mechanics", "order": 2, "subtopics": [
            "Kinematics (linear and projectile motion)",
            "Newton's laws of motion",
            "Work, energy and power",
            "Momentum and collisions",
            "Circular motion and gravitation",
        ]},
        {"name": "Properties of Matter", "order": 3, "subtopics": [
            "Elasticity (stress, strain and Young's modulus)",
            "Pressure in fluids",
            "Archimedes' principle and floatation",
            "Viscosity and surface tension",
        ]},
        {"name": "Heat and Thermodynamics", "order": 4, "subtopics": [
            "Temperature and heat",
            "The gas laws and kinetic theory",
            "Thermodynamics (first law)",
            "Heat transfer (conduction, convection, radiation)",
        ]},
        {"name": "Waves", "order": 5, "subtopics": [
            "Progressive waves",
            "Superposition and interference",
            "Stationary waves",
            "Sound waves and their properties",
        ]},
        {"name": "Geometric Optics", "order": 6, "subtopics": [
            "Reflection and refraction",
            "Lenses and optical instruments",
            "The prism and dispersion",
            "Optical fibres",
        ]},
    ],
    "Form 6": [
        {"name": "Electricity", "order": 1, "subtopics": [
            "Electrostatics",
            "Capacitors and dielectrics",
            "Current electricity (advanced)",
            "Electrical circuits and measurements",
        ]},
        {"name": "Magnetism and Electromagnetism", "order": 2, "subtopics": [
            "Magnetic fields",
            "Forces on currents and charges",
            "Electromagnetic induction",
            "Inductance and transformers",
        ]},
        {"name": "Alternating Currents", "order": 3, "subtopics": [
            "AC circuits (R, L, C)",
            "Impedance and resonance",
            "AC power and power factor",
            "Applications of AC",
        ]},
        {"name": "Modern Physics", "order": 4, "subtopics": [
            "The photoelectric effect",
            "Quantum theory (basics)",
            "Atomic structure and spectra",
            "Nuclear physics (radioactivity, fission, fusion)",
        ]},
        {"name": "Electronics", "order": 5, "subtopics": [
            "Semiconductors and diodes",
            "Transistors and amplifiers",
            "Logic gates",
            "Applications of electronics",
        ]},
        {"name": "Applied Physics", "order": 6, "subtopics": [
            "Measurement instruments",
            "Energy resources and conservation",
            "Medical physics applications",
            "Revision for ACSEE",
        ]},
    ],
}


ADVANCED_CHEMISTRY = {
    "Form 5": [
        {"name": "Atomic Structure and Periodicity", "order": 1, "subtopics": [
            "Subatomic particles and atomic models",
            "Electronic configuration",
            "The periodic table and periodicity",
            "Ionisation energy and electron affinity",
        ]},
        {"name": "Chemical Bonding", "order": 2, "subtopics": [
            "Ionic and covalent bonding",
            "Metallic bonding",
            "Intermolecular forces",
            "Shapes of molecules (VSEPR)",
            "Hybridisation",
        ]},
        {"name": "Stoichiometry", "order": 3, "subtopics": [
            "The mole concept (advanced)",
            "Chemical formulae and equations",
            "Concentrations of solutions",
            "Titrations and volumetric analysis",
            "Empirical and molecular formulae",
        ]},
        {"name": "States of Matter", "order": 4, "subtopics": [
            "The gaseous state and gas laws",
            "The liquid state",
            "The solid state",
            "Phase changes and phase diagrams",
        ]},
        {"name": "Energetics", "order": 5, "subtopics": [
            "Enthalpy changes",
            "Hess's law",
            "Bond energies",
            "Entropy and free energy",
        ]},
        {"name": "Chemical Kinetics", "order": 6, "subtopics": [
            "Rates of reaction",
            "Factors affecting rates",
            "Order of reaction and rate laws",
            "Reaction mechanisms (basics)",
        ]},
        {"name": "Chemical Equilibrium", "order": 7, "subtopics": [
            "The equilibrium constant",
            "Le Chatelier's principle",
            "Acid-base equilibria",
            "Solubility product",
        ]},
    ],
    "Form 6": [
        {"name": "Acids, Bases and Salts (Advanced)", "order": 1, "subtopics": [
            "Acid-base theories",
            "pH and indicators",
            "Buffer solutions",
            "Hydrolysis of salts",
        ]},
        {"name": "Electrochemistry", "order": 2, "subtopics": [
            "Electrolytic cells",
            "Galvanic cells and electrode potentials",
            "Electrolysis and Faraday's laws",
            "Applications of electrochemistry",
        ]},
        {"name": "Organic Chemistry — Hydrocarbons", "order": 3, "subtopics": [
            "Alkanes",
            "Alkenes and alkynes",
            "Arenes (benzene)",
            "Reactions and mechanisms",
        ]},
        {"name": "Organic Chemistry — Functional Groups", "order": 4, "subtopics": [
            "Halogenoalkanes",
            "Alcohols and phenols",
            "Aldehydes and ketones",
            "Carboxylic acids and esters",
            "Amines and amides",
            "Polymers",
        ]},
        {"name": "Transition Metals", "order": 5, "subtopics": [
            "General properties",
            "Complexes and ligands",
            "Colour and magnetic properties",
            "Catalysis by transition metals",
        ]},
        {"name": "Environmental and Applied Chemistry", "order": 6, "subtopics": [
            "Air and water pollution",
            "Green chemistry",
            "Industrial chemistry (ammonia, sulphuric acid)",
            "Revision for ACSEE",
        ]},
    ],
}


ADVANCED_BIOLOGY = {
    "Form 5": [
        {"name": "Cytology", "order": 1, "subtopics": [
            "Cell structure and organelles",
            "Cell membranes and transport",
            "The nucleus and chromosomes",
            "Cell division (mitosis and meiosis)",
            "Cell specialisation",
        ]},
        {"name": "Biochemistry", "order": 2, "subtopics": [
            "Carbohydrates",
            "Proteins and amino acids",
            "Lipids",
            "Nucleic acids",
            "Vitamins and minerals",
            "Water and its biological importance",
        ]},
        {"name": "Enzymology", "order": 3, "subtopics": [
            "Nature and properties of enzymes",
            "Mechanism of enzyme action",
            "Factors affecting enzyme activity",
            "Enzyme inhibition",
            "Applications of enzymes",
        ]},
        {"name": "Plant Physiology", "order": 4, "subtopics": [
            "Water uptake and transport",
            "Photosynthesis",
            "Respiration in plants",
            "Mineral nutrition",
            "Plant growth and hormones",
        ]},
        {"name": "Animal Physiology", "order": 5, "subtopics": [
            "Nutrition and digestion",
            "Respiration and gas exchange",
            "Circulation and transport",
            "Excretion and osmoregulation",
            "Temperature regulation",
        ]},
        {"name": "Classification and Diversity", "order": 6, "subtopics": [
            "Principles of classification",
            "Kingdom Monera and Protoctista",
            "Kingdom Fungi",
            "Kingdom Plantae",
            "Kingdom Animalia",
        ]},
        {"name": "Genetics (Basics)", "order": 7, "subtopics": [
            "Mendelian inheritance",
            "Monohybrid and dihybrid crosses",
            "Sex-linked inheritance",
            "Gene interaction",
        ]},
    ],
    "Form 6": [
        {"name": "Genetics (Advanced)", "order": 1, "subtopics": [
            "DNA structure and replication",
            "Protein synthesis",
            "Gene mutation",
            "Chromosomal aberrations",
            "Genetic engineering and biotechnology",
        ]},
        {"name": "Evolution", "order": 2, "subtopics": [
            "Evidence of evolution",
            "Theories of evolution",
            "Natural selection",
            "Speciation",
            "Human evolution",
        ]},
        {"name": "Ecology", "order": 3, "subtopics": [
            "Ecosystems and energy flow",
            "Biogeochemical cycles",
            "Population ecology",
            "Community ecology and succession",
            "Conservation and environmental issues",
        ]},
        {"name": "Reproduction", "order": 4, "subtopics": [
            "Reproduction in plants",
            "Reproduction in animals",
            "Hormonal control of reproduction",
            "Human reproductive health",
        ]},
        {"name": "Coordination and Control", "order": 5, "subtopics": [
            "The nervous system",
            "The endocrine system",
            "Receptors and effectors",
            "Plant responses",
            "Homeostasis",
        ]},
        {"name": "Growth and Development", "order": 6, "subtopics": [
            "Patterns of growth",
            "Growth in plants",
            "Growth in animals",
            "Factors affecting growth",
        ]},
        {"name": "Applied Biology", "order": 7, "subtopics": [
            "Biotechnology (fermentation, genetic engineering)",
            "Medical applications",
            "Agricultural applications",
            "Environmental applications",
            "Revision for ACSEE",
        ]},
    ],
}


ADVANCED_ENGLISH = {
    "Form 5": [
        {"name": "Advanced Grammar", "order": 1, "subtopics": [
            "Sentence structures and patterns",
            "Tenses and aspects (advanced)",
            "Modality and conditionals",
            "Reported speech",
            "Punctuation and mechanics",
            "Common grammatical errors",
        ]},
        {"name": "Essay Writing", "order": 2, "subtopics": [
            "The essay structure",
            "Argumentative essays",
            "Expository essays",
            "Narrative and descriptive essays",
            "Persuasive writing",
        ]},
        {"name": "Summary Writing", "order": 3, "subtopics": [
            "Identifying main ideas",
            "Paraphrasing",
            "Writing summaries within word limits",
            "Summarising different text types",
        ]},
        {"name": "Reading Comprehension", "order": 4, "subtopics": [
            "Reading for gist and detail",
            "Inference and deduction",
            "Critical reading",
            "Text analysis",
        ]},
        {"name": "Oral Communication", "order": 5, "subtopics": [
            "Public speaking",
            "Debates and discussions",
            "Presentations",
            "Listening skills",
        ]},
        {"name": "Phonetics and Phonology", "order": 6, "subtopics": [
            "Speech sounds",
            "Stress and intonation",
            "Pronunciation skills",
            "Spoken English in context",
        ]},
    ],
    "Form 6": [
        {"name": "Advanced Composition", "order": 1, "subtopics": [
            "Writing for different audiences",
            "Academic writing style",
            "Creative writing",
            "Journalistic writing",
            "Editing and proofreading",
        ]},
        {"name": "Literary Analysis", "order": 2, "subtopics": [
            "Prose analysis",
            "Poetry analysis",
            "Drama analysis",
            "Literary devices and techniques",
            "Writing literary essays",
        ]},
        {"name": "Research and Report Writing", "order": 3, "subtopics": [
            "Research methods (basics)",
            "Referencing and citations",
            "Writing reports",
            "Writing research papers",
        ]},
        {"name": "Translation and Interpretation", "order": 4, "subtopics": [
            "Translation techniques",
            "Translation between English and Kiswahili",
            "Interpretation skills",
            "Accuracy and style in translation",
        ]},
        {"name": "Integrated Language Skills", "order": 5, "subtopics": [
            "Integrating reading, writing, listening and speaking",
            "Language in the media",
            "Language and society",
            "Revision for ACSEE",
        ]},
    ],
}


ADVANCED_KISWAHILI = {
    "Form 5": [
        {"name": "Sarufi ya Kina", "order": 1, "subtopics": [
            "Ngeli za nomino (kina)",
            "Uundaji wa maneno (unyambuaji na utohoaji)",
            "Muundo wa sentensi",
            "Matumizi ya lugha (pragmatiki)",
            "Makosa ya kisarufi na marekebisho",
        ]},
        {"name": "Fasihi: Nadharia na Uhakiki", "order": 2, "subtopics": [
            "Dhana ya fasihi na tanzu zake",
            "Nadharia za fasihi",
            "Vipengele vya uhakiki",
            "Uhakiki wa riwaya",
            "Uhakiki wa tamthilia",
            "Uhakiki wa ushairi",
        ]},
        {"name": "Ushairi", "order": 3, "subtopics": [
            "Aina za mashairi",
            "Vipengele vya ushairi",
            "Uchambuzi wa mashairi",
            "Uhakiki wa mashairi",
            "Utungaji wa mashairi",
        ]},
        {"name": "Insha za Kina", "order": 4, "subtopics": [
            "Insha za hoja",
            "Insha za makala",
            "Insha za kiutendaji",
            "Uandishi wa insha bora",
        ]},
        {"name": "Matumizi ya Lugha", "order": 5, "subtopics": [
            "Misamiati na istilahi",
            "Nahau, methali, misemo na vitendawili",
            "Maana za maneno katika muktadha",
            "Lugha ya mitaani na usanifu",
        ]},
        {"name": "Tamthilia na Riwaya", "order": 6, "subtopics": [
            "Tamthilia za Kiswahili",
            "Riwaya za Kiswahili",
            "Uchambuzi wa kazi teule",
            "Mbinu za kisanii katika tamthilia na riwaya",
        ]},
    ],
    "Form 6": [
        {"name": "Uhakiki wa Fasihi (Kina)", "order": 1, "subtopics": [
            "Nadharia za uhakiki (kina)",
            "Uhakiki linganishi",
            "Uhakiki wa kazi teule za ACSEE",
            "Uandishi wa makala ya uhakiki",
        ]},
        {"name": "Fasihi Simulizi", "order": 2, "subtopics": [
            "Dhana ya fasihi simulizi",
            "Tanzu za fasihi simulizi",
            "Vipera vya fasihi simulizi",
            "Kuhifadhi fasihi simulizi",
        ]},
        {"name": "Lugha na Jamii", "order": 3, "subtopics": [
            "Lugha na utamaduni",
            "Lugha na mawasiliano",
            "Tathmini ya lugha",
            "Sera ya lugha Tanzania",
        ]},
        {"name": "Utafiti wa Lugha", "order": 4, "subtopics": [
            "Mbinu za utafiti wa lugha",
            "Kukusanya data ya lugha",
            "Kuchambua data ya lugha",
            "Kuandika ripoti ya utafiti",
        ]},
        {"name": "Uandishi wa Makala", "order": 5, "subtopics": [
            "Aina za makala",
            "Muundo wa makala",
            "Uandishi wa makala za kitaaluma",
            "Uandishi wa makala za magazeti",
        ]},
        {"name": "Mapitio ya ACSEE", "order": 6, "subtopics": [
            "Mapitio ya sarufi",
            "Mapitio ya fasihi",
            "Mapitio ya insha",
            "Mazoezi ya maswali ya ACSEE",
        ]},
    ],
}


ADVANCED_COMMUNICATION = {
    "Form 5": [
        {"name": "Academic Writing Basics", "order": 1, "subtopics": [
            "Features of academic writing",
            "Academic style and tone",
            "Paragraph development",
            "Cohesion and coherence",
        ]},
        {"name": "Reading Academic Texts", "order": 2, "subtopics": [
            "Reading strategies",
            "Critical reading of academic texts",
            "Analysing arguments",
            "Evaluating sources",
        ]},
        {"name": "Note-taking and Summarising", "order": 3, "subtopics": [
            "Note-taking techniques",
            "Summarising academic texts",
            "Paraphrasing and quoting",
            "Synthesising information",
        ]},
        {"name": "Presentation Skills", "order": 4, "subtopics": [
            "Planning a presentation",
            "Delivering presentations",
            "Using visual aids",
            "Handling questions",
        ]},
        {"name": "Research Basics", "order": 5, "subtopics": [
            "What is research",
            "Formulating research questions",
            "Data collection methods",
            "Ethics in research",
        ]},
        {"name": "Referencing", "order": 6, "subtopics": [
            "Why we reference",
            "The APA style",
            "The MLA style",
            "Avoiding plagiarism",
        ]},
    ],
    "Form 6": [
        {"name": "Research Methods", "order": 1, "subtopics": [
            "Quantitative and qualitative research",
            "Sampling techniques",
            "Data analysis",
            "Presenting research findings",
        ]},
        {"name": "Writing Research Proposals", "order": 2, "subtopics": [
            "Structure of a research proposal",
            "The problem statement",
            "Literature review",
            "Methodology and budget",
        ]},
        {"name": "Report Writing", "order": 3, "subtopics": [
            "Types of reports",
            "Structure of reports",
            "Writing clear and concise reports",
            "Editing reports",
        ]},
        {"name": "Critical Thinking and Analysis", "order": 4, "subtopics": [
            "Arguments and reasoning",
            "Fallacies",
            "Critical analysis of texts",
            "Problem solving",
        ]},
        {"name": "Academic Presentations", "order": 5, "subtopics": [
            "Defending a research proposal",
            "Presenting findings",
            "Academic discussions and seminars",
            "Peer review",
        ]},
        {"name": "Thesis Writing Basics", "order": 6, "subtopics": [
            "Structure of a thesis/dissertation",
            "Writing chapters",
            "Referencing in theses",
            "Revision and finalisation",
        ]},
    ],
}


ADVANCED_LITERATURE = {
    "Form 5": [
        {"name": "Introduction to Literature", "order": 1, "subtopics": [
            "Definition and functions of literature",
            "Genres of literature",
            "The relationship between literature and society",
            "Literary appreciation",
        ]},
        {"name": "Prose", "order": 2, "subtopics": [
            "The novel",
            "The short story",
            "Elements of prose (plot, character, setting, theme)",
            "Narrative techniques",
            "Reading and analysing prose texts",
        ]},
        {"name": "Poetry", "order": 3, "subtopics": [
            "Forms of poetry",
            "Poetic devices",
            "Meter, rhyme and rhythm",
            "Themes in poetry",
            "Analysing poems",
        ]},
        {"name": "Drama", "order": 4, "subtopics": [
            "Elements of drama",
            "Types of drama",
            "Stagecraft and theatre",
            "Analysing plays",
        ]},
        {"name": "Literary Devices", "order": 5, "subtopics": [
            "Figures of speech",
            "Imagery and symbolism",
            "Irony and satire",
            "Style and diction",
        ]},
        {"name": "African Literature", "order": 6, "subtopics": [
            "Introduction to African literature",
            "Oral tradition in Africa",
            "African novels and short stories",
            "African poetry and drama",
        ]},
    ],
    "Form 6": [
        {"name": "Advanced Literary Analysis", "order": 1, "subtopics": [
            "Close reading",
            "Thematic analysis",
            "Character analysis",
            "Structural analysis",
            "Writing critical essays",
        ]},
        {"name": "Shakespearean Drama", "order": 2, "subtopics": [
            "Introduction to Shakespeare",
            "The tragedies",
            "The comedies",
            "Language and imagery in Shakespeare",
            "Analysing a Shakespearean play",
        ]},
        {"name": "Modern Drama", "order": 3, "subtopics": [
            "Theatre of the absurd",
            "Modern African drama",
            "Contemporary playwrights",
            "Drama and social change",
        ]},
        {"name": "World Literature", "order": 4, "subtopics": [
            "Literature from different continents",
            "Postcolonial literature",
            "Translation and world literature",
            "Comparative themes",
        ]},
        {"name": "Literary Criticism", "order": 5, "subtopics": [
            "Schools of criticism",
            "Feminist criticism",
            "Marxist criticism",
            "Psychoanalytic criticism",
            "Postcolonial criticism",
        ]},
        {"name": "Comparative Literature", "order": 6, "subtopics": [
            "Comparing texts across cultures",
            "Comparing genres",
            "Themes across literature",
            "Revision for ACSEE",
        ]},
    ],
}


ADVANCED_FASIHI = {
    "Form 5": [
        {"name": "Utangulizi wa Fasihi", "order": 1, "subtopics": [
            "Dhana ya fasihi",
            "Aina za fasihi",
            "Umuhimu wa fasihi",
            "Fasihi na jamii",
        ]},
        {"name": "Fasihi Simulizi", "order": 2, "subtopics": [
            "Tanzu za fasihi simulizi",
            "Ngano, hadithi na hekaya",
            "Methali, nahau na vitendawili",
            "Nyimbo na tenzi",
            "Uhifadhi wa fasihi simulizi",
        ]},
        {"name": "Ushairi", "order": 3, "subtopics": [
            "Aina za mashairi",
            "Vipengele vya ushairi",
            "Uchambuzi wa mashairi",
            "Utungaji wa mashairi",
        ]},
        {"name": "Riwaya", "order": 4, "subtopics": [
            "Dhana ya riwaya",
            "Vipengele vya riwaya",
            "Uchambuzi wa riwaya teule",
            "Mbinu za kisanii katika riwaya",
        ]},
        {"name": "Tamthilia", "order": 5, "subtopics": [
            "Dhana ya tamthilia",
            "Vipengele vya tamthilia",
            "Uchambuzi wa tamthilia teule",
            "Mbinu za kisanii katika tamthilia",
        ]},
        {"name": "Hadithi Fupi", "order": 6, "subtopics": [
            "Dhana ya hadithi fupi",
            "Vipengele vya hadithi fupi",
            "Uchambuzi wa hadithi fupi",
            "Uandishi wa hadithi fupi",
        ]},
    ],
    "Form 6": [
        {"name": "Uhakiki wa Fasihi", "order": 1, "subtopics": [
            "Dhana ya uhakiki",
            "Vigezo vya uhakiki",
            "Uhakiki wa riwaya na tamthilia",
            "Uhakiki wa ushairi na hadithi fupi",
        ]},
        {"name": "Nadharia za Fasihi", "order": 2, "subtopics": [
            "Nadharia ya kijamii",
            "Nadharia ya kisaikolojia",
            "Nadharia ya kiisimu",
            "Nadharia za kisasa",
        ]},
        {"name": "Fasihi Linganishi", "order": 3, "subtopics": [
            "Dhana ya fasihi linganishi",
            "Kulinganisha kazi za fasihi",
            "Fasihi ya Kiswahili na fasihi za kigeni",
        ]},
        {"name": "Fasihi ya Kiswahili ya Kisasa", "order": 4, "subtopics": [
            "Fasihi andishi ya kisasa",
            "Fasihi ya mtandao",
            "Waandishi wa kisasa wa Kiswahili",
            "Mwelekeo mpya katika fasihi",
        ]},
        {"name": "Uandishi wa Kisanii", "order": 5, "subtopics": [
            "Mbinu za uandishi wa kisanii",
            "Uandishi wa riwaya",
            "Uandishi wa tamthilia",
            "Uandishi wa ushairi",
        ]},
        {"name": "Mapitio ya ACSEE", "order": 6, "subtopics": [
            "Mapitio ya uhakiki",
            "Mapitio ya tanzu zote",
            "Mazoezi ya maswali ya ACSEE",
            "Uandishi wa majibu bora",
        ]},
    ],
}


ADVANCED_ECONOMICS = {
    "Form 5": [
        {"name": "Introduction to Economics", "order": 1, "subtopics": [
            "Definition and scope of economics",
            "Scarcity, choice and opportunity cost",
            "Economic systems",
            "The circular flow of income",
        ]},
        {"name": "Demand and Supply", "order": 2, "subtopics": [
            "The theory of demand",
            "The theory of supply",
            "Market equilibrium",
            "Elasticity of demand and supply",
            "Applications of elasticity",
        ]},
        {"name": "Theory of Production", "order": 3, "subtopics": [
            "The factors of production",
            "Production functions",
            "Returns to scale",
            "Costs of production",
        ]},
        {"name": "Market Structures", "order": 4, "subtopics": [
            "Perfect competition",
            "Monopoly",
            "Monopolistic competition",
            "Oligopoly",
            "Price determination in different markets",
        ]},
        {"name": "National Income", "order": 5, "subtopics": [
            "Concepts of national income",
            "Measuring national income",
            "The multiplier and accelerator",
            "Income distribution",
        ]},
        {"name": "Money and Banking", "order": 6, "subtopics": [
            "The functions of money",
            "The banking system",
            "Central banking and monetary policy",
            "Inflation and deflation",
        ]},
        {"name": "Economic Development", "order": 7, "subtopics": [
            "Concepts of development",
            "Characteristics of developing countries",
            "Obstacles to development",
            "Development strategies",
        ]},
    ],
    "Form 6": [
        {"name": "Macroeconomics", "order": 1, "subtopics": [
            "Aggregate demand and supply",
            "Unemployment",
            "Fiscal policy",
            "Monetary policy",
            "Economic growth",
        ]},
        {"name": "International Trade", "order": 2, "subtopics": [
            "The basis of international trade",
            "Balance of payments",
            "Exchange rates",
            "Trade policies and protectionism",
            "Regional integration (EAC, AU)",
        ]},
        {"name": "Public Finance", "order": 3, "subtopics": [
            "Public expenditure",
            "Taxation",
            "Public debt",
            "Government budgeting",
        ]},
        {"name": "Economic Planning", "order": 4, "subtopics": [
            "Types of economic planning",
            "Planning in Tanzania",
            "Project appraisal",
            "Cost-benefit analysis",
        ]},
        {"name": "Agricultural and Industrial Economics", "order": 5, "subtopics": [
            "Agricultural economics",
            "Industrial development",
            "Agro-industries",
            "Industrialisation strategies",
        ]},
        {"name": "Labour Economics", "order": 6, "subtopics": [
            "Labour markets",
            "Wages and employment",
            "Trade unions",
            "Human capital",
        ]},
        {"name": "Revision for ACSEE", "order": 7, "subtopics": [
            "Mapitio ya microeconomics",
            "Mapitio ya macroeconomics",
            "Past paper practice",
            "Essay writing in economics",
        ]},
    ],
}


ADVANCED_GEOGRAPHY = {
    "Form 5": [
        {"name": "Physical Geography — Geomorphology", "order": 1, "subtopics": [
            "The structure of the earth",
            "Rocks and weathering",
            "Earth movements and landforms",
            "Glaciation and its landforms",
            "Coastal landforms",
        ]},
        {"name": "Climatology", "order": 2, "subtopics": [
            "The atmosphere and its composition",
            "Insolation and temperature",
            "Pressure and winds",
            "Moisture in the atmosphere",
            "Climatic types and regions",
            "Climate change",
        ]},
        {"name": "Biogeography", "order": 3, "subtopics": [
            "The biosphere and ecosystems",
            "Soils and soil formation",
            "Vegetation types",
            "Wildlife and conservation",
        ]},
        {"name": "Map Work", "order": 4, "subtopics": [
            "Map reading and interpretation",
            "Topographic maps",
            "Compass bearings and directions",
            "Scale, distance and area",
            "Cross-sections and profiles",
        ]},
        {"name": "Population Studies", "order": 5, "subtopics": [
            "Population distribution and density",
            "Population structure",
            "Population dynamics (birth, death, migration)",
            "Population policies",
        ]},
        {"name": "Settlement Geography", "order": 6, "subtopics": [
            "Types of settlements",
            "Rural settlements",
            "Urban settlements",
            "Urbanisation in Tanzania and Africa",
        ]},
    ],
    "Form 6": [
        {"name": "Economic Geography — Agriculture", "order": 1, "subtopics": [
            "Subsistence and commercial agriculture",
            "Food crops and cash crops",
            "Livestock keeping",
            "Agricultural systems in Tanzania and Africa",
        ]},
        {"name": "Mining and Energy", "order": 2, "subtopics": [
            "Minerals and mining",
            "Energy resources",
            "Renewable and non-renewable energy",
            "Mining and the environment",
        ]},
        {"name": "Industry", "order": 3, "subtopics": [
            "Industrial location theory",
            "Types of industries",
            "Industrialisation in Tanzania",
            "Industrial development in Africa",
        ]},
        {"name": "Transport and Trade", "order": 4, "subtopics": [
            "Modes of transport",
            "Trade and commerce",
            "Regional trade blocs",
            "Transport and development",
        ]},
        {"name": "Environmental Management", "order": 5, "subtopics": [
            "Environmental problems",
            "Natural resources management",
            "Sustainable development",
            "Environmental policies",
        ]},
        {"name": "Regional Geography", "order": 6, "subtopics": [
            "Regional geography of Tanzania",
            "Regional geography of Africa",
            "Regional geography of the world",
            "Comparative regional studies",
        ]},
        {"name": "Research Methodology and Revision", "order": 7, "subtopics": [
            "Field research methods",
            "Data collection and analysis",
            "Writing geographical reports",
            "Revision for ACSEE",
        ]},
    ],
}


ADVANCED_HISTORY = {
    "Form 5": [
        {"name": "Introduction to History", "order": 1, "subtopics": [
            "Meaning and importance of history",
            "Sources of history",
            "Historical research methods",
            "The relationship between history and other disciplines",
        ]},
        {"name": "Pre-colonial Africa", "order": 2, "subtopics": [
            "Early societies in Africa",
            "The development of agriculture",
            "Trade in pre-colonial Africa",
            "States and empires (Ghana, Mali, Songhay)",
            "Social and political organisation",
        ]},
        {"name": "The Scramble for Africa", "order": 3, "subtopics": [
            "Causes of the scramble",
            "The Berlin Conference",
            "The partition of Africa",
            "Colonial conquest and resistance",
        ]},
        {"name": "Colonial Administration", "order": 4, "subtopics": [
            "Indirect rule",
            "Direct rule",
            "Assimilation and association",
            "The colonial economy",
            "Colonial social policies",
        ]},
        {"name": "African Responses to Colonialism", "order": 5, "subtopics": [
            "Primary resistance",
            "Religious movements",
            "The rise of nationalism",
            "Trade unions and political parties",
        ]},
        {"name": "African Nationalism", "order": 6, "subtopics": [
            "Factors for the rise of nationalism",
            "Nationalist movements in East Africa",
            "Nationalist movements in West Africa",
            "Nationalist movements in Southern Africa",
        ]},
    ],
    "Form 6": [
        {"name": "African Independence Movements", "order": 1, "subtopics": [
            "Ghana — the first independent state",
            "The independence of Tanganyika and Zanzibar",
            "Independence in Kenya and Uganda",
            "Independence in West and Southern Africa",
        ]},
        {"name": "Post-independence Africa", "order": 2, "subtopics": [
            "State building after independence",
            "Political instability and coups",
            "Economic development challenges",
            "Pan-Africanism and the OAU/AU",
        ]},
        {"name": "International Relations", "order": 3, "subtopics": [
            "The Cold War and Africa",
            "Non-alignment",
            "The United Nations and Africa",
            "South-South cooperation",
            "The New International Economic Order",
        ]},
        {"name": "Economic History of Africa", "order": 4, "subtopics": [
            "The colonial economic legacy",
            "Structural adjustment programmes",
            "Regional integration (EAC, SADC, ECOWAS)",
            "Africa in the global economy",
        ]},
        {"name": "Tanzania's Foreign Policy", "order": 5, "subtopics": [
            "The principles of Tanzania's foreign policy",
            "Tanzania and the liberation of Southern Africa",
            "Tanzania in the EAC",
            "Tanzania in international organisations",
        ]},
        {"name": "East African Cooperation", "order": 6, "subtopics": [
            "The history of East African cooperation",
            "The East African Community (re-established)",
            "Cooperation in trade, transport and security",
            "Challenges and prospects of integration",
        ]},
        {"name": "Revision for ACSEE", "order": 7, "subtopics": [
            "Revision of pre-colonial and colonial Africa",
            "Revision of nationalism and independence",
            "Revision of international relations",
            "Past paper practice",
        ]},
    ],
}


ADVANCED_ACCOUNTANCY = {
    "Form 5": [
        {"name": "Introduction to Accounting", "order": 1, "subtopics": [
            "The nature and purpose of accounting",
            "Users of accounting information",
            "The accounting equation",
            "The double entry system",
        ]},
        {"name": "Accounting Concepts and Conventions", "order": 2, "subtopics": [
            "Accounting concepts",
            "Accounting conventions",
            "The qualitative characteristics of accounting information",
        ]},
        {"name": "Books of Original Entry", "order": 3, "subtopics": [
            "The journal",
            "Cash book and petty cash book",
            "Sales and purchases day books",
            "Returns day books",
        ]},
        {"name": "The Ledger and Trial Balance", "order": 4, "subtopics": [
            "Posting to the ledger",
            "Balancing ledger accounts",
            "The trial balance",
            "Correction of errors",
            "The suspense account",
        ]},
        {"name": "Final Accounts", "order": 5, "subtopics": [
            "Trading account",
            "Profit and loss account",
            "The balance sheet",
            "Adjustments (accruals, prepayments, depreciation)",
        ]},
        {"name": "Bank Reconciliation", "order": 6, "subtopics": [
            "The bank statement",
            "The cash book",
            "Preparing the bank reconciliation statement",
            "Bank errors and timing differences",
        ]},
    ],
    "Form 6": [
        {"name": "Company Accounts", "order": 1, "subtopics": [
            "The nature of companies",
            "Share capital and loan capital",
            "The issue of shares",
            "Final accounts of companies",
        ]},
        {"name": "Partnership Accounts", "order": 2, "subtopics": [
            "The nature of partnerships",
            "Partnership agreements",
            "Appropriation of profits",
            "Admission and retirement of partners",
            "Dissolution of partnerships",
        ]},
        {"name": "Depreciation and Provisions", "order": 3, "subtopics": [
            "Methods of depreciation",
            "Depreciation and asset disposal",
            "Provisions and reserves",
            "Irrecoverable debts and allowances",
        ]},
        {"name": "Financial Statement Analysis", "order": 4, "subtopics": [
            "Ratio analysis",
            "Liquidity ratios",
            "Profitability ratios",
            "Efficiency ratios",
            "Interpretation of financial statements",
        ]},
        {"name": "Cost Accounting", "order": 5, "subtopics": [
            "Cost classification",
            "Materials, labour and overheads",
            "Job and process costing",
            "Marginal costing",
        ]},
        {"name": "Budgeting", "order": 6, "subtopics": [
            "The purpose of budgeting",
            "Preparing budgets",
            "Cash budgets",
            "Flexible and fixed budgets",
            "Budgetary control",
        ]},
        {"name": "Auditing and Revision", "order": 7, "subtopics": [
            "The nature of auditing",
            "Internal and external audit",
            "Audit procedures",
            "Revision for ACSEE",
        ]},
    ],
}


ADVANCED_COMPUTER = {
    "Form 5": [
        {"name": "Introduction to Computer Science", "order": 1, "subtopics": [
            "Computer systems and their components",
            "The history of computing",
            "Classification of computers",
            "Computers in society",
        ]},
        {"name": "Computer Hardware", "order": 2, "subtopics": [
            "The central processing unit",
            "Memory and storage devices",
            "Input and output devices",
            "Interfaces and ports",
        ]},
        {"name": "Computer Software", "order": 3, "subtopics": [
            "System software",
            "Application software",
            "Programming languages",
            "Software licensing",
        ]},
        {"name": "Operating Systems", "order": 4, "subtopics": [
            "Functions of operating systems",
            "Process management",
            "Memory management",
            "File systems",
            "Examples of operating systems",
        ]},
        {"name": "Data Representation", "order": 5, "subtopics": [
            "Number systems (binary, octal, hexadecimal)",
            "Data representation in computers",
            "Logic gates and circuits",
            "Data storage units",
        ]},
        {"name": "Programming Basics", "order": 6, "subtopics": [
            "Introduction to programming",
            "Variables and data types",
            "Control structures",
            "Functions and procedures",
            "Pseudocode and flowcharts",
        ]},
        {"name": "Networking", "order": 7, "subtopics": [
            "Types of networks",
            "Network topologies",
            "The OSI model",
            "The internet and the web",
            "Network security (basics)",
        ]},
    ],
    "Form 6": [
        {"name": "Data Structures", "order": 1, "subtopics": [
            "Arrays and lists",
            "Stacks and queues",
            "Linked lists",
            "Trees and graphs",
            "Searching and sorting",
        ]},
        {"name": "Algorithms", "order": 2, "subtopics": [
            "Algorithm design",
            "Complexity analysis",
            "Recursion",
            "Algorithm paradigms (divide and conquer, dynamic programming)",
        ]},
        {"name": "Database Management", "order": 3, "subtopics": [
            "The database approach",
            "The relational model",
            "SQL (queries, joins, updates)",
            "Database design and normalisation",
            "Database administration",
        ]},
        {"name": "Web Development", "order": 4, "subtopics": [
            "HTML and CSS",
            "JavaScript (basics)",
            "Client-server architecture",
            "Web security",
        ]},
        {"name": "Software Engineering", "order": 5, "subtopics": [
            "The software development life cycle",
            "Requirements analysis",
            "Design and implementation",
            "Testing and maintenance",
        ]},
        {"name": "System Analysis and Design", "order": 6, "subtopics": [
            "Systems analysis",
            "Feasibility study",
            "System design tools (DFD, ERD)",
            "Implementation and evaluation",
        ]},
        {"name": "Emerging Technologies", "order": 7, "subtopics": [
            "Artificial intelligence",
            "Machine learning (basics)",
            "The Internet of Things",
            "Cloud computing",
            "Cyber security",
            "Revision for ACSEE",
        ]},
    ],
}


ADVANCED_BAM = {
    "Form 5": [
        {"name": "Introduction to Business Administration", "order": 1, "subtopics": [
            "Meaning and scope of business administration",
            "The functions of management",
            "The role of the manager",
            "Business organisations and their forms",
        ]},
        {"name": "Management Functions", "order": 2, "subtopics": [
            "Planning",
            "Organising",
            "Leading",
            "Controlling",
            "Coordination",
        ]},
        {"name": "Organisational Structures", "order": 3, "subtopics": [
            "Types of organisational structures",
            "Span of control and chain of command",
            "Centralisation and decentralisation",
            "Organisational charts",
        ]},
        {"name": "Business Environment", "order": 4, "subtopics": [
            "The internal environment",
            "The external environment",
            "PESTEL analysis",
            "SWOT analysis",
        ]},
        {"name": "Marketing Management", "order": 5, "subtopics": [
            "The marketing concept",
            "The marketing mix (4Ps)",
            "Market segmentation and targeting",
            "Consumer behaviour",
            "Marketing research",
        ]},
        {"name": "Human Resource Management", "order": 6, "subtopics": [
            "Human resource planning",
            "Recruitment and selection",
            "Training and development",
            "Performance appraisal",
            "Motivation and rewards",
        ]},
    ],
    "Form 6": [
        {"name": "Financial Management", "order": 1, "subtopics": [
            "The objectives of financial management",
            "Financial planning",
            "Sources of finance",
            "Working capital management",
            "Investment appraisal",
        ]},
        {"name": "Operations Management", "order": 2, "subtopics": [
            "Operations strategy",
            "Production planning and control",
            "Quality management",
            "Inventory management",
            "Supply chain management",
        ]},
        {"name": "Strategic Management", "order": 3, "subtopics": [
            "Strategy formulation",
            "Strategy implementation",
            "Strategy evaluation and control",
            "Competitive strategy",
            "Corporate strategy",
        ]},
        {"name": "Entrepreneurship", "order": 4, "subtopics": [
            "The entrepreneurial process",
            "Business opportunity identification",
            "Business planning",
            "Small business management",
            "Innovation and creativity",
        ]},
        {"name": "Business Communication", "order": 5, "subtopics": [
            "Principles of business communication",
            "Written communication",
            "Oral communication",
            "Communication technology in business",
        ]},
        {"name": "Business Law", "order": 6, "subtopics": [
            "The legal environment of business",
            "Contracts",
            "Company law (basics)",
            "Consumer protection",
            "Labour law",
        ]},
        {"name": "Revision for ACSEE", "order": 7, "subtopics": [
            "Revision of management functions",
            "Revision of functional areas",
            "Case study analysis",
            "Past paper practice",
        ]},
    ],
}


ADVANCED_AGRICULTURE = {
    "Form 5": [
        {"name": "Introduction to Agriculture", "order": 1, "subtopics": [
            "The importance of agriculture",
            "Agricultural systems",
            "Agriculture in Tanzania's economy",
            "Agricultural policies and institutions",
        ]},
        {"name": "Soil Science", "order": 2, "subtopics": [
            "Soil formation and composition",
            "Soil properties (physical and chemical)",
            "Soil fertility and nutrients",
            "Soil management and conservation",
            "Soil erosion and control",
        ]},
        {"name": "Crop Production", "order": 3, "subtopics": [
            "Land preparation",
            "Crop establishment",
            "Field crops (maize, rice, wheat, sorghum)",
            "Cash crops (coffee, cotton, tea, sisal)",
            "Crop protection and pests",
        ]},
        {"name": "Horticulture", "order": 4, "subtopics": [
            "Vegetable production",
            "Fruit production",
            "Flower production",
            "Nursery management",
            "Post-harvest handling of horticultural crops",
        ]},
        {"name": "Plant Protection", "order": 5, "subtopics": [
            "Plant pests and diseases",
            "Weeds and their control",
            "Integrated pest management",
            "Safe use of agrochemicals",
        ]},
        {"name": "Agricultural Economics", "order": 6, "subtopics": [
            "Basic economic concepts in agriculture",
            "Farm records and accounts",
            "Costs and returns in agriculture",
            "Agricultural marketing",
        ]},
    ],
    "Form 6": [
        {"name": "Animal Production", "order": 1, "subtopics": [
            "Livestock breeds and selection",
            "Animal nutrition and feeding",
            "Animal breeding and reproduction",
            "Livestock management (cattle, goats, sheep, poultry)",
        ]},
        {"name": "Animal Health", "order": 2, "subtopics": [
            "Common livestock diseases",
            "Disease prevention and control",
            "Vaccination programmes",
            "Parasites of livestock",
            "Animal first aid",
        ]},
        {"name": "Agricultural Mechanisation", "order": 3, "subtopics": [
            "Farm power and machinery",
            "Tractors and implements",
            "Irrigation systems",
            "Farm structures and buildings",
        ]},
        {"name": "Farm Management", "order": 4, "subtopics": [
            "Farm planning and budgeting",
            "Farm records and bookkeeping",
            "Resource management",
            "Decision making in farm management",
        ]},
        {"name": "Agricultural Marketing", "order": 5, "subtopics": [
            "Marketing functions and channels",
            "Price determination in agriculture",
            "Marketing boards and cooperatives",
            "Export marketing",
        ]},
        {"name": "Agribusiness", "order": 6, "subtopics": [
            "Agribusiness concepts",
            "Agricultural entrepreneurship",
            "Value addition and agro-processing",
            "Agribusiness enterprises",
        ]},
        {"name": "Agricultural Research and Revision", "order": 7, "subtopics": [
            "Research methods in agriculture",
            "Experimental design (basics)",
            "Data collection and analysis",
            "Revision for ACSEE",
        ]},
    ],
}


# =============================================================================
# CONSOLIDATED DICTS
# =============================================================================

PRIMARY_NEW_SYLLABUS = {
    "Hesabu": {"code": None, "topics_by_class": PRIMARY_HESABU},
    "Kusoma": {"code": None, "topics_by_class": PRIMARY_KUSOMA},
    "Kuandika": {"code": None, "topics_by_class": PRIMARY_KUANDIKA},
    "Sayansi": {"code": None, "topics_by_class": PRIMARY_SAYANSI},
    "Maarifa ya Jamii": {"code": None, "topics_by_class": PRIMARY_MAARIFA},
    "Stadi za Kazi": {"code": None, "topics_by_class": PRIMARY_STADI},
    "Elimu ya Dini": {"code": None, "topics_by_class": PRIMARY_DINI},
    "Uchoraji": {"code": None, "topics_by_class": PRIMARY_UCHORAJI},
    "Muziki": {"code": None, "topics_by_class": PRIMARY_MUZIKI},
    "Michezo": {"code": None, "topics_by_class": PRIMARY_MICHEZO},
}

SECONDARY_EXTRA_SYLLABUS = {
    "Bible Knowledge": {"code": None, "topics_by_class": SECONDARY_BIBLE},
    "Islamic Knowledge": {"code": None, "topics_by_class": SECONDARY_ISLAMIC},
    "French": {"code": None, "topics_by_class": SECONDARY_FRENCH},
    "Arabic": {"code": None, "topics_by_class": SECONDARY_ARABIC},
}

ADVANCED_SYLLABUS = {
    "Advance Mathematics": {"code": None, "topics_by_class": ADVANCED_MATHEMATICS},
    "Physics": {"code": None, "topics_by_class": ADVANCED_PHYSICS},
    "Chemistry": {"code": None, "topics_by_class": ADVANCED_CHEMISTRY},
    "Biology": {"code": None, "topics_by_class": ADVANCED_BIOLOGY},
    "English Language": {"code": None, "topics_by_class": ADVANCED_ENGLISH},
    "Kiswahili": {"code": None, "topics_by_class": ADVANCED_KISWAHILI},
    "Academic Communication": {"code": None, "topics_by_class": ADVANCED_COMMUNICATION},
    "Literature in English": {"code": None, "topics_by_class": ADVANCED_LITERATURE},
    "Fasihi ya Kiswahili": {"code": None, "topics_by_class": ADVANCED_FASIHI},
    "Economics": {"code": None, "topics_by_class": ADVANCED_ECONOMICS},
    "Geography": {"code": None, "topics_by_class": ADVANCED_GEOGRAPHY},
    "History": {"code": None, "topics_by_class": ADVANCED_HISTORY},
    "Accountancy": {"code": None, "topics_by_class": ADVANCED_ACCOUNTANCY},
    "Computer Science": {"code": None, "topics_by_class": ADVANCED_COMPUTER},
    "BAM": {"code": None, "topics_by_class": ADVANCED_BAM},
    "Agriculture": {"code": None, "topics_by_class": ADVANCED_AGRICULTURE},
}


def _technical_topics_by_class():
    """VETA/technical topics — same topic list for every VETA class (kama ilivyo
    kwenye migration 0009_technical_syllabus_topics). Chanzo kimoja cha data ili
    seed command na migration 0015 zifanane na 0009."""
    _mig = _importlib.import_module('curriculum.migrations.0009_technical_syllabus_topics')
    result = {}
    for subject_name, subject_data in _mig.TECHNICAL_SYLLABUS.items():
        result[subject_name] = {
            'code': subject_data.get('code'),
            'topics_by_class': {
                cls: [
                    {
                        'name': t['name'],
                        'order': i + 1,
                        'subtopics': list(t.get('subtopics', [])),
                    }
                    for i, t in enumerate(subject_data['topics'])
                ]
                for cls in TECHNICAL_CLASSES
            },
        }
    return result


TECHNICAL_SYLLABUS = _technical_topics_by_class()


def get_full_syllabus():
    """Return combined dict for the seed command + data migration."""
    data = {}
    for name, d in PRIMARY_NEW_SYLLABUS.items():
        data[name] = {**d, "level": "primary"}
    for name, d in SECONDARY_EXTRA_SYLLABUS.items():
        data[name] = {**d, "level": "secondary"}
    for name, d in ADVANCED_SYLLABUS.items():
        data[name] = {**d, "level": "advanced"}
    for name, d in TECHNICAL_SYLLABUS.items():
        data[name] = {**d, "level": "technical"}
    return data
