/**
 * Minimal static SPA host for Phase A Playwright (no Django).
 * Serves /app/* shell + /static/frontend/* assets and stubs key APIs.
 */
import http from "node:http";
import { readFileSync, existsSync } from "node:fs";
import { extname, join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, "../..");
const port = Number(process.env.MOCK_SPA_PORT || 8765);

const meBrowse = {
  authenticated: false,
  is_browse_mode: true,
  react_spa_enabled: true,
  user: null,
  unread_notifications: 0,
  dm_unread_total: 0,
  onboarding_required: false,
  onboarding_completed: true,
};

const meAuthed = {
  authenticated: true,
  is_browse_mode: false,
  react_spa_enabled: true,
  user: {
    id: 1,
    email: "demo@example.com",
    username: "demo",
    display_name: "デモ学生",
    avatar_url: "",
    initial: "デ",
    department: "政治経済学部",
  },
  unread_notifications: 0,
  dm_unread_total: 0,
  onboarding_required: false,
  onboarding_completed: true,
  linked_profiles: [],
  can_add_linked_profile: false,
};

const spaHtml = `<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="csrf-token" content="test-csrf">
  <title>わせわせ</title>
  <link rel="stylesheet" href="/static/frontend/assets/main.css">
</head>
<body class="shell-desktop">
  <div id="root"></div>
  <script type="module" src="/static/frontend/assets/main.js"></script>
</body>
</html>`;

const mime = {
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};

function sendJson(res, status, body) {
  const raw = JSON.stringify(body);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
  });
  res.end(raw);
}

function sendFile(res, filePath) {
  if (!existsSync(filePath)) {
    res.writeHead(404);
    res.end("not found");
    return;
  }
  const type = mime[extname(filePath)] || "application/octet-stream";
  res.writeHead(200, { "Content-Type": type });
  res.end(readFileSync(filePath));
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url || "/", `http://127.0.0.1:${port}`);
  const path = url.pathname;

  if (path === "/api/v1/me/" || path === "/api/v1/me") {
    const browse =
      url.searchParams.get("browse") === "1" ||
      req.headers.cookie?.includes("mock_browse=1");
    return sendJson(res, 200, browse ? meBrowse : meAuthed);
  }
  if (path.startsWith("/api/v1/search")) {
    return sendJson(res, 200, {
      ok: true,
      q: "",
      tab: "all",
      results: [],
      users: [],
      organizations: [],
      products: [],
      offerings: [],
      posts: [],
      threads: [],
      discover: {
        trending: [],
        faculty: null,
        communities: [],
        products: [],
      },
    });
  }
  if (path.startsWith("/api/v1/courses/discover")) {
    return sendJson(res, 200, {
      ok: true,
      enrolled: [],
      active: [],
      popular: [],
    });
  }
  if (path.startsWith("/api/v1/communities/threads")) {
    return sendJson(res, 200, { ok: true, threads: [] });
  }
  if (path.startsWith("/api/v1/flea")) {
    return sendJson(res, 200, {
      ok: true,
      products: [],
      feed: "all",
      q: "",
      faculty: "",
      campus: "",
      campus_label: "",
      order: "new",
      order_label: "新着",
      feed_following_unauthenticated: false,
      user_faculty: "",
      faculty_tabs: [],
      campus_tabs: [],
      order_options: [],
    });
  }
  if (path.startsWith("/api/timetable") || path.startsWith("/api/v1/timetable")) {
    return sendJson(res, 200, {
      ok: true,
      slots: {},
      is_timetable_public: true,
      can_edit: true,
    });
  }
  if (path.startsWith("/api/v1/timeline") || path.startsWith("/api/timeline")) {
    return sendJson(res, 200, { ok: true, posts: [], next_cursor: null });
  }
  if (path.startsWith("/api/")) {
    return sendJson(res, 200, { ok: true });
  }

  if (path.startsWith("/static/frontend/")) {
    return sendFile(res, join(root, path.slice(1)));
  }

  if (path === "/app" || path.startsWith("/app/")) {
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(spaHtml);
    return;
  }

  res.writeHead(302, { Location: "/app/" });
  res.end();
});

server.listen(port, "127.0.0.1", () => {
  console.log(`mock spa http://127.0.0.1:${port}/app/`);
});
