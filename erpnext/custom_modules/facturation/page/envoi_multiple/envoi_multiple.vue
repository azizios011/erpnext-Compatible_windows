<!-- Envoi Multiple des documents — upload several files and create one
     Facturation document per file, grouped by the chosen month/year.

     Frappe UI island page (the old envoi_multiple.js ported 1:1): the desk
     draws this Page through its island, so the script lives here as a Vue
     component. Backend calls, upload semantics, exercice-driven period
     selects, batching and cancel/retry behavior are unchanged. -->
<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { Button } from "frappe-ui";

const frappe = window.frappe;
const __ = window.__;

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

// the dock context's Exercice drives the period: the year defaults to the
// Exercice's and the month list is limited to the months inside it
// (send_documents re-validates server-side)
const exercice_debut = frappe.boot.axeane_context?.date_debut
	? frappe.datetime.str_to_obj(frappe.boot.axeane_context.date_debut)
	: null;
const exercice_fin = frappe.boot.axeane_context?.date_fin
	? frappe.datetime.str_to_obj(frappe.boot.axeane_context.date_fin)
	: null;

const month = ref("");
const year = ref(exercice_debut ? exercice_debut.getFullYear() : new Date().getFullYear());
const doctype = ref("");
const type_groups = ref([]);
const types_error = ref(false);

const items = ref([]);
const summary = ref("");
const open_list_doctype = ref("");
const sending = ref(false);
const dragging = ref(false);
const file_input = ref(null);

const month_options = computed(() => {
	const y = parseInt(year.value, 10) || (exercice_debut ? exercice_debut.getFullYear() : new Date().getFullYear());
	let first = 1;
	let last = 12;
	if (exercice_debut) {
		if (exercice_debut.getFullYear() > y) {
			first = 13; // the year sits before the Exercice: no month at all
		} else if (exercice_debut.getFullYear() === y) {
			first = exercice_debut.getMonth() + 1;
		}
		if (exercice_fin) {
			if (exercice_fin.getFullYear() === y) {
				last = Math.min(last, exercice_fin.getMonth() + 1);
			} else if (exercice_fin.getFullYear() < y) {
				last = 0;
			}
		}
	}
	const options = [];
	for (let m = first; m <= last; m++) {
		options.push({ value: m, label: MONTHS[m - 1] });
	}
	return options;
});

// a year change re-clamps the months; keep the selection when still inside
watch(year, () => {
	const value = parseInt(month.value, 10) || 0;
	const valid = month_options.value.some((option) => option.value === value);
	if (value && !valid) {
		month.value = "";
	}
});

const pending_items = computed(() => items.value.filter((item) => !item.done && !item.error));
const uploading_count = computed(
	() => items.value.filter((item) => item.status === "uploading").length
);
const can_send = computed(() => Boolean(month.value && doctype.value && pending_items.value.length));
const can_cancel = computed(() => uploading_count.value > 0);

function allowed(file) {
	const ext = (file.name || "").split(".").pop().toLowerCase();
	return ALLOWED.indexOf(ext) !== -1;
}

function fmt_size(bytes) {
	if (bytes > 1048576) return (bytes / 1048576).toFixed(1) + " Mo";
	return Math.max(1, Math.round(bytes / 1024)) + " Ko";
}

let item_seq = 0;

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
		items.value.push({
			id: ++item_seq,
			file,
			name: file.name,
			size: file.size,
			progress: 0,
			status: "idle", // idle | uploading | uploaded | sent | error
			error: "",
			file_url: "",
			docname: "",
			controller: null,
		});
	});
}

function remove_item(item) {
	if (item.status === "uploading") return;
	const index = items.value.indexOf(item);
	if (index !== -1) items.value.splice(index, 1);
}

function pick_files() {
	file_input.value?.click();
}

function on_pick(e) {
	add_files(e.target.files);
	e.target.value = "";
}

function on_drag_over() {
	dragging.value = true;
}

function on_drop(e) {
	dragging.value = false;
	add_files(e.dataTransfer?.files || []);
}

function upload_one(item) {
	return new Promise((resolve) => {
		const xhr = new XMLHttpRequest();
		item.controller = { abort: () => xhr.abort() };
		const form = new FormData();
		form.append("file", item.file);
		form.append("is_private", "1");
		xhr.open("POST", "/api/method/upload_file");
		xhr.setRequestHeader("X-Frappe-CSRF-Token", frappe.csrf_token);
		xhr.upload.onprogress = (e) => {
			if (e.lengthComputable) {
				item.progress = Math.round((e.loaded / e.total) * 100);
			}
		};
		xhr.onload = () => {
			try {
				const body = JSON.parse(xhr.responseText);
				const message = body.message || {};
				if (xhr.status === 200 && message.file_url) {
					item.file_url = message.file_url;
					item.docname = message.name;
					item.status = "uploaded";
					item.progress = 100;
				} else {
					item.error = body._server_messages
						? JSON.parse(body._server_messages)
								.map((m) => (JSON.parse(m) || {}).message || "")
								.join(" ")
						: __("Upload failed") + " (" + xhr.status + ")";
					item.status = "error";
				}
			} catch (error) {
				item.error = __("Upload failed") + " (" + xhr.status + ")";
				item.status = "error";
			}
			resolve();
		};
		xhr.onerror = () => {
			item.error = __("Upload failed");
			item.status = "error";
			resolve();
		};
		xhr.send(form);
	});
}

