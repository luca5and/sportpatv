(function () {
  "use strict";

  const TZ = "Europe/Stockholm";
  const dayKey = (d) => new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
  const timeFmt = new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
  const dayFmt = new Intl.DateTimeFormat("sv-SE", { timeZone: TZ, weekday: "short", day: "numeric", month: "short" });

  const state = { events: [], day: null, sport: null };
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
    const today = dayKey(new Date());
    const tomorrow = dayKey(new Date(Date.now() + 864e5));
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
    const tvRow = el("div", { class: "tv" }, [tvBadge(e.tv)]);
    if (e.tv.status !== "confirmed" && e.tv.note && e.tv.note !== "Sänds inte i Sverige") tvRow.append(e.tv.note);
    if (e.tv.status === "confirmed" && e.tv.source) {
      tvRow.append(el("a", { href: e.tv.source, rel: "nofollow noopener", target: "_blank" }, ["källa"]));
    }
    return el("li", { class: "event" }, [
      el("div", { class: "time" + (live ? " live" : ""), title: live ? "Har börjat" : null }, [live ? "Pågår" : timeFmt.format(start)]),
      el("div", { class: "body" }, [
        el("div", { class: "meta" }, [`${e.sport} · ${e.competition}`]),
        el("div", { class: "title" }, [e.title]),
        el("div", { class: "swedes" }, e.swedes.map((s) =>
          el("span", { class: "swede" }, [s.name, " ", el("small", {}, [s.team])]))),
        tvRow,
      ]),
    ]);
  }

  function render() {
    const days = [...new Set(state.events.map((e) => dayKey(new Date(e.start))))];
    if (!days.includes(state.day)) state.day = days[0] || null;

    $("days").replaceChildren(...days.map((d) => {
      const b = el("button", { class: "chip", role: "tab", "aria-selected": String(d === state.day) }, [dayLabel(d)]);
      b.onclick = () => { state.day = d; render(); };
      return b;
    }));

    const ofDay = state.events.filter((e) => dayKey(new Date(e.start)) === state.day);
    const sports = [...new Set(ofDay.map((e) => e.sport))];
    if (state.sport && !sports.includes(state.sport)) state.sport = null;
    const filters = sports.length > 1 ? [null, ...sports] : [];
    $("filters").replaceChildren(...filters.map((s) => {
      const n = s ? ofDay.filter((e) => e.sport === s).length : ofDay.length;
      const b = el("button", { class: "chip", "aria-pressed": String(s === state.sport) }, [s || "Alla", el("span", { class: "count" }, [String(n)])]);
      b.onclick = () => { state.sport = s; render(); };
      return b;
    }));

    const shown = ofDay.filter((e) => !state.sport || e.sport === state.sport);
    $("list").replaceChildren(...shown.map(renderEvent));
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
