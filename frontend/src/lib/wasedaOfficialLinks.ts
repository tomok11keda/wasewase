/**
 * Official Waseda University service shortcuts.
 * These are public portal URLs only — WaseWase never collects, stores,
 * or proxies MyWaseda credentials, cookies, or academic records.
 *
 * Sources (verified 2026-09-24, not guessed):
 * - MyWaseda login URL published by Waseda IT Service Portal
 *   https://support.waseda.jp/it/s/login-trouble → https://my.waseda.jp/
 *   (https://my.waseda.jp/ meta-refreshes to /login/login)
 * - Waseda Moodle direct login published for when MyWaseda is unavailable
 *   https://support.waseda.jp/it/s/article/000007523 → https://wsdmoodle.waseda.jp/
 * - 成績照会: Support Anywhere tells students to open the MyWaseda login
 *   screen and tap 「成績照会・科目登録専用」. The banner href on that
 *   page (coursereg.waseda.jp/...?HID_P14=…) starts a session-memory SAML
 *   RelayState; the IdP also warns not to bookmark the auth screen.
 *   Link the stable official login page instead of that deep link.
 */
export const WASEDA_OFFICIAL_LINKS = [
  {
    id: "mywaseda",
    label: "MyWaseda",
    href: "https://my.waseda.jp/",
    note: "（外部サイト）",
  },
  {
    id: "moodle",
    label: "Waseda Moodle",
    href: "https://wsdmoodle.waseda.jp/",
    note: "（外部サイト）",
  },
  {
    id: "grades",
    label: "成績照会",
    href: "https://my.waseda.jp/login/login",
    note: "（外部サイト）",
    title: "MyWasedaログイン画面の「成績照会・科目登録専用」から開きます",
  },
] as const;

export type WasedaOfficialLinkId = (typeof WASEDA_OFFICIAL_LINKS)[number]["id"];
