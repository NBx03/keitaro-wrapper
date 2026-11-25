export interface OfferOut {
  keitaro_id: number;
  name: string;
}

export interface StreamOfferOut {
  offer_keitaro_id: number;
  offer_name: string;
  draft_state: "active" | "removed" | string;
  draft_share: number;
  published_state: "active" | "removed" | "none" | string;
  published_share: number;
  is_pinned: boolean;
}

export interface StreamOut {
  id: number;
  keitaro_id: number;
  name: string;
  position: number;
  schema: string;
  has_offers: boolean;
  is_dirty: boolean;
  total_active_share: number;
  offers: StreamOfferOut[];
}

export interface CampaignSummaryOut {
  keitaro_id: number;
  name: string;
  alias: string | null;
  is_synced_locally: boolean;
}

export interface CampaignDetailOut {
  keitaro_id: number;
  name: string;
  alias: string | null;
  tracking_url: string | null;
  keitaro_admin_url: string;
  domain_id: number | null;
  group_id: number | null;
  traffic_source_id: number | null;
  last_fetched_at: string | null;
  streams: StreamOut[];
}

export interface CampaignCreateIn {
  name: string;
  geo: string;
  offer_id: number;
}
