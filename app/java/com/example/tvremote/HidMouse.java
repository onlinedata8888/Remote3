package com.example.tvremote;

import android.app.Activity;
import android.app.Application;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothHidDevice;
import android.bluetooth.BluetoothHidDeviceAppSdpSettings;
import android.bluetooth.BluetoothProfile;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.IntentFilter;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;
import org.json.JSONArray;
import org.json.JSONObject;

import java.util.Set;
import java.util.concurrent.Executor;

/**
 * Phone -> PC Bluetooth HID mouse ("PC mode" of the Mouse page).
 *
 * The phone registers itself as a Bluetooth HID *device* (BluetoothHidDevice, Android 9 / API 28+) that
 * looks like a normal 3-button mouse with a scroll wheel + horizontal scroll (AC Pan). Once the PC has
 * paired with the phone and the app connected to it, move()/click()/scroll() send real HID input reports,
 * so the PC's own cursor moves. JS side object name: "HidNative"; native -> JS callback:
 * window.__hid.onState(state, hostName).
 *
 * state: unsupported | noperm | btoff | starting | ready | connecting | connected | error
 */
final class HidMouse {
    private static final int REQ_PERM = 73;
    private static final String PREF_LAST = "hid_last_host";
    private static final String PREF_PROFILE = "hid_profile";   // 0 = mouse+keyboard+pad (combo), 1 = pad only

    /** Mouse report (Report ID 1): [buttons][dx][dy][wheel][acPan]. Keyboard report (Report ID 2): [mods][0][k1..k6]. */
    private static final int[] DESC = {
        0x05, 0x01,             // Usage Page (Generic Desktop)
        0x09, 0x02,             // Usage (Mouse)
        0xA1, 0x01,             // Collection (Application)
        0x85, 0x01,             //   Report ID (1)
        0x09, 0x01,             //   Usage (Pointer)
        0xA1, 0x00,             //   Collection (Physical)
        0x05, 0x09,             //     Usage Page (Buttons)
        0x19, 0x01, 0x29, 0x03, //     Usage Min (1) Max (3)
        0x15, 0x00, 0x25, 0x01, //     Logical Min 0 Max 1
        0x95, 0x03, 0x75, 0x01, //     Report Count 3, Size 1
        0x81, 0x02,             //     Input (Data,Var,Abs)  -> 3 button bits
        0x95, 0x01, 0x75, 0x05, //     Report Count 1, Size 5
        0x81, 0x03,             //     Input (Const)          -> padding
        0x05, 0x01,             //     Usage Page (Generic Desktop)
        0x09, 0x30, 0x09, 0x31, //     Usage X, Usage Y
        0x09, 0x38,             //     Usage Wheel
        0x15, 0x81, 0x25, 0x7F, //     Logical Min -127 Max 127
        0x75, 0x08, 0x95, 0x03, //     Size 8, Count 3
        0x81, 0x06,             //     Input (Data,Var,Rel)
        0x05, 0x0C,             //     Usage Page (Consumer)
        0x0A, 0x38, 0x02,       //     Usage (AC Pan)  -> horizontal scroll
        0x15, 0x81, 0x25, 0x7F,
        0x75, 0x08, 0x95, 0x01,
        0x81, 0x06,             //     Input (Data,Var,Rel)
        0xC0, 0xC0,             // End Collection x2

        // ---- Keyboard (Report ID 2): [modifiers][reserved][key1..key6] ----
        0x05, 0x01,             // Usage Page (Generic Desktop)
        0x09, 0x06,             // Usage (Keyboard)
        0xA1, 0x01,             // Collection (Application)
        0x85, 0x02,             //   Report ID (2)
        0x05, 0x07,             //   Usage Page (Key Codes)
        0x19, 0xE0, 0x29, 0xE7, //   Usage Min (Left Ctrl) Max (Right GUI)
        0x15, 0x00, 0x25, 0x01, //   Logical Min 0 Max 1
        0x75, 0x01, 0x95, 0x08, //   Size 1, Count 8
        0x81, 0x02,             //   Input (Data,Var,Abs)  -> modifier byte
        0x95, 0x01, 0x75, 0x08, //   Count 1, Size 8
        0x81, 0x01,             //   Input (Const)          -> reserved byte
        0x95, 0x05, 0x75, 0x01, //   Count 5, Size 1
        0x05, 0x08,             //   Usage Page (LEDs)
        0x19, 0x01, 0x29, 0x05, //   Usage Min 1 Max 5
        0x91, 0x02,             //   Output (Data,Var,Abs) -> LEDs
        0x95, 0x01, 0x75, 0x03, //   Count 1, Size 3
        0x91, 0x01,             //   Output (Const)         -> LED padding
        0x95, 0x06, 0x75, 0x08, //   Count 6, Size 8
        0x15, 0x00, 0x25, 0x65, //   Logical Min 0 Max 101
        0x05, 0x07,             //   Usage Page (Key Codes)
        0x19, 0x00, 0x29, 0x65, //   Usage Min 0 Max 101
        0x81, 0x00,             //   Input (Data,Array)     -> 6 pressed keys
        0xC0,                   // End Collection

        // ---- Game pad (Report ID 3): [btnLo][btnHi][hat][lx][ly][rx][ry] ----
        0x05, 0x01,             // Usage Page (Generic Desktop)
        0x09, 0x05,             // Usage (Game Pad)
        0xA1, 0x01,             // Collection (Application)
        0x85, 0x03,             //   Report ID (3)
        0x05, 0x09,             //   Usage Page (Buttons)
        0x19, 0x01, 0x29, 0x10, //   Usage Min 1 Max 16
        0x15, 0x00, 0x25, 0x01, //   Logical Min 0 Max 1
        0x75, 0x01, 0x95, 0x10, //   Size 1, Count 16
        0x81, 0x02,             //   Input (Data,Var,Abs)  -> 16 buttons
        0x05, 0x01,             //   Usage Page (Generic Desktop)
        0x09, 0x39,             //   Usage (Hat switch)
        0x15, 0x01, 0x25, 0x08, //   Logical Min 1 Max 8 (0 = released)
        0x75, 0x04, 0x95, 0x01, //   Size 4, Count 1
        0x81, 0x42,             //   Input (Data,Var,Abs,Null state)
        0x75, 0x04, 0x95, 0x01, //   Size 4, Count 1
        0x81, 0x03,             //   Input (Const) -> padding
        0x09, 0x30, 0x09, 0x31, //   Usage X, Usage Y   (left stick)
        0x09, 0x32, 0x09, 0x35, //   Usage Z, Usage Rz  (right stick)
        0x15, 0x81, 0x25, 0x7F, //   Logical Min -127 Max 127
        0x75, 0x08, 0x95, 0x04, //   Size 8, Count 4
        0x81, 0x02,             //   Input (Data,Var,Abs)
        0xC0                    // End Collection
    };

