<!-- Account autocomplete component for entries lines grid.
     Renders a text input with code · libelle display, 250ms debounced search,
     keyboard navigation, and blur revert. The dropdown is teleported to <body>
     as a manual popover: the browser's top layer keeps it above every
     z-index of the page (the island root's stacking context used to sit above
     the old z-index 9999 dropdown, letting page elements paint over it), and
     it carries inline literal styles with CSS-var fallbacks because the
     island's design tokens do not reach the body. staticMode turns the server
     search off: the options prop is the whole list, even when it is empty. -->
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
	// static list mode: ONLY the options prop is ever offered, even when it is
	// empty — searchMethod is never called and an empty list reads "Aucune
	// opération de trésorerie" (Trésorerie cell of the entries grids)
	staticMode: { type: Boolean, default: false },
	// staticMode empty-list text override: the Trésorerie loader puts its
	// failure message here; the default is the plain no-operation row
	emptyMessage: { type: String, default: "" },
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
const hovered_index = ref(-1);
const dropdown_style = ref({});
const selected_label = ref("");

let debounce_timer = null;

// Inline literal styles with CSS-var fallbacks: outside the island root the
// frappe-ui design tokens are not defined, so the teleported dropdown cannot
// rely on token classes. The hovered row and the keyboard-highlighted row
// share the same background; hover is visual only — it never moves the
// keyboard highlight that Enter selects.
const DROPDOWN_HEIGHT = 220;
const ROW_STYLE = { padding: "6px 12px", cursor: "pointer" };
const ROW_ACTIVE_STYLE = { ...ROW_STYLE, background: "var(--surface-gray-2, #f3f3f3)" };
const NOTE_STYLE = { padding: "8px 12px", fontSize: "12px", color: "var(--ink-gray-5, #7c7c7c)" };
const ERROR_STYLE = { padding: "8px 12px", fontSize: "12px", color: "var(--ink-red-6, #e03434)" };

const empty_text = computed(() => {
	if (props.staticMode) return props.emptyMessage || __("Aucune opération de trésorerie");
	return __("Aucun résultat");
});

function label_for_value(val) {
	// staticMode always reads its label from the options prop, even when it is
	// still empty — never a Chart of Account lookup for a Trésorerie name
	const list = props.staticMode
		? props.options || []
		: props.options && props.options.length
			? props.options
			: null;
	if (!list) return null;
	const found = list.find((o) => o.value === val);
	return found ? found.label : String(val);
}

// Synchronize label with modelValue
watch(
	() => props.modelValue,
	(val) => {
		if (!val) {
			input_text.value = "";
			selected_label.value = "";
			return;
		}
		const label = label_for_value(val);
		if (label !== null) {
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

// the static list may arrive after the value (async loader): re-sync the label
watch(
	() => props.options,
	() => {
		if (!props.staticMode || !props.modelValue) return;
		const label = label_for_value(props.modelValue);
		if (label !== null) {
			selected_label.value = label;
			input_text.value = label;
		}
	}
);

function update_dropdown_position() {
	if (!input_ref.value) return;
	const rect = input_ref.value.getBoundingClientRect();
	const dropdown_height = DROPDOWN_HEIGHT;
	const space_below = window.innerHeight - rect.bottom;
	const open_up = space_below < dropdown_height && rect.top > dropdown_height;
	dropdown_style.value = {
		// pinned to the input's viewport rect; `inset: auto` and `margin: 0`
		// cancel the popover UA defaults (inset: 0, margin: auto)
		position: "fixed",
		inset: "auto",
		margin: "0",
		top: open_up ? `${rect.top - dropdown_height - 4}px` : `${rect.bottom + 4}px`,
		left: `${rect.left}px`,
		width: `${Math.max(rect.width, 260)}px`,
		maxHeight: `${dropdown_height}px`,
		zIndex: 9999, // fallback only: the top layer needs no z-index
		boxSizing: "border-box",
		lineHeight: "1.4",
		// literal styles with CSS-var fallbacks — the island's Tailwind tokens
		// do not reach an element teleported outside the island root
		background: "var(--surface-white, #fff)",
		color: "var(--ink-gray-8, #1f272e)",
		border: "1px solid var(--outline-gray-2, #d1d8dd)",
		borderRadius: "6px",
		boxShadow: "0 4px 12px rgba(0, 0, 0, 0.15)",
		fontSize: "13px",
		padding: "4px 0",
		overflowY: "auto",
	};
}

// The Popover API moves the dropdown to the browser's top layer, above every
// z-index of the desk; both calls are guarded, the fallback being the plain
// fixed-position card with its fallback z-index (a browser without the API
// renders [popover] as a normal element and v-show keeps it hidden when
// closed).
function show_top_layer(el) {
	try {
		if (el && typeof el.showPopover === "function") el.showPopover();
	} catch (error) {
		// Already showing (or the API refusing): the dropdown is visible either way.
	}
}

function hide_top_layer(el) {
	try {
		if (el && typeof el.hidePopover === "function") el.hidePopover();
	} catch (error) {
		// Already hidden.
	}
}

function open_dropdown() {
	if (props.disabled || props.readOnly) return;
	update_dropdown_position();
	is_open.value = true;
	hovered_index.value = -1;
	show_top_layer(dropdown_ref.value);
	window.addEventListener("scroll", update_dropdown_position, true);
	window.addEventListener("resize", update_dropdown_position);
}

function close_dropdown() {
	is_open.value = false;
	highlighted_index.value = -1;
	hovered_index.value = -1;
	hide_top_layer(dropdown_ref.value);
	window.removeEventListener("scroll", update_dropdown_position, true);
	window.removeEventListener("resize", update_dropdown_position);
}

async function fetch_options(txt = "") {
	// staticMode: the options prop is the whole list — filter it, even when it
	// is empty; the server search is never called
	if (props.staticMode) {
		const query = (txt || "").toLowerCase().trim();
		const source = props.options || [];
		options_list.value = query
			? source.filter(
					(o) =>
						(o.label && o.label.toLowerCase().includes(query)) ||
						(o.value && o.value.toLowerCase().includes(query))
			  )
			: [...source];
		highlighted_index.value = options_list.value.length ? 0 : -1;
		return;
	}

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
	hide_top_layer(dropdown_ref.value); // out of the top layer before the node goes away
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

		<!-- Teleported to <body> as a manual popover: the top layer keeps it
		     above every z-index of the page, `manual` keeps light-dismiss off
		     (the component owns its closing) and takes no focus. v-show (not
		     v-if) keeps the node mounted so hidePopover can always run — a
		     closed popover is display:none anyway. -->
		<Teleport to="body">
			<div v-show="is_open" ref="dropdown_ref" popover="manual" :style="dropdown_style">
				<div v-if="loading" :style="NOTE_STYLE">
					{{ __("Recherche...") }}
				</div>
				<div v-else-if="search_error" :style="ERROR_STYLE">
					{{ __("Erreur: {0}", [search_error]) }}
				</div>
				<div v-else-if="!options_list.length" :style="NOTE_STYLE">
					{{ empty_text }}
				</div>
				<template v-else>
					<div
						v-for="(opt, idx) in options_list"
						:key="opt.value"
						:data-index="idx"
						:style="
							idx === highlighted_index || idx === hovered_index ? ROW_ACTIVE_STYLE : ROW_STYLE
						"
						@mouseenter="hovered_index = idx"
						@mouseleave="hovered_index = -1"
						@mousedown.prevent="select_option(opt)"
					>
						{{ opt.label }}
					</div>
				</template>
			</div>
		</Teleport>
	</div>
</template>
