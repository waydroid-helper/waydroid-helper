package org.waydroid.helper;

import android.app.ActivityManager.RunningTaskInfo;
import android.graphics.Rect;
import android.os.SystemClock;

import java.lang.reflect.Field;
import java.lang.reflect.Method;

/** Keeps desktop-mode Android tasks inside the emulator's full-UI surface. */
final class EmbeddedDisplay {
    private static final String ACTIVE_APPS = "waydroid.active_apps";
    private static final String FULL_UI = "Waydroid";
    private static final int FULLSCREEN = 1, FREEFORM = 5;
    private String requestedPackage;
    private long launchDeadline;
    private final Method getProperty, setProperty, setMode, setBounds, apply;
    private final Field token = RunningTaskInfo.class.getField("token");
    private final Class<?> transaction = Class.forName("android.window.WindowContainerTransaction");
    private final Object organizer = Class.forName("android.window.WindowOrganizer").getConstructor().newInstance();

    EmbeddedDisplay() throws Exception {
        Class<?> properties = Class.forName("android.os.SystemProperties");
        Class<?> container = Class.forName("android.window.WindowContainerToken");
        getProperty = properties.getMethod("get", String.class);
        setProperty = properties.getMethod("set", String.class, String.class);
        setMode = transaction.getMethod("setWindowingMode", container, int.class);
        setBounds = transaction.getMethod("setBounds", container, Rect.class);
        apply = organizer.getClass().getMethod("applyTransaction", transaction);
    }

    String showFullUi() throws Exception {
        // A desktop .desktop entry can launch an app even when our session
        // owns the display. Restore the same runtime target as show-full-ui.
        // Never change the persistent property used by the next desktop boot.
        String target = (String) getProperty.invoke(null, ACTIVE_APPS);
        if (!FULL_UI.equals(target)) {
            setProperty.invoke(null, ACTIVE_APPS, FULL_UI);
            // Waydroid publishes the package before launchApp creates or
            // resumes its task. Keep that intent across task snapshots. Older
            // Wayland surfaces may briefly focus the previously displayed app.
            requestedPackage = target.equals("none") || target.isEmpty() ? null : target;
            launchDeadline = SystemClock.uptimeMillis() + 3000;
        }
        if (SystemClock.uptimeMillis() >= launchDeadline) requestedPackage = null;
        return requestedPackage;
    }

    void clearLaunch() {
        requestedPackage = null;
    }

    Object fitTask(Object changes, RunningTaskInfo task, int mode) throws Exception {
        // Android's PC feature gives new tasks freeform bounds independently
        // of Waydroid's output surface. Change only those tasks, leaving PiP,
        // system dialogs and other displays to Android's window manager.
        if (mode != FREEFORM) return changes;
        if (changes == null) changes = transaction.getConstructor().newInstance();
        Object container = token.get(task);
        setMode.invoke(changes, container, FULLSCREEN);
        setBounds.invoke(changes, container, null);
        return changes;
    }

    void apply(Object changes) throws Exception {
        if (changes != null) apply.invoke(organizer, changes);
    }
}