    /**
     * Pad-only profile (Report ID 1): [btnLo][btnHi][hat][lx][ly][rx][ry] - a plain game pad with nothing else, which is what
     * hosts (Android TV, Windows, Mac, Linux) expect from a real controller. Same 7-byte layout as the pad collection above.
     */
    private static final int[] PAD_DESC = {
        0x05, 0x01, 0x09, 0x05, 0xA1, 0x01,       // Generic Desktop / Game Pad / Collection (Application)
        0x85, 0x01,                               //   Report ID (1)
        0x05, 0x09, 0x19, 0x01, 0x29, 0x10,       //   Buttons 1..16
        0x15, 0x00, 0x25, 0x01, 0x75, 0x01, 0x95, 0x10,
        0x81, 0x02,
        0x05, 0x01, 0x09, 0x39,                   //   Hat switch
        0x15, 0x01, 0x25, 0x08, 0x35, 0x00, 0x46, 0x3B, 0x01, 0x65, 0x14,   // 1..8 -> 0..315 degrees
        0x75, 0x04, 0x95, 0x01, 0x81, 0x42,
        0x65, 0x00,                               //   Unit none
        0x75, 0x04, 0x95, 0x01, 0x81, 0x03,       //   padding
        0x05, 0x01, 0x09, 0x30, 0x09, 0x31, 0x09, 0x32, 0x09, 0x35,   // X, Y, Z, Rz
        0x15, 0x81, 0x25, 0x7F, 0x75, 0x08, 0x95, 0x04, 0x81, 0x02,
        0xC0
    };

    private final Activity act;
    private final WebView web;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final SharedPreferences prefs;
    private final Executor exec = new Executor() {
        public void execute(Runnable r) { ui.post(r); }
    };

