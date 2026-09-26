/**
 * AssureX_AI — main.js
 * Modular JS: AXI Robot, Demo Toggles, Multi-step Form,
 * Loading Overlay, OCR Status Carousel, Drag-and-drop
 */

// ══════════════════════════════════════════
// AXI ROBOT — Contextual Tooltip Manager
// ══════════════════════════════════════════
const AXI = {
  contextMessages: {
    login:    "Fill your correct data to get in for warranty claiming process 🚀",
    register: "Fill your correct data to get in for warranty claiming process 🚀",
    claim:    "Double check your receipt numbers for 100% fast verification! ⚡",
    summary:  "Analyzing raw image data via AI Engine... Almost there! 🤖",
    default:  "Hey!! Don't take stress... it's not good for health 😊"
  },

  init(page = 'default') {
    this.page = page;
    this._renderCompanion();
    this._renderContextTip(page);
  },

  _renderCompanion() {
    const el = document.getElementById('axiCompanion');
    if (!el) return;
    const bubble = el.querySelector('.axi-speech-bubble');
    if (bubble) bubble.textContent = this.contextMessages.default;
  },

  _renderContextTip(page) {
    const el = document.getElementById('axiContextTip');
    if (!el) return;
    const msg = this.contextMessages[page] || this.contextMessages.default;
    el.textContent = msg;
    // show tip on load pages that need it
    if (['login','register','claim','summary'].includes(page)) {
      el.style.display = 'block';
      setTimeout(() => {
        el.style.opacity = '0';
        el.style.transition = 'opacity 0.5s ease';
        setTimeout(() => el.style.display = 'none', 500);
      }, 5000);
    } else {
      el.style.display = 'none';
    }
  }
};

// ══════════════════════════════════════════
// LOADING / OCR OVERLAY
// ══════════════════════════════════════════
const OCRLoader = {
  statusMessages: [
    "Scanning raw images & extracting OCR metadata...",
    "Computing SHA-256 document fingerprint hash...",
    "Running Tesseract OCR text extraction engine...",
    "Verifying document hash with manufacturer database...",
    "Cross-referencing serial number & purchase date...",
    "Finalizing AI confidence score computation..."
  ],

  progressSteps: [10, 25, 42, 60, 80, 100],

  _msgEl: null,
  _barEl: null,
  _idx: 0,
  _timer: null,

  show(onComplete) {
    const overlay = document.getElementById('cyclingLoader');
    if (!overlay) return;
    overlay.style.display = 'flex';
    overlay.style.opacity = '0';
    requestAnimationFrame(() => { overlay.style.transition = 'opacity 0.4s ease'; overlay.style.opacity = '1'; });

    this._msgEl = document.getElementById('loaderStatusText');
    this._barEl = document.getElementById('loaderProgress');
    this._idx = 0;
    this._tick(onComplete);
  },

  _tick(onComplete) {
    if (this._idx >= this.statusMessages.length) {
      setTimeout(() => this._finish(onComplete), 600);
      return;
    }
    if (this._msgEl) this._msgEl.textContent = this.statusMessages[this._idx];
    if (this._barEl) this._barEl.style.width = this.progressSteps[this._idx] + '%';
    this._idx++;
    this._timer = setTimeout(() => this._tick(onComplete), 1100);
  },

  _finish(onComplete) {
    const overlay = document.getElementById('cyclingLoader');
    if (overlay) { overlay.style.opacity = '0'; setTimeout(() => overlay.style.display = 'none', 400); }
    if (typeof onComplete === 'function') onComplete();
  },

  hide() {
    clearTimeout(this._timer);
    const overlay = document.getElementById('cyclingLoader');
    if (overlay) { overlay.style.opacity = '0'; setTimeout(() => overlay.style.display = 'none', 400); }
  }
};

// ══════════════════════════════════════════
// DEMO VERDICT TOGGLES (claim summary)
// ══════════════════════════════════════════
const VerdictDemo = {
  verdicts: {
    valid: {
      badgeClass: 'verdict-approved',
      badgeText: '✅ Claim Auto-Approved',
      score: '98.5%',
      scoreOffset: 4,   // stroke-dashoffset: 283 - (283 * 0.985) ≈ 4
      ringColor: '#10B981',
      message: 'Your warranty claim has passed multi-modal AI verification. All document hashes match the manufacturer database, and date validity is confirmed.',
      toggleClass: 'active-valid'
    },
    invalid: {
      badgeClass: 'verdict-rejected',
      badgeText: '❌ Claim Rejected',
      score: '94%',
      scoreOffset: 17,
      ringColor: '#EF4444',
      message: 'AI analysis detected that this receipt fingerprint has already been used in a previous claim. The SHA-256 hash matches claim #CLM-9021. This claim cannot be processed.',
      toggleClass: 'active-invalid'
    },
    review: {
      badgeClass: 'verdict-review',
      badgeText: '🔍 Manual Review Required',
      score: '72%',
      scoreOffset: 79,
      ringColor: '#F59E0B',
      message: 'The AI models detected discrepancies between the extracted purchase date and the warranty window. A human adjudicator will review this claim within 24–48 hours.',
      toggleClass: 'active-review'
    }
  },

  init() {
    this.apply('valid');
  },

  apply(type) {
    const v = this.verdicts[type];
    if (!v) return;

    // Badge
    const badge = document.getElementById('verdictBadge');
    if (badge) {
      badge.className = 'verdict-badge ' + v.badgeClass;
      badge.textContent = v.badgeText;
    }

    // Ring
    const ringFill = document.getElementById('ringFill');
    if (ringFill) {
      ringFill.style.stroke = v.ringColor;
      ringFill.style.strokeDashoffset = v.scoreOffset;
    }
    const ringScore = document.getElementById('ringScore');
    if (ringScore) ringScore.textContent = v.score;

    // Message
    const msg = document.getElementById('verdictMessage');
    if (msg) msg.textContent = v.message;

    // Toggle buttons
    document.querySelectorAll('.demo-toggle').forEach(btn => {
      btn.classList.remove('active-valid', 'active-invalid', 'active-review');
      if (btn.dataset.verdict === type) btn.classList.add(v.toggleClass);
    });
  }
};

