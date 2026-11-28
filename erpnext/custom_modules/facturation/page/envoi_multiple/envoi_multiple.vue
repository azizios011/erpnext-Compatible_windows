<!-- Envoi Multiple des documents — upload several files and create one
     Facturation document per file, grouped by the chosen month/year.

     Frappe UI island page: built from frappe-ui components (FormControl,
     Progress, Badge, Button) and the desk tailwind tokens, porting the old
     envoi_multiple.js behavior 1:1 — exercice-driven period selects,
     extension allowlist, sequential uploads with per-file progress, batched
     send_documents with per-file retry, cancel, and the Pending-list
     redirect. Backend calls are unchanged. -->
<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { Badge, Button, FormControl, Progress } from "frappe-ui";

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

const month = ref(null);
const year = ref(exercice_debut ? exercice_debut.getFullYear() : new Date().getFullYear());
const doctype = ref(null);
const type_groups = ref([]);
const types_error = ref(false);

const items = ref([]);
const summary = ref("");
const open_list_doctype = ref("");
const sending = ref(false);
const dragging = ref(false);
const file_input = ref(null);

// Mensuelle workbooks: one Mensuelle per monthly sheet, confirmed through a
// preview before anything is created (never auto-import)
const is_mensuelle = computed(() => doctype.value === "Mensuelle");
const previews = ref({}); // file_url -> {sheets: [...], recap_months: [...]}
const overwrite = ref(false);
const importing = ref(false);
const preview_count = computed(() => Object.keys(previews.value).length);
const can_import = computed(
	() => preview_count.value > 0 && !importing.value && !items.value.some((item) => item.status === "error")
);

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
		options.push({ label: MONTHS[m - 1], value: m });
	}
	return options;
});

// a year change re-clamps the months; keep the selection when still inside
watch(year, () => {
	const value = parseInt(month.value, 10) || 0;
	const valid = month_options.value.some((option) => option.value === value);
	if (value && !valid) {
		month.value = null;
	}
});

const type_options = computed(() => {
	const options = [];
	type_groups.value.forEach((group) => {
		group.doctypes.forEach((dt) => options.push({ label: dt, value: dt }));
	});
	return options;
});

const pending_items = computed(() => items.value.filter((item) => !item.done && !item.error));
const uploading_count = computed(
	() => items.value.filter((item) => item.status === "uploading").length
);
const can_send = computed(
	() =>
		Boolean(
			doctype.value && pending_items.value.length && (is_mensuelle.value || (month.value && year.value))
		)
);
const can_cancel = computed(() => uploading_count.value > 0);

function status_of(item) {
	if (item.status === "error") return { theme: "red", label: __("Erreur") };
	if (item.status === "sent") return { theme: "green", label: __("Envoye") };
	if (item.status === "uploaded") return { theme: "blue", label: __("Pret") };
	if (item.status === "uploading") return null;
	return { theme: "gray", label: __("En attente") };
}

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
	if (item.status === "uploading" || sending.value) return;
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
	if (target_doctype === "Mensuelle") {
		return mensuelle_flow();
	}
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

// ── Mensuelle workbook flow ──────────────────────────────────────────────────
// The workbook is SPLIT: one Mensuelle per monthly sheet (DM 01..dm 10);
// RECAP and the scratch sheets are ignored. The preview lists month, layout
// and errors per sheet and the user confirms before anything is created.
async function mensuelle_flow() {
	sending.value = true;
	try {
		const pending = items.value.filter((item) => !item.done && !item.error && !item.file_url);
		for (const item of pending) {
			item.status = "uploading";
			await upload_one(item);
		}
		const ready = items.value.filter((item) => item.file_url && !item.done);
		for (const item of ready) {
			item.status = "uploading";
			try {
				const preview = await frappe.xcall(
					"erpnext.custom_modules.facturation.api.preview_mensuelle_workbook",
					{ file_url: item.file_url }
				);
				previews.value = { ...previews.value, [item.file_url]: preview || { sheets: [] } };
				item.status = "uploaded";
			} catch (error) {
				item.error = error?.message || __("Analyse impossible");
				item.status = "error";
			}
		}
		summary.value = previews.value
			? __("Classeurs analyses: {0} — confirmez l'import ci-dessous", [preview_count.value])
			: "";
	} finally {
		sending.value = false;
	}
}

