/**
 * OpenClaw Chrome Extension — Background Service Worker v2
 * ==========================================================
 * Architecture: pre-built "recipes" per domain.
 * The Python agent sends ONE high-level command (e.g. "playYouTube").
 * All DOM work happens here — zero extra LLM calls per action.
 *
 * Commands supported:
 *   Core         : getTabs, switchTab, closeTab, navigate, injectScript, getDom, clickElement, fillInput, screenshot, waitForSelector
 *   YouTube      : playYouTube, pauseYouTube, searchYouTube, setVolume, seekTo, getVideoInfo
 *   Gmail        : composeMail, sendMail, searchMail, replyMail, getUnread
 *   Google Cal   : createEvent, getEvents, deleteEvent, openCalendar
 *   Google Meet  : joinMeet, scheduleMeet, muteMic, muteCamera, leaveMeet
 *   Google Drive : searchDrive, openFile
 *   General DOM  : smartClick, smartFill, waitAndClick, extractStructured
 */

const WS_URL = 'ws://127.0.0.1:8765';
let ws = null;
let reconnectDelay = 5000;
const MAX_RECONNECT_DELAY = 30000;

// ─── WebSocket connection ─────────────────────────────────────────────────

function connectWebSocket() {
  // Clean up old connection
  if (ws) {
    try { ws.close(); } catch {}
    ws = null;
  }

  try {
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      console.log('[OpenClaw] ✓ Connected to IntentOS agent');
      chrome.storage.local.set({ connectionStatus: 'connected' });
      reconnectDelay = 5000; // Reset backoff on successful connect
    };

    ws.onmessage = async (event) => {
      let data;
      try { data = JSON.parse(event.data); } catch { return; }
      try {
        const result = await handleCommand(data);
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ id: data.id, success: true, ...result }));
        }
      } catch (err) {
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
      // Exponential backoff: 5s → 10s → 20s → 30s max
      reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY);
    };

    ws.onerror = () => {
      // onerror always fires before onclose — let onclose handle reconnect
      console.log('[OpenClaw] WebSocket error (onclose will handle reconnect)');
    };
  } catch (e) {
    console.log('[OpenClaw] Connection failed:', e);
    setTimeout(connectWebSocket, reconnectDelay);
    reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY);
  }
}


// ─── Main dispatcher ──────────────────────────────────────────────────────

async function handleCommand({ command, params = {} }) {
  logCommand(command);
  switch (command) {

    // ── Core ────────────────────────────────────────────────────────────
    case 'getTabs':         return getTabs();
    case 'switchTab':       return switchTab(params.tabId);
    case 'closeTab':        return closeTab(params.tabId);
    case 'navigate':        return navigateTab(params.tabId, params.url, params.newTab);
    case 'injectScript':    return injectScript(params.tabId, params.code);
    case 'getDom':          return getDomContent(params.tabId, params.selector);
    case 'clickElement':    return clickElement(params.tabId, params.selector);
    case 'fillInput':       return fillInput(params.tabId, params.selector, params.value);
    case 'screenshot':      return captureTab();
    case 'waitForSelector': return waitForSelector(params.tabId, params.selector, params.timeout);
    case 'smartClick':      return smartClick(params.tabId, params.text, params.role);
    case 'smartFill':       return smartFill(params.tabId, params.label, params.value);
    case 'extractStructured': return extractStructured(params.tabId, params.schema);

    // ── YouTube ─────────────────────────────────────────────────────────
    case 'searchYouTube':   return searchYouTube(params.query, params.autoplay);
    case 'playYouTube':     return youtubeControl('play');
    case 'pauseYouTube':    return youtubeControl('pause');
    case 'setVolume':       return youtubeSetVolume(params.level);
    case 'seekTo':          return youtubeSeek(params.seconds);
    case 'getVideoInfo':    return youtubeGetInfo();
    case 'nextVideo':       return youtubeControl('next');

    // ── Gmail ────────────────────────────────────────────────────────────
    case 'composeMail':     return composeMail(params.to, params.subject, params.body, params.send);
    case 'sendMail':        return composeMail(params.to, params.subject, params.body, true);
    case 'searchMail':      return searchMail(params.query);
    case 'replyMail':       return replyMail(params.tabId, params.body);
    case 'getUnread':       return getUnreadCount();

    // ── Google Calendar ──────────────────────────────────────────────────
    case 'openCalendar':    return openCalendar();
    case 'createEvent':     return createCalendarEvent(params);
    case 'getEvents':       return getCalendarEvents(params.date);

    // ── Google Meet ──────────────────────────────────────────────────────
    case 'joinMeet':        return joinMeet(params.url);
    case 'scheduleMeet':    return scheduleMeet(params);
    case 'muteMic':         return meetControl('mute_mic');
    case 'muteCamera':      return meetControl('mute_camera');
    case 'leaveMeet':       return meetControl('leave');

    // ── Google Drive ─────────────────────────────────────────────────────
    case 'searchDrive':     return searchDrive(params.query);
    case 'openDriveFile':   return openDriveFile(params.fileId);

    // ── Agentic Web Agent (works on ANY website) ──────────────────────
    case 'extractPage':     return extractPageElements(params.tabId);
    case 'performActions':  return performPageActions(params.tabId, params.actions);

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
    const tab = await chrome.tabs.create({ url });
    return { tabId: tab.id };
  }
  if (!tabId) {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab) tabId = tab.id;
    else {
      const newT = await chrome.tabs.create({ url });
      return { tabId: newT.id };
    }
  }
  await chrome.tabs.update(tabId, { url });
  return { tabId };
}

