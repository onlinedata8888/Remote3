package com.example.tvremote;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.Socket;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;

/** A live remote-control connection (port 6466). Sends are queued on one thread so key order is preserved. */
final class RemoteSession {
    interface Listener {
        void onVolume(int level, int max, boolean muted);

        void onPower(boolean on);

        /** v40: the TV's text field changed / opened. value = the text currently inside the TV's field. */
        void onIme(String value, boolean active);

        void onClosed(RemoteSession s, String reason);
    }

    private final Socket socket;
    private final InputStream in;
    private final OutputStream out;
    private final Listener listener;
    private final ExecutorService writer = Executors.newSingleThreadExecutor(new ThreadFactory() {
        public Thread newThread(Runnable r) {
            Thread t = new Thread(r, "tv-writer");
            t.setDaemon(true);
            return t;
        }
    });
    private final CountDownLatch ready = new CountDownLatch(1);
    private volatile boolean closed;
    private volatile int active = Msgs.F_PING | Msgs.F_KEY | Msgs.F_IME | Msgs.F_VOICE | Msgs.F_POWER | Msgs.F_VOLUME | Msgs.F_APP_LINK;
    private volatile int imeCounter;
    private volatile int fieldCounter;
    private volatile boolean imeSeen;
    private volatile String tvText = "";   // v40: what the TV's text field currently contains
    private final AtomicInteger voiceSessionCounter = new AtomicInteger(0);
    private final AtomicInteger voiceSessionActive = new AtomicInteger(0);
    private volatile long voiceId;
    private volatile boolean voiceEnded;
    private final java.util.Set<Integer> held = java.util.Collections.synchronizedSet(new java.util.HashSet<Integer>());

    private final String deviceId;

    private RemoteSession(Socket s, Listener l, String deviceId) throws IOException {
        this.deviceId = deviceId;
        this.socket = s;
        this.in = s.getInputStream();
        this.out = s.getOutputStream();
        this.listener = l;
    }

    static RemoteSession open(CertStore cs, String host, int port, Listener l) throws Exception {
        Socket s = Tls.connect(cs, host, port, 3000);
        s.setSoTimeout(25000); // TV pings every ~5 s; silence for 25 s means the link is dead
        final RemoteSession r = new RemoteSession(s, l, cs.id);
        Thread t = new Thread(new Runnable() {
            public void run() {
                r.readLoop();
            }
        }, "tv-reader");
        t.setDaemon(true);
        t.start();
        return r;
    }

    boolean isClosed() {
        return closed;
    }

    boolean awaitReady(long ms) {
        try {
            return ready.await(ms, TimeUnit.MILLISECONDS) && !closed;
        } catch (InterruptedException e) {
            return false;
        }
    }

    // ------------------------------------------------------------------ reading
    private void readLoop() {
        String why = "closed";
        try {
            while (!closed) {
                byte[] f = Msgs.readFrame(in);
                handle(f);
            }
        } catch (Exception e) {
            why = String.valueOf(e);
        }
        close(why);
    }

