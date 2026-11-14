<!-- Plan comptable — Frappe UI island page for the Chart of Account doctype.

     Modes from the desk route props (pageview passes the URL below the page as
     `route` and the query string as `query`):
       - /app/plan-comptable                    → accounts of one entreprise
       - /app/plan-comptable/new                → the create form
       - /app/plan-comptable/<account name>     → the edit panel
     The Entreprise is the dock's "Contexte comptable" (window.axeane.context,
     boot backup frappe.boot.axeane_context) — never a selector, never the URL.
     The list renders class tabs (1..7 + "Comptes non attribués") with counts
     from ONE group_by call, a server-filtered/paginated accounts table and
     generic frappe.client.* calls only (get_list / get_count / delete); the
     server additionally scopes every query to the context Entreprise. -->
<script setup>
import { computed, onBeforeUnmount, onErrorCaptured, onMounted, ref, watch } from "vue";
import { Badge, Button, Dialog, Dropdown, FormControl } from "frappe-ui";

import PlanComptableAccount from "./plan_comptable_account.vue";
import PlanComptableImportDialog from "./PlanComptableImportDialog.vue";

const frappe = window.frappe;
const __ = window.__;

const props = defineProps({
	route: { type: Array, default: () => [] },
	query: { type: Object, default: () => ({}) },
});
const emit = defineEmits(["title"]);

const DOCTYPE = "Chart of Account";
const PAGE_SIZE = 50;
const ROOT_CLASSES = ["1", "2", "3", "4", "5", "6", "7"];

const CLASS_TABS = [
	{ value: "1", label: "Capitaux" },
	{ value: "2", label: "Immobilisations" },
	{ value: "3", label: "Stock et Encours" },
	{ value: "4", label: "Tiers" },
	{ value: "5", label: "Financiers" },
	{ value: "6", label: "Charges" },
	{ value: "7", label: "Produits" },
	{ value: "other", label: "Comptes non attribués" },
];

const NATURE_FILTERS = [
	{ label: "Tous", value: "all" },
	{ label: "Regroupement", value: "regroupement" },
	{ label: "Comptable", value: "comptable" },
];

const SENS_FILTERS = [
	{ label: "Tous", value: "all" },
	{ label: "C", value: "C" },
	{ label: "D", value: "D" },
	{ label: "DC", value: "DC" },
];

// ── routing ──────────────────────────────────────────────────────────────────
const mode = computed(() => {
	if (!props.route?.length) return "list";
	return props.route[0] === "new" ? "new" : "record";
});

// A render error inside the island blanks it silently otherwise; captured here
// the message shows on the page itself (same pattern as the Entreprise page).
const render_error = ref(null);
onErrorCaptured((error, instance, info) => {
	render_error.value = `${error?.message || String(error)} (${info})`;
	return false;
});

// ── the accounting context is the only source of Entreprise ──────────────────
function context_entreprise() {
	const ctx = window.axeane?.context?.get?.() || frappe.boot?.axeane_context || null;
	return ctx?.entreprise || "";
}

function context_entreprise_label() {
	const ctx = window.axeane?.context?.get?.() || frappe.boot?.axeane_context || null;
	if (!ctx?.entreprise) return "";
	return [ctx.entreprise, ctx.entreprise_label].filter(Boolean).join(" · ");
}

const entreprise = ref(context_entreprise());
const entreprise_label = ref(context_entreprise_label());

// ── class counts (one group_by call for all tabs) ────────────────────────────
const class_counts = ref({});
const counts_loaded = ref(false);

async function load_counts() {
	if (!entreprise.value) return;
	try {
		const rows = await frappe.xcall("frappe.client.get_list", {
			doctype: DOCTYPE,
			// this frappe rejects SQL functions as strings in SELECT: counts go
			// through the dict syntax ({'COUNT': '*', 'as': ...})
			fields: ["classe", { COUNT: "name", as: "n" }],
			filters: { entreprise: entreprise.value },
			group_by: "classe",
			order_by: "classe asc",
			limit_page_length: 0,
		});
		const map = {};
		for (const row of rows || []) {
			map[row.classe || ""] = row.n;
		}
		class_counts.value = map;
	} finally {
		counts_loaded.value = true;
	}
}

