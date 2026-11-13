import { mountVueIsland } from "@framework/ui/island";

import Page from "./plan_comptable.vue";

export const mount = (el, context) => mountVueIsland(el, { ...context, component: Page });
