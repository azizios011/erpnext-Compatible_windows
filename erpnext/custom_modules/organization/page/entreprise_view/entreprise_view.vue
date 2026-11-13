<!-- Entreprises — Frappe UI island page for the Entreprise doctype.

     Two modes from the desk route props (pageview passes `route` under the
     page segment and updates it on in-page navigation):
       - /app/entreprise-view            → list of entreprises
       - /app/entreprise-view/<CODE>     → the record as a frappe-ui wizard
       - /app/entreprise-view/new        → a blank record
     The editor renders every tab/section from the doctype meta through
     FormLayout + buildLayoutFromMeta; the Documents tab gets the framework
     FileUpload dialog; the Validation tab drops the raw validation_html field
     and shows frappe-ui recap cards instead. Saving goes through
     save_entreprise (whitelisted, runs the normal validate pipeline);
     validating reuses valider_entreprise. Server-side Entreprise-User
     visibility and permissions apply unchanged. -->
<script setup>
import { computed, onErrorCaptured, ref, watch } from "vue";
import { Badge, Button } from "frappe-ui";
import { buildLayoutFromMeta, FormLayout } from "@framework/ui/FormLayout";
import { useDoctypeMeta } from "@framework/ui";
import { FileUploadDialog } from "@framework/ui/FileUpload";

const frappe = window.frappe;
const __ = window.__;

const props = defineProps({
	route: { type: Array, default: () => [] },
	query: { type: Object, default: () => ({}) },
});
const emit = defineEmits(["title"]);

const DOCTYPE = "Entreprise";
const SKIPPED_FIELDTYPES = new Set(["HTML", "Button"]);
const NUMERIC_TYPES = new Set(["Int", "Float", "Currency", "Percent", "Check"]);

// ── routing ──────────────────────────────────────────────────────────────────
const mode = computed(() => (props.route?.length ? "record" : "list"));
const record_name = computed(() => props.route?.[0] || "");

// ── list mode ────────────────────────────────────────────────────────────────
const entreprises = ref([]);
const list_loading = ref(false);
const search_query = ref("");
const status_filter = ref("all");

const status_filters = [
	{ label: __("Toutes"), value: "all" },
	{ label: __("En création"), value: "En creation" },
	{ label: __("Créée"), value: "Creee" },
];

async function load_list() {
	list_loading.value = true;
	try {
		entreprises.value = await frappe.xcall("frappe.client.get_list", {
			doctype: DOCTYPE,
			fields: [
				"name",
				"code",
				"raison_sociale",
				"status",
				"param_paie",
				"nb_utilisateurs",
				"matricule_fiscal",
				"forme_juridique",
				"activite",
				"date_creation",
			],
			order_by: "code asc",
			limit_page_length: 0,
		});
	} finally {
		list_loading.value = false;
	}
}

const filtered_entreprises = computed(() => {
	const q = (search_query.value || "").trim().toLowerCase();
	return (entreprises.value || []).filter((item) => {
		if (status_filter.value !== "all" && item.status !== status_filter.value) {
			return false;
		}
		if (!q) return true;
		const code = (item.code || "").toLowerCase();
		const raison = (item.raison_sociale || "").toLowerCase();
		const matricule = (item.matricule_fiscal || "").toLowerCase();
		return code.includes(q) || raison.includes(q) || matricule.includes(q);
	});
});

const count_label = computed(() => {
	const count = filtered_entreprises.value.length;
	return count === 1 ? __("1 entreprise") : __("{0} entreprises", [count]);
});

function open_record(name) {
	frappe.set_route("entreprise-view", name);
}

function new_record() {
	frappe.set_route("entreprise-view", "new");
}

function status_theme(status) {
	return status === "Creee" ? "green" : "amber";
}

// ── record mode ──────────────────────────────────────────────────────────────
const doc = ref(null);
const layout = ref(null);
const general_layout = ref(null);
const financier_layout = ref(null);
const active_tab = ref("");
const loading_doc = ref(false);
const saving = ref(false);
const validating = ref(false);
const is_new = ref(false);
const uploader_open = ref(false);
const render_error = ref(null);