    private void handle(byte[] raw) {
        Pb.Reader r = new Pb.Reader(raw);
        while (r.next()) {
            if (r.wire != 2) continue;
            switch (r.field) {
                case 1: { // remote_configure: TV tells which features it supports
                    int code1 = 0;
                    Pb.Reader s = new Pb.Reader(r.data);
                    while (s.next()) if (s.field == 1) code1 = (int) s.num;
                    active &= code1;
                    send(Msgs.remoteConfigure(active, deviceId));
                    break;
                }
                case 2: // remote_set_active
                    send(Msgs.remoteSetActive(active));
                    break;
                case 3:
                    TvLog.d("remote_error from TV");
                    break;
                case 8: { // ping request -> ping response
                    int v = 0;
                    Pb.Reader s = new Pb.Reader(r.data);
                    while (s.next()) if (s.field == 1) v = (int) s.num;
                    send(Msgs.pingResponse(v));
                    break;
                }
                case 20: { // ime_key_inject { app_info = 1; text_field_status = 2 }
                    imeSeen = true;
                    readFieldStatus(r.data, 2);
                    break;
                }
                case 22: { // ime_show_request { text_field_status = 2 }
                    imeSeen = true;
                    readFieldStatus(r.data, 2);
                    break;
                }
                case 21: { // ime_batch_edit from the TV
                    imeSeen = true;
                    Pb.Reader s = new Pb.Reader(r.data);
                    String val = null;
                    while (s.next()) {
                        if (s.field == 1) imeCounter = (int) s.num;
                        else if (s.field == 2) fieldCounter = (int) s.num;
                        else if (s.field == 3 && s.wire == 2) { // edit_info { insert = 1; object = 2 { start, end, value = 3 } }
                            Pb.Reader e = new Pb.Reader(s.data);
                            while (e.next()) {
                                if (e.field == 2 && e.wire == 2) {
                                    Pb.Reader o = new Pb.Reader(e.data);
                                    while (o.next()) if (o.field == 3 && o.wire == 2) val = utf8(o.data);
                                }
                            }
                        }
                    }
                    if (val != null) {
                        tvText = val;
                        listener.onIme(val, true);
                    }
                    break;
                }
                case 30: { // remote_voice_begin: TV acknowledged the voice UI.
                    long id = 0;
                    Pb.Reader s = new Pb.Reader(r.data);
                    while (s.next()) if (s.field == 1) id = s.num;
                    voiceId = id;
                    break;
                }
                case 32: // TV finished listening (it understood the command or gave up)
                    voiceEnded = true;
                    break;
                case 40: { // remote_start: ready for commands
                    boolean on = false;
                    Pb.Reader s = new Pb.Reader(r.data);
                    while (s.next()) if (s.field == 1) on = s.num != 0;
                    ready.countDown();
                    listener.onPower(on);
                    break;
                }
                case 50: { // volume info
                    int max = 0, level = 0;
                    boolean muted = false;
                    Pb.Reader s = new Pb.Reader(r.data);
                    while (s.next()) {
                        if (s.field == 6) max = (int) s.num;
                        else if (s.field == 7) level = (int) s.num;
                        else if (s.field == 8) muted = s.num != 0;
                    }
                    listener.onVolume(level, max, muted);
                    break;
                }
                default:
                    break;
            }
        }
    }

    // ------------------------------------------------------------------ writing
    private void writeNow(byte[] bytes) {
        try {
            out.write(bytes);
            out.flush();
        } catch (IOException e) {
            close("write failed: " + e);
        }
    }

    private void write(final byte[] bytes) {
        if (closed) return;
        try {
            writer.execute(new Runnable() {
                public void run() {
                    if (!closed) writeNow(bytes);
                }
            });
        } catch (Exception ignored) {
        }
    }

    private void send(byte[] payload) {
        write(Msgs.frame(payload));
    }

    /** dir: 1 = key down (START_LONG), 2 = key up (END_LONG), 3 = full press (SHORT). */
    void key(int code, int dir) {
        if (dir == Msgs.DIR_START_LONG) held.add(code);
        else if (dir == Msgs.DIR_END_LONG) held.remove(code);
        send(Msgs.keyInject(code, dir));
    }

    /** n quick presses in a single network write. */
    void keys(int code, int n) {
        if (n <= 0) return;
        if (n > 60) n = 60;
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        byte[] one = Msgs.frame(Msgs.keyInject(code, Msgs.DIR_SHORT));
        for (int i = 0; i < n; i++) b.write(one, 0, one.length);
        write(b.toByteArray());
    }

    void releaseHeld() {
        Object[] codes = held.toArray();
        held.clear();
        for (int i = 0; i < codes.length; i++) send(Msgs.keyInject((Integer) codes[i], Msgs.DIR_END_LONG));
    }


    private static String utf8(byte[] b) {
        try {
            return new String(b, "UTF-8");
        } catch (Exception e) {
            return "";
        }
    }

    /** text_field_status { counter_field = 1; value = 2; start = 3; end = 4 } is nested at `field` of msg. */
    private void readFieldStatus(byte[] msg, int field) {
        try {
            Pb.Reader m = new Pb.Reader(msg);
            while (m.next()) {
                if (m.field == field && m.wire == 2) {
                    Pb.Reader f = new Pb.Reader(m.data);
                    String val = "";
                    while (f.next()) {
                        if (f.field == 1 && f.wire == 0) fieldCounter = (int) f.num;
                        else if (f.field == 2 && f.wire == 2) val = utf8(f.data);
                    }
                    tvText = val;
                    listener.onIme(val, true);
                    return;
                }
            }
        } catch (Exception ignored) {
        }
        listener.onIme(tvText, true);
    }

