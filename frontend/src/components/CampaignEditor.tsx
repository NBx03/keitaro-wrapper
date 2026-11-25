import { useState } from "react";
import { Check, Copy, ExternalLink, RefreshCw } from "lucide-react";

import type { CampaignDetailOut, StreamOut } from "../types/api";
import { ConfirmModal } from "./ConfirmModal";
import { StreamCard } from "./StreamCard";

interface CampaignEditorProps {
  campaign: CampaignDetailOut;
  fetching: boolean;
  onFetchStreams: () => Promise<void>;
  onStreamUpdated: (updated: StreamOut) => void;
  onNotify: (type: "success" | "error", message: string) => void;
}

export function CampaignEditor({
  campaign,
  fetching,
  onFetchStreams,
  onStreamUpdated,
  onNotify,
}: CampaignEditorProps) {
  const [copied, setCopied] = useState(false);
  const [confirmFetchOpen, setConfirmFetchOpen] = useState(false);

  const hasAnyDirty = campaign.streams.some((s) => s.is_dirty);

  async function handleCopyTracking() {
    if (!campaign.tracking_url) return;
    try {
      await navigator.clipboard.writeText(campaign.tracking_url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      onNotify("error", "Не удалось скопировать ссылку в буфер обмена");
    }
  }

  function handleFetchClick() {
    if (hasAnyDirty) {
      setConfirmFetchOpen(true);
      return;
    }
    void onFetchStreams();
  }

  return (
    <div>
      <header className="card campaign-header">
        <div className="campaign-header-main">
          <div className="campaign-title-row">
            <h1 className="campaign-title">{campaign.name}</h1>
            <span className="badge badge--neutral mono">#{campaign.keitaro_id}</span>
          </div>

          {campaign.tracking_url && (
            <div className="tracking-bar">
              <span className="tracking-url mono" title={campaign.tracking_url}>
                {campaign.tracking_url}
              </span>
              <button
                type="button"
                className="btn btn--sm"
                onClick={handleCopyTracking}
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
                {copied ? "Скопировано" : "Копировать"}
              </button>
            </div>
          )}
        </div>

        <div className="campaign-header-actions">
          <a
            href={campaign.keitaro_admin_url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn"
            style={{ textDecoration: "none" }}
          >
            <ExternalLink size={15} />
            VIEW IN KT
          </a>
          <button
            type="button"
            className="btn btn--primary"
            disabled={fetching}
            onClick={handleFetchClick}
          >
            <RefreshCw size={15} className={fetching ? "spin" : ""} />
            FETCH STREAMS FROM KT
          </button>
        </div>
      </header>

      <div className="streams-stack">
        {campaign.streams.length === 0 ? (
          <div className="card empty-state">
            <span>У этой кампании пока нет потоков в Keitaro.</span>
          </div>
        ) : (
          campaign.streams.map((stream) => (
            <StreamCard
              key={stream.id}
              stream={stream}
              onStreamUpdated={onStreamUpdated}
              onNotify={onNotify}
            />
          ))
        )}
      </div>

      {confirmFetchOpen && (
        <ConfirmModal
          title="Перезаписать несохранённые черновики?"
          description="В одном или нескольких потоках есть несохранённые локальные изменения (Unpublished changes). Загрузка данных из Keitaro сбросит эти черновики."
          confirmLabel="Да, загрузить из KT"
          onCancel={() => setConfirmFetchOpen(false)}
          onConfirm={() => {
            setConfirmFetchOpen(false);
            void onFetchStreams();
          }}
        />
      )}
    </div>
  );
}
