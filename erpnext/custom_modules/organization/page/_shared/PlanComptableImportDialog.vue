<!-- Plan comptable — shared xlsx import dialog.

     Consumed by BOTH island pages (plan_comptable.vue and entreprise_view.vue)
     through a relative import. It lives in page/_shared/, a folder WITHOUT a
     `<name>.json`, so the island discovery (frappe-Compatible_windows/ui/vite/
     island/pages.js — readPage skips any page folder with no json beside it)
     never treats it as a page of its own.

     Flow: drop zone (.xlsx only, uploaded as a PRIVATE File through the
     framework's useUploader — the same engine behind FileUploadDialog used by
     the Entreprise documents dialog) → import_plan_comptable dry_run=1
     ("Vérification…") → summary with per-class mini bars → either the error
     list (no import button) or "Importer N comptes" → dry_run=0 → success
     state + emits "imported" with the backend result dict. Server errors stay
     inside the dialog. -->
<script setup>
import { computed, ref, watch } from "vue";
import { Button, Dialog, Spinner } from "frappe-ui";
import { useUploader } from "@framework/ui/FileUpload";

const frappe = window.frappe;
const __ = window.__;

const props = defineProps({
	entreprise: { type: String, default: "" },
});
const open = defineModel("open", { type: Boolean, default: false });
const emit = defineEmits(["imported"]);

const IMPORT_METHOD = "erpnext.custom_modules.organization.plan_comptable.import_plan_comptable";
const ROOT_CLASSES = ["1", "2", "3", "4", "5", "6", "7"];
const ROOT_CLASS_NAMES = {
	1: "Capitaux",
	2: "Immobilisations",
	3: "Stock et Encours",
	4: "Tiers",
	5: "Financiers",
	6: "Charges",
	7: "Produits",
};

// choose | uploading | checking | summary | importing | done
const step = ref("choose");
const file_url = ref("");
const file_name = ref("");
const result = ref(null); // dry_run=1 summary (and fallback for a refused import)
const final_result = ref(null); // dry_run=0 result
const dialog_errors = ref([]);
const drag_over = ref(false);
const file_input = ref(null);

const uploader = useUploader({
	multiple: false,
	isPrivate: true,
	restrictions: { allowed_file_types: [".xlsx"] },
});

watch(open, (isOpen) => {
	if (isOpen) reset();
});

function reset() {
	step.value = "choose";
	file_url.value = "";
	file_name.value = "";
	result.value = null;
	final_result.value = null;
	dialog_errors.value = [];
	drag_over.value = false;
	uploader.clear();
	if (file_input.value) file_input.value.value = "";
}

// ── upload ───────────────────────────────────────────────────────────────────
function pick_file() {
	file_input.value?.click();
}

function on_change(event) {
	const files = event.target?.files;
	if (files?.length) void handle_files(files);
	event.target.value = "";
}

function on_drop(event) {
	drag_over.value = false;
	const files = event.dataTransfer?.files;
	if (files?.length) void handle_files(files);
}

async function handle_files(files) {
	dialog_errors.value = [];
	const file = files[0];
	if (!file) return;
	if (!file.name.toLowerCase().endsWith(".xlsx")) {
		dialog_errors.value = [__("Le plan comptable doit être un fichier Excel .xlsx.")];
		return;
	}
	uploader.clear();
	uploader.add([file]);
	step.value = "uploading";
	try {
		const results = await uploader.commit();
		const uploaded = results?.[0];
		if (!uploaded?.file_url) {
			throw new Error(__("L'envoi du fichier a échoué."));
		}
		file_url.value = uploaded.file_url;
		file_name.value = uploaded.file_name || file.name;
		await run_check();
	} catch (error) {
		dialog_errors.value = collect_upload_errors(error);
		uploader.clear();
		step.value = "choose";
	}
}

function collect_upload_errors(error) {
	const messages = [...(uploader.errors.value || [])];
	const item_error = uploader.items.find((item) => item.error)?.error;
	if (item_error) messages.push(item_error);
	if (!messages.length) messages.push(error?.message || String(error));
	return messages;
}

