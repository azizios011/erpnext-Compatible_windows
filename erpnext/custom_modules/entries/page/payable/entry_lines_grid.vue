<!-- Lines grid shared by the payable and receivable islands
     (identical copies: the island toolchain resolves bare imports only for
     files inside a discovered page directory — commit bd3ffc3cab).

     Columns: No / Compte / Libelle / Trésorerie / Debit / Credit. The rows
     array is owned by the parent form and mutated in place; the parent
     recomputes the totals. The Trésorerie column renders only when the
     Entreprise allows the cash-flow model. The third-party rule (401 Credit
     / 411 Debit, read from the server via get_entry_defaults) highlights the
     expected side and warns on the opposite one without ever blocking. -->
<script setup>
import { nextTick, onMounted, ref, watch } from "vue";
import { Badge, Button } from "frappe-ui";
import AccountAutocomplete from "./account_autocomplete.vue";

const frappe = window.frappe;
const __ = window.__;
const flt = (v) => {
	const n = parseFloat(v);
	return Number.isFinite(n) ? n : 0;
};

const props = defineProps({
	lines: { type: Array, default: () => [] },
	partyRule: { type: Object, default: () => ({ prefix: "", side: "", label: "" }) },
	showTresorerie: { type: Boolean, default: false },
	readOnly: { type: Boolean, default: false },
});
const emit = defineEmits(["add-row", "remove-row"]);

const EXPECTED_CLASSES = "border-surface-amber-3 bg-surface-amber-1";

// ── Compte picker: server search over the context Entreprise's accounts ──────
// frappe-ui 1.0.2 Combobox, input mode: the input IS the selected-value
// display, so `update:query` fires with the committed option's LABEL (on
// select) and again with that label when the dropdown closes (display sync),
// and `focus` re-emits the raw FocusEvent. None of those is a search term —
// only real typing searches; the full list is loaded on mount and reloaded
// on every open (see on_account_open).

const account_options = ref([]);
const known_accounts = ref({});
let account_timer = null;

function load_account_options(txt = "") {
	if (account_timer) clearTimeout(account_timer);
	account_timer = setTimeout(() => {
		frappe.xcall("erpnext.custom_modules.organization.tiers_accounts.compte_search", {
			doctype: "Chart of Account",
			txt: txt || "",
			searchfield: "name",
			start: 0,
			page_len: 500,
		}).then((rows) => {
			const options = (rows || []).map((r) => ({
				label: `${r.account_number} · ${r.account_name}`,
				value: r.name,
			}));
			// an unfiltered load (txt "") that comes back empty (server
			// hiccup) must not wipe the list already on screen
			if (txt === "" && !options.length && account_options.value.length) return;
			account_options.value = options;
			(rows || []).forEach((r) => remember_account(r.name, r.account_number, r.account_name));
		});
	}, 250);
}

function remember_account(name, account_number, account_name) {
	if (!name) return;
	known_accounts.value = {
		...known_accounts.value,
		[name]: { account_number: account_number || "", account_name: account_name || "" },
	};
}

function options_for(row) {
	const list = [...account_options.value];
	if (row.account && !list.some((o) => o.value === row.account)) {
		const meta = known_accounts.value[row.account];
		list.unshift({
			label: meta ? `${meta.account_number} · ${meta.account_name}` : row.account,
			value: row.account,
		});
	}
	return list;
}

/** The query handler. The component echoes the display into the query:
 * ignore anything that is not a string, ignore the empty display reset, and
 * ignore a text equal to the selected option's label or to any option
 * already listed — only then debounce-search. Never replaces
 * account_options with an empty result on txt "". */
function on_account_query(row, txt) {
	if (typeof txt !== "string") return;
	if (txt === "") return;
	const selected = options_for(row).find((o) => o.value === row.account);
	if (selected && txt === selected.label) return;
	if (account_options.value.some((o) => o.label === txt)) return;
	load_account_options(txt);
}

/** The dropdown opened: nothing is typed at that point (input mode resets
 * the query to the display value on close), so reload the full list. */
function on_account_open(is_open) {
	if (is_open) load_account_options("");
}

/** The one explicit model update: assign, then the existing account_number /
 * expected-side / focus follow-ups. (v-model plus a second update handler
 * raced with the component's own label echo, which emptied the options the
 * click depended on.) */
