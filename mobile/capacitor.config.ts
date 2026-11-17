import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.thesee.app",
  appName: "Thésée",
  webDir: "dist",
  backgroundColor: "#0b1120",
  android: { allowMixedContent: false },
};

export default config;
