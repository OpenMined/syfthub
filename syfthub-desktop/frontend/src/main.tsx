import React from "react";
import { createRoot } from "react-dom/client";
import "@/index.css";
import App from "@/App";
import { SettingsProvider } from "@/contexts/SettingsContext";
import { ThemeProvider } from "@/contexts/ThemeContext";
import { UpdateProvider } from "@/contexts/UpdateContext";
import { TooltipProvider } from "@/components/ui/tooltip";

const container = document.getElementById("root");

const root = createRoot(container!);

root.render(
  <React.StrictMode>
    <ThemeProvider defaultTheme="dark">
      <SettingsProvider>
        <UpdateProvider>
          <TooltipProvider>
            <App />
          </TooltipProvider>
        </UpdateProvider>
      </SettingsProvider>
    </ThemeProvider>
  </React.StrictMode>
);
