// Accessible Bulgarian calendar picker (Monday-first, DD.MM.YYYY).
// "Today" and the earliest allowed date come from the server (Europe/Sofia), never the browser clock.
// The server validates the chosen date again; this component only makes valid choices easy.
(function () {
  const MONTHS = ["Януари", "Февруари", "Март", "Април", "Май", "Юни", "Юли", "Август", "Септември", "Октомври", "Ноември", "Декември"];
  const WEEKDAYS = [["Пн", "Понеделник"], ["Вт", "Вторник"], ["Ср", "Сряда"], ["Чт", "Четвъртък"], ["Пт", "Петък"], ["Сб", "Събота"], ["Нд", "Неделя"]];
  const DAY = 864e5;

  const pad = (n) => String(n).padStart(2, "0");
  const parse = (iso) => { const [y, m, d] = iso.split("-").map(Number); return { y, m, d }; };
  const iso = (o) => `${o.y}-${pad(o.m)}-${pad(o.d)}`;
  const fmt = (o) => `${pad(o.d)}.${pad(o.m)}.${o.y}`;
  const ts = (o) => Date.UTC(o.y, o.m - 1, o.d);
  const fromTs = (t) => { const x = new Date(t); return { y: x.getUTCFullYear(), m: x.getUTCMonth() + 1, d: x.getUTCDate() }; };
  const addDays = (o, n) => fromTs(ts(o) + n * DAY);
  const daysIn = (y, m) => new Date(Date.UTC(y, m, 0)).getUTCDate();
  const mondayIndex = (o) => (new Date(ts(o)).getUTCDay() + 6) % 7;
  const monthKey = (o) => o.y * 12 + o.m;

  function init(root) {
    const today = parse(root.dataset.today);
    const min = parse(root.dataset.min);
    const hidden = root.querySelector('input[type="hidden"]');
    const trigger = root.querySelector(".datepicker__trigger");
    const valueEl = root.querySelector(".datepicker__value");
    const pop = root.querySelector(".datepicker__pop");
    const title = root.querySelector(".datepicker__title");
    const grid = root.querySelector(".datepicker__grid");
    const prevBtn = root.querySelector('[data-nav="-1"]');
    const nextBtn = root.querySelector('[data-nav="1"]');

    let selected = parse(hidden.value || root.dataset.today);
    let view = { y: selected.y, m: selected.m, d: 1 };
    let focus = selected;
    const initial = selected;

    const clamp = (o) => (ts(o) < ts(min) ? min : ts(o) > ts(today) ? today : o);
    const inRange = (o) => ts(o) >= ts(min) && ts(o) <= ts(today);

    // When many months are selectable, replace the static title with month + year selects for fast jumping.
    const spanMonths = monthKey(today) - monthKey(min);
    let monSel = null, yearSel = null;
    if (spanMonths > 2) {
      let years = "";
      for (let y = today.y; y >= min.y; y--) years += `<option value="${y}">${y}</option>`;
      title.innerHTML =
        `<select class="datepicker__sel" aria-label="Месец">${MONTHS.map((m, i) => `<option value="${i + 1}">${m}</option>`).join("")}</select>` +
        `<select class="datepicker__sel" aria-label="Година">${years}</select>`;
      [monSel, yearSel] = title.querySelectorAll("select");
      const jump = () => {
        let v = { y: Number(yearSel.value), m: Number(monSel.value), d: 1 };
        if (monthKey(v) < monthKey(min)) v = { y: min.y, m: min.m, d: 1 };
        if (monthKey(v) > monthKey(today)) v = { y: today.y, m: today.m, d: 1 };
        view = v;
        render();
      };
      monSel.addEventListener("change", jump);
      yearSel.addEventListener("change", jump);
    }

    function render() {
      if (monSel) {
        yearSel.value = view.y;
        monSel.value = view.m;
        [...monSel.options].forEach((o) => {
          const k = view.y * 12 + Number(o.value);
          o.disabled = k < monthKey(min) || k > monthKey(today);
        });
      } else {
        title.textContent = `${MONTHS[view.m - 1]} ${view.y}`;
      }
      prevBtn.disabled = monthKey(view) <= monthKey(min);
      nextBtn.disabled = monthKey(view) >= monthKey(today);
      // roving tabindex target: focus date if visible, else selected, else first selectable day
      let target = monthKey(focus) === monthKey(view) && inRange(focus) ? focus : null;
      if (!target && monthKey(selected) === monthKey(view)) target = selected;
      if (!target) {
        for (let d = 1; d <= daysIn(view.y, view.m); d++) {
          const o = { y: view.y, m: view.m, d };
          if (inRange(o)) { target = o; break; }
        }
      }
      focus = target || focus;

      let html = "<div class='datepicker__row' role='row'>" + WEEKDAYS.map(([s, l]) => `<span class='datepicker__wd' role='columnheader' aria-label='${l}'>${s}</span>`).join("") + "</div>";
      const lead = mondayIndex({ y: view.y, m: view.m, d: 1 });
      const total = daysIn(view.y, view.m);
      const cells = [];
      for (let i = 0; i < lead; i++) cells.push("<span class='datepicker__blank' role='gridcell'></span>");
      for (let d = 1; d <= total; d++) {
        const o = { y: view.y, m: view.m, d };
        const ok = inRange(o);
        const isSel = ts(o) === ts(selected);
        const isToday = ts(o) === ts(today);
        const cls = "datepicker__day" + (isSel ? " is-selected" : "") + (isToday ? " is-today" : "");
        const label = `${d} ${MONTHS[view.m - 1].toLowerCase()} ${view.y}${isToday ? ", днес" : ""}`;
        cells.push(
          `<button type="button" role="gridcell" class="${cls}" data-iso="${iso(o)}" aria-label="${label}"` +
          `${isSel ? ' aria-selected="true"' : ""}${isToday ? ' aria-current="date"' : ""}` +
          `${ok ? "" : " disabled"} tabindex="${target && ts(o) === ts(target) ? 0 : -1}">${d}</button>`
        );
      }
      for (let i = 0; i < cells.length; i += 7) html += "<div class='datepicker__row' role='row'>" + cells.slice(i, i + 7).join("") + "</div>";
      grid.innerHTML = html;
    }

    function focusDay() {
      const el = grid.querySelector(`[data-iso="${iso(focus)}"]`);
      if (el) el.focus();
    }

    function isOpen() { return pop.classList.contains("is-open"); }

    function open() {
      view = { y: selected.y, m: selected.m, d: 1 };
      focus = selected;
      render();
      pop.classList.add("is-open");
      trigger.setAttribute("aria-expanded", "true");
      focusDay();
    }

    function close(returnFocus) {
      if (!isOpen()) return;
      pop.classList.remove("is-open");
      trigger.setAttribute("aria-expanded", "false");
      if (returnFocus) trigger.focus();
    }

    function select(o, returnFocus = true) {
      if (!inRange(o)) return;
      selected = o;
      hidden.value = iso(o);
      valueEl.textContent = fmt(o);
      // let the form clear any previous error for this field
      hidden.dispatchEvent(new Event("input", { bubbles: true }));
      close(returnFocus);
    }

    function moveFocus(o) {
      focus = clamp(o);
      view = { y: focus.y, m: focus.m, d: 1 };
      render();
      focusDay();
    }

    trigger.addEventListener("click", () => (isOpen() ? close(false) : open()));
    trigger.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" && !isOpen()) { e.preventDefault(); open(); }
    });

    [prevBtn, nextBtn].forEach((btn) =>
      btn.addEventListener("click", () => {
        const delta = Number(btn.dataset.nav);
        const t = new Date(Date.UTC(view.y, view.m - 1 + delta, 1));
        view = { y: t.getUTCFullYear(), m: t.getUTCMonth() + 1, d: 1 };
        render();
      })
    );

    root.querySelector(".datepicker__today").addEventListener("click", () => select(today));

    grid.addEventListener("click", (e) => {
      const b = e.target.closest(".datepicker__day");
      if (b && !b.disabled) select(parse(b.dataset.iso));
    });

    grid.addEventListener("keydown", (e) => {
      const cur = e.target.closest(".datepicker__day");
      if (!cur) return;
      const o = parse(cur.dataset.iso);
      const step = {
        ArrowLeft: () => addDays(o, -1), ArrowRight: () => addDays(o, 1),
        ArrowUp: () => addDays(o, -7), ArrowDown: () => addDays(o, 7),
        Home: () => addDays(o, -mondayIndex(o)), End: () => addDays(o, 6 - mondayIndex(o)),
        PageUp: () => fromTs(Date.UTC(o.y, o.m - 2, Math.min(o.d, daysIn(o.y, o.m - 1 || 12)))),
        PageDown: () => fromTs(Date.UTC(o.y, o.m, Math.min(o.d, daysIn(o.y, o.m + 1)))),
      }[e.key];
      if (step) { e.preventDefault(); moveFocus(step()); }
    });

    pop.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { e.stopPropagation(); close(true); }
    });
    root.addEventListener("focusout", (e) => {
      if (e.relatedTarget && !root.contains(e.relatedTarget)) close(false);
    });
    document.addEventListener("pointerdown", (e) => { if (!root.contains(e.target)) close(false); });

    // "Попълни нов отчет" resets the form: go back to today's date.
    const form = root.closest("form");
    if (form) form.addEventListener("reset", () => setTimeout(() => {
      selected = initial; hidden.value = iso(initial); valueEl.textContent = fmt(initial); close(false);
    }, 0));
  }

  document.querySelectorAll(".datepicker").forEach(init);
})();
