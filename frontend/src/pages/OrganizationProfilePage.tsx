import { useCallback, useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { BrowsePreviewNotice } from "../components/BrowsePreviewNotice";
import { VerifiedOrganizationBadge } from "../components/VerifiedOrganizationBadge";
import { spaLoginPath } from "../features/auth/api";
import {
  fetchOrganizationProfile,
  OrganizationRequestError,
} from "../features/orgs/api";
import {
  organizationCategoryLabel,
  organizationExternalHref,
  organizationInitial,
  type OrganizationProfilePayload,
} from "../features/orgs/orgProfile";
import { isBrowsePreview, useSession } from "../lib/session";

function statusFromError(err: unknown): string {
  if (err instanceof OrganizationRequestError) return err.code;
  return "load_failed";
}

export function OrganizationProfilePage() {
  const { slug } = useParams();
  const { me, loading: sessionLoading } = useSession();
  const browsePreview = isBrowsePreview(me);
  const [payload, setPayload] = useState<OrganizationProfilePayload | null>(
    null
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!slug) {
      setError("not_found");
      setPayload(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await fetchOrganizationProfile(slug);
      setPayload(data);
    } catch (err) {
      setPayload(null);
      setError(statusFromError(err));
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    if (sessionLoading) return;
    if (browsePreview) {
      setLoading(false);
      setPayload(null);
      setError(null);
      return;
    }
    void load();
  }, [sessionLoading, browsePreview, load]);

  if (!slug) {
    return <Navigate to="/" replace />;
  }

  const loginNext = `/app/orgs/${slug}`;

  if (browsePreview) {
    return (
      <div className="profile-page org-profile-page" data-spa-page="団体">
        <div className="main-inner">
          <BrowsePreviewNotice nextPath={loginNext}>
            団体プロフィールはログイン後に表示されます。
          </BrowsePreviewNotice>
        </div>
      </div>
    );
  }

  if (loading || sessionLoading) {
    return (
      <div className="profile-page org-profile-page" data-spa-page="団体">
        <div className="main-inner">
          <p>読み込み中…</p>
        </div>
      </div>
    );
  }

  if (error === "unauthorized") {
    return (
      <div className="profile-page org-profile-page" data-spa-page="団体">
        <div className="main-inner">
          <p>団体プロフィールを表示するにはログインが必要です。</p>
          <p>
            <Link className="btn btn-primary" to={spaLoginPath(loginNext)}>
              ログイン
            </Link>
          </p>
        </div>
      </div>
    );
  }

  if (error === "not_found") {
    return (
      <div className="profile-page org-profile-page" data-spa-page="団体">
        <div className="main-inner">
          <p>この団体は見つからないか、表示できません。</p>
        </div>
      </div>
    );
  }

  if (error || !payload) {
    return (
      <div className="profile-page org-profile-page" data-spa-page="団体">
        <div className="main-inner">
          <p>通信に失敗しました。時間をおいて再度お試しください。</p>
          <p>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void load()}
            >
              再試行
            </button>
          </p>
        </div>
      </div>
    );
  }

  const org = payload.organization;
  const instagram = organizationExternalHref(org.instagram_url);
  const website = organizationExternalHref(org.website_url);

  return (
    <div className="profile-page org-profile-page" data-spa-page="団体">
      <div className="main-inner">
        <section className="profile-card">
          <div className="profile-header org-profile-header">
            {org.avatar_url ? (
              <img
                className="profile-avatar org-profile-avatar user-avatar--image"
                src={org.avatar_url}
                alt=""
              />
            ) : (
              <span className="profile-avatar org-profile-avatar user-avatar--icon">
                {organizationInitial(org.name)}
              </span>
            )}
            <div className="profile-identity">
              <p className="org-profile-kicker">学生団体</p>
              <h1 className="profile-name">{org.name}</h1>
              <p className="org-profile-category">
                {organizationCategoryLabel(org.category)}
              </p>
              <VerifiedOrganizationBadge verified={org.is_verified} />
            </div>
          </div>

          {org.description ? (
            <p className="profile-bio org-profile-description">
              {org.description}
            </p>
          ) : (
            <p className="org-profile-empty">紹介文はまだありません。</p>
          )}

          {instagram || website ? (
            <div className="org-profile-links">
              {instagram ? (
                <a
                  className="org-profile-link"
                  href={instagram}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Instagram
                </a>
              ) : null}
              {website ? (
                <a
                  className="org-profile-link"
                  href={website}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Webサイト
                </a>
              ) : null}
            </div>
          ) : null}

          {payload.can_manage ? (
            <div className="profile-actions profile-actions--own">
              <Link className="btn btn-secondary" to={`/orgs/${org.slug}/edit`}>
                プロフィールを編集
              </Link>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}
