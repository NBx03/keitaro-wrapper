import { useMemo, useState } from "react";
import {
  AlertTriangle,
  Loader2,
  Pin,
  Plus,
  RotateCcw,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";

import { apiClient } from "../api/client";
import type { OfferOut, StreamOut } from "../types/api";
import { formatOfferTitle } from "../utils/offers";
import { OfferAutocomplete } from "./OfferAutocomplete";

interface StreamCardProps {
  stream: StreamOut;
  onStreamUpdated: (updated: StreamOut) => void;
  onNotify: (type: "success" | "error", message: string) => void;
}

export function StreamCard({ stream, onStreamUpdated, onNotify }: StreamCardProps) {
  const [selectedOffer, setSelectedOffer] = useState<OfferOut | null>(null);
  const [busy, setBusy] = useState(false);

  const activeOffers = useMemo(
    () => stream.offers.filter((o) => o.draft_state === "active"),
    [stream.offers],
  );
  const removedOffers = useMemo(
    () => stream.offers.filter((o) => o.draft_state !== "active"),
    [stream.offers],
  );
  const activeOfferIds = useMemo(
    () => new Set(activeOffers.map((o) => o.offer_keitaro_id)),
    [activeOffers],
  );

  if (!stream.has_offers) {
    return (
      <div className="stream-card stream-card--compact">
        <div className="stream-header-left">
          <h3 className="stream-title">Stream: {stream.name}</h3>
          <span className="badge badge--neutral">Redirect / Rules</span>
        </div>
        <span style={{ color: "var(--text-muted)", fontSize: 13 }}>
          Поток не содержит офферов
        </span>
      </div>
    );
  }

  async function runAction(action: () => Promise<StreamOut>, successMessage?: string) {
    setBusy(true);
    try {
      const updated = await action();
      onStreamUpdated(updated);
      if (successMessage) {
        onNotify("success", successMessage);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Ошибка при обновлении потока";
      onNotify("error", msg);
    } finally {
      setBusy(false);
    }
  }

  async function handleAddOffer() {
    if (!selectedOffer) return;
    const offerToAdd = selectedOffer;
    await runAction(async () => {
      const updated = await apiClient.addStreamOffer(stream.id, offerToAdd.keitaro_id);
      setSelectedOffer(null);
      return updated;
    });
  }

  const shareValid = stream.total_active_share === 100 && activeOffers.length > 0;

  return (
    <section className={`stream-card ${stream.is_dirty ? "stream-card--dirty" : ""}`}>
      <div className="stream-header">
        <div className="stream-header-left">
          <h3 className="stream-title">Stream: {stream.name}</h3>
          {stream.is_dirty && (
            <span className="badge badge--dirty">
              <AlertTriangle size={13} />
              Unpublished changes
            </span>
          )}
          <span className={`badge mono ${shareValid ? "badge--ok" : "badge--warn"}`}>
            {shareValid ? "100%" : `Сумма: ${stream.total_active_share}%`}
          </span>
        </div>

        {stream.is_dirty && (
          <div className="stream-header-actions">
            <button
              type="button"
              className="btn btn--sm"
              disabled={busy}
              onClick={() =>
                runAction(
                  () => apiClient.cancelStream(stream.id),
                  "Черновик потока отменён",
                )
              }
            >
              <X size={15} />
              CANCEL
            </button>
            <button
              type="button"
              className="btn btn--sm btn--push"
              disabled={busy}
              onClick={() =>
                runAction(
                  () => apiClient.pushStream(stream.id),
                  `Поток «${stream.name}» отправлен в Keitaro`,
                )
              }
            >
              {busy ? (
                <Loader2 size={15} className="spin" />
              ) : (
                <UploadCloud size={15} />
              )}
              PUSH TO KT
            </button>
          </div>
        )}
      </div>

      <div className="offers-table-wrap">
        <table className="offers-table">
          <thead>
            <tr>
              <th>Offer</th>
              <th className="col-share">Share</th>
              <th className="col-actions">Actions</th>
            </tr>
          </thead>
          <tbody>
            {activeOffers.length === 0 && removedOffers.length === 0 ? (
              <tr>
                <td colSpan={3} style={{ textAlign: "center", color: "var(--text-muted)" }}>
                  В потоке пока нет офферов
                </td>
              </tr>
            ) : (
              <>
                {activeOffers.map((item) => (
                  <tr key={item.offer_keitaro_id}>
                    <td>
                      <div className="offer-cell">
                        <span className="offer-id-tag mono">#{item.offer_keitaro_id}</span>
                        <span className="offer-name">
                          {formatOfferTitle(item.offer_keitaro_id, item.offer_name)}
                        </span>
                      </div>
                    </td>
                    <td>
                      <div className="share-cell">
                        <span className="share-value mono">{item.draft_share}%</span>
                        <button
                          type="button"
                          disabled={busy}
                          className={`btn-pin ${item.is_pinned ? "btn-pin--active" : ""}`}
                          title={
                            item.is_pinned
                              ? "Вес закреплён"
                              : "Закрепить текущий вес при пересчёте"
                          }
                          aria-label={
                            item.is_pinned ? "Открепить вес" : "Закрепить вес"
                          }
                          onClick={() =>
                            runAction(() =>
                              apiClient.pinStreamOffer(
                                stream.id,
                                item.offer_keitaro_id,
                                !item.is_pinned,
                              ),
                            )
                          }
                        >
                          <Pin
                            size={14}
                            fill={item.is_pinned ? "currentColor" : "none"}
                          />
                        </button>
                      </div>
                    </td>
                    <td>
                      <div className="actions-cell">
                        <button
                          type="button"
                          className="btn btn--sm btn--remove"
                          disabled={busy}
                          onClick={() =>
                            runAction(() =>
                              apiClient.removeStreamOffer(stream.id, item.offer_keitaro_id),
                            )
                          }
                        >
                          <Trash2 size={15} />
                          REMOVE
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}

                {removedOffers.length > 0 && activeOffers.length > 0 && (
                  <tr className="offers-section-divider">
                    <td colSpan={3}>Удалённые из потока</td>
                  </tr>
                )}

                {removedOffers.map((item) => (
                  <tr key={item.offer_keitaro_id} className="offer-row--removed">
                    <td>
                      <div className="offer-cell-removed">
                        <span className="offer-name">
                          {formatOfferTitle(item.offer_keitaro_id, item.offer_name)}
                        </span>
                        <div className="offer-removed-meta">
                          <span className="offer-id-tag mono">#{item.offer_keitaro_id}</span>
                          <span className="badge badge--removed">removed</span>
                        </div>
                      </div>
                    </td>
                    <td>
                      <div className="share-cell">
                        <span className="share-value mono">0%</span>
                      </div>
                    </td>
                    <td>
                      <div className="actions-cell">
                        <button
                          type="button"
                          className="btn btn--sm btn--bring-back"
                          disabled={busy}
                          onClick={() =>
                            runAction(() =>
                              apiClient.bringBackStreamOffer(
                                stream.id,
                                item.offer_keitaro_id,
                              ),
                            )
                          }
                        >
                          <RotateCcw size={15} />
                          BRING BACK
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </>
            )}
          </tbody>
        </table>
      </div>

      <div className="stream-footer">
        <div className="stream-footer-autocomplete">
          <OfferAutocomplete
            value={selectedOffer}
            disabled={busy}
            disabledOfferIds={activeOfferIds}
            placeholder="Добавить оффер в поток (по названию или ID)..."
            onChange={setSelectedOffer}
          />
        </div>
        <button
          type="button"
          className="btn btn--primary"
          disabled={busy || !selectedOffer}
          onClick={handleAddOffer}
        >
          <Plus size={16} />
          ADD
        </button>
      </div>
    </section>
  );
}
