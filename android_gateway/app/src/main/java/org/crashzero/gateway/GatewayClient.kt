package org.crashzero.gateway

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.concurrent.TimeUnit

data class CallRequest(val id:String,val incidentId:String?,val kind:String,val destination:String,val message:String,
    val cameraName:String?,val location:String?,val eventType:String?)

class GatewayClient(private val config: GatewayConfig) {
    private val client=OkHttpClient.Builder().connectTimeout(5,TimeUnit.SECONDS).readTimeout(8,TimeUnit.SECONDS).build()
    private fun builder(path:String)=Request.Builder().url(config.server+path).header("Authorization","Bearer ${config.token}")
    suspend fun health():Boolean=withContext(Dispatchers.IO) {
        client.newCall(builder("/api/v1/health").get().build()).execute().use { it.isSuccessful }
    }
    suspend fun next():CallRequest?=withContext(Dispatchers.IO) {
        client.newCall(builder("/api/v1/calls/next").get().build()).execute().use { response ->
            if(!response.isSuccessful) throw IllegalStateException("Gateway HTTP ${response.code}")
            val item=JSONObject(response.body!!.string()).optJSONObject("call") ?: return@withContext null
            CallRequest(item.getString("id"),item.optString("incident_id").ifBlank { null },item.optString("kind"),
                item.getString("destination"),item.optString("message"),item.optString("camera_name").ifBlank { null },item.optString("location").ifBlank { null },
                item.optString("event_type").ifBlank { null })
        }
    }
    suspend fun status(id:String,status:String,detail:String?=null)=withContext(Dispatchers.IO) {
        val json=JSONObject().put("status",status).put("detail",detail).toString()
        client.newCall(builder("/api/v1/calls/$id/status").post(json.toRequestBody("application/json".toMediaType())).build()).execute().use {
            if(!it.isSuccessful) throw IllegalStateException("Status HTTP ${it.code}")
        }
    }
}
