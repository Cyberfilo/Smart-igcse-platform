/* =========================================================
   IGCSE 0580 Topics Recap Map — Interactivity
   Handles: topic filtering + dark mode toggle with persistence
   ========================================================= */

(function () {
  'use strict';

  // -- Topic filter navigation --
  const nav = document.getElementById('nav');
  const cards = document.querySelectorAll('.topic-card');

  if (nav) {
    nav.addEventListener('click', function (e) {
      const btn = e.target.closest('.nav-btn');
      if (!btn) return;

      document.querySelectorAll('.nav-btn').forEach(function (b) {
        b.classList.remove('active');
      });
      btn.classList.add('active');

      const topic = btn.dataset.topic;
      cards.forEach(function (card) {
        if (topic === 'all' || card.dataset.id === topic) {
          card.classList.remove('hidden');
        } else {
          card.classList.add('hidden');
        }
      });

      // Smooth scroll to first visible card when filtering to a single topic
      if (topic !== 'all') {
        const firstVisible = document.querySelector('.topic-card:not(.hidden)');
        if (firstVisible) {
          firstVisible.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      } else {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    });
  }

  // -- Dark mode toggle with localStorage persistence --
  const themeToggle = document.getElementById('theme-toggle');
  const themeIcon = themeToggle ? themeToggle.querySelector('.theme-icon') : null;

  // Load saved theme or use system preference
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
    // Skip if user is typing in an input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    // Number keys 1-7 jump to topics
    if (e.key >= '1' && e.key <= '7') {
      const btn = document.querySelector('.nav-btn[data-topic="' + e.key + '"]');
      if (btn) btn.click();
    }
    // "a" or "0" to show all
    if (e.key === 'a' || e.key === '0') {
      const allBtn = document.querySelector('.nav-btn[data-topic="all"]');
      if (allBtn) allBtn.click();
    }
    // "d" toggles dark mode
    if (e.key === 'd' && themeToggle) {
      themeToggle.click();
    }
  });

})();
