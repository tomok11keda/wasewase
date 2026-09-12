import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ImagePickField } from "../../components/ImagePickField";
import type { OnboardingProfile } from "./api";
import { saveOnboardingProfile } from "./api";

type Props = {
  profile: OnboardingProfile;
  faculties: { value: string; label: string }[];
  onDone: () => void;
};

const SLIDE_COUNT = 4;
const HANDLE_PATTERN = /^[a-zA-Z0-9_]{3,30}$/;
const ERROR_SLIDE: Record<string, number> = {
  name: 0,
  username: 1,
  department: 2,
  avatar: 3,
};

function normalizeHandle(raw: string) {
  return raw.trim().replace(/^@+/, "");
}

export function ProfileStep({ profile, faculties, onDone }: Props) {
  const [slide, setSlide] = useState(0);
  const [name, setName] = useState(profile.name);
  const [username, setUsername] = useState(
    profile.username_is_placeholder ? "" : profile.username
  );
  const [department, setDepartment] = useState(profile.department);
  const [avatar, setAvatar] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState(false);
  const [photoPickerOpen, setPhotoPickerOpen] = useState(false);

  const previewUrl = useMemo(
    () => (avatar ? URL.createObjectURL(avatar) : null),
    [avatar]
  );

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const avatarSrc = previewUrl || profile.avatar_url || "";
  const fieldError = (key: string) => fieldErrors[key]?.[0] || null;

  useEffect(() => {
    if (slide === 0) document.getElementById("ob-name")?.focus();
    if (slide === 1) document.getElementById("ob-username")?.focus();
    if (slide === 2) document.getElementById("ob-faculty")?.focus();
  }, [slide]);

  const validateSlide = (index: number): Record<string, string[]> => {
    if (index === 0) {
      const trimmed = name.trim();
      if (!trimmed) return { name: ["表示名を入力してください。"] };
      if (trimmed.length > 80) {
        return { name: ["表示名は80文字以内で入力してください。"] };
      }
    }
    if (index === 1) {
      const handle = normalizeHandle(username);
      if (!handle) return { username: ["ユーザー名を入力してください。"] };
      if (!HANDLE_PATTERN.test(handle)) {
        return {
          username: [
            "ユーザー名は英数字とアンダースコア（_）のみ、3〜30文字で入力してください。",
          ],
        };
      }
    }
    if (index === 2 && !department) {
      return { department: ["学部を選択してください。"] };
    }
    return {};
  };

  const submitProfile = async (file: File | null = avatar) => {
    setBusy(true);
    setError(null);
    setFieldErrors({});
    try {
      const result = await saveOnboardingProfile({
        name: name.trim(),
        username: normalizeHandle(username),
        department,
        avatar: file,
      });
      if (!result.ok) {
        const errors = result.errors || {};
        setFieldErrors(errors);
        setError("入力内容を確認してください。");
        const firstKey = Object.keys(errors).find((key) => ERROR_SLIDE[key] != null);
        if (firstKey) setSlide(ERROR_SLIDE[firstKey]);
        return;
      }
      onDone();
    } catch {
      setError("保存に失敗しました。");
    } finally {
      setBusy(false);
    }
  };

  const goNext = (e?: FormEvent) => {
    e?.preventDefault();
    if (busy) return;
    const errors = validateSlide(slide);
    if (Object.keys(errors).length) {
      setFieldErrors(errors);
      setError(null);
      return;
    }
    setFieldErrors({});
    setError(null);
    if (slide < SLIDE_COUNT - 1) {
      setSlide(slide + 1);
      return;
    }
    void submitProfile();
  };

  const goBack = () => {
    if (busy || slide === 0) return;
    setFieldErrors({});
    setError(null);
    setPhotoPickerOpen(false);
    setSlide(slide - 1);
  };

  const skipAvatar = () => {
    if (busy) return;
    setAvatar(null);
    void submitProfile(null);
  };

  const onAvatarChange = (file: File | null) => {
    setAvatar(file);
    if (file) setPhotoPickerOpen(false);
  };

  const err = (key: string) =>
    fieldError(key) ? <p className="field-error">{fieldError(key)}</p> : null;

  return (
    <div className="onboarding-wizard">
      <div className="onboarding-wizard-bar">
        {slide > 0 ? (
          <button
            type="button"
            className="onboarding-back"
            onClick={goBack}
            disabled={busy}
          >
            戻る
          </button>
        ) : (
          <span className="onboarding-back-spacer" />
        )}
        <div
          className="onboarding-dots"
          role="img"
          aria-label={`プロフィール設定 ${slide + 1} / ${SLIDE_COUNT}`}
        >
          {Array.from({ length: SLIDE_COUNT }, (_, index) => (
            <span
              key={index}
              className={index <= slide ? "is-on" : undefined}
            />
          ))}
        </div>
        <span className="onboarding-back-spacer" />
      </div>

      {error ? <p className="field-error">{error}</p> : null}

      <div className="onboarding-slides">
        <div
          className="onboarding-track"
          style={{ transform: `translateX(-${slide * 100}%)` }}
        >
          <section className="onboarding-pane" aria-hidden={slide !== 0}>
            <form onSubmit={goNext}>
              <div className="onboarding-pane-body">
                <h1 className="onboarding-question">WaseWaseで使う名前は？</h1>
                <label className="visually-hidden" htmlFor="ob-name">
                  表示名
                </label>
                <input
                  id="ob-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="例：田中太郎"
                  autoComplete="nickname"
                  maxLength={80}
                  tabIndex={slide === 0 ? 0 : -1}
                />
                {err("name")}
              </div>
              <button type="submit" className="btn onboarding-cta" disabled={busy}>
                次へ
              </button>
            </form>
          </section>

          <section className="onboarding-pane" aria-hidden={slide !== 1}>
            <form onSubmit={goNext}>
              <div className="onboarding-pane-body">
                <h1 className="onboarding-question">ユーザーネームを決めよう</h1>
                <label className="visually-hidden" htmlFor="ob-username">
                  ユーザーネーム
                </label>
                <div className="onboarding-handle">
                  <span className="onboarding-handle-at" aria-hidden="true">
                    @
                  </span>
                  <input
                    id="ob-username"
                    value={username}
                    onChange={(e) => setUsername(normalizeHandle(e.target.value))}
                    placeholder="tanaka_taro"
                    autoComplete="off"
                    autoCapitalize="none"
                    spellCheck={false}
                    tabIndex={slide === 1 ? 0 : -1}
                  />
                </div>
                {err("username")}
                <p className="onboarding-note">
                  英数字と _ のみ、3〜30文字。他の早稲田生から見える、公開ユーザーネームです。
                </p>
              </div>
              <button type="submit" className="btn onboarding-cta" disabled={busy}>
                次へ
              </button>
            </form>
          </section>

          <section className="onboarding-pane" aria-hidden={slide !== 2}>
            <form onSubmit={goNext}>
              <div className="onboarding-pane-body">
                <h1 className="onboarding-question">学部を教えてください</h1>
                <label className="visually-hidden" htmlFor="ob-faculty">
                  学部
                </label>
                <select
                  id="ob-faculty"
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                  tabIndex={slide === 2 ? 0 : -1}
                >
                  <option value="">学部を選択</option>
                  {faculties.map((f) => (
                    <option key={f.value} value={f.value}>
                      {f.label}
                    </option>
                  ))}
                </select>
                {err("department")}
              </div>
              <button type="submit" className="btn onboarding-cta" disabled={busy}>
                次へ
              </button>
            </form>
          </section>

          <section
            className={`onboarding-pane onboarding-avatar-step${
              photoPickerOpen ? " is-picking" : ""
            }`}
            aria-hidden={slide !== 3}
          >
            <form onSubmit={goNext}>
              <div className="onboarding-pane-body">
                <h1 className="onboarding-question">プロフィール写真を追加しよう</h1>
                <div
                  className={`onboarding-avatar-btn${avatarSrc ? "" : " is-empty"}`}
                  aria-hidden="true"
                >
                  {avatarSrc ? (
                    <img src={avatarSrc} alt="" />
                  ) : (
                    <span>+</span>
                  )}
                </div>
                <button
                  type="button"
                  className="onboarding-photo-add"
                  onClick={() => setPhotoPickerOpen((open) => !open)}
                  tabIndex={slide === 3 ? 0 : -1}
                >
                  写真を追加
                </button>
                <ImagePickField
                  id="ob-avatar"
                  value={avatar}
                  onChange={onAvatarChange}
                  disabled={busy || slide !== 3 || !photoPickerOpen}
                  hint="JPEG / PNG / GIF / WebP、5MB以下。あとからでも設定できます。"
                  allowClear={Boolean(avatar)}
                />
                {err("avatar")}
              </div>
              <button type="submit" className="btn onboarding-cta" disabled={busy}>
                次へ
              </button>
              <p className="onboarding-skip-wrap">
                <button
                  type="button"
                  className="onboarding-skip"
                  disabled={busy}
                  onClick={skipAvatar}
                >
                  今はスキップ
                </button>
              </p>
            </form>
          </section>
        </div>
      </div>
    </div>
  );
}
