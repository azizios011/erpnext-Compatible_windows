<!-- Payable Transaction — Frappe UI island page for the Entries doctypes.

     Routes (props.route / props.query):
       - /app/payable                     → list of this doctype's entries
       - /app/payable/creation            → new entry (optional query params
         source_doctype, source_name, date_operation, ref_doc, journal)
       - /app/payable/modify/<MVT>        → edit a saved entry
       - /app/payable/inspect/<MVT>       → read-only view
       - /app/payable/<MVT>               → redirected to inspect
     Three modes share one screen: creation and modify are editable, inspect
     is fully read-only (no model buttons, no save, no delete). The
     Entreprise/Exercice never come from the client: the controller takes them
     from the accounting context on before_insert, get_list is scoped
     server-side (SCOPED_DOCTYPES), and the third-party rule + the
     can_modify / existence / context checks come from entries.api.open_entry.

     The receivable island is the same code with different constants — shared
     components (entry_lines_grid, totals_footer, model_dialogs) exist as
     identical copies in both page folders (toolchain rule, bd3ffc3cab). -->
<script setup>
import { computed, onErrorCaptured, onMounted, ref, watch } from "vue";
import { Badge, Button, FormControl } from "frappe-ui";

import EntryLinesGrid from "./entry_lines_grid.vue";
import ModelDialogs from "./model_dialogs.vue";
import TotalsFooter from "./totals_footer.vue";

// ── page constants (the only difference between the two islands) ─────────────
const DOCTYPE = "Receivable Transaction";
const PAGE = "receivable";
const TITLE = "Receivable Transaction";
const DEFAULT_JOURNAL = "VT";

const frappe = window.frappe;
const __ = window.__;
const flt = (v) => {
	const n = parseFloat(v);
	return Number.isFinite(n) ? n : 0;
};

const props = defineProps({
	route: { type: Array, default: () => [] },
	query: { type: Object, default: () => ({}) },
});
const emit = defineEmits(["title"]);

const METHOD = "erpnext.custom_modules.entries.api";
const PAGE_SIZE = 50;

// ── helpers ──────────────────────────────────────────────────────────────────
function context_obj() {
	return window.axeane?.context?.get?.() || frappe.boot?.axeane_context || null;
}
function context_entreprise() {
	return context_obj()?.entreprise || "";
}
function context_exercice() {
	return context_obj()?.exercice || "";
}
function context_headline() {
	const ctx = context_obj() || {};
	return [ctx.entreprise_label || ctx.entreprise, ctx.exercice_label || ctx.exercice]
		.filter(Boolean)
		.join(" · ");
}

// frappe.xcall rejects with r?.message, which is undefined for server-thrown
// errors (those are already surfaced by the standard error dialog).
function extract_error(error) {
	if (typeof error === "string" && error) return error;
	if (error && typeof error === "object") {
		if (error.message) return String(error.message);
		if (error._server_messages) {
			try {
				const messages =
					typeof error._server_messages === "string"
						? JSON.parse(error._server_messages)
						: error._server_messages;
				const text = (messages || [])
					.map((m) => (typeof m === "string" ? JSON.parse(m)?.message : m?.message))
					.filter(Boolean)
					.join(" · ");
				if (text) return text;
			} catch {
				// fall through
			}
		}
		if (error.exc) return String(error.exc).split("\n").pop();
	}
	return __("Une erreur est survenue — voir le message d'erreur affiché.");
}

// A render error inside the island blanks it silently otherwise; captured here
// the message shows on the page itself (same pattern as plan_comptable).
const render_error = ref(null);
onErrorCaptured((error, instance, info) => {
	render_error.value = `${error?.message || String(error)} (${info})`;
	return false;
});

// ── routing: list / creation / modify / inspect ──────────────────────────────
const mode = computed(() => {
	if (!props.route?.length) return "list";
	const head = props.route[0];
	if (head === "creation" || head === "modify" || head === "inspect") return head;
	return "redirect";
});
const record_name = computed(() =>
	mode.value === "modify" || mode.value === "inspect" ? props.route?.[1] || "" : ""
);

