<!-- Plan comptable — create / edit account panel.

     Rendered by plan_comptable.vue for the routes ["new"] and [<account name>]
     (props.mode). The entreprise always comes from the page state; ?parent=
     prefills "Sous-compte de". Saving uses generic frappe.client.insert / save
     / delete; the server (Chart of Account controller) stays the source of
     truth — client-side validation only mirrors its rules with the same
     French messages, and server errors land in the panel's error box.

     A standard (locked) account renders every field read-only behind a blue
     banner; an Accounts Manager can unlock it (is_standard 1 -> 0 and nothing
     else — exactly what the server allows), and a Regroupement always keeps
     "+ Ajouter un sous-compte", locked or not. -->
<script setup>
import { computed, ref, watch } from "vue";
import { Badge, Button, Dialog, FormControl } from "frappe-ui";
import { Link } from "@framework/ui";

const frappe = window.frappe;
const __ = window.__;

const props = defineProps({
	mode: { type: String, default: "new" }, // "new" | "record"
	recordName: { type: String, default: "" },
	entreprise: { type: String, default: "" },
	parentName: { type: String, default: "" },
});
const emit = defineEmits(["title", "saved", "deleted"]);

const DOCTYPE = "Chart of Account";
const ROOT_CLASS_NAMES = {
	1: "Capitaux",
	2: "Immobilisations",
	3: "Stock et Encours",
	4: "Tiers",
	5: "Financiers",
	6: "Charges",
	7: "Produits",
};

const NATURE_OPTIONS = [
	{ label: __("Comptable"), value: "0" },
	{ label: __("Regroupement"), value: "1" },
];

const SENS_OPTIONS = [
	{ label: __("C — Crédit"), value: "C" },
	{ label: __("D — Débit"), value: "D" },
	{ label: __("DC — Débit ou crédit"), value: "DC" },
];

// ── state ────────────────────────────────────────────────────────────────────
// nature stays a string ("0"/"1") because it feeds a select; saved as a number
const form = ref({ parent_chart_of_account: "", account_number: "", account_name: "", is_group: "0", sens: "" });
const doc = ref(null); // the loaded record (edit mode)
const parent_info = ref(null); // the parent chosen in the parent field
const entreprise_info = ref(null);
const sub_count = ref(0);
const loading = ref(false);
const saving = ref(false);
const deleting = ref(false);
const unlocking = ref(false);
const form_error = ref(null);
const delete_dialog = ref(false);
const unlock_dialog = ref(false);

const is_manager = computed(() => (frappe.user_roles || []).includes("Accounts Manager"));
const is_group_num = computed(() => Number(form.value.is_group));
const fields_disabled = computed(() => props.mode === "record" && Boolean(doc.value?.is_standard));
const number_frozen = computed(() => props.mode === "record"); // identity is frozen server-side
const has_children = computed(() => Boolean(doc.value?.is_group && sub_count.value > 0));

const longueur = computed(() => Number(entreprise_info.value?.longueur_compte_comptable) || 0);

// ── titles (the parent or the typed number gives the class) ──────────────────
const classe = computed(() => {
	const source = form.value.account_number || parent_info.value?.account_number || "";
	return source.charAt(0) || "";
});

const class_name = computed(() => ROOT_CLASS_NAMES[classe.value] || "");

const panel_title = computed(() => {
	if (props.mode === "new") {
		return classe.value && class_name.value
			? __("Nouveau compte comptable — Classe {0} — {1}", [classe.value, __(class_name.value)])
			: __("Nouveau compte comptable");
	}
	if (doc.value) {
		return __("Compte {0} — {1}", [doc.value.account_number, doc.value.account_name]);
	}
	return props.recordName || __("Plan comptable");
});

watch(panel_title, (title) => emit("title", title), { immediate: true });