    private BluetoothAdapter adapter;
    private BluetoothHidDevice hid;
    private volatile BluetoothDevice host;
    private volatile boolean registered;
    private boolean proxyRequested;
    private boolean wantStart;          // start() was called; finish once permission / Bluetooth is available
    private boolean userOff;            // user tapped "disconnect": don't auto-reconnect
    private int retry;                  // consecutive failed connect attempts
    private int tick;                   // keep-alive / watchdog counter
    private int noopFail;               // consecutive keep-alive reports the stack refused
    private BroadcastReceiver btReceiver;
    private final Runnable keepAlive = new Runnable() {
        public void run() {
            if (disposed) return;
            try { keepAliveTick(); } catch (Throwable ignored) {}
            ui.postDelayed(this, 4000);
        }
    };
    private final Runnable connectTimeout = new Runnable() {
        public void run() {
            if ("connected".equals(state)) return;
            try { String a = lastAddr(); if (hid != null && a != null && adapter != null) hid.disconnect(adapter.getRemoteDevice(a)); } catch (Throwable ignored) {}
            failedConnect();
        }
    };
    private final Runnable retryRun = new Runnable() {
        public void run() {
            String a = lastAddr();
            if (!"connected".equals(state) && !userOff && a != null) doConnect(a);
        }
    };
    private volatile String state = "idle";
    private volatile int buttons;
    private volatile int profile;                     // see PREF_PROFILE
    private volatile int[] lastPad = new int[6];      // btn, hat, lx, ly, rx, ry (re-sent as keep-alive)
    private Application.ActivityLifecycleCallbacks lifecycle;
    private boolean disposed;

    HidMouse(Activity a, WebView w) {
        act = a;
        web = w;
        prefs = a.getSharedPreferences("tvremote", 0);
        profile = prefs.getInt(PREF_PROFILE, 0) == 1 ? 1 : 0;
        lifecycle = new Application.ActivityLifecycleCallbacks() {
            public void onActivityResumed(Activity x) {
                // coming back from the permission dialog / "enable Bluetooth" screen
                if (x != act || disposed) return;
                if (wantStart) begin();
                else if (hid == null) warmUp();
                else if (!registered) restartQuiet();
                else if (registered && !"connected".equals(state) && !"connecting".equals(state)) { retry = 0; connectLast(); }
            }
            public void onActivityCreated(Activity x, Bundle b) {}
            public void onActivityStarted(Activity x) {}
            public void onActivityPaused(Activity x) {}
            public void onActivityStopped(Activity x) {}
            public void onActivitySaveInstanceState(Activity x, Bundle b) {}
            public void onActivityDestroyed(Activity x) {}
        };
        try { act.getApplication().registerActivityLifecycleCallbacks(lifecycle); } catch (Throwable ignored) {}
        // Bluetooth switched off / on (or the BT service restarted): re-register + reconnect by itself, no need to touch the app
        btReceiver = new BroadcastReceiver() {
            public void onReceive(Context c, Intent i) {
                if (disposed || i == null) return;
                if (!BluetoothAdapter.ACTION_STATE_CHANGED.equals(i.getAction())) return;
                int st = i.getIntExtra(BluetoothAdapter.EXTRA_STATE, -1);
                if (st == BluetoothAdapter.STATE_OFF || st == BluetoothAdapter.STATE_TURNING_OFF) {
                    ui.removeCallbacks(connectTimeout); ui.removeCallbacks(retryRun);
                    hid = null; registered = false; proxyRequested = false; host = null;
                    synchronized (mv) { pendX = 0; pendY = 0; }
                    buttons = 0;
                    push("btoff", "");
                } else if (st == BluetoothAdapter.STATE_ON) {
                    retry = 0;
                    ui.postDelayed(new Runnable() { public void run() { restartQuiet(); } }, 1200);
                }
            }
        };
        try { act.registerReceiver(btReceiver, new IntentFilter(BluetoothAdapter.ACTION_STATE_CHANGED)); } catch (Throwable ignored) {}
        ui.postDelayed(keepAlive, 4000);
    }

    /** Re-register as a HID mouse without any dialog (only if permission is already granted). */
    private void restartQuiet() {
        if (disposed || Build.VERSION.SDK_INT < 28 || !hasPerms()) return;
        BluetoothAdapter a = BluetoothAdapter.getDefaultAdapter();
        if (a == null || !a.isEnabled()) return;
        if (hid != null && registered) { if (!"connected".equals(state)) { retry = 0; connectLast(); } return; }
        if (hid != null) { registerApp(); return; }
        proxyRequested = false;
        begin();
    }

    /** Every 4 s: keeps the link busy (idle links get dropped by Windows / phone power saving) and re-connects if it is down. */
    private void keepAliveTick() {
        tick++;
        if ("connected".equals(state)) {
            boolean ok;
            if (profile == 1) { int[] p = lastPad; ok = sendPad(p[0], p[1], p[2], p[3], p[4], p[5]); }
            else ok = report(buttons, 0, 0, 0, 0);
            if (ok) { noopFail = 0; return; }
            if (++noopFail >= 3) {          // link looks dead although Android still says "connected"
                noopFail = 0;
                try { BluetoothDevice h = host; if (hid != null && h != null) hid.disconnect(h); } catch (Throwable ignored) {}
                host = null; retry = 0; failedConnect();
            }
            return;
        }
        noopFail = 0;
        if (userOff || "connecting".equals(state) || lastAddr() == null) return;
        if (tick % 5 != 0) return;           // ~ every 20 s
        if (hid == null || !registered) restartQuiet(); else { retry = 0; connectLast(); }
    }

