package ru.liftcontrol.liftcontrol_mobile

import android.content.ActivityNotFoundException
import android.content.Intent
import androidx.core.content.FileProvider
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.util.UUID

class MainActivity : FlutterActivity() {
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        DeviceBridge.notifyOpen(this)
    }
    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        DeviceBridge.attach(this, flutterEngine)
        val directory = File(cacheDir, "liftcontrol").apply { mkdirs() }
        directory.listFiles()?.filter { System.currentTimeMillis() - it.lastModified() > 24 * 60 * 60 * 1000L }?.forEach { it.delete() }
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "ru.liftcontrol.app/files")
            .setMethodCallHandler { call, result ->
                try {
                    when (call.method) {
                        "openPdf" -> {
                            val bytes = call.argument<ByteArray>("bytes")
                            if (bytes == null || bytes.size > 32 * 1024 * 1024 || bytes.size < 5 ||
                                String(bytes.copyOfRange(0, 5), Charsets.US_ASCII) != "%PDF-") {
                                result.error("FORMAT", "Файл PDF повреждён или слишком большой.", null)
                            } else {
                                val file = File(directory, "${UUID.randomUUID()}.pdf")
                                file.outputStream().use { it.write(bytes) }
                                val uri = FileProvider.getUriForFile(this, "$packageName.files", file)
                                val intent = Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/pdf")
                                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                                startActivity(Intent.createChooser(intent, "Открыть документацию"))
                                result.success(null)
                            }
                        }
                        "shareReport" -> {
                            val text = call.argument<String>("text") ?: ""
                            if (text.length > 128 * 1024) {
                                result.error("LIMIT", "Отчёт слишком большой.", null)
                            } else {
                                startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).apply {
                                    type = "text/plain"
                                    putExtra(Intent.EXTRA_SUBJECT, "LiftControl: диагностический отчёт")
                                    putExtra(Intent.EXTRA_TEXT, text)
                                }, "Поделиться отчётом"))
                                result.success(null)
                            }
                        }
                        "clearPrivateFiles" -> {
                            directory.listFiles()?.forEach { it.delete() }
                            result.success(null)
                        }
                        else -> result.notImplemented()
                    }
                } catch (_: ActivityNotFoundException) {
                    result.error("NO_VIEWER", "На устройстве нет приложения для открытия этого файла.", null)
                } catch (_: Exception) {
                    result.error("FILE_ERROR", "Не удалось открыть или передать файл.", null)
                }
            }
    }
}