function chunks(list, size) {
	const batches = [];
	for (let i = 0; i < list.length; i += size) {
		batches.push(list.slice(i, i + size));
	}
	return batches;
}

async function send() {
	if (!can_send.value || sending.value) return;
	const target_doctype = doctype.value;
	const target_month = parseInt(month.value, 10);
	const target_year = parseInt(year.value, 10);
	sending.value = true;

	// one upload at a time, in list order — same as the old chain
	const pending = items.value.filter((item) => !item.done && !item.error && !item.file_url);
	for (const item of pending) {
		item.status = "uploading";
		await upload_one(item);
	}

	// documents are created in batches of 50; the backend rolls back one
	// file's savepoint on failure, so results are matched per file_url
	const ready = items.value.filter((item) => item.file_url && !item.done);
	for (const batch of chunks(ready, 50)) {
		try {
			const result = await frappe.xcall(
				"erpnext.custom_modules.facturation.api.send_documents",
				{
					doctype: target_doctype,
					month: target_month,
					year: target_year,
					files: JSON.stringify(batch.map((item) => item.file_url)),
				}
			);
			(result?.results || []).forEach((row) => {
				const item = items.value.find((q) => q.file_url === row.file_url);
				if (!item) return;
				if (row.ok) {
					item.done = true;
					item.status = "sent";
					item.docname = row.name;
				} else {
					item.error = row.error || __("Creation failed");
					item.file_url = "";
					item.status = "error";
				}
			});
		} catch (error) {
			batch.forEach((item) => {
				item.error = error?.message || __("Creation failed");
				item.status = "error";
			});
		}
	}

	const ok_count = items.value.filter((item) => item.status === "sent").length;
	summary.value = __("{0} documents envoyes", [ok_count]);
	const failures = items.value.filter((item) => item.error);
	if (!failures.length && ok_count) {
		setTimeout(() => open_list(target_doctype), 1000);
	} else if (ok_count) {
		open_list_doctype.value = target_doctype;
	}
	sending.value = false;
}

function cancel() {
	items.value.forEach((item) => item.status === "uploading" && item.controller?.abort());
	items.value.splice(0, items.value.length);
	summary.value = "";
	open_list_doctype.value = "";
}

function open_list(target_doctype) {
	frappe.route_options = { status: "Pending" };
	frappe.set_route("List", target_doctype);
}

onMounted(async () => {
	try {
		const result = await frappe.xcall(
			"erpnext.custom_modules.facturation.api.get_upload_targets"
		);
		type_groups.value = result?.groups || [];
		types_error.value = !type_groups.value.length;
	} catch (error) {
		types_error.value = true;
	}
});
</script>

