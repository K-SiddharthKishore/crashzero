package org.crashzero.gateway

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.ViewGroup
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.*

class MainActivity : AppCompatActivity() {
    private lateinit var server:EditText; private lateinit var token:EditText; private lateinit var destination:EditText
    private lateinit var automatic:Switch; private lateinit var status:TextView; private lateinit var logs:TextView
    override fun onCreate(state:Bundle?) {
        super.onCreate(state);title="CrashZero Gateway"
        val config=GatewayConfig.load(this);val root=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL;setPadding(36,36,36,36) }
        fun field(hint:String,value:String)=EditText(this).also { it.hint=hint;it.setText(value);root.addView(it,ViewGroup.LayoutParams(-1,-2)) }
        root.addView(TextView(this).apply { text="CRASHZERO GATEWAY";textSize=26f;setTextColor(Color.rgb(16,61,92)) })
        root.addView(TextView(this).apply { text="Local SIM calling gateway · physical-device verification required" })
        server=field("Server URL, e.g. http://192.168.1.2:8766",config.server)
        token=field("Pairing token (32+ characters)",config.token)
        destination=field("Approved receiving number",config.destination)
        automatic=Switch(this).apply { text="Enable automatic calling";isChecked=config.automatic;root.addView(this) }
        root.addView(TextView(this).apply { text="Calling permission: "+if(ContextCompat.checkSelfPermission(this@MainActivity,Manifest.permission.CALL_PHONE)==PackageManager.PERMISSION_GRANTED) "granted" else "not granted" })
        status=TextView(this).apply { text="Monitoring stopped";setPadding(0,18,0,18);root.addView(this) }
        val row=LinearLayout(this)
        row.addView(Button(this).apply { text="Start Monitoring";setOnClickListener { save();permissions();ContextCompat.startForegroundService(this@MainActivity,Intent(this@MainActivity,GatewayService::class.java));status.text="Monitoring requested" } })
        row.addView(Button(this).apply { text="Stop";setOnClickListener { stopService(Intent(this@MainActivity,GatewayService::class.java));status.text="Monitoring stopped" } })
        root.addView(row)
        root.addView(Button(this).apply { text="Test Connection";setOnClickListener { save();lifecycleTest() } })
        root.addView(Button(this).apply { text="Test Call From Phone";setOnClickListener { save();localTestCall() } })
        root.addView(TextView(this).apply { text="History and errors";textSize=18f;setPadding(0,24,0,8) })
        logs=TextView(this);root.addView(logs)
        setContentView(ScrollView(this).apply { addView(root) });refreshLogs()
    }
    private fun save()=GatewayConfig.save(this,GatewayConfig(server.text.toString(),token.text.toString(),destination.text.toString(),automatic.isChecked))
    private fun permissions() {
        val wanted=arrayOf(Manifest.permission.CALL_PHONE,Manifest.permission.READ_PHONE_STATE,Manifest.permission.POST_NOTIFICATIONS)
        ActivityCompat.requestPermissions(this,wanted,41)
    }
    private fun lifecycleTest() { CoroutineScope(Dispatchers.Main).launch { status.text=try { if(GatewayClient(GatewayConfig.load(this@MainActivity)).health()) "Connected and authenticated" else "Server rejected connection" } catch(e:Exception) { "Connection failed: ${e.javaClass.simpleName}" } } }
    private fun localTestCall() {
        val number=destination.text.toString();if(!PhoneSafety.allowed(number)){status.text="Rejected: enter a non-emergency approved number";return}
        val direct=automatic.isChecked && ContextCompat.checkSelfPermission(this,Manifest.permission.CALL_PHONE)==PackageManager.PERMISSION_GRANTED
        startActivity(Intent(if(direct) Intent.ACTION_CALL else Intent.ACTION_DIAL,Uri.parse("tel:${Uri.encode(number)}")))
        GatewayConfig.appendLog(this,if(direct) "Local test dialing requested" else "Local test opened manual dial confirmation");refreshLogs()
    }
    private fun refreshLogs(){logs.text=GatewayConfig.logs(this)}
}

object PhoneSafety {
    private val emergency=setOf("112","100","101","102","108","911")
    fun digits(value:String)=value.filter { it.isDigit() }
    fun allowed(value:String):Boolean { val d=digits(value);return d.length>=8 && d !in emergency }
}
