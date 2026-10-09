(function () {
  "use strict";

  const TZ = "Europe/Stockholm";
  const dayKey = (d) => new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
  const timeFmt = new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
  const dayFmt = new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, weekday: "short", day: "numeric", month: "short" });
  const hourFmt = new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, hour: "numeric", hourCycle: "h23" });
  const NIGHT_END = 6; // matcher före 06:00 hör till kvällen innan (NHL)
  const PAGE = 15;     // antal matcher innan "Visa fler"
  const ICONS = { Fotboll: "⚽", Ishockey: "🏒", Alpint: "⛷", Längdskidor: "⛷", Handboll: "🤾", Golf: "⛳", Tennis: "🎾" };
  const STORE_KEY = "sportpatv.sport";

  // Dagen en händelse hör till: nattmatcher räknas till kvällen innan.
  const eventDay = (iso) => dayKey(new Date(new Date(iso).getTime() - NIGHT_END * 3600e3));
  const isNight = (iso) => Number(hourFmt.format(new Date(iso))) < NIGHT_END;

  function loadSport() {
    try { return localStorage.getItem(STORE_KEY); } catch (_) { return null; }
  }
  function saveSport(sport) {
    try { sport ? localStorage.setItem(STORE_KEY, sport) : localStorage.removeItem(STORE_KEY); } catch (_) { /* privat läge */ }
  }

  const state = { events: [], day: null, sport: loadSport(), expanded: false };
  const $ = (id) => document.getElementById(id);

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null) continue;
      if (k === "text") node.textContent = v;
      else node.setAttribute(k, v);
    }
    for (const c of children || []) if (c) node.append(c);
    return node;
  }

  function dayLabel(key) {
    const today = eventDay(new Date().toISOString());
    const tomorrow = eventDay(new Date(Date.now() + 864e5).toISOString());
    if (key === today) return "Idag";
    if (key === tomorrow) return "Imorgon";
    return dayFmt.format(new Date(key + "T12:00:00"));
  }

  function tvBadge(tv) {
    if (tv.status === "confirmed") {
      const label = tv.channel ? `${tv.service} · ${tv.channel}` : tv.service;
      return el("span", { class: "badge confirmed", title: tv.note || "Bekräftad för den här matchen" }, [label]);
    }
    if (tv.status === "likely") {
      return el("span", { class: "badge likely", title: "Slutsats från omgångens övriga sändningar – ej kontrollerad" }, [tv.service]);
    }
    if (tv.status === "none") {
      return el("span", { class: "badge none" }, ["Sänds inte i Sverige"]);
    }
    return el("span", { class: "badge unknown" }, ["Ej bekräftat"]);
  }

  function renderEvent(e) {
    const start = new Date(e.start);
    const live = start <= new Date();
    const timeCell = el("div", { class: "time" + (live ? " live" : ""), title: live ? "Har börjat" : null },
      [live ? "Pågår" : timeFmt.format(start)]);
    if (!live && isNight(e.start)) timeCell.append(el("small", { class: "night", title: "Natten efter vald dag" }, ["natt"]));
    const tvRow = el("div", { class: "tv" }, [tvBadge(e.tv)]);
    if (e.tv.status !== "confirmed" && e.tv.note && e.tv.note !== "Sänds inte i Sverige") tvRow.append(e.tv.note);
    if (e.tv.status === "confirmed" && e.tv.source) {
      tvRow.append(el("a", { href: e.tv.source, rel: "nofollow noopener", target: "_blank" }, ["källa"]));
    }
    return el("li", { class: "event" }, [
      timeCell,
      el("div", { class: "body" }, [
        el("div", { class: "meta" }, [`${e.sport} · ${e.competition}`]),
        el("div", { class: "title" }, [e.title]),
        el("div", { class: "swedes" }, e.swedes.map((s) => {
          const name = s.page
            ? el("a", { href: s.page, title: s.name + " på TV" }, [s.name])
            : s.url
              ? el("a", { href: s.url, rel: "noopener", target: "_blank", title: "Om " + s.name + " på Wikipedia" }, [s.name])
              : s.name;
          return el("span", { class: "swede" }, [name, " ", el("small", {}, [s.team])]);
        })),
        tvRow,
      ]),
    ]);
  }

  function render() {
    const days = [...new Set(state.events.map((e) => eventDay(e.start)))];
    if (!days.includes(state.day)) state.day = days[0] || null;

    $("days").replaceChildren(...days.map((d) => {
      const b = el("button", { class: "chip", role: "tab", "aria-selected": String(d === state.day) }, [dayLabel(d)]);
      b.onclick = () => { state.day = d; state.expanded = false; render(); };
      return b;
    }));

    const ofDay = state.events.filter((e) => eventDay(e.start) === state.day);
    const sports = [...new Set(ofDay.map((e) => e.sport))].sort();
    // Sparat val gäller bara om sporten finns den här dagen; valet ligger kvar till nästa dag.
    const active = sports.includes(state.sport) ? state.sport : null;
    const filters = sports.length > 1 ? [null, ...sports] : [];
    $("filters").replaceChildren(...filters.map((s) => {
      const n = s ? ofDay.filter((e) => e.sport === s).length : ofDay.length;
      const label = s ? `${ICONS[s] || ""} ${s}`.trim() : "Alla";
      const b = el("button", { class: "chip", "aria-pressed": String(s === active) }, [label, el("span", { class: "count" }, [String(n)])]);
      b.onclick = () => { state.sport = s; state.expanded = false; saveSport(s); render(); };
      return b;
    }));

    const shown = ofDay.filter((e) => !active || e.sport === active);
    const visible = state.expanded ? shown : shown.slice(0, PAGE);
    const items = visible.map(renderEvent);
    if (visible.length < shown.length) {
      const more = el("button", { class: "more" }, [`Visa fler (${shown.length - visible.length})`]);
      more.onclick = () => { state.expanded = true; render(); };
      items.push(el("li", { class: "more-row" }, [more]));
    }
    $("list").replaceChildren(...items);
    $("empty").hidden = shown.length > 0;
    $("empty").textContent = state.events.length ? "Inget här just nu." : "Inga svenskar på TV de närmaste dagarna – eller så har vi inte hämtat datan än.";
  }

  fetch("data/swedes-on-tv.json", { cache: "no-cache" })
    .then((r) => r.json())
    .then((data) => {
      // Datan byggs en gång per dygn; dölj matcher som rimligen är slut.
      const cutoff = Date.now() - 2.5 * 3600e3;
      state.events = (data.events || []).filter((e) => new Date(e.start).getTime() >= cutoff);
      if (data.generated) {
        $("updated").textContent = "Uppdaterad " + dayFmt.format(new Date(data.generated)) + " " + timeFmt.format(new Date(data.generated)) + ".";
      }
      render();
    })
    .catch(() => {
      $("empty").hidden = false;
      $("empty").textContent = "Kunde inte ladda datan. Försök igen om en stund.";
    });
})();
