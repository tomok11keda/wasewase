/**
 * Official Waseda University service shortcut.
 * Public portal URL only — WaseWase never collects, stores, or proxies
 * MyWaseda credentials, cookies, or academic records.
 *
 * https://my.waseda.jp/ is the login URL published by Waseda IT Service
 * Portal (https://support.waseda.jp/it/s/login-trouble). That published
 * entry reaches the official hub where MyWaseda, Moodle, and grade
 * inquiry are available. Device testing confirmed the same destination.
 */
export const WASEDA_OFFICIAL_SERVICE = {
  label: "早稲田大学サービス",
  note: "MyWaseda・Moodle・成績照会",
  href: "https://my.waseda.jp/",
} as const;