<template>
	<div class="envoi-multiple">
		<div class="fields-row">
			<div class="field">
				<label>{{ __("Mois") }}</label>
				<select v-model="month" class="control">
					<option value="">{{ __("Choisir mois") }}</option>
					<option v-for="option in month_options" :key="option.value" :value="option.value">
						{{ option.label }}
					</option>
				</select>
			</div>
			<div class="field field-year">
				<label>{{ __("Annee") }}</label>
				<input v-model="year" type="number" class="control" />
			</div>
			<div class="field field-type">
				<label>{{ __("Type document") }}</label>
				<select v-model="doctype" class="control">
					<option value="">{{ types_error ? __("Erreur de chargement") : __("Choisir type") }}</option>
					<optgroup v-for="group in type_groups" :key="group.group" :label="group.group">
						<option v-for="dt in group.doctypes" :key="dt" :value="dt">{{ dt }}</option>
					</optgroup>
				</select>
			</div>
		</div>

		<div
			class="dropzone"
			:class="{ dragging }"
			@dragover.prevent="on_drag_over"
			@dragleave.prevent="dragging = false"
			@drop.prevent="on_drop"
		>
			<div>{{ __("Faites glisser des fichiers ici") }}</div>
			<div class="dropzone-pick">
				<Button variant="solid" size="sm" @click="pick_files">
					{{ __("Choisir des documents") }}
				</Button>
			</div>
		</div>
		<input ref="file_input" type="file" multiple class="file-input" @change="on_pick" />

		<table class="rows">
			<thead>
				<tr>
					<th>{{ __("NOM") }}</th>
					<th>{{ __("TAILLE") }}</th>
					<th class="col-progress">{{ __("PROGRESSION") }}</th>
					<th class="col-actions">{{ __("ACTIONS") }}</th>
				</tr>
			</thead>
			<tbody>
				<tr v-for="item in items" :key="item.id">
					<td class="cell-name">{{ item.name }}</td>
					<td>{{ fmt_size(item.size) }}</td>
					<td class="col-progress">
						<div class="bar">
							<div
								class="bar-fill"
								:class="{ 'bar-fill-error': item.status === 'error' }"
								:style="{ width: item.status === 'error' ? '100%' : item.progress + '%' }"
							></div>
						</div>
						<div class="status" :class="{ 'status-error': item.status === 'error', 'status-ok': item.status === 'sent' }"
							:title="item.error || ''">
							<template v-if="item.status === 'error'">{{ __("Erreur") }}</template>
							<template v-else-if="item.status === 'sent'">{{ __("Envoye") }}</template>
						</div>
					</td>
					<td class="col-actions">
						<button
							class="btn-remove"
							:disabled="item.status === 'uploading' || sending"
							@click="remove_item(item)"
						>
							{{ __("Retirer") }}
						</button>
					</td>
				</tr>
			</tbody>
		</table>

		<div class="actions-row">
			<Button variant="solid" :disabled="!can_send || sending" @click="send">
				{{ __("Envoyer") }}
			</Button>
			<Button variant="subtle" :disabled="!can_cancel || sending" @click="cancel">
				{{ __("Annuler") }}
			</Button>
			<span v-if="summary" class="summary">{{ summary }}</span>
			<Button
				v-if="open_list_doctype"
				variant="ghost"
				size="sm"
				@click="open_list(open_list_doctype)"
			>
				{{ __("Ouvrir la liste") }}
			</Button>
		</div>
	</div>
</template>

<style>
.envoi-multiple {
	max-width: 860px;
}
.fields-row {
	display: flex;
	gap: 12px;
	flex-wrap: wrap;
	align-items: flex-end;
	margin-bottom: 12px;
}
.field {
	display: flex;
	flex-direction: column;
	gap: 4px;
	min-width: 180px;
}
.field-year {
	min-width: 120px;
}
.field-type {
	min-width: 240px;
	flex-grow: 1;
}
.field label {
	font-size: 11px;
	color: var(--text-muted);
}
.control {
	height: 28px;
	border: 1px solid var(--border-color);
	border-radius: var(--border-radius, 6px);
	background: var(--control-bg);
	color: var(--text-color);
	padding: 0 8px;
	font-size: 12px;
	outline: none;
}
.control:focus {
	border-color: var(--brand-primary, var(--text-color));
}
.dropzone {
	border: 2px dashed var(--border-color);
	border-radius: 8px;
	padding: 28px;
	text-align: center;
	color: var(--text-muted);
	margin-bottom: 12px;
	transition: background 0.15s ease;
}
.dropzone.dragging {
	background: var(--control-bg);
}
.dropzone-pick {
	margin-top: 8px;
}
.file-input {
	display: none;
}
.rows {
	width: 100%;
	font-size: 12px;
	border-collapse: collapse;
}
.rows th,
.rows td {
	border: 1px solid var(--border-color);
	padding: 6px 8px;
	text-align: left;
	vertical-align: middle;
}
.rows th {
	color: var(--text-muted);
	font-weight: 600;
}
.col-progress {
	width: 30%;
}
.col-actions {
	width: 90px;
}
.cell-name {
	word-break: break-all;
}
.bar {
	height: 12px;
	background: var(--surface-gray-2, #f0f0f0);
	border-radius: 3px;
	overflow: hidden;
}
.bar-fill {
	height: 100%;
	background: var(--brand-primary, #2490ef);
	transition: width 0.2s ease;
}
.bar-fill-error {
	background: #c0392b;
}
.status {
	font-size: 11px;
	margin-top: 2px;
	color: var(--text-muted);
}
.status-error {
	color: #c0392b;
}
.status-ok {
	color: #1a7f37;
}
.btn-remove {
	border: 1px solid var(--border-color);
	background: var(--control-bg);
	border-radius: 4px;
	font-size: 11px;
	padding: 2px 8px;
	color: var(--text-color);
	cursor: pointer;
}
.btn-remove:disabled {
	opacity: 0.5;
	cursor: default;
}
.actions-row {
	display: flex;
	gap: 8px;
	align-items: center;
	margin-top: 10px;
}
.summary {
	color: var(--text-muted);
	font-size: 12px;
}
</style>
