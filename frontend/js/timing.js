// Waiting helper for the polling loops.
export function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
