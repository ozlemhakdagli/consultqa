// The one deliberate scroll of the page: a new answer is brought into view once, and only when its
// top edge is above the window or in the lower half of it. A reader who already sees it is not moved.
export function revealIfHidden(node, win = window) {
  const { top } = node.getBoundingClientRect();
  if (top < 0 || top > win.innerHeight * 0.5) node.scrollIntoView({ block: "start" });
}
