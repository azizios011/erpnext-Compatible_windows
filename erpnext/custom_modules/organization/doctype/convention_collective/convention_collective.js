// Nombre d'heures is computed from Nombre de jours (8h/day, see the
// controller's HEURES_PAR_JOUR) — recomputed live, never typed.
frappe.ui.form.on("Convention Collective", {
	nombre_jours(frm) {
		frm.set_value("nombre_heures", flt(frm.doc.nombre_jours) * 8);
	},
});
