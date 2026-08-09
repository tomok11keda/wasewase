import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles/tokens.css";
import "./styles/shell.css";
import "./styles/timeline.css";
import "./styles/home.css";
import "./styles/image-pick.css";
import "./styles/faculty-filter.css";
import "./styles/local-search.css";
import "./styles/community.css";
import "./styles/flea.css";
import "./styles/timetable.css";
import "./styles/profile.css";
import "./styles/dm.css";
import "./styles/notifications-auth.css";
import "./styles/ios-form-zoom.css";

document.body.classList.add("shell-desktop");

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
