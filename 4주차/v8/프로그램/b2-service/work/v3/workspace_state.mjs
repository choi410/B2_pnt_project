// A delayed flow redraw must not resurrect a workspace after session expiry.
export function updateWorkspace(current, update) {
  return typeof update === 'function'
    ? current?.user ? update(current) : current
    : update;
}
