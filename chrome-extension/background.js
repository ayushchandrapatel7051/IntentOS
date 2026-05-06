/**
 * OpenClaw Chrome Extension — Background Service Worker v3.1
 * ==========================================================
 * Architecture: pre-built "recipes" per domain.
 * The Python agent sends ONE high-level command (e.g. "playYouTube").
 * All DOM work happens here — zero extra LLM calls per action.
 *
 * Fixes in v3.1:
 *   - composeMail: verifies "Message sent" confirmation (retries 3×)
 *   - createCalendarEvent: clicks "Add Google Meet" button, waits for
 *     Meet link to appear, extracts it, THEN saves the event
 *   - All commands return { success, verified } for executor validation
 *   - Duplicate-tab guard for Gmail compose window
 */

const WS_URL = 'ws://127.0.0.1:8765';
let ws = null;
let reconnectDelay = 1000;
const MAX_RECONNECT_DELAY = 15000;
const DEFAULT_COMMAND_TIMEOUT_MS = 45000;

function withTimeout(promise, ms, label) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${label} timed out after ${Math.round(ms / 1000)}s`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

// ─── WebSocket connection ─────────────────────────────────────────────────

function connectWebSocket() {
  if (ws) {
    try { ws.close(); } catch {}
    ws = null;
  }

  try {
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      console.log('[OpenClaw] ✓ Connected to IntentOS agent');
      chrome.storage.local.set({ connectionStatus: 'connected' });
      reconnectDelay = 1000;
    };

    ws.onmessage = async (event) => {
      let data;
      try { data = JSON.parse(event.data); } catch { return; }
      try {
        const timeoutMs = Number(data.timeout || data.params?.timeoutMs || DEFAULT_COMMAND_TIMEOUT_MS);
        const result = await withTimeout(handleCommand(data), timeoutMs, data.command || 'command');
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ id: data.id, success: true, verified: result.verified ?? true, ...result }));
        }
        reconnectDelay = 1000;
      } catch (err) {
        console.error('[OpenClaw] Command error:', err);
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ id: data.id, success: false, verified: false, error: err.message }));
        }
      }
    };

    ws.onclose = (ev) => {
      console.log(`[OpenClaw] Disconnected (code ${ev.code}). Retry in ${reconnectDelay / 1000}s`);
      chrome.storage.local.set({ connectionStatus: 'disconnected' });
      ws = null;
      setTimeout(connectWebSocket, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY);
    };

    ws.onerror = () => {
      console.log('[OpenClaw] WebSocket error (onclose will handle reconnect)');
    };
  } catch (e) {
    console.log('[OpenClaw] Connection failed:', e);
    setTimeout(connectWebSocket, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY);
  }
}

// ─── Tab resolution (THE FIX for "No active tab" in MV3) ─────────────────

async function getActiveTab() {
  const [focusedTab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (focusedTab) return focusedTab;

  const activeTabs = await chrome.tabs.query({ active: true });
  if (activeTabs.length > 0) return activeTabs[0];

  const allTabs = await chrome.tabs.query({});
  if (allTabs.length > 0) {
    allTabs.sort((a, b) => (b.lastAccessed || 0) - (a.lastAccessed || 0));
    return allTabs[0];
  }

  throw new Error('No tabs found — browser has no open tabs');
}

async function resolveTabId(tabId) {
  // Validate tabId is a positive integer — reject null, undefined, NaN, 0, strings, etc.
  if (tabId != null && Number.isInteger(tabId) && tabId > 0) {
    // Verify the tab actually exists before returning
    try {
      await chrome.tabs.get(tabId);
      return tabId;
    } catch (_) {
      // Tab doesn't exist anymore — fall through to getActiveTab()
    }
  }
  const tab = await getActiveTab();
  return tab.id;
}

async function waitForTabLoad(tabId, timeoutMs = 15000) {
  // Guard: if tabId is not a valid positive integer, resolve immediately
  if (tabId == null || !Number.isInteger(tabId) || tabId <= 0) {
    return;
  }

  try {
    // MV3: chrome.tabs.get() returns a Promise — do NOT use callback style
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === 'complete') return;
  } catch (err) {
    // Tab doesn't exist or was closed — nothing to wait for
    return;
  }

  // Wait for the tab to finish loading
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      resolve();
    }, timeoutMs);

    function listener(updatedTabId, changeInfo) {
      if (updatedTabId === tabId && changeInfo.status === 'complete') {
        clearTimeout(timer);
        chrome.tabs.onUpdated.removeListener(listener);
        resolve();
      }
    }
    chrome.tabs.onUpdated.addListener(listener);
  });
}

async function ensureTab(url, waitForLoad = true) {
  const wins = await chrome.windows.getAll();
  let tab;
  if (wins.length === 0) {
    const win = await chrome.windows.create({ url, focused: true });
    tab = win.tabs[0];
  } else {
    tab = await chrome.tabs.create({ url });
  }

  if (waitForLoad) {
    await waitForTabLoad(tab.id, 20000);
    tab = await chrome.tabs.get(tab.id);
  }
  return tab;
}

// ─── Main dispatcher ──────────────────────────────────────────────────────

async function handleCommand({ command, params = {} }) {
  logCommand(command);
  switch (command) {

    // ── Core ────────────────────────────────────────────────────────────
    case 'getTabs':           return getTabs();
    case 'switchTab':         return switchTab(params.tabId);
    case 'closeTab':          return closeTab(params.tabId);
    case 'navigate':          return navigateTab(params.tabId, params.url, params.newTab);
    case 'injectScript':      return injectScript(params.tabId, params.code);
    case 'getDom':            return getDomContent(params.tabId, params.selector);
    case 'clickElement':      return clickElement(params.tabId, params.selector);
    case 'fillInput':         return fillInput(params.tabId, params.selector, params.value);
    case 'screenshot':        return captureTab();
    case 'waitForSelector':   return waitForSelector(params.tabId, params.selector, params.timeout);
    case 'smartClick':        return smartClick(params.tabId, params.text, params.role);
    case 'smartFill':         return smartFill(params.tabId, params.label, params.value);
    case 'extractStructured': return extractStructured(params.tabId, params.schema);

    // ── YouTube ─────────────────────────────────────────────────────────
    case 'searchYouTube':     return searchYouTube(params.query, params.autoplay, params.videoIndex);
    case 'playYouTube':       return youtubeControl('play');
    case 'pauseYouTube':      return youtubeControl('pause');
    case 'setVolume':         return youtubeSetVolume(params.level);
    case 'seekTo':            return youtubeSeek(params.seconds);
    case 'getVideoInfo':      return youtubeGetInfo();
    case 'nextVideo':         return youtubeControl('next');

    // ── Gmail ────────────────────────────────────────────────────────────
    case 'composeMail':       return composeMail(params.to, params.subject, params.body, params.send);
    case 'sendMail':          return composeMail(params.to, params.subject, params.body, true);
    case 'searchMail':        return searchMail(params.query);
    case 'replyMail':         return replyMail(params.tabId, params.body);
    case 'getUnread':         return getUnreadCount();

    // ── Google Calendar ──────────────────────────────────────────────────
    case 'openCalendar':      return openCalendar();
    case 'createEvent':       return createCalendarEvent(params);
    case 'getEvents':         return getCalendarEvents(params.date);

    // ── Google Meet ──────────────────────────────────────────────────────
    case 'joinMeet':          return joinMeet(params.url);
    case 'scheduleMeet':      return scheduleMeet(params);
    case 'muteMic':           return meetControl('mute_mic');
    case 'muteCamera':        return meetControl('mute_camera');
    case 'leaveMeet':         return meetControl('leave');

    // ── Google Drive ─────────────────────────────────────────────────────
    case 'searchDrive':       return searchDrive(params.query);
    case 'openDriveFile':     return openDriveFile(params.fileId);

    // ── Agentic Web Agent ─────────────────────────────────────────────
    case 'extractPage':       return extractPageElements(params.tabId);
    case 'performActions':    return performPageActions(params.tabId, params.actions);

    // ── Direct content extraction (no LLM needed) ─────────────────────
    case 'extractText':
    case 'getPageText':       return getPageText(params.tabId, params.selector);

    default:
      throw new Error(`Unknown command: ${command}`);
  }
}

// ─── Core helpers ─────────────────────────────────────────────────────────

async function getTabs() {
  const tabs = await chrome.tabs.query({});
  return { tabs: tabs.map(t => ({ id: t.id, url: t.url, title: t.title, active: t.active })) };
}

async function switchTab(tabId) {
  await chrome.tabs.update(tabId, { active: true });
  const tab = await chrome.tabs.get(tabId);
  await chrome.windows.update(tab.windowId, { focused: true });
  return { switched: tabId };
}

async function closeTab(tabId) {
  await chrome.tabs.remove(tabId);
  return { closed: tabId };
}

async function navigateTab(tabId, url, newTab = false) {
  if (newTab) {
    const tab = await ensureTab(url);
    return { tabId: tab.id };
  }
  tabId = await resolveTabId(tabId);
  await chrome.tabs.update(tabId, { url });
  await waitForTabLoad(tabId, 3000);
  return { tabId };
}

async function injectScript(tabId, code) {
  tabId = await resolveTabId(tabId);
  await waitForTabLoad(tabId);
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: new Function(`return (${code})()`),
  });
  return { result: results[0]?.result };
}

async function getDomContent(tabId, selector = 'body') {
  tabId = await resolveTabId(tabId);
  await waitForTabLoad(tabId);
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (sel) => {
      const el = document.querySelector(sel);
      return el ? el.innerText.substring(0, 6000) : '';
    },
    args: [selector],
  });
  return { content: results[0]?.result || '' };
}

/**
 * getPageText — directly extract visible text from a CSS selector.
 * NO LLM calls, no element enumeration — just pure DOM innerText.
 * Perfect for Wikipedia, news articles, documentation pages, etc.
 *
 * selector examples:
 *   "#mw-content-text"  → Wikipedia article body
 *   "article"           → generic article tag
 *   "body"              → entire page (default)
 */
async function getPageText(tabId, selector = 'body') {
  tabId = await resolveTabId(tabId);
  // Extra wait to let page content fully render (Wikipedia, articles, etc.)
  await waitForTabLoad(tabId, 20000);
  await new Promise(r => setTimeout(r, 2000));

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (sel) => {
      // Try the requested selector first; fall back to body
      const el = document.querySelector(sel) || document.body;
      return (el.innerText || el.textContent || '').trim();
    },
    args: [selector || 'body'],
  });
  const text = results[0]?.result || '';
  return { text, selector: selector || 'body', length: text.length };
}

async function clickElement(tabId, selector) {
  tabId = await resolveTabId(tabId);
  await waitForTabLoad(tabId);
  await chrome.scripting.executeScript({
    target: { tabId },
    func: (sel) => {
      const el = document.querySelector(sel);
      if (!el) throw new Error(`Element not found: ${sel}`);
      el.scrollIntoView({ behavior: 'instant', block: 'center' });
      el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
      el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
      el.click();
    },
    args: [selector],
  });
  return { clicked: selector };
}

async function fillInput(tabId, selector, value) {
  tabId = await resolveTabId(tabId);
  await waitForTabLoad(tabId);
  await chrome.scripting.executeScript({
    target: { tabId },
    func: (sel, val) => {
      const el = document.querySelector(sel);
      if (!el) throw new Error(`Element not found: ${sel}`);
      el.focus();
      el.value = val;
      ['input', 'change', 'blur'].forEach(ev =>
        el.dispatchEvent(new Event(ev, { bubbles: true }))
      );
    },
    args: [selector, value],
  });
  return { filled: selector };
}

async function captureTab() {
  const [win] = await chrome.windows.getAll({ windowTypes: ['normal'] })
    .then(ws => ws.filter(w => w.focused));
  const windowId = win ? win.id : undefined;
  const dataUrl = await chrome.tabs.captureVisibleTab(windowId, { format: 'jpeg', quality: 80 });
  return { screenshot: dataUrl };
}

async function waitForSelector(tabId, selector, timeout = 10000) {
  tabId = await resolveTabId(tabId);
  await waitForTabLoad(tabId);
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (sel, ms) => new Promise((resolve, reject) => {
      if (document.querySelector(sel)) return resolve(true);
      const ob = new MutationObserver(() => {
        if (document.querySelector(sel)) { ob.disconnect(); resolve(true); }
      });
      ob.observe(document.documentElement, { childList: true, subtree: true });
      setTimeout(() => {
        ob.disconnect();
        reject(new Error(`Timeout waiting for: ${sel}`));
      }, ms);
    }),
    args: [selector, timeout],
  });
  return { found: results[0]?.result };
}

async function smartClick(tabId, text, role = null) {
  tabId = await resolveTabId(tabId);
  await waitForTabLoad(tabId);
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (txt, rl) => {
      const lower = txt.toLowerCase();
      const sel = rl
        ? `[role="${rl}"]`
        : 'button, a, [role="button"], [role="link"], input[type="submit"]';
      const el = Array.from(document.querySelectorAll(sel))
        .find(e => e.textContent.trim().toLowerCase().includes(lower));
      if (!el) throw new Error(`No element with text "${txt}"`);
      el.scrollIntoView({ behavior: 'instant', block: 'center' });
      el.click();
      return el.textContent.trim();
    },
    args: [text, role],
  });
  return { clicked: results[0]?.result };
}

async function smartFill(tabId, label, value) {
  tabId = await resolveTabId(tabId);
  await waitForTabLoad(tabId);
  await chrome.scripting.executeScript({
    target: { tabId },
    func: (lbl, val) => {
      const lower = lbl.toLowerCase();
      const inputs = Array.from(document.querySelectorAll('input, textarea, [contenteditable]'));
      const el = inputs.find(i =>
        (i.getAttribute('aria-label') || '').toLowerCase().includes(lower) ||
        (i.placeholder || '').toLowerCase().includes(lower) ||
        (() => {
          const id = i.id;
          if (!id) return false;
          const lab = document.querySelector(`label[for="${id}"]`);
          return lab && lab.textContent.toLowerCase().includes(lower);
        })()
      );
      if (!el) throw new Error(`No input for label "${lbl}"`);
      el.focus();
      if (el.isContentEditable) {
        el.textContent = val;
      } else {
        const proto = el.tagName === 'TEXTAREA'
          ? HTMLTextAreaElement.prototype
          : HTMLInputElement.prototype;
        const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
        if (nativeSetter) nativeSetter.call(el, val);
        else el.value = val;
      }
      ['input', 'change'].forEach(ev => el.dispatchEvent(new Event(ev, { bubbles: true })));
    },
    args: [label, value],
  });
  return { filled: label };
}

async function extractStructured(tabId, schema = 'text') {
  tabId = await resolveTabId(tabId);
  await waitForTabLoad(tabId);
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (sch) => {
      if (sch === 'links') {
        return Array.from(document.querySelectorAll('a[href]'))
          .slice(0, 30)
          .map(a => ({ text: a.textContent.trim(), href: a.href }));
      }
      if (sch === 'headings') {
        return Array.from(document.querySelectorAll('h1,h2,h3'))
          .map(h => ({ level: h.tagName, text: h.textContent.trim() }));
      }
      return document.body.innerText.substring(0, 5000);
    },
    args: [schema],
  });
  return { data: results[0]?.result };
}

// ─── Shared click-retry helper ────────────────────────────────────────────

async function retryClickButton(tabId, selectors, maxRetries = 8, intervalMs = 1500) {
  const cssSelectors = selectors.filter(s => !s.startsWith('text:'));
  const textMatchers  = selectors
    .filter(s => s.startsWith('text:'))
    .map(s => s.slice(5).toLowerCase());

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    await new Promise(r => setTimeout(r, intervalMs));

    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: (cssSels, textStrs) => {
        for (const sel of cssSels) {
          try {
            const el = document.querySelector(sel);
            if (el && el.offsetParent !== null) {
              el.scrollIntoView({ behavior: 'instant', block: 'center' });
              el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
              el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
              el.click();
              return { clicked: sel, text: el.textContent?.trim() };
            }
          } catch (_) {}
        }

        const clickables = Array.from(document.querySelectorAll(
          'button, [role="button"], input[type="submit"], a'
        ));
        for (const el of clickables) {
          if (el.offsetParent === null) continue;
          const elText = (el.textContent?.trim() || el.value || '').toLowerCase();
          for (const matcher of textStrs) {
            if (elText.includes(matcher)) {
              el.scrollIntoView({ behavior: 'instant', block: 'center' });
              el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
              el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
              el.click();
              return { clicked: 'text:' + matcher, text: el.textContent?.trim() };
            }
          }
        }
        return null;
      },
      args: [cssSelectors, textMatchers],
    });

    const r = results[0]?.result;
    if (r) return r;
  }
  return null;
}

// ─── YouTube recipes ──────────────────────────────────────────────────────

async function searchYouTube(query, autoplay = true, videoIndex = 1) {
  const url = `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}`;

  const [existingTab] = await chrome.tabs.query({ url: "*://*.youtube.com/*" });
  let tab;
  if (existingTab) {
    tab = await chrome.tabs.update(existingTab.id, { url, active: true });
    await waitForTabLoad(tab.id, 20000);
  } else {
    tab = await ensureTab(url, true);
  }

  if (!autoplay) return { tabId: tab.id, searched: query, playing: false };

  const idx = videoIndex || 1;
  let clickResult = null;

  for (let attempt = 0; attempt < 5; attempt++) {
    if (attempt > 0) await new Promise(r => setTimeout(r, 1500));

    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: (targetIdx) => {
        const selectors = [
          'ytd-video-renderer a#video-title',
          'ytd-video-renderer h3 a',
          '#contents ytd-video-renderer a[href^="/watch"]',
        ];
        let videos = [];
        for (const sel of selectors) {
          videos = Array.from(document.querySelectorAll(sel))
            .filter(el => el.href && el.href.includes('/watch'));
          if (videos.length >= targetIdx) break;
        }
        const target = videos[targetIdx - 1];
        if (!target) return { found: false, total: videos.length };
        target.scrollIntoView({ behavior: 'instant', block: 'center' });
        target.click();
        return { found: true, title: target.textContent.trim(), index: targetIdx };
      },
      args: [idx],
    });

    clickResult = results[0]?.result;
    if (clickResult?.found) break;
  }

  if (clickResult?.found) {
    return { tabId: tab.id, searched: query, playing: true, videoIndex: idx, title: clickResult.title };
  }
  return { tabId: tab.id, searched: query, playing: false, warning: `Video ${idx} not found after retries` };
}

async function youtubeControl(action) {
  const tabs = await chrome.tabs.query({ url: '*://www.youtube.com/*' });
  if (!tabs.length) throw new Error('No YouTube tab is open');
  const tab = tabs[0];
  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: (act) => {
      const video = document.querySelector('video');
      if (!video) throw new Error('No <video> element found on this YouTube page');
      if (act === 'play')  { video.play(); return; }
      if (act === 'pause') { video.pause(); return; }
      if (act === 'next')  {
        const btn = document.querySelector('.ytp-next-button');
        if (btn) btn.click();
        else throw new Error('Next button not found');
      }
    },
    args: [action],
  });
  return { action, tabId: tab.id };
}

async function youtubeSetVolume(level = 50) {
  const tabs = await chrome.tabs.query({ url: '*://www.youtube.com/*' });
  if (!tabs.length) throw new Error('No YouTube tab is open');
  await chrome.scripting.executeScript({
    target: { tabId: tabs[0].id },
    func: (vol) => {
      const v = document.querySelector('video');
      if (!v) throw new Error('No <video> element');
      v.volume = Math.max(0, Math.min(1, vol / 100));
    },
    args: [level],
  });
  return { volume: level };
}

async function youtubeSeek(seconds = 0) {
  const tabs = await chrome.tabs.query({ url: '*://www.youtube.com/*' });
  if (!tabs.length) throw new Error('No YouTube tab is open');
  await chrome.scripting.executeScript({
    target: { tabId: tabs[0].id },
    func: (s) => {
      const v = document.querySelector('video');
      if (!v) throw new Error('No <video> element');
      v.currentTime = s;
    },
    args: [seconds],
  });
  return { seeked: seconds };
}

async function youtubeGetInfo() {
  const tabs = await chrome.tabs.query({ url: '*://www.youtube.com/watch*' });
  if (!tabs.length) return { error: 'No YouTube watch tab is open' };
  const results = await chrome.scripting.executeScript({
    target: { tabId: tabs[0].id },
    func: () => {
      const v = document.querySelector('video');
      return {
        title:       document.title,
        currentTime: v?.currentTime,
        duration:    v?.duration,
        paused:      v?.paused,
        volume:      v?.volume,
      };
    },
  });
  return results[0]?.result || {};
}

// ─── Gmail recipes ────────────────────────────────────────────────────────

/**
 * Wait for "Message sent" confirmation toast in Gmail.
 * Returns true if found within timeoutMs, false otherwise.
 */
async function waitForGmailSentConfirmation(tabId, timeoutMs = 10000) {
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (ms) => new Promise((resolve) => {
      // Check immediately — toast may already be visible
      const SENT_SELECTORS = [
        '[data-tooltip="Message sent"]',
        '[aria-label="Message sent"]',
        '.bAq',       // Gmail's internal "sent" snackbar class
        '.vh',        // Another known sent-toast class
      ];
      const SENT_TEXT = ['message sent', 'sent', 'message was sent'];

      function isSentVisible() {
        // 1. Selector-based check
        for (const sel of SENT_SELECTORS) {
          if (document.querySelector(sel)) return true;
        }
        // 2. Text-based check on visible snackbars / toasts
        const candidates = Array.from(document.querySelectorAll(
          '[role="alert"], [role="status"], .aZ, .vh, .bAq, [data-message-id]'
        ));
        for (const el of candidates) {
          const txt = (el.textContent || '').toLowerCase().trim();
          if (SENT_TEXT.some(t => txt.includes(t))) return true;
        }
        // 3. Gmail URL hash confirms — compose window closed → mail sent
        if (!document.querySelector('[name="subjectbox"], [aria-label*="Subject"]')) {
          // The compose window is gone; check if we're back on the inbox
          if (window.location.hash.includes('#inbox') || window.location.hash.includes('#sent')) {
            return true;
          }
        }
        return false;
      }

      if (isSentVisible()) return resolve(true);

      const ob = new MutationObserver(() => {
        if (isSentVisible()) { ob.disconnect(); clearTimeout(timer); resolve(true); }
      });
      ob.observe(document.documentElement, { childList: true, subtree: true, attributes: true });

      const timer = setTimeout(() => { ob.disconnect(); resolve(false); }, ms);
    }),
    args: [timeoutMs],
  });
  return results[0]?.result === true;
}

async function composeMail(to, subject, body, send = false) {
  // ── Duplicate-tab guard ─────────────────────────────────────────────
  // Gmail opens a compose window in the existing tab — avoid opening a
  // second Gmail tab if one is already open.
  const existingGmailTabs = await chrome.tabs.query({ url: '*://mail.google.com/*' });
  let tab;

  const gmailUrl = `https://mail.google.com/mail/?view=cm&fs=1`
    + `&to=${encodeURIComponent(to || '')}`
    + `&su=${encodeURIComponent(subject || '')}`
    + `&body=${encodeURIComponent(body || '')}`;

  if (existingGmailTabs.length > 0) {
    tab = await chrome.tabs.update(existingGmailTabs[0].id, { url: gmailUrl, active: true });
    await waitForTabLoad(tab.id, 20000);
  } else {
    tab = await ensureTab(gmailUrl, true);
  }

  if (!send) return { tabId: tab.id, status: 'draft_opened', verified: false };

  // ── Send + verify loop (up to 3 attempts) ──────────────────────────
  const MAX_SEND_ATTEMPTS = 3;
  let lastClickResult = null;

  for (let attempt = 0; attempt < MAX_SEND_ATTEMPTS; attempt++) {
    // 1. Click Send button
    const clicked = await retryClickButton(tab.id, [
      '[data-tooltip*="Send"]',
      '[aria-label*="Send"]',
      'div[aria-label*="Send"]',
      '.T-I.J-J5-Ji[role="button"]',
      'text:Send',
    ], 8, 1200);

    lastClickResult = clicked;

    if (!clicked) {
      // Fallback: Ctrl+Enter to send
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => {
          const target = document.activeElement || document.body;
          target.dispatchEvent(new KeyboardEvent('keydown', {
            key: 'Enter', code: 'Enter', keyCode: 13, ctrlKey: true, bubbles: true
          }));
        }
      });
    }

    // 2. Wait for "Message sent" confirmation (up to 10s)
    const confirmed = await waitForGmailSentConfirmation(tab.id, 10000);

    if (confirmed) {
      // Wait 5s for Gmail to finish the SMTP upload BEFORE closing the tab.
      // Closing too early cancels the in-flight send request.
      await new Promise(r => setTimeout(r, 5000));
      try { await chrome.tabs.remove(tab.id); } catch {}
      return {
        tabId: tab.id,
        status: 'sent',
        verified: true,
        to,
        subject,
        attempt: attempt + 1,
      };
    }

    // Not confirmed yet — wait before retry
    if (attempt < MAX_SEND_ATTEMPTS - 1) {
      console.warn(`[OpenClaw] Gmail send attempt ${attempt + 1} not confirmed, retrying...`);
      await new Promise(r => setTimeout(r, 2000));
    }
  }

  // All attempts exhausted without confirmation.
  // DO NOT close the tab — Gmail may still be uploading the message in the background.
  // Closing it now would cancel the in-flight SMTP request.
  return {
    tabId: tab.id,
    status: 'send_unverified',
    verified: false,
    to,
    subject,
    error: 'Message sent confirmation not detected after 3 attempts (tab left open to allow background send)',
  };
}