// A render error inside the editor subtree blanks it silently otherwise;
// captured here the message shows on the page itself.
onErrorCaptured((error, instance, info) => {
	render_error.value = `${error?.message || String(error)} (${info})`;
	return false;
});

const meta = useDoctypeMeta(DOCTYPE);

// Apply default values from doctype metadata to new records without overwriting
// anything the user has already typed.
function apply_meta_defaults(target_doc) {
	if (!target_doc || !meta.meta.value?.fields) return;
	const fields = meta.meta.value.fields;

	for (const field of fields) {
		if (
			field.fieldname &&
			field.default !== undefined &&
			field.default !== null &&
			field.default !== ""
		) {
			if (
				target_doc[field.fieldname] === undefined ||
				target_doc[field.fieldname] === null ||
				target_doc[field.fieldname] === ""
			) {
				let def = field.default;
				if (NUMERIC_TYPES.has(field.fieldtype)) {
					const num = Number(def);
					def = Number.isFinite(num) ? num : 0;
				}
				target_doc[field.fieldname] = def;
			}
		}
	}
}

// the raw validation_html field (template-literal cards in the standard form)
// and the button stub are replaced by this island's own UI; hidden fields
// (entreprise/exercice links, computed summaries) stay server-side. The child
// metas feed the Documents / Utilisateurs grid columns.
function build_layout(fields) {
	if (!Array.isArray(fields)) return;
	const kept = fields.filter((f) => !SKIPPED_FIELDTYPES.has(f.fieldtype) && !f.hidden);
	const child_metas = Object.fromEntries(
		Object.entries(meta.metas.value || {}).map(([name, child]) => [name, child.fields || []])
	);
	const tabs = buildLayoutFromMeta(kept, { childMetas: child_metas });

	const general_tab = tabs.find((t) => t.name === "tab_general");
	const financier_tab = tabs.find((t) => t.name === "tab_financier");
	const kept_tabs = [general_tab, financier_tab].filter(Boolean);

	for (const tab of kept_tabs) {
		(tab.sections || []).forEach((section, index) => {
			section.collapsible = false;
			section.opened = true;
			if (index === 0) {
				// The top-level card header already provides the card title
				section.hideLabel = true;
				section.hideBorder = true;
			} else {
				// Keep the section labels from meta for subheadings (Identification, Adresse, etc.)
				section.hideLabel = false;
				section.hideBorder = false;
			}
		});
	}

	const merged = {
		name: "main",
		label: "",
		sections: [
			...(general_tab?.sections || []),
			...(financier_tab?.sections || []),
		],
	};

	// Flatten each section's fields into one column so it renders as one row-aligned grid
	for (const section of merged.sections) {
		const all_fields = (section.columns || []).flatMap((col) => col.fields || []);
		section.columns = [{ fields: all_fields }];
	}

	layout.value = [merged];
	general_layout.value = general_tab
		? [{ ...general_tab, label: "", sections: general_tab.sections }]
		: null;
	financier_layout.value = financier_tab
		? [{ ...financier_tab, label: "", sections: financier_tab.sections }]
		: null;

	console.debug("[entreprise-view] sections:", merged.sections.map((s) => s.label || s.name));
}

watch(
	() => meta.meta.value?.fields,
	(fields) => {
		build_layout(fields);
		if (is_new.value && doc.value) {
			apply_meta_defaults(doc.value);
		}
	},
	{ immediate: true }
);

async function load_record(name) {
	loading_doc.value = true;
	try {
		doc.value = await frappe.xcall("frappe.client.get", { doctype: DOCTYPE, name });
		is_new.value = false;
	} finally {
		loading_doc.value = false;
	}
}

function start_new_record() {
	doc.value = { doctype: DOCTYPE, status: "En creation" };
	is_new.value = true;
	apply_meta_defaults(doc.value);
}

