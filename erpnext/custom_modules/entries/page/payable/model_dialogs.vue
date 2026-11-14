<!-- Model dialogs shared by the payable and receivable islands
     (identical copies): "Appel Modele" loads a Journal Model's lines into the
     grid, "Enreg. Modele" saves the grid's accounts and sides as a new model.
     The parent opens them through defineExpose and receives the lines through
     the apply-lines event. -->
<script setup>
import { ref } from "vue";
import { Button, Dialog, FormControl } from "frappe-ui";

const frappe = window.frappe;
const __ = window.__;
const flt = (v) => {
	const n = parseFloat(v);
	return Number.isFinite(n) ? n : 0;
};

const props = defineProps({
	journal: { type: String, default: "" },
	lines: { type: Array, default: () => [] },
});
const emit = defineEmits(["apply-lines"]);

const METHOD = "erpnext.custom_modules.entries.api";

const appel_open = ref(false);
const models = ref([]);
const selected_model = ref("");
const enreg_open = ref(false);
const model_name = ref("");
let saved_lines = [];

function open_appel() {
	if (!props.journal) {
		frappe.msgprint({
			title: __("Appel Modele"),
			message: __("Pick a journal first."),
			indicator: "orange",
		});
		return;
	}
	frappe.xcall(`${METHOD}.get_journal_models`, { journal: props.journal }).then((rows) => {
		models.value = rows || [];
		if (!models.value.length) {
			frappe.msgprint({
				title: __("Appel Modele"),
				message: __("Journal {0} has no Journal Model yet.", [props.journal]),
				indicator: "orange",
			});
			return;
		}
		selected_model.value = (models.value.find((m) => m.is_default) || models.value[0]).name;
		appel_open.value = true;
	});
}

function load_model() {
	frappe.xcall(`${METHOD}.get_journal_model_lines`, { model: selected_model.value }).then((result) => {
		emit("apply-lines", (result && result.lines) || []);
		frappe.show_alert(__("Model {0} loaded.", [selected_model.value]));
		appel_open.value = false;
	});
}

function open_enreg() {
	// the side comes from the column that holds the amount
	const lines = (props.lines || [])
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
	saved_lines = lines;
	model_name.value = __("Model {0}", [frappe.datetime.get_today()]);
	enreg_open.value = true;
}

function save_model() {
	frappe.xcall(`${METHOD}.save_journal_model`, {
		journal: props.journal,
		model_name: model_name.value,
		lines: JSON.stringify(saved_lines),
	}).then(() => {
		frappe.show_alert({
			message: __("Model {0} saved for journal {1}.", [model_name.value, props.journal]),
			indicator: "green",
		});
		enreg_open.value = false;
	});
}

defineExpose({ open_appel, open_enreg });
</script>

<template>
	<Dialog v-model="appel_open" :title="__('Appel Modele')">
		<template #default>
			<FormControl
				v-model="selected_model"
				type="select"
				:label="__('Model')"
				:options="models.map((m) => ({ label: m.model_name || m.name, value: m.name }))"
			/>
		</template>
		<template #actions>
			<Button variant="subtle" :label="__('Annuler')" @click="appel_open = false" />
			<Button variant="solid" :label="__('Charger')" @click="load_model" />
		</template>
	</Dialog>

	<Dialog v-model="enreg_open" :title="__('Enreg. Modele')">
		<template #default>
			<FormControl v-model="model_name" type="data" :label="__('Model Name')" />
		</template>
		<template #actions>
			<Button variant="subtle" :label="__('Annuler')" @click="enreg_open = false" />
			<Button variant="solid" :label="__('Enregistrer')" @click="save_model" />
		</template>
	</Dialog>
</template>