// ── dry run ──────────────────────────────────────────────────────────────────
async function run_check() {
	step.value = "checking";
	dialog_errors.value = [];
	try {
		result.value = await frappe.xcall(IMPORT_METHOD, {
			entreprise: props.entreprise,
			file_url: file_url.value,
			dry_run: 1,
		});
		step.value = "summary";
	} catch (error) {
		dialog_errors.value = [error?.message || String(error)];
		step.value = "choose";
	}
}

// ── import ───────────────────────────────────────────────────────────────────
async function run_import() {
	step.value = "importing";
	dialog_errors.value = [];
	try {
		final_result.value = await frappe.xcall(IMPORT_METHOD, {
			entreprise: props.entreprise,
			file_url: file_url.value,
			dry_run: 0,
		});
		if (!final_result.value?.ok) {
			// defensive: the import refused where the check had passed
			result.value = final_result.value;
			step.value = "summary";
			return;
		}
		emit("imported", final_result.value);
		step.value = "done";
	} catch (error) {
		dialog_errors.value = [error?.message || String(error)];
		step.value = "summary";
	}
}

// ── display ──────────────────────────────────────────────────────────────────
const summary = computed(() => final_result.value || result.value);
const has_errors = computed(() => (summary.value?.error_count || 0) > 0);
const importable_count = computed(() =>
	Math.max(0, (summary.value?.total || 0) - (summary.value?.deja_existants || 0))
);

const stat_rows = computed(() => [
	{ label: __("Comptes dans le fichier"), value: summary.value?.total ?? 0 },
	{ label: __("Regroupements"), value: summary.value?.regroupements ?? 0 },
	{ label: __("Comptables"), value: summary.value?.comptables ?? 0 },
	{ label: __("Standard (verrouillés)"), value: summary.value?.standard ?? 0 },
	{ label: __("Personnalisés (modifiables)"), value: summary.value?.personnalises ?? 0 },
	{ label: __("Déjà existants (ignorés)"), value: summary.value?.deja_existants ?? 0 },
]);

const classe_rows = computed(() => {
	const par = summary.value?.par_classe || {};
	const rows = ROOT_CLASSES.map((c) => ({
		key: c,
		label: `${c} — ${__(ROOT_CLASS_NAMES[c])}`,
		count: par[c] || 0,
	}));
	const other = Object.entries(par)
		.filter(([c]) => !ROOT_CLASSES.includes(c))
		.reduce((sum, [, n]) => sum + n, 0);
	rows.push({ key: "other", label: __("Non attribués"), count: other });
	const max = Math.max(1, ...rows.map((row) => row.count));
	for (const row of rows) {
		row.width = Math.round((row.count / max) * 100);
	}
	return rows;
});

function open_plan_comptable() {
	open.value = false;
	frappe.set_route("plan-comptable", { entreprise: props.entreprise });
}
</script>

