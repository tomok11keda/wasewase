import { useEffect, useRef } from "react";
import { recordSponsorClick, recordSponsorImpression } from "./api";
import type { SponsorAd } from "./types";

type Props = {
  ad: SponsorAd;
  layout?: "feed" | "discover";
};

export function SponsorAdCard({ ad, layout = "feed" }: Props) {
  const tracked = useRef(false);

  useEffect(() => {
    if (tracked.current) return;
    tracked.current = true;
    void recordSponsorImpression(ad.id, ad.placement);
  }, [ad.id, ad.placement]);

  const onCta = () => {
    void recordSponsorClick(ad.id, ad.placement);
  };

  return (
    <article
      className={`sponsor-ad-card sponsor-ad-card--${layout}`}
      data-sponsor-ad={ad.id}
      data-sponsor-placement={ad.placement}
      data-sponsor-kind={ad.kind}
    >
      <div className="sponsor-ad-card__chrome">
        <span className="sponsor-ad-card__badge">{ad.badge_label}</span>
        <span className="sponsor-ad-card__sponsor">{ad.sponsor_name}</span>
      </div>
      {ad.image_url ? (
        <div className="sponsor-ad-card__media">
          <img src={ad.image_url} alt="" loading="lazy" />
        </div>
      ) : null}
      <div className="sponsor-ad-card__body">
        <h3 className="sponsor-ad-card__title">{ad.title}</h3>
        {ad.description ? (
          <p className="sponsor-ad-card__desc">{ad.description}</p>
        ) : null}
        <a
          className="sponsor-ad-card__cta"
          href={ad.cta_url}
          target="_blank"
          rel="noopener noreferrer sponsored"
          onClick={onCta}
          data-sponsor-cta="1"
        >
          {ad.cta_label}
        </a>
      </div>
    </article>
  );
}