const total_accounts = computed(() =>
	Object.values(class_counts.value).reduce((sum, n) => sum + n, 0)
);

function tab_count(tab) {
	if (tab.value === "other") {
		return Object.entries(class_counts.value)
			.filter(([classe]) => !ROOT_CLASSES.includes(classe))
			.reduce((sum, [, n]) => sum + n, 0);
	}
	return class_counts.value[tab.value] || 0;
}

// ── table state & filters ────────────────────────────────────────────────────
const active_tab = ref("1");
const code_search = ref("");
const name_search = ref("");
const nature_filter = ref("all");
const sens_filter = ref("all");
const rows = ref([]);
const rows_loading = ref(false);
const total_rows = ref(0);
const page = ref(1);

const has_active_filters = computed(
	() =>
		code_search.value.trim() !== "" ||
		name_search.value.trim() !== "" ||
		nature_filter.value !== "all" ||
		sens_filter.value !== "all"
);

function current_filters() {
	// the explicit entreprise filter rides along with the server scope
	const filters = { entreprise: entreprise.value };
	filters.classe =
		active_tab.value === "other" ? ["not in", ROOT_CLASSES] : active_tab.value;
	if (code_search.value.trim()) {
		filters.account_number = ["like", `${code_search.value.trim()}%`];
	}
	if (name_search.value.trim()) {
		filters.account_name = ["like", `%${name_search.value.trim()}%`];
	}
	if (nature_filter.value === "regroupement") {
		filters.is_group = 1;
	} else if (nature_filter.value === "comptable") {
		filters.is_group = 0;
	}
	if (sens_filter.value !== "all") {
		filters.sens = sens_filter.value;
	}
	return filters;
}

let search_timer = null;

function on_search_input() {
	if (search_timer) clearTimeout(search_timer);
	search_timer = setTimeout(() => {
		page.value = 1;
		load_rows();
	}, 300);
}

function on_filter_select() {
	page.value = 1;
	load_rows();
}

function switch_tab(value) {
	if (value === active_tab.value) return;
	active_tab.value = value;
	page.value = 1;
	load_rows();
}

function reset_filters() {
	code_search.value = "";
	name_search.value = "";
	nature_filter.value = "all";
	sens_filter.value = "all";
	page.value = 1;
	load_rows();
}

// ── rows & pagination ────────────────────────────────────────────────────────
const ROW_FIELDS = [
	"name",
	"account_number",
	"account_name",
	"is_group",
	"sens",
	"is_standard",
	"classe",
];

async function fetch_rows(filters) {
	return frappe.xcall("frappe.client.get_list", {
		doctype: DOCTYPE,
		fields: ROW_FIELDS,
		filters,
		order_by: "account_number asc",
		limit_start: (page.value - 1) * PAGE_SIZE,
		limit_page_length: PAGE_SIZE,
	});
}

async function load_rows() {
	if (!entreprise.value) return;
	rows_loading.value = true;
	try {
		const filters = current_filters();
		rows.value = await fetch_rows(filters);
		total_rows.value = await frappe.xcall("frappe.client.get_count", {
			doctype: DOCTYPE,
			filters,
		});
		// a delete or a filter change can leave the page beyond the end
		if (total_rows.value && page.value > total_pages.value) {
			page.value = total_pages.value;
			rows.value = await fetch_rows(filters);
		}
	} finally {
		rows_loading.value = false;
	}
}

const total_pages = computed(() => Math.max(1, Math.ceil(total_rows.value / PAGE_SIZE)));

