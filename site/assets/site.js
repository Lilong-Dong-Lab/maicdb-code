// MAIC-DB site JavaScript — vanilla, no framework (spec Q1).
//
// Channel-card provenance deep links (spec Q10, M3-T4): every evidence
// row is a <details> whose id is the row's measurement_id. A URL like
// /channels/piezo1/#PIEZO1-EX-00004 opens that row's details block and
// scrolls to it — on load and on later same-page hash changes.
// T6 wires the global search here (client-side substring match over the
// build-time search-index.json, spec Q9).
function openAnchorTarget() {
  var hash = window.location.hash;
  if (!hash || hash.length < 2) return;
  var target = document.getElementById(decodeURIComponent(hash.slice(1)));
  if (!target) return;
  var details = target.closest("details");
  if (details) details.open = true;
  target.scrollIntoView();
}

window.addEventListener("DOMContentLoaded", openAnchorTarget);
window.addEventListener("hashchange", openAnchorTarget);
