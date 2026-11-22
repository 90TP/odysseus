package com.seventhhaven.meals.data

import android.content.Context
import android.content.SharedPreferences
import com.squareup.moshi.Moshi
import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.moshi.MoshiConverterFactory
import retrofit2.http.GET
import retrofit2.http.Path
import retrofit2.http.Query

interface TandoorApi {
    @GET("api/recipe/")
    suspend fun recipes(
        @Query("page") page: Int = 1,
        @Query("page_size") pageSize: Int = 100,
        @Query("query") query: String? = null
    ): RecipePage

    @GET("api/recipe/{id}/")
    suspend fun recipe(@Path("id") id: Int): RecipeDetail
}

data class ConnectionTestResult(
    val ok: Boolean,
    val statusCode: Int?,
    val message: String
)

class AppSettings(context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("7th_heaven_settings", Context.MODE_PRIVATE)

    var baseUrl: String
        get() {
            val stored = prefs.getString(KEY_BASE_URL, DEFAULT_BASE_URL) ?: DEFAULT_BASE_URL
            val migrated = migrateLegacyBaseUrl(stored)
            if (migrated != stored) {
                prefs.edit().putString(KEY_BASE_URL, migrated).apply()
            }
            return migrated
        }
        set(value) {
            val normalized = normalize(value)
            prefs.edit().putString(KEY_BASE_URL, migrateLegacyBaseUrl(normalized)).apply()
        }

    var authToken: String
        get() = prefs.getString(KEY_TOKEN, "") ?: ""
        set(value) = prefs.edit().putString(KEY_TOKEN, cleanToken(value)).apply()

    private fun normalize(value: String): String {
        val trimmed = value.trim()
        return if (trimmed.endsWith('/')) trimmed else "$trimmed/"
    }

    private fun migrateLegacyBaseUrl(value: String): String {
        val normalized = normalize(value)
        return when (normalized) {
            "http://192.168.0.153:8321/",
            "https://192.168.0.153:8321/",
            "http://100.115.160.72:8321/",
            "https://100.115.160.72:8321/",
            "http://highwind.tailfc86b0.ts.net:8321/" -> DEFAULT_BASE_URL
            else -> normalized
        }
    }

    companion object {
        const val DEFAULT_BASE_URL = "https://highwind.tailfc86b0.ts.net:8321/"
        private const val KEY_BASE_URL = "base_url"
        private const val KEY_TOKEN = "auth_token"

        fun cleanToken(value: String): String {
            var token = value.trim()
            if (token.startsWith("Bearer ", ignoreCase = true)) token = token.substring(7).trim()
            if (token.startsWith("Token ", ignoreCase = true)) token = token.substring(6).trim()
            return token
        }
    }
}

class ApiFactory(private val settings: AppSettings) {
    private fun currentToken(): String = AppSettings.cleanToken(settings.authToken)

    private fun createClient(): OkHttpClient {
        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        }

        val auth = Interceptor { chain ->
            val token = currentToken()
            val builder = chain.request().newBuilder()
                .header("Accept", "application/json")

            if (token.isNotBlank()) {
                builder.header("Authorization", "Bearer $token")
            }

            chain.proceed(builder.build())
        }

        return OkHttpClient.Builder()
            .addInterceptor(auth)
            .addInterceptor(logging)
            .build()
    }

    fun create(): TandoorApi {
        val moshi = Moshi.Builder()
            .add(RecipeListAdapter())
            .add(KotlinJsonAdapterFactory())
            .build()

        return Retrofit.Builder()
            .baseUrl(settings.baseUrl)
            .client(createClient())
            .addConverterFactory(MoshiConverterFactory.create(moshi))
            .build()
            .create(TandoorApi::class.java)
    }

    fun testConnection(): ConnectionTestResult {
        val token = currentToken()
        val url = settings.baseUrl.trimEnd('/') + "/api/recipe/?page=1&page_size=1"
        val requestBuilder = Request.Builder()
            .url(url)
            .header("Accept", "application/json")
            .get()

        // Attach auth explicitly for the diagnostic request so there is no ambiguity
        // about whether an interceptor or preference refresh omitted it.
        if (token.isNotBlank()) {
            requestBuilder.header("Authorization", "Bearer $token")
        }

        val request = requestBuilder.build()
        val authAttached = request.header("Authorization") != null
        val prefix = "URL=$url | tokenChars=${token.length} | authHeader=$authAttached"

        return try {
            OkHttpClient.Builder()
                .addInterceptor(HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BASIC })
                .build()
                .newCall(request)
                .execute()
                .use { response ->
                    val body = response.body?.string().orEmpty()
                    val detail = body.take(500).ifBlank { response.message }
                    if (response.isSuccessful) {
                        ConnectionTestResult(
                            ok = true,
                            statusCode = response.code,
                            message = "$prefix\nHTTP ${response.code} — connection and Bearer authentication succeeded."
                        )
                    } else {
                        ConnectionTestResult(
                            ok = false,
                            statusCode = response.code,
                            message = "$prefix\nHTTP ${response.code}: $detail"
                        )
                    }
                }
        } catch (t: Throwable) {
            ConnectionTestResult(
                ok = false,
                statusCode = null,
                message = "$prefix\n${t::class.java.simpleName}: ${t.message ?: "Unknown connection error"}"
            )
        }
    }

    fun absoluteMediaUrl(path: String?): String? {
        if (path.isNullOrBlank()) return null
        if (path.startsWith("http://") || path.startsWith("https://")) return path
        val base = settings.baseUrl.trimEnd('/')
        val normalized = if (path.startsWith('/')) path else "/$path"
        return "$base$normalized"
    }
}
