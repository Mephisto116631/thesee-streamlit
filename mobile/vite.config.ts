import { defineConfig } from "vite";
import preact from "@preact/preset-vite";

// base "./" : chemins relatifs -> le même build marche dans l'APK (Capacitor)
// et sur GitHub Pages (https://<user>.github.io/thesee-streamlit/).
export default defineConfig({
  base: "./",
  plugins: [preact()],
  server: { fs: { allow: [".."] } }, // ranges.json est à la racine du dépôt
  build: { outDir: "dist", chunkSizeWarningLimit: 900 },
});