    // ---------------------------------------------------------------------------------- helpers
    private static String q(String s) { return JSONObject.quote(s == null ? "" : s); }

    private void push(String st, String name) {
        state = st;
        final String js = "window.__hid&&window.__hid.onState&&window.__hid.onState(" + q(st) + "," + q(name) + ")";
        ui.post(new Runnable() {
            public void run() { try { web.evaluateJavascript(js, null); } catch (Throwable ignored) {} }
        });
    }

    private String hostName() {
        BluetoothDevice h = host;
        if (h == null) return "";
        try { String n = h.getName(); return n != null ? n : h.getAddress(); } catch (SecurityException e) { return h.getAddress(); }
    }

    private String[] neededPerms() {
        if (Build.VERSION.SDK_INT >= 31) {
            return new String[] { "android.permission.BLUETOOTH_CONNECT", "android.permission.BLUETOOTH_ADVERTISE" };
        }
        return new String[0];
    }

    private boolean hasPerms() {
        for (String p : neededPerms()) {
            if (act.checkSelfPermission(p) != PackageManager.PERMISSION_GRANTED) return false;
        }
        return true;
    }

    // ---------------------------------------------------------------------------------- start-up
    @JavascriptInterface
    public void start() {
        wantStart = true;
        ui.post(new Runnable() { public void run() { begin(); } });
    }

    private void begin() {
        if (disposed) return;
        if (Build.VERSION.SDK_INT < 28) { push("unsupported", ""); wantStart = false; return; }
        if (!hasPerms()) {
            push("noperm", "");
            try { act.requestPermissions(neededPerms(), REQ_PERM); } catch (Throwable ignored) {}
            return;   // onActivityResumed() calls begin() again after the dialog
        }
        adapter = BluetoothAdapter.getDefaultAdapter();
        if (adapter == null) { push("unsupported", ""); wantStart = false; return; }
        if (!adapter.isEnabled()) {
            push("btoff", "");
            try {
                Intent i = new Intent(BluetoothAdapter.ACTION_REQUEST_ENABLE);
                act.startActivity(i);
            } catch (Throwable ignored) {}
            return;   // resumes here after the user answers
        }
        wantStart = false;
        if (hid != null && registered) {
            if (state.equals("connected") || state.equals("connecting")) { push(state, hostName()); return; }
            retry = 0;
            if (lastAddr() != null && !userOff) connectLast(); else push("ready", "");
            return;
        }
        push("starting", "");
        if (proxyRequested) return;
        proxyRequested = true;
        boolean ok = false;
        try {
            ok = adapter.getProfileProxy(act.getApplicationContext(), new BluetoothProfile.ServiceListener() {
                public void onServiceConnected(int profile, BluetoothProfile proxy) {
                    if (profile != BluetoothProfile.HID_DEVICE) return;
                    hid = (BluetoothHidDevice) proxy;
                    registerApp();
                }
                public void onServiceDisconnected(int profile) {
                    if (profile != BluetoothProfile.HID_DEVICE) return;
                    hid = null; registered = false; proxyRequested = false; host = null;
                    push("connecting", lastName());
                    ui.postDelayed(new Runnable() { public void run() { restartQuiet(); } }, 2000);
                }
            }, BluetoothProfile.HID_DEVICE);
        } catch (Throwable t) { ok = false; }
        if (!ok) { proxyRequested = false; push("unsupported", ""); }
    }

