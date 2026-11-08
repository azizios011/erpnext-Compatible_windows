// Entreprise form: the 4-tab layout mirrors Axeane's wizard. Tab 4 renders
// the recap cards (validation_html), tab 3 hosts the plan comptable attach
// and the multi-document uploader; Valider runs the whitelisted
// valider_entreprise after saving unsaved changes.
frappe.ui.form.on("Entreprise", {
	refresh(frm) {
		frm.toggle_display("status", false); // shown as the page indicator instead
		render_status_indicator(frm);
		render_validation_cards(frm);
		bind_valider_button(frm);
		bind_document_uploader(frm);
	},
	personne_physique(frm) {
		// mirrors the controller default, so the recap shows it immediately
		if (frm.doc.personne_physique && !frm.doc.type_plan_comptable) {
			frm.set_value("type_plan_comptable", "Personne Physique");
		}
		render_validation_cards(frm);
	},
});

const WATCHED_FIELDS = [
	"pays", "code", "raison_sociale", "matricule_fiscal", "activite", "date_creation",
	"forme_juridique", "personne_physique", "code_exploitation", "code_exploitation_karama",
	"convention", "affectation_compte_tiers", "numero_rne", "numero_dossier", "numero",
	"rue", "code_postal", "ville", "pays_adresse", "capital_social",
	"nombre_actions_parts_sociales", "valeur_nominale_action", "devise", "taux_imposition",
	"duree_exercice", "jour_arrete", "mois_arrete", "code_douane", "numero_cnss",
];

WATCHED_FIELDS.forEach((fieldname) => {
	frappe.ui.form.on("Entreprise", { [fieldname]: (frm) => render_validation_cards(frm) });
});

frappe.ui.form.on("Entreprise Document", {
	documents_add(frm) {
		render_validation_cards(frm);
	},
	documents_remove(frm) {
		render_validation_cards(frm);
	},
});

function render_status_indicator(frm) {
	if (frm.doc.status === "Creee") {
		frm.page.set_indicator(__("Creee"), "green");
	} else {
		frm.page.set_indicator(__("En creation"), "orange");
	}
}

function bind_valider_button(frm) {
	if (frm.doc.status !== "En creation" || frm.is_new()) {
		return;
	}
	frm.add_custom_button(__("Valider l'entreprise"), () => {
		if (frm.is_dirty()) {
			frappe.confirm(
				__("Des modifications ne sont pas enregistrees. Les enregistrer maintenant ?"),
				() =>
					frm.save("Save", () => {
						valider(frm);
					})
			);
			return;
		}
		valider(frm);
	});
}

function valider(frm) {
	frappe.call({
		method: "erpnext.custom_modules.organization.doctype.entreprise.entreprise.valider_entreprise",
		args: { name: frm.doc.name },
		freeze: true,
		callback() {
			frm.reload_doc();
			frappe.show_alert({ message: __("Entreprise validee."), indicator: "green" });
		},
	});
}

function bind_document_uploader(frm) {
	const button = frm.fields_dict.btn_ajouter_documents;
	if (!button || !button.$input || button.$input.__axeane_uploader_bound) {
		return;
	}
	button.$input.__axeane_uploader_bound = true;
	button.$input.on("click", () => {
		new frappe.ui.FileUploader({
			allow_multiple: true,
			make_attachments_public: false,
			restrictions: { allowed_file_types: [] }, // any file type on this uploader
			dialog_title: __("Ajouter plusieurs documents"),
			on_success(file_doc) {
				add_document_row(frm, file_doc);
			},
		});
	});
}

function add_document_row(frm, file_doc) {
	const file_name = file_doc.file_name || "";
	const extension = file_name.split(".").pop().toLowerCase();
	const is_plan =
		file_name.toLowerCase().includes("plan") && ["xlsx", "xls", "pdf"].includes(extension);
	const row = frm.add_child("documents");
	row.fichier = file_doc.file_url;
	row.libelle = file_name.replace(/\.[^.]+$/, "");
	row.type_document = is_plan ? "Plan comptable" : "Autre";
	row.ajoute_par = frappe.session.user;
	row.date_ajout = frappe.datetime.get_today();
	frm.refresh_field("documents");
	render_validation_cards(frm);
}