async function injectScript(tabId, code) {
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: new Function(`return (${code})()`),
  });
  return { result: results[0]?.result };
}

async function getDomContent(tabId, selector = 'body') {
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
  await chrome.scripting.executeScript({
    target: { tabId },
    func: (sel) => {
      const el = document.querySelector(sel);
      if (!el) throw new Error(`Not found: ${sel}`);
      el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
      el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
      el.click();
    },
    args: [selector],
  });
  return { clicked: selector };
}

async function fillInput(tabId, selector, value) {
  await chrome.scripting.executeScript({
    target: { tabId },
    func: (sel, val) => {
      const el = document.querySelector(sel);
      if (!el) throw new Error(`Not found: ${sel}`);
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
  const dataUrl = await chrome.tabs.captureVisibleTab(null, { format: 'jpeg', quality: 80 });
  return { screenshot: dataUrl };
}

async function waitForSelector(tabId, selector, timeout = 10000) {
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (sel, ms) => new Promise((resolve, reject) => {
      if (document.querySelector(sel)) return resolve(true);
      const ob = new MutationObserver(() => {
        if (document.querySelector(sel)) { ob.disconnect(); resolve(true); }
      });
      ob.observe(document.body, { childList: true, subtree: true });
      setTimeout(() => { ob.disconnect(); reject(new Error(`Timeout waiting for ${sel}`)); }, ms);
    }),
    args: [selector, timeout],
  });
  return { found: results[0]?.result };
}

/** Click by visible text and optional ARIA role — no brittle CSS selectors needed */
async function smartClick(tabId, text, role = null) {
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (txt, rl) => {
      const lower = txt.toLowerCase();
      const all = Array.from(document.querySelectorAll(
        rl ? `[role="${rl}"]` : 'button, a, [role="button"], [role="link"], input[type="submit"]'
      ));
      const el = all.find(e => e.textContent.trim().toLowerCase().includes(lower));
      if (!el) throw new Error(`No element with text "${txt}"`);
      el.click();
      return el.textContent.trim();
    },
    args: [text, role],
  });
  return { clicked: results[0]?.result };
}

/** Fill input by its associated label text */
async function smartFill(tabId, label, value) {
  await chrome.scripting.executeScript({
    target: { tabId },
    func: (lbl, val) => {
      const lower = lbl.toLowerCase();
      // Try aria-label, placeholder, associated <label>
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
        el.value = val;
      }
      ['input', 'change'].forEach(ev => el.dispatchEvent(new Event(ev, { bubbles: true })));
    },
    args: [label, value],
  });
  return { filled: label };
}

/** Extract structured data from the page without sending it to the LLM */
async function extractStructured(tabId, schema = 'text') {
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
      // Default: page text
      return document.body.innerText.substring(0, 5000);
    },
    args: [schema],
  });
  return { data: results[0]?.result };
}

// ─── YouTube recipes ──────────────────────────────────────────────────────

