"""
MAKTABA IMPORTER
================
Inachota notes na mitihani kutoka sites za elimu za Tanzania
(Wazaelimu, Lusa Elimu, Mitihani.co.tz, Elimu Zone, Teacher.ac,
Shule Direct) kiotomatiki:

  1. Inasoma kurasa za listing/category (zilizowekwa kwenye MaterialSource).
  2. Inafuata links za articles za site hiyo (kikomo cha max_articles_per_run;
     url_filter (regex) inaweza kupunguza articles — mf. Teacher.ac
     'notes-tanzania' ili kuepuka kurasa za Uganda/Kenya).
  3. Kila article ina links za PDF ama moja kwa moja ama kwa Google Drive ama
     zilizofichwa kwenye PDF-viewer (viewer.html?file=...) — inazipata na
     kupakua (Drive: uc?export=download&id=...).
  4. PDF inahifadhiwa local; maudhui ya ukurasa wa kwanza yanachimbwa
     (pypdfium2) kwa ajili ya uainishaji (classification).
  5. Uainishaji: sheria (Form/Kidato/Std + majina ya masomo EN/SW) kwanza,
      AI kama kumbufu — pamoja na muhtasari (summary) wa Kiswahili.
  6. Dedupe: original_url unique + content_hash.
  7. Junk (tangazo, fomu za maombi, ajira, maudhui ya Uganda/Kenya) inatupwa.

Attribution: kila ScrapedMaterial inahifadhi original_url na jina la chanzo —
maktaba inaonyesha "Chanzo: ..." na link ya asili.
"""
import hashlib
import io
import logging
import re
from datetime import timedelta
from urllib.parse import urljoin, urlparse

import requests
from lxml import html as LH
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

EAT = ZoneInfo('Africa/Dar_es_Salaam')

UA = {
    'User-Agent': ('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/124 Safari/537.36'),
    'Accept-Language': 'en,sw;q=0.8',
}

MAX_FILE_BYTES = 30 * 1024 * 1024   # 30 MB
PDF_TEXT_CHARS = 2500               # kwa classification/summary
FETCH_TIMEOUT = 25

DRIVE_PATTERNS = [
    re.compile(r'drive\.google\.com/file/d/([A-Za-z0-9_-]{20,})', re.I),
    re.compile(r'drive\.google\.com/(?:open|uc)\?(?:[^#]*&)?id=([A-Za-z0-9_-]{20,})', re.I),
]

# ---------------- HAKIKISHO LA HTTP ----------------

def _get(url, stream=False):
    return requests.get(url, headers=UA, timeout=FETCH_TIMEOUT, stream=stream)


# ---------------- PATA LINKS ----------------

def _norm_url(u):
    return (u or '').split('#')[0].strip()


def drive_file_id(url):
    for pat in DRIVE_PATTERNS:
        m = pat.search(url or '')
        if m:
            return m.group(1)
    return None


def unwrap_pdf_viewer(url):
    """PDF-viewer links (mf. bsk-pdf-manager-pro): viewer.html?file=<encoded pdf>.

    Inarudisha PDF halisi (decoded) — mf. kurasa za Teacher.ac zinazuia PDF
    ndani ya viewer; tunifungue ili tupakue faili yenyewe.
    """
    if not url or 'viewer.html?file=' not in url:
        return url
    from urllib.parse import unquote
    enc = url.split('viewer.html?file=', 1)[1].split('&', 1)[0]
    try:
        dec = unquote(enc)
    except Exception:  # noqa: BLE001
        return url
    return dec if dec.lower().split('?')[0].endswith('.pdf') else url


def _is_article(url, base_host):
    """Link ya kurasa za site hiyo yenyewe (si category/tag/author/nje)."""
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if not p.scheme.startswith('http') or p.netloc != base_host:
        return False
    path = (p.path or '/').strip('/')
    if not path:
        return False
    bad = ('category', 'tag', 'author', 'page', 'wp-content', 'wp-login',
           'wp-admin', 'login', 'register', 'feed', 'comment', 'cdn', 'assets',
           'search',  # blogspot /search/label/... — snippets, si articles
           '.png', '.jpg', '.jpeg', '.gif', '.css', '.js', '.webp', '.svg', '.ico')
    if any(b in path.lower() for b in bad):
        return False
    return True


