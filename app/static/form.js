// Collects the form, posts JSON, and shows backend validation errors inline.
// All real validation happens on the server; this file only renders its result.
(function () {
  const form = document.getElementById("report");
  const formView = document.getElementById("form-view");
  const successView = document.getElementById("success-view");
  const submitBtn = document.getElementById("submit");
  const banner = document.getElementById("form-error");

  const fieldEl = (key) => {
    const [qid, code] = key.split(".");
    if (code) return form.querySelector(`[data-text-for="${code}"]`);
    return form.querySelector(`[data-field="${qid}"]`);
  };

  function clearErrors() {
    form.querySelectorAll(".error").forEach((e) => (e.textContent = ""));
    form.querySelectorAll(".has-error").forEach((e) => e.classList.remove("has-error"));
    banner.hidden = true;
  }

  function showErrors(errors) {
    let first = null;
    Object.entries(errors).forEach(([key, msg]) => {
      if (key === "_form") { banner.textContent = msg; banner.hidden = false; return; }
      const el = fieldEl(key);
      if (!el) return;
      const target = el.matches("[data-field]") ? el : el.closest("[data-field]");
      const out = el.matches("[data-field]")
        ? el.querySelector(":scope > .error")
        : el.querySelector(".error");
      if (out) out.textContent = msg;
      if (target) target.classList.add("has-error");
      first = first || target || el;
    });
    if (first) first.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function collect() {
    const answers = {};
    form.querySelectorAll("[data-field]").forEach((f) => {
      const id = f.dataset.field;
      const type = f.dataset.type;
      if (type === "multi_choice") {
        const selected = [...f.querySelectorAll('input[type="checkbox"]:checked')].map((c) => c.value);
        const texts = {};
        selected.forEach((code) => {
          const t = f.querySelector(`[data-text-for="${code}"] input`);
          if (t) texts[code] = t.value;
        });
        answers[id] = { selected, texts };
      } else if (type) {
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

  // Checkbox behaviour: "exclusive" answers clear the others; text boxes follow their checkbox.
  form.addEventListener("change", (e) => {
    const box = e.target;
    if (!box.matches('input[type="checkbox"]')) return;
    const group = box.closest("[data-field]");
    if (box.checked && box.hasAttribute("data-exclusive")) {
      group.querySelectorAll('input[type="checkbox"]').forEach((c) => { if (c !== box) c.checked = false; });
    } else if (box.checked) {
      group.querySelectorAll("input[data-exclusive]").forEach((c) => (c.checked = false));
    }
    group.querySelectorAll("[data-text-for]").forEach((wrap) => {
      const cb = group.querySelector(`input[value="${wrap.dataset.textFor}"]`);
      wrap.hidden = !(cb && cb.checked);
      if (wrap.hidden) wrap.querySelector("input").value = "";
    });
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearErrors();
    submitBtn.disabled = true;
    submitBtn.textContent = "Изпращане...";
    try {
      const res = await fetch("/api/submissions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(collect()),
      });
      if (res.status === 201) {
        formView.hidden = true;
        successView.hidden = false;
        window.scrollTo({ top: 0, behavior: "smooth" });
      } else if (res.status === 422 || res.status === 400) {
        showErrors((await res.json()).errors || {});
      } else {
        throw new Error("server");
      }
    } catch (_) {
      banner.textContent = "Възникна проблем при изпращането. Данните Ви са запазени в страницата - опитайте отново след малко.";
      banner.hidden = false;
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Изпрати дневен отчет";
    }
  });

  document.getElementById("another").addEventListener("click", () => {
    form.reset();
    form.querySelectorAll("[data-text-for]").forEach((w) => (w.hidden = true));
    successView.hidden = true;
    formView.hidden = false;
    window.scrollTo({ top: 0 });
  });
})();