// ── list mode ────────────────────────────────────────────────────────────────
const entries = ref([]);
const entries_loading = ref(false);
const total_rows = ref(0);
const page = ref(1);
const list_search = ref("");
const list_journal = ref("all");
const date_from = ref("");
const date_to = ref("");

const journal_options = ref([]);

function list_filters() {
	const filters = { entreprise: context_entreprise(), exercice: context_exercice() };
	if (list_journal.value !== "all") filters.journal = list_journal.value;
	if (date_from.value && date_to.value) {
		filters.date_operation = ["between", [date_from.value, date_to.value]];
	} else if (date_from.value) {
		filters.date_operation = [">=", date_from.value];
	} else if (date_to.value) {
		filters.date_operation = ["<=", date_to.value];
	}
	return filters;
}

async function load_entries() {
	if (!context_entreprise() || !context_exercice()) return;
	entries_loading.value = true;
	try {
		const filters = list_filters();
		const args = {
			doctype: DOCTYPE,
			fields: ["name", "date_operation", "journal", "ref_doc", "libelle", "total_debit", "total_credit", "status"],
			filters,
			order_by: "creation desc",
			limit_start: (page.value - 1) * PAGE_SIZE,
			limit_page_length: PAGE_SIZE,
		};
		const term = list_search.value.trim();
		if (term) {
			args.or_filters = [
				["name", "like", `%${term}%`],
				["ref_doc", "like", `%${term}%`],
				["libelle", "like", `%${term}%`],
			];
		}
		entries.value = await frappe.xcall("frappe.client.get_list", args);
		// this frappe rejects SQL functions as strings in SELECT: counts go
		// through the dict syntax ({'COUNT': '*', 'as': ...})
		const count_args = { doctype: DOCTYPE, fields: [{ COUNT: "name", as: "n" }], filters };
		if (term) count_args.or_filters = args.or_filters;
		const counted = await frappe.xcall("frappe.client.get_list", count_args);
		total_rows.value = (counted && counted[0] && counted[0].n) || 0;
		if (total_rows.value && page.value > total_pages.value) {
			page.value = total_pages.value;
			entries.value = await frappe.xcall("frappe.client.get_list", args);
		}
	} finally {
		entries_loading.value = false;
	}
}

const total_pages = computed(() => Math.max(1, Math.ceil(total_rows.value / PAGE_SIZE)));
const range_label = computed(() => {
	if (!total_rows.value) return "";
	const start = (page.value - 1) * PAGE_SIZE + 1;
	const end = Math.min(page.value * PAGE_SIZE, total_rows.value);
	return `${start}–${end} sur ${total_rows.value}`;
});

function go_to_page(target) {
	if (target < 1 || target > total_pages.value || target === page.value) return;
	page.value = target;
	load_entries();
}

function open_entry(row) {
	frappe.set_route(PAGE, "inspect", row.name);
}
function new_entry() {
	frappe.set_route(PAGE, "creation");
}

let search_timer = null;
function on_search_input() {
	if (search_timer) clearTimeout(search_timer);
	search_timer = setTimeout(() => {
		page.value = 1;
		load_entries();
	}, 300);
}

function on_list_filter_change() {
	page.value = 1;
	load_entries();
}

// ── form mode ────────────────────────────────────────────────────────────────
const empty_row = () => ({ account: "", libelle: "", fact: "", tresorerie: "", debit: "", credit: "" });

const doc = ref(null);
const loading_doc = ref(false);
const status = ref("Brouillon");
const party_rule = ref({ prefix: "", side: "", label: "" });
const source_attachment = ref("");
const saving = ref(false);
const deleting = ref(false);
const form_error = ref(null);
const page_error = ref(null);
const can_modify = ref(false);
const model_dialogs_ref = ref(null);

const is_inspect = computed(() => mode.value === "inspect");
const editable = computed(() => mode.value !== "inspect");
const is_new = computed(() => mode.value === "creation");
const has_source = computed(() => Boolean(doc.value?.source_doctype && doc.value?.source_name));
const show_tresorerie = computed(() => Boolean(Number(frappe.boot?.axeane_context?.flux_tresorerie_autorise)));

