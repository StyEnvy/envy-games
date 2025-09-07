(function () {
    // --- Resolve prefix from management form robustly ---
    function findTotalInput() {
        // Prefer explicit links TOTAL_FORMS
        const direct = document.getElementById("id_links-TOTAL_FORMS");
        if (direct) return direct;

        // Fallback: any *-TOTAL_FORMS near the container
        const all = document.querySelectorAll("input[id$='-TOTAL_FORMS']");
        if (all.length) return all[0];
        return null;
    }

    const container = document.getElementById("links-forms");
    const addBtn = document.getElementById("add-link-btn");
    const tmpl = document.getElementById("link-empty-form-template");
    const totalInput = findTotalInput();

    if (!container || !totalInput || !tmpl) return;

    const totalId = totalInput.id; // e.g., id_links-TOTAL_FORMS
    const prefix = (totalId.match(/^id_(.+)-TOTAL_FORMS$/) || [, "links"])[1]; // => "links"

    // --- Utils ---
    function qsa(el, sel) { return Array.from(el.querySelectorAll(sel)); }

    function replaceIndex(str, fromRe, toStr) { return str.replace(fromRe, toStr); }

    function allRows() {
        return qsa(container, ".link-form");
    }

    function isExistingRow(row) {
        const idField = row.querySelector(`input[name^="${prefix}-"][name$="-id"]`);
        return !!(idField && idField.value);
    }

    function toggleRequired(row, on) {
        qsa(row, "input, select, textarea").forEach(el => {
            if (!on) {
                el.removeAttribute("required");
            } else {
                if (el.dataset.wasRequired === "1") el.setAttribute("required", "required");
            }
        });
    }

    function disableNonCritical(row, disabled) {
        qsa(row, "input, select, textarea").forEach(el => {
            const isDelete = /\-DELETE$/.test(el.name || "");
            const isId = /\-id$/.test(el.name || "");
            if (isDelete || isId) {
                el.disabled = false;
            } else {
                // Track original required state so we can restore if needed
                if (disabled && el.hasAttribute("required")) el.dataset.wasRequired = "1";
                if (!disabled) delete el.dataset.wasRequired;

                el.disabled = !!disabled;
                if (disabled) el.removeAttribute("required");
            }
        });
    }

    // Reindex ALL rows (visible + hidden) so indices stay contiguous for Django.
    function reindexAll() {
        const rows = allRows();
        const re = new RegExp(`${prefix}-\\d+`, "g");

        rows.forEach((row, i) => {
            qsa(row, "input, select, textarea, label").forEach(el => {
                if (el.name) el.name = replaceIndex(el.name, re, `${prefix}-${i}`);
                if (el.id) el.id = replaceIndex(el.id, re, `${prefix}-${i}`);
                if (el.htmlFor) el.htmlFor = replaceIndex(el.htmlFor, re, `${prefix}-${i}`);
            });
        });
        totalInput.value = rows.length;
    }

    function nextPositionGuess() {
        let maxPos = 0;
        qsa(container, `input[name^="${prefix}-"][name$="-position"]`).forEach(input => {
            const v = parseInt(input.value, 10);
            if (!isNaN(v) && v > maxPos) maxPos = v;
        });
        return (isFinite(maxPos) ? maxPos : 0) + 100;
    }

    function addRow() {
        const idx = parseInt(totalInput.value || "0", 10);
        const html = tmpl.innerHTML.replace(/__prefix__/g, idx);
        const wrap = document.createElement("div");
        wrap.innerHTML = html.trim();
        const node = wrap.firstElementChild;

        container.appendChild(node);
        totalInput.value = idx + 1;

        // Autofill position
        const posInput = node.querySelector(`input[name^="${prefix}-"][name$="-position"]`);
        if (posInput && !posInput.value) {
            const guess = nextPositionGuess();
            if (Number.isFinite(guess)) posInput.value = String(guess);
        }
    }

    function removeRow(row) {
        if (isExistingRow(row)) {
            // Existing DB-backed row: check DELETE, disable inputs (except id/DELETE), hide
            const del = row.querySelector(`input[name^="${prefix}-"][name$="-DELETE"]`);
            if (del) del.checked = true;
            disableNonCritical(row, true);
            row.style.display = "none";
            // IMPORTANT: do NOT decrement TOTAL_FORMS for existing rows
            // keep indices as-is; if user later removes a new row we reindex all forms
        } else {
            // New row: remove entirely and reindex everything
            row.remove();
            reindexAll();
        }
    }

    // --- Events ---
    container.addEventListener("click", function (e) {
        // Support both legacy .js-remove-new-link and new .js-remove-row
        const btn = e.target.closest(".js-remove-row, .js-remove-new-link");
        if (!btn) return;
        const row = btn.closest(".link-form");
        if (!row) return;
        removeRow(row);
    });

    if (addBtn) addBtn.addEventListener("click", function (e) {
        e.preventDefault();
        addRow();
    });
})();