async function searchMail(query) {
  const url = `https://mail.google.com/mail/u/0/#search/${encodeURIComponent(query)}`;
  const tab = await ensureTab(url, true);
  return { tabId: tab.id, query };
}

async function replyMail(tabId, body) {
  tabId = await resolveTabId(tabId);
  await waitForTabLoad(tabId);
  await chrome.scripting.executeScript({
    target: { tabId },
    func: (txt) => {
      const replyBtn = document.querySelector('[data-tooltip*="Reply"], [aria-label*="Reply"]');
      if (!replyBtn) throw new Error('Reply button not found');
      replyBtn.click();
      setTimeout(() => {
        const box = document.querySelector('[g_editable="true"], [contenteditable="true"]');
        if (box) { box.focus(); box.textContent = txt; }
      }, 1200);
    },
    args: [body],
  });
  return { replied: true };
}

async function getUnreadCount() {
  const tabs = await chrome.tabs.query({ url: '*://mail.google.com/*' });
  if (!tabs.length) {
    const newTab = await ensureTab('https://mail.google.com', true);
    return { tabId: newTab.id, note: 'Gmail opened — check the tab for unread count' };
  }
  const results = await chrome.scripting.executeScript({
    target: { tabId: tabs[0].id },
    func: () => {
      const el = document.querySelector('[title*="Inbox"]');
      return el ? el.title : document.title;
    },
  });
  return { info: results[0]?.result };
}

