package com.sloscout.config;

import org.apache.flink.streaming.api.windowing.assigners.TumblingEventTimeWindows;
import org.apache.flink.streaming.api.windowing.time.Time;

/**
 * Windowing configuration per T058
 * Tumbling window 1h, allowed lateness 10m per streaming-capsule.yaml
 */
public class WindowConfig {

    // Window duration: 1 hour tumbling windows
    public static final Time WINDOW_SIZE = Time.hours(1);

    // Allowed lateness: 10 minutes
    public static final Time ALLOWED_LATENESS = Time.minutes(10);

    /**
     * Get tumbling event time window assigner
     */
    public static TumblingEventTimeWindows getTumblingWindows() {
        return TumblingEventTimeWindows.of(WINDOW_SIZE);
    }

    /**
     * Get allowed lateness duration
     */
    public static Time getAllowedLateness() {
        return ALLOWED_LATENESS;
    }
}