    private void registerApp() {
        try {
            final boolean padOnly = profile == 1;
            int[] src = padOnly ? PAD_DESC : DESC;
            byte[] d = new byte[src.length];
            for (int i = 0; i < d.length; i++) d[i] = (byte) src[i];
            BluetoothHidDeviceAppSdpSettings sdp = padOnly
                    ? new BluetoothHidDeviceAppSdpSettings("Remote Gamepad", "Phone as Bluetooth game pad", "Remote 13",
                            (byte) (BluetoothHidDevice.SUBCLASS2_GAMEPAD << 2), d)
                    : new BluetoothHidDeviceAppSdpSettings("Remote 13 Mouse", "Phone as Bluetooth mouse + keyboard + game pad", "Remote 13",
                            BluetoothHidDevice.SUBCLASS1_COMBO, d);
            boolean ok = hid.registerApp(sdp, null, null, exec, new BluetoothHidDevice.Callback() {
                @Override public void onAppStatusChanged(BluetoothDevice pluggedDevice, boolean isRegistered) {
                    registered = isRegistered;
                    if (isRegistered) {
                        syncConnected();
                        if (!"connected".equals(state)) {
                            if (lastAddr() != null && !userOff) { retry = 0; connectLast(); }
                            else push("ready", "");
                        }
                    } else {
                        push("starting", "");
                        ui.postDelayed(new Runnable() { public void run() { if (!disposed && hid != null && !registered) registerApp(); } }, 2500);
                    }
                }
                @Override public void onConnectionStateChanged(BluetoothDevice device, int st) {
                    if (st == BluetoothProfile.STATE_CONNECTED) {
                        ui.removeCallbacks(connectTimeout); ui.removeCallbacks(retryRun);
                        retry = 0; userOff = false;
                        host = device;
                        prefs.edit().putString(PREF_LAST, device.getAddress()).apply();
                        push("connected", nameOf(device));
                    } else if (st == BluetoothProfile.STATE_CONNECTING) {
                        if (!"connected".equals(state)) push("connecting", nameOf(device));
                    } else if (st == BluetoothProfile.STATE_DISCONNECTED) {
                        boolean wasConnected = "connected".equals(state);
                        if (host != null && host.equals(device)) host = null;
                        synchronized (mv) { pendX = 0; pendY = 0; }
                        buttons = 0;
                        if (userOff) { push("ready", ""); }
                        else { if (wasConnected) retry = 0; failedConnect(); }   // link dropped / attempt failed -> keep trying quietly
                    }
                }
                @Override public void onGetReport(BluetoothDevice device, byte type, byte id, int bufferSize) {
                    try {
                        if (type == BluetoothHidDevice.REPORT_TYPE_INPUT) hid.replyReport(device, type, id, new byte[profile == 1 ? 7 : (id == 3 ? 7 : (id == 2 ? 8 : 5))]);
                        else hid.reportError(device, BluetoothHidDevice.ERROR_RSP_UNSUPPORTED_REQ);
                    } catch (Throwable ignored) {}
                }
                @Override public void onSetReport(BluetoothDevice device, byte type, byte id, byte[] data) {
                    try { hid.reportError(device, BluetoothHidDevice.ERROR_RSP_SUCCESS); } catch (Throwable ignored) {}
                }
                @Override public void onVirtualCableUnplug(BluetoothDevice device) {
                    if (host != null && host.equals(device)) host = null;
                    // PCs also send this when they sleep / reconnect, so do NOT give up: keep trying quietly
                    retry = 0; failedConnect();
                }
            });
            if (!ok) push("error", "");
        } catch (Throwable t) {
            push("error", "");
        }
    }

    private static String nameOf(BluetoothDevice d) {
        try { String n = d.getName(); return n != null ? n : d.getAddress(); } catch (SecurityException e) { return d.getAddress(); }
    }

    private String lastAddr() { return prefs.getString(PREF_LAST, null); }

    private String lastName() {
        try { String a = lastAddr(); return a == null || adapter == null ? "" : nameOf(adapter.getRemoteDevice(a)); } catch (Throwable t) { return ""; }
    }

    /** If a PC is already connected (e.g. it connected to us while the page was closed) pick it up. */
    private void syncConnected() {
        try {
            if (hid == null) return;
            java.util.List<BluetoothDevice> cd = hid.getConnectedDevices();
            if (cd != null && !cd.isEmpty()) { host = cd.get(0); push("connected", nameOf(host)); }
        } catch (Throwable ignored) {}
    }

    private void connectLast() {
        String a = lastAddr();
        if (a == null || hid == null || !registered || adapter == null || userOff) return;
        doConnect(a);
    }

    private void doConnect(String addr) {
        try {
            BluetoothDevice d = adapter.getRemoteDevice(addr);
            BluetoothDevice cur = host;
            if (cur != null && !cur.equals(d)) hid.disconnect(cur);
            push("connecting", nameOf(d));
            ui.removeCallbacks(connectTimeout);
            ui.postDelayed(connectTimeout, 9000);
            if (!hid.connect(d)) failedConnect();
        } catch (Throwable t) { failedConnect(); }
    }

    /** One connect attempt failed: retry with a short back-off, silently (UI keeps saying "Connecting"). */
    private void failedConnect() {
        ui.removeCallbacks(connectTimeout);
        ui.removeCallbacks(retryRun);
        if (userOff || lastAddr() == null) { push("ready", ""); return; }
        retry++;
        push("connecting", lastName());
        ui.postDelayed(retryRun, retry <= 6 ? Math.min(3000, 600L * retry) : 12000);   // never gives up while the app is alive
    }

    /** Call at app start / resume: registers as a HID mouse in the background (only if permission is already granted). */
    void warmUp() {
        ui.post(new Runnable() {
            public void run() {
                if (disposed || Build.VERSION.SDK_INT < 28 || hid != null || proxyRequested || !hasPerms()) return;
                BluetoothAdapter a = BluetoothAdapter.getDefaultAdapter();
                if (a == null || !a.isEnabled()) return;
                begin();
            }
        });
    }

