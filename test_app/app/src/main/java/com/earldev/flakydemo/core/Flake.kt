package com.earldev.flakydemo.core

import android.util.Log
import kotlin.random.Random

/** Every log line the app emits carries this tag, so `expect_log` has something stable to match. */
const val TAG = "FlakyDemo"

/**
 * The single source of non-determinism in the app.
 *
 * Every intermittent bug routes its coin flip through [hit] and every artificial latency through
 * [jitter], drawn from one seeded generator. Launching with `--el flake_seed <n>` makes a session
 * replayable; `--ez flake_enabled false` turns the whole family of flaky bugs off, which is the
 * fastest way to tell a flaky failure from a deterministic one.
 */
object Flake {

    @Volatile
    var enabled: Boolean = true
        private set

    @Volatile
    var seed: Long = 0L
        private set

    private var rng: Random = Random(0)
    private var rolls: Int = 0

    @Synchronized
    fun init(seed: Long, enabled: Boolean) {
        this.seed = seed
        this.enabled = enabled
        this.rng = Random(seed)
        this.rolls = 0
        Log.i(TAG, "flake init seed=$seed enabled=$enabled")
    }

    /** True when the bug named [name] should fire on this attempt. */
    @Synchronized
    fun hit(rate: Double, name: String): Boolean {
        if (!enabled) {
            Log.d(TAG, "flake name=$name suppressed")
            return false
        }
        val roll = rng.nextDouble()
        rolls++
        val hit = roll < rate
        Log.d(TAG, "flake name=$name n=$rolls rate=$rate roll=$roll hit=$hit")
        if (hit) Log.w(TAG, "flake FIRED name=$name")
        return hit
    }

    /** A latency between [baseMs] and [baseMs] + [spreadMs]; collapses to [baseMs] when disabled. */
    @Synchronized
    fun jitter(baseMs: Long, spreadMs: Long): Long =
        if (!enabled) baseMs else baseMs + rng.nextLong(0, spreadMs + 1)

    @Synchronized
    fun pick(bound: Int): Int = if (!enabled) 0 else rng.nextInt(bound)
}

fun logScreen(screen: String, detail: String = "") {
    Log.i(TAG, "screen=$screen $detail")
}

fun logAction(action: String, detail: String = "") {
    Log.i(TAG, "action=$action $detail")
}