// ── hints under the number field ─────────────────────────────────────────────
const number_hints = computed(() => {
	if (props.mode !== "new") return [];
	const hints = [];
	if (form.value.parent_chart_of_account && parent_info.value?.account_number) {
		hints.push(__("doit commencer par {0}", [parent_info.value.account_number]));
	}
	if (longueur.value && is_group_num.value === 0) {
		hints.push(__("{0} chiffres", [longueur.value]));
	}
	return hints;
});

// ── loading ──────────────────────────────────────────────────────────────────
async function load_entreprise_info() {
	if (!props.entreprise) return;
	entreprise_info.value = await frappe.xcall("frappe.client.get_value", {
		doctype: "Entreprise",
		filters: { name: props.entreprise },
		fieldname: ["longueur_compte_comptable", "raison_sociale"],
	});
}

async function load_record(name) {
	doc.value = await frappe.xcall("frappe.client.get", { doctype: DOCTYPE, name });
	form.value = {
		parent_chart_of_account: doc.value.parent_chart_of_account || "",
		account_number: doc.value.account_number || "",
		account_name: doc.value.account_name || "",
		is_group: String(doc.value.is_group ?? 0),
		sens: doc.value.sens || "",
	};
	load_entreprise_info();
	sub_count.value = await frappe.xcall("frappe.client.get_count", {
		doctype: DOCTYPE,
		filters: { parent_chart_of_account: name },
	});
}

async function init() {
	form_error.value = null;
	delete_dialog.value = false;
	unlock_dialog.value = false;
	if (props.mode === "new") {
		doc.value = null;
		sub_count.value = 0;
		parent_info.value = null;
		form.value = { parent_chart_of_account: props.parentName || "", account_number: "", account_name: "", is_group: "0", sens: "" };
		load_entreprise_info();
	} else if (props.mode === "record" && props.recordName) {
		loading.value = true;
		try {
			await load_record(props.recordName);
		} catch (error) {
			doc.value = null;
			form_error.value = [error?.message || String(error)];
		} finally {
			loading.value = false;
		}
	}
}

// the parent field drives the hints, the sens prefill and the client-side
// prefix check — keep parent_info in sync with it (also covers ?parent=)
watch(
	() => form.value.parent_chart_of_account,
	async (name) => {
		if (!name) {
			parent_info.value = null;
			return;
		}
		if (parent_info.value?.name === name) return;
		try {
			const parent = await frappe.xcall("frappe.client.get", { doctype: DOCTYPE, name });
			if (form.value.parent_chart_of_account !== name) return; // changed again meanwhile
			parent_info.value = parent;
			form.value.sens = parent.sens || form.value.sens;
		} catch {
			parent_info.value = null;
		}
	}
);

watch(
	[() => props.mode, () => props.recordName, () => props.entreprise, () => props.parentName],
	() => init(),
	{ immediate: true }
);

// ── input handling ───────────────────────────────────────────────────────────
function on_number_input() {
	// digits only, enforced live (the server refuses everything else anyway)
	form.value.account_number = (form.value.account_number || "").replace(/\D+/g, "");
}

// ── validation (mirrors the server rules; the server stays the source of truth)
function validate_form() {
	const errors = [];
	const number = (form.value.account_number || "").trim();
	if (!number) {
		errors.push(__("Le code du compte doit être composé de chiffres uniquement (reçu: vide)."));
	}
	if (!form.value.account_name?.trim()) {
		errors.push(__("Le libellé est obligatoire."));
	}
	if (!["C", "D", "DC"].includes(form.value.sens || "")) {
		errors.push(__("Le sens est obligatoire: C (crédit), D (débit) ou DC (débit ou crédit)."));
	}
	if (number && !/^\d+$/.test(number)) {
		errors.push(__("Le code du compte doit être composé de chiffres uniquement (reçu: {0}).", [form.value.account_number]));
	}
	const parent_number = parent_info.value?.account_number;
	if (number && form.value.parent_chart_of_account && parent_info.value?.name === form.value.parent_chart_of_account && parent_number) {
		if (number.length <= parent_number.length || !number.startsWith(parent_number)) {
			errors.push(__("Le code {0} doit commencer par le code du parent {1} et être plus long.", [number, parent_number]));
		}
	}
	if (number && longueur.value && is_group_num.value === 0 && number.length !== longueur.value) {
		errors.push(__("Le code {0} doit comporter {1} chiffres (longueur des comptes définie sur l'entreprise).", [number, longueur.value]));
	}
	return errors;
}

