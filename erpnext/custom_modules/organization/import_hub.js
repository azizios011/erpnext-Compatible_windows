// The import hub dialog (Organization workspace — Import Configuration):
// one shared flow for Entreprise and the Master data doctypes. Attach an
// xlsx, "Telecharger le modele" for the configured headers, Valider shows
// the per-row errors from the dry run, and Importer (only enabled once the
// validation is clean) upserts through the generic engine
// (organization.importing). Loaded via hooks doctype_list_js / doctype_js
// for the doctypes that carry an Importer button.

frappe.provide("erpnext.import_hub");

const IMPORT_HUB_API = "erpnext.custom_modules.organization.importing.";

erpnext.import_hub.open_dialog = function (target, opts) {
	opts = opts || {};
	const esc = frappe.utils.escape_html;
	const doctype = opts.doctype || target;

	const d = new frappe.ui.Dialog({
		title: __("Importer {0}", [__(target)]),
		size: "large",
		fields: [
			{
				fieldname: "file",
				fieldtype: "Attach",
				label: __("Fichier xlsx"),
				reqd: 1,
				description: __("Un classeur .xlsx conforme a l'Import Configuration du {0}.", [__(target)]),
			},
			{ fieldname: "template_btn", fieldtype: "Button", label: __("Telecharger le modele") },
			{ fieldname: "preview", fieldtype: "HTML", options: "" },
		],
		primary_action_label: __("Valider"),
		primary_action: null,
	});

	// the generated xlsx model (the configuration's headers)
	d.fields_dict.template_btn.$input.on("click", () => {
		frappe.call({
			method: IMPORT_HUB_API + "template",
			args: { target: target },
			callback(r) {
				if (r.message && r.message.file_url) {
					window.open(r.message.file_url, "_blank");
				}
			},
		});
	});

	const $preview = () => d.fields_dict.preview.$wrapper;

	function render_errors(errors, error_count) {
		const rows = errors
			.map(
				(error) => `<tr><td style="padding: 2px 8px; white-space: nowrap;">${esc(error)}</td></tr>`
			)
			.join("");
		$preview().html(
			`<div class="alert alert-danger" style="margin-top: 8px;">
				<b>${__("{0} ligne(s) invalide(s).", [error_count])}</b>
				${error_count > errors.length ? `<div class="text-muted">${__("Premieres {0} seules affichees.", [errors.length])}</div>` : ""}
				<table class="table table-sm" style="margin-top: 6px;">${rows}</table>
			</div>`
		);
	}

	function render_preview(message) {
		const counts = `${__("Lignes valides: {0}", [message.row_count])}`;
		const header = `<b>${__("Validation OK")} — ${esc(counts)}</b>
			<div class="text-muted" style="font-size: 12px;">${__(
				"Cliquer Importer pour ecrire ces {0} ligne(s) dans {1}.",
				[message.row_count, __(message.doctype)]
			)}</div>`;
		const preview_rows = (message.preview || [])
			.map(
				(row) =>
					`<tr>${(message.columns || [])
						.map((column) => `<td style="padding: 2px 6px;">${esc(row[column] || "")}</td>`)
						.join("")}</tr>`
			)
			.join("");
		$preview().html(
			`<div class="alert alert-success" style="margin-top: 8px;">${header}</div>
			${
				preview_rows
					? `<div style="overflow-x: auto;"><table class="table table-sm table-bordered" style="font-size: 12px;">
						<thead><tr>${(message.columns || [])
							.map((column) => `<th style="padding: 2px 6px;">${esc(__(column))}</th>`)
							.join("")}</tr></thead>
						<tbody>${preview_rows}</tbody>
					</table></div>`
					: ""
			}`
		);
	}

	function run_import(file_url) {
		frappe.call({
			method: IMPORT_HUB_API + "import_records",
			args: { file_url: file_url, target: target },
			freeze: true,
			freeze_message: __("Import en cours..."),
			callback(r) {
				d.hide();
				const result = r.message || {};
				const summary = [
					__("{0} cree(s)", [result.inserted || 0]),
					__("{0} mis a jour", [result.updated || 0]),
					__("{0} ignore(s)", [result.skipped || 0]),
				].join(" · ");
				frappe.msgprint({
					title: __("Import {0}", [__(target)]),
					message: __("Import termine: {0}.", [summary]),
					indicator: "green",
				});
				if (opts.on_import) opts.on_import();
			},
		});
	}

	function validate(file_url) {
		frappe.call({
			method: IMPORT_HUB_API + "validate",
			args: { file_url: file_url, target: target },
			freeze: true,
			freeze_message: __("Validation du fichier..."),
			callback(r) {
				const message = r.message || {};
				if (message.error_count) {
					render_errors(message.errors || [], message.error_count);
					// back to Valider: fix the file, re-validate
					d.set_primary_action(__("Valider"), () => check_and_validate());
					return;
				}
				render_preview(message);
				d.set_primary_action(__("Importer"), () => run_import(file_url));
			},
		});
	}

	function check_and_validate() {
		const file_url = d.get_value("file");
		if (!file_url) {
			frappe.msgprint({ message: __("Joignez d'abord un fichier .xlsx."), indicator: "orange" });
			return;
		}
		validate(file_url);
	}

	d.set_primary_action(__("Valider"), () => check_and_validate());
	d.show();
};
