/**
 * OpenClaw Chrome Extension — Background Service Worker v3
 * ==========================================================
 * Architecture: pre-built "recipes" per domain.
 * The Python agent sends ONE high-level command (e.g. "playYouTube").
 * All DOM work happens here — zero extra LLM calls per action.
 *
 * Fixes in v3:
 *   - Unified getActiveTab() that works in MV3 service workers (no currentWindow assumption)
 *   - waitForTabLoad() before any DOM injection — eliminates "Cannot access tab" races
 *   - retryClickButton text: prefix logic fixed
 *   - performPageActions has per-action wait-for-element with configurable timeout
 *   - searchYouTube always returns a consistent shape
 *   - ensureTab returns only after tab URL is committed (onUpdated status=complete)
 *   - All tabId params default through getActiveTab() centrally
 *
 * Commands supported:
 *   Core         : getTabs, switchTab, closeTab, navigate, injectScript, getDom,
 *                  clickElement, fillInput, screenshot, waitForSelector
 *   YouTube      : playYouTube, pauseYouTube, searchYouTube, setVolume, seekTo,
 *                  getVideoInfo, nextVideo
 *   Gmail        : composeMail, sendMail, searchMail, replyMail, getUnread
 *   Google Cal   : createEvent, getEvents, deleteEvent, openCalendar
 *   Google Meet  : joinMeet, scheduleMeet, muteMic, muteCamera, leaveMeet
 *   Google Drive : searchDrive, openFile
 *   General DOM  : smartClick, smartFill, waitAndClick, extractStructured
 *   Agentic      : extractPage, performActions
 */

const WS_URL = 'ws://127.0.0.1:8765';
let ws = null;
let reconnectDelay = 1000;
const MAX_RECONNECT_DELAY = 15000;

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
        const result = await handleCommand(data);
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ id: data.id, success: true, ...result }));
        }
        reconnectDelay = 1000;
      } catch (err) {
        console.error('[OpenClaw] Command error:', err);
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ id: data.id, success: false, error: err.message }));
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

/**
 * Reliably get the active tab in MV3 service workers.
 *
 * chrome.tabs.query({ active: true, currentWindow: true }) is BROKEN in
 * service workers because there is no "current window" concept — the worker
 * runs headlessly. We must query all windows and pick the focused one.
 */