function set_account(row, index, value) {
	if (!value) {
		row.account = "";
		row.account_number = "";
		row.account_name = "";
		return;
	}
	if (typeof value === "object") {
		row.account = value.value;
		row.account_number = value.account_number || "";
		row.account_name = value.account_name || "";
		remember_account(value.value, value.account_number, value.account_name);
	} else {
		row.account = value;
		if (known_accounts.value[value]) {
			row.account_number = known_accounts.value[value].account_number;
		} else {
			frappe.db.get_value("Chart of Account", value, ["account_number", "account_name"]).then((r) => {
				const values = r?.message || {};
				remember_account(value, values.account_number, values.account_name);
				row.account_number = values.account_number || "";
			});
		}
	}
	const expected = expected_side(row);
	if (expected) {
		nextTick(() => focus_side(index, expected));
	}
}

// ── third-party side reminder (never blocks; avoirs reverse the side) ────────
function expected_side(row) {
	const rule = props.partyRule || {};
	const number = row.account_number || "";
	if (!rule.prefix) return "";
	return number.startsWith(rule.prefix) && number.length > rule.prefix.length ? rule.side : "";
}

function badge_text(row) {
	const expected = expected_side(row);
	if (!expected) return "";
	const word = expected === "Credit" ? "Crédit" : "Débit";
	return `${word} · ${props.partyRule.label}`;
}

function row_note(row, side) {
	if (props.readOnly) return ""; // inspect: badges stay, warnings do not
	const expected = expected_side(row);
	if (!expected || expected === side) return "";
	const amount_on_side = side === "Debit" ? flt(row.debit) : flt(row.credit);
	if (amount_on_side <= 0) return "";
	const word = expected === "Credit" ? "crédit" : "débit";
	return __("Compte {0}: {1} attendu (avoir ?)", [props.partyRule.label, word]);
}

// ── Trésorerie picker: visible operations of the context's plan type ─────────
const tresorerie_options = ref([]);

onMounted(() => {
	load_account_options("");
	if (!props.showTresorerie) return;
	const type_plan = frappe.boot?.axeane_context?.type_plan || "Societe";
	frappe.xcall("frappe.client.get_list", {
		doctype: "Operation Tresorerie",
		fields: ["name", "libelle"],
		filters: { visible: 1, type_plan },
		limit_page_length: 0,
	}).then((rows) => {
		tresorerie_options.value = (rows || []).map((r) => ({
			label: r.libelle || r.name,
			value: r.name,
		}));
	});
});

// rows arriving from the server (edit mode, model loads) carry the account
// name only: fetch code + libelle so the reminders and display work
watch(
	() => props.lines,
	(lines) => {
		(lines || []).forEach((row) => {
			if (!row.account || row.account_number !== undefined) return;
			row.account_number = "";
			frappe.db.get_value("Chart of Account", row.account, ["account_number", "account_name"]).then((r) => {
				const values = r?.message || {};
				remember_account(row.account, values.account_number, values.account_name);
				row.account_number = values.account_number || "";
				row.account_name = values.account_name || "";
			});
		});
	},
	{ immediate: true, deep: true }
);

// typing on one side clears the other (the server refuses both)
function on_debit_input(row) {
	row.credit = "";
}
function on_credit_input(row) {
	row.debit = "";
}

const grid_root = ref(null);

function focus_side(index, side) {
	nextTick(() => {
		const input = grid_root.value?.querySelector(
			`tr[data-row-index="${index}"] input[data-side="${side}"]`
		);
		if (input) input.focus();
	});
}
</script>

