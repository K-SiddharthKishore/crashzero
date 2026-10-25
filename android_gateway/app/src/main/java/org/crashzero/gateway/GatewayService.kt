package org.crashzero.gateway

import android.Manifest
import android.app.*
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.IBinder
import android.telephony.PhoneStateListener
import android.telephony.TelephonyManager
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.*

class GatewayService:Service() {
    private val scope=CoroutineScope(SupervisorJob()+Dispatchers.IO);private var current:CallRequest?=null
    private var sawOffHook=false
    private lateinit var client:GatewayClient
    override fun onCreate(){super.onCreate();channel();listenForCallState()}
    override fun onStartCommand(intent:Intent?,flags:Int,startId:Int):Int {
        startForeground(100,notification("Monitoring for authenticated requests"));scope.launch { poll() };return START_STICKY
    }
    override fun onDestroy(){scope.cancel();super.onDestroy()}
    override fun onBind(intent:Intent?):IBinder?=null
    private suspend fun poll(){
        while(scope.isActive){
            val cfg=GatewayConfig.load(this);client=GatewayClient(cfg)
            try { val request=client.next();if(request!=null) handle(request,cfg) }
            catch(e:Exception){GatewayConfig.appendLog(this,"Polling error: ${e.javaClass.simpleName}")}
            delay(3000)
        }
    }
    private suspend fun handle(request:CallRequest,cfg:GatewayConfig){
        current=request;sawOffHook=false;client.status(request.id,"RECEIVED","Request authenticated by Android gateway")
        if(!PhoneSafety.allowed(request.destination)||PhoneSafety.digits(request.destination)!=PhoneSafety.digits(cfg.destination)){
            client.status(request.id,"FAILED","Destination does not match the phone's approved number");return
        }
        val permitted=ContextCompat.checkSelfPermission(this,Manifest.permission.CALL_PHONE)==PackageManager.PERMISSION_GRANTED
        if(cfg.automatic&&permitted&&request.kind!="verified_test"){
            try { client.status(request.id,"DIALING_REQUESTED","Android ACTION_CALL submitted; remote answer is not yet known")
                startActivity(Intent(Intent.ACTION_CALL,Uri.parse("tel:${Uri.encode(request.destination)}")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                GatewayConfig.appendLog(this,"Dialing requested for ${request.incidentId ?: "test"}")
            } catch(e:Exception){
                GatewayConfig.appendLog(this,"Automatic dial blocked: ${e.javaClass.simpleName}; showing confirmation fallback")
                showManualDial(request)
                client.status(request.id,"REQUIRES_CONFIRMATION","Android blocked automatic dialing; manual confirmation opened")
            }
        } else {
            showManualDial(request)
            client.status(request.id,"REQUIRES_CONFIRMATION","Automatic calling disabled or CALL_PHONE permission unavailable")
        }
    }
    private fun showManualDial(request:CallRequest){
        val dial=Intent(Intent.ACTION_DIAL,Uri.parse("tel:${Uri.encode(request.destination)}"))
        val pending=PendingIntent.getActivity(this,request.id.hashCode(),dial,PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val note=NotificationCompat.Builder(this,"crashzero_calls").setSmallIcon(android.R.drawable.sym_action_call)
            .setContentTitle("CrashZero call needs confirmation").setContentText(request.message.take(100)).setContentIntent(pending).setAutoCancel(true).build()
        getSystemService(NotificationManager::class.java).notify(request.id.hashCode(),note)
    }
    @Suppress("DEPRECATION") private fun listenForCallState(){
        if(ContextCompat.checkSelfPermission(this,Manifest.permission.READ_PHONE_STATE)!=PackageManager.PERMISSION_GRANTED)return
        getSystemService(TelephonyManager::class.java).listen(object:PhoneStateListener(){
            override fun onCallStateChanged(state:Int,number:String?){
                val request=current?:return
                scope.launch { try {
                    if(state==TelephonyManager.CALL_STATE_OFFHOOK){sawOffHook=true;client.status(request.id,"CALL_ACTIVE","Device reports OFFHOOK; remote answer is not guaranteed")}
                    if(state==TelephonyManager.CALL_STATE_IDLE&&sawOffHook){client.status(request.id,"CALL_ENDED","Device returned to IDLE");current=null;sawOffHook=false}
                }catch(_:Exception){} }
            }
        },PhoneStateListener.LISTEN_CALL_STATE)
    }
    private fun channel(){
        val manager=getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("crashzero_gateway","Gateway monitoring",NotificationManager.IMPORTANCE_LOW))
        manager.createNotificationChannel(NotificationChannel("crashzero_calls","Call requests",NotificationManager.IMPORTANCE_HIGH))
    }
    private fun notification(text:String)=NotificationCompat.Builder(this,"crashzero_gateway").setSmallIcon(android.R.drawable.stat_notify_sync)
        .setContentTitle("CrashZero Gateway").setContentText(text).setOngoing(true).build()
}
