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
import { computed, onErrorCaptured, provide, ref, watch } from "vue";
import { Badge, Button } from "frappe-ui";
import { buildLayoutFromMeta, FormLayout, LinkTitlesKey } from "@framework/ui/FormLayout";
import { useDoctypeMeta } from "@framework/ui";
import { FileUploadDialog } from "@framework/ui/FileUpload";
import PlanComptableImportDialog from "./PlanComptableImportDialog.vue";

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
const plan_uploader_open = ref(false);
const plan_import_open = ref(false);
const plan_accounts_count = ref(0);
const plan_import_hint = __("Enregistrez l'entreprise avant d'importer son plan comptable");
const plan_import_disabled = computed(() => Boolean(is_new.value || !doc.value?.name));
const render_error = ref(null);

// ── Link fields human titles (Part 1) ────────────────────────────────────────
const linkTitles = ref({});
provide(LinkTitlesKey, linkTitles);
const convention_details = ref(null);

// A render error inside the editor subtree blanks it silently otherwise;
// captured here the message shows on the page itself.
onErrorCaptured((error, instance, info) => {
	render_error.value = `${error?.message || String(error)} (${info})`;
	return false;
});

const meta = useDoctypeMeta(DOCTYPE);

function get_link_fields() {
	return (meta.meta.value?.fields || []).filter(
		(f) => f.fieldtype === "Link" && f.options
	);
}

async function fetch_link_title(doctype, docname) {
	if (!doctype || !docname) return;
	const key = `${doctype}::${docname}`;
	if (linkTitles.value[key] !== undefined) return linkTitles.value[key];
	try {
		const title = await frappe.xcall("frappe.desk.search.get_link_title", {
			doctype,
			docname,
		});
		if (title) {
			linkTitles.value = { ...linkTitles.value, [key]: title };
			return title;
		}
	} catch {
		// Ignore failures silently
	}
}

async function fetch_all_link_titles() {
	if (!doc.value) return;
	const link_fields = get_link_fields();
	for (const field of link_fields) {
		const val = doc.value[field.fieldname];
		if (val) {
			fetch_link_title(field.options, val);
		}
	}
}

watch(
	() => {
		if (!doc.value) return [];
		const link_fields = get_link_fields();
		return link_fields.map((f) => ({
			doctype: f.options,
			val: doc.value[f.fieldname],
		}));
	},
	(fields) => {
		for (const { doctype, val } of fields) {
			if (doctype && val && !linkTitles.value[`${doctype}::${val}`]) {
				fetch_link_title(doctype, val);
			}
		}
	},
	{ deep: true, immediate: true }
);

async function load_convention_details(code) {
	if (!code) {
		convention_details.value = null;
		return;
	}
	try {
		const res = await frappe.xcall("frappe.client.get_value", {
			doctype: "Convention Collective",
			filters: { name: code },
			fieldname: ["nombre_jours", "nombre_heures", "droit_conge"],
		});
		if (res) {
			convention_details.value = res;
		}
	} catch {
		convention_details.value = null;
	}
}

watch(
	() => doc.value?.convention,
	(code) => {
		load_convention_details(code);
	},
	{ immediate: true }
);

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
		if (!Array.isArray(doc.value.documents)) doc.value.documents = [];
		is_new.value = false;
		fetch_all_link_titles();
		plan_accounts_count.value = await frappe.xcall("frappe.client.get_count", {
			doctype: "Chart of Account",
			filters: { entreprise: name },
		});
	} finally {
		loading_doc.value = false;
	}
}

