import { useMemo, useState } from "react";
import { Layers, Plus, RefreshCw, Search, X } from "lucide-react";

import type { CampaignSummaryOut } from "../types/api";

interface SidebarProps {
  campaigns: CampaignSummaryOut[];
  loading: boolean;
  selectedCampaignId: number | null;
  isCreateMode: boolean;
  mobileOpen: boolean;
  onCloseMobile: () => void;
  onSelectCampaign: (keitaroId: number) => void;
  onOpenCreate: () => void;
  onRefresh: () => void;
}

export function Sidebar({
  campaigns,
  loading,
  selectedCampaignId,
  isCreateMode,
  mobileOpen,
  onCloseMobile,
  onSelectCampaign,
  onOpenCreate,
  onRefresh,
}: SidebarProps) {
  const [filter, setFilter] = useState("");

  const filteredCampaigns = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return campaigns;
    return campaigns.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        String(c.keitaro_id).includes(q) ||
        (c.alias ? c.alias.toLowerCase().includes(q) : false),
    );
  }, [campaigns, filter]);

  return (
    <>
      {mobileOpen && (
        <div
          className="sidebar-backdrop"
          aria-hidden="true"
          onClick={onCloseMobile}
        />
      )}
      <aside className={`sidebar ${mobileOpen ? "sidebar--open" : ""}`}>
        <div className="sidebar-header">
          <div className="brand-row">
            <div className="brand">
              <span className="brand-badge">
                <Layers size={15} />
              </span>
              <span>Adrobot</span>
            </div>
            <button
              type="button"
              className="btn btn--sm btn--icon sidebar-close-btn"
              aria-label="Закрыть меню"
              onClick={onCloseMobile}
            >
              <X size={16} />
            </button>
          </div>
          <button
            type="button"
            className="btn btn--full btn--primary"
            onClick={() => {
              onOpenCreate();
              onCloseMobile();
            }}
          >
            <Plus size={16} />
            Новая кампания
          </button>
        </div>

        <div className="sidebar-search-row">
          <div className="search-input-wrap">
            <Search size={15} className="search-input-icon" aria-hidden="true" />
            <input
              type="text"
              className="input input--with-icon input--subtle"
              placeholder="Поиск кампаний..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
          <button
            type="button"
            className="btn btn--icon"
            title="Обновить список кампаний"
            aria-label="Обновить список кампаний"
            disabled={loading}
            onClick={onRefresh}
          >
            <RefreshCw size={15} className={loading ? "spin" : ""} />
          </button>
        </div>

        <div className="sidebar-list">
          {loading && campaigns.length === 0 ? (
            <>
              <div className="skeleton" />
              <div className="skeleton" />
              <div className="skeleton" />
            </>
          ) : filteredCampaigns.length === 0 ? (
            <div className="empty-state" style={{ padding: "28px 12px" }}>
              <span style={{ fontSize: 13 }}>
                {campaigns.length === 0
                  ? "Кампаний пока нет"
                  : "Ничего не найдено"}
              </span>
            </div>
          ) : (
            filteredCampaigns.map((campaign) => {
              const isSelected = !isCreateMode && selectedCampaignId === campaign.keitaro_id;
              return (
                <button
                  key={campaign.keitaro_id}
                  type="button"
                  className={`sidebar-item ${isSelected ? "sidebar-item--active" : ""}`}
                  onClick={() => {
                    onSelectCampaign(campaign.keitaro_id);
                    onCloseMobile();
                  }}
                >
                  <span className="sidebar-item-name" title={campaign.name}>
                    {campaign.name}
                  </span>
                  <span className="sidebar-item-meta">
                    <span className="mono">#{campaign.keitaro_id}</span>
                    <span className="sync-dot">
                      <span
                        className={`sync-dot-circle ${
                          campaign.is_synced_locally ? "" : "sync-dot-circle--remote"
                        }`}
                      />
                      {campaign.is_synced_locally ? "синхр." : "в KT"}
                    </span>
                  </span>
                </button>
              );
            })
          )}
        </div>
      </aside>
    </>
  );
}
