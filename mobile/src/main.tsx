import { render } from "preact";
import { App } from "./app";
import "./styles.css";

render(<App />, document.getElementById("app")!);

// PWA : service worker seulement dans le navigateur (pas dans l'APK Capacitor)
const isNative = (window as any).Capacitor?.isNativePlatform?.();
if ("serviceWorker" in navigator && !isNative && import.meta.env.PROD) {
  navigator.serviceWorker.register("./sw.js").catch(() => {});
}