def extract_candidates(listing_urls, base_host):
    """Rudisha (articles, files) kutoka kurasa za listing.

    files = [(url, title)] — PDF ya moja kwa moja au Drive link.
    """
    articles, files = [], []
    seen_files, seen_arts = set(), set()

    for lu in listing_urls:
        try:
            r = _get(lu)
            tree = LH.fromstring(r.content)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[maktaba] listing %s imefail: %s", lu, exc)
            continue

        # (a) direct PDF links na Drive links zenye maandishi ya anchor
        for a in tree.xpath('//a[@href]'):
            href = _norm_url(a.get('href'))
            if not href:
                continue
            absu = unwrap_pdf_viewer(urljoin(lu, href))
            is_pdf = absu.lower().split('?')[0].endswith('.pdf')
            is_drive = drive_file_id(absu) is not None
            if not (is_pdf or is_drive):
                continue
            if absu in seen_files:
                continue
            title = ' '.join(t for t in a.itertext() if t.strip()).strip()
            seen_files.add(absu)
            files.append((absu, title))

        # (b) article links za host hiyo
        for href in tree.xpath('//a[@href]/@href'):
            href = _norm_url(href)
            if not href:
                continue
            absu = urljoin(lu, href)
            if not _is_article(absu, base_host) or absu in seen_arts:
                continue
            seen_arts.add(absu)
            articles.append(absu)

    return articles, files


RAW_DRIVE_RE = re.compile(r'drive\.google\.com/file/d/([A-Za-z0-9_-]{20,})')


def extract_from_article(url):
    """Rudisha (files, title) kutoka article moja."""
    files, title = [], ''
    try:
        r = _get(url)
        tree = LH.fromstring(r.content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[maktaba] article %s imefail: %s", url, exc)
        return [], ''

    # jina la article: og:title > h1 > <title>
    og = tree.xpath('//meta[@property="og:title"]/@content')
    h1 = tree.xpath('//h1//text()')
    ttag = tree.xpath('//title//text()')
    title = (og[0] if og else '') or ' '.join(h1).strip() or (ttag[0] if ttag else '')

    seen = set()
    for a in tree.xpath('//a[@href]'):
        href = _norm_url(a.get('href'))
        if not href:
            continue
        absu = unwrap_pdf_viewer(urljoin(url, href))
        is_pdf = absu.lower().split('?')[0].endswith('.pdf')
        is_drive = drive_file_id(absu) is not None
        if not (is_pdf or is_drive) or absu in seen:
            continue
        seen.add(absu)
        anchor_text = ' '.join(t for t in a.itertext() if t.strip()).strip()
        files.append((absu, anchor_text))

    # Drive files zilizofichwa (escaped iframes, data-attribs, JS) — mfano
    # blogspot: &lt;iframe src="drive.google.com/file/d/.../preview"&gt;
    # tunachota IDs kutoka raw HTML; label ni jina la article.
    anchor_ids = {drive_file_id(u) for u, _ in files}
    for fid in set(RAW_DRIVE_RE.findall(r.text)) - anchor_ids:
        files.append((f'https://drive.google.com/file/d/{fid}/view', title.strip()))
    return files, title.strip()


# ---------------- DOWNLOAD ----------------

def download_file(url):
    """Rudisha (bytes, final_url) ya PDF — Drive ama direct.

    Inarudisha (None, reason) kama haikuweza.
    """
    fid = drive_file_id(url)
    if fid:
        dl = f'https://drive.google.com/uc?export=download&id={fid}'
    elif url.lower().split('?')[0].endswith('.pdf'):
        dl = url
    else:
        return None, 'sio PDF wala Drive'

    try:
        r = _get(dl, stream=True)
        if r.status_code != 200:
            return None, f'HTTP {r.status_code}'
        ctype = (r.headers.get('Content-Type') or '').lower()
        first = next(r.iter_content(8192), b'')

        # Drive: files kubwa / non-PDF zina HTML confirm page
        if first[:4] != b'%PDF':
            # jaribu confirm-token ya Drive
            m = re.search(rb'name="confirm" value="([^"]+)"', first)
            uuid = re.search(rb'name="uuid" value="([^"]+)"', first)
            if fid and m:
                params = {'export': 'download', 'id': fid, 'confirm': m.group(1).decode()}
                if uuid:
                    params['uuid'] = uuid.group(1).decode()
                r2 = requests.get('https://drive.google.com/uc', params=params,
                                  headers=UA, timeout=FETCH_TIMEOUT, stream=True)
                if r2.status_code == 200:
                    r = r2
                    first = next(r2.iter_content(8192), b'')
        if first[:4] != b'%PDF':
            return None, f'sio PDF ({ctype})'

        size = int(r.headers.get('Content-Length') or 0)
        if size and size > MAX_FILE_BYTES:
            return None, f'kubwa mno ({size})'

        data = first
        for chunk in r.iter_content(64 * 1024):
            data += chunk
            if len(data) > MAX_FILE_BYTES:
                return None, 'kubwa mno (stream)'
        return data, dl
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)[:100]


