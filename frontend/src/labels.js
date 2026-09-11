// Fixed order everywhere — legends, matrix axes, distribution bars — so a class's
// identity never depends on which other classes happen to be present.
export const LABELS = ["bug", "enhancement", "question", "documentation", "security", "other"];

export const labelColor = (label) => `var(--label-${label})`;
