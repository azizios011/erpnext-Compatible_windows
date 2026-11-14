<!-- Totals footer shared by the payable-entry and receivable-entry islands
     (identical copies): four cards sticky at the bottom, live-recomputed from
     the grid rows — visible on a new, unsaved entry too. -->
<script setup>
import { computed } from "vue";

const props = defineProps({
	lines: { type: Array, default: () => [] },
	devise: { type: String, default: "" },
});

const flt = (v) => {
	const n = parseFloat(v);
	return Number.isFinite(n) ? n : 0;
};

const active_rows = computed(() =>
	props.lines.filter((line) => line.account || flt(line.debit) || flt(line.credit)).length
);
const total_debit = computed(() => flt(props.lines.reduce((sum, line) => sum + flt(line.debit), 0)));
const total_credit = computed(() => flt(props.lines.reduce((sum, line) => sum + flt(line.credit), 0)));
const solde = computed(() => total_debit.value - total_credit.value);
// green only when the entry balances AND at least one line exists
const solde_ok = computed(() => Math.abs(solde.value) < 0.001 && active_rows.value > 0);

const fmt = (value) => {
	const text = new Intl.NumberFormat("fr-FR", {
		minimumFractionDigits: 3,
		maximumFractionDigits: 3,
	}).format(Number(value) || 0);
	return props.devise ? `${text} ${props.devise}` : text;
};
</script>

<template>
	<div class="sticky bottom-0 z-10 border-t border-surface-gray-2 bg-surface-white px-4 py-2.5">
		<div class="flex gap-3">
			<div class="flex-1 rounded-md border border-surface-gray-2 bg-surface-gray-1 px-3 py-1.5">
				<div class="text-xs text-ink-gray-5">{{ __("Mvt Compte") }}</div>
				<div class="text-sm font-bold text-ink-gray-9">{{ active_rows }}</div>
			</div>
			<div class="flex-1 rounded-md border border-surface-gray-2 bg-surface-gray-1 px-3 py-1.5">
				<div class="text-xs text-ink-gray-5">{{ __("Tot Debit") }}</div>
				<div class="text-sm font-bold text-ink-green-7">{{ fmt(total_debit) }}</div>
			</div>
			<div class="flex-1 rounded-md border border-surface-gray-2 bg-surface-gray-1 px-3 py-1.5">
				<div class="text-xs text-ink-gray-5">{{ __("Tot Credit") }}</div>
				<div class="text-sm font-bold text-ink-red-7">{{ fmt(total_credit) }}</div>
			</div>
			<div class="flex-1 rounded-md border border-surface-gray-2 bg-surface-gray-1 px-3 py-1.5">
				<div class="text-xs text-ink-gray-5">{{ __("Solde") }}</div>
				<div class="text-sm font-bold" :class="solde_ok ? 'text-ink-green-7' : 'text-ink-red-7'">
					{{ fmt(solde) }}
				</div>
			</div>
		</div>
	</div>
</template>
