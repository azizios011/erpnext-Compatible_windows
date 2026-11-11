import { mountVueIsland } from "@framework/ui/island";

import Page from "./envoi_multiple.vue";

export const mount = (el, context) => mountVueIsland(el, { ...context, component: Page });
