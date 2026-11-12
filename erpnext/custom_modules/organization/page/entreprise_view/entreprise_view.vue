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
import { computed, ref, watch } from "vue";
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

// ── routing ──────────────────────────────────────────────────────────────────
const mode = computed(() => (props.route?.length ? "record" : "list"));
const record_name = computed(() => props.route?.[0] || "");

// ── list mode ────────────────────────────────────────────────────────────────
const entreprises = ref([]);
const list_loading = ref(false);

async function load_list() {
	list_loading.value = true;
	try {
		entreprises.value = await frappe.xcall("frappe.client.get_list", {
			doctype: DOCTYPE,
			fields: ["name", "code", "raison_sociale", "status", "param_paie", "nb_utilisateurs"],
			order_by: "code asc",
			limit_page_length: 0,
		});
	} finally {
		list_loading.value = false;
	}
}

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
const active_tab = ref("");
const loading_doc = ref(false);
const saving = ref(false);
const validating = ref(false);
const is_new = ref(false);
const uploader_open = ref(false);

const meta = useDoctypeMeta(DOCTYPE);

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
	layout.value = buildLayoutFromMeta(kept, { childMetas: child_metas });
}
watch(() => meta.meta.value?.fields, build_layout, { immediate: true });

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
		const label = value.raison_sociale || value.name || __("Nouvelle Entreprise");
		emit("title", value.code ? `${label} (${value.code})` : label);
	}
});

const is_validated = computed(() => doc.value?.status === "Creee");
const is_validation_tab = computed(() => /validation/i.test(active_tab.value || ""));
const is_documents_tab = computed(() => /documents/i.test(active_tab.value || ""));

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
		frappe.msgprint({ message: error?.message || String(error), indicator: "red" });
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
	<div class="h-full overflow-y-auto pb-10">
		<!-- ══ List mode ══ -->
		<div v-if="mode === 'list'" class="mx-auto w-full max-w-3xl px-6">
			<div class="mb-4 flex items-center justify-between gap-3">
				<div class="text-p-medium text-ink-gray-7">
					{{ __("Structure de vos societes comptables") }}
				</div>
				<Button variant="solid" :label="__('Nouvelle Entreprise')" @click="new_record" />
			</div>

			<div v-if="list_loading" class="space-y-2">
				<div v-for="index in 3" :key="index" class="h-14 animate-pulse rounded bg-surface-gray-2" />
			</div>

			<div
				v-else-if="entreprises.length"
				class="divide-y divide-surface-gray-2 rounded-lg border border-surface-gray-2 bg-surface-white"
			>
				<button
					v-for="entreprise in entreprises"
					:key="entreprise.name"
					class="flex w-full items-center gap-4 px-4 py-3 text-left transition-colors hover:bg-surface-gray-1"
					@click="open_record(entreprise.name)"
				>
					<div class="min-w-0 flex-1">
						<div class="truncate text-p-medium text-ink-gray-9">
							{{ entreprise.raison_sociale || entreprise.name }}
						</div>
						<div class="text-p-sm text-ink-gray-5">{{ entreprise.code }}</div>
					</div>
					<div class="text-p-sm text-ink-gray-5">
						{{ __("Suivi paie") }}: {{ entreprise.param_paie || "—" }}
					</div>
					<Badge variant="subtle" size="sm" :theme="status_theme(entreprise.status)" :label="entreprise.status" />
				</button>
			</div>

			<div v-else class="mt-16 text-center text-p-medium text-ink-gray-5">
				{{ __("Aucune entreprise. Creez la premiere.") }}
			</div>
		</div>

		<!-- ══ Record mode ══ -->
		<div v-else class="mx-auto w-full max-w-3xl px-6">
			<div v-if="loading_doc || (!doc && !is_new)" class="space-y-3">
				<div v-for="index in 4" :key="index" class="h-10 animate-pulse rounded bg-surface-gray-2" />
			</div>

			<template v-else-if="doc">
				<div class="mb-4 flex items-center justify-between gap-3">
					<Badge variant="subtle" size="md" :theme="status_theme(doc.status)" :label="doc.status" />
					<div class="flex items-center gap-2">
						<Button
							v-if="!is_new && !is_validated"
							variant="subtle"
							:label="__('Valider l\'entreprise')"
							:loading="validating"
							@click="valider"
						/>
						<Button variant="solid" :label="__('Enregistrer')" :loading="saving" @click="save" />
					</div>
				</div>

				<div v-if="is_documents_tab" class="mb-3 flex justify-end">
					<Button variant="subtle" :label="__('Ajouter des documents')" @click="uploader_open = true" />
				</div>

				<div v-if="layout" class="rounded-lg border border-surface-gray-2 bg-surface-white px-4 py-2">
					<FormLayout :layout="layout" v-model:doc="doc" @update:activeTab="active_tab = $event" />
				</div>

				<!-- Validation tab body: frappe-ui recap cards where the raw
				     validation_html field used to be -->
				<div v-if="is_validation_tab" class="mt-4 flex flex-wrap gap-3">
					<div
						v-for="(rows, group) in card_rows"
						:key="group"
						class="min-w-[300px] flex-1 rounded-lg border border-surface-gray-2 bg-surface-white p-4"
					>
						<div class="mb-2 font-semibold text-ink-amber-6">
							{{ group === "identification" ? __("Identification") : __("Comptabilite") }}
						</div>
						<div
							v-for="[fieldname, value] in rows"
							:key="fieldname"
							class="flex items-baseline justify-between gap-4 border-b border-dashed border-surface-gray-2 py-1 text-p-sm last:border-0"
						>
							<span class="text-ink-gray-5">{{ FIELD_LABELS[fieldname] || fieldname }}</span>
							<span class="text-ink-gray-9">{{ value }}</span>
						</div>
					</div>
				</div>
			</template>
		</div>

		<FileUploadDialog v-model:open="uploader_open" multiple @committed="on_documents_committed" />
	</div>
</template>
