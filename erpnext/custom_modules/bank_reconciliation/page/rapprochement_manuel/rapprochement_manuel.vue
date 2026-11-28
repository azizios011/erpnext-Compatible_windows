<!-- Rapprochement Manuel — Frappe UI island page of the Bank Reconciliation
     module (the WRITE side of the rapprochement bancaire; the read side is
     the two routed reports Bank Reconciliation Statement / Bank Clearance
     Summary under Reports → Bank).

     Filters: Compte (bank accounts), Journal (Banque journals), period
     (Mensuelle / Annuelle / Date a date, resolved server-side against the
     context Exercice), Type ecriture (Toutes / Rapprochees / Non
     rapprochees), Piece de tresorerie, Date rapprochement (exact).
     The table is the Ecriture Comptable ledger of the context — multi-select
     with Rapprocher (date prompt) / Annuler le rapprochement — and the
     footer carries Total Debit / Credit / Solde. "Solde initial" upserts the
     Solde Initial Banque row of the filtered account.

     All writes go through rapprochement_api.py: context Entreprise/Exercice
     never come from the client, the Exercice must be Ouvert, and only
     Banque-journal rows can be marked. Desk CSS variables only. -->
<script setup>
import { computed, onErrorCaptured, onMounted, reactive, ref } from "vue";
import { Button, FormControl } from "frappe-ui";

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

const API = "erpnext.custom_modules.bank_reconciliation.rapprochement_api.";
const MONTHS = [
	"Janvier", "Fevrier", "Mars", "Avril", "Mai", "Juin",
	"Juillet", "Aout", "Septembre", "Octobre", "Novembre", "Decembre",
];
const PERIODS = ["Mensuelle", "Annuelle", "Date a date"];

// ── render errors surface on the page instead of blanking the island ────────
const render_error = ref(null);
onErrorCaptured((error, instance, info) => {
	render_error.value = `${error?.message || String(error)} (${info})`;
	return false;
});

// ── filters ──────────────────────────────────────────────────────────────────
const filters = reactive({
	account: "",
	journal: "",
	period_type: "Mensuelle",
	month: MONTHS[new Date().getMonth()],
	from_date: "",
	to_date: "",
	type_ecriture: "Toutes",
	tresorerie: "",
	date_rapprochement: "",
});
const options = reactive({ accounts: [], journals: [], tresoreries: [] });
const rows = ref([]);
const totals = reactive({ total_debit: 0, total_credit: 0, solde: 0 });
const loading = ref(false);
const selected = ref(new Set());

const context_obj = () => window.axeane?.context?.get?.() || frappe.boot?.axeane_context || null;
const context_headline = computed(() => {
	const ctx = context_obj() || {};
	return [ctx.entreprise_label || ctx.entreprise, ctx.exercice_label || ctx.exercice]
		.filter(Boolean)
		.join(" · ");
});

function fmt(value) {
	return frappe.utils.format_number(flt(value), null, 3);
}
function esc(value) {
	return frappe.utils.escape_html(value == null ? "" : String(value));
}
function fmt_date(value) {
	if (!value) return "";
	const date = new Date(value);
	return Number.isNaN(date.getTime())
		? String(value)
		: date.toLocaleDateString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric" });
}

// ── read ─────────────────────────────────────────────────────────────────────
async function load() {
	loading.value = true;
	try {
		const result =
			(await frappe.xcall(API + "lignes", { filters: { ...filters } })) || {};
		rows.value = result.rows || [];
		Object.assign(totals, result.totals || {});
		Object.assign(options, result.options || {});
		if (!filters.account && options.accounts.length) filters.account = "";
		selected.value = new Set();
	} finally {
		loading.value = false;
	}
}

