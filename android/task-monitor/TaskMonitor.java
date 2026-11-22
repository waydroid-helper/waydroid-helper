package org.waydroid.helper;

import android.app.ActivityManager.RunningTaskInfo;
import android.app.TaskStackListener;
import android.content.Intent;
import android.os.Handler;
import android.os.Looper;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Maps the default Android display's live tasks to tabs over one ADB shell stream. */
public final class TaskMonitor extends TaskStackListener {
    private static final int STANDARD = 1, HOME = 2, RECENTS = 3;
    private final Handler handler = new Handler(Looper.myLooper());
    private final Class<?> api = Class.forName("android.app.IActivityTaskManager");
    private final Object service = Class.forName("android.app.ActivityTaskManager")
            .getMethod("getService").invoke(null);
    private final Class<?> listener = Class.forName("android.app.ITaskStackListener");
    private final Field displayId = RunningTaskInfo.class.getField("displayId");
    private final EmbeddedDisplay display = new EmbeddedDisplay();
    // Android 11 exposes task modes through WindowConfiguration. Newer
    // TaskInfo convenience methods read the same fields.
    private final Field configuration = RunningTaskInfo.class.getField("configuration");
    private final Field windowConfiguration = configuration.getType().getField("windowConfiguration");
    private final Method activityType = windowConfiguration.getType().getMethod("getActivityType");
    private final Method windowingMode = windowConfiguration.getType().getMethod("getWindowingMode");
    private final Method listTasks;
    private final Object[] arguments;
    private final Set<Integer> appTasks = new HashSet<>();
    private final Runnable refresh = this::publish;
    private String previous = "";

    private TaskMonitor() throws Exception {
        // The Android 11 and 13 Waydroid images use different Binder signatures.
        // Resolve the runtime interface by name so the desktop package can ship
        // one DEX without relying on a particular build's transaction numbers.
        Method selected = null;
        Object[] args = null;
        for (Method method : api.getMethods()) {
            if (!method.getName().equals("getTasks")) continue;
            switch (method.getParameterTypes().length) {
                case 4: args = new Object[]{Integer.MAX_VALUE, false, false, 0}; break;
                case 3: args = new Object[]{Integer.MAX_VALUE, false, false}; break;
                case 1: args = new Object[]{Integer.MAX_VALUE}; break;
                default: continue;
            }
            selected = method;
            break;
        }
        if (selected == null) throw new NoSuchMethodException("IActivityTaskManager.getTasks");
        listTasks = selected;
        arguments = args;
    }

    @Override
    public void onTaskStackChanged() {
        // Binder delivers a burst of callbacks during launches and removals.
        // Snapshot on the main looper after the transition, without polling
        // or letting repeated notifications postpone a refresh indefinitely.
        synchronized (refresh) {
            if (!handler.hasCallbacks(refresh)) handler.postDelayed(refresh, 45);
        }
    }

    @Override
    public void onTaskFocusChanged(int taskId, boolean focused) {
        onTaskStackChanged();
    }

    @Override
    public void onTaskMovedToFront(RunningTaskInfo task) {
        onTaskStackChanged();
    }

    @Override
    public void onActivityRestartAttempt(RunningTaskInfo task, boolean homeVisible,
            boolean clearedTask, boolean wasVisible) {
        onTaskStackChanged();
    }

    @Override
    public void onTaskRemoved(int taskId) {
        onTaskStackChanged();
    }

    @SuppressWarnings("unchecked")
    private void publish() {
        try {
            List<RunningTaskInfo> tasks = (List<RunningTaskInfo>) listTasks.invoke(service, arguments);
            Object changes = null;
            String launch = display.showFullUi();
            int launchTask = -1;
            JSONArray apps = new JSONArray();
            int active = -1;
            appTasks.clear();
            // RunningTasks returns the focused task first. Home and Recents
            // belong to the pinned device tab. Ignore empty organizer roots,
            // permission prompts and other transient tasks excluded from Recents.
            for (RunningTaskInfo task : tasks) {
                if (displayId.getInt(task) != 0
                        || task.baseActivity == null || task.numActivities == 0) continue;
                Object config = windowConfiguration.get(configuration.get(task));
                int type = (int) activityType.invoke(config);
                if (type == HOME || type == RECENTS) {
                    if (active == -1) active = 0;
                    continue;
                }
                if (type != STANDARD || (task.baseIntent.getFlags() & Intent.FLAG_ACTIVITY_EXCLUDE_FROM_RECENTS) != 0) continue;
                changes = display.fitTask(changes, task, (int) windowingMode.invoke(config));
                if (launchTask == -1 && task.baseActivity.getPackageName().equals(launch)) {
                    launchTask = task.taskId;
                }
                if (active == -1) active = task.taskId;
                appTasks.add(task.taskId);
                apps.put(new JSONObject().put("id", task.taskId)
                        .put("package", task.baseActivity.getPackageName()));
            }
            display.apply(changes);
            if (launchTask != -1) {
                display.clearLaunch();
                api.getMethod("setFocusedTask", int.class).invoke(service, launchTask);
                if (launchTask != active) {
                    onTaskStackChanged();
                    return;
                }
            }
            String snapshot = new JSONObject().put("apps", apps)
                    .put("active", Math.max(0, active)).toString();
            if (!snapshot.equals(previous)) {
                System.out.println(snapshot);
                previous = snapshot;
            }
        } catch (Exception error) {
            // Fatal protocol/API errors must reach the host, which can restart
            // the observer independently while the embedded display stays live.
            error.printStackTrace(System.err);
            System.exit(1);
        }
    }

    private void command(String line) {
        try {
            String[] parts = line.split(" ");
            int id = Integer.parseInt(parts[1]);
            if (appTasks.contains(id)) {
                display.clearLaunch();
                if (parts[0].equals("focus")) {
                    api.getMethod("setFocusedTask", int.class).invoke(service, id);
                } else if (parts[0].equals("close")) {
                    api.getMethod("removeTask", int.class).invoke(service, id);
                }
            }
        } catch (Exception error) {
            error.printStackTrace(System.err);
            System.out.println("{\"error\":true}");
        }
        // setFocusedTask can return before the new task is actually on top.
        // Publishing an immediate acknowledgement would briefly select the old
        // tab again. Normal callbacks report the transition; send a delayed
        // acknowledgement only if the state stayed the same (e.g. a stale ID).
        String before = previous;
        onTaskStackChanged();
        handler.postDelayed(() -> {
            if (before.equals(previous)) {
                previous = "";
                publish();
            }
        }, 300);
    }

    public static void main(String[] args) throws Exception {
        Looper.prepare();
        TaskMonitor monitor = new TaskMonitor();
        monitor.api.getMethod("registerTaskStackListener", monitor.listener)
                .invoke(monitor.service, monitor);
        monitor.publish();
        Thread input = new Thread(() -> {
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(System.in))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    final String command = line;
                    monitor.handler.post(() -> monitor.command(command));
                }
            } catch (Exception error) {
                error.printStackTrace(System.err);
            } finally {
                monitor.handler.getLooper().quitSafely();
            }
        });
        input.start();
        Looper.loop();
        monitor.api.getMethod("unregisterTaskStackListener", monitor.listener)
                .invoke(monitor.service, monitor);
    }
}