<template>
	<div ref="grid_root">
		<div class="overflow-hidden rounded-lg border border-surface-gray-2 bg-surface-white">
			<div class="overflow-x-auto">
				<table class="w-full border-collapse text-left">
					<thead>
						<tr class="border-b border-surface-gray-2 bg-surface-gray-1">
							<th class="w-12 bg-surface-gray-1 px-2 py-2 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6 text-center">
								{{ __("No") }}
							</th>
							<th class="bg-surface-gray-1 px-3 py-2 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6">
								{{ __("Compte") }}
							</th>
							<th class="bg-surface-gray-1 px-3 py-2 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6">
								{{ __("Libelle") }}
							</th>
							<th v-if="showTresorerie" class="bg-surface-gray-1 px-3 py-2 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6">
								{{ __("Trésorerie") }}
							</th>
							<th class="bg-surface-gray-1 px-3 py-2 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6 text-end">
								{{ __("Debit") }}
							</th>
							<th class="bg-surface-gray-1 px-3 py-2 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6 text-end">
								{{ __("Credit") }}
							</th>
							<th v-if="!readOnly" class="w-12 bg-surface-gray-1"></th>
						</tr>
					</thead>
					<tbody class="divide-y divide-surface-gray-2">
						<tr v-for="(row, index) in lines" :key="index" :data-row-index="index" class="align-top">
							<td class="px-2 py-2.5 text-center text-p-sm text-ink-gray-6">
								{{ index + 1 }}
							</td>
							<td class="min-w-[240px] px-2 py-2">
								<AccountAutocomplete
									:model-value="row.account"
									:placeholder="__('code · libellé')"
									:disabled="readOnly"
									@select="(opt) => set_account(row, index, opt)"
									@update:model-value="(val) => { if (!val) set_account(row, index, null); }"
								/>
							</td>
							<td class="min-w-[180px] px-2 py-2">
								<input
									v-model="row.libelle"
									type="text"
									class="h-7 w-full rounded border border-surface-gray-3 bg-surface-white px-2 text-p-sm text-ink-gray-9 placeholder:text-ink-gray-4 focus:border-ink-gray-5 focus:outline-none focus:ring-1 focus:ring-ink-gray-5"
								/>
							</td>
							<td v-if="showTresorerie" class="min-w-[160px] px-2 py-2">
								<AccountAutocomplete
									v-model="row.tresorerie"
									:options="tresorerie_options"
									:placeholder="__('Trésorerie')"
									:disabled="readOnly"
								/>
							</td>
							<td class="w-40 px-2 py-2 text-end">
								<div class="flex flex-col items-end gap-1">
									<input
										v-model="row.debit"
										type="number"
										step="0.001"
										min="0"
										data-side="Debit"
										:disabled="readOnly"
										class="h-7 w-full rounded border bg-surface-white disabled:bg-surface-gray-1 disabled:text-ink-gray-5 px-2 text-end text-p-sm tabular-nums text-ink-gray-9 placeholder:text-ink-gray-4 focus:outline-none focus:ring-1 focus:ring-ink-gray-5"
										:class="expected_side(row) === 'Debit' ? EXPECTED_CLASSES : 'border-surface-gray-3'"
										@input="on_debit_input(row)"
									/>
									<Badge v-if="expected_side(row) === 'Debit'" variant="subtle" theme="orange" size="sm" :label="badge_text(row)" />
									<div v-if="row_note(row, 'Debit')" class="text-start text-xs text-ink-amber-7">
										{{ row_note(row, "Debit") }}
									</div>
								</div>
							</td>
							<td class="w-40 px-2 py-2 text-end">
								<div class="flex flex-col items-end gap-1">
									<input
										v-model="row.credit"
										type="number"
										step="0.001"
										min="0"
										data-side="Credit"
										:disabled="readOnly"
										class="h-7 w-full rounded border bg-surface-white disabled:bg-surface-gray-1 disabled:text-ink-gray-5 px-2 text-end text-p-sm tabular-nums text-ink-gray-9 placeholder:text-ink-gray-4 focus:outline-none focus:ring-1 focus:ring-ink-gray-5"
										:class="expected_side(row) === 'Credit' ? EXPECTED_CLASSES : 'border-surface-gray-3'"
										@input="on_credit_input(row)"
									/>
									<Badge v-if="expected_side(row) === 'Credit'" variant="subtle" theme="orange" size="sm" :label="badge_text(row)" />
									<div v-if="row_note(row, 'Credit')" class="text-start text-xs text-ink-amber-7">
										{{ row_note(row, "Credit") }}
									</div>
								</div>
							</td>
							<td v-if="!readOnly" class="px-2 py-2.5 text-center">
								<Button variant="ghost" :title="__('Supprimer la ligne')" @click="emit('remove-row', index)">
									<svg class="size-4 text-ink-red-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
										<line x1="5" y1="12" x2="19" y2="12" />
									</svg>
								</Button>
							</td>
						</tr>
					</tbody>
				</table>
			</div>
			<div class="border-t border-surface-gray-2 px-3 py-2">
				<Button variant="subtle" :label="__('Ajouter une ligne')" @click="emit('add-row')" />
			</div>
		</div>
	</div>
</template>
