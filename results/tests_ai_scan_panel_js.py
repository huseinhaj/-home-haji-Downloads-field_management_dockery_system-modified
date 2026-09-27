"""Majaribio ya moduli ya paneli ya AI (results/static/results/js/ai_scan_panel.js).

Moduli hii ndiyo inayoripoti "jinsi inavyochakata upload" kwa mtu — bar ya
asilimia halisi, majina ya hatua, na ujumbe wa kosa. Django test runner
hauangalizi JavaScript, hivomo tunaisoma na kuizungusha kwa node ndani ya
harness ndogo unaotumia DOM ya kubuni (hakuna jsdom inayohitajika).

Kama node haipo kwenye mfumo, majaribio haya yasikiliwa (skip) — programu
bado inafanya kazi, tu hatujali JS hapa.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

PANEL_JS = Path(__file__).resolve().parent / 'static' / 'results' / 'js' / 'ai_scan_panel.js'

HARNESS = r"""
function El() {
  this._cls = {};
  this.classList = {
    add: function () { for (var i = 0; i < arguments.length; i++) this._owner._cls[arguments[i]] = true; },
    remove: function () { for (var i = 0; i < arguments.length; i++) delete this._owner._cls[arguments[i]]; },
    contains: function (c) { return !!this._owner._cls[c]; },
    toggle: function (c, v) { if (v) this._owner._cls[c] = true; else delete this._owner._cls[c]; },
    _owner: null,
  };
  this.dataset = {};
  // style inapasika kuwa kama CSSStyleDeclaration halisi: moduli inatumia
  // setProperty() kwa CSS variable (--pct) kwenye mzunguko.
  var props = {};
  this.style = {
    setProperty: function (k, v) { props[k] = v; },
    getPropertyValue: function (k) { return (k in props) ? props[k] : ''; },
  };
  this.textContent = '';
  this.innerHTML = '';
  this.children = [];
  this.scrollTop = 0;
  this.scrollHeight = 0;
  this.appendChild = function (c) { this.children.push(c); };
  this.querySelector = function () { return new El(); };
  this.querySelectorAll = function () { return []; };
}

var root = new El();
root.classList._owner = root;
var stage = new El(), sub = new El(), bar = new El(), log = new El(), clock = new El();
var parts = { stage: stage, sub: sub, bar: bar, log: log, clock: clock, orb: new El(), steps: new El(),
              ring: new El(), ringLabel: new El(), pct: new El() };
root.querySelector = function (sel) {
  var m = /data-ai="([A-Za-z]+)"/.exec(sel);
  return m ? parts[m[1]] : new El();
};
function ringPct() { return parts.ring.style.getPropertyValue('--pct'); }

global.window = {};
global.document = { getElementById: function () { return root; }, createElement: function () { return new El(); } };
global.setInterval = function () { return 1; };
global.clearInterval = function () {};

var failures = 0;
function ok(cond, label) {
  if (!cond) { failures++; console.log('FAIL: ' + label); }
}

require(__PANEL__);
var AiScanPanel = global.window.AiScanPanel;
ok(typeof AiScanPanel === 'function', 'AiScanPanel imeexportiwa');

// start(): paneli inaonekana, inabeba jengo la AI, timer inaanza
var p = new AiScanPanel({ lang: 'sw', id: 'root', float: true });
p.start();
ok(root.classList.contains('on'), 'start() inaonyesha paneli');
ok(root.classList.contains('me-ai-panel--float'), 'float:true inabanda paneli juu');
ok(root.dataset.busy === '1', 'start() inaweka busy=1');

