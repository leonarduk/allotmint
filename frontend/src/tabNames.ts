// Browser tab names for the two surfaces (#9575). Each tab names itself after
// the surface it shows (see Menu), and the cross-links target those names, so
// "Operations" and "App" switch to the already-open tab instead of stacking
// new ones, and open it only when it isn't open yet. Those links must not use
// rel="noopener": named-tab lookup only finds tabs linked by an opener, and
// both tabs are this same-origin app.
export const APP_TAB_NAME = 'allotmint-app';
export const OPERATIONS_TAB_NAME = 'allotmint-operations';
