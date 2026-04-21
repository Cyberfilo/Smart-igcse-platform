/* =========================================================
   IGCSE Recap Map — Interactivity
   Two-level filter (area + topic) + dark mode + keyboard shortcuts
   ========================================================= */

(function () {
  'use strict';

  const areaNav = document.getElementById('area-nav');
  const topicNav = document.getElementById('topic-nav');
  // Legacy single-nav fallback for the bundled static `templates/index.html`
  // page served when the DB has no syllabi seeded.
  const legacyNav = document.getElementById('nav');
  const cards = document.querySelectorAll('.topic-card');

  // Filter state — "all" means unfiltered.
  let activeArea = 'all';
  let activeTopic = 'all';

  function applyFilter() {
    cards.forEach(function (card) {
      const cardArea = card.dataset.area || 'other';
      const cardTopic = card.dataset.id || '';
      const areaMatch = activeArea === 'all' || cardArea === activeArea;
      const topicMatch = activeTopic === 'all' || cardTopic === activeTopic;
      if (areaMatch && topicMatch) {
        card.classList.remove('hidden');
      } else {
        card.classList.add('hidden');
      }
    });

    // Topic-nav buttons outside the selected area fade back to inactive.
    if (topicNav) {
      topicNav.querySelectorAll('.nav-btn').forEach(function (btn) {
        const a = btn.dataset.area || 'other';
        if (activeArea === 'all' || a === activeArea) {
          btn.classList.remove('dimmed');
        } else {
          btn.classList.add('dimmed');
        }
      });
    }

    if (activeTopic !== 'all') {
      const firstVisible = document.querySelector('.topic-card:not(.hidden)');
      if (firstVisible) {
        firstVisible.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  }

  function setActive(nav, attr, value) {
    if (!nav) return;
    nav.querySelectorAll('.nav-btn').forEach(function (b) {
      if (b.dataset[attr] === value) {
        b.classList.add('active');
      } else {
        b.classList.remove('active');
      }
    });
  }

  if (areaNav) {
    areaNav.addEventListener('click', function (e) {
      const btn = e.target.closest('.nav-btn');
      if (!btn) return;
      activeArea = btn.dataset.area || 'all';
      // Selecting an area clears topic filter so the whole area is visible.
      activeTopic = 'all';
      setActive(areaNav, 'area', activeArea);
      setActive(topicNav, 'topic', 'all');  // no topic button has data-topic="all"; no-op
      applyFilter();
      if (activeArea === 'all') {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    });
  }

  if (topicNav) {
    topicNav.addEventListener('click', function (e) {
      const btn = e.target.closest('.nav-btn');
      if (!btn) return;
      activeTopic = btn.dataset.topic || 'all';
      setActive(topicNav, 'topic', activeTopic);
      applyFilter();
    });
  }

  // Legacy single-nav path (static bundled page).
  if (legacyNav && !areaNav) {
    legacyNav.addEventListener('click', function (e) {
      const btn = e.target.closest('.nav-btn');
      if (!btn) return;
      legacyNav.querySelectorAll('.nav-btn').forEach(function (b) { b.classList.remove('active'); });
      btn.classList.add('active');
      const topic = btn.dataset.topic;
      cards.forEach(function (card) {
        if (topic === 'all' || card.dataset.id === topic) {
          card.classList.remove('hidden');
        } else {
          card.classList.add('hidden');
        }
      });
      if (topic !== 'all') {
        const firstVisible = document.querySelector('.topic-card:not(.hidden)');
        if (firstVisible) firstVisible.scrollIntoView({ behavior: 'smooth', block: 'start' });
      } else {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    });
  }

  // -- Dark mode toggle with localStorage persistence --
  const themeToggle = document.getElementById('theme-toggle');
  const themeIcon = themeToggle ? themeToggle.querySelector('.theme-icon') : null;

  const savedTheme = localStorage.getItem('igcse-theme');
  const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;

  if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
    document.body.classList.add('dark-mode');
    if (themeIcon) themeIcon.textContent = '◑';
  }

  if (themeToggle) {
    themeToggle.addEventListener('click', function () {
      document.body.classList.toggle('dark-mode');
      const isDark = document.body.classList.contains('dark-mode');
      localStorage.setItem('igcse-theme', isDark ? 'dark' : 'light');
      if (themeIcon) themeIcon.textContent = isDark ? '◑' : '◐';
    });
  }

  // -- Keyboard shortcuts --
  document.addEventListener('keydown', function (e) {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    // "a" or "0" to show all areas + topics
    if (e.key === 'a' || e.key === '0') {
      activeArea = 'all'; activeTopic = 'all';
      setActive(areaNav, 'area', 'all');
      applyFilter();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
    // "d" toggles dark mode
    if (e.key === 'd' && themeToggle) {
      themeToggle.click();
    }
  });

})();