const page_numbers = computed(() => {
	const total = total_pages.value;
	const current = page.value;
	if (total <= 7) {
		return Array.from({ length: total }, (_, index) => index + 1);
	}
	const start = Math.max(1, Math.min(current - 2, total - 4));
	const end = Math.min(total, start + 4);
	const windowed = [];
	for (let p = start; p <= end; p++) {
		windowed.push(p);
	}
	return [...new Set([1, ...windowed, total])].sort((a, b) => a - b);
});

const range_label = computed(() => {
	if (!total_rows.value) return "";
	const start = (page.value - 1) * PAGE_SIZE + 1;
	const end = Math.min(page.value * PAGE_SIZE, total_rows.value);
	return `${start}–${end} sur ${total_rows.value}`;
});

function go_to_page(target) {
	if (target < 1 || target > total_pages.value || target === page.value) return;
	page.value = target;
	load_rows();
}

// ── actions ──────────────────────────────────────────────────────────────────
function open_account(row) {
	frappe.set_route("plan-comptable", row.name);
}

function new_account() {
	frappe.set_route("plan-comptable", "new");
}

function add_sub_account(row) {
	frappe.set_route("plan-comptable", "new", { parent: row.name });
}

const delete_target = ref(null);
const delete_dialog_open = ref(false);
const import_dialog_open = ref(false);

function on_imported() {
	// same class tab, fresh counts and rows
	load_counts();
	load_rows();
}

function ask_delete(row) {
	delete_target.value = row;
	delete_dialog_open.value = true;
}

function row_menu(row) {
	return [
		{ label: __("Ouvrir"), onClick: () => open_account(row) },
		{
			label: __("Supprimer"),
			condition: () => !row.is_standard,
			danger: true,
			onClick: () => ask_delete(row),
		},
	];
}

async function confirm_delete() {
	const row = delete_target.value;
	delete_dialog_open.value = false;
	delete_target.value = null;
	if (!row) return;
	try {
		await frappe.xcall("frappe.client.delete", { doctype: DOCTYPE, name: row.name });
		frappe.show_alert({ message: __("Compte supprimé."), indicator: "green" });
		load_counts();
		load_rows();
	} catch {
		// the server message is already surfaced by frappe.call
	}
}

// ── display helpers ──────────────────────────────────────────────────────────
function nature_label(row) {
	return row.is_group ? __("Regroupement") : __("Comptable");
}

function nature_theme(row) {
	return row.is_group ? "amber" : "blue";
}

function sens_theme(row) {
	if (row.sens === "C") return "green";
	if (row.sens === "D") return "red";
	return "gray";
}

// the hierarchy reads through a left offset that grows with the code length
function code_indent(row) {
	const depth = Math.max(0, (row.account_number || "").length - 1);
	return `${12 + depth * 14}px`;
}

// ── boot & context reactions ─────────────────────────────────────────────────
function on_context_changed(event, ctx) {
	const changed = (ctx?.entreprise || context_entreprise()) !== entreprise.value;
	entreprise.value = ctx?.entreprise || context_entreprise();
	entreprise_label.value = context_entreprise_label();
	if (mode.value !== "list") {
		// an account of another Entreprise may be on screen: back to the list
		frappe.set_route("plan-comptable", {});
	}
	if (changed && entreprise.value) {
		page.value = 1;
		load_counts();
		load_rows();
	}
}

onMounted(() => {
	if (entreprise.value) {
		load_counts();
		load_rows();
	}
	// the dock's "Contexte comptable" fires this jQuery event on every change
	const $ = window.jQuery;
	if ($) {
		$(document).on("axeane-context-changed", on_context_changed);
	}
});

onBeforeUnmount(() => {
	const $ = window.jQuery;
	if ($) {
		$(document).off("axeane-context-changed", on_context_changed);
	}
});

// ── account panel (create / edit) ────────────────────────────────────────────
function on_panel_title(title) {
	emit("title", title);
}

