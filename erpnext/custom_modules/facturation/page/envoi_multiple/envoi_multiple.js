// Envoi Multiple des documents — upload several files and create one
// Facturation document per file, grouped by the chosen month/year.
frappe.pages["envoi-multiple"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Envoi Multiple des documents"),
		single_column: true,
	});

	const ALLOWED = ["pdf", "jpg", "jpeg", "png", "tif", "tiff", "xlsx"];
	const MONTHS = [
		"Janvier",
		"Fevrier",
		"Mars",
		"Avril",
		"Mai",
		"Juin",
		"Juillet",
		"Aout",
		"Septembre",
		"Octobre",
		"Novembre",
		"Decembre",
	];

	const body = page.main;
	body.html(`
		<div class="envoi-multiple" style="max-width: 860px;">
			<div class="form-column" style="display:flex; gap:12px; flex-wrap:wrap; align-items:flex-end; margin-bottom:12px;">
				<div style="min-width:180px;">
					<label class="control-label">${__("Mois")}</label>
					<select class="form-control form-control-sm" id="envoi-mois">
						<option value="">${__("Choisir mois")}</option>
						${MONTHS.map((m, i) => `<option value="${i + 1}">${m}</option>`).join("")}
					</select>
				</div>
				<div style="min-width:120px;">
					<label class="control-label">${__("Annee")}</label>
					<input type="number" class="form-control form-control-sm" id="envoi-annee"
						value="${new Date().getFullYear()}">
				</div>
				<div style="min-width:240px;">
					<label class="control-label">${__("Type document")}</label>
					<select class="form-control form-control-sm" id="envoi-type"></select>
				</div>
			</div>

			<div id="envoi-dropzone" style="border: 2px dashed var(--border-color); border-radius: 8px;
				padding: 28px; text-align: center; color: var(--text-muted); margin-bottom: 12px;">
				${__("Faites glisser des fichiers ici")}
				<div style="margin-top: 8px;">
					<button class="btn btn-primary btn-sm" id="envoi-pick">${__("Choisir des documents")}</button>
				</div>
			</div>
			<input type="file" id="envoi-file-input" multiple style="display: none;">

			<table class="table table-bordered" style="font-size: 12px;">
				<thead><tr>
					<th>${__("NOM")}</th><th>${__("TAILLE")}</th>
					<th style="width: 30%;">${__("PROGRESSION")}</th><th style="width: 90px;">${__("ACTIONS")}</th>
				</tr></thead>
				<tbody id="envoi-rows"></tbody>
			</table>

			<div style="display:flex; gap:8px; align-items:center;">
				<button class="btn btn-primary btn-sm" id="envoi-send" disabled>${__("Envoyer")}</button>
				<button class="btn btn-default btn-sm" id="envoi-cancel" disabled>${__("Annuler")}</button>
				<span id="envoi-summary" class="text-muted" style="font-size: 12px;"></span>
			</div>
			<div style="margin-top: 10px;">
				<button class="btn btn-secondary btn-sm hidden" id="envoi-open-list">${__("Ouvrir la liste")}</button>
			</div>
		</div>
	`);

	const $ = window.jQuery;
	const $mois = body.find("#envoi-mois");
	const $annee = body.find("#envoi-annee");
	const $type = body.find("#envoi-type");
	const $rows = body.find("#envoi-rows");
	const $dropzone = body.find("#envoi-dropzone");
	const $input = body.find("#envoi-file-input");
	const $send = body.find("#envoi-send");
	const $cancel = body.find("#envoi-cancel");
	const $summary = body.find("#envoi-summary");
	const $open_list = body.find("#envoi-open-list");

	const queue = [];
	const in_flight = [];
	let last_type = null;

	// the dock context's Exercice drives the period: the year defaults to
	// the Exercice's and the month list is limited to the months inside it
	// (send_documents re-validates server-side)
	const exercice_debut = frappe.boot.axeane_context?.date_debut
		? frappe.datetime.str_to_obj(frappe.boot.axeane_context.date_debut)
		: null;
	const exercice_fin = frappe.boot.axeane_context?.date_fin
		? frappe.datetime.str_to_obj(frappe.boot.axeane_context.date_fin)
		: null;
	if (exercice_debut) {
		$annee.val(exercice_debut.getFullYear());
	}

	function rebuild_month_options() {
		const year =
			parseInt($annee.val(), 10) ||
			(exercice_debut ? exercice_debut.getFullYear() : new Date().getFullYear());
		let first = 1;
		let last = 12;
		if (exercice_debut) {
			if (exercice_debut.getFullYear() > year) {
				first = 13; // the year sits before the Exercice: no month at all
			} else if (exercice_debut.getFullYear() === year) {
				first = exercice_debut.getMonth() + 1;
			}
			if (exercice_fin) {
				if (exercice_fin.getFullYear() === year) {
					last = Math.min(last, exercice_fin.getMonth() + 1);
				} else if (exercice_fin.getFullYear() < year) {
					last = 0;
				}
			}
		}
		const selected = parseInt($mois.val(), 10) || 0;
		const options = [`<option value="">${__("Choisir mois")}</option>`];
		for (let month = first; month <= last; month++) {
			options.push(`<option value="${month}">${MONTHS[month - 1]}</option>`);
		}
		$mois.html(options.join(""));
		if (selected >= first && selected <= last) {
			$mois.val(String(selected));
		}
		refresh_state();
	}
	rebuild_month_options();
	$annee.on("change", rebuild_month_options);

	function allowed(file) {
		const ext = (file.name || "").split(".").pop().toLowerCase();
		return ALLOWED.indexOf(ext) !== -1;
	}

	function fmt_size(bytes) {
		if (bytes > 1048576) return (bytes / 1048576).toFixed(1) + " Mo";
		return Math.max(1, Math.round(bytes / 1024)) + " Ko";
	}

	function refresh_state() {
		$send.prop(
			"disabled",
			!($mois.val() && $type.val() && queue.some((item) => !item.done && !item.error))
		);
		$cancel.prop("disabled", !in_flight.length);
	}

	function add_files(files) {
		[...files].forEach((file) => {
			if (!allowed(file)) {
				frappe.msgprint({
					title: file.name,
					message: __("Type de fichier non supporte (pdf, jpg, jpeg, png, tif, tiff, xlsx)."),
					indicator: "red",
				});
				return;
			}
			const item = { file, done: false, error: "", file_url: "", docname: "" };
			queue.push(item);
			const $row = $(`
				<tr>
					<td>${frappe.utils.escape_html(file.name)}</td>
					<td>${fmt_size(file.size)}</td>
					<td><div class="progress" style="height: 12px;">
						<div class="progress-bar" style="width:0%"></div></div>
						<div class="envoi-status text-muted" style="font-size:11px;"></div></td>
					<td><button class="btn btn-xs btn-default envoi-remove">${__("Retirer")}</button></td>
				</tr>`);
			item.$row = $row;
			item.$bar = $row.find(".progress-bar");
			item.$status = $row.find(".envoi-status");
			$row.find(".envoi-remove").on("click", () => {
				const index = queue.indexOf(item);
				if (index !== -1) queue.splice(index, 1);
				$row.remove();
				refresh_state();
			});
			$rows.append($row);
		});
		refresh_state();
	}

	function upload_one(item) {
		return new Promise((resolve) => {
			const xhr = new XMLHttpRequest();
			in_flight.push(xhr);
			const form = new FormData();
			form.append("file", item.file);
			form.append("is_private", "1");
			xhr.open("POST", "/api/method/upload_file");
			xhr.setRequestHeader("X-Frappe-CSRF-Token", frappe.csrf_token);
			xhr.upload.onprogress = (e) => {
				if (e.lengthComputable) {
					item.$bar.css("width", Math.round((e.loaded / e.total) * 100) + "%");
				}
			};
			xhr.onload = () => {
				in_flight.splice(in_flight.indexOf(xhr), 1);
				try {
					const body = JSON.parse(xhr.responseText);
					const message = body.message || {};
					if (xhr.status === 200 && message.file_url) {
						item.file_url = message.file_url;
						item.docname = message.name;
					} else {
						item.error = body._server_messages
							? JSON.parse(body._server_messages)
									.map((m) => (JSON.parse(m) || {}).message || "")
									.join(" ")
							: __("Upload failed") + " (" + xhr.status + ")";
					}
				} catch (error) {
					item.error = __("Upload failed") + " (" + xhr.status + ")";
				}
				resolve();
			};
			xhr.onerror = () => {
				in_flight.splice(in_flight.indexOf(xhr), 1);
				item.error = __("Upload failed");
				resolve();
			};
			xhr.send(form);
		});
	}

	function mark_row(item) {
		if (item.error) {
			item.$bar.css("width", "100%").addClass("progress-bar-danger");
			item.$status.text(__("Erreur")).css("color", "#c0392b").attr("title", item.error);
		} else if (item.sent_ok) {
			item.$bar.css("width", "100%").removeClass("progress-bar-danger");
			item.$status.text(__("Envoye")).css("color", "#1a7f37");
		}
	}

	function send() {
		const doctype = $type.val();
		const month = parseInt($mois.val(), 10);
		const year = parseInt($annee.val(), 10);
		const pending = queue.filter((item) => !item.done && !item.error && !item.file_url);

		$send.prop("disabled", true);
		$cancel.prop("disabled", true);

		const upload_chain = pending.reduce(
			(chain, item) => chain.then(() => upload_one(item).then(() => mark_row(item))),
			Promise.resolve()
		);

		upload_chain.then(() => {
			const ready = queue.filter((item) => item.file_url && !item.done);
			const batches = [];
			for (let i = 0; i < ready.length; i += 50) {
				batches.push(ready.slice(i, i + 50));
			}
			const send_chain = batches.reduce((chain, batch) => {
				return chain.then(
					() =>
						new Promise((resolve) => {
							frappe.call({
								method: "erpnext.custom_modules.facturation.api.send_documents",
								args: {
									doctype: doctype,
									month: month,
									year: year,
									files: JSON.stringify(batch.map((item) => item.file_url)),
								},
								callback(r) {
									const results = (r.message && r.message.results) || [];
									results.forEach((result) => {
										const item = queue.find((q) => q.file_url === result.file_url);
										if (!item) return;
										if (result.ok) {
											item.done = true;
											item.sent_ok = true;
											item.docname = result.name;
										} else {
											item.error = result.error || __("Creation failed");
											item.file_url = "";
										}
										mark_row(item);
									});
									resolve();
								},
								error() {
									batch.forEach((item) => {
										item.error = __("Creation failed");
										mark_row(item);
									});
									resolve();
								},
							});
						})
				);
			}, Promise.resolve());

			send_chain.then(() => {
				const ok_count = queue.filter((item) => item.sent_ok).length;
				$summary.text(__("{0} documents envoyes", [ok_count]));
				const failures = queue.filter((item) => item.error);
				if (!failures.length && ok_count) {
					setTimeout(() => open_list(doctype), 1000);
				} else if (ok_count) {
					$open_list.removeClass("hidden");
					$open_list.off("click").on("click", () => open_list(doctype));
				}
				refresh_state();
			});
		});
	}

	function open_list(doctype) {
		frappe.route_options = { status: "Pending" };
		frappe.set_route("List", doctype);
	}

	$type.html('<option value="">Choisir type</option>');
	frappe.call({
		method: "erpnext.custom_modules.facturation.api.get_upload_targets",
		args: {},
		callback(r) {
			const groups = (r.message && r.message.groups) || [];
			if (!groups.length) {
				$type.html('<option value="">' + __("Aucun type disponible") + "</option>");
				return;
			}
			groups.forEach((group) => {
				const $group = $("<optgroup>").attr("label", group.group);
				group.doctypes.forEach((dt) => {
					$group.append($("<option>").attr("value", dt).text(dt));
				});
				$type.append($group);
			});
		},
		error(r) {
			$type.html('<option value="">' + __("Erreur de chargement") + "</option>");
		},
	});

	$mois.add($type).add($annee).on("change", refresh_state);
	$send.on("click", send);
	$cancel.on("click", () => {
		in_flight.forEach((xhr) => xhr.abort());
		queue.splice(0, queue.length);
		$rows.empty();
		$summary.text("");
		refresh_state();
	});
	$input.on("change", (e) => {
		add_files(e.target.files);
		$input.val("");
	});
	$dropzone.on("dragover", (e) => {
		e.preventDefault();
		$dropzone.css("background", "var(--control-bg, #f8f8f8)");
	});
	$dropzone.on("dragleave drop", () => $dropzone.css("background", ""));
	$dropzone.on("drop", (e) => {
		e.preventDefault();
		add_files(e.originalEvent.dataTransfer.files);
	});
	body.find("#envoi-pick").on("click", () => $input.trigger("click"));
};
