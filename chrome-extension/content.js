/**
 * OpenClaw Chrome Extension — Content Script
 * ==============================================
 * Runs in the context of web pages for DOM interaction.
 * Communicates with the background service worker.
 */

// --- Listen for messages from background ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  try {
    switch (message.action) {
      case 'getPageInfo':
        sendResponse({
          url: window.location.href,
          title: document.title,
          text: document.body.innerText.substring(0, 5000),
          forms: getFormInfo(),
        });
        break;

      case 'clickElement':
        const clickTarget = document.querySelector(message.selector);
        if (clickTarget) {
          clickTarget.click();
          sendResponse({ success: true });
        } else {
          sendResponse({ error: `Element not found: ${message.selector}` });
        }
        break;

      case 'fillInput':
        const input = document.querySelector(message.selector);
        if (input) {
          input.value = message.value;
          input.dispatchEvent(new Event('input', { bubbles: true }));
          input.dispatchEvent(new Event('change', { bubbles: true }));
          sendResponse({ success: true });
        } else {
          sendResponse({ error: `Element not found: ${message.selector}` });
        }
        break;

      case 'extractText':
        const textTarget = document.querySelector(message.selector || 'body');
        sendResponse({
          text: textTarget ? textTarget.innerText : '',
        });
        break;

      case 'getLinks':
        const links = Array.from(document.querySelectorAll('a[href]')).map(a => ({
          text: a.textContent.trim(),
          href: a.href,
        }));
        sendResponse({ links: links.slice(0, 50) });
        break;

      case 'scrollTo':
        window.scrollTo({
          top: message.y || 0,
          left: message.x || 0,
          behavior: 'smooth',
        });
        sendResponse({ success: true });
        break;

      default:
        sendResponse({ error: `Unknown action: ${message.action}` });
    }
  } catch (error) {
    sendResponse({ error: error.message });
  }

  return true; // Keep message channel open for async response
});

// --- Helper Functions ---
function getFormInfo() {
  const forms = document.querySelectorAll('form');
  return Array.from(forms).map((form, i) => {
    const inputs = Array.from(form.querySelectorAll('input, textarea, select'));
    return {
      index: i,
      action: form.action,
      method: form.method,
      fields: inputs.map(inp => ({
        type: inp.type || inp.tagName.toLowerCase(),
        name: inp.name,
        id: inp.id,
        placeholder: inp.placeholder,
        value: inp.type === 'password' ? '***' : inp.value,
      })),
    };
  });
}

// --- Notify extension is loaded ---
console.log('[OpenClaw] Content script loaded on', window.location.hostname);
