import { defineConfig } from "wxt";

export default defineConfig({
  srcDir: "src",
  outDir: "dist",
  modules: ["@wxt-dev/module-react"],
  manifest: {
    name: "Still Open",
    description: "Treat an open tab as unfinished business. File it, then close.",
    version: "0.1.0",
    permissions: ["tabs", "tabGroups", "sidePanel", "storage", "alarms"],
    host_permissions: ["http://127.0.0.1:8080/*", "https://*.run.app/*"],
    optional_host_permissions: ["https://*/*", "http://*/*"],
    action: {
      default_title: "Still Open",
    },
  },
});
