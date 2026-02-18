import React from "react";
import { createRoot } from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { SettingsProvider } from "@/contexts/SettingsContext";
import { TooltipProvider } from "@/components/ui/tooltip";

const container = document.getElementById("root");

const root = createRoot(container!);

root.render(
  <React.StrictMode>
    <SettingsProvider>
      <TooltipProvider>
        <App />
      </TooltipProvider>
    </SettingsProvider>
  </React.StrictMode>
);
