frappe.provide("erpnext.facturation");

erpnext.facturation.EntriesGrid = class EntriesGrid {
	constructor(opts) {
		Object.assign(
			this,
			{
				page_length: 20,
				order_by: "date desc, creation desc",
			},
			opts
		);
		this.page_start = 0;
		this.make();
	}

	make() {
		this.$wrapper = this.frm.fields_dict[this.field].$wrapper;
		this.$wrapper.empty();

		if (this.frm.is_new()) {
			this.$wrapper.html(
				`<div class="text-muted" style="padding: 8px 0;">${__(
					"Save this document to add entries."
				)}</div>`
			);
			return;
		}

		this.$container = $(`
			<div class="entries-grid-container">
				<div class="entries-grid-toolbar" style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
					<div class="entries-grid-summary text-muted small"></div>
					<button class="btn btn-xs btn-default entries-grid-add">${__("Add Entry")}</button>
				</div>
				<div class="entries-grid-table"></div>
				<div class="entries-grid-pagination" style="display:flex; justify-content:flex-end; gap:8px; align-items:center; margin-top:8px;">
					<button class="btn btn-xs btn-default entries-grid-prev">${__("Previous")}</button>
					<span class="entries-grid-page-label text-muted small"></span>
					<button class="btn btn-xs btn-default entries-grid-next">${__("Next")}</button>
				</div>
			</div>
		`).appendTo(this.$wrapper);

		this.$container.find(".entries-grid-add").on("click", () => this.add_entry());
		this.$container.find(".entries-grid-prev").on("click", () => this.change_page(-1));
		this.$container.find(".entries-grid-next").on("click", () => this.change_page(1));

		this.refresh();
	}

	change_page(direction) {
		const new_start = this.page_start + direction * this.page_length;
		if (new_start < 0) return;
		this.page_start = new_start;
		this.refresh();
	}

	add_entry() {
		frappe.ui.form.make_quick_entry(
			this.child_doctype,
			() => this.refresh(),
			null,
			{ [this.parent_field]: this.frm.doc.name },
			true
		);
	}

	refresh() {
		const filters = { [this.parent_field]: this.frm.doc.name };
		const fields = ["name", ...this.columns.map((c) => c.fieldname)];

		Promise.all([
			frappe.call({
				method: "frappe.client.get_list",
				args: {
					doctype: this.child_doctype,
					filters,
					fields,
					order_by: this.order_by,
					limit_start: this.page_start,
					limit_page_length: this.page_length,
				},
			}),
			frappe.call({
				method: "frappe.client.get_count",
				args: { doctype: this.child_doctype, filters },
			}),
		]).then(([list_res, count_res]) => {
			const data = list_res.message || [];
			const total = count_res.message || 0;
			this.render_table(data);
			this.render_pagination(total, data.length);
		});
	}

	render_table(data) {
		const columns = this.columns.map((c) => ({
			id: c.fieldname,
			name: c.label,
			width: c.width || 100,
			align: c.align || "left",
			editable: false,
		}));

		const rows = data.map((row) =>
			this.columns.map((c) => {
				let value = row[c.fieldname];
				if (value === null || value === undefined) value = "";
				return value;
			})
		);

		const $table = this.$container.find(".entries-grid-table");

		if (!this.datatable) {
			this.datatable = new DataTable($table[0], {
				columns,
				data: rows,
				layout: "fixed",
				serialNoColumn: true,
				checkboxColumn: false,
				inlineFilters: false,
				noDataMessage: __("No entries yet."),
				cellHeight: 33,
			});
		} else {
			this.datatable.refresh(rows, columns);
		}
	}

	render_pagination(total, shown_count) {
		const start = total === 0 ? 0 : this.page_start + 1;
		const end = this.page_start + shown_count;
		this.$container
			.find(".entries-grid-summary")
			.text(`${__("Showing")} ${start}-${end} ${__("of")} ${total}`);
		this.$container
			.find(".entries-grid-page-label")
			.text(`${Math.floor(this.page_start / this.page_length) + 1} / ${Math.max(
				1,
				Math.ceil(total / this.page_length)
			)}`);
		this.$container.find(".entries-grid-prev").prop("disabled", this.page_start === 0);
		this.$container
			.find(".entries-grid-next")
			.prop("disabled", this.page_start + this.page_length >= total);
	}
};