async function import_workbooks() {
	if (!can_import.value || importing.value) return;
	importing.value = true;
	try {
		for (const [file_url, preview] of Object.entries(previews.value)) {
			const item = items.value.find((q) => q.file_url === file_url);
			try {
				const result = await frappe.xcall(
					"erpnext.custom_modules.facturation.api.import_mensuelle_workbook",
					{ file_url, overwrite: overwrite.value ? 1 : 0 }
				);
				const created = (result?.results || []).filter((row) => row.ok && !row.skipped).length;
				const skipped = (result?.results || []).filter((row) => row.skipped).length;
				const failed = (result?.results || []).filter((row) => !row.ok).length;
				if (item) {
					item.done = true;
					item.status = failed ? "error" : "sent";
					item.docname = (result?.results || []).find((row) => row.ok && !row.skipped)?.name || "";
					item.error = failed
						? __("{} feuille(s) en erreur", [failed])
						: skipped
							? __("{} feuille(s) ignoree(s) (deja presentes)", [skipped])
							: "";
				}
				summary.value = __("Mensuelles creees/remplacees: {0}, ignorees: {1}, echecs: {2}", [
					created,
					skipped,
					failed,
				]);
			} catch (error) {
				if (item) {
					item.error = error?.message || __("Import impossible");
					item.status = "error";
				}
			}
		}
		delete_imported_previews();
	} finally {
		importing.value = false;
	}
}

function delete_imported_previews() {
	const kept = {};
	Object.entries(previews.value).forEach(([file_url, preview]) => {
		const item = items.value.find((q) => q.file_url === file_url);
		if (!item || !item.done) kept[file_url] = preview;
	});
	previews.value = kept;
}