    @JavascriptInterface
    public void reconnect() {
        ui.post(new Runnable() {
            public void run() {
                userOff = false; retry = 0;
                if (hid == null || !registered) { start(); return; }
                if (lastAddr() != null) connectLast(); else push("ready", "");
            }
        });
    }

    // ---------------------------------------------------------------------------------- pairing / connect
    /** [{"name","addr","connected","last"}] of every phone-paired Bluetooth device (the PC must be paired first). */
    @JavascriptInterface
    public String devices() {
        JSONArray out = new JSONArray();
        try {
            if (adapter == null) adapter = BluetoothAdapter.getDefaultAdapter();
            if (adapter == null || !hasPerms()) return "[]";
            Set<BluetoothDevice> bonded = adapter.getBondedDevices();
            String last = prefs.getString(PREF_LAST, "");
            BluetoothDevice h = host;
            if (bonded != null) {
                for (BluetoothDevice d : bonded) {
                    JSONObject o = new JSONObject();
                    o.put("name", nameOf(d));
                    o.put("addr", d.getAddress());
                    o.put("connected", h != null && h.equals(d) && "connected".equals(state));
                    o.put("last", d.getAddress().equals(last));
                    out.put(o);
                }
            }
        } catch (Throwable ignored) {}
        return out.toString();
    }

    @JavascriptInterface
    public void connect(final String addr) {
        ui.post(new Runnable() {
            public void run() {
                userOff = false; retry = 0;
                ui.removeCallbacks(retryRun);
                if (hid == null || !registered || adapter == null) { prefs.edit().putString(PREF_LAST, addr).apply(); start(); return; }
                doConnect(addr);
            }
        });
    }

    @JavascriptInterface
    public void disconnect() {
        ui.post(new Runnable() {
            public void run() {
                try {
                    userOff = true;
                    ui.removeCallbacks(connectTimeout); ui.removeCallbacks(retryRun);
                    BluetoothDevice h = host;
                    if (hid != null && h != null) hid.disconnect(h);
                    prefs.edit().remove(PREF_LAST).apply();
                    push("ready", "");
                } catch (Throwable ignored) {}
            }
        });
    }

    /** Makes the phone visible for 2 minutes so the PC can find and pair with it (first time only). */
    @JavascriptInterface
    public void discoverable() {
        ui.post(new Runnable() {
            public void run() {
                try {
                    Intent i = new Intent(BluetoothAdapter.ACTION_REQUEST_DISCOVERABLE);
                    i.putExtra(BluetoothAdapter.EXTRA_DISCOVERABLE_DURATION, 120);
                    act.startActivity(i);
                } catch (Throwable t) { btSettings(); }
            }
        });
    }

    @JavascriptInterface
    public void btSettings() {
        ui.post(new Runnable() {
            public void run() {
                try { act.startActivity(new Intent(Settings.ACTION_BLUETOOTH_SETTINGS)); } catch (Throwable ignored) {}
            }
        });
    }

    @JavascriptInterface
    public String status() {
        try {
            JSONObject o = new JSONObject();
            o.put("state", state);
            o.put("name", hostName());
            o.put("profile", profile);
            return o.toString();
        } catch (Throwable t) { return "{}"; }
    }

    // ---------------------------------------------------------------------------------- input
    private synchronized boolean report(int b, int dx, int dy, int wheel, int pan) {
        BluetoothDevice h = host;
        BluetoothHidDevice p = hid;
        if (profile != 0 || h == null || p == null || !"connected".equals(state)) return false;
        try {
            return p.sendReport(h, 1, new byte[] { (byte) b, (byte) dx, (byte) dy, (byte) wheel, (byte) pan });
        } catch (Throwable t) { return false; }
    }

    private static int clamp(int v) { return v > 127 ? 127 : (v < -127 ? -127 : v); }

    // ---- smooth pointer output ------------------------------------------------------------------
    // JS hands us one movement delta per screen frame (~60 Hz, chunky). A real mouse reports 125 Hz+.
    // So deltas are queued here and a pump thread drains them every 10 ms with exponential easing
    // (fractions carried over, nothing is lost) -> ~100 reports/s with evenly spread steps instead of
    // 60 big jumps. Clicks / scroll flush the queue first so they happen at the right spot.
    private final Object mv = new Object();
    private double pendX, pendY, carryX, carryY;
    private Thread pump;
    private boolean pumpRun;
    private static final double EASE = 0.4;
    private static final long TICK_MS = 8;