// ─── Google Calendar recipes ──────────────────────────────────────────────

async function openCalendar() {
  const [existingTab] = await chrome.tabs.query({ url: "*://calendar.google.com/*" });
  if (existingTab) {
    const tab = await chrome.tabs.update(existingTab.id, { active: true });
    return { tabId: tab.id };
  }
  const tab = await ensureTab('https://calendar.google.com', true);
  return { tabId: tab.id };
}

/**
 * Click "Add Google Meet video conferencing" inside the Calendar event form
 * and wait for the Meet link chip to appear. Returns the extracted link.
 *
 * Google Calendar renders the Meet button as:
 *   <button aria-label="Add Google Meet video conferencing">
 * or inside a div with data-id="videochat".
 * After clicking, the Meet link appears as an <a> with meet.google.com URL.
 */
async function addMeetAndExtractLink(tabId, timeoutMs = 15000) {
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (ms) => new Promise((resolve) => {
      // ── Step 1: Click the "Add Google Meet video conferencing" button ──
      const MEET_BTN_SELECTORS = [
        '[data-id="videochat"]',
        '[aria-label*="Google Meet"]',
        '[aria-label*="video conferencing"]',
        '[data-tooltip*="Google Meet"]',
        'button[jsname*="meet"]',
        // Fallback: any visible button containing "Meet" text
      ];

      let clicked = false;
      for (const sel of MEET_BTN_SELECTORS) {
        try {
          const el = document.querySelector(sel);
          if (el && el.offsetParent !== null) {
            el.scrollIntoView({ behavior: 'instant', block: 'center' });
            el.click();
            clicked = true;
            break;
          }
        } catch (_) {}
      }

      // Text fallback
      if (!clicked) {
        const buttons = Array.from(document.querySelectorAll('button, [role="button"]'));
        for (const btn of buttons) {
          const txt = (btn.textContent || btn.getAttribute('aria-label') || '').toLowerCase();
          if (txt.includes('meet') || txt.includes('video conferencing')) {
            if (btn.offsetParent !== null) {
              btn.scrollIntoView({ behavior: 'instant', block: 'center' });
              btn.click();
              clicked = true;
              break;
            }
          }
        }
      }

      if (!clicked) {
        return resolve({ meetClicked: false, meetLink: null });
      }

      // ── Step 2: Wait for Meet link chip to appear ─────────────────────
      function extractMeetLink() {
        const links = Array.from(document.querySelectorAll('a[href*="meet.google.com"]'));
        if (links.length > 0) return links[0].href;
        // Also check text nodes / data attributes
        const chips = Array.from(document.querySelectorAll('[data-id="videochat"] a, [jsname] a'));
        for (const c of chips) {
          if (c.href && c.href.includes('meet.google.com')) return c.href;
        }
        return null;
      }

      const existingLink = extractMeetLink();
      if (existingLink) return resolve({ meetClicked: true, meetLink: existingLink });

      const ob = new MutationObserver(() => {
        const link = extractMeetLink();
        if (link) {
          ob.disconnect();
          clearTimeout(timer);
          resolve({ meetClicked: true, meetLink: link });
        }
      });
      ob.observe(document.documentElement, { childList: true, subtree: true, attributes: true });

      const timer = setTimeout(() => {
        ob.disconnect();
        // Return success for click even if we couldn't extract the link text
        resolve({ meetClicked: true, meetLink: null });
      }, ms);
    }),
    args: [timeoutMs],
  });

  return results[0]?.result || { meetClicked: false, meetLink: null };
}

