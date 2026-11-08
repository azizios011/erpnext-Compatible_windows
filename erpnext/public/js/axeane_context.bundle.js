// Axeane accounting context (dock selector) + search scope.
//
// 1. A dock utility button ("Contexte comptable") between the Search and
//    Notifications utilities, opening a frappe.ui.Dropdown with two nested
//    side lists (Entreprise / Exercice) backed by frappe.boot.axeane_context.
// 2. When frappe.boot.axeane_search_scope exists (everyone but
//    Administrator), the awesome-bar sources are filtered to the custom
//    modules' items. Display filter only — not a permission change: direct
//    URLs and the sidebar keep working.
(function () {
	"use strict";

	const CONTEXT_METHOD = "erpnext.custom_modules.organization.context";

	// ── shared state ─────────────────────────────────────────────────────────

	window.axeane = window.axeane || {};

	function context() {
		return frappe.boot.axeane_context || null;
	}

	function apply_context(ctx) {
		frappe.boot.axeane_context = ctx;
		refresh_tooltip();
		$(document).trigger("axeane-context-changed", ctx);
		// open lists pick up route options on re-render; the router's own
		// render() re-runs the current route in this frappe version
		if (frappe.router && typeof frappe.router.render === "function") {
			try {
				frappe.router.render();
			} catch (error) {
				console.warn("axeane-context: route re-render failed", error);
			}
		}
	}

	window.axeane.context = {
		get() {
			return context();
		},
		set(entreprise, exercice) {
			return new Promise((resolve) => {
				frappe.call({
					method: CONTEXT_METHOD + ".set_context",
					args: { entreprise: entreprise || "", exercice: exercice || "" },
					callback(r) {
						const ctx = r.message;
						if (ctx) apply_context(ctx);
						resolve(ctx);
					},
				});
			});
		},
	};

	// ── dock utility ─────────────────────────────────────────────────────────

	let context_tooltip = null;
	let dropdown = null;

	function tooltip_text() {
		const ctx = context() || {};
		const parts = [];
		if (ctx.entreprise) parts.push(ctx.entreprise);
		if (ctx.exercice_label) parts.push(ctx.exercice_label);
		return parts.length ? parts.join(" · ") : __("Contexte comptable");
	}

	function refresh_tooltip() {
		const $btn = $("#axeane-context-utility");
		if (!$btn.length) return;
		attach_tooltip($btn);
	}

	function attach_tooltip($btn) {
		if (context_tooltip && context_tooltip.destroy) {
			context_tooltip.destroy();
		}
		context_tooltip = new frappe.ui.Tooltip($btn[0], {
			text: tooltip_text(),
			side: "right",
			delay: 0,
			offset: 10,
			class: "es-tooltip--plain",
		});
		return context_tooltip;
	}

	function make_utility_button(dock) {
		const $btn = $(
			`<button class="dock-item axeane-context-utility" aria-label="${__(
				"Contexte comptable"
			)}">
			<span class="dock-item-icon">${frappe.utils.icon("building", "sm")}</span>
		</button>`
		);
		dock.name_tile($btn, tooltip_text(), dock.utility_tooltips);
		// keep the tooltip text in sync with the context
		const original_tooltip = dock.utility_tooltips[dock.utility_tooltips.length - 1];
		if (original_tooltip) {
			context_tooltip = original_tooltip;
		}
		attach_tooltip($btn);
		return $btn;
	}

	function insert_utility(dock) {
		if (frappe.session.user === "Guest") return;
		const $utilities = dock.$dock && dock.$dock.find(".dock-utilities");
		if (!$utilities || !$utilities.length) return;
		if ($utilities.find(".axeane-context-utility").length) return; // already there

		const $button = make_utility_button(dock);
		const $search = $utilities.find(".navbar-modal-search-mobile");
		const $bell = $utilities.find(".sidebar-notification");
		if ($bell.length) {
			$bell.before($button); // between Search and Notifications
		} else if ($search.length) {
			$search.after($button);
		} else {
			$utilities.prepend($button);
		}

		// the Dropdown owns the trigger's click (menu-button pattern); the
		// lists reload on every open so new Entreprises/Exercices show up
		dropdown = new frappe.ui.Dropdown({
			trigger: $button,
			side: "right",
			options: () => menu_options(),
			on_open() {
				frappe.call({
					method: "erpnext.custom_modules.organization.context.get_context",
					args: {},
					callback(r) {
						if (r.message) {
							frappe.boot.axeane_context = r.message;
							dropdown && dropdown.set_options(menu_options());
							refresh_tooltip();
						}
					},
				});
			},
		});
	}

	function menu_options() {
		const ctx = context() || {};
		const entreprise_rows = (ctx.entreprises || []).map((row) => ({
			label: esc(row.label),
			icon: row.name === ctx.entreprise ? "check" : "",
			onclick() {
				select("entreprise", row.name);
			},
		}));
		if (!entreprise_rows.length) {
			entreprise_rows.push({ label: __("Aucune entreprise"), disabled: true });
		}
		const exercice_rows = (ctx.exercices || []).map((row) => ({
			label: `${esc(row.label)}${row.status === "Cloture" ? " (" + __("Cloture") + ")" : ""}`,
			icon: row.name === ctx.exercice ? "check" : "",
			onclick() {
				select("exercice", row.name);
			},
		}));
		if (!exercice_rows.length) {
			exercice_rows.push({ label: __("Aucun exercice"), disabled: true });
			exercice_rows.push({
				label: __("Creer un exercice"),
				icon: "plus",
				onclick() {
					frappe.new_doc("Exercice", { entreprise: ctx.entreprise || "" });
				},
			});
		}
		return [
			{ group: __("Contexte comptable") },
			{
				label: `${__("Entreprise")}: ${ctx.entreprise || "—"}`,
				icon: "building",
				submenu: entreprise_rows,
			},
			{
				label: `${__("Exercice")}: ${ctx.exercice_label || "—"}`,
				icon: "calendar",
				submenu: exercice_rows,
			},
		];
	}

	function esc(value) {
		return frappe.utils.escape_html(value === null || value === undefined ? "" : String(value));
	}

	function select(kind, name) {
		const args = kind === "entreprise" ? { entreprise: name } : { exercice: name };
		window.axeane.context
			.set(args.entreprise || "", args.exercice || "")
			.then((ctx) => {
				if (!ctx) return;
				frappe.show_alert({
					message: __("Contexte comptable: {0} · {1}", [ctx.entreprise, ctx.exercice_label]),
					indicator: "green",
				});
				// the exercice list follows the freshly selected Entreprise
				if (dropdown) dropdown.set_options(menu_options());
			});
	}

	// a search input at the head of a submenu panel (MenuTree has no built-in
	// search): filter the panel's rows as the user types
	function bind_submenu_search() {
		$(document).on(
			"input",
			".axeane-submenu-search",
			frappe.utils.debounce(function () {
				const term = $(this).val().toLowerCase();
				$(this)
					.closest(".es-menu")
					.find(".es-menu__item")
					.each(function () {
						const text = $(this).text().toLowerCase();
						$(this).toggleClass("hidden", term !== "" && text.indexOf(term) === -1);
					});
			}, 150)
		);
	}

	function inject_submenu_search(menu) {
		// only our dropdown's submenu panels, and only when they carry enough
		// rows for a search to be useful
		if (this !== dropdown) return;
		const $panels = $("body").find(".es-menu");
		const $panel = $panels.last();
		if (!$panel.length || $panel.find(".axeane-submenu-search").length) return;
		if ($panel.find(".es-menu__item").length < 6) return;
		const $input = $(
			`<input type="text" class="form-control form-control-sm axeane-submenu-search"
				placeholder="${__("Rechercher...")}" style="margin: 6px 8px; width: calc(100% - 16px);">`
		);
		$panel.prepend($input);
		bind_submenu_search();
		$input.trigger("focus");
	}

	function patch_dock() {
		const Dock = frappe.ui && frappe.ui.Dock;
		if (!Dock || Dock.prototype.__axeane_context_patched) {
			// an already-rendered dock instance still needs the button once
			if (frappe.ui.sidebar && frappe.ui.sidebar.dock && frappe.ui.sidebar.dock.$dock) {
				insert_utility(frappe.ui.sidebar.dock);
			}
			return;
		}
		Dock.prototype.__axeane_context_patched = true;
		const original = Dock.prototype.render_utilities;
		Dock.prototype.render_utilities = function () {
			original.apply(this, arguments);
			// our button rides along after every re-render; insert_utility
			// refuses a second copy
			try {
				insert_utility(this);
			} catch (error) {
				console.warn("axeane-context: dock insert failed", error);
			}
		};
		// a dock may already be on screen when the bundle loads
		if (frappe.ui.sidebar && frappe.ui.sidebar.dock && frappe.ui.sidebar.dock.$dock) {
			try {
				insert_utility(frappe.ui.sidebar.dock);
			} catch (error) {
				console.warn("axeane-context: dock insert failed", error);
			}
		}
		// the submenu search input rides on every Dropdown menu open
		const Dropdown = frappe.ui.Dropdown;
		if (Dropdown && dropdown && !dropdown.__axeane_submenu_search) {
			dropdown.__axeane_submenu_search = true;
			const original_open = Dropdown.prototype.open;
			dropdown.open = function () {
				const result = original_open.apply(this, arguments);
				if (this.menu) {
					// only the nested side panels get a search input; the root
					// panel keeps its two rows tight
					const observer = new MutationObserver(() => {
						if ($("body").find(".es-menu").length > 1) {
							inject_submenu_search.call(dropdown, this.menu);
						}
					});
					observer.observe(document.body, { childList: true, subtree: true });
					setTimeout(() => observer.disconnect(), 5000);
				}
				return result;
			};
		}
	}

	// ── search scope (client) ────────────────────────────────────────────────

	function target_of(result) {
		const route = result.route || [];
		if (["List", "Tree"].includes(route[0]) && route[1]) return ["doctypes", route[1]];
		if (route[0] === "Form" && route[1]) return ["doctypes", route[1]];
		if (route[0] === "query-report" && route[1]) return ["reports", route[1]];
		if (route[0] === "dashboard-view" && route[1]) return ["dashboards", route[1]];
		if (route[0] === "page" && route[1]) return ["pages", route[1]];
		if (route[0] === "Workspaces") return route[1] ? ["workspaces", route[1]] : null;
		if (result.type === "New" && result.match) return ["doctypes", result.match];
		return null;
	}

	function wrap_search_utils() {
		const utils = frappe.search && frappe.search.utils;
		if (!utils || utils.__axeane_scope_wrapped) return true;
		const scope = frappe.boot.axeane_search_scope;
		if (!scope) return true; // Administrator: unrestricted, nothing to do

		utils.__axeane_scope_wrapped = true;
		const allowed = (kind, name) => (scope[kind] || []).includes(name);
		const keep = (result) => {
			const target = target_of(result);
			return target ? allowed(target[0], target[1]) : false;
		};

		[
			"get_doctypes",
			"get_reports",
			"get_pages",
			"get_dashboards",
			"get_recent_pages",
			"get_frequent_links",
		].forEach((name) => {
			if (typeof utils[name] !== "function") return;
			const original = utils[name].bind(utils);
			utils[name] = function (keywords) {
				return original(keywords).filter(keep);
			};
		});

		// workspaces: the results carry the title, not the name — map titles
		// back through frappe.workspaces before filtering
		if (typeof utils.get_workspaces === "function") {
			const original_workspaces = utils.get_workspaces.bind(utils);
			utils.get_workspaces = function (keywords) {
				const title_to_name = {};
				Object.values(frappe.workspaces || {}).forEach((workspace) => {
					title_to_name[workspace.title || workspace.label || workspace.name] = workspace.name;
				});
				const open_workspace_label = __("Open {0} Workspace", ["{0}"]);
				return original_workspaces(keywords).filter((result) => {
					// label = __("Open {0} Workspace", [marked title]) — recover the
					// title, then the workspace name, from frappe.workspaces
					const title = Object.keys(title_to_name).find((title) =>
						result.label.includes(title)
					);
					const name = title ? title_to_name[title] : null;
					return name ? allowed("workspaces", name) : false;
				});
			};
		}
		return true;
	}

	function boot() {
		patch_dock();
		bind_submenu_search();
		// the search utils land with the desk bundle; they are already there
		// when this bundle loads (app includes come last), but retry briefly
		// in case the load order changes
		if (!wrap_search_utils()) {
			let tries = 0;
			const timer = setInterval(() => {
				tries += 1;
				if (wrap_search_utils() || tries > 20) clearInterval(timer);
			}, 500);
		}
	}

	if (frappe.session && frappe.session.user !== "Guest") {
		if (document.readyState === "complete" || document.readyState === "interactive") {
			setTimeout(boot, 0);
		} else {
			document.addEventListener("DOMContentLoaded", () => boot());
		}
	}
})();
