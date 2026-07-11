/* DevMemory public site — nav, scroll reveal, copy buttons, docs scrollspy.
   Vanilla, no deps. Loaded by landing.html and docs.html. */

// ── Sticky-nav shadow on scroll ──────────────────────────────────────────────
const nav = document.querySelector('.nav');
if (nav) {
  const onScroll = () => nav.classList.toggle('scrolled', window.scrollY > 8);
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });
}

// ── Mobile nav toggle ────────────────────────────────────────────────────────
const toggle = document.querySelector('.nav-toggle');
const links = document.querySelector('.nav-links');
if (toggle && links) {
  toggle.addEventListener('click', () => links.classList.toggle('open'));
  links.querySelectorAll('a').forEach(a =>
    a.addEventListener('click', () => links.classList.remove('open')));
}

// ── Scroll reveal ────────────────────────────────────────────────────────────
const reveals = document.querySelectorAll('.reveal');
if (reveals.length && 'IntersectionObserver' in window) {
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
    }
  }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
  reveals.forEach(el => io.observe(el));
} else {
  reveals.forEach(el => el.classList.add('in'));
}

// ── Copy buttons (data-copy) ─────────────────────────────────────────────────
document.addEventListener('click', async (e) => {
  const btn = e.target.closest('.copy-btn');
  if (!btn) return;
  const text = btn.dataset.copy || '';
  try {
    if (navigator.clipboard) await navigator.clipboard.writeText(text);
    else {
      const t = document.createElement('textarea');
      t.value = text; t.style.position = 'fixed'; t.style.opacity = '0';
      document.body.appendChild(t); t.select(); document.execCommand('copy'); t.remove();
    }
    const original = btn.innerHTML;
    btn.classList.add('done');
    btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
    setTimeout(() => { btn.classList.remove('done'); btn.innerHTML = original; }, 1400);
  } catch { /* clipboard blocked — no-op */ }
});

// ── Docs scrollspy ───────────────────────────────────────────────────────────
const sideLinks = document.querySelectorAll('.docs-side a[href^="#"]');
if (sideLinks.length && 'IntersectionObserver' in window) {
  const map = new Map();
  sideLinks.forEach(a => {
    const el = document.getElementById(a.getAttribute('href').slice(1));
    if (el) map.set(el, a);
  });
  const setActive = (a) => {
    sideLinks.forEach(x => x.classList.remove('active'));
    if (a) a.classList.add('active');
  };
  const spy = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (e.isIntersecting) setActive(map.get(e.target));
    }
  }, { rootMargin: '-80px 0px -70% 0px', threshold: 0 });
  map.forEach((_, el) => spy.observe(el));
}
