<!-- Account autocomplete component for entries lines grid.
     Renders a text input with code · libelle display, 250ms debounced search,
     fixed/teleported dropdown, keyboard navigation, and blur revert. -->
<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";

const props = defineProps({
	modelValue: { type: [String, Number], default: "" },
	placeholder: { type: String, default: "code · libellé" },
	searchMethod: {
		type: String,
		default: "erpnext.custom_modules.organization.tiers_accounts.compte_search",
	},
	options: { type: Array, default: null }, // static options (e.g. for Trésorerie)
	disabled: { type: Boolean, default: false },
	readOnly: { type: Boolean, default: false },
});

const emit = defineEmits(["update:modelValue", "select", "change"]);

const frappe = window.frappe;
const __ = window.__ || ((s) => s);

const input_ref = ref(null);
const dropdown_ref = ref(null);
const input_text = ref("");
const is_open = ref(false);
const options_list = ref([]);
const loading = ref(false);
const search_error = ref(null);
const highlighted_index = ref(-1);
const dropdown_style = ref({});
const selected_label = ref("");

let debounce_timer = null;

// Synchronize label with modelValue
watch(
	() => props.modelValue,
	(val) => {
		if (!val) {
			input_text.value = "";
			selected_label.value = "";
			return;
		}
		// If static options are provided
		if (props.options && props.options.length) {
			const found = props.options.find((o) => o.value === val);
			const label = found ? found.label : String(val);
			selected_label.value = label;
			input_text.value = label;
			return;
		}
		// If already matching current label
		if (selected_label.value && input_text.value === selected_label.value) {
			return;
		}
		// Lookup account details
		frappe.db.get_value("Chart of Account", val, ["account_number", "account_name"]).then((r) => {
			const values = r?.message || {};
			if (values.account_number || values.account_name) {
				const label = `${values.account_number || ""} · ${values.account_name || ""}`;
				selected_label.value = label;
				input_text.value = label;
			} else {
				selected_label.value = String(val);
				input_text.value = String(val);
			}
		});
	},
	{ immediate: true }
);

function update_dropdown_position() {
	if (!input_ref.value) return;
	const rect = input_ref.value.getBoundingClientRect();
	const dropdown_height = 220;
	const space_below = window.innerHeight - rect.bottom;
	const open_up = space_below < dropdown_height && rect.top > dropdown_height;
	dropdown_style.value = {
		position: "fixed",
		top: open_up ? `${rect.top - dropdown_height - 4}px` : `${rect.bottom + 4}px`,
		left: `${rect.left}px`,
		width: `${Math.max(rect.width, 260)}px`,
		maxHeight: `${dropdown_height}px`,
		zIndex: 9999,
	};
}

function open_dropdown() {
	if (props.disabled || props.readOnly) return;
	update_dropdown_position();
	is_open.value = true;
	window.addEventListener("scroll", update_dropdown_position, true);
	window.addEventListener("resize", update_dropdown_position);
}

function close_dropdown() {
	is_open.value = false;
	highlighted_index.value = -1;
	window.removeEventListener("scroll", update_dropdown_position, true);
	window.removeEventListener("resize", update_dropdown_position);
}

async function fetch_options(txt = "") {
	if (props.options && props.options.length) {
		const query = (txt || "").toLowerCase().trim();
		options_list.value = query
			? props.options.filter(
					(o) =>
						(o.label && o.label.toLowerCase().includes(query)) ||
						(o.value && o.value.toLowerCase().includes(query))
			  )
			: [...props.options];
		highlighted_index.value = options_list.value.length ? 0 : -1;
		return;
	}

	loading.value = true;
	search_error.value = null;
	try {
		const rows = await frappe.xcall(props.searchMethod, {
			doctype: "Chart of Account",
			txt: txt || "",
			searchfield: "name",
			start: 0,
			page_len: 50,
		});
		options_list.value = (rows || []).map((r) => ({
			label: `${r.account_number} · ${r.account_name}`,
			value: r.name,
			account_number: r.account_number,
			account_name: r.account_name,
		}));
		highlighted_index.value = options_list.value.length ? 0 : -1;
		if (!options_list.value.length) {
			console.error("compte_search returned no results for query:", txt);
		}
	} catch (err) {
		console.error("compte_search error:", err);
		search_error.value = err?.message || String(err);
		options_list.value = [];
	} finally {
		loading.value = false;
	}
}