def pdf_first_pages_text(data, max_pages=3):
    """Chimba maandishi ya kurasa za kwanza (kwa classification/summary)."""
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(io.BytesIO(data))
        try:
            n = len(pdf)
            chunks = []
            for i in range(min(max_pages, n)):
                page = pdf[i]
                tp = page.get_textpage()
                chunks.append(tp.get_text_range() or '')
        finally:
            pdf.close()
        text = re.sub(r'\s+', ' ', ' '.join(chunks)).strip()
        return text[:PDF_TEXT_CHARS], n
    except Exception as exc:  # noqa: BLE001
        logger.warning("[maktaba] pdf text extract fail: %s", exc)
        return '', 0


# ---------------- UAINISHAJI (CLASSIFICATION) ----------------

SUBJECT_MAP = {
    # kiswahili -> jina la Subject (ili match iwe rahisi)
    'kiswahili': 'Kiswahili', 'english': 'English', 'biology': 'Biology',
    'chemistry': 'Chemistry', 'physics': 'Physics', 'mathematics': 'Mathematics',
    'hisabati': 'Hisabati', 'basic mathematics': 'Basic Mathematics',
    'geography': 'Geography', 'jiografia': 'Geography', 'history': 'History',
    'historia': 'History', 'civics': 'Civics', 'uraia': 'Civics',
    'science': 'Science', 'sayansi': 'Science', 'sayansi na teknolojia': 'Science',
    'maarifa ya jamii': 'Maarifa ya Jamii', 'english language': 'English',
    'literature': 'Literature', 'fasihi': 'Literature',
    'book keeping': 'Book Keeping', 'bookkeeping': 'Book Keeping',
    'commerce': 'Commerce', 'business studies': 'Business Studies',
    'agriculture': 'Agricultulture', 'kilimo': 'Agriculture',
    'computer': 'Computer Studies', 'computer studies': 'Computer Studies',
    'ict': 'Computer Studies', ' elimu ya dini': 'Elimu ya Dini',
    'edk': 'Elimu ya Dini ya Kiislamu', 'islamic knowledge': 'Elimu ya Dini ya Kiislamu',
    'bible knowledge': 'Bible Knowledge', 'french': 'French', 'arabic': 'Arabic',
    'home economics': 'Home Economics', 'elimu ya nyumbani': 'Home Economics',
}

CLASS_PATTERNS = [
    (re.compile(r'\bform\s*(?:one|two|three|four|five|six|i{1,3}|iv|v|vi|1|2|3|4|5|6)\b', re.I), 'form'),
    # F2 / F4 — mitindo ya TETEA (mf. Biology-F2-2021.pdf)
    (re.compile(r'\bf\s*([1-6])\b', re.I), 'form'),
    (re.compile(r'\bkidato\s*cha\s*(kwanza|pili|tatu|nne|tano|sita|1|2|3|4|5|6)\b', re.I), 'kidato'),
    (re.compile(r'\b(?:std|standard|darasa(?:\s*la)?)\s*(1|2|3|4|5|6|7|moja|mbili|tatu|nne|tano|sita|saba)\b', re.I), 'std'),
    # S1 / S5 — mitindo ya TETEA primary (mf. ArithmeticSkills-S1-2024.pdf)
    (re.compile(r'\bs\s*([1-7])\b', re.I), 'std'),
]

WORD_NUM = {
    'one': 1, 'moja': 1, 'two': 2, 'mbili': 2, 'three': 3, 'tatu': 3,
    'four': 4, 'nne': 4, 'five': 5, 'tano': 5, 'six': 6, 'sita': 6,
    'seven': 7, 'saba': 7, 'i': 1, 'ii': 2, 'iii': 3, 'iv': 4, 'v': 5, 'vi': 6,
}


