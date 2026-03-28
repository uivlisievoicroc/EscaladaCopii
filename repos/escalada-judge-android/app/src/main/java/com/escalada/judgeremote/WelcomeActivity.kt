package com.escalada.judgeremote

import android.R.string.cancel
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.text.InputType
import android.widget.EditText
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import com.escalada.judgeremote.databinding.ActivityWelcomeBinding
import com.google.android.material.dialog.MaterialAlertDialogBuilder

class WelcomeActivity : AppCompatActivity() {
    private lateinit var binding: ActivityWelcomeBinding
    private val prefs by lazy { getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE) }

    private val scanQrLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            val scannedContent =
                result.data?.getStringExtra(SCAN_RESULT_EXTRA)?.trim().orEmpty()
            if (scannedContent.isBlank()) {
                return@registerForActivityResult
            }
            val normalized = normalizeUrl(scannedContent)
            if (normalized == null) {
                Toast.makeText(this, R.string.toast_invalid_qr_url, Toast.LENGTH_SHORT).show()
                return@registerForActivityResult
            }
            openJudge(normalized)
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityWelcomeBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.scanQrButton.setOnClickListener {
            launchQrScanner()
        }
        binding.enterUrlButton.setOnClickListener {
            showManualUrlDialog()
        }
    }

    private fun launchQrScanner() {
        val scanIntent =
            Intent(SCAN_ACTION).apply {
                putExtra(SCAN_MODE_EXTRA, QR_CODE_MODE)
                putExtra(PROMPT_MESSAGE_EXTRA, getString(R.string.scan_qr_prompt))
            }

        if (scanIntent.resolveActivity(packageManager) == null) {
            Toast.makeText(this, R.string.toast_missing_scanner_app, Toast.LENGTH_SHORT).show()
            return
        }

        scanQrLauncher.launch(scanIntent)
    }

    private fun showManualUrlDialog() {
        val input =
            EditText(this).apply {
                hint = getString(R.string.url_hint)
                inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
                isSingleLine = true
                setText(prefs.getString(PREF_LAST_URL, "").orEmpty())
                setSelection(text?.length ?: 0)
            }

        MaterialAlertDialogBuilder(this)
            .setTitle(R.string.dialog_enter_url_title)
            .setView(input)
            .setPositiveButton(R.string.dialog_connect_button) { _, _ ->
                val normalized = normalizeUrl(input.text?.toString().orEmpty())
                if (normalized == null) {
                    Toast.makeText(this, R.string.toast_invalid_url, Toast.LENGTH_SHORT).show()
                    return@setPositiveButton
                }
                openJudge(normalized)
            }
            .setNegativeButton(cancel, null)
            .show()
    }

    private fun openJudge(url: String) {
        startActivity(
            Intent(this, MainActivity::class.java).putExtra(EXTRA_JUDGE_URL, url),
        )
        finish()
    }

    companion object {
        private const val SCAN_ACTION = "com.google.zxing.client.android.SCAN"
        private const val SCAN_MODE_EXTRA = "SCAN_MODE"
        private const val QR_CODE_MODE = "QR_CODE_MODE"
        private const val SCAN_RESULT_EXTRA = "SCAN_RESULT"
        private const val PROMPT_MESSAGE_EXTRA = "PROMPT_MESSAGE"
    }
}
