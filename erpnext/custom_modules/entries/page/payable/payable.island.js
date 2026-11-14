import { mountVueIsland } from "@framework/ui/island";

import Page from "./payable.vue";

export const mount = (el, context) => mountVueIsland(el, { ...context, component: Page });