// ══════════════════════════════════════════
// DRAG & DROP UPLOAD
// ══════════════════════════════════════════
function initDropzone(zoneId, inputId, listId) {
  const zone  = document.getElementById(zoneId);
  const input = document.getElementById(inputId);
  const list  = document.getElementById(listId);
  if (!zone || !input) return;

  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', ()  => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', e => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    handleFiles(e.dataTransfer.files, list);
  });
  zone.addEventListener('click', () => input.click());
  input.addEventListener('change', () => handleFiles(input.files, list));
}

function handleFiles(files, list) {
  if (!list) return;
  Array.from(files).forEach(file => {
    const item = document.createElement('div');
    item.className = 'dropzone-file';
    const ext = file.name.split('.').pop().toUpperCase();
    const icons = { PDF:'📄', PNG:'🖼️', JPG:'🖼️', JPEG:'🖼️', MP4:'🎥', MOV:'🎥' };
    item.innerHTML = `<span>${icons[ext] || '📎'}</span>
      <span class="file-name">${file.name}</span>
      <span class="file-size">${(file.size / 1024).toFixed(1)} KB</span>
      <button onclick="this.parentElement.remove()" style="background:none;border:none;font-size:16px;cursor:pointer;color:var(--text-muted)">×</button>`;
    list.appendChild(item);
  });
}

// ══════════════════════════════════════════
// NAVBAR — Mobile hamburger
// ══════════════════════════════════════════
function initNavbar() {
  const toggle = document.getElementById('navToggle');
  const menu   = document.getElementById('navMenu');
  if (!toggle || !menu) return;
  toggle.addEventListener('click', () => {
    const open = menu.classList.toggle('nav-open');
    menu.style.display = open ? 'flex' : 'none';
  });
}

// ══════════════════════════════════════════
// SMOOTH SCROLL for anchor links
// ══════════════════════════════════════════
function initSmoothScroll() {
  document.querySelectorAll('a[href^="#"]').forEach(a => {
    a.addEventListener('click', e => {
      const target = document.querySelector(a.getAttribute('href'));
      if (target) { e.preventDefault(); target.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
    });
  });
}

// ══════════════════════════════════════════
// SCROLL REVEAL — fade in on scroll
// ══════════════════════════════════════════
function initScrollReveal() {
  const items = document.querySelectorAll('[data-reveal]');
  if (!items.length) return;
  const io = new IntersectionObserver((entries) => {
    entries.forEach(en => {
      if (en.isIntersecting) { en.target.style.animation = `fadeInUp 0.6s var(--ease-smooth) both`; io.unobserve(en.target); }
    });
  }, { threshold: 0.12 });
  items.forEach(el => { el.style.opacity = '0'; io.observe(el); });
}

// ══════════════════════════════════════════
// CLAIM FORM — multi-section validation
// ══════════════════════════════════════════
const ClaimForm = {
  init() {
    const submitBtn = document.getElementById('claimSubmitBtn');
    if (!submitBtn) return;
    submitBtn.addEventListener('click', (e) => {
      e.preventDefault();
      if (!this._validate()) return;
      OCRLoader.show(() => {
        // Navigate to summary page after loading
        window.location.href = 'claim.html#summary';
      });
    });
  },

  _validate() {
    let valid = true;
    const required = document.querySelectorAll('[required]');
    required.forEach(el => {
      if (!el.value.trim()) {
        el.style.borderColor = 'var(--danger)';
        el.style.boxShadow = '0 0 0 3px rgba(239,68,68,0.15)';
        valid = false;
        el.addEventListener('input', () => {
          el.style.borderColor = '';
          el.style.boxShadow = '';
        }, { once: true });
      }
    });
    if (!valid) {
      const first = document.querySelector('[required]:invalid, .neo-input[style]');
      if (first) first.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    return valid;
  }
};

// ══════════════════════════════════════════
// GLOBAL PAGE INIT
// ══════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
  // Detect page context from body data-page attribute or URL
  const page = document.body.dataset.page || 'default';

  AXI.init(page);
  initNavbar();
  initSmoothScroll();
  initScrollReveal();

  // Page-specific init
  if (page === 'claim') {
    initDropzone('dropzone1', 'fileInput1', 'fileList1');
    initDropzone('dropzone2', 'fileInput2', 'fileList2');
    initDropzone('dropzone3', 'fileInput3', 'fileList3');
    ClaimForm.init();
  }

  if (page === 'summary') {
    VerdictDemo.init();
    document.querySelectorAll('.demo-toggle').forEach(btn => {
      btn.addEventListener('click', () => VerdictDemo.apply(btn.dataset.verdict));
    });
  }
});