// ── selection ────────────────────────────────────────────────────────────────
function toggle_row(name) {
	const next = new Set(selected.value);
	if (next.has(name)) next.delete(name);
	else next.add(name);
	selected.value = next;
}
function toggle_all(event) {
	selected.value = event.target.checked ? new Set(rows.value.map((r) => r.name)) : new Set();
}
const all_selected = computed(
	() => rows.value.length > 0 && rows.value.every((r) => selected.value.has(r.name))
);
const selection_sums = computed(() => {
	let debit = 0;
	let credit = 0;
	rows.value.forEach((row) => {
		if (!selected.value.has(row.name)) return;
		debit += flt(row.debit);
		credit += flt(row.credit);
	});
	return { debit: fmt(debit), credit: fmt(credit), ecart: fmt(debit - credit) };
});

// ── writes ───────────────────────────────────────────────────────────────────
function selected_names() {
	const names = rows.value.filter((r) => selected.value.has(r.name)).map((r) => r.name);
	if (!names.length) {
		frappe.msgprint({ message: __("Aucune ligne selectionnee."), indicator: "orange" });
		return null;
	}
	return names;
}

function rapprocher() {
	const names = selected_names();
	if (!names) return;
	frappe.prompt(
		{
			fieldname: "date_rapprochement",
			fieldtype: "Date",
			label: __("Date rapprochement"),
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		(values) => {
			frappe.xcall(API + "rapprocher", {
				ecriture_names: names,
				date_rapprochement: values.date_rapprochement,
			}).then((result) => {
				frappe.show_alert({
					message: __("Rapproche: {0} ligne(s) au {1}.", [result.rapprochees, fmt_date(result.date_rapprochement)]),
					indicator: "green",
				});
				load();
			});
		},
		__("Rapprocher"),
		__("Valider")
	);
}

function de_rapprocher() {
	const names = selected_names();
	if (!names) return;
	frappe.confirm(__("Annuler le rapprochement de {0} ligne(s) ?", [names.length]), () => {
		frappe.xcall(API + "de_rapprocher", { ecriture_names: names }).then((result) => {
			frappe.show_alert({
				message: __("Rapprochement annule: {0} ligne(s).", [result.annulees]),
				indicator: "blue",
			});
			load();
		});
	});
}

function set_solde_initial() {
	if (!filters.account) {
		frappe.msgprint({ message: __("Choisissez d'abord le compte de banque."), indicator: "orange" });
		return;
	}
	frappe.prompt(
		[
			{
				fieldname: "solde_initial",
				fieldtype: "Currency",
				label: __("Solde initial"),
				reqd: 1,
				precision: 3,
			},
			{
				fieldname: "mois",
				fieldtype: "Select",
				label: __("Mois"),
				options: MONTHS.join("\n"),
				default: filters.month || MONTHS[0],
				reqd: 1,
			},
			{
				fieldname: "sens",
				fieldtype: "Select",
				label: __("Sens (releve banque)"),
				options: "Debit\nCredit",
				default: "Debit",
				reqd: 1,
				description: __("Debit = solde crediteur banque (argent disponible)."),
			},
		],
		(values) => {
			frappe.xcall(API + "set_solde_initial", {
				account: filters.account,
				solde_initial: values.solde_initial,
				mois: values.mois,
				sens: values.sens,
			}).then((result) => {
				frappe.show_alert({ message: __("Solde initial enregistre ({0}).", [result.name]), indicator: "green" });
			});
		},
		__("Solde initial banque"),
		__("Enregistrer")
	);
}

onMounted(() => {
	emit("title", [__("Rapprochement Manuel"), context_headline.value].filter(Boolean).join(" · "));
	load();
});
</script>

<template>
	<div class="rappro-page">
		<div v-if="render_error" class="rappro-error">{{ render_error }}</div>

		<!-- ── filters ─────────────────────────────────────────────────────── -->
		<div class="rappro-filters">
			<div class="rappro-filter">
				<label>{{ __("Compte") }}</label>
				<select v-model="filters.account" class="form-control">
					<option value="">{{ __("Toutes les banques") }}</option>
					<option v-for="account in options.accounts" :key="account.value" :value="account.value">
						{{ account.label }}
					</option>
				</select>
			</div>
			<div class="rappro-filter">
				<label>{{ __("Journal") }}</label>
				<select v-model="filters.journal" class="form-control">
					<option value="">{{ __("Tous") }}</option>
					<option v-for="journal in options.journals" :key="journal.value" :value="journal.value">
						{{ journal.label }}
					</option>
				</select>
			</div>
			<div class="rappro-filter">
				<label>{{ __("Periode") }}</label>
				<select v-model="filters.period_type" class="form-control">
					<option v-for="period in PERIODS" :key="period" :value="period">{{ __(period) }}</option>
				</select>
			</div>
			<div v-if="filters.period_type === 'Mensuelle'" class="rappro-filter">
				<label>{{ __("Mois") }}</label>
				<select v-model="filters.month" class="form-control">
					<option v-for="month in MONTHS" :key="month" :value="month">{{ __(month) }}</option>
				</select>
			</div>
			<template v-if="filters.period_type === 'Date a date'">
				<div class="rappro-filter">
					<label>{{ __("Du") }}</label>
					<input v-model="filters.from_date" type="date" class="form-control" />
				</div>
				<div class="rappro-filter">
					<label>{{ __("Au") }}</label>
					<input v-model="filters.to_date" type="date" class="form-control" />
				</div>
			</template>
			<div class="rappro-filter">
				<label>{{ __("Type ecriture") }}</label>
				<select v-model="filters.type_ecriture" class="form-control">
					<option value="Toutes">{{ __("Toutes") }}</option>
					<option value="Rapprochees">{{ __("Rapprochees") }}</option>
					<option value="Non rapprochees">{{ __("Non rapprochees") }}</option>
				</select>
			</div>
			<div class="rappro-filter">
				<label>{{ __("Piece de tresorerie") }}</label>
				<select v-model="filters.tresorerie" class="form-control">
					<option value="">{{ __("Toutes") }}</option>
					<option v-for="t in options.tresoreries" :key="t.value" :value="t.value">{{ t.label }}</option>
				</select>
			</div>
			<div class="rappro-filter">
				<label>{{ __("Date rapprochement") }}</label>
				<input v-model="filters.date_rapprochement" type="date" class="form-control" />
			</div>
			<div class="rappro-filter rappro-filter-actions">
				<Button variant="solid" :loading="loading" @click="load">{{ __("Appliquer") }}</Button>
				<Button variant="subtle" @click="set_solde_initial">{{ __("Solde initial") }}</Button>
			</div>
		</div>

		<!-- ── action bar ──────────────────────────────────────────────────── -->
		<div class="rappro-actions">
			<Button variant="solid" :disabled="!selected.size" @click="rapprocher">
				{{ __("Rapprocher") }}<span v-if="selected.size">&nbsp;({{ selected.size }})</span>
			</Button>
			<Button variant="subtle" :disabled="!selected.size" @click="de_rapprocher">
				{{ __("Annuler le rapprochement") }}
			</Button>
			<span v-if="selected.size" class="rappro-selection text-muted">
				{{ __("Debit {0} · Credit {1} · Ecart {2}", [selection_sums.debit, selection_sums.credit, selection_sums.ecart]) }}
			</span>
		</div>

		<!-- ── the ledger table ────────────────────────────────────────────── -->
		<div class="rappro-table-wrap">
			<table class="rappro-table">
				<thead>
					<tr>
						<th class="rappro-check">
							<input type="checkbox" :checked="all_selected" @change="toggle_all" :aria-label="__('Tout selectionner')" />
						</th>
						<th>{{ __("Mvt") }}</th>
						<th>{{ __("Jrn") }}</th>
						<th>{{ __("Date rappro.") }}</th>
						<th>{{ __("Compte") }}</th>
						<th>{{ __("Date") }}</th>
						<th>{{ __("Tresorerie") }}</th>
						<th>{{ __("Libelle") }}</th>
						<th class="rappro-num">{{ __("Debit") }}</th>
						<th class="rappro-num">{{ __("Credit") }}</th>
						<th>{{ __("N Doc") }}</th>
					</tr>
				</thead>
				<tbody>
					<tr v-if="loading">
						<td colspan="11" class="text-muted">{{ __("Chargement…") }}</td>
					</tr>
					<tr v-else-if="!rows.length">
						<td colspan="11" class="text-muted">{{ __("Aucune ecriture de banque pour ces filtres.") }}</td>
					</tr>
					<tr
						v-else
						v-for="row in rows"
						:key="row.name"
						:class="{ 'rappro-cleared': row.rapprochement_manuel }"
					>
						<td class="rappro-check">
							<input
								type="checkbox"
								:checked="selected.has(row.name)"
								@change="toggle_row(row.name)"
								:aria-label="__('Ligne {0}', [row.mvt || row.name])"
							/>
						</td>
						<td>{{ esc(row.mvt) }}</td>
						<td>{{ esc(row.journal) }}</td>
						<td>
							<span v-if="row.date_rapprochement" class="indicator-pill no-indicator-icon indicator-green">
								{{ fmt_date(row.date_rapprochement) }}
							</span>
						</td>
						<td>{{ esc(row.account) }}</td>
						<td>{{ fmt_date(row.posting_date) }}</td>
						<td>{{ esc(row.tresorerie) }}</td>
						<td class="rappro-libelle">{{ esc(row.libelle) }}</td>
						<td class="rappro-num">{{ row.debit ? fmt(row.debit) : "" }}</td>
						<td class="rappro-num">{{ row.credit ? fmt(row.credit) : "" }}</td>
						<td>{{ esc(row.ref_doc) }}</td>
					</tr>
				</tbody>
				<tfoot>
					<tr>
						<td colspan="8">{{ __("Total ({0} ligne(s))", [rows.length]) }}</td>
						<td class="rappro-num">{{ fmt(totals.total_debit) }}</td>
						<td class="rappro-num">{{ fmt(totals.total_credit) }}</td>
						<td class="rappro-num">{{ __("Solde") }} {{ fmt(totals.solde) }}</td>
					</tr>
				</tfoot>
			</table>
		</div>
	</div>
</template>

<style scoped>
.rappro-page { display: flex; flex-direction: column; gap: 10px; color: var(--text-color); }
.rappro-error { background: var(--danger-bg, var(--bg-color)); border: 1px solid var(--border-color); border-radius: 8px; padding: 8px 10px; }
.rappro-filters { display: flex; flex-wrap: wrap; gap: 8px; align-items: flex-end; background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 8px; padding: 10px; }
.rappro-filter { display: flex; flex-direction: column; gap: 3px; min-width: 140px; }
.rappro-filter label { font-size: 11px; color: var(--text-muted); }
.rappro-filter-actions { flex-direction: row; align-items: center; gap: 6px; min-width: auto; }
.rappro-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.rappro-selection { font-size: 11px; }
.rappro-table-wrap { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: 8px; overflow: auto; max-height: calc(100vh - 320px); }
.rappro-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.rappro-table th, .rappro-table td { border-bottom: 1px solid var(--border-color); padding: 5px 8px; text-align: left; white-space: nowrap; }
.rappro-table th { position: sticky; top: 0; background: var(--control-bg); font-weight: 600; }
.rappro-table tfoot td { position: sticky; bottom: 0; background: var(--control-bg); font-weight: 600; }
.rappro-num { text-align: right !important; font-variant-numeric: tabular-nums; }
.rappro-libelle { white-space: normal; min-width: 220px; }
.rappro-check { width: 28px; }
.rappro-cleared { color: var(--text-muted); }
</style>
