package org.crashzero.gateway

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

data class GatewayConfig(val server: String, val token: String, val destination: String, val automatic: Boolean) {
    companion object {
        private const val PREFS = "gateway"
        private fun preferences(context:Context):SharedPreferences {
            val key=MasterKey.Builder(context).setKeyScheme(MasterKey.KeyScheme.AES256_GCM).build()
            return EncryptedSharedPreferences.create(context,PREFS,key,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM)
        }
        fun load(context: Context): GatewayConfig {
            val p = preferences(context)
            return GatewayConfig(p.getString("server", "http://192.168.1.2:8766")!!.trimEnd('/'),
                p.getString("token", "")!!, p.getString("destination", "")!!, p.getBoolean("automatic", false))
        }
        fun save(context: Context, value: GatewayConfig) {
            preferences(context).edit()
                .putString("server", value.server.trimEnd('/')).putString("token", value.token)
                .putString("destination", value.destination).putBoolean("automatic", value.automatic).apply()
        }
        fun appendLog(context: Context, line: String) {
            val prefs=preferences(context)
            val old=prefs.getString("logs","") ?: ""
            prefs.edit().putString("logs",("${System.currentTimeMillis()}: $line\n"+old).take(8000)).apply()
        }
        fun logs(context: Context)=preferences(context).getString("logs","") ?: ""
    }
}
