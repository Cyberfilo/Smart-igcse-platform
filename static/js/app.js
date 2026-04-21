/* =========================================================
   IGCSE Recap Map — Interactivity
   Area drill-down · topic jump · per-topic chat · dark mode · shortcuts
   ========================================================= */

(function () {
  'use strict';

  const areaGrid    = document.getElementById('area-grid');
  const areaView    = document.getElementById('area-view');
  const areaBack    = document.getElementById('area-back');
  const areaTitle   = document.getElementById('area-view-title');
  const topicNav    = document.getElementById('topic-nav');
  const topicCards  = document.getElementById('topic-cards');
  // Legacy single-nav fallback for the bundled static page.
  const legacyNav   = document.getElementById('nav');
  const allCards    = document.querySelectorAll('.topic-card');

  // ----- Area drill-down -----

  function showArea(areaCode, areaName) {
    if (!areaView) return;
    areaView.hidden = false;
    if (areaGrid) areaGrid.hidden = true;
    areaTitle.textContent = areaName || areaCode;

    // Populate topic-nav with just this area's topics.
    if (topicNav) {
      topicNav.innerHTML = '';
      const seen = [];
      allCards.forEach(card => {
        if ((card.dataset.area || '') !== areaCode) return;
        const btn = document.createElement('button');
        btn.className = 'nav-btn';
        btn.dataset.topic = card.dataset.id;
        btn.textContent = card.dataset.short || card.dataset.id;
        topicNav.appendChild(btn);
        seen.push(card.dataset.id);
      });
    }

    // Filter cards to this area.
    allCards.forEach(card => {
      if ((card.dataset.area || '') === areaCode) {
        card.classList.remove('hidden');
      } else {
        card.classList.add('hidden');
      }
    });

    window.scrollTo({ top: areaView.offsetTop - 80, behavior: 'smooth' });
  }

  function showAreaPicker() {
    if (areaGrid) areaGrid.hidden = false;
    if (areaView) areaView.hidden = true;
    allCards.forEach(card => card.classList.add('hidden'));
    if (topicNav) topicNav.innerHTML = '';
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  if (areaGrid) {
    areaGrid.addEventListener('click', (e) => {
      const tile = e.target.closest('.area-tile');
      if (!tile) return;
      const code = tile.dataset.area;
      const name = tile.querySelector('.area-tile-name')?.textContent.trim() || code;
      showArea(code, name);
    });
  }

  if (areaBack) {
    areaBack.addEventListener('click', showAreaPicker);
  }

  // Topic-nav click → scroll to that card.
  if (topicNav) {
    topicNav.addEventListener('click', (e) => {
      const btn = e.target.closest('.nav-btn');
      if (!btn) return;
      topicNav.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const id = btn.dataset.topic;
      const target = document.querySelector(`.topic-card[data-id="${id}"]`);
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  // Legacy single-nav path for the pre-DB static fallback page.
  if (legacyNav && !areaGrid) {
    legacyNav.addEventListener('click', (e) => {
      const btn = e.target.closest('.nav-btn');
      if (!btn) return;
      legacyNav.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const topic = btn.dataset.topic;
      allCards.forEach(card => {
        if (topic === 'all' || card.dataset.id === topic) card.classList.remove('hidden');
        else card.classList.add('hidden');
      });
      if (topic !== 'all') {
        const first = document.querySelector('.topic-card:not(.hidden)');
        if (first) first.scrollIntoView({ behavior: 'smooth' });
      } else window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }

  // ----- Per-topic chat -----

  document.querySelectorAll('.topic-chat').forEach(setupChat);

  function setupChat(wrap) {
    const topicId = wrap.dataset.topicId;
    const openBtn = wrap.querySelector('.chat-open');
    const panel   = wrap.querySelector('.chat-panel');
    const log     = wrap.querySelector('.chat-log');
    const form    = wrap.querySelector('.chat-form');
    const input   = wrap.querySelector('.chat-input');
    const history = []; // {role, content}

    openBtn.addEventListener('click', () => {
      panel.hidden = !panel.hidden;
      if (!panel.hidden) input.focus();
    });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const msg = input.value.trim();
      if (!msg) return;
      input.value = '';
      appendMsg(log, 'user', msg);
      history.push({ role: 'user', content: msg });
      const thinking = appendMsg(log, 'assistant', '…thinking');
      thinking.classList.add('chat-msg-thinking');

      try {
        const resp = await fetch(`/api/chat/${topicId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: msg, history: history.slice(0, -1) }),
        });
        const data = await resp.json();
        thinking.classList.remove('chat-msg-thinking');
        thinking.textContent = '';
        renderMsg(thinking, data.reply || '(no reply)');
        history.push({ role: 'assistant', content: data.reply || '' });
        if (window.MathJax && window.MathJax.typesetPromise) {
          window.MathJax.typesetPromise([thinking]).catch(() => {});
        }
      } catch (err) {
        thinking.classList.remove('chat-msg-thinking');
        thinking.textContent = 'Network error. Try again.';
      }
    });
  }

  function appendMsg(log, role, text) {
    const el = document.createElement('div');
    el.className = `chat-msg chat-msg-${role}`;
    el.textContent = text;
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
    return el;
  }

  // Keep basic markdown-ish rendering (paragraphs, line breaks) safe — escape HTML,
  // then restore LaTeX delimiters so MathJax can find them.
  function renderMsg(el, raw) {
    const escaped = raw
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\n\n/g, '</p><p>')
      .replace(/\n/g, '<br>');
    el.innerHTML = `<p>${escaped}</p>`;
  }

  // ----- Dark mode -----

  const themeToggle = document.getElementById('theme-toggle');
  const themeIcon = themeToggle?.querySelector('.theme-icon');
  const saved = localStorage.getItem('igcse-theme');
  const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  if (saved === 'dark' || (!saved && prefersDark)) {
    document.body.classList.add('dark-mode');
    if (themeIcon) themeIcon.textContent = '◑';
  }
  themeToggle?.addEventListener('click', () => {
    document.body.classList.toggle('dark-mode');
    const isDark = document.body.classList.contains('dark-mode');
    localStorage.setItem('igcse-theme', isDark ? 'dark' : 'light');
    if (themeIcon) themeIcon.textContent = isDark ? '◑' : '◐';
  });

  // ----- Keyboard shortcuts -----

  document.addEventListener('keydown', (e) => {
    if (['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return;
    if (e.key === 'a' || e.key === '0') showAreaPicker();
    if (e.key === 'd' && themeToggle) themeToggle.click();
    if (e.key === 'Escape') {
      document.querySelectorAll('.chat-panel:not([hidden])').forEach(p => p.hidden = true);
    }
  });
})();
