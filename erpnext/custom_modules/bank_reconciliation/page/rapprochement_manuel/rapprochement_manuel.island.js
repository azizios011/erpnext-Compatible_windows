import { mountVueIsland } from "@framework/ui/island";

import Page from "./rapprochement_manuel.vue";

export const mount = (el, context) => mountVueIsland(el, { ...context, component: Page });