watch(
	() => props.route,
	(route) => {
		if (!route?.length) {
			load_list();
			emit("title", __("Entreprises"));
			return;
		}
		const target = route[0];
		if (target === "new") {
			start_new_record();
			emit("title", __("Nouvelle Entreprise"));
		} else {
			load_record(target);
		}
	},
	{ immediate: true }
);

watch(doc, (value) => {
	if (mode.value === "record" && value) {
		const label = is_new.value
			? __("Nouvelle Entreprise")
			: value.raison_sociale || value.name || __("Nouvelle Entreprise");
		emit("title", value.code && !is_new.value ? `${label} (${value.code})` : label);
	}
});

const is_validated = computed(() => doc.value?.status === "Creee");
const is_validation_tab = computed(() => /validation/i.test(active_tab.value || ""));
const is_documents_tab = computed(() => /documents/i.test(active_tab.value || ""));

const record_title = computed(() => {
	if (is_new.value) return __("Nouvelle Entreprise");
	return doc.value?.raison_sociale || doc.value?.name || __("Nouvelle Entreprise");
});

const card_rows = computed(() => {
	const d = doc.value || {};
	const pick = (...fieldnames) =>
		fieldnames
			.filter((fieldname) => d[fieldname] !== undefined && d[fieldname] !== null && d[fieldname] !== "")
			.map((fieldname) => [fieldname, d[fieldname]]);
	return {
		identification: pick(
			"code",
			"raison_sociale",
			"matricule_fiscal",
			"forme_juridique",
			"activite",
			"convention",
			"numero_rne",
			"numero_dossier"
		),
		comptabilite: pick(
			"capital_social",
			"valeur_nominale_action",
			"devise",
			"taux_imposition",
			"duree_exercice",
			"jour_arrete",
			"mois_arrete",
			"type_plan_comptable",
			"longueur_compte_comptable"
		),
	};
});

// ── actions ──────────────────────────────────────────────────────────────────
async function save() {
	saving.value = true;
	try {
		const payload = JSON.parse(JSON.stringify(doc.value));
		if (is_new.value) {
			const inserted = await frappe.xcall("frappe.client.insert", { doc: payload });
			is_new.value = false;
			frappe.show_alert({ message: __("Entreprise creee."), indicator: "green" });
			frappe.set_route("entreprise-view", inserted.name);
			return;
		}
		doc.value = await frappe.xcall(
			"erpnext.custom_modules.organization.doctype.entreprise.entreprise.save_entreprise",
			{ doc: payload }
		);
		frappe.show_alert({ message: __("Enregistre."), indicator: "green" });
	} catch (error) {
		const text = error?.message || error?.exc || "";
		// frappe.call already displays server-raised messages; only surface
		// client-side failures that carried no server message
		if (text && !text.includes("Code is required") && !error?._server_messages) {
			frappe.msgprint({ message: text, indicator: "red" });
		}
	} finally {
		saving.value = false;
	}
}

async function valider() {
	validating.value = true;
	try {
		await save();
		if (is_new.value || !doc.value?.name) return;
		await frappe.xcall(
			"erpnext.custom_modules.organization.doctype.entreprise.entreprise.valider_entreprise",
			{ name: doc.value.name }
		);
		doc.value.status = "Creee";
		frappe.show_alert({ message: __("Entreprise validee."), indicator: "green" });
	} catch (error) {
		// save()/valider already surfaced the server message via msgprint
	} finally {
		validating.value = false;
	}
}

function on_documents_committed(results) {
	for (const uploaded of results || []) {
		const filename = (uploaded.file_name || "").toLowerCase();
		const is_plan = filename.includes("plan") && /\.(xlsx|xls|pdf)$/.test(filename);
		doc.value?.documents?.push({
			type_document: is_plan ? "Plan comptable" : "Autre",
			libelle: uploaded.file_name,
			fichier: uploaded.file_url,
			date_ajout: frappe.datetime.nowdate(),
			ajoute_par: frappe.session.user,
		});
	}
}

