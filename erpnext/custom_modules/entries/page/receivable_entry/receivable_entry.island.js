import { mountVueIsland } from "@framework/ui/island";

import Page from "./receivable_entry.vue";

export const mount = (el, context) => mountVueIsland(el, { ...context, component: Page });
