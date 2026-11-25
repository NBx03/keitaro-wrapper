import { useEffect, useRef, useState } from "react";
import { Loader2, Search, X } from "lucide-react";

import { apiClient } from "../api/client";
import type { OfferOut } from "../types/api";
import { formatOfferTitle } from "../utils/offers";

interface OfferAutocompleteProps {
  value: OfferOut | null;
  onChange: (offer: OfferOut | null) => void;
  placeholder?: string;
  disabledOfferIds?: Set<number>;
  disabled?: boolean;
  inputId?: string;
}

function formatSelectedLabel(offer: OfferOut): string {
  return `#${offer.keitaro_id} ${formatOfferTitle(offer.keitaro_id, offer.name)}`;
}

export function OfferAutocomplete({
  value,
  onChange,
  placeholder = "Поиск оффера по названию или ID...",
  disabledOfferIds,
  disabled = false,
  inputId,
}: OfferAutocompleteProps) {
  const [query, setQuery] = useState(value ? formatSelectedLabel(value) : "");
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [options, setOptions] = useState<OfferOut[]>([]);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [error, setError] = useState<string | null>(null);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const debounceRef = useRef<number | null>(null);
  const requestSeqRef = useRef(0);

  useEffect(() => {
    if (value) {
      setQuery(formatSelectedLabel(value));
    } else if (!open) {
      setQuery("");
    }
  }, [value, open]);

  useEffect(() => {
    function handleOutsideClick(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
        if (value) {
          setQuery(formatSelectedLabel(value));
        }
      }
    }
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, [value]);

  useEffect(() => {
    if (!open) return;

    const searchText = value && query === formatSelectedLabel(value) ? "" : query;

    if (debounceRef.current) {
      window.clearTimeout(debounceRef.current);
    }

    const seq = ++requestSeqRef.current;
    debounceRef.current = window.setTimeout(async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await apiClient.listOffers(searchText, 25);
        if (requestSeqRef.current === seq) {
          setOptions(result);
          setHighlightedIndex(result.length > 0 ? 0 : -1);
        }
      } catch (err) {
        if (requestSeqRef.current === seq) {
          setError(err instanceof Error ? err.message : "Не удалось загрузить офферы");
          setOptions([]);
        }
      } finally {
        if (requestSeqRef.current === seq) {
          setLoading(false);
        }
      }
    }, 250);

    return () => {
      if (debounceRef.current) {
        window.clearTimeout(debounceRef.current);
      }
    };
  }, [open, query, value]);

  function selectOption(offer: OfferOut) {
    if (disabledOfferIds?.has(offer.keitaro_id)) return;
    onChange(offer);
    setQuery(formatSelectedLabel(offer));
    setOpen(false);
  }

  function clearSelection() {
    onChange(null);
    setQuery("");
    setOpen(true);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!open && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      setOpen(true);
      return;
    }

    if (event.key === "Escape") {
      setOpen(false);
      if (value) {
        setQuery(formatSelectedLabel(value));
      }
      return;
    }

    if (!open || options.length === 0) return;

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlightedIndex((prev) => (prev + 1) % options.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlightedIndex((prev) => (prev <= 0 ? options.length - 1 : prev - 1));
    } else if (event.key === "Enter") {
      if (highlightedIndex >= 0 && highlightedIndex < options.length) {
        const candidate = options[highlightedIndex];
        if (!disabledOfferIds?.has(candidate.keitaro_id)) {
          event.preventDefault();
          selectOption(candidate);
        }
      }
    }
  }

  return (
    <div className="autocomplete" ref={containerRef}>
      <div className="autocomplete-control">
        <Search size={15} className="search-input-icon" aria-hidden="true" />
        <input
          id={inputId}
          type="text"
          className="input input--with-icon"
          style={{ paddingRight: value || query ? 34 : 12 }}
          value={query}
          placeholder={placeholder}
          disabled={disabled}
          autoComplete="off"
          onFocus={() => setOpen(true)}
          onChange={(e) => {
            setQuery(e.target.value);
            if (value) {
              onChange(null);
            }
            setOpen(true);
          }}
          onKeyDown={handleKeyDown}
        />
        {(value || query) && !disabled && (
          <button
            type="button"
            className="autocomplete-clear"
            aria-label="Очистить выбор оффера"
            onClick={clearSelection}
          >
            <X size={14} />
          </button>
        )}
      </div>

      {open && (
        <div className="autocomplete-dropdown" role="listbox">
          {loading ? (
            <div className="autocomplete-empty">
              <Loader2 size={15} className="spin" style={{ verticalAlign: "middle", marginRight: 6 }} />
              Загрузка офферов...
            </div>
          ) : error ? (
            <div className="autocomplete-empty" style={{ color: "var(--danger-hover-text)" }}>
              {error}
            </div>
          ) : options.length === 0 ? (
            <div className="autocomplete-empty">Офферы не найдены</div>
          ) : (
            options.map((offer, index) => {
              const isInStream = disabledOfferIds?.has(offer.keitaro_id) ?? false;
              const isSelected = value?.keitaro_id === offer.keitaro_id;
              const isHighlighted = index === highlightedIndex;
              return (
                <button
                  key={offer.keitaro_id}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  disabled={isInStream}
                  className={[
                    "autocomplete-option",
                    isHighlighted ? "autocomplete-option--highlighted" : "",
                    isSelected ? "autocomplete-option--selected" : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                  onMouseEnter={() => setHighlightedIndex(index)}
                  onClick={() => selectOption(offer)}
                >
                  <span className="autocomplete-option-main">
                    <span className="offer-id-tag mono">#{offer.keitaro_id}</span>
                    <span
                      className="autocomplete-option-name"
                      title={formatOfferTitle(offer.keitaro_id, offer.name)}
                    >
                      {formatOfferTitle(offer.keitaro_id, offer.name)}
                    </span>
                  </span>
                  {isInStream && <span className="badge badge--neutral">В потоке</span>}
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}
