// The default library and the names that belong to it. Its stored name is the same in every
// language, so switching the language never creates a second library.
import { DEFAULT_LIBRARY_NAME } from "./config.js";
import { t } from "./i18n.js";
import { DICTIONARIES } from "./strings.js";

// A name is compared under the Turkish and the English lowercasing, so a capital I with a dot
// above (U+0130) and a plain capital I give the same name, as they should for the default library.
const LOWERCASE_RULES = ["tr", "en"];

function lowercasings(name) {
  const trimmed = name.trim();
  return LOWERCASE_RULES.map((rule) => trimmed.toLocaleLowerCase(rule));
}

const RESERVED_NAMES = [
  DEFAULT_LIBRARY_NAME,
  ...Object.values(DICTIONARIES).map((dictionary) => dictionary["library.defaultName"]),
];
const RESERVED_FORMS = new Set(RESERVED_NAMES.flatMap(lowercasings));

export function isDefaultLibrary(collection) {
  return collection?.name === DEFAULT_LIBRARY_NAME;
}

// The name a person sees: the label of the default library, otherwise the folder's own name.
export function libraryLabel(collection) {
  if (!collection) return "";
  return isDefaultLibrary(collection) ? t("library.defaultName") : collection.name;
}

// A new folder may not take the stored name, nor the label of the default library in any language.
export function isReservedLibraryName(name) {
  return lowercasings(name).some((form) => RESERVED_FORMS.has(form));
}
