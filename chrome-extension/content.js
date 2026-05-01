/**
 * OpenClaw Content Script v2
 * ===========================
 * Runs inside every page. Handles messages from background.js
 * for fine-grained DOM interaction that requires page context.
 */

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  (async () => {
    try {
      sendResponse(await handleMessage(msg));
    } catch (e) {
      sendResponse({ error: e.message });
    }
  })();
  return true; // keep channel open for async
});

async function handleMessage(msg) {
  switch (msg.action) {

    case 'getPageInfo':
      return {
        url:    window.location.href,
        title:  document.title,
        text:   document.body.innerText.substring(0, 5000),
        forms:  getFormInfo(),
        domain: window.location.hostname,
      };

    case 'clickElement':
      return domClick(msg.selector);

    case 'smartClick':
      return smartClickByText(msg.text, msg.role);

    case 'fillInput':
      return domFill(msg.selector, msg.value);

    case 'smartFill':
      return smartFillByLabel(msg.label, msg.value);

    case 'extractText':
      return { text: (document.querySelector(msg.selector || 'body') || document.body).innerText };

    case 'extractLinks':
      return {
        links: Array.from(document.querySelectorAll('a[href]'))
          .slice(0, 50)
          .map(a => ({ text: a.textContent.trim(), href: a.href })),
      };

    case 'scrollTo':
      window.scrollTo({ top: msg.y || 0, left: msg.x || 0, behavior: 'smooth' });
      return { scrolled: true };

    case 'scrollIntoView':
      (document.querySelector(msg.selector) || document.body).scrollIntoView({ behavior: 'smooth' });
      return { done: true };

    case 'pressKey':
      document.dispatchEvent(new KeyboardEvent('keydown', { key: msg.key, bubbles: true }));
      return { pressed: msg.key };

    case 'waitForElement': {
      const el = await waitForEl(msg.selector, msg.timeout || 8000);
      return { found: !!el, text: el?.textContent?.trim() };
    }

    // ── YouTube helpers (called from page context) ──────────────────────

    case 'ytPlay':
      document.querySelector('video')?.play();
      return { playing: true };

    case 'ytPause':
      document.querySelector('video')?.pause();
      return { paused: true };

    case 'ytVolume':
      if (document.querySelector('video')) document.querySelector('video').volume = (msg.level || 50) / 100;
      return { volume: msg.level };

    // ── Google Meet helpers ─────────────────────────────────────────────

    case 'meetJoinClick': {
      const btn = Array.from(document.querySelectorAll('button'))
        .find(b => /join|ask to join/i.test(b.textContent));
      if (btn) { btn.click(); return { joined: true }; }
      return { joined: false, note: 'Join button not found yet' };
    }

    default:
      return { error: `Unknown action: ${msg.action}` };
  }
}

// ─── DOM helpers ──────────────────────────────────────────────────────────

function domClick(selector) {
  const el = document.querySelector(selector);
  if (!el) throw new Error(`Not found: ${selector}`);
  el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
  el.dispatchEvent(new MouseEvent('mouseup',   { bubbles: true }));
  el.click();
  return { clicked: selector };
}

function domFill(selector, value) {
  const el = document.querySelector(selector);
  if (!el) throw new Error(`Not found: ${selector}`);
  el.focus();
  if (el.isContentEditable) {
    el.textContent = value;
  } else {
    // Native input value setter — works with React/Angular controlled inputs
    const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set
      || Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
    if (nativeSetter) nativeSetter.call(el, value); else el.value = value;
  }
  ['input', 'change', 'blur'].forEach(ev => el.dispatchEvent(new Event(ev, { bubbles: true })));
  return { filled: selector };
}

function smartClickByText(text, role = null) {
  const lower = text.toLowerCase();
  const scope = role
    ? `[role="${role}"]`
    : 'button, a, [role="button"], [role="link"], input[type="submit"], input[type="button"]';
  const el = Array.from(document.querySelectorAll(scope))
    .find(e => e.textContent.trim().toLowerCase().includes(lower));
  if (!el) throw new Error(`No element matching text "${text}"`);
  el.click();
  return { clicked: el.textContent.trim() };
}

function smartFillByLabel(label, value) {
  const lower = label.toLowerCase();
  const inputs = Array.from(document.querySelectorAll('input, textarea, [contenteditable="true"]'));
  const el = inputs.find(i => {
    if ((i.getAttribute('aria-label') || '').toLowerCase().includes(lower)) return true;
    if ((i.placeholder || '').toLowerCase().includes(lower)) return true;
    if (i.id) {
      const lab = document.querySelector(`label[for="${i.id}"]`);
      if (lab && lab.textContent.toLowerCase().includes(lower)) return true;
    }
    return false;
  });
  if (!el) throw new Error(`No input for label "${label}"`);
  return domFill(el.id ? `#${el.id}` : '[contenteditable="true"]', value);
}

function waitForEl(selector, timeout = 8000) {
  return new Promise((resolve) => {
    if (document.querySelector(selector)) return resolve(document.querySelector(selector));
    const ob = new MutationObserver(() => {
      const el = document.querySelector(selector);
      if (el) { ob.disconnect(); resolve(el); }
    });
    ob.observe(document.body, { childList: true, subtree: true });
    setTimeout(() => { ob.disconnect(); resolve(null); }, timeout);
  });
}

function getFormInfo() {
  return Array.from(document.querySelectorAll('form')).map((form, i) => ({
    index:  i,
    action: form.action,
    fields: Array.from(form.querySelectorAll('input, textarea, select')).map(inp => ({
      type:        inp.type || inp.tagName.toLowerCase(),
      name:        inp.name,
      id:          inp.id,
      placeholder: inp.placeholder,
      ariaLabel:   inp.getAttribute('aria-label'),
    })),
  }));
}

console.log('[OpenClaw v2] Content script ready on', window.location.hostname);