def _class_from_match(txt, kind):
    m = None
    for pat in CLASS_PATTERNS:
        mm = pat[0].search(txt)
        if mm:
            m = mm
            kind = pat[1]
            break
    if not m:
        return '', ''
    raw = m.group(0).lower()
    # ute namba
    num = None
    for w in re.findall(r'[a-z]+|\d+', raw):
        if w.isdigit():
            num = int(w)
        elif w in WORD_NUM:
            num = WORD_NUM[w]
    if num is None:
        return '', ''
    if kind == 'form':
        level = 'advanced' if num >= 5 else 'ordinary'
        return f'Form {num}', level
    if kind == 'kidato':
        level = 'advanced' if num >= 5 else 'ordinary'
        return f'Form {num}', level
    return f'Standard {num}', 'primary'


JUNK_RE = re.compile(
    r'(tangazo|matangazo|announcement|advertisement|fomu ya maombi|'
    r'fomu ya usajili|application form|ajira|vacanc|sensa|newsletter|'
    r'joining instruction)'
)

# maudhui ya nchi jirani/nje — checked kwenye TITLE tu (si body, ili notes
# za TZ zinazotaja "Kenya" katika maandishi zisitupwe kimakosa)
JUNK_TITLE_RE = re.compile(
    r'(uganda|kenya|\bkcse\b|\bkcpe\b|\bp\.\s?[1-7]\b|\bpp[12]\b)'
)


def is_junk(title, text=''):
    """True kama faili si material ya elimu (tangazo, fomu ya maombi, ajira, n.k.)."""
    t = (title or '').lower()
    if JUNK_TITLE_RE.search(t):
        return True
    hay = f'{title} {text[:600]}'.lower()
    return bool(JUNK_RE.search(hay))


def classify_by_rules(title, text):
    """Rudisha dict {material_type, education_level, class_name, subject_name} kwa sheria."""
    hay = f'{title} {text[:600]}'.lower()

    # aina — study aids/teacher guides (mf. Shika na Mikono) ni VITABU hata
    # kama zinamtaja NECTA kwenye jina/maudhui
    if re.search(r'\b(syllabus|mtaala|curriculum)\b', hay):
        mtype = 'syllabus'
    elif re.search(r'(shika\s*na\s*mikono|study\s*aid|teacher.?s?\s*guide|teachers?\s*guide)', hay):
        mtype = 'book'
    elif re.search(r'\b(exam|mtihani|examination|mock|pre.?necta|necta|terminal|midterm|test paper|paper\s*[1-3]|marking|solutions?|csee|ftna|acsee|psle|sfna|qt|gatce|dsee|dtee)\b', hay):
        mtype = 'exam'
    elif re.search(r'\b(tie\s*book|kitabu|textbook|book(?![- ]?keeping)|shika\s*na\s*mikono|teacher.?s?\s*guide|teachers?\s*guide)\b', hay):
        mtype = 'book'
    else:
        # hakuna ishara ya aina — acha tupu ili default ya CHANZO itumike
        # (mf. TETEA ni past papers: default_type='exam')
        mtype = ''

    # darasa + level
    class_name, level = _class_from_match(hay, 'form')

    # somo
    subject = ''
    hay_title = title.lower()
    for key, name in SUBJECT_MAP.items():
        if key.strip() in hay_title:
            subject = name
            break
    if not subject:
        # tafuta kwenye maandishi (mano ya kwanza tu — generic text)
        for key, name in SUBJECT_MAP.items():
            if key.strip() in hay:
                subject = name
                break

    return {
        'material_type': mtype,
        'education_level': level or ('primary' if 'standard' in hay or 'darasa' in hay else ''),
        'class_name': class_name,
        'subject_name': subject,
    }