async function createCalendarEvent({ title, date, time, duration, guests, description, meet, autoSave = true }) {
  const base = 'https://calendar.google.com/calendar/render?action=TEMPLATE';
  const startDT = buildCalDT(date, time);
  const endDT   = buildCalDT(date, time, duration || 60);

  let url = `${base}&text=${encodeURIComponent(title || 'New Event')}`
    + `&dates=${startDT}/${endDT}`;

  if (guests)      url += `&add=${encodeURIComponent(guests)}`;
  if (description) url += `&details=${encodeURIComponent(description)}`;
  // NOTE: We no longer pass video=1 in the URL — it's unreliable.
  // Instead we explicitly click the Meet button after the page loads (below).

  let tab;
  const [existingTab] = await chrome.tabs.query({ url: "*://calendar.google.com/*" });
  if (existingTab) {
    tab = await chrome.tabs.update(existingTab.id, { url, active: true });
    await waitForTabLoad(tab.id, 20000);
  } else {
    tab = await ensureTab(url, true);
  }

  // Give the Calendar SPA extra time to render the event form
  await new Promise(r => setTimeout(r, 2000));

  // ── Add Google Meet video conferencing if requested ────────────────
  let meetLink = null;
  if (meet) {
    const meetResult = await addMeetAndExtractLink(tab.id, 15000);
    meetLink = meetResult.meetLink;

    if (!meetResult.meetClicked) {
      console.warn('[OpenClaw] Could not find "Add Google Meet" button — proceeding without Meet link');
    } else {
      // Give Meet link chip a moment to fully render before saving
      await new Promise(r => setTimeout(r, 1500));
    }
  }

  if (!autoSave) {
    return {
      tabId: tab.id, title, date, time,
      status: 'event_form_opened',
      meetLink,
      verified: false,
    };
  }

  // ── Save the event ─────────────────────────────────────────────────
  const clicked = await retryClickButton(tab.id, [
    '[data-tooltip*="Save"]',
    '[aria-label*="Save"]',
    'button[aria-label="Save"]',
    'text:Save',
  ], 10, 1500);

  if (clicked) {
    // Wait for Calendar to redirect back to the calendar view (confirms save)
    await new Promise(r => setTimeout(r, 3000));

    // Verify: Calendar redirects away from /render after a successful save
    const savedTab = await chrome.tabs.get(tab.id);
    const saved = savedTab && !savedTab.url.includes('/render?action=TEMPLATE');

    return {
      tabId:    tab.id,
      title,
      date,
      time,
      status:   saved ? 'event_saved' : 'save_unverified',
      verified: saved,
      meetLink,
    };
  }

  return {
    tabId:    tab.id,
    title,
    date,
    time,
    status:   'save_button_not_found',
    verified: false,
    meetLink,
  };
}

