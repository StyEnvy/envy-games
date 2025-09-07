(function () {
    // --- Helpers
    function debounce(fn, wait) {
        var t;
        return function () {
            var ctx = this, args = arguments;
            clearTimeout(t);
            t = setTimeout(function () { fn.apply(ctx, args); }, wait);
        };
    }
    function $(sel, scope) { return (scope || document).querySelector(sel); }

    // --- Config
    var cfg = $("#tt-config");
    var PROJECT_URL = cfg?.dataset.projectOptionsUrl || "";
    var TASK_URL = cfg?.dataset.taskOptionsUrl || "";

    var projectSel = $("#id_project");
    var taskSel = $("#id_task");
    var projectSearch = $("#project-search");
    var taskSearch = $("#task-search");

    // --- Replace <select> options with server-rendered <option> HTML
    function setOptions(selectEl, html, keepValue) {
        if (!selectEl) return;
        var current = keepValue ? selectEl.value : "";
        selectEl.innerHTML = html;
        if (keepValue && current) {
            var opt = selectEl.querySelector('option[value="' + current + '"]');
            if (opt) selectEl.value = current;
        }
    }

    function safeFetch(url) {
        return fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
            .then(function (r) { return r.text(); })
            .catch(function () { return ""; });
    }

    // --- Load projects (typeahead)
    var loadProjects = debounce(function () {
        if (!PROJECT_URL || !projectSel) return;
        var params = new URLSearchParams();
        var q = (projectSearch?.value || "").trim();
        if (q) params.set("q", q);
        // (optional) hint for server; harmless if ignored
        if (projectSel.value) params.set("selected", projectSel.value);

        safeFetch(PROJECT_URL + "?" + params.toString())
            .then(function (html) {
                if (html) {
                    setOptions(projectSel, html, true);
                    // After projects load, if a project is selected, load tasks for it
                    if (projectSel.value) { loadTasks(true); }
                }
            });
    }, 180);

    // --- Load tasks (typeahead) scoped to selected project
    var loadTasks = debounce(function (keepValue) {
        if (!TASK_URL || !taskSel) return;
        var pid = projectSel?.value;
        if (!pid) {
            setOptions(taskSel, '<option value="">— Select a task —</option>', false);
            taskSel.disabled = true;
            return;
        }
        taskSel.disabled = false;

        var params = new URLSearchParams();
        params.set("project", pid);
        var q = (taskSearch?.value || "").trim();
        if (q) params.set("q", q);
        // (optional) hint for server; harmless if ignored
        if (keepValue && taskSel.value) params.set("selected", taskSel.value);

        safeFetch(TASK_URL + "?" + params.toString())
            .then(function (html) {
                if (html) setOptions(taskSel, html, keepValue);
            });
    }, 180);

    // --- Bind project search / change
    if (projectSearch) projectSearch.addEventListener("input", loadProjects);
    if (projectSel) {
        projectSel.addEventListener("change", function () {
            if (taskSearch) taskSearch.value = "";
            loadTasks(false);
        });
    }

    // --- Bind task search
    if (taskSearch) taskSearch.addEventListener("input", function () { loadTasks(true); });

    // initial state: enable/disable tasks based on selected project
    if (taskSel && projectSel) {
        taskSel.disabled = !projectSel.value;
    }

    // ------------------------------
    // Entries list search & modal edit bindings
    // ------------------------------
    function bindEntriesSearch() {
        var box = document.getElementById('entries-search');
        var table = document.getElementById('entries-table');
        if (!box || !table) return;
        box.addEventListener('input', function () {
            var q = (this.value || "").toLowerCase();
            Array.from(table.querySelectorAll('tbody tr[data-row]')).forEach(function (tr) {
                var date = (tr.querySelector('.col-date')?.textContent || "").toLowerCase();
                var pt = (tr.querySelector('.col-pt')?.textContent || "").toLowerCase();
                tr.style.display = (date.indexOf(q) !== -1 || pt.indexOf(q) !== -1) ? "" : "none";
            });
        });
    }
    bindEntriesSearch();

    var modal = document.getElementById('entry-modal');
    var modalContent = document.getElementById('entry-modal-content');

    function openModalWith(url) {
        safeFetch(url).then(function (html) {
            if (!html) return;
            modalContent.innerHTML = html;
            if (typeof modal.showModal === 'function') modal.showModal();
            else modal.setAttribute('open', 'open');
        });
    }

    function bindEditButtons(scope) {
        (scope || document).querySelectorAll('.entry-edit-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var url = this.getAttribute('data-edit-url');
                if (url) openModalWith(url);
            });
        });
    }
    bindEditButtons();

    document.body.addEventListener('entriesChanged', function () {
        setTimeout(function () {
            bindEntriesSearch();
            bindEditButtons();
            if (modal) modal.close();
        }, 0);
    });

    // --- Initial populate on page load
    // If a project is already selected (server-side), load tasks for it;
    // otherwise, load the project list so users see options immediately.
    if (projectSel && projectSel.value) {
        loadTasks(true);
    } else {
        loadProjects();
    }
})();
