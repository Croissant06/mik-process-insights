// Collects the form, posts JSON, and renders the backend's validation errors inline.
// All real validation happens on the server; this file only shows its result.
(function () {
  const form = document.getElementById("report");
  const formView = document.getElementById("form-view");
  const successView = document.getElementById("success-view");
  const submitBtn = document.getElementById("submit");
  const submitLabel = document.getElementById("submit-label");
  const banner = document.getElementById("form-error");
  const LABEL = submitLabel.textContent;
  const fileInput = document.getElementById("attachments");
  const maxFileBytes = 5 * 1024 * 1024;
  const maxFiles = 10;

  const errEl = (key) => document.getElementById("err-" + key.replace(".", "-"));
  const controlOf = (key) => {
    const [qid, code] = key.split(".");
    if (code) return form.querySelector(`[data-text-for="${code}"] input`);
    const f = form.querySelector(`[data-field="${qid}"]`);
    return f && f.querySelector("input:not([type=hidden]), select, textarea, button.datepicker__trigger");
  };

  function setInvalid(key, msg) {
    const out = errEl(key);
    const ctl = controlOf(key);
    if (out) out.textContent = msg;
    if (ctl) ctl.setAttribute("aria-invalid", "true");
    return ctl;
  }

  function clearInvalid(key) {
    const out = errEl(key);
    const ctl = controlOf(key);
    if (out) out.textContent = "";
    if (ctl) ctl.removeAttribute("aria-invalid");
  }

  function clearAll() {
    form.querySelectorAll(".field__error").forEach((e) => (e.textContent = ""));
    form.querySelectorAll("[aria-invalid]").forEach((e) => e.removeAttribute("aria-invalid"));
    banner.hidden = true;
  }

  function showBanner(msg) {
    banner.querySelector("span").textContent = msg;
    banner.hidden = false;
    banner.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function showErrors(errors) {
    let first = null;
    Object.entries(errors).forEach(([key, msg]) => {
      if (key === "_form") return showBanner(msg);
      const ctl = setInvalid(key, msg);
      first = first || ctl;
    });
    if (first) {
      first.scrollIntoView({ behavior: "smooth", block: "center" });
      first.focus({ preventScroll: true });
    }
  }

  function collect() {
    const answers = {};
    form.querySelectorAll("[data-type]").forEach((f) => {
      const id = f.dataset.field;
      if (f.dataset.type === "multi_choice") {
        const selected = [...f.querySelectorAll('input[type="checkbox"]:checked')].map((c) => c.value);
        const texts = {};
        selected.forEach((code) => {
          const t = f.querySelector(`[data-text-for="${code}"] input`);
          if (t) texts[code] = t.value;
        });
        answers[id] = { selected, texts };
      } else {
        answers[id] = f.querySelector("input, textarea").value;
      }
    });
    return {
      questionnaire_version: Number(form.dataset.version),
      respondent_name: form.elements.respondent_name.value,
      department: form.elements.department.value,
      work_date: form.elements.work_date.value,
      answers,
    };
  }

  // Clear a field's error as soon as the person starts fixing it.
  form.addEventListener("input", (e) => {
    const f = e.target.closest("[data-field]");
    if (!f) return;
    const text = e.target.closest("[data-text-for]");
    clearInvalid(text ? `${f.dataset.field}.${text.dataset.textFor}` : f.dataset.field);
  });

  form.addEventListener("change", (e) => {
    const box = e.target;
    const f = box.closest("[data-field]");
    if (f) clearInvalid(f.dataset.field);
    if (!box.matches('input[type="checkbox"]')) return;
    // "Exclusive" answers (e.g. "no obstacles") clear the others, and vice versa.
    if (box.checked && box.hasAttribute("data-exclusive")) {
      f.querySelectorAll('input[type="checkbox"]').forEach((c) => { if (c !== box) c.checked = false; });
    } else if (box.checked) {
      f.querySelectorAll("input[data-exclusive]").forEach((c) => (c.checked = false));
    }
    // Free-text boxes follow their checkbox.
    f.querySelectorAll("[data-text-for]").forEach((wrap) => {
      const cb = f.querySelector(`input[type="checkbox"][value="${wrap.dataset.textFor}"]`);
      const show = !!(cb && cb.checked);
      if (wrap.hidden && show) setTimeout(() => wrap.querySelector("input").focus({ preventScroll: true }), 0);
      wrap.hidden = !show;
      if (!show) { wrap.querySelector("input").value = ""; clearInvalid(`${f.dataset.field}.${wrap.dataset.textFor}`); }
    });
  });

  function setLoading(on) {
    submitBtn.disabled = on;
    submitBtn.classList.toggle("is-loading", on);
    submitLabel.textContent = on ? "Изпращане..." : LABEL;
  }

  function readFile(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve({ name: file.name, data: reader.result.split(",", 2)[1] });
      reader.onerror = reject;
      reader.onabort = reject;
      reader.readAsDataURL(file);
    });
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (submitBtn.disabled) return;
    clearAll();
    setLoading(true);
    const payload = collect();
    try {
      const files = fileInput ? [...fileInput.files] : [];
      if (files.length > maxFiles || files.some((file) => file.size === 0 || file.size > maxFileBytes)) {
        showErrors({ attachments: "Изберете до 10 файла по 5 MB. Празни файлове не се приемат." });
        return;
      }
      if (files.length) {
        payload.attachments = [];
        for (const file of files) payload.attachments.push(await readFile(file)); // one at a time: gentler on phones
      }
      const endpoint = files.length ? "/api/submissions/with-attachments" : "/api/submissions";
      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.status === 201) {
        const label = document.querySelector(".datepicker__value").textContent;
        document.getElementById("success-text").textContent =
          "Дневният отчет" + (label ? " за " + label : "") + " е изпратен успешно.";
        formView.hidden = true;
        successView.hidden = false;
        successView.classList.add("view-in");
        window.scrollTo({ top: 0 });
        successView.querySelector("h2").focus({ preventScroll: true });
      } else if ([400, 413, 422, 503].includes(res.status)) {
        const contentType = res.headers.get("content-type") || "";
        if (contentType.includes("application/json")) {
          showErrors((await res.json()).errors || {});
        } else if (res.status === 413) {
          showErrors({ _form: "Общият размер на файловете е твърде голям." });
        } else {
          throw new Error("server");
        }
      } else {
        throw new Error("server");
      }
    } catch (_) {
      showBanner("Възникна проблем при изпращането. Въведеното е запазено в страницата - опитайте отново след малко.");
    } finally {
      setLoading(false);
    }
  });

  document.getElementById("another").addEventListener("click", () => {
    form.reset();
    form.querySelectorAll("[data-text-for]").forEach((w) => (w.hidden = true));
    clearAll();
    successView.hidden = true;
    successView.classList.remove("view-in");
    formView.hidden = false;
    window.scrollTo({ top: 0 });
  });
})();
