/**
 * OpenClaw Chrome Extension — Background Service Worker
 * ========================================================
 * Connects to the Python agent via WebSocket and dispatches
 * tab management, DOM interaction, and navigation commands.
 */

const WS_URL = 'ws://127.0.0.1:8765';
let ws = null;
let reconnectTimer = null;

// --- WebSocket Connection ---
function connectWebSocket() {
  if (ws && ws.readyState === WebSocket.OPEN) return;

  try {
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      console.log('[OpenClaw] Connected to agent');
      chrome.storage.local.set({ connectionStatus: 'connected' });
    };

    ws.onmessage = async (event) => {
      try {
        const data = JSON.parse(event.data);
        const response = await handleCommand(data);
        ws.send(JSON.stringify({
          id: data.id,
          ...response,
        }));
      } catch (error) {
        ws.send(JSON.stringify({
          id: data?.id,
          error: error.message,
        }));
      }
    };

    ws.onclose = () => {
      console.log('[OpenClaw] Disconnected from agent');
      chrome.storage.local.set({ connectionStatus: 'disconnected' });
      // Auto-reconnect after 5 seconds
      reconnectTimer = setTimeout(connectWebSocket, 5000);
    };

    ws.onerror = (error) => {
      console.error('[OpenClaw] WebSocket error:', error);
    };
  } catch (e) {
    console.error('[OpenClaw] Connection failed:', e);
    reconnectTimer = setTimeout(connectWebSocket, 5000);
  }
}

// --- Command Dispatcher ---
async function handleCommand(data) {
  const { command, params } = data;

  switch (command) {
    case 'getTabs':
      return await getTabs();

    case 'switchTab':
      return await switchTab(params.tabId);

    case 'closeTab':
      return await closeTab(params.tabId);

    case 'injectScript':
      return await injectScript(params.tabId, params.code);

    case 'getDom':
      return await getDomContent(params.tabId, params.selector);

    case 'clickElement':
      return await clickElement(params.tabId, params.selector);

    case 'fillInput':
      return await fillInput(params.tabId, params.selector, params.value);

    case 'navigate':
      return await navigateTab(params.tabId, params.url);

    case 'screenshot':
      return await captureTab(params.tabId);

    default:
      throw new Error(`Unknown command: ${command}`);
  }
}

// --- Tab Management ---
async function getTabs() {
  const tabs = await chrome.tabs.query({});
  return {
    tabs: tabs.map(t => ({
      id: t.id,
      url: t.url,
      title: t.title,
      active: t.active,
      windowId: t.windowId,
    })),
  };
}

async function switchTab(tabId) {
  await chrome.tabs.update(tabId, { active: true });
  const tab = await chrome.tabs.get(tabId);
  await chrome.windows.update(tab.windowId, { focused: true });
  return { success: true };
}

async function closeTab(tabId) {
  await chrome.tabs.remove(tabId);
  return { success: true };
}

async function navigateTab(tabId, url) {
  if (tabId) {
    await chrome.tabs.update(tabId, { url });
  } else {
    await chrome.tabs.create({ url });
  }
  return { success: true };
}

// --- DOM Interaction ---
async function injectScript(tabId, code) {
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: new Function(code),
  });
  return { result: results[0]?.result };
}

async function getDomContent(tabId, selector = 'body') {
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: (sel) => {
      const el = document.querySelector(sel);
      return el ? el.innerText : '';
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
      if (el) el.click();
      else throw new Error(`Element not found: ${sel}`);
    },
    args: [selector],
  });
  return { success: true };
}

async function fillInput(tabId, selector, value) {
  await chrome.scripting.executeScript({
    target: { tabId },
    func: (sel, val) => {
      const el = document.querySelector(sel);
      if (el) {
        el.value = val;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      } else {
        throw new Error(`Element not found: ${sel}`);
      }
    },
    args: [selector, value],
  });
  return { success: true };
}

async function captureTab(tabId) {
  const dataUrl = await chrome.tabs.captureVisibleTab(null, { format: 'png' });
  return { screenshot: dataUrl };
}

// --- Initialize ---
connectWebSocket();

// Reconnect on extension install/update
chrome.runtime.onInstalled.addListener(() => {
  console.log('[OpenClaw] Extension installed/updated');
  connectWebSocket();
});

// Keep service worker alive with periodic alarm
chrome.alarms.create('keepAlive', { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'keepAlive') {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      connectWebSocket();
    }
  }
});