const FIELD_LABELS = {
	code: __("Code"),
	raison_sociale: __("Raison sociale"),
	matricule_fiscal: __("Matricule fiscal"),
	forme_juridique: __("Forme juridique"),
	activite: __("Activite"),
	convention: __("Convention collective"),
	numero_rne: __("Numero RNE"),
	numero_dossier: __("Numero dossier"),
	capital_social: __("Capital social"),
	valeur_nominale_action: __("Valeur nominale action"),
	devise: __("Devise"),
	taux_imposition: __("Taux d'imposition"),
	duree_exercice: __("Duree exercice"),
	jour_arrete: __("Jour arrete"),
	mois_arrete: __("Mois arrete"),
	type_plan_comptable: __("Type plan comptable"),
	longueur_compte_comptable: __("Longueur compte comptable"),
};
</script>

<template>
	<div class="h-full overflow-y-auto">
		<!-- Render error captured within subtree -->
		<div v-if="render_error" class="mx-auto w-full max-w-[1600px] px-6 lg:px-10 pt-4">
			<pre class="rounded border border-surface-red-3 bg-surface-red-1 p-3 text-p-sm text-ink-red-6 whitespace-pre-wrap">{{ render_error }}</pre>
		</div>

		<!-- ══ List mode ══ -->
		<div v-if="mode === 'list'" class="mx-auto w-full max-w-[1600px] px-6 lg:px-10 py-6 pb-16 space-y-6">
			<!-- Top bar -->
			<div class="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
				<div class="flex flex-wrap items-center gap-3">
					<!-- Search input -->
					<div class="relative w-64 sm:w-80">
						<span class="pointer-events-none absolute inset-y-0 start-0 flex items-center ps-3 text-ink-gray-4">
							<svg class="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
								<circle cx="11" cy="11" r="8" />
								<path d="m21 21-4.3-4.3" />
							</svg>
						</span>
						<input
							v-model="search_query"
							type="search"
							:placeholder="__('Rechercher par code, nom, matricule...')"
							class="h-9 w-full rounded-md border border-surface-gray-3 bg-surface-white ps-9 pe-3 text-p-sm text-ink-gray-9 placeholder:text-ink-gray-4 focus:border-ink-gray-5 focus:outline-none focus:ring-1 focus:ring-ink-gray-5"
						/>
					</div>

					<!-- Status filter chips -->
					<div class="inline-flex items-center rounded-lg border border-surface-gray-2 bg-surface-gray-1 p-1">
						<button
							v-for="chip in status_filters"
							:key="chip.value"
							type="button"
							:class="[
								'rounded-md px-3 py-1 text-p-sm font-medium transition-colors',
								status_filter === chip.value
									? 'bg-surface-white text-ink-gray-9 shadow-xs'
									: 'text-ink-gray-6 hover:text-ink-gray-9',
							]"
							@click="status_filter = chip.value"
						>
							{{ chip.label }}
						</button>
					</div>

					<!-- Count -->
					<span class="text-p-sm text-ink-gray-5">
						{{ count_label }}
					</span>
				</div>

				<!-- New record button -->
				<Button variant="solid" :label="__('Nouvelle Entreprise')" @click="new_record" />
			</div>

			<!-- Full-width table card -->
			<div class="overflow-hidden rounded-lg border border-surface-gray-2 bg-surface-white shadow-xs">
				<div class="overflow-x-auto">
					<table class="w-full text-left border-collapse">
						<thead>
							<tr class="sticky top-0 z-10 border-b border-surface-gray-2 bg-surface-gray-1">
								<th class="bg-surface-gray-1 px-4 py-3 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6">
									{{ __("Code") }}
								</th>
								<th class="bg-surface-gray-1 px-4 py-3 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6">
									{{ __("Raison sociale") }}
								</th>
								<th class="bg-surface-gray-1 px-4 py-3 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6">
									{{ __("Matricule fiscal") }}
								</th>
								<th class="bg-surface-gray-1 px-4 py-3 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6">
									{{ __("Forme juridique") }}
								</th>
								<th class="bg-surface-gray-1 px-4 py-3 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6">
									{{ __("Activité") }}
								</th>
								<th class="bg-surface-gray-1 px-4 py-3 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6">
									{{ __("Suivi paie") }}
								</th>
								<th class="bg-surface-gray-1 px-4 py-3 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6 text-center">
									{{ __("Utilisateurs") }}
								</th>
								<th class="bg-surface-gray-1 px-4 py-3 text-p-xs font-semibold uppercase tracking-wider text-ink-gray-6 text-end">
									{{ __("Statut") }}
								</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-surface-gray-2">
							<!-- Loading skeleton rows -->
							<template v-if="list_loading">
								<tr v-for="i in 5" :key="i">
									<td v-for="j in 8" :key="j" class="px-4 py-3.5">
										<div class="h-4 w-3/4 animate-pulse rounded bg-surface-gray-2" />
									</td>
								</tr>
							</template>

							<!-- Filtered data rows -->
							<template v-else-if="filtered_entreprises.length">
								<tr
									v-for="entreprise in filtered_entreprises"
									:key="entreprise.name"
									class="cursor-pointer transition-colors hover:bg-surface-gray-1"
									@click="open_record(entreprise.name)"
								>
									<td class="px-4 py-3.5 text-p-sm font-semibold text-ink-gray-9">
										{{ entreprise.code }}
									</td>
									<td class="px-4 py-3.5 text-p-sm font-medium text-ink-gray-9">
										{{ entreprise.raison_sociale || entreprise.name }}
									</td>
									<td class="px-4 py-3.5 text-p-sm text-ink-gray-7">
										{{ entreprise.matricule_fiscal || "—" }}
									</td>
									<td class="px-4 py-3.5 text-p-sm text-ink-gray-7">
										{{ entreprise.forme_juridique || "—" }}
									</td>
									<td class="px-4 py-3.5 text-p-sm text-ink-gray-7">
										{{ entreprise.activite || "—" }}
									</td>
									<td class="px-4 py-3.5 text-p-sm text-ink-gray-7">
										{{ entreprise.param_paie || "—" }}
									</td>
									<td class="px-4 py-3.5 text-p-sm text-ink-gray-7 text-center">
										{{ entreprise.nb_utilisateurs ?? 0 }}
									</td>
									<td class="px-4 py-3.5 text-p-sm text-end">
										<Badge
											variant="subtle"
											size="sm"
											:theme="status_theme(entreprise.status)"
											:label="entreprise.status"
										/>
									</td>
								</tr>
							</template>
						</tbody>
					</table>
				</div>

				<!-- Empty state -->
				<div
					v-if="!list_loading && !filtered_entreprises.length"
					class="flex flex-col items-center justify-center px-6 py-16 text-center"
				>
					<div class="mb-4 flex size-14 items-center justify-center rounded-full bg-surface-gray-2 text-ink-gray-5">
						<svg class="size-7" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75">
							<rect width="16" height="20" x="4" y="2" rx="2" ry="2" />
							<path d="M9 22v-4h6v4" />
							<path d="M8 6h.01" />
							<path d="M16 6h.01" />
							<path d="M12 6h.01" />
							<path d="M12 10h.01" />
							<path d="M12 14h.01" />
							<path d="M16 10h.01" />
							<path d="M16 14h.01" />
							<path d="M8 10h.01" />
							<path d="M8 14h.01" />
						</svg>
					</div>
					<h3 class="text-p-base font-semibold text-ink-gray-9">
						{{ entreprises.length ? __("Aucun résultat") : __("Aucune entreprise") }}
					</h3>
					<p class="mt-1 max-w-sm text-p-sm text-ink-gray-5">
						{{
							entreprises.length
								? __("Aucune entreprise ne correspond à vos critères de recherche.")
								: __("Créez votre première entreprise pour configurer vos données comptables.")
						}}
					</p>
					<div class="mt-6">
						<Button variant="solid" :label="__('Nouvelle Entreprise')" @click="new_record" />
					</div>
				</div>
			</div>
		</div>

		<!-- ══ Record mode ══ -->
		<div v-else class="min-h-full">
			<!-- Sticky header bar -->
			<div class="sticky top-0 z-20 border-b border-surface-gray-2 bg-surface-white">
				<div class="mx-auto flex w-full max-w-[1600px] items-center justify-between gap-4 px-6 lg:px-10 py-3.5">
					<div class="flex min-w-0 items-center gap-3">
						<Button
							variant="ghost"
							:label="__('← Entreprises')"
							@click="frappe.set_route('entreprise-view')"
						/>
						<div class="h-4 w-px bg-surface-gray-2" />
						<h1 class="truncate text-p-base font-semibold text-ink-gray-9">
							{{ record_title }}
						</h1>
						<Badge
							variant="subtle"
							size="sm"
							:theme="status_theme(doc?.status || 'En creation')"
							:label="doc?.status || 'En creation'"
						/>
					</div>

					<div class="flex items-center gap-2">
						<Button
							v-if="!is_new && !is_validated"
							variant="subtle"
							:label="__('Valider l\'entreprise')"
							:loading="validating"
							@click="valider"
						/>
						<Button
							variant="solid"
							:label="__('Enregistrer')"
							:loading="saving"
							@click="save"
						/>
					</div>
				</div>
			</div>

			<!-- Record content area -->
			<div class="mx-auto w-full max-w-[1600px] px-6 lg:px-10 py-6 pb-16 space-y-6">
				<!-- Loading skeleton -->
				<div v-if="loading_doc || (!doc && !is_new)" class="space-y-6">
					<div v-for="index in 2" :key="index" class="rounded-lg border border-surface-gray-2 bg-surface-white p-6 space-y-4">
						<div class="h-6 w-48 animate-pulse rounded bg-surface-gray-2" />
						<div class="h-px bg-surface-gray-2" />
						<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
							<div v-for="f in 8" :key="f" class="h-12 animate-pulse rounded bg-surface-gray-2" />
						</div>
					</div>
				</div>

				<template v-else-if="doc">
					<div v-if="is_documents_tab" class="mb-4 flex justify-end">
						<Button variant="subtle" :label="__('Ajouter des documents')" @click="uploader_open = true" />
					</div>

					<!-- Stacked white cards -->
					<div class="flex flex-col gap-6 entreprise-form">
						<!-- Informations Générales Card -->
						<div class="rounded-lg border border-surface-gray-2 bg-surface-white p-6 shadow-xs">
							<div class="text-base font-bold text-ink-gray-9">
								{{ __("Informations Générales") }}
							</div>
							<div class="my-4 border-b border-surface-gray-2" />
							<FormLayout
								v-if="general_layout"
								:layout="general_layout"
								v-model:doc="doc"
								@update:activeTab="active_tab = $event"
							/>
						</div>

						<!-- Informations Financières Card -->
						<div class="rounded-lg border border-surface-gray-2 bg-surface-white p-6 shadow-xs">
							<div class="text-base font-bold text-ink-gray-9">
								{{ __("Informations Financières") }}
							</div>
							<div class="my-4 border-b border-surface-gray-2" />
							<FormLayout
								v-if="financier_layout"
								:layout="financier_layout"
								v-model:doc="doc"
								@update:activeTab="active_tab = $event"
							/>
						</div>
					</div>

					<!-- Validation tab body (retained recap cards) -->
					<div v-if="is_validation_tab" class="mt-6 flex flex-wrap gap-4">
						<div
							v-for="(rows, group) in card_rows"
							:key="group"
							class="min-w-[300px] flex-1 rounded-lg border border-surface-gray-2 bg-surface-white p-6 shadow-xs"
						>
							<div class="mb-3 font-semibold text-ink-amber-6">
								{{ group === "identification" ? __("Identification") : __("Comptabilité") }}
							</div>
							<div
								v-for="[fieldname, value] in rows"
								:key="fieldname"
								class="flex items-baseline justify-between gap-4 border-b border-dashed border-surface-gray-2 py-2 text-p-sm last:border-0"
							>
								<span class="text-ink-gray-5">{{ FIELD_LABELS[fieldname] || fieldname }}</span>
								<span class="text-ink-gray-9">{{ value }}</span>
							</div>
						</div>
					</div>
				</template>
			</div>
		</div>

		<FileUploadDialog v-model:open="uploader_open" multiple @committed="on_documents_committed" />
	</div>