async function searchYouTube(query, autoplay = true, videoIndex = 1) {
  const url = `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}`;
  const tab = await chrome.tabs.create({ url });
  if (!autoplay) return { tabId: tab.id, searched: query };

  // Wait for search results to render (retry up to 4x with 1.5s gaps)
  let clicked = false;
  for (let attempt = 0; attempt < 4; attempt++) {
    await new Promise(r => setTimeout(r, attempt === 0 ? 3000 : 1500));
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: (idx) => {
        // YouTube search result selectors (in priority order)
        const selectors = [
          'ytd-video-renderer a#video-title',      // standard search result
          'ytd-video-renderer h3 a',               // fallback
          '#contents ytd-video-renderer a[href^="/watch"]', // href-based
        ];
        let videos = [];
        for (const sel of selectors) {
          videos = Array.from(document.querySelectorAll(sel))
            .filter(el => el.href && el.href.includes('/watch')); // skip ads/playlists
          if (videos.length >= idx) break;
        }
        const target = videos[idx - 1]; // idx is 1-based
        if (!target) return { found: false, count: videos.length };
        target.click();
        return { found: true, title: target.textContent.trim(), index: idx };
      },
      args: [videoIndex],
    });
    const res = results[0]?.result;
    if (res?.found) {
      clicked = true;
      return { tabId: tab.id, playing: query, videoIndex, title: res.title };
    }
  }
  return { tabId: tab.id, searched: query, warning: `Video ${videoIndex} not found after retries` };
}

async function youtubeControl(action) {
  const [tab] = await chrome.tabs.query({ url: '*://www.youtube.com/*' });
  if (!tab) throw new Error('No YouTube tab open');
  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: (act) => {
      const video = document.querySelector('video');
      if (!video) throw new Error('No video element');
      if (act === 'play')  video.play();
      if (act === 'pause') video.pause();
      if (act === 'next') {
        const btn = document.querySelector('.ytp-next-button');
        if (btn) btn.click();
      }
    },
    args: [action],
  });
  return { action, tabId: tab.id };
}

async function youtubeSetVolume(level = 50) {
  const [tab] = await chrome.tabs.query({ url: '*://www.youtube.com/*' });
  if (!tab) throw new Error('No YouTube tab open');
  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: (vol) => { document.querySelector('video').volume = vol / 100; },
    args: [level],
  });
  return { volume: level };
}

async function youtubeSeek(seconds = 0) {
  const [tab] = await chrome.tabs.query({ url: '*://www.youtube.com/*' });
  if (!tab) throw new Error('No YouTube tab open');
  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: (s) => { document.querySelector('video').currentTime = s; },
    args: [seconds],
  });
  return { seeked: seconds };
}

async function youtubeGetInfo() {
  const [tab] = await chrome.tabs.query({ url: '*://www.youtube.com/watch*' });
  if (!tab) return { error: 'No YouTube video open' };
  const results = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => {
      const v = document.querySelector('video');
      return {
        title: document.title,
        currentTime: v?.currentTime,
        duration: v?.duration,
        paused: v?.paused,
        volume: v?.volume,
      };
    },
  });
  return results[0]?.result || {};
}

// ─── Gmail recipes ────────────────────────────────────────────────────────

/**
 * Retry clicking a button that matches any of the given selectors.
 * Google apps (Gmail, Calendar, Meet) load DOM asynchronously,
 * so the button might not exist for 3-8 seconds after page load.
 * This retries up to `maxRetries` times with `intervalMs` gap.
 */
async function retryClickButton(tabId, selectors, maxRetries = 8, intervalMs = 1500) {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    await new Promise(r => setTimeout(r, intervalMs));
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: (sels) => {
        for (const sel of sels) {
          // CSS selector
          const el = document.querySelector(sel);
          if (el && el.offsetParent !== null) {
            el.click();
            return { clicked: sel, text: el.textContent?.trim() };
          }
        }
        // Also try finding by visible text (for buttons with dynamic selectors)
        const buttons = Array.from(document.querySelectorAll('button, [role="button"]'));
        for (const btn of buttons) {
          const txt = btn.textContent?.trim().toLowerCase() || '';
          for (const sel of sels) {
            if (sel.startsWith('text:') && txt.includes(sel.slice(5).toLowerCase())) {
              btn.click();
              return { clicked: 'text:' + txt };
            }
          }
        }
        return null;
      },
      args: [selectors],
    });
    const r = results[0]?.result;
    if (r) return r;
  }
  return null;
}