    /**
     * v40: put `full` into the TV's text field, like the Google TV remote does. When the TV has an active text
     * field the WHOLE value is replaced (so deleting / clearing / pre-filled text all work). Without an IME session
     * it falls back to key events (DEL for removed characters, then the new ones).
     */
    void setText(String full, String prev) {
        if (full == null) full = "";
        if (prev == null) prev = "";
        if (imeSeen && (active & Msgs.F_IME) != 0) {
            tvText = full;
            send(Msgs.imeText(imeCounter, fieldCounter, full));
            return;
        }
        int c = 0;
        int n = Math.min(prev.length(), full.length());
        while (c < n && prev.charAt(c) == full.charAt(c)) c++;
        int dels = prev.length() - c;
        if (dels > 0) keys(67, dels);   // KEYCODE_DEL
        for (int i = c; i < full.length(); i++) {
            int kc = keyCodeForChar(full.charAt(i));
            if (kc > 0) send(Msgs.keyInject(kc, Msgs.DIR_SHORT));
        }
    }

    String tvText() {
        return tvText;
    }

    boolean imeActive() {
        return imeSeen && (active & Msgs.F_IME) != 0;
    }

    void text(String s) {
        if (s == null || s.length() == 0) return;
        if (imeSeen && (active & Msgs.F_IME) != 0) {
            send(Msgs.imeText(imeCounter, fieldCounter, s));
            return;
        }
        for (int i = 0; i < s.length(); i++) {
            int kc = keyCodeForChar(s.charAt(i));
            if (kc > 0) send(Msgs.keyInject(kc, Msgs.DIR_SHORT));
        }
    }

    static int keyCodeForChar(char c) {
        if (c >= 'a' && c <= 'z') return 29 + (c - 'a');
        if (c >= 'A' && c <= 'Z') return 29 + (c - 'A');
        if (c >= '0' && c <= '9') return 7 + (c - '0');
        switch (c) {
            case ' ':
                return 62;
            case '.':
                return 56;
            case ',':
                return 55;
            case '-':
                return 69;
            case '@':
                return 77;
            case '/':
                return 76;
            default:
                return -1;
        }
    }

    // ---------------------------------------------------------------- voice (tested Cast_Remote flow)

    static final long VOICE_FAILED = Long.MIN_VALUE;
    private static final int VOICE_CHUNK_MAX = 20 * 1024;

    boolean voiceSupported() {
        return (active & Msgs.F_VOICE) != 0;
    }

    /**
     * Starts RemoteVoiceBegin using a locally generated session id.
     * The caller sends KEYCODE_SEARCH before calling this method, matching
     * the tested Cast_Remote implementation.
     */
    long startVoice() {
        if (closed) return VOICE_FAILED;

        if (voiceSessionActive.get() != 0) {
            return voiceId;
        }

        int id = voiceSessionCounter.incrementAndGet();
        if (id <= 0) {
            voiceSessionCounter.set(1);
            id = 1;
        }

        voiceId = id;
        voiceEnded = false;

        write(Msgs.frame(Msgs.voiceBegin(id)));
        voiceSessionActive.set(1);
        return id;
    }

    /** Streams raw 16-bit PCM mono 8 kHz audio, split at 20 KB. */
    void sendVoiceChunk(byte[] pcmChunk, int len) {
        if (voiceSessionActive.get() == 0 || pcmChunk == null || len <= 0) return;

        int offset = 0;
        while (offset < len && !closed) {
            int n = Math.min(VOICE_CHUNK_MAX, len - offset);
            byte[] samples = new byte[n];
            System.arraycopy(pcmChunk, offset, samples, 0, n);

            write(Msgs.frame(Msgs.voicePayload(voiceId, samples)));
            offset += n;
        }
    }

    /** Ends the current voice session. */
    void stopVoice() {
        if (voiceSessionActive.getAndSet(0) == 0) return;

        long id = voiceId;
        voiceId = VOICE_FAILED;
        write(Msgs.frame(Msgs.voiceEnd(id)));
    }

    // Compatibility helpers retained for the existing voice code/tests.
    long voiceBegin(long timeoutMs) {
        key(84, Msgs.DIR_SHORT);
        try {
            Thread.sleep(200);
        } catch (InterruptedException ignored) {
            Thread.currentThread().interrupt();
            return VOICE_FAILED;
        }
        return startVoice();
    }

    void voiceChunk(long id, byte[] pcm, int len) {
        if (voiceSessionActive.get() == 0) {
            voiceId = id;
            voiceSessionActive.set(1);
        }
        sendVoiceChunk(pcm, len);
    }

    boolean voiceEndedByTv() {
        return voiceEnded;
    }

    void voiceEnd(long id) {
        stopVoice();
    }

    void launch(String link) {
        send(Msgs.appLink(link));
    }

    void close(String reason) {
        if (closed) return;
        closed = true;
        try {
            socket.close();
        } catch (IOException ignored) {
        }
        writer.shutdownNow();
        ready.countDown();
        try {
            listener.onClosed(this, reason);
        } catch (Exception ignored) {
        }
    }
}
