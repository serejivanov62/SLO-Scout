package com.sloscout.config;

import org.apache.flink.contrib.streaming.state.EmbeddedRocksDBStateBackend;
import org.apache.flink.runtime.state.StateBackend;
import org.apache.flink.streaming.api.CheckpointingMode;
import org.apache.flink.streaming.api.environment.CheckpointConfig;
import org.apache.flink.streaming.api.environment.StreamExecutionEnvironment;

/**
 * Checkpointing configuration per T059
 * RocksDB incremental, 5-minute interval, exactly-once semantics per research.md
 */
public class CheckpointConfig {

    // Checkpoint interval: 5 minutes
    public static final long CHECKPOINT_INTERVAL = 5 * 60 * 1000L;

    // Minimum pause between checkpoints
    public static final long MIN_PAUSE_BETWEEN_CHECKPOINTS = 1000L;

    // Checkpoint timeout: 10 minutes
    public static final long CHECKPOINT_TIMEOUT = 10 * 60 * 1000L;

    // Max concurrent checkpoints
    public static final int MAX_CONCURRENT_CHECKPOINTS = 1;

    /**
     * Configure checkpointing for the environment
     */
    public static void configureCheckpointing(StreamExecutionEnvironment env) throws Exception {
        // Enable checkpointing with 5-minute interval
        env.enableCheckpointing(CHECKPOINT_INTERVAL);

        // Checkpointing configuration
        CheckpointConfig config = env.getCheckpointConfig();

        // Exactly-once semantics per research.md
        config.setCheckpointingMode(CheckpointingMode.EXACTLY_ONCE);

        // Minimum pause between checkpoints
        config.setMinPauseBetweenCheckpoints(MIN_PAUSE_BETWEEN_CHECKPOINTS);

        // Checkpoint timeout
        config.setCheckpointTimeout(CHECKPOINT_TIMEOUT);

        // Max concurrent checkpoints
        config.setMaxConcurrentCheckpoints(MAX_CONCURRENT_CHECKPOINTS);

        // Retain checkpoints on cancellation
        config.setExternalizedCheckpointCleanup(
            CheckpointConfig.ExternalizedCheckpointCleanup.RETAIN_ON_CANCELLATION
        );

        // Fail on checkpoint errors
        config.setFailOnCheckpointingErrors(true);

        // RocksDB state backend with incremental checkpoints
        StateBackend stateBackend = new EmbeddedRocksDBStateBackend(true); // true = incremental
        env.setStateBackend(stateBackend);
    }
}
