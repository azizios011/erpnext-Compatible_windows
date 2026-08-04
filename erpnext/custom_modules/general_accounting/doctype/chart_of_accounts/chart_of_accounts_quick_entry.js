frappe.provide("frappe.ui.form");

frappe.ui.form.ChartOfAccountsQuickEntryForm = class ChartOfAccountsQuickEntryForm extends frappe.ui.form.QuickEntryForm {
	constructor(doctype, after_insert, init_callback, doc, force) {
		super(doctype, after_insert, init_callback, doc, force);
		this.selected_class = null;
	}

	render_dialog() {
		this.mandatory = [
			{
				label: __("Account"),
				fieldname: "account",
				fieldtype: "Data",
				reqd: 1,
			},
			{
				label: __("Label"),
				fieldname: "label",
				fieldtype: "Data",
				reqd: 1,
			},
			{
				label: __("Account Type"),
				fieldname: "account_type",
				fieldtype: "Data",
				reqd: 0,
			},
			{
				label: __("Nature"),
				fieldname: "nature",
				fieldtype: "Data",
			},
			{
				label: __("Direction"),
				fieldname: "direction",
				fieldtype: "Data",
				reqd: 0,
			},
		];

		super.render_dialog();
		this.render_step_1();
	}

	render_step_1() {
		const me = this;
		this.selected_class = null;
		this.dialog.set_title(__("Select Account Class"));

		// Hide standard footer primary button and fields layout in step 1
		this.dialog.get_primary_btn().hide();
		if (this.dialog.custom_action_btn) {
			this.dialog.custom_action_btn.hide();
		}
		$(this.dialog.body).find(".form-layout").hide();

		// Hide back button if present
		if (this.dialog.$wrapper) {
			this.dialog.$wrapper.find(".coa-btn-back").hide();
		}

		// Create step 1 container if not existing
		let $step1 = $(this.dialog.body).find(".coa-step-1");
		if (!$step1.length) {
			$step1 = $('<div class="coa-step-1"></div>').appendTo(this.dialog.body);
		}
		$step1.empty().show();

		const classes = [
			"Capitaux",
			"Immobilisations",
			"Stock et Encours",
			"Tiers",
			"Financiers",
			"Charges",
			"Produits",
		];

		const $list = $('<div class="list-group"></div>').appendTo($step1);

		classes.forEach((className) => {
			const $item = $(
				`<a href="#" class="list-group-item list-group-item-action">${className}</a>`
			);
			$item.on("click", (e) => {
				e.preventDefault();
				me.selected_class = className;
				me.render_step_2(className);
			});
			$list.append($item);
		});
	}

	render_step_2(className) {
		const me = this;
		this.dialog.set_title(__("New {0} Account", [className]));

		// Hide step 1 view
		$(this.dialog.body).find(".coa-step-1").hide();

		// Show standard fields layout and primary button
		$(this.dialog.body).find(".form-layout").show();
		this.dialog.get_primary_btn().show();

		// Set or show back button in title head / header
		let $backBtn = this.dialog.$wrapper.find(".coa-btn-back");
		if (!$backBtn.length) {
			$backBtn = $(
				`<button class="btn btn-default btn-xs pull-left coa-btn-back mr-2" style="margin-right: 8px;">
					<i class="fa fa-arrow-left"></i> ${__("Back")}
				</button>`
			);
			const $header = this.dialog.$wrapper.find(".modal-header");
			const $target = $header.find(".title-section").length
				? $header.find(".title-section")
				: $header;
			$backBtn.prependTo($target);
			$backBtn.on("click", (e) => {
				e.preventDefault();
				me.render_step_1();
			});
		}
		$backBtn.show();
	}
};
