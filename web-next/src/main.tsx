import React from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/inter";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/glass.css";
import App from "./App";
import "./styles/interactions.css";

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);