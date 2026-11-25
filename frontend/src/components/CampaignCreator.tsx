import { useState } from "react";
import { Loader2, PlusCircle } from "lucide-react";

import { apiClient } from "../api/client";
import type { CampaignDetailOut, OfferOut } from "../types/api";
import { OfferAutocomplete } from "./OfferAutocomplete";

interface CampaignCreatorProps {
  onCreated: (campaign: CampaignDetailOut) => void;
  onError: (message: string) => void;
}

const POPULAR_GEOS = ["AU", "MX", "RO", "US", "DE", "PL"];
const TEST_PREFIX = "test_bazarov_";

export function CampaignCreator({ onCreated, onError }: CampaignCreatorProps) {
  const [name, setName] = useState("");
  const [geo, setGeo] = useState("AU");
  const [offer, setOffer] = useState<OfferOut | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  function insertPrefix() {
    if (!name.startsWith(TEST_PREFIX)) {
      setName(`${TEST_PREFIX}${name}`);
    }
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setFormError(null);

    const cleanName = name.trim();
    const cleanGeo = geo.trim().toUpperCase();

    if (!cleanName) {
      setFormError("Укажите название кампании.");
      return;
    }
    if (!/^[A-Z]{2}$/.test(cleanGeo)) {
      setFormError("Гео-код должен состоять ровно из 2 латинских букв (например, AU).");
      return;
    }
    if (!offer) {
      setFormError("Выберите стартовый оффер для Flow 2.");
      return;
    }

    setSubmitting(true);
    try {
      const created = await apiClient.createCampaign({
        name: cleanName,
        geo: cleanGeo,
        offer_id: offer.keitaro_id,
      });
      onCreated(created);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Не удалось создать кампанию";
      setFormError(msg);
      onError(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="creator-wrap">
      <div className="card creator-card">
        <h1 className="creator-title">Создать кампанию в Keitaro</h1>
        <p className="creator-subtitle">
          Автоматически создастся кампания с двумя потоками: Flow 1 (гео-фильтр с редиректом на
          Google) и Flow 2 (выбранный оффер со 100% долей).
        </p>

        <form className="form-stack" onSubmit={handleSubmit}>
          <div className="form-field">
            <div className="form-label-row">
              <label className="form-label" htmlFor="campaign-name-input">
                Название кампании
              </label>
              <button
                type="button"
                className="chip"
                disabled={submitting}
                onClick={insertPrefix}
              >
                Вставить префикс <span className="mono">{TEST_PREFIX}</span>
              </button>
            </div>
            <input
              id="campaign-name-input"
              type="text"
              className="input"
              placeholder="test_bazarov_campaign1"
              value={name}
              disabled={submitting}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="form-field">
            <label className="form-label" htmlFor="campaign-geo-input">
              Гео-код страны (ISO-2)
            </label>
            <div className="geo-row">
              <input
                id="campaign-geo-input"
                type="text"
                maxLength={2}
                className="input input--geo mono"
                value={geo}
                disabled={submitting}
                onChange={(e) =>
                  setGeo(e.target.value.replace(/[^a-zA-Z]/g, "").toUpperCase())
                }
              />
              <div className="chip-row">
                {POPULAR_GEOS.map((code) => (
                  <button
                    key={code}
                    type="button"
                    disabled={submitting}
                    className={`chip mono ${geo === code ? "chip--active" : ""}`}
                    onClick={() => setGeo(code)}
                  >
                    {code}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="form-field">
            <label className="form-label" htmlFor="campaign-offer-input">
              Оффер (Flow 2)
            </label>
            <OfferAutocomplete
              inputId="campaign-offer-input"
              value={offer}
              disabled={submitting}
              onChange={setOffer}
            />
          </div>

          {formError && <div className="form-error">{formError}</div>}

          <button
            type="submit"
            className="btn btn--primary btn--full"
            disabled={submitting}
          >
            {submitting ? (
              <>
                <Loader2 size={16} className="spin" />
                Создание кампании...
              </>
            ) : (
              <>
                <PlusCircle size={16} />
                Создать кампанию
              </>
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