async function composeMail(to, subject, body, send = false) {
  const gmailUrl = `https://mail.google.com/mail/?view=cm&to=${encodeURIComponent(to)}&su=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  const tab = await chrome.tabs.create({ url: gmailUrl });

  if (!send) return { tabId: tab.id, status: 'draft_opened' };

  // Wait for Gmail compose to fully render, then click Send with retries
  const clicked = await retryClickButton(tab.id, [
    '[data-tooltip*="Send"]',           // Gmail's Send button tooltip
    '[aria-label*="Send"]',             // Accessibility label
    'div[aria-label*="Send"]',          // Some Gmail versions use div
    '.T-I.J-J5-Ji[role="button"]',      // Gmail compose Send button class
    'text:Send',                        // Fallback: find button with "Send" text
  ], 8, 1500);

  if (clicked) {
    // Wait a moment for Gmail to process, then close the tab
    await new Promise(r => setTimeout(r, 2000));
    try { await chrome.tabs.remove(tab.id); } catch {}
    return { tabId: tab.id, status: 'sent', to, subject };
  }
  return { tabId: tab.id, status: 'send_button_not_found', to, subject };
}

async function searchMail(query) {
  const url = `https://mail.google.com/mail/#search/${encodeURIComponent(query)}`;
  const tab = await chrome.tabs.create({ url });
  return { tabId: tab.id, query };
}

async function replyMail(tabId, body) {
  await chrome.scripting.executeScript({
    target: { tabId },
    func: (txt) => {
      const replyBtn = document.querySelector('[data-tooltip*="Reply"], [aria-label*="Reply"]');
      if (!replyBtn) throw new Error('Reply button not found');
      replyBtn.click();
      setTimeout(() => {
        const box = document.querySelector('[g_editable="true"], [contenteditable="true"]');
        if (box) { box.focus(); box.textContent = txt; }
      }, 1000);
    },
    args: [body],
  });
  return { replied: true };
}

async function getUnreadCount() {
  const [tab] = await chrome.tabs.query({ url: '*://mail.google.com/*' });
  if (!tab) {
    const newTab = await chrome.tabs.create({ url: 'https://mail.google.com' });
    return { tabId: newTab.id, note: 'Gmail opened, check manually' };
  }
  const results = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => {
      const el = document.querySelector('[title*="Inbox"]');
      return el ? el.title : document.title;
    },
  });
  return { info: results[0]?.result };
}

// ─── Google Calendar recipes ──────────────────────────────────────────────

async function openCalendar() {
  const tab = await chrome.tabs.create({ url: 'https://calendar.google.com' });
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

  const tab = await chrome.tabs.create({ url });

  if (!autoSave) return { tabId: tab.id, title, date, time, status: 'event_form_opened' };

  // Wait for Calendar form to render, then click Save
  const clicked = await retryClickButton(tab.id, [
    '[data-tooltip*="Save"]',          // Calendar Save button tooltip
    '[aria-label*="Save"]',            // Accessibility
    'button[aria-label="Save"]',       // Explicit button
    'text:Save',                       // Fallback: button text
  ], 8, 1500);

  if (clicked) {
    await new Promise(r => setTimeout(r, 2000));
    return { tabId: tab.id, title, date, time, status: 'event_saved' };
  }
  return { tabId: tab.id, title, date, time, status: 'save_button_not_found' };
}

/** Convert "2026-05-01" + "14:30" + optional offset minutes → YYYYMMDDTHHmmss (local time, no Z) */
function buildCalDT(dateStr, timeStr, offsetMin = 0) {
  if (!dateStr) {
    // Default to tomorrow if no date given
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    dateStr = tomorrow.toISOString().split('T')[0];
  }
  const [y, mo, d] = dateStr.split('-').map(Number);
  const [h, mi] = (timeStr || '00:00').split(':').map(Number);
  const dt = new Date(y, mo - 1, d, h || 0, (mi || 0) + offsetMin);
  // Format as YYYYMMDDTHHmmss (NO trailing Z — Google Calendar interprets as local timezone)
  const pad = (n) => String(n).padStart(2, '0');
  return `${dt.getFullYear()}${pad(dt.getMonth()+1)}${pad(dt.getDate())}T${pad(dt.getHours())}${pad(dt.getMinutes())}00`;
}

async function getCalendarEvents(date) {
  const [tab] = await chrome.tabs.query({ url: '*://calendar.google.com/*' });
  if (!tab) return openCalendar();
  const results = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
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
  const tab = await chrome.tabs.create({ url });

  // Retry clicking Join / Ask to join button
  const clicked = await retryClickButton(tab.id, [
    'text:Join now',
    'text:Ask to join',
    'text:Join',
    '[data-tooltip*="Join"]',
    '[aria-label*="Join"]',
  ], 10, 1500);

  return { tabId: tab.id, url, status: clicked ? 'joined' : 'join_button_not_found' };
}