</template>

<style scoped>
/* Responsive grid for FormLayout fields inside each card section */
.entreprise-form :deep(.column) {
	display: grid !important;
	grid-template-columns: repeat(1, minmax(0, 1fr)) !important;
	gap: 1.25rem 1rem !important;
	align-items: start !important;
}

@media (min-width: 640px) {
	.entreprise-form :deep(.column) {
		grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
	}
}

@media (min-width: 1024px) {
	.entreprise-form :deep(.column) {
		grid-template-columns: repeat(3, minmax(0, 1fr)) !important;
	}
}

@media (min-width: 1280px) {
	.entreprise-form :deep(.column) {
		grid-template-columns: repeat(4, minmax(0, 1fr)) !important;
	}
}

/* Sub-group section headers: small uppercase muted subheading taking full row */
.entreprise-form :deep(.section-header) {
	width: 100% !important;
	max-width: 100% !important;
	margin-bottom: 0.75rem !important;
	padding-top: 0.25rem !important;
	cursor: default !important;
}

.entreprise-form :deep(.section-header span) {
	font-size: 0.75rem !important;
	line-height: 1rem !important;
	letter-spacing: 0.05em !important;
	text-transform: uppercase !important;
	color: var(--ink-gray-5, #64748b) !important;
	font-weight: 600 !important;
}

/* Thin divider between sub-groups within a card */
.entreprise-form :deep(.section) {
	border-top-color: var(--surface-gray-2, #e2e8f0) !important;
}

.entreprise-form :deep(.section:first-child) {
	border-top: none !important;
	padding-top: 0 !important;
	margin-top: 0 !important;
}

/* Field labels: one line where possible, no wrapping at normal widths */
.entreprise-form :deep(.field [data-slot="label"]),
.entreprise-form :deep(.field label) {
	white-space: nowrap !important;
	overflow: hidden !important;
	text-overflow: ellipsis !important;
	font-weight: 500 !important;
}

/* Required asterisk in red */
.entreprise-form :deep(.field [data-slot="label"] span.text-ink-red-5),
.entreprise-form :deep(.field [data-slot="label"] span[aria-hidden="true"]),
.entreprise-form :deep(.field label span.text-ink-red-5),
.entreprise-form :deep(.field label span[aria-hidden="true"]) {
	color: var(--ink-red-5, #ef4444) !important;
}

/* Consistent input heights */
.entreprise-form :deep(.field input),
.entreprise-form :deep(.field select),
.entreprise-form :deep(.field button[role="combobox"]),
.entreprise-form :deep(.field [data-slot="input"]),
.entreprise-form :deep(.field [data-slot="control"]) {
	min-height: 2.25rem !important;
	height: 2.25rem !important;
}

/* Checkboxes aligned on the same baseline as inputs, not floating */
.entreprise-form :deep(.field[data-fieldtype="Check"]) {
	display: flex !important;
	align-items: flex-start !important;
	padding-top: 1.625rem !important;
	min-height: 3.875rem !important;
}

.entreprise-form :deep(.field[data-fieldtype="Check"] > div) {
	min-height: 2.25rem !important;
	display: inline-flex !important;
	align-items: center !important;
}

.entreprise-form :deep(.field[data-fieldtype="Check"] input[type="checkbox"]) {
	margin-top: 0 !important;
}
</style>