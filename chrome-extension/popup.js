// popup.js — OpenClaw extension popup logic
// Separated from popup.html for MV3 Content Security Policy compliance

function updateUI() {
  chrome.storage.local.get(['connectionStatus', 'recentCommands'], (data) => {
    const dot  = document.getElementById('statusDot');
    const text = document.getElementById('statusText');
    const btn  = document.getElementById('reconnectBtn');

    if (data.connectionStatus === 'connected') {
      dot.className = 'dot connected';
      text.textContent = 'Connected to IntentOS agent';
      btn.style.display = 'none';
    } else {
      dot.className = 'dot disconnected';
      text.textContent = 'Agent not connected';
      btn.style.display = 'block';
    }

    if (data.recentCommands && data.recentCommands.length > 0) {
      const list = document.getElementById('recentList');
      list.innerHTML = data.recentCommands
        .slice(0, 5)
        .map(cmd => `<div class="recent-item">${cmd}</div>`)
        .join('');
    }
  });
}

// Initial check
updateUI();

// Re-check every 2s while popup is open
setInterval(updateUI, 2000);

// Reconnect button
document.getElementById('reconnectBtn').addEventListener('click', () => {
  chrome.runtime.sendMessage({ action: 'reconnect' });
  document.getElementById('statusText').textContent = 'Reconnecting...';
});