function on_account_saved(payload = {}) {
	// back to the list, on the class tab of the saved account
	if (payload.classe) {
		active_tab.value = ROOT_CLASSES.includes(payload.classe) ? payload.classe : "other";
	}
	page.value = 1;
	frappe.set_route("plan-comptable", {});
	load_counts();
	load_rows();
}

function on_account_deleted() {
	page.value = 1;
	frappe.set_route("plan-comptable", {});
	load_counts();
	load_rows();
}

// Navigating between list and the account panel keeps the list state
watch(
	() => props.route,
	(route) => {
		if (!route?.length) {
			emit("title", __("Plan comptable"));
		} else if (route[0] === "new") {
			emit("title", __("Nouveau compte"));
		} else {
			emit("title", route[0]);
		}
	},
	{ immediate: true }
);
</script>

<template>
	<div class="h-full overflow-y-auto">
		<!-- Render error captured within the island -->
		<div v-if="render_error" class="mx-auto w-full max-w-[1600px] px-6 lg:px-10 pt-4">
			<pre class="rounded border border-surface-red-3 bg-surface-red-1 p-3 text-p-sm text-ink-red-6 whitespace-pre-wrap">{{ render_error }}</pre>
		</div>

		<!-- ══ List mode ══ -->
		<div v-if="mode === 'list'" class="min-h-full">
			<!-- Sticky top bar -->
			<div class="sticky top-0 z-20 border-b border-surface-gray-2 bg-surface-white">
				<div class="mx-auto flex w-full max-w-[1600px] items-center justify-between gap-4 px-6 lg:px-10 py-3.5">
					<div class="flex min-w-0 items-center gap-3">
						<h1 class="truncate text-p-base font-semibold text-ink-gray-9">
							{{ __("Plan comptable") }}
						</h1>
						<div class="h-4 w-px bg-surface-gray-2" />
						<div
							v-if="entreprise"
							class="flex min-w-0 items-center gap-2"
							:title="__('Défini par le contexte comptable')"
						>
							<span class="inline-flex min-w-0 items-center gap-1.5 rounded-md border border-surface-gray-2 bg-surface-gray-1 px-2.5 py-1 text-p-sm font-medium text-ink-gray-7">
								<svg class="size-3.5 shrink-0 text-ink-gray-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<rect width="16" height="20" x="4" y="2" rx="2" ry="2" />
									<path d="M9 22v-4h6v4" />
									<path d="M8 6h.01" />
									<path d="M16 6h.01" />
									<path d="M12 10h.01" />
									<path d="M12 14h.01" />
									<path d="M16 14h.01" />
								</svg>
								<span class="truncate">{{ entreprise_label || entreprise }}</span>
							</span>
							<span class="hidden shrink-0 text-xs text-ink-gray-4 lg:inline">
								{{ __("Défini par le contexte comptable") }}
							</span>
						</div>
					</div>

					<div v-if="entreprise" class="flex items-center gap-2">
						<Button
							variant="subtle"
							:label="__('Importer un plan comptable')"
							@click="import_dialog_open = true"
						/>
						<Button variant="solid" :label="__('Nouveau compte')" @click="new_account" />
					</div>
				</div>
			</div>

			<!-- Content area -->
			<div class="mx-auto w-full max-w-[1600px] space-y-6 px-6 lg:px-10 py-6 pb-16">
				<!-- No context entreprise: nothing to show, the scope would be empty -->
				<div v-if="!entreprise" class="rounded-lg border border-surface-gray-2 bg-surface-white p-6 shadow-xs">
					<div class="flex flex-col items-center justify-center px-6 py-12 text-center">
						<div class="mb-4 flex size-14 items-center justify-center rounded-full bg-surface-gray-2 text-ink-gray-5">
							<svg class="size-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75">
								<rect width="16" height="20" x="4" y="2" rx="2" ry="2" />
								<path d="M9 22v-4h6v4" />
								<path d="M8 6h.01" />
								<path d="M16 6h.01" />
								<path d="M12 10h.01" />
								<path d="M12 14h.01" />
								<path d="M16 14h.01" />
							</svg>
						</div>
						<h3 class="text-p-base font-semibold text-ink-gray-9">
							{{ __("Choisissez une entreprise dans le contexte comptable") }}
						</h3>
						<p class="mt-1 max-w-sm text-p-sm text-ink-gray-5">
							{{ __("Le plan comptable suit l'entreprise définie dans le contexte comptable.") }}
						</p>
					</div>
				</div>

				<!-- No plan comptable for the context entreprise -->
				<div v-else-if="counts_loaded && !total_accounts" class="rounded-lg border border-surface-gray-2 bg-surface-white p-6 shadow-xs">
					<div class="flex flex-col items-center justify-center px-6 py-12 text-center">
						<div class="mb-4 flex size-14 items-center justify-center rounded-full bg-surface-gray-2 text-ink-gray-5">
							<svg class="size-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75">
								<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20" />
							</svg>
						</div>
						<h3 class="text-p-base font-semibold text-ink-gray-9">
							{{ __("Aucun plan comptable pour {0}", [entreprise_label || entreprise]) }}
						</h3>
						<p class="mt-1 max-w-sm text-p-sm text-ink-gray-5">
							{{ __("Importez le plan comptable de l'entreprise ou créez vos premiers comptes à la main.") }}
						</p>
						<div class="mt-6 flex items-center gap-2">
							<Button variant="subtle" :label="__('Importer un plan comptable')" @click="import_dialog_open = true" />
							<Button variant="solid" :label="__('Nouveau compte')" @click="new_account" />
						</div>
					</div>
				</div>

				<!-- Tabs + table -->
				<template v-else>
					<!-- Class tabs -->
					<div class="flex flex-wrap items-center gap-1 rounded-lg border border-surface-gray-2 bg-surface-gray-1 p-1">
						<button
							v-for="tab in CLASS_TABS"
							:key="tab.value"
							type="button"
							:class="[
								'inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-p-sm font-medium transition-colors',
								active_tab === tab.value
									? 'bg-surface-white text-ink-gray-9 shadow-xs'
									: 'text-ink-gray-6 hover:text-ink-gray-9',
							]"
							@click="switch_tab(tab.value)"
						>
							{{ __(tab.label) }}
							<span
								class="inline-block min-w-5 rounded-full px-1.5 py-0.5 text-center text-xs leading-4"
								:class="active_tab === tab.value
									? 'bg-surface-gray-1 text-ink-gray-6'
									: 'text-ink-gray-5'"
							>
								{{ tab_count(tab) }}
							</span>
						</button>
					</div>

					<!-- Table card -->
					<div class="overflow-hidden rounded-lg border border-surface-gray-2 bg-surface-white shadow-xs">
						<!-- Filter row -->
						<div class="flex flex-wrap items-center gap-3 border-b border-surface-gray-2 px-4 py-3">
							<input
								v-model="code_search"
								type="search"
								:placeholder="__('Code commence par...')"
								class="h-9 w-44 rounded-md border border-surface-gray-3 bg-surface-white px-3 text-p-sm text-ink-gray-9 placeholder:text-ink-gray-4 focus:border-ink-gray-5 focus:outline-none focus:ring-1 focus:ring-ink-gray-5"
								@input="on_search_input"
							/>
							<input
								v-model="name_search"
								type="search"
								:placeholder="__('Libellé contient...')"
								class="h-9 w-56 rounded-md border border-surface-gray-3 bg-surface-white px-3 text-p-sm text-ink-gray-9 placeholder:text-ink-gray-4 focus:border-ink-gray-5 focus:outline-none focus:ring-1 focus:ring-ink-gray-5"
								@input="on_search_input"
							/>
							<div class="w-44">
								<FormControl
									type="select"
									v-model="nature_filter"
									:options="NATURE_FILTERS"
									@update:model-value="on_filter_select"
								/>
							</div>
							<div class="w-28">
								<FormControl
									type="select"
									v-model="sens_filter"
									:options="SENS_FILTERS"
									@update:model-value="on_filter_select"
								/>
							</div>
							<Button
								v-if="has_active_filters"
								variant="ghost"
								:label="__('Retirer les filtres')"
								@click="reset_filters"
							/>
						</div>

						<div class="overflow-x-auto">
							<table class="w-full text-left border-collapse">
								<thead>
									<tr class="border-b border-surface-gray-2 bg-surface-gray-1">
										<th class="bg-surface-gray-1 px-4 py-3 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6">
											{{ __("Code") }}
										</th>
										<th class="bg-surface-gray-1 px-4 py-3 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6">
											{{ __("Libellé") }}
										</th>
										<th class="bg-surface-gray-1 px-4 py-3 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6">
											{{ __("Nature") }}
										</th>
										<th class="bg-surface-gray-1 px-4 py-3 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6">
											{{ __("Sens") }}
										</th>
										<th class="bg-surface-gray-1 px-4 py-3 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6">
											{{ __("Statut") }}
										</th>
										<th class="bg-surface-gray-1 px-4 py-3 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6 text-end">
											{{ __("Édition") }}
										</th>
									</tr>
								</thead>
								<tbody class="divide-y divide-surface-gray-2">
									<!-- Loading skeleton rows -->
									<template v-if="rows_loading">
										<tr v-for="i in 5" :key="i">
											<td v-for="j in 6" :key="j" class="px-4 py-3.5">
												<div class="h-4 w-3/4 animate-pulse rounded bg-surface-gray-2" />
											</td>
										</tr>
									</template>

									<!-- Account rows -->
									<template v-else-if="rows.length">
										<tr
											v-for="row in rows"
											:key="row.name"
											class="cursor-pointer transition-colors hover:bg-surface-gray-1"
											@click="open_account(row)"
										>
											<td
												class="whitespace-nowrap py-3 pr-4 font-mono text-p-sm"
												:class="row.is_group ? 'font-semibold text-ink-gray-9' : 'text-ink-gray-7'"
												:style="{ paddingLeft: code_indent(row) }"
											>
												{{ row.account_number }}
											</td>
											<td class="px-4 py-3 text-p-sm text-ink-gray-9">
												{{ row.account_name }}
											</td>
											<td class="px-4 py-3">
												<Badge variant="subtle" size="sm" :theme="nature_theme(row)" :label="nature_label(row)" />
											</td>
											<td class="px-4 py-3">
												<Badge variant="subtle" size="sm" :theme="sens_theme(row)" :label="row.sens || '—'" />
											</td>
											<td class="px-4 py-3">
												<div v-if="row.is_standard" class="flex items-center gap-1.5 text-p-sm text-ink-gray-6">
													<svg class="size-3.5 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
														<rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
														<path d="M7 11V7a5 5 0 0 1 10 0v4" />
													</svg>
													{{ __("Standard") }}
												</div>
												<span v-else class="text-p-sm text-ink-gray-5">
													{{ __("Personnalisé") }}
												</span>
											</td>
											<td class="px-4 py-2.5 text-end" @click.stop>
												<div class="inline-flex items-center justify-end gap-0.5">
													<span v-if="!row.is_group" :title="__('Un compte comptable ne peut pas avoir de sous-comptes')">
														<Button variant="ghost" disabled>
															<svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
																<line x1="12" y1="5" x2="12" y2="19" />
																<line x1="5" y1="12" x2="19" y2="12" />
															</svg>
														</Button>
													</span>
													<Button v-else variant="ghost" :title="__('Ajouter un sous-compte')" @click="add_sub_account(row)">
														<svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
															<line x1="12" y1="5" x2="12" y2="19" />
															<line x1="5" y1="12" x2="19" y2="12" />
														</svg>
													</Button>
													<Dropdown :options="row_menu(row)" placement="right">
														<template #default>
															<Button variant="ghost" :title="__('Actions')">
																<svg class="size-4" viewBox="0 0 24 24" fill="currentColor">
																	<circle cx="5" cy="12" r="1.6" />
																	<circle cx="12" cy="12" r="1.6" />
																	<circle cx="19" cy="12" r="1.6" />
																</svg>
															</Button>
														</template>
													</Dropdown>
												</div>
											</td>
										</tr>
									</template>

									<!-- Filters matched nothing -->
									<template v-else>
										<tr>
											<td colspan="6">
												<div class="flex flex-col items-center justify-center px-6 py-12 text-center">
													<div class="mb-3 flex size-12 items-center justify-center rounded-full bg-surface-gray-2 text-ink-gray-4">
														<svg class="size-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75">
															<circle cx="11" cy="11" r="8" />
															<path d="m21 21-4.3-4.3" />
															<line x1="8" y1="11" x2="14" y2="11" />
														</svg>
													</div>
													<p class="text-p-sm font-medium text-ink-gray-7">{{ __("Aucun résultat") }}</p>
													<p class="mt-1 text-xs text-ink-gray-5">
														{{ __("Aucun compte ne correspond aux filtres actifs.") }}
													</p>
													<div class="mt-4">
														<Button variant="subtle" :label="__('Retirer les filtres')" @click="reset_filters" />
													</div>
												</div>
											</td>
										</tr>
									</template>
								</tbody>
							</table>
						</div>

						<!-- Pagination footer -->
						<div v-if="!rows_loading && total_rows > 0" class="flex flex-col gap-3 border-t border-surface-gray-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
							<span class="text-p-sm text-ink-gray-5">
								{{ range_label }}
							</span>
							<div class="flex items-center gap-1">
								<Button variant="ghost" :label="__('Précédent')" :disabled="page <= 1" @click="go_to_page(page - 1)" />
								<button
									v-for="p in page_numbers"
									:key="p"
									type="button"
									:class="[
										'min-w-8 rounded-md px-2 py-1 text-p-sm font-medium transition-colors',
										page === p
											? 'bg-surface-gray-2 text-ink-gray-9'
											: 'text-ink-gray-6 hover:bg-surface-gray-1 hover:text-ink-gray-9',
									]"
									@click="go_to_page(p)"
								>
									{{ p }}
								</button>
								<Button variant="ghost" :label="__('Suivant')" :disabled="page >= total_pages" @click="go_to_page(page + 1)" />
							</div>
						</div>
					</div>
				</template>
			</div>
		</div>

		<!-- ══ New / record mode — the account panel ══ -->
		<PlanComptableAccount
			v-else
			:mode="mode"
			:record-name="mode === 'record' ? props.route?.[0] || '' : ''"
			:entreprise="entreprise"
			:parent-name="props.query?.parent || ''"
			@title="on_panel_title"
			@saved="on_account_saved"
			@deleted="on_account_deleted"
		/>

		<!-- Delete confirmation -->
		<Dialog v-model="delete_dialog_open" :title="__('Supprimer le compte')">
			<template #default>
				<p class="text-p-sm text-ink-gray-7">
					{{
						__("Supprimer le compte {0} — {1} ? Cette action est définitive.", [
							delete_target?.account_number || "",
							delete_target?.account_name || "",
						])
					}}
				</p>
			</template>
			<template #actions>
				<Button variant="subtle" :label="__('Annuler')" @click="delete_dialog_open = false" />
				<Button variant="solid" theme="red" :label="__('Supprimer')" @click="confirm_delete" />
			</template>
		</Dialog>

		<!-- Import dialog (a copy also lives in the Entreprise page folder) -->
		<PlanComptableImportDialog
			v-model:open="import_dialog_open"
			:entreprise="entreprise"
			@imported="on_imported"
		/>
	</div>
</template>
