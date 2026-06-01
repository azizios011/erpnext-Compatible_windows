// Tunisian Accounting desk routing — Treatments opens a new Entry of Entries (invoice entry).

const ENTRY_OF_ENTRIES_NEW_ROUTE = ["Form", "Entry of Entries", "new-entry-of-entries-1"];

function route_is_treatments_workspace() {
	const route = frappe.get_route() || [];
	const normalized = route.map((part) => String(part).toLowerCase());

	if (normalized.includes("entry of entries") || normalized.includes("entry-of-entries")) {
		return false;
	}

	return (
		(route[0] === "Workspaces" && route.includes("Treatments")) ||
		(route[0] === "workspace" && route[1] === "Treatments") ||
		(route.length === 1 && route[0] === "Treatments")
	);
}

function route_is_entry_of_entries_list() {
	const route = frappe.get_route() || [];
	return route[0] === "List" && route[1] === "Entry of Entries";
}

function open_new_entry_of_entries() {
	if (frappe.get_route().join("/") === ENTRY_OF_ENTRIES_NEW_ROUTE.join("/")) {
		return;
	}
	frappe.set_route(...ENTRY_OF_ENTRIES_NEW_ROUTE);
}

function setup_tunisian_accounting_desk_routes() {
	if (!frappe.router || frappe.tunisian_accounting_desk_routes_setup) {
		return;
	}

	frappe.tunisian_accounting_desk_routes_setup = true;
	frappe.router.on("change", () => {
		if (route_is_treatments_workspace() || route_is_entry_of_entries_list()) {
			open_new_entry_of_entries();
		}
	});
}

if (frappe.router) {
	setup_tunisian_accounting_desk_routes();
} else {
	$(document).on("app_ready", setup_tunisian_accounting_desk_routes);
}
