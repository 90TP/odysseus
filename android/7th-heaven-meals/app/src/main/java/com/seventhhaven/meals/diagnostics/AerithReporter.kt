package com.seventhhaven.meals.diagnostics

import android.content.Context
import android.util.Log
import com.seventhhaven.meals.BuildConfig
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.util.Collections
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicInteger

/**
 * Sends this app's crashes and errors to Aerith on Odysseus, so she can draft
 * fixes (POST /api/companion/aerith/maintenance/logs).
 *
 * Off unless `aerith.url` and `aerith.token` are set in local.properties.
 * Crashes are written to disk first and sent on the next launch, because the
 * process is dying when they happen. Nothing here may itself crash the app.
 */
object AerithReporter {
    private const val TAG = "AerithReporter"
    private const val PENDING_DIR = "aerith-reports"
    private const val MAX_PENDING_FILES = 50
    private const val MAX_REPORTS_PER_LAUNCH = 20
    private const val LOGS_PATH = "api/companion/aerith/maintenance/logs"

    private val executor = Executors.newSingleThreadExecutor()
    private val reportsThisLaunch = AtomicInteger(0)
    private val seenThisLaunch: MutableSet<String> = Collections.synchronizedSet(HashSet())

    @Volatile
    private var appContext: Context? = null

    val enabled: Boolean
        get() = BuildConfig.AERITH_URL.isNotBlank() && BuildConfig.AERITH_TOKEN.isNotBlank()

    /** Call once from Activity/Application onCreate. */
    fun install(context: Context) {
        val ctx = context.applicationContext
        if (appContext != null) return
        appContext = ctx
        if (!enabled) return

        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            try {
                savePending(
                    ctx,
                    event(
                        message = "Crash: ${error.javaClass.name}: ${error.message ?: ""}".trim(),
                        detail = Log.getStackTraceString(error),
                        source = "crash/${thread.name}",
                    ),
                )
            } catch (_: Throwable) {
                // Never get in the way of the real crash handler.
            }
            previous?.uncaughtException(thread, error)
        }
        executor.execute { flushPending(ctx) }
    }

    /** Report a non-fatal error. Deduplicated and rate-limited per launch. */
    fun report(message: String, detail: String = "", source: String = "app") {
        val ctx = appContext ?: return
        if (!enabled || message.isBlank()) return
        if (!seenThisLaunch.add("$source|$message".take(400))) return
        if (reportsThisLaunch.incrementAndGet() > MAX_REPORTS_PER_LAUNCH) return
        val event = event(message, detail, source)
        executor.execute {
            if (!send(listOf(event))) savePending(ctx, event)
        }
    }

    private fun event(message: String, detail: String, source: String): JSONObject =
        JSONObject()
            .put("level", "ERROR")
            .put("message", message.take(4000))
            .put("detail", detail.take(20000))
            .put("source", source.take(200))
            .put("timestamp", Instant.now().toString())

    private fun pendingDir(ctx: Context) = File(ctx.filesDir, PENDING_DIR).apply { mkdirs() }

    private fun savePending(ctx: Context, event: JSONObject) {
        try {
            val dir = pendingDir(ctx)
            val files = dir.listFiles()?.sortedBy { it.name } ?: emptyList()
            // Keep the newest reports if something keeps failing.
            files.dropLast(MAX_PENDING_FILES - 1).forEach { it.delete() }
            File(dir, "${System.currentTimeMillis()}-${event.hashCode()}.json").writeText(event.toString())
        } catch (e: Exception) {
            Log.w(TAG, "Could not save report", e)
        }
    }

    private fun flushPending(ctx: Context) {
        val files = pendingDir(ctx).listFiles()?.sortedBy { it.name } ?: return
        if (files.isEmpty()) return
        val events = files.mapNotNull { f ->
            try {
                JSONObject(f.readText())
            } catch (e: Exception) {
                f.delete() // unreadable, drop it
                null
            }
        }
        if (events.isNotEmpty() && send(events.take(100))) {
            files.forEach { it.delete() }
        }
    }

    private fun send(events: List<JSONObject>): Boolean {
        val body = JSONObject()
            .put("platform", "android")
            .put("app_id", BuildConfig.APPLICATION_ID)
            .put("app_version", BuildConfig.VERSION_NAME)
            .put("events", JSONArray(events))
            .toString()
            .toByteArray(Charsets.UTF_8)
        val base = BuildConfig.AERITH_URL.trim().trimEnd('/')
        var conn: HttpURLConnection? = null
        return try {
            conn = (URL("$base/$LOGS_PATH").openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = 10_000
                readTimeout = 15_000
                doOutput = true
                setRequestProperty("Content-Type", "application/json")
                setRequestProperty("Authorization", "Bearer ${BuildConfig.AERITH_TOKEN.trim()}")
            }
            conn.outputStream.use { it.write(body) }
            val code = conn.responseCode
            if (code !in 200..299) Log.w(TAG, "Odysseus answered HTTP $code")
            // Keep reports for problems that can be fixed (bad token, rate
            // limit); drop ones Odysseus rejected as malformed so they don't
            // pile up forever.
            code in 200..299 || (code in 400..499 && code !in setOf(401, 403, 408, 429))
        } catch (e: IOException) {
            Log.i(TAG, "Odysseus unreachable; will retry next launch")
            false
        } catch (e: Exception) {
            Log.w(TAG, "Report failed", e)
            false
        } finally {
            conn?.disconnect()
        }
    }
}