async function getActiveTab() {
  // Strategy 1: focused window's active tab (works when browser is in foreground)
  const [focusedTab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (focusedTab) return focusedTab;

  // Strategy 2: any active tab across all windows
  const activeTabs = await chrome.tabs.query({ active: true });
  if (activeTabs.length > 0) return activeTabs[0];

  // Strategy 3: the most recently accessed tab at all
  const allTabs = await chrome.tabs.query({});
  if (allTabs.length > 0) {
    // Sort by lastAccessed descending (most recent first)
    allTabs.sort((a, b) => (b.lastAccessed || 0) - (a.lastAccessed || 0));
    return allTabs[0];
  }

  throw new Error('No tabs found — browser has no open tabs');
}

/**
 * Resolve a tabId param: use it if provided, otherwise fall back to active tab.
 */
async function resolveTabId(tabId) {
  if (tabId) return tabId;
  const tab = await getActiveTab();
  return tab.id;
}

/**
 * Wait for a tab to finish loading before injecting scripts.
 * MV3 scripting.executeScript on a still-loading tab throws "Cannot access".
 */
function waitForTabLoad(tabId, timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    chrome.tabs.get(tabId, (tab) => {
      if (chrome.runtime.lastError) return reject(new Error(chrome.runtime.lastError.message));
      if (tab.status === 'complete') return resolve();

      const timer = setTimeout(() => {
        chrome.tabs.onUpdated.removeListener(listener);
        resolve(); // Timeout — attempt anyway
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
  });
}

/**
 * Open a new tab and wait until it is fully loaded before returning.
 * Eliminates the race where we inject scripts before DOMContentLoaded.
 */
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
    // Re-fetch tab to get final state after redirects
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

    // ── Agentic Web Agent (works on ANY website) ──────────────────────
    case 'extractPage':       return extractPageElements(params.tabId);
    case 'performActions':    return performPageActions(params.tabId, params.actions);

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
  await waitForTabLoad(tabId);
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
  // captureVisibleTab needs the focused window — find it
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
        // Use native setter so React/Vue/Angular watchers fire
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

/**
 * Retry clicking a button matched by CSS selector OR "text:<string>" pseudo-selector.
 * 
 * FIX: The original code tried to use text: selectors inside document.querySelector()
 * which is invalid CSS — this is now handled separately via textContent matching.
 */
async function retryClickButton(tabId, selectors, maxRetries = 8, intervalMs = 1500) {
  // Split selectors into CSS selectors and text matchers
  const cssSelectors = selectors.filter(s => !s.startsWith('text:'));
  const textMatchers  = selectors
    .filter(s => s.startsWith('text:'))
    .map(s => s.slice(5).toLowerCase());

  for (let attempt = 0; attempt < maxRetries; attempt++) {
    await new Promise(r => setTimeout(r, intervalMs));

    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: (cssSels, textStrs) => {
        // 1. Try each CSS selector
        for (const sel of cssSels) {
          try {
            const el = document.querySelector(sel);
            if (el && el.offsetParent !== null) {
              el.scrollIntoView({ behavior: 'instant', block: 'center' });
              el.click();
              return { clicked: sel, text: el.textContent?.trim() };
            }
          } catch (_) { /* invalid selector — skip */ }
        }

        // 2. Try matching by visible button/link text
        const clickables = Array.from(document.querySelectorAll(
          'button, [role="button"], input[type="submit"], a'
        ));
        for (const el of clickables) {
          if (el.offsetParent === null) continue; // hidden
          const elText = (el.textContent?.trim() || el.value || '').toLowerCase();
          for (const matcher of textStrs) {
            if (elText.includes(matcher)) {
              el.scrollIntoView({ behavior: 'instant', block: 'center' });
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
  const tab = await ensureTab(url, true); // wait for page load

  if (!autoplay) return { tabId: tab.id, searched: query, playing: false };

  const idx = videoIndex || 1;
  let clickResult = null;

  // Retry clicking the Nth result (results render after initial load)
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

async function composeMail(to, subject, body, send = false) {
  const gmailUrl = `https://mail.google.com/mail/?view=cm&fs=1`
    + `&to=${encodeURIComponent(to || '')}`
    + `&su=${encodeURIComponent(subject || '')}`
    + `&body=${encodeURIComponent(body || '')}`;

  const tab = await ensureTab(gmailUrl, true);
  if (!send) return { tabId: tab.id, status: 'draft_opened' };

  const clicked = await retryClickButton(tab.id, [
    '[data-tooltip*="Send"]',
    '[aria-label*="Send"]',
    'div[aria-label*="Send"]',
    '.T-I.J-J5-Ji[role="button"]',
    'text:Send',
  ], 10, 1500);

  if (clicked) {
    await new Promise(r => setTimeout(r, 2000));
    try { await chrome.tabs.remove(tab.id); } catch {}
    return { tabId: tab.id, status: 'sent', to, subject };
  }
  return { tabId: tab.id, status: 'send_button_not_found', to, subject };
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
  const tab = await ensureTab('https://calendar.google.com', true);
  return { tabId: tab.id };
}

async function createCalendarEvent({ title, date, time, duration, guests, description, meet, autoSave = true }) {
  const base = 'https://calendar.google.com/calendar/render?action=TEMPLATE';
  const startDT = buildCalDT(date, time);
  const endDT   = buildCalDT(date, time, duration || 60);

  let url = `${base}&text=${encodeURIComponent(title || 'New Event')}`
    + `&dates=${startDT}/${endDT}`;

  if (guests)      url += `&add=${encodeURIComponent(guests)}`;
  if (description) url += `&details=${encodeURIComponent(description)}`;
  if (meet)        url += `&crm=AVAILABLE&ctz=Asia%2FKolkata&video=1`;

  const tab = await ensureTab(url, true);

  if (!autoSave) return { tabId: tab.id, title, date, time, status: 'event_form_opened' };

  const clicked = await retryClickButton(tab.id, [
    '[data-tooltip*="Save"]',
    '[aria-label*="Save"]',
    'button[aria-label="Save"]',
    'text:Save',
  ], 10, 1500);

  if (clicked) {
    await new Promise(r => setTimeout(r, 2000));
    return { tabId: tab.id, title, date, time, status: 'event_saved' };
  }
  return { tabId: tab.id, title, date, time, status: 'save_button_not_found' };
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
  tabId = await resolveTabId(tabId); // ← FIX: centralised, no more inline query
  await waitForTabLoad(tabId);

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      function getSelector(el) {
        if (el.id) return '#' + CSS.escape(el.id);
        if (el.name) return `${el.tagName.toLowerCase()}[name="${el.name}"]`;
        if (el.getAttribute('data-testid'))
          return `[data-testid="${el.getAttribute('data-testid')}"]`;
        if (el.getAttribute('aria-label'))
          return `[aria-label="${el.getAttribute('aria-label')}"]`;
        const tag = el.tagName.toLowerCase();
        const parent = el.parentElement;
        if (!parent) return tag;
        const siblings = Array.from(parent.children).filter(c => c.tagName === el.tagName);
        const idx = siblings.indexOf(el) + 1;
        const parentSel = parent.id ? '#' + CSS.escape(parent.id) : '';
        return `${parentSel} > ${tag}:nth-of-type(${idx})`;
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
        return s.display !== 'none' && s.visibility !== 'hidden'
          && s.opacity !== '0' && el.offsetParent !== null;
      }

      const elements = [];

      document.querySelectorAll('input, textarea, select, [contenteditable="true"]').forEach(el => {
        if (!isVisible(el)) return;
        const type = el.type || el.tagName.toLowerCase();
        if (type === 'hidden') return;
        const info = {
          tag: el.tagName.toLowerCase(),
          type: el.isContentEditable ? 'contenteditable' : type,
          selector: getSelector(el),
          label: getLabel(el),
          required: el.required || false,
        };
        if (el.tagName === 'SELECT') {
          info.options = Array.from(el.options).map(o => ({
            value: o.value, text: o.textContent.trim(), selected: o.selected,
          }));
        }
        if (el.value) info.value = el.value;
        else if (el.textContent && el.isContentEditable) info.value = el.textContent;
        if (el.placeholder) info.placeholder = el.placeholder;
        else if (el.getAttribute('data-placeholder'))
          info.placeholder = el.getAttribute('data-placeholder');
        elements.push(info);
      });

      document.querySelectorAll(
        'button, input[type="submit"], input[type="button"], [role="button"], a.btn, a.button'
      ).forEach(el => {
        if (!isVisible(el)) return;
        elements.push({
          tag: 'button',
          type: el.type || 'button',
          selector: getSelector(el),
          label: el.textContent?.trim() || el.value || el.getAttribute('aria-label') || '',
        });
      });

      document.querySelectorAll('a[href]').forEach(el => {
        if (!isVisible(el)) return;
        const href = el.getAttribute('href');
        if (href.startsWith('javascript') || href === '#') return;
        const label = el.textContent?.trim();
        if (!label) return;
        if (!el.matches('.btn, .button, [role="button"]')) {
          elements.push({
            tag: 'a',
            selector: getSelector(el),
            label: label.slice(0, 50),
            href: href.slice(0, 100),
          });
        }
      });

      return elements;
    },
  });

  // Also return the tab's current URL + title so the web-agent can detect
  // done-states (e.g. YouTube /watch) without an extra round-trip.
  let tabInfo = {};
  try {
    const tab = await chrome.tabs.get(tabId);
    tabInfo = { url: tab.url || '', title: tab.title || '' };
  } catch (_) {}

  return { elements: results[0]?.result || [], ...tabInfo };
}

/**
 * Perform a batch of DOM actions on a page.
 * Each action: { action, selector, value?, timeout? }
 *
 * FIX: Each action now waits for the element to exist before acting,
 * so single-page-app transitions between actions don't cause failures.
 */
async function performPageActions(tabId, actions) {
  tabId = await resolveTabId(tabId); // ← FIX: centralised
  if (!actions || !actions.length) return { performed: 0, total: 0, results: [] };

  await waitForTabLoad(tabId);

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: async (actionList) => {
      /**
       * Wait for a selector to appear in the DOM (for SPA navigations between actions).
       */
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
          // Wait for element (handles SPA route changes between sequential actions)
          const el = await waitForEl(act.selector, act.timeout || 5000);
          if (!el) {
            results.push({ action: act.action, selector: act.selector, ok: false, error: 'Element not found (timeout)' });
            continue;
          }

          el.scrollIntoView({ behavior: 'instant', block: 'center' });

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
              // Dispatch on the element itself
              const enterEvent = (type) => new KeyboardEvent(type, {
                key: 'Enter', code: 'Enter', keyCode: 13, which: 13,
                bubbles: true, cancelable: true,
              });
              ['keydown', 'keypress', 'keyup'].forEach(type => {
                el.dispatchEvent(enterEvent(type));
              });
              // ChatGPT / React SPAs intercept Enter at document level
              ['keydown', 'keypress', 'keyup'].forEach(type => {
                document.body.dispatchEvent(enterEvent(type));
              });
              // Last resort: click the nearest visible send/submit button
              const sendBtn = (
                document.querySelector('[data-testid="send-button"]') ||
                document.querySelector('button[aria-label*="Send"]') ||
                document.querySelector('button[type="submit"]') ||
                document.querySelector('#composer-submit-button') ||
                (() => {
                  // Walk up and find a sibling/nearby button
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
  console.log('[OpenClaw] Extension v3 installed');
  chrome.storage.local.set({ connectionStatus: 'disconnected', recentCommands: [] });
  connectWebSocket();
});

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'reconnect') {
    if (ws) { try { ws.close(); } catch {} }
    ws = null;
    connectWebSocket();
    sendResponse({ ok: true });
  }
  return true;
});

// Keep service worker alive (MV3 service workers terminate after 30s idle)
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