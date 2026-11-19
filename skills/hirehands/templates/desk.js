// Shared by both self-contained previews. A normal browser cannot send to Hermes.
const byId = id => document.getElementById(id);
function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
let sending = false;
async function dispatch(text) {
  if (sending) return;
  sending = true;
  const status = byId('feedback');
  status.replaceChildren();
  try {
    if (typeof window.hermes?.send === 'function') {
      await window.hermes.send(text);
      status.textContent = 'Sent to Hermes.';
      document.querySelectorAll('button, select, input, textarea').forEach(n => n.disabled = true);
      return;
    }
    await navigator.clipboard.writeText(text);
    status.textContent = 'Copied. Paste the command into your Hermes chat.';
  } catch {
    const field = el('textarea'); field.className = 'fallback'; field.readOnly = true; field.value = text;
    field.setAttribute('aria-label', 'Command to copy'); status.append('Could not send. Copy this command into your chat:', field); field.select();
  }
  sending = false;
}