function sheet_status_theme(sheet) {
	if (!sheet.ok) return "red";
	if (sheet.existing_mensuelle) return "orange";
	return "green";
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
	<div class="h-full overflow-y-auto pb-10">
		<div class="mx-auto w-full max-w-3xl px-6">
			<!-- Mensuelle workbooks: the months come from the sheets -->
			<div
				v-if="is_mensuelle"
				class="rounded-lg border border-surface-gray-2 bg-surface-gray-1 px-4 py-3 text-p-sm text-ink-gray-6"
			>
				{{
					__(
						"Classeur de declaration mensuelle: il est decoupe en une Mensuelle par feuille mensuelle (DM 01 a dm 10). L'onglet RECAP sert de controle et les feuilles de travail sont ignorees."
					)
				}}
			</div>

			<!-- Period and document type -->
			<div class="grid grid-cols-1 gap-4 sm:grid-cols-[170px_120px_1fr]">
				<FormControl
					v-if="!is_mensuelle"
					type="select"
					:label="__('Mois')"
					v-model="month"
					:options="month_options"
					:placeholder="types_error ? __('Erreur de chargement') : __('Choisir mois')"
					size="md"
					fill-width
				/>
				<FormControl v-if="!is_mensuelle" type="number" :label="__('Annee')" v-model="year" size="md" fill-width />
				<FormControl
					type="select"
					:label="__('Type document')"
					v-model="doctype"
					:options="type_options"
					:placeholder="types_error ? __('Erreur de chargement') : __('Choisir type')"
					size="md"
					fill-width
				/>
			</div>

			<!-- Dropzone -->
			<div
				class="mt-6 flex cursor-pointer flex-col items-center gap-2 rounded-lg border-2 border-dashed p-10 text-center transition-colors"
				:class="
					dragging
						? 'border-ink-gray-4 bg-surface-gray-2'
						: 'border-surface-gray-3 bg-surface-gray-1 hover:bg-surface-gray-2'
				"
				@click="pick_files"
				@dragover.prevent="dragging = true"
				@dragleave.prevent="dragging = false"
				@drop.prevent="on_drop"
			>
				<svg
					viewBox="0 0 24 24"
					fill="none"
					stroke="currentColor"
					stroke-width="1.5"
					class="size-8 text-ink-gray-3"
				>
					<path d="M12 16V4m0 0 4 4m-4-4L8 8" stroke-linecap="round" stroke-linejoin="round" />
					<path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" stroke-linecap="round" />
				</svg>
				<div class="text-p-medium text-ink-gray-6">{{ __("Faites glisser des fichiers ici") }}</div>
				<div class="text-p-sm text-ink-gray-4">
					{{ __("pdf, jpg, jpeg, png, tif, tiff ou xlsx") }}
				</div>
				<Button variant="solid" size="sm" class="mt-2" @click.stop="pick_files">
					{{ __("Choisir des documents") }}
				</Button>
			</div>
			<input ref="file_input" type="file" multiple class="hidden" :accept="ALLOWED.map((ext) => '.' + ext).join(',')" @change="on_pick" />

			<!-- File queue -->
			<div
				v-if="items.length"
				class="mt-6 divide-y divide-surface-gray-2 rounded-lg border border-surface-gray-2 bg-surface-white"
			>
				<div v-for="item in items" :key="item.id" class="flex items-center gap-4 px-4 py-3">
					<div class="min-w-0 flex-1">
						<div class="truncate text-p-medium text-ink-gray-9">{{ item.name }}</div>
						<div class="text-p-sm text-ink-gray-5">{{ fmt_size(item.size) }}</div>
					</div>
					<div class="w-40 shrink-0">
						<Progress :value="item.progress" />
					</div>
					<div class="w-24 shrink-0 text-center" :title="item.error || ''">
						<Badge
							v-if="status_of(item)"
							variant="subtle"
							size="sm"
							:theme="status_of(item).theme"
							:label="status_of(item).label"
						/>
					</div>
					<Button
						variant="ghost"
						:label="__('Retirer')"
						:disabled="item.status === 'uploading' || sending"
						@click="remove_item(item)"
					/>
				</div>
			</div>

			<!-- Mensuelle workbook preview: one row per monthly sheet -->
			<div v-if="preview_count" class="mt-6 space-y-4">
				<div
					v-for="(preview, file_url) in previews"
					:key="file_url"
					class="rounded-lg border border-surface-gray-2 bg-surface-white"
				>
					<div class="flex items-center justify-between border-b border-surface-gray-2 px-4 py-2">
						<div class="text-p-medium text-ink-gray-9">{{ file_url.split('/').pop() }}</div>
						<label class="flex items-center gap-2 text-p-sm text-ink-gray-6">
							<input type="checkbox" v-model="overwrite" />
							{{ __("Remplacer les documents Pending existants") }}
						</label>
					</div>
					<table class="w-full border-collapse text-left">
						<thead>
							<tr class="bg-surface-gray-1 text-p-xs uppercase text-ink-gray-5">
								<th class="px-4 py-2">{{ __("Feuille") }}</th>
								<th class="px-4 py-2">{{ __("Mois") }}</th>
								<th class="px-4 py-2">{{ __("Layout") }}</th>
								<th class="px-4 py-2">{{ __("Mensuelle") }}</th>
								<th class="px-4 py-2">{{ __("Declaration (Entries)") }}</th>
								<th class="px-4 py-2">{{ __("Erreurs") }}</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-surface-gray-2">
							<tr v-for="sheet in preview.sheets" :key="sheet.sheet">
								<td class="px-4 py-2 text-p-sm text-ink-gray-9">{{ sheet.sheet }}</td>
								<td class="px-4 py-2 text-p-sm text-ink-gray-7">{{ sheet.month }}</td>
								<td class="px-4 py-2 text-p-sm text-ink-gray-7">{{ sheet.layout }}</td>
								<td class="px-4 py-2 text-p-sm">
									<Badge
										variant="subtle"
										size="sm"
										:theme="sheet_status_theme(sheet)"
										:label="sheet.existing_mensuelle ? sheet.existing_mensuelle + ' (' + sheet.existing_status + ')' : '—'"
									/>
								</td>
								<td class="px-4 py-2 text-p-sm text-ink-gray-7">
									{{ sheet.declaration ? sheet.declaration + ' (' + sheet.declaration_status + ')' : '—' }}
								</td>
								<td class="px-4 py-2 text-p-sm" :class="sheet.errors.length ? 'text-ink-red-6' : 'text-ink-gray-5'">
									{{ sheet.errors.length ? sheet.errors.join(' ; ') : '—' }}
								</td>
							</tr>
						</tbody>
					</table>
				</div>
				<Button variant="solid" :label="__('Importer les declarations')" :loading="importing" :disabled="!can_import" @click="import_workbooks" />
			</div>

			<!-- Actions -->
			<div class="mt-6 flex items-center gap-3">
				<Button
					variant="solid"
					:label="is_mensuelle ? __('Analyser') : __('Envoyer')"
					:loading="sending"
					:disabled="!can_send"
					@click="send"
				/>
				<Button
					variant="subtle"
					:label="__('Annuler')"
					:disabled="!can_cancel || sending"
					@click="cancel"
				/>
				<span v-if="summary" class="text-p-sm text-ink-gray-5">{{ summary }}</span>
				<Button
					v-if="open_list_doctype"
					variant="ghost"
					:label="__('Ouvrir la liste')"
					@click="open_list(open_list_doctype)"
				/>
			</div>
		</div>
	</div>
</template>
