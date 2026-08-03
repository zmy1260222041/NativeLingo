package com.nativelingo.app.repo

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Encrypted storage for the cloud device token.
 *
 * The token is a per-device credential issued by POST /register (server-side
 * device registration, v0.7.1) — it replaces the shared token that used to be
 * baked into the APK via BuildConfig (OWASP Mobile Top 10 M1: anything inside
 * the APK is extractable, so the APK ships with NO key at all now).
 *
 * The token itself is encrypted with an AES-256-GCM key held in the Android
 * Keystore (hardware-backed where the device provides it), so it survives
 * neither APK extraction nor root filesystem reads.
 *
 * The device id (an identifier, not a credential) is plain — it is what the
 * operator sees in `GET /devices`.
 */
class TokenStore(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences("nl_cloud", Context.MODE_PRIVATE)

    private val keyStore: KeyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }

    private fun getOrCreateKey(): SecretKey {
        (keyStore.getEntry(KEY_ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build(),
        )
        return gen.generateKey()
    }

    /** The client-generated device id (UUID), created once and stable. */
    fun deviceId(): String {
        prefs.getString(KEY_DEVICE_ID, null)?.let { return it }
        val id = java.util.UUID.randomUUID().toString()
        prefs.edit().putString(KEY_DEVICE_ID, id).apply()
        return id
    }

    fun saveToken(token: String) {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        val iv = cipher.iv
        val ct = cipher.doFinal(token.toByteArray(Charsets.UTF_8))
        prefs.edit()
            .putString(KEY_TOKEN_IV, Base64.encodeToString(iv, Base64.NO_WRAP))
            .putString(KEY_TOKEN, Base64.encodeToString(ct, Base64.NO_WRAP))
            .apply()
    }

    fun loadToken(): String? {
        val ivB64 = prefs.getString(KEY_TOKEN_IV, null) ?: return null
        val ctB64 = prefs.getString(KEY_TOKEN, null) ?: return null
        return try {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(
                Cipher.DECRYPT_MODE,
                getOrCreateKey(),
                GCMParameterSpec(128, Base64.decode(ivB64, Base64.NO_WRAP)),
            )
            String(cipher.doFinal(Base64.decode(ctB64, Base64.NO_WRAP)), Charsets.UTF_8)
        } catch (e: Exception) {
            // Key rotation / keystore reset — the token is unrecoverable, which
            // is fine: the user just activates the device again.
            prefs.edit().remove(KEY_TOKEN).remove(KEY_TOKEN_IV).apply()
            null
        }
    }

    fun clear() {
        prefs.edit().remove(KEY_TOKEN).remove(KEY_TOKEN_IV).apply()
    }

    companion object {
        private const val KEY_ALIAS = "nl_cloud_device_token"
        private const val KEY_TOKEN = "token_ct"
        private const val KEY_TOKEN_IV = "token_iv"
        private const val KEY_DEVICE_ID = "device_id"
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
    }
}
