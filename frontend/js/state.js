const state = {currentFund: null, portfolio: null, watchlist: [], dashboard: null, loading: {}, errors: {}};
const listeners = new Set();
export const getState = () => ({...state});
export function setState(patch) { Object.assign(state, patch); listeners.forEach(fn => fn(getState())); }
export function subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); }
