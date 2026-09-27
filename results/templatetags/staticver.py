"""{% staticver 'results/styles.css' %} — {% static %} yenye '?v=' inayotokana
na mwenyewe wa faili.

Lazima tu, kwa sababu hii ndiyo njia pekee ya kuvusha cache ya kivinjari
kwa CSS/JS:

  * WhiteNoise anasema kila kitu chini ya /static/ ni
    `Cache-Control: public, max-age=31536000, immutable` — yaani browser
    hafungani kuuliza tena kwa mwaka mzima. Hii ni sahihi kwenye majina
    YALIYO-HASHED (mfano styles.8e32a3463d99.css: hash hubadilika paka
    content inapobadilika), lakini si kwenye jina la kawaida.
  * Django hutoa hash pale staticfiles.json haipo au haikusomi
    (mfano: collectstatic haukuendeshwa kwenye image, au hiyo haisomeki
    kwa ruhusa). Kisha {% static %} inarudi jina la kawaida
    (`/static/results/styles.css`) bila kuwa na hash — na hiyo ndiyo
    URL ambayo WhiteNoise inaweka immutable.

Matokeo: ukurasa uliopo hubaki pale pale. Mtu aliyefungua paneli ya AI
mwla asubuhi (kabla `.me-ai-*` zilipoandikwa kwenye styles.css) hata
angetazama paneli ya zamani baada ya kila deploy — mpaka atafute cache
kwa mkono au afungue browser mpya. Hii ndiyo ilikuwa inatokea kwenye
"Pakia Scoresheets" ya academic: ukurasa ulikuwa na moduli ya paneli
na markup zake, lakini mtumiaji alikuwa bado anaona stylesheet ya
kabisa ya kati ya miaka mitatu iliyokuwa haijui kama paneli inaipo.

Hapa tunongeza muda wa mwisho wa faili (mtime) kama `?v=`, hivyo URL
hubadilika KILA mtu mabadiliko mpya unapopelekwa — bila kutaratibu
'?v=...' kwa mkono kwenye kila ukurasa, na bila kugusa WhiteNoise au
njia ya kuingiza static (riski ya kuvunja vituvinginevinge).

Kama Django tayali amepata hash (staticfiles.json ipo), URL ina hash
tayari na '?v=' hapa ni ya ziada tu — lakini salama, kwa sababu hash
na mtime zinasogeera pamoja.

Mahali pa kumbuka: process hii inafanya kazi kwa muda wa mzigo mmoja.
Kila deploy hurejesha container, hivyo kumbukumbu ya hapa chini
inasafika na yenyewe — hakuna hatari ya kutumia tarehe ya zamani.
"""

import os

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()

# {path: (mtime, url)} — msimamo wa process moja (deploy hurejesha
# container, hivyo mtime hazibadilikiwi hata kati ya watu wote wa
# mzigo mmoja).
_MEMO = {}


@register.simple_tag
def staticver(path):
    """{% staticver 'results/styles.css' %} -> /static/.../styles.css?v=64ab12cd"""
    url = static(path)
    if '?' in url:
        return url

    hit = _MEMO.get(path)
    if hit is None:
        source = finders.find(path)
        try:
            stamp = int(os.path.getmtime(source))
        except (OSError, TypeError, ValueError):
            # Faili haipo kwenye diski (mfano: inatoka kwa bundle) — tusipe
            # URL isiyofanya kitu badala ya kuiangusha ukurasa wote.
            return url
        url = '%s?v=%x' % (url, stamp)
        _MEMO[path] = (stamp, url)

    return _MEMO[path][1]
