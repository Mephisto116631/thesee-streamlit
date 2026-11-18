package com.thesee.app;

import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import androidx.core.content.FileProvider;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Mise à jour intégrée (comme Sisyphe) : l'APK est téléchargé dans le cache
 * (cacheDir/updates) avec sa progression, puis l'installeur Android est ouvert.
 * Copié dans le projet Android par le workflow mobile.yml.
 */
@CapacitorPlugin(name = "MiseAJour")
public class MiseAJourPlugin extends Plugin {

    private File dossier() {
        File d = new File(getContext().getCacheDir(), "updates");
        d.mkdirs();
        return d;
    }

    /** APK déjà téléchargé en entier (taille conforme) : { chemin } ou { chemin: null }. */
    @PluginMethod
    public void enCache(PluginCall call) {
        File f = new File(dossier(), call.getString("nom", "thesee.apk"));
        long taille = call.getLong("taille", 0L);
        JSObject r = new JSObject();
        r.put("chemin", f.exists() && (taille == 0 || f.length() == taille) ? f.getAbsolutePath() : null);
        call.resolve(r);
    }

    /** Télécharge { url, nom } ; émet "progression" { p: 0..1 } ; renvoie { chemin }. */
    @PluginMethod
    public void telecharger(PluginCall call) {
        String url = call.getString("url");
        String nom = call.getString("nom", "thesee.apk");
        long tailleAttendue = call.getLong("taille", 0L);
        if (url == null) { call.reject("url manquante"); return; }
        new Thread(() -> {
            File fichier = new File(dossier(), nom);
            File part = new File(dossier(), nom + ".part"); // jamais d'APK à moitié écrit
            HttpURLConnection c = null;
            try {
                c = (HttpURLConnection) new URL(url).openConnection();
                c.setInstanceFollowRedirects(true);
                c.setConnectTimeout(15000);
                c.setReadTimeout(30000);
                c.setRequestProperty("User-Agent", "thesee-app");
                int code = c.getResponseCode();
                if (code != 200) throw new Exception("HTTP " + code);
                long total = c.getContentLengthLong() > 0 ? c.getContentLengthLong() : tailleAttendue;
                try (InputStream in = c.getInputStream(); FileOutputStream out = new FileOutputStream(part)) {
                    byte[] buf = new byte[65536];
                    long recu = 0, dernier = 0;
                    int n;
                    while ((n = in.read(buf)) > 0) {
                        out.write(buf, 0, n);
                        recu += n;
                        long now = System.currentTimeMillis();
                        if (total > 0 && now - dernier > 150) {
                            dernier = now;
                            JSObject p = new JSObject();
                            p.put("p", (double) recu / total);
                            notifyListeners("progression", p);
                        }
                    }
                }
                if (fichier.exists()) fichier.delete();
                if (!part.renameTo(fichier)) throw new Exception("écriture impossible");
                JSObject r = new JSObject();
                r.put("chemin", fichier.getAbsolutePath());
                call.resolve(r);
            } catch (Exception e) {
                part.delete();
                call.reject("Téléchargement : " + e.getMessage());
            } finally {
                if (c != null) c.disconnect();
            }
        }).start();
    }

    /** Ouvre l'installeur : { etat: "started" } ou "needs_permission" (réglage « sources inconnues » ouvert). */
    @PluginMethod
    public void installer(PluginCall call) {
        String chemin = call.getString("chemin");
        if (chemin == null) { call.reject("chemin manquant"); return; }
        JSObject r = new JSObject();
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
                && !getContext().getPackageManager().canRequestPackageInstalls()) {
            Intent i = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + getContext().getPackageName()));
            i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            getContext().startActivity(i);
            r.put("etat", "needs_permission");
            call.resolve(r);
            return;
        }
        Uri uri = FileProvider.getUriForFile(getContext(), getContext().getPackageName() + ".fileprovider", new File(chemin));
        Intent i = new Intent(Intent.ACTION_VIEW)
                .setDataAndType(uri, "application/vnd.android.package-archive")
                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
        getContext().startActivity(i);
        r.put("etat", "started");
        call.resolve(r);
    }

    /** Octets occupés par les APK téléchargés. */
    @PluginMethod
    public void tailleCache(PluginCall call) {
        long n = 0;
        File[] fs = dossier().listFiles();
        if (fs != null) for (File f : fs) n += f.length();
        JSObject r = new JSObject();
        r.put("octets", n);
        call.resolve(r);
    }

    /** Supprime les APK obsolètes, sauf { garder } (mise à jour prête). Renvoie { liberes }. */
    @PluginMethod
    public void nettoyer(PluginCall call) {
        String garder = call.getString("garder");
        long n = 0;
        File[] fs = dossier().listFiles();
        if (fs != null) for (File f : fs) {
            if (garder != null && f.getName().equals(garder)) continue;
            long l = f.length();
            if (f.delete()) n += l;
        }
        JSObject r = new JSObject();
        r.put("liberes", n);
        call.resolve(r);
    }
}
