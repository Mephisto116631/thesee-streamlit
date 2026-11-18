package com.thesee.app;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

/** Remplace l'activité générée par Capacitor pour enregistrer le plugin de mise à jour. */
public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(MiseAJourPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