function start_new_record() {
	doc.value = { doctype: DOCTYPE, status: "En creation", documents: [] };
	is_new.value = true;
	plan_accounts_count.value = 0;
	apply_meta_defaults(doc.value);
	fetch_all_link_titles();
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
			frappe.show_alert({
				message: __("Entreprise enregistrée — vous pouvez maintenant importer son plan comptable"),
				indicator: "green",
			});
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

// ── Plan comptable & formatting helpers (Part 2) ───────────────────────────────
function get_filename(url) {
	if (!url) return "";
	try {
		const path = new URL(url, "http://x").pathname;
		return decodeURIComponent(path.split("/").filter(Boolean).pop() || url);
	} catch {
		return String(url).split("/").pop() || String(url);
	}
}

function format_date_dmy(val) {
	if (!val) return null;
	if (typeof val === "string" && /^\d{4}-\d{2}-\d{2}/.test(val)) {
		const [y, m, d] = val.slice(0, 10).split("-");
		return `${d}/${m}/${y}`;
	}
	try {
		const dt = new Date(val);
		if (isNaN(dt.getTime())) return String(val);
		const d = String(dt.getDate()).padStart(2, "0");
		const m = String(dt.getMonth() + 1).padStart(2, "0");
		const y = dt.getFullYear();
		return `${d}/${m}/${y}`;
	} catch {
		return String(val);
	}
}

function format_datetime_dmy(val) {
	if (!val) return "";
	if (typeof val === "string" && /^\d{4}-\d{2}-\d{2}/.test(val)) {
		const [y, m, d] = val.slice(0, 10).split("-");
		const time = val.slice(11, 16);
		return time ? `${d}/${m}/${y} ${time}` : `${d}/${m}/${y}`;
	}
	try {
		const dt = new Date(val);
		if (isNaN(dt.getTime())) return String(val);
		const d = String(dt.getDate()).padStart(2, "0");
		const m = String(dt.getMonth() + 1).padStart(2, "0");
		const y = dt.getFullYear();
		const time = `${String(dt.getHours()).padStart(2, "0")}:${String(dt.getMinutes()).padStart(2, "0")}`;
		return `${d}/${m}/${y} ${time}`;
	} catch {
		return String(val);
	}
}

function format_number_fr(val) {
	if (val === undefined || val === null || val === "") return null;
	const num = Number(val);
	if (isNaN(num)) return String(val);
	return new Intl.NumberFormat("fr-FR").format(num);
}

function get_type_document_options() {
	const child_fields = meta.metas.value?.["Entreprise Document"]?.fields;
	const main_fields = meta.meta.value?.fields;
	const field =
		(child_fields || []).find((f) => f.fieldname === "type_document") ||
		(main_fields || []).find((f) => f.fieldname === "type_document");
	if (field?.options) {
		return field.options
			.split("\n")
			.map((s) => s.trim())
			.filter(Boolean);
	}
	return [];
}

function on_documents_committed(results) {
	if (!doc.value) return;
	if (!Array.isArray(doc.value.documents)) {
		doc.value.documents = [];
	}
	const type_options = get_type_document_options();
	const default_non_plan =
		type_options.find((opt) => opt !== "Plan comptable") || type_options[0] || "Autre";

	for (const uploaded of results || []) {
		const filename = uploaded.file_name || "";
		const is_plan = filename.toLowerCase().includes("plan");
		doc.value.documents.push({
			doctype: "Entreprise Document",
			parentfield: "documents",
			parenttype: DOCTYPE,
			type_document: is_plan ? "Plan comptable" : default_non_plan,
			libelle: uploaded.file_name,
			fichier: uploaded.file_url,
			date_ajout: frappe.datetime?.nowdate?.() || new Date().toISOString().slice(0, 10),
			ajoute_par: frappe.session?.user || "Administrator",
		});
	}
}

function on_plan_comptable_committed(results) {
	const first = results?.[0];
	if (first && doc.value) {
		doc.value.plan_comptable_fichier = first.file_url;
		doc.value.plan_comptable_ajoute_le =
			frappe.datetime?.now_datetime?.() ||
			new Date().toISOString().slice(0, 19).replace("T", " ");
	}
}

function clear_plan_comptable() {
	if (!doc.value) return;
	doc.value.plan_comptable_fichier = null;
	doc.value.plan_comptable_ajoute_le = null;
}

function open_plan_comptable() {
	if (doc.value?.name) {
		frappe.set_route("plan-comptable", { entreprise: doc.value.name });
	}
}

async function on_plan_imported() {
	// the backend stamped plan_comptable_fichier / plan_comptable_ajoute_le:
	// reload the doc and the imported-accounts count
	if (!doc.value?.name) return;
	try {
		doc.value = await frappe.xcall("frappe.client.get", { doctype: DOCTYPE, name: doc.value.name });
		if (!Array.isArray(doc.value.documents)) doc.value.documents = [];
		is_new.value = false;
		fetch_all_link_titles();
		plan_accounts_count.value = await frappe.xcall("frappe.client.get_count", {
			doctype: "Chart of Account",
			filters: { entreprise: doc.value.name },
		});
	} catch {
		// the server message is already surfaced by frappe.call
	}
}

function remove_document(index) {
	if (doc.value?.documents) {
		doc.value.documents.splice(index, 1);
	}
}

function open_file(url) {
	if (url) {
		window.open(url, "_blank", "noopener");
	}
}

// ── Validation preview section (Part 3) ───────────────────────────────────────
const LAYOUT_FIELDTYPES = new Set([
	"Section Break",
	"Column Break",
	"Tab Break",
	"HTML",
	"Button",
	"Fold",
	"Heading",
]);

function is_value_empty(val) {
	if (val === undefined || val === null) return true;
	if (typeof val === "string" && val.trim() === "") return true;
	if (Array.isArray(val) && val.length === 0) return true;
	return false;
}

const missing_required_fields = computed(() => {
	if (!doc.value || !meta.meta.value?.fields) return [];
	const d = doc.value;
	return meta.meta.value.fields.filter((field) => {
		if (!field.reqd || LAYOUT_FIELDTYPES.has(field.fieldtype) || field.hidden) {
			return false;
		}
		return is_value_empty(d[field.fieldname]);
	});
});

const missing_count_label = computed(() => {
	const count = missing_required_fields.value.length;
	return count === 1
		? __("1 champ obligatoire manquant")
		: __("{0} champs obligatoires manquants", [count]);
});

const forme_juridique_title = computed(() => {
	const f = doc.value?.forme_juridique;
	if (!f) return null;
	return linkTitles.value[`Forme Juridique::${f}`] || f;
});

const activite_display = computed(() => {
	const code = doc.value?.activite;
	if (!code) return null;
	const title = linkTitles.value[`Activite::${code}`];
	return title && title !== code ? `${code} — ${title}` : code;
});

const convention_display = computed(() => {
	const code = doc.value?.convention;
	if (!code) return null;
	const title = linkTitles.value[`Convention Collective::${code}`];
	return title && title !== code ? `${code} — ${title}` : code;
});

const convention_summary = computed(() => {
	const c = convention_details.value;
	if (!c) return null;
	const parts = [];
	if (c.nombre_jours !== undefined && c.nombre_jours !== null) {
		parts.push(`${c.nombre_jours} jours`);
	}
	if (c.nombre_heures !== undefined && c.nombre_heures !== null) {
		parts.push(`${c.nombre_heures} heures`);
	}
	if (c.droit_conge !== undefined && c.droit_conge !== null) {
		parts.push(`${c.droit_conge} congé`);
	}
	return parts.length ? parts.join(" · ") : null;
});

const adresse_display = computed(() => {
	const d = doc.value;
	if (!d) return null;
	const street = [d.numero, d.rue]
		.filter((v) => v !== undefined && v !== null && String(v).trim() !== "")
		.join(" ");
	const city = [d.code_postal, d.ville]
		.filter((v) => v !== undefined && v !== null && String(v).trim() !== "")
		.join(" ");
	const country_title = d.pays_adresse
		? linkTitles.value[`Country::${d.pays_adresse}`] || d.pays_adresse
		: "";
	const parts = [street, city, country_title].filter((p) => p && p.trim() !== "");
	return parts.length ? parts.join(", ") : null;
});

const pays_comptabilite_title = computed(() => {
	const p = doc.value?.pays;
	if (!p) return null;
	return linkTitles.value[`Country::${p}`] || p;
});

const devise_title = computed(() => {
	const d = doc.value?.devise;
	if (!d) return null;
	return linkTitles.value[`Currency::${d}`] || d;
});

const date_arrete_display = computed(() => {
	const j = doc.value?.jour_arrete;
	const m = doc.value?.mois_arrete;
	if (j === undefined || j === null || j === "" || m === undefined || m === null || m === "") {
		return null;
	}
	const jour = String(j).padStart(2, "0");
	const mois = String(m).padStart(2, "0");
	return `${jour}/${mois}`;
});

const plan_comptable_main_preview = computed(() => {
	const file = doc.value?.plan_comptable_fichier;
	if (!file) return null;
	const filename = get_filename(file);
	const date = doc.value?.plan_comptable_ajoute_le
		? format_datetime_dmy(doc.value.plan_comptable_ajoute_le)
		: "";
	return date ? `${filename} · ${date}` : filename;
});

const preview_identification = computed(() => [
	{ label: __("Code"), value: doc.value?.code, reqd: true },
	{ label: __("Raison sociale"), value: doc.value?.raison_sociale, reqd: true },
	{ label: __("Matricule fiscal"), value: doc.value?.matricule_fiscal, reqd: true },
	{ label: __("Forme juridique"), value: forme_juridique_title.value, reqd: true },
	{ label: __("Activité"), value: activite_display.value, reqd: true },
	{
		label: __("Convention"),
		value: convention_display.value,
		subtitle: convention_summary.value,
		reqd: true,
	},
	{
		label: __("Personne physique"),
		value: doc.value?.personne_physique ? __("Oui") : __("Non"),
		reqd: false,
	},
	{
		label: __("Date de création"),
		value: format_date_dmy(doc.value?.date_creation),
		reqd: true,
	},
	{ label: __("Numéro RNE"), value: doc.value?.numero_rne, reqd: true },
	{ label: __("Numéro dossier"), value: doc.value?.numero_dossier, reqd: false },
	{ label: __("Code exploitation CNSS RG"), value: doc.value?.code_exploitation, reqd: true },
	{
		label: __("Code exploitation AV-CNSS"),
		value: doc.value?.code_exploitation_karama,
		reqd: false,
	},
	{ label: __("Adresse"), value: adresse_display.value, reqd: true },
	{ label: __("Pays comptabilité"), value: pays_comptabilite_title.value, reqd: true },
]);

const preview_financier = computed(() => [
	{
		label: __("Capital social"),
		value: format_number_fr(doc.value?.capital_social),
		reqd: false,
	},
	{
		label: __("Nb actions/parts"),
		value: format_number_fr(doc.value?.nombre_actions_parts_sociales),
		reqd: false,
	},
	{
		label: __("Valeur nominale"),
		value: format_number_fr(doc.value?.valeur_nominale_action),
		reqd: false,
	},
	{ label: __("Devise"), value: devise_title.value, reqd: true },
	{
		label: __("Taux imposition (%)"),
		value:
			doc.value?.taux_imposition !== undefined &&
			doc.value?.taux_imposition !== null &&
			doc.value?.taux_imposition !== ""
				? `${doc.value.taux_imposition} %`
				: null,
		reqd: true,
	},
	{
		label: __("Durée exercice (mois)"),
		value:
			doc.value?.duree_exercice !== undefined &&
			doc.value?.duree_exercice !== null &&
			doc.value?.duree_exercice !== ""
				? `${doc.value.duree_exercice} mois`
				: null,
		reqd: true,
	},
	{ label: __("Date d'arrêté"), value: date_arrete_display.value, reqd: true },
	{ label: __("Code douane"), value: doc.value?.code_douane, reqd: false },
	{ label: __("N. CNSS"), value: doc.value?.numero_cnss, reqd: true },
	{ label: __("Type plan comptable"), value: doc.value?.type_plan_comptable, reqd: false },
	{ label: __("Modèle bilan"), value: doc.value?.modele_bilan, reqd: true },
	{ label: __("Modèle état de résultat"), value: doc.value?.modele_etat_resultat, reqd: true },
	{
		label: __("Longueur compte comptable"),
		value: doc.value?.longueur_compte_comptable,
		reqd: false,
	},
	{
		label: __("Flux trésorerie autorisé"),
		value: doc.value?.modele_flux_tresorerie_autorise ? __("Oui") : __("Non"),
		reqd: false,
	},
]);

const plan_comptable_preview_value = computed(() => {
	const count = plan_accounts_count.value || 0;
	return count === 1 ? __("1 compte importé") : __("{0} comptes importés", [count]);
});

const preview_plan_comptable = computed(() => [
	{
		label: __("Plan comptable"),
		value: plan_comptable_preview_value.value,
		subtitle: doc.value?.plan_comptable_ajoute_le
			? __("Ajouté le {0}", [format_datetime_dmy(doc.value.plan_comptable_ajoute_le)])
			: null,
		reqd: false,
		onClick: plan_accounts_count.value > 0 ? open_plan_comptable : null,
		linkLabel: __("Ouvrir le plan comptable"),
	},
]);

const valider_disabled = computed(() => {
	return Boolean(is_new.value || missing_required_fields.value.length > 0 || is_validated.value);
});

const valider_tooltip = computed(() => {
	if (is_new.value) {
		return __("Veuillez d'abord enregistrer l'entreprise avant de la valider.");
	}
	if (missing_required_fields.value.length > 0) {
		return __("Des champs obligatoires sont manquants.");
	}
	if (is_validated.value) {
		return __("Entreprise déjà validée.");
	}
	return __("Valider l'entreprise");
});

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
					<!-- Stacked white cards: 1. Informations Générales  2. Informations Financières  3. Plan comptable  4. Validation -->
					<div class="flex flex-col gap-6 entreprise-form">
						<!-- ══ Card 1: Informations Générales ══ -->
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

						<!-- ══ Card 2: Informations Financières ══ -->
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

						<!-- ══ Card 3: Plan comptable ══ -->
						<div class="rounded-lg border border-surface-gray-2 bg-surface-white p-6 shadow-xs space-y-6">
							<div class="text-base font-bold text-ink-gray-9">
								{{ __("Plan comptable") }}
							</div>
							<div class="border-b border-surface-gray-2" />

							<!-- Block A: Plan comptable principal -->
							<div class="space-y-3">
								<div class="text-xs font-semibold uppercase tracking-wider text-ink-gray-5">
									{{ __("Plan comptable principal") }}
								</div>

								<!-- File tile when file is set -->
								<div
									v-if="doc.plan_comptable_fichier"
									class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-lg border border-surface-gray-2 bg-surface-gray-1/60 p-4"
								>
									<div class="flex items-center gap-3 min-w-0">
										<div class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-surface-white border border-surface-gray-2 text-ink-gray-6">
											<svg class="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
												<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
												<polyline points="14 2 14 8 20 8" />
											</svg>
										</div>
										<div class="min-w-0">
											<div class="truncate text-p-sm font-semibold text-ink-gray-9">
												{{ get_filename(doc.plan_comptable_fichier) }}
											</div>
											<div v-if="doc.plan_comptable_ajoute_le" class="text-xs text-ink-gray-5">
												{{ __("Ajouté le {0}", [format_datetime_dmy(doc.plan_comptable_ajoute_le)]) }}
											</div>
										</div>
									</div>

									<div class="flex flex-wrap items-center gap-2 shrink-0">
										<Button
											variant="ghost"
											:label="__('Afficher')"
											@click="open_file(doc.plan_comptable_fichier)"
										/>
										<div :title="plan_import_disabled ? plan_import_hint : undefined" class="inline-flex">
											<Button
												variant="subtle"
												:label="__('Importer un plan comptable')"
												:disabled="plan_import_disabled"
												@click="plan_import_open = true"
											/>
										</div>
										<Button
											v-if="plan_accounts_count > 0"
											variant="subtle"
											:label="__('Ouvrir le plan comptable')"
											@click="open_plan_comptable"
										/>
									</div>
								</div>

								<!-- Empty state when no file -->
								<div
									v-else
									class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-lg border border-dashed border-surface-gray-3 bg-surface-gray-1/40 p-5"
								>
									<div class="flex items-center gap-3">
										<div class="flex size-10 shrink-0 items-center justify-center rounded-lg bg-surface-gray-2 text-ink-gray-4">
											<svg class="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75">
												<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
												<polyline points="14 2 14 8 20 8" />
											</svg>
										</div>
										<div>
											<div class="text-p-sm font-medium text-ink-gray-7">
												{{ __("Aucun plan comptable principal") }}
											</div>
											<div class="text-xs text-ink-gray-5">
												{{ __("Rattachez un fichier de plan comptable (fichier Excel .xlsx)") }}
											</div>
										</div>
									</div>

									<div :title="plan_import_disabled ? plan_import_hint : undefined" class="inline-flex">
										<Button
											variant="subtle"
											:label="__('Importer un plan comptable')"
											:disabled="plan_import_disabled"
											@click="plan_import_open = true"
										/>
									</div>
								</div>
							</div>

							
						</div>

						<!-- ══ Card 4: Validation ══ -->
						<div class="rounded-lg border border-surface-gray-2 bg-surface-white p-6 shadow-xs space-y-6">
							<div class="text-base font-bold text-ink-gray-9">
								{{ __("Validation") }}
							</div>
							<div class="border-b border-surface-gray-2" />

							<!-- Top banner -->
							<div
								v-if="missing_required_fields.length > 0"
								class="rounded-lg border border-surface-amber-3 bg-surface-amber-1 p-4 text-p-sm"
							>
								<div class="flex items-center gap-2 font-semibold text-ink-amber-8">
									<svg class="size-5 shrink-0 text-ink-amber-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
										<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
										<line x1="12" y1="9" x2="12" y2="13" />
										<line x1="12" y1="17" x2="12.01" y2="17" />
									</svg>
									<span>{{ missing_count_label }}</span>
								</div>
								<div class="mt-3 flex flex-wrap gap-1.5">
									<span
										v-for="field in missing_required_fields"
										:key="field.fieldname"
										class="inline-flex items-center rounded bg-surface-amber-2 px-2.5 py-1 text-xs font-medium text-ink-amber-9 border border-surface-amber-3"
									>
										{{ field.label || field.fieldname }}
									</span>
								</div>
							</div>

							<div
								v-else
								class="flex items-center gap-2.5 rounded-lg border border-surface-green-3 bg-surface-green-1 px-4 py-3 text-p-sm font-semibold text-ink-green-8"
							>
								<svg class="size-5 shrink-0 text-ink-green-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
									<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
									<polyline points="22 4 12 14.01 9 11.01" />
								</svg>
								<span>{{ __("Prêt à valider") }}</span>
							</div>

							<!-- 3 Preview cards -->
							<div class="flex flex-col gap-6">
								<!-- Preview Card A: Identification -->
								<div class="rounded-lg border border-surface-gray-2 bg-surface-gray-1/30 p-5">
									<div class="mb-4 text-xs font-semibold uppercase tracking-wider text-ink-gray-5">
										{{ __("Identification") }}
									</div>
									<div class="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3.5">
										<div
											v-for="item in preview_identification"
											:key="item.label"
											class="flex flex-col gap-0.5 min-w-0"
										>
											<span class="text-xs font-medium text-ink-gray-5 truncate">
												{{ item.label }}
											</span>
											<div class="flex items-center gap-2 text-p-sm font-semibold text-ink-gray-9">
												<template v-if="item.value !== null && item.value !== undefined && item.value !== ''">
													<div class="min-w-0">
														<div class="truncate">{{ item.value }}</div>
														<div v-if="item.subtitle" class="text-xs font-normal text-ink-gray-5">
															{{ item.subtitle }}
														</div>
													</div>
												</template>
												<template v-else>
													<span class="text-ink-gray-4 font-normal">—</span>
													<span
														v-if="item.reqd"
														class="inline-flex items-center rounded bg-surface-red-2 px-1.5 py-0.5 text-[11px] font-medium text-ink-red-6"
													>
														{{ __("Manquant") }}
													</span>
												</template>
											</div>
										</div>
									</div>
								</div>

								<!-- Preview Card B: Informations financières -->
								<div class="rounded-lg border border-surface-gray-2 bg-surface-gray-1/30 p-5">
									<div class="mb-4 text-xs font-semibold uppercase tracking-wider text-ink-gray-5">
										{{ __("Informations financières") }}
									</div>
									<div class="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3.5">
										<div
											v-for="item in preview_financier"
											:key="item.label"
											class="flex flex-col gap-0.5 min-w-0"
										>
											<span class="text-xs font-medium text-ink-gray-5 truncate">
												{{ item.label }}
											</span>
											<div class="flex items-center gap-2 text-p-sm font-semibold text-ink-gray-9">
												<template v-if="item.value !== null && item.value !== undefined && item.value !== ''">
													<div class="min-w-0">
														<div class="truncate">{{ item.value }}</div>
													</div>
												</template>
												<template v-else>
													<span class="text-ink-gray-4 font-normal">—</span>
													<span
														v-if="item.reqd"
														class="inline-flex items-center rounded bg-surface-red-2 px-1.5 py-0.5 text-[11px] font-medium text-ink-red-6"
													>
														{{ __("Manquant") }}
													</span>
												</template>
											</div>
										</div>
									</div>
								</div>

								<!-- Preview Card C: Plan comptable -->
								<div class="rounded-lg border border-surface-gray-2 bg-surface-gray-1/30 p-5">
									<div class="mb-4 text-xs font-semibold uppercase tracking-wider text-ink-gray-5">
										{{ __("Plan comptable") }}
									</div>
									<div class="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-3.5">
										<div
											v-for="item in preview_plan_comptable"
											:key="item.label"
											class="flex flex-col gap-0.5 min-w-0"
										>
											<span class="text-xs font-medium text-ink-gray-5 truncate">
												{{ item.label }}
											</span>
											<div class="flex items-center gap-2 text-p-sm font-semibold text-ink-gray-9">
												<template v-if="item.value !== null && item.value !== undefined && item.value !== ''">
													<div class="min-w-0">
														<div class="truncate">{{ item.value }}</div>
														<div v-if="item.subtitle" class="text-xs font-normal text-ink-gray-5">
															{{ item.subtitle }}
														</div>
														<button
															v-if="item.onClick"
															type="button"
															class="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-ink-gray-7 underline decoration-surface-gray-3 underline-offset-2 hover:text-ink-gray-9"
															@click.stop="item.onClick"
														>
															{{ item.linkLabel }}
														</button>
													</div>
												</template>
												<template v-else>
													<span class="text-ink-gray-4 font-normal">—</span>
													<span
														v-if="item.reqd"
														class="inline-flex items-center rounded bg-surface-red-2 px-1.5 py-0.5 text-[11px] font-medium text-ink-red-6"
													>
														{{ __("Manquant") }}
													</span>
												</template>
											</div>
										</div>
									</div>
								</div>
							</div>

							<!-- Bottom action bar -->
							<div class="pt-4 border-t border-surface-gray-2 flex items-center justify-end gap-3">
								<Button
									variant="outline"
									:label="__('Enregistrer')"
									:loading="saving"
									@click="save"
								/>
								<div :title="valider_disabled ? valider_tooltip : undefined" class="inline-flex">
									<Button
										variant="solid"
										:label="__('Valider l\'entreprise')"
										:loading="validating"
										:disabled="valider_disabled"
										:tooltip="valider_tooltip"
										@click="valider"
									/>
								</div>
							</div>
						</div>
					</div>
				</template>
			</div>
		</div>

		<PlanComptableImportDialog
			v-model:open="plan_import_open"
			:entreprise="doc?.name || ''"
			@imported="on_plan_imported"
		/>
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