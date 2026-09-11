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
        @Query("page_size") pageSize: Int = 100,
        @Query("query") query: String? = null
    ): RecipePage

    @GET("api/recipe/{id}/")
    suspend fun recipe(@Path("id") id: Int): RecipeDetail
}

class AppSettings(context: Context) {
    private val prefs: SharedPreferences = context.getSharedPreferences("7th_heaven_settings", Context.MODE_PRIVATE)

    var baseUrl: String
        get() = prefs.getString(KEY_BASE_URL, DEFAULT_BASE_URL) ?: DEFAULT_BASE_URL
        set(value) {
            val normalized = value.trim().let { if (it.endsWith('/')) it else "$it/" }
            prefs.edit().putString(KEY_BASE_URL, normalized).apply()
        }

    var authToken: String
        get() = prefs.getString(KEY_TOKEN, "") ?: ""
        set(value) = prefs.edit().putString(KEY_TOKEN, value.trim()).apply()

    companion object {
        const val DEFAULT_BASE_URL = "http://100.115.160.72:8321/"
        private const val KEY_BASE_URL = "base_url"
        private const val KEY_TOKEN = "auth_token"
    }
}

class ApiFactory(private val settings: AppSettings) {
    fun create(): TandoorApi {
        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        }

        val auth = Interceptor { chain ->
            val token = settings.authToken
            val original = chain.request()
            val request: Request = if (token.isBlank()) {
                original
            } else {
                original.newBuilder()
                    .header("Authorization", "Token $token")
                    .build()
            }
            chain.proceed(request)
        }

        val client = OkHttpClient.Builder()
            .addInterceptor(auth)
            .addInterceptor(logging)
            .build()

        val moshi = Moshi.Builder()
            .add(RecipeListAdapter())
            .add(KotlinJsonAdapterFactory())
            .build()

        return Retrofit.Builder()
            .baseUrl(settings.baseUrl)
            .client(client)
            .addConverterFactory(MoshiConverterFactory.create(moshi))
            .build()
            .create(TandoorApi::class.java)
    }

    fun absoluteMediaUrl(path: String?): String? {
        if (path.isNullOrBlank()) return null
        if (path.startsWith("http://") || path.startsWith("https://")) return path
        val base = settings.baseUrl.trimEnd('/')
        val normalized = if (path.startsWith('/')) path else "/$path"
        return "$base$normalized"
    }
}