def ai_classify_and_summarise(title, text, hints):
    """AI: thibitisha/jaza classification + andika muhtasari wa Kiswahili.

    Inatumia curriculum.ai_utils (fallback kamili: OpenRouter → Groq → Gemini
    direct HTTP) ili isifeil kama provider mmoja akawa na shida.
    """
    try:
        from curriculum.ai_utils import client as ai_client, model_name
    except ImportError:
        from .ai_utils import client as ai_client, model_name
    if ai_client is None or not text:
        return None
    try:
        import json as _json
        prompt = f"""You are a Tanzanian education librarian. Given a PDF's title and first-page text, return ONLY valid JSON with these keys:
- "material_type": one of "notes", "exam", "book", "syllabus", "other"
- "education_level": one of "primary", "ordinary", "advanced", "technical" ("" if unknown)
- "class_name": e.g. "Form 2", "Standard 5" ("" if unknown)
- "subject_name": official subject name in English or Kiswahili ("" if unknown)
- "summary": muhtasari mfupi wa Kiswahili (sentensi 2-3) anayelezea mwalimu/wanafunzi anachopata

Title: {title}
First-page text: {text[:1800]}
Rule-based guesses (may be wrong): {_json.dumps(hints)}
"""
        resp = ai_client.models.generate_content(model=model_name, contents=prompt)
        raw = resp.text
        raw = re.sub(r'```json\s*|\`\`\`', '', raw).strip()
        s, e = raw.find('{'), raw.rfind('}')
        if s == -1 or e <= s:
            return None
        data = _json.loads(raw[s:e + 1])
        if not isinstance(data, dict):
            return None
        return {
            'material_type': data.get('material_type') or hints.get('material_type') or '',
            'education_level': data.get('education_level') or hints.get('education_level') or '',
            'class_name': data.get('class_name') or hints.get('class_name') or '',
            'subject_name': data.get('subject_name') or hints.get('subject_name') or '',
            'summary': (data.get('summary') or '')[:1200],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("[maktaba] AI classify fail: %s", exc)
        return None


def match_subject(name):
    """Linganisha jina la somo na Subject model."""
    if not name:
        return None, name
    from .models import Subject
    n = name.strip().lower()
    subj = (Subject.objects.filter(name__iexact=name).first()
            or Subject.objects.filter(name__iexact=n).first())
    if subj:
        return subj, subj.name
    # contains match
    subj = Subject.objects.filter(name__icontains=name).first()
    if subj:
        return subj, subj.name
    return None, name


# ---------------- IMPORT MOJA ----------------

GENERIC_TITLES = {
    'download', 'download pdf', 'download here', 'click here', 'here',
    'pdf', 'view', 'open', 'read', 'link', 'download now',
}

# anchors zisizo na maana pekee ('(Solutions)', '2024', '(Answers)')
WEAK_ANCHORS = {'solutions', 'answers', 'answer', 'marking scheme', 'results',
                'result', 'paper', 'pdf', 'notes', 'notes pdf', 'download pdf'}


def _is_weak_title(title):
    """Anchor haile jina halisi (mwaka tu, mabano tu, neno la generic).

    Mfano TETEA: anchor '2024' au '(Solutions)' kwenye faili
    'ArithmeticSkills-S1-2024-Solutions.pdf' — jina la URL ni bora.
    """
    t = (title or '').strip()
    if not t or t.lower() in GENERIC_TITLES:
        return True
    core = t.strip('()[]{}').strip()
    if core.lower() in WEAK_ANCHORS or core.lower() in GENERIC_TITLES:
        return True
    # hakuna herufi 4 za pamoja (mf. '2024', 'F2', '(2020)') — ni mwaka/tufe
    letters = re.sub(r'[^A-Za-z]', '', core)
    return len(letters) < 4


def _title_from_url(url):
    """Jina la faili kutoka URL (mf. Biology2-F6-2025.pdf → 'Biology2 F6 2025')."""
    base = urlparse(url).path.rstrip('/').split('/')[-1]
    base = base.rsplit('.', 1)[0]
    base = re.sub(r'[-_]+', ' ', base).strip()
    return base if len(base) >= 4 else ''


def import_one(source, url, fallback_title):
    """Chota, pakua, ainisha, hifadhi ScrapedMaterial moja. Rudisha status."""
    from django.core.files.base import ContentFile
    from .models import ScrapedMaterial

    if ScrapedMaterial.objects.filter(original_url=url).exists():
        return 'exists'

    # junk check ya kwanza kwa jina — okoa bandwidth (hakuna download)
    if is_junk(fallback_title or ''):
        return 'skip: tangazo/fomu (jina)'

    data, err = download_file(url)
    if data is None:
        return f'skip: {err}'
    if len(data) < 2048:
        return 'skip: faili ndogo mno'

    text, pages = pdf_first_pages_text(data)
    title = (fallback_title or '').strip()
    if _is_weak_title(title):
        # anchor haile jina halisi — tumia jina la faili kutoka URL
        title = _title_from_url(url) or title
    if not title or len(title) < 6:
        title = f'Material — {url}'
    title = re.sub(r'\s+', ' ', title)[:300]

    if is_junk(title, text):
        return 'skip: tangazo/fomu'

    hints = classify_by_rules(title, text)
    ai = ai_classify_and_summarise(title, text, hints)
    used = ai or hints
    used_by = 'ai' if ai else 'rules'

    subject, subject_name = match_subject(used.get('subject_name') or '')

    chash = hashlib.sha256(data).hexdigest()
    if ScrapedMaterial.objects.filter(content_hash=chash).exclude(content_hash='').exists():
        return 'skip: nakala (hash)'

    fname = re.sub(r'[^A-Za-z0-9._ -]', '', title)[:80] or 'material'
    if not fname.lower().endswith('.pdf'):
        fname += '.pdf'

    mat = ScrapedMaterial(
        source=source,
        title=title,
        original_url=url,
        file_size=len(data),
        content_hash=chash,
        pages=pages,
        material_type=used.get('material_type') or source.default_type or 'notes',
        education_level=used.get('education_level') or '',
        class_name=used.get('class_name') or '',
        subject=subject,
        subject_name=subject_name or '',
        ai_summary=(ai or {}).get('summary', ''),
        classified_by=used_by,
    )
    mat.file.save(fname, ContentFile(data), save=False)
    mat.save()
    return 'ok'


# ---------------- IMPORT CHANZO / VYOTE ----------------

def import_source(source, max_new=20, today=None):
    """Run moja ya chanzo kimoja. Rudisha muhtasari."""
    from django.utils import timezone as dj_tz
    from .models import ScrapedMaterial

    host = urlparse(source.site_url).netloc
    listing = source.listing_urls or [source.site_url]
    articles, files = extract_candidates(listing, host)

    # url_filter (regex) — mf. Teacher.ac: 'notes-tanzania' ili kuepuka
    # kurasa za Uganda/Kenya zilizo mbele kwenye listing ileile
    url_pat = None
    uf = (getattr(source, 'url_filter', '') or '').strip()
    if uf:
        try:
            url_pat = re.compile(uf)
        except re.error:
            logger.warning("[maktaba] url_filter mbaya (%r) — inapuuzwa", uf)
    if url_pat:
        articles = [a for a in articles if url_pat.search(a)]
        files = [(u, t) for (u, t) in files if url_pat.search(u)]

    # article mpya kwanza (mpya zaidi zina mafaili mapya).
    # NOTE: articles hazihifadhiwi zenyewe — huchotwa files zake tu;
    # hakuna haja ya ku-check DB kila article (TETEA ina 1000+ articles —
    # ilikuwa inafanya queries 1117 zisizo na maana kila run).
    articles = articles[:source.max_articles_per_run or 15]

    candidates = list(files)
    for art in articles:
        try:
            f, title = extract_from_article(art)
        except Exception:  # noqa: BLE001
            continue
        for u, anchor in f:
            label = anchor if len(anchor) > 6 else (title or anchor)
            candidates.append((u, label))

    # dedupe kwa URL na Drive id (URL mbili zinaweza kuwa file moja)
    seen, uniq = set(), []
    for u, t in candidates:
        fid = drive_file_id(u)
        key = f'drive:{fid}' if fid else u
        if key in seen:
            continue
        seen.add(key)
        uniq.append((u, t))

    created = skipped = errors = 0
    for u, t in uniq:
        if created >= max_new:
            break
        # Downloads ndefu (PDF kubwa) zinaacha connection ya DB bila shughuli —
        # Postgres ya production inaifunga (SSL EOF). Funga connections zamani
        # kabla ya kila candidate ili DB iwe fresh. (Salama: hakuna transaction
        # ya nje hapa — kila import_one ina autocommit yake.)
        from django.db import close_old_connections
        close_old_connections()
        try:
            res = import_one(source, u, t)
            if res == 'ok':
                created += 1
            elif res == 'exists':
                pass
            elif res.startswith('skip'):
                skipped += 1
            else:
                errors += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("[maktaba] import_one %s", u)
            errors += 1

    source.last_scraped_at = dj_tz.localtime(dj_tz.now(), EAT)
    source.save(update_fields=['last_scraped_at'])
    return {
        'source': source.name,
        'found': len(uniq),
        'created': created,
        'skipped': skipped,
        'errors': errors,
    }


def import_all_sources(max_new_per_source=40):
    """Kwa scheduler: endesha vyanzo vyote vilivyo ON."""
    from .models import MaterialSource
    results, errors = [], []
    for src in MaterialSource.objects.filter(enabled=True):
        try:
            results.append(import_source(src, max_new=max_new_per_source))
        except Exception as exc:  # noqa: BLE001
            logger.exception("[maktaba] source %s fail", src.name)
            errors.append(f"{src.name}: {exc}")
    return {'runs': results, 'errors': errors}