// ── save: new ────────────────────────────────────────────────────────────────
async function save_new() {
	const errors = validate_form();
	if (errors.length) {
		form_error.value = errors;
		return null;
	}
	saving.value = true;
	try {
		return await frappe.xcall("frappe.client.insert", {
			doc: {
				doctype: DOCTYPE,
				entreprise: props.entreprise,
				account_number: form.value.account_number.trim(),
				account_name: form.value.account_name.trim(),
				is_group: is_group_num.value,
				sens: form.value.sens,
				parent_chart_of_account: form.value.parent_chart_of_account || null,
			},
		});
	} catch (error) {
		form_error.value = [error?.message || String(error)];
		return null;
	} finally {
		saving.value = false;
	}
}

async function save_and_new() {
	const inserted = await save_new();
	if (!inserted) return;
	frappe.show_alert({ message: __("Compte {0} créé.", [inserted.account_number]), indicator: "green" });
	// reset keeping the parent and the entreprise; sens comes back from the parent
	form.value = {
		parent_chart_of_account: form.value.parent_chart_of_account,
		account_number: "",
		account_name: "",
		is_group: "0",
		sens: parent_info.value?.sens || "",
	};
	form_error.value = null;
}

async function save_new_then_leave() {
	const inserted = await save_new();
	if (!inserted) return;
	frappe.show_alert({ message: __("Compte {0} créé.", [inserted.account_number]), indicator: "green" });
	emit("saved", { classe: (inserted.account_number || "").charAt(0) });
}

// ── save: edit ───────────────────────────────────────────────────────────────
async function save_edit() {
	if (!doc.value) return;
	const errors = [];
	if (!form.value.account_name?.trim()) {
		errors.push(__("Le libellé est obligatoire."));
	}
	if (!["C", "D", "DC"].includes(form.value.sens || "")) {
		errors.push(__("Le sens est obligatoire: C (crédit), D (débit) ou DC (débit ou crédit)."));
	}
	if (is_group_num.value === 0 && doc.value.is_group && has_children.value) {
		errors.push(__("Ce compte possède {0} sous-compte(s): un regroupement ne peut pas devenir un compte comptable.", [sub_count.value]));
	}
	if (errors.length) {
		form_error.value = errors;
		return;
	}
	saving.value = true;
	try {
		await frappe.xcall("frappe.client.save", {
			doc: {
				doctype: DOCTYPE,
				name: doc.value.name,
				account_number: doc.value.account_number,
				account_name: form.value.account_name.trim(),
				is_group: is_group_num.value,
				sens: form.value.sens,
				entreprise: doc.value.entreprise,
				parent_chart_of_account: form.value.parent_chart_of_account || null,
			},
		});
		form_error.value = null;
		frappe.show_alert({ message: __("Enregistré."), indicator: "green" });
		await load_record(doc.value.name);
	} catch (error) {
		form_error.value = [error?.message || String(error)];
	} finally {
		saving.value = false;
	}
}