async function scheduleMeet({ title, date, time, duration, guests }) {
  // Create a Calendar event with Meet video conference enabled
  return createCalendarEvent({ title, date, time, duration, guests, meet: true });
}

async function meetControl(action) {
  const [tab] = await chrome.tabs.query({ url: '*://meet.google.com/*' });
  if (!tab) throw new Error('No Meet tab open');
  await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: (act) => {
      if (act === 'mute_mic') {
        const btn = document.querySelector('[data-tooltip*="microphone"], [aria-label*="microphone"]');
        if (btn) btn.click();
      } else if (act === 'mute_camera') {
        const btn = document.querySelector('[data-tooltip*="camera"], [aria-label*="camera"]');
        if (btn) btn.click();
      } else if (act === 'leave') {
        const btn = document.querySelector('[aria-label*="Leave"], [data-tooltip*="Leave"]');
        if (btn) btn.click();
      }
    },
    args: [action],
  });
  return { action, tabId: tab.id };
}

// ─── Google Drive ─────────────────────────────────────────────────────────

async function searchDrive(query) {
  const url = `https://drive.google.com/drive/search?q=${encodeURIComponent(query)}`;
  const tab = await chrome.tabs.create({ url });
  return { tabId: tab.id, query };
}

async function openDriveFile(fileId) {
  const tab = await chrome.tabs.create({ url: `https://drive.google.com/file/d/${fileId}/view` });
  return { tabId: tab.id, fileId };
}

// ─── Agentic Web Agent — works on ANY website ────────────────────────────

/**
 * Extract all interactive elements from the current page.
 * Returns a compact representation for the LLM to reason about.
 * Cost: ZERO LLM calls — this is pure DOM scraping.
 */
async function extractPageElements(tabId) {
  // If no tabId given, use the active tab
  if (!tabId) {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) throw new Error('No active tab');
    tabId = tab.id;
  }

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => {
      // Generate a unique CSS selector for an element
      function getSelector(el) {
        if (el.id) return '#' + CSS.escape(el.id);
        if (el.name) return `${el.tagName.toLowerCase()}[name="${el.name}"]`;
        if (el.getAttribute('data-testid'))
          return `[data-testid="${el.getAttribute('data-testid')}"]`;
        if (el.getAttribute('aria-label'))
          return `[aria-label="${el.getAttribute('aria-label')}"]`;
        // Fallback: nth-of-type
        const tag = el.tagName.toLowerCase();
        const parent = el.parentElement;
        if (!parent) return tag;
        const siblings = Array.from(parent.children).filter(c => c.tagName === el.tagName);
        const idx = siblings.indexOf(el) + 1;
        const parentSel = parent.id ? '#' + CSS.escape(parent.id) : '';
        return `${parentSel} > ${tag}:nth-of-type(${idx})`;
      }

      // Get the visible label text for a form element
      function getLabel(el) {
        // Explicit <label for="...">
        if (el.id) {
          const label = document.querySelector(`label[for="${el.id}"]`);
          if (label) return label.textContent.trim();
        }
        // Parent <label>
        const parentLabel = el.closest('label');
        if (parentLabel) return parentLabel.textContent.trim();
        // aria-label
        if (el.getAttribute('aria-label')) return el.getAttribute('aria-label');
        // placeholder
        if (el.placeholder) return el.placeholder;
        // Previous sibling text
        const prev = el.previousElementSibling;
        if (prev && (prev.tagName === 'LABEL' || prev.tagName === 'SPAN'))
          return prev.textContent.trim();
        return '';
      }

      // Check visibility
      function isVisible(el) {
        const style = window.getComputedStyle(el);
        return style.display !== 'none' && style.visibility !== 'hidden'
          && style.opacity !== '0' && el.offsetParent !== null;
      }

      const elements = [];

      // Input fields (text, email, password, number, tel, date, etc.)
      document.querySelectorAll('input, textarea, select').forEach(el => {
        if (!isVisible(el)) return;
        const type = el.type || el.tagName.toLowerCase();
        if (type === 'hidden') return;

        const info = {
          tag: el.tagName.toLowerCase(),
          type: type,
          selector: getSelector(el),
          label: getLabel(el),
          required: el.required || false,
        };

        if (el.tagName === 'SELECT') {
          info.options = Array.from(el.options).map(o => ({
            value: o.value,
            text: o.textContent.trim(),
            selected: o.selected,
          }));
        }

        if (el.value) info.value = el.value;
        if (el.placeholder) info.placeholder = el.placeholder;

        elements.push(info);
      });

      // Buttons (submit, regular buttons, links that look like buttons)
      document.querySelectorAll('button, input[type="submit"], input[type="button"], [role="button"], a.btn, a.button').forEach(el => {
        if (!isVisible(el)) return;
        elements.push({
          tag: 'button',
          type: el.type || 'button',
          selector: getSelector(el),
          label: el.textContent?.trim() || el.value || el.getAttribute('aria-label') || '',
        });
      });

      // Links (only visible, non-button links)
      document.querySelectorAll('a[href]').forEach(el => {
        if (!isVisible(el)) return;
        if (el.classList.contains('btn') || el.classList.contains('button')) return; // Already captured
        const text = el.textContent?.trim();
        if (!text || text.length > 80) return; // Skip empty or very long links
        elements.push({
          tag: 'link',
          selector: getSelector(el),
          label: text,
          href: el.href,
        });
      });

      return {
        url: window.location.href,
        title: document.title,
        elements: elements.slice(0, 100), // Cap at 100 elements for token efficiency
        pageText: document.body?.innerText?.slice(0, 1000) || '', // First 1000 chars for context
      };
    },
  });

  return results[0]?.result || { elements: [] };
}

