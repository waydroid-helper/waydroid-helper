package android.app;

// Compile-only subset of the platform class. ART supplies the actual Binder
// implementation, including the version-specific ITaskStackListener methods.
public abstract class TaskStackListener {
    public void onTaskRemoved(int taskId) {}
    public void onTaskStackChanged() {}
    public void onTaskFocusChanged(int taskId, boolean focused) {}
    public void onTaskMovedToFront(ActivityManager.RunningTaskInfo task) {}
    public void onActivityRestartAttempt(ActivityManager.RunningTaskInfo task,
            boolean homeVisible, boolean clearedTask, boolean wasVisible) {}
}