// ── unlock (Accounts Manager only: is_standard 1 -> 0, nothing else) ─────────
async function do_unlock() {
	unlock_dialog.value = false;
	if (!doc.value) return;
	unlocking.value = true;
	try {
		await frappe.xcall("frappe.client.save", {
			doc: {
				doctype: DOCTYPE,
				name: doc.value.name,
				account_number: doc.value.account_number,
				account_name: doc.value.account_name,
				is_group: doc.value.is_group,
				sens: doc.value.sens,
				parent_chart_of_account: doc.value.parent_chart_of_account || null,
				entreprise: doc.value.entreprise,
				is_standard: 0,
			},
		});
		form_error.value = null;
		frappe.show_alert({ message: __("Compte déverrouillé."), indicator: "green" });
		await load_record(doc.value.name);
	} catch (error) {
		form_error.value = [error?.message || String(error)];
	} finally {
		unlocking.value = false;
	}
}

// ── delete ───────────────────────────────────────────────────────────────────
async function do_delete() {
	delete_dialog.value = false;
	if (!doc.value) return;
	deleting.value = true;
	try {
		const children = await frappe.xcall("frappe.client.get_count", {
			doctype: DOCTYPE,
			filters: { parent_chart_of_account: doc.value.name },
		});
		if (children > 0) {
			form_error.value = [__("Suppression impossible: ce compte possède {0} sous-compte(s).", [children])];
			return;
		}
		await frappe.xcall("frappe.client.delete", { doctype: DOCTYPE, name: doc.value.name });
		frappe.show_alert({ message: __("Compte supprimé."), indicator: "green" });
		emit("deleted", { classe: doc.value.classe });
	} catch (error) {
		form_error.value = [error?.message || String(error)];
	} finally {
		deleting.value = false;
	}
}

// ── navigation ───────────────────────────────────────────────────────────────
function go_back() {
	// the trailing {} clears the query string; the list keeps its own
	// entreprise and class tab state
	frappe.set_route("plan-comptable", {});
}

function add_sub_account() {
	const entreprise = doc.value?.entreprise || props.entreprise;
	const parent = doc.value?.name || form.value.parent_chart_of_account;
	frappe.set_route("plan-comptable", "new", { entreprise, parent });
}

function open_parent() {
	if (doc.value?.parent_chart_of_account) {
		frappe.set_route("plan-comptable", doc.value.parent_chart_of_account);
	}
}

// ── display helpers (same formatting as the Entreprise page) ─────────────────
function format_date_dmy(val) {
	if (!val) return "—";
	if (typeof val === "string" && /^\d{4}-\d{2}-\d{2}/.test(val)) {
		const [y, m, d] = val.slice(0, 10).split("-");
		return `${d}/${m}/${y}`;
	}
	return String(val);
}

function format_datetime_dmy(val) {
	if (!val) return "—";
	if (typeof val === "string" && /^\d{4}-\d{2}-\d{2}/.test(val)) {
		const time = val.slice(11, 16);
		return time ? `${val.slice(0, 10).split("-").reverse().join("/")} ${time}` : format_date_dmy(val);
	}
	return String(val);
}
</script>

