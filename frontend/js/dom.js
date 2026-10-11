// DOM helpers. Nodes are built from text and never from HTML strings.

// Text is set before children are appended, so a string child and the text option never mix.
export function el(tag, options = {}, ...children) {
  const node = document.createElement(tag);
  if (options.class) node.className = options.class;
  if (options.text !== undefined) node.textContent = options.text;
  for (const [name, value] of Object.entries(options.attrs ?? {})) {
    node.setAttribute(name, String(value));
  }
  for (const [type, handler] of Object.entries(options.on ?? {})) {
    node.addEventListener(type, handler);
  }
  node.append(...children);
  return node;
}

export function byId(id) {
  const node = document.getElementById(id);
  if (!node) throw new Error(`missing element #${id}`);
  return node;
}

export function setVisible(node, visible) {
  node.hidden = !visible;
}

// A message line: null hides it, otherwise its text and kind are shown.
export function showMessage(node, message) {
  setVisible(node, message !== null);
  if (message === null) return;
  node.textContent = message.text;
  node.className = `message message-${message.kind}`;
}