function on_focus() {
	if (props.disabled || props.readOnly) return;
	open_dropdown();
	fetch_options(""); // opening/focusing with an empty field shows the first accounts
}

function on_input(event) {
	const val = event.target.value;
	input_text.value = val;
	if (!is_open.value) open_dropdown();
	else update_dropdown_position();

	if (debounce_timer) clearTimeout(debounce_timer);
	debounce_timer = setTimeout(() => {
		fetch_options(val);
	}, 250);
}

function select_option(opt) {
	if (!opt) return;
	selected_label.value = opt.label;
	input_text.value = opt.label;
	close_dropdown();
	emit("update:modelValue", opt.value);
	emit("select", opt);
	emit("change", opt.value);
}

function on_blur() {
	// on blur the text reverts to the selected account's label
	input_text.value = selected_label.value;
	close_dropdown();
}

function scroll_highlighted_into_view() {
	nextTick(() => {
		if (!dropdown_ref.value) return;
		const el = dropdown_ref.value.querySelector(`[data-index="${highlighted_index.value}"]`);
		if (el) el.scrollIntoView({ block: "nearest" });
	});
}

function on_keydown(event) {
	if (!is_open.value) {
		if (event.key === "ArrowDown" || event.key === "Enter") {
			open_dropdown();
			fetch_options("");
			event.preventDefault();
		}
		return;
	}

	if (event.key === "ArrowDown") {
		event.preventDefault();
		if (options_list.value.length) {
			highlighted_index.value = (highlighted_index.value + 1) % options_list.value.length;
			scroll_highlighted_into_view();
		}
	} else if (event.key === "ArrowUp") {
		event.preventDefault();
		if (options_list.value.length) {
			highlighted_index.value =
				(highlighted_index.value - 1 + options_list.value.length) % options_list.value.length;
			scroll_highlighted_into_view();
		}
	} else if (event.key === "Enter") {
		event.preventDefault();
		if (highlighted_index.value >= 0 && highlighted_index.value < options_list.value.length) {
			select_option(options_list.value[highlighted_index.value]);
		}
	} else if (event.key === "Escape") {
		event.preventDefault();
		input_text.value = selected_label.value;
		close_dropdown();
	}
}

onBeforeUnmount(() => {
	if (debounce_timer) clearTimeout(debounce_timer);
	window.removeEventListener("scroll", update_dropdown_position, true);
	window.removeEventListener("resize", update_dropdown_position);
});
</script>

<template>
	<div class="relative w-full">
		<input
			ref="input_ref"
			type="text"
			:value="input_text"
			:placeholder="placeholder"
			:disabled="disabled || readOnly"
			class="h-7 w-full rounded border border-surface-gray-3 bg-surface-white px-2 text-p-sm text-ink-gray-9 placeholder:text-ink-gray-4 focus:border-ink-gray-5 focus:outline-none focus:ring-1 focus:ring-ink-gray-5 disabled:bg-surface-gray-1 disabled:text-ink-gray-5"
			@focus="on_focus"
			@input="on_input"
			@blur="on_blur"
			@keydown="on_keydown"
		/>

		<Teleport to="body">
			<div
				v-if="is_open"
				ref="dropdown_ref"
				:style="dropdown_style"
				class="overflow-y-auto rounded-md border border-surface-gray-3 bg-surface-white py-1 shadow-lg"
			>
				<div v-if="loading" class="px-3 py-2 text-p-xs text-ink-gray-5">
					{{ __("Recherche...") }}
				</div>
				<div v-else-if="search_error" class="px-3 py-2 text-p-xs text-ink-red-6">
					{{ __("Erreur: {0}", [search_error]) }}
				</div>
				<div v-else-if="!options_list.length" class="px-3 py-2 text-p-xs text-ink-gray-5">
					{{ __("Aucun résultat") }}
				</div>
				<template v-else>
					<div
						v-for="(opt, idx) in options_list"
						:key="opt.value"
						:data-index="idx"
						class="cursor-pointer px-3 py-1.5 text-p-sm transition-colors"
						:class="idx === highlighted_index ? 'bg-surface-gray-2 text-ink-gray-9' : 'text-ink-gray-7 hover:bg-surface-gray-1'"
						@mousedown.prevent="select_option(opt)"
					>
						{{ opt.label }}
					</div>
				</template>
			</div>
		</Teleport>
	</div>
</template>