<template>
	<div class="min-h-full">
		<!-- Sticky top bar -->
		<div class="sticky top-0 z-20 border-b border-surface-gray-2 bg-surface-white">
			<div class="mx-auto flex w-full max-w-[1600px] items-center justify-between gap-4 px-6 lg:px-10 py-3.5">
				<div class="flex min-w-0 items-center gap-3">
					<Button variant="ghost" :label="__('← Plan comptable')" @click="go_back" />
					<div class="h-4 w-px bg-surface-gray-2" />
					<h1 class="truncate text-p-base font-semibold text-ink-gray-9">
						{{ panel_title }}
					</h1>
					<Badge
						v-if="mode === 'new'"
						variant="subtle"
						size="sm"
						theme="blue"
						:label="__('Personnalisé')"
					/>
					<Badge
						v-else-if="doc"
						variant="subtle"
						size="sm"
						:theme="doc.is_standard ? 'gray' : 'blue'"
						:label="doc.is_standard ? __('Standard') : __('Personnalisé')"
					/>
				</div>

				<div class="flex items-center gap-2">
					<!-- New mode -->
					<template v-if="mode === 'new'">
						<Button variant="outline" :label="__('Enregistrer & nouveau')" :loading="saving" @click="save_and_new" />
						<Button variant="solid" :label="__('Enregistrer')" :loading="saving" @click="save_new_then_leave" />
					</template>

					<!-- Edit mode -->
					<template v-else-if="doc">
						<Button
							v-if="doc.is_group"
							variant="subtle"
							:label="__('+ Ajouter un sous-compte')"
							@click="add_sub_account"
						/>
						<template v-if="!doc.is_standard">
							<Button variant="outline" theme="red" :label="__('Supprimer')" :loading="deleting" @click="delete_dialog = true" />
							<Button variant="solid" :label="__('Enregistrer')" :loading="saving" @click="save_edit" />
						</template>
						<Button
							v-else-if="is_manager"
							variant="subtle"
							:label="__('Déverrouiller')"
							:loading="unlocking"
							@click="unlock_dialog = true"
						/>
					</template>
				</div>
			</div>
		</div>

		<!-- Content -->
		<div class="mx-auto w-full max-w-[1600px] space-y-6 px-6 lg:px-10 py-6 pb-16">
			<!-- Error box: client-side validation + server errors -->
			<div v-if="form_error?.length" class="rounded-lg border border-surface-red-3 bg-surface-red-1 p-4">
				<div class="flex items-center gap-2 font-semibold text-ink-red-8">
					<svg class="size-5 shrink-0 text-ink-red-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
						<line x1="12" y1="9" x2="12" y2="13" />
						<line x1="12" y1="17" x2="12.01" y2="17" />
					</svg>
					<span>{{ __("Vérifiez les points suivants") }}</span>
				</div>
				<ul class="mt-2 list-disc space-y-1 pl-5 text-p-sm text-ink-red-7">
					<li v-for="(message, index) in form_error" :key="index">{{ message }}</li>
				</ul>
			</div>

			<!-- Locked banner -->
			<div
				v-if="mode === 'record' && doc?.is_standard"
				class="flex items-center gap-2.5 rounded-lg border border-surface-blue-3 bg-surface-blue-1 px-4 py-3 text-p-sm font-semibold text-ink-blue-8"
			>
				<svg class="size-5 shrink-0 text-ink-blue-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
					<rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
					<path d="M7 11V7a5 5 0 0 1 10 0v4" />
				</svg>
				<span>{{ __("Compte standard — non modifiable") }}</span>
			</div>

			<!-- No entreprise in the page state -->
			<div v-if="!entreprise" class="rounded-lg border border-surface-gray-2 bg-surface-white p-6 shadow-xs">
				<div class="flex flex-col items-center justify-center px-6 py-10 text-center">
					<h3 class="text-p-base font-semibold text-ink-gray-9">{{ __("Aucune entreprise sélectionnée") }}</h3>
					<p class="mt-1 text-p-sm text-ink-gray-5">
						{{ __("Retournez à la liste et choisissez une entreprise.") }}
					</p>
				</div>
			</div>

			<!-- Loading skeleton -->
			<div v-else-if="loading" class="rounded-lg border border-surface-gray-2 bg-surface-white p-6 shadow-xs">
				<div class="h-6 w-48 animate-pulse rounded bg-surface-gray-2" />
				<div class="my-4 h-px bg-surface-gray-2" />
				<div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
					<div v-for="i in 6" :key="i" class="h-12 animate-pulse rounded bg-surface-gray-2" />
				</div>
			</div>

			<!-- Fields card -->
			<div v-else-if="mode === 'new' || doc" class="rounded-lg border border-surface-gray-2 bg-surface-white p-6 shadow-xs">
				<div class="text-base font-bold text-ink-gray-9">
					{{ mode === "new" ? __("Nouveau compte") : __("Compte") }}
				</div>
				<div class="my-4 border-b border-surface-gray-2" />

				<div class="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2">
					<!-- Sous-compte de -->
					<div class="space-y-1.5">
						<div class="text-xs font-medium text-ink-gray-5">
							{{ __("Sous-compte de") }}
						</div>
						<Link
							:key="entreprise"
							v-model="form.parent_chart_of_account"
							doctype="Chart of Account"
							:filters="{ entreprise: entreprise, is_group: 1 }"
							:disabled="fields_disabled"
							:placeholder="__('Racine de classe (aucun)')"
						/>
					</div>

					<!-- Numéro de compte -->
					<div class="space-y-1.5">
						<div class="text-xs font-medium text-ink-gray-5">
							{{ __("Numéro de compte") }}
							<span class="text-ink-red-5">*</span>
						</div>
						<input
							v-model="form.account_number"
							type="text"
							inputmode="numeric"
							:disabled="fields_disabled || number_frozen"
							class="h-8 w-full rounded-md border border-surface-gray-3 bg-surface-white px-3 font-mono text-p-sm text-ink-gray-9 placeholder:text-ink-gray-4 focus:border-ink-gray-5 focus:outline-none focus:ring-1 focus:ring-ink-gray-5 disabled:bg-surface-gray-1 disabled:text-ink-gray-5"
							placeholder="401002"
							@input="on_number_input"
						/>
						<div v-if="number_hints.length" class="text-xs text-ink-gray-5">
							{{ number_hints.join(" · ") }}
						</div>
						<div v-else-if="number_frozen" class="text-xs text-ink-gray-5">
							{{ __("Le code d'un compte existant ne peut pas être modifié.") }}
						</div>
					</div>

					<!-- Libellé -->
					<div class="space-y-1.5">
						<div class="text-xs font-medium text-ink-gray-5">
							{{ __("Libellé") }}
							<span class="text-ink-red-5">*</span>
						</div>
						<input
							v-model="form.account_name"
							type="text"
							:disabled="fields_disabled"
							class="h-8 w-full rounded-md border border-surface-gray-3 bg-surface-white px-3 text-p-sm text-ink-gray-9 placeholder:text-ink-gray-4 focus:border-ink-gray-5 focus:outline-none focus:ring-1 focus:ring-ink-gray-5 disabled:bg-surface-gray-1 disabled:text-ink-gray-5"
							:placeholder="__('Fournisseurs locaux')"
						/>
					</div>

					<!-- Nature -->
					<div class="space-y-1.5">
						<div class="text-xs font-medium text-ink-gray-5">
							{{ __("Nature") }}
						</div>
						<FormControl
							type="select"
							v-model="form.is_group"
							:options="NATURE_OPTIONS"
							:disabled="fields_disabled"
						/>
					</div>

					<!-- Sens -->
					<div class="space-y-1.5">
						<div class="text-xs font-medium text-ink-gray-5">
							{{ __("Sens") }}
							<span class="text-ink-red-5">*</span>
						</div>
						<FormControl
							type="select"
							v-model="form.sens"
							:options="SENS_OPTIONS"
							:disabled="fields_disabled"
						/>
					</div>

					<!-- Read-only chips -->
					<div v-if="mode === 'new'" class="flex flex-wrap items-center gap-2 sm:col-span-2">
						<span class="inline-flex items-center rounded-md border border-surface-gray-2 bg-surface-gray-1 px-2.5 py-1 text-xs font-medium text-ink-gray-7">
							{{ __("Classe") }}: {{ classe || "—" }}{{ class_name ? ` — ${__(class_name)}` : "" }}
						</span>
						<span class="inline-flex items-center rounded-md border border-surface-gray-2 bg-surface-gray-1 px-2.5 py-1 text-xs font-medium text-ink-gray-7">
							{{ __("Statut") }}: {{ __("Personnalisé") }}
						</span>
					</div>
				</div>
			</div>

			<!-- Informations card (edit mode) -->
			<div v-if="mode === 'record' && doc" class="rounded-lg border border-surface-gray-2 bg-surface-white p-6 shadow-xs">
				<div class="text-base font-bold text-ink-gray-9">
					{{ __("Informations") }}
				</div>
				<div class="my-4 border-b border-surface-gray-2" />
				<div class="grid grid-cols-1 gap-x-8 gap-y-3.5 md:grid-cols-2">
					<div class="flex flex-col gap-0.5">
						<span class="text-xs font-medium text-ink-gray-5">{{ __("Entreprise") }}</span>
						<span class="text-p-sm font-semibold text-ink-gray-9">
							{{ doc.entreprise }}{{ entreprise_info?.raison_sociale ? ` — ${entreprise_info.raison_sociale}` : "" }}
						</span>
					</div>
					<div class="flex flex-col gap-0.5">
						<span class="text-xs font-medium text-ink-gray-5">{{ __("Classe") }}</span>
						<span class="text-p-sm font-semibold text-ink-gray-9">
							{{ doc.classe || "—" }}{{ ROOT_CLASS_NAMES[doc.classe] ? ` — ${__(ROOT_CLASS_NAMES[doc.classe])}` : "" }}
						</span>
					</div>
					<div class="flex flex-col gap-0.5">
						<span class="text-xs font-medium text-ink-gray-5">{{ __("Compte parent") }}</span>
						<button
							v-if="doc.parent_chart_of_account"
							type="button"
							class="text-start text-p-sm font-semibold text-ink-gray-9 underline decoration-surface-gray-3 underline-offset-2 hover:text-ink-gray-7"
							@click="open_parent"
						>
							{{ doc.parent_chart_of_account }}
						</button>
						<span v-else class="text-p-sm text-ink-gray-5">{{ __("Racine de classe") }}</span>
					</div>
					<div class="flex flex-col gap-0.5">
						<span class="text-xs font-medium text-ink-gray-5">{{ __("Sous-comptes") }}</span>
						<span class="text-p-sm font-semibold text-ink-gray-9">{{ sub_count }}</span>
					</div>
					<div class="flex flex-col gap-0.5">
						<span class="text-xs font-medium text-ink-gray-5">{{ __("Créé le") }}</span>
						<span class="text-p-sm text-ink-gray-7">{{ format_date_dmy(doc.creation) }}</span>
					</div>
					<div class="flex flex-col gap-0.5">
						<span class="text-xs font-medium text-ink-gray-5">{{ __("Modifié le") }}</span>
						<span class="text-p-sm text-ink-gray-7">{{ format_datetime_dmy(doc.modified) }}</span>
					</div>
				</div>
			</div>
		</div>

		<!-- Delete confirmation -->
		<Dialog v-model="delete_dialog" :options="{ title: __('Supprimer le compte') }">
			<template #body>
				<p class="text-p-sm text-ink-gray-7">
					{{
						__("Supprimer le compte {0} — {1} ? Cette action est définitive.", [
							doc?.account_number || "",
							doc?.account_name || "",
						])
					}}
				</p>
			</template>
			<template #actions>
				<Button variant="subtle" :label="__('Annuler')" @click="delete_dialog = false" />
				<Button variant="solid" theme="red" :label="__('Supprimer')" :loading="deleting" @click="do_delete" />
			</template>
		</Dialog>

		<!-- Unlock confirmation -->
		<Dialog v-model="unlock_dialog" :options="{ title: __('Déverrouiller le compte') }">
			<template #body>
				<p class="text-p-sm text-ink-gray-7">
					{{
						__("Rendre le compte {0} — {1} modifiable ? Il ne sera plus verrouillé comme compte standard.", [
							doc?.account_number || "",
							doc?.account_name || "",
						])
					}}
				</p>
			</template>
			<template #actions>
				<Button variant="subtle" :label="__('Annuler')" @click="unlock_dialog = false" />
				<Button variant="solid" :label="__('Déverrouiller')" :loading="unlocking" @click="do_unlock" />
			</template>
		</Dialog>
	</div>
</template>
