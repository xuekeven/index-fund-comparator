import { defaultSchema } from "rehype-sanitize";

export const markdownPresetClasses = [
  "md-text-muted",
  "md-text-green",
  "md-text-red",
  "md-align-center",
  "md-align-right",
  "md-small",
  "md-callout",
];

export const markdownSanitizeSchema = {
  ...defaultSchema,
  tagNames: Array.from(new Set([...(defaultSchema.tagNames ?? []), "mark"])),
  attributes: {
    ...defaultSchema.attributes,
    "*": [
      ...(defaultSchema.attributes?.["*"] ?? []),
      ["className", ...markdownPresetClasses],
    ],
  },
};
