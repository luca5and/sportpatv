// Anonym besöksstatistik – "räkna, men känn aldrig igen".
// Samma modell som varärbussen.se: klick räknas bara i minnet (inget sparas på
// enheten, inga cookies, inga id:n) och skickas som en summa när fliken döljs.
// Servern lägger ihop summorna per dag, separat från bussidans statistik.
(function () {
  "use strict";

  var ENDPOINT = "https://xn--varrbussen-s5a.se/api/usage";
  var SITE_PATH = "/sportpatv"; // på luca5and.github.io delas domänen med andra sidor

  // Sökmotorer och automatiska webbläsare ska inte räknas som besök.
  var IS_BOT = (function () {
    try {
      return navigator.webdriver === true ||
        /bot\b|bot\/|crawl|spider|slurp|headless|lighthouse|pagespeed|inspectiontool|preview/i.test(navigator.userAgent);
    } catch (e) { return false; }
  })();

  function sameSite(url) {
    try {
      var u = new URL(url);
      if (u.origin !== location.origin) return false;
      return location.hostname !== "luca5and.github.io" || u.pathname.indexOf(SITE_PATH + "/") === 0;
    } catch (e) { return false; }
  }

  // Ett besök räknas bara när man kommer utifrån, inte vid klick mellan våra sidor.
  var visitPending = !sameSite(document.referrer);
  var counts = {};
  var items = {};
  var visibleSince = document.visibilityState === "visible" ? Date.now() : 0;

  function track(name) { counts[name] = (counts[name] || 0) + 1; }

  var path = location.pathname;
  track(path.indexOf("/spelare/") >= 0 ? "pagePlayer" : path.indexOf("/lag/") >= 0 ? "pageTeam" : "pageIndex");

  function durationBucket(ms) {
    if (ms < 30000) return "dur_lt30s";
    if (ms < 120000) return "dur_30s_2m";
    if (ms < 600000) return "dur_2_10m";
    return "dur_gt10m";
  }

  function flush() {
    if (IS_BOT || !visibleSince) return;
    var payload = JSON.stringify({
      visit: visitPending,
      duration: durationBucket(Date.now() - visibleSince),
      events: counts,
      items: items,
    });
    visitPending = false;
    counts = {};
    items = {};
    visibleSince = 0;
    try {
      var blob = new Blob([payload], { type: "text/plain" });
      if (!(navigator.sendBeacon && navigator.sendBeacon(ENDPOINT, blob))) {
        fetch(ENDPOINT, { method: "POST", body: payload, headers: { "Content-Type": "text/plain" }, keepalive: true })
          .catch(function () {});
      }
    } catch (e) { /* statistiken är bara ett plus */ }
  }

  document.addEventListener("click", function (ev) {
    var t = ev.target;
    if (!(t instanceof Element)) return;
    var a = t.closest("a");
    var href = a ? a.getAttribute("href") || "" : "";
    if (a && a.classList.contains("coffee")) return track("coffeeClick");
    if (a && href.indexOf("spelare/") >= 0) {
      track("playerClick");
      var m = href.match(/spelare\/([a-z0-9-]+)\//);
      if (m) items[m[1]] = (items[m[1]] || 0) + 1;
      return;
    }
    if (a && href.indexOf("lag/") >= 0) return track("teamClick");
    if (a && href.indexOf("wikipedia.org") >= 0) return track("wikiClick");
    if (a && a.closest(".tv")) return track("sourceClick");
    if (t.closest("#days button")) return track("daySelect");
    var chip = t.closest("#filters button");
    if (chip) {
      var label = chip.textContent || "";
      return track(label.indexOf("Ishockey") >= 0 ? "sportHockey" : label.indexOf("Fotboll") >= 0 ? "sportFootball" : "sportAll");
    }
    if (t.closest(".more")) return track("showMore");
    if (t.closest(".legend:not(.about) summary")) return track("legendOpen");
  }, true);

  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") flush();
    else visibleSince = Date.now();
  });
  // iOS Safari skickar inte alltid visibilitychange när fliken stängs
  window.addEventListener("pagehide", flush);
})();