/** Convert "2026-05-01" + "14:30" + optional offset minutes → YYYYMMDDTHHmmss */
function buildCalDT(dateStr, timeStr, offsetMin = 0) {
  if (!dateStr) {
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    dateStr = tomorrow.toISOString().split('T')[0];
  }
  const [y, mo, d] = dateStr.split('-').map(Number);
  const [h, mi] = (timeStr || '00:00').split(':').map(Number);
  const dt = new Date(y, mo - 1, d, h || 0, (mi || 0) + offsetMin);
  const pad = n => String(n).padStart(2, '0');
  return `${dt.getFullYear()}${pad(dt.getMonth() + 1)}${pad(dt.getDate())}T${pad(dt.getHours())}${pad(dt.getMinutes())}00`;
}

async function getCalendarEvents(date) {
  const tabs = await chrome.tabs.query({ url: '*://calendar.google.com/*' });
  if (!tabs.length) return openCalendar();
  const results = await chrome.scripting.executeScript({
    target: { tabId: tabs[0].id },
    func: () => {
      const events = Array.from(document.querySelectorAll('[data-eventid], [data-eventchip]'));
      return events.slice(0, 20).map(e => e.getAttribute('aria-label') || e.textContent.trim());
    },
  });
  return { events: results[0]?.result || [], date };
}

