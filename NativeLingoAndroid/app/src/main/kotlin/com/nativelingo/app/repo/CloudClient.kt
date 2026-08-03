package com.nativelingo.app.repo

import com.nativelingo.app.BuildConfig
import com.nativelingo.app.R
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.util.concurrent.TimeUnit

/** Raised for every cloud-call failure the UI should surface (network down,
 * wrong token, server-side 4xx/5xx). The server's `detail` message is kept
 * verbatim so its diagnostics ("audio contained no speech", …) reach the user.
 *
 * [authError] is true for 401s — the UI turns that into the activation card
 * instead of an error toast (the device token was revoked or the server was
 * reset). */
class CloudApiException(
    message: String,
    cause: Throwable? = null,
    val authError: Boolean = false,
) : Exception(message, cause)

/**
 * Thin OkHttp wrapper for the NativeLingo cloud Speaking backend — the
 * Duolingo-style architecture where transcription, forced alignment, SSL
 * scoring and FR-11 phoneme diagnosis run server-side.
 *
 * One client for the whole app: the per-device token (v0.7.1 — never baked
 * into the APK, issued by POST /register) rides every request via
 * [tokenProvider], which is consulted per call so an activation mid-session
 * takes effect without recreating the client. The timeouts are sized for a
 * cold server — the first /analyze_video after deploy can pull multi-GB
 * models (MMS + phoneme) before the warmup has finished, so reads are allowed
 * minutes, not the usual 30 s. (Warmup prefetches these at startup;
 * steady-state analysis is well under a minute.)
 *
 * [baseUrl] defaults to BuildConfig (gradle property); tests and local dev
 * override both.
 *
 * **TLS pinning (v0.7.3):** the self-hosted server has no domain, so its
 * certificate is signed by a private CA (`server/` deploy docs) and the CA is
 * baked into the APK (`res/raw/nl_ca.pem`). [CloudClient] trusts ONLY that CA
 * — a system-trusted or forged certificate chain is rejected, so no MITM can
 * impersonate the server. HTTP URLs (local dev) are untouched.
 */
class CloudClient(
    private val appContext: android.content.Context,
    private val baseUrl: String = BuildConfig.SERVER_URL,
    private val tokenProvider: () -> String? = { null },
) {

    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .writeTimeout(120, TimeUnit.SECONDS)   // video upload (import path)
        .readTimeout(300, TimeUnit.SECONDS)    // cold-server first analysis
        .apply { pinnedTls(this) }
        .build()

    /** GET and parse a JSON body. Throws [CloudApiException] on transport or
     * non-2xx responses. */
    fun getJson(path: String): JSONObject =
        call(request(path).get().build())

    /** POST multipart fields + files and parse the JSON body. */
    fun postMultipart(
        path: String,
        fields: Map<String, String> = emptyMap(),
        files: List<Pair<String, File>> = emptyList(),
        byteFiles: List<Pair<String, ByteArray>> = emptyList(),
    ): JSONObject {
        require(fields.isNotEmpty() || files.isNotEmpty() || byteFiles.isNotEmpty()) {
            "multipart body must have at least one part — use postEmpty() for bare POSTs"
        }
        val body = MultipartBody.Builder().setType(MultipartBody.FORM).apply {
            for ((k, v) in fields) addFormDataPart(k, v)
            for ((k, f) in files) {
                addFormDataPart(k, f.name, f.asRequestBody("application/octet-stream".toMediaType()))
            }
            for ((k, bytes) in byteFiles) {
                addFormDataPart(k, "upload.wav", bytes.toRequestBody("audio/wav".toMediaType()))
            }
        }.build()
        return call(request(path).post(body).build())
    }

    /** POST with an empty body (endpoints that take no payload) and parse JSON. */
    fun postEmpty(path: String): JSONObject =
        call(request(path).post("".toRequestBody()).build())

    // ── internals ──────────────────────────────────────────────────────────

    /** Trust only the private CA baked into the APK (no domain → self-signed
     * chain; pinning is the only way to prevent MITM on a bare IP). */
    private fun pinnedTls(builder: OkHttpClient.Builder) {
        val caPem = appContext.resources.openRawResource(R.raw.nl_ca).use { it.readBytes() }
        val ca = java.security.cert.CertificateFactory.getInstance("X.509")
            .generateCertificate(java.io.ByteArrayInputStream(caPem))
        val ks = java.security.KeyStore.getInstance(java.security.KeyStore.getDefaultType()).apply {
            load(null)
            setCertificateEntry("nl_ca", ca)
        }
        val tmf = javax.net.ssl.TrustManagerFactory.getInstance(
            javax.net.ssl.TrustManagerFactory.getDefaultAlgorithm(),
        ).apply { init(ks) }
        val sslContext = javax.net.ssl.SSLContext.getInstance("TLS")
        sslContext.init(null, tmf.trustManagers, null)
        builder.sslSocketFactory(
            sslContext.socketFactory,
            tmf.trustManagers!!.first { it is javax.net.ssl.X509TrustManager } as javax.net.ssl.X509TrustManager,
        )
    }

    private fun request(path: String): Request.Builder =
        Request.Builder()
            .url(baseUrl.trimEnd('/') + path)
            .apply {
                tokenProvider()?.let { header("Authorization", "Bearer $it") }
            }

    private fun call(request: Request): JSONObject {
        val resp = try {
            http.newCall(request).execute()
        } catch (e: IOException) {
            // 不把 baseUrl / e.message 拼进用户可见提示（避免暴露服务器公网 IP；
            // e.message 常含 "Failed to connect to /124.220.234.178:8756" 等）。
            // 完整堆栈仍进 logcat 便于排查。
            throw CloudApiException(
                "无法连接云端服务器，请检查网络连接后重试", e,
            )
        }
        resp.use {
            val bodyText = it.body?.string().orEmpty()
            if (!it.isSuccessful) {
                val detail = runCatching { JSONObject(bodyText).optString("detail") }
                    .getOrDefault("")
                val msg = detail.ifBlank { "HTTP ${it.code}" }
                throw CloudApiException(msg, authError = it.code == 401)
            }
            return try {
                JSONObject(bodyText)
            } catch (e: Exception) {
                throw CloudApiException("服务器返回了无法解析的响应：${e.message}", e)
            }
        }
    }
}
