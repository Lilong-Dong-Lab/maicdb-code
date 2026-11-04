// MAIC-DB site JavaScript — vanilla, no framework (spec Q1).
//
// Channel-card provenance deep links (spec Q10, M3-T4): every evidence
// row is a <details> whose id is the row's measurement_id. A URL like
// /channels/piezo1/#PIEZO1-EX-00004 opens that row's details block and
// scrolls to it — on load and on later same-page hash changes.
//
// Global search (spec Q9, M3-T6): the build writes a flat
// search-index.json at each locale tree's root (site/build.py copies
// the data layer's index — the deployed root is the rendered tree).
// The match below is the twin of searchEntries() in
// tests/test_site_search.py (same fields, same lowercase substring
// rule); the two must not drift. Results group by type and link into
// the page's own locale tree via the data-root prefix.
//
// Q9 reading note: "channel name/aliases/UniProt + family" includes the
// channel's own family attribute among the channel entry's searchable
// fields — querying a family name recalls the family entry (browse
// anchor) AND its member channels. The Python twin carries the same
// note; change both or neither.
function openAnchorTarget() {
  var hash = window.location.hash;
  if (!hash || hash.length < 2) return;
  var target = document.getElementById(decodeURIComponent(hash.slice(1)));
  if (!target) return;
  var details = target.closest("details");
  if (details) details.open = true;
  target.scrollIntoView();
}

function searchEntries(entries, query) {
  var q = query.trim().toLowerCase();
  if (!q) return [];
  return entries.filter(function (entry) {
    var fields;
    if (entry.type === "channel") {
      fields = [entry.label].concat(entry.aliases || [], entry.uniprots || [], [entry.family]);
    } else if (entry.type === "family") {
      fields = [entry.label];
    } else {
      fields = [entry.name, entry.label];
    }
    return fields.some(function (field) {
      return field.toLowerCase().indexOf(q) !== -1;
    });
  });
}

function initSearch() {
  var form = document.querySelector(".site-search");
  var input = document.getElementById("site-search");
  var box = document.getElementById("site-search-results");
  if (!form || !input || !box) return;
  var root = form.getAttribute("data-root") || ".";
  var groupLabels = {
    channel: form.getAttribute("data-label-channel"),
    family: form.getAttribute("data-label-family"),
    parameter: form.getAttribute("data-label-parameter"),
  };
  var noResultsLabel = form.getAttribute("data-label-no-results");
  var entries = null;

  fetch(root + "/search-index.json")
    .then(function (response) { return response.json(); })
    .then(function (doc) { entries = doc.entries; })
    .catch(function () {
      // fetch is unavailable under file:// previews — degrade silently:
      // the search box stays, just with no results (deployed on Pages it is
      // always http(s) and loads normally).
    });

  function resultLabel(entry) {
    if (entry.type === "parameter") return entry.label + " (" + entry.name + ")";
    return entry.label;
  }

  function render(hits) {
    box.textContent = "";
    if (!hits.length) {
      var empty = document.createElement("p");
      empty.className = "search-empty";
      empty.textContent = noResultsLabel;
      box.appendChild(empty);
    } else {
      ["channel", "family", "parameter"].forEach(function (type) {
        var group = hits.filter(function (entry) { return entry.type === type; });
        if (!group.length) return;
        var section = document.createElement("section");
        section.className = "search-group";
        var heading = document.createElement("h3");
        heading.textContent = groupLabels[type];
        section.appendChild(heading);
        var list = document.createElement("ul");
        group.forEach(function (entry) {
          var item = document.createElement("li");
          var link = document.createElement("a");
          link.href = root + entry.url;
          link.textContent = resultLabel(entry);
          item.appendChild(link);
          list.appendChild(item);
        });
        section.appendChild(list);
        box.appendChild(section);
      });
    }
    box.hidden = false;
  }

  function hideResults() {
    box.hidden = true;
    box.textContent = "";
  }

  input.addEventListener("input", function () {
    if (entries === null) return;
    if (!input.value.trim()) {
      hideResults();
      return;
    }
    render(searchEntries(entries, input.value));
  });
  // refocus re-shows results when a query is already present
  // (after a click-outside close)
  input.addEventListener("focus", function () {
    if (entries !== null && input.value.trim()) {
      render(searchEntries(entries, input.value));
    }
  });
  input.addEventListener("keydown", function (event) {
    if (event.key === "Escape") hideResults();
  });
  document.addEventListener("click", function (event) {
    if (!form.contains(event.target)) hideResults();
  });
  // No results page exists (spec Q9 has no standalone page); a form
  // submit would only reload — prevent it.
  form.addEventListener("submit", function (event) { event.preventDefault(); });
}

window.addEventListener("DOMContentLoaded", openAnchorTarget);
window.addEventListener("hashchange", openAnchorTarget);
window.addEventListener("DOMContentLoaded", initSearch);