// setUpload(): ASILIMIA HALISI — hii ndiyo "jinsi inavyochakata upload"
p.setUpload(2621440, 5242880);   // 2.5 MB / 5 MB
ok(root.dataset.upload === '1', 'setUpload() inaweka data-upload');
ok(bar.style.width === '50%', 'bar ni 50% (uliolewa: ' + bar.style.width + ')');
ok(/50%/.test(sub.textContent), 'sub inaonyesha asilimia: ' + sub.textContent);
ok(/2\.5 MB \/ 5\.0 MB/.test(sub.textContent), 'sub inaonyesha ukubwa: ' + sub.textContent);
// MZUNGUKO: --pct lazima iwa ASILIMIA HALISI ile ile ya bar (conic-gradient)
ok(ringPct() === 50, 'mzunguko ni 50% wakati wa kupakia: ' + ringPct());
ok(parts.pct.textContent === '50%', 'nambari ya mzunguko ni 50%: ' + parts.pct.textContent);
ok(parts.ringLabel.hidden === false, 'lebo ya mzunguko inaonekana kuna asilimia');
p.setUpload(5242880, 5242880);
ok(bar.style.width === '100%', 'bar ni 100% mwishoni');
// Logi haipatikani mara kwa mara: robo moja tu
ok(log.children.length === 2, 'log ina mistari 2 (25% na 50%), si kila onprogress: ' + log.children.length);

// applyMeta(): AI imeanza kusoma — bar ya kurasa, si ya byte
p.applyMeta({ stage: 'reading', pages_done: 1, pages_total: 4 });
ok(root.dataset.upload === undefined, 'applyMeta() inafutha data-upload');
ok(bar.style.width === '25%', 'bar inaonyesha kurasa 1/4: ' + bar.style.width);
ok(/1\/4/.test(sub.textContent), 'sub inaonyesha Ukurasa 1/4: ' + sub.textContent);
ok(ringPct() === 25, 'mzunguko unafuata KURASA (1/4 = 25%), si byte: ' + ringPct());
p.applyMeta({ stage: 'matching', rows: 12 });
ok(parts.steps !== null, 'hatua ya kulinganisha inafika');
ok(ringPct() === 100, 'mzunguko unaonyesha 100% baada ya kusoma (AI inakoroga): ' + ringPct());

// finish(): mwisho, hakuna byte progress tena
p.finish({ title: 'Imekamilika', sub: 'Wanafunzi 12' });
ok(root.dataset.busy === '0', 'finish() inaweka busy=0');
ok(root.dataset.upload === undefined, 'finish() inafutha data-upload');
ok(root.classList.contains('is-done'), 'finish() inaweka is-done');
ok(bar.style.width === '100%', 'finish() inafikisha bar');
ok(ringPct() === 100, 'finish() unafikisha mzunguko 100%');

// fail(): ujumbe wa kosa unaonekana, si tupu
var p2 = new AiScanPanel({ lang: 'sw', id: 'root' });
p2.start();
ok(ringPct() === 0, 'start() inauzisha mzunguko kwa 0%: ' + ringPct());
ok(parts.ringLabel.hidden === true, 'start() haionyeshi lebo ya asilimia');
p2.setUpload(100, 200);
ok(ringPct() === 50, 'mzunguko unafuata upload hata baada ya restart: ' + ringPct());
p2.fail('Gemini imekataa');
ok(root.classList.contains('is-error'), 'fail() inaweka is-error');
ok(/Gemini imekataa/.test(parts.sub.textContent), 'fail() inaonyesha sababu: ' + parts.sub.textContent);
ok(root.dataset.upload === undefined, 'fail() inafutha data-upload');
ok(parts.ringLabel.hidden === true, 'fail() inaficha lebo ya asilimia (ring inabaki pale ilipofika)');

// upload(): POST kwa XHR — kipekee halisi + kosa halisi cha seriveri
var sent = null;
var FakeXHR = function () { this.upload = {}; this.status = 0; this.responseText = ''; };
FakeXHR.prototype.open = function (m, u) { this._m = m; this._u = u; };
FakeXHR.prototype.setRequestHeader = function () {};
FakeXHR.prototype.send = function (fd) {
  sent = { method: this._m, url: this._u, fd: fd, xhr: this };
  this.upload.onprogress({ lengthComputable: true, loaded: 50, total: 100 });
};
global.XMLHttpRequest = FakeXHR;