const status_theme_for = (s) => (s === "Comptabilise" ? "green" : "orange");
const status_label_for = (s) => (s === "Comptabilise" ? "Comptabilise" : "Brouillon");
const status_theme = computed(() => status_theme_for(status.value));
const status_label = computed(() => status_label_for(status.value));

const panel_title = computed(() => {
	if (is_inspect.value) return doc.value?.mvt || record_name.value;
	if (mode.value === "modify") return doc.value?.mvt || record_name.value;
	return doc.value?.mvt || __("Nouvelle écriture");
});

const currency_options = ref([]);

async function load_journal_and_devise_options() {
	const journals = await frappe.xcall("frappe.client.get_list", {
		doctype: "Journal",
		fields: ["name"],
		limit_page_length: 0,
	});
	journal_options.value = (journals || []).map((j) => ({ label: j.name, value: j.name }));
	const currencies = await frappe.xcall("frappe.client.get_list", {
		doctype: "Currency",
		fields: ["name"],
		limit_page_length: 0,
	});
	currency_options.value = (currencies || []).map((c) => ({ label: c.name, value: c.name }));
}

const is_pdf = (url) => String(url || "").toLowerCase().split("?")[0].endsWith(".pdf");

async function load_attachment() {
	source_attachment.value = "";
	if (!has_source.value) return;
	const r = await frappe.xcall("frappe.client.get_value", {
		doctype: doc.value.source_doctype,
		filters: { name: doc.value.source_name },
		fieldname: "attachment",
	});
	source_attachment.value = (r && r.attachment) || "";
}

// ── init (creation / modify / inspect) ───────────────────────────────────────
async function init_new() {
	form_error.value = null;
	page_error.value = null;
	can_modify.value = true;
	status.value = "Brouillon";
	source_attachment.value = "";
	const q = props.query || {};
	const source_doctype = q.source_doctype || "";
	const source_name = q.source_name || "";
	if (source_doctype && source_name) {
		// a source that already has an entry redirects to its modify/inspect
		// view instead of opening a second form (one entry per document)
		const target = await frappe
			.xcall(`${METHOD}.open_entry`, {
				entry_doctype: DOCTYPE,
				mode: "auto",
				source_doctype,
				source_name,
			})
			.catch((error) => {
				page_error.value = [extract_error(error)];
				return null;
			});
		if (!target) return;
		if (target.mode !== "creation") {
			frappe.show_alert({
				message: __("This document already has an entry; opening it."),
				indicator: "orange",
			});
			frappe.set_route(...target.route);
			return;
		}
	}
	doc.value = {
		doctype: DOCTYPE,
		date_operation: q.date_operation || frappe.datetime.get_today(),
		journal: q.journal || DEFAULT_JOURNAL,
		devise: "TND",
		mvt: "",
		ref_doc: q.ref_doc || "",
		libelle: "",
		apply_libelle_to_lines: 0,
		source_doctype,
		source_name,
		lines: [empty_row(), empty_row()],
	};
	await load_defaults();
}

async function init_record(name, head) {
	form_error.value = null;
	page_error.value = null;
	loading_doc.value = true;
	try {
		// the resolver enforces existence, permissions and the context match,
		// and reports whether the exercice still allows modification
		const target = await frappe.xcall(`${METHOD}.open_entry`, {
			entry_doctype: DOCTYPE,
			mode: head,
			name,
		});
		can_modify.value = Boolean(target?.can_modify);
		const loaded = await frappe.xcall("frappe.client.get", { doctype: DOCTYPE, name });
		doc.value = {
			doctype: DOCTYPE,
			name: loaded.name,
			date_operation: loaded.date_operation || frappe.datetime.get_today(),
			journal: loaded.journal || DEFAULT_JOURNAL,
			devise: loaded.devise || "TND",
			mvt: loaded.mvt || "",
			ref_doc: loaded.ref_doc || "",
			libelle: loaded.libelle || "",
			apply_libelle_to_lines: loaded.apply_libelle_to_lines ? 1 : 0,
			source_doctype: loaded.source_doctype || "",
			source_name: loaded.source_name || "",
			lines: (loaded.lines || []).map((line) => ({
				account: line.account || "",
				libelle: line.libelle || "",
				fact: line.fact || "",
				tresorerie: line.tresorerie || "",
				debit: line.debit,
				credit: line.credit,
			})),
		};
		status.value = loaded.status || "Brouillon";
		await load_defaults();
	} catch (error) {
		doc.value = null;
		can_modify.value = false;
		page_error.value = [extract_error(error)];
	} finally {
		loading_doc.value = false;
	}
}