/**
 * Perform a batch of DOM actions on a page.
 * Each action is: { action: "fill"|"click"|"select"|"check", selector, value? }
 * This is the EXECUTION arm — zero LLM calls, pure DOM manipulation.
 */
async function performPageActions(tabId, actions) {
  if (!tabId) {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) throw new Error('No active tab');
    tabId = tab.id;
  }
  if (!actions || !actions.length) return { performed: 0 };

  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (actionList) => {
      const results = [];

      for (const act of actionList) {
        try {
          const el = document.querySelector(act.selector);
          if (!el) {
            results.push({ action: act.action, selector: act.selector, ok: false, error: 'Element not found' });
            continue;
          }

          switch (act.action) {
            case 'fill': {
              el.focus();
              // Clear existing value
              el.value = '';
              // Dispatch events to trigger React/Angular/Vue watchers
              el.dispatchEvent(new Event('input', { bubbles: true }));
              // Set new value
              el.value = act.value || '';
              el.dispatchEvent(new Event('input', { bubbles: true }));
              el.dispatchEvent(new Event('change', { bubbles: true }));
              el.dispatchEvent(new Event('blur', { bubbles: true }));
              results.push({ action: 'fill', selector: act.selector, ok: true, value: act.value });
              break;
            }
            case 'click': {
              el.click();
              results.push({ action: 'click', selector: act.selector, ok: true, text: el.textContent?.trim()?.slice(0, 50) });
              break;
            }
            case 'select': {
              // For <select> elements
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
              results.push({ action: act.action, selector: act.selector, ok: false, error: 'Unknown action' });
          }
        } catch (err) {
          results.push({ action: act.action, selector: act.selector, ok: false, error: err.message });
        }
      }

      return { performed: results.filter(r => r.ok).length, total: actionList.length, results };
    },
    args: [actions],
  });

  return results[0]?.result || { performed: 0 };
}

// ─── Bootstrap ───────────────────────────────────────────────────────────


connectWebSocket();

chrome.runtime.onInstalled.addListener(() => {
  console.log('[OpenClaw] Extension v2 installed');
  chrome.storage.local.set({ connectionStatus: 'disconnected', recentCommands: [] });
  connectWebSocket();
});

// Handle messages from popup (e.g. reconnect button)
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'reconnect') {
    if (ws) { try { ws.close(); } catch {} }
    ws = null;
    connectWebSocket();
    sendResponse({ ok: true });
  }
  return true;
});

// Keep service worker alive
chrome.alarms.create('keepAlive', { periodInMinutes: 0.4 });
chrome.alarms.onAlarm.addListener(() => {
  if (!ws || ws.readyState !== WebSocket.OPEN) connectWebSocket();
});

// ─── Command logging helper ──────────────────────────────────────────────

function logCommand(command) {
  chrome.storage.local.get(['recentCommands'], (data) => {
    const cmds = data.recentCommands || [];
    const timestamp = new Date().toLocaleTimeString();
    cmds.unshift(`[${timestamp}] ${command}`);
    if (cmds.length > 10) cmds.length = 10;
    chrome.storage.local.set({ recentCommands: cmds });
  });
}