<template>
	<Dialog v-model="open" :options="{ title: __('Importer un plan comptable') }">
		<template #body>
			<p v-if="entreprise" class="mb-4 text-p-sm text-ink-gray-6">
				{{ __("Entreprise {0}", [entreprise]) }}
			</p>

			<!-- Server errors, always inside the dialog -->
			<div v-if="dialog_errors.length" class="mb-4 rounded-lg border border-surface-red-3 bg-surface-red-1 p-3">
				<div class="flex items-center gap-2 text-p-sm font-semibold text-ink-red-8">
					<svg class="size-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
						<line x1="12" y1="9" x2="12" y2="13" />
						<line x1="12" y1="17" x2="12.01" y2="17" />
					</svg>
					<span>{{ __("Erreur") }}</span>
				</div>
				<ul class="mt-1 list-disc space-y-0.5 pl-5 text-p-sm text-ink-red-7">
					<li v-for="(message, index) in dialog_errors" :key="index">{{ message }}</li>
				</ul>
			</div>

			<!-- Choose the file -->
			<div v-if="step === 'choose' || step === 'uploading'">
				<div
					v-if="!uploader.items.length"
					class="cursor-pointer rounded-lg border border-dashed border-surface-gray-3 bg-surface-gray-1/40 p-6 text-center transition-colors hover:bg-surface-gray-1"
					:class="{ 'border-ink-gray-5 bg-surface-gray-1': drag_over }"
					@click="pick_file"
					@dragover.prevent="drag_over = true"
					@dragleave.prevent="drag_over = false"
					@drop.prevent="on_drop"
				>
					<div class="mx-auto mb-3 flex size-11 items-center justify-center rounded-lg bg-surface-gray-2 text-ink-gray-5">
						<svg class="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75">
							<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
							<polyline points="17 8 12 3 7 8" />
							<line x1="12" y1="3" x2="12" y2="15" />
						</svg>
					</div>
					<p class="text-p-sm font-medium text-ink-gray-7">
						{{ __("Déposez le fichier Excel ici") }}
					</p>
					<p class="mt-0.5 text-xs text-ink-gray-5">
						{{ __("ou") }}
					</p>
					<div class="mt-2">
						<Button variant="subtle" :label="__('Parcourir')" @click.stop="pick_file" />
					</div>
					<p class="mt-3 text-xs text-ink-gray-5">
						{{ __("Fichier Excel avec les colonnes Code, Libelle, Nature, Sens (une feuille par classe)") }}
					</p>
				</div>
				<div v-else class="rounded-lg border border-surface-gray-2 bg-surface-gray-1/60 p-4">
					<div class="flex items-center gap-3">
						<Spinner v-if="step === 'uploading'" class="size-4 shrink-0" />
						<svg v-else class="size-5 shrink-0 text-ink-gray-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
							<polyline points="14 2 14 8 20 8" />
						</svg>
						<div class="min-w-0 flex-1">
							<div class="truncate text-p-sm font-semibold text-ink-gray-9">
								{{ file_name || uploader.items[0]?.name }}
							</div>
							<div class="text-xs text-ink-gray-5">
								{{ step === "uploading" ? __("Envoi du fichier...") : __("Fichier reçu.") }}
							</div>
						</div>
					</div>
					<div v-if="step === 'uploading'" class="mt-3 h-1.5 w-full overflow-hidden rounded bg-surface-gray-2">
						<div class="h-1.5 rounded bg-surface-gray-5 transition-all" :style="{ width: `${Math.round(uploader.progress * 100)}%` }" />
					</div>
				</div>
				<input ref="file_input" type="file" accept=".xlsx" class="hidden" @change="on_change" />
			</div>

			<!-- Checking -->
			<div v-else-if="step === 'checking'" class="flex items-center gap-3 rounded-lg border border-surface-gray-2 bg-surface-gray-1/60 p-4">
				<Spinner class="size-4 shrink-0" />
				<span class="text-p-sm text-ink-gray-7">{{ __("Vérification…") }}</span>
			</div>

			<!-- Summary (dry run) -->
			<div v-else-if="step === 'summary' && summary" class="space-y-4">
				<div class="space-y-3 rounded-lg border border-surface-gray-2 bg-surface-gray-1/40 p-4">
					<div class="grid grid-cols-1 gap-x-8 gap-y-2 sm:grid-cols-2">
						<div v-for="row in stat_rows" :key="row.label" class="flex items-center justify-between gap-4 text-p-sm">
							<span class="text-ink-gray-6">{{ row.label }}</span>
							<span class="font-semibold text-ink-gray-9">{{ row.value }}</span>
						</div>
					</div>

					<div class="space-y-1.5 border-t border-surface-gray-2 pt-3">
						<div v-for="row in classe_rows" :key="row.key" class="flex items-center gap-2 text-xs">
							<span class="w-44 shrink-0 truncate text-ink-gray-6">{{ row.label }}</span>
							<div class="h-2 min-w-0 flex-1 overflow-hidden rounded bg-surface-gray-2">
								<div class="h-2 rounded bg-surface-gray-5" :style="{ width: `${row.width}%` }" />
							</div>
							<span class="w-8 shrink-0 text-end font-medium text-ink-gray-7">{{ row.count }}</span>
						</div>
					</div>

					<p class="border-t border-surface-gray-2 pt-3 text-xs text-ink-gray-5">
						{{ __("Les comptes existants ne sont jamais modifiés ni supprimés.") }}
					</p>
				</div>

				<div v-if="has_errors" class="rounded-lg border border-surface-red-3 bg-surface-red-1 p-3">
					<div class="flex items-center gap-2 text-p-sm font-semibold text-ink-red-8">
						<svg class="size-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
							<line x1="12" y1="9" x2="12" y2="13" />
							<line x1="12" y1="17" x2="12.01" y2="17" />
						</svg>
						<span>{{ __("{0} erreur(s): import impossible.", [summary.error_count]) }}</span>
					</div>
					<div class="mt-2 max-h-48 overflow-y-auto rounded border border-surface-red-2 bg-surface-white">
						<table class="w-full text-left border-collapse">
							<thead>
								<tr class="border-b border-surface-gray-2 bg-surface-gray-1">
									<th class="px-2.5 py-1.5 text-xs font-semibold text-ink-gray-6">{{ __("Feuille") }}</th>
									<th class="px-2.5 py-1.5 text-xs font-semibold text-ink-gray-6">{{ __("Ligne") }}</th>
									<th class="px-2.5 py-1.5 text-xs font-semibold text-ink-gray-6">{{ __("Code") }}</th>
									<th class="px-2.5 py-1.5 text-xs font-semibold text-ink-gray-6">{{ __("Message") }}</th>
								</tr>
							</thead>
							<tbody class="divide-y divide-surface-gray-2">
								<tr v-for="(error, index) in summary.errors" :key="index">
									<td class="px-2.5 py-1.5 text-xs text-ink-gray-6">{{ error.sheet }}</td>
									<td class="px-2.5 py-1.5 text-xs text-ink-gray-6">{{ error.row ?? "—" }}</td>
									<td class="px-2.5 py-1.5 font-mono text-xs text-ink-gray-7">{{ error.code || "—" }}</td>
									<td class="px-2.5 py-1.5 text-xs text-ink-gray-9">{{ error.message }}</td>
								</tr>
							</tbody>
						</table>
					</div>
				</div>
			</div>

			<!-- Importing -->
			<div v-else-if="step === 'importing'" class="flex items-center gap-3 rounded-lg border border-surface-gray-2 bg-surface-gray-1/60 p-4">
				<Spinner class="size-4 shrink-0" />
				<span class="text-p-sm text-ink-gray-7">{{ __("Import en cours...") }}</span>
			</div>

			<!-- Done -->
			<div v-else-if="step === 'done' && final_result" class="space-y-4">
				<div class="flex items-center gap-2.5 rounded-lg border border-surface-green-3 bg-surface-green-1 px-4 py-3 text-p-sm font-semibold text-ink-green-8">
					<svg class="size-5 shrink-0 text-ink-green-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
						<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
						<polyline points="22 4 12 14.01 9 11.01" />
					</svg>
					<span>{{ __("Import réussi: {0} compte(s) créé(s).", [final_result.inserted]) }}</span>
				</div>
				<div class="grid grid-cols-1 gap-x-8 gap-y-2 rounded-lg border border-surface-gray-2 bg-surface-gray-1/40 p-4 sm:grid-cols-2">
					<div v-for="row in stat_rows" :key="row.label" class="flex items-center justify-between gap-4 text-p-sm">
						<span class="text-ink-gray-6">{{ row.label }}</span>
						<span class="font-semibold text-ink-gray-9">{{ row.value }}</span>
					</div>
				</div>
			</div>
		</template>

		<template #actions>
			<template v-if="step === 'choose' || step === 'uploading'">
				<Button variant="subtle" :label="__('Fermer')" :disabled="step === 'uploading'" @click="open = false" />
			</template>
			<template v-else-if="step === 'summary' && summary">
				<Button variant="ghost" :label="__('Choisir un autre fichier')" @click="reset" />
				<Button
					v-if="!has_errors"
					variant="solid"
					:label="__('Importer {0} comptes', [importable_count])"
					@click="run_import"
				/>
			</template>
			<template v-else-if="step === 'done'">
				<Button variant="subtle" :label="__('Fermer')" @click="open = false" />
				<Button variant="solid" :label="__('Ouvrir le plan comptable')" @click="open_plan_comptable" />
			</template>
		</template>
	</Dialog>
</template>
