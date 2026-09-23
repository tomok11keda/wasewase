"""Push pre-permission UX: bootstrap must not auto-prompt; CTA is user-initiated."""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def _function_body(source: str, name: str) -> str:
    marker = f"async function {name}("
    start = source.find(marker)
    if start < 0:
        marker = f"function {name}("
        start = source.find(marker)
    if start < 0:
        marker = f"export function {name}("
        start = source.find(marker)
    if start < 0:
        raise AssertionError(f"missing function {name}")
    depth = 0
    started = False
    for i, ch in enumerate(source[start:], start=start):
        if ch == "{":
            depth += 1
            started = True
        elif ch == "}":
            depth -= 1
            if started and depth == 0:
                return source[start : i + 1]
    raise AssertionError(f"unterminated function {name}")


class PushPrePermissionScriptTests(SimpleTestCase):
    def test_static_and_www_capacitor_native_match(self):
        static_js = _read("static/js/capacitor_native.js")
        www_js = _read("www/js/capacitor_native.js")
        self.assertEqual(static_js, www_js)

    def test_bootstrap_checks_and_does_not_auto_request(self):
        source = _read("static/js/capacitor_native.js")
        init = _function_body(source, "initializePushNotifications")
        self.assertIn("readReceivePermission", init)
        self.assertNotIn("requestPermissions", init)
        self.assertIn("plugin_missing", init)
        self.assertIn('receive === "granted"', init)
        self.assertIn('receive === "denied"', init)
        self.assertIn("waiting for user CTA", init)

        user = _function_body(source, "requestPushPermissionFromUser")
        self.assertIn("requestPermissions", user)
        self.assertIn("pushPermissionRequestInFlight", user)
        self.assertIn("plugin_missing", user)
        self.assertIn('current === "denied"', user)
        self.assertIn("acquireFcmTokenAfterGrant", user)

        check = _function_body(source, "readReceivePermission")
        self.assertIn("checkPermissions", check)

        self.assertIn("await initializePushNotifications()", source)
        self.assertIn("requestPushPermissionFromUser: requestPushPermissionFromUser", source)
        self.assertIn("tokenReceived", source)
        self.assertIn("notificationActionPerformed", source)
        self.assertIn("wase:push-open", source)
        self.assertIn("wase:push-received", source)
        self.assertIn("adoptFcmToken", source)

    def test_spa_shell_still_loads_production_capacitor_native(self):
        head = _read("templates/includes/pwa_head.html")
        self.assertIn("js/capacitor_native.js", head)
        spa = _read("templates/spa.html")
        self.assertIn("pwa_head.html", spa)


def should_show_push_prepermission(
    *,
    plugin_available: bool,
    permission: str,
    dismissed_this_session: bool,
    authenticated: bool,
    onboarding_required: bool,
    pathname: str,
) -> bool:
    """Mirrors frontend/src/lib/pushPrePermission.ts shouldShowPushPrePermission."""
    if not plugin_available:
        return False
    if dismissed_this_session:
        return False
    if not authenticated:
        return False
    if onboarding_required:
        return False
    prefixes = (
        "/login",
        "/signup",
        "/verify",
        "/onboarding",
        "/password-reset",
        "/internal/push-diag",
    )
    if any(pathname == p or pathname.startswith(p + "/") for p in prefixes):
        return False
    return permission == "prompt"


class PushPrePermissionDecisionTests(SimpleTestCase):
    def _base(self, **overrides):
        data = {
            "plugin_available": True,
            "permission": "prompt",
            "dismissed_this_session": False,
            "authenticated": True,
            "onboarding_required": False,
            "pathname": "/",
        }
        data.update(overrides)
        return should_show_push_prepermission(**data)

    def test_plugin_unavailable_hides_ui(self):
        self.assertFalse(self._base(plugin_available=False))

    def test_granted_hides_ui(self):
        self.assertFalse(self._base(permission="granted"))

    def test_denied_hides_ui(self):
        self.assertFalse(self._base(permission="denied"))

    def test_not_determined_shows_ui_on_home(self):
        self.assertTrue(self._base(permission="prompt", pathname="/"))

    def test_later_hides_for_session(self):
        self.assertFalse(self._base(dismissed_this_session=True))

    def test_login_and_onboarding_do_not_show(self):
        self.assertFalse(self._base(pathname="/login"))
        self.assertFalse(self._base(pathname="/signup"))
        self.assertFalse(self._base(pathname="/onboarding"))
        self.assertFalse(self._base(authenticated=False, pathname="/"))
        self.assertFalse(self._base(onboarding_required=True))

    def test_typescript_source_matches_decision_table(self):
        ts = _read("frontend/src/lib/pushPrePermission.ts")
        self.assertIn('return input.permission === "prompt"', ts)
        self.assertIn("if (!input.pluginAvailable) return false", ts)
        self.assertIn("if (input.dismissedThisSession) return false", ts)
        self.assertIn("if (!input.authenticated) return false", ts)
        self.assertIn("if (input.onboardingRequired) return false", ts)
        self.assertIn("shouldAutoRequestOnBootstrap", ts)
        self.assertIn("return false", _function_body(ts, "shouldAutoRequestOnBootstrap"))
        prompt = _read("frontend/src/components/NativePushPermissionPrompt.tsx")
        self.assertIn("わせわせを見逃さない", prompt)
        self.assertIn("通知を受け取る", prompt)
        self.assertIn("あとで", prompt)
        self.assertIn("requestPushPermissionFromUser", prompt)
        self.assertNotIn("必須", prompt)
        self.assertIn("createPortal", prompt)
        self.assertIn("document.body", prompt)
        router = _read("frontend/src/components/NativePushOpenRouter.tsx")
        self.assertIn("wase:push-open", router)
        self.assertIn("consumePendingPushOpenLink", router)


class PushPrePermissionStackingTests(SimpleTestCase):
    def test_overlay_sits_above_compose_fab(self):
        overlay = _read("frontend/src/styles/push-preperm.css")
        home = _read("frontend/src/styles/home.css")
        shell = _read("frontend/src/styles/shell.css")
        self.assertRegex(overlay, r"\.push-preperm\s*\{[^}]*z-index:\s*500")
        self.assertRegex(home, r"\.compose-fab\s*\{[^}]*z-index:\s*250")
        self.assertRegex(shell, r"\.bottom-nav\s*\{[^}]*z-index:\s*200")
        self.assertGreater(500, 250)
        self.assertGreater(500, 200)
        # Permission bootstrap must still not auto-request.
        native = _read("static/js/capacitor_native.js")
        init = _function_body(native, "initializePushNotifications")
        self.assertNotIn("requestPermissions", init)


class PushLinkHelperSourceTests(SimpleTestCase):
    def test_deep_link_helper_unchanged_markers(self):
        src = _read("frontend/src/lib/nativePush.ts")
        self.assertIn("export function pushLinkToRouterPath", src)
        self.assertIn("wase:push-token", src)
        self.assertIn("/api/push-token/", src)
        self.assertIn("unregisterNativePushForSession", src)
        self.assertIn("sanitizePushDiagError", src)
        self.assertTrue(
            re.search(r"function pushLinkToRouterPath", src)
            or "export function pushLinkToRouterPath" in src
        )