// ─── Google Meet recipes ──────────────────────────────────────────────────

async function joinMeet(url) {
  if (!url) throw new Error('Meet URL required');
  const tab = await ensureTab(url, true);

  const clicked = await retryClickButton(tab.id, [
    'text:Join now',
    'text:Ask to join',
    'text:Join',
    '[data-tooltip*="Join"]',
    '[aria-label*="Join"]',
  ], 12, 1500);

  return { tabId: tab.id, url, status: clicked ? 'joined' : 'join_button_not_found' };
}

async function scheduleMeet({ title, date, time, duration, guests }) {
  return createCalendarEvent({ title, date, time, duration, guests, meet: true });
}

async function meetControl(action) {
  const tabs = await chrome.tabs.query({ url: '*://meet.google.com/*' });
  if (!tabs.length) throw new Error('No Google Meet tab is open');
  await chrome.scripting.executeScript({
    target: { tabId: tabs[0].id },
    func: (act) => {
      const sel = act === 'mute_mic'    ? '[data-tooltip*="microphone"], [aria-label*="microphone"]'
                : act === 'mute_camera' ? '[data-tooltip*="camera"], [aria-label*="camera"]'
                :                         '[aria-label*="Leave"], [data-tooltip*="Leave"]';
      const btn = document.querySelector(sel);
      if (btn) btn.click();
      else throw new Error(`Meet control button not found for action: ${act}`);
    },
    args: [action],
  });
  return { action, tabId: tabs[0].id };
}

// ─── Google Drive ─────────────────────────────────────────────────────────

async function searchDrive(query) {
  const url = `https://drive.google.com/drive/search?q=${encodeURIComponent(query)}`;
  const tab = await ensureTab(url, true);
  return { tabId: tab.id, query };
}

async function openDriveFile(fileId) {
  const tab = await ensureTab(`https://drive.google.com/file/d/${fileId}/view`, true);
  return { tabId: tab.id, fileId };
}

// ─── Agentic Web Agent — works on ANY website ────────────────────────────

