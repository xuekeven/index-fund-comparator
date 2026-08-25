import { EXCHANGES, VENUES } from "./fund-list";
import type { VenueFilter } from "./fund-list";

const FILTER_PREFERENCES_KEY = "index-fund-comparator:filters:v1";

export interface FilterPreferences {
  activeIndex: string;
  venue: VenueFilter;
  exchanges: string[];
  shareClasses: string[];
  currencies: string[];
}

const DEFAULT_FILTER_PREFERENCES: FilterPreferences = {
  activeIndex: "csi-500",
  venue: "场内",
  exchanges: [...EXCHANGES],
  shareClasses: [],
  currencies: [],
};

function stringArray(value: unknown) {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

export function readFilterPreferences(): FilterPreferences {
  if (typeof window === "undefined") return DEFAULT_FILTER_PREFERENCES;
  try {
    const parsed = JSON.parse(window.localStorage.getItem(FILTER_PREFERENCES_KEY) ?? "null");
    if (!parsed || typeof parsed !== "object") return DEFAULT_FILTER_PREFERENCES;
    const value = parsed as Partial<FilterPreferences>;
    const venue = VENUES.includes(value.venue as VenueFilter)
      ? value.venue as VenueFilter
      : "场内";
    const exchanges = stringArray(value.exchanges).filter((item) => EXCHANGES.includes(item));
    return {
      activeIndex: typeof value.activeIndex === "string" && value.activeIndex
        ? value.activeIndex
        : DEFAULT_FILTER_PREFERENCES.activeIndex,
      venue,
      exchanges: venue === "场内" ? exchanges.length > 0 ? exchanges : [...EXCHANGES] : [],
      shareClasses: venue === "场外" ? stringArray(value.shareClasses) : [],
      currencies: venue === "场外" ? stringArray(value.currencies) : [],
    };
  } catch {
    return DEFAULT_FILTER_PREFERENCES;
  }
}

export function writeFilterPreferences(preferences: FilterPreferences) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(FILTER_PREFERENCES_KEY, JSON.stringify(preferences));
  } catch {
    return;
  }
}

export function keepAvailable(current: string[], available: string[]) {
  const next = current.filter((item) => available.includes(item));
  return next.length === current.length ? current : next;
}
