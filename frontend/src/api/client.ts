import type {
  CampaignCreateIn,
  CampaignDetailOut,
  CampaignSummaryOut,
  OfferOut,
  StreamOut,
} from "../types/api";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let message = `Ошибка запроса (${response.status})`;
    try {
      const data = (await response.json()) as { detail?: unknown };
      if (typeof data.detail === "string" && data.detail) {
        message = data.detail;
      } else if (Array.isArray(data.detail) && data.detail.length > 0) {
        const first = data.detail[0] as { msg?: string };
        if (first?.msg) {
          message = first.msg;
        }
      }
    } catch {
      // Ignore non-JSON error body
    }
    throw new ApiError(response.status, message);
  }

  return (await response.json()) as T;
}

export const apiClient = {
  listOffers(query: string, limit = 20, refresh = false): Promise<OfferOut[]> {
    const params = new URLSearchParams({
      q: query,
      limit: String(limit),
      refresh: String(refresh),
    });
    return request<OfferOut[]>(`/api/offers?${params.toString()}`);
  },

  listCampaigns(): Promise<CampaignSummaryOut[]> {
    return request<CampaignSummaryOut[]>("/api/campaigns");
  },

  createCampaign(payload: CampaignCreateIn): Promise<CampaignDetailOut> {
    return request<CampaignDetailOut>("/api/campaigns", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  getCampaign(keitaroId: number): Promise<CampaignDetailOut> {
    return request<CampaignDetailOut>(`/api/campaigns/${keitaroId}`);
  },

  fetchCampaign(keitaroId: number): Promise<CampaignDetailOut> {
    return request<CampaignDetailOut>(`/api/campaigns/${keitaroId}/fetch`, {
      method: "POST",
    });
  },

  addStreamOffer(streamId: number, offerId: number): Promise<StreamOut> {
    return request<StreamOut>(`/api/streams/${streamId}/offers`, {
      method: "POST",
      body: JSON.stringify({ offer_id: offerId }),
    });
  },

  removeStreamOffer(streamId: number, offerKeitaroId: number): Promise<StreamOut> {
    return request<StreamOut>(
      `/api/streams/${streamId}/offers/${offerKeitaroId}/remove`,
      { method: "POST" },
    );
  },

  bringBackStreamOffer(streamId: number, offerKeitaroId: number): Promise<StreamOut> {
    return request<StreamOut>(
      `/api/streams/${streamId}/offers/${offerKeitaroId}/bring-back`,
      { method: "POST" },
    );
  },

  pinStreamOffer(
    streamId: number,
    offerKeitaroId: number,
    isPinned: boolean,
  ): Promise<StreamOut> {
    return request<StreamOut>(`/api/streams/${streamId}/offers/${offerKeitaroId}/pin`, {
      method: "PATCH",
      body: JSON.stringify({ is_pinned: isPinned }),
    });
  },

  pushStream(streamId: number): Promise<StreamOut> {
    return request<StreamOut>(`/api/streams/${streamId}/push`, {
      method: "POST",
    });
  },

  cancelStream(streamId: number): Promise<StreamOut> {
    return request<StreamOut>(`/api/streams/${streamId}/cancel`, {
      method: "POST",
    });
  },
};