async function extractPageElements(tabId) {
  tabId = await resolveTabId(tabId);
  await waitForTabLoad(tabId, 3000);

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      const MAX_ELEMENTS = 60;
      const MAX_TEXT = 400;
      const truncate = (value, max) => {
        const text = String(value || '').replace(/\s+/g, ' ').trim();
        if (text.length <= max) return text;
        if (max <= 3) return text.slice(0, max);
        return text.slice(0, max - 3).trim() + '...';
      };
      const attr = (name, value) => `[${name}="${String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"]`;
      const isUnique = (selector) => {
        try { return document.querySelectorAll(selector).length === 1; }
        catch (_) { return false; }
      };

      function getSelector(el) {
        if (el.id) {
          const byId = '#' + CSS.escape(el.id);
          if (isUnique(byId)) return byId;
        }
        if (el.name) {
          const byName = `${el.tagName.toLowerCase()}${attr('name', el.name)}`;
          if (isUnique(byName)) return byName;
        }
        if (el.getAttribute('data-testid')) {
          const byTestId = attr('data-testid', el.getAttribute('data-testid'));
          if (isUnique(byTestId)) return byTestId;
        }
        if (el.getAttribute('aria-label')) {
          const byAria = attr('aria-label', el.getAttribute('aria-label'));
          if (isUnique(byAria)) return byAria;
        }

        const parts = [];
        let node = el;
        for (let depth = 0; node && node.nodeType === 1 && depth < 6; depth++, node = node.parentElement) {
          const tag = node.tagName.toLowerCase();
          if (node.id) {
            const idSel = '#' + CSS.escape(node.id);
            if (isUnique(idSel)) {
              parts.unshift(idSel);
              break;
            }
          }
          const parent = node.parentElement;
          if (!parent) {
            parts.unshift(tag);
            break;
          }
          const siblings = Array.from(parent.children).filter(c => c.tagName === node.tagName);
          const idx = siblings.indexOf(node) + 1;
          parts.unshift(`${tag}:nth-of-type(${idx})`);
        }
        return parts.join(' > ');
      }

      function getLabel(el) {
        if (el.id) {
          const label = document.querySelector(`label[for="${el.id}"]`);
          if (label) return label.textContent.trim();
        }
        const parentLabel = el.closest('label');
        if (parentLabel) return parentLabel.textContent.trim();
        if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
        if (el.placeholder) return el.placeholder;
        const prev = el.previousElementSibling;
        if (prev && (prev.tagName === 'LABEL' || prev.tagName === 'SPAN'))
          return prev.textContent.trim();
        return '';
      }

      function isVisible(el) {
        const s = window.getComputedStyle(el);
        const r = el.getBoundingClientRect();
        return s.display !== 'none' && s.visibility !== 'hidden'
          && s.opacity !== '0' && r.width > 0 && r.height > 0;
      }

      const elements = [];
      const seen = new Set();

      function addElement(info) {
        if (!info.selector || seen.has(info.selector) || elements.length >= MAX_ELEMENTS) return;
        seen.add(info.selector);
        elements.push(info);
      }

      document.querySelectorAll('input, textarea, select, [contenteditable="true"]').forEach(el => {
        if (!isVisible(el) || elements.length >= MAX_ELEMENTS) return;
        const type = el.type || el.tagName.toLowerCase();
        if (type === 'hidden') return;
        const info = {
          tag: el.tagName.toLowerCase(),
          type: el.isContentEditable ? 'contenteditable' : type,
          selector: getSelector(el),
          label: truncate(getLabel(el), 80),
          required: el.required || false,
        };
        if (el.tagName === 'SELECT') {
          info.options = Array.from(el.options).slice(0, 8).map(o => ({
            value: truncate(o.value, 40),
            text: truncate(o.textContent, 60),
            selected: o.selected,
          }));
        }
        if (el.value && type !== 'password') info.value = truncate(el.value, 60);
        else if (el.textContent && el.isContentEditable) info.value = truncate(el.textContent, 60);
        if (el.placeholder) info.placeholder = truncate(el.placeholder, 80);
        else if (el.getAttribute('data-placeholder'))
          info.placeholder = truncate(el.getAttribute('data-placeholder'), 80);
        addElement(info);
      });

      document.querySelectorAll(
        'ytd-video-renderer a#video-title, ytd-video-renderer h3 a, a#video-title[href*="/watch"], a[href^="/watch"]'
      ).forEach(el => {
        if (!isVisible(el) || elements.length >= MAX_ELEMENTS) return;
        const href = el.getAttribute('href') || '';
        const label = truncate(el.textContent || el.getAttribute('aria-label') || el.title || '', 80);
        if (!label) return;
        addElement({
          tag: 'a',
          selector: getSelector(el),
          label,
          href: truncate(el.href || href, 120),
        });
      });

      document.querySelectorAll(
        'button, input[type="submit"], input[type="button"], [role="button"], a.btn, a.button'
      ).forEach(el => {
        if (!isVisible(el) || elements.length >= MAX_ELEMENTS) return;
        addElement({
          tag: 'button',
          type: el.type || 'button',
          selector: getSelector(el),
          label: truncate(el.textContent || el.value || el.getAttribute('aria-label') || '', 80),
        });
      });

      document.querySelectorAll('a[href]').forEach(el => {
        if (!isVisible(el) || elements.length >= MAX_ELEMENTS) return;
        const href = el.getAttribute('href') || '';
        if (href.startsWith('javascript') || href === '#') return;
        const label = truncate(el.textContent || el.getAttribute('aria-label') || el.title || '', 80);
        if (!label) return;
        if (!el.matches('.btn, .button, [role="button"]')) {
          addElement({
            tag: 'a',
            selector: getSelector(el),
            label,
            href: truncate(el.href || href, 120),
          });
        }
      });

      return {
        elements,
        pageText: truncate(document.body?.innerText || '', MAX_TEXT),
      };
    },
  });

  let tabInfo = {};
  try {
    const tab = await chrome.tabs.get(tabId);
    tabInfo = { url: tab.url || '', title: tab.title || '' };
  } catch (_) {}

  const payload = results[0]?.result || { elements: [], pageText: '' };
  return { ...payload, ...tabInfo };
}

