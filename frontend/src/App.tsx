import { useCallback, useEffect, useRef, useState } from "react";
import { Layers, Loader2, Menu, Plus } from "lucide-react";

import { apiClient } from "./api/client";
import { CampaignCreator } from "./components/CampaignCreator";
import { CampaignEditor } from "./components/CampaignEditor";
import { Sidebar } from "./components/Sidebar";
import { ToastContainer, type ToastItem } from "./components/ToastContainer";
import type { CampaignDetailOut, CampaignSummaryOut, StreamOut } from "./types/api";

type ViewMode = "empty" | "create" | "detail";

export function App() {
  const [campaigns, setCampaigns] = useState<CampaignSummaryOut[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [viewMode, setViewMode] = useState<ViewMode>("empty");
  const [selectedCampaignId, setSelectedCampaignId] = useState<number | null>(null);
  const [campaignDetail, setCampaignDetail] = useState<CampaignDetailOut | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [fetchingStreams, setFetchingStreams] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const toastIdRef = useRef(0);
  const detailRequestSeqRef = useRef(0);

  const notify = useCallback((type: "success" | "error", message: string) => {
    const id = ++toastIdRef.current;
    setToasts((prev) => [...prev, { id, type, message }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((item) => item.id !== id));
    }, 4000);
  }, []);

  const loadCampaigns = useCallback(async () => {
    setLoadingList(true);
    try {
      const list = await apiClient.listCampaigns();
      setCampaigns(list);
    } catch (err) {
      notify("error", err instanceof Error ? err.message : "Не удалось загрузить кампании");
    } finally {
      setLoadingList(false);
    }
  }, [notify]);

  useEffect(() => {
    void loadCampaigns();
  }, [loadCampaigns]);

  async function handleSelectCampaign(keitaroId: number) {
    const seq = ++detailRequestSeqRef.current;
    setViewMode("detail");
    setSelectedCampaignId(keitaroId);
    setLoadingDetail(true);
    try {
      const detail = await apiClient.getCampaign(keitaroId);
      if (detailRequestSeqRef.current !== seq) return;
      setCampaignDetail(detail);
      setCampaigns((prev) =>
        prev.map((c) =>
          c.keitaro_id === keitaroId ? { ...c, is_synced_locally: true } : c,
        ),
      );
    } catch (err) {
      if (detailRequestSeqRef.current !== seq) return;
      notify("error", err instanceof Error ? err.message : "Не удалось загрузить кампанию");
      setCampaignDetail(null);
    } finally {
      if (detailRequestSeqRef.current === seq) {
        setLoadingDetail(false);
      }
    }
  }

  function handleOpenCreate() {
    ++detailRequestSeqRef.current;
    setLoadingDetail(false);
    setViewMode("create");
  }

  function handleCampaignCreated(created: CampaignDetailOut) {
    ++detailRequestSeqRef.current;
    setCampaigns((prev) => [
      {
        keitaro_id: created.keitaro_id,
        name: created.name,
        alias: created.alias,
        is_synced_locally: true,
      },
      ...prev.filter((c) => c.keitaro_id !== created.keitaro_id),
    ]);
    setSelectedCampaignId(created.keitaro_id);
    setCampaignDetail(created);
    setLoadingDetail(false);
    setViewMode("detail");
    notify("success", `Кампания «${created.name}» создана в Keitaro`);
  }

  async function handleFetchStreams() {
    if (!campaignDetail) return;
    const seq = ++detailRequestSeqRef.current;
    const targetId = campaignDetail.keitaro_id;
    setFetchingStreams(true);
    try {
      const updated = await apiClient.fetchCampaign(targetId);
      if (detailRequestSeqRef.current !== seq) return;
      setCampaignDetail(updated);
      notify("success", "Потоки синхронизированы из Keitaro");
    } catch (err) {
      if (detailRequestSeqRef.current !== seq) return;
      notify("error", err instanceof Error ? err.message : "Ошибка синхронизации из Keitaro");
    } finally {
      if (detailRequestSeqRef.current === seq) {
        setFetchingStreams(false);
      }
    }
  }

  function handleStreamUpdated(updatedStream: StreamOut) {
    setCampaignDetail((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        streams: prev.streams.map((s) => (s.id === updatedStream.id ? updatedStream : s)),
      };
    });
  }

  return (
    <div className="app-shell">
      <div className="mobile-topbar">
        <button
          type="button"
          className="btn btn--sm"
          aria-label="Открыть список кампаний"
          onClick={() => setMobileOpen(true)}
        >
          <Menu size={16} />
          Кампании
        </button>
        <div className="brand">
          <span className="brand-badge">
            <Layers size={14} />
          </span>
          <span>Adrobot</span>
        </div>
        <button
          type="button"
          className="btn btn--sm btn--primary"
          onClick={handleOpenCreate}
        >
          <Plus size={15} />
          Новая
        </button>
      </div>

      <Sidebar
        campaigns={campaigns}
        loading={loadingList}
        selectedCampaignId={selectedCampaignId}
        isCreateMode={viewMode === "create"}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
        onSelectCampaign={handleSelectCampaign}
        onOpenCreate={handleOpenCreate}
        onRefresh={() => void loadCampaigns()}
      />

      <main className="main-area">
        <div className="main-container">
          {viewMode === "create" ? (
            <CampaignCreator
              onCreated={handleCampaignCreated}
              onError={(msg) => notify("error", msg)}
            />
          ) : viewMode === "detail" ? (
            loadingDetail ? (
              <div className="card empty-state">
                <Loader2 size={22} className="spin" />
                <span>Загрузка кампании и потоков...</span>
              </div>
            ) : campaignDetail ? (
              <CampaignEditor
                campaign={campaignDetail}
                fetching={fetchingStreams}
                onFetchStreams={handleFetchStreams}
                onStreamUpdated={handleStreamUpdated}
                onNotify={notify}
              />
            ) : (
              <div className="card empty-state">
                <span>Не удалось загрузить выбранную кампанию.</span>
              </div>
            )
          ) : (
            <div className="card empty-state" style={{ marginTop: 24 }}>
              <div className="empty-state-icon">
                <Layers size={22} />
              </div>
              <div style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: 16 }}>
                Выберите кампанию в списке слева или создайте новую
              </div>
              <div style={{ maxWidth: 420, fontSize: 13.5 }}>
                Редактор позволяет синхронизировать потоки с Keitaro, управлять долями
                офферов с закреплением и отправлять изменения кнопкой PUSH TO KT.
              </div>
              <button
                type="button"
                className="btn btn--primary"
                onClick={handleOpenCreate}
              >
                <Plus size={16} />
                Создать кампанию
              </button>
            </div>
          )}
        </div>
      </main>

      <ToastContainer
        toasts={toasts}
        onDismiss={(id) => setToasts((prev) => prev.filter((item) => item.id !== id))}
      />
    </div>
  );
}
