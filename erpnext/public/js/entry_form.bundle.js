// Shared client helpers for the four Entries documents ("Saisie des
// ecritures"). Loaded through app_include_js so it is always available
// before the per-doctype scripts; exposes erpnext.entries.*. The Axeane
// screen: header (date operation, journal, mois, devise, mvt, jour,
// ref/libelle), the lines grid, the footer totals and the side attachment
// preview. Nothing here auto-saves a document.
frappe.provide("erpnext.entries");

// live totals while the shared Ecriture Ligne grid is edited
frappe.ui.form.on("Ecriture Ligne", {
	debit(frm) {
		erpnext.entries.update_totals(frm);
	},
	credit(frm) {
		erpnext.entries.update_totals(frm);
	},
	lines_remove(frm) {
		erpnext.entries.update_totals(frm);
	},
});

Object.assign(erpnext.entries, {
	update_totals(frm) {
		let total_debit = 0;
		let total_credit = 0;
		(frm.doc.lines || []).forEach((line) => {
			total_debit += flt(line.debit);
			total_credit += flt(line.credit);
		});
		frm.set_value("total_debit", total_debit);
		frm.set_value("total_credit", total_credit);
		frm.set_value("solde", total_debit - total_credit);
		erpnext.entries.render_totaux_cards(frm);
	},

	/** The Axeane footer: four cards sticky at the bottom of the form. */
	render_totaux_cards(frm) {
		const field = frm.fields_dict.totaux_html;
		if (!field || !field.$wrapper) {
			return;
		}
		const currency = frm.doc.devise || "";
		const lines = (frm.doc.lines || []).filter((line) => line.account || flt(line.debit) || flt(line.credit)).length;
		const fmt = (value) =>
			frappe.format(flt(value), "Currency", { currency: currency, precision: 3 }, frm.doc);
		if (!frappe._totaux_css) {
			frappe._totaux_css = true;
			$(`<style>
				.totaux-cards { position: sticky; bottom: 0; z-index: 5; background: var(--card-bg, #fff);
					border-top: 1px solid var(--border-color); padding: 8px 4px; display: flex; gap: 12px; }
				.totaux-card { flex: 1; border: 1px solid var(--border-color); border-radius: 6px;
					padding: 6px 10px; }
				.totaux-card .totaux-label { font-size: 11px; color: var(--text-muted, #666); }
				.totaux-card .totaux-value { font-size: 14px; font-weight: 700; }
				.totaux-card.tot-debit .totaux-value { color: var(--text-on-green, #1a7f37); }
				.totaux-card.tot-credit .totaux-value { color: var(--text-on-red, #c0392b); }
				.totaux-card.tot-solde .totaux-value { color: var(--text-on-purple, #6f42c1); }
			</style>`).appendTo("head");
		}
		const card = (label, value, css_class) =>
			`<div class="totaux-card ${css_class}"><div class="totaux-label">${label}</div>
				<div class="totaux-value">${fmt(value)}</div></div>`;
		field.$wrapper.html(
			`<div class="totaux-cards">` +
				card(__("Mvt Compte"), lines, "mvt-compte") +
				card(__("Tot Debit"), total_debit, "tot-debit") +
				card(__("Tot Credit"), total_credit, "tot-credit") +
				card(__("Solde"), total_debit - total_credit, "tot-solde") +
				`</div>`
		);
	},

	/** The list view's Totaux bar: aggregates over the currently filtered
	 * rows (server-side, through get_list_totaux). */
	list_totaux(listview) {
		const args = listview.get_args ? listview.get_args() : {};
		frappe.call({
			method: "erpnext.custom_modules.entries.api.get_list_totaux",
			args: {
				doctype: listview.doctype,
				filters: JSON.stringify(args.filters || []),
				or_filters: JSON.stringify(args.or_filters || []),
			},
			callback(r) {
				const totals = r.message || {};
				let $bar = listview.$result.parent().find(".tu-list-totaux");
				if (!$bar.length) {
					$bar = $('<div class="totaux-cards tu-list-totaux" style="border-top: 1px solid var(--border-color); padding: 8px 4px; display: flex; gap: 12px;"></div>');
					listview.$paging_area.before($bar);
				}
				const fmt = (value) => frappe.format(flt(value), "Currency", { currency: "", precision: 3 });
				const card = (label, value, css_class) =>
					`<div class="totaux-card ${css_class}" style="flex:1; border:1px solid var(--border-color); border-radius:6px; padding:4px 10px;">
						<div class="totaux-label" style="font-size:11px; color:#666;">${label}</div>
						<div class="totaux-value" style="font-size:14px; font-weight:700;">${fmt(value)}</div></div>`;
				$bar.html(
					card(__("Mvt Compte"), totals.count || 0, "mvt-compte") +
						card(__("Tot Debit"), totals.total_debit || 0, "tot-debit") +
						card(__("Tot Credit"), totals.total_credit || 0, "tot-credit") +
						card(__("Solde"), totals.solde || 0, "tot-solde")
				);
			},
		});
	},

	derive_period(frm) {
		if (!frm.doc.date_operation) {
			return;
		}
		const date = frappe.datetime.str_to_obj(frm.doc.date_operation);
		if (!date) {
			return;
		}
		frm.set_value("mois", String(date.getMonth() + 1).padStart(2, "0"));
		frm.set_value("jour", date.getDate());
	},

	apply_libelle(frm) {
		if (!frm.doc.apply_libelle_to_lines || !frm.doc.libelle) {
			return;
		}
		(frm.doc.lines || []).forEach((line) => {
			line.libelle = frm.doc.libelle;
		});
		frm.refresh_field("lines");
	},

	setup_tresorerie_query(frm) {
		// the Tresorerie dropdown only offers treasury accounts (Bank / Cash)
		frm.set_query("tresorerie", "lines", () => ({
			filters: { account_type: ["in", ["Bank", "Cash"]] },
		}));
		frm.set_query("account", "lines", () => ({
			filters: { disabled: 0 },
		}));
	},

	preview_source_attachment(frm) {
		const field = frm.fields_dict.attachment_preview;
		if (!field) {
			return;
		}
		if (!frm.doc.source_doctype || !frm.doc.source_name) {
			field.$wrapper.empty();
			return;
		}
		frappe.db
			.get_value(frm.doc.source_doctype, frm.doc.source_name, "attachment")
			.then((r) => {
				const url = r.message && r.message.attachment;
				if (!url) {
					field.$wrapper.html(
						`<div class="text-muted" style="padding: 8px 0;">${__(
							"The source document carries no attachment."
						)}</div>`
					);
					return;
				}
				const clean_url = frappe.utils.escape_html(url);
				const is_pdf = url.toLowerCase().split("?")[0].endsWith(".pdf");
				const html = is_pdf
					? `<iframe src="${clean_url}#toolbar=0&navpanes=0&scrollbar=0" style="width:100%; height:480px; border:1px solid var(--border-color); border-radius:4px;"></iframe>`
					: `<img src="${clean_url}" style="max-width:100%; max-height:480px; display:block; border-radius:4px;">`;
				field.$wrapper.html(html);
			});
	},

	open_source(frm) {
		if (frm.doc.source_doctype && frm.doc.source_name) {
			frappe.set_route("Form", frm.doc.source_doctype, frm.doc.source_name);
		}
	},

	set_lines(frm, lines) {
		frm.clear_table("lines");
		(lines || []).forEach((line) => {
			const row = frm.add_child("lines");
			row.account = line.account;
			row.libelle = line.libelle || "";
			row.fact = "";
			row.tresorerie = "";
			row.debit = flt(line.debit);
			row.credit = flt(line.credit);
		});
		frm.refresh_field("lines");
		erpnext.entries.update_totals(frm);
	},

	/** Called from every entry doctype's refresh. */
	entry_form(frm) {
		erpnext.entries.update_totals(frm);
		erpnext.entries.derive_period(frm);
		erpnext.entries.setup_tresorerie_query(frm);
		erpnext.entries.preview_source_attachment(frm);
		frm.add_custom_button(__("Modifier la ligne source"), () => erpnext.entries.open_source(frm));
		frm.add_custom_button(__("Appel Modele"), () => erpnext.entries.appel_modele(frm));
		frm.add_custom_button(__("Enreg. Modele"), () => erpnext.entries.enreg_modele(frm));
		// the save is the posting: keep frappe's callback pattern (frm.save is
		// not promise-based)
		frm.add_custom_button(__("Enregistrer"), () => {
			frm.save("Save", () => {
				frappe.show_alert({
					message: __("Entry posted to the ledger."),
					indicator: "green",
				});
			});
		});
	},

	/** New-form prefill: source mirrors + default model lines, or the
	 * Releve Vente grouping when the source is one. Nothing is saved. */
	load_entry_defaults(frm) {
		if (!frm.is_new() || frm.__entry_defaults_loaded) {
			return;
		}
		frm.__entry_defaults_loaded = true;
		const source_doctype = frm.doc.source_doctype || "";
		const source_name = frm.doc.source_name || "";
		frappe.call({
			method: "erpnext.custom_modules.entries.api.get_entry_defaults",
			args: { entry_doctype: frm.doctype, source_doctype, source_name },
			callback(r) {
				const defaults = r.message || {};
				if (!frm.doc.ref_doc && defaults.ref_doc) {
					frm.set_value("ref_doc", defaults.ref_doc);
				}
				const is_releve_vente = source_doctype === "Releve Vente" && source_name;
				if (is_releve_vente) {
					frappe.call({
						method: "erpnext.custom_modules.entries.api.get_model_lines",
						args: { source_doctype, source_name, journal: frm.doc.journal || "" },
						callback(r2) {
							const result = r2.message || {};
							if ((result.lines || []).length) {
								erpnext.entries.set_lines(frm, result.lines);
							}
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
						},
					});
				} else if ((defaults.lines || []).length && !(frm.doc.lines || []).length) {
					erpnext.entries.set_lines(frm, defaults.lines);
				}
				erpnext.entries.preview_source_attachment(frm);
			},
		});
	},

	appel_modele(frm) {
		if (!frm.doc.journal) {
			frappe.msgprint({
				title: __("Appel Modele"),
				message: __("Pick a journal first."),
				indicator: "orange",
			});
			return;
		}
		frappe.call({
			method: "erpnext.custom_modules.entries.api.get_journal_models",
			args: { journal: frm.doc.journal },
			callback(r) {
				const models = r.message || [];
				if (!models.length) {
					frappe.msgprint({
						title: __("Appel Modele"),
						message: __("Journal {0} has no Journal Model yet.", [frm.doc.journal]),
						indicator: "orange",
					});
					return;
				}
				const dialog = new frappe.ui.Dialog({
					title: __("Appel Modele"),
					fields: [
						{
							fieldname: "model",
							fieldtype: "Select",
							label: __("Model"),
							options: models.map((m) => m.name),
							reqd: 1,
							default: (models.find((m) => m.is_default) || models[0]).name,
						},
					],
					primary_action_label: __("Load"),
					primary_action(values) {
						dialog.hide();
						frappe.call({
							method: "erpnext.custom_modules.entries.api.get_journal_model_lines",
							args: { model: values.model },
							callback(r2) {
								erpnext.entries.set_lines(frm, (r2.message && r2.message.lines) || []);
								frappe.show_alert(__("Model {0} loaded.", [values.model]));
							},
						});
					},
				});
				dialog.show();
			},
		});
	},

	enreg_modele(frm) {
		const lines = (frm.doc.lines || [])
			.filter((line) => line.account)
			.map((line) => ({
				account: line.account,
				side: flt(line.debit) > 0 ? "Debit" : "Credit",
				libelle: line.libelle || "",
				amount_source: "Manual",
			}));
		if (!lines.length) {
			frappe.msgprint({
				title: __("Enreg. Modele"),
				message: __("The grid has no account lines to save as a model."),
				indicator: "orange",
			});
			return;
		}
		const dialog = new frappe.ui.Dialog({
			title: __("Enreg. Modele"),
			fields: [
				{
					fieldname: "model_name",
					fieldtype: "Data",
					label: __("Model Name"),
					reqd: 1,
					default: __("Model {0}", [frappe.datetime.get_today()]),
				},
			],
			primary_action_label: __("Save"),
			primary_action(values) {
				dialog.hide();
				frappe.call({
					method: "erpnext.custom_modules.entries.api.save_journal_model",
					args: {
						journal: frm.doc.journal,
						model_name: values.model_name,
						lines: JSON.stringify(lines),
					},
					callback() {
						frappe.show_alert({
							message: __("Model {0} saved for journal {1}.", [values.model_name, frm.doc.journal]),
							indicator: "green",
						});
					},
				});
			},
		});
		dialog.show();
	},
});