async function performPageActions(tabId, actions) {
  tabId = await resolveTabId(tabId);
  if (!actions || !actions.length) return { performed: 0, total: 0, results: [] };

  await waitForTabLoad(tabId);

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: async (actionList) => {
      function waitForEl(selector, timeoutMs = 5000) {
        return new Promise((resolve) => {
          const existing = document.querySelector(selector);
          if (existing) return resolve(existing);
          const ob = new MutationObserver(() => {
            const el = document.querySelector(selector);
            if (el) { ob.disconnect(); resolve(el); }
          });
          ob.observe(document.documentElement, { childList: true, subtree: true });
          setTimeout(() => { ob.disconnect(); resolve(null); }, timeoutMs);
        });
      }

      const results = [];

      for (const act of actionList) {
        try {
          let el = null;
          let sel = (act.selector || '').trim();
          
          if (act.action === 'extract_text') {
            // No selector needed, el stays null
          } else if (sel === 'body' || sel === 'document.body' || sel === 'html') {
            el = document.body || document.documentElement;
            act.selector = 'body'; // normalise for the results array
          } else {
            el = await waitForEl(sel, act.timeout || 5000);
            if (!el) {
              results.push({ action: act.action, selector: act.selector, ok: false, error: 'Element not found (timeout)' });
              continue;
            }
          }

          if (el) {
            el.scrollIntoView({ behavior: 'instant', block: 'center' });
          }

          switch (act.action) {
            case 'fill': {
              el.focus();
              el.value = '';
              el.dispatchEvent(new Event('input', { bubbles: true }));
              el.value = act.value || '';
              el.dispatchEvent(new Event('input', { bubbles: true }));
              el.dispatchEvent(new Event('change', { bubbles: true }));
              el.dispatchEvent(new Event('blur', { bubbles: true }));
              results.push({ action: 'fill', selector: act.selector, ok: true, value: act.value });
              break;
            }
            case 'fill_react': {
              el.focus();
              try {
                const proto = el.tagName === 'TEXTAREA'
                  ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
                const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                if (nativeSetter) nativeSetter.call(el, act.value || '');
                else el.value = act.value || '';
              } catch (_) { el.value = act.value || ''; }
              el.dispatchEvent(new Event('input', { bubbles: true }));
              el.dispatchEvent(new Event('change', { bubbles: true }));
              if (el.isContentEditable) {
                el.textContent = act.value || '';
                el.dispatchEvent(new Event('input', { bubbles: true }));
              }
              results.push({ action: 'fill_react', selector: act.selector, ok: true, value: act.value });
              break;
            }
            case 'enter': {
              el.focus();
              const enterEvent = (type) => new KeyboardEvent(type, {
                key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
                bubbles: true, cancelable: true,
              });
              ['keydown', 'keypress', 'keyup'].forEach(type => {
                el.dispatchEvent(enterEvent(type));
              });
              ['keydown', 'keypress', 'keyup'].forEach(type => {
                document.body.dispatchEvent(enterEvent(type));
              });
              const sendBtn = (
                document.querySelector('[data-testid="send-button"]') ||
                document.querySelector('button[aria-label*="Send"]') ||
                document.querySelector('button[type="submit"]') ||
                document.querySelector('#composer-submit-button') ||
                (() => {
                  let p = el.parentElement;
                  for (let i = 0; i < 5 && p; i++, p = p.parentElement) {
                    const btn = p.querySelector('button');
                    if (btn && btn.offsetParent !== null) return btn;
                  }
                  return null;
                })()
              );
              if (sendBtn && sendBtn.offsetParent !== null) sendBtn.click();
              results.push({ action: 'enter', selector: act.selector, ok: true });
              break;
            }
            case 'click': {
              el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
              el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
              el.click();
              results.push({ action: 'click', selector: act.selector, ok: true, text: el.textContent?.trim()?.slice(0, 50) });
              break;
            }
            case 'select': {
              el.value = act.value || '';
              el.dispatchEvent(new Event('change', { bubbles: true }));
              results.push({ action: 'select', selector: act.selector, ok: true, value: act.value });
              break;
            }
            case 'check': {
              const shouldCheck = act.value === true || act.value === 'true';
              if (el.checked !== shouldCheck) el.click();
              results.push({ action: 'check', selector: act.selector, ok: true, checked: el.checked });
              break;
            }
            case 'scroll': {
              if (act.selector === 'body' || act.selector === 'window') {
                window.scrollBy({ top: window.innerHeight * 0.8, behavior: 'smooth' });
              } else {
                el.scrollIntoView({ behavior: 'smooth', block: 'center' });
              }
              results.push({ action: 'scroll', selector: act.selector, ok: true });
              break;
            }
            case 'extract_text': {
              // Special no-selector action: grab full page text for downstream steps
              const pageText = document.body.innerText || document.body.textContent || '';
              results.push({ action: 'extract_text', selector: '', ok: true, text: pageText });
              break;
            }
            default:
              results.push({ action: act.action, selector: act.selector, ok: false, error: `Unknown action: ${act.action}` });
          }
        } catch (err) {
          results.push({ action: act.action, selector: act.selector, ok: false, error: err.message });
        }
      }

      return {
        performed: results.filter(r => r.ok).length,
        total: actionList.length,
        results,
      };
    },
    args: [actions],
  });

  return results[0]?.result || { performed: 0, total: actions.length, results: [] };
}

// ─── Bootstrap ───────────────────────────────────────────────────────────

connectWebSocket();

chrome.runtime.onInstalled.addListener(() => {
  console.log('[OpenClaw] Extension v3.1 installed');
  chrome.storage.local.set({ connectionStatus: 'disconnected', recentCommands: [] });
  connectWebSocket();
});

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'reconnect') {
    if (ws) { try { ws.close(); } catch {} }
    ws = null;
    connectWebSocket();
    sendResponse({ ok: true });
  } else if (msg.action === 'PING') {
    sendResponse({ pong: true });
  }
  return true;
});

chrome.alarms.create('keepAlive', { periodInMinutes: 0.4 });
chrome.alarms.onAlarm.addListener(() => {
  if (!ws || ws.readyState !== WebSocket.OPEN) connectWebSocket();
});

// ─── Command logging helper ───────────────────────────────────────────────

function logCommand(command) {
  chrome.storage.local.get(['recentCommands'], (data) => {
    const cmds = data.recentCommands || [];
    cmds.unshift(`[${new Date().toLocaleTimeString()}] ${command}`);
    if (cmds.length > 10) cmds.length = 10;
    chrome.storage.local.set({ recentCommands: cmds });
  });
}