    private void ensurePump() {
        synchronized (mv) {
            if (pump != null) return;
            pumpRun = true;
            pump = new Thread(new Runnable() { public void run() { pumpLoop(); } }, "hid-pump");
            pump.setDaemon(true);
            pump.start();
        }
    }

    private void pumpLoop() {
        while (true) {
            double px, py;
            synchronized (mv) {
                while (pumpRun && pendX == 0 && pendY == 0) {
                    try { mv.wait(); } catch (InterruptedException e) { return; }
                }
                if (!pumpRun) return;
                double mag = Math.hypot(pendX, pendY);
                double f = mag < 2.0 ? 1.0 : EASE;
                px = pendX * f; py = pendY * f;
                pendX -= px; pendY -= py;
                if (mag < 2.0) { pendX = 0; pendY = 0; }
            }
            emit(px, py);
            try { Thread.sleep(TICK_MS); } catch (InterruptedException e) { return; }
        }
    }

    private synchronized void emit(double px, double py) {
        double tx = px + carryX, ty = py + carryY;
        int ix = (int) tx, iy = (int) ty;          // truncate toward zero, keep the fraction for next time
        carryX = tx - ix; carryY = ty - iy;
        int guard = 40;
        while ((ix != 0 || iy != 0) && guard-- > 0) {
            int sx = clamp(ix), sy = clamp(iy);
            if (!report(buttons, sx, sy, 0, 0)) {
                // the Bluetooth stack refused this report (busy): don't lose the movement - retry on the next tick
                if ("connected".equals(state)) {
                    synchronized (mv) { pendX += ix; pendY += iy; }
                }
                return;
            }
            ix -= sx; iy -= sy;
        }
    }

    private void flushPending() {
        double px, py;
        synchronized (mv) { px = pendX; py = pendY; pendX = 0; pendY = 0; }
        if (px != 0 || py != 0) emit(px, py);
    }

    /** Relative pointer movement in HID units (fractions allowed; smoothed + sent at ~100 Hz). */
    @JavascriptInterface
    public void move(double dx, double dy) {
        if (profile != 0 || !"connected".equals(state)) return;
        ensurePump();
        synchronized (mv) {
            pendX = Math.max(-1500, Math.min(1500, pendX + dx));
            pendY = Math.max(-1500, Math.min(1500, pendY + dy));
            mv.notifyAll();
        }
    }

    /** Sets which buttons are held (bit0 left, bit1 right, bit2 middle). Used for press / drag / release. */
    @JavascriptInterface
    public void buttons(int mask) {
        flushPending();
        buttons = mask & 7;
        report(buttons, 0, 0, 0, 0);
    }

    /** Quick press + release of one button mask (1 left, 2 right, 4 middle). */
    @JavascriptInterface
    public void click(int mask) {
        flushPending();
        int keep = buttons;
        report(keep | (mask & 7), 0, 0, 0, 0);
        report(keep, 0, 0, 0, 0);
    }

    /** v: wheel notches (positive = scroll up), h: horizontal notches (positive = right). */
    @JavascriptInterface
    public void scroll(int v, int h) {
        flushPending();
        int guard = 40;
        while ((v != 0 || h != 0) && guard-- > 0) {
            int sv = clamp(v), sh = clamp(h);
            if (!report(buttons, 0, 0, sv, sh)) return;
            v -= sv; h -= sh;
        }
    }

    // ---------------------------------------------------------------------------------- keyboard
    /** Keyboard report (Report ID 2): [modifiers][0][key1..key6]. key = HID usage (0 = none, modifiers only). */
    private synchronized boolean keyReport(int mods, int usage) {
        BluetoothDevice h = host;
        BluetoothHidDevice p = hid;
        if (profile != 0 || h == null || p == null || !"connected".equals(state)) return false;
        try {
            return p.sendReport(h, 2, new byte[] { (byte) mods, 0, (byte) usage, 0, 0, 0, 0, 0 });
        } catch (Throwable t) { return false; }
    }

    /**
     * Press + release one key on the PC. usage = USB HID key code (4 = A ... 40 = Enter ...),
     * mods bit mask: 1 Ctrl, 2 Shift, 4 Alt, 8 Win. usage 0 with mods = tap of the modifier alone (e.g. Win -> Start).
     */
    @JavascriptInterface
    public void key(int usage, int mods) {
        flushPending();
        synchronized (this) {
            if (!"connected".equals(state)) return;
            keyReport(mods & 15, usage & 0xFF);       // press
            try { Thread.sleep(6); } catch (InterruptedException ignored) {}
            keyReport(0, 0);                           // release
        }
    }