/** New-form prefill and modify/inspect rule + attachment loads — the same
 * data the classic bundle's load_entry_defaults fetches, through the same
 * api.py. Model lines only ever land on a creation form. */
async function load_defaults() {
	const source_doctype = doc.value.source_doctype || "";
	const source_name = doc.value.source_name || "";
	const defaults = await frappe.xcall(`${METHOD}.get_entry_defaults`, {
		entry_doctype: DOCTYPE,
		source_doctype,
		source_name,
	});
	party_rule.value = {
		prefix: defaults.tiers_prefix || "",
		side: defaults.tiers_side || "",
		label: defaults.tiers_label || "",
	};
	if (defaults.mvt && !doc.value.mvt) doc.value.mvt = defaults.mvt;
	if (!doc.value.ref_doc && defaults.ref_doc) doc.value.ref_doc = defaults.ref_doc;
	if (defaults.attachment) source_attachment.value = defaults.attachment;
	else await load_attachment();

	const is_releve_vente = source_doctype === "Releve Vente" && source_name;
	if (is_releve_vente && mode.value === "creation") {
		const result = await frappe.xcall(`${METHOD}.get_model_lines`, {
			source_doctype,
			source_name,
			journal: doc.value.journal || "",
		});
		if ((result.lines || []).length) apply_model_lines(result.lines);
		if ((result.warnings || []).length) {
			frappe.msgprint({
				title: __("Operations without a model"),
				message:
					__("No Journal Model matched these operations; enter their lines manually:") +
					"<br>" +
					frappe.utils.escape_html(result.warnings.join(", ")),
				indicator: "orange",
			});
		}
	} else if (mode.value === "creation" && (defaults.lines || []).length && !doc.value.lines.some((l) => l.account)) {
		apply_model_lines(defaults.lines);
	}
}

function apply_model_lines(lines) {
	doc.value.lines = (lines || []).map((line) => ({
		account: line.account || "",
		libelle: line.libelle || "",
		fact: line.fact || "",
		tresorerie: "",
		debit: flt(line.debit),
		credit: flt(line.credit),
	}));
}

// ── apply libelle to all lines (live, while checked) ─────────────────────────
watch(
	() => [doc.value?.libelle, doc.value?.apply_libelle_to_lines],
	([libelle, apply]) => {
		if (apply && libelle) {
			(doc.value?.lines || []).forEach((line) => {
				line.libelle = libelle;
			});
		}
	}
);

// ── save / delete ────────────────────────────────────────────────────────────
function build_payload() {
	return {
		doctype: DOCTYPE,
		date_operation: doc.value.date_operation,
		journal: doc.value.journal,
		devise: doc.value.devise || "TND",
		ref_doc: doc.value.ref_doc || "",
		libelle: doc.value.libelle || "",
		apply_libelle_to_lines: doc.value.apply_libelle_to_lines ? 1 : 0,
		source_doctype: doc.value.source_doctype || "",
		source_name: doc.value.source_name || "",
		// never entreprise / exercice / mvt / status: the controller owns them
		lines: (doc.value.lines || [])
			.filter((line) => line.account || flt(line.debit) || flt(line.credit))
			.map((line) => ({
				account: line.account,
				libelle: line.libelle || "",
				fact: line.fact || "",
				tresorerie: line.tresorerie || "",
				debit: flt(line.debit),
				credit: flt(line.credit),
			})),
	};
}

