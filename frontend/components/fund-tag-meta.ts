import type { FundTag } from "@/lib/types";

export const FUND_TAG_META: Record<FundTag, { label: string; title: string }> = {
  favorite: { label: "收藏", title: "我的收藏" },
  holding: { label: "持有", title: "我的持有" },
  recurring: { label: "定投", title: "我的定投" },
};