    /** Pinch zoom on the PC: Ctrl + mouse wheel. n > 0 = zoom in (wheel up), n < 0 = zoom out. */
    @JavascriptInterface
    public void zoom(int n) {
        flushPending();
        synchronized (this) {
            if (n == 0 || !"connected".equals(state)) return;
            keyReport(1, 0);                           // hold Ctrl
            int guard = 20, v = n;
            while (v != 0 && guard-- > 0) {
                int sv = clamp(v);
                if (!report(buttons, 0, 0, sv, 0)) break;
                v -= sv;
            }
            try { Thread.sleep(4); } catch (InterruptedException ignored) {}
            keyReport(0, 0);                           // release Ctrl
        }
    }

    // ---------------------------------------------------------------------------------- game pad
    /**
     * Game pad report (Report ID 3). btn = 16 button bits (bit0 A, bit1 B, bit3 X, bit4 Y, bit6 L1, bit7 R1,
     * bit8 L2, bit9 R2, bit10 Select, bit11 Start, bit12 Mode), hat = 0 none / 1 N .. 8 NW (clockwise),
     * lx, ly, rx, ry = stick axes -127..127.
     */
    @JavascriptInterface
    public synchronized void pad(int btn, int hat, int lx, int ly, int rx, int ry) {
        lastPad = new int[] { btn, hat, lx, ly, rx, ry };
        sendPad(btn, hat, lx, ly, rx, ry);
    }

    private synchronized boolean sendPad(int btn, int hat, int lx, int ly, int rx, int ry) {
        BluetoothDevice h = host;
        BluetoothHidDevice p = hid;
        if (h == null || p == null || !"connected".equals(state)) return false;
        try {
            return p.sendReport(h, profile == 1 ? 1 : 3, new byte[] { (byte) btn, (byte) (btn >> 8), (byte) (hat & 15),
                    (byte) clamp(lx), (byte) clamp(ly), (byte) clamp(rx), (byte) clamp(ry) });
        } catch (Throwable t) { return false; }
    }

    // ---------------------------------------------------------------------------------- profile / pairing helpers
    /** 0 = mouse + keyboard + pad, 1 = pad only (best for games). Switching re-registers with a new SDP record. */
    @JavascriptInterface
    public int getProfile() { return profile; }

    @JavascriptInterface
    public void setProfile(final int p) {
        final int np = p == 1 ? 1 : 0;
        ui.post(new Runnable() {
            public void run() {
                if (np == profile) return;
                profile = np;
                prefs.edit().putInt(PREF_PROFILE, np).apply();
                synchronized (mv) { pendX = 0; pendY = 0; }
                buttons = 0;
                lastPad = new int[6];
                try {
                    BluetoothDevice h = host;
                    if (hid != null && h != null) hid.disconnect(h);
                } catch (Throwable ignored) {}
                host = null;
                ui.removeCallbacks(connectTimeout); ui.removeCallbacks(retryRun);
                if (hid != null) {
                    registered = false;
                    push("starting", "");
                    try { hid.unregisterApp(); } catch (Throwable ignored) {}
                    // normally onAppStatusChanged(false) re-registers; this is the safety net
                    ui.postDelayed(new Runnable() { public void run() { if (!disposed && hid != null && !registered) registerApp(); } }, 2500);
                } else start();
            }
        });
    }

    /** Removes the Bluetooth pairing with that device from the phone (best effort; hidden API). Returns false if Android refused. */
    @JavascriptInterface
    public boolean forget(String addr) {
        try {
            if (adapter == null) adapter = BluetoothAdapter.getDefaultAdapter();
            BluetoothDevice d = adapter.getRemoteDevice(addr);
            try { if (hid != null && host != null && host.equals(d)) hid.disconnect(d); } catch (Throwable ignored) {}
            boolean ok = (Boolean) d.getClass().getMethod("removeBond").invoke(d);
            if (ok && addr.equals(lastAddr())) prefs.edit().remove(PREF_LAST).apply();
            return ok;
        } catch (Throwable t) { return false; }
    }

    // ---------------------------------------------------------------------------------- shutdown
    void dispose() {
        disposed = true;
        ui.removeCallbacks(connectTimeout); ui.removeCallbacks(retryRun); ui.removeCallbacks(keepAlive);
        try { if (btReceiver != null) act.unregisterReceiver(btReceiver); } catch (Throwable ignored) {}
        synchronized (mv) { pumpRun = false; mv.notifyAll(); }
        try { act.getApplication().unregisterActivityLifecycleCallbacks(lifecycle); } catch (Throwable ignored) {}
        try {
            BluetoothDevice h = host;
            if (hid != null) {
                if (h != null) hid.disconnect(h);
                hid.unregisterApp();
                if (adapter != null) adapter.closeProfileProxy(BluetoothProfile.HID_DEVICE, hid);
            }
        } catch (Throwable ignored) {}
        hid = null; registered = false; host = null;
    }
}