async function save_entry() {
	if (!doc.value) return;
	form_error.value = null;
	saving.value = true;
	try {
		let saved;
		if (is_new.value) {
			saved = await frappe.xcall("frappe.client.insert", { doc: build_payload() });
		} else {
			saved = await frappe.xcall("frappe.client.save", { doc: { ...build_payload(), name: doc.value.name } });
		}
		frappe.show_alert({ message: __("Entry posted to the ledger."), indicator: "green" });
		if (is_new.value && saved?.name) {
			// a fresh creation continues in modify mode
			frappe.set_route(PAGE, "modify", saved.name);
		} else {
			status.value = saved?.status || "Comptabilise";
		}
	} catch (error) {
		form_error.value = [extract_error(error)];
	} finally {
		saving.value = false;
	}
}

function delete_entry() {
	if (!doc.value?.name) return;
	frappe.confirm(__("Supprimer l'ecriture {0} ?", [doc.value.name]), async () => {
		deleting.value = true;
		try {
			await frappe.xcall("frappe.client.delete", { doctype: DOCTYPE, name: doc.value.name });
			frappe.show_alert({ message: __("Ecriture supprimee."), indicator: "green" });
			frappe.set_route(PAGE, {});
		} catch (error) {
			form_error.value = [extract_error(error)];
		} finally {
			deleting.value = false;
		}
	});
}

function open_source() {
	if (has_source.value) {
		frappe.set_route("Form", doc.value.source_doctype, doc.value.source_name);
	}
}

function go_back() {
	frappe.set_route(PAGE, {});
}

// ── boot & route reactions ───────────────────────────────────────────────────
onMounted(async () => {
	await load_journal_and_devise_options();
});

// Navigating between list and form keeps the list state
watch(
	() => props.route,
	(route) => {
		if (!route?.length) {
			emit("title", __(TITLE));
			load_entries();
			return;
		}
		const head = route[0];
		if (head === "creation") {
			emit("title", `${__(TITLE)} · ${__("Création")}`);
			init_new();
			return;
		}
		if (head === "modify" || head === "inspect") {
			if (!route[1]) {
				page_error.value = [__("Cette route demande le numéro d'une ecriture.")];
				emit("title", __(TITLE));
				return;
			}
			const word = head === "modify" ? "Modification" : "Consultation";
			emit("title", `${__(TITLE)} · ${__(word)} ${route[1]}`);
			init_record(route[1], head);
			return;
		}
		// /app/payable/<MVT> without a mode: the inspect view
		frappe.set_route(PAGE, "inspect", head);
	},
	{ immediate: true }
);
</script>