var p3 = new AiScanPanel({ lang: 'sw', id: 'root' });
p3.start();
var settled = p3.upload('/scan', { a: 1 }, { csrf: 'tok' }).then(function (data) {
  ok(sent.method === 'POST', 'upload() inatumia POST');
  ok(sent.url === '/scan', 'upload() inaenda kwenye URL iliyoitwa');
  ok(/50%/.test(parts.sub.textContent), 'onprogress inaonyesha asilimia kwenye paneli: ' + parts.sub.textContent);
  ok(data.task_id === 'x1', 'upload() inarekodi data ya seriveri');
  // 200 lakini jibu ni kosa (mfano: Gemini imekataa ndani ya ndani)
  sent.xhr.status = 400;
  sent.xhr.responseText = JSON.stringify({ error: 'Gemini imekataa' });
  return p3.upload('/scan', {}, { csrf: 't' }).then(
    function () { ok(false, 'upload() inapaswa kukataa kwenye jibu la 400'); },
    function (e) { ok(/Gemini imekataa/.test(e.message), 'upload() inaleta kosa halisi: ' + e.message); }
  );
}, function (e) { ok(false, 'upload() ilikataa: ' + e.message); });

setTimeout(function () {
  if (failures) { process.exit(1); }
  console.log('JS HARNESS OK');
  process.exit(0);
}, 200);
"""


@unittest.skipUnless(shutil.which('node'), 'node haipo kwenye mfumo — JS harness inarekebiwa')
class AiScanPanelJsTests(unittest.TestCase):
    """Paneli ya AI lazima ionyeshe hatua halisi, si 'subiri kidogo'."""

    maxDiff = None

    def _run(self, body):
        with tempfile.TemporaryDirectory() as tmp:
            harness = Path(tmp) / 'harness.js'
            harness.write_text(HARNESS.replace('__PANEL__', json.dumps(str(PANEL_JS))))
            proc = subprocess.run(
                [shutil.which('node'), str(harness)],
                capture_output=True, text=True, timeout=60,
                cwd=str(PANEL_JS.parent),
            )
        self.assertEqual(
            proc.returncode, 0,
            f'JS harness imeshindwa (rc={proc.returncode})\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}',
        )
        return proc.stdout

    def test_panel_shows_real_progress_and_errors(self):
        out = self._run('')
        self.assertIn('JS HARNESS OK', out)

    def test_module_is_referenced_by_all_three_scan_pages(self):
        """Paneli moja inatumika kwenye madarasa matatu ya kusoma AI —
        bila hapo mojawili zinazofika kwenye moduli na paneli zinadidwa
        kwenye akasimu ya mzanzizo."""
        base = PANEL_JS.parent.parent.parent.parent  # results/
        consumers = (
            ('marks_entry.html', 'meScanPanel'),
            ('upload_form_students.html', 'rosterScanPanel'),
            ('bulk_scoresheet_upload.html', 'bulkScanPanel'),
        )
        for tpl, panel_id in consumers:
            src = (base / 'templates' / 'results' / tpl).read_text()
            self.assertIn('results/js/ai_scan_panel.js', src, f'{tpl} haipaswi moduli')
            self.assertIn('results/includes/ai_scan_panel.html', src, f'{tpl} haipaswi paneli')
            self.assertIn(panel_id, src, f'{tpl} haitumii ID {panel_id}')

    def test_academic_panel_is_at_top_of_page(self):
        """Paneli ya academic lazima iwe JUU ya ukurasa (ndani ya container
        ya kwanza) — ndani ya kadi ya vikwamba ilikuwa hatua 4 chini, hivyo
        mtu aliyobofya 'Piga Picha' hakuona chochote."""
        base = PANEL_JS.parent.parent.parent.parent
        src = (base / 'templates' / 'results' / 'upload_form_students.html').read_text()
        content_at = src.index('{% block content %}')
        include_at = src.index('results/includes/ai_scan_panel.html', content_at)
        heading_at = src.index('<h2 class="mb-1"', content_at)
        self.assertLess(include_at, heading_at,
                        'paneli ya AI lazima iwe kabla ya kichwa cha ukurasa')
        self.assertIn('float: true', src,
                      'academic paneli inapaswa kubanda juu (float: true)')

    def test_bulk_upload_panel_shows_bytes_and_pages(self):
        """Ukurasa wa 'Pakia Scoresheets — Masomo Yote': paneli ya AI
        lazima ionyeshe (a) byte halisi wa kupakia na (b) kurasa/mistari
        wa AI. Bila (b) paneli ingebaki 'Inasoma...' tu — hasa kwa sababu
        hii njia ya thread haikuandika meta kama Celery."""
        base = PANEL_JS.parent.parent.parent.parent
        src = (base / 'templates' / 'results' / 'bulk_scoresheet_upload.html').read_text()
        self.assertIn('aiPanel.upload(', src,
                      'bulk upload inapasika kutumia panel.upload (XHR) ili kuonyesha asilimia halisi')
        self.assertIn('aiPanel.applyMeta(data)', src,
                      'pollTask inapasika kumpa meta kwa paneli (kurasa/mistari)')
        self.assertIn('aiPanel.finish(', src, 'lazima kuwa na muhtasari wa mwisho')
        self.assertIn('aiPanel.fail(', src, 'kosa la AI lazima lionyeshe kwenye paneli')
        # Paneli iko kabla ya hero (mwamba wa ukurasa), na inabanda juu
        hero_at = src.index('class="bulk-hero"')
        include_at = src.index('results/includes/ai_scan_panel.html')
        self.assertLess(include_at, hero_at, 'paneli ya AI iko chini ya kichwa')
        self.assertIn("id: 'bulkScanPanel'", src)
        self.assertIn('float: true', src, 'paneli inapaswa kubanda juu ya ekran')

    def test_progress_ring_is_in_markup_and_css(self):
        """Mzunguko wa asilimia lazima uwe kwenye markup NA kwenye CSS
        (conic-gradient inayotumia --pct). Bila sehemu moja, paneli
        ingeonekana kama zamani: mtu waonaje asilimia halisi.
        Majaribio ya JS hapa juu yanathibitisha karekebisha --pct."""
        base = PANEL_JS.parent.parent.parent.parent
        markup = (base / 'templates' / 'results' / 'includes' / 'ai_scan_panel.html').read_text()
        self.assertIn('data-ai="ring"', markup, 'markup haijaweka mzunguko')
        self.assertIn('data-ai="pct"', markup, 'markup haijaweka nambari ya asilimia')
        css = (base / 'static' / 'results' / 'styles.css').read_text()
        self.assertIn('.me-ai-ring {', css, 'CSS haijaweka mzunguko')
        self.assertIn('conic-gradient', css, 'mzunguko unapaswa kuwa conic-gradient')
        self.assertIn('var(--pct', css,
                      'mzunguko unapaswa kusoma --pct ambayo JS inaiweka')

    def test_academic_roster_scans_multiple_pages_with_thumbnails(self):
        """Orodha ya academic inapaswa kutumia scanner ya kurasa nyingi
        (nzuri/vizuiri za kila ukurasa, kama Marks Entry). Bila hii, mtu
        aliyepiga orodha ya kurasa 3+ alipata picha moja tu kwa kila
        wakati — alizoekana kama hakuna scan kamwe."""
        base = PANEL_JS.parent.parent.parent.parent
        src = (base / 'templates' / 'results' / 'upload_form_students.html').read_text()
        self.assertIn('results/js/scoresheet_scanner.js', src,
                      'academic roster inapasika kupakia moduli ya scanner')
        self.assertIn('rosterMultiScanBtn', src, 'button ya kurasa nyingi haipo')
        self.assertIn('ScoresheetScanner.open(', src, 'scanner haijazulishwa kwenye orodha')
        self.assertIn('jspdf.umd.min.js', src,
                      'scanner inahitaji jsPDF kwa kufunga kurasa kuwa PDF mmoja')
        # PDF moja ya kurasa zote inapasika kuingia kwenye njia ya OCR
        # ile ile ya picha/PDF iliyochaguliwa (usiitume kwa endpoint tofauti).
        self.assertIn('scanRosterFile(pdfFile)', src,
                      'PDF ya scanner inapaswa kuingia kwenye njia ya OCR ya kawaida')


class ScanAssetCacheBustingTests(unittest.TestCase):
    """CSS/JS za kuingia lazima zibadilishwe kila mtu zinapobadilika.

    WhiteNoise anasema kila kitu chini ya /static/ ni `immutable,
    max-age=31536000` — browser hafungani kuuliza tena kwa mwaka. Hiyo
    ni salama kwenye majina YALIYO-HASHED, lakini kwenye jina la kawaida
    (`/static/results/styles.css`) URL hubaki pale pale na mtu hataona
    mabadiliko mapya. Hii ndiyo iliyokuwa ikisemwa "deployment imefanikiwa
    lakini bar ya maendeleo haionekani" kwenye ukurasa wa academic: ukurasa
    ulikuwa na markup na moduli yake, lakini kivinjari kilikuwa kikiwa na
    stylesheet ya zamani ambayo haikuwa na `.me-ai-*` hata kidogo.
    """

    maxDiff = None

    def _base(self):
        return PANEL_JS.parent.parent.parent.parent

    def test_staticver_is_used_for_the_scan_assets(self):
        base = self._base()
        consumers = ('bulk_scoresheet_upload.html', 'marks_entry.html',
                     'upload_form_students.html')
        for tpl in consumers:
            src = (base / 'templates' / 'results' / tpl).read_text()
            for asset in ('results/js/ai_scan_panel.js',
                          'results/js/scoresheet_scanner.js'):
                wanted = "{% staticver '" + asset + "' %}"
                self.assertIn(wanted, src,
                              tpl + ' lazima ipakie moduli kwa staticver, si '
                              '{% static %} (kiole hiki hakiwezi kubadilika)')
            self.assertNotIn("{% static 'results/js/ai_scan_panel.js' %}", src,
                             tpl + ' bado inapakia moduli bila cache-busting')

    def test_stylesheet_is_cache_busted(self):
        base = self._base()
        src = (base / 'templates' / 'results' / 'base.html').read_text()
        self.assertIn("{% staticver 'results/styles.css' %}", src,
                      'styles.css lazima iwekwe ?v= (staticver), bila hiyo '
                      'kivinjari kinashikilia stylesheet ya zamani kwa mwaka')
        self.assertNotIn("{% static 'results/styles.css' %}?", src,
                         '?v= iliyoandikwa kwa mkono haibadilishwi kwenye '
                         'deploy mpya — hiyo ndiyo iliyosababisha tatizo')

    def test_staticver_appends_the_files_own_mtime(self):
        from django.template import Context, Template
        out = Template("{% load staticver %}{% staticver 'results/styles.css' %}"
                       ).render(Context({}))
        self.assertIn('?v=', out)
        mtime = int(os.path.getmtime(self._base() / 'static/results/styles.css'))
        self.assertTrue(out.endswith('?v=%x' % mtime),
                        f'?v= inapaswa kuwa mtime ya faili: {out}')

    def test_staticver_survives_a_file_it_cannot_stat(self):
        """Faili isiyopatikana kwenye disku haipaswi kuiangusha ukurasa
        wote — tunarudi kwenye URL ya kawaida (hali ya zamani)."""
        from unittest import mock

        from results.templatetags import staticver as tag
        tag._MEMO.clear()          # memo ya majaribio yaliyotangulia
        with mock.patch.object(tag.finders, 'find', return_value=None):
            out = tag.staticver('results/styles.css')
        self.assertIn('/static/', out)
        self.assertNotIn('?v=', out)


class TemplateCommentTests(unittest.TestCase):
    """`{# ... #}` ya Django ni ya mstari MOJA kama.

    Ikiwa imeandikwa kwa mistari mingi, Django haisoma kama dokeo — regex
    yake haipiti mistari. Sehemu iliyobaki inakuwa maandishi ya kawaida
    kwenye HTML, kwa hiyo mtu anaona `{# Paneli ya AI — JUU kabisa...` kama
    maandishi kwenye ukurasa (kilichotokea kwenye 'Pakia Scoresheets').
    Maoni marefu yaliyokuwa yanayosomekana kama kichwa cha paneli.
    """

    def test_no_multiline_django_comments(self):
        leaked = []
        for path in sorted((self.results_templates()).rglob('*.html')):
            for no, line in enumerate(path.read_text().splitlines(), 1):
                idx = line.find('{#')
                if idx != -1 and '#}' not in line[idx:]:
                    leaked.append(f'{path.name}:{no}')
        self.assertEqual(
            leaked, [],
            'Dokeo la {# #} linalozunguka mistari huu linaonekana kama '
            'maandishi kwenye ukurasa — andika kwa {% comment %}: ' + ', '.join(leaked),
        )

    def results_templates(self):
        return PANEL_JS.parent.parent.parent.parent / 'templates'


if __name__ == '__main__':
    unittest.main()
