/* Интерфейс КассаКонтроль: страницы собираются из данных API.
   Источники: GET /api/v1/jobs, GET /api/v1/jobs/{id}, GET /api/v1/jobs/{id}/progress (ключ в X-API-Key). */
(() => {
  const qs = new URLSearchParams(location.search);
  if (qs.get("key")) { try { localStorage.setItem("kk_key", qs.get("key")); } catch (e) {} }
  if (qs.get("theme")) { try { localStorage.setItem("kk_theme", qs.get("theme")); } catch (e) {} }
  let theme = "light";
  try { theme = localStorage.getItem("kk_theme") || "light"; } catch (e) {}
  if (theme === "dark") document.documentElement.setAttribute("data-theme", "dark");

  const KEY = () => { try { return localStorage.getItem("kk_key") || ""; } catch (e) { return ""; } };
  const H = () => ({ "X-API-Key": KEY() });
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmt = t => { t = Math.max(0, +t || 0); const m = Math.floor(t / 60), s = Math.floor(t % 60); return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`; };
  const fmt1 = t => { t = Math.max(0, +t || 0); const m = Math.floor(t / 60), s = (t % 60).toFixed(1).padStart(4, "0"); return `${String(m).padStart(2, "0")}:${s.replace(".", ",")}`; };
  const mb = b => (b / 1048576).toFixed(1).replace(".", ",") + " МБ";
  const dt = ts => ts ? new Date(ts * 1000).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "—";
  const dur = s => s < 60 ? `${Math.round(s)} с` : `${Math.floor(s / 60)} мин ${String(Math.round(s % 60)).padStart(2, "0")} с`;
  const pct = (t, d) => (100 * t / Math.max(d, 0.01)).toFixed(2) + "%";
  const codecName = c => ({ h264: "H.264", hevc: "H.265 (HEVC)", mpeg4: "MPEG-4", vp9: "VP9", av1: "AV1", prores: "ProRes", mjpeg: "MJPEG" }[String(c || "").toLowerCase()] || String(c || "").toUpperCase());
  const RU_OBJ = { laptop: "ноутбук", tv: "монитор", chair: "стул", "dining table": "стол", keyboard: "клавиатура", mouse: "мышь", "cell phone": "телефон", book: "пачка банкнот/документы", cup: "чашка", bottle: "бутылка", bowl: "миска", handbag: "сумка", backpack: "рюкзак", remote: "пульт", person: "человек", clock: "часы", "potted plant": "растение", couch: "диван", bench: "скамья", suitcase: "чемодан", vase: "ваза" };
  const ruObj = k => RU_OBJ[k] || k;

  const I = {
    mark: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="6" width="17" height="12" rx="2"/><circle cx="12" cy="12" r="2.4"/></svg>',
    chevL: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 6l-6 6 6 6"/></svg>',
    list: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3.5" y="4" width="7" height="7" rx="1.5"/><rect x="13.5" y="4" width="7" height="7" rx="1.5"/><rect x="3.5" y="14" width="7" height="7" rx="1.5"/><rect x="13.5" y="14" width="7" height="7" rx="1.5"/></svg>',
    up: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 15V4M7 9l5-5 5 5"/><path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/></svg>',
    book: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 21V5M9 7h6M9 11h6"/></svg>',
    code: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 7l-5 5 5 5M16 7l5 5-5 5"/></svg>',
    moon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/></svg>',
    sun: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
    help: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17.5h.01"/></svg>',
    search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/></svg>',
    dl: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11M7 10l5 5 5-5M4 19h16"/></svg>',
    ok: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
    okc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M8 12.3l2.7 2.7L16 9.5"/></svg>',
    xc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5M12 16.5h.01"/></svg>',
    warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 2.6 17.2A2 2 0 0 0 4.3 20h15.4a2 2 0 0 0 1.7-2.8L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>',
    ext: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>',
    prev: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 5h2v14H6zM20 5v14L9 12z"/></svg>',
    next: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M16 5h2v14h-2zM4 5v14l11-7z"/></svg>',
    film: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 9h18M3 15h18M8 5v14M16 5v14"/></svg>',
    doc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/></svg>',
    task: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3 8-8"/><path d="M20 12v7a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h11"/></svg>',
    copy: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/></svg>',
    lock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>',
    log: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6h16M4 12h10M4 18h13"/></svg>',
    menu: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>',
  };
  const sh = k => k === "ok" ? `<span class="sh ok">${I.okc}</span>` : k === "x" ? `<span class="sh x">${I.xc}</span>` : `<span class="sh ${k}"></span>`;
  const confKind = c => c === "низкая" ? "w" : "d";

  // ---------- каркас ----------
  function side(active, rail) {
    const it = (ic, t, href, on, k) => rail
      ? `<a class="ritem ${on ? "on" : ""}" href="${href}">${ic}${t}</a>`
      : `<a class="${on ? "on" : ""}" href="${href}">${ic}${t}${k ? `<span class="k">${k}</span>` : ""}</a>`;
    const themeBtn = `<span class="ibtn b" id="themeBtn" title="Тема">${theme === "dark" ? I.sun : I.moon}</span>`;
    if (rail) return `<aside class="side"><div class="rbrand"><a href="index.html" class="mark" style="color:inherit">${I.mark}</a></div>
      ${it(I.list, "Проверки", "index.html", active === "list")}${it(I.up, "Новая", "index.html#upload", false)}${it(I.code, "API", "api.html", active === "api")}
      <div class="sfoot" style="align-items:center"><a class="ritem" id="themeBtn">${theme === "dark" ? I.sun : I.moon}Тема</a><a class="ritem" href="help.html">${I.help}Помощь</a></div></aside>`;
    return `<aside class="side">
      <div class="sbrand"><span class="mark">${I.mark}</span>КассаКонтроль<span class="col">${I.chevL}</span></div>
      <div class="ucard"><span class="ava">ПК</span><div><b>Проверяющий</b><span>Служба контроля</span></div></div>
      <nav class="nav">${it(I.list, "Проверки", "index.html", active === "list")}${it(I.up, "Новая проверка", "index.html#upload", false)}${it(I.book, "Каталог правил", "rules.html", active === "rules")}${it(I.code, "API для жюри", "api.html", active === "api")}</nav>
      <div class="slab">Последние</div><div class="recent" id="recent"></div>
      <div class="sfoot"><div class="srow"><div class="lang">Рус</div>${themeBtn}</div><a class="help" href="help.html">${I.help}Как это работает</a></div></aside>`;
  }
  function topline(crumbs, health) {
    return `<header class="top"><span class="mtop"><a class="mark" href="index.html">${I.mark}</a></span>
      <div class="crumbs">${crumbs}</div><div class="spacer"></div>
      <div class="svc" id="svc"><span class="dotok"></span>${health || "Сервис работает"}</div></header>`;
  }
  function statusbar(parts, right) {
    const s = p => p.map(x => `<span>${x}</span>`).join('<span class="sep"></span>');
    return `<footer class="status"><span class="dotok"></span>${s(parts)}<span class="spacer"></span>${s(right || [])}</footer>`;
  }
  function shell(o) {
    return `<div class="app ${o.rail ? "rail" : ""} ${o.fixed ? "fixed" : ""}">${side(o.active, o.rail)}
      <div class="work">${topline(o.crumbs)}<main style="display:flex;flex-direction:column;min-height:0;min-width:0">${o.main}</main>${statusbar(o.st || [], o.str || [])}</div></div>`;
  }
  function head(o) {
    return `<section class="ph"><div class="ph1"><div style="min-width:0"><h1>${esc(o.title)}${o.tag || ""}</h1><div class="disc">${o.disc || ""}</div></div><div class="acts">${o.acts || ""}</div></div>
      <div class="metas">${(o.metas || []).map(([l, v]) => `<div class="m"><div class="lab">${l}</div><div class="num">${v}</div></div>`).join("")}${o.ring || ""}</div>
      ${o.prog != null ? `<div class="prog"><i style="width:${o.prog}%"></i></div>` : ""}${o.tabs ? `<nav class="tabs">${o.tabs}</nav>` : ""}</section>`;
  }
  const ring = (a, b, label) => { const p = b ? a / b : 0, C = 2 * Math.PI * 9; return `<div class="ring"><svg viewBox="0 0 22 22"><circle cx="11" cy="11" r="9" fill="none" stroke="var(--muted2)" stroke-width="3"/><circle cx="11" cy="11" r="9" fill="none" stroke="var(--text)" stroke-width="3" stroke-dasharray="${C * p} ${C}" transform="rotate(-90 11 11)"/></svg><div class="m"><div class="lab">${label}</div><div class="num" style="font-size:13px;font-weight:500">${a} из ${b}</div></div></div>`; };

  // ---------- общие вызовы ----------
  async function api(path) {
    const r = await fetch(path, { headers: H() });
    if (r.status === 401) { showKeyForm(); throw new Error("нужен ключ"); }
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json();
  }
  function showKeyForm() {
    document.getElementById("root").innerHTML = `<div style="max-width:420px;margin:80px auto;padding:24px;border:1px solid var(--line);border-radius:12px;background:var(--bg)">
      <div class="sbrand" style="padding:0;margin-bottom:12px"><span class="mark">${I.mark}</span>КассаКонтроль</div>
      <b>${KEY() ? "Ключ не подошёл — введите заново" : "Введите ключ доступа"}</b><div style="color:var(--text2);font-size:13px;margin:4px 0 12px">Тот же ключ, что в заголовке X-API-Key для API. Он сохранится в этом браузере.</div>
      <input id="keyIn" type="password" style="width:100%;height:36px;border:1px solid var(--line2);border-radius:8px;padding:0 10px;font:inherit;background:var(--bg);color:var(--text)">
      <div style="margin-top:12px"><span class="btn dark" id="keyOk">Войти</span></div></div>`;
    document.getElementById("keyOk").onclick = () => { try { localStorage.setItem("kk_key", document.getElementById("keyIn").value.trim()); } catch (e) {} location.reload(); };
    document.getElementById("keyIn").onkeydown = e => { if (e.key === "Enter") document.getElementById("keyOk").click(); };
    document.getElementById("keyIn").focus();
  }
  function bindCommon(root) {
    const b = root.querySelector("#themeBtn");
    if (b) b.onclick = () => { theme = theme === "dark" ? "light" : "dark"; try { localStorage.setItem("kk_theme", theme); } catch (e) {} if (theme === "dark") document.documentElement.setAttribute("data-theme", "dark"); else document.documentElement.removeAttribute("data-theme"); b.innerHTML = (theme === "dark" ? I.sun : I.moon) + (b.classList.contains("ritem") ? "Тема" : ""); };
  }
  async function fillRecent() {
    const el = document.getElementById("recent");
    if (!el) return;
    try {
      const { jobs } = await api("/api/v1/jobs");
      el.innerHTML = jobs.slice(0, 5).map(j => {
        const k = j.status === "done" ? (JSON.parse(j.progress_json || "{}"), "i") : j.status === "failed" ? "x" : "p";
        return `<a href="job.html?id=${j.id}">${sh(k)}${esc(j.filename)}<span class="mono">${j.finished_at ? new Date(j.finished_at * 1000).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }) : "…"}</span></a>`;
      }).join("");
    } catch (e) { /* нет ключа */ }
    api("/health").then(h => { const s = document.getElementById("svc"); if (s) s.innerHTML = `<span class="dotok"></span>Сервис работает · очередь ${h.queue} · v${h.version}`; }).catch(() => {});
  }

  // ---------- страница списка и загрузки ----------
  async function pageIndex() {
    const root = document.getElementById("root");
    const { jobs } = await api("/api/v1/jobs");
    const h = await api("/health").catch(() => ({}));
    const dec = id => { try { return JSON.parse(localStorage.getItem("kk_dec_" + id) || "{}"); } catch (e) { return {}; } };
    const rows = jobs.map(j => {
      const p = j.progress_json ? JSON.parse(j.progress_json) : null;
      let st = "", out = "", r = "—", g = "p";
      if (j.status === "done") {
        // кратко: число событий узнаем по ссылке; хранится в карточке
        st = `<span class="tag n" data-job="${j.id}">готово</span>`; out = `<a class="more" href="job.html?id=${j.id}">Открыть результат</a>`; g = "i";
      } else if (j.status === "failed") { st = `<span class="tag d">${sh("x")}Ошибка файла</span>`; out = esc(j.error || ""); g = "x"; }
      else { st = `<div class="minibar"><div class="mbar"><i style="width:${p ? Math.round(100 * p.frames_done / Math.max(1, p.frames_total)) : 5}%"></i></div>${p ? `этап ${p.stage} из ${p.stages}` : "в очереди"}</div>`; out = `<span style="color:var(--label)">${p ? esc(p.label) : "ждёт обработчика"}</span>`; g = "p"; }
      return `<tr data-id="${j.id}" data-g="${g}"><td class="f"><a href="job.html?id=${j.id}" style="color:inherit">${esc(j.filename)}</a><small>${j.id}</small></td><td class="m">${mb(j.size_bytes)}</td><td class="m">${dt(j.created_at)}</td><td class="st">${st}</td><td class="out">${out}</td><td class="dec">${r}</td></tr>`;
    }).join("");
    const main = `<div class="page">
      <div class="pgh"><div><div class="path">Рабочее пространство · служба внутреннего контроля</div><h1>Проверки видео</h1>
        <div class="metas" style="margin-top:10px">${[["Всего", jobs.length], ["Готово", jobs.filter(j => j.status === "done").length], ["В обработке", jobs.filter(j => j.status === "processing" || j.status === "queued").length], ["Очередь сервиса", h.queue ?? "—"]].map(([l, v]) => `<div class="m"><div class="lab">${l}</div><div class="num">${v}</div></div>`).join("")}</div></div>
        <div class="acts" style="margin-left:auto;display:flex;gap:8px"><a class="btn" href="rules.html">${I.book}Каталог правил</a><span class="btn dark" id="pick">${I.up}Загрузить видео</span></div></div>
      <div class="lst"><div style="display:flex;flex-direction:column;gap:16px;min-width:0">
        <div class="drop" id="drop"><div id="err"></div>
          <div class="dr1"><span class="dic">${I.up}</span><div><b>Перетащите видеозапись кассы сюда</b><span>.mov или .mp4 · до 200 МБ · звук не нужен · любой ракурс камеры · анализ 1–3 мин</span></div><span class="btn dark" id="pick2">Выбрать файл</span><input type="file" id="file" accept="video/*,.mov,.mp4" style="display:none"></div>
          <div class="steps5">${[["Загрузка", "видео остаётся на нашем сервере"], ["Кадры", "5 кадров в секунду"], ["Люди и предметы", "кассир, клиент, наличные, экран"], ["Правила", "по моментам: уход, вход, рабочее место"], ["Заключение", "кадры, норма, PDF и API"]].map(([a, b], i) => `<div><span class="n">${i + 1}</span><b>${a}</b>${b}</div>`).join("")}</div></div>
        <div class="chips" id="chips"><span class="chip on" data-g="all">Все <span class="c">${jobs.length}</span></span><span class="chip" data-g="d">${sh("d")}С событиями <span class="c">0</span></span><span class="chip" data-g="i">${sh("i")}Без нарушений <span class="c">${jobs.filter(j => j.status === "done").length}</span></span><span class="chip" data-g="p">${sh("p")}В обработке <span class="c">${jobs.filter(j => j.status === "processing" || j.status === "queued").length}</span></span><span class="chip" data-g="x">${sh("x")}Ошибки <span class="c">${jobs.filter(j => j.status === "failed").length}</span></span></div>
        <div class="tbl"><table><thead><tr><th>Файл</th><th>Размер</th><th>Загружен</th><th>Статус</th><th>Результат</th><th>Решения</th></tr></thead><tbody id="tb">${rows || `<tr><td colspan="6" style="color:var(--label);text-align:center;padding:24px">Проверок пока нет. Загрузите первое видео.</td></tr>`}</tbody></table></div>
      </div>
      <aside class="catp" id="catp"><div class="hd"><b>Что проверяет система</b><span>7 категорий и основание для каждой</span></div><div id="cats"></div>
        <div class="priv">${I.lock}<span>Видео обрабатывается на этом сервере и не уходит во внешние ИИ-сервисы. Лица не распознаются. Файл удаляется после анализа, результат хранится 24 часа.</span></div></aside></div></div>`;
    root.innerHTML = shell({ active: "list", crumbs: `<b>Проверки</b>`, main, st: ["Сервис работает", `очередь ${h.queue ?? "—"}`, `версия ${h.version || ""}`, "каталог правил 17.10.2026"], str: ["API: <b>/api/v1/analyze</b>", "Хранение результатов: 24 ч"] });
    bindCommon(root); fillRecent();
    // каталог правил в боковой карточке
    fetch("rules.json").then(r => r.json()).then(cat => {
      const byId = Object.fromEntries(cat.types.map(t => [t.id, t]));
      document.getElementById("cats").innerHTML = cat.categories.map((c, i) => { const t = byId[c.types[0]]; const d = cat.documents[t.source.doc]; return `<div class="ci"><span class="n">0${i + 1}</span><div><b>${esc(c.name)}</b><div class="ref">${esc(d.short)} · ${esc(t.source.point)}</div></div></div>`; }).join("");
    }).catch(() => {});
    // число событий и решений для готовых; счётчики чипов пересчитываются по мере ответов
    const recount = () => { const trs = [...root.querySelectorAll("#tb tr[data-id]")]; root.querySelectorAll("#chips .chip").forEach(c => { const g = c.dataset.g, el = c.querySelector(".c"); if (el) el.textContent = g === "all" ? trs.length : trs.filter(tr => tr.dataset.g === g).length; }); const on = root.querySelector("#chips .chip.on"); if (on && on.dataset.g !== "all") trs.forEach(tr => { tr.style.display = tr.dataset.g === on.dataset.g ? "" : "none"; }); };
    for (const j of jobs.filter(j => j.status === "done").slice(0, 30)) {
      api(`/api/v1/jobs/${j.id}/progress`).then(p => {
        const d = p.details || {}; const n = (d.findings || []).length; const tr = root.querySelector(`tr[data-id="${j.id}"]`); if (!tr) return;
        tr.querySelector(".st").innerHTML = n ? `<span class="tag d">${sh("d")}${n} ${n === 1 ? "событие" : n < 5 ? "события" : "событий"}</span>` : `<span class="tag i">${sh("i")}Не обнаружено</span>`;
        tr.dataset.g = n ? "d" : "i"; recount();
        tr.querySelector(".out").innerHTML = n ? (d.findings || []).slice(0, 2).map(f => `<div><span class="mono">${fmt(f.timecode_sec)}</span>${esc(f.type)}</div>`).join("") : `<span style="color:var(--label)">Проверено 7 категорий</span>`;
        const made = Object.keys(dec(j.id)).length; tr.querySelector(".dec").innerHTML = n ? `<span class="tag n">${made} из ${n}</span>` : "—";
      }).catch(() => {});
    }
    const pick = () => document.getElementById("file").click();
    document.getElementById("pick").onclick = pick; document.getElementById("pick2").onclick = pick;
    document.getElementById("file").onchange = e => upload(e.target.files[0]);
    const drop = document.getElementById("drop");
    drop.ondragover = e => { e.preventDefault(); drop.style.borderColor = "var(--sel)"; };
    drop.ondragleave = () => { drop.style.borderColor = ""; };
    drop.ondrop = e => { e.preventDefault(); drop.style.borderColor = ""; if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); };
    document.getElementById("chips").onclick = e => { const c = e.target.closest(".chip"); if (!c) return; root.querySelectorAll("#chips .chip").forEach(x => x.classList.toggle("on", x === c)); root.querySelectorAll("#tb tr").forEach(tr => { tr.style.display = c.dataset.g === "all" || tr.dataset.g === c.dataset.g ? "" : "none"; }); };
    if (location.hash === "#upload") drop.scrollIntoView();
    async function upload(file) {
      const err = document.getElementById("err");
      err.innerHTML = `<div class="errb" style="background:var(--muted);border-color:var(--line)"><span class="sh p"></span><div><b>Загружаем ${esc(file.name)} (${mb(file.size)})…</b><span>Не закрывайте страницу до окончания загрузки.</span></div></div>`;
      const fd = new FormData(); fd.append("file", file);
      try {
        const r = await fetch("/api/v1/analyze", { method: "POST", headers: H(), body: fd });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) { err.innerHTML = `<div class="errb">${I.warn}<div><b>${esc(body.detail || `Ошибка ${r.status}`)}</b><span>Нужна запись .mov или .mp4 до 200 МБ. Если снимали на телефон, отправьте как файл, а не как фото.</span></div></div>`; return; }
        location.href = `job.html?id=${body.job_id}`;
      } catch (e) { err.innerHTML = `<div class="errb">${I.warn}<div><b>Не удалось отправить файл</b><span>${esc(e.message)}</span></div></div>`; }
    }
  }

  // ---------- страница задачи ----------
  async function pageJob() {
    const id = qs.get("id");
    const root = document.getElementById("root");
    if (!id) { location.href = "index.html"; return; }
    let timer = null;
    async function tick() {
      let p;
      try { p = await api(`/api/v1/jobs/${id}/progress`); } catch (e) { if (/ключ/.test(e.message)) return; frame(`<h1 class="doc-h1">Проверка не найдена</h1><p class="doc-lead">Задачи с номером <code class="doc-code">${esc(id)}</code> нет: ссылка неверна или результат уже удалён (результаты хранятся 24 часа).</p><p style="color:var(--label);font-size:12.5px">Ответ сервера: ${esc(e.message)}</p><div><a class="btn dark" href="index.html">К списку проверок</a></div>`, { active: "list", crumbs: `<a href="index.html">Проверки</a><span class="sep">/</span><b>${esc(id)}</b>`, st: ["Задача не найдена"] }); return; }
      if (p.status === "processing") { renderProcessing(p); timer = setTimeout(tick, 2000); return; }
      if (p.status === "failed") { renderFailed(p); return; }
      const res = await api(`/api/v1/jobs/${id}`);
      renderResult(p, res);
    }
    tick();

    function renderProcessing(p) {
      const queued = !p.progress, ahead = p.queue_ahead || 0;
      const pr = p.progress || { stage: 1, stages: 5, label: "Видео в очереди", frames_done: 0, frames_total: 1, elapsed_sec: Math.max(0, Date.now() / 1000 - (p.created_at || Date.now() / 1000)) };
      const pc = Math.round(100 * pr.frames_done / Math.max(1, pr.frames_total));
      const stg = (n, name, d, k, tm, extra) => `<div class="stg ${k}"><span class="ic">${k === "done" ? I.ok : ""}</span><div><div class="eyebrow">Этап 0${n}</div><b>${name}</b><div class="d">${d}</div>${extra || ""}</div><span class="tm">${tm}</span></div>`;
      const names = [["Видео загружено", mb(p.size_bytes)], ["Файл проверен", "формат, длительность, поворот"], ["Люди и предметы в кадре", "5 кадров в секунду: кассир, клиент, наличные, экран"], ["Сопоставление с правилами", "7 категорий · каталог правил от 17.10.2026"], ["Кадры-доказательства и заключение", "1–3 кадра на событие, PDF и ответ API"]];
      const main = head({ title: p.filename, tag: `<span class="tag p">${sh("p")}${queued ? "В очереди" : `Анализ · этап ${pr.stage} из ${pr.stages}`}</span>`, disc: "Можно закрыть страницу: результат останется по этой ссылке.", acts: `<a class="btn dark" href="index.html#upload">${I.up}Новая проверка</a>`,
        metas: [["Размер", mb(p.size_bytes)], ["Загружено", dt(p.created_at)], ["Прошло", dur(pr.elapsed_sec)], ["Готово", queued ? (ahead ? `в очереди · впереди ${ahead}` : "в очереди") : `${pc} % · кадр ${pr.frames_done} из ${pr.frames_total}`], ["Предел", "4 мин на видео"]], prog: Math.max(2, pc),
        tabs: `<a class="on">${I.film}События <span class="c">…</span></a><a>${I.task}Категории <span class="c">7</span></a><a>${I.log}Журнал анализа</a><a>${I.code}Ответ API</a>` })
        + `<div class="body" style="flex:1"><section class="left"><div class="card view"><div class="evid"><div class="evh"><b>Найденные события</b><span class="tag n" style="margin-left:auto">появятся после этапа 4</span></div>
          <div class="pend"><b>Система просматривает видео</b><span>${queued ? (ahead ? `Видео в очереди: перед ним ещё ${ahead}. Обработка начнётся автоматически.` : "Видео в очереди, обработчик вот-вот начнёт.") : `${esc(pr.label)}: кадр ${pr.frames_done} из ${pr.frames_total}.`}<br>Обычно анализ занимает 1–3 минуты.</span><div class="skel" style="width:100%;max-width:420px"><i style="width:70%"></i><i style="width:92%"></i><i style="width:55%"></i></div></div></div></div></section>
        <aside class="rp"><div class="rph lab" style="grid-template-columns:1fr auto"><span>Ход анализа</span><span>Этап</span></div><div class="rpl"><div class="stages">
          ${names.map(([n, d], i) => stg(i + 1, n, d, i + 1 < pr.stage ? "done" : i + 1 === pr.stage ? "now" : "wait", i + 1 < pr.stage ? "✓" : i + 1 === pr.stage ? "…" : "—", i + 1 === pr.stage && pr.stage === 3 ? `<div class="mbar"><i style="width:${pc}%"></i></div><div class="d mono" style="font-size:11.5px;margin-top:5px">кадр ${pr.frames_done} / ${pr.frames_total}</div>` : "")).join("")}</div>
          <div class="linkbox">Результат будет доступен по ссылке:<div class="u">${location.host}/ui/job.html?id=${id}${I.copy}</div></div>
          <div class="note" style="padding:12px 16px">Если анализ не уложится в предел, сервис отдаст лучший частичный результат, а не «нарушений нет».</div></div></aside></div>`;
      root.innerHTML = shell({ rail: true, fixed: true, active: "list", crumbs: `<a href="index.html">Проверки</a><span class="sep">/</span><b>${esc(p.filename)}</b><span class="idchip">${id}</span>`, main, st: [queued ? "В очереди" : "Анализ идёт", `задача ${id}`, queued ? `впереди ${ahead}` : `кадр ${pr.frames_done} / ${pr.frames_total}`] });
      const u = root.querySelector(".linkbox .u");
      if (u) { u.style.cursor = "pointer"; u.title = "Скопировать ссылку"; u.onclick = () => { const link = location.origin + "/ui/job.html?id=" + id; const done = () => { u.firstChild.textContent = "Ссылка скопирована"; setTimeout(() => { u.firstChild.textContent = location.host + "/ui/job.html?id=" + id; }, 1500); }; if (navigator.clipboard) navigator.clipboard.writeText(link).then(done, () => {}); }; }
      bindCommon(root);
    }
    function renderFailed(p) {
      const main = head({ title: p.filename, tag: `<span class="tag d">${sh("x")}Не обработано</span>`, disc: "Это не означает отсутствия нарушений: файл не удалось проанализировать.", acts: `<a class="btn dark" href="index.html#upload">${I.up}Загрузить другое видео</a>`, metas: [["Размер", mb(p.size_bytes)], ["Загружено", dt(p.created_at)]] })
        + `<div class="page"><div class="errb">${I.warn}<div><b>${esc(p.error || "Файл не является видео или повреждён")}</b><span>Нужна запись .mov или .mp4. Если снимали на телефон, отправьте её как файл, а не как фото.</span></div></div></div>`;
      root.innerHTML = shell({ active: "list", crumbs: `<a href="index.html">Проверки</a><span class="sep">/</span><b>${esc(p.filename)}</b>`, main, st: ["Ошибка файла", `задача ${id}`] });
      bindCommon(root); fillRecent();
    }

    function renderResult(p, res) {
      const d = p.details || {}; const fs = d.findings || []; const W = d.width || 464, Hh = d.height || 848;
      const decKey = "kk_dec_" + id; let decisions = {}; try { decisions = JSON.parse(localStorage.getItem(decKey) || "{}"); } catch (e) {}
      let sel = +(qs.get("ev") || 0); if (sel >= fs.length) sel = 0;
      let tab = "events", flt = "all";
      const framesOf = i => (res.violations[i] || {}).evidence_frames || [];
      const low = f => f.confidence === "низкая";
      const groups = { d: fs.map((f, i) => [f, i]).filter(([f]) => !low(f)), w: fs.map((f, i) => [f, i]).filter(([f]) => low(f)) };

      function boxesHtml(f, t) {
        return (f.boxes || []).filter(b => Math.abs(b.t - t) <= 1.2).map(b => { const [x1, y1, x2, y2] = b.box; return `<div class="bx bx--${b.kind}" style="left:${100 * x1 / W}%;top:${100 * y1 / Hh}%;width:${100 * (x2 - x1) / W}%;height:${100 * (y2 - y1) / Hh}%"><span>${esc(b.label)}</span></div>`; }).join("");
      }
      function zoomHtml(f, frame) {
        const main = (f.boxes || []).find(b => b.kind === "obj") || (f.boxes || [])[0];
        if (!main || !frame) return "";
        const [x1, y1, x2, y2] = main.box; const cx = (x1 + x2) / 2, cy = (y1 + y2) / 2;
        const rw = Math.max(140, (x2 - x1) * 3), rh = rw * 1.25; const rx = Math.min(Math.max(0, cx - rw / 2), W - rw), ry = Math.min(Math.max(0, cy - rh / 2), Hh - rh);
        const Wv = 224, Hv = 280, s = Math.min(Wv / rw, Hv / rh);
        const bx = (f.boxes || []).filter(b => Math.abs(b.t - frame.timestamp_sec) <= 1.2).map(b => `<div class="bx bx--${b.kind}" style="left:${(b.box[0] - rx) * s}px;top:${(b.box[1] - ry) * s}px;width:${(b.box[2] - b.box[0]) * s}px;height:${(b.box[3] - b.box[1]) * s}px"><span>${esc(b.label)}</span></div>`).join("");
        return `<div class="zoom" style="width:${Wv}px;height:${Hv}px"><div class="inner" style="transform:translate(${-rx * s}px,${-ry * s}px) scale(${s})"><img src="data:image/jpeg;base64,${frame.image_base64}" style="width:${W}px;height:${Hh}px"></div>${bx}<span class="ovl bl">×${s.toFixed(1).replace(".", ",")} · место события</span></div>`;
      }
      function timelineHtml() {
        const dsec = d.duration_sec || 1; const step = dsec > 40 ? 15 : 5; const ticks = [];
        for (let t = 0; t <= dsec - step * 0.4; t += step) ticks.push(`<span style="left:${pct(t, dsec)}">${fmt(t)}</span>`);
        const strip = (d.strip || []).map(s => `<img src="data:image/jpeg;base64,${s.jpeg_base64}" title="${fmt(s.t)}">`).join("");
        const km = d.key_moment, kmT = km && km.times && km.times.length ? km.times : null;
        const pins = fs.length ? fs.map((f, i) => `<div class="pin" style="left:${pct(f.timecode_sec, dsec)};cursor:pointer" data-i="${i}">${sh(low(f) ? "w" : "d")}${i === sel ? `<em>${fmt(f.timecode_sec)}</em>` : ""}</div>`).join("")
          : km ? `<div class="pin" style="left:${pct(km.t, dsec)}"><span class="okc">${I.ok}</span><em>${fmt(km.t)}</em></div>` : "";
        const rng = fs.length ? fs.map(f => f.t_end ? `<div class="erng ${low(f) ? "w" : "d"}" style="left:${pct(f.timecode_sec, dsec)};width:${pct(Math.max(0.5, f.t_end - f.timecode_sec), dsec)}"></div>` : "").join("")
          : kmT ? `<div class="erng ok" style="left:${pct(kmT[0], dsec)};width:${pct(Math.max(0.5, kmT[kmT.length - 1] - kmT[0]), dsec)}"></div>` : "";
        const at = fs[sel] ? fs[sel].timecode_sec : km ? km.t : null;
        const okc = `<span style="display:inline-grid;place-items:center;width:14px;height:14px;border-radius:50%;background:var(--ok);color:#fff"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" style="width:9px;height:9px"><path d="M20 6 9 17l-5-5"/></svg></span>`;
        return `<div class="card tl"><div class="tlh"><b>Шкала видео</b><span class="hint">${fs.length ? "нажмите на значок, чтобы перейти к событию" : "✓ — ключевой момент записи"} · само видео удалено после анализа</span>
          <div class="leg">${fs.length ? `<span>${sh("d")}нарушение</span><span>${sh("w")}требует проверки</span>` : `<span>${okc}проверенный момент</span>`}</div></div>
          <div class="trk"><span class="lab">События</span><div class="etrack" id="etrack">${rng}${pins}</div><span class="lab">Кадры</span><div class="strip">${strip}${at != null ? `<div class="played" style="width:${pct(at, dsec)}"></div><div class="phead" style="left:${pct(at, dsec)}"></div>` : ""}</div></div>
          <div class="ruler">${ticks.join("")}</div>
          <div class="ctrls"><span class="cb" id="prevEv" title="Предыдущее событие">${I.prev}</span><span class="cb" id="nextEv" title="Следующее событие">${I.next}</span>
          <span class="clock"><b>${at != null ? fmt1(at) : "00:00,0"}</b> / ${fmt1(dsec)}</span><span class="keys"><span><span class="kbd">J</span><span class="kbd">L</span>событие</span></span></div></div>`;
      }
      function leftHtml() {
        if (!fs.length) {
          const km = d.key_moment, sm = d.samples || []; const mainS = sm[1] || sm[0];
          const player = mainS ? `<div class="player"><img src="data:image/jpeg;base64,${mainS.image_base64}"><span class="ovl tl">${fmt1(mainS.t)}</span></div>` : "";
          const frs = sm.length ? sm.map(s => `<figure><div class="th"><img src="data:image/jpeg;base64,${s.image_base64}"></div><figcaption><span class="mono">${fmt(s.t)}</span><span>${esc(s.caption)}</span></figcaption></figure>`).join("")
            : (d.strip || []).filter((_, i) => i % 8 === 2).slice(0, 3).map(s => `<figure><div class="th"><img src="data:image/jpeg;base64,${s.jpeg_base64}"></div><figcaption><span class="mono">${fmt(s.t)}</span><span>кадр записи</span></figcaption></figure>`).join("");
          const range = km && km.times ? `${fmt(km.times[0])}–${fmt(km.times[km.times.length - 1])}` : `${fmt(0)}–${fmt(d.duration_sec || 0)}`;
          const title = !km ? "Запись просмотрена целиком, признаков нарушений не найдено" : km.kind === "none" ? "Запись просмотрена целиком: людей у рабочего места не найдено" : `Ключевой момент: ${esc(km.title).toLowerCase()}`;
          return `<div class="card view">${player}<div class="evid"><div class="evh"><span class="mono" style="color:var(--ok)">${range}</span><b>${title}</b><span class="tag ok" style="margin-left:auto">${sh("ok")}Проверено</span></div>
            <div class="evcol"><div class="frames tall" style="max-width:${sm.length ? 470 : 520}px">${frs}</div>
            <div class="sig"><div class="lab" style="margin-bottom:4px">Что проверила система</div><table>${(d.checked || []).map(c => `<tr><td class="mono" style="${c.result === "not_checked" ? "" : "color:var(--ok)"}">${c.result === "found" ? "◆" : c.result === "not_checked" ? "—" : "✓"}</td><td>${esc(c.category)}: ${esc(c.note)}</td></tr>`).join("")}</table></div></div></div></div>` + timelineHtml();
        }
        const f = fs[sel]; const frs = framesOf(sel); const main = frs[0];
        return `<div class="card view"><div class="player">${main ? `<img src="data:image/jpeg;base64,${main.image_base64}">${boxesHtml(f, main.timestamp_sec)}` : ""}<span class="ovl tl">${fmt1(f.timecode_sec)}</span><span class="ovl tr">${low(f) ? "▲" : "◆"} ${sel + 1} / ${fs.length}</span></div>
          <div class="evid"><div class="evh"><span class="mono" style="${low(f) ? "color:var(--warnText)" : ""}">${fmt(f.timecode_sec)}</span><b>${esc(f.type)}</b><span class="tag ${low(f) ? "w" : "d"}">${sh(low(f) ? "w" : "d")}Уверенность: ${esc(f.confidence)}</span></div>
            <div class="evrow">${zoomHtml(f, main)}<div class="evcol"><div class="frames">${frs.map((x, k) => `<figure><div class="th ${k === 0 ? "ev" : ""}"><img src="data:image/jpeg;base64,${x.image_base64}">${k === 0 ? boxesHtml(f, x.timestamp_sec) : ""}</div><figcaption><span class="mono">${fmt(x.timestamp_sec)}</span><span>${k === 0 ? "событие" : x.timestamp_sec < f.timecode_sec ? "до" : "после"}</span></figcaption></figure>`).join("")}</div>
              <div class="sig"><div class="lab" style="margin-bottom:4px">Что заметила система</div><table>${(f.signals || []).map((s, i, a) => `<tr class="${i === a.length - 1 ? "hit" : ""}"><td class="mono">${esc(s.t)}</td><td>${esc(s.text)}</td></tr>`).join("")}</table></div></div></div></div></div>` + timelineHtml();
      }
      function evRow(f, i) {
        const k = low(f) ? "w" : "d"; const decn = decisions[i];
        const tag = decn ? `<span class="tag ${decn === "confirm" ? "d" : decn === "reject" ? "n" : "w"}">${decn === "confirm" ? "Подтверждено" : decn === "reject" ? "Не нарушение" : "Доп. проверка"}</span>` : `<span class="tag n">Не проверено</span>`;
        const r = f.rule || {};
        const seen = (f.description || "").split(r.interpretation || "\u0000")[0].trim();
        const det = i === sel ? `<div class="det">
          <div class="fld"><div class="lab">Что видно</div><p>${esc(seen)}</p></div>
          <div class="fld"><div class="lab">Норма</div><div class="norm"><div class="ref">${esc(r.doc)} · ${esc(r.point)}</div><q>«${esc(r.quote)}»</q><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc((r.url || "").replace("https://", ""))} ${I.ext}</a></div></div>
          <div class="fld"><div class="lab">Почему это может быть нарушением</div><p>${esc(r.interpretation)}</p></div>
          <div class="fld"><div class="lab">Чего не видно на записи</div><p style="color:var(--text2)">${esc(r.cannot_see)}</p></div>
          <div class="fld"><div class="lab">Что проверить</div><div class="todo">${I.task}<span>${esc(r.check)}</span></div>
            <div class="dec"><span class="btn dark sm" data-dec="confirm" data-i="${i}">${I.ok}Подтвердить</span><span class="btn sm" data-dec="reject" data-i="${i}">Не нарушение</span><span class="btn sm" data-dec="recheck" data-i="${i}">Нужна доп. проверка</span></div>
            <div class="note">Решение сохраняется в этом браузере и попадёт в заключение. Вывод системы сохранится рядом.</div></div></div>` : "";
        return `<div class="row ${i === sel ? "sel" : ""}" data-i="${i}" style="cursor:pointer"><span class="mono" style="color:${k === "w" ? "var(--warnText)" : "var(--dangerText)"}">${fmt(f.timecode_sec)}</span>
          <div><div class="t">${esc(f.type)}</div><div class="sub">${sh(k)}Уверенность ${esc(f.confidence)} · ${esc(r.point || "")}</div></div><div class="r">${tag}</div></div>${det}`;
      }
      function rightHtml() {
        if (tab === "categories" || !fs.length) {
          return `<div class="rph lab" style="grid-template-columns:1fr 104px"><span>Категория · результат</span><span style="text-align:right">Итог</span></div><div class="rpl">
            ${(d.checked || []).map(c => `<div class="row" style="grid-template-columns:1fr 112px"><div><div class="t" style="display:flex;gap:9px;align-items:flex-start"><span style="margin-top:2px">${c.result === "found" ? sh("d") : c.result === "not_checked" ? sh("n") : sh("ok")}</span>${esc(c.category)}</div><div class="sub" style="padding-left:23px">${esc(c.note)}</div></div><div class="r">${c.result === "found" ? '<span class="tag d">Найдено</span>' : c.result === "not_checked" ? '<span class="tag n">Не проверялось</span>' : c.result === "not_applicable" ? '<span class="tag n">Не применимо</span>' : '<span class="tag ok">Не обнаружено</span>'}</div></div>`).join("")}
            <div class="cat" style="color:var(--label);font-size:12.5px;border:0;align-items:flex-start">${I.lock.replace("<svg", '<svg style="width:14px;height:14px;flex:none;margin-top:3px"')}Система не проверяет то, чего не видно на видео: проводки, сверку, подлинность банкнот, документы клиента.</div></div>`;
        }
        if (tab === "log") {
          const sc = d.scene || {};
          return `<div class="rph lab" style="grid-template-columns:1fr"><span>Журнал анализа</span></div><div class="rpl"><div class="stages">
            ${[["Режим", `${esc(d.mode || "полный")} · ${d.fps || 5} к/с · ${d.frames_total} кадров`], ["Время анализа", dur(d.elapsed_sec || 0) + (d.timed_out ? " · предел исчерпан, частичный результат" : "")], ["Видео", [fmt(d.duration_sec), `${d.width}×${d.height}`, d.fps_src ? `${Math.round(d.fps_src)} к/с` : "", esc(codecName(d.codec))].filter(Boolean).join(" · ")], ["Кассир", sc.cashier_track != null ? `трек ${sc.cashier_track}, рост сидя ${sc.h_seated} px, стоя ${sc.h_stand} px` : "не найден"], ["Люди в кадре", (sc.tracks || []).map(t => `${t.role} ${fmt(t.t0)}–${fmt(t.t1)}`).join("; ") || "—"], ["Опорные предметы", Object.keys(sc.anchors || {}).map(ruObj).join(", ") || "—"], ["Заметки", (d.notes || []).join(" ") || "—"], ["Модель", `YOLOX-s (ONNX, Apache-2.0) + ByteTrack · конвейер v${esc(d.pipeline_version)}`]].map(([l, v]) => `<div class="fld"><div class="lab">${l}</div><p style="font-size:13px">${v}</p></div>`).join("")}</div></div>`;
        }
        if (tab === "api") {
          const short = JSON.parse(JSON.stringify(res)); (short.violations || []).forEach(v => v.evidence_frames.forEach(f => { f.image_base64 = f.image_base64.slice(0, 24) + "… (" + Math.round(f.image_base64.length * 3 / 4 / 1024) + " КБ)"; }));
          return `<div class="rph lab" style="grid-template-columns:1fr"><span>Ответ API · GET /api/v1/jobs/${id}</span></div><div class="rpl"><pre style="margin:0;padding:14px 16px;font:12px/18px var(--mono);white-space:pre-wrap;word-break:break-word">${esc(JSON.stringify(short, null, 2))}</pre>
            <div class="note" style="padding:0 16px 14px">Полный ответ с кадрами: <a class="more" id="dlJson">скачать JSON</a>. Поля ровно по §10 технического задания; кадры — JPEG в base64.</div></div>`;
        }
        const grp = (k, title, arr) => arr.length ? `<div class="grp">${sh(k)}${title} <span class="c">${arr.length}</span></div>${arr.map(([f, i]) => evRow(f, i)).join("")}` : "";
        const nd = (d.checked || []).filter(c => c.result !== "found");
        const vis = ([f, i]) => flt === "all" || (flt === "d" && !low(f)) || (flt === "w" && low(f)) || (flt === "n" && !decisions[i]);
        return `<div class="rph lab"><span>Время</span><span>Событие · основание</span><span style="text-align:right">Решение</span></div><div class="rpl">
          ${grp("d", "Нарушения", groups.d.filter(vis))}${grp("w", "Требуют проверки", groups.w.filter(vis))}${groups.d.filter(vis).length + groups.w.filter(vis).length ? "" : `<div class="cat" style="color:var(--label);border:0">Событий по выбранному фильтру нет</div>`}
          <div class="grp">${sh("ok")}Остальные категории <span class="c">${nd.length}</span></div>
          ${nd.map(c => `<div class="cat">${c.result === "not_checked" ? sh("n") : sh("ok")}${esc(c.category)}<span class="mono">${c.result === "not_checked" ? "не проверялось" : c.result === "not_applicable" ? "не применимо" : "не обнаружено"}</span></div>`).join("")}</div>`;
      }
      function render() {
        const n = fs.length, made = Object.keys(decisions).length;
        const tag = n ? `<span class="tag d">${sh("d")}Найдены признаки нарушений · ${n}</span>` : `<span class="tag i">${sh("i")}Нарушение не обнаружено</span>`;
        const disc = n ? "Это подсказка, а не вывод о нарушении — решение принимает проверяющий." : `Проверено ${fmt(d.duration_sec)} видео по 7 категориям. Это не гарантирует отсутствия нарушений — при необходимости просмотрите запись.`;
        const main = head({ title: p.filename, tag, disc, acts: `<a class="btn" href="report.html?id=${id}">${I.dl}Заключение PDF</a><a class="btn" id="dlJson2">JSON</a><a class="btn dark" href="index.html#upload">${I.up}Новая проверка</a>`,
          metas: [["Длительность", `${fmt(d.duration_sec)} <span style="color:var(--label)">(${(d.duration_sec || 0).toFixed(1).replace(".", ",")} с)</span>`], ["Формат", [`${d.width}×${d.height}`, d.fps_src ? `${Math.round(d.fps_src)} к/с` : "", esc(codecName(d.codec))].filter(Boolean).join(" · ")], ["Загружено", dt(p.created_at)], ["Анализ", dur(d.elapsed_sec || 0)], ["Модель", `<span class="mono" style="font-size:12.5px">v${esc(d.pipeline_version)} · правила 17.10.2026</span>`]],
          ring: n ? ring(made, n, "Решения") : "",
          tabs: [["events", I.film, "События", n], ["categories", I.task, "Категории", 7], ["log", I.log, "Журнал анализа", ""], ["api", I.code, "Ответ API", ""]].map(([k, ic, t, c]) => `<a class="${tab === k ? "on" : ""}" data-tab="${k}" style="cursor:pointer">${ic}${t} ${c !== "" ? `<span class="c">${c}</span>` : ""}</a>`).join("") })
          + (n && tab === "events" ? `<div class="bar">${[["all", "", "Все события", n], ["d", sh("d"), "Нарушения", groups.d.length], ["w", sh("w"), "Требуют проверки", groups.w.length], ["n", sh("n"), "Без решения", n - made]].map(([k, ic, t, c]) => `<span class="chip ${flt === k ? "on" : ""}" data-f="${k}" style="cursor:pointer">${ic}${t} <span class="c">${c}</span></span>`).join("")}</div>` : "")
          + `<div class="body" style="flex:1"><section class="left">${leftHtml()}</section><aside class="rp">${rightHtml()}</aside></div>`;
        root.innerHTML = shell({ rail: true, fixed: true, active: "list", crumbs: `<a href="index.html">Проверки</a><span class="sep">/</span><b>${esc(p.filename)}</b><span class="idchip">${id}</span>`, main,
          st: [`Анализ завершён ${dt(p.created_at + (d.elapsed_sec || 0))}`, `задача ${id}`, `${d.frames_total} кадров · ${d.fps || 5} к/с`, `модель v${esc(d.pipeline_version)}`, "каталог правил 17.10.2026"], str: [`Событий: <b>${n}</b>`, `Решений: <b>${made} из ${n}</b>`, `режим ${esc(d.mode || "полный")}`] });
        bindCommon(root);
        root.querySelectorAll("[data-tab]").forEach(a => a.onclick = () => { tab = a.dataset.tab; render(); });
        root.querySelectorAll("[data-f]").forEach(c => c.onclick = () => { flt = c.dataset.f; render(); });
        root.querySelectorAll(".row[data-i]").forEach(r => r.onclick = e => { if (e.target.closest("[data-dec]") || e.target.closest("a")) return; sel = +r.dataset.i; tab = "events"; render(); });
        root.querySelectorAll("[data-dec]").forEach(b => b.onclick = () => { decisions[b.dataset.i] = b.dataset.dec; try { localStorage.setItem(decKey, JSON.stringify(decisions)); } catch (e) {} render(); });
        root.querySelectorAll(".pin[data-i]").forEach(pn => pn.onclick = () => { sel = +pn.dataset.i; render(); });
        const pe = root.querySelector("#prevEv"), ne = root.querySelector("#nextEv");
        if (pe) pe.onclick = () => { if (n) { sel = (sel - 1 + n) % n; render(); } };
        if (ne) ne.onclick = () => { if (n) { sel = (sel + 1) % n; render(); } };
        const dl = () => { const blob = new Blob([JSON.stringify(res, null, 2)], { type: "application/json" }); const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `${id}.json`; a.click(); };
        const d1 = root.querySelector("#dlJson"), d2 = root.querySelector("#dlJson2"); if (d1) d1.onclick = dl; if (d2) d2.onclick = dl;
      }
      document.onkeydown = e => { if (e.key === "j" || e.key === "J") { if (fs.length) { sel = (sel - 1 + fs.length) % fs.length; render(); } } if (e.key === "l" || e.key === "L") { if (fs.length) { sel = (sel + 1) % fs.length; render(); } } };
      render();
    }
  }

  // ---------- заключение (печать в PDF) ----------
  async function pageReport() {
    const id = qs.get("id"); const root = document.getElementById("root");
    const p = await api(`/api/v1/jobs/${id}/progress`); const res = await api(`/api/v1/jobs/${id}`);
    const d = p.details || {}; const fs = d.findings || []; const W = d.width || 464, Hh = d.height || 848;
    let decisions = {}; try { decisions = JSON.parse(localStorage.getItem("kk_dec_" + id) || "{}"); } catch (e) {}
    const decText = i => ({ confirm: "Подтверждено проверяющим", reject: "Не нарушение (решение проверяющего)", recheck: "Нужна дополнительная проверка" }[decisions[i]] || "решение не принято");
    const low = f => f.confidence === "низкая";
    const hdr = (n, tot) => `<div class="hdr"><span class="mark">${I.mark}</span><b>КассаКонтроль</b><span class="g">Заключение по видеозаписи</span><span class="r"><span>№ ${id.toUpperCase()}</span><span>Стр. ${n} / ${tot}</span></span></div>`;
    const ftr = `<div class="ftr"><span>Сформировано автоматически системой анализа видео КассаКонтроль v${esc(d.pipeline_version)}, ${dt(p.created_at + (d.elapsed_sec || 0))}.<br>Вспомогательный материал для проверки; не является заключением о дисциплинарном проступке или правонарушении.</span><span class="mono">${id}</span></div>`;
    const meta = `<div class="meta c4">${[["Файл", `${esc(p.filename)} · ${mb(p.size_bytes)}`], ["Длительность", `${fmt(d.duration_sec)} (${(d.duration_sec || 0).toFixed(1).replace(".", ",")} с)`], ["Формат", [`${d.width}×${d.height}`, d.fps_src ? `${Math.round(d.fps_src)} к/с` : "", esc(codecName(d.codec))].filter(Boolean).join(" · ")], ["Задача", id, 1], ["Дата анализа", dt(p.created_at + (d.elapsed_sec || 0))], ["Время анализа", dur(d.elapsed_sec || 0)], ["Модель", `v${esc(d.pipeline_version)} · YOLOX-s`, 1], ["Каталог правил", "от 17.10.2026", 1]].map(([l, v, m]) => `<div><div class="lab">${l}</div><div class="v ${m ? "mono" : ""} num">${v}</div></div>`).join("")}</div>`;
    const catTbl = `<div class="tbox"><table class="t"><thead><tr><th style="width:8mm">№</th><th>Категория</th><th style="text-align:right">Результат</th></tr></thead><tbody>${(d.checked || []).map((c, i) => `<tr><td class="mono">0${i + 1}</td><td style="font-size:9pt">${esc(c.category)}<div style="font-size:7.8pt;line-height:1.35;color:var(--label)">${esc(c.note)}</div></td><td style="text-align:right">${c.result === "found" ? `<span class="tag d"><span class="sh d"></span>находка</span>` : c.result === "not_checked" ? `<span class="tag n">не проверялось</span>` : c.result === "not_applicable" ? `<span class="tag n">не применимо</span>` : `<span class="tag ok">${sh("ok")}не обнаружено</span>`}</td></tr>`).join("")}</tbody></table></div>`;
    const limits = `<ul class="lim"><li>Анализируется только изображение: звук, проводки, кассовый журнал, сверка и подлинность банкнот не проверяются.</li><li>Лица не распознаются; люди различаются по роли и положению в кадре (кассир, клиент, посетитель).</li><li>В этой версии не проверяются: состояние сейфа и ключа, закрытие двери, порядок пересчёта и предъявление документа — для них нужен отдельный детектор.</li><li>Ссылки на нормы берутся из каталога правил, сверенного с adilet.zan.kz, и не генерируются моделью.</li>${d.timed_out ? "<li>Анализ не уложился в предел времени: результат частичный.</li>" : ""}</ul>`;
    const pages = [];
    const total = fs.length ? fs.length + 2 : 1;
    if (!fs.length) {
      const sm = d.samples || [], km = d.key_moment;
      const cleanFigs = sm.length ? `<h2><span class="n">01</span>${km && km.kind !== "none" ? `Ключевой момент: ${esc(km.title).toLowerCase()}` : "Кадры записи"}</h2><div class="figs" style="grid-template-columns:repeat(3,1fr)">${sm.map((s, k) => `<figure><div class="ph" style="height:58mm"><img src="data:image/jpeg;base64,${s.image_base64}"><span class="ts">${fmt(s.t)}</span></div><figcaption><span class="mono">Рис. ${k + 1} · ${fmt(s.t)}</span><span>${esc(s.caption)}</span></figcaption></figure>`).join("")}</div>` : "";
      const n0 = sm.length ? 1 : 0;
      pages.push(`<section class="page">${hdr(1, 1)}<div style="margin-top:4.5mm"><div class="eyebrow">Заключение · автоматическая проверка видеозаписи кассы</div><h1>Признаки нарушений не обнаружены</h1><div class="sub">по видеозаписи ${esc(p.filename)}, проверка от ${dt(p.created_at).split(",")[0]}</div></div>${meta}
        <div class="verdict i"><span class="vic"><span class="sh i"></span></span><div><b>Нарушение не обнаружено</b><p>Проверено ${fmt(d.duration_sec)} видео по 7 категориям, признаков не найдено. Это не гарантирует отсутствия нарушений — при необходимости просмотрите запись.</p></div></div>
        ${cleanFigs}<h2><span class="n">0${1 + n0}</span>Проверенные категории</h2>${catTbl}<h2><span class="n">0${2 + n0}</span>Ограничения метода</h2>${limits}
        <div class="sign" style="grid-template-columns:1fr 1fr 1fr"><div class="line">Проверяющий<i></i></div><div class="line">Подпись<i></i></div><div class="line">Дата<i></i></div></div>${ftr}</section>`);
    } else {
      pages.push(`<section class="page">${hdr(1, total)}<div style="margin-top:4.5mm"><div class="eyebrow">Заключение · автоматическая проверка видеозаписи кассы</div><h1>Признаки возможных нарушений кассовой дисциплины</h1><div class="sub">по видеозаписи ${esc(p.filename)}, проверка от ${dt(p.created_at).split(",")[0]}</div></div>${meta}
        <div class="verdict"><span class="vic"><span class="sh d"></span></span><div><b>Обнаружены признаки возможных нарушений</b><p>Заключение — вспомогательный материал. Оно не является выводом о нарушении; решение по каждой находке принимает проверяющий.</p></div><div class="kp"><div><div class="lab">Находок</div><div class="v">${fs.length}</div></div><div><div class="lab">Решений</div><div class="v">${Object.keys(decisions).length}/${fs.length}</div></div></div></div>
        <h2><span class="n">01</span>Сводка</h2><div class="tbox"><table class="t"><thead><tr><th>№</th><th>Время</th><th>Тип</th><th>Уверенность</th><th>Основание</th><th>Решение</th></tr></thead><tbody>${fs.map((f, i) => `<tr><td class="mono">${i + 1}</td><td class="mono">${fmt(f.timecode_sec)}</td><td style="font-weight:500">${esc(f.type)}</td><td><span class="tag ${low(f) ? "w" : "d"}"><span class="sh ${low(f) ? "w" : "d"}"></span>${esc(f.confidence)}</span></td><td class="ref">${esc((f.rule || {}).doc || "")} · ${esc((f.rule || {}).point || "")}</td><td><span class="tag n">${decisions[i] ? decText(i).split(" ")[0] : "не принято"}</span></td></tr>`).join("")}</tbody></table></div>
        <h2><span class="n">02</span>Проверенные категории</h2>${catTbl}${ftr}</section>`);
      fs.forEach((f, i) => {
        const frs = (res.violations[i] || {}).evidence_frames || []; const r = f.rule || {};
        const seen = (f.description || "").split(r.interpretation || "\u0000")[0].trim();
        const main = frs[0]; const mb_ = (f.boxes || []).find(b => b.kind === "obj") || (f.boxes || [])[0];
        let zoom = "";
        if (main && mb_) { const [x1, y1, x2, y2] = mb_.box; const cx = (x1 + x2) / 2, cy = (y1 + y2) / 2; const rw = Math.max(140, (x2 - x1) * 3), rh = rw * 1.25; const rx = Math.min(Math.max(0, cx - rw / 2), W - rw), ry = Math.min(Math.max(0, cy - rh / 2), Hh - rh); const Wv = 190, Hv = 234, s = Math.min(Wv / rw, Hv / rh);
          zoom = `<figure><div class="ph zoom" style="height:${Hv}px"><div class="inner" style="transform:translate(${-rx * s}px,${-ry * s}px) scale(${s})"><img src="data:image/jpeg;base64,${main.image_base64}" style="width:${W}px;height:${Hh}px"></div>${(f.boxes || []).filter(b => Math.abs(b.t - main.timestamp_sec) <= 1.2).map(b => `<div class="bx bx--${b.kind}" style="left:${(b.box[0] - rx) * s}px;top:${(b.box[1] - ry) * s}px;width:${(b.box[2] - b.box[0]) * s}px;height:${(b.box[3] - b.box[1]) * s}px"><span>${esc(b.label)}</span></div>`).join("")}<span class="ts">${fmt(main.timestamp_sec)}</span></div><figcaption><span class="mono">Рис. ${i + 1}.1 · ${fmt(main.timestamp_sec)}</span>Фрагмент кадра, увеличено</figcaption></figure>`; }
        const figs = frs.map((x, k) => `<figure><div class="ph ${k === 0 ? "ev" : ""}"><img src="data:image/jpeg;base64,${x.image_base64}">${k === 0 ? (f.boxes || []).filter(b => Math.abs(b.t - x.timestamp_sec) <= 1.2).map(b => `<div class="bx bx--${b.kind}" style="left:${100 * b.box[0] / W}%;top:${100 * b.box[1] / Hh}%;width:${100 * (b.box[2] - b.box[0]) / W}%;height:${100 * (b.box[3] - b.box[1]) / Hh}%"><span>${esc(b.label)}</span></div>`).join("") : ""}<span class="ts">${fmt(x.timestamp_sec)}</span></div><figcaption><span class="mono">Рис. ${i + 1}.${k + 2} · ${fmt(x.timestamp_sec)}</span>${k === 0 ? "Событие" : x.timestamp_sec < f.timecode_sec ? "До" : "После"}</figcaption></figure>`).join("");
        pages.push(`<section class="page">${hdr(i + 2, total)}<h2><span class="n">0${i + 3}</span>Находка ${i + 1}. ${esc(f.type)}<span class="x"><span class="tag ${low(f) ? "w" : "d"}"><span class="sh ${low(f) ? "w" : "d"}"></span>${low(f) ? "Требует проверки" : "Нарушение"}</span></span></h2>
          <div class="fhead"><span class="tag n mono">${fmt(f.timecode_sec)} · ${(+f.timecode_sec).toFixed(1).replace(".", ",")} с</span><span class="tag n">Уверенность: ${esc(f.confidence)}</span><span class="tag n">${esc(r.point || "")}</span></div>
          <div class="figs">${zoom}${figs}</div>
          <div class="att"><div class="r"><span class="lab">Наблюдение</span><p>${esc(seen)}</p></div>
            <div class="r"><span class="lab">Хронология</span><div class="chron">${(f.signals || []).map((s, k, a) => `<span class="mono ${k === a.length - 1 ? "hit" : ""}">${esc(s.t)}</span><span class="${k === a.length - 1 ? "hit" : ""}">${esc(s.text)}</span>`).join("")}</div></div>
            <div class="r"><span class="lab">Критерий</span><div class="quote">«${esc(r.quote)}»<div class="ref">${esc(r.doc)} · ${esc(r.point)}</div><div class="url">${esc((r.url || "").replace("https://", ""))}</div></div></div>
            <div class="r"><span class="lab">Возможное значение</span><p>${esc(r.interpretation)}</p></div>
            <div class="r"><span class="lab">Ограничения</span><p style="color:var(--text2)">${esc(r.cannot_see)}</p></div>
            <div class="r"><span class="lab">Рекомендация</span><div class="rec">${esc(r.check)}</div></div></div>
          <div class="sign"><div class="opts"><span class="lab">Решение проверяющего</span>${["confirm|Подтверждаю", "reject|Не нарушение", "recheck|Нужна доп. проверка"].map(o => { const [k, t] = o.split("|"); return `<span class="cbx"><i style="${decisions[i] === k ? "background:var(--text)" : ""}"></i>${t}</span>`; }).join("")}</div><div class="line">Комментарий<i></i></div><div class="line">Ф. И. О.<i></i></div><div class="line">Подпись<i></i></div><div class="line">Дата<i></i></div></div>${ftr}</section>`);
      });
      pages.push(`<section class="page">${hdr(total, total)}<h2 style="margin-top:6mm"><span class="n">0${fs.length + 3}</span>Как проводился анализ</h2>
        <div class="tbox"><table class="t"><thead><tr><th style="width:16mm">Этап</th><th>Что делалось</th><th>Результат</th></tr></thead><tbody>
          <tr><td class="mono">01</td><td>Приём файла</td><td>${mb(p.size_bytes)} · ${esc(p.filename)}</td></tr><tr><td class="mono">02</td><td>Проверка файла</td><td>${esc(codecName(d.codec))} · ${d.width}×${d.height} · ${(d.duration_sec || 0).toFixed(1).replace(".", ",")} с</td></tr>
          <tr><td class="mono">03</td><td>Поиск людей и предметов: ${d.fps || 5} кадров в секунду (YOLOX-s, ByteTrack)</td><td>${d.frames_total} кадров · ${((d.scene || {}).tracks || []).length} человек в кадре</td></tr><tr><td class="mono">04</td><td>Сопоставление с каталогом правил</td><td>7 категорий · ${fs.length} находок · режим «${esc(d.mode || "полный")}»</td></tr>
          <tr><td class="mono">05</td><td>Кадры-доказательства и заключение</td><td>${fs.reduce((a, f) => a + ((res.violations[fs.indexOf(f)] || {}).evidence_frames || []).length, 0)} кадров извлечены из исходного файла без изменений · ${dur(d.elapsed_sec || 0)}</td></tr></tbody></table></div>
        <div class="meta" style="margin-top:3.5mm">${[["Обработка", "на сервере команды, без внешних ИИ-сервисов"], ["Модели", "открытые, локальные, лицензии Apache-2.0 / MIT"], ["Лица", "не распознаются"], ["Хранение видео", "удаляется сразу после анализа"], ["Хранение результата", "24 часа"], ["Повторяемость", "тот же файл и та же версия дают тот же результат"]].map(([l, v]) => `<div><div class="lab">${l}</div><div class="v" style="font-size:8.6pt">${v}</div></div>`).join("")}</div>
        <h2><span class="n">0${fs.length + 4}</span>Ограничения метода</h2>${limits}
        <h2><span class="n">0${fs.length + 5}</span>Итог проверки</h2><div class="tbox"><table class="t"><thead><tr><th>Находка</th><th>Время</th><th>Решение проверяющего</th></tr></thead><tbody>${fs.map((f, i) => `<tr><td>${i + 1}. ${esc(f.type)}</td><td class="mono">${fmt(f.timecode_sec)}</td><td>${decText(i)}</td></tr>`).join("")}</tbody></table></div>
        <div class="sign" style="grid-template-columns:1fr 1fr"><div class="line">Проверяющий (Ф. И. О.)<i></i></div><div class="line">Подпись<i></i></div><div class="line">Руководитель<i></i></div><div class="line">Дата<i></i></div></div>${ftr}</section>`);
    }
    root.innerHTML = `<div class="bar-print"><a class="btn" href="job.html?id=${id}">← К результату</a><span class="btn dark" onclick="window.print()">${I.dl}Скачать PDF</span><span style="color:#555;font-size:13px">В окне печати выберите «Сохранить как PDF», формат A4.</span></div>` + pages.join("");
    document.title = `Заключение ${id} — КассаКонтроль`;
  }

  // Общий каркас для простых страниц (каталог правил, помощь, API): боковая панель + верхняя строка.
  function frame(main, o) {
    const root = document.getElementById("root");
    root.innerHTML = shell({ active: o.active, crumbs: o.crumbs, main: `<div class="page" style="max-width:${o.width || "1100px"};width:100%">${main}</div>`,
      st: o.st || ["Сервис работает", "каталог правил 17.10.2026"], str: o.str || [] });
    bindCommon(root); fillRecent();
  }

  window.KK = { pageIndex, pageJob, pageReport, api, fillRecent, frame, sh, I, esc };
})();