<template>
	<div class="h-full overflow-y-auto">
		<!-- Render error captured within the island -->
		<div v-if="render_error" class="mx-auto w-full max-w-[1400px] px-6 pt-4">
			<pre class="whitespace-pre-wrap rounded border border-surface-red-3 bg-surface-red-1 p-3 text-p-sm text-ink-red-6">{{ render_error }}</pre>
		</div>

		<!-- ══ List mode ══ -->
		<div v-if="mode === 'list'" class="min-h-full">
			<!-- Sticky top bar -->
			<div class="sticky top-0 z-20 border-b border-surface-gray-2 bg-surface-white">
				<div class="flex w-full items-center justify-between gap-4 px-6 py-3.5">
					<h1 class="truncate text-p-base font-semibold text-ink-gray-9">{{ __(TITLE) }}</h1>
					<Button variant="solid" :label="__('Nouvelle écriture')" @click="new_entry" />
				</div>
			</div>

			<!-- Content area -->
			<div class="space-y-4 px-6 py-4 pb-16">
				<!-- No context entreprise/exercice: nothing to show -->
				<div v-if="!context_entreprise() || !context_exercice()" class="rounded-lg border border-surface-gray-2 bg-surface-white p-6 shadow-xs">
					<div class="flex flex-col items-center justify-center px-6 py-12 text-center">
						<h3 class="text-p-base font-semibold text-ink-gray-9">
							{{ __("Choisissez une entreprise et un exercice dans le contexte comptable") }}
						</h3>
						<p class="mt-1 max-w-sm text-p-sm text-ink-gray-5">
							{{ __("Les ecritures suivent l'entreprise et l'exercice du contexte comptable.") }}
						</p>
					</div>
				</div>

				<template v-else>
					<!-- Filter row -->
					<div class="flex flex-wrap items-center gap-3 rounded-lg border border-surface-gray-2 bg-surface-white px-3 py-2.5 shadow-xs">
						<input
							v-model="list_search"
							type="search"
							:placeholder="__('MVT, réf ou libellé...')"
							class="h-8 w-56 rounded border border-surface-gray-3 bg-surface-white px-2.5 text-p-sm text-ink-gray-9 placeholder:text-ink-gray-4 focus:border-ink-gray-5 focus:outline-none focus:ring-1 focus:ring-ink-gray-5"
							@input="on_search_input"
						/>
						<div class="w-44">
							<FormControl
								v-model="list_journal"
								type="select"
								:options="[{ label: __('Journal: tous'), value: 'all' }, ...journal_options]"
								@update:model-value="on_list_filter_change"
							/>
						</div>
						<input v-model="date_from" type="date" class="h-8 rounded border border-surface-gray-3 bg-surface-white px-2 text-p-sm text-ink-gray-9 focus:border-ink-gray-5 focus:outline-none focus:ring-1 focus:ring-ink-gray-5" @change="on_list_filter_change" />
						<span class="text-xs text-ink-gray-4">→</span>
						<input v-model="date_to" type="date" class="h-8 rounded border border-surface-gray-3 bg-surface-white px-2 text-p-sm text-ink-gray-9 focus:border-ink-gray-5 focus:outline-none focus:ring-1 focus:ring-ink-gray-5" @change="on_list_filter_change" />
					</div>

					<!-- Table card -->
					<div class="overflow-hidden rounded-lg border border-surface-gray-2 bg-surface-white shadow-xs">
						<div class="overflow-x-auto">
							<table class="w-full border-collapse text-left">
								<thead>
									<tr class="border-b border-surface-gray-2 bg-surface-gray-1">
										<th class="bg-surface-gray-1 px-3 py-2 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6">{{ __("MVT") }}</th>
										<th class="bg-surface-gray-1 px-3 py-2 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6">{{ __("Date Operation") }}</th>
										<th class="bg-surface-gray-1 px-3 py-2 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6">{{ __("Journal") }}</th>
										<th class="bg-surface-gray-1 px-3 py-2 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6">{{ __("Ref/N°doc") }}</th>
										<th class="bg-surface-gray-1 px-3 py-2 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6">{{ __("Libelle") }}</th>
										<th class="bg-surface-gray-1 px-3 py-2 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6 text-end">{{ __("Tot Debit") }}</th>
										<th class="bg-surface-gray-1 px-3 py-2 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6 text-end">{{ __("Tot Credit") }}</th>
										<th class="bg-surface-gray-1 px-3 py-2 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6 text-center">{{ __("Status") }}</th>
									</tr>
								</thead>
								<tbody class="divide-y divide-surface-gray-2">
									<template v-if="entries_loading">
										<tr v-for="i in 5" :key="i">
											<td v-for="j in 8" :key="j" class="px-3 py-3">
												<div class="h-4 w-3/4 animate-pulse rounded bg-surface-gray-2" />
											</td>
										</tr>
									</template>
									<template v-else-if="entries.length">
										<tr
											v-for="row in entries"
											:key="row.name"
											class="cursor-pointer transition-colors hover:bg-surface-gray-1"
											@click="open_entry(row)"
										>
											<td class="whitespace-nowrap px-3 py-2.5 font-mono text-p-sm font-semibold text-ink-gray-9">{{ row.name }}</td>
											<td class="whitespace-nowrap px-3 py-2.5 text-p-sm text-ink-gray-7">{{ row.date_operation || "—" }}</td>
											<td class="px-3 py-2.5 text-p-sm text-ink-gray-7">{{ row.journal || "—" }}</td>
											<td class="px-3 py-2.5 text-p-sm text-ink-gray-7">{{ row.ref_doc || "—" }}</td>
											<td class="px-3 py-2.5 text-p-sm text-ink-gray-7">{{ row.libelle || "—" }}</td>
											<td class="px-3 py-2.5 text-end text-p-sm tabular-nums text-ink-gray-7">{{ flt(row.total_debit).toFixed(3) }}</td>
											<td class="px-3 py-2.5 text-end text-p-sm tabular-nums text-ink-gray-7">{{ flt(row.total_credit).toFixed(3) }}</td>
											<td class="px-3 py-2.5 text-center">
												<Badge variant="subtle" size="sm" :theme="status_theme_for(row.status)" :label="status_label_for(row.status)" />
											</td>
										</tr>
									</template>
									<template v-else>
										<tr>
											<td colspan="8">
												<div class="flex flex-col items-center justify-center px-6 py-12 text-center">
													<p class="text-p-sm font-medium text-ink-gray-7">{{ __("Aucun résultat") }}</p>
													<p class="mt-1 text-xs text-ink-gray-5">{{ __("Aucune ecriture ne correspond aux filtres actifs.") }}</p>
												</div>
											</td>
										</tr>
									</template>
								</tbody>
							</table>
						</div>
						<div v-if="!entries_loading && total_rows > 0" class="flex items-center justify-between border-t border-surface-gray-2 px-3 py-2">
							<span class="text-p-sm text-ink-gray-5">{{ range_label }}</span>
							<div class="flex items-center gap-2">
								<Button variant="ghost" :label="__('Précédent')" :disabled="page <= 1" @click="go_to_page(page - 1)" />
								<Button variant="ghost" :label="__('Suivant')" :disabled="page >= total_pages" @click="go_to_page(page + 1)" />
							</div>
						</div>
					</div>
				</template>
			</div>
		</div>

		<!-- ══ Form modes (creation / modify / inspect) ══ -->
		<div v-else class="min-h-full">
			<!-- Sticky top bar -->
			<div class="sticky top-0 z-20 border-b border-surface-gray-2 bg-surface-white">
				<div class="flex w-full items-center justify-between gap-4 px-6 py-3.5">
					<div class="flex min-w-0 items-center gap-3">
						<Button variant="ghost" :label="`← ${__(TITLE)}`" @click="go_back" />
						<div class="h-4 w-px bg-surface-gray-2" />
						<h1 class="truncate font-mono text-p-base font-semibold text-ink-gray-9">{{ panel_title }}</h1>
						<Badge v-if="mode !== 'creation'" variant="subtle" size="sm" :theme="status_theme" :label="status_label" />
					</div>
					<div class="flex items-center gap-2">
						<template v-if="mode !== 'inspect'">
							<Button variant="outline" :label="__('Appel Modele')" @click="model_dialogs_ref?.open_appel()" />
							<Button variant="outline" :label="__('Enreg. Modele')" @click="model_dialogs_ref?.open_enreg()" />
							<Button v-if="has_source" variant="ghost" :label="__('Modifier la ligne source')" @click="open_source" />
						</template>
						<template v-if="mode === 'modify'">
							<Button variant="subtle" :label="__('Consulter')" @click="frappe.set_route(PAGE, 'inspect', doc.name)" />
							<Button variant="outline" theme="red" :label="__('Supprimer')" :loading="deleting" @click="delete_entry" />
						</template>
						<Button v-if="mode === 'inspect' && has_source" variant="outline" :label="__('Voir la source')" @click="open_source" />
						<Button
							v-if="mode === 'inspect' && can_modify"
							variant="solid"
							:label="__('Modifier')"
							@click="frappe.set_route(PAGE, 'modify', doc.name)"
						/>
						<Button v-if="mode !== 'inspect'" variant="solid" :label="__('Enregistrer')" :loading="saving" @click="save_entry" />
					</div>
				</div>
			</div>

			<!-- Content -->
			<div class="space-y-4 px-6 pb-4 pt-4">
				<!-- Headline: accounting context + source link -->
				<div class="flex items-center gap-2 text-p-sm text-ink-gray-6">
					<span>{{ context_headline() }}</span>
					<template v-if="has_source">
						<span class="text-ink-gray-4">—</span>
						<Button variant="ghost" :label="mode === 'inspect' ? __('Voir la source') : `${__(doc.source_doctype)} ${doc.source_name}`" @click="open_source" />
					</template>
				</div>

				<!-- Page-level error: unknown route, missing entry, wrong doctype... -->
				<div v-if="page_error?.length" class="rounded-lg border border-surface-red-3 bg-surface-red-1 p-4">
					<div class="flex items-center gap-2 text-p-sm font-semibold text-ink-red-8">
						<svg class="size-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
							<line x1="12" y1="9" x2="12" y2="13" />
							<line x1="12" y1="17" x2="12.01" y2="17" />
						</svg>
						<span>{{ __("Vérifiez les points suivants") }}</span>
					</div>
					<ul class="mt-2 list-disc space-y-1 pl-5 text-p-sm text-ink-red-7">
						<li v-for="(message, index) in page_error" :key="index">{{ message }}</li>
					</ul>
				</div>

				<template v-else>
					<!-- Loading skeleton -->
					<div v-if="loading_doc" class="rounded-lg border border-surface-gray-2 bg-surface-white p-5 shadow-xs">
						<div class="grid grid-cols-1 gap-3.5 md:grid-cols-3">
							<div v-for="i in 6" :key="i" class="h-10 animate-pulse rounded bg-surface-gray-2" />
						</div>
						<div class="mt-4 h-24 animate-pulse rounded bg-surface-gray-2" />
					</div>

					<!-- Header card -->
					<div v-else-if="doc" class="rounded-lg border border-surface-gray-2 bg-surface-white p-5 shadow-xs">
						<div class="grid grid-cols-1 gap-x-6 gap-y-3.5 md:grid-cols-3">
							<FormControl v-model="doc.date_operation" type="date" :label="__('Date Operation')" :required="true" :disabled="is_inspect" />
							<FormControl
								v-model="doc.journal"
								type="select"
								:label="__('Journal')"
								:required="true"
								:options="journal_options"
								:disabled="is_inspect"
							/>
							<FormControl
								v-model="doc.devise"
								type="select"
								:label="__('Devise')"
								:options="currency_options"
								:disabled="is_inspect"
							/>
							<FormControl v-model="doc.mvt" :label="__('MVT')" :disabled="true" />
							<FormControl v-model="doc.ref_doc" :label="__('Ref/N°doc')" :required="true" :disabled="is_inspect" />
							<FormControl v-model="doc.libelle" :label="__('Libelle')" :disabled="is_inspect" />
							<FormControl
								v-model="doc.apply_libelle_to_lines"
								type="checkbox"
								:label="__('Apply libelle to all lines')"
								:disabled="is_inspect"
							/>
						</div>
					</div>

					<!-- Lines card -->
					<div v-if="doc && !loading_doc" class="rounded-lg border border-surface-gray-2 bg-surface-white p-5 shadow-xs">
						<EntryLinesGrid
							:lines="doc.lines"
							:party-rule="party_rule"
							:show-tresorerie="show_tresorerie"
							:read-only="is_inspect"
							@add-row="doc.lines.push(empty_row())"
							@remove-row="(index) => doc.lines.splice(index, 1)"
						/>
					</div>

					<!-- Source attachment preview -->
					<div v-if="has_source && !loading_doc" class="rounded-lg border border-surface-gray-2 bg-surface-white p-5 shadow-xs">
						<div class="text-base font-bold text-ink-gray-9">{{ __("Pièce source") }}</div>
						<div class="my-3 border-b border-surface-gray-2" />
						<iframe
							v-if="source_attachment && is_pdf(source_attachment)"
							:src="`${source_attachment}#toolbar=0&navpanes=0&scrollbar=0`"
							class="h-[480px] w-full rounded border border-surface-gray-2"
						></iframe>
						<img
							v-else-if="source_attachment"
							:src="source_attachment"
							class="block max-h-[480px] max-w-full rounded border border-surface-gray-2"
						/>
						<div v-else class="text-p-sm text-ink-gray-5">{{ __("The source document carries no attachment.") }}</div>
					</div>
				</template>
			</div>

			<!-- Totals footer -->
			<TotalsFooter v-if="doc && !loading_doc && !page_error?.length" :lines="doc.lines" :devise="doc.devise || ''" />
		</div>

		<!-- Model dialogs (Appel Modele / Enreg. Modele) -->
		<ModelDialogs
			v-if="doc && mode !== 'inspect'"
			ref="model_dialogs_ref"
			:journal="doc.journal || ''"
			:lines="doc.lines"
			@apply-lines="apply_model_lines"
		/>
	</div>
</template>