function render_validation_cards(frm) {
	const field = frm.fields_dict.validation_html;
	if (!field || !field.$wrapper) {
		return;
	}
	const doc = frm.doc;
	const card = (title, rows) => `
		<div class="axeane-card" style="flex: 1; min-width: 320px; border: 1px solid var(--border-color);
			border-radius: 8px; padding: 10px 14px; margin-bottom: 10px;">
			<div style="color: var(--warning-text, #e36414); font-weight: 700; margin-bottom: 6px;">${title}</div>
			${rows
				.map(
					([label, value]) => `
				<div style="display: flex; justify-content: space-between; gap: 12px; padding: 2px 0; font-size: 12px;">
					<span class="text-muted">${label}</span>
					<span style="font-weight: 700; text-align: right;">${value || "—"}</span>
				</div>`
				)
				.join("")}
		</div>`;

	const link_value = (doctype, name) =>
		name
			? `<span class="tu-link-title" data-doctype="${esc(doctype)}" data-name="${esc(name)}">${esc(name)}</span>`
			: "";
	// hydrate the link titles from each doctype's title field after render
	setTimeout(() => {
		field.$wrapper.find(".tu-link-title").each(function () {
			const $el = $(this);
			const link_doctype = $el.data("doctype");
			const link_name = $el.data("name");
			const title_field = frappe.get_meta(link_doctype).title_field || "name";
			frappe.db.get_value(link_doctype, link_name, title_field).then((r) => {
				const title = r.message && r.message[title_field];
				if (title) {
					$el.text(title);
				}
			});
		});
	}, 0);

	const adresse = [doc.numero, doc.rue, doc.code_postal, doc.ville, doc.pays_adresse]
		.filter((part) => part)
		.join(", ");

	const general_rows = [
		[__("Code"), esc(doc.code)],
		[__("Activite"), link_value("Activite", doc.activite)],
		[__("Adresse"), esc(adresse)],
		[__("Code exploitation CNSS RG"), esc(doc.code_exploitation)],
		[__("Code exploitation AV-CNSS"), esc(doc.code_exploitation_karama)],
		[__("Numero dossier"), esc(doc.numero_dossier)],
		[__("Convention"), link_value("Convention Collective", doc.convention)],
	];

	const financier_rows = [
		[__("Raison sociale"), esc(doc.raison_sociale)],
		[__("Matricule fiscal"), esc(doc.matricule_fiscal)],
		[__("Personne physique"), doc.personne_physique ? __("Oui") : __("Non")],
		[__("Date de creation"), doc.date_creation ? frappe.datetime.str_to_user(doc.date_creation) : ""],
		[__("Forme juridique"), link_value("Forme Juridique", doc.forme_juridique)],
	];

	const financier_rows_2 = [
		[__("Capital social"), doc.capital_social ? fmt_money_3(doc.capital_social) : ""],
		[__("Nb actions/parts sociales"), doc.nombre_actions_parts_sociales || ""],
		[__("Valeur nominale"), doc.valeur_nominale_action ? fmt_money_3(doc.valeur_nominale_action) : ""],
		[__("Devise"), esc(doc.devise)],
	];

	const financier_rows_3 = [
		[__("Taux imposition"), doc.taux_imposition ? `${fmt_money_3(doc.taux_imposition)} %` : ""],
		[__("Duree exercice"), doc.duree_exercice ? `${doc.duree_exercice} ${__("mois")}` : ""],
		[
			__("Date arrete"),
			doc.jour_arrete && doc.mois_arrete
				? `${String(doc.jour_arrete).padStart(2, "0")}/${String(doc.mois_arrete).padStart(2, "0")}`
				: "",
		],
		[__("Code douane"), esc(doc.code_douane)],
		[__("N° CNSS"), esc(doc.numero_cnss)],
	];

	const plan_comptable = doc.plan_comptable_fichier
		? esc((doc.plan_comptable_fichier || "").split("/").pop())
		: `<span class="indicator-pill orange">${__("Plan comptable : non fourni")}</span>`;
	const document_count = (doc.documents || []).length;

	field.$wrapper.html(`
		<style>
			.axeane-cards { display: flex; flex-wrap: wrap; gap: 12px; }
		</style>
		<div class="axeane-validation" style="display: flex; flex-direction: column; gap: 4px;">
			<div class="axeane-cards">${card(__("Informations Generales"), general_rows)}
			${card(__("Informations Financieres"), financier_rows)}</div>
			<div class="axeane-cards">${card(__("Informations Financieres (suite)"), financier_rows_2)}
			${card(__("Informations Financieres (suite 2)"), financier_rows_3)}</div>
			<div class="axeane-cards">${card(
				__("Documents"),
				[
					[__("Plan comptable"), plan_comptable],
					[__("Documents joints"), `${document_count}`],
				]
			)}</div>
		</div>
	`);

	// the Valider button rides the tab header area while the entreprise is
	// still being created
	const $btn = field.$wrapper.find(".axeane-cards");
	if (doc.status === "En creation" && !frm.is_new()) {
		$btn.append(
			`<div style="margin-top: 6px;"><button class="btn btn-primary btn-sm tu-valider">${__(
				"Valider l'entreprise"
			)}</button></div>`
		);
		field.$wrapper.find(".tu-valider").on("click", () => {
			if (frm.is_dirty()) {
				frappe.confirm(
					__("Des modifications ne sont pas enregistrees. Les enregistrer maintenant ?"),
					() => frm.save("Save", () => valider(frm))
				);
				return;
			}
			valider(frm);
		});
	}
}

function fmt_money_3(value) {
	return frappe.format(flt(value), "Currency", { precision: 3 });
}

function esc(value) {
	return frappe.utils.escape_html(value === null || value === undefined ? "" : String(value));
}
