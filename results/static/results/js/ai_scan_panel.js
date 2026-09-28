/* Paneli ya AI: "AI inasoma" — kiungo kimoja kikichorwa na Marks Entry na
 * Academic roster scan.
 *
 * Kabla ya hila kila ukurasa ulikuwa na JS yake; mtu alipokuwa anaona
 * marks entry alikuwa na paneli nzuri, kwenye academic hakuna chochoto
 * (kromu "Inasoma... subiri kidogo" iliyokuwa ikikaa kwenye span tupu).
 * Sasa paneli moja, matumizi mawili.
 *
 * Markup: results/templates/results/includes/ai_scan_panel.html
 * CSS:    results/static/results/styles.css (darasa .me-ai-*)
 *
 * Matumizi:
 *   const panel = new AiScanPanel({ lang: LANG, rosterSize: 30 });
 *   panel.start();
 *   panel.applyMeta(pollData);        // { stage, pages_done, pages_total, rows }
 *   panel.finish({ title, sub });
 *   panel.fail('Ufunguo si sahihi');
 */
(function (global) {
  'use strict';

  // 0 = kupakia, 1 = AI inasoma, 2 = kulinganisha, 3 = imekamilika.
  var STEPS = ['uploading', 'reading', 'matching', 'done'];

  // Nyuma saa moja inaonekana "0s"; mbili hapo chini inaokoa nafasi ya
  // kipekee kwenye paneli ya sekunde moja (mara kwa mara scan huwa
  // haraka, na "45s" peke yake ni habari bure).
  function fmt(secs) {
    if (secs < 60) return secs + 's';
    return Math.floor(secs / 60) + 'm ' + (secs % 60) + 's';
  }

  function AiScanPanel(opts) {
    opts = opts || {};
    this.lang = opts.lang === 'en' ? 'en' : 'sw';
    this.root = document.getElementById(opts.id || 'aiScanPanel');
    // Kadirio ya idadi ya wanafunzi: inaongeza "x kati ya y" kwenye
    // hatua ya kulinganisha, ambayo kwingine ni namba isiyoeleweka.
    this.rosterSize = opts.rosterSize || 0;
    // float: paneli inabanda juu ya viewport badala ya kusogea ndani ya
    // ukurasa. Inahitajika kwenye ukurasa ambao kifungu cha scan
    // kiko chini sana (academic: vikwamba vya picha viko hatua 4).
    this.float = !!opts.float;
    this.timer = null;
    this.startedAt = 0;
    this.idx = 0;
    if (this.root) {
      if (this.float) this.root.classList.add('me-ai-panel--float');
      this.el = {
        ring: this.root.querySelector('[data-ai="ring"]'),
        ringLabel: this.root.querySelector('[data-ai="ringLabel"]'),
        pct: this.root.querySelector('[data-ai="pct"]'),
        orb: this.root.querySelector('[data-ai="orb"]'),
        stage: this.root.querySelector('[data-ai="stage"]'),
        sub: this.root.querySelector('[data-ai="sub"]'),
        clock: this.root.querySelector('[data-ai="clock"]'),
        bar: this.root.querySelector('[data-ai="bar"]'),
        steps: this.root.querySelector('[data-ai="steps"]'),
        log: this.root.querySelector('[data-ai="log"]'),
        close: this.root.querySelector('[data-ai="close"]'),
      };
      if (this.el.ring) this.el.ring.style.setProperty('--pct', 0);
      if (this.el.close) {
        var self = this;
        this.el.close.addEventListener('click', function (e) {
          e.preventDefault();
          e.stopPropagation();
          self.close();
        });
      }
    }
  }

  /* ── Kufunga paneli ───────────────────────────────────────────────
   * Bezwe hapo awali paneli ilibaki milele baada ya kushindwa
   * ("AI could not read this") — mtu alikuwa lazima a-refresh ukurasa
   * ili kuiondoa. Sasa kitufe cha ✕ (na Escape) kuna kuifunga.
   * close() pia kuanzisha upya paneli ili scan inayofuata isitumie
   * mzigo wa zilizopita. */
  AiScanPanel.prototype.close = function () {
    if (this.timer) { clearInterval(this.timer); this.timer = null; }
    if (!this.root) return;
    this.root.hidden = true;
    this.root.classList.remove('is-done', 'is-error');
    this.root.dataset.busy = '0';
    delete this.root.dataset.upload;
    this.idx = 0;
    this.startedAt = 0;
    if (this.el && this.el.bar) this.el.bar.style.width = '0%';
    if (this.el && this.el.orb) this.el.orb.textContent = '🤖';
    if (this.el && this.el.log) this.el.log.innerHTML = '';
  };

  /* Onyesha paneli tena (inaitwa na start() na wa mtu anayefanya
   * scan mwingine baada ya kui funga). */
  AiScanPanel.prototype.reopen = function () {
    if (!this.root) return;
    this.root.hidden = false;
  };

  /* ── Mzunguko wa asilimia ────────────────────────────────────────
   * Kipande kimoja kinajibu: byte wakati wa kupakia, kurasa wakati
   * wa kusoma, 100% alimaliza. Ring na bar zinaonyesha kitu kile
   * kile, kwa hivyo mtu anayetazama tu mzunguko (kawaida kwenye
   * simu) hupotezi taarifa yoyote. */
  AiScanPanel.prototype.setPct = function (value) {
    if (!this.root) return;
    var pct = Math.max(0, Math.min(100, Math.round(value || 0)));
    if (this.el && this.el.ring) {
      this.el.ring.style.setProperty('--pct', pct);
      this.el.ring.dataset.pct = pct;
    }
    if (this.el && this.el.ringLabel) {
      // Lebo inaonekana tu kama kuna asilimia ya kuonyesha (si 0% cha
      // hatua "AI inaanza"), ili paneli isisomeke tupu.
      this.el.ringLabel.hidden = pct <= 0;
    }
    if (this.el && this.el.pct) this.el.pct.textContent = pct + '%';
  };

  AiScanPanel.prototype.t = function (sw, en) {
    return this.lang === 'sw' ? sw : en;
  };

  AiScanPanel.prototype.renderSteps = function (idx) {
    if (!this.el || !this.el.steps) return;
    var kids = this.el.steps.querySelectorAll('.me-ai-step');
    for (var i = 0; i < kids.length; i++) {
      var pos = STEPS.indexOf(kids[i].dataset.step);
      kids[i].classList.toggle('active', pos === idx);
      kids[i].classList.toggle('done', pos < idx);
    }
  };

  AiScanPanel.prototype.log = function (text) {
    if (!this.el || !this.el.log) return;
    var row = document.createElement('div');
    var t = document.createElement('span');
    t.className = 't';
    t.textContent = fmt(Math.round((Date.now() - this.startedAt) / 1000));
    var m = document.createElement('span');
    m.textContent = text;  // textContent, si innerHTML — maandishi ya AI
    row.appendChild(t);
    row.appendChild(m);
    this.el.log.appendChild(row);
    this.el.log.scrollTop = this.el.log.scrollHeight;
  };

  AiScanPanel.prototype.setStage = function (idx, stageText, subText) {
    this.idx = idx;
    if (this.el && this.el.stage && stageText) this.el.stage.textContent = stageText;
    if (this.el && this.el.sub) this.el.sub.textContent = subText || '';
    this.renderSteps(idx);
  };

  AiScanPanel.prototype.start = function (opts) {
    opts = opts || {};
    if (!this.root) return;
    this.reopen();
    this.root.classList.add('on');
    this.root.classList.remove('is-error', 'is-done');
    this.root.dataset.busy = '1';
    delete this.root.dataset.upload;
    delete this.root.dataset.pagesLogged;
    delete this.root.dataset.upLogged;
    this.startedAt = Date.now();
    this.idx = 0;
    if (this.el.log) this.el.log.innerHTML = '';
    if (this.el.clock) this.el.clock.textContent = '0s';
    if (this.el.bar) this.el.bar.style.width = '';
    if (this.el.orb) this.el.orb.textContent = '\u{1F916}';
    this.setPct(0);
    this.setStage(
      0,
      opts.title || this.t('Pakia picha/PDF…', 'Uploading photo/PDF…'),
      opts.sub || this.t('Tuma faili — hii inachukua sekunde chache.',
                         'Sending the file — this takes a few seconds.')
    );
    var self = this;
    if (this.timer) clearInterval(this.timer);
    this.timer = setInterval(function () {
      if (self.el && self.el.clock) {
        self.el.clock.textContent = fmt(Math.round((Date.now() - self.startedAt) / 1000));
      }
    }, 500);
  };

  /* Hatua 1 — kupakia: onyesha byte halisi zinazopelekwa kwenye
   * seriveri. Picha ya 5 MB kwenye mtandao wa simu inaweza kuchukua
   * sekunde 30; bila kipekee hapo mtu anafikiri kimekatika. */
  AiScanPanel.prototype.setUpload = function (loaded, total) {
    if (!this.root) return;
    this.root.dataset.upload = '1';
    var pct = total ? Math.round((loaded / total) * 100) : 0;
    if (this.el && this.el.bar) this.el.bar.style.width = pct + '%';
    this.setPct(pct);
    var mb = function (b) {
      return b >= 1048576 ? (b / 1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(b / 1024)) + ' KB';
    };
    var sub = this.t('Kupakia faili kwenye seriveri', 'Sending the file to the server');
    if (total) {
      sub += ' — ' + pct + '% (' + mb(loaded) + ' / ' + mb(total) + ')';
    } else if (loaded) {
      sub += ' — ' + mb(loaded);
    }
    this.setStage(0, this.t('Kupakia picha/PDF…', 'Uploading photo/PDF…'), sub);
    if (total) {
      // Log kila robo, si kila onprogress (ambao hutokea mara nyingi
      // kwa sekunde) — log isiyojae mzigo mtupu.
      var quarter = Math.floor(pct / 25) * 25;
      var seen = this.root.dataset.upLogged || '';
      if (quarter > 0 && seen.indexOf(',' + quarter) === -1) {
        this.root.dataset.upLogged = seen + ',' + quarter;
        this.log(this.t('Kupakia ' + quarter + '%', 'Uploaded ' + quarter + '%'));
      }
    }
  };

  /* Kupakia kwa XHR (si fetch) — fetch HAIONYESHI maendeleo ya bytes
   * zinazotumwa. Hapa tunapata kipekee halisi na kuipokea kwenye
   * paneli. Promise inarejia data ya JSON kama fetch, ili msimbo
   * wa ukurusa usibadilike. */
  AiScanPanel.prototype.upload = function (url, formData, opts) {
    opts = opts || {};
    var self = this;
    return new Promise(function (resolve, reject) {
      var xhr = new XMLHttpRequest();
      xhr.open('POST', url, true);
      xhr.setRequestHeader('X-CSRFToken', opts.csrf || '');
      if (xhr.upload) {
        xhr.upload.onprogress = function (e) {
          if (e.lengthComputable) self.setUpload(e.loaded, e.total);
        };
      }
      xhr.onload = function () {
        var data = {};
        try { data = JSON.parse(xhr.responseText); } catch (err) { data = {}; }
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data);
        } else {
          reject(new Error(data.error || self.t('Kupakia imeshindwa.', 'Upload failed.')));
        }
      };
      xhr.onerror = function () {
        reject(new Error(self.t('Muunganisho umekatika wakati wa kupakia.',
                                'The connection dropped during upload.')));
      };
      xhr.ontimeout = function () {
        reject(new Error(self.t('Muda wa kupakia umeisha.', 'Upload timed out.')));
      };
      xhr.send(formData);
    });
  };

  AiScanPanel.prototype.finish = function (summary) {
    summary = summary || {};
    if (this.timer) { clearInterval(this.timer); this.timer = null; }
    if (!this.root) return;
    this.root.dataset.busy = '0';
    delete this.root.dataset.upload;
    this.root.classList.add('is-done');
    if (this.el && this.el.bar) this.el.bar.style.width = '100%';
    this.setPct(100);
    this.setStage(3, summary.title, summary.sub);
    if (this.el && this.el.orb) this.el.orb.textContent = '✅';
  };

  AiScanPanel.prototype.fail = function (message) {
    if (this.timer) { clearInterval(this.timer); this.timer = null; }
    if (!this.root) return;
    this.root.dataset.busy = '0';
    delete this.root.dataset.upload;
    this.root.classList.remove('is-done');
    this.root.classList.add('is-error');
    if (this.el && this.el.orb) this.el.orb.textContent = '⚠️';
    if (this.el && this.el.ringLabel) this.el.ringLabel.hidden = true;
    this.setStage(3, this.t('AI imeshindwa kusoma', 'AI could not read this'), message);
  };

  /* Meta ya seriveri ('reading'/'matching') kuwa paneli yenye maelezo.
   * Kurasa zinazofeli pia zinahesabiwa (seriveri hupanga hivyo), hivyo
   * mzigo hausimama kwenye 1/3 ukurasa uliokufa — ambapo mtu angevutia
   * akisubiri milele. */
  AiScanPanel.prototype.applyMeta = function (meta) {
    if (!this.root || !meta || !meta.stage) return;
    // Kupakia kumekamilika; meta ya AI inafuata — bar inapasua kuonyesha
    // kurasa, si asilimia za byte.
    delete this.root.dataset.upload;
    if (meta.stage === 'reading') {
      if (this.idx > 1) return;  // tuko tayari zaidi — usirudi nyuma
      var total = meta.pages_total;
      var done = meta.pages_done;
      var sub = this.t('AI inasoma kutoka kwa kurasa.',
                       'AI reads from the pages.');
      if (total) {
        sub += ' ' + this.t('Ukurasa', 'Page') + ' ' + (done || 0) + '/' + total;
        var pagePct = Math.round(((done || 0) / total) * 100);
        if (this.el && this.el.bar) this.el.bar.style.width = pagePct + '%';
        // Mzunguko unaonyesha kurasa (si asilimia ya byte) — akina
        // progress ya ukusoma ni mimi, ndiyo inayotatanisha.
        this.setPct(pagePct);
      }
      if (done) {
        // Mstari mmoja kwa kila ukurasa, si kila poll (2500ms) — log
        // isisomeke maneno yale yale mara kwa mara.
        var seen = this.root.dataset.pagesLogged || '';
        if (seen.indexOf(',' + done) === -1) {
          this.root.dataset.pagesLogged = seen + ',' + done;
          this.log(this.t('Ukurasa ' + done + ' umesomwa.', 'Page ' + done + ' read.'));
        }
      }
      this.setStage(1, this.t('AI inasoma…', 'AI is reading…'), sub);
    } else if (meta.stage === 'matching') {
      var sub2;
      if (meta.rows && this.rosterSize) {
        sub2 = this.t(
          'Mistari ' + meta.rows + ' imesomwa — inalinganishwa na wanafunzi ' + this.rosterSize + '.',
          meta.rows + ' rows read — matching against ' + this.rosterSize + ' students.'
        );
      } else if (this.rosterSize) {
        sub2 = this.t('Inalinganisha na orodha ya ' + this.rosterSize + ' wanafunzi.',
                      'Matching against the ' + this.rosterSize + '-student roster.');
      } else {
        sub2 = this.t('Inalinganisha majina na orodha.', 'Matching names to the roster.');
      }
      // AI amesoma kurasa zote; mzunguko unaonyesha kwamba hatua ya
      // kusoma imekamilika (100%) — kulinganisha hana kipekee cha
      // asilimia, kwa hivyo hatutoi mzunguko nyuma.
      this.setPct(100);
      this.setStage(2, this.t('AI inalinganisha majina na orodha…',
                              'AI is matching names to the roster…'), sub2);
    }
  };

  AiScanPanel.STEPS = STEPS;
  global.AiScanPanel = AiScanPanel;
})(window);